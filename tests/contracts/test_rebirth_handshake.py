"""Rebirth-handshake cross-file contract pins.

The lever-2 rebirth pause/resume handshake is split across two files that MUST agree:
  * `.claude/commands/drive.md` — the coordinator prose: the I1 safe-boundary handler, the
    `↻ REBIRTH` run-graph node, the handoff block, the resume rebirth-continue +
    `rebirth_pending` re-arm, the canonical `waiting` amendment, and gate precedence.
  * `bin/drive-stop-hook.py` — the Stop-hook escalation steer: once `rebirth_pending` is set
    and the run is still over hard water, the hook steers the coordinator to perform the I1
    handshake at its next safe boundary.

A drift on EITHER side — a reordered I1 step, a dropped legend glyph, a desynced canonical
`waiting` definition, a hook steer that no longer names the handshake the prose implements —
reds a pin here. The pins are STRUCTURAL/bounded, NOT loose substrings: section-bounded
enumeration + by-index ordering (`_I1_STEP_RE`, `_RESUME_BULLET_RE`), contiguous-clause
literals (whitespace-normalized), and a total-over-the-enum selector check. Each load-bearing
pin is proven to RED against a mutated COPY of the relevant prose/code (never the real files)
in the accompanying `test_*_flips_on_*` cases.
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
    `- **Resume:**` bullet to the next `## ` heading — its nested `- **<Label>:**`
    sub-bullets are the resume reconciliation steps (mirrors slice 1.3's accessor)."""
    md = _drive_md()
    start = md.index("- **Resume:**")
    end = md.index("\n## ", start)
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
    start = md.index("↻ REBIRTH — this /drive run is approaching its context budget")
    fence_open = md.rindex("```", 0, start)
    fence_close = md.index("```", start)
    return md[fence_open: fence_close]


def _handoff_goal_line():
    """The `/goal …` line inside the bounded handoff block, whitespace-normalized — the
    leg-aware re-arm line whose trailing `<leg-condition>` placeholder the selector binds.
    Bounded to the handoff block so an unrelated `/goal` line elsewhere can't satisfy it."""
    block = _norm(_handoff_block())
    start = block.index("/goal The /drive run <runId> is resuming after a context-pressure")
    # the line is the goal sentence through its trailing `<leg-condition>` placeholder token
    return block[start:]


def test_handoff_block_goal_line_carries_leg_condition_placeholder():
    """AC12: the handoff block's `/goal` re-arm line actually CONTAINS the `<leg-condition>`
    placeholder token (not a dropped/empty tail) — so the leg-aware condition is bound at
    resume, not silently omitted. Dropping the placeholder from the `/goal` line reds this."""
    goal_line = _handoff_goal_line()
    assert "<leg-condition>" in goal_line, (
        "the handoff block's `/goal` re-arm line must carry the `<leg-condition>` placeholder "
        "token (a dropped placeholder would re-arm a leg-blind goal)"
    )


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
    mutated COPY) — same bounds as `_resume_section`, parameterized for the flip-proof."""
    start = drive_md.index("- **Resume:**")
    end = drive_md.index("\n## ", start)
    return drive_md[start:end]


def test_reset_on_resume_is_structural_not_prose_only():
    """AC4 / D36 (design-phase3.md L533-534) + P1-2: assert the `rebirth_pending` reset
    structurally fires on BOTH resume paths — the sessionId-rebind bullet AND the
    rebirth-continue bullet — and is ABSENT from the I1 outgoing handler, over the REAL merged
    drive.md, not just the prose CLAIM."""
    _assert_reset_on_resume_structural(_drive_md())


# =========================================================================== #
# AC8 — gate precedence (D45): Gate A hands the next leg's /goal line; Gate B hands NONE
# (push is immediate); NEITHER gate emits /drive <runId>; rebirth uniquely contributes the
# runId resume line. (Ground truth: drive-ship.md Gate B pushes after approval, no goal.)
# =========================================================================== #
def test_gate_precedence_neither_gate_emits_runid_resume():
    """AC8/D45: drive.md's gate-precedence prose states Gate A hands the next leg's `/goal`
    line on approval and Gate B hands NONE (immediate push, no next leg), NEITHER emits a
    `/drive <runId>` resume token, and the runId resume line is the rebirth handshake's
    DISTINCT contribution. (Corrected from the false 'BOTH gates hand a goal' claim.)"""
    blob = _norm(_drive_md())
    assert (
        "**Gate A** hands the next leg's `/goal` line on approval; **Gate B** hands NO goal "
        "(after Gate-B approval the push is immediate — there is no next leg)"
    ) in blob, (
        "gate precedence must state Gate A hands the next leg's /goal line and Gate B hands "
        "NONE (immediate push) — not the false 'BOTH gates hand a goal'"
    )
    # the false claim must NOT remain anywhere
    assert "BOTH Gate A and Gate B hand the next leg's `/goal` line" not in blob, (
        "the false 'BOTH Gate A and Gate B hand the next leg's /goal line' claim must be gone"
    )
    assert (
        "NEITHER gate emits a `/drive <runId>` resume token (that runId resume line is the "
        "rebirth handshake's distinct contribution)"
    ) in blob, (
        "gate precedence must state NEITHER gate emits `/drive <runId>` and that the runId "
        "resume line is rebirth's distinct contribution"
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
# AC12 — the rebirth-handoff `/goal <leg-condition>` selector is TOTAL over the stage enum
# (premises, plan, execute, finalize, verify, ship) → exactly one leg-condition each.
# =========================================================================== #
# A leg-condition selector bullet: a list item (`- `) keyed on `stage` that lists the stages
# it covers in a `{…}` brace group and maps them to a leg-CONDITION body. Loosened from the
# original (which hard-coded a 3-space indent, a `:`-terminated single line, and a 5-space
# one-line body) to pin the MEANING — the stage-set → condition partition — not incidental
# indentation/wrapping. Still bites on a real partition change: the braces capture is the
# load-bearing selector, and `cond` must be non-empty (a stage moved/dropped reds the
# total-coverage check below; a body-less bullet reds the non-empty check).
#   - `stages`: everything inside the first `{…}` after `stage` (the covered stage tokens).
#   - `cond`  : the bullet's remaining text after the brace group up to the next sibling
#               `- ` bullet (or block end) — wrap-tolerant, so a reflowed multi-line
#               condition still reads as one non-empty body.
_STAGE_ENUM = ("premises", "plan", "execute", "finalize", "verify", "ship")
_LEG_BULLET_RE = re.compile(
    r"^\s*- .*?`stage`.*?\{(?P<stages>[^}]*)\}(?P<cond>.*?)(?=^\s*- |\Z)",
    re.MULTILINE | re.DOTALL,
)
_STAGE_TOK_RE = re.compile(r"`\"(\w+)\"`")


def _leg_selector_section():
    """The `Select <leg-condition> by state.stage` block — bounded from its bolded heading
    to the next blank-line-separated paragraph, so only its selector bullets are scanned."""
    md = _drive_md()
    start = md.index("**Select `<leg-condition>` by `state.stage`**")
    end = md.index("\n\n", start)
    return md[start:end]


def test_leg_condition_selector_is_total_over_stage_enum():
    """AC12: the rebirth-handoff `/goal <leg-condition>` selector covers the FULL stage enum
    (premises, plan, execute, finalize, verify, ship) with each stage mapped to exactly ONE
    leg-condition. A stage dropped (a successor resumes with no goal) or double-mapped (an
    ambiguous selection) flips the test."""
    section = _leg_selector_section()
    bullets = _LEG_BULLET_RE.findall(section)
    assert bullets, f"no leg-condition selector bullets found in:\n{section}"
    covered = []
    for stages_blob, cond in bullets:
        toks = _STAGE_TOK_RE.findall(stages_blob)
        assert toks, f"a selector bullet listed no stage tokens: {stages_blob!r}"
        assert cond.strip(), "every selector bullet must carry a non-empty leg-condition"
        covered.extend(toks)
    # TOTAL: every enum stage is covered …
    assert set(covered) == set(_STAGE_ENUM), (
        f"the leg-condition selector must be TOTAL over the stage enum {_STAGE_ENUM}; "
        f"covered {sorted(set(covered))}"
    )
    # … exactly ONCE each (no stage double-mapped to two leg-conditions)
    assert len(covered) == len(set(covered)) == len(_STAGE_ENUM), (
        f"each stage must map to EXACTLY ONE leg-condition; got {sorted(covered)}"
    )


# The two canonical leg-condition semantics (whitespace-normalized, meaning-bearing
# fragments — NOT the whole line, so benign reflow/added qualifiers don't false-red). Each
# is the distinctive "NOT met while autonomous <leg-work> remains" clause that the resume
# `/goal` must carry for its leg; they mirror the Stage-0/Gate-A leg-goal definitions.
#   - PLANNING leg (premises, plan): autonomous planning/design/autoplan/review work remains.
#   - EXECUTE   leg (execute, finalize, verify, ship): autonomous implement/review/harden/verify/ship.
_PLANNING_COND = "NOT met while autonomous planning"
_PLANNING_COND_TAIL = "design, autoplan, dual-voice review) work remains."
_EXECUTE_COND = "NOT met while autonomous implement / review / harden / finalize / verify / ship work remains."

# The stage-set that keys each leg, as the frozensets the selector partition must produce.
_PLANNING_STAGES = frozenset({"premises", "plan"})
_EXECUTE_STAGES = frozenset({"execute", "finalize", "verify", "ship"})


def _leg_bullet_map(section):
    """Map each selector bullet's covered stage-set (a frozenset of stage tokens) to its
    whitespace-normalized leg-condition body. Reuses the AC12 `_LEG_BULLET_RE`/`_STAGE_TOK_RE`
    enumeration so the mapping pin walks the SAME selector partition the totality pin does."""
    out = {}
    for stages_blob, cond in _LEG_BULLET_RE.findall(section):
        toks = frozenset(_STAGE_TOK_RE.findall(stages_blob))
        out[toks] = _norm(cond)
    return out


def _assert_leg_condition_mapping(section):
    """AC12 mapping pin: the PLANNING stage-set binds the PLANNING-leg condition semantics
    and the EXECUTE stage-set binds the EXECUTE-leg condition semantics — and each leg's
    condition is NOT the other's (so swapping the two condition texts, or pointing a
    stage-set at the wrong leg's condition, reds). Raises AssertionError on any wrong-leg
    binding."""
    bymap = _leg_bullet_map(section)
    assert _PLANNING_STAGES in bymap, (
        f"the planning leg must be keyed on {sorted(_PLANNING_STAGES)}; got {sorted(map(sorted, bymap))}"
    )
    assert _EXECUTE_STAGES in bymap, (
        f"the execute leg must be keyed on {sorted(_EXECUTE_STAGES)}; got {sorted(map(sorted, bymap))}"
    )
    planning_cond = bymap[_PLANNING_STAGES]
    execute_cond = bymap[_EXECUTE_STAGES]
    # the planning-leg row binds the PLANNING condition semantics …
    assert _PLANNING_COND in planning_cond and _PLANNING_COND_TAIL in planning_cond, (
        "the planning-leg row (premises, plan) must bind the PLANNING-leg condition "
        f"('NOT met while autonomous planning … work remains.'); got {planning_cond!r}"
    )
    # … and NOT the execute condition (so a swap reds) …
    assert _EXECUTE_COND not in planning_cond, (
        "the planning-leg row must NOT carry the EXECUTE-leg condition (swap/mis-map)"
    )
    # … the execute-leg row binds the EXECUTE condition semantics …
    assert _EXECUTE_COND in execute_cond, (
        "the execute-leg row (execute, finalize, verify, ship) must bind the EXECUTE-leg condition "
        f"('NOT met while autonomous implement / review / harden / verify / ship …'); got {execute_cond!r}"
    )
    # … and NOT the planning condition (so a swap reds).
    assert _PLANNING_COND_TAIL not in execute_cond, (
        "the execute-leg row must NOT carry the PLANNING-leg condition (swap/mis-map)"
    )


def test_leg_condition_selector_maps_each_leg_to_its_own_condition():
    """AC12: beyond totality, the selector binds the CORRECT condition per leg — the planning
    stage-set (premises, plan) → the planning-leg condition, the execute stage-set (execute,
    finalize, verify, ship) → the execute-leg condition — over the REAL merged drive.md. A swapped or
    mis-mapped condition (a handoff that re-arms the WRONG leg's goal) reds this pin."""
    _assert_leg_condition_mapping(_leg_selector_section())


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


# --- AC7: cross-file /goal rebirth-pause clause consistency ----------------- #
# The `/goal` rebirth-pause clause must be present + byte-identical across BOTH
# drive.md (×2: the rebirth-handoff re-arm goal + the Stage-0 leg-1 goal) and
# drive-plan.md (×1: the Gate-A→leg-2 goal) — AC7 / design-phase4.md edge-case 4: a
# one-sided edit to any of those `/goal` surfaces must red this pin.
_GOAL_REBIRTH_PAUSE_CLAUSE = (
    'paused at a rebirth handoff (waiting="rebirth") awaiting my paste of the resume line'
)


def _assert_goal_rebirth_pause_consistent(drive_md, drive_plan_md):
    """The cross-file AC7 pin, factored so the flip-proof runs the SAME assertion against a
    mutated COPY. Both files (whitespace-normalized) must carry the SAME rebirth-pause `/goal`
    clause, at its expected per-file count. drive.md carries it ×2 — once in the rebirth-handoff
    successor re-arm goal (the I-section leg-aware re-arm) and once in the Stage-0 leg-1 goal;
    drive-plan.md carries it ×1, in the Gate-A→leg-2 goal it hands the planner. A one-sided edit
    to EITHER file's clause — including dropping just ONE of drive.md's two — reds this.
    Raises AssertionError if the clause is missing from, altered in, or mis-counted in either."""
    assert _norm(drive_md).count(_GOAL_REBIRTH_PAUSE_CLAUSE) == 2, (
        "drive.md must carry the SAME /goal rebirth-pause clause in both the rebirth-handoff "
        "re-arm goal and the Stage-0 leg-1 goal (×2)"
    )
    assert _norm(drive_plan_md).count(_GOAL_REBIRTH_PAUSE_CLAUSE) == 1, (
        "drive-plan.md must carry the SAME /goal rebirth-pause clause in its leg-2 goal (×1)"
    )


def test_goal_rebirth_pause_clause_consistent_across_drive_and_plan():
    """AC7 cross-file consistency: the leg-2 `/goal` rebirth-pause clause
    (`waiting="rebirth"` … awaiting my paste of the resume line) is present and identical in
    BOTH drive.md and drive-plan.md, so the two `/goal` surfaces can't drift apart."""
    _assert_goal_rebirth_pause_consistent(_drive_md(), _drive_plan_md())

