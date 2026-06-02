You are running the REVIEW stage (Stage 3) — the harness's **dual-voice review
primitive**. It does NOT call gstack `/review` (fix-first, mutates code). It runs
a passive Claude reviewer AND a direct codex pass over the SAME scope, then
combines them. `/drive` (or `/plan`) invokes it with a **scope**:

- `design` — review `.harness/design.md` itself, before Gate A: buildable
  interfaces, testable acceptance criteria, and a sound `## Phases & Slices`
  breakdown (no slice dependency cycle; parallel slices own disjoint files).
- `slice <id>` — review that slice's diff against that slice's acceptance criteria
  (owned files only).
- `phase <P>` — review the assembled phase diff (all the phase's slices) for
  integration issues (interfaces, cross-slice contracts).

Let `<scope>` be `design`, a slice id (e.g. `1.2`), or `phase<P>` (e.g. `phase1`).
.harness/design.md must exist; for slice/phase scopes the implementation must be
on disk.

**Loop counter:** `N = (this scope's counter) + 1` — `state.designReview` for
`design`, `state.slices[<id>].reviewCount` for a slice, or the round count in
`state.phaseReview[<P>]` for a phase (fall back to counting
`.harness/review-<scope>-*.md` files + 1 if state is absent). If N > 8, STOP —
this scope is not converging; summarize what each side asserts.

## Step 1 — Claude reviewer (passive, separation-preserving)

CRITICAL CONTEXT BOUNDARY: do NOT include any implementer notes/rationale in the
reviewer's prompt. Pass file PATHS only.

Spawn a generic reviewer subagent (the Agent tool):

----- BEGIN SUBAGENT SCOPE -----
Audit the <scope>:
- `design`: audit `.harness/design.md` ITSELF — are the interfaces buildable, the
  acceptance criteria testable, and the `## Phases & Slices` breakdown sound (no
  dependency cycle; parallel slices own disjoint files)? There is no code diff.
- a slice: audit the slice's diff against THAT slice's acceptance criteria under
  "Phases & Slices".
- a phase: audit the assembled phase diff for integration correctness.
Spec + prior decisions: .harness/design.md, .harness/decisions.md.
For slice/phase, derive changed files authoritatively from git (`git status
--short` + `git diff --name-only` vs the base branch), restricted to the scope's
files — do NOT rely on an ephemeral implementer list.

Severity (P-levels) — pick one per finding, don't ask:
- BLOCKING (P1): prod incident risk, data loss, security hole, spec violation that
  breaks an acceptance criterion
- MAJOR (P1): clear bug, missing edge case the design listed, test gap on a criterion
- MINOR (P2): code quality / readability / perf with no spec impact
- NIT (P3): style; usually omit
Do NOT flag style outside codebase conventions, or out-of-scope improvements.
Out-of-scope real bugs → .harness/followups.md.

Write .harness/review-<scope>-N.md:
  # Review <scope> N
  ## Verdict: CONVERGED | FINDINGS
  ## Findings
  ### [SEVERITY] Short title
  **Where:** file:line
  **Issue / Why it matters / Suggested fix**
CONVERGED = no P1 (no BLOCKING or MAJOR). Return: the path, verdict, one-line count.
----- END SUBAGENT SCOPE -----

## Step 2 — Cross-model codex pass (direct CLI)

Run codex DIRECTLY from this (main) context — NEVER inside a subagent that waits
on it (subagents bail on codex ~50% of the time). Background + a log:

```
codex exec "Review <scope> in this repo. For 'design': audit .harness/design.md
itself (buildable interfaces, testable criteria, sound Phases & Slices — no
dependency cycle or overlapping parallel ownership). For a slice: only its
acceptance criteria + owned files. For a phase: the assembled slices for
integration. Flag issues BLOCKING/MAJOR/MINOR, specific to file:line. Prioritized
list." > .harness/codex-raw.log 2>&1
```

run_in_background; wait for the completion notification; then a bounded
post-process subagent: "Read .harness/codex-raw.log, extract codex's final
findings only, write .harness/codex-review-<scope>.md with the same severity tags,
under 150 words." (Keeps the raw log out of the main context.)

Degradation (do NOT hard-fail): codex CLI missing OR hangs/times out → write
codex-review-<scope>.md = "codex unavailable — Claude-only review" + a warning,
and continue.

## Step 3 — Combine & converge

Compare reviewer vs codex: both-flagged = high confidence; **codex-only = scrutinize
hardest** (bugs Claude missed); reviewer-only = claude-only.

**Converged** when NEITHER voice has an open **P1** (BLOCKING or MAJOR). P2/P3 are
logged (the review file / followups.md) but do not block convergence. Record to
.harness/state.json: set this scope's verdict (`CONVERGED | FINDINGS`) and
increment its reviewCount.

After this stage:
- **FINDINGS** (a P1 from either voice) → suggest /implement on this scope to fix.
  Do NOT auto-loop here — `/drive` owns the loop and the cap-8.
- **CONVERGED** → `/drive` proceeds (next slice, then phase-integration, then —
  after all phases converge — verify/ship).
