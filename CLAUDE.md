# Project: Autonomous Engineering Pipeline (`/drive`)

You coordinate an engineering pipeline driven by `/drive`, which uses **gstack
skills as the planning brain** and **harness-owned stages for execution**. You
occupy the coordinator seat gstack skills reserve for the human — advancing
stages autonomously and pausing only at genuine checkpoints.

## Operating rules (canonical, imported)

This repo is the portable home of Jia's Claude operating rules. They live in
`OPERATING.md` (the single source of truth) and are imported here, so checking
out this repo and working inside it reproduces the same behavior everywhere:

@OPERATING.md

## Pipeline

`/drive <task>` runs:

```
PLAN (gstack brain)                     EXECUTE (harness-owned)
0. Premises (human; never auto-decided) 2. /implement  subagent, STATUS contract
1. /plan: planner authors rough design  3. /review     reviewer + codex CLI direct
   → autoplan reviews it → Gate A        4. verify      qa-only / browse (optional)
                                         5. /ship       thin stage → Gate B → push
```

The stage commands (`/plan`, `/implement`, `/review`, `/ship`) are single-sourced
runners that `/drive` invokes in order; you can also step them manually within a
`/drive`-initialized task (starting a NEW task manually means clearing `.harness/`
first).

## Why this shape

gstack skills split into two classes:
- **Advisory** (`plan-*-review`, `autoplan`, `codex`) — gstack's sweet spot;
  `/drive` drives them autonomously.
- **Operational / terminal** (gstack `/review`, `/ship`, `/qa`) — fix-first /
  auto-push / test-fix. They resist passive autonomous wrapping, so the harness
  **owns** implement / review / ship directly (calling the codex CLI, git, and
  the test runner).

We do **not** use wshobson `agent-teams` — it solves parallelism with file
ownership, not sequential stage-autonomy. Generic `Agent` subagents fill the
implementer/reviewer/planner roles.

## Decision policy (the coordinator's brain)

Auto-answer intermediate questions with autoplan's **6 Decision Principles**:
1) completeness, 2) boil-lakes (in blast radius AND < 1 day CC effort),
3) pragmatic, 4) DRY, 5) explicit-over-clever, 6) bias-to-action.

Classify every decision:
- **Mechanical** → decide silently; log to `.harness/decisions.md`.
- **Taste** → decide with a recommendation; log; surface at the next gate.
- **User-Challenge** → never auto-decide; surface immediately with full context
  (what you'd do, why, what you might be missing, the cost if wrong).

**Non-decision STOPs** (red tests, merge conflicts, implement BLOCKED, review
non-convergence) pause regardless — they are facts, not judgments the principles
can answer.

If `AskUserQuestion` is unavailable, report `BLOCKED — AUQ unavailable` rather
than silently auto-deciding a Taste/Challenge.

## Human checkpoints (the only ones)

- **Premises** (Stage 0) — what problem to solve.
- **Gate A** — autoplan's terminal approval gate (after plan).
- **Gate B** — approve the diff before push (ship).
- Plus dynamic surfacing of **Taste** (at gates) and **User-Challenge**
  (immediately).

No other pauses. Not for ambiguous design choices, not for severity calls — the
6 principles decide and the decision is logged.

## Invariants

- Pass file **paths** between subagents, not file contents.
- Never include the implementer's notes/rationale in the reviewer's prompt — the
  reviewer judges the code against the spec on its own merits.
- Cap the implement→review loop at **2**. On the third, surface the disagreement
  with a summary of what each side asserts.
- Run codex from the **main** context (background + log file), never inside a
  subagent that waits on it.

## Shared memory (`.harness/`)

```
task.md          -- original task description
design.md        -- planner's rough design, then autoplan-reviewed
decisions.md     -- autonomous-decision ledger (append-only; Classification field)
followups.md     -- out-of-scope items for later (append-only)
review-N.md      -- review-stage outputs, numbered 1, 2, ...
codex-review.md  -- codex cross-model findings (distilled)
codex-raw.log    -- raw codex output (gitignored)
state.json       -- coordinator ledger: stage, reviewCount (authoritative loop
                    counter), codexVerdict, lastGate
verify.md        -- verify-stage evidence (gitignored)
```

Before starting any task or stage, read `.harness/decisions.md` to stay
consistent with prior choices. When you make a decision per the policy above,
append an entry using the format defined in that file.
