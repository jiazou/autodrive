---
description: HARDEN stage (Stage 4.5) of /drive — per-phase quality-hardening pass that runs AFTER the phase-integration review converges. Find→fix→verify over the assembled phase to (1) reduce AI slop, (2) add missing tests, (3) fix logic bugs. Mutating, beyond acceptance criteria. Usually invoked by /drive.
argument-hint: phase <P> (within an existing run)
---
You are running the HARDEN stage (Stage 4.5) for **one phase**. Harness-owned — no
gstack skill. Unlike `/drive-review` (a PASSIVE conformance audit scoped to
acceptance criteria), HARDEN is a **mutating find→fix→verify loop** that hunts
quality defects **beyond** the spec. `/drive` invokes it once per phase, AFTER the
phase-integration review CONVERGED and BEFORE `featureBranch` advances, operating on
the assembled `phaseInt/<P>` worktree (so its commits land on that branch — the same
branch `featureBranch` will fast-forward to).

`/drive` passes: `phase <P>`, the absolute **`phaseInt/<P>` worktree path** (the
implementer subagent's cwd), `phaseBaseSha`, and `$RUN_DIR` (absolute). The phase's
spec lives in `$RUN_DIR/design.md` under `## Phases & Slices`.

The scope is the **assembled phase diff** `git diff <phaseBaseSha>..phaseInt/<P>` and
the files it touches — the "relevant codebase" for this phase. Derive it
authoritatively from git, never an ephemeral implementer list.

## Preconditions (non-decision STOPs)

This is a sub-stage of `/drive`, not a standalone tool — it hardens an assembled phase
*in flight*, so it needs that run's context. On invocation, bind and verify, in order;
**STOP with the stated message** (do not guess, fabricate a run, or harden an arbitrary
tree) if any fails:
- `<P>` = the phase number from `$ARGUMENTS` (the `phase <P>` argument). Missing/unparseable
  → STOP: "no phase given — usage: `/drive-harden phase <P>` within an active `/drive` run."
- `$RUN_DIR` is provided (by `/drive`) or inferable from a single in-progress run under
  `~/.claude/harness-runs/`. None, or only runs with `state.stage == "done"`/`"ship"` →
  STOP: "no active /drive run to harden — `/drive-harden` runs inside an in-flight run, after a phase review converges. Start one with `/drive <task>`."
- That run's `state.json` shows phase `<P>` `phaseReview[<P>].status == "converged"` (or
  `"hardening"` on resume). Not converged / not yet assembled → STOP: "phase <P> hasn't
  passed its integration review yet — harden runs only after `/drive-review phase <P>` converges."
- The `phaseInt/<P>` worktree exists (`git worktree list`) and `$RUN_DIR/design.md` is
  present. Missing → STOP naming what's absent (the run is mid-rebuild or corrupt; let
  `/drive` reconcile on resume).

When `/drive` invokes this stage it passes all of the above directly, so these checks
pass by construction; they exist for a bare/manual invocation.

## The three hardening lenses

1. **Reduce AI slop** (per OPERATING.md "No AI Slop"): speculative fallbacks,
   unnecessary `try/catch`, "just in case" defensive code, dead/unreachable code,
   over-abstraction, redundant narration comments, copy-paste duplication,
   inconsistent naming. **De-slop edits YIELD to conformance:** an edit that would
   drop coverage of any acceptance criterion is VETOED — log it to
   `$RUN_DIR/followups.md`, never make it (this is what stops de-slop ↔ conformance
   oscillation).
2. **Add missing tests**: acceptance criteria, branches, edge cases, and error paths
   with no test → add them. A test that guards a bug MUST **fail against the pre-fix
   code** (per OPERATING.md "a green test can pass for the wrong reason" — drive the
   real production wiring, not seeded/stubbed state).
3. **Fix logic issues & bugs**: off-by-one, wrong conditionals, unhandled
   null/empty, races, incorrect error handling, contract violations the conformance
   review missed.

## Loop counter & cap

`N` = this invocation's index = (count of existing `$RUN_DIR/harden-<P>-*.md`) + 1;
each invocation writes exactly one `harden-<P>-N.md`.

`hardenRound` counts **fix rounds only** — invocations that actually changed code. The
cap is **HARDEN_CAP = 3** fix rounds. A round that audits clean and applies nothing
(the confirming audit) is **free** — it does NOT increment `hardenRound`, so N fix
rounds don't need an N+1th to confirm clean. Harden therefore allows up to 3
code-changing rounds plus the final clean audit that declares HARDENED. If
`hardenRound >= HARDEN_CAP` AND this invocation's audit still has open P1 → STOP and
summarize what is open per lens (a flagged half-hardened phase beats a silent advance).

This counter is **independent of the conformance `phaseReview[<P>].round` (cap-8)**:
the Step-4 regression guard runs `/drive-review phase <P> harden-regress`, which by
contract does not touch `round` — so a phase whose integration already used 6–8
conformance rounds is not false-STOPped when harden re-reviews it.

Reconcile `hardenRound` from artifacts, not state alone (a crash can write
`harden-<P>-N.md` or land a `phaseInt/<P>` commit before the state write): on entry,
`hardenRound = max(state.phaseReview[<P>].hardenRound or 0, count of `harden-<P>-*.md`
with `AppliedEdits: yes`)`. The `AppliedEdits` line in each audit file (see Step 1
schema) is the machine-readable marker of a fix round; clean confirming audits carry
`AppliedEdits: no` and don't count.

## Scope-creep HARD GATE (not a guideline)

Bind every edit to the 6 Decision Principles' blast-radius + boil-lakes test as a
**gate**, not advice. The gate's purpose is to stop "fix logic bugs" from mutating
into "rewrite the codebase" — NOT to block correctness work the phase genuinely needs.
Allowed to edit:
- The files in `git diff <phaseBaseSha>..phaseInt/<P>` (the phase's own surface).
- New **test files** + existing **test-support** (fixtures, harnesses, snapshots)
  needed to cover those files — lens 2 legitimately adds and wires up tests.
- A file **just outside** the diff ONLY when it is the true root cause of a **flagged
  P1** in the phase and deferring would knowingly ship a broken phase. This widens
  scope, so **log it to `$RUN_DIR/decisions.md`** (Classification) and surface at
  Gate B. Never reach forward into another *unbuilt* phase's planned files.
Forbidden: any **refactor / taste edit without a flagged P1**, and editing unrelated
working code. A non-P1 improvement outside the diff → `$RUN_DIR/followups.md`, skip it.

## Step 1 — Audit (dual-voice, 3-lens)

Run the **same dual-voice mechanics as `/drive-review`** (a passive Claude reviewer
subagent + a direct codex pass over the same scope), but with the **harden 3-lens
prompt** below instead of the conformance prompt. CRITICAL BOUNDARY: pass PATHS +
git refs only — never any implementer's or harden-fixer's notes/rationale (preserves
the reviewer's independent judgment, exactly as conformance review does).

Spawn a generic reviewer subagent:

----- BEGIN SUBAGENT SCOPE -----
Audit `git diff <phaseBaseSha>..phaseInt/<P>` and the files it touches, against the
THREE hardening lenses (NOT just acceptance-criterion conformance):
1. AI slop — speculative fallbacks, needless try/catch, defensive "just in case"
   code, dead code, over-abstraction, redundant comments, copy-paste, inconsistent
   naming. For each, note whether removing it would drop an acceptance criterion's
   coverage (if so, mark VETOED — do not propose it).
2. Missing tests — acceptance criteria / branches / edge cases / error paths with no
   test. Name the exact case to cover.
3. Logic & bugs — off-by-one, wrong conditionals, unhandled null/empty, races, bad
   error handling, contract violations.
Spec + prior decisions: `$RUN_DIR/design.md`, `$RUN_DIR/decisions.md`.

Severity — pick one, don't ask:
- P1 (actionable this stage): a real bug (lens 3), or a missing test on an acceptance
  criterion / on a bug being fixed (lens 2).
- P2: slop worth removing (lens 1) or a missing test on a non-criterion path — fix
  only if cheap AND in the phase's blast radius; otherwise → followups.
- P3: cosmetic; → followups, never fix.
Out-of-phase / out-of-diff real bugs → `$RUN_DIR/followups.md`.

Write `$RUN_DIR/harden-<P>-N.md`:
  # Harden phase <P> N
  ## Verdict: HARDENED | FINDINGS
  ## AppliedEdits: pending          (Step 4 finalizes this to yes|no — the resume marker)
  ## Findings → ### [SEVERITY][LENS] Short title / **Where** file:line / Issue / Fix / Veto? 
HARDENED = no open P1 AND nothing cheap-P2 left to apply. Return: path, verdict, one-line count.
----- END SUBAGENT SCOPE -----

Codex pass (run DIRECTLY from main, background, per-scope log — NEVER inside a
subagent that waits on it):

```
codex exec "Harden phase <P>: review git diff <phaseBaseSha>..phaseInt/<P> for (1) AI
slop to remove, (2) missing tests to add (acceptance criteria, branches, edge/error
paths), (3) logic bugs. Flag P1 (real bug / missing test on a criterion) vs P2 (slop
/ non-criterion test gap) with file:line. Note any de-slop edit that would drop an
acceptance criterion (do not propose it). Prioritized." > $RUN_DIR/codex-harden-<P>.log 2>&1
```

run_in_background; wait for completion; then a bounded post-process subagent: "Read
`$RUN_DIR/codex-harden-<P>.log`, extract codex's final findings, write
`$RUN_DIR/codex-harden-<P>.md` (same severity/lens tags, <150 words)."

Degradation (do NOT hard-fail): codex missing OR hangs/times out → write
`codex-harden-<P>.md` = "codex unavailable — Claude-only harden" + warning; continue.

## Step 2 — Triage

Combine voices: both-flagged = high confidence; **codex-only = scrutinize hardest**
(bugs Claude missed); reviewer-only = claude-only. Build the fix set from:
- All open **P1** from this round's audit (lens 3 bugs + lens 2 criterion/bug tests).
- **Any P1 conformance regression** the prior round's Step-4 re-review left open
  (recorded in `$RUN_DIR/review-phase<P>-*.md` / state) — fold it in so a harden edit
  that dropped a criterion gets repaired, not lost.
- **P2** slop / non-criterion tests — only if cheap AND in the phase blast radius
  (6 principles); else → `$RUN_DIR/followups.md`.
- **P3** and **VETOED** de-slop → `$RUN_DIR/followups.md`, never apply.

If the fix set is empty (no open P1 from the audit, no outstanding regression, nothing
cheap-P2 left) → **HARDENED** (this is the free confirming round — return per Step 4,
do not increment `hardenRound`). Otherwise classify each kept item Mechanical / Taste /
User-Challenge (6 principles); Taste → log to `$RUN_DIR/decisions.md`, surface at
Gate B; User-Challenge → STOP and surface.

## Step 3 — Fix (implementer subagent, cwd = phaseInt worktree)

Spawn a generic implementer subagent with **cwd = the `phaseInt/<P>` worktree**. Pass
file PATHS + the harden + codex finding paths, never contents.

----- BEGIN SUBAGENT SCOPE -----
You are hardening phase <P>. Your cwd is its assembled integration worktree on branch
`phaseInt/<P>`. Code paths are relative to this worktree; artifact paths are the
absolute `$RUN_DIR` (never edit code via absolute paths to the main repo). Read:
- $RUN_DIR/design.md (acceptance criteria for the phase's slices)
- $RUN_DIR/decisions.md (stay consistent)
- $RUN_DIR/harden-<P>-N.md + codex-harden-<P>.md (the fix set; codex-only items live
  only in the codex file, so read it)

Apply ONLY the fix set, honoring the scope-creep HARD GATE (see above): the phase-diff
files; new test files + existing test-support (fixtures/harnesses/snapshots) for them;
and a file just outside the diff ONLY as the root cause of a flagged P1 (then append a
scope-widening note to `$RUN_DIR/decisions.md`). No refactor / taste edit without a
flagged P1 — a non-P1 improvement outside the diff → `$RUN_DIR/followups.md`, skip it.
- Lens 3 bugs: fix them; add a test that FAILS against the pre-fix code, then passes.
- Lens 2 gaps: add the named tests, driving real production wiring (not stubbed state).
- Lens 1 slop: remove it ONLY if it does not drop any acceptance criterion's coverage
  (if it would, append to followups and skip — VETOED).
Run the FULL build + integration tests until green. Commit to `phaseInt/<P>`
(`git add -A && git commit`) before returning.

Return STATUS as the FIRST line, then the changed-file list:
- `STATUS: DONE` — fix set applied, tests green, committed. List changed files (within
  the allowed scope above). "Flagged:" line for deviations / Taste / vetoed items / any
  scope-widening root-cause edit (also logged to `$RUN_DIR/decisions.md`).
- `STATUS: BLOCKED — <reason>` — non-decision blocker (env/tool/test failure you
  can't resolve). State it + what would unblock.
- `STATUS: NEEDS_CONTEXT — <question>` — a User-Challenge, or a needed fix is out of
  the allowed scope (another phase's files / can't be deferred). State the one question.
----- END SUBAGENT SCOPE -----

## Step 4 — Regression guard & converge

One round per invocation; `/drive` owns the loop. Decide the return per the cap rules
in **Loop counter & cap**, then finalize the round's `AppliedEdits` marker:

- **No fix applied this invocation** (Step-2 fix set was empty — the free confirming
  audit) → set `harden-<P>-N.md` `AppliedEdits: no` → return `HARDENED`.
- **A fix was applied** → `hardenRound += 1`; set `AppliedEdits: yes`. Re-run
  `/drive-review phase <P> harden-regress` as the regression guard (catches a
  conformance break the tests can't — e.g. a de-slop edit that dropped a criterion).
  Any P1 it finds is folded into the next round's fix set. Return `FINDINGS` (the next
  invocation re-audits; a subsequent clean audit returns HARDENED).
- **`hardenRound >= HARDEN_CAP` and this audit still has open P1** → return `STOP`.

Record `phaseReview[<P>].hardenRound` to `$RUN_DIR/state.json` each invocation.
`/drive` sets `phaseReview[<P>].status = hardened` on the `HARDENED` return.

## Return contract to /drive

- `HARDENED` — audit clean + conformance still converged. `/drive` advances
  `featureBranch` to `phaseInt/<P>`, removes the worktree, deletes slice branches,
  proceeds to the next phase.
- `FINDINGS` — still looping (a fix round ran; not yet clean). `/drive` re-invokes
  HARDEN for this phase (the loop owns its cap of 3 fix rounds).
- `STOP — <reason>` — cap exceeded, BLOCKED, or NEEDS_CONTEXT. Surface; the phase does
  NOT advance until resolved.

Budget: increment `state.budget.calls` per harden subagent/codex dispatch; if a
ceiling is set and exceeded → STOP with a spend summary (the half-hardened phase is
left on `phaseInt/<P>` for inspection — see /drive resume).

Never include the harden-implementer's notes/rationale in any audit or review prompt.
