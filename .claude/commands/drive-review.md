---
description: REVIEW stage (Stage 3) of /drive — dual-voice review (Claude reviewer subagent + codex) over a design/slice/phase scope; converged when neither voice has an open P1. Usually invoked by /drive.
argument-hint: design | slice <id> | phase <P> [harden-regress]
---
You are running the REVIEW stage (Stage 3) — the harness's **dual-voice review
primitive** (a passive Claude reviewer + a direct codex pass over the same scope,
combined). NOT gstack `/review` (fix-first, mutates). `/drive`
(or `/drive-plan`) invokes it with a **scope** and passes `$RUN_DIR` + the scope's git
refs:

- `design` — review the **high-level** `$RUN_DIR/design.md` itself, before Gate A: a
  sound goal/approach and a sound ordered `## Phases` breakdown (no phase dependency
  cycle; phase boundaries that can deliver the goal). High-level altitude — it does NOT
  demand slice/interface detail (that is each phase's own design). No code diff.
- `phase <P> design` — review the per-phase detailed design `$RUN_DIR/design-phase<P>.md`
  itself (invoked by `/drive-design`, before that phase implements): buildable interfaces,
  testable acceptance criteria, a sound slice breakdown (no slice dependency cycle; parallel
  slices own disjoint files; no slice contract that contradicts the real prior-phase code).
  No code diff.
- `slice <id>` — review the slice's diff `git diff <phaseBaseSha>..slice/<runId>/<id>`
  against that slice's acceptance criteria (owned files only).
- `phase <P>` — review the assembled integration diff
  `git diff <phaseBaseSha>..phaseInt/<runId>/<P>` for integration issues (interfaces,
  cross-slice contracts).
- `phase <P> harden-regress` — same review as `phase <P>`, but invoked by
  `/drive-harden` as its regression guard. Identical scope/diff/mechanics; the ONLY
  difference is the counter (below) — its bounding is owned by the harden loop, not the
  conformance cap.

Let `<scope>` be `design`, `<id>` (e.g. `1.2`), `phase<P>`, or the phasedesign token (the
per-phase design review of `design-phase<P>.md`). **Resolve the phasedesign token's
redesign epoch YOURSELF** by the single epoch-resolution rule (drive.md § Durable
checkpoint contract, In-flight dispatch markers) — invokers pass `phase <P> design`
unchanged: set `R` = the highest epoch among `$RUN_DIR/redesign-<P>-r*.marker` (0 if
none); `R == 0` → the bare `phasedesign<P>`, `R >= 1` → `phasedesign<P>-r<R>`. Use the
resolved token everywhere `<scope>` appears — the review file, the codex sibling, the
`codex-raw-<scope>.log`, and the file-count counter fallback. The coordinator writes the
in-flight marker, not this stage.

**Loop counter:** `N = (this scope's counter) + 1` — `state.designReview` for
`design`, `state.slices[<id>].reviewCount` for a slice, the `phaseReview[<P>]`
round for a `phase <P>` review, `state.phaseDesign[<P>].round` for a `phase <P> design`
review (fall back to counting `$RUN_DIR/review-<scope>-*.md` + 1 if state is absent).
If N > 8, STOP — not converging; summarize each side.
**Exception — `harden-regress`:** do NOT read, increment, or cap against the
conformance `phaseReview[<P>].round`. The harden loop already bounds the number of
these passes (its 3-fix-round cap), so there is no N>8 STOP here; just run the review
and report CONVERGED/FINDINGS. (This is what lets harden re-review a phase whose
integration already used 6–8 conformance rounds without false-STOPping.)

## Step 1 — Claude reviewer (passive, separation-preserving)

CRITICAL BOUNDARY: do NOT include any implementer notes/rationale in the reviewer's
prompt. Pass PATHS + git refs only. Spawn a generic reviewer subagent:

----- BEGIN SUBAGENT SCOPE -----
Audit the <scope>:
- `design`: audit the HIGH-LEVEL `$RUN_DIR/design.md` ITSELF — a sound goal/approach and
  a sound ordered `## Phases` breakdown (no phase dependency cycle; phase boundaries that
  can deliver the goal). High-level altitude — do NOT demand slice/interface detail. No
  code diff.
- `phasedesign<P>`: audit the per-phase detailed design `$RUN_DIR/design-phase<P>.md` ITSELF
  — interfaces buildable, acceptance criteria testable, the `Slices` breakdown sound (no
  slice dependency cycle; parallel slices own disjoint files; no slice contract that
  contradicts the real prior-phase code). No code diff.
- a slice: audit `git diff <phaseBaseSha>..slice/<runId>/<id>` against THAT slice's
  acceptance criteria, restricted to its owned files.
- a phase: audit `git diff <phaseBaseSha>..phaseInt/<runId>/<P>` for integration correctness.
Spec + prior decisions: the phase's detailed design `$RUN_DIR/design-phase<P>.md` (for a
slice/phase scope — the slice acceptance criteria live there; `$RUN_DIR/design.md` is the
high-level context), and `$RUN_DIR/decisions.md`. Derive the diff authoritatively from git
(the refs above) — never an ephemeral implementer list.

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
- **design / phasedesign:** OMIT `reviewed-sha:` — these audit a design DOC
  (`design.md` / `design-phase<P>.md`), not a git tip. (`design` feeds the plan-gate,
  which requires only `## Verdict: CONVERGED` + the codex file; `phasedesign<P>` is
  consumed by `/drive-design` and the verdict-only `phasedesign-gate:<P>` (which
  reads the current-epoch `review-phasedesign<P>[-r<R>]-N.md` + codex pair — verdict +
  codex presence, no git tip to bind).)
----- END SUBAGENT SCOPE -----

## Step 2 — Cross-model codex pass (direct CLI, per-scope log)

Run codex DIRECTLY from the main context — NEVER inside a subagent that waits on it.
Use a **per-scope** log so parallel slice reviews don't collide:

```
codex exec "Review <scope>. For 'design': audit $RUN_DIR/design.md — high-level only
(sound goal/approach + ordered ## Phases, no phase cycle). For 'phasedesign<P>': audit
$RUN_DIR/design-phase<P>.md (buildable interfaces, testable criteria, sound Slices — no
slice cycle, disjoint owns, no contract contradicting real prior-phase code). For a slice:
git diff <phaseBaseSha>..slice/<runId>/<id>, only its acceptance criteria + owned files. For
a phase: git diff <phaseBaseSha>..phaseInt/<runId>/<P>, integration. Flag BLOCKING/MAJOR/
MINOR with file:line. Prioritized." > $RUN_DIR/codex-raw-<scope>.log 2>&1
```

On a re-dispatch after a stranded `inflight-review-<scope>.marker`, first `mv` the
existing `codex-raw-<scope>.log` aside (e.g. `codex-raw-<scope>.log.stranded`) — an
orphaned background codex may still be appending to it.

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
`$RUN_DIR/state.json`: this scope's verdict + increment its counter — `state.designReview`
for `design`, `state.slices[<id>].reviewCount` for a slice, `state.phaseReview[<P>].round`
for a `phase <P>` review, `state.phaseDesign[<P>].round` for a `phase <P> design` review.
**Exception — `harden-regress`:** increment nothing (the harden loop's 3-fix-round cap
bounds it).

After this stage:
- **FINDINGS** → `/drive` loops `/drive-implement` on this scope (it owns the cap-8).
- **CONVERGED** → `/drive` proceeds (next slice → phase-integration → after all
  phases, verify/ship).
