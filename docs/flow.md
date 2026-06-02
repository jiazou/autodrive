# `/drive` execution flow

How a `/drive` run moves through its sub-steps, with the slash command that runs
at each one annotated. Example shape: **2 phases × 2 slices per phase**, each slice
taking **3 implement→review rounds** to converge.

`[C+X]` = the **dual-voice review** = a Claude reviewer subagent **+** `codex exec`.
The Claude subagent and `codex exec` are mechanics *inside* `/review`, not slash
commands themselves.

```
/drive "<task>"                                    ◀══ whole run orchestrated by  /drive
│
├─ STAGE 0  PREMISES                               (no command — /drive inspects the task)
│
├─ STAGE 1  PLAN ─────────────────────────────────  runs  /plan
│    1a  planner subagent → design.md + Phases&Slices      (Agent subagent, no command)
│    1b  autoplan review ───────────────────────────────   runs  /autoplan      (gstack)
│    1c  design-review convergence [C+X] ↺ ────────────    runs  /review · design
│    ◆ GATE A  (human: approve direction)                                   ◀── PAUSE 1
│
├─ EXECUTE ──────────────────────────────────────  loop driven by  /drive
│
│  ┌── PHASE 1 ────────────────────────────────────────────────────────────────┐
│  │   slice 1.1 & 1.2 own DISJOINT files → run IN PARALLEL                     │
│  │                                                                            │
│  │   SLICE 1.1 (parallel)                  SLICE 1.2 (parallel)               │
│  │   R1  /implement 1.1 → /review 1.1[C+X] ↺P1   R1  /implement 1.2 → /review 1.2[C+X] ↺P1
│  │   R2  /implement 1.1 → /review 1.1[C+X] ↺P1   R2  /implement 1.2 → /review 1.2[C+X] ↺P1
│  │   R3  /implement 1.1 → /review 1.1[C+X] ✓CONV  R3  /implement 1.2 → /review 1.2[C+X] ✓CONV
│  │                         └──────────────┬───────────────┘                   │
│  │   PHASE-1 INTEGRATION ──────────────────────────────  runs  /review · phase 1[C+X] → ✓
│  └────────────────────────────────────────────────────────────────────────────┘
│                          │  (phases are SEQUENTIAL)
│  ┌── PHASE 2 ────────────────────────────────────────────────────────────────┐
│  │   SLICE 2.1 (parallel)                  SLICE 2.2 (parallel)               │
│  │   R1  /implement 2.1 → /review 2.1[C+X] ↺P1   R1  /implement 2.2 → /review 2.2[C+X] ↺P1
│  │   R2  /implement 2.1 → /review 2.1[C+X] ↺P1   R2  /implement 2.2 → /review 2.2[C+X] ↺P1
│  │   R3  /implement 2.1 → /review 2.1[C+X] ✓CONV  R3  /implement 2.2 → /review 2.2[C+X] ✓CONV
│  │   PHASE-2 INTEGRATION ──────────────────────────────  runs  /review · phase 2[C+X] → ✓
│  └────────────────────────────────────────────────────────────────────────────┘
│
├─ STAGE 4b  VERIFY (optional) ───────────────────  runs  /qa-only   or  /browse   (gstack)
│
├─ STAGE 5   SHIP (once, whole feature) ──────────  runs  /ship
│            preconditions; tests (red→STOP); build ONE commit + PR
│    ◆ GATE B  (human: approve diff)                                        ◀── PAUSE 2
│            → push + open PR
│
└─ DONE  ── completion report (decisions D-log, followups, PR link)
```

## Legend

- `[C+X]` — dual-voice review: Claude reviewer subagent + `codex exec`
- `↺P1` — a P1 (BLOCKING/MAJOR) was found → loop back to `/implement` (cap 8 rounds)
- `✓CONV` — **converged**: neither voice has an open P1
- `◆` — a human gate. The only two pauses in the whole run.
- slices in a phase run **in parallel** (disjoint file ownership); phases are **sequential**

## Slash-command invocations for this run (2 phases × 2 slices × 3 rounds)

| Command | Times | Where |
|---|---|---|
| `/drive` | 1 | top-level orchestrator |
| `/plan` | 1 | Stage 1 |
| `/autoplan` | 1 | inside `/plan` (gstack) |
| `/implement` | 12 | 4 slices × 3 rounds |
| `/review` | 15 | 12 per-slice + 2 phase-integration + 1 design |
| `/qa-only` | 1 | verify (optional) |
| `/ship` | 1 | Stage 5 |
| **Total** | **32** | + ~15 `codex exec` calls inside the `/review`s (CLI, not a command) |

## Notes

- **Human sees exactly 2 pauses** (Gate A, Gate B); everything between is
  auto-decided via the 6 Decision Principles and logged to `.harness/decisions.md`.
- **`reviewCount` is per-loop** — each slice and each phase-integration carries its
  own counter, so a stuck slice trips the cap-8 on its own without dragging others.
- **Non-decision STOPs** (a slice `BLOCKED`/`NEEDS_CONTEXT`, red tests, a slice that
  can't converge in 8 rounds, budget ceiling) pause regardless of the decision policy.

## Under the hood — run model + worktrees

The diagram is the *logical* flow. Mechanically: each run has a `run-id` + external
`$RUN_DIR` (all state + worktrees); the coordinator works on **refs + worktrees
only**, never your main tree. Each parallel slice runs in its own `git worktree` on
`slice/<id>` from the frozen `phaseBaseSha`; after slices converge the phase branch
is **rebuilt idempotently from `phaseBaseSha`** (rebuild = the rollback),
`featureBranch` advances, worktrees GC. Resume reconciles worktrees from
`state.json`. Full mechanics: `.harness/design.md` + `CLAUDE.md` invariants.
