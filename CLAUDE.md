# Project: Autonomous Engineering Pipeline (`/drive`)

`/drive` coordinates the pipeline: **gstack for planning**, **harness-owned stages
for execution**. It advances autonomously between two human gates (A, B) and
non-decision STOPs.

## Operating rules (canonical, imported)

Canonical operating rules live in `OPERATING.md` (imported here, and by the
machine-global `~/CLAUDE.md`):

@OPERATING.md

## Pipeline

`/drive <task>` runs:

```
PLAN (gstack brain)
0. Premises (human; never auto-decided)
1. /plan: planner authors design + a ## Phases & Slices breakdown
   → autoplan reviews → dual-voice design review converges (no P1) → Gate A

EXECUTE (harness-owned) — for each PHASE in order:
2. /implement per slice — independent slices run in PARALLEL (file-ownership scoped)
3. /review per slice — Claude subagent + codex; converged = no P1; cap 8
   then a phase-integration /review over the assembled phase
4. verify — qa-only / browse (optional), after all phases converge
5. /ship ONCE → Gate B → push
```

The stage commands (`/plan`, `/implement`, `/review`, `/ship`) are single-sourced
runners that `/drive` invokes in order; you can also step them manually within an
existing run (a new task is a new run-id).

## Why this shape

gstack skills split into two classes:
- **Advisory** (`plan-*-review`, `autoplan`, `codex`) — gstack's sweet spot;
  `/drive` drives them autonomously.
- **Operational / terminal** (gstack `/review`, `/ship`, `/qa`) — fix-first /
  auto-push / test-fix. They resist passive autonomous wrapping, so the harness
  **owns** implement / review / ship directly (calling the codex CLI, git, and
  the test runner).

The implementer/reviewer/planner roles are generic `Agent` subagents:
**sequential phases**, with **independent slices fanned out in parallel** via file
ownership — no parallel-team framework needed (rationale: `.harness/decisions.md`
D1).

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
- **Every review — the design review and every code review — runs both a Claude
  reviewer subagent AND codex.** A review is **converged** only when neither voice
  has an open **P1** (BLOCKING or MAJOR); P2/P3 are logged, not blocking.
- Each slice/phase implement→review loop caps at **8** rounds (own `reviewCount`).
  Beyond that, surface the disagreement with what each side asserts.
- **File ownership is the parallelism contract:** independent slices own disjoint
  files and run in parallel; a slice never writes outside its owned files.
- Run codex from the **main** context (background + per-scope log), never inside a
  subagent that waits on it.
- The coordinator operates on git **refs + worktrees** only — it **never mutates
  the user's main working tree**. A run starts from a clean tree on a fresh
  `featureBranch` (from `baseRef`).
- Each parallel slice runs in its **own coordinator-created worktree** on a
  `slice/<runId>/<id>` branch cut from the frozen `phaseBaseSha = rev-parse
  featureBranch`. The phase integration branch is **rebuilt idempotently** from
  `phaseBaseSha` each assembly — that rebuild *is* the conflict/crash rollback
  (never `git merge --abort`).
- All per-run artifacts live in the external **`$RUN_DIR`** (absolute,
  worktree-reachable); the committed repo ledgers are promoted at ship.

## Run state & shared memory

Per-run state lives in **`$RUN_DIR` = `~/.claude/harness-runs/<run-id>/`** (external,
so every worktree reaches it by absolute path; not committed, not portable):

```
task.md / design.md          -- premise; planner design (+ ## Phases & Slices)
state.json                   -- run model: runId, baseRef, featureBranch, phase,
                                phaseBaseSha, concurrencyCap, budget, per-slice
                                {step,reviewCount,branch,worktree,baseSha}, phaseReview
event-log.jsonl              -- append-only dispatch/verdict/merge/gate timeline
review-<scope>-N.md          -- per-scope (design/slice/phase) review outputs
codex-review-<scope>.md      -- codex findings; codex-raw-<scope>.log raw
decisions.md / followups.md  -- run-local ledgers (promoted to the repo at ship)
verify.md                    -- verify-stage evidence
wt/                          -- per-slice + integration + ship worktrees
```

The **committed** cross-task ledgers stay in the repo: `.harness/decisions.md`,
`.harness/followups.md`. Read `.harness/decisions.md` at the start of a task to
stay consistent; the coordinator promotes a run's `$RUN_DIR` ledgers into them at
ship.
