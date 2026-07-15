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
3. Read enough of the codebase to fix the shape and the phase boundaries, and to
   sketch the **dependency graph** of the work — the units of change and which depend
   on which. The phase breakdown is DERIVED from this graph, not from a template.
   While reading, also **count the change surface** (touch-points) — new modules,
   modified functions, call-sites touched, new interfaces, modified contracts — and
   from it estimate the production-code size (next bullet).
4. Write $RUN_DIR/design.md covering:
   - Goal (one paragraph)
   - Approach (the high-level strategy / architecture — the shape, not the signatures)
   - **Size estimate** — the touch-point count from step 3 and an estimated **production
     SLOC** band. Production SLOC = source lines of the shipping code, **EXCLUDING tests,
     comments, docstrings, and blank lines** (logic, not prose). Prefer the touch-point count
     over a raw line guess; calibrate against similar past changes in this repo where you can.
     State the band and what it triggers:
       - **≲150 SLOC** — single unit; no seam-hunt required.
       - **~150–500 SLOC** (or > ~8 touch-points) — **mandatory seam-hunt:** re-examine the
         dependency graph for a fan-out or staged-risk seam you may have lumped. Split ONLY on
         a natural seam found this way; if none exists, keep it one phase and add a
         `heightened-review:` note (an extra adversarial pass at integration review).
       - **≳500 SLOC** (or > ~20 touch-points, or > 3 new interfaces) — **must split on
         natural seams OR justify atomicity explicitly** + carry `heightened-review:`.
     Size is a tripwire for attention and review depth, NOT a license to cut a cohesive change
     at an arbitrary line count; the cut itself is governed by fan-out / staged-risk below.
   - **Phases** — **default to ONE phase.** A phase boundary is justified ONLY by one of:
     (a) **fan-out** — units that can be built independently/in parallel (distinct
     subsystems, disjoint files), or (b) **staged risk** — an intermediate unit is a
     *foundation* whose correctness must be verified (built + tested / behaviorally gated)
     before later units are safe to build on it. A linear dependency chain collapses to ONE
     phase, however many files it touches — UNLESS it contains such a foundation. The test is
     NOT "does later code depend on this" (everything does) but "would building dependents on a
     subtly-wrong foundation hide or scatter the failure absent an intermediate verify?" If its
     correctness is proven by the SAME tests/gate as its dependents, it is one phase; if it
     needs its own verify first, split. Tests and process artifacts (ledgers, docs)
     NEVER form their own phase — they ride with the code they cover. For each phase beyond
     the first, the `relies on:` field MUST name its justification (`fan-out` or
     `staged-risk: <foundation that must verify first>`); a phase that can cite neither is
     collapsed into its predecessor. Give each phase a one-to-three-line scope: what it
     delivers, its rough boundary, what it relies on. Format:
         ### Phase 1: <name> — delivers <what>; boundary <rough scope>; relies on: none
         ### Phase 2: <name> — delivers <what>; boundary <rough scope>; relies on: Phase 1 (fan-out | staged-risk: <reason>)
     Do NOT enumerate slices, interfaces, or edge cases — that is each phase's own
     detailed-design job.
   - Decisions (high-level choices made autonomously)
   - Out of scope
   - Open questions (zero to two — genuine close calls only)
5. Write `$RUN_DIR/verify-design-claims-design.md` — an ARTIFACT-shaped transcript (the
   commands run + their outputs) verifying EVERY citation, quoted snippet, and empirical
   claim the design makes. If the design makes none, the file states that explicitly
   ("no citations / no quoted snippets / no empirical claims in this design") — the file
   is ALWAYS written, never skipped. Where the design proposes a classifier/matcher rule,
   ship a runnable calibration script + its corpus + a stated imprecision budget as
   design INPUT (paths named in the design). Never a prose "verified" attestation.
6. Return the design path and a 3-line summary.

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

b) **Dual-voice design-review convergence** — BEFORE dispatching round 1 (and again
   before every later round), CHECK `$RUN_DIR/verify-design-claims-design.md` exists
   non-empty AND — on every round after a post-P1 `design.md` revision — that its
   coverage statement is re-affirmed at the CURRENT revision (the re-affirmation names
   the revised text, per the revalidation rule below); missing, empty, or coverage not
   re-affirmed at the current revision ⇒ send the author back first (a pre-round-1
   gate, not a review round — it consumes no counter). Then run `/drive-review` scoped `design`
   (`/drive-review` — `~/.claude/commands/drive-review.md`): a Claude reviewer subagent AND `codex exec`
   both audit `$RUN_DIR/design.md` for P1s **at the high-level altitude** (BLOCKING/MAJOR
   — e.g. a phase dependency cycle, an unsound phase boundary, an approach that can't
   deliver the goal). They do NOT demand slice/interface detail — that is each phase's
   own design. If either flags a P1, the planner subagent revises design.md and you
   re-run — loop until **converged** (neither voice has an open P1), capped at 8 rounds.
   On every post-P1 `design.md` revision the planner RE-VERIFIES the transcript BEFORE
   the next round: claims added/changed by the revision are verified and appended,
   unchanged claims stand, and the transcript's coverage statement is re-affirmed against
   the REVISED text — the coordinator's pre-round check re-fires each round (existence +
   non-emptiness + the coverage re-affirmation naming the current revision), so the
   whole-design transcript can never go stale across review rounds.

**Rebirth checkpoint at the planning safe boundaries.** Detection is stage-agnostic, so a
`rebirth_pending` may be set during planning (author / autoplan / a design-review round).
At each planning safe boundary — between these steps and after each design-review round (the
coordinator is between dispatch units with no open `inflight-*.marker`), and before presenting
Gate A — run the **Safe-boundary rebirth handler** per
`~/.claude/commands/drive.md` § *I1 — Safe-boundary rebirth
handler* (the shared routine: with `rebirth_pending` set at a safe boundary, prove the
checkpoint → write `checkpoint-complete.marker` → set `waiting="rebirth"` → Present human
pause with the paste-ready `/drive <runId>`; the I1 routine is the authority for the proof
modes). Gate A precedence still holds (§ I1 Gate/STOP precedence). If `drive.md` is unreachable, skip the
handler and continue (the Stop-hook backstop still steers).

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

At Gate A just present the direction + Taste/Challenge items and wait for approval. On
approval the coordinator runs **Seam A** — a deterministic context-clear handoff (drive.md
§ Stage 1 / § I1) — which clears context so Execute begins in a FRESH session and presents
the `/drive <runId>` resume line (its single source). No goal is emitted.

(Running `/drive-plan` standalone, without the coordinator: after approval continue manually
— the deterministic handoff is the coordinator's step.)

## After this stage

- Approved → update $RUN_DIR/state.json (`stage=execute`, `lastGate="A"`,
  `waiting=null`), parse the `## Phases` breakdown into the ordered phase ids in
  `state.phaseList`. (This is ONE atomic `state.json` write — `stage=execute` +
  `lastGate="A"` + `waiting=null` + the parsed `phaseList` committed together, per drive.md
  § Stage 1; never a partial `{stage:execute, phaseList:[]}`.) The coordinator then runs
  **Seam A** — the deterministic post-Gate-A
  context-clear handoff (drive.md § Stage 1 / § I1) — so the **execute half begins in a fresh
  session**, not in-context here. **Slices are NOT defined here** — `state.slices` stays
  empty; each phase's `/drive-design phase <P>` produces and records its own slices just
  before that phase implements.
- No approved/converged design (cancelled, or can't converge in 8 rounds) → STOP
  and report what's missing **via the Present human pause routine**: set
  `state.waiting="stop:<reason>"`, then emit the run graph — read
  `~/.claude/commands/drive.md` § *Emit run graph* and follow it (if `drive.md` is
  unreachable, emit `(run graph unavailable: drive.md not found)` and continue) — then
  report. (This makes a standalone `/drive-plan` STOP self-sufficient.)

Do not begin implementation on this command.
