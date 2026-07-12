"""Rebirth-handshake cross-file contract pins.

The lever-2 rebirth pause/resume handshake is split across two files that MUST agree:
  * `.claude/commands/drive.md` — the coordinator prose: the I1 safe-boundary handler, the
    `↻ REBIRTH` run-graph node, the handoff block, the resume rebirth-continue +
    `rebirth_pending` re-arm, the canonical `waiting` amendment, gate precedence, the
    context-of-execution summary shared step, and the hook-sole continuation contract.
  * `bin/drive-stop-hook.py` — the Stop-hook escalation steer: once `rebirth_pending` is set
    and the run is still over hard water, the hook steers the coordinator to perform the I1
    handshake at its next safe boundary.

A drift on EITHER side — a reordered I1 step, a dropped legend glyph, a desynced canonical
`waiting` definition, a hook steer that no longer names the handshake the prose implements —
reds a pin here. The pins are STRUCTURAL/bounded, NOT loose substrings: section-bounded
enumeration + by-index ordering (`_I1_STEP_RE`, `_RESUME_BULLET_RE`) and contiguous-clause
literals (whitespace-normalized). Each load-bearing pin is proven to RED against a mutated
COPY of the relevant prose/code (never the real files) in the accompanying
`test_*_flips_on_*` cases.
"""
import re

import pytest

from _helpers import REPO_ROOT

DRIVE_MD = REPO_ROOT / ".claude" / "commands" / "drive.md"
DRIVE_PLAN_MD = REPO_ROOT / ".claude" / "commands" / "drive-plan.md"
HOOK_PY = REPO_ROOT / "bin" / "drive-stop-hook.py"


# --------------------------------------------------------------------------- #
# File-text accessors + the same `_norm` whitespace collapse slice 1.3 uses, so a
# wrapped prose clause pins on its WORDS, not on incidental line breaks.
# --------------------------------------------------------------------------- #
def _text(path):
    assert path.is_file(), f"expected file at {path}"
    return path.read_text(encoding="utf-8")


def _drive_md():
    return _text(DRIVE_MD)


def _hook_py():
    return _text(HOOK_PY)


def _drive_plan_md():
    return _text(DRIVE_PLAN_MD)


def _norm(text):
    """Collapse runs of whitespace (incl. newlines) to a single space — a prose phrase pin
    robust to wrapping/reflow but still load-bearing on the words themselves."""
    return re.sub(r"\s+", " ", text)


def _section(md, heading, *, level="### "):
    """Body of the markdown section opened by `level + heading`, up to the next heading of
    `level` OR a shallower one. Returns ORIGINAL newlines (not _norm'd) so a line-anchored
    enumeration regex can walk the section's items in document order.

    `heading` is matched as the start of a heading line; the end is the next line that
    starts with `level` or any shallower `#`-run (`## `/`# `), whichever comes first."""
    start_marker = level + heading
    start = md.index(start_marker)
    body_start = start + len(start_marker)
    # the section ends at the next heading at the same or a shallower level
    end_re = re.compile(r"^#{1," + str(level.count("#")) + r"} ", re.MULTILINE)
    m = end_re.search(md, body_start)
    return md[body_start: m.start()] if m else md[body_start:]


# A numbered step in the I1 handler: a line that begins `N. **<Label>` at column 0.
_I1_STEP_RE = re.compile(r"^(\d+)\. \*\*(.+?)[.*]", re.MULTILINE)

# A resume reconciliation sub-bullet: a nested (indented) bolded `- **<Label>**` line —
# mirrors the slice-1.3 structural rule in test_checkpoint_contract.py, widened to the
# bold SPAN (`- **…**`) rather than a `:**`-only terminator so the rebirth-continue bullet
# (whose bold ends `NOT a STOP.**`, not `:**`) is enumerated alongside the `:`-terminated
# siblings. The top-level `- **Resume:**` bullet is at column 0; its children are indented,
# so the leading-whitespace requirement excludes the parent and matches only the steps. A
# trailing `:` is stripped from the captured label so labels read the same as their source.
_RESUME_BULLET_RE = re.compile(r"^[ \t]+- \*\*(.+?)\*\*", re.MULTILINE)


def _resume_bullet_labels(section):
    """Enumerated resume sub-bullet labels (trailing `:` stripped) in document order."""
    return [lbl.rstrip(":") for lbl in _RESUME_BULLET_RE.findall(section)]


def _resume_bullet_bodies(section):
    """The FULL text of each enumerated resume sub-bullet (its `- **…**` start line through
    every following more-indented line, up to the next sibling sub-bullet), in document
    order — same bounded `_RESUME_BULLET_RE` enumeration, sliced between match starts so a
    negative pin ("X does NOT appear in bullet N") can scan one bullet's own span only."""
    starts = [m.start() for m in _RESUME_BULLET_RE.finditer(section)]
    bounds = starts + [len(section)]
    return [section[bounds[i]: bounds[i + 1]] for i in range(len(starts))]


def _i1_section():
    return _section(_drive_md(), "I1 — Safe-boundary rebirth handler", level="## ")


def _resume_section():
    """The body of drive.md's `## Run setup & resume` resume bullet list, from the
    `- **Resume:**` bullet to the sibling `- **Fresh run:**` bullet that follows it — its
    nested `- **<Label>:**` sub-bullets are the resume reconciliation steps (mirrors slice
    1.3's accessor). Bounded on Fresh-run (not the far-off `## ` heading) so indented bullets
    inside the Fresh-run setup block are not miscounted as resume sub-bullets."""
    md = _drive_md()
    start = md.index("- **Resume:**")
    end = md.index("\n- **Fresh run:**", start)
    return md[start:end]


# =========================================================================== #
# AC1 — fail-closed ordering: PROVE checkpoint + WRITE marker BEFORE waiting="rebirth".
# Bounded/enumerated (by step INDEX), NOT a raw two-substring offset compare.
# =========================================================================== #
def _i1_steps():
    """The I1 handler's numbered steps as an ordered [(num, label)] list, bounded to the
    `## I1 …` section so a step elsewhere in drive.md cannot leak in."""
    return [(int(n), lbl) for n, lbl in _I1_STEP_RE.findall(_i1_section())]


def _step_index(steps, predicate):
    return next((i for i, (_n, lbl) in enumerate(steps) if predicate(lbl)), None)


def test_i1_marker_write_is_step_before_waiting_set_and_adjacent():
    """AC1: in the I1 handler, `checkpoint-complete.marker` is WRITTEN (step 4) strictly
    BEFORE `waiting="rebirth"` is set (step 5), and the two are ADJACENT ordered steps — a
    reorder, or an inserted step between them, flips the test. Asserted by STEP INDEX over
    the bounded section (not a raw offset compare), per the slice-1.3 D38 precedent."""
    steps = _i1_steps()
    assert len(steps) >= 6, f"expected the I1 handler to enumerate its steps; got {steps}"
    # the step that WRITES the durable marker
    marker_idx = _step_index(steps, lambda l: "WRITE the durable marker" in l)
    # the step that THEN sets waiting="rebirth"
    waiting_idx = _step_index(steps, lambda l: "set `waiting = \"rebirth\"`" in l)
    assert marker_idx is not None, f"no marker-write step found in {steps}"
    assert waiting_idx is not None, f"no waiting-set step found in {steps}"
    # ordered: marker BEFORE waiting …
    assert marker_idx < waiting_idx, (
        f"the checkpoint-complete.marker write (step {steps[marker_idx][0]}) must precede "
        f"the waiting=rebirth set (step {steps[waiting_idx][0]}); got order {steps}"
    )
    # … and ADJACENT (no step inserted between proving-durable and committing the pause)
    assert waiting_idx == marker_idx + 1, (
        "the marker-write and waiting=rebirth steps must be ADJACENT (no step between "
        f"making resumability durable and committing the pause); got order {steps}"
    )
    # the document numbers them 4 then 5 (the AC's literal expectation)
    assert steps[marker_idx][0] == 4 and steps[waiting_idx][0] == 5, (
        f"AC1 pins the marker write as step 4 and the waiting set as step 5; got "
        f"{steps[marker_idx][0]} / {steps[waiting_idx][0]}"
    )


# =========================================================================== #
# P1-2 — I1 is ONE shared rebirth-checkpoint routine wired at EVERY claimed safe
# boundary (Plan, Execute, Verify, Ship), not just Execute.
# =========================================================================== #
def _stage_section(heading):
    """A `### Stage …` section body, bounded to the next `### `/`## ` heading."""
    return _section(_drive_md(), heading, level="### ")


# The shared-routine invocation each stage must carry: run the I1 Safe-boundary rebirth
# handler at that stage's safe boundary (detection is the Stop hook; this handler consumes
# the `rebirth_pending` the hook's steer set).
_I1_INVOCATION = "the **Safe-boundary rebirth handler** (§ I1"


@pytest.mark.parametrize(
    "heading",
    ["Stage 1 — Plan", "Stage 4b — Verify (optional)", "Stage 5 — Ship (once)"],
)
def test_i1_wired_into_plan_verify_ship_stage_sections(heading):
    """P1-2: each non-Execute autonomous stage (Plan, Verify, Ship) actually INVOKES the
    shared I1 rebirth handler at its safe boundary — so a rebirth signalled in
    that stage has a consumer. The invocation is asserted INSIDE the stage's own section."""
    section = _norm(_stage_section(heading))
    assert _I1_INVOCATION in section, (
        f"{heading} must invoke the Safe-boundary rebirth handler (§ I1) at its safe boundary"
    )


def test_execute_loop_still_wires_i1():
    """P1-2 regression: the Execute loop's existing I1 wiring is preserved (the
    fix ADDS the other stages, never drops Execute's)."""
    md = _norm(_drive_md())
    assert "the **Safe-boundary rebirth handler** (§ I1 above" in md, (
        "the Execute loop must still wire the I1 handler (preserved alongside the new sites)"
    )


# The Execute step-1 (phase DESIGN) call site: bounded to the `1. **Design the phase` step,
# from its number through the next top-level numbered step (`2. **Freeze base`).
def _execute_step1_design():
    md = _drive_md()
    start = md.index("1. **Design the phase")
    end = md.index("\n2. **Freeze base", start)
    return md[start:end]


def test_i1_wired_at_phase_design_call_site():
    """P1-1: the real call site — Execute step 1 (`/drive-design phase`) actually INVOKES the
    shared I1 rebirth handler AFTER the design converges (its marker cleared)
    and BEFORE freezing base / dispatching slices. So every boundary the I1 preamble
    enumerates has a real call site, not just a claim."""
    step1 = _norm(_execute_step1_design())
    assert _I1_INVOCATION in step1, (
        "Execute step 1 must invoke the Safe-boundary rebirth handler (§ I1) after the design "
        "converges, BEFORE freezing base / dispatching slices"
    )
    # the call site is at the right boundary — after the design marker is cleared
    assert "inflight-design-<P>.marker` is cleared" in step1, (
        "the step-1 I1 call must sit at the design-converged safe boundary (marker cleared)"
    )


# =========================================================================== #
# P1-1 — the DELEGATED Plan runner (`.claude/commands/drive-plan.md`), where the real
# autoplan + dual-voice design-review rounds run, INVOKES the shared rebirth handshake at
# its planning safe boundary. drive.md's Stage-1 wiring is parent-prose; the actual
# multi-round review context grows inside drive-plan.md, so a rebirth signalled during
# planning has NO consumer until Gate A unless the delegated runner itself calls it.
# =========================================================================== #
_PLAN_REBIRTH_CLAUSE = (
    "run the **Safe-boundary rebirth handler**"
)


def test_drive_plan_invokes_rebirth_handshake_at_planning_boundary():
    """P1-1: `.claude/commands/drive-plan.md` invokes the shared rebirth handler
    at its planning safe boundary — after each design-review round and before presenting Gate A
    — referencing drive.md's § I1 routine, so a rebirth signalled during author/autoplan/review
    is consumed rather than running on unhandled to Gate A."""
    plan = _norm(_drive_plan_md())
    assert _PLAN_REBIRTH_CLAUSE in plan, (
        "drive-plan.md must invoke the Safe-boundary rebirth handler"
    )
    # it fires at the planning safe boundary (after each design-review round, before Gate A)
    assert "after each design-review round" in plan, (
        "the drive-plan.md handshake must run after each design-review round"
    )
    assert "before presenting\nGate A".replace("\n", " ") in plan, (
        "the drive-plan.md handshake must run before presenting Gate A"
    )
    # it references drive.md's shared routine rather than duplicating the I1 prose
    assert "§ *I1 — Safe-boundary rebirth\nhandler*".replace("\n", " ") in plan, (
        "drive-plan.md must reference drive.md's § I1 routine (not duplicate it)"
    )
    # and names the load-bearing handshake steps (prove → marker → waiting → handoff).
    # Per D46 (slice 4.3), drive-plan.md names NO inline proof mode itself — it defers to
    # drive.md's § I1 as "the authority for the proof modes" — so the call-site says "prove
    # the checkpoint" and references I1 for the modes, rather than spelling `--mode checkpoint`.
    assert "prove the checkpoint" in plan and "checkpoint-complete.marker" in plan
    assert "the I1 routine is the authority for the proof modes" in plan, (
        "drive-plan.md must defer the proof modes to drive.md's § I1 (D46: no inline mode here)"
    )
    assert 'set `waiting="rebirth"`' in plan
    assert "/drive <runId>" in plan, "the handoff must surface the paste-ready resume line"


# =========================================================================== #
# AC2/AC3 — run-graph ↻ REBIRTH node + the handoff block.
# =========================================================================== #
def _handoff_block():
    """The fenced handoff block presented when `waiting=="rebirth"` (Present human pause
    step 3): the ```-fenced block whose first line starts the `↻ REBIRTH —` orientation."""
    md = _drive_md()
    start = md.index("↻ REBIRTH — this /drive run has checkpointed and is clearing context")
    fence_open = md.rindex("```", 0, start)
    fence_close = md.index("```", start)
    return md[fence_open: fence_close]


# =========================================================================== #
# AC4 — resume treats rebirth-waiting as CONTINUE; rebirth_pending re-arm at the
# sessionId-rebind step (single reset point). Bounded/enumerated by BULLET INDEX.
# =========================================================================== #
def _resume_bullets():
    """The resume reconciliation sub-bullet labels in document order (slice-1.3 rule)."""
    return _resume_bullet_labels(_resume_section())


def test_resume_rebirth_continue_bullet_after_rebind_and_marker():
    """AC4: the `waiting=="rebirth"` → CONTINUE bullet comes AFTER the sessionId-rebind
    (index 0) and the marker-consume bullets — an inserted/reordered bullet flips the index
    assertion. Reuses the slice-1.3 `_RESUME_BULLET_RE` structural rule, not raw offsets."""
    labels = _resume_bullets()
    assert len(labels) >= 5, f"expected the resume sub-bullets to enumerate; got {labels}"
    rebind_idx = next(
        (i for i, l in enumerate(labels) if l.startswith("sessionId rebind")), None
    )
    marker_idx = next(
        (i for i, l in enumerate(labels) if l.startswith("Consume `checkpoint-complete")),
        None,
    )
    rebirth_idx = next(
        (i for i, l in enumerate(labels) if l.startswith('`waiting == "rebirth"`')), None
    )
    assert rebind_idx == 0, f"sessionId-rebind must be the FIRST resume bullet; got {labels}"
    assert marker_idx is not None, f"no marker-consume bullet found in {labels}"
    assert rebirth_idx is not None, f"no rebirth-continue bullet found in {labels}"
    assert rebind_idx < rebirth_idx and marker_idx < rebirth_idx, (
        "the rebirth-continue bullet must come AFTER the sessionId-rebind AND the "
        f"marker-consume bullets; got order {labels}"
    )


def test_resume_rebirth_continue_is_fail_closed_re_proven():
    """P1-3 (tightened per the adversarial review): the resume consumer RE-PROVES resumability
    via BOTH `--mode checkpoint` AND `--mode state-lint` (D40 r2) BEFORE treating
    `waiting=="rebirth"` as a continue — it does NOT
    trust the marker's tip alone (a tip-matching marker is *necessary, NOT sufficient*: an open
    in-flight marker or mid-flight redesign span can postdate a tip-matching file). A failing/
    erroring proof OR a missing/stale marker FAILS CLOSED with `stop:checkpoint-unprovable` —
    never a silent continue. `waiting="rebirth"` is set ONLY by I1 after its own passing proof."""
    blob = _norm(_drive_md())
    # waiting=rebirth is set ONLY by I1 after a passing proof + marker (provenance claim)
    assert (
        '`waiting = "rebirth"` is set ONLY by the I1 handler AFTER a passing proof + a durable'
        " `checkpoint-complete.marker`" in blob
    ), "resume must state waiting=rebirth is set ONLY by I1 after a passing proof + marker"
    # the resume consumer RE-PROVES (not trust-tip-alone) before continuing
    assert "the resume consumer\nRE-PROVES resumability before continuing".replace("\n", " ") in blob, (
        "the resume consumer must RE-PROVE resumability before continuing"
    )
    # the re-prove names BOTH modes (D40 r2 — checkpoint AND state-lint, both clean)
    assert (
        "RE-PROVE via BOTH `bin/drive-conformance.sh $RUN_DIR --mode checkpoint` AND "
        "`bin/drive-conformance.sh $RUN_DIR --mode state-lint`"
    ) in blob, (
        "fail-closed must RE-PROVE via BOTH the checkpoint AND state-lint conformance modes"
    )
    # the marker's tip alone is NOT trusted (necessary-not-sufficient carve-out)
    assert "it does NOT trust the marker's tip alone" in blob, (
        "the resume must NOT trust the marker tip alone (necessary-not-sufficient)"
    )
    assert "`markerValid` is corroborating" in blob, (
        "the marker validity must be corroborating-only, never the authorization"
    )
    # missing/stale marker OR failing proof FAILS CLOSED with the unprovable STOP
    assert (
        "A failing/erroring proof, or a missing/stale marker, FAILS CLOSED" in blob
    ), "a failing proof OR a missing/stale marker must FAIL CLOSED"
    assert "do NOT silently clear+continue" in blob, (
        "fail-closed must explicitly forbid a silent clear+continue"
    )
    assert '`waiting = "stop:checkpoint-unprovable"`' in blob, (
        "a failing re-prove must STOP with stop:checkpoint-unprovable"
    )
    # the rebirth re-prove is the SOLE carve-out from the marker-consume from-scratch rule
    assert "SOLE carve-out from the marker-consume bullet" in blob, (
        "the rebirth re-prove must be the SOLE carve-out from the 'reconcile from scratch' rule"
    )
    # the marker-consume bullet records the validity the rebirth bullet consults
    assert "record this validity as `markerValid`" in blob, (
        "the marker-consume bullet must record the validity (markerValid) the rebirth-continue "
        "bullet consults (the marker is deleted there, so its validity must be captured)"
    )


# A `rebirth_pending` RESET assignment — `[state.]rebirth_pending = false` (optional
# backticks/`state.` prefix, flexible inner whitespace). Deliberately matches the ASSIGNMENT
# form (`= false`), NOT the JSON default `"rebirth_pending": false` (a `:` initializer) nor
# bare prose, so the count reflects real reset *writes* of the flag.
_REBIRTH_RESET_RE = re.compile(r"`?(?:state\.)?rebirth_pending`?\s*=\s*`?false`?")


def _assert_reset_on_resume_structural(drive_md):
    """AC4 / D36 (design-phase3.md L533-534) + P1-2 LOGICAL contract: the `rebirth_pending`
    reset is the reset-on-RESUME re-arm — it appears at the sessionId-rebind bullet (index 0,
    fresh-session resume) AND the rebirth-continue bullet (index 2, same-session re-paste), and
    is ABSENT from the I1 OUTGOING-session handler (where the flag must STAY SET). Factored so
    the flip-proof runs the SAME structural pin against a mutated COPY; raises AssertionError
    when a resume reset is dropped or the outgoing handler grows one.

    This replaces the old "exactly ONCE, rebind-only" pin: a same-session re-paste keeps
    `state.sessionId` unchanged and so skips the rebind reset, so the rebirth-continue path
    MUST carry its own unconditional reset — the contract is reset-on-resume (both paths), not
    a single textual write coupled to the rebind.

    `drive_md` is the RAW drive.md text (not `_norm`'d — the bullet bounding walks lines)."""
    section = _resume_section_of(drive_md)
    bodies = _resume_bullet_bodies(section)
    assert len(bodies) >= 3, f"expected the resume sub-bullets to enumerate; got {len(bodies)}"

    # the sessionId-rebind bullet (index 0) resets on the fresh-session resume path …
    assert _REBIRTH_RESET_RE.search(bodies[0]), (
        "the sessionId-rebind bullet must reset `rebirth_pending = false` (fresh-session resume)"
    )
    # … and the rebirth-continue bullet (index 2) resets on the same-session re-paste path —
    # the P1-2 fix: this is no longer absent (it MUST re-arm when the rebind reset is skipped).
    assert _REBIRTH_RESET_RE.search(bodies[2]), (
        "the rebirth-continue bullet must reset `rebirth_pending = false` (same-session "
        "re-paste, where the sessionId-rebind reset is skipped) — the P1-2 unconditional re-arm"
    )
    # … but the marker-consume bullet (index 1, the same-session NON-rebirth reconcile path)
    # must carry NO reset — a Gate/STOP-deferred rebirth_pending PERSISTS there (codex F1: the
    # reset is scoped to exactly the two resume paths, never a blanket every-resume clear).
    assert not _REBIRTH_RESET_RE.search(bodies[1]), (
        "the marker-consume bullet (same-session non-rebirth reconcile) must NOT reset "
        "`rebirth_pending` — a gate/STOP-deferred rebirth must PERSIST so I1 still hands off"
    )

    # The OUTGOING-session I1 handler must carry NO reset write — the flag STAYS SET there.
    i1 = _section(drive_md, "I1 — Safe-boundary rebirth handler", level="## ")
    assert not _REBIRTH_RESET_RE.search(i1), (
        "the I1 outgoing-session handler must NOT reset `rebirth_pending` — it STAYS SET "
        "through the outgoing pause (reset happens only on the incoming resume)"
    )


def _resume_section_of(drive_md):
    """The resume reconciliation bullet list of an arbitrary drive.md TEXT (the real file or a
    mutated COPY) — same bounds as `_resume_section` (Resume bullet → sibling Fresh-run bullet),
    parameterized for the flip-proof."""
    start = drive_md.index("- **Resume:**")
    end = drive_md.index("\n- **Fresh run:**", start)
    return drive_md[start:end]


def test_reset_on_resume_is_structural_not_prose_only():
    """AC4 / D36 (design-phase3.md L533-534) + P1-2: assert the `rebirth_pending` reset
    structurally fires on BOTH resume paths — the sessionId-rebind bullet AND the
    rebirth-continue bullet — and is ABSENT from the I1 outgoing handler, over the REAL merged
    drive.md, not just the prose CLAIM."""
    _assert_reset_on_resume_structural(_drive_md())


# =========================================================================== #
# AC8 — gate precedence (deterministic Seam A, NO goal): on approval Gate A fires the
# Seam A handoff, so Gate A DOES emit the `/drive <runId>` resume line (NO goal — the
# `/goal` mechanism was removed); Gate B hands NO goal and NO resume token (push is
# immediate). The OLD "NEITHER gate emits a resume token" invariant is intentionally
# superseded by the deterministic context-clear after Gate A. (Ground truth: drive-ship.md
# Gate B pushes after approval, no goal.)
# =========================================================================== #
def test_gate_precedence_gateA_emits_resume_via_seam_a():
    """AC8 (deterministic Seam A, NO goal): drive.md's gate-precedence prose states that on
    approval Gate A fires the Seam A handoff and so DOES emit the `/drive <runId>` resume
    line with NO goal (Execute begins in a fresh session), while Gate B hands NO goal and
    NO resume token (immediate push, no next leg). The OLD 'NEITHER gate emits a resume
    token' invariant is intentionally superseded — Gate A now clears context after approval."""
    blob = _norm(_drive_md())
    # Gate A now emits the resume line (NO goal — the /goal mechanism is gone), via Seam A
    assert (
        "Gate A DOES emit the `/drive <runId>` resume\nline (NO goal)".replace("\n", " ")
    ) in blob, (
        "gate precedence must state Gate A DOES emit the resume line (NO goal) "
        "(the deterministic Seam A handoff fires on approval)"
    )
    # Gate B still hands nothing — no goal, no resume token (immediate push)
    assert "**Gate B** hands NO goal and NO resume token" in blob, (
        "gate precedence must state Gate B hands NO goal and NO resume token (immediate push)"
    )
    # the OLD 'neither gate emits a resume token' claim must be GONE (Gate A now emits it)
    assert "NEITHER gate emits a `/drive <runId>` resume token" not in blob, (
        "the old 'NEITHER gate emits a /drive <runId> resume token' invariant must be gone — "
        "Gate A now emits it via the deterministic Seam A handoff"
    )


def test_gate_stop_wins_precedence_over_rebirth():
    """AC9 / P1-1: at a boundary where both a rebirth and a gate/STOP are due, the gate/STOP
    wins. `rebirth_pending` does NOT carry forward ACROSS the fresh-session resume (reset once
    at the rebind), but DOES PERSIST within the same outgoing session — the two halves of the
    ONE lifecycle story, pinned as contiguous clauses so the blanket-contradiction (a bare
    'does NOT carry forward') cannot return."""
    blob = _norm(_drive_md())
    assert "the **gate/STOP wins**" in blob, "gate/STOP must win precedence over rebirth"
    # qualified: does NOT carry forward ACROSS the fresh-session resume (not a blanket claim)
    assert "`rebirth_pending` does NOT carry forward ACROSS the fresh-session resume" in blob, (
        "rebirth_pending must be pinned as not carrying forward ACROSS the fresh-session "
        "resume (the qualified, non-contradictory claim — NOT a blanket 'does NOT carry "
        "forward')"
    )
    # the same-session PERSIST half, so the gate-precedence prose agrees with Leave-pending
    assert "WITHIN the same outgoing session it does PERSIST" in blob, (
        "gate-precedence prose must state the same-session PERSIST half (consistent with the "
        "I1 Leave-pending semantics), so the lifecycle is ONE consistent story"
    )


# =========================================================================== #
# AC11 — canonical `waiting` definition enumerates `rebirth` with its DUAL nature in BOTH
# drive.md sites AND the hook docstring.
# =========================================================================== #
def _assert_ac11_dual_nature(blob):
    """The AC11 dual-nature pin, factored so the flip-proof runs the SAME assertion against a
    mutated COPY. `blob` is `_norm`'d drive.md text; raises AssertionError on any drift."""
    assert "`waiting = \"rebirth\"` is the lone CONTINUE exception" in blob, (
        "the Autonomous-continuation contract must name rebirth the lone CONTINUE exception"
    )
    # both halves of the dual nature, contiguous
    assert "set-to-pause in the OUTGOING session" in blob, (
        "must state the outgoing-set half"
    )
    assert "auto-cleared-as-continue by the resume path in the INCOMING session" in blob, (
        "must state the auto-clear-on-resume half"
    )
    # the hook reads truthiness only (so this is a doc-contract amendment, not a behavior change)
    assert "The hook reads only `waiting`'s truthiness" in blob


def test_drive_md_autonomous_continuation_contract_enumerates_rebirth_dual():
    """AC11: drive.md's Autonomous-continuation contract enumerates `rebirth` as the lone
    CONTINUE exception with BOTH halves of its dual nature — set-to-pause in the OUTGOING
    session AND auto-cleared-as-continue on resume — as a contiguous clause."""
    _assert_ac11_dual_nature(_norm(_drive_md()))


def test_hook_docstring_enumerates_rebirth_dual():
    """AC11: bin/drive-stop-hook.py's docstring `waiting` field block enumerates `rebirth`
    with BOTH halves of its dual nature (outgoing-set; resume auto-clears as CONTINUE) and
    states the hook does NOT distinguish it (acts on truthiness only)."""
    doc = _norm(_hook_py())
    assert "`rebirth` is ALSO a truthy `waiting` value but NOT a human pause" in doc, (
        "the hook docstring `waiting` field must enumerate `rebirth` as a non-human-pause "
        "truthy waiting value"
    )
    assert "outgoing session sets it to checkpoint-and-hand-off" in doc, (
        "the docstring must state the outgoing-set half"
    )
    assert "the resume path auto-clears it as a CONTINUE (dual nature)" in doc, (
        "the docstring must state the auto-clear-on-resume half (dual nature)"
    )
    assert "The hook does not distinguish it — it acts on truthiness only" in doc, (
        "the docstring must state the hook acts on truthiness only"
    )


# =========================================================================== #
# CROSS-FILE INVARIANT — the hook's escalation steer (3.2) and drive.md's I1 handshake
# (3.1) agree: the hook steers the coordinator to do exactly what the I1 handler implements.
# =========================================================================== #
def _escalation_steer_text(src=None):
    """The ESCALATION-branch return string from the hook's `_rebirth_steer` — the steer
    emitted when `rebirth_pending` is already set and the run is still over hard water. We
    bound it to the `if run.get("rebirth_pending"):` branch so the pre-flag set-flag steer
    can't leak into the assertion.

    `src` defaults to the REAL merged hook source; the flip-proof passes a MUTATED COPY so
    the SAME accessor runs against it (mutate-a-copy, never the real file)."""
    if src is None:
        src = _hook_py()
    start = src.index('if run.get("rebirth_pending"):')
    end = src.index("# PRE-FLAG", start)
    return _norm(src[start:end])


def test_hook_escalation_steer_directs_the_i1_handshake():
    """Cross-file invariant: the hook's ESCALATION steer (slice 3.2) names the SAME handshake
    drive.md's I1 handler (slice 3.1) implements — at the NEXT safe boundary: perform the
    rebirth checkpoint + handoff per the I1 routine (proof = BOTH `--mode checkpoint` AND
    `--mode state-lint`, both clean), write `checkpoint-complete.marker`, set
    `waiting="rebirth"`, present the handoff block. So the hook steers the coordinator to do
    precisely what the I1 contract specifies (the hook never enacts it itself)."""
    steer = _escalation_steer_text()
    # the steer fires only over hard water with the flag already set
    assert "rebirth high-water mark and " in steer
    assert "state.rebirth_pending is already set" in steer
    # it defers to the coordinator's NEXT safe boundary — the I1 trigger condition
    assert "At your NEXT safe boundary (no open " in steer
    assert "inflight-*.marker" in steer
    # it points at the I1 routine as the proof authority (not a hard-coded handoff sequence)
    assert "I1 routine" in steer, "steer must defer to the drive.md § I1 routine"
    # the proof it names is the BOTH-modes contract — NOT checkpoint-only. Both modes named.
    assert "--mode checkpoint" in steer and "--mode state-lint" in steer, (
        "the escalation steer must name BOTH proof modes (the both-modes contract), not "
        "single out --mode checkpoint"
    )
    # NOT checkpoint-only: every `--mode checkpoint` mention is paired with state-lint.
    assert "--mode checkpoint AND --mode state-lint" in steer, (
        "the steer must present the both-modes proof, never a checkpoint-only proof surface"
    )
    assert "checkpoint-complete.marker" in steer, "steer must name the durable marker write"
    # the hook source escapes the quotes in the steer literal, so the raw text reads
    # `state.waiting=\"rebirth\"` — match that source form.
    assert r'state.waiting=\"rebirth\"' in steer, "steer must name the waiting=rebirth set"
    assert "present " in steer and "the handoff block" in steer, (
        "steer must name presenting the handoff block"
    )
    # the proof step is steered BEFORE the waiting set (the I1 fail-closed ordering)
    assert steer.index("--mode checkpoint") < steer.index(r'state.waiting=\"rebirth\"'), (
        "the escalation steer must order proof-then-pause (proof before waiting set), "
        "agreeing with I1's fail-closed ordering"
    )


# `rebirth` appears in the source-escaped form `\"rebirth\"` in the steer literal.
# Both proof modes are load-bearing shared tokens — a checkpoint-only steer must red.
_SHARED_STEER_TOKENS = (
    "--mode checkpoint",
    "--mode state-lint",
    "checkpoint-complete.marker",
    r'\"rebirth\"',
)


def _assert_steer_names_shared_tokens(steer):
    """The cross-file shared-token pin over the escalation steer, factored so the flip-proof
    runs the SAME assertion against a mutated COPY. Raises AssertionError on a missing token."""
    for token in _SHARED_STEER_TOKENS:
        assert token in steer, f"the escalation steer must name `{token}`"


def test_hook_escalation_and_i1_share_the_handshake_tokens():
    """Cross-file invariant (token agreement): every load-bearing token in the hook's
    escalation steer is the SAME token drive.md's I1 handler uses, so a rename on either
    side (e.g. the marker file, the conformance mode, the waiting value) reds this pin and
    surfaces the cross-file drift."""
    _assert_steer_names_shared_tokens(_escalation_steer_text())
    i1 = _norm(_i1_section())
    # the I1 handler names BOTH conformance proof modes, the marker, and the rebirth value
    assert "bin/drive-conformance.sh $RUN_DIR --mode checkpoint" in i1
    assert "--mode state-lint" in i1
    assert "checkpoint-complete.marker" in i1
    assert 'set `waiting = "rebirth"`' in i1


# =========================================================================== #
# AC-1/AC-2 — the context-of-execution summary shared step exists, is placed between the
# run-graph section and Pipeline, names its four data-source families, EXCLUDES the
# event-log, cross-references the Missing-artifact rule, and defines its four prose parts.
# =========================================================================== #
_CTX_SUMMARY_HEADING = "Emit context-of-execution summary (shared step)"


def _ctx_summary_section():
    """The body of the `## Emit context-of-execution summary (shared step)` section, bounded
    to the next `## `/`# ` heading (so its own `### ` children stay in), section-bounding every
    AC-1/AC-2 assertion so no token elsewhere in drive.md can satisfy them vacuously."""
    return _section(_drive_md(), _CTX_SUMMARY_HEADING, level="## ")


def test_context_summary_section_exists_and_names_sources():
    """AC-1/AC-2: drive.md carries a `## Emit context-of-execution summary (shared step)`
    section, placed AFTER `## Emit run graph` and BEFORE `## Pipeline`; its body names the
    four data-source families (state.json full surface, design.md, review/harden/finalize
    artifacts, decisions.md), EXCLUDES `event-log.jsonl`, cross-references the Missing-artifact
    rule, and defines the four prose parts (problem · where we are · done/decided · next).
    Section-bounded so a token elsewhere cannot satisfy it vacuously."""
    md = _drive_md()
    # positioned between the run-graph section and Pipeline
    run_graph_idx = md.index("## Emit run graph (shared step)")
    summary_idx = md.index("## " + _CTX_SUMMARY_HEADING)
    pipeline_idx = md.index("## Pipeline")
    assert run_graph_idx < summary_idx < pipeline_idx, (
        "the context-summary section must sit AFTER `## Emit run graph` and BEFORE `## Pipeline`"
    )
    section = _norm(_ctx_summary_section())
    # the four data-source families (mirrors the run graph's discipline)
    assert "`state.json` in full" in section, "must name the full state.json surface"
    assert "`design.md`" in section, "must name design.md as a source"
    assert (
        "review-<scope>-N.md" in section
        and "harden-<P>-N.md" in section
        and "review-finalize-<N>.md" in section
    ), "must name the fixed-format review/harden/finalize artifacts as a source"
    assert "`decisions.md`" in section, "must name decisions.md as a source"
    # the event-log EXCLUSION (no event-log parsing — event names drift)
    assert "NEVER parse `event-log.jsonl`" in section, (
        "the section must EXCLUDE event-log.jsonl parsing (event names drift)"
    )
    # cross-references the Missing-artifact rule (single-sourced with the run graph)
    assert "Missing-artifact rule (general — never fabricate)" in section, (
        "the section must cross-reference the run graph's Missing-artifact rule"
    )
    # the four prose parts, each mapped to concrete fields
    for part in ("**Problem**", "**Where we are**", "**Done / decided**", "**Next**"):
        assert part in section, f"the section must define the `{part}` prose part"


# =========================================================================== #
# AC-3/AC-4/AC-5 — the summary is invoked at BOTH fresh-session sites: Present human pause
# step 2 (rebirth-scoped, above the run graph) AND the resume path (a fresh-session-scoped
# LAST reconcile sub-bullet, index ≥ 3, bodies[0/1/2] preserved). The fenced paste block
# carries neither a summary nor a `/goal`.
# =========================================================================== #
def _present_human_pause_section():
    return _section(_drive_md(), "Present human pause (shared routine)", level="## ")


def test_context_summary_invoked_at_both_fresh_session_sites():
    """AC-3/AC-4/AC-5: Present human pause step 2 carries the rebirth-scoped
    summary-ABOVE-run-graph clause; the resume reconcile list carries a fresh-session-scoped
    orientation sub-bullet that is LAST and at index ≥ 3 (bodies[0/1/2] labels preserved); and
    the fenced `/drive <runId>` paste block carries neither the summary nor a `/goal`. All
    assertions are section-/bullet-bounded, not whole-file greps."""
    # (a) outgoing — Present human pause step 2, rebirth-scoped, ABOVE the run graph
    php = _norm(_present_human_pause_section())
    assert (
        'When `waiting == "rebirth"`, FIRST emit the context-of-execution summary' in php
    ), "Present human pause step 2 must carry the rebirth-scoped summary clause"
    assert "IMMEDIATELY ABOVE the run graph" in php, (
        "the rebirth-scoped clause must place the summary ABOVE the run graph"
    )
    # (b) incoming — the resume orientation sub-bullet is LAST, index ≥ 3, fresh-session-scoped
    labels = _resume_bullet_labels(_resume_section())
    bodies = _resume_bullet_bodies(_resume_section())
    # bodies[0/1/2] indices are preserved (AC4 structural pin depends on them)
    assert labels[0].startswith("sessionId rebind"), f"bodies[0] must stay the rebind; got {labels}"
    assert labels[1].startswith("Consume `checkpoint-complete"), (
        f"bodies[1] must stay marker-consume; got {labels}"
    )
    assert labels[2].startswith('`waiting == "rebirth"`'), (
        f"bodies[2] must stay rebirth-continue; got {labels}"
    )
    orient_idx = next(
        (i for i, l in enumerate(labels) if l.startswith("Fresh-session orientation")), None
    )
    assert orient_idx is not None, f"no Fresh-session-orientation resume bullet found; got {labels}"
    assert orient_idx >= 3, f"the orientation bullet must be at index ≥ 3; got {orient_idx}"
    assert orient_idx == len(labels) - 1, (
        f"the orientation bullet must be the LAST resume sub-bullet; got index {orient_idx} "
        f"of {len(labels)}"
    )
    orient_body = _norm(bodies[orient_idx])
    assert "Emit context-of-execution summary" in orient_body, (
        "the orientation bullet must invoke the shared summary section by heading"
    )
    assert "freshSessionResume" in orient_body, (
        "the orientation bullet must be scoped to a fresh-session resume (freshSessionResume)"
    )
    # capture↔consume contract (D11): the orientation bullet CONSUMES `freshSessionResume`,
    # so the sessionId-rebind bullet (bodies[0]) MUST DEFINE it — and define it BEFORE it
    # overwrites `state.sessionId` (the comparison reads the OLD persisted id). A dropped
    # capture would leave the consumer referencing an undefined variable; this pins the pair
    # together so one can't silently move without the other.
    rebind_body = _norm(bodies[0])
    assert "freshSessionResume =" in rebind_body, (
        "the sessionId-rebind bullet must CAPTURE `freshSessionResume =` so the orientation "
        "bullet's consumer is defined on BOTH branches (fresh vs same-session)"
    )
    assert rebind_body.index("freshSessionResume =") < rebind_body.index(
        "rewrite `state.sessionId`"
    ), (
        "the `freshSessionResume` capture must precede the `state.sessionId` overwrite "
        "(the comparison must read the OLD persisted sessionId, not the freshly-written one)"
    )
    # (c) the fenced paste block carries neither a summary nor a `/goal` (AC-5, structural pin)
    block = _handoff_block()
    assert "/drive <runId>" in block, "the paste block must keep the minimal resume line"
    assert "/goal" not in block, "the fenced paste block must carry no `/goal` line"
    assert "context-of-execution summary" not in block, (
        "the fenced paste block must not embed the summary (it is emitted ABOVE, outside the fence)"
    )


# =========================================================================== #
# AC-7 — the Autonomous-continuation contract is reworded: NO `/goal`, states the installed
# Stop hook is the SOLE continuation mechanism + the hook-absent manual-continue degradation,
# while the preserved dual-nature `waiting="rebirth"` paragraph keeps AC11 green.
# =========================================================================== #
def _autonomous_continuation_contract():
    """The Autonomous-continuation contract paragraph, bounded from its bold lead to the start
    of the preserved `waiting = "rebirth"` dual-nature paragraph — so the AC-7 assertions scan
    ONLY the contract, not the dual-nature paragraph AC11 pins."""
    md = _drive_md()
    start = md.index("**Autonomous-continuation contract (`waiting`).**")
    end = md.index('`waiting = "rebirth"` is the lone CONTINUE exception', start)
    return md[start:end]


def test_autonomous_continuation_contract_states_hook_sole():
    """AC-7: the Autonomous-continuation contract carries NO `/goal` and states the installed
    Stop hook is the SOLE turn-to-turn continuation mechanism plus the hook-absent
    manual-continue degradation; the preserved dual-nature paragraph still satisfies AC11.
    Section-bounded to the contract paragraph so a `/goal` elsewhere cannot mask a regression."""
    contract = _norm(_autonomous_continuation_contract())
    assert "/goal" not in contract, (
        "the reworded Autonomous-continuation contract must carry NO `/goal` reference"
    )
    assert "independent of `/goal`" not in contract, (
        "the old 'independent of /goal — use either or both' framing must be gone"
    )
    assert (
        "The installed Stop hook is the SOLE turn-to-turn continuation mechanism" in contract
    ), "the contract must state the installed Stop hook is the SOLE continuation mechanism"
    assert "manual-continue degradation" in contract, (
        "the contract must state the hook-absent manual-continue degradation"
    )
    # the preserved dual-nature paragraph (AC11 tokens) still passes unchanged
    _assert_ac11_dual_nature(_norm(_drive_md()))


# =========================================================================== #
# AC-6 — anti-reintroduction: ZERO live `/goal`-mechanism references survive across the
# live spec/doc surfaces (`.claude/commands/` + `docs/` + `README.md` + `CLAUDE.md` +
# `OPERATING.md`). The `/goal` command, the `<leg-condition>` leg selector, the "session
# goal (native /goal" concept, and the "execute-leg goal" per-leg goal were all removed;
# a future reintroduction into ANY live surface must RED this pin. Previously the removal
# was enforced ONLY by review-time grep — this makes it a durable contract.
#
# Carve-outs (deterministic, no judgment call at review time):
#   * `docs/trellis-analysis.md` — a SHA-pinned historical comparative-analysis snapshot
#     whose `/goal` mentions are point-in-time descriptions, NOT the live spec (excluded by
#     name; also absent in this tree, so exclusion is future-proofing).
#   * the incidental `boundary/goal` substring (drive-design.md `.../scope/boundary/goal`)
#     is excluded STRUCTURALLY by the `(?<!\w)` lookbehind: a live `/goal` command is always
#     preceded by whitespace / backtick / line-start, never a word char, whereas
#     `boundary/goal` has the word char `y` before the slash.
# Surfaces are resolved from `REPO_ROOT` (not cwd) so the pin is deterministic under any
# invocation dir, and read via pathlib directly (rg would skip the dot-prefixed
# `.claude/` directory as hidden — a real footgun this pin avoids).
# =========================================================================== #

# A live `/goal` command/mechanism reference: `/goal` at a word boundary whose slash is NOT
# preceded by a word char. Excludes the incidental `boundary/goal`; matches ` /goal`,
# "`/goal`", a line-leading `/goal`, and "(native /goal".
_LIVE_GOAL_RE = re.compile(r"(?<!\w)/goal\b")

# Other removed-mechanism tokens with no `/goal` substring (so `_LIVE_GOAL_RE` misses them).
_REMOVED_GOAL_TOKENS = ("<leg-condition>", "execute-leg goal")

# Excluded by name — the SHA-pinned historical snapshot (AC-6 carve-out).
_GOAL_GREP_EXCLUDE = ("docs/trellis-analysis.md",)


def _live_goal_surfaces():
    """The live spec/doc surfaces AC-6 scans, resolved from REPO_ROOT: every file under
    `.claude/commands/` and `docs/`, plus `README.md`, `CLAUDE.md`, `OPERATING.md`. Absent
    files are skipped (portable across worktrees); the SHA-pinned snapshot is carved out."""
    excluded = {REPO_ROOT / rel for rel in _GOAL_GREP_EXCLUDE}
    surfaces = []
    for sub in (".claude/commands", "docs"):
        d = REPO_ROOT / sub
        if d.is_dir():
            surfaces += sorted(p for p in d.rglob("*") if p.is_file())
    for top in ("README.md", "CLAUDE.md", "OPERATING.md"):
        p = REPO_ROOT / top
        if p.is_file():
            surfaces.append(p)
    return [p for p in surfaces if p not in excluded]


def test_no_live_goal_mechanism_reference_survives():
    """AC-6 (anti-reintroduction): ZERO live `/goal`-mechanism references across the live
    spec/doc surfaces — the `/goal` command (word-boundary, excluding the incidental
    `boundary/goal`), the `<leg-condition>` leg selector, and the "execute-leg goal" per-leg
    goal. Excludes the SHA-pinned `docs/trellis-analysis.md` snapshot. Reintroducing `/goal`
    into any live surface reds this pin (previously enforced only by review-time grep)."""
    offenders = []
    for path in _live_goal_surfaces():
        rel = path.relative_to(REPO_ROOT).as_posix()
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _LIVE_GOAL_RE.search(line):
                offenders.append(f"{rel}:{i}: {line.strip()}")
            for tok in _REMOVED_GOAL_TOKENS:
                if tok in line:
                    offenders.append(f"{rel}:{i}: [{tok}] {line.strip()}")
    assert not offenders, (
        "the `/goal` mechanism was removed (drive-ctx-summary run) and must STAY removed "
        "across the live spec/doc surfaces; found surviving live reference(s):\n"
        + "\n".join(offenders)
    )


# =========================================================================== #
# AC1 (R1) — the folded rebirth-gated CID claim lives in bodies[0] (the sessionId-rebind
# bullet) as its FIRST action, gated on waiting=="rebirth", BEFORE `freshSessionResume =`,
# and the resume prose carries NO nested `- **` that would shatter the index map.
# =========================================================================== #
def test_bodies0_carries_rebirth_gated_claim_before_freshSessionResume():
    """AC1: bodies[0] carries the atomic `os.replace` CLAIM as its FIRST action, GATED on
    `waiting == "rebirth"` (D26), renaming to the CID-keyed claim-target, BEFORE the
    `freshSessionResume =` capture; and bodies[0] contains exactly ONE `- **` (its own label)
    — the claim sub-cases are PROSE, not nested bold bullets (which would break the index map)."""
    section = _resume_section()
    bodies = _resume_bullet_bodies(section)
    b0 = bodies[0]
    b0n = _norm(b0)
    assert "os.replace" in b0n, "bodies[0] must carry the atomic os.replace claim"
    assert 'ONLY when `waiting == "rebirth"`' in b0n, "the claim must be gated on waiting==rebirth (D26)"
    assert "checkpoint-claimed-<$CLAUDE_CODE_SESSION_ID>-<CID>.marker" in b0n, (
        "the claim renames to the CID-keyed claim-target"
    )
    assert b0n.index("os.replace") < b0n.index("freshSessionResume ="), (
        "the claim must precede the `freshSessionResume =` capture (the FIRST action of the bullet)"
    )
    assert len(re.findall(r"^[ \t]+- \*\*", b0, re.MULTILINE)) == 1, (
        "bodies[0] must contain exactly ONE `- **` (its own label) — the claim sub-cases are PROSE"
    )


# =========================================================================== #
# AC13 (R1) — the resume WRITE-DISCIPLINE INVARIANT + rebirth-gating pinned as drive.md prose.
# =========================================================================== #
def test_write_discipline_invariant_rebirth_gating_pinned():
    """AC13: a drive.md PROSE pin asserts the write-discipline INVARIANT + rebirth-gating — the
    claim is rebirth-gated (a non-rebirth resume never claims); only the rename-winner or the
    non-rebirth sole-resumer writes state.json; a loser to a current-CID claim-target writes
    NOTHING; an auto-trigger never takes the sole-resumer path; detection is glob-by-CID +
    proof.tip==tip. Guards the SPEC invariant, not only the AC4 e2e test."""
    blob = _norm(_drive_md())
    assert "the claim is rebirth-gated (a non-rebirth resume never claims)" in blob
    assert (
        "only the rename-winner or the non-rebirth sole-resumer writes state.json" in blob
    ), "the write-discipline invariant (winner/sole-resumer only) must be pinned"
    assert "a loser to a current-CID claim-target writes NOTHING" in blob
    assert "an auto-trigger never takes the sole-resumer path" in blob
    assert "detection is glob-by-CID + proof.tip==tip" in blob


# =========================================================================== #
# AC5 (R1) — the auto-trigger CID-conditional gate + I1 step 5.7 host-local capability +
# per-CID create-only scheduled-marker dedup.
# =========================================================================== #
def test_auto_trigger_cid_gate_and_step_5_7_pinned():
    """AC5: drive.md pins the auto-trigger CID gate (proceed ONLY IF `pendingCID == CID_N` AND
    `waiting == "rebirth"`, else a clean no-op writing NO state.json; a human paste has no
    CID_N), AND I1 step 5.7 with the (c) HOST-LOCAL capability clause + the per-CID create-only
    scheduled-marker dedup + the fenced-block degradation."""
    blob = _norm(_drive_md())
    assert (
        'proceed to the reconciliation below ONLY IF `state.pendingCID == CID_N` AND '
        '`waiting == "rebirth"`' in blob
    ), "the auto-trigger CID gate must be pinned"
    assert "a late/duplicate auto-trigger is a clean no-op" in blob
    assert "A HUMAN paste `/drive <runId>` carries no `CID_N`" in blob
    # I1 step 5.7 exists, with the (c) host-local clause and per-CID create-only dedup.
    assert "Schedule the fresh-session auto-resume trigger (capability-detected)" in blob
    assert "(c) is HOST-LOCAL" in blob
    assert "auto-resume-scheduled-<CID>.marker` exists" in blob, "per-CID dedup must be pinned"
    assert "create-only" in blob
    assert "degrade to the fenced block only" in blob


# =========================================================================== #
# AC9 (R3) — the ONE authoritative observability sub-event rule.
# =========================================================================== #
def test_subevent_authoritative_rule_pinned():
    """AC9: drive.md carries the ONE authoritative observability sub-event rule — the six
    schemas, `date -u`, jq-built, APPEND-only, WRITE-ONLY (NEVER-parse restated), and the
    clear-after-record `idle_detected` seam with the absent/unparseable → no-emit guard."""
    blob = _norm(_drive_md())
    for kind in ("subagent-started", "codex-started", "suite-run-started",
                 "suite-run-finished", "fix-applied", "idle_detected"):
        assert kind in blob, f"the sub-event rule must define the `{kind}` schema"
    assert "extend the `event-log.jsonl` VOCABULARY only" in blob
    assert "`date -u`" in blob
    assert "APPEND-only" in blob
    assert "WRITE-ONLY" in blob
    assert "NEVER parse event-log.jsonl" in blob, "the never-parse invariant must be restated"
    # the idle_detected seam: clear-after-record, >30min, elapsedMin, fail-open guard
    assert "clear-after-record step above" in blob
    assert "> 30 min" in blob
    assert "elapsedMin = floor(elapsed/60)" in blob
    assert "absent/unparseable `startedAt` → NO line (fail-open)" in blob


# =========================================================================== #
# AC7 (R3) — the Present-human-pause notify side-effect: gateB differentiation, the anchored
# decision-bearing grammar, rebirth exclusion, pure-side-effect contract, drive-notify.sh call.
# =========================================================================== #
def test_notify_side_effect_gateB_and_anchored_grammar_pinned():
    """AC7: drive.md's Present-human-pause notify side-effect pins the gateB differentiation
    (the gate QUESTION + "reply 'approve' after reviewing the diff", NEVER a `/drive <runId>`
    line), fires ONLY for the ANCHORED `^(gateA|gateB|stop:.+|ask:.+)$` (never `rebirth`), is a
    pure side-effect (does NOT gate/block/write state.json), and invokes bin/drive-notify.sh."""
    blob = _norm(_drive_md())
    assert "Notify side-effect (R3, decision-bearing parks only)" in blob
    assert "`^(gateA|gateB|stop:.+|ask:.+)$` (NEVER `rebirth`)" in blob, (
        "the notify must fire only for the anchored decision-bearing grammar, never rebirth"
    )
    assert (
        'gateB: the gate QUESTION + "reply \'approve\' after reviewing the diff" '
        "(NEVER a `/drive <runId>` paste line)" in blob
    ), "the gateB message must carry the question + approve-instruction, NEVER a /drive paste line"
    assert 'bin/drive-notify.sh --run-dir "$RUN_DIR" --waiting "$waiting"' in blob
    assert "it does not gate, block, or write `state.json`" in blob
    assert "never notify on rebirth" in blob


# =========================================================================== #
# AC14 (R1) — the state.pendingCID lifecycle + tolerated-extra doc-consistency (prose pin).
# =========================================================================== #
def test_pendingcid_lifecycle_tolerated_extra_prose_pinned():
    """AC14: drive.md pins the pendingCID lifecycle — I1 step 5 sets `state.pendingCID = CID` in
    the SAME write as `waiting="rebirth"`; the rebirth-continue bullet clears it with
    `waiting=null`; it is a TOLERATED-EXTRA field (template default null), NOT a CORE key / not
    state-lint-required, NOT in CLAUDE.md. The state.json TEMPLATE carries `"pendingCID": null`."""
    md = _drive_md()
    blob = _norm(md)
    assert '"pendingCID": null' in md, "the state.json template must carry pendingCID (default null)"
    assert 'set `state.waiting = "rebirth"` AND `state.pendingCID = CID`' in blob, (
        "I1 step 5 must set pendingCID together with waiting=rebirth in ONE write"
    )
    assert "clear `state.waiting = null`, clear `state.pendingCID = null`" in blob, (
        "the rebirth-continue bullet must clear pendingCID together with waiting=null"
    )
    assert "TOLERATED-EXTRA state.json field" in blob
    assert "NOT a CORE key and NOT state-lint-required" in blob
    assert "is NOT documented in CLAUDE.md" in blob


# =========================================================================== #
# AC-P1 (R1 finalize) — the winner path must VERIFY CID == state.pendingCID BEFORE claiming
# and STOP fail-closed on a MISMATCH (a stale/forged/wrong-handoff marker), closing the
# double-drive hole where the winner claimed under a wrong CID key that the loser's
# pendingCID-keyed glob would miss.
# =========================================================================== #
def test_winner_verifies_cid_equals_pendingcid():
    """AC-P1: drive.md case (b) mandates the WINNER VERIFY `CID == state.pendingCID` BEFORE
    claiming, os.replace ONLY on a MATCH, and STOP fail-closed (`stop:checkpoint-unprovable`)
    on a MISMATCH — so the claim-target is ALWAYS keyed on pendingCID and the loser's
    pendingCID-keyed glob can never miss it (no double-drive). Guards the live PROSE the
    coordinator follows, not only the executable mirror."""
    blob = _norm(_drive_md())
    assert "VERIFY `CID == state.pendingCID` BEFORE claiming" in blob, (
        "the winner must verify CID == state.pendingCID before claiming"
    )
    assert "On a MISMATCH (`CID != state.pendingCID`" in blob, (
        "case (b) must define the MISMATCH outcome explicitly"
    )
    assert "do NOT claim and do NOT continue: STOP fail-closed" in blob, (
        "a MISMATCH must fail closed (no claim, no continue), not claim under a wrong key"
    )



# =========================================================================== #
# Slice 1.1 — Pre-Execute resume guard (phaseList × stage matrix). Fixes the
# resume "Current phase" vacuous-∀ misroute: a Plan-stage rebirth with an empty
# `phaseList` must resume into Plan, not fall through to the PAST-Execute /
# Finalize derivation. Pins P1–P4b/P6/P7 (+ P5 atomic Gate-A transition) bind the
# guard prose SECTION-BOUND (never a whole-file grep); every load-bearing guard-arm
# token asserted by `_assert_guard_structural` is mutation-verified by a committed
# `_mutation_reds` flip below — the P1 route's four sub-clauses (empty+autonomous
# Plan re-entry, Premises re-entry, do-NOT-re-enter Premises; the non-empty legitimate
# fall-through) plus P2/P3/P4/P4b, one flip each.
# =========================================================================== #
def _guard_body():
    """The Pre-Execute resume guard sub-bullet's own FULL span (section-bound), or None.
    Sliced by the live `_RESUME_BULLET_RE` enumeration so a pin scans ONLY the guard's
    text — no inner guard line may begin `  - **` (it would truncate this body)."""
    bodies = _resume_bullet_bodies(_resume_section())
    return next(
        (b for b in bodies if b.lstrip().startswith("- **Pre-Execute resume route")),
        None,
    )


def _current_phase_body_of(section):
    """The Current-phase resume sub-bullet's FULL span from an ARBITRARY resume section."""
    bodies = _resume_bullet_bodies(section)
    return next(
        (b for b in bodies if b.lstrip().startswith("- **Current phase")),
        None,
    )


def test_pre_execute_guard_positive_route():
    """P1 (AC1): the empty-`phaseList` + `{premises,plan}` + autonomous case re-enters the
    pipeline at Plan/Premises (re-invoke `/drive-plan`), NOT the Current-phase derivation;
    the non-empty legitimate case falls through. Section-bound to the guard body only."""
    body = _guard_body()
    assert body is not None, "the Pre-Execute resume guard sub-bullet must be enumerated"
    nb = _norm(body)
    assert "set `stage = plan` and **re-invoke `/drive-plan`**" in nb, (
        "empty+plan+autonomous must re-invoke /drive-plan (not route to Current-phase)"
    )
    assert "`stage == premises` → resume **Stage 0 (Premises)**" in nb, (
        "empty+premises+autonomous must resume Stage 0 (Premises)"
    )
    assert "Do **NOT** re-enter Stage 0 Premises when `task.md`/`design.md` already exist" in nb, (
        "the autonomous branch must NOT re-ask the premise when task.md/design.md exist"
    )
    assert "**fall through UNCHANGED** to the Current-phase" in nb, (
        "the non-empty legitimate case must fall through to the Current-phase derivation"
    )


def test_current_phase_derivation_bound_to_nonempty_phaselist():
    """P2 (AC2): the Current-phase derivation is reached ONLY when `phaseList` is non-empty —
    the anti-vacuity precondition. Section-bound to the Current-phase bullet body. Deleting
    the Interface-2 precondition clause reds this (mutation-verified below by
    `test_pre_execute_guard_current_phase_precondition_mutation_reds`)."""
    body = _current_phase_body_of(_resume_section())
    assert body is not None, "the Current-phase resume sub-bullet must be enumerated"
    assert "reached ONLY when `state.phaseList` is non-empty" in _norm(body), (
        "the Current-phase derivation must be bound to a non-empty phaseList (anti-vacuity)"
    )


def test_pre_execute_guard_parked_waiting_represent():
    """P3 (AC3): empty+plan+parked (`waiting` ∈ {gateA, ask:*, stop:*}) RE-PRESENTS the pause
    via Present human pause, NOT a /drive-plan re-invoke. Section-bound to the guard body."""
    nb = _norm(_guard_body())
    assert "`state.waiting` ∈ {`gateA`, `ask:*`, `stop:*`} →" in nb, (
        "the parked-pause branch must key on waiting ∈ {gateA, ask:*, stop:*}"
    )
    assert "RE-PRESENT" in nb and "Present human pause" in nb, (
        "the parked-pause branch must RE-PRESENT via the Present human pause routine"
    )
    assert "Do NOT re-enter a stage or re-invoke a command" in nb, (
        "the parked-pause branch must NOT swallow the pause into a re-invoke"
    )


def test_pre_execute_guard_failclosed_empty_corner():
    """P4 (AC4): empty+later-stage (execute/finalize/verify/ship/done or unknown) STOPs with
    `stop:phaselist-malformed` — never silently restarts Plan. Section-bound to the guard."""
    nb = _norm(_guard_body())
    assert "`stage ∈ {execute, finalize, verify, ship, done}` or unknown → an empty" in nb, (
        "the empty-branch later-stage arm must be present (` or unknown → an empty` suffix)"
    )
    assert "Fail closed: STOP" in nb, "the empty later-stage corner must fail closed with a STOP"
    assert '`waiting = "stop:phaselist-malformed"`' in nb, (
        "the STOP must set waiting=stop:phaselist-malformed"
    )
    assert "never silently restart at Plan" in nb, (
        "the empty later-stage corner must NEVER silently restart Plan (would discard progress)"
    )


def test_pre_execute_guard_failclosed_symmetric_nonempty_corner():
    """P4b (AC4b): non-empty+pre-Execute (`{premises,plan}` or unknown) STOPs with
    `stop:phaselist-malformed` — the SYMMETRIC corner --mode state-lint under-polices — and
    does NOT fall through; the fall-through is CONDITIONAL on `stage ≥ execute`, never
    unconditional. Section-bound to the guard body."""
    nb = _norm(_guard_body())
    assert "`stage ∈ {premises, plan}` or unknown → **fail-closed STOP**" in nb, (
        "the non-empty pre-Execute corner must fail closed (symmetric malformed STOP)"
    )
    assert "a non-empty `phaseList` at a pre-Execute stage is the SYMMETRIC malformed corner" in nb, (
        "the symmetric malformed corner must be named"
    )
    assert "ALWAYS carries `stage ≥ execute`, so this NEVER false-blocks a legitimate resume" in nb, (
        "the symmetric STOP must document why it never false-blocks a legitimate resume"
    )
    assert "`stage ∈ {execute, finalize, verify, ship, done}` → **fall through UNCHANGED**" in nb, (
        "the non-empty fall-through must be CONDITIONAL on stage ≥ execute (not unconditional)"
    )


def test_atomic_gateA_transition_both_files():
    """P5 (AC5): drive.md § Stage 1 states the Gate-A mutation as ONE atomic state.json write
    (stage+lastGate+waiting+phaseList together, never two writes); drive-plan.md is consistent
    (not two separable writes). Section-bound to the Stage-1 body / the After-this-stage
    region — never a whole-file grep."""
    stage1 = _norm(_stage_section("Stage 1 — Plan"))
    assert "single atomic `state.json` write" in stage1, (
        "drive.md Stage 1 must call the Gate-A transition a single atomic state.json write"
    )
    for field in ("`stage = \"execute\"`", "`lastGate = \"A\"`", "`waiting = null`", "parsed `phaseList`"):
        assert field in stage1, f"the atomic write must name {field} in the same clause"
    assert "never\n`stage=execute` first and `phaseList` in a later write".replace("\n", " ") in stage1, (
        "drive.md must state the negative intent (never stage=execute first, phaseList later)"
    )
    after = _norm(_section(_drive_plan_md(), "After this stage", level="## "))
    assert "ONE atomic `state.json` write" in after, (
        "drive-plan.md § After this stage must state the transition is ONE atomic write "
        "(doc-drift guard, consistent with drive.md § Stage 1)"
    )


def test_pre_execute_guard_is_adjacent_between_rebirth_and_current_phase():
    """P6 (AC6): the guard sits at resume-bullet index 3 — EXACTLY between the
    `waiting=="rebirth"` bullet (its own earlier bullet must have cleared `waiting`) and the
    Current-phase bullet, ADJACENT on both sides (a sibling slipped between either pair breaks
    the "runs BEFORE Current phase, after rebirth clears waiting" contract)."""
    labels = _resume_bullet_labels(_resume_section())
    guard_idx = next(i for i, l in enumerate(labels) if l.startswith("Pre-Execute resume route"))
    rebirth_idx = next(i for i, l in enumerate(labels) if l.startswith('`waiting == "rebirth"`'))
    phase_idx = next(i for i, l in enumerate(labels) if l.startswith("Current phase"))
    assert guard_idx == rebirth_idx + 1 and phase_idx == guard_idx + 1, (
        f"guard must sit ADJACENT — immediately after rebirth and immediately before "
        f"Current phase; got rebirth={rebirth_idx}, guard={guard_idx}, phase={phase_idx}"
    )


def _assert_guard_structural(drive_md):
    """P7 factoring: bound the guard + Current-phase bullets from an ARBITRARY drive.md TEXT
    (real or mutated) and re-assert the load-bearing P1/P3/P4/P4b/P2 tokens, so a mutation
    that guts a malformed-corner STOP reds. Raises AssertionError when a clause is unbound."""
    section = _resume_section_of(drive_md)
    bodies = _resume_bullet_bodies(section)
    guard = next((b for b in bodies if b.lstrip().startswith("- **Pre-Execute resume route")), None)
    phase = next((b for b in bodies if b.lstrip().startswith("- **Current phase")), None)
    assert guard is not None, "the Pre-Execute resume guard bullet must be enumerated"
    assert phase is not None, "the Current-phase bullet must be enumerated"
    nb = _norm(guard)
    np = _norm(phase)
    # P1 (positive route) — all four load-bearing sub-clauses of the autonomous arm
    assert "set `stage = plan` and **re-invoke `/drive-plan`**" in nb
    assert "`stage == premises` → resume **Stage 0 (Premises)**" in nb
    assert "Do **NOT** re-enter Stage 0 Premises when `task.md`/`design.md` already exist" in nb
    assert "**fall through UNCHANGED** to the Current-phase" in nb
    # P3 (parked re-present)
    assert "`state.waiting` ∈ {`gateA`, `ask:*`, `stop:*`} →" in nb
    # P4 (empty corner fail-closed) — the load-bearing empty-branch STOP
    assert "`stage ∈ {execute, finalize, verify, ship, done}` or unknown → an empty" in nb
    assert "never silently restart at Plan" in nb
    # P4b (symmetric non-empty corner fail-closed)
    assert "`stage ∈ {premises, plan}` or unknown → **fail-closed STOP**" in nb
    # P2 (anti-vacuity precondition on the Current-phase bullet)
    assert "reached ONLY when `state.phaseList` is non-empty" in np


def test_pre_execute_guard_is_structural_not_prose_only():
    """P7 (AC8): the factored guard structural pin is green on the REAL merged drive.md."""
    _assert_guard_structural(_drive_md())


def test_pre_execute_guard_empty_branch_mutation_reds():
    """P7 (AC8) non-vacuity: gutting the empty-branch later-stage STOP unbinds P4 → reds."""
    mutated = _drive_md().replace(
        "`stage ∈ {execute, finalize, verify, ship, done}` or unknown → an empty",
        "(empty-branch STOP removed)",
    )
    with pytest.raises(AssertionError):
        _assert_guard_structural(mutated)


def test_pre_execute_guard_symmetric_branch_mutation_reds():
    """P7 (AC8) non-vacuity: reverting the non-empty branch to an unconditional fall-through
    (removing the symmetric STOP) unbinds P4b → reds."""
    mutated = _drive_md().replace(
        "`stage ∈ {premises, plan}` or unknown → **fail-closed STOP**",
        "(symmetric STOP removed)",
    )
    with pytest.raises(AssertionError):
        _assert_guard_structural(mutated)


def test_pre_execute_guard_current_phase_precondition_mutation_reds():
    """P7 (AC8) non-vacuity: gutting the Current-phase precondition clause (Interface 2)
    unbinds P2 → reds. The `old` substring is the exact anti-vacuity token P2 asserts on the
    Current-phase bullet body (unique in drive.md, single raw line)."""
    mutated = _drive_md().replace(
        "reached ONLY when `state.phaseList` is non-empty",
        "(precondition removed)",
    )
    with pytest.raises(AssertionError):
        _assert_guard_structural(mutated)


def test_pre_execute_guard_parked_pause_mutation_reds():
    """P7 (AC8) non-vacuity: gutting the empty+plan parked-pause clause unbinds P3 → reds.
    The `old` substring is the exact parked-waiting token P3 asserts on the guard body
    (unique in drive.md, single raw line)."""
    mutated = _drive_md().replace(
        "`state.waiting` ∈ {`gateA`, `ask:*`, `stop:*`} →",
        "(parked-pause clause removed)",
    )
    with pytest.raises(AssertionError):
        _assert_guard_structural(mutated)


def test_pre_execute_guard_positive_route_mutation_reds():
    """P7 (AC8) non-vacuity: gutting the empty+autonomous Plan re-entry arm unbinds P1 → reds
    — completes "every guard arm non-vacuous". The `old` substring is the load-bearing chunk
    of the P1 re-invoke-`/drive-plan` token (unique in drive.md, single raw line)."""
    mutated = _drive_md().replace(
        "`stage = plan` and **re-invoke `/drive-plan`**",
        "(positive Plan re-entry removed)",
    )
    with pytest.raises(AssertionError):
        _assert_guard_structural(mutated)


def test_pre_execute_guard_premises_reentry_mutation_reds():
    """P7 (AC8) non-vacuity: gutting the empty+autonomous Premises re-entry sub-clause unbinds
    the P1-arm Premises token → reds. The `old` substring is the exact Premises-re-entry token
    now asserted in `_assert_guard_structural` (unique in drive.md, single raw line)."""
    mutated = _drive_md().replace(
        "`stage == premises` → resume **Stage 0 (Premises)**",
        "(Premises re-entry removed)",
    )
    with pytest.raises(AssertionError):
        _assert_guard_structural(mutated)


def test_pre_execute_guard_no_reenter_premises_mutation_reds():
    """P7 (AC8) non-vacuity: gutting the do-NOT-re-enter-Premises guard sub-clause unbinds the
    P1-arm do-not-re-enter token → reds. The `old` substring is the exact do-not-re-enter token
    now asserted in `_assert_guard_structural` (unique in drive.md, single raw line)."""
    mutated = _drive_md().replace(
        "Do **NOT** re-enter Stage 0 Premises when `task.md`/`design.md` already exist",
        "(do-not-re-enter Premises removed)",
    )
    with pytest.raises(AssertionError):
        _assert_guard_structural(mutated)


def test_pre_execute_guard_fall_through_mutation_reds():
    """P7 (AC8) non-vacuity: gutting the non-empty legitimate FALL-THROUGH clause unbinds the
    P1-route fall-through token → reds. The `old` substring `**fall through UNCHANGED**` is the
    load-bearing chunk of the fall-through token `_assert_guard_structural` asserts (unique in
    drive.md; the full token wraps a raw newline, so the flip keys on this unique sub-token)."""
    mutated = _drive_md().replace(
        "**fall through UNCHANGED**",
        "(fall-through removed)",
    )
    with pytest.raises(AssertionError):
        _assert_guard_structural(mutated)
