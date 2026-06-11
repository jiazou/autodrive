"""Phase-3 rebirth-handshake cross-file contract pins (slice 3.3).

The lever-2 rebirth pause/resume handshake is split across two files that MUST agree:
  * `.claude/commands/drive.md` — the coordinator prose (slice 3.1): the I1 safe-boundary
    handler, the `↻ REBIRTH` run-graph node, the handoff block, the resume rebirth-continue
    + `rebirth_pending` re-arm, the canonical `waiting` amendment, and gate precedence.
  * `bin/drive-stop-hook.py` — the Stop-hook escalation steer (slice 3.2): once
    `rebirth_pending` is set and the run is still over hard water, the hook steers the
    coordinator to perform the I1 handshake at its next safe boundary.

Slice 3.3 owns ONLY this file; slices 3.1 and 3.2 are merged into this worktree, so the
assertions run against the REAL integrated text. A future drift on EITHER side — a
reordered I1 step, a dropped legend glyph, a desynced canonical `waiting` definition, a
hook steer that no longer names the handshake the prose implements — reds a pin here.

The pins are STRUCTURAL/bounded, NOT loose substrings, per the slice-1.3
(test_checkpoint_contract.py) precedent: section-bounded enumeration + by-index ordering
(`_I1_STEP_RE`, `_RESUME_BULLET_RE`), contiguous-clause literals (whitespace-normalized),
and a total-over-the-enum selector check. Each load-bearing pin is proven to RED against a
mutated COPY of the relevant prose/code (never the real files) in the accompanying
`test_*_flips_on_*` cases — a mutate-a-copy flip-proof, exactly as slice 1.3 does.
"""
import re

import pytest

from _helpers import REPO_ROOT

DRIVE_MD = REPO_ROOT / ".claude" / "commands" / "drive.md"
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
    return _section(_drive_md(), "I1 — Safe-boundary rebirth handler")


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
    `### I1 …` section so a step elsewhere in drive.md cannot leak in."""
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


def test_i1_fail_closed_clause_present_in_section():
    """AC1: the fail-closed invariant — never enter the pause on a failing proof — is a
    CONTIGUOUS clause inside the I1 section (whitespace-normalized), so it cannot be
    satisfied by the same words scattered across distant prose."""
    blob = _norm(_i1_section())
    assert 'fail closed: Never set `waiting = "rebirth"` on a failing proof.' in blob, (
        "the I1 handler must keep the contiguous fail-closed clause "
        '`fail closed: Never set `waiting = "rebirth"` on a failing proof.`'
    )


def test_ac1_ordering_pin_flips_on_reordered_copy():
    """Flip-proof (mutate a COPY, never the real file): swapping the marker-write and
    waiting-set step labels in a COPY of the I1 section makes the adjacency/order pin RED —
    proving the assertion is load-bearing on the real ordering, not incidentally green."""
    section = _i1_section()
    steps = _I1_STEP_RE.findall(section)
    labels = [lbl for _n, lbl in steps]
    marker_idx = next(i for i, l in enumerate(labels) if "WRITE the durable marker" in l)
    waiting_idx = next(i for i, l in enumerate(labels) if 'set `waiting = "rebirth"`' in l)
    # swap the two step labels in the enumerated list derived from the COPY
    labels[marker_idx], labels[waiting_idx] = labels[waiting_idx], labels[marker_idx]
    mi = next(i for i, l in enumerate(labels) if "WRITE the durable marker" in l)
    wi = next(i for i, l in enumerate(labels) if 'set `waiting = "rebirth"`' in l)
    # the real order has marker before waiting & adjacent; the mutated copy must NOT
    assert not (mi < wi and wi == mi + 1), (
        "reordering the marker/waiting steps in a COPY must break the ordering pin"
    )


# =========================================================================== #
# P1-2 — I1 is ONE shared rebirth-checkpoint routine wired at EVERY claimed safe
# boundary (Plan, Execute, Verify, Ship), not just Execute.
# =========================================================================== #
def _stage_section(heading):
    """A `### Stage …` section body, bounded to the next `### `/`## ` heading."""
    return _section(_drive_md(), heading, level="### ")


def test_i1_preamble_claims_all_four_stage_boundaries():
    """P1-2: the I1 handler's preamble enumerates ALL four autonomous stages as safe-boundary
    sites that invoke the shared routine — Execute, Plan, Verify, AND Ship — so its scope
    claim matches reality (it is no longer Execute-only)."""
    i1 = _norm(_i1_section())
    assert "ONE routine every safe-boundary site calls" in i1, (
        "the I1 preamble must state it is the ONE shared routine every safe-boundary calls"
    )
    # the stage-agnostic detection rationale (why every stage must invoke it)
    assert "stage-agnostic and can set `rebirth_pending` in ANY stage" in i1, (
        "the I1 preamble must state detection is stage-agnostic across all stages"
    )
    for stage in ("**Execute**", "**Plan**", "**Verify**", "**Ship**"):
        assert stage in i1, f"the I1 preamble must enumerate the {stage} boundary site"
    # the Ship boundary description must match the real Stage-5 call site (BEFORE /drive-ship
    # is dispatched, not "before Gate B"), and note Gate B precedence covers a post-dispatch
    # rebirth — so the preamble and the call site do not contradict (no lost-handoff hole).
    assert "BEFORE `/drive-ship` is dispatched" in i1, (
        "the I1 Ship boundary must be described as BEFORE /drive-ship is dispatched (matching "
        "the Stage-5 call site), not an inside-ship boundary that never fires"
    )
    assert "no post-dispatch rebirth is lost" in i1, (
        "the I1 Ship description must state Gate B precedence covers a post-dispatch rebirth"
    )


# The shared-routine invocation each stage must carry: run the Coordinator soft-check then
# the I1 Safe-boundary rebirth handler at that stage's safe boundary.
_I1_INVOCATION = "the **Safe-boundary rebirth handler** (§ I1"


@pytest.mark.parametrize(
    "heading",
    ["Stage 1 — Plan", "Stage 4b — Verify (optional)", "Stage 5 — Ship (once)"],
)
def test_i1_wired_into_plan_verify_ship_stage_sections(heading):
    """P1-2: each non-Execute autonomous stage (Plan, Verify, Ship) actually INVOKES the
    shared soft-check + I1 rebirth handler at its safe boundary — so a rebirth signalled in
    that stage has a consumer (previously only Execute did, so Plan/Verify/Ship rebirths were
    never handed off). The invocation is asserted INSIDE the stage's own section."""
    section = _norm(_stage_section(heading))
    assert "Coordinator soft-check" in section, (
        f"{heading} must run the Coordinator soft-check at its safe boundary"
    )
    assert _I1_INVOCATION in section, (
        f"{heading} must invoke the Safe-boundary rebirth handler (§ I1) at its safe boundary"
    )


def test_execute_loop_still_wires_i1():
    """P1-2 regression: the Execute loop's existing soft-check + I1 wiring is preserved (the
    fix ADDS the other stages, never drops Execute's)."""
    md = _norm(_drive_md())
    assert "the **Safe-boundary rebirth handler** (§ I1 above" in md, (
        "the Execute loop must still wire the I1 handler (preserved alongside the new sites)"
    )


def test_p1_2_wiring_pin_flips_on_dropped_ship_invocation_copy():
    """Flip-proof (mutate a COPY): removing the I1 invocation from the Ship stage in a COPY of
    drive.md makes the per-stage wiring pin RED for Ship — proving it bites on the real call
    site, not incidentally green on the preamble's claim alone."""
    md = _drive_md()
    ship = _section(md, "Stage 5 — Ship (once)", level="### ")
    assert _I1_INVOCATION in _norm(ship), "fixture: Ship must carry the I1 invocation to drop"
    # drop the whole leading I1-checkpoint paragraph from a COPY of the Ship section
    drifted_ship = re.sub(
        r"At the ship dispatch boundary.*?§ I1 Gate/STOP precedence\)\.\n\n",
        "",
        ship,
        count=1,
        flags=re.DOTALL,
    )
    assert _I1_INVOCATION not in _norm(drifted_ship), (
        "dropping the Ship I1 invocation from a COPY must remove the wiring the pin requires"
    )


# =========================================================================== #
# AC2/AC3 — run-graph ↻ REBIRTH node + the handoff block.
# =========================================================================== #
def test_run_graph_rebirth_anchor_node_and_legend():
    """AC2/AC3: the run-graph render contract maps `waiting=="rebirth"` to a `↻ REBIRTH`
    CONTINUATION node (NOT a `✗ STOP` leaf), the legend lists `↻ rebirth`, and the node
    text carries the literal `/drive <runId>` resume token."""
    blob = _norm(_drive_md())
    # the legend line enumerates the rebirth glyph
    assert "↻ rebirth" in blob, "the run-graph legend must list the `↻ rebirth` glyph"
    # the anchor table maps rebirth -> a ↻ REBIRTH continuation node, explicitly not a STOP leaf
    assert (
        "`rebirth` → a `↻ REBIRTH` CONTINUATION node (NOT a `✗ STOP` leaf)"
    ) in blob, (
        "the `← YOU ARE HERE` anchor table must map `rebirth` to a `↻ REBIRTH` "
        "CONTINUATION node, explicitly NOT a `✗ STOP` leaf"
    )
    # the node text contains the literal /drive <runId> resume token
    assert (
        "↻ REBIRTH: context-pressure handoff (resume: /drive <runId>) ← YOU ARE HERE"
    ) in blob, "the ↻ REBIRTH node text must carry the literal `/drive <runId>` resume token"


def _handoff_block():
    """The fenced handoff block presented when `waiting=="rebirth"` (Present human pause
    step 3): the ```-fenced block whose first line starts the `↻ REBIRTH —` orientation."""
    md = _drive_md()
    start = md.index("↻ REBIRTH — this /drive run is approaching its context budget")
    fence_open = md.rindex("```", 0, start)
    fence_close = md.index("```", start)
    return md[fence_open: fence_close]


def test_handoff_block_has_resume_line_and_rearmed_goal():
    """AC3: the rebirth handoff block contains the literal `/drive <runId>` resume line AND
    a re-armed `/goal` line (the successor's leg goal). Pinned WITHIN the bounded handoff
    block so an unrelated `/drive <runId>` / `/goal` mention elsewhere can't satisfy it."""
    block = _handoff_block()
    # the EXACT resume invocation, indented as a paste-ready line
    assert "\n     /drive <runId>\n" in block, (
        "the handoff block must contain the literal paste-ready `/drive <runId>` resume line"
    )
    # the re-armed /goal line for the successor's leg
    assert "/goal The /drive run <runId> is resuming after a context-pressure rebirth" in block, (
        "the handoff block must re-arm the successor leg's `/goal` line"
    )


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


def test_handoff_goal_placeholder_pin_flips_on_dropped_placeholder_copy():
    """Flip-proof (mutate a COPY, never the real file): dropping the trailing
    `<leg-condition>` placeholder from a COPY of the handoff block's `/goal` line makes the
    placeholder pin RED — proving it bites on the bound placeholder, not incidentally green."""
    block = _norm(_handoff_block())
    # remove the trailing placeholder token from the COPY (the exact drop drift AC12 prevents)
    drifted = block.replace(" <leg-condition>", "", 1)
    assert drifted != block, "the placeholder-drop mutation matched nothing"
    start = drifted.index("/goal The /drive run <runId> is resuming after a context-pressure")
    assert "<leg-condition>" not in drifted[start:], (
        "dropping the `<leg-condition>` placeholder from a COPY must red the placeholder pin"
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


def test_resume_rebirth_continue_clause_is_continue_not_stop():
    """AC4: the rebirth-continue bullet names a re-proven (fail-closed) CONTINUE — NOT a
    STOP — as a contiguous clause, so a drift to re-presenting it (treating it as a human
    pause) reds the pin. The CONTINUE is now gated on a fresh PASSING proof (P1-3 fail-closed)."""
    blob = _norm(_drive_md())
    assert (
        '`waiting == "rebirth"` → re-proven CONTINUE (fail closed), NOT a STOP.' in blob
    ), "the resume bullet must pin rebirth as a re-proven (fail-closed) CONTINUE, NOT a STOP"
    assert "clear `state.waiting = null`" in blob, (
        "the rebirth-continue bullet must CLEAR waiting and continue (on a passing proof)"
    )
    # explicit do-NOT-re-present (so a future edit can't quietly surface it as a pause)
    assert "do NOT surface it as a paused-for-human state, do NOT re-present the handoff" in blob


def test_resume_rebirth_continue_is_fail_closed_re_proven():
    """P1-3 (tightened per the adversarial review): the resume consumer RE-PROVES resumability
    via `--mode checkpoint` BEFORE treating `waiting=="rebirth"` as a continue — it does NOT
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
    assert "RE-PROVE via\n`bin/drive-conformance.sh $RUN_DIR --mode checkpoint`".replace("\n", " ") in blob, (
        "fail-closed must RE-PROVE via the checkpoint conformance mode"
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


def test_rebirth_pending_rearm_at_rebind_is_single_reset_point():
    """AC4 (D36): the `rebirth_pending=false` re-arm lives at the sessionId-rebind step, in
    the SAME write, on ANY fresh-session resume — and is the SINGLE reset point (NOT re-done
    in the rebirth-continue step). Pinned as contiguous clauses so a second reset, or moving
    it off the rebind step, reds the pin."""
    blob = _norm(_drive_md())
    # reset is AT the rebind step, in the same write, uniform over all waiting values
    assert "reset `state.rebirth_pending = false` — uniformly on ANY fresh-session" in blob, (
        "the rebirth_pending re-arm must sit at the sessionId-rebind step, on ANY "
        "fresh-session resume (uniform over all waiting values)"
    )
    # it is the SINGLE reset point, explicitly not re-done in the rebirth-continue step
    assert "This is the SINGLE reset point" in blob, (
        "the re-arm must be pinned as the SINGLE reset point"
    )
    assert "never re-done in the `rebirth`-continue step" in blob, (
        "the re-arm must NOT be re-done in the rebirth-continue step"
    )


def _assert_single_reset_structural(drive_md):
    """AC4 / D36 negative (design-phase3.md L533-534): the `rebirth_pending` reset write
    appears EXACTLY ONCE in the resume reconciliation list and ONLY at the sessionId-rebind
    bullet (index 0) — ABSENT from the rebirth-continue bullet (index 2) and from the I1
    OUTGOING-session handler (where the flag must STAY SET). Factored so the flip-proof runs
    the SAME structural pin against a mutated COPY; raises AssertionError on a second reset.

    `drive_md` is the RAW drive.md text (not `_norm`'d — the bullet bounding walks lines)."""
    section = _resume_section_of(drive_md)
    bodies = _resume_bullet_bodies(section)
    assert len(bodies) >= 3, f"expected the resume sub-bullets to enumerate; got {len(bodies)}"

    # EXACTLY ONE reset write across the entire resume reconciliation list …
    total = sum(len(_REBIRTH_RESET_RE.findall(b)) for b in bodies)
    assert total == 1, (
        f"`rebirth_pending = false` must be reset EXACTLY ONCE across the resume bullets; "
        f"found {total} reset writes (a redundant second reset breaks the single-reset point)"
    )
    # … and that one reset lives ONLY at the sessionId-rebind bullet (index 0) …
    assert _REBIRTH_RESET_RE.search(bodies[0]), (
        "the single `rebirth_pending = false` reset must live at the sessionId-rebind bullet"
    )
    # … and is ABSENT from the rebirth-continue bullet (index 2 — must NOT re-reset).
    assert not _REBIRTH_RESET_RE.search(bodies[2]), (
        "the rebirth-continue bullet must NOT re-reset `rebirth_pending` (single reset point)"
    )

    # The OUTGOING-session I1 handler must carry NO reset write — the flag STAYS SET there.
    i1 = _section(drive_md, "I1 — Safe-boundary rebirth handler", level="### ")
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


def test_single_reset_point_is_structural_not_prose_only():
    """AC4 / D36 (design-phase3.md L533-534) negative: assert the `rebirth_pending` reset is
    written EXACTLY ONCE and ONLY at the rebind step — ABSENT from the rebirth-continue
    bullet and the I1 outgoing handler — over the REAL merged drive.md, not just the prose
    CLAIM of single-reset."""
    _assert_single_reset_structural(_drive_md())


def test_single_reset_pin_flips_on_redundant_second_reset_copy():
    """Flip-proof (genuine — run the REAL structural pin against a mutated COPY): inject a
    redundant SECOND `rebirth_pending = false` reset into the rebirth-continue bullet of a
    COPY of drive.md (the exact double-reset drift D36/edge-case-9 prevents) and assert the
    SAME `_assert_single_reset_structural` pin RAISES. Proves the negative is structural, not
    presence-only — the prose `SINGLE reset point` sentences stay intact in the copy."""
    drifted = _drive_md().replace(
        "clear `state.waiting = null` (JSON-safe write) and",
        "clear `state.waiting = null` (JSON-safe write), reset `state.rebirth_pending = false`, "
        "and",
        1,
    )
    # the injection must actually land (else the flip-proof is vacuous) …
    assert drifted != _drive_md(), "the redundant-second-reset injection matched nothing"
    # … the prose single-reset CLAIM is still present in the copy (so a presence-only pin
    # would stay green — proving this pin bites on STRUCTURE) …
    assert "This is the SINGLE reset point" in drifted
    # … and the REAL structural pin, run against the drifted COPY, must RED.
    with pytest.raises(AssertionError):
        _assert_single_reset_structural(drifted)


def test_ac4_resume_order_pin_flips_on_reordered_copy():
    """Flip-proof: inserting a NEW resume sub-bullet AHEAD of the rebind bullet in a COPY
    of the resume section makes the rebind-is-index-0 pin RED (the real file has it first)."""
    section = _resume_section()
    # inject a fake first sub-bullet at the same indentation as the real reconciliation steps
    injected = section.replace(
        "  - **sessionId rebind",
        "  - **injected bogus step:** noise\n  - **sessionId rebind",
        1,
    )
    labels = _resume_bullet_labels(injected)
    rebind_idx = next(i for i, l in enumerate(labels) if l.startswith("sessionId rebind"))
    assert rebind_idx != 0, (
        "a sub-bullet inserted ahead of the rebind in a COPY must push rebind off index 0"
    )


# =========================================================================== #
# AC9 — gate precedence: both gates hand a /goal line; neither emits /drive <runId>;
# rebirth uniquely contributes the runId resume line.
# =========================================================================== #
def test_gate_precedence_neither_gate_emits_runid_resume():
    """AC9: drive.md's gate-precedence prose states BOTH Gate A and Gate B hand the next
    leg's `/goal` line on approval, NEITHER emits a `/drive <runId>` resume token, and the
    runId resume line is the rebirth handshake's DISTINCT contribution."""
    blob = _norm(_drive_md())
    assert (
        "BOTH Gate A and Gate B hand the next leg's `/goal` line on approval" in blob
    ), "gate precedence must state both gates hand the next leg's /goal line"
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


def test_rebirth_pending_carry_forward_claim_is_qualified_not_blanket():
    """P1-1 negative: the contradictory BLANKET claim — `rebirth_pending` 'does NOT carry
    forward' NOT immediately qualified by 'ACROSS the fresh-session resume' — must NOT appear.
    Pinned structurally: every `does NOT carry forward` occurrence for `rebirth_pending` is
    followed by the `ACROSS the fresh-session resume` qualifier."""
    blob = _norm(_drive_md())
    for m in re.finditer(r"`rebirth_pending` does NOT carry forward", blob):
        tail = blob[m.end(): m.end() + len(" ACROSS the fresh-session resume")]
        assert tail == " ACROSS the fresh-session resume", (
            "every `rebirth_pending` does-NOT-carry-forward claim must be QUALIFIED with "
            "`ACROSS the fresh-session resume` (a blanket claim contradicts the same-session "
            f"PERSIST lifecycle); found unqualified tail {tail!r}"
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


def test_present_human_pause_step1_enumerates_rebirth_dual():
    """AC11: Present-human-pause step 1's reason enumeration includes `"rebirth"` alongside
    the human-pause reasons AND states its distinct continue semantics (awaits a
    FRESH-SESSION RESUME; the resume auto-clears it) — not a bare addition to the set."""
    blob = _norm(_drive_md())
    # the reason enumeration lists rebirth alongside the human-pause reasons
    assert (
        '`"gateA"`, `"gateB"`, `"stop:<short>"`, `"ask:<header>"`, or `"rebirth"`'
    ) in blob, "step-1's reason enumeration must include `\"rebirth\"`"
    # …with its dual/continue semantics, contiguous (NOT just appended to the set). The
    # resume RE-PROVES before auto-clearing (P1-3 fail-closed), so the continue clause names it.
    assert (
        '`"rebirth"` awaits a FRESH-SESSION RESUME: the resume path re-proves then auto-clears '
        "it and continues"
    ) in blob, (
        "step 1 must state rebirth's continue semantics (awaits a fresh-session resume; "
        "the resume re-proves then auto-clears it), not merely add it to the reason set"
    )


def test_present_human_pause_never_sets_rebirth_itself():
    """P1-3 outbound fail-closed: Present-human-pause step 1 must state it NEVER sets
    `waiting="rebirth"` itself — only the I1 handler sets it, AFTER its passing proof + durable
    marker. So `rebirth` is not a generic caller-supplied pause reason a sibling path can pass
    in to end a turn without I1's prove→marker→wait sequence (the outbound half of fail-closed)."""
    blob = _norm(_drive_md())
    assert "this routine NEVER sets `waiting = \"rebirth\"` itself" in blob, (
        "Present-human-pause must state it NEVER sets waiting=rebirth itself"
    )
    assert 'Only the I1 handler sets `"rebirth"`' in blob, (
        "Present-human-pause must name I1 as the SOLE setter of waiting=rebirth"
    )
    # the set-here list (step 1) must NOT include rebirth — only the human-pause reasons
    assert (
        'HUMAN-pause reason this routine is setting —\n   `"gateA"`, `"gateB"`, '
        '`"stop:<short>"`, or `"ask:<header>"`'
    ).replace("\n   ", " ") in blob, (
        "step-1's SET-HERE list must enumerate only the four human-pause reasons (NOT rebirth)"
    )
    assert '`"rebirth"` is NOT in this set-here list' in blob, (
        "step 1 must state rebirth is NOT in the set-here list"
    )
    assert "NOT a generic caller-supplied pause reason" in blob, (
        "rebirth must be stated as NOT a generic caller-supplied pause reason"
    )


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


def test_ac11_dual_nature_pin_flips_on_human_pause_only_copy():
    """Flip-proof (genuine — run the REAL pin against a mutated COPY): revert a COPY of the
    Autonomous-continuation contract to the pre-edit human-pause-ONLY phrasing (drop the
    auto-clear-on-resume half — the exact way the contract would drift) and assert the SAME
    `_assert_ac11_dual_nature` pin RAISES on it. This proves the pin bites on the continue
    semantics, not just the literal token `rebirth`."""
    drifted = _drive_md().replace(
        "auto-cleared-as-continue by the resume path in the INCOMING session —\n"
        "it is NOT a STOP awaiting a human answer.",
        "a STOP awaiting a human answer like every other `waiting` value.",
    )
    # the mutation must actually change the source (else the flip-proof is vacuous) …
    assert drifted != _drive_md(), "the human-pause-only drift mutation matched nothing"
    # … and the REAL pin, run against the drifted COPY, must RED.
    with pytest.raises(AssertionError):
        _assert_ac11_dual_nature(_norm(drifted))


# =========================================================================== #
# AC12 — the rebirth-handoff `/goal <leg-condition>` selector is TOTAL over the stage enum
# (premises, plan, execute, verify, ship) → exactly one leg-condition each.
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
_STAGE_ENUM = ("premises", "plan", "execute", "verify", "ship")
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
    (premises, plan, execute, verify, ship) with each stage mapped to exactly ONE
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
#   - EXECUTE   leg (execute, verify, ship): autonomous implement/review/harden/verify/ship.
_PLANNING_COND = "NOT met while autonomous planning"
_PLANNING_COND_TAIL = "design, autoplan, dual-voice review) work remains."
_EXECUTE_COND = "NOT met while autonomous implement / review / harden / verify / ship work remains."

# The stage-set that keys each leg, as the frozensets the selector partition must produce.
_PLANNING_STAGES = frozenset({"premises", "plan"})
_EXECUTE_STAGES = frozenset({"execute", "verify", "ship"})


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
    """AC12 mapping pin (factored for the flip-proofs): the PLANNING stage-set binds the
    PLANNING-leg condition semantics and the EXECUTE stage-set binds the EXECUTE-leg
    condition semantics — and each leg's condition is NOT the other's (so swapping the two
    condition texts, or pointing a stage-set at the wrong leg's condition, reds). Raises
    AssertionError on any wrong-leg binding."""
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
        "the execute-leg row (execute, verify, ship) must bind the EXECUTE-leg condition "
        f"('NOT met while autonomous implement / review / harden / verify / ship …'); got {execute_cond!r}"
    )
    # … and NOT the planning condition (so a swap reds).
    assert _PLANNING_COND_TAIL not in execute_cond, (
        "the execute-leg row must NOT carry the PLANNING-leg condition (swap/mis-map)"
    )


def test_leg_condition_selector_maps_each_leg_to_its_own_condition():
    """AC12: beyond totality, the selector binds the CORRECT condition per leg — the planning
    stage-set (premises, plan) → the planning-leg condition, the execute stage-set (execute,
    verify, ship) → the execute-leg condition — over the REAL merged drive.md. A swapped or
    mis-mapped condition (a handoff that re-arms the WRONG leg's goal) reds this pin."""
    _assert_leg_condition_mapping(_leg_selector_section())


def test_ac12_mapping_pin_flips_on_swapped_conditions_copy():
    """Flip-proof (mutate a COPY, never the real file): SWAP the planning-leg and execute-leg
    condition bodies in a COPY of the selector block and assert the SAME mapping pin RAISES —
    proving it bites on which leg owns which condition, not just on totality/presence."""
    section = _leg_selector_section()
    planning_line = "`NOT met while autonomous planning (design, autoplan, dual-voice review) work remains.`"
    execute_line = "`NOT met while autonomous implement / review / harden / verify / ship work remains.`"
    assert planning_line in section and execute_line in section, (
        "the swap flip-proof must find both canonical condition lines to swap"
    )
    # swap via sentinels so the two replacements don't interfere
    swapped = (
        section.replace(planning_line, "\x00PLAN\x00", 1)
        .replace(execute_line, planning_line, 1)
        .replace("\x00PLAN\x00", execute_line, 1)
    )
    assert swapped != section, "the condition-swap mutation matched nothing"
    # totality is UNCHANGED by the swap (same stage tokens) — proving this pin bites on mapping
    bullets = _LEG_BULLET_RE.findall(swapped)
    covered = [t for sb, _c in bullets for t in _STAGE_TOK_RE.findall(sb)]
    assert set(covered) == set(_STAGE_ENUM), "the swap must leave totality intact (mapping-only drift)"
    with pytest.raises(AssertionError):
        _assert_leg_condition_mapping(swapped)


def test_ac12_mapping_pin_flips_on_wrong_leg_condition_copy():
    """Flip-proof (mutate a COPY, never the real file): point the EXECUTE-leg row at the
    PLANNING-leg condition in a COPY (a one-sided mis-map, not a clean swap) and assert the
    SAME mapping pin RAISES — proving it catches a stage-set bound to the wrong leg's
    condition, not only a symmetric swap."""
    section = _leg_selector_section()
    execute_line = "`NOT met while autonomous implement / review / harden / verify / ship work remains.`"
    planning_line = "`NOT met while autonomous planning (design, autoplan, dual-voice review) work remains.`"
    # mis-map: overwrite the execute-leg condition with the planning-leg one (totality intact)
    mismapped = section.replace(execute_line, planning_line, 1)
    assert mismapped != section, "the wrong-leg mis-map mutation matched nothing"
    bullets = _LEG_BULLET_RE.findall(mismapped)
    covered = [t for sb, _c in bullets for t in _STAGE_TOK_RE.findall(sb)]
    assert set(covered) == set(_STAGE_ENUM), "the mis-map must leave totality intact"
    with pytest.raises(AssertionError):
        _assert_leg_condition_mapping(mismapped)


def test_ac12_total_selector_pin_flips_when_a_stage_is_dropped():
    """Flip-proof: dropping `"verify"` from a COPY of the selector block makes the
    total-coverage assertion RED — proving the pin bites on completeness, not just presence
    of some bullets."""
    section = _leg_selector_section()
    # remove the verify stage token from the execute-leg bullet in the COPY
    mutated = section.replace(
        '{`"execute"`, `"verify"`, `"ship"`}', '{`"execute"`, `"ship"`}', 1
    )
    bullets = _LEG_BULLET_RE.findall(mutated)
    covered = []
    for stages_blob, _cond in bullets:
        covered.extend(_STAGE_TOK_RE.findall(stages_blob))
    assert set(covered) != set(_STAGE_ENUM), (
        "dropping a stage from a COPY of the selector must break the total-coverage pin"
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
    drive.md's I1 handler (slice 3.1) implements — at the NEXT safe boundary: prove the
    checkpoint via `--mode checkpoint`, write `checkpoint-complete.marker`, set
    `waiting="rebirth"`, present the handoff block. So the hook steers the coordinator to do
    precisely what the I1 contract specifies (the hook never enacts it itself)."""
    steer = _escalation_steer_text()
    # the steer fires only over hard water with the flag already set
    assert "rebirth high-water mark and " in steer
    assert "state.rebirth_pending is already set" in steer
    # it defers to the coordinator's NEXT safe boundary — the I1 trigger condition
    assert "At your NEXT safe boundary (no open " in steer
    assert "inflight-*.marker" in steer
    # and names each I1 step in order: prove → write marker → set waiting → present block
    assert "bin/drive-conformance.sh --mode checkpoint" in steer, "steer must name the proof"
    assert "checkpoint-complete.marker" in steer, "steer must name the durable marker write"
    # the hook source escapes the quotes in the steer literal, so the raw text reads
    # `state.waiting=\"rebirth\"` — match that source form.
    assert r'state.waiting=\"rebirth\"' in steer, "steer must name the waiting=rebirth set"
    assert "present " in steer and "the handoff block" in steer, (
        "steer must name presenting the handoff block"
    )
    # the proof step is steered BEFORE the waiting set (the I1 fail-closed ordering)
    assert steer.index("--mode checkpoint") < steer.index(r'state.waiting=\"rebirth\"'), (
        "the escalation steer must order proof-then-pause (checkpoint before waiting set), "
        "agreeing with I1's fail-closed ordering"
    )


# `rebirth` appears in the source-escaped form `\"rebirth\"` in the steer literal.
_SHARED_STEER_TOKENS = ("--mode checkpoint", "checkpoint-complete.marker", r'\"rebirth\"')


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
    # the I1 handler names the conformance proof, the marker, and the rebirth waiting value
    assert "bin/drive-conformance.sh $RUN_DIR --mode checkpoint" in i1
    assert "checkpoint-complete.marker" in i1
    assert 'set `waiting = "rebirth"`' in i1


def test_cross_file_invariant_flips_on_renamed_steer_token_copy():
    """Flip-proof (genuine — run the REAL accessor + pin against a mutated COPY): rename the
    marker token in a COPY of the whole hook SOURCE (the exact way a cross-file drift would
    happen), re-extract the steer via the SAME `_escalation_steer_text` accessor, and assert
    the SAME `_assert_steer_names_shared_tokens` pin RAISES. Proves the agreement check is
    load-bearing on the real token, not coincidentally green."""
    drifted_src = _hook_py().replace("checkpoint-complete.marker", "some-other.marker")
    # the rename must actually change the source (else the flip-proof is vacuous) …
    assert drifted_src != _hook_py(), "the marker-rename mutation matched nothing in the hook"
    # … and the REAL accessor + pin, run over the drifted COPY, must RED.
    with pytest.raises(AssertionError):
        _assert_steer_names_shared_tokens(_escalation_steer_text(drifted_src))
