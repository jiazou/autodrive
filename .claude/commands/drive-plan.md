---
description: PLAN stage (Stage 1) of /drive — planner authors a HIGH-LEVEL design (goal, approach, ordered phases; no slice/interface detail), autoplan reviews, dual-voice design review converges → Gate A. Usually invoked by /drive.
argument-hint: <task> (or resume within an existing run)
---
You are running the PLAN stage (Stage 1). Two steps: a planner subagent authors a
**high-level** design, then gstack `autoplan` reviews it (autoplan reviews, it can't
author — so we author first).

This whole-run design is deliberately **high-level** — it fixes the *shape* of the
work (the goal, the approach, the ordered phases), NOT its details. Interface
signatures, edge cases, and the per-slice breakdown are **not** authored here; each
phase produces its own detailed design just-in-time, against the real code the prior
phases produced (`/drive-design`). Keeping this design coarse is the point: it is what
Gate A approves and what later phases refine.

First, read $RUN_DIR/decisions.md to load prior decisions you must stay
consistent with.

## Step 1 — Author a high-level design (planner subagent)

Spawn a generic planner subagent (the Agent tool) with the scope below.

----- BEGIN SUBAGENT SCOPE -----
Produce a HIGH-LEVEL design document for the task. Do NOT implement anything, and do
NOT drill into low-level detail — **no exact signatures, no exhaustive edge cases, no
per-slice breakdown.** Those are deferred to each phase's own detailed design
(`/drive-design`), authored later against the real code earlier phases produce.

Steps:
1. Read $RUN_DIR/task.md if it exists; otherwise use the task at the end of
   this prompt.
2. Read $RUN_DIR/decisions.md to stay consistent with prior choices.
3. Read enough of the codebase to fix the shape and the phase boundaries.
4. Write $RUN_DIR/design.md covering:
   - Goal (one paragraph)
   - Approach (the high-level strategy / architecture — the shape, not the signatures)
   - **Phases** — break the work into ordered phases (each builds on the last). For
     each phase give a one-to-three-line scope: what it delivers, its rough boundary,
     and what it relies on from earlier phases. Format:
         ### Phase 1: <name> — delivers <what>; boundary <rough scope>; relies on: none
         ### Phase 2: <name> — delivers <what>; boundary <rough scope>; relies on: Phase 1
     Do NOT enumerate slices, interfaces, or edge cases — that is each phase's own
     detailed-design job.
   - Decisions (high-level choices made autonomously)
   - Out of scope
   - Open questions (zero to two — genuine close calls only)
5. Return the design path and a 3-line summary.

Decision protocol (overrides any "ask the human" reflex) — apply the 6 Decision
Principles (see the harness `CLAUDE.md`). For design choices with a clear best option, TAKE IT and record
it under "Decisions"; also append to $RUN_DIR/decisions.md with a Classification
field. Reserve "Open questions" for genuine close calls. Out-of-scope discoveries
→ $RUN_DIR/followups.md.

Task: $ARGUMENTS
----- END SUBAGENT SCOPE -----

## Step 2 — Review the rough design (autoplan, then dual-voice convergence)

Once $RUN_DIR/design.md exists:

a) **autoplan** — run gstack `autoplan` on it (the rich CEO → Design → Eng → DX
   review, auto-deciding via the 6 principles). Invoke it as the gstack skill so
   its runtime semantics apply: run `/autoplan` pointed at $RUN_DIR/design.md, or
   load ~/.claude/skills/gstack/autoplan/SKILL.md and follow it. Ensure the
   reviewed design lands back in $RUN_DIR/design.md.

b) **Dual-voice design-review convergence** — run `/drive-review` scoped `design`
   (`/drive-review` — `~/.claude/commands/drive-review.md`): a Claude reviewer subagent AND `codex exec`
   both audit `$RUN_DIR/design.md` for P1s **at the high-level altitude** (BLOCKING/MAJOR
   — e.g. a phase dependency cycle, an unsound phase boundary, an approach that can't
   deliver the goal). They do NOT demand slice/interface detail — that is each phase's
   own design. If either flags a P1, the planner subagent revises design.md and you
   re-run — loop until **converged** (neither voice has an open P1), capped at 8 rounds.

## Gate A (the single human checkpoint for direction)

Once autoplan has approved AND the design review has converged, present **Gate A**
to me: the direction plus any Taste / User-Challenge items autoplan or the
reviewers surfaced. The dual-voice convergence is automated — Gate A is still the
only human gate here; wait for my approval. Run the **Present human pause** routine —
(1) set `state.waiting = "gateA"`; (2) **emit the run graph**: read
`~/.claude/commands/drive.md` § *Emit run graph* and follow it (if `drive.md` is
unreachable, emit a one-line `(run graph unavailable: drive.md not found)` note and
continue; do NOT paraphrase the spec); (3) present Gate A and wait for approval; clear
`waiting = null` on approval.

Reaching this gate satisfied (and so auto-cleared) the leg-1 `/goal`, so also hand
me the **leg-2** goal to paste *alongside* my approval — it keeps the execute half
(implement → review → harden → verify → ship) driving autonomously to Gate B. Bind
`<task>` = the run's task:

> Paste this with your approval to drive the execute half up to Gate B:
>
> ```
> /goal The /drive run for "<task>" has opened its PR (Gate B passed, stage=done), OR is paused awaiting my input at Gate B, a non-decision STOP, or an AskUserQuestion. NOT met while autonomous implement / review / harden / verify / ship work remains.
> ```

(If the user skips it, the execute half still runs — it just won't auto-continue
across turns. After Gate B the push is immediate, so no further goal is needed.)

## After this stage

- Approved → update $RUN_DIR/state.json (`stage=execute`, `lastGate="A"`,
  `waiting=null`), parse the `## Phases` breakdown into the ordered phase ids in
  `state.phaseList`, and begin the execute half (see drive.md). **Slices are NOT defined
  here** — `state.slices` stays empty; each phase's `/drive-design phase <P>` produces and
  records its own slices just before that phase implements.
- No approved/converged design (cancelled, or can't converge in 8 rounds) → STOP
  and report what's missing **via the Present human pause routine**: set
  `state.waiting="stop:<reason>"`, then emit the run graph — read
  `~/.claude/commands/drive.md` § *Emit run graph* and follow it (if `drive.md` is
  unreachable, emit `(run graph unavailable: drive.md not found)` and continue) — then
  report. (This makes a standalone `/drive-plan` STOP self-sufficient.)

Do not begin implementation on this command.
