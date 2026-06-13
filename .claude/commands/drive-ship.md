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
3. **Finalize CONVERGED:** the run's terminal `$RUN_DIR/review-finalize-N.md`
   (highest-N) is `## Verdict: CONVERGED`, a non-empty
   `$RUN_DIR/codex-review-finalize.md` exists, AND its `reviewed-sha R` is an
   ANCESTOR of the current `featureBranch` tip with `R..tip` ≤1 commit ⊆ the 3-file
   ledger allowlist `{.harness/decisions.md, .harness/followups.md, TODO.md}` — i.e.
   `R == tip` (first ship entry, pre-ledger) OR `R..tip` is exactly the single ledger
   commit (a resume after ship's ledger commit). This precondition must TOLERATE the
   one ledger commit because a resumed ship re-enters this check AFTER the
   ledger-promotion commit — /drive-ship makes that commit BEFORE the suite-red STOP
   and BEFORE Gate B, so a run resumed past either re-arrives here with the tip one
   commit ahead of finalize's reviewed-sha; strict `== tip` would FALSE-STOP a
   legitimately-finalized resumed ship. This is the SAME criterion the downstream
   `--mode ship` conformance gate applies to this SAME finalize artifact. Missing /
   non-converged / R not an allowlisted-≤1 ancestor → STOP: "run `/drive-finalize` so
   its reviewed-sha covers the shipped tip."
4. **`featureBranch` exists** with each phase's integration merged in.
5. **Tooling:** git remote, `gh` (or `glab`), `jq`, a runnable test runner.

If any fails → STOP with which one + what to do, **via the Present human pause routine**:
set `state.waiting="stop:<reason>"`, then emit the run graph — read
`~/.claude/commands/drive.md` § *Emit run graph* and follow it (if `drive.md` is unreachable,
emit `(run graph unavailable: drive.md not found)` and continue) — then report. (Makes a
standalone `/drive-ship` precondition STOP self-sufficient.)

## Ship worktree + ledger promotion

- `git worktree add $RUN_DIR/wt/ship <featureBranch>` and work there (cwd).
- **Promote the run ledgers into the repo's committed ones:** append this run's
  `$RUN_DIR/decisions.md` + `$RUN_DIR/followups.md` entries to the repo's
  `.harness/decisions.md` + `.harness/followups.md` (the cross-task ledgers). Then,
  **if** `$RUN_DIR/finalize-todo.md` is non-empty (finalize produced architectural
  findings), promote it into the driven project's repo-root `TODO.md` (append under
  its dated run heading; if `TODO.md` does not exist, create it from the
  finalize-todo content) and `git add TODO.md`. If `$RUN_DIR/finalize-todo.md` is
  absent/empty (no architectural findings), promote nothing — `TODO.md` is untouched
  and stays out of the commit. `git commit` all of the above on `featureBranch` as a
  SINGLE commit. (Slice subagents wrote to `$RUN_DIR`; this is where it lands in the
  repo.) **This commit MUST touch EXACTLY the ledger files — `.harness/decisions.md`,
  `.harness/followups.md`, and repo-root `TODO.md` when finalize produced
  architectural findings — and nothing else, as a single commit.** Those three paths
  are the ship gate's ledger allowlist (`SHIP_LEDGER_ALLOWLIST` in
  `bin/drive-conformance.sh`, now 3 entries: `{.harness/decisions.md,
  .harness/followups.md, TODO.md}`). The ship invariant tolerates one post-review
  commit only if `R..tip` is a subset of that allowlist; staging any other file
  (incl. other `.harness/*`), or splitting into >1 commit, makes the ship conformance
  check fail. Keep this in sync with the `SHIP_LEDGER_ALLOWLIST` constant.

## Run the full suite (flaky-retry)

Run the FULL test suite in the ship worktree. **Red → retry once**; green →
continue (log the flake to `$RUN_DIR/event-log.jsonl`); **still red → STOP** and
report the failures (a human-fix blocker, not a decision) **via the Present human pause
routine** — set `state.waiting="stop:suite-red"`, then emit the run graph (read
`~/.claude/commands/drive.md` § *Emit run graph* and follow it; if unreachable, emit
`(run graph unavailable: drive.md not found)`), then report. Record the suite result to
`state.ship.suite` (e.g. "191 passed").

## Build the PR (no push yet)

- Surface a one-line summary of every decision promoted this run (with
  Classification) + any followups added.
- If `$RUN_DIR/finalize-todo.md` exists, surface its architectural follow-ups (from
  the durable `$RUN_DIR` copy — NOT from the worktree) so the user sees what finalize
  deferred to `TODO.md` before approving the push at Gate B.
- Propose a commit/PR title + body from `$RUN_DIR/design.md` + the
  `git diff <baseRef>..<featureBranch>`.

## Ship conformance (defense-in-depth, before Gate B)

Before surfacing the PR for approval, run `bin/drive-conformance.sh $RUN_DIR --mode
ship` and proceed only if it reports clean — it verifies all shipped **code** was
covered by a converged, SHA-bound review (∃ the CONVERGED finalize review with
`reviewed-sha R` that is an ancestor of tip with `R..tip` ≤1 commit ⊆ the 3-file
ledger allowlist — NOT strict `R == tip`, since ship's own ledger commit sits one
commit past finalize's reviewed-sha — AND ≥1 counting phase-integration review as a
precondition). On a violation, run `/drive-finalize` so its `reviewed-sha` covers the
shipped tip (ship-mode's terminal candidate-R is the `review-finalize-N.md` artifact,
not a phase review — a phase review's reviewed-sha is an ancestor of, but no longer
equal to, the post-finalize tip), then retry. The PreToolUse hook enforces this
same gate (fail-CLOSED) on the push/PR; running it in-prose first makes enforcement
degrade gracefully where the hooks aren't installed. Record the conformance result to
`state.ship.conformance` (e.g. "clean").

## Gate B — approval before push

Run the **Present human pause** routine — (1) set `state.waiting = "gateB"`; (2)
**emit the run graph**: read `~/.claude/commands/drive.md` § *Emit run graph* and follow
it (if unreachable, emit `(run graph unavailable: drive.md not found)` and continue; no
paraphrase); (3) surface the diff summary + proposed PR text and WAIT for approval. Do
NOT push or open the PR until approved.

End commit messages with:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>

End PR bodies with:
🤖 Generated with [Claude Code](https://claude.com/claude-code)

## After approval

Push `featureBranch`; open ONE PR (`gh pr create --base <baseRef>` / `glab`). Record
the PR url to `state.ship.prUrl`.
Update `$RUN_DIR/state.json` (`lastGate="B"`, `stage="done"`). `git worktree
remove` the ship worktree. Report the PR link and the `$RUN_DIR` path (kept for
the run record). The user's main working tree was never touched.
