You are running the PLAN stage (Stage 1). Two steps: a planner subagent AUTHORS
a rough design, then gstack `autoplan` REVIEWS it. (autoplan is a reviewer, not
an author — it cannot produce a design from a raw task, so we author one first.)

First, read .harness/decisions.md to load prior decisions you must stay
consistent with.

## Step 1 — Author a rough design (planner subagent)

Spawn a generic planner subagent (the Agent tool) with the scope below.

----- BEGIN SUBAGENT SCOPE -----
Produce a rough design document for the task. Do NOT implement anything.

Steps:
1. Read .harness/task.md if it exists; otherwise use the task at the end of
   this prompt.
2. Read .harness/decisions.md to stay consistent with prior choices.
3. Read the relevant parts of the codebase for context.
4. Write .harness/design.md covering:
   - Goal (one paragraph)
   - Interfaces (exact signatures, types, endpoints)
   - Data flow
   - Edge cases and failure modes (at least 5, with intended behavior)
   - Acceptance criteria (numbered, testable)
   - **Phases & Slices** — break the work into ordered phases (each builds on the
     last); within each phase, slices that are independent units. For each slice
     give `acceptance:` (which criteria it satisfies), `owns:` (the files/dirs it
     will write — slices intended to run in parallel MUST own DISJOINT files),
     and `deps:` (other slice ids it needs first). Format:
         ### Phase 1: <name>
         - Slice 1.1 <name> — acceptance: <criteria>; owns: <files>; deps: none
         - Slice 1.2 <name> — acceptance: ...; owns: <disjoint files>; deps: 1.1
   - Decisions (choices made autonomously)
   - Out of scope
   - Open questions (zero to two — genuine close calls only)
5. Return the design path and a 3-line summary.

Decision protocol (overrides any "ask the human" reflex) — apply the 6 Decision
Principles (see CLAUDE.md). For design choices with a clear best option, TAKE IT and record
it under "Decisions"; also append to .harness/decisions.md with a Classification
field. Reserve "Open questions" for genuine close calls. Out-of-scope discoveries
→ .harness/followups.md.

Task: $ARGUMENTS
----- END SUBAGENT SCOPE -----

## Step 2 — Review the rough design (autoplan, then dual-voice convergence)

Once .harness/design.md exists:

a) **autoplan** — run gstack `autoplan` on it (the rich CEO → Design → Eng → DX
   review, auto-deciding via the 6 principles). Invoke it as the gstack skill so
   its runtime semantics apply: run `/autoplan` pointed at .harness/design.md, or
   load ~/.claude/skills/gstack/autoplan/SKILL.md and follow it. Ensure the
   reviewed design lands back in .harness/design.md.

b) **Dual-voice design-review convergence** — run the review primitive (see
   review.md / the design.md "Review primitive" section) on .harness/design.md:
   a Claude reviewer subagent AND `codex exec` both audit the design for P1s
   (BLOCKING/MAJOR — e.g. an unbuildable interface, a slice dependency cycle,
   overlapping slice ownership). If either flags a P1, the planner subagent
   revises design.md and you re-run the primitive — loop until **converged**
   (neither voice has an open P1), capped at 8 rounds.

## Gate A (the single human checkpoint for direction)

Once autoplan has approved AND the design review has converged, present **Gate A**
to me: the direction plus any Taste / User-Challenge items autoplan or the
reviewers surfaced. The dual-voice convergence is automated — Gate A is still the
only human gate here; wait for my approval.

## After this stage

- Approved → update .harness/state.json (`stage=implement`, `lastGate="A"`) and
  begin the execute half (per-phase, per-slice — see drive.md).
- No approved/converged design (cancelled, or can't converge in 8 rounds) → STOP
  and report what's missing.

Do not begin implementation on this command.
