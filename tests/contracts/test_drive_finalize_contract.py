"""Cross-file contract for the FINALIZE stage (Stage 4c) of /drive.

Phase 1 added `drive-finalize.md` + narrowed `drive-harden.md`; Phase 2 wired the
stage into drive.md, drive-ship.md, bin/drive-conformance.sh, bin/drive-merge-gate.sh,
and CLAUDE.md. These are PURE SPEC-PROSE pins (the script BEHAVIOR is covered by the
bash conformance suite, slice 3.1) so a later edit cannot silently drop the wiring.

Two anti-vacuity disciplines run throughout (per design D-P3-7):

1. SECTION-BOUNDED pins. `/drive-finalize` and `stage = finalize` also appear in
   drive.md's resume/recovery prose (drive.md:128/133/399-402), so a loose "appears
   somewhere" assertion passes vacuously even if the real Stage-4c dispatch / the
   Execute→Finalize transition is deleted. The Stage-4c tests therefore slice the
   `### Stage 4c — Finalize` section by its header anchor and the transition by its
   real line, and assert the token THERE.

2. PER-TOKEN REQUIRED-PRESENCE for cross-file token consistency (NOT exact-set-
   equality): each token must appear in its REQUIRED carrier files; extra occurrences
   elsewhere are tolerated (so a token legitimately gaining one more carrier never
   false-reds). Grounded by `grep -rln '<token>' .claude/commands/ bin/ CLAUDE.md`
   on the real worktree.

Each assertion PASSES on the current correct worktree and reds only on a real
regression — a dropped dispatch/transition, a re-applied harden de-slop lens, a
dropped artifact-contract clause, or a token drop/spelling-drift in a required carrier.
"""
import re

from _helpers import REPO_ROOT

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
COMMANDS = REPO_ROOT / ".claude" / "commands"
BIN = REPO_ROOT / "bin"

DRIVE_MD = COMMANDS / "drive.md"
DRIVE_HARDEN = COMMANDS / "drive-harden.md"
DRIVE_FINALIZE = COMMANDS / "drive-finalize.md"
DRIVE_SHIP = COMMANDS / "drive-ship.md"
CONFORMANCE = BIN / "drive-conformance.sh"
MERGE_GATE = BIN / "drive-merge-gate.sh"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

# A genuine `/drive-<word>` SLASH-COMMAND token (NOT a `bin/drive-*` path substring).
# Mirrors test_drive_command_refs.py's proven negative-lookbehind so a buried path or
# code-fence path cannot false-pass.
_DRIVE_REF = re.compile(r"(?<![\w/])/drive-[a-z]+")


# --------------------------------------------------------------------------- #
# File-text accessors + helpers
# --------------------------------------------------------------------------- #
def _text(path):
    assert path.is_file(), f"expected file at {path}"
    return path.read_text(encoding="utf-8")


def _norm(text):
    """Collapse whitespace runs (incl. newlines) to a single space — robust to wrap/
    reflow but still load-bearing on the words."""
    return re.sub(r"\s+", " ", text)


def _section(text, header_re, *, stop_re=r"^#{1,4}\s"):
    """Slice the lines from the FIRST line matching `header_re` up to (excluding) the
    next line matching `stop_re` (another `#`..`####` markdown header) or EOF. Returns
    the section's text. Asserts the header exists so a renamed/removed header reds."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.search(header_re, ln)), None)
    assert start is not None, f"section header /{header_re}/ not found"
    end = next(
        (j for j in range(start + 1, len(lines)) if re.search(stop_re, lines[j])),
        len(lines),
    )
    return "\n".join(lines[start:end])


# =========================================================================== #
# AC39 — finalize command exists with frontmatter; dispatched IN Stage 4c
# =========================================================================== #
def test_drive_finalize_command_exists_with_frontmatter():
    """`drive-finalize.md` exists, opens with a `---` frontmatter fence, and has a
    non-empty `description:` naming the finalize/aggregate stage. The FEATURE's own
    pin (belt-and-braces over test_drive_command_refs.py's generic frontmatter scan)."""
    assert DRIVE_FINALIZE.is_file(), f"drive-finalize.md missing at {DRIVE_FINALIZE}"
    lines = _text(DRIVE_FINALIZE).splitlines()
    assert lines and lines[0].strip() == "---", "drive-finalize.md must open with `---`"
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    assert end is not None, "drive-finalize.md frontmatter not closed with `---`"
    desc = next((ln for ln in lines[1:end] if ln.startswith("description:")), None)
    assert desc is not None, "drive-finalize.md frontmatter has no `description:`"
    value = desc[len("description:"):].strip().lower()
    assert value, "drive-finalize.md `description:` is empty"
    assert "finalize" in value or "aggregate" in value, (
        f"description should name the finalize/aggregate stage; got: {value!r}"
    )


def test_drive_md_dispatches_drive_finalize_in_stage_4c():
    """`/drive-finalize` is wired as the actual Stage-4c DISPATCH, not merely mentioned
    in resume/recovery prose. SECTION-BOUNDED: slice the `### Stage 4c — Finalize`
    section and assert a real `/drive-finalize` slash-command token appears INSIDE it
    (the dispatch is the `then invoke /drive-finalize` line). Deleting the Stage-4c
    dispatch reds this even though `/drive-finalize` survives in the resume prose
    (drive.md:399-402). Pins AC39."""
    section = _section(_drive_md_text(), r"^###\s+Stage 4c\b")
    refs = _DRIVE_REF.findall(section)
    assert "/drive-finalize" in refs, (
        "the Stage 4c section must DISPATCH /drive-finalize (as a slash-command token), "
        f"not just reference it elsewhere; found refs in section: {sorted(set(refs))}"
    )


def _drive_md_text():
    return _text(DRIVE_MD)


# =========================================================================== #
# AC40 — Stage-4c placement: header, Execute→Finalize transition, run-graph order
# =========================================================================== #
def test_finalize_stage_4c_placement():
    """Three SECTION/LINE-BOUNDED pins so a regression that removes the real wiring
    reds even though the bare token survives in resume prose. Pins AC40."""
    text = _drive_md_text()

    # (a) the section header exists.
    assert re.search(r"^###\s+Stage 4c\b.*Finalize", text, re.MULTILINE), (
        "drive.md must have a `### Stage 4c — Finalize` section header"
    )

    # (b) the Execute->Finalize transition exists at its real site: a single line that
    # co-locates `all phases`, `hardened`, and `stage = finalize`. `stage = finalize`
    # alone also appears in the resume routing prose (drive.md:128/133) and step-6
    # (drive.md:974), so anchor on the transition's distinctive co-occurrence.
    transition = re.compile(
        r"all phases.*hardened.*stage\s*=\s*`?\s*finalize", re.IGNORECASE
    )
    assert any(transition.search(ln) for ln in text.splitlines()), (
        "drive.md must carry the Execute->Finalize transition on one line "
        "(`all phases ... hardened -> stage = finalize`); the bare `stage = finalize` "
        "token in resume prose does not satisfy this"
    )

    # (c) the run-graph stage-order line places Finalize between Execute and Verify.
    # Assert INDEX order on the rendered line, not a verbatim glyph match.
    order_line = next(
        (
            ln for ln in text.splitlines()
            if "Execute" in ln and "Finalize" in ln and "Verify" in ln
            and "Plan" in ln and "Ship" in ln
        ),
        None,
    )
    assert order_line is not None, (
        "drive.md must have the run-graph stage-order line "
        "(Premises ... Execute ... Finalize ... Verify ... Ship)"
    )
    i_exec = order_line.index("Execute")
    i_fin = order_line.index("Finalize")
    i_ver = order_line.index("Verify")
    assert i_exec < i_fin < i_ver, (
        f"run-graph order must be Execute < Finalize < Verify; got line: {order_line!r}"
    )


# =========================================================================== #
# AC41 — drive-harden narrowed to two correctness lenses; de-slop DEFERRED
# =========================================================================== #
def test_harden_narrowed_to_two_lenses():
    """drive-harden.md is narrowed: it DEFERS de-slop to `/drive-finalize`, keeps the
    two correctness lenses (add missing tests / fix logic bugs), and no longer instructs
    APPLYING a de-slop edit within harden. Anchors on stable directive tokens, not exact
    prose (OPERATING: structural over brittle-regex). Pins AC41."""
    norm = _norm(_text(DRIVE_HARDEN))

    # Deferral target named.
    assert "/drive-finalize" in norm, "drive-harden.md must name /drive-finalize"
    assert "defer" in norm.lower(), (
        "drive-harden.md must DEFER slop (a `defer`/`deferred` directive) to finalize"
    )

    # The two correctness lenses are present (stable directive tokens).
    assert re.search(r"add missing tests", norm, re.IGNORECASE), (
        "harden lens 1 (add missing tests) missing"
    )
    assert re.search(r"fix logic", norm, re.IGNORECASE), (
        "harden lens 2 (fix logic issues/bugs) missing"
    )

    # The narrowing directive: harden no longer REMOVES slop in-stage. This is the
    # robust negative — assert the explicit "do NOT remove slop here" directive is
    # present (a re-introduced de-slop lens would have to delete this directive).
    assert re.search(r"do not remove any slop", norm, re.IGNORECASE) or re.search(
        r"no longer removes slop", norm, re.IGNORECASE
    ), (
        "drive-harden.md must state it does NOT remove/apply slop in-stage "
        "(de-slop is deferred to finalize); a re-applied de-slop lens would drop this"
    )


# =========================================================================== #
# AC42 — drive-finalize artifact + scope-gate + cap + regression-guard contract
# =========================================================================== #
def test_finalize_emits_shipgate_artifact_contract():
    """drive-finalize.md states the ship-gate artifact contract: `review-finalize-N.md`
    + `## AppliedEdits:` marker + a `reviewed-sha` bound to the featureBranch tip + the
    `codex-review-finalize.md` sibling + `codex-raw-finalize.log` per-scope log + the
    `CODEX_UNAVAILABLE` degradation + `FINALIZE_CAP = 3` / `finalizeRound` + the full-suite
    regression guard with REVERT-on-red. Pins AC42 (artifact half)."""
    text = _text(DRIVE_FINALIZE)
    norm = _norm(text)

    assert "review-finalize-N.md" in norm, "names the review-finalize-N.md artifact"
    assert "## AppliedEdits:" in text, "the `## AppliedEdits:` marker line"
    assert "reviewed-sha" in norm, "the reviewed-sha binding line"
    # reviewed-sha bound to the featureBranch tip.
    assert re.search(r"rev-parse\s+<?\s*`?featureBranch", norm) or re.search(
        r"featureBranch\s*`?\s*tip", norm, re.IGNORECASE
    ), "reviewed-sha must bind to the featureBranch tip"
    assert "codex-review-finalize.md" in norm, "the codex sibling"
    assert "codex-raw-finalize.log" in norm, "the per-scope raw codex log"
    assert "CODEX_UNAVAILABLE" in norm, "the codex-unavailable degradation token"
    assert re.search(r"FINALIZE_CAP\s*=\s*3", norm), "FINALIZE_CAP = 3"
    assert "finalizeRound" in norm, "the finalizeRound counter"
    # Full-suite regression guard with revert-on-red.
    assert re.search(r"full\b.*\bsuite", norm, re.IGNORECASE), (
        "the full-suite regression guard"
    )
    assert re.search(r"\bREVERT\b", text), "the revert-on-red rule"


def test_finalize_scope_creep_gate_and_arch_todo():
    """drive-finalize.md states: the diff scope `baseRef..featureBranch`, the edit-scope
    HARD GATE (run diff + test-support + flagged-P1 root cause), the three lenses (de-slop
    LED + aggregate tests + aggregate bugs), and the `$RUN_DIR/finalize-todo.md` ->
    repo-root `TODO.md` architectural route (NOT a `wt/finalize/TODO.md`). Pins AC42
    (scope/gate/arch half)."""
    text = _text(DRIVE_FINALIZE)
    norm = _norm(text)

    assert "baseRef..featureBranch" in norm, "the whole-run diff scope baseRef..featureBranch"
    assert "HARD GATE" in text, "the edit-scope HARD GATE"
    # Three lenses, de-slop LED.
    assert re.search(r"de-slop", norm, re.IGNORECASE), "the de-slop lens"
    assert re.search(r"missing test", norm, re.IGNORECASE), "the aggregate missing-test lens"
    assert re.search(r"logic bug", norm, re.IGNORECASE), "the aggregate logic-bug lens"
    # Architectural findings route: durable finalize-todo.md, promoted to repo-root TODO.md.
    assert "finalize-todo.md" in norm, "the durable $RUN_DIR/finalize-todo.md"
    assert "TODO.md" in norm, "the repo-root TODO.md promotion target"
    # NOT a finalize working-tree TODO.md (the broken design D10 ruled out).
    assert re.search(r"NEVER writes or commits any project `TODO.md`", text) or re.search(
        r"do not create any `?TODO\.md`?", norm, re.IGNORECASE
    ), "finalize must NOT write a wt/finalize/TODO.md (architectural findings go to $RUN_DIR)"


# =========================================================================== #
# AC43 — drive-ship precondition/promotion + CLAUDE.md pipeline/invariant
# =========================================================================== #
def test_ship_spec_finalize_precondition_and_promotion():
    """drive-ship.md: a Finalize-CONVERGED precondition that is TOLERANT (NOT strict
    `== tip`), remediation that names `/drive-finalize`, promotion of `finalize-todo.md`
    -> `TODO.md`, and the 3-entry `SHIP_LEDGER_ALLOWLIST` surfaced at Gate B. Pins AC43
    (ship half)."""
    text = _text(DRIVE_SHIP)
    norm = _norm(text)

    assert re.search(r"Finalize CONVERGED", norm, re.IGNORECASE), (
        "ship must gate a Finalize-CONVERGED precondition"
    )
    assert "/drive-finalize" in norm, "ship remediation must name /drive-finalize"
    # Tolerant test (ancestor / ≤1 commit), NOT strict == tip — the precondition must
    # explicitly TOLERATE a post-ledger resume tip.
    assert re.search(r"TOLERATE", text) or re.search(
        r"ancestor", norm, re.IGNORECASE
    ), "the finalize precondition must be TOLERANT (ancestor/≤1-commit), not strict == tip"
    assert "finalize-todo.md" in norm and "TODO.md" in norm, (
        "ship must promote $RUN_DIR/finalize-todo.md -> repo-root TODO.md"
    )
    assert "SHIP_LEDGER_ALLOWLIST" in norm, "the SHIP_LEDGER_ALLOWLIST constant"
    # The 3-entry allowlist contents.
    assert "TODO.md" in norm and ".harness/decisions.md" in norm and (
        ".harness/followups.md" in norm
    ), "the 3-entry ledger allowlist {decisions.md, followups.md, TODO.md}"
    assert "Gate B" in text, "the finalize follow-ups are surfaced at Gate B"


def test_claudemd_pipeline_and_invariant():
    """CLAUDE.md lists `/drive-finalize` as Stage 4c between harden and verify in the
    Pipeline + runner list; the harden lens list defers de-slop to finalize; a FINALIZE
    invariant is present (ship tip-binding = finalize artifact, omission-proof, cap 3,
    finalizeRound); Run-state lists the finalize artifacts. Pins AC43 (CLAUDE.md half)."""
    text = _text(CLAUDE_MD)
    norm = _norm(text)

    assert "/drive-finalize" in norm, "CLAUDE.md must reference /drive-finalize"
    assert re.search(r"Stage 4c", norm), "CLAUDE.md must place finalize as Stage 4c"
    # Harden's lens list defers de-slop to finalize (not applied in harden).
    assert re.search(r"de-slop is deferred to `?/drive-finalize`?", norm) or re.search(
        r"defer.*de-slop.*finalize", norm, re.IGNORECASE
    ), "CLAUDE.md harden description must defer de-slop to /drive-finalize"
    # FINALIZE invariant: ship tip-binding on the finalize artifact + cap + counter.
    assert "FINALIZE_CAP=3" in norm or re.search(r"FINALIZE_CAP\s*=\s*3", norm), (
        "the FINALIZE_CAP=3 invariant"
    )
    assert "finalizeRound" in norm, "the finalizeRound counter in the invariant"
    assert re.search(r"omission-", norm, re.IGNORECASE), (
        "the omission-proof property (a run that omits finalize cannot ship)"
    )
    # Run-state lists the finalize artifacts.
    assert "review-finalize-N.md" in norm, "Run-state lists review-finalize-N.md"
    assert "finalize-todo.md" in norm, "Run-state lists finalize-todo.md"
    assert "inflight-finalize" in norm, "Run-state mentions the inflight-finalize marker"


# =========================================================================== #
# AC44 — finalize-token consistency: PER-TOKEN REQUIRED-PRESENCE (not set-equality)
# =========================================================================== #
# Required carrier sets, grounded by `grep -rln '<token>' .claude/commands/ bin/ CLAUDE.md`
# on the real worktree. EXTRA occurrences elsewhere are tolerated (a superset is fine).
_REQUIRED_CARRIERS = {
    # The dispatch marker: owned by the coordinator (drive.md) + documented in CLAUDE.md's
    # run-state. drive-finalize.md / conformance.sh do NOT reference it.
    "inflight-finalize": (DRIVE_MD, CLAUDE_MD),
    # The state field: read/written by every consumer.
    "finalizeRound": (DRIVE_MD, DRIVE_FINALIZE, CONFORMANCE, CLAUDE_MD),
    # The review-scope token: all six genuinely carry it (the merge-gate emits the
    # review-finalize-N.md remediation).
    "review-finalize": (DRIVE_MD, DRIVE_FINALIZE, CONFORMANCE, DRIVE_SHIP, MERGE_GATE, CLAUDE_MD),
    # The exact `## AppliedEdits: yes` literal (heading prefix + `: yes` value). NOT
    # drive-harden.md (carries `## AppliedEdits: pending` + an inline non-`##`
    # `AppliedEdits: yes` only); NOT CLAUDE.md (never the literal heading). Requiring
    # either would red on correct code.
    "## AppliedEdits: yes": (DRIVE_MD, DRIVE_FINALIZE, CONFORMANCE),
}


def test_finalize_token_consistency_across_files():
    """Each load-bearing finalize token appears, spelled IDENTICALLY (the byte-literal
    token), in every REQUIRED carrier file. Asserted as PER-TOKEN REQUIRED-PRESENCE: each
    required carrier MUST contain the literal; extra occurrences elsewhere are tolerated.
    NOT exact-set-equality (which reds on correct code the moment a token legitimately
    appears in one more file). Passes on the current worktree; reds when a required
    carrier drops the token or drifts its spelling. Pins AC44."""
    for token, required in _REQUIRED_CARRIERS.items():
        missing = [p.name for p in required if token not in _text(p)]
        assert not missing, (
            f"token {token!r} is REQUIRED in {[p.name for p in required]} but is "
            f"missing from {missing} (a drop or spelling-drift in a required carrier)"
        )
