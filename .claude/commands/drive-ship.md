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

- **Create `wt/ship` idempotently** (a resumed ship may have a stale one from a prior
  partial attempt): `git worktree remove --force $RUN_DIR/wt/ship 2>/dev/null; git
  worktree prune`, then `git worktree add $RUN_DIR/wt/ship <featureBranch>` and work
  there (cwd).
- **Resume-idempotency rule (do NOT double-promote / double-commit).** The ledger commit
  is created BEFORE the suite-red STOP and BEFORE Gate B, so a resumed ship re-enters
  here AFTER it already landed. Determine state from git BEFORE appending: let `R` =
  finalize's `reviewed-sha` (precondition #3). If `R..featureBranch` tip is already
  exactly the single ledger commit (`R` is the tip's parent AND the tip touches only the
  3-file `SHIP_LEDGER_ALLOWLIST`), the ledger was already promoted on a prior crashed
  attempt → **SKIP** the append+commit below (re-appending would DUPLICATE entries and a
  second commit would break the `R..tip ≤1 commit` ship-gate invariant). Append+commit
  ONLY when the tip is still AT `R` (`R == tip`, pre-ledger). The forward path (first
  ship entry, `R == tip`) is unchanged.
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

## Design-doc handoff audit

After the ledger commit, audit `$RUN_DIR/decisions.md` for **cross-run decisions** — decisions that introduce or change contracts, surface API methods, naming conventions, or cross-slice ownership rules that future runs will need to build on. A decision is cross-run if its subject (a method name, a carrier field, a paradigm label, a directive contract) does not appear in the driven project's shared design doc.

For each cross-run decision not yet reflected in the design doc, append a `HANDOFF:` entry to `$RUN_DIR/followups.md` in the form:
```
HANDOFF: [D-N] <subject> — land in <design-doc path> before next run starts
```

These entries are promoted into `.harness/followups.md` by the ledger commit already made above. Surface them at Gate B alongside the PR summary so the user sees what the next run must pick up. Do NOT block Gate B on unresolved handoffs — they are advisory, not a hard gate.

## Run the full suite (flaky-retry)

Run the FULL test suite — **`bin/run-tests.sh`** (the canonical runner: `python3 -m pytest
tests/` AND every `test/*.test.sh`, all suites, no early-exit) — in the ship worktree.
Do NOT hand-pick a subset (pytest + one bash file misses the other gate suites). **Red →
retry once**; green →
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

**Degraded codex this run** (surface at Gate B alongside the diff summary): `Degraded codex this
run: <k> killed-timeout, <u> unavailable across scopes {…}` — the scopes whose codex degraded at
their FINAL round, computed from the final-round `codex-*` files + `$RUN_DIR/codex-attempts-<runId>.jsonl`.
Codex artifacts are single-file-per-scope, so no per-round history is claimed (the count is scopes
degraded at their final round). Advisory — it does NOT block Gate B.

End commit messages with this trailer, substituting <model> = the shipping session's own
model name as reported by its environment (e.g. `Claude Fable 5`); if unavailable, use
`Claude`:
Co-Authored-By: <model> <noreply@anthropic.com>

End PR bodies with:
🤖 Generated with [Claude Code](https://claude.com/claude-code)

## After approval

The decisive invariant is **`completedAt`-after-removal-SUCCESS, NOT stage-ordering**: the
helper's `is_done()` treats a parseable `completedAt` ALONE as done (independent of `stage`),
so a `completedAt` written before removals finished would itself make the run sweepable. The
marker MUST be the LAST thing, written only after EVERY required removal is PROVEN done.

1. Push `featureBranch`; open ONE PR (`gh pr create --base <baseRef>` / `glab`). Record the
   PR url to `state.ship.prUrl`.
2. **Require a `-d`-VALID `repoRoot`, then `cd` OUT of `wt/ship` to a VERIFIED-STABLE dir
   FIRST**, BEFORE the removal loop. The ship coordinator's cwd is `$RUN_DIR/wt/ship` — itself
   a drive-owned name the loop removes; the removal would delete the live cwd if cwd is still
   inside it, AND the removal loop runs `git -C "<repoRoot>"`, so an invalid `repoRoot` cannot
   unregister anything. Validate `repoRoot` with an explicit `-d` check — mirror the helper's
   guard `[ -d "$rr" ]` EXACTLY; do NOT treat "`repoRoot` is set" as sufficient (a
   stale/deleted-but-present `state.repoRoot` makes the `git worktree remove` calls FAIL yet
   leaves `trash` reachable — NOT fail-closed). **The destructive teardown REQUIRES a
   `-d`-valid `repoRoot`: if `repoRoot` is empty OR NOT `[ -d "$repoRoot" ]`, fail-closed for
   the WHOLE teardown — run NO `git worktree remove`/`prune`, NO `trash`, and DO NOT write
   `completedAt` / `stage="done"`.** Only with a valid `repoRoot`: select the cd target
   `target = "$repoRoot"` (a stable dir OUTSIDE every `wt/<name>` being removed); the `cd` is
   itself CHECKED (`cd "$target" || <fail-closed>`). **Fail-closed branch — invalid `repoRoot`
   OR a failed `cd`:** run NO destructive verb (no `git worktree remove`, no `trash`), leave
   the worktrees, and DO NOT write `completedAt` / `stage="done"` — the run stays NOT-done /
   not-sweepable; report the failure; a later resume re-attempts (it can re-derive nothing — D7
   write-once — but a transient `repoRoot`-unmounted condition may clear). The destructive loop
   (steps 3-6) runs ONLY AFTER a `-d`-valid `repoRoot` AND a successful `cd` to it.
3. **Remove ALL drive-owned worktrees of the run, in the owning (now `-d`-valid) repo,
   capturing per-tree removal success.** For each `$RUN_DIR/wt/<name>` whose `<name>` is
   drive-owned: `git -C "<repoRoot>" worktree remove --force "$RUN_DIR/wt/<name>"
   2>/dev/null`; then once `git -C "<repoRoot>" worktree prune`; then `trash
   "$RUN_DIR/wt/<name>"` the dead dirs (drive-owned names only — never ad-hoc names). **For
   EACH drive-owned `<name>`, VERIFY removal completed: confirm `[ ! -e "$RUN_DIR/wt/<name>"
   ]`** — the per-tree removal-success proof. (Removing `wt/ship` itself succeeds because the
   command runs `-C "<repoRoot>"`, not inside the worktree, and cwd is already out of it per
   step 2; including it is idempotent.) Because step 2 already proved `repoRoot` is `-d`-valid,
   the `git -C "<repoRoot>"` unregister is genuine — never a silently-failed no-op that leaves
   `trash` to reclaim a still-registered tree.
4. **GATE: write `completedAt` ONLY IF every required drive-owned worktree removal in step 3
   is PROVEN done** (all `$RUN_DIR/wt/<name>` dirs gone). If ANY drive-owned worktree could
   NOT be removed (still exists on disk after the loop), DO NOT write `completedAt` and DO NOT
   write `stage="done"` — STOP and report the un-removable worktree (fail-safe: the run stays
   NOT-done / not-sweepable, no orphan-attesting marker). Only when all removals are proven
   done: `printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$RUN_DIR/completedAt"` (one clean
   ISO-8601 line + trailing newline — EXACTLY the format the helper parses strictly; interior
   whitespace would make it unparseable).
5. **THEN** update `$RUN_DIR/state.json` (`lastGate="B"`, `stage="done"`) via the standard
   temp-file+`mv`. `stage="done"` after the marker is belt-and-suspenders, NOT the
   load-bearing gate (the gate is the proven-removal `completedAt` in step 4).
6. Report the PR link and the `$RUN_DIR` path (kept for the run record), run from
   `<repoRoot>`. The user's main working tree was never touched.
