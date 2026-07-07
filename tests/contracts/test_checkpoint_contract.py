"""The durable cross-file contract between the lever-2 rebirth checkpoint PROSE
(drive.md, drive-review.md, drive-harden.md) and the SCRIPT (bin/drive-conformance.sh)
— AC8 (test part), AC10, and the string pins named in AC4/5/6/7/9. A drift on EITHER
side (a renamed violation, a dropped reconstruction rule, a reordered harden Step 4)
breaks a test here.

Two kinds of pin: SCRIPT-side contracts are asserted BEHAVIORALLY (build a git +
RUN_DIR fixture, run `drive-conformance.sh --mode checkpoint`, assert its JSON / exit
code — the mode name, the `counters` derivation, and every violation NAME the prose
references must resolve in the shipped script). PROSE-ONLY coordinator contracts (the
reconstruction rules, the REDESIGN epoch-marker ordering, the sessionId rebind, the
single-use marker, adopt-needs-both-voices, the read-only harden Step-4 ordering) are
NOT script-executable — they are pinned by string assertions on the shipped prose so a
later edit cannot silently drop them.
"""
import json
import re
import shutil
import subprocess

import pytest

from _helpers import REPO_ROOT, _git, _rev, _commit, _review, _codex

CONFORMANCE = REPO_ROOT / "bin" / "drive-conformance.sh"
DRIVE_MD = REPO_ROOT / ".claude" / "commands" / "drive.md"
DRIVE_REVIEW_MD = REPO_ROOT / ".claude" / "commands" / "drive-review.md"
DRIVE_HARDEN_MD = REPO_ROOT / ".claude" / "commands" / "drive-harden.md"


# --------------------------------------------------------------------------- #
# Lazy file-text accessors (read once, cached).
# --------------------------------------------------------------------------- #
def _text(path):
    assert path.is_file(), f"expected file at {path}"
    return path.read_text(encoding="utf-8")


def _drive_md():
    return _text(DRIVE_MD)


def _drive_review_md():
    return _text(DRIVE_REVIEW_MD)


def _drive_harden_md():
    return _text(DRIVE_HARDEN_MD)


def _conformance():
    return _text(CONFORMANCE)


def _norm(text):
    """Collapse runs of whitespace (incl. newlines) to a single space so a prose phrase
    pin is robust to wrapping/reflow but still load-bearing on the words themselves."""
    return re.sub(r"\s+", " ", text)


# --------------------------------------------------------------------------- #
# SCRIPT-side: drive a real --mode checkpoint over a tempdir fixture.
# These replicate test/fixtures/mkfixture.sh::mk_checkpoint shapes in python so the
# behavioral contract is provable from the pytest suite alone. The script REQUIRES cwd
# inside the fixture git repo (it resolves git/<runId> refs relative to cwd).
# --------------------------------------------------------------------------- #
pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("bash") is None,
    reason="needs git + bash to exercise drive-conformance.sh",
)


def _harden(rd, p, n, applied):
    (rd / f"harden-{p}-{n}.md").write_text(
        f"# Harden phase {p} {n}\n## Verdict: HARDENED\n## AppliedEdits: {applied}\n",
        encoding="utf-8",
    )


def _marked_review(rd, scope, n, sha, verdict="CONVERGED"):
    """A harden-regress review file matching the REAL writer schema (drive-review.md:133-136):
    a header preamble carrying `## Verdict:`, `reviewed-sha: <sha>`, and the column-0
    `harden-regress: yes` marker (strictly BEFORE `## Findings`), followed by the
    always-present `## Findings` header. The header sha binds under the delimiter-required
    `reviewed_sha_of`, and the marker (in the header preamble) reads MARKED under the §1.3
    header-region classifier. LOCAL to this test file on purpose: the shared
    `_helpers._review` stays the UNMARKED integration writer (no marker), so the two helpers
    are the marked/unmarked pair the marker/distinct-sha contract counts. `sha` must be a
    valid 40-hex (distinct marked shas come from `"a"*40` vs `"b"*40`)."""
    (rd / f"review-{scope}-{n}.md").write_text(
        f"# Review {scope} round {n}\n\n## Verdict: {verdict}\n\n"
        f"reviewed-sha: {sha}\nharden-regress: yes\n## Findings\n\nNo open P1.\n",
        encoding="utf-8",
    )


def _findings_review(rd, scope, n, sha, verdict="CONVERGED"):
    """A well-formed UNMARKED review matching the REAL writer schema (drive-review.md:133-136):
    a header preamble (`## Verdict:` + `reviewed-sha: <sha>`) followed by the always-present
    `## Findings` header, so the header sha binds under the delimiter-required
    `reviewed_sha_of`. LOCAL to this file: the shared `_helpers._review` predates the
    `## Findings` schema pin (its reviewed-sha is never consumed by a tip-binding gate in any
    test) and stays untouched; use THIS helper wherever a legit review's sha must bind a gate."""
    (rd / f"review-{scope}-{n}.md").write_text(
        f"# Review {scope} round {n}\n\n## Verdict: {verdict}\n\n"
        f"reviewed-sha: {sha}\n## Findings\n\nNo open P1.\n",
        encoding="utf-8",
    )


def _no_findings_body_sha_review(rd, scope, n, tip):
    """A MALFORMED review with NO `## Findings` header at all: its header carries NO
    `reviewed-sha:` line; the ONLY `reviewed-sha: <tip>` is a fenced BODY quote. The real
    writer ALWAYS emits `## Findings` (drive-review.md:136 / drive-finalize.md:202), so a
    review lacking it is malformed. Under the pre-fix awk (which ran to EOF when `## Findings`
    was absent) this body sha bound == tip; the delimiter-required reader emits the header
    region ONLY when `## Findings` is seen → no `## Findings` → NO sha (fail-closed). Distinct
    from `_body_only_sha_review`, which HAS `## Findings` and quotes the sha BELOW it — this
    fixture is the no-`## Findings` gap the round-3 BLOCKING reopened."""
    (rd / f"review-{scope}-{n}.md").write_text(
        f"# Review {scope} round {n}\n## Verdict: CONVERGED\n"
        f"Body prose (no Findings header). The writer emits it like:\n"
        f"```\nreviewed-sha: {tip}\n```\nend.\n",
        encoding="utf-8",
    )


def _redesign_marker(rd, p, r):
    (rd / f"redesign-{p}-r{r}.marker").write_text(
        json.dumps({"phase": p, "epoch": r}) + "\n", encoding="utf-8"
    )


def _inflight(rd, ks):
    (rd / f"inflight-{ks}.marker").write_text(
        json.dumps({"kind": "x", "scope": "x", "runId": "x",
                    "sessionId": None, "startedAt": "now"}) + "\n",
        encoding="utf-8",
    )


def _base_run(tmp_path, name):
    """A repo on a `drive/<name>` branch + an empty RUN_DIR named <name> (so runId =
    basename(RUN_DIR) = name → featureBranch = drive/<name>). Returns (repo, rd)."""
    repo = tmp_path / f"{name}-repo"
    rd = tmp_path / name
    repo.mkdir(parents=True)
    rd.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "README", "base", "base")
    _git(repo, "checkout", "-q", "-b", f"drive/{name}")
    _commit(repo, "drive.sh", "echo drive", "drive work")
    return repo, rd


def _run_checkpoint(repo, rd):
    """Run the checkpoint mode from inside the repo; return (returncode, parsed-json)."""
    proc = subprocess.run(
        ["bash", str(CONFORMANCE), str(rd), "--mode", "checkpoint"],
        cwd=str(repo), capture_output=True, text=True,
    )
    assert proc.stdout.strip(), f"no JSON on stdout (stderr={proc.stderr!r})"
    return proc.returncode, json.loads(proc.stdout)


def _run_mode(repo, rd, mode):
    """Run an arbitrary conformance mode (e.g. `phase-merge:1`, `ship`) from inside the
    repo; return (returncode, parsed-json). Same driver as `_run_checkpoint`, generalized
    so the header-bound reviewed-sha contract can be proven on the SIBLING gates that also
    consume `reviewed_sha_of` — not just `--mode checkpoint`."""
    proc = subprocess.run(
        ["bash", str(CONFORMANCE), str(rd), "--mode", mode],
        cwd=str(repo), capture_output=True, text=True,
    )
    assert proc.stdout.strip(), f"no JSON on stdout (stderr={proc.stderr!r})"
    return proc.returncode, json.loads(proc.stdout)


def _body_only_sha_review(rd, scope, tip):
    """Write `review-<scope>-<1>.md` whose header is CONVERGED but carries NO header
    `reviewed-sha:` — the ONLY `reviewed-sha: <tip>` line is a fenced BODY quote BELOW
    `## Findings`. Under the pre-fix whole-file `reviewed_sha_of` this body sha == tip
    would satisfy the gate's tip-binding; under the header-bound reader it is invisible."""
    (rd / f"review-{scope}-1.md").write_text(
        f"# Review {scope} round 1\n## Verdict: CONVERGED\n"
        f"## Findings\nThe writer emits it like:\n```\nreviewed-sha: {tip}\n```\nend.\n",
        encoding="utf-8",
    )


def _reasons(obj):
    return {v["reason"] for v in obj["violations"]}


def _viol(scope, reason, exp="", found=""):
    """The exact violation-object shape the script's `violation()` helper emits — all four
    keys always present (expected/found default to empty strings). Asserting the FULL
    `violations` list against these catches a right-reason/wrong-scope, an extra, OR a
    duplicate violation that a `reason in _reasons()` membership check would pass."""
    return {"scope": scope, "reason": reason,
            "expected_sha": exp, "found_sha": found}


def test_checkpoint_clean_fixture_passes_with_counters(tmp_path):
    """AC1/AC3 (behavioral cross-file contract): a quiescent, well-formed run is clean
    (exit 0) and emits `counters` derived per the I3 rules — reviewCount from
    pure-integer-N files; phaseReviewRound = count of review-phase files WITHOUT the
    harden-regress marker (no subtraction); hardenRound counts ONLY `yes`;
    phaseDesignRound from the epoch-0 family. This is the pure integration-only clean
    baseline (all `_review` files are UNMARKED); marked-file paths are exercised by the
    surplus/deficit/dedup fixtures below."""
    repo, rd = _base_run(tmp_path, "ckpt-clean")
    _git(repo, "checkout", "-q", "-b", "phaseInt/ckpt-clean/1")
    _commit(repo, "phase.sh", "echo p1", "phase 1 integration")
    _review(rd, "design", 1)
    _review(rd, "1.1", 1)
    _review(rd, "1.1", 2)
    (rd / "review-1.1-final.md").write_text("notes, not a round file\n", encoding="utf-8")
    _review(rd, "phase1", 1)
    _review(rd, "phase1", 2)
    _review(rd, "phase1", 3)
    _harden(rd, 1, 1, "yes")
    _harden(rd, 1, 2, "no")
    _review(rd, "phasedesign1", 1)

    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 0, f"clean fixture should exit 0; got {rc} / {obj}"
    assert obj["clean"] is True
    assert obj["mode"] == "checkpoint"
    # `tip` is load-bearing: the checkpoint-complete.marker's `proof.tip` is validated
    # against it at resume. Assert it resolves to the live featureBranch (drive/<runId>)
    # tip exactly — a broken/empty tip would silently break marker validation.
    assert obj["tip"] == _rev(repo, "drive/ckpt-clean"), obj
    counters = obj["counters"]
    assert counters["reviewCount"] == {"1.1": 2}, counters
    # 3 UNMARKED integration files → 3 rounds (marker-aware; no subtraction, independent of
    # harden-yes — the harden-regress marker, not a yes-count subtraction, is what separates
    # a regress review from an integration review).
    assert counters["phaseReviewRound"] == {"1": 3}, counters
    assert counters["hardenRound"] == {"1": 1}, counters        # one yes, one no
    assert counters["phaseDesignRound"] == {"1": 1}, counters   # epoch-0 family
    assert counters["redesigns"] == {}, counters


def test_checkpoint_never_reads_state_json(tmp_path):
    """AC1/AC4 + criterion 4's behavioral 'never reads state.json' contract: the clean
    verdict and counters are byte-identical whether state.json is corrupt garbage,
    deleted, or claims a DIFFERENT redesigns count. The mode is a pure git+artifact
    function — state.json is never a proof input."""
    repo, rd = _base_run(tmp_path, "ckpt-nostate")
    _git(repo, "checkout", "-q", "-b", "phaseInt/ckpt-nostate/1")
    _commit(repo, "phase.sh", "echo p1", "phase 1 integration")
    _review(rd, "1.1", 1)
    _review(rd, "phase1", 1)

    # corrupt state.json
    (rd / "state.json").write_text("CORRUPT-NOT-JSON{{{\n", encoding="utf-8")
    rc_corrupt, obj_corrupt = _run_checkpoint(repo, rd)
    # a valid state.json claiming a wildly different counter
    (rd / "state.json").write_text(
        json.dumps({"phaseReview": {"1": {"round": 99, "hardenRound": 99}},
                    "slices": {"1.1": {"reviewCount": 99}},
                    "phaseDesign": {"1": {"redesigns": 7}}}) + "\n",
        encoding="utf-8",
    )
    rc_valid, obj_valid = _run_checkpoint(repo, rd)
    # no state.json at all
    (rd / "state.json").unlink()
    rc_absent, obj_absent = _run_checkpoint(repo, rd)

    assert rc_corrupt == rc_valid == rc_absent == 0
    assert obj_corrupt["counters"] == obj_valid["counters"] == obj_absent["counters"], (
        "counters must be derived from artifacts ONLY — state.json must not change them"
    )
    assert obj_valid["counters"]["reviewCount"] == {"1.1": 1}
    assert obj_valid["counters"]["redesigns"] == {}


def test_checkpoint_inflight_open_violation(tmp_path):
    """AC1: any open `inflight-*.marker` → violation `inflight-open`, exit 1 — the
    proof never probes liveness; an open marker is 'not safe', full stop."""
    repo, rd = _base_run(tmp_path, "ckpt-inflight")
    _review(rd, "phase1", 1)
    _inflight(rd, "review-phase1")
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 1 and obj["clean"] is False
    # EXACT: one inflight-open violation, scope = the marker's basename, no shas, no extras.
    assert obj["violations"] == [
        _viol("inflight-review-phase1.marker", "inflight-open")
    ], obj["violations"]


def test_checkpoint_regress_mismatch_fires_on_surplus(tmp_path):
    """AC5 (SURPLUS guard): `distinct-marked-sha > harden-yes` is unambiguously malformed
    (each fix round dispatches exactly one regress review, so the marked count can never
    legitimately exceed the yes-count) → exactly one `regress-mismatch` on `phase1`, exit 1.
    2 marked regress files at DISTINCT shas + 1 harden-yes ⇒ 2 > 1 fires. The integration
    round is `count(unmarked)` = 1 and is NOT clamped to 0 even while the guard fires — the
    DD2 guard: the round stays the honest unmarked count, disjoint from the marked surplus."""
    repo, rd = _base_run(tmp_path, "ckpt-surplus")
    _review(rd, "phase1", 1)                              # 1 UNMARKED integration file
    _marked_review(rd, "phase1", 2, sha="a" * 40)         # marked regress, sha a
    _marked_review(rd, "phase1", 3, sha="b" * 40)         # marked regress, sha b (distinct)
    _harden(rd, 1, 1, "yes")                              # 1 fix round
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 1
    # EXACT: exactly one regress-mismatch on scope `phase1`, no shas, nothing else.
    assert obj["violations"] == [
        _viol("phase1", "regress-mismatch")
    ], obj["violations"]
    # NOT clamped to 0: integration-round = count(unmarked) = 1, independent of the surplus.
    assert obj["counters"]["phaseReviewRound"] == {"1": 1}, obj["counters"]


def test_checkpoint_regress_deficit_is_benign(tmp_path):
    """AC5 (DEFICIT is NOT a fire): `distinct-marked-sha < harden-yes` (a drop / mid-harden
    crash window / legacy phase) is diagnosed, never STOPped by the guard. These are the OLD
    subtraction-era inputs (1 review-phase + 2 harden-yes) — under the marker/distinct-sha
    reader they INVERT: 0 marked > 2 yes is FALSE → no fire, clean, round = count(unmarked)
    = 1 (NOT clamped to 0 as the reverted subtraction would have)."""
    repo, rd = _base_run(tmp_path, "ckpt-deficit")
    _review(rd, "phase1", 1)                              # 1 UNMARKED integration file
    _harden(rd, 1, 1, "yes")
    _harden(rd, 1, 2, "yes")                              # 2 yes, 0 marked → deficit
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 0, f"a deficit must be benign (no fire); got {obj}"
    assert obj["clean"] is True
    assert "regress-mismatch" not in _reasons(obj), obj["violations"]
    assert obj["counters"]["phaseReviewRound"] == {"1": 1}, obj["counters"]


def test_checkpoint_marker_classifies_marked_vs_unmarked_and_body_fenced(tmp_path):
    """AC2 (header-region, value-anchored classification): a `harden-regress: yes` line
    counts as a marked regress ONLY when it appears in the header preamble (before the first
    `## Findings`). A marker quoted in the review BODY — inside a fenced code block AFTER
    `## Findings` (the reverse-collision this feature's OWN review triggers) — classifies
    UNMARKED. Behavioral proof: an unmarked integration file + a header-marked file at a
    distinct sha + a body-fenced-quote file ⇒ marked-regress counts ONLY the header-marked
    one (distinct-sha = 1), and the body-fenced file counts toward the integration round.

    Mutation-verify (non-vacuous vs the base subtraction reader): 3 review-phase files, 2
    harden-yes ⇒ the OLD `files − yes` reader would give `3 − 2 = 1`, but the marker reader
    counts `count(unmarked) = 2` — so `phaseReviewRound == {"1": 2}` REDs on the base
    subtraction code and only greens under the marker classifier."""
    repo, rd = _base_run(tmp_path, "ckpt-classify")
    _review(rd, "phase1", 1)                              # UNMARKED integration
    _marked_review(rd, "phase1", 2, sha="a" * 40)         # header-MARKED regress
    # A file whose exact `harden-regress: yes` line sits inside a fenced block BELOW the
    # `## Findings` header — must classify UNMARKED (header-region bound), else it would
    # inflate distinct-marked-sha and false-fire the surplus guard.
    (rd / "review-phase1-3.md").write_text(
        "# Review phase1 round 3\n\n## Verdict: FINDINGS\n\nreviewed-sha: " + "c" * 40 +
        "\n## Findings\nThe writer emits it like:\n```\nharden-regress: yes\n```\nend.\n",
        encoding="utf-8",
    )
    _harden(rd, 1, 1, "yes")                              # 2 harden-yes: distinct-marked 1 ≤ 2,
    _harden(rd, 1, 2, "yes")                              # and `files − yes = 1` ≠ count(unmarked)
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 0, f"only the header-marked file is a regress → clean; got {obj}"
    assert "regress-mismatch" not in _reasons(obj), obj["violations"]
    # 2 unmarked integration files (the plain _review + the body-fenced-quote file) → round 2.
    # DIVERGES from the base `3 − 2 = 1` subtraction, so this asserts the marker reader, not
    # a value both readers happen to produce.
    assert obj["counters"]["phaseReviewRound"] == {"1": 2}, obj["counters"]


def test_checkpoint_negative_classifier_variants_all_unmarked(tmp_path):
    """codex P1 (AC2 negative branches): the `^harden-regress:[[:space:]]*yes[[:space:]]*$`
    header-region, column-0, VALUE-exact anchor classifies these three near-miss header
    occurrences as UNMARKED (integration), NOT marked regress:
      (a) `harden-regress: no`  — value is `no`, not `yes`;
      (b) `  harden-regress: yes` INDENTED — not column-0 (`^` anchor);
      (c) a prose mention of `harden-regress` before `## Findings` — not a standalone `= yes` line.
    Each is a well-formed parseable review (header sha + `## Findings`) at a DISTINCT sha with
    ZERO harden-yes, so if ANY misclassified MARKED its distinct sha would make
    `distinct-marked-sha ≥ 1 > harden-yes = 0` → a `regress-mismatch` fire. All UNMARKED ⇒ no
    fire, clean, integration-round = count(unmarked) = 3.

    Mutation-verify (REDs under a LOOSER anchor): drop the value-check (`^harden-regress:` only)
    → (a) marks; drop the column-0 `^` (`harden-regress:...yes`) → (b) marks; use a bare
    substring (`grep -q harden-regress`) → (c) marks — any of these turns this fixture into a
    surplus fire (rc 1), so the clean/round-3 assertion is non-vacuous on the exact anchor."""
    repo, rd = _base_run(tmp_path, "ckpt-negclass")
    # (a) value `no` in the header preamble (after reviewed-sha, before ## Findings)
    (rd / "review-phase1-1.md").write_text(
        "# Review phase1 round 1\n## Verdict: CONVERGED\nreviewed-sha: " + "a" * 40 +
        "\nharden-regress: no\n## Findings\n\nNo open P1.\n",
        encoding="utf-8",
    )
    # (b) INDENTED `harden-regress: yes` (leading whitespace → not column-0)
    (rd / "review-phase1-2.md").write_text(
        "# Review phase1 round 2\n## Verdict: CONVERGED\nreviewed-sha: " + "b" * 40 +
        "\n  harden-regress: yes\n## Findings\n\nNo open P1.\n",
        encoding="utf-8",
    )
    # (c) prose occurrence of the token before ## Findings (not a standalone `= yes` line)
    (rd / "review-phase1-3.md").write_text(
        "# Review phase1 round 3\n## Verdict: CONVERGED\nreviewed-sha: " + "c" * 40 +
        "\nThis phase used a harden-regress review earlier; nothing marked here.\n"
        "## Findings\n\nNo open P1.\n",
        encoding="utf-8",
    )
    # ZERO harden-yes: any misclassified-marked file makes distinct-marked-sha > 0 → fire.
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 0, f"all three near-miss files must classify UNMARKED → clean; got {obj}"
    assert obj["clean"] is True, obj
    assert "regress-mismatch" not in _reasons(obj), obj["violations"]
    # all three are UNMARKED integration files → integration round = 3.
    assert obj["counters"]["phaseReviewRound"] == {"1": 3}, obj["counters"]


def test_checkpoint_marked_file_body_only_sha_is_unparseable(tmp_path):
    """Round-6 boundary completion (was `...body_only_sha_excluded_from_distinct`): a MARKED
    review-phase file (header `harden-regress: yes` above `## Findings`) whose ONLY
    `reviewed-sha:` line is a fenced BODY quote BELOW `## Findings` — NO header-region sha — is
    now `unparseable-review`, NOT silently excluded-and-clean. The completed boundary requires a
    valid header-region `reviewed-sha:` anchor: a marked file whose header sha reads EMPTY is
    exactly the silent-bucketing hole (its empty sha dropped from `distinct_marked_sha` could hide
    a real surplus), so it is rejected fail-closed at the boundary rather than absorbed.

    (The real writer ALWAYS emits `reviewed-sha:` in the header preamble above `## Findings`;
    a body-only-sha file is malformed/forged, so rejecting it breaks no legit review — this
    tightens the round-5 "excluded → clean" contract, which is why that older assertion is
    superseded here.)

    Mutation-verify (REDs on the round-5 code lacking the reviewed-sha requirement): pre-fix the
    empty header sha was excluded from distinct → `0 > 0` FALSE → CLEAN (rc 0) with
    `phaseReviewRound == {"1": 0}`. The completed boundary flags it `unparseable-review`, rc 1."""
    repo, rd = _base_run(tmp_path, "ckpt-bodysha")
    # MARKED in the header (harden-regress: yes strictly above ## Findings) but the ONLY
    # reviewed-sha is a body quote in a fenced block BELOW ## Findings → NO header sha anchor.
    (rd / "review-phase1-1.md").write_text(
        "# Review phase1 round 1\n## Verdict: CONVERGED\nharden-regress: yes\n"
        "## Findings\nThe writer emits it like:\n```\nreviewed-sha: " + "a" * 40 +
        "\n```\nend.\n",
        encoding="utf-8",
    )
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 1, f"body-only sha on a marked file lacks the header sha anchor → unparseable; got {obj}"
    assert obj["clean"] is False, obj
    # EXACT: unparseable-review at the boundary, NOT bucketed (no distinct sha, no round).
    assert obj["violations"] == [
        _viol("review-phase1-1.md", "unparseable-review")
    ], obj["violations"]
    assert obj["counters"]["phaseReviewRound"] == {}, obj["counters"]


def test_checkpoint_no_findings_review_phase_unparseable_body_marker(tmp_path):
    """Round-5 BLOCKING root fix (PARSEABILITY BOUNDARY — `## Findings` REQUIRED for a
    review-phase<P> file, mirroring the `## Verdict:` requirement): a MALFORMED review with NO
    `## Findings` header — here with a `harden-regress: yes` line quoted in a fenced BODY block —
    is NOT silently bucketed. The round-4 behavior (fail-closed to UNMARKED, counted as
    integration) was itself UNSAFE: a no-`## Findings` file cannot be safely classified (a marked
    file truncated after the marker but before the delimiter would read UNMARKED → its sha drops
    from distinct_marked_sha, hiding a real surplus). The fix flags it `unparseable-review` at the
    boundary → checkpoint NOT clean (rc 1) → the run STOPs for stranded-marker recovery / a human.

    Mutation-verify (REDs on the pre-fix code that lacked the `## Findings` parseability
    requirement — it read this file clean/UNMARKED with `phaseReviewRound == {"1": 1}`): the fix
    yields exactly one `unparseable-review` on the offending file, rc 1, NOT clean."""
    repo, rd = _base_run(tmp_path, "ckpt-nofindings-marker")
    # `## Verdict: CONVERGED`, NO `## Findings` header at all; a `harden-regress: yes` line sits
    # in a fenced BODY quote — malformed either way; the boundary rejects it on the missing
    # delimiter alone (independent of the marker).
    (rd / "review-phase1-1.md").write_text(
        "# Review phase1 round 1\n## Verdict: CONVERGED\n"
        "Body prose (no Findings header). The writer emits it like:\n"
        "```\nharden-regress: yes\n```\nend.\n",
        encoding="utf-8",
    )
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 1, f"a no-Findings review-phase file must be unparseable (not clean); got {obj}"
    assert obj["clean"] is False, obj
    # EXACT: one unparseable-review on the offending file's basename, no shas, no extras. The file
    # is NOT bucketed, so it contributes no integration round.
    assert obj["violations"] == [
        _viol("review-phase1-1.md", "unparseable-review")
    ], obj["violations"]
    assert obj["counters"]["phaseReviewRound"] == {}, obj["counters"]


def test_phase_merge_body_only_sha_not_tip_bound(tmp_path):
    """MAJOR-fix regression pin (unify sibling gates on the header-bound reviewed-sha reader):
    the build-time `--mode phase-merge:<P>` gate (via `check_scope_counts` → `reviewed_sha_of`)
    must NOT accept a phase review whose ONLY `reviewed-sha: <tip>` is a fenced BODY quote below
    `## Findings` — matching `--mode checkpoint`'s header-only contract. Otherwise a body-only-sha
    review would satisfy merge tip-binding but not checkpoint (the inconsistency codex flagged).

    Mutation-verify (REDs on the pre-fix whole-file `reviewed_sha_of`): the body sha EQUALS the
    real `phaseInt/<runId>/1` tip. The pre-fix whole-file read finds it → `rsha == tip` → the
    scope COUNTS → gate CLEAN (rc 0). The header-bound read yields NO header sha → `reviewed_sha_of`
    rc1 → `sha-mismatch` → the scope does NOT count → gate BLOCKS (rc 1)."""
    repo, rd = _base_run(tmp_path, "pm-bodysha")
    _git(repo, "checkout", "-q", "-b", "phaseInt/pm-bodysha/1")
    _commit(repo, "phase.sh", "echo p1", "phase 1 integration")
    tip = _rev(repo, "phaseInt/pm-bodysha/1")
    _body_only_sha_review(rd, "phase1", tip)
    _codex(rd, "phase1")   # present so the pre-fix reader would reach a CLEAN verdict

    rc, obj = _run_mode(repo, rd, "phase-merge:1")
    assert rc == 1, f"body-only sha must not tip-bind phase-merge → block; got {obj}"
    assert "sha-mismatch" in _reasons(obj), obj["violations"]


def test_ship_body_only_sha_phase_review_not_counted(tmp_path):
    """MAJOR-fix regression pin (ship b-i + finalize b-ii on the header-bound reader): a phase
    review AND the finalize review whose ONLY `reviewed-sha` is a fenced BODY quote must NOT
    satisfy ship's tip-binding — b-i's `candidate_R` (via `reviewed_sha_of`) stays empty →
    `no-phase-review`. Under the pre-fix whole-file reader the body sha would populate
    `candidate_R` → b-i passes and ship falls through to the finalize check.

    Mutation-verify (REDs on the pre-fix reader): with a body-only-sha phase review + codex, the
    pre-fix read counts it (b-i satisfied) and — no finalize artifact → `no-review`. The
    header-bound read leaves `candidate_R` empty at b-i → `no-phase-review`. Asserting the
    b-i-specific reason pins that the phase reader (not just finalize) is header-bound."""
    repo, rd = _base_run(tmp_path, "ship-bodysha")
    _git(repo, "checkout", "-q", "-b", "phaseInt/ship-bodysha/1")
    _commit(repo, "phase.sh", "echo p1", "phase 1 integration")
    _git(repo, "checkout", "-q", "drive/ship-bodysha")
    tip = _rev(repo, "phaseInt/ship-bodysha/1")
    _body_only_sha_review(rd, "phase1", tip)
    _codex(rd, "phase1")

    rc, obj = _run_mode(repo, rd, "ship")
    assert rc == 1, f"body-only sha phase review must not satisfy ship b-i; got {obj}"
    assert "no-phase-review" in _reasons(obj), obj["violations"]


# --------------------------------------------------------------------------- #
# round-3 BLOCKING regression: the NO-`## Findings` gap (speculative EOF fallback).
# The round-2 body-only pins above use `_body_only_sha_review`, which HAS a `## Findings`
# header. The reopened bypass is a review with NO `## Findings` at all: the pre-fix
# `reviewed_sha_of` awk (`/^## Findings/ { exit } { print }`) ran to EOF and accepted a
# `reviewed-sha:` ANYWHERE (fenced/body). The fix REQUIRES the `## Findings` delimiter to
# bound the header (emit the header region ONLY when `## Findings` is seen), so a malformed
# no-`## Findings` review binds NO tip anywhere — proven on ALL FOUR reviewed_sha_of
# consumers: checkpoint (distinct_marked_sha), phase-merge + ship b-i + finalize b-ii.
# Each is mutation-verified against the pre-fix EOF fallback below.
# --------------------------------------------------------------------------- #

def test_checkpoint_no_findings_review_phase_unparseable_header_marker(tmp_path):
    """Round-5 BLOCKING root fix (PARSEABILITY BOUNDARY — the header-marker arm): a review with
    the `harden-regress: yes` marker in the header region BUT NO `## Findings` header at all is
    MALFORMED and must be flagged `unparseable-review` — NOT silently bucketed. This is precisely
    the crash-window / forgery the boundary closes: a marked-INTENT review truncated before the
    `## Findings` delimiter. The round-4 behavior (fail-closed to UNMARKED) hid such a file's
    reviewed-sha from distinct_marked_sha, which could mask a real surplus; the fix rejects it at
    the boundary instead (checkpoint rc 1, not clean).

    Mutation-verify (REDs on the pre-fix code lacking the `## Findings` parseability requirement —
    it read this file clean/UNMARKED with `phaseReviewRound == {"1": 1}`): the fix yields exactly
    one `unparseable-review`, rc 1, NOT clean."""
    repo, rd = _base_run(tmp_path, "ckpt-nofind")
    # `harden-regress: yes` in the header region, NO `## Findings` anywhere; the only
    # reviewed-sha is a fenced body quote. Malformed → unparseable at the boundary.
    (rd / "review-phase1-1.md").write_text(
        "# Review phase1 round 1\n## Verdict: CONVERGED\nharden-regress: yes\n"
        "Body prose (no Findings header):\n```\nreviewed-sha: " + "a" * 40 + "\n```\nend.\n",
        encoding="utf-8",
    )
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 1, f"a no-Findings review-phase file must be unparseable (not clean); got {obj}"
    assert obj["clean"] is False, obj
    # EXACT: one unparseable-review; the file is not bucketed (no integration round, no sha into
    # the surplus guard).
    assert obj["violations"] == [
        _viol("review-phase1-1.md", "unparseable-review")
    ], obj["violations"]
    assert obj["counters"]["phaseReviewRound"] == {}, obj["counters"]


def test_checkpoint_no_findings_plain_review_phase_unparseable(tmp_path):
    """Root-fix boundary (marker-AGNOSTIC): even a PLAIN, NON-marked review-phase file with a
    valid `## Verdict:` header + `reviewed-sha:` but NO `## Findings` header is
    `unparseable-review`. The requirement is structural (the delimiter must be present), not
    conditional on a marker — a valid-verdict file reaching the counter path without the
    delimiter would otherwise be silently bucketed UNMARKED, the exact silent path the boundary
    closes (and the shape a marked review truncated before `## Findings` degenerates to).

    Mutation-verify (REDs on the pre-fix code lacking the `## Findings` requirement — it read
    this file clean/UNMARKED with `phaseReviewRound == {"1": 1}`): the fix flags it, rc 1."""
    repo, rd = _base_run(tmp_path, "ckpt-nofind-plain")
    (rd / "review-phase1-1.md").write_text(
        "# Review phase1 round 1\n## Verdict: CONVERGED\nreviewed-sha: " + "a" * 40 +
        "\nno findings header here\n",
        encoding="utf-8",
    )
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 1, f"a plain no-Findings review-phase file must be unparseable; got {obj}"
    assert obj["clean"] is False, obj
    assert obj["violations"] == [
        _viol("review-phase1-1.md", "unparseable-review")
    ], obj["violations"]
    assert obj["counters"]["phaseReviewRound"] == {}, obj["counters"]


def test_checkpoint_surplus_marked_missing_findings_is_unparseable_not_hidden(tmp_path):
    """Codex's round-5 reproduction, CLOSED. The surplus scenario
    (`test_checkpoint_regress_mismatch_fires_on_surplus`: 2 marked distinct-sha reviews + 1
    harden-yes → `regress-mismatch`) must NOT be silently suppressed by dropping `## Findings`
    from one marked review. Pre-fix, a no-`## Findings` marked file fell into the UNMARKED bucket
    (its sha dropped from distinct_marked_sha), so `2 > 1` collapsed to `1 > 1` FALSE → CLEAN,
    HIDING the surplus. With the parseability boundary the malformed file is `unparseable-review`
    (rc 1, not clean) — the surplus is never hidden.

    Mutation-verify (REDs on the pre-fix code: it read CLEAN with `phaseReviewRound == {"1": 1}`
    and NO unparseable-review — exactly codex's suppression): the fix flags the malformed file."""
    repo, rd = _base_run(tmp_path, "ckpt-surplus-nofind")
    _marked_review(rd, "phase1", 1, sha="a" * 40)         # well-formed marked regress, sha a
    # The SECOND marked regress (DISTINCT sha b) with `## Findings` REMOVED — the exact mutation
    # from the surplus repro (a crash after the marker, or a forgery). Pre-fix it fell UNMARKED
    # (sha b dropped from distinct_marked_sha) → 2>1 collapsed to 1>1 FALSE → clean, hiding it.
    (rd / "review-phase1-2.md").write_text(
        "# Review phase1 round 2\n## Verdict: CONVERGED\nreviewed-sha: " + "b" * 40 +
        "\nharden-regress: yes\nno findings header\n",
        encoding="utf-8",
    )
    _harden(rd, 1, 1, "yes")                              # 1 fix round
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 1, f"a marked review missing ## Findings must be unparseable, not hidden; got {obj}"
    assert obj["clean"] is False, obj
    # EXACT: the malformed file is flagged unparseable-review (not silently absorbed into the
    # buckets). The well-formed marked `a` (distinct=1) ≤ harden-yes 1 → no regress-mismatch.
    assert obj["violations"] == [
        _viol("review-phase1-2.md", "unparseable-review")
    ], obj["violations"]


def test_checkpoint_surplus_marked_missing_sha_is_unparseable_not_hidden(tmp_path):
    """Round-6 BLOCKING (PARSEABILITY BOUNDARY COMPLETED — the reviewed-sha anchor). Codex's
    round-6 reproduction, CLOSED: a review-phase file with `## Verdict:` + `## Findings` +
    `harden-regress: yes` but NO `reviewed-sha:` line was STILL silently bucketed after round-5
    (which only required `## Findings`). The marked path swallowed the missing sha into `msha=""`,
    which the `$2!=""` filter drops from distinct_marked_sha → a real surplus is HIDDEN.

    Scenario (codex's (i)): 1 well-formed marked regress (sha a) + 1 marked regress with NO
    reviewed-sha + 1 harden-yes. Pre-fix (round-5 code), the no-sha marked file bucketed marked
    with an empty sha → distinct_marked_sha counts only `a` = 1 ≤ harden-yes 1 → NO fire, CLEAN,
    `phaseReviewRound == {"1": 0}` (both marked, 0 unmarked) — the surplus SILENTLY hidden. The
    completed boundary flags the no-sha file `unparseable-review` (rc 1, not clean) instead.

    Mutation-verify (REDs on the round-5 code lacking the reviewed-sha requirement): pre-fix reads
    CLEAN with NO unparseable-review and `phaseReviewRound == {"1": 0}` — exactly codex's silent
    bucketing. The fix flags the malformed file, rc 1."""
    repo, rd = _base_run(tmp_path, "ckpt-surplus-nosha")
    _marked_review(rd, "phase1", 1, sha="a" * 40)         # well-formed marked regress, sha a
    # A SECOND marked regress with `## Verdict:` + `## Findings` + the header marker but NO
    # `reviewed-sha:` line at all — the exact sibling-omission codex reproduced (a crash before
    # the sha, or a forgery). Pre-fix it bucketed marked with an empty sha (dropped from the
    # distinct set) → the `a`-only distinct=1 ≤ harden-yes 1 → surplus hidden.
    (rd / "review-phase1-2.md").write_text(
        "# Review phase1 round 2\n\n## Verdict: CONVERGED\n\n"
        "harden-regress: yes\n## Findings\n\nNo open P1.\n",
        encoding="utf-8",
    )
    _harden(rd, 1, 1, "yes")                              # 1 fix round
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 1, f"a marked review missing reviewed-sha must be unparseable, not hidden; got {obj}"
    assert obj["clean"] is False, obj
    # EXACT: the malformed file is flagged unparseable-review (not silently absorbed into the
    # buckets). The well-formed marked `a` (distinct=1) ≤ harden-yes 1 → no regress-mismatch.
    assert obj["violations"] == [
        _viol("review-phase1-2.md", "unparseable-review")
    ], obj["violations"]
    # NOT bucketed: the no-sha file contributes neither an integration round nor a distinct sha.
    assert obj["counters"]["phaseReviewRound"] == {"1": 0}, obj["counters"]


def test_checkpoint_unmarked_review_phase_missing_sha_is_unparseable(tmp_path):
    """Round-6 BLOCKING (PARSEABILITY BOUNDARY COMPLETED — the UNMARKED arm). Codex's (ii): an
    UNMARKED (integration) review-phase file with `## Verdict:` + `## Findings` but NO
    `reviewed-sha:` line must be `unparseable-review` — NOT silently counted toward the round.

    Pre-fix (round-5 code, which only required `## Verdict:` + `## Findings`) this file passed the
    boundary, read UNMARKED, and counted toward the integration round → CLEAN with
    `phaseReviewRound == {"1": 1}`. The completed boundary requires the reviewed-sha anchor too, so
    an integration file omitting its sha is rejected fail-closed.

    Mutation-verify (REDs on the round-5 code): pre-fix reads CLEAN with NO unparseable-review and
    `phaseReviewRound == {"1": 1}`. The fix flags it, rc 1, and does NOT bucket it."""
    repo, rd = _base_run(tmp_path, "ckpt-unmarked-nosha")
    # UNMARKED (no `harden-regress:` marker), well-formed `## Verdict:` + `## Findings`, but NO
    # `reviewed-sha:` line anywhere in the header preamble.
    (rd / "review-phase1-1.md").write_text(
        "# Review phase1 round 1\n\n## Verdict: CONVERGED\n\n## Findings\n\nNo open P1.\n",
        encoding="utf-8",
    )
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 1, f"an unmarked review-phase file missing reviewed-sha must be unparseable; got {obj}"
    assert obj["clean"] is False, obj
    assert obj["violations"] == [
        _viol("review-phase1-1.md", "unparseable-review")
    ], obj["violations"]
    # NOT bucketed: contributes no integration round.
    assert obj["counters"]["phaseReviewRound"] == {}, obj["counters"]


def test_phase_merge_no_findings_body_sha_not_tip_bound(tmp_path):
    """round-3 BLOCKING (phase-merge arm): the `--mode phase-merge:<P>` gate (via
    `check_scope_counts` → `reviewed_sha_of`) must NOT accept a phase review with NO
    `## Findings` header whose only `reviewed-sha: <tip>` is a fenced body quote.

    Mutation-verify (REDs on the pre-fix EOF fallback): the body sha EQUALS the real
    `phaseInt/<runId>/1` tip → the pre-fix EOF read finds it → `rsha == tip` → the scope
    COUNTS → gate CLEAN (rc 0). The delimiter-required read yields NO sha → `sha-mismatch`
    → gate BLOCKS (rc 1)."""
    repo, rd = _base_run(tmp_path, "pm-nofind")
    _git(repo, "checkout", "-q", "-b", "phaseInt/pm-nofind/1")
    _commit(repo, "phase.sh", "echo p1", "phase 1 integration")
    tip = _rev(repo, "phaseInt/pm-nofind/1")
    _no_findings_body_sha_review(rd, "phase1", 1, tip)
    _codex(rd, "phase1")   # present so the pre-fix reader would reach a CLEAN verdict

    rc, obj = _run_mode(repo, rd, "phase-merge:1")
    assert rc == 1, f"no-Findings body sha must not tip-bind phase-merge → block; got {obj}"
    assert "sha-mismatch" in _reasons(obj), obj["violations"]


def test_ship_no_findings_body_sha_phase_review_not_counted(tmp_path):
    """round-3 BLOCKING (ship b-i arm): a phase review with NO `## Findings` header whose
    only `reviewed-sha` is a fenced body quote must NOT satisfy ship's b-i precondition —
    `candidate_R` (via `reviewed_sha_of`) stays empty → `no-phase-review`.

    Mutation-verify (REDs on the pre-fix EOF fallback): the pre-fix read counts the body sha
    (b-i satisfied) and — no finalize artifact → `no-review`. The delimiter-required read
    leaves `candidate_R` empty at b-i → `no-phase-review` (pins the phase reader, not just
    finalize, is delimiter-bound)."""
    repo, rd = _base_run(tmp_path, "ship-nofind")
    _git(repo, "checkout", "-q", "-b", "phaseInt/ship-nofind/1")
    _commit(repo, "phase.sh", "echo p1", "phase 1 integration")
    _git(repo, "checkout", "-q", "drive/ship-nofind")
    tip = _rev(repo, "phaseInt/ship-nofind/1")
    _no_findings_body_sha_review(rd, "phase1", 1, tip)
    _codex(rd, "phase1")

    rc, obj = _run_mode(repo, rd, "ship")
    assert rc == 1, f"no-Findings body sha phase review must not satisfy ship b-i; got {obj}"
    assert "no-phase-review" in _reasons(obj), obj["violations"]


def test_ship_no_findings_finalize_review_not_tip_bound(tmp_path):
    """round-3 BLOCKING (finalize / ship b-ii arm): with a VALID counting phase review
    (so b-i passes), a finalize review with NO `## Findings` header whose only
    `reviewed-sha: <tip>` is a fenced body quote must NOT bind the terminal candidate-R —
    `reviewed_sha_of(fin_rf)` fails → `candidate_R=""` → ship blocks with `no-review`.

    Mutation-verify (REDs on the pre-fix EOF fallback): the finalize body sha EQUALS the
    featureBranch tip → the pre-fix EOF read binds it → R == tip → (a) ancestor, (b) empty
    diff ⊆ allowlist, (c) 0 commits → ship_clean → CLEAN (rc 0). The delimiter-required read
    yields NO finalize sha → `candidate_R` empty → `no-review` (rc 1)."""
    repo, rd = _base_run(tmp_path, "ship-fin-nofind")
    tip = _rev(repo, "drive/ship-fin-nofind")
    # b-i satisfied by a well-formed CONVERGED phase review (header sha + ## Findings) + codex.
    _findings_review(rd, "phase1", 1, sha="a" * 40)
    _codex(rd, "phase1")
    # b-ii finalize candidate: NO ## Findings, sha only in the body, == featureBranch tip
    # (so the pre-fix reader would satisfy (a)(b)(c) and ship clean).
    _no_findings_body_sha_review(rd, "finalize", 1, tip)
    _codex(rd, "finalize")

    rc, obj = _run_mode(repo, rd, "ship")
    assert rc == 1, f"no-Findings finalize review must not tip-bind ship b-ii; got {obj}"
    assert "no-review" in _reasons(obj), obj["violations"]


def test_ship_body_only_sha_finalize_review_not_tip_bound(tmp_path):
    """codex P1 (finalize / ship b-ii arm, the WITH-`## Findings` variant the matrix missed):
    with a VALID counting phase review (so b-i passes), a finalize review that HAS a NORMAL
    `## Findings` header but whose ONLY `reviewed-sha: <tip>` is a fenced BODY quote BELOW
    `## Findings` must NOT bind the terminal candidate-R — `reviewed_sha_of(fin_rf)` reads the
    header region ONLY (empty here) → `candidate_R=""` → ship blocks with `no-review`. The
    sibling `test_ship_no_findings_finalize_review_not_tip_bound` covers the NO-`## Findings`
    variant; this is the b-ii finalize case with `## Findings` present (codex verified the
    script already blocks it — this is the missing behavioral pin).

    Mutation-verify (REDs on a whole-file `reviewed_sha_of`): the finalize body sha EQUALS the
    featureBranch tip, so a whole-file read would bind R == tip → (a) ancestor, (b) empty diff
    ⊆ allowlist, (c) 0 commits → ship clean (rc 0). The header-bound read yields NO finalize
    sha → `candidate_R` empty → `no-review` (rc 1)."""
    repo, rd = _base_run(tmp_path, "ship-fin-bodysha")
    tip = _rev(repo, "drive/ship-fin-bodysha")
    # b-i satisfied by a well-formed CONVERGED phase review (header sha + ## Findings) + codex.
    _findings_review(rd, "phase1", 1, sha="a" * 40)
    _codex(rd, "phase1")
    # b-ii finalize candidate: HAS `## Findings`, sha ONLY in a fenced BODY quote BELOW it,
    # == featureBranch tip (so a whole-file reader would satisfy (a)(b)(c) and ship clean).
    _body_only_sha_review(rd, "finalize", tip)
    _codex(rd, "finalize")

    rc, obj = _run_mode(repo, rd, "ship")
    assert rc == 1, f"body-only-sha finalize review (with ## Findings) must not tip-bind ship b-ii; got {obj}"
    assert "no-review" in _reasons(obj), obj["violations"]


def test_checkpoint_distinct_sha_dedup(tmp_path):
    """AC4 (distinct-reviewed-sha dedup): two MARKED files at the SAME `reviewed-sha` count
    as ONE regress round (a stranded dual-voice re-dispatch that appended a duplicate marked
    file at the same tip is deduped) — so 2 marked-same-sha + 1 harden-yes is `1 > 1` FALSE
    → clean; whereas two marked files at DISTINCT shas would be `2 > 1` → fire. The dedup is
    what makes the surplus guard immune to stranded-review duplication (protects the NORMAL
    harden loop, not just the heal)."""
    repo, rd = _base_run(tmp_path, "ckpt-dedup")
    _marked_review(rd, "phase1", 1, sha="a" * 40)         # same sha
    _marked_review(rd, "phase1", 2, sha="a" * 40)         # duplicate of the SAME tip
    _harden(rd, 1, 1, "yes")
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 0, f"two marked files at the same sha dedupe to 1 ≤ 1 yes → clean; got {obj}"
    assert "regress-mismatch" not in _reasons(obj), obj["violations"]
    # Both files are marked → neither counts toward the integration round.
    assert obj["counters"]["phaseReviewRound"] == {"1": 0}, obj["counters"]


def test_checkpoint_backward_compat_no_marked_no_baseSha(tmp_path):
    """AC6 (backward-compat is inherent): a legacy run with NO marked review-phase files (and
    no state.baseSha) is checkpoint-clean w.r.t. `regress-mismatch` (`0 ≤ harden-yes`), and
    its old unmarked regress files count toward the integration round — no era field, no
    fallback branch. 2 unmarked review-phase + 2 harden-yes ⇒ 0 marked > 2 is FALSE → clean,
    round = count(unmarked) = 2."""
    repo, rd = _base_run(tmp_path, "ckpt-legacy")
    _review(rd, "phase1", 1)
    _review(rd, "phase1", 2)
    _harden(rd, 1, 1, "yes")
    _harden(rd, 1, 2, "yes")
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 0, f"a legacy no-marker run must be clean; got {obj}"
    assert "regress-mismatch" not in _reasons(obj), obj["violations"]
    assert obj["counters"]["phaseReviewRound"] == {"1": 2}, obj["counters"]


def test_checkpoint_open_inflight_heal_marker_not_clean(tmp_path):
    """AC13: an OPEN `inflight-heal-<P>.marker` makes `--mode checkpoint` report NOT clean
    (the `inflight-*.marker` glob emits `inflight-open`) — the consequence that gives the
    orphaned-heal-marker recovery teeth (the resume sweep must clear it before any
    Execute-boundary checkpoint, so no proof is ever taken against an open heal marker)."""
    repo, rd = _base_run(tmp_path, "ckpt-healmarker")
    _review(rd, "phase1", 1)
    _inflight(rd, "heal-1")
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 1 and obj["clean"] is False
    assert obj["violations"] == [
        _viol("inflight-heal-1.marker", "inflight-open")
    ], obj["violations"]


def test_checkpoint_epoch_gap_violation_and_highest_r(tmp_path):
    """AC2/AC4 (script half): markers r1 + r3 (r2 lost) → violation `epoch-gap`, and
    `redesigns` reconstructs as the HIGHEST epoch R (3), NOT the marker count (2) —
    proving the I3-rule-4 highest-R rule the prose states. A state.json claiming
    redesigns:2 does NOT change it (state never read)."""
    repo, rd = _base_run(tmp_path, "ckpt-epochgap")
    _redesign_marker(rd, 1, 1)
    _redesign_marker(rd, 1, 3)
    (rd / "state.json").write_text(
        json.dumps({"phaseDesign": {"1": {"redesigns": 2, "round": 0}}}) + "\n",
        encoding="utf-8",
    )
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 1
    # EXACT: a single epoch-gap on scope `redesign-1` (the loop breaks on the first gap, so
    # r1+r3 yields ONE violation, not two) — a duplicate or stray entry would fail here.
    assert obj["violations"] == [
        _viol("redesign-1", "epoch-gap")
    ], obj["violations"]
    assert obj["counters"]["redesigns"] == {"1": 3}, (
        "redesigns must reconstruct as highest-R (3), not the marker count (2)"
    )


def test_checkpoint_unparseable_review_violation(tmp_path):
    """AC1: a `review-<scope>-N.md` with no `## Verdict:` line → `unparseable-review`."""
    repo, rd = _base_run(tmp_path, "ckpt-unrev")
    (rd / "review-2.2-1.md").write_text(
        "# half-written review\nno verdict line here\n", encoding="utf-8"
    )
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 1
    # EXACT: one unparseable-review on the offending file's basename, no shas, no extras.
    assert obj["violations"] == [
        _viol("review-2.2-1.md", "unparseable-review")
    ], obj["violations"]


def test_checkpoint_unparseable_harden_violation(tmp_path):
    """AC1: a `harden-<P>-N.md` with no `AppliedEdits:` line → `unparseable-harden`."""
    repo, rd = _base_run(tmp_path, "ckpt-unharden")
    (rd / "harden-1-1.md").write_text(
        "# Harden phase 1 1\n## Verdict: HARDENED\n", encoding="utf-8"
    )
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 1
    # EXACT: one unparseable-harden on the offending file's basename, no shas, no extras.
    assert obj["violations"] == [
        _viol("harden-1-1.md", "unparseable-harden")
    ], obj["violations"]


def test_checkpoint_epoch_unmarked_violation(tmp_path):
    """AC1/AC9 (the D21 fail-closed contract): an epoch-suffixed phasedesign artifact
    (review + codex sibling) with NO matching `redesign-<P>-r<R>.marker` → violation
    `epoch-unmarked`, exit 1. Without the check, `highest_epoch()` falls back to a LOWER
    epoch and the run reads CLEAN on corruption — this pins the fail-closed behavior."""
    repo, rd = _base_run(tmp_path, "ckpt-unmarked")
    _review(rd, "phasedesign1", 1)            # epoch-0 pair (looks complete)
    _review(rd, "phasedesign1-r1", 1)         # r1 artifact with NO r1 marker
    _codex(rd, "phasedesign1-r1")
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 1
    # EXACT: one epoch-unmarked on scope `phasedesign1` (one per phase, deduped over both
    # the review and codex markerless artifacts), no shas, nothing else.
    assert obj["violations"] == [
        _viol("phasedesign1", "epoch-unmarked")
    ], obj["violations"]


def test_checkpoint_phaseint_divergent_violation(tmp_path):
    """AC1: a `phaseInt/<runId>/<P>` ref related to `drive/<runId>` in NEITHER ancestry
    direction → `phaseInt-divergent`. Built by cutting the phaseInt branch from `main`
    (not from drive) after drive moved on."""
    repo, rd = _base_run(tmp_path, "ckpt-divergent")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "phaseInt/ckpt-divergent/1")
    _commit(repo, "px.sh", "echo px", "divergent phase work")
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 1
    # EXACT: one phaseInt-divergent on the divergent ref, with expected_sha = drive tip and
    # found_sha = the phaseInt tip (this violation DOES carry shas — assert both, not just
    # the reason — so a wrong-sha or duplicate-ref regression is caught).
    drive_tip = _rev(repo, "drive/ckpt-divergent")
    pint_tip = _rev(repo, "phaseInt/ckpt-divergent/1")
    assert obj["tip"] == drive_tip
    assert obj["violations"] == [
        _viol("phaseInt/ckpt-divergent/1", "phaseInt-divergent", drive_tip, pint_tip)
    ], obj["violations"]


def test_checkpoint_nonnumeric_phase_id_4a_processed_not_skipped(tmp_path):
    """AC1/AC11 boundary (D18 ancestry, NO numeric phase-id ordering): the mode must
    actually PROCESS a non-numeric phase id `phaseInt/<runId>/4a`, not silently skip it.
    To make a skip observably fail, `4a` is built DIVERGENT (cut from `main`, non-ancestor
    of `drive/<runId>`): the real script must flag `phaseInt-divergent` for `phaseInt/.../4a`
    specifically. A numeric-only selection would skip `4a` and read CLEAN — proving that the
    flagged-divergent assertion is load-bearing on non-numeric processing (the behavioral
    proof is the companion test_..._verdict_flips_on_divergence: flip only `4a`'s divergence
    and the verdict differs, with NO coupling to the script source)."""
    repo, rd = _base_run(tmp_path, "ckpt-4a")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "phaseInt/ckpt-4a/4a")
    _commit(repo, "p4a.sh", "echo 4a", "phase 4a divergent integration")
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 1, f"divergent non-numeric 4a must be flagged (processed); got {obj}"
    drive_tip = _rev(repo, "drive/ckpt-4a")
    pint_tip = _rev(repo, "phaseInt/ckpt-4a/4a")
    assert obj["violations"] == [
        _viol("phaseInt/ckpt-4a/4a", "phaseInt-divergent", drive_tip, pint_tip)
    ], obj["violations"]


def test_checkpoint_nonnumeric_phase_id_4a_verdict_flips_on_divergence(tmp_path):
    """AC1/AC11 (companion to the divergent-4a case): the non-numeric `4a` id is PROCESSED,
    not skipped — proven BEHAVIORALLY by flipping only whether `phaseInt/<runId>/4a` is
    divergent and asserting the verdict differs, with NO coupling to drive-conformance.sh
    source text. A numeric-only selection would skip `4a` in BOTH builds and read CLEAN in
    both — so the verdict difference IS the proof the script handles the non-numeric id.
    Same fixture shape as the divergent case, but `4a` is cut FROM `drive/<runId>` (a
    descendant, fast-forwardable) → no divergence → CLEAN."""
    repo, rd = _base_run(tmp_path, "ckpt-4a-ff")
    # 4a as a DESCENDANT of drive/<runId> (cut from it, then commit forward): an ancestor
    # relation holds in one direction, so it is NOT phaseInt-divergent.
    _git(repo, "checkout", "-q", "-b", "phaseInt/ckpt-4a-ff/4a", "drive/ckpt-4a-ff")
    _commit(repo, "p4a.sh", "echo 4a", "phase 4a fast-forward integration")
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 0 and obj["clean"] is True and obj["violations"] == [], (
        f"a NON-divergent (descendant) non-numeric 4a must read CLEAN; got {obj}"
    )
    # The flip: identical fixture except 4a IS divergent (cut from main) → phaseInt-divergent.
    # If the script skipped the non-numeric id, BOTH builds would read CLEAN and the verdict
    # would NOT differ — so this difference proves the non-numeric id is processed.
    repo2, rd2 = _base_run(tmp_path, "ckpt-4a-div")
    _git(repo2, "checkout", "-q", "main")
    _git(repo2, "checkout", "-q", "-b", "phaseInt/ckpt-4a-div/4a")
    _commit(repo2, "p4a.sh", "echo 4a", "phase 4a divergent integration")
    rc2, obj2 = _run_checkpoint(repo2, rd2)
    assert rc2 == 1 and "phaseInt-divergent" in _reasons(obj2), (
        f"a divergent non-numeric 4a must be flagged phaseInt-divergent; got {obj2}"
    )
    # The verdicts differ on the SAME non-numeric id — the behavioral proof of processing.
    assert obj["clean"] != obj2["clean"]


def test_checkpoint_epoch_files_count_current_epoch_only(tmp_path):
    """AC2/AC4: with an r1 marker present, phaseDesignRound counts ONLY the current
    epoch's (`phasedesign1-r1`) round files; epoch-0 files don't count. r1 marker +
    1 epoch-0 file + 2 epoch-r1 files → phaseDesignRound {"1":2}, redesigns {"1":1}."""
    repo, rd = _base_run(tmp_path, "ckpt-epochfiles")
    _redesign_marker(rd, 1, 1)
    _review(rd, "phasedesign1", 1)            # epoch 0 — must NOT count
    _review(rd, "phasedesign1-r1", 1)
    _review(rd, "phasedesign1-r1", 2)
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 0, f"well-formed r1 epoch fixture should be clean; got {obj}"
    assert obj["counters"]["phaseDesignRound"] == {"1": 2}, obj["counters"]
    assert obj["counters"]["redesigns"] == {"1": 1}, obj["counters"]


def test_checkpoint_usage_error_exits_2(tmp_path):
    """AC1: a usage/IO error (a non-directory RUN_DIR) exits 2 — distinct from the
    1 = has-violations verdict, mirroring the script's documented envelope."""
    repo, _ = _base_run(tmp_path, "ckpt-usage")
    proc = subprocess.run(
        ["bash", str(CONFORMANCE), str(tmp_path / "does-not-exist"),
         "--mode", "checkpoint"],
        cwd=str(repo), capture_output=True, text=True,
    )
    assert proc.returncode == 2, f"missing RUN_DIR must exit 2; got {proc.returncode}"


def test_checkpoint_unresolvable_enumerated_ref_exits_2(tmp_path):
    """AC1: an enumerated `slice/<runId>/*` ref that for-each-ref LISTS but `rev` cannot
    resolve (a dangling ref → a missing object) is a genuine git/IO error, NOT a verdict —
    it must exit 2 (the ref-error path), distinct from the 1 = has-violations verdict and
    distinct from a clean exit 0. Without this split a corrupt ref would read as no-finding."""
    repo, rd = _base_run(tmp_path, "ckpt-referr")
    # plant a dangling loose ref under slice/<runId>/: for-each-ref lists it, but the sha
    # names no object so `git rev-parse <ref>^{commit}` fails → the loop's exit-2 path.
    ref_path = repo / ".git" / "refs" / "heads" / "slice" / "ckpt-referr" / "9.9"
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_text("dead" * 9 + "beef" + "\n", encoding="utf-8")  # 40 hex, no object
    # sanity: for-each-ref must surface it AND rev-parse must fail (so the exit-2 is real,
    # not a fixture that quietly resolves).
    listed = subprocess.run(
        ["git", "-C", str(repo), "for-each-ref", "--format=%(refname:short)",
         "refs/heads/slice/ckpt-referr/"],
        capture_output=True, text=True,
    ).stdout
    assert "slice/ckpt-referr/9.9" in listed, listed
    resolves = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet",
         "slice/ckpt-referr/9.9^{commit}"],
        capture_output=True, text=True,
    )
    assert resolves.returncode != 0, "fixture ref must be UNRESOLVABLE for the exit-2 path"

    proc = subprocess.run(
        ["bash", str(CONFORMANCE), str(rd), "--mode", "checkpoint"],
        cwd=str(repo), capture_output=True, text=True,
    )
    assert proc.returncode == 2, (
        f"unresolvable enumerated slice ref must exit 2 (git-error, not verdict); "
        f"got rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "cannot resolve slice ref" in proc.stderr, proc.stderr


# --------------------------------------------------------------------------- #
# CROSS-FILE NAME CONTRACT: every conformance mode / token / violation NAME the prose
# references must EXIST in the script (else the prose points at nothing). Anchored on the
# deterministic script source, not on generated output.
# --------------------------------------------------------------------------- #
def test_prose_references_mode_checkpoint_which_the_script_implements():
    """AC9 cross-file: drive.md names `--mode checkpoint`; the script's usage + dispatch
    must implement it. A drift renaming either side breaks the pair."""
    assert "--mode checkpoint" in _drive_md(), "drive.md must reference `--mode checkpoint`"
    conf = _conformance()
    assert "checkpoint)" in conf, "drive-conformance.sh must have a `checkpoint)` mode arm"
    assert "|checkpoint" in conf, "the script usage line must list the checkpoint mode"


def test_all_checkpoint_violation_names_emitted_by_script():
    """AC9 cross-file: every checkpoint violation NAME in the contract is a string the
    script can actually emit (the cross-slice contract the phase-integration holds). This
    is the load-bearing direction — the behavioral tests above trigger each, and this
    pins the literal token in the deterministic script source so a rename is caught even
    if a fixture stops reaching that branch."""
    conf = _conformance()
    for name in ("epoch-unmarked", "regress-mismatch", "epoch-gap",
                 "inflight-open", "unparseable-review", "unparseable-harden",
                 "phaseInt-divergent"):
        assert name in conf, f"drive-conformance.sh must emit the violation `{name}`"


def test_prose_referenced_violation_names_resolve_in_script():
    """AC9 cross-file: the violation names the coordinator PROSE cites (the reconstruction
    rules name `regress-mismatch` and `epoch-gap` as the malformed-counter flags) must
    resolve to real script violations — so the prose never points at a token the script
    can't emit. The other violations are script-internal and intentionally not surfaced
    in coordinator prose."""
    drive = _drive_md()
    conf = _conformance()
    for name in ("regress-mismatch", "epoch-gap"):
        assert name in drive, f"drive.md reconstruction rules must reference `{name}`"
        assert name in conf, f"drive-conformance.sh must emit the prose-named `{name}`"


def test_epoch_scope_token_form_in_prose_and_script():
    """AC9 cross-file: the epoch-aware scope token form `phasedesign<P>-r<R>` (R≥1; bare
    for epoch 0) appears in BOTH drive.md and drive-review.md as the prose contract, and
    the script resolves the same `phasedesign$P-r$R` shape. drive-review.md self-resolves
    the epoch (R = highest `redesign-<P>-r*.marker`)."""
    drive = _drive_md()
    review = _drive_review_md()
    conf = _conformance()
    assert "phasedesign<P>-r<R>" in drive, "drive.md must name the phasedesign<P>-r<R> token"
    assert "phasedesign<P>-r<R>" in review, "drive-review.md must name the token form"
    # the script builds the literal `phasedesign$P-r$R` scope and globs the marker family
    assert "phasedesign$P-r$R" in conf, (
        "drive-conformance.sh must build the epoch-qualified phasedesign scope"
    )
    assert "redesign-$P-r" in conf, "the script must scan the redesign-<P>-r*.marker family"


# --------------------------------------------------------------------------- #
# AC4/5/6 PROSE PINS — the five I3 reconstruction rules + the resume directives.
# --------------------------------------------------------------------------- #
def test_resume_repair_hint_sentence_verbatim():
    """AC4/AC6: the verbatim hint-never-proof sentence and the one-directional max rule —
    the contract that resume may RAISE a counter (tighten a cap) but never lower it."""
    blob = _norm(_drive_md())
    assert "state.json is a resume-repair HINT, never a proof input" in blob, (
        "drive.md must keep the verbatim 'state.json is a resume-repair HINT, never a "
        "proof input' sentence"
    )
    assert "max(state hint, artifact-derived value)" in blob, (
        "drive.md must state the one-directional max(state hint, artifact) repair rule"
    )


def test_five_reconstruction_rules_pinned():
    """AC4/AC6: all five I3 per-counter reconstruction rules are present, each pinned as
    its CONTIGUOUS formula clause (not scattered substrings) so a semantic rewrite that
    changes the derivation — e.g. reverting rule 2 to the old `MINUS … AppliedEdits: yes`
    subtraction instead of the marker-aware `WITHOUT the harden-regress: yes marker` count,
    or dropping the `HIGHEST epoch R` rule — breaks the pin. A dropped rule is a silent
    resume hole."""
    blob = _norm(_drive_md())
    # Each entry is the literal contiguous formula from drive.md's reconstruction list.
    rules = [
        # rule 1 — reviewCount derivation
        "`slices[<id>].reviewCount` = max(state, count of `review-<id>-N.md`, "
        "pure-integer N)",
        # rule 2 — phaseReview round = count of review-phase files WITHOUT the marker (no
        # subtraction; the harden-regress marker, not a yes-count subtraction, separates them)
        "`phaseReview[<P>].round` = max(state, count of `review-phase<P>-N.md` files "
        "(pure-integer N) WITHOUT the `harden-regress: yes` marker)",
        # rule 3 — hardenRound counts ONLY AppliedEdits: yes
        "`phaseReview[<P>].hardenRound` = max(state, count of `harden-<P>-*.md` with "
        "`AppliedEdits: yes`)",
        # rule 4 — redesigns = HIGHEST epoch R among the redesign markers
        "`phaseDesign[<P>].redesigns` = max(state, HIGHEST epoch R among "
        "`redesign-<P>-r*.marker`)",
        # rule 5 — phaseDesign round counts only the CURRENT-epoch round files
        "`phaseDesign[<P>].round` = max(state, count of `review-<T>-N.md`) where "
        "`T = phasedesign<P>` if artifact-derived redesigns == 0, else "
        "`phasedesign<P>-r<R>` for the current (highest) epoch R",
    ]
    for i, rule in enumerate(rules, 1):
        assert rule in blob, f"reconstruction rule {i} formula drifted or dropped:\n{rule}"


def _resume_section_text(md):
    """The body of drive.md's `## Run setup & resume` section, from the `- **Resume:**`
    bullet to the next `## ` heading — the span whose nested `- **<Label>:**` sub-bullets
    are the resume reconciliation steps. Returned with original newlines (not _norm'd) so a
    line-anchored bullet regex can enumerate them in document order."""
    start = md.index("- **Resume:**")
    end = md.index("\n## ", start)
    return md[start:end]


# A resume reconciliation sub-bullet: a nested (indented) `- **<Label>:**` line. The
# top-level `- **Resume:**` bullet is at column 0; its children are indented, so the
# leading-whitespace requirement excludes the parent and matches only the steps.
_RESUME_BULLET_RE = re.compile(r"^[ \t]+- \*\*(.+?):\*\*", re.MULTILINE)


def test_sessionId_rebind_is_first_resume_bullet():
    """AC6 (I7): resume opens with the sessionId rebind — rewrite state.sessionId to the
    live $CLAUDE_CODE_SESSION_ID on ANY new-session resume, BEFORE reconciling. Pinned as
    the FIRST resume directive so a reorder that delays hook-attribution is caught."""
    blob = _norm(_drive_md())
    assert "sessionId rebind (FIRST, on ANY resume into a new session)" in blob, (
        "drive.md resume must open with the FIRST sessionId-rebind bullet"
    )
    assert "rewrite `state.sessionId` to the live `$CLAUDE_CODE_SESSION_ID`" in blob
    # STRUCTURAL FIRST-ness (not just the parenthetical label, and not merely "before two
    # named siblings"): enumerate EVERY resume sub-bullet in document order and assert the
    # rebind bullet is the minimum-index one — so a NEW bullet inserted ahead of the rebind
    # (which a `rebind < marker < phase` ordering check would pass) breaks the pin.
    section = _resume_section_text(_drive_md())
    labels = _RESUME_BULLET_RE.findall(section)
    assert len(labels) >= 5, f"expected the resume sub-bullets to enumerate; got {labels}"
    rebind_idx = next(
        (i for i, lbl in enumerate(labels) if lbl.startswith("sessionId rebind")), None
    )
    assert rebind_idx is not None, f"no sessionId-rebind sub-bullet found among {labels}"
    assert rebind_idx == 0, (
        "the sessionId-rebind bullet must be the FIRST resume sub-bullet (minimum index "
        f"among ALL resume steps), not just ahead of two named siblings; got order {labels}"
    )


def test_checkpoint_marker_consumption_single_use():
    """AC6/AC7 (D17): the checkpoint-complete.marker is consumed at resume — validate
    (parse + proof.tip == current tip) then DELETE, single-use, record-not-authorization
    (tip-match necessary, NOT sufficient)."""
    blob = _norm(_drive_md())
    assert "checkpoint-complete.marker" in blob
    assert "SINGLE-USE" in blob, "the marker must be pinned SINGLE-USE"
    assert "A proof RECORD, never an authorization" in blob
    assert "necessary, NOT sufficient" in blob, (
        "tip-match must be pinned necessary-but-not-sufficient"
    )


def test_derived_phasedesign_status_and_resume_redesign_cap():
    """AC6 (D16): resume DERIVES phase-design convergence from the epoch-aware
    phasedesign-gate (status is a hint, never the trigger), and re-derives the
    redesigns >= 3 STOP at resume."""
    blob = _norm(_drive_md())
    assert "Derived phase-design status" in blob
    assert "phasedesign-gate:<P>" in blob, (
        "resume must delegate convergence to the epoch-aware phasedesign-gate mode"
    )
    assert "is a hint, never the trigger" in blob
    assert "redesigns >= 3" in blob, "the resume-side redesign-cap STOP must be pinned"


# --------------------------------------------------------------------------- #
# AC5 PROSE PIN — REDESIGN handler epoch-marker ordering.
# --------------------------------------------------------------------------- #
def test_redesign_handler_marker_before_state_mutation():
    """AC5: the REDESIGN handler writes the epoch marker as its FIRST action, create-only
    + tmp/`mv`, strictly BEFORE the redesigns/round mutation; STOP on already-exists; the
    marker-write → state-write span is one atomic step. Round-reconstruction soundness (the
    rule-2 derivation) depends on this ordering."""
    blob = _norm(_drive_md())
    assert "redesign-<P>-r<R>.marker" in blob
    assert "create-only" in blob, "the epoch marker must be pinned create-only"
    assert "marker already exists → STOP" in blob, "STOP on already-exists must be pinned"
    # ordering: the marker write precedes the redesigns/round mutation
    assert "BEFORE the `redesigns`/`round` mutation" in blob, (
        "the marker must be written BEFORE the redesigns/round state mutation"
    )
    assert "one atomic step" in blob


# --------------------------------------------------------------------------- #
# AC6/AC7 PROSE PIN — stranded-marker recovery (adopt needs BOTH voices).
# --------------------------------------------------------------------------- #
def test_stranded_marker_adopt_requires_both_voices_never_wait():
    """AC6/AC7 (D12 amended): stranded-marker recovery is adopt / re-dispatch / STOP —
    NEVER wait; adopt of a review unit requires BOTH the Claude review file AND its
    non-empty codex sibling. Adopting a half-finished dual-voice chain would wedge the
    next gate."""
    blob = _norm(_drive_md())
    assert "adopt / re-dispatch / STOP" in blob, "recovery order must be pinned"
    assert "never wait" in blob.lower(), "recovery must be pinned 'never wait'"
    # adopt of a review unit needs both the review file AND the codex sibling
    assert "review-<scope>-N.md" in blob
    assert "codex-review-<scope>.md" in blob
    assert "unfinished dual-voice chain" in blob, (
        "a review file WITHOUT its codex sibling must be pinned as unfinished → re-dispatch"
    )


# --------------------------------------------------------------------------- #
# AC7 PROSE PIN — durable checkpoint contract section (safe boundary, prove-then-pause).
# --------------------------------------------------------------------------- #
def test_durable_checkpoint_contract_section_present():
    """AC7: the Durable checkpoint contract section pins the safe-boundary definition,
    the assemble/advance no-marker rationale, write-before-dispatch/clear-after-record,
    and the prove-then-pause ordering with `stop:checkpoint-unprovable`."""
    blob = _norm(_drive_md())
    assert "Durable checkpoint contract" in blob
    assert "Safe boundary" in blob
    assert "no open `inflight-*.marker`" in blob
    assert "Write-before-dispatch, clear-after-record" in blob
    assert "Prove-then-pause" in blob
    assert "stop:checkpoint-unprovable" in blob, (
        "the failing-proof STOP reason must be pinned"
    )
    # the assemble/advance no-marker rationale (the two steps that carry no marker)
    assert "carry NO marker" in blob


# --------------------------------------------------------------------------- #
# AC9 PROSE PIN — drive-review.md epoch self-resolution + drive.md graph/gate family.
# --------------------------------------------------------------------------- #
def test_drive_review_self_resolves_epoch():
    """AC9 (D19): drive-review.md defines the epoch-qualified token AND self-resolves R
    (highest redesign-<P>-r*.marker; bare for epoch 0); invokers pass `phase <P> design`
    unchanged. This is the single derivation point that closes the post-REDESIGN wedge."""
    blob = _norm(_drive_review_md())
    assert "Resolve the phasedesign token's redesign epoch YOURSELF" in blob, (
        "drive-review.md must self-resolve the epoch"
    )
    assert "highest epoch among `$RUN_DIR/redesign-<P>-r*.marker`" in blob
    assert "`R == 0` → the bare `phasedesign<P>`, `R >= 1` → `phasedesign<P>-r<R>`" in blob
    assert "invokers pass `phase <P> design`" in blob


def test_drive_review_codex_rule_matches_codex_present():
    """P1-1: drive-review.md's degradation prose must state the SAME rule codex_present()
    enforces — ANY non-empty codex-review file satisfies, the first-line CODEX_UNAVAILABLE
    is a convention the gate does NOT parse — with no residual "anchored/buried" claim."""
    blob = _norm(_drive_review_md())
    assert "satisfied by ANY non-empty `codex-review-<scope>.md`" in blob
    assert "does NOT parse the marker" in blob
    assert "matches it anchored" not in blob
    assert "buried mention" not in blob


def test_drive_review_round_fallback_is_pure_integer_n():
    """P1-2: the state-absent round-count fallback counts ONLY pure-integer-N round files
    (`review-<scope>-<N>.md`, all digits) and EXCLUDES suffixed names, matching how
    bin/drive-conformance.sh reconstructs the round count."""
    blob = _norm(_drive_review_md())
    assert "pure-integer-N round files" in blob
    assert "EXCLUDE any suffixed name" in blob
    assert "review-<scope>-*.md` + 1" not in blob


def test_run_graph_and_gate_name_current_epoch_family():
    """AC9: drive.md's run-graph data-sources/render lines AND the Stage-2–4.5 gate
    paragraph name the CURRENT-epoch phasedesign file family (R = highest redesign
    marker), so older epochs never render as live rounds."""
    blob = _norm(_drive_md())
    # the current-epoch family literal appears (render + gate use the [-r<R>] form)
    assert "review-phasedesign<P>[-r<R>]-*.md" in blob, (
        "the run graph/gate must name the current-epoch review-phasedesign<P>[-r<R>] family"
    )
    assert "codex-review-phasedesign<P>[-r<R>].md" in blob


# --------------------------------------------------------------------------- #
# AC10 READ-ONLY PINS — drive-harden.md Step-4 ordering that rule-2 depends on.
# drive-harden.md is NOT edited by this phase; these pins protect the marker/distinct-sha
# surplus guard from a future harden-ordering change.
# --------------------------------------------------------------------------- #
def test_harden_sets_applied_yes_before_dispatching_regress():
    """AC10: drive-harden.md Step 4 sets `AppliedEdits: yes` BEFORE dispatching the
    regress review — the `yes` audit is the durable per-fix-round marker the checkpoint's
    `distinct-marked-sha > harden-yes` surplus guard counts. If harden dispatched the regress
    before setting `yes`, the crash window would widen and the guard could miscount."""
    blob = _norm(_drive_harden_md())
    # CONTIGUOUS span of the Step-4 "fix applied" branch: it must increment hardenRound,
    # set `AppliedEdits: yes`, THEN re-run the harden-regress review — pinned as one literal
    # clause so a reorder (dispatch-before-yes) or a dropped `yes` set breaks the pin.
    assert (
        "**A fix was applied** → `hardenRound += 1`; set `AppliedEdits: yes`. "
        "Re-run `/drive-review phase <P> harden-regress`"
    ) in blob, (
        "drive-harden.md Step 4 'fix applied' branch must set `AppliedEdits: yes` BEFORE "
        "re-running `/drive-review phase <P> harden-regress`, as one contiguous clause"
    )


def test_harden_one_regress_per_fix_round():
    """AC10: exactly ONE regress pass per fix round — a fix round sets yes once and runs
    one harden-regress review; the (harden-yes : distinct-marked-sha) correspondence is what
    makes the surplus guard exact. Pinned via the per-invocation `hardenRound += 1`
    + single regress dispatch in the same branch."""
    blob = _norm(_drive_harden_md())
    assert "One round per invocation" in blob, (
        "harden must be pinned one round per invocation (one regress per fix round)"
    )
    assert "`hardenRound += 1`" in blob
    # the regress review is the same family the phase review writes (review-phase<P>-N.md)
    assert "harden-regress" in blob


def test_harden_regress_no_round_increment_contract_pinned_both_voices():
    """AC10 + AC3 (load-bearing): the harden-regress round-scheme contract the checkpoint
    rule-2 reconstruction depends on, RE-PINNED to the marker/distinct-sha derivation (no
    subtraction). The contract has TWO halves — (A) harden-regress does NOT increment
    `phaseReview[<P>].round`, and (B) it writes into the SAME `review-phase<P>-N.md` family,
    self-identifying with the `harden-regress: yes` marker and counted SEPARATELY as
    distinct-`reviewed-sha` — and BOTH halves are pinned on BOTH prose voices (drive.md and
    drive-review.md) as CONTIGUOUS clauses, so a drift to a DIFFERENT round/file scheme in
    EITHER voice breaks this test.

    The contract: a harden-regress review writes into the SAME `review-phase<P>-N.md` family
    WITHOUT incrementing the conformance round; the checkpoint derives
    `phaseReview.round = count(UNMARKED review-phase<P>-N.md)` DIRECTLY (no subtraction) and
    counts marked-regress separately as distinct `reviewed-sha`. If the prose drifted to a
    different scheme, the reconstruction would over- or under-count silently and lossless
    rebirth counter recovery would break."""
    # 1a. drive.md — the contiguous clause that states the same-family / no-round-inflation /
    # marker half of rule 2. Pinned as one literal span so a reword onto a different scheme
    # fails. `_norm` collapses the wrap so the clause is one line.
    drive = _norm(_drive_md())
    assert (
        "A harden-regress review self-identifies with the `harden-regress: yes` header "
        "marker and is counted separately as marked-regress (the DISTINCT `reviewed-sha` "
        "among marked files); it never inflates the integration round"
    ) in drive, (
        "drive.md rule 2 must keep the contiguous 'harden-regress … self-identifies … marker "
        "… never inflates the integration round' clause — a drift to a different round/file "
        "scheme must break this pin"
    )
    # 1b. drive-review.md — BOTH halves of the contract at the review-write point:
    #   half A (no round increment): the harden-regress exception must NOT read/increment/cap
    #     the conformance round, naming the SAME `phaseReview[<P>].round` counter. UNCHANGED —
    #     harden-regress STILL does not increment the conformance round under the marker design.
    #   half B (same family, TWO file-family-preserving differences): harden-regress is the
    #     SAME review as `phase <P>` differing only by the no-round-increment AND the
    #     `harden-regress: yes` marker — same `review-phase<P>-N.md` family. A drift rerouting
    #     it to a DIFFERENT file family must change this clause and red the test.
    review = _norm(_drive_review_md())
    assert (
        "Exception — `harden-regress`:** do NOT read, increment, or cap against the "
        "conformance `phaseReview[<P>].round`"
    ) in review, (
        "drive-review.md must pin the harden-regress no-round-increment half (do NOT "
        "increment the conformance `phaseReview[<P>].round`) — the write-point half A"
    )
    assert (
        "Identical scope/diff/mechanics, differing in TWO file-family-preserving ways"
    ) in review, (
        "drive-review.md must pin the harden-regress same-family half as TWO "
        "file-family-preserving differences (no round increment + the marker) — not the "
        "stale 'ONLY difference is the counter'"
    )
    assert (
        "it emits the `harden-regress: yes` self-identifying control line"
    ) in review, (
        "drive-review.md must name the `harden-regress: yes` self-identifying marker as the "
        "second file-family-preserving difference (half B)"
    )

    # 2. CROSS-CHECK prose ⇆ script describe the SAME contract. The script's rule-2 derives
    # `phaseReviewRound = count(UNMARKED review-phase<P> files)` DIRECTLY (no subtraction) and
    # fires regress-mismatch on a SURPLUS (distinct-marked-sha > harden-yes). Assert both the
    # no-subtraction derivation AND the surplus guard so a one-sided drift is caught.
    conf = _conformance()
    # (a) the direct count(unmarked) derivation exists and the subtraction is GONE.
    assert "integration-round = count(UNMARKED review-phase<P> files)" in conf, (
        "drive-conformance.sh rule-2 must derive the round as count(UNMARKED review-phase "
        "files) directly — no subtraction"
    )
    assert "$((prc - yc))" not in conf, (
        "the subtraction `$((prc - yc))` must be GONE from the script (marker/distinct-sha "
        "replaces it)"
    )
    assert "distinct_marked_sha" in conf, (
        "the script must count marked-regress via the distinct-reviewed-sha helper"
    )
    # (b) the surplus-only guard: regress-mismatch fires iff distinct-marked-sha > harden-yes.
    assert '[ "$mreg" -gt "$yc" ]' in conf, (
        "regress-mismatch must fire on a SURPLUS (distinct-marked-sha > harden-yes), not a "
        "deficit and not the old yes>review-count comparison"
    )

    # 3. BEHAVIORAL agreement: a MARKED regress file does NOT inflate the integration round.
    # 2 unmarked integration files + 1 MARKED regress file + 1 harden-yes → round == 2
    # (the marked file is a harden-regress write, counted separately, so it did NOT bump the
    # integration round; distinct-marked 1 ≤ harden-yes 1 → clean).
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        repo = tmp / "r"; rd = tmp / "rd"
        repo.mkdir(); rd.mkdir()
        _git(repo, "init", "-q", "-b", "main")
        _commit(repo, "README", "base", "base")
        _git(repo, "checkout", "-q", "-b", "drive/rd")
        _commit(repo, "drive.sh", "echo", "work")
        _review(rd, "phase1", 1)
        _review(rd, "phase1", 2)
        _marked_review(rd, "phase1", 3, sha="a" * 40)   # a harden-regress write (MARKED)
        _harden(rd, 1, 1, "yes")                        # the matching fix-round audit
        rc, obj = _run_checkpoint(repo, rd)
        assert rc == 0, obj
        assert obj["counters"]["phaseReviewRound"] == {"1": 2}, (
            "2 UNMARKED integration files + 1 MARKED regress file = round 2 (the marked "
            "harden-regress file did NOT bump the integration round) — script and prose "
            "must agree"
        )


# --------------------------------------------------------------------------- #
# SELF-IDENTIFYING HARDEN-REGRESS MARKER — writer + resume-sweep PROSE PINS.
# The resume all-phases heal sweep, the generic-recovery carve-out, the base= strip, and
# the FINDINGS→STOP routing are /drive COORDINATOR PROSE (no executable resume consumer);
# the executable surface (marker classification, distinct-sha, surplus guard, inflight-open
# on the heal marker) is covered behaviorally above. These pin the prose so an edit cannot
# silently drop a load-bearing directive.
# --------------------------------------------------------------------------- #
def test_drive_review_writer_emits_harden_regress_marker():
    """AC1: drive-review.md instructs the writer to emit the `harden-regress: yes` control
    line in the HEADER PREAMBLE (after `reviewed-sha:`, before `## Findings`) ONLY for a
    harden-regress invocation — the header-region placement the reader's classifier binds to."""
    blob = _norm(_drive_review_md())
    assert "harden-regress self-identifying marker (harden-regress invocation ONLY)" in blob, (
        "drive-review.md must instruct the writer to emit the marker for harden-regress only"
    )
    assert "at column 0 in the HEADER PREAMBLE" in blob
    assert "immediately after `reviewed-sha:` and strictly BEFORE `## Findings`" in blob, (
        "the marker placement (after reviewed-sha, before ## Findings) must be pinned so it "
        "cannot drift below `## Findings` where the header-region classifier ignores it"
    )


def test_drive_review_base_override_strip_before_scope():
    """AC8 (DD7): drive-review.md defines the OPTIONAL `base=<40-hex>` diff-base override,
    parsed by scanning args for `^base=([0-9a-fA-F]{40})$`, STRIPPED before `<scope>`
    derivation (so scope stays `phase<P>`), defaulting to the global `phaseBaseSha` when
    absent. Named in the argument-hint. Only the resume-sweep heal supplies it."""
    text = _drive_review_md()
    assert "[base=<sha>]" in text, "the argument-hint must name the optional base override"
    blob = _norm(text)
    assert "^base=([0-9a-fA-F]{40})$" in blob, "the base= token regex must be pinned"
    assert "REMOVE that token from the arg list" in blob, (
        "base= must be STRIPPED before scope derivation (strip-before-scope, DD7)"
    )
    assert "ONLY the resume-sweep heal supplies `base=`" in blob


def test_resume_heal_sweep_marker_recovery_before_trigger():
    """AC9/AC13 (DD9): the resume all-phases heal sweep is present, visits every phaseList
    entry (advanced included), and its FIRST per-phase action recovers an OPEN
    `inflight-heal-<P>.marker` (adopt / re-dispatch) ORDERED BEFORE the stale-FINDINGS
    trigger — the marker-keyed crash-safety the distinct marker alone does not provide."""
    blob = _norm(_drive_md())
    assert "All-phases harden-regress heal sweep" in blob, (
        "drive.md resume must define the all-phases harden-regress heal sweep"
    )
    assert "advanced phases included" in blob, "the sweep must visit advanced phases"
    assert "marker-recovery BEFORE the trigger" in blob, (
        "the sweep must recover an open inflight-heal marker BEFORE evaluating the trigger"
    )
    assert "FIRST recover any OPEN `inflight-heal-<P>.marker`" in blob


def test_resume_heal_sweep_carves_out_inflight_heal_from_generic_recovery():
    """AC13 (DD6): `inflight-heal-<P>.marker` is a DISTINCT marker kind in the registry and
    is EXCLUDED from generic stranded-marker recovery (owned by the resume sweep) — else
    generic recovery would re-run a stranded heal as a plain `phase <P>` review, stripping
    the harden-regress flag and the base= override."""
    blob = _norm(_drive_md())
    assert "inflight-heal-<P>.marker" in blob, "the new marker kind must appear in drive.md"
    # the resume Stranded-in-flight bullet excludes it
    assert "EXCEPT `inflight-heal-<P>.marker`" in blob, (
        "the resume generic stranded-marker recovery must EXCLUDE inflight-heal"
    )
    # the § Durable checkpoint contract stranded-recovery also excludes it
    assert "EXCLUDES `inflight-heal-<P>.marker`" in blob, (
        "the Durable checkpoint contract stranded-recovery must exclude inflight-heal"
    )


def test_resume_heal_findings_routes_to_manual_stop():
    """AC9: a heal that returns FINDINGS on an already-advanced phase is an HONEST terminal
    NON-DECISION STOP routed to the documented MANUAL harden-regress recovery (bind the
    hardened tip, re-review/fix for real, NEVER forge) — not a claim of automated closure,
    shippability unchanged. Both outcomes self-terminate via `reviewed-sha == hardened tip`."""
    blob = _norm(_drive_md())
    assert "FINDINGS → HONEST terminal NON-DECISION STOP, routed to MANUAL recovery" in blob
    assert "NEVER forge" in blob, "the manual-recovery routing must forbid forging CONVERGED"
    assert "self-identifies" in blob  # marker semantics present in resume prose
    # legacy first-phase (baseSha absent) also fail-closed STOPs, never auto-heals
    assert "LEGACY fail-closed" in blob, (
        "a baseSha-absent first-phase heal must fail closed to a NON-DECISION STOP"
    )


def test_resume_heal_adopt_findings_routes_to_manual_stop():
    """codex phase1 BLOCKING: the step-1 ADOPT path must inspect the recovered terminal's
    verdict before continuing. A crash after a real-FINDINGS heal completed (both artifacts
    written, marker not yet cleared) resumes → ADOPTS; the marked terminal is at the hardened
    tip (`reviewed-sha == tip`) so the stale-FINDINGS trigger (step 3) SKIPS it — so the adopt
    path itself must route a FINDINGS-at-tip adopted terminal through the SAME honest manual
    STOP as the fresh-dispatch FINDINGS outcome (step 5), not silently clear-and-continue."""
    blob = _norm(_drive_md())
    # adopt path is verdict-aware: CONVERGED continues, FINDINGS-at-tip STOPs
    assert "Adopted terminal CONVERGED (at the hardened tip) → healed" in blob, (
        "the adopt path must continue only on a CONVERGED-at-tip adopted terminal"
    )
    assert (
        "Adopted terminal FINDINGS (at the hardened tip) → HONEST terminal NON-DECISION STOP,"
        " routed to MANUAL recovery" in blob
    ), (
        "the adopt path must route a FINDINGS-at-tip adopted terminal to the manual STOP "
        "(the trigger self-terminates on reviewed-sha == tip and would otherwise drop it)"
    )


def test_resume_heal_redispatch_findings_routes_to_manual_stop():
    """lens-2 fix (mirror of the adopt-branch pin): the step-1 RE-DISPATCH branch must ALSO
    inspect the resulting terminal's verdict. A re-dispatched heal lands at the hardened tip
    (`reviewed-sha == tip`), so the stale-FINDINGS trigger (step 3) SKIPS it — so the
    re-dispatch path itself must route a FINDINGS-at-tip re-dispatched terminal through the
    SAME honest manual STOP as the adopt branch / fresh-dispatch outcome (step 5), not
    silently clear-the-marker-and-continue past a genuine open P1."""
    blob = _norm(_drive_md())
    # re-dispatch path is verdict-aware: CONVERGED continues, FINDINGS-at-tip STOPs
    assert "Re-dispatched terminal CONVERGED (at the hardened tip) → healed" in blob, (
        "the re-dispatch path must continue only on a CONVERGED-at-tip re-dispatched terminal"
    )
    assert (
        "Re-dispatched terminal FINDINGS (at the hardened tip) → HONEST terminal"
        " NON-DECISION STOP, routed to MANUAL recovery" in blob
    ), (
        "the re-dispatch path must route a FINDINGS-at-tip re-dispatched terminal to the "
        "manual STOP (the trigger self-terminates on reviewed-sha == tip and would otherwise "
        "silently continue past it)"
    )


def test_resume_heal_sweep_skips_fresh_trigger_on_open_inflight_harden():
    """codex P1 (AC9 single-owner): the resume sweep SKIPS the fresh trigger for a phase with
    an OPEN `inflight-harden-<P>.marker` — that phase is owned by the harden loop's
    stranded-marker recovery. Without the skip, both the sweep AND harden-recovery would
    co-dispatch a regress review → two marked files at distinct shas → `distinct-marked-sha >
    harden-yes` → a false `regress-mismatch` STOP. Mutation-verify: reword the skip clause
    away (or drop the single-owner ownership statement) and this pin REDs."""
    blob = _norm(_drive_md())
    assert (
        "Skip the fresh trigger (steps 3–5) for a phase with an open "
        "`inflight-harden-<P>.marker`" in blob
    ), "the sweep must skip the fresh trigger for a phase with an open inflight-harden marker"
    # the ownership rationale (single owner — harden-recovery owns that phase) must be pinned
    assert "single owner" in blob, (
        "the skip must be justified as single-owner (harden-recovery owns the inflight-harden "
        "phase; a co-dispatch would false-fire the surplus guard)"
    )


def test_resume_heal_base_recovery_phaselist_order():
    """AC8: `base(P)` is recovered off `state.phaseList` ORDER (never arithmetic `P−1`) —
    `phaseInt/<runId>/<prev>` for a non-first entry, else `state.baseSha`."""
    blob = _norm(_drive_md())
    assert "keyed off `state.phaseList` ORDER (never arithmetic `P−1`" in blob
    assert "`base(P) = git rev-parse phaseInt/<runId>/<prev>`" in blob
    assert "`P` IS the first entry → `base(P) = state.baseSha`" in blob


def _harden_cap_stop_branch_body(md):
    r"""The cap-STOP branch of drive-harden.md Step 4: the `- **\`hardenRound >= HARDEN_CAP\`
    …**` bullet, bounded at the next paragraph break (blank line). Returns the bullet's
    OWN text so an assertion can pin what THAT branch does (and does not) dispatch — not
    text borrowed from a sibling bullet."""
    anchor = "- **`hardenRound >= HARDEN_CAP` and this audit still has open P1**"
    start = md.index(anchor)
    end = md.index("\n\n", start)
    return md[start:end]


def test_harden_cap_stop_dispatches_no_regress():
    """AC10: a cap-STOP round applies no fix and dispatches NO regress review — so it
    writes no `AppliedEdits: yes`, preserving the harden-yes / distinct-marked-sha
    correspondence. The cap-STOP branch returns STOP without the fix→yes→regress sequence."""
    md = _drive_harden_md()
    branch = _harden_cap_stop_branch_body(md)
    # The branch returns STOP …
    assert "return `STOP`" in branch, (
        "the `hardenRound >= HARDEN_CAP` + open-P1 branch must return `STOP`"
    )
    # … and — the load-bearing assertion the marker/distinct-sha guard depends on — it
    # dispatches NO regress review: a `harden-regress` re-run added to THIS branch would
    # write an `AppliedEdits: yes` audit (and a marked review file) with no matching fix,
    # skewing the harden-yes vs distinct-marked-sha correspondence. Pinned on the branch's
    # OWN text (not the whole Step) so adding a regress dispatch here BITES.
    assert "harden-regress" not in branch, (
        "the cap-STOP branch must dispatch NO `harden-regress` review (a regress re-run "
        "here writes AppliedEdits: yes and skews the harden-yes / distinct-marked-sha guard)"
    )
    # Sanity that the branch bound is the LOCAL bullet (not the whole doc): the sibling
    # "fix applied" branch — which DOES dispatch harden-regress — must lie OUTSIDE it, so
    # the `not in branch` check above is genuinely scoped to the cap-STOP branch.
    assert "A fix was applied" not in branch, (
        "the cap-STOP branch body must not bleed into the sibling 'fix applied' branch"
    )
    # the clean confirming audit writes `no` (not `yes`) and dispatches no regress.
    assert "set `harden-<P>-N.md` `AppliedEdits: no`" in _norm(md), (
        "the no-fix confirming audit must set AppliedEdits: no (no regress dispatch)"
    )


# --------------------------------------------------------------------------- #
# AC8 (test part) — the state template parses as JSON and carries rebirth_pending.
# (test_state_json_shape.py covers the broader soft contract; this adds the
# rebirth_pending parse assertion the design names explicitly for this file.)
# --------------------------------------------------------------------------- #
_JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def test_state_template_parses_and_has_rebirth_pending():
    """AC8 (test part): drive.md's ```json state template parses as JSON AND carries
    `rebirth_pending: false`. A malformed template or a dropped key breaks resume."""
    m = _JSON_FENCE_RE.search(_drive_md())
    assert m, "drive.md must carry a ```json fenced state template"
    obj = json.loads(m.group(1))
    assert isinstance(obj, dict)
    assert "rebirth_pending" in obj, (
        "the state template must include `rebirth_pending` (lever-2 rebirth signal)"
    )
    assert obj["rebirth_pending"] is False, "rebirth_pending defaults to false"
