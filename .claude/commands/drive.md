---
description: Autonomous engineering lifecycle — premises → plan (Gate A) → implement → review+codex → verify → ship (Gate B). Drives a task through all stages with two human gates.
argument-hint: <task to drive>
---
You are `/drive` — the autonomous lifecycle coordinator. Advance stages
autonomously; pause only at the gates and non-decision STOPs. You own the **run
model** and **worktree lifecycle**: operate on git **refs + worktrees**, NEVER
mutating the user's main working tree.

Argument: `$ARGUMENTS` is the task (the premise).

## Preconditions (non-decision STOPs)

- gstack installed at `~/.claude/skills/gstack` — else STOP ("gstack not installed").
- Inside a git repo with a **clean main working tree** (`git status --porcelain`
  empty) — else STOP (a run branches from a clean base; don't disturb the user's
  uncommitted work).
- `gh` (or `glab`) + `jq` on PATH for ship.

## Decision policy (every stage)

Apply autoplan's 6 Decision Principles + Mechanical/Taste/User-Challenge
classification (see the harness `CLAUDE.md`; autoplan also carries the canonical 6).
Log decisions to `$RUN_DIR/decisions.md` (promoted
to the repo `.harness/decisions.md` at ship).

**Non-decision STOPs** (red/flaky tests, merge conflict, implement BLOCKED, review
N>8, budget ceiling) pause regardless of policy. If `AskUserQuestion` is
unavailable, report `BLOCKED — AUQ unavailable` rather than auto-deciding.

## Run setup & resume

Generate `runId = <branch>-<timestamp>` and `RUN_DIR = ~/.claude/harness-runs/<runId>/`
(`mkdir -p`). All per-run artifacts live in `$RUN_DIR` (absolute path), reachable
from any worktree. Append a line to `$RUN_DIR/event-log.jsonl` at every dispatch /
verdict / merge / gate.

- **Resume:** if invoked with an existing runId (its `$RUN_DIR/state.json` exists),
  load it, **reconcile worktrees** (`git worktree list` vs `state.slices[].worktree`
  / `phaseReview[].integrationWorktree`; `git worktree remove` + `branch -D`
  orphans; a phase left `integrating` is rebuilt from scratch — see Execute), and
  continue each slice from its `step`.
- **Fresh run:** assert the clean-tree precondition; record `baseRef` (the repo's
  default/integration branch, e.g. `main`); create `featureBranch` from `baseRef`;
  initialize and write `$RUN_DIR/state.json`:

```json
{ "runId": "<id>", "task": "<task>", "stage": "premises",
  "baseRef": "main", "featureBranch": "drive/<id>",
  "phase": 1, "phaseBaseSha": null, "concurrencyCap": 4, "designReview": 0,
  "budget": { "ceilingCalls": null, "ceilingMin": null, "calls": 0, "startedAt": "<iso>" },
  "slices": {}, "phaseReview": {}, "lastGate": null,
  "designPath": "$RUN_DIR/design.md" }
```

Update `state.json` after every transition. Increment `budget.calls` on each
subagent/codex dispatch; if `ceilingCalls`/`ceilingMin` is set and exceeded → STOP
with a spend summary (budget circuit-breaker).

## Pipeline

### Stage 0 — Premises
If the task is ambiguous about WHAT problem to solve, pause and ask. → `stage = plan`

### Stage 1 — Plan (gstack brain)
Run the PLAN stage (`/drive-plan` — `~/.claude/commands/drive-plan.md`): planner authors
`$RUN_DIR/design.md` **with a `## Phases & Slices` breakdown**, autoplan reviews it,
then the dual-voice **design-review** primitive converges it (no open P1). **Gate A**
= autoplan approved AND design converged — the one human gate here. If no
approved/converged design → STOP. → `lastGate = "A"`, `stage = execute`

Parse the breakdown into `state.slices` (`{<id>: {step:"queued", reviewCount:0}}`
with each slice's `owns`/`deps`) and the ordered phase list.

### Stage 2–4 — Execute (per phase; refs + worktrees only)
For each PHASE in order:

1. **Freeze base:** `phaseBaseSha = git rev-parse <featureBranch>`.
2. **Dispatch slices** whose `deps` are CONVERGED, ≤ `concurrencyCap` in flight.
   Slices with **disjoint `owns`** run in PARALLEL; create a worktree per slice
   `git worktree add $RUN_DIR/wt/<id> -b slice/<runId>/<id> <phaseBaseSha>`, copy
   the declared gitignored config allowlist (`.env`, …) in, and dispatch IMPLEMENT
   (`/drive-implement` — `~/.claude/commands/drive-implement.md`) with cwd = that worktree (`step=implementing`).
   Overlapping-`owns` ready slices are NOT parallelized — run by dep order; if the
   design left them unsequenced, STOP (planning bug). Excess past the cap queue.
3. **Per-slice loop:** when a slice's IMPLEMENT returns:
   - `DONE` → `step=awaiting_review`; run REVIEW scoped `slice <id>` (slice-local
     tests). CONVERGED → `step=converged`, then **`git worktree remove` its worktree
     (keep the slice branch for assembly)** — frees a concurrency slot + disk, so
     worktree count stays ≤ cap regardless of slices-per-phase. FINDINGS →
     `step=needs_fix`; if its `reviewCount < 8` re-run IMPLEMENT then REVIEW
     (re-create the worktree first if it was removed); if `>=8` → STOP.
   - `BLOCKED`/`NEEDS_CONTEXT` → `step=blocked`, STOP that slice + surface; other
     in-flight slices continue; the phase can't integrate until it resolves. If the
     blocker needs files outside ownership → **plan-amendment** (amend the design's
     Phases & Slices, re-converge the design review, resume).
4. **Assemble (idempotent)** once ALL slices in the phase are `converged`:
   delete any existing `phaseInt/<P>` branch/worktree, then
   `git worktree add $RUN_DIR/wt/phase<P> -b phaseInt/<P> <phaseBaseSha>`; merge
   each converged slice branch IN. **Conflict → STOP** (the rebuild-from-base is the
   rollback; never `git merge --abort` to undo prior merges). Run the **FULL build +
   integration tests** + REVIEW scoped `phase <P>` in this worktree.
   - CONVERGED → advance `featureBranch` to `phaseInt/<P>` (`git merge --ff-only`,
     else `reset --hard`); `git worktree remove` the integration worktree (slice
     worktrees were already removed on convergence), delete slice branches;
     `phaseReview[<P>].status = converged`; next phase.
   - FINDINGS → route each P1 to the responsible slice (`step=needs_fix`,
     re-dispatch — re-creating its worktree — loop its cap-8), then
     **re-assemble from scratch**.

When all phases are `converged` → `stage = verify`.

### Stage 4b — Verify (optional)
If the change touches a UI/URL (auto-detect), run gstack `qa-only` / `browse` on the
`featureBranch` tree; write `$RUN_DIR/verify.md`. Report-only. Honor "no qa".
→ `stage = ship`

### Stage 5 — Ship (once)
Run the SHIP stage (`/drive-ship` — `~/.claude/commands/drive-ship.md`) on `featureBranch`: promote
`$RUN_DIR/decisions.md`+`followups.md` into the repo ledgers, run the full suite
(red → retry once → STOP), build the **single** commit + PR, **Gate B** (approve
diff), then push/open PR. → `lastGate = "B"`, `stage = done`

## Completion

Report: design path, per-phase verdicts, PR link; a one-line summary of every
decision promoted this run; `followups.md` entries; the event-log path; anything
uncertain. Note any worktrees/branches left for inspection.
