# Project: Autonomous Engineering Pipeline (`/drive`)

`/drive` coordinates the pipeline: **gstack for planning**, **harness-owned stages for
execution** — autonomous between two human gates (A, B) and non-decision STOPs.

## Operating rules (canonical, imported)

@OPERATING.md

## Pipeline

`/drive <task>` runs the stages below — design progressively refined: high-level plan
→ per-phase detailed design → per-slice assumption check.

```
PLAN (gstack brain)
0. Premises (human; never auto-decided)
1. /drive-plan: HIGH-LEVEL design (goal · approach · ordered ## Phases; no slice/interface detail) → autoplan + dual-voice review converge (no P1) → Gate A
EXECUTE (harness-owned) — per PHASE, in order:
2. /drive-design phase — DETAILED design (interfaces, edge cases, slices) vs the REAL prior-phase code; dual-voice review (cap 8); no human gate
3. /drive-implement per slice — slices run in PARALLEL under file ownership; FIRST validate assumptions vs reality: hold → implement; drift → adapt; BIG divergence → STATUS: REDESIGN → re-run the phase design (step 2), re-derive the slices
4. /drive-review per slice — Claude subagent + codex; converged = no P1; cap 8; then a phase-integration /drive-review
5. /drive-harden phase — after the phase review converges: a mutating find→fix→verify for missing tests + logic bugs (de-slop deferred to the aggregate finalize stage); own cap 3; then advance
6. /drive-finalize — ONCE after all phases hardened, BEFORE verify: whole-run (baseRef..featureBranch) de-slop + logic-bug/missing-test sweep; architectural findings → TODO.md; emits the ship gate's terminal SHA-bound review (own cap 3)
7. verify — qa-only / browse (optional), after finalize
8. /drive-ship ONCE → Gate B → push
```

The stage commands are single-sourced runners `/drive` invokes in order; you can also
step them manually within an existing run (a new task is a new run-id).

## Decision policy (the coordinator's brain)

Auto-answer intermediate questions with autoplan's **6 Decision Principles**:
1) completeness, 2) boil-lakes (in blast radius AND < 1 day CC effort), 3) pragmatic,
4) DRY, 5) explicit-over-clever, 6) bias-to-action. Classify every decision:
- **Mechanical** → decide silently; log to `.harness/decisions.md`.
- **Taste** → decide with a recommendation; log; surface at the next gate.
- **User-Challenge** → never auto-decide; surface immediately with full context
  (what you'd do, why, what you might be missing, the cost if wrong).

**Non-decision STOPs** (red tests, merge conflicts, implement BLOCKED, review
non-convergence) pause regardless — facts, not judgments. If `AskUserQuestion` is
unavailable, report `BLOCKED — AUQ unavailable` instead of auto-deciding a
Taste/Challenge.

## Human checkpoints (the only ones)

- **Premises** (Stage 0) — what problem to solve.
- **Gate A** — autoplan's terminal approval gate (after plan).
- **Gate B** — approve the diff before push (ship).
- Plus dynamic surfacing of **Taste** (at gates) and **User-Challenge** (immediately).

**Deterministic context-clear handoffs (fresh context per leg).** `/drive`
checkpoints, runs `/decant`, clears context, and resumes FRESH at two
**seams** — **after Gate A approval** and **after each phase advance** —
reusing the **rebirth** checkpoint-and-handoff routine (drive.md § I1 steps
2–6, trigger class B); the durable run-state lives in `$RUN_DIR` (paths, not
context). The context-pressure rebirth (class A, Stop-hook-triggered) stays
as the safety net for a leg that overflows its window. **Decant runs at
every context-clear boundary** (I1 step 5.5), plus once at the true run-wrap
(after Gate B). The handoff is human-initiated by design — you paste the
emitted minimal prompt `/drive <runId>` at each `═══` boundary; the
installed Stop hook re-arms autonomy WITHIN each leg.

No other pauses — not ambiguous design choices, not severity calls; the 6 principles
decide and the decision is logged.

## Invariants

- Pass file **paths** between subagents, not file contents.
- Never include the implementer's notes/rationale in the reviewer's prompt — the
  reviewer judges the code against the spec.
- **Every review — design and code — runs both a Claude reviewer subagent AND
  codex.** **Converged** = no open **P1** from either voice (BLOCKING or MAJOR);
  P2/P3 logged, not blocking.
- Each slice/phase implement→review loop caps at **8** rounds (own counters:
  `reviewCount`, `phaseReview[<P>].round`); beyond that, surface the disagreement.
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
- The coordinator operates on git **refs + worktrees** only — **never mutating the
  user's main working tree**; a run starts from a clean tree on a fresh
  `featureBranch` (from `baseRef`).
- Each parallel slice runs in its **own coordinator-created worktree** on a
  `slice/<runId>/<id>` branch cut from the frozen `phaseBaseSha` (= `rev-parse
  featureBranch` at phase start). The phase integration branch is **rebuilt
  idempotently** from `phaseBaseSha` each assembly — that rebuild *is* the
  conflict/crash rollback (never `git merge --abort`).
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
codex-review-<scope>.md      -- codex findings (bin/drive-codex.sh supervisor); codex-raw-<scope>.log raw.
                                A degraded leg's first line = CODEX_UNAVAILABLE | CODEX_KILLED_TIMEOUT
harden-<P>-N.md              -- per-phase harden audit (2-lens) outputs
codex-harden-<P>.md          -- codex harden findings; codex-harden-<P>.log raw
codex-raw-<scope>.killed-N.log / codex-harden-<P>.killed-N.log -- watchdog-killed codex raw logs,
                                quarantined on a CODEX_KILLED_TIMEOUT (Tier-L swept)
codex-attempts-<runId>.jsonl -- per-op codex-supervisor attempt log (KEEP; op = probe|dispatch|
                                kill|retry|degrade; effort tier + sandbox rung + model tier + max inter-append gap)
sandbox-spike-evidence.md    -- codex sandbox-rung spike evidence (phase-design precondition; READ-ONLY)
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
codex-refuted-<scope>.md     -- per-scope in-run refutation records (R7; replay +
                                review-enrichment surface)
codex-refutations-pending.md -- durable-qualifying refutations staged for ship promotion
                                (ids PROVISIONAL; promoted to .harness/codex-refutations.md)
verify-design-claims-*.md    -- R8 author claims transcripts (design/phase<P>; input-side,
                                rewritten in place on revision legs)
verify.md                    -- verify-stage evidence
wt/                          -- per-slice + integration + ship worktrees
```

The **committed** cross-task ledgers stay in the repo: `.harness/decisions.md`,
`.harness/followups.md`, `.harness/codex-refutations.md` (durable
codex-refutation adjudications). Read `.harness/decisions.md` at the start of a
task to stay consistent; the coordinator promotes a run's `$RUN_DIR` ledgers
into them at ship.
