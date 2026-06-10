"""AC8 (test part), AC10, and the string pins named in AC4/5/6/7/9 — the durable
cross-file contract between the lever-2 rebirth checkpoint PROSE (drive.md,
drive-review.md, drive-harden.md) and the SCRIPT (bin/drive-conformance.sh).

Slice 1.3 owns ONLY this file; slices 1.1 (the script) and 1.2 (the prose) are merged
into this worktree, so the assertions run against the REAL integrated text/behavior.
A future drift on EITHER side — a renamed violation, a dropped reconstruction rule, a
reordered harden Step 4 — breaks a test here.

Two kinds of pin, deliberately chosen per the design's "prefer real behavior over
string-matching where feasible" rule:

  * SCRIPT-side contracts are asserted BEHAVIORALLY: we build a minimal git repo +
    RUN_DIR fixture in a tempdir, run `drive-conformance.sh --mode checkpoint`, and
    assert its JSON / exit code (the same shape test/drive-conformance.test.sh covers
    in bash, re-pinned here so the python suite alone proves the mode name, the
    `counters` derivation, and every violation NAME the prose references actually
    resolve in the shipped script). This is the load-bearing cross-file contract:
    the prose names `--mode checkpoint`, the `phasedesign<P>-r<R>` token form, and the
    violations `epoch-unmarked`/`regress-mismatch`/`epoch-gap` — each must EXIST in the
    script or the prose points at nothing.

  * PROSE-ONLY coordinator contracts (the resume reconstruction rules, the REDESIGN
    epoch-marker ordering, the sessionId rebind, the single-use marker, adopt-needs-
    both-voices, and the read-only drive-harden.md Step-4 ordering that rule-2's
    round-subtraction depends on) are NOT script-executable — they are pinned by
    string assertions on the shipped prose so a later edit cannot silently drop them.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

from _helpers import REPO_ROOT

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


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True,
    )


def _rev(repo, ref):
    """Resolve a ref to its full 40-char sha (for asserting expected/found_sha exactly)."""
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", ref],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _commit(repo, path, content, msg):
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(content + "\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


def _review(rd, scope, n, sha="0" * 40, verdict="CONVERGED"):
    (rd / f"review-{scope}-{n}.md").write_text(
        f"# Review {scope} round {n}\n\n## Verdict: {verdict}\n\nreviewed-sha: {sha}\n",
        encoding="utf-8",
    )


def _harden(rd, p, n, applied):
    (rd / f"harden-{p}-{n}.md").write_text(
        f"# Harden phase {p} {n}\n## Verdict: HARDENED\n## AppliedEdits: {applied}\n",
        encoding="utf-8",
    )


def _redesign_marker(rd, p, r):
    (rd / f"redesign-{p}-r{r}.marker").write_text(
        json.dumps({"phase": p, "epoch": r}) + "\n", encoding="utf-8"
    )


def _codex(rd, scope):
    (rd / f"codex-review-{scope}.md").write_text(
        f"codex review for {scope}\nlooks fine\n", encoding="utf-8"
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
    """AC1/AC2 (behavioral cross-file contract): a quiescent, well-formed run is clean
    (exit 0) and emits `counters` derived per the I3 rules — reviewCount from
    pure-integer-N files; phaseReviewRound = review-phase count MINUS AppliedEdits:yes
    harden files; hardenRound counts ONLY `yes`; phaseDesignRound from the epoch-0
    family. Mirrors mkfixture.sh::mk_checkpoint clean."""
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
    assert counters["phaseReviewRound"] == {"1": 2}, counters  # 3 files − 1 yes
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


def test_checkpoint_regress_mismatch_violation_and_zero_round(tmp_path):
    """AC2: yes-count exceeding the review-phase file count is malformed → violation
    `regress-mismatch` and phaseReviewRound clamped to 0 (the rule-2 subtraction would
    otherwise go negative). 1 review-phase1 file + 2 AppliedEdits:yes harden files."""
    repo, rd = _base_run(tmp_path, "ckpt-regress")
    _review(rd, "phase1", 1)
    _harden(rd, 1, 1, "yes")
    _harden(rd, 1, 2, "yes")
    rc, obj = _run_checkpoint(repo, rd)
    assert rc == 1
    # EXACT: exactly one regress-mismatch on scope `phase1`, no shas, nothing else.
    assert obj["violations"] == [
        _viol("phase1", "regress-mismatch")
    ], obj["violations"]
    assert obj["counters"]["phaseReviewRound"] == {"1": 0}


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


def _run_checkpoint_with_script(repo, rd, script):
    """Run an arbitrary conformance script (used to exercise a MUTATED tmp COPY of the real
    script — the real bin/drive-conformance.sh is never edited)."""
    proc = subprocess.run(
        ["bash", str(script), str(rd), "--mode", "checkpoint"],
        cwd=str(repo), capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout


def test_checkpoint_nonnumeric_phase_id_4a_processed_not_skipped(tmp_path):
    """AC1/AC11 boundary (D18 ancestry, NO numeric phase-id ordering): the mode must
    actually PROCESS a non-numeric phase id `phaseInt/<runId>/4a`, not silently skip it.
    To make a skip observably fail, `4a` is built DIVERGENT (cut from `main`, non-ancestor
    of `drive/<runId>`): the real script must flag `phaseInt-divergent` for `phaseInt/.../4a`
    specifically. A numeric-only selection would skip `4a` and read CLEAN — proving that the
    flagged-divergent assertion is load-bearing on non-numeric processing (proof below via a
    tmp COPY of the script with a numeric-id filter injected)."""
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

    # PROOF the assertion FLIPS under numeric-only selection: copy the real script to a
    # tmp dir, inject a `skip non-numeric phase id` filter into the phaseInt loop, and
    # confirm the COPY now reads CLEAN (no phaseInt-divergent) for the very same fixture —
    # i.e. the real script's NON-numeric processing is what makes the assertion above
    # catch the divergence. The real bin/drive-conformance.sh is never modified.
    src = CONFORMANCE.read_text(encoding="utf-8")
    anchor = '    if ! ptip="$(rev "$pref")"; then\n'
    assert anchor in src, "expected phaseInt-loop anchor in drive-conformance.sh"
    # derive the numeric phase id from the ref (basename) and `continue` if non-numeric.
    numeric_only = (
        '    _pid="${pref##*/}"\n'
        '    case "$_pid" in (*[!0-9]*|"") continue;; esac\n'
    ) + anchor
    mutated = src.replace(anchor, numeric_only, 1)
    assert mutated != src, "numeric-only mutation must change the script text"
    copy = tmp_path / "conformance-numeric-only.sh"
    copy.write_text(mutated, encoding="utf-8")
    rc2, out2 = _run_checkpoint_with_script(repo, rd, copy)
    obj2 = json.loads(out2)
    assert rc2 == 0 and obj2["clean"] is True and obj2["violations"] == [], (
        "under numeric-only selection the divergent 4a is skipped and reads CLEAN — "
        "this is exactly the regression the real (non-numeric-processing) script prevents"
    )


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
    changes the derivation — e.g. dropping the `MINUS … AppliedEdits: yes` subtraction or
    the `HIGHEST epoch R` rule — breaks the pin. A dropped rule is a silent resume hole."""
    blob = _norm(_drive_md())
    # Each entry is the literal contiguous formula from drive.md's reconstruction list.
    rules = [
        # rule 1 — reviewCount derivation
        "`slices[<id>].reviewCount` = max(state, count of `review-<id>-N.md`, "
        "pure-integer N)",
        # rule 2 — phaseReview round = review-phase count MINUS AppliedEdits: yes harden
        "`phaseReview[<P>].round` = max(state, count of `review-phase<P>-N.md` "
        "(pure-integer N) MINUS count of `harden-<P>-*.md` with `AppliedEdits: yes`)",
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


def test_sessionId_rebind_is_first_resume_bullet():
    """AC6 (I7): resume opens with the sessionId rebind — rewrite state.sessionId to the
    live $CLAUDE_CODE_SESSION_ID on ANY new-session resume, BEFORE reconciling. Pinned as
    the FIRST resume directive so a reorder that delays hook-attribution is caught."""
    blob = _norm(_drive_md())
    assert "sessionId rebind (FIRST, on ANY resume into a new session)" in blob, (
        "drive.md resume must open with the FIRST sessionId-rebind bullet"
    )
    assert "rewrite `state.sessionId` to the live `$CLAUDE_CODE_SESSION_ID`" in blob
    # STRUCTURAL FIRST-ness (not just the parenthetical label): the rebind bullet must
    # POSITIONALLY precede the other resume-section steps, so a reorder that delays
    # hook-attribution is caught even if it leaves the now-false "(FIRST, ...)" label.
    i_rebind = blob.index("sessionId rebind (FIRST")
    i_marker = blob.index("Consume `checkpoint-complete.marker` (single-use)")
    i_phase = blob.index("**Current phase:**")
    assert i_rebind < i_marker < i_phase, (
        "the sessionId-rebind bullet must appear BEFORE the marker-consume and "
        "current-phase resume steps (structural FIRST-ness, not just the label)"
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
    marker-write → state-write span is one atomic step. Round-subtraction soundness (the
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
# drive-harden.md is NOT edited by this phase; these pins protect the round-subtraction
# rule from a future harden-ordering change.
# --------------------------------------------------------------------------- #
def test_harden_sets_applied_yes_before_dispatching_regress():
    """AC10: drive-harden.md Step 4 sets `AppliedEdits: yes` BEFORE dispatching the
    regress review — the `yes` audit is the durable 1:1 marker rule-2's round-subtraction
    counts. If harden dispatched the regress before setting `yes`, the crash window would
    widen and the subtraction would mis-count."""
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
    one harden-regress review; the 1:1 (yes-file : regress-review) correspondence is what
    makes the rule-2 subtraction exact. Pinned via the per-invocation `hardenRound += 1`
    + single regress dispatch in the same branch."""
    blob = _norm(_drive_harden_md())
    assert "One round per invocation" in blob, (
        "harden must be pinned one round per invocation (one regress per fix round)"
    )
    assert "`hardenRound += 1`" in blob
    # the regress review is the same family the phase review writes (review-phase<P>-N.md)
    assert "harden-regress" in blob


def test_harden_cap_stop_dispatches_no_regress():
    """AC10: a cap-STOP round applies no fix and dispatches NO regress review — so it
    writes no `AppliedEdits: yes`, preserving the rule-2 subtraction. The cap-STOP branch
    returns STOP without the fix→yes→regress sequence."""
    blob = _norm(_drive_harden_md())
    # The cap-STOP branch, pinned as the LOCAL contiguous Step-4 clause — NOT a lazy
    # `.*?` span that could bridge to the distant "→ STOP and summarize" statement ~9KB
    # away. This is the single `→ return `STOP`` in the doc; a rewrite of the local
    # condition→return ordering breaks the pin.
    assert (
        "**`hardenRound >= HARDEN_CAP` and this audit still has open P1** → return `STOP`."
    ) in blob, (
        "drive-harden.md Step 4 must return `STOP` on `hardenRound >= HARDEN_CAP` + open "
        "P1 as one contiguous clause (the cap-STOP branch applies no fix → no regress)"
    )
    # the clean confirming audit writes `no` (not `yes`) and dispatches no regress.
    assert "set `harden-<P>-N.md` `AppliedEdits: no`" in blob, (
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
