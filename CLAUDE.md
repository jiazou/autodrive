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
1. /drive-plan: planner authors a HIGH-LEVEL design (goal · approach · ordered ## Phases —
   no slice/interface detail) → autoplan reviews → dual-voice design review converges
   (no P1) → Gate A

EXECUTE (harness-owned) — for each PHASE in order (design is progressively refined: the
high-level plan → a detailed per-phase design → a per-slice assumption check):
2. /drive-design phase — author the phase's DETAILED design (interfaces, edge cases, slice
   breakdown) against the REAL prior-phase code; dual-voice review converges (cap 8); no
   human gate. Populates this phase's slices.
3. /drive-implement per slice — independent slices run in PARALLEL (file-ownership scoped).
   FIRST validates the slice's assumptions vs reality (deps' real code/comments, decisions,
   logs): hold → implement; minor drift → adapt; BIG divergence → STATUS: REDESIGN, which
   re-runs the phase design (step 2) with review and re-derives the affected slices.
4. /drive-review per slice — Claude subagent + codex; converged = no P1; cap 8
   then a phase-integration /drive-review over the assembled phase
5. /drive-harden phase — after the phase review converges: a mutating find→fix→verify
   pass over the assembled phase to add missing tests, fix logic bugs (de-slop is
   DEFERRED to the final aggregate /drive-finalize stage)
   (own cap 3; re-runs the conformance review as a regression guard); then advance
6. /drive-finalize — ONCE after all phases hardened, BEFORE verify: an aggregate quality
   pass over the whole-run diff (baseRef..featureBranch) that LEADS with de-slop (moved out
   of per-phase harden) + a whole-run logic-bug/missing-test sweep; routes architectural
   findings to the driven project's TODO.md; emits the ship gate's terminal SHA-bound review
   artifact (own cap 3)
7. verify — qa-only / browse (optional), after finalize
8. /drive-ship ONCE → Gate B → push
```

The stage commands (`/drive-plan`, `/drive-design`, `/drive-implement`, `/drive-review`, `/drive-harden`, `/drive-finalize`, `/drive-ship`) are single-sourced
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

**Deterministic context-clear handoffs (fresh context per leg).** Beyond the gates, `/drive`
checkpoints, runs `/decant`, clears context, and resumes in a FRESH session at two
deterministic **seams**: **after Gate A approval** (→ Execute starts fresh) and **after each
phase advance** (→ the next phase's design, or Finalize after the last phase, starts fresh).
These reuse the existing **rebirth** checkpoint-and-handoff routine (drive.md § I1 steps 2–6,
trigger class B) — they are NOT a new mechanism; the durable run-state lives in `$RUN_DIR`
(paths, not context) and the handoff emits the minimal succinct prompt (`/drive <runId>`).
The context-pressure rebirth (class A, Stop-hook-triggered) remains as a
safety net for any single leg that overflows its window. **Decant runs at every context-clear
boundary** (I1 step 5.5) — distilling the outgoing leg's learnings before they are lost — plus
once at the true run-wrap (after Gate B). Clearing context = a fresh session, which Claude
Code cannot self-initiate: you paste `/drive <runId>` at each `═══` boundary; the installed
Stop hook re-arms autonomy WITHIN each leg.

No other pauses. Not for ambiguous design choices, not for severity calls — the
6 principles decide and the decision is logged.

## Invariants

- Pass file **paths** between subagents, not file contents.
- Never include the implementer's notes/rationale in the reviewer's prompt — the
  reviewer judges the code against the spec on its own merits.
- **Every review — the design review and every code review — runs both a Claude
  reviewer subagent AND codex.** A review is **converged** only when neither voice
  has an open **P1** (BLOCKING or MAJOR); P2/P3 are logged, not blocking.
- Each slice/phase implement→review loop caps at **8** rounds (own counter — a slice's
  `reviewCount`, a phase's `phaseReview[<P>].round`). Beyond that, surface the
  disagreement with what each side asserts.
- **Each phase ends with a HARDEN pass** (after its review converges, before
  `featureBranch` advances): a mutating find→fix→verify over the assembled phase for
  missing tests and logic bugs (de-slop is deferred to `/drive-finalize`) — *beyond*
  acceptance criteria. It bounds edits to the phase's own surface + test-support
  (scope-creep gate, with flagged root-cause exceptions) and vetoes edits that would
  drop a criterion's coverage. The phase reaches the terminal `hardened` status — and
  `featureBranch` advances by a pure ref move — only when harden returns HARDENED.
- **Harden has its own cap of 3 fix rounds**, independent of the conformance cap-8: the
  confirming clean audit is free, and its regression guard runs `/drive-review phase
  <P> harden-regress` (which does NOT touch the phase `round`), so a phase whose
  integration already used 6–8 rounds is never false-STOPped during hardening.
- **The run ends with a single FINALIZE pass** (`/drive-finalize`, Stage 4c) AFTER all
  phases hardened and BEFORE Verify — an aggregate de-slop + whole-run
  logic-bug/missing-test sweep over `baseRef..featureBranch`, run in
  `$RUN_DIR/wt/finalize`. It emits the ship gate's TERMINAL SHA-bound review
  (`review-finalize-N.md` with `reviewed-sha == featureBranch tip`); ship's tip-binding
  candidate-R is THIS artifact (the phase-integration review is demoted to a
  precondition), so a run that omits or fails finalize CANNOT ship (omission- and
  non-convergence-proof). Own cap FINALIZE_CAP=3 fix rounds; counter
  `state.finalizeRound`.
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
task.md / design.md          -- premise; HIGH-LEVEL design (goal · approach · ## Phases)
design-phase<P>.md           -- per-phase DETAILED design (interfaces, edge cases, Slices)
state.json                   -- run model: runId, baseRef, featureBranch, repoRoot, stage, phase,
                                phaseBaseSha, concurrencyCap, designReview, budget, per-slice
                                {step,reviewCount,owns,deps} (populated per-phase by /drive-design),
                                phaseDesign{round,status,redesigns} per phase (status
                                designing→converged; round = design-review cap-8 counter;
                                redesigns = REDESIGN re-run count, cap 3),
                                phaseReview{status,round,hardenRound} where status
                                = converged→hardening→hardened (terminal); plus the
                                top-level run-singleton counter finalizeRound;
                                plus lastGate, designPath, rebirth_pending (signal/hint —
                                never a proof input), and the Stop-hook keys the hooks
                                read: sessionId, autoContinue, waiting
event-log.jsonl              -- append-only dispatch/verdict/merge/gate timeline
review-<scope>-N.md          -- per-scope (design/phasedesign<P>[-r<R>]/slice/phase/finalize) review outputs
codex-review-<scope>.md      -- codex findings; codex-raw-<scope>.log raw
harden-<P>-N.md              -- per-phase harden audit (2-lens) outputs
codex-harden-<P>.md          -- codex harden findings; codex-harden-<P>.log raw
finalize-todo.md             -- finalize architectural follow-ups (durable; promoted to
                                repo-root TODO.md at ship)
redesign-<P>-r<R>.marker     -- append-only redesign epoch markers (highest R = the
                                artifact-derived redesign count; current review epoch)
inflight-<kind>-<scope>.marker -- open = a dispatch unit in flight (write-before-dispatch,
                                clear-after-record); none open = half of "safe boundary"
                                (e.g. inflight-finalize.marker brackets the finalize dispatch)
checkpoint-complete.marker   -- single-use checkpoint proof record (tip-bound; consumed
                                at resume; never an authorization)
decisions.md / followups.md  -- run-local ledgers (promoted to the repo at ship)
verify.md                    -- verify-stage evidence
wt/                          -- per-slice + integration + ship worktrees
```

The **committed** cross-task ledgers stay in the repo: `.harness/decisions.md`,
`.harness/followups.md`. Read `.harness/decisions.md` at the start of a task to
stay consistent; the coordinator promotes a run's `$RUN_DIR` ledgers into them at
ship.
