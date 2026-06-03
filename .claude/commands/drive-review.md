---
description: REVIEW stage (Stage 3) of /drive — dual-voice review (Claude reviewer subagent + codex) over a design/slice/phase scope; converged when neither voice has an open P1. Usually invoked by /drive.
argument-hint: design | slice <id> | phase <P>
---
You are running the REVIEW stage (Stage 3) — the harness's **dual-voice review
primitive** (a passive Claude reviewer + a direct codex pass over the same scope,
combined). NOT gstack `/review` (fix-first, mutates). `/drive`
(or `/drive-plan`) invokes it with a **scope** and passes `$RUN_DIR` + the scope's git
refs:

- `design` — review `$RUN_DIR/design.md` itself, before Gate A: buildable
  interfaces, testable acceptance criteria, a sound `## Phases & Slices` breakdown
  (no slice dependency cycle; parallel slices own disjoint files). No code diff.
- `slice <id>` — review the slice's diff `git diff <phaseBaseSha>..slice/<runId>/<id>`
  against that slice's acceptance criteria (owned files only).
- `phase <P>` — review the assembled integration diff
  `git diff <phaseBaseSha>..phaseInt/<P>` for integration issues (interfaces,
  cross-slice contracts).

Let `<scope>` be `design`, `<id>` (e.g. `1.2`), or `phase<P>`.

**Loop counter:** `N = (this scope's counter) + 1` — `state.designReview` for
`design`, `state.slices[<id>].reviewCount` for a slice, the `phaseReview[<P>]`
round for a phase (fall back to counting `$RUN_DIR/review-<scope>-*.md` + 1 if
state is absent). If N > 8, STOP — not converging; summarize each side.

## Step 1 — Claude reviewer (passive, separation-preserving)

CRITICAL BOUNDARY: do NOT include any implementer notes/rationale in the reviewer's
prompt. Pass PATHS + git refs only. Spawn a generic reviewer subagent:

----- BEGIN SUBAGENT SCOPE -----
Audit the <scope>:
- `design`: audit `$RUN_DIR/design.md` ITSELF — interfaces buildable, acceptance
  criteria testable, `## Phases & Slices` sound (no dependency cycle; parallel
  slices own disjoint files). No code diff.
- a slice: audit `git diff <phaseBaseSha>..slice/<runId>/<id>` against THAT slice's
  acceptance criteria, restricted to its owned files.
- a phase: audit `git diff <phaseBaseSha>..phaseInt/<P>` for integration correctness.
Spec + prior decisions: `$RUN_DIR/design.md`, `$RUN_DIR/decisions.md`. Derive the
diff authoritatively from git (the refs above) — never an ephemeral implementer list.

Severity (P-levels) — pick one, don't ask:
- BLOCKING (P1): prod incident risk, data loss, security hole, spec violation that
  breaks an acceptance criterion
- MAJOR (P1): clear bug, missing edge case the design listed, test gap on a criterion
- MINOR (P2): code quality / readability / perf with no spec impact
- NIT (P3): style; usually omit
Out-of-scope real bugs → `$RUN_DIR/followups.md`.

Write `$RUN_DIR/review-<scope>-N.md`:
  # Review <scope> N
  ## Verdict: CONVERGED | FINDINGS
  reviewed-sha: <40-hex>
  ## Findings → ### [SEVERITY] Short title / **Where** file:line / Issue / Why / Fix
CONVERGED = no P1. Return: the path, verdict, one-line count.

**`reviewed-sha:` (SHA-bound proof — the enforcement gate reads this).** Emit a line
`reviewed-sha: <40-hex>` = the **exact git tip this review diffed**, so a review only
counts for code whose tip equals it (a stale CONVERGED file can't cover newly-added
commits). Bind it by scope:
- **slice `<id>`:** `<40-hex>` = `git rev-parse slice/<runId>/<id>` (the slice tip the
  diff `<phaseBaseSha>..slice/<runId>/<id>` ended at).
- **phase `<P>`:** `<40-hex>` = `git rev-parse phaseInt/<runId>/<P>` (the assembled
  integration tip). The **harden-regress** re-review (run by HARDEN after it commits
  to `phaseInt/<runId>/<P>`) MUST re-emit `reviewed-sha:` at the **post-fix**
  `git rev-parse phaseInt/<runId>/<P>` tip — otherwise the phase-merge gate sees a
  stale pre-harden sha and blocks the advance.
- **design:** OMIT `reviewed-sha:` — design review audits `design.md`, not a git tip;
  the plan-gate only requires `## Verdict: CONVERGED` + the codex file (no sha).
----- END SUBAGENT SCOPE -----

## Step 2 — Cross-model codex pass (direct CLI, per-scope log)

Run codex DIRECTLY from the main context — NEVER inside a subagent that waits on it.
Use a **per-scope** log so parallel slice reviews don't collide:

```
codex exec "Review <scope>. For 'design': audit $RUN_DIR/design.md (buildable
interfaces, testable criteria, sound Phases & Slices). For a slice: git diff
<phaseBaseSha>..slice/<runId>/<id>, only its acceptance criteria + owned files. For
a phase: git diff <phaseBaseSha>..phaseInt/<P>, integration. Flag BLOCKING/MAJOR/
MINOR with file:line. Prioritized." > $RUN_DIR/codex-raw-<scope>.log 2>&1
```

run_in_background; wait for completion; then a bounded post-process subagent: "Read
`$RUN_DIR/codex-raw-<scope>.log`, extract codex's final findings, write
`$RUN_DIR/codex-review-<scope>.md` (same severity tags, <150 words)."

Degradation (do NOT hard-fail): codex missing OR hangs/times out → write
`codex-review-<scope>.md` with the **anchored first-line token `CODEX_UNAVAILABLE`**
(exactly that bare token as the file's FIRST line — conformance's codex check matches
it anchored, so a buried mention elsewhere is NOT recognized), optionally followed by
a warning note on later lines; continue.

## Step 3 — Combine & converge

Compare: both-flagged = high confidence; **codex-only = scrutinize hardest** (bugs
Claude missed); reviewer-only = claude-only. **Converged** when NEITHER voice has an
open **P1** (BLOCKING/MAJOR); P2/P3 logged, not blocking. Record to
`$RUN_DIR/state.json`: this scope's verdict + increment its `reviewCount`.

After this stage:
- **FINDINGS** → `/drive` loops `/drive-implement` on this scope (it owns the cap-8).
- **CONVERGED** → `/drive` proceeds (next slice → phase-integration → after all
  phases, verify/ship).
