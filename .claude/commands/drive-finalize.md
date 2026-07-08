---
description: FINALIZE stage (Stage 4c) of /drive — the end-of-run AGGREGATE hardening pass over the WHOLE-RUN diff (baseRef..featureBranch), run ONCE after all phases hardened and BEFORE Verify. Leads with de-slop (moved out of per-phase harden), plus a whole-run logic-bug + missing-test sweep; routes architectural findings to the driven project's TODO. Emits the ship-gate's terminal SHA-bound review artifact. Usually invoked by /drive.
argument-hint: (operates on the run's featureBranch; no phase arg)
---
You are running the FINALIZE stage (Stage 4c) — the **end-of-run aggregate quality
pass** over the WHOLE run. Harness-owned — no gstack skill. It is the dual to
`/drive-harden`: harden is per-phase and correctness-only; FINALIZE is run-singleton,
runs ONCE over the whole-run diff, and **LEADS with de-slop** (the lens harden defers to
here), then sweeps for aggregate logic bugs + missing tests that surface only once all
phases are assembled. It runs AFTER every phase reached `hardened` and BEFORE Verify
(Stage 4b). It emits the **terminal SHA-bound review artifact the ship gate consumes**.

## Invocation & arguments

`/drive` invokes `/drive-finalize` **ONCE, with no phase argument** (run-singleton).
`/drive` passes (as drive-harden.md passes its set): `<runId>`, `$RUN_DIR` (absolute),
`baseRef`, `featureBranch`, and the absolute path of a dedicated **finalize worktree**
`$RUN_DIR/wt/finalize` checked out at `featureBranch` (created by `/drive`; this spec
assumes cwd = that worktree, the same way drive-harden.md assumes the `phaseInt`
worktree). The stage's edits commit to `featureBranch` directly there. The high-level
context is `$RUN_DIR/design.md`; per-phase acceptance criteria live in
`$RUN_DIR/design-phase<P>.md`; prior decisions in `$RUN_DIR/decisions.md`.

> Working-tree precondition for Phase 2 (stated, not implemented here): finalize runs
> AFTER the last phase advanced, so `featureBranch` is checked out in NO phase worktree
> and is free to be checked out in `$RUN_DIR/wt/finalize`; finalize's commits land on it
> directly. This is a self-contained terminal stage (no further `branch -f` advance), so
> a checked-out `featureBranch` is correct here.

## Preconditions (non-decision STOPs)

This is a sub-stage of `/drive`, run in flight; it needs that run's context. On
invocation, bind and verify, in order; **STOP with the stated message** if any fails:
- `$RUN_DIR` is provided (by `/drive`) or inferable from a single in-progress run under
  `~/.claude/harness-runs/`. None, or only runs with `state.stage == "done"`/`"ship"` →
  STOP: "no active /drive run to finalize — `/drive-finalize` runs inside an in-flight
  run, after ALL phases hardened. Start one with `/drive <task>`."
- That run's `state.json` shows EVERY phase `phaseReview[<P>].status == "hardened"` (or
  finalize was already in flight). A phase not yet hardened → STOP: "phase <P> isn't
  hardened — finalize runs only after all phases harden."
- The `$RUN_DIR/wt/finalize` worktree exists (`git worktree list`) on `featureBranch`.
  Missing → STOP naming what's absent (let `/drive` reconcile on resume).

When `/drive` invokes this stage it passes all of the above directly, so these checks
pass by construction; they exist for a bare/manual invocation.

## Scope (READ vs EDIT)

- **Diff scope (the logic to harden)** = `git diff <baseRef>..<featureBranch>` — the whole
  run's added logic. Derive it authoritatively from git, never an implementer list.
- **Read context** = the whole driven codebase (for aggregate awareness — duplication
  across phases, a slop pattern repeated run-wide). READ-only.

## Scope-creep HARD GATE (not a guideline — IDENTICAL discipline to drive-harden.md, D3)

Bind every edit to the 6 Decision Principles' blast-radius + boil-lakes test as a
**gate**, not advice. Its purpose is to stop "de-slop / fix bugs" from mutating into
"rewrite the user's codebase" — `/drive` builds a feature; it must NOT rewrite untouched
pre-existing user code, no matter how much was READ. Allowed to edit:
- The files in `git diff <baseRef>..<featureBranch>` (the run's own surface).
- New **test files** + existing **test-support** (fixtures, harnesses, snapshots) needed
  to cover those files.
- A file **just outside** the diff ONLY when it is the true root cause of a **flagged
  P1** and deferring would knowingly ship a broken run. This widens scope, so **log it to
  `$RUN_DIR/decisions.md`** (Classification) and surface at Gate B.
Forbidden: any **refactor / taste edit without a flagged P1**, and editing untouched user
code. A non-P1 improvement outside the diff → `$RUN_DIR/followups.md`, skip it. A
cross-phase slop pattern that recurs in untouched user code is recorded to
followups/TODO, not edited.

## The three lenses (DE-SLOP LED)

1. **De-slop (LED here)** — remove AI slop across the WHOLE-RUN diff: speculative
   fallbacks, needless `try/catch`, defensive "just in case" code, dead/unreachable code,
   over-abstraction, redundant narration comments, copy-paste duplication (now visible
   across phases), inconsistent naming. **De-slop MUST be behavior-preserving:** a de-slop
   edit that reds a test is a REAL REGRESSION → **REVERT** that edit; do NOT reconcile it
   by changing the test (the Step-4 regression-guard rule). **The source of truth for
   "what slop is APPLICABLE this round" is THIS round's own AUDIT of the run-diff CODE**
   (`git diff <baseRef>..<featureBranch>`): each round re-scans the actual code for
   remaining slop, and the round's de-slop fix set is the CHEAP IN-SCOPE slop the audit
   finds STILL PRESENT in the current code (6-principles blast-radius + boil-lakes gate).
   Slop the audit confirms is present but is NON-cheap or OUT-of-scope is **deferred to
   `$RUN_DIR/followups.md`** (Step 2's routing) and is **EXPLICITLY NON-BLOCKING** — it
   stays in the code and does NOT keep the round from converging (mirrors how harden's
   non-cheap P2 → followups doesn't block HARDENED). So convergence keys on the APPLICABLE
   set being empty, NOT on "no slop anywhere in the code." **Seed the audit's lens-1
   candidate scan from `$RUN_DIR/followups.md`'s
   `## slop (deferred to finalize)` section** (the per-phase harden deferred-slop handoff,
   one line per item as `file:line — description`) so harden's pre-identified spots aren't
   missed — but these notes are a best-effort SEED, NOT a standing fix set: an item is
   fixed only if the audit confirms the slop is still in the code. Because followups.md is
   APPEND-ONLY, finalize does NOT drain or mutate it; convergence does NOT depend on that
   section being empty. An already-applied deferred-slop edit will not reappear (the code no
   longer has that slop), so a stale line there is harmless — it is not the convergence
   signal; the code re-audit is. (The seed heading string must match harden's canonical
   `## slop (deferred to finalize)` EXACTLY.) A
   de-slop edit that would drop coverage of any acceptance criterion (ANY phase's) is
   **VETOED** → `$RUN_DIR/followups.md`, never made (convergence is not blocked by a vetoed
   item — it is logged, not a P1).
2. **Aggregate missing tests** — test gaps that surface only once all phases are assembled
   (cross-phase integration paths, an end-to-end criterion no single phase's tests
   covered). A test that guards a bug MUST **fail against the pre-fix code**.
3. **Aggregate logic bugs** — cross-phase contract violations, integration bugs,
   off-by-one / null-empty / race issues visible only in the assembled whole.

## Architectural findings → durable `$RUN_DIR/finalize-todo.md` (D4/D10 — NOT fixed in-run)

A MAJOR architectural problem (wrong responsibility boundary, a design smell spanning
phases) is **NOT fixed here** (out of the run's blast radius). Finalize **APPENDS** it to
`$RUN_DIR/finalize-todo.md` under a dated heading
`## /drive run <runId> — architectural follow-ups (<iso>)`, one bullet per finding
(`file:area` + the problem + why it's out of scope for this run).

**Why `$RUN_DIR`, not a finalize working-tree `TODO.md`:** finalize runs in
`$RUN_DIR/wt/finalize`; the ship stage runs in the SEPARATE `$RUN_DIR/wt/ship` worktree
built from the branch tip, so an UNCOMMITTED `wt/finalize/TODO.md` would be invisible to
ship and lost before Gate B. `$RUN_DIR` is absolute and reachable from every worktree, so
the finding survives. **finalize NEVER writes or commits any project `TODO.md`** (no
`wt/finalize/TODO.md`); because `finalize-todo.md` lives OUTSIDE the worktree, Step-3's
`git add -A` does not pick it up. If there are NO architectural findings,
`finalize-todo.md` is **not created** (no empty-heading stub). The ship stage (Phase 2)
promotes `$RUN_DIR/finalize-todo.md` → the driven project's repo-root `TODO.md` and
surfaces it at Gate B (see the Phase-2 obligations note at the end).

## Loop counter & cap

`N` = (count of existing `$RUN_DIR/review-finalize-*.md` with pure-integer N) + 1; each
invocation writes exactly one `review-finalize-N.md`.

`finalizeRound` counts **fix rounds only** — invocations that actually changed code. The
cap is **FINALIZE_CAP = 3** fix rounds. A round that audits clean and applies nothing
(the confirming audit) is **free** — it does NOT increment `finalizeRound`. If
`finalizeRound >= FINALIZE_CAP` AND this invocation's audit still has open P1 → return
`STOP` and summarize what is open per lens (a flagged half-finalized run beats a silent
ship).

Reconcile `finalizeRound` from artifacts on entry, not state alone (a crash can write
`review-finalize-N.md` or land a `featureBranch` commit before the state write):
`finalizeRound = max(state.finalizeRound or 0, count of review-finalize-*.md whose
dual-voice round APPLIED edits)`.

> Counter marker (parallels harden's `AppliedEdits` line). Each `review-finalize-N.md`
> carries an `## AppliedEdits: yes|no|pending` line (Step 4 finalizes it): `yes` = a fix
> round (increments `finalizeRound`), `no` = the free confirming clean audit. Reconcile
> from these markers, not state alone. NOTE the artifact-family difference Phase 2 must
> honor: harden's checkpoint reconstruction scans `harden-*.md`, but finalize's marker
> lives in `review-finalize-*.md` — so Phase 2's `finalizeRound` reconstruction scans the
> `review-finalize-*.md` family for `## AppliedEdits: yes` (NOT the harden loop). This is
> one of the explicit Phase-2 checkpoint obligations (see the note at the end).

## Step 1 — Audit (dual-voice, 3-lens)

Run the **same dual-voice mechanics as `/drive-review`** (a passive Claude reviewer
subagent + a direct codex pass over the same scope), with the finalize 3-lens prompt
below. CRITICAL BOUNDARY: pass PATHS + git refs only — never any implementer's or
finalizer's notes/rationale (preserves the reviewer's independent judgment).

Spawn a generic reviewer subagent:

----- BEGIN SUBAGENT SCOPE -----
Audit `git diff <baseRef>..<featureBranch>` (the whole run's added logic) against the
THREE finalize lenses, reading the whole driven codebase for aggregate context but
flagging EDITS only within the edit scope (run diff + test-support + a flagged-P1 root
cause just outside it):
1. AI slop (LED) — the source of truth is YOUR AUDIT of the run-diff CODE: SCAN the run
   diff (`git diff <baseRef>..<featureBranch>`) for slop STILL PRESENT in the current code:
   speculative fallbacks, needless try/catch, defensive "just in case" code, dead code,
   over-abstraction, redundant comments, copy-paste (now visible across phases),
   inconsistent naming. SEED the candidate scan from `$RUN_DIR/followups.md`'s
   `## slop (deferred to finalize)` section (the per-phase harden passes' deferred-slop
   notes, one line per item as `file:line — description`) so harden's pre-identified spots
   aren't missed — but only flag a seeded item if the audit confirms the slop is still in
   the code (an already-applied note whose slop is gone is NOT a finding). For each, note
   whether removing it would drop an acceptance criterion's coverage (if so, mark VETOED —
   do not propose it).
2. Aggregate missing tests — cross-phase integration paths / end-to-end criteria no
   single phase's tests covered. Name the exact case to cover.
3. Aggregate logic bugs — cross-phase contract violations, integration bugs, off-by-one /
   null-empty / race issues visible only in the assembled whole.
Spec + prior decisions: each phase's `$RUN_DIR/design-phase<P>.md` (acceptance criteria),
`$RUN_DIR/design.md` (high-level context), `$RUN_DIR/decisions.md`. Deferred-slop SEED:
`$RUN_DIR/followups.md` — read its `## slop (deferred to finalize)` section (the
per-phase harden handoff) to seed lens 1's candidate scan (see lens 1 above); it is a
best-effort seed, not a fix set — the run-diff code audit decides what is still slop.

Severity — pick one, don't ask:
- P1 (actionable this stage): a real aggregate bug (lens 3), or a missing test on an
  acceptance criterion / on a bug being fixed (lens 2).
- P2: slop worth removing (lens 1, the LED lens — so finalize DOES apply cheap in-scope
  P2 slop, unlike narrowed harden) or a non-criterion test gap (the test gap is logged to
  `$RUN_DIR/followups.md`, not fixed in-run).
- P3: cosmetic; → followups, never fix.
Architectural findings → flag as `ARCH` (routed to TODO, not a code fix). Out-of-scope
real bugs → `$RUN_DIR/followups.md`.

Write `$RUN_DIR/review-finalize-N.md`:
  # Finalize N
  ## Verdict: CONVERGED | FINDINGS
  ## AppliedEdits: pending          (Step 4 finalizes this to yes|no — the resume marker)
  reviewed-sha: <40-hex>            (EXACTLY ONE such line; Step 4 REPLACES it in place)
  ## Findings → ### [SEVERITY][LENS] title / **Where** file:line / Issue / Fix / Veto?
  ## Architectural (→ TODO) → ### file:area / problem / why deferred
CONVERGED = no open P1 AND no cheap in-scope P2 slop left to apply. Return: path,
verdict, one-line count.
----- END SUBAGENT SCOPE -----

**`reviewed-sha:` binding (LOAD-BEARING — the ship gate reads this).** Each
`review-finalize-N.md` carries **EXACTLY ONE** `^reviewed-sha:` line = `git rev-parse
<featureBranch>` **AS OF THE END OF THIS AUDIT ROUND** — i.e. AFTER Step-3's fix commit for
THIS round (the post-edit tip); for the free confirming clean audit it is the unchanged
tip. When Step 4 updates it, it **REPLACES that single line IN PLACE — it MUST NOT append a
second `reviewed-sha:` line** (the conformance helper `reviewed_sha_of()` reads the FIRST
matching line, so an appended post-fix sha would be shadowed by a stale Step-1 first line
and the ship gate would bind the wrong tip). The terminal CONVERGED `review-finalize-N.md`
therefore binds the FINAL post-de-slop `featureBranch` tip — exactly what the ship gate
needs (R == tip, so `R..tip` is empty ⊆ the ledger allowlist). This is the SAME mechanism
as harden-regress's "re-emit reviewed-sha at the post-fix tip" rule (drive-review.md
§ phase). Emit **lowercase 40-hex** (conformance lowercases, but emit lowercase).

Codex pass (run DIRECTLY from main, background, per-scope log — NEVER inside a subagent
that waits on it):

```
codex exec "Finalize (aggregate harden) the run: review git diff <baseRef>..<featureBranch> for (1) AI slop to REMOVE across the whole run diff (de-slop, behavior-preserving), (2) aggregate missing tests (cross-phase / end-to-end criteria), (3) aggregate logic bugs (cross-phase contract/integration). Flag P1 (real bug / missing criterion test) vs P2 (slop / non-criterion test) with file:line. List any MAJOR architectural problem separately as ARCH (do not propose fixing it in-run). Note any de-slop edit that would red a test or drop a criterion (do not propose it). Prioritized." > $RUN_DIR/codex-raw-finalize.log 2>&1
```

run_in_background; wait for completion; then a bounded post-process subagent: "Read
`$RUN_DIR/codex-raw-finalize.log`, extract codex's final findings, write
`$RUN_DIR/codex-review-finalize.md` (same severity/lens tags, <150 words)."

Degradation (do NOT hard-fail): codex missing OR hangs/times out → write
`codex-review-finalize.md` whose FIRST line is the bare token `CODEX_UNAVAILABLE` (the
same convention as drive-review.md / drive-harden.md, so the run-graph's codex-n/a
detection is uniform), optionally a note on later lines; continue. The conformance
`codex_present` check inspects existence + non-emptiness only — any non-empty file
satisfies it.

## Step 2 — Triage

Combine voices: both-flagged = high confidence; **codex-only = scrutinize hardest** (bugs
Claude missed); reviewer-only = claude-only. The round's de-slop fix set (the APPLICABLE
set) is keyed on THIS round's AUDIT of the current code, NOT on the followups ledger. Build
the fix set from:
- All open **P1** from this round's audit (lens 2 criterion/bug tests + lens 3 bugs).
- **Cheap in-scope P2 slop the audit finds STILL PRESENT in the current code** — lens-1
  slop (the LED lens) that is cheap AND within the run's blast radius (6 principles):
  applied HERE, not deferred (finalize APPLIES cheap in-scope slop, unlike harden). The
  audit's candidate scan was seeded by the followups `## slop (deferred to finalize)`
  notes, but an item enters the fix set only when the audit confirms the slop is still in
  the code. Same lens-1 rules: behavior-preserving, scope-gated, VETO if it would drop any
  acceptance criterion's coverage. NON-cheap or out-of-scope slop the audit confirms is
  present is NOT in the fix set — it is routed to followups (below) and is non-blocking.
- **Any P1 regression** the prior round's Step-4 guard left open.
**No finding class is silently dropped.** Every finding has a destination:
- **P1** (lens 2 criterion/bug tests + lens 3 bugs) → fix set.
- **Cheap in-scope P2 slop** → fix set (above).
- **Non-criterion test gaps (P2) + non-cheap / out-of-scope P2 / P3** → `$RUN_DIR/followups.md`
  (exactly as drive-harden.md routes non-criterion / non-cheap findings) — logged, never
  silently dropped; convergence is not blocked by them.
- **VETOED** (a de-slop edit that would drop a criterion) → `$RUN_DIR/followups.md`.
- **ARCH** (MAJOR architectural problems) → `$RUN_DIR/finalize-todo.md`.

The fix set Step 2 builds here is EXACTLY what Step 3 applies: the open P1s and the
audit-confirmed CHEAP IN-SCOPE run-diff slop (the APPLICABLE set). Finalize does NOT drain
or mutate `followups.md` (it is an APPEND-ONLY ledger); a stale already-applied
deferred-slop line there is harmless because it is NOT the convergence signal — the code
re-audit is. An already-applied edit will not reappear (the code no longer has that slop),
so the applicable fix set naturally empties.

If the APPLICABLE fix set is empty — no open P1, and no cheap in-scope slop the audit finds
still present in the code (any remaining slop the audit sees is non-cheap/out-of-scope and
was routed to followups) → **CONVERGED** (the free confirming round — return per Step 4, do
not increment `finalizeRound`). CONVERGED is the applicable set being empty, NOT "no slop
anywhere in the code": slop deferred to followups does NOT block convergence (mirrors how
harden's non-cheap P2 → followups doesn't block HARDENED). Convergence does NOT depend on
the followups section being empty. Otherwise classify
each kept item Mechanical / Taste / User-Challenge (6 principles); Taste → log to
`$RUN_DIR/decisions.md`, surface at Gate B; User-Challenge → STOP and surface.

## Step 3 — Fix (implementer subagent, cwd = finalize worktree)

Spawn a generic implementer subagent with **cwd = `$RUN_DIR/wt/finalize`**. Pass file
PATHS + the finalize + codex finding paths, never contents.

----- BEGIN SUBAGENT SCOPE -----
You are finalizing the run. Your cwd is the finalize worktree on branch `featureBranch`.
Code paths are relative to this worktree; artifact paths are the absolute `$RUN_DIR`
(never edit code via absolute paths to the main repo). Read:
- $RUN_DIR/design-phase<P>.md for each phase (acceptance criteria)
- $RUN_DIR/design.md (high-level context), $RUN_DIR/decisions.md (stay consistent)
- $RUN_DIR/followups.md — its `## slop (deferred to finalize)` section: the per-phase
  harden deferred-slop notes (`file:line — description`). These SEED the audit; they are
  NOT a standing fix set. Apply a lens-1 item only when this round's audit
  (`review-finalize-N.md`) confirms the slop is still in the code — behavior-preserving and
  within the scope-creep gate. Do NOT re-apply notes whose slop is already gone, and do NOT
  drain or edit followups.md (it is append-only).
- $RUN_DIR/review-finalize-N.md + codex-review-finalize.md (the fix set; codex-only items
  live only in the codex file, so read it)

Apply ONLY the fix set, honoring the scope-creep HARD GATE (see above): the run-diff
files; new test files + existing test-support for them; and a file just outside the diff
ONLY as the root cause of a flagged P1 (then append a scope-widening note to
`$RUN_DIR/decisions.md`). No refactor / taste edit without a flagged P1 — a non-P1
improvement outside the diff → `$RUN_DIR/followups.md`, skip it.
- Lens 1 de-slop: remove the slop the audit found STILL PRESENT in the code (its candidate
  scan was seeded by the `## slop (deferred to finalize)` notes, but apply an item only
  when the slop is actually still in the code) — **behavior-preserving only**, and ONLY if
  it does not drop any acceptance criterion's coverage (if it would, append to followups
  and skip — VETOED).
- Lens 3 bugs: fix them; add a test that FAILS against the pre-fix code, then passes.
- Lens 2 gaps: add the named tests, driving real production wiring (not stubbed state).
Do NOT create any `TODO.md` — architectural findings go to the durable
`$RUN_DIR/finalize-todo.md` OUTSIDE the worktree (the ship stage materializes the driven
`TODO.md`), so `git add -A` does not touch it.
Run the **driven project's FULL test suite** (not one phase's tests) until green — via
**`bin/run-tests.sh`** (the canonical runner: `python3 -m pytest tests/` AND every
`test/*.test.sh`, all suites, no early-exit); do NOT hand-pick a subset. Commit
to `featureBranch` (`git add -A && git commit`) before returning.

Return STATUS as the FIRST line, then the changed-file list:
- `STATUS: DONE` — fix set applied, full suite green, committed. List changed files
  (within the allowed scope). "Flagged:" line for deviations / Taste / vetoed items /
  ARCH items / any scope-widening root-cause edit (also logged to `$RUN_DIR/decisions.md`).
- `STATUS: BLOCKED — <reason>` — non-decision blocker (env/tool/test failure you can't
  resolve). State it + what would unblock.
- `STATUS: NEEDS_CONTEXT — <question>` — a User-Challenge, or a needed fix is out of the
  allowed scope. State the one question.
----- END SUBAGENT SCOPE -----

## Step 4 — Regression guard & converge

One round per invocation; `/drive` owns the loop. Decide the return per the cap rules in
**Loop counter & cap**, then finalize the round's `AppliedEdits` marker and update the
single `reviewed-sha:` line **IN PLACE** (REPLACE it — never append a second one; see the
`reviewed-sha:` binding note for why a second line would shadow the post-fix tip):

- **No fix applied this invocation** (Step-2 fix set was empty — the free confirming
  audit) → set `review-finalize-N.md` `AppliedEdits: no`, leave the single `reviewed-sha:`
  line at the unchanged `git rev-parse <featureBranch>` tip → return `CONVERGED`.
- **A fix was applied** → `finalizeRound += 1`; set `AppliedEdits: yes`; REPLACE the single
  `reviewed-sha:` line with the POST-fix tip (Step-1 binding). Run the **driven project's FULL
  suite** (`bin/run-tests.sh` — pytest + every `test/*.test.sh`) as the regression guard: **a reddened test from a de-slop edit is a REAL
  REGRESSION → REVERT the offending edit (do NOT reconcile by editing the test)**, re-run,
  and fold any still-open P1 into the next round's fix set. Return `FINDINGS` (the next
  invocation re-audits; a subsequent clean audit returns CONVERGED).
- **`finalizeRound >= FINALIZE_CAP` and this audit still has open P1** → return `STOP`.

Record `state.finalizeRound` to `$RUN_DIR/state.json` each invocation (Phase 2 owns the
field). On `CONVERGED`, `/drive` marks the stage done and proceeds to Verify (Phase 2
wires the Stage-4c→Verify transition).

## Return contract to /drive

- `CONVERGED` — audit clean + full suite green + the terminal `review-finalize-N.md` binds
  the current `featureBranch` tip. `/drive` proceeds to Verify (Stage 4b).
- `FINDINGS` — a fix round ran, not yet clean. `/drive` re-invokes `/drive-finalize` (the
  loop owns its cap of 3 fix rounds).
- `STOP — <reason>` — cap exceeded / BLOCKED / NEEDS_CONTEXT. Surface; the run does NOT
  ship (a terminal FINDINGS leaves the ship gate's finalize existential R absent → ship
  blocks; omission and non-convergence both fail closed at ship).

Budget: increment `state.budget.calls` per finalize subagent/codex dispatch; if a ceiling
is set and exceeded → STOP with a spend summary.

Never include the finalize-implementer's notes/rationale in any audit or review prompt.

## Phase-2 wiring obligations (this spec's contract — NOT built here)

The finalize contract above is self-contained, but the following wiring (drive.md,
drive-ship.md, `bin/drive-conformance.sh`, CLAUDE.md) is **Phase 2's** job; this spec
DEPENDS on each being honored:

1. **Ship-mode terminal R.** `--mode ship`'s terminal existential R becomes the finalize
   artifact's `reviewed-sha` (the phase-integration existential is demoted to a
   precondition). Finalize's code commits MOVE the tip past every phase review's
   `reviewed-sha`, so the finalize artifact is the ONLY review whose `reviewed-sha ==
   post-finalize tip`. Phase 2 amends the candidate scan to collect the `finalize` scope's
   R via the existing `highest_review_file`/`reviewed_sha_of`/`codex_present` helpers (the
   `finalize` artifacts reuse `review-<scope>-N.md` naming verbatim, so the helpers work
   UNMODIFIED) — and the `finalize` scope does NOT match the existing `review-phase*` glob,
   so it is added as a SEPARATE, EXPLICIT candidate-R source — applying the IDENTICAL
   (a)(b)(c) ancestor/allowlist/≤1-commit test.
2. **Checkpoint scope-classifier (MANDATORY — else the checkpoint proof BREAKS) [AC16].**
   The `--mode checkpoint`/`--mode state-lint` scope-classifier (`bin/drive-conformance.sh`,
   the `case "$scope"` over `review-*.md`) buckets every scope that is not
   `design`/`phasedesign?*`/`phase?*` as a **slice key**. A `review-finalize-N.md` would
   thus become a PHANTOM slice `finalize` whose `slice/<runId>/finalize` branch does not
   resolve → checkpoint violation, failing closed on every rebirth/handoff once finalize
   has run. Phase 2 MUST add an explicit `(finalize)` case to that classifier so `finalize`
   is NOT treated as a slice.
3. **`finalizeRound` reconstruction (6th counter) [AC16].** Phase 2 adds `finalizeRound`
   to the checkpoint `counters` output + drive.md's resume counter-reconstruction rules,
   derived artifact-side as `count of review-finalize-*.md with ## AppliedEdits: yes`
   (mirrors the harden `AppliedEdits: yes` rule — note it scans the `review-finalize-*.md`
   family, NOT the harden loop). `state.finalizeRound` is a resume HINT only (one-directional
   max with the artifact value), never a proof input — same discipline as the five existing
   counters.
4. **Run-graph node.** Phase 2 adds a Finalize node to drive.md's run-graph (its glyph from
   `state.finalizeRound` / the `review-finalize-*` + codex sibling dual-voice rule),
   rendered between the last phase and Verify.
5. **Ship TODO promotion + allowlist [AC17].** drive-ship.md promotes
   `$RUN_DIR/finalize-todo.md` → repo-root `TODO.md` within its single ledger-promotion
   commit; `SHIP_LEDGER_ALLOWLIST` is EXTENDED to include `TODO.md` (so the one ship commit
   touching {`.harness/decisions.md`, `.harness/followups.md`, `TODO.md`} stays ≤1 commit ⊆
   allowlist); Gate B surfaces it from the durable `$RUN_DIR` copy. drive-ship.md's
   remediation prose moves off "rerun the final phase review" onto "re-run `/drive-finalize`
   so its reviewed-sha covers the shipped tip." If `finalize-todo.md` is absent (no
   architectural findings), ship promotes nothing and `TODO.md` is untouched.
