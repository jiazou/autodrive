---
description: SHIP stage (Stage 5) of /drive — promotes run ledgers, runs the full suite, builds one commit + PR in a ship worktree, then Gate B before push. Usually invoked by /drive.
argument-hint: (operates on the run's featureBranch)
---
You are running the SHIP stage (Stage 5) — harness-owned, ONCE for the feature, on
`featureBranch` in a dedicated **ship worktree** (`$RUN_DIR/wt/ship`), never the
main tree. NOT gstack `/ship` (auto-pushes): wait at **Gate B** before `push`/PR.

## Preconditions (non-decision STOPs)

1. **Gate A passed:** `$RUN_DIR/state.json` has `lastGate == "A"`. Do NOT infer it
   from a review file existing.
2. **All phases hardened:** every `state.phaseReview[*].status == "hardened"` (the
   terminal per-phase state — a phase reaches it only after its review converged AND
   its harden pass completed) and no slice left non-`converged` in `state.slices`.
   Gate on state, not review files.
3. **`featureBranch` exists** with each phase's integration merged in.
4. **Tooling:** git remote, `gh` (or `glab`), `jq`, a runnable test runner.

If any fails → STOP with which one + what to do.

## Ship worktree + ledger promotion

- `git worktree add $RUN_DIR/wt/ship <featureBranch>` and work there (cwd).
- **Promote the run ledgers into the repo's committed ones:** append this run's
  `$RUN_DIR/decisions.md` + `$RUN_DIR/followups.md` entries to the repo's
  `.harness/decisions.md` + `.harness/followups.md` (the cross-task ledgers), then
  `git commit` that on `featureBranch`. (Slice subagents wrote to `$RUN_DIR`; this
  is where it lands in the repo.) **This commit MUST touch EXACTLY those two files
  and nothing else, as a single commit** — they are the ship gate's ledger allowlist
  (`SHIP_LEDGER_ALLOWLIST` in `bin/drive-conformance.sh`). The ship invariant tolerates
  one post-review commit only if `R..tip` is a subset of that allowlist; staging any
  other file (incl. other `.harness/*`), or splitting into >1 commit, makes the ship
  conformance check fail. Keep this in sync with the allowlist constant.

## Run the full suite (flaky-retry)

Run the FULL test suite in the ship worktree. **Red → retry once**; green →
continue (log the flake to `$RUN_DIR/event-log.jsonl`); **still red → STOP** and
report the failures (a human-fix blocker, not a decision).

## Build the PR (no push yet)

- Surface a one-line summary of every decision promoted this run (with
  Classification) + any followups added.
- Propose a commit/PR title + body from `$RUN_DIR/design.md` + the
  `git diff <baseRef>..<featureBranch>`.

## Ship conformance (defense-in-depth, before Gate B)

Before surfacing the PR for approval, run `bin/drive-conformance.sh $RUN_DIR --mode
ship` and proceed only if it reports clean — it verifies all shipped **code** was
covered by a converged, SHA-bound review (∃ a counting phase review with `reviewed-sha
R` s.t. `R` is an ancestor of `featureBranch`'s tip and `R..tip` is ≤1 commit touching
only the two allowlisted ledger files). On a violation, run `/drive-review phase <P>` for
the final phase so its reviewed-sha covers the shipped tip (ship-mode reads `review-phase*`
artifacts; it has no `ship` scope), then retry. The PreToolUse hook enforces this
same gate (fail-CLOSED) on the push/PR; running it in-prose first makes enforcement
degrade gracefully where the hooks aren't installed.

## Gate B — approval before push

Surface the diff summary + proposed PR text and WAIT for explicit approval. Do NOT
push or open the PR until approved. **Set `state.waiting = "gateB"` before you
present it** so the Stop hook lets the turn end here.

End commit messages with:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>

End PR bodies with:
🤖 Generated with [Claude Code](https://claude.com/claude-code)

## After approval

Push `featureBranch`; open ONE PR (`gh pr create --base <baseRef>` / `glab`).
Update `$RUN_DIR/state.json` (`lastGate="B"`, `stage="done"`). `git worktree
remove` the ship worktree. Report the PR link and the `$RUN_DIR` path (kept for
the run record). The user's main working tree was never touched.
