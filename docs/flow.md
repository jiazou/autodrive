# `/drive` execution flow

How a `/drive` run moves through its sub-steps, with the slash command that runs
at each one annotated. Example shape: **2 phases × 2 slices per phase**, each phase
opening with a **1-round architectural design**, each slice taking **3 implement→review
rounds** to converge, then a **1-round harden** per phase, and finally a single
**1-round aggregate finalize** over the whole run.

`[C+X]` = the **dual-voice review** = a Claude reviewer subagent **+** `codex exec`.
The Claude subagent and `codex exec` are mechanics *inside* `/drive-review`, not slash
commands themselves.

**Design is progressively refined across three tiers** — each defers detail to where more
real information exists:
- **Tier 1 — high-level, whole run** — `/drive-plan` → `design.md`: goal · approach · the
  ordered `## Phases` only (NO slices/interfaces). Gate A approves this shape.
- **Tier 2 — detailed, per phase** — `/drive-design phase <P>` → `design-phase<P>.md`: that
  phase's interfaces, edge cases, and slice breakdown, authored against the REAL code earlier
  phases produced; dual-voice review converges (cap 8); no human gate.
- **Tier 3 — assumption check, per slice** — `/drive-implement` first validates the slice's
  assumptions vs reality; a BIG divergence returns `REDESIGN`, re-running Tier 2 with review.

> **Tier 1 (`/drive-plan`) and Tier 2 (`/drive-design`) are different commands with different
> scopes.** `/drive-plan` runs ONCE before Gate A and writes the high-level `design.md`.
> `/drive-design` runs ONCE PER PHASE during Execute, writes a per-phase `design-phase<P>.md`,
> and only *reads* `design.md` for context — it never writes it. `/drive-design` is never
> invoked before Gate A.

```
/drive "<task>"                                    ◀══ whole run orchestrated by  /drive
│
├─ STAGE 0  PREMISES                               (no command — /drive inspects the task)
│
├─ STAGE 1  PLAN  (Tier 1: high-level, whole run) ─  runs  /drive-plan
│    1a  planner subagent → design.md = goal · approach · ## Phases   (Agent subagent, no command)
│            (HIGH-LEVEL — NO slices, NO interfaces)
│    1b  autoplan review ───────────────────────────────   runs  /autoplan      (gstack)
│    1c  design-review convergence [C+X] ↺ ────────────    runs  /drive-review · design
│    ◆ GATE A  (human: approve the shape / direction)                       ◀── PAUSE 1
│
├─ EXECUTE ──────────────────────────────────────  loop driven by  /drive  (phases SEQUENTIAL)
│
│  ┌── PHASE 1 ────────────────────────────────────────────────────────────────────────┐
│  │  ① ARCH DESIGN  (Tier 2: detailed, THIS phase) ──────  runs  /drive-design · phase 1 │
│  │       → design-phase1.md = interfaces · edge cases · SLICES                          │
│  │         (authored against the REAL code earlier phases produced)                     │
│  │       design-review convergence [C+X] ↺(cap 8) → ✓CONV       (NO human gate)         │
│  │       ⊘ phasedesign-gate (fail-closed): slices below CANNOT build until ✓CONV         │
│  │  ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈            │
│  │  ② BUILD SLICES — 1.1 & 1.2 own DISJOINT files → run IN PARALLEL                     │
│  │      (each /drive-implement FIRST runs a Tier-3 assumption check vs reality;         │
│  │       BIG divergence → REDESIGN ↺──────────────── back to ① /drive-design phase 1)   │
│  │      SLICE 1.1 (parallel)                    SLICE 1.2 (parallel)                    │
│  │      R1 /drive-implement 1.1 → /drive-review 1.1[C+X] ↺P1  R1 …1.2 → …[C+X] ↺P1       │
│  │      R2 /drive-implement 1.1 → /drive-review 1.1[C+X] ↺P1  R2 …1.2 → …[C+X] ↺P1       │
│  │      R3 /drive-implement 1.1 → /drive-review 1.1[C+X] ✓CONV R3 …1.2 → …[C+X] ✓CONV    │
│  │                          └──────────────┬───────────────┘                            │
│  │  ③ PHASE-1 INTEGRATION ───────────────────────────  runs  /drive-review · phase 1[C+X] → ✓
│  │  ④ PHASE-1 HARDEN ↺(cap 3) ───────────────────────  runs  /drive-harden · phase 1     │
│  │       find→fix→verify: ① add tests ② fix bugs; de-slop→finalize; re-review[C+X] → ✓HARDENED
│  └──────────────────────────────────────────────────────────────────────────────────────┘
│                          │  (advance featureBranch, then next phase)
│  ┌── PHASE 2 ────────────────────────────────────────────────────────────────────────┐
│  │  ① ARCH DESIGN ───────────────────────────────────  runs  /drive-design · phase 2   │
│  │       → design-phase2.md (interfaces · edge cases · SLICES, vs Phase-1's REAL code)  │
│  │       design-review [C+X] ↺(cap 8) → ✓CONV                   (NO human gate)         │
│  │       ⊘ phasedesign-gate (fail-closed): slices below CANNOT build until ✓CONV         │
│  │  ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈            │
│  │  ② BUILD SLICES 2.1 ‖ 2.2  (Tier-3 check each; REDESIGN ↺ → ① if big divergence)     │
│  │      R1…R3  /drive-implement 2.x → /drive-review 2.x[C+X]  → ✓CONV                    │
│  │  ③ PHASE-2 INTEGRATION ───────────────────────────  runs  /drive-review · phase 2[C+X] → ✓
│  │  ④ PHASE-2 HARDEN ↺(cap 3) ───────────────────────  runs  /drive-harden · phase 2 → ✓HARDENED
│  └──────────────────────────────────────────────────────────────────────────────────────┘
│                          │  (ALL phases hardened → featureBranch final)
│  ┌── STAGE 4c  FINALIZE  (once, whole run, before Verify) ── runs  /drive-finalize ──────┐
│  │       aggregate pass over  git diff baseRef..featureBranch  (the WHOLE-RUN diff)       │
│  │       find→fix→verify ↺(cap FINALIZE_CAP=3): ① de-slop (LED — moved out of harden)     │
│  │                                              ② aggregate missing tests ③ aggregate bugs│
│  │       MAJOR architectural findings → $RUN_DIR/finalize-todo.md (ship promotes → TODO.md)│
│  │       dual-voice audit[C+X] → ✓CONV; emits review-finalize-N.md = the ship gate's      │
│  │       TERMINAL SHA-bound review (reviewed-sha == featureBranch tip)                     │
│  └──────────────────────────────────────────────────────────────────────────────────────┘
│
├─ STAGE 4b  VERIFY (optional) ───────────────────  runs  /qa-only   or  /browse   (gstack)
│
├─ STAGE 5   SHIP (once, whole feature) ──────────  runs  /drive-ship
│            preconditions; tests (red→STOP); build ONE commit + PR
│    ◆ GATE B  (human: approve diff)                                        ◀── PAUSE 2
│            → push + open PR
│
└─ DONE  ── completion report (decisions D-log, followups, PR link)
```

## Legend

- `[C+X]` — dual-voice review: Claude reviewer subagent + `codex exec`
- `↺P1` — a P1 (BLOCKING/MAJOR) was found → loop back to `/drive-implement` (cap 8 rounds)
- `✓CONV` — **converged**: neither voice has an open P1
- `✓HARDENED` — phase harden clean (no open P1, nothing cheap left) + conformance re-review still converged
- `REDESIGN ↺` — a slice's Tier-3 assumption check found the phase design is stale vs reality
  → re-run that phase's `/drive-design` (Tier 2) with review (bounded: 3 redesigns/phase)
- `‖` — slices that run in parallel (disjoint file ownership)
- `◆` — a human gate. The only two **approval** gates in the run (non-decision STOPs also
  pause — red tests, BLOCKED, a cap exceeded — but those are halts, not approvals; see Notes)
- `⊘ phasedesign-gate` — an **omission-proof** gate (not a human pause): a phase's slices
  cannot be built (the slice worktree-add is denied) until its Tier-2 design review is
  ✓CONV. One link in the enforcement gate chain `plan → phasedesign → slice → phase → ship`
  (full mechanics: `docs/drive-enforcement.md`)
- **design tiers:** ① per-phase ARCH DESIGN (`/drive-design`, Tier 2) is **distinct** from the
  Stage-1 whole-run design (`/drive-plan`, Tier 1) — different command, file, and scope
- phases are **sequential**; slices within a phase run **in parallel**
- **HARDEN** runs once per phase after its review converges — a *mutating* find→fix→verify
  (add tests / fix bugs; de-slop deferred to finalize), own **cap 3**, scoped to the phase
  diff; advance only when ✓HARDENED
- **FINALIZE** runs once for the whole run after ALL phases harden and before Verify — an
  aggregate find→fix→verify over `baseRef..featureBranch` that LEADS with de-slop (moved out
  of per-phase harden) plus an aggregate missing-test / logic-bug sweep, own **cap
  FINALIZE_CAP=3**; appends MAJOR architectural findings to `$RUN_DIR/finalize-todo.md` (ship
  promotes it to the project's `TODO.md`) and emits the ship gate's terminal SHA-bound review
  (`review-finalize-N.md`)

## Slash-command invocations for this run (2 phases × 2 slices × 3 rounds)

| Command | Times | Where |
|---|---|---|
| `/drive` | 1 | top-level orchestrator |
| `/drive-plan` | 1 | Stage 1 — Tier-1 high-level whole-run design |
| `/drive-design` | 2 | Execute, once per phase — Tier-2 detailed per-phase design |
| `/autoplan` | 1 | inside `/drive-plan` (gstack) |
| `/drive-implement` | 12 | 4 slices × 3 rounds (each first runs a Tier-3 assumption check) |
| `/drive-review` | 19 | 12 per-slice + 2 phase-integration + 1 whole-run design + 2 per-phase design + 2 harden-regress |
| `/drive-harden` | 4 | per phase: 1 fix round (→ FINDINGS) + 1 free confirming audit (→ HARDENED); 2 phases. Up to 3 fix rounds/phase. Add tests + fix bugs only (de-slop deferred to `/drive-finalize`) |
| `/drive-finalize` | 2 | Stage 4c, once for the whole run: 1 fix round (→ FINDINGS) + 1 free confirming audit (→ CONVERGED). De-slop-led aggregate sweep over `baseRef..featureBranch`. Up to FINALIZE_CAP=3 fix rounds |
| `/qa-only` | 1 | verify (optional) |
| `/drive-ship` | 1 | Stage 5 |
| **Total** | **44** | exact for this idealized run, and a floor (1 round per phase design, 3 per slice, 1 harden fix round/phase, 1 finalize fix round). A `REDESIGN` or extra round only adds more. + `codex exec` inside every `/drive-review`, every `/drive-harden` audit, AND every `/drive-finalize` audit (CLI, not a command) |

## Notes

- **Human sees exactly 2 pauses** (Gate A, Gate B); everything between is
  auto-decided via the 6 Decision Principles and logged to `.harness/decisions.md`.
  Per-phase architectural design (Tier 2) is dual-voice reviewed but **adds no gate** —
  Gate A already approved the shape.
- **Two distinct design commands:** `/drive-plan` (Tier 1, once, `design.md`, high-level
  whole-run shape) vs `/drive-design` (Tier 2, once per phase, `design-phase<P>.md`, detailed
  single-phase). The latter reads `design.md` for context and never writes it.
- **The review-round counter is per-loop** — each slice (`reviewCount`), each phase
  integration (`phaseReview[<P>].round`), and each per-phase design (`phaseDesign[<P>].round`)
  carries its own counter, so a stuck unit trips its cap-8 without dragging others.
- **HARDEN has its own `hardenRound` cap-3**, separate from the conformance cap-8, so
  a few legitimate harden rounds can't exhaust the review budget. Per-phase harden adds
  tests + fixes bugs only; slop it spots is RECORDED (under `## slop (deferred to finalize)`)
  and handed to `/drive-finalize`, never fixed in-phase. A phase left mid-harden
  resumes from its committed harden commits on `phaseInt/<P>` (not rebuilt).
- **FINALIZE has its own `finalizeRound` cap (FINALIZE_CAP=3)**, separate from the
  conformance cap-8 and from harden's cap-3 — its free confirming clean audit is free
  (does not increment the counter). De-slop edits that would drop an acceptance criterion's
  coverage are **vetoed** (logged to followups), which is what stops de-slop ↔ conformance
  oscillation. A terminal FINDINGS / cap-exceeded finalize leaves the ship gate's terminal
  review absent, so the run **cannot ship** (omission- and non-convergence-proof).
- **Non-decision STOPs** (a slice `BLOCKED`/`REDESIGN`-loop exceeded, `NEEDS_CONTEXT`, red
  tests, a unit that can't converge in its cap, budget ceiling) pause regardless of policy.

## Under the hood — run model + worktrees

The diagram is the *logical* flow. Mechanically: each run has a `run-id` + external
`$RUN_DIR` (all state + worktrees); the coordinator works on **refs + worktrees
only**, never your main tree. Each phase first designs itself in a **detached read worktree**
at the current `featureBranch` tip (so its design sees real prior-phase code); then each
parallel slice runs in its own `git worktree` on `slice/<id>` from the frozen `phaseBaseSha`;
after slices converge the phase branch is **rebuilt idempotently from `phaseBaseSha`**
(rebuild = the rollback), then the phase is **hardened** in that integration worktree
(add tests / fix bugs — de-slop deferred to finalize — committed onto `phaseInt/<P>`); only
then does `featureBranch` advance and worktrees GC. After ALL phases harden, **finalize**
runs ONCE in a dedicated `$RUN_DIR/wt/finalize` worktree at the `featureBranch` tip — a
de-slop-led aggregate sweep over `baseRef..featureBranch` whose commits land directly on
`featureBranch` and whose terminal `review-finalize-N.md` binds the shipped tip. Resume
reconciles worktrees from git truth. Full mechanics: `CLAUDE.md` invariants + the stage
command files.

## Context-pressure rebirth

A long run can fill its context window before it reaches DONE. Rather than overrun
silently, `/drive` detects the pressure and **hands the run off to a fresh session at a
proven-safe boundary** — a continuation, not a restart.

**Detection (signal-only).** The **Stop hook** (`bin/drive-stop-hook.py`) is the SOLE detector.
It watches the same token-sum the statusline computes (the latest assistant line's `input +
cache_creation + cache_read` tokens ÷ the model's window, from `bin/rebirth-thresholds.json`):
it fires every turn and, past the **hard** high-water mark, appends a steer to its block
reason — first instructing the coordinator to set `rebirth_pending`, then (once set) to run
the handoff at its next safe boundary. There is NO coordinator-side self-measurement — the
coordinator eyeballing its own context pressure over-triggers (subagent/codex volume lives in
other contexts, so the coordinator's own transcript grows far slower than the visible churn).
The coordinator sets `rebirth_pending` only when the hook steers it.

The hook does not act directly — it only steers the coordinator to *record* the
`rebirth_pending` signal. Acting on it is separated out so the handoff happens at a boundary
the run can actually resume from.

**The handshake (safe-boundary, prove-then-pause).** When `rebirth_pending` is set and the
coordinator reaches a safe boundary — no open `inflight-*.marker` AND no partial multi-step
git mutation detectable from git AND the current atomic step finished (a REDESIGN
marker-write → state-write span is never split) — the shared **I1 rebirth handler** runs, in
order:
1. **Prove** resumability — both `bin/drive-conformance.sh $RUN_DIR --mode checkpoint` AND
   `--mode state-lint` must be clean (fail-closed: a failing proof never sets the pause).
2. **Write** `checkpoint-complete.marker` (durable, sha-bound, single-use).
3. **Set** `waiting="rebirth"`, then present a human pause with a paste-ready `/drive
   <runId>` resume line + a re-armed `/goal`, and end the turn.

This is a **prompted human handshake, not a self-restart** — by design the harness does
not spawn sessions programmatically; a fresh session is started by the human pasting the resume line.
Resume is a *continue*: the new session rebinds `state.sessionId` to itself, consumes the
marker, re-proves (both modes), re-arms, clears `waiting`, and drives on.

I1 fires at the safe boundaries of every autonomous stage — **Plan**, **per-phase design**,
**Execute** (per-slice / phase-integration / harden / advance), **Verify**, and the **Ship**
dispatch boundary. If a Gate (A/B) or a non-decision STOP and a rebirth are both due, the
**gate/STOP wins** and the human resumes in a fresh session by pasting the runId themselves.

Durable-checkpoint mechanics, the conformance modes, and the acknowledged residual limits:
`docs/drive-enforcement.md` § "Durable checkpoint & rebirth".
