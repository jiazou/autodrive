You are running the REVIEW stage (Stage 3). Harness-owned — it does NOT call
gstack `/review` (which is fix-first and mutates code, breaking the
implementer↔reviewer separation). It runs a passive Claude reviewer PLUS a direct
cross-model codex pass, then compares them. This stage also subsumes the old
standalone `/codex` step — there is one codex pass, here, on the diff.

The design must exist at .harness/design.md and the implementation on disk.

Determine N from the authoritative loop counter: `N = state.reviewCount + 1`
(if `.harness/state.json` is absent OR has no `reviewCount` — e.g. a standalone
/review run — fall back to counting `.harness/review-*.md` files and adding 1).
If N > 2, STOP and
surface — the implementer and reviewer are not converging; summarize what each
side has been asserting.

## Step 1 — Claude reviewer (passive, separation-preserving)

CRITICAL CONTEXT BOUNDARY: do NOT include any of the implementer's notes,
rationale, or summary in the reviewer's prompt. Pass file PATHS only. The
reviewer judges the code against the spec on its own merits.

Spawn a generic reviewer subagent (the Agent tool — NOT a wshobson team-*
subagent):

----- BEGIN SUBAGENT SCOPE -----
Audit the diff against the spec.
Spec: .harness/design.md
Prior decisions to respect: .harness/decisions.md
Changed files: derive authoritatively from git (`git status --short` +
`git diff --name-only` vs the base branch) — do NOT rely on an ephemeral list
passed by the implementer; it is lost on resume or a dirty branch.

When a finding's severity is ambiguous, PICK ONE (do not ask):
- BLOCKING: prod incident risk, data loss, security hole, spec violation that
  breaks an acceptance criterion
- MAJOR: clear bug, missing edge case the design listed, test gap on a criterion
- MINOR: code quality / readability / perf with no spec impact
- NIT: style; usually omit
Do NOT flag style not in codebase conventions, or improvements the design marked
out of scope. Out-of-scope real bugs → .harness/followups.md.

Write .harness/review-N.md:
  # Review N
  ## Verdict: CLEAN | FINDINGS
  ## Findings
  ### [SEVERITY] Short title
  **Where:** file:line
  **Issue:** what's wrong
  **Why it matters:** what breaks
  **Suggested fix:** what to do
CLEAN = no BLOCKING or MAJOR findings. Return: the path, verdict, one-line count.
----- END SUBAGENT SCOPE -----

## Step 2 — Cross-model codex pass (direct CLI)

Run codex DIRECTLY from this (main) context — NEVER inside a subagent that waits
on it (subagents bail on codex ~50% of the time). Use background + a log file:

```
codex exec "Review the diff on this branch against the spec in
.harness/design.md. Flag issues with severity BLOCKING/MAJOR/MINOR, specific to
file:line. Output a prioritized list." > .harness/codex-raw.log 2>&1
```

Run it with run_in_background. Wait for the completion notification. Then spawn a
bounded post-process subagent: "Read .harness/codex-raw.log, extract codex's
final findings only, write .harness/codex-review.md with the same severity tags,
under 150 words." (Keeps the raw log out of the main context.)

Degradation (do NOT hard-fail the pipeline):
- codex CLI missing → skip Step 2; write `codex-review.md` = "codex unavailable —
  Claude-only review" and note it.
- codex hangs / times out → same degradation + a warning.

## Step 3 — Compare & combined verdict

Compare reviewer vs codex findings:
- flagged by BOTH → high confidence, definitely real
- codex-only → scrutinize hardest (bugs Claude missed)
- reviewer-only → claude-only
Combined verdict:
- **FINDINGS** if EITHER voice has a BLOCKING or MAJOR finding.
- **CLEAN** only if both are clean (or codex unavailable and the reviewer clean).

Record to `.harness/state.json`: set `codexVerdict` to the combined verdict and
**increment `reviewCount`** (the single authoritative loop counter `/drive` reads
for the cap — do not rely on file counts). After this stage:
- FINDINGS → suggest /implement to address them. Do NOT auto-loop here — `/drive`
  owns the loop and the cap-of-2.
- CLEAN → suggest the verify stage (if UI) then /ship.
