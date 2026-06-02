You are running the SHIP stage (Stage 5) — a harness-owned thin stage. It does
NOT call gstack `/ship` (which auto-pushes); we keep an explicit human gate
before anything leaves the machine. This is the second and final human gate
(Gate B).

## Preconditions (check first; non-decision STOPs)

1. Gate A passed: `.harness/state.json` has `lastGate == "A"` (the plan was
   approved). Do NOT infer this from a `review-*.md` file merely existing.
2. Implementation changes are on disk (the working tree / branch has the diff).
3. All phases converged: every entry in `state.phaseReview` is `converged` (each
   phase passed its dual-voice integration review — neither voice has an open P1),
   and no slice is left non-CONVERGED in `state.slices`. Gate on this state; do
   NOT re-parse the per-scope review files (they're the human-readable detail).
4. Ship tooling present: a git remote, `gh` (or `glab`) on PATH, `jq`, a
   clean-enough tree, a known base branch, and a runnable test runner.

If any precondition fails, STOP and say which one and what to do. These are
facts, not decisions — do not auto-decide past them.

## Run tests

Run the test suite now (per the project's runner). **If tests are red → STOP.**
Broken tests are a human-fix blocker, not a decision the 6 principles can answer.
Report the failures. Do not proceed.

## Build the PR (no push yet)

If tests pass:
- Read `.harness/decisions.md` → surface a one-line summary of every decision
  whose **Task:** matches this run, with its Classification. (decisions.md is an
  append-only cross-task ledger — filter by the Task field; never clear it.)
- Read `.harness/followups.md` → surface entries added for this task.
- Propose a commit message and PR description derived from `design.md` + the diff.
- If not already on a feature branch, create one (never commit straight to the
  default branch).

## Gate B — approval before push

Surface the diff summary + the proposed commit/PR text and WAIT for explicit
approval. Do NOT push or open the PR until approved.

End commit messages with:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>

End PR bodies with:
🤖 Generated with [Claude Code](https://claude.com/claude-code)

## After approval

Commit, push the branch, and open the PR (`gh pr create` / `glab`). Update
`.harness/state.json` (`lastGate="B"`, `stage="done"`) and report the PR link.
