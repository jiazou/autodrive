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

`N = state.phaseReview[<P>].hardenRound + 1` (fall back to counting
`$RUN_DIR/harden-<P>-*.md` + 1 if state is absent). The harden loop has its **own**
cap — **HARDEN_CAP = 3** — separate from the conformance review's cap-8. Quality
hardening should converge fast; if N > 3 → STOP, summarize what is still open per
lens, and surface (do NOT advance the phase silently — a phase left half-hardened is
worse than a flagged STOP). Rationale: the harden P1 fix-set is small (real bugs are
few); a tight cap fails fast instead of grinding.

## Scope-creep HARD GATE (not a guideline)

Bind every edit to the 6 Decision Principles' blast-radius + boil-lakes test as a
**gate**, not advice:
- **Only touch the phase's own surface:** the files in `git diff
  <phaseBaseSha>..phaseInt/<P>`, PLUS new **test files** that cover those files (lens
  2 legitimately adds new tests). Never edit a file this phase didn't build — that's
  another phase's or out of scope.
- **No refactor without a flagged P1.** Don't rewrite working code for taste.
- A bug whose fix needs editing files OUTSIDE the phase diff → `$RUN_DIR/followups.md`,
  do NOT reach forward into another phase.
This gate is the guard against "fix logic bugs" mutating into "rewrite the codebase."

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
(bugs Claude missed); reviewer-only = claude-only. Build the fix set:
- All open **P1** (lens 3 bugs + lens 2 criterion/bug tests) → fix.
- **P2** slop / non-criterion tests → fix only if cheap AND in the phase blast radius
  (6 principles); else → `$RUN_DIR/followups.md`.
- **P3** and **VETOED** de-slop → `$RUN_DIR/followups.md`, never apply.

If the fix set is empty AND no regression is outstanding from a prior round →
**HARDENED** (skip to the return contract). Classify each kept item Mechanical /
Taste / User-Challenge (6 principles); Taste → log to `$RUN_DIR/decisions.md`, surface
at Gate B; User-Challenge → STOP and surface.

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

Apply ONLY the fix set, honoring the scope-creep HARD GATE: touch only files already in
`git diff <phaseBaseSha>..phaseInt/<P>` PLUS new test files covering them; no refactor
without a flagged P1; a fix that needs editing a file outside the phase diff → append it
to `$RUN_DIR/followups.md` and skip it.
- Lens 3 bugs: fix them; add a test that FAILS against the pre-fix code, then passes.
- Lens 2 gaps: add the named tests, driving real production wiring (not stubbed state).
- Lens 1 slop: remove it ONLY if it does not drop any acceptance criterion's coverage
  (if it would, append to followups and skip — VETOED).
Run the FULL build + integration tests until green. Commit to `phaseInt/<P>`
(`git add -A && git commit`) before returning.

Return STATUS as the FIRST line, then the changed-file list:
- `STATUS: DONE` — fix set applied, tests green, committed. List changed files (all
  within the phase diff). "Flagged:" line for deviations / Taste / vetoed items.
- `STATUS: BLOCKED — <reason>` — non-decision blocker (env/tool/test failure you
  can't resolve). State it + what would unblock.
- `STATUS: NEEDS_CONTEXT — <question>` — a User-Challenge, or a fix needs files
  outside the phase diff that can't be deferred. State the one question.
----- END SUBAGENT SCOPE -----

## Step 4 — Regression guard & converge

This stage runs **one round per invocation** (like `/drive-review`); `/drive` owns
the loop and re-invokes on `FINDINGS`. On entry, if `N > HARDEN_CAP` → return `STOP`
(not converging; summarize what is open per lens).

If Step 3 **changed code**, re-run `/drive-review phase <P>` (the conformance
dual-voice review) on the now-hardened `phaseInt/<P>`. This is NOT redundant with the
full test run: tests don't encode spec conformance, and a de-slop edit can pass every
test yet drop an acceptance criterion. The re-review gets PATHS + refs only (reviewer
boundary). Because the harden loop caps at 3, this adds ≤3 to the phase's conformance
counter — comfortably under its own cap-8.
- Conformance **FINDINGS** (a P1 regression introduced by harden) OR the Step-1 audit
  had open P1 → this round did work but isn't clean → return `FINDINGS` (`/drive`
  re-invokes; the next round folds these into the fix set).
- Conformance **CONVERGED** AND the Step-1 audit returned HARDENED (no open P1, no
  cheap-P2 left) → return `HARDENED`.

Record to `$RUN_DIR/state.json` each invocation: `phaseReview[<P>].hardenRound = N`;
on `HARDENED`, `phaseReview[<P>].hardened = true`.

## Return contract to /drive

- `HARDENED` — audit clean + conformance still converged. `/drive` advances
  `featureBranch` to `phaseInt/<P>`, removes the worktree, deletes slice branches,
  proceeds to the next phase.
- `FINDINGS` — still looping (a fix round ran; not yet clean). `/drive` re-invokes
  HARDEN for this phase (the loop owns its cap-3).
- `STOP — <reason>` — cap exceeded, BLOCKED, or NEEDS_CONTEXT. Surface; the phase does
  NOT advance until resolved.

Budget: increment `state.budget.calls` per harden subagent/codex dispatch; if a
ceiling is set and exceeded → STOP with a spend summary (the half-hardened phase is
left on `phaseInt/<P>` for inspection — see /drive resume).

Never include the harden-implementer's notes/rationale in any audit or review prompt.
