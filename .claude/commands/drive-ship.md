---
description: SHIP stage (Stage 5) of /drive — promotes run ledgers, runs the full suite, builds one commit + PR in a ship worktree, then Gate B before push. Usually invoked by /drive.
argument-hint: (operates on the run's featureBranch)
---
You are running the SHIP stage (Stage 5) — harness-owned, ONCE for the feature, on
`featureBranch` in a dedicated **ship worktree** (`$RUN_DIR/wt/ship`), never the
main tree. NOT gstack `/ship` (auto-pushes): wait at **Gate B** before `push`/PR.

## Preconditions (non-decision STOPs)

1. **Gate A passed:** `$RUN_DIR/state.json` has `lastGate == "A"` (the fast path). When
   `lastGate` is absent/`null` (NOT a skipped approval — e.g. a write that failed to
   persist the field despite § Stage 1's atomic-write PRESCRIPTION, a crash mid-write, or a
   legacy run predating the field; guard-repoint D-9 observed exactly this), Gate A is
   instead PROVEN by the actor-independent artifact chain (a run cannot reach ship without
   the human-approved Gate-A transition having run), requiring ALL of:
   - (a) **[load-bearing]** `state.phaseList` is NON-EMPTY **and** `state.stage` ∈
     {`execute`, `finalize`, `verify`, `ship`}. The Gate-A transition (drive.md § Stage 1)
     is the SOLE writer of a non-empty `phaseList` and runs ONLY after the human approves
     Gate A, so a populated `phaseList` at an Execute-or-later stage proves that transition
     ran; the dropped `lastGate` is the same atomic write's un-persisted field. (An empty
     `phaseList`, or a pre-Execute `stage`, means the transition never ran → Gate A NOT
     passed.)
   - (b) the highest-N `$RUN_DIR/review-design-N.md` is `## Verdict: CONVERGED` with a
     non-empty `$RUN_DIR/codex-review-design.md` sibling; and (c) precondition #2 holds
     (every phase `hardened`). (b)/(c) CORROBORATE — do NOT infer Gate A from a review
     file ALONE (a converged design can exist pre-approval); the load-bearing signal is
     (a).
   When Gate A is DERIVED (not the fast path): repair `state.lastGate = "A"`, LOG the
   derivation to `$RUN_DIR/decisions.md` (evidence-cited — recording an established fact a
   dropped write failed to persist, NOT a forge), and surface it at Gate B. Neither
   `lastGate == "A"` NOR a sound derivation (an empty `phaseList`, or a pre-Execute
   `stage`) → STOP: "Gate A not provable — no recorded approval and the artifact chain
   does not establish it." This mirrors the resume router, which already refuses to key on
   the droppable `lastGate` scalar (drive.md D1).
2. **All phases hardened:** every `state.phaseReview[*].status == "hardened"` (the
   terminal per-phase state — a phase reaches it only after its review converged AND
   its harden pass completed) and no slice left non-`converged` in `state.slices`.
   Gate on state, not review files.
3. **Finalize CONVERGED:** the run's terminal `$RUN_DIR/review-finalize-N.md`
   (highest-N) is `## Verdict: CONVERGED`, its first `## AppliedEdits:` line reads
   exactly `## AppliedEdits: no` (a fix round is non-terminal), a non-empty
   `$RUN_DIR/codex-review-finalize.md` exists, AND its `reviewed-sha R` is an
   ANCESTOR of the current `featureBranch` tip with `R..tip` ≤1 commit ⊆ the 4-file
   ledger allowlist `{.harness/decisions.md, .harness/followups.md, TODO.md,
   .harness/codex-refutations.md}` — i.e.
   `R == tip` (first ship entry, pre-ledger) OR `R..tip` is exactly the single ledger
   commit (a resume after ship's ledger commit). This precondition must TOLERATE the
   one ledger commit because a resumed ship re-enters this check AFTER the
   ledger-promotion commit — /drive-ship makes that commit BEFORE the suite-red STOP
   and BEFORE Gate B, so a run resumed past either re-arrives here with the tip one
   commit ahead of finalize's reviewed-sha; strict `== tip` would FALSE-STOP a
   legitimately-finalized resumed ship. This is the SAME criterion the downstream
   `--mode ship` conformance gate applies to this SAME finalize artifact. Missing /
   non-converged / first-`## AppliedEdits:`≠`## AppliedEdits: no` / R not an
   allowlisted-≤1 ancestor → STOP: "run `/drive-finalize` so its reviewed-sha covers
   the shipped tip."
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
- **Base-freshness preflight (diverged-base auto-resolve) — BEFORE the ledger promotion.**
  A run branches from `baseRef` at the frozen `state.baseSha`; if `baseRef` advanced while the
  run was in flight (common in a shared clone) AND both sides appended to the append-only
  `.harness` ledgers, promoting onto the STALE base copy yields a PR that CONFLICTS at merge —
  silently, unless checked. Run **`bin/drive-base-preflight.sh $RUN_DIR`** — a read-only detector
  that predicts the merge via `git merge-tree`, mutates nothing, and ALWAYS exits 0 with a JSON
  verdict (a legacy run without `baseSha`, or any unresolvable ref / invalid repoRoot, fails OPEN
  to `recommendation:"none"` → ship exactly as today; it never invents a block). Act on
  `.recommendation`:
  - `none` / `ship-as-is` → proceed UNCHANGED (base unmoved, or moved but the merge is clean).
    For `ship-as-is`, surface "base moved `.movedCommits` commits, merge clean" at Gate B
    (informational).
  - `manual-merge` (base moved AND a **non-ledger** file conflicts — a genuine semantic overlap;
    a clean auto-merge of overlapping subsystems is NOT a correct merge) → do NOT auto-rewrite;
    **STOP** via Present human pause (`waiting="stop:base-diverged-conflict"`), reporting
    `.conflicts` + `.currentBase` for the human to rebase/merge.
  - `auto-rebase` (base moved, the run's code is disjoint, and the ONLY conflict is on the
    append-only ledgers — either already on the tree, OR the PENDING promotion append the detector
    predicts from `git diff <baseSha>..<currentBase>` ∩ the ledgers the run will append to. NOTE:
    the detector returns `auto-rebase` even when the current-tree merge is "clean" (`mergeClean:true`),
    because on a FRESH ship featureBranch has not appended its ledger entries yet — the conflict is
    the pending append, which `mergeClean` cannot see) → AUTO-RESOLVE, each step a fail-closed gate:
    1. **Semantic gate — merged-tree suite.** A ledger-only TEXT conflict is not proof of
       semantic safety. In a SCRATCH worktree at `.currentBase`, `git merge <featureBranch>` and
       run the FULL suite (`bin/run-tests.sh`). Red → **STOP** (`waiting="stop:base-diverged-suite-red"`),
       do NOT rebase; remove the scratch worktree either way.
    2. **Rebase onto the fresh base.** In `wt/ship`,
       `git rebase --onto <.currentBase> <state.baseSha> <featureBranch>` (content-preserving —
       the code is disjoint). **VERIFY content-preservation:** the run's own files — the name-set
       from `git diff --name-only <state.baseSha>..<featureBranch>` (the FROZEN fork point, NOT
       the movable `baseRef` name) — have IDENTICAL blobs at the pre- vs post-rebase finalize
       commit. Not identical → `git rebase --abort` / reset to the pre-rebase tip and **STOP**
       (`waiting="stop:base-rebase-not-clean"`).
    3. **Re-bind finalize's `reviewed-sha` (sanctioned post-rebase re-bind, NOT a forge).** The
       finalize commit's sha changed under the rebase; the reviewed CODE is byte-identical (step
       2), so the CONVERGED review still holds. REPLACE the single `reviewed-sha:` line IN PLACE
       in the terminal `$RUN_DIR/review-finalize-N.md` (highest-N, `## AppliedEdits: no`) with the
       rebased finalize commit sha (the post-rebase pre-ledger `featureBranch` tip). Do NOT touch
       the `## Verdict:` line.
    4. **Re-confirm clean (fail-closed).** Re-run `bin/drive-base-preflight.sh $RUN_DIR`; require
       `.mergeClean == true`. Still conflicting → **STOP** (`waiting="stop:base-rebase-unresolved"`).
       Surface the auto-resolution ("rebased onto `.currentBase`; finalize reviewed-sha re-bound")
       at Gate B.
  **Degraded check** — when the detector could not run its prediction fully: `.fetchOk == false`
  (could not fetch `baseRef` from `origin`, so the compare ran against a possibly-STALE
  remote-tracking ref) OR the verdict carries a `.reason` (a fail-open — e.g. `merge-tree-failed`,
  an unresolvable ref). A `none`/`ship-as-is` from a degraded check may MISS a real divergence, so
  do NOT trust it silently: surface at Gate B — "base-freshness check was degraded (`<reason>` /
  fetch failed); the merge-conflict prediction may be stale — verify the base is current before
  merge" — REGARDLESS of `.recommendation`. A warning, NOT a block (offline / old-git / no-remote
  dev is legitimate — mirrors drive.md's base pre-flight fail-open; it degrades to the pre-detector
  behaviour where the human catches the conflict at merge).
  A FRESH ship rebases BEFORE the first push, so no force-push is needed; a RESUMED ship whose
  branch was already pushed force-pushes the rebased branch at the push step (§ After approval —
  explicit refspec, `--force-with-lease`).
- **Resume-idempotency rule (do NOT double-promote / double-commit).** The ledger commit
  is created BEFORE the suite-red STOP and BEFORE Gate B, so a resumed ship re-enters
  here AFTER it already landed. Determine state from git BEFORE appending: let `R` =
  finalize's `reviewed-sha` (precondition #3). If `R..featureBranch` tip is already
  exactly the single ledger commit (`R` is the tip's parent AND the tip touches only the
  4-file `SHIP_LEDGER_ALLOWLIST`), the ledger was already promoted on a prior crashed
  attempt → **SKIP** the append+commit below (re-appending would DUPLICATE entries and a
  second commit would break the `R..tip ≤1 commit` ship-gate invariant). Append+commit
  ONLY when the tip is still AT `R` (`R == tip`, pre-ledger). The forward path (first
  ship entry, `R == tip`) is unchanged.
- **Promote the run ledgers into the repo's committed ones:** FIRST run the *Design-doc
  handoff audit* (§ below) so any `HANDOFF:` entries it appends are already in
  `$RUN_DIR/followups.md` and ride THIS single commit (forward path only — on the resume
  SKIP path above, skip the audit too, since its entries already rode the original commit).
  Then append this run's
  `$RUN_DIR/decisions.md` + `$RUN_DIR/followups.md` entries to the repo's
  `.harness/decisions.md` + `.harness/followups.md` (the cross-task ledgers). Then the
  **activation-aware refutation promotion**: **if** `$RUN_DIR/codex-refutations-pending.md`
  is non-empty (`[ -s … ]` — durable refutation adjudications staged for promotion),
  probe the LIVE gate for the 4th allowlist entry —
  `grep -qF '.harness/codex-refutations.md' ~/.claude/drive-enforcement-worktree/bin/drive-conformance.sh`.
  Admitted (the grep succeeds) ⇒ promote the pending entries into
  `.harness/codex-refutations.md`, RE-DERIVING each entry's `CR-<n>` id from the LIVE
  committed ledger at promotion time: next id = (the ledger's current max `## CR-<n>`,
  via grep) + 1, assigned sequentially in pending-file order. A pending entry that
  carries an unfenced `> **VOID CR-<n> …**` annotation is DEFEATED and is SKIPPED at
  promotion — never promoted, never renumbered (the run-local file keeps the record);
  only live (un-voided) pending entries are promoted and renumbered. An absent or entry-less
  ledger has max 0 (the first promoted entry = CR-1; create the missing file with the
  B-3 schema header — the ledger's purpose/usage header + entry-schema block — before
  appending). The pending file's ids are
  PROVISIONAL by contract — a post-rebase base append may already occupy them (the
  base-preflight auto-rebases when the base advanced this ledger), so NEVER append a
  staged/remembered number verbatim; renumber, then `git add` the file so the
  renumbered entries ride the SAME single ledger
  commit below. Absent, or the probe fails (e.g. the enforcement worktree is missing) ⇒
  leave the entries run-local and surface the pending-activation followup at Gate B
  (graceful degrade — never a push false-block). Then,
  **if** `$RUN_DIR/finalize-todo.md` is non-empty (finalize produced architectural
  findings), promote it into the driven project's repo-root `TODO.md` (append under
  its dated run heading; if `TODO.md` does not exist, create it from the
  finalize-todo content) and `git add TODO.md`. If `$RUN_DIR/finalize-todo.md` is
  absent/empty (no architectural findings), promote nothing — `TODO.md` is untouched
  and stays out of the commit. `git commit` all of the above on `featureBranch` as a
  SINGLE commit. (Slice subagents wrote to `$RUN_DIR`; this is where it lands in the
  repo.) **This commit MUST touch EXACTLY the ledger files — `.harness/decisions.md`,
  `.harness/followups.md`, repo-root `TODO.md` when finalize produced architectural
  findings, and `.harness/codex-refutations.md` when pending refutations exist AND the
  live gate admits it — and nothing else, as a single commit.** (The conditional members
  stay conditional: `TODO.md` iff finalize-todo, `codex-refutations` iff
  pending+activated.) Those paths
  are the ship gate's ledger allowlist (`SHIP_LEDGER_ALLOWLIST` in
  `bin/drive-conformance.sh`, now 4 entries: `{.harness/decisions.md,
  .harness/followups.md, TODO.md, .harness/codex-refutations.md}`). The ship invariant tolerates one post-review
  commit only if `R..tip` is a subset of that allowlist; staging any other file
  (incl. other `.harness/*`), or splitting into >1 commit, makes the ship conformance
  check fail. Keep this in sync with the `SHIP_LEDGER_ALLOWLIST` constant.

## Design-doc handoff audit

**BEFORE the ledger-promotion append+commit above** (it is that step's FIRST action, forward
path only), audit `$RUN_DIR/decisions.md` for **cross-run decisions** — decisions that introduce or change contracts, surface API methods, naming conventions, or cross-slice ownership rules that future runs will need to build on. A decision is cross-run if its subject (a method name, a carrier field, a paradigm label, a directive contract) does not appear in the driven project's shared design doc.

For each cross-run decision not yet reflected in the design doc, append a `HANDOFF:` entry to `$RUN_DIR/followups.md` in the form:
```
HANDOFF: [D-N] <subject> — land in <design-doc path> before next run starts
```
Append each entry **idempotently** — only if that exact `HANDOFF: [D-N] …` line is not already
present in `$RUN_DIR/followups.md`. A ship crash in the narrow audit→commit window leaves the
tip still at `R == tip` (pre-ledger), so resume re-enters this forward-path audit; the idempotent
append means the re-run adds nothing (no duplicate `HANDOFF:` lines ride the eventual commit).

Because these entries are appended to `$RUN_DIR/followups.md` **before** the ledger-promotion append reads it, they ride that SAME single ledger commit into `.harness/followups.md` — never a second commit (which would strand them in the GC-swept `$RUN_DIR/followups.md` AND trip the `R..tip ≤1 commit` ship allowlist). Surface them at Gate B alongside the PR summary so the user sees what the next run must pick up. Do NOT block Gate B on unresolved handoffs — they are advisory, not a hard gate.

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
`reviewed-sha R` that is an ancestor of tip with `R..tip` ≤1 commit ⊆ the 4-file
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

**Portability advisory** (surface at Gate B alongside the diff summary): run
`bin/drive-portability-lint.sh <changed test/*.sh + bin/*.sh in baseRef..featureBranch>` and
surface any hits — commands the `macos-latest` CI runner lacks (`timeout`, GNU `g*` tools, …)
that pass locally (homebrew) but red on CI. **ADVISORY — it does NOT block Gate B** (the lint is a
grep heuristic, abstain-biased, exit 0 always; the real gate is the post-push CI-wait, step 1a).
It just lets the human catch a portability slip here and save a push→CI→red→fix round-trip.

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
   PR url to `state.ship.prUrl`. **PR-create IDEMPOTENCY (a resume after a CI-wait STOP
   re-enters here with the PR ALREADY open):** BEFORE `gh pr create`, if `state.ship.prUrl` is
   already set, OR `gh pr list --head <featureBranch> --json url` returns a non-empty result,
   SKIP the create and REUSE that PR url — a second `gh pr create` errors ("a pull request
   already exists"), so a naive re-create would wedge the resume before it re-reaches the
   CI-wait. Push is idempotent (fast-forward / `--force-with-lease` on a rebased resume).
1a. **CI-wait gate (post-push; BEFORE teardown) — a /drive run must not reach `stage=done`
   with red CI (the human no longer has to notice).** After the push + PR, run
   `bin/drive-ci-wait.sh --pr <state.ship.prUrl> --repo-root <repoRoot>` (GitHub/`gh` only —
   see the GitLab residual below) and map its exit code:
   - `0` (GREEN — CI started, all checks concluded non-failing) → proceed to teardown (step 2).
   - `2` (NO-CI — no `.github/workflows` and 0 checks, OR `gh`/`jq` unavailable) → best-effort
     PROCEED to teardown (never block a run for absent/unreachable CI — mirrors the base-preflight
     / notify fail-open posture). Note it at step 6's report.
   - `1` (RED — ≥1 check FAILED) → **STOP via the Present human pause routine** (drive.md §
     *Present human pause*; `waiting = "stop:ci-red"`), which fires the R3 notify so the human
     LEARNS CI is red. Surface the failing check names/links from the helper's stdout. Do NOT
     tear down, do NOT write `completedAt`/`stage="done"` — the run stays NOT-done /
     not-sweepable / resumable. **Recovery is NOT a bare re-push:** a fix to a `test/*.sh` /
     `bin/*.sh` / product file is a NON-ledger change that moves `featureBranch` past finalize's
     `reviewed-sha R`, so the run must **re-enter `/drive-finalize`** (re-review the new code,
     re-bind the terminal artifact) BEFORE re-shipping — else the ship gate's precondition #3
     (`R..tip ≤1 commit ⊆ ledger allowlist`) false-STOPs. (Surface the failing checks so the
     human can distinguish a required-check red — fix — from an advisory/optional red —
     approve-anyway.)
   - `3` (PENDING — max wait elapsed with checks still pending, or workflows-present-but-0-checks)
     → **STOP via Present human pause** (`waiting = "stop:ci-pending"`) reporting "CI still
     pending after N min"; re-runnable on resume (the CI-wait re-polls; PR-create is skipped per
     step 1's idempotency). NOT a red, NOT done.
   **GitLab residual (named, out of scope):** `drive-ci-wait.sh` is GitHub/`gh`-only. On a
   `glab`/GitLab-backed run, do NOT invoke it — the run degrades to the pre-existing
   behaviour (the human catches a CI-red at merge, as before). Provider-aware CI-wait is a
   follow-up; documenting it keeps this a NAMED residual, not a silent fail-open.
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
