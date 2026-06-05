# Follow-ups

Out-of-scope discoveries during engineering tasks. Bugs unrelated to the
current task, refactor opportunities, suspicious code, dependency upgrades,
etc. Subagents and the main session APPEND here instead of pausing or
addressing inline.

The human reviews this file periodically and decides what to promote to a
real task.

## Entry format

### YYYY-MM-DD -- Short title
**Found during:** which task / stage
**Where:** file:line or area of the codebase
**Observation:** one or two sentences
**Suggested action:** what would be worth doing about it (optional)
**Severity guess:** low | medium | high

---

## Entries

(append below this line)
## From run drive-review-hooks-20260603-135659

- **Component D (forgery-proof driver):** rewrite the per-slice loop as a deterministic external driver (Workflow/shell) so review is a function call, not a remembered step, and proof is produced out-of-band. Only this defeats an adversarial coordinator that forges SHA-bound review artifacts. The hook-based C+A+B delivered here defeats OMISSION (the observed failure) with auto-remediation; it does not claim forgery-proofness.
- **Extend git-truth enforcement to IMPLEMENT-stage** (test-presence, etc.) using the same conformance pattern.
- **2.1 gate matcher hardening (exotic git global-option forms):** `git_target_repo()` treats `-C`/`--git-dir`/`--work-tree` as last-path-wins; git actually *composes* stacked `-C a -C b` and `-C /repo --git-dir=.git`. The gate can wrong-target on these. /drive never emits `-C` forms (it cd-s into worktrees), and the ship gate (HEAD/whole-tree) backstops any merge-gate miss, so this is hardening vs adversarial/pathological input, not an omission-threat gap. Fix: model composed git path options properly.

## Run: comprehensive test plan (run harness-tests-20260604-070040)

F1 done.py: exit-3 "no frontmatter" branch (mark l.116-118) is unreachable — _resolve already
   requires type:task frontmatter. Frontmatter-less file => exit 2. Remove dead branch or document.
F2 mc-bind.sh / mc-hook.py do not mkdir -p ~/mission-control before appending. Fresh-machine hazard
   (mc-bind set -euo crashes; mc-hook silently no-ops). Tests seed the dir via seed_mc_home.
   NOTE: main's mc-bind.sh changed (+18) — re-check whether main already added mkdir -p in Phase 3.
F3 install.sh launchctl/defaults/open are guarded (2>/dev/null || true) -> exit 0 in sandbox. Watch.
F4 No CI wiring (e.g. .github/workflows running pytest -q). Out of scope; recommend as follow-on.
F5 INCIDENT: a branch-name-keyed cleanup deleted this run's RUN_DIR + git branches when the
   chore/distribution-readiness branch was merged/deleted concurrently. Future /drive runs should
   avoid run-ids derived from a branch that may be merged+swept mid-run (use a task-derived id).
F6 (P3 harden phase1, deferred) Drifted `module.py:NN` source-line citations in test comments:
   test_bucket.py (vault_tasks.py:170/177 -> backlog append is :174, waiting bucket :180),
   test_done.py:174 (done.py:45-46 -> .md strip is :47-48), test_weekly.py:62,92 (weekly.py:26/41-48),
   test_session_summary.py:87,95 (session_summary.py:62-64/72). Cosmetic, will silently rot. Fix by
   citing the function name instead of the line number when those files are next touched. Not fixed
   here: harden scope was the goal-precedence + de-slop fixes; editing 4 unrelated files for cosmetic
   comments would exceed the cheap-blast-radius bound.

## Quality-pass deferrals (chore/quality-pass) — RESOLVED in fix/merge-gate-git-dir-and-dedup
- ~~drive-merge-gate.sh `--git-dir`/`--work-tree` mis-targets~~ — INVESTIGATED, NOT A BUG. conformance
  runs `cd "$REPO" && drive-conformance` doing only SHA/ref ops (rev-parse, for-each-ref, diff R..tip,
  merge-base --is-ancestor, symbolic-ref HEAD); these resolve IDENTICALLY whether CWD is a worktree
  root or a `.git` dir (verified empirically). Decision via --git-dir/--work-tree matches the bare form
  (deny unreviewed / silent reviewed / inert non-drive). LOCKED IN by 5 regression tests in
  test/drive-merge-gate.test.sh (both `--opt=val` and `--opt val` forms).
- ~~factor the 4x copy-pasted skip loop~~ — DECLINED (per scope-creep gate). Reviewed: the 4 scanners
  share only an env-prefix skip + a generic option table, but each does something genuinely different
  after (find subcommand / find action word / CAPTURE the -C/--git-dir value / scan refspecs); the
  shared part is small and the parser is safety-critical + heavily tested. A pure-DRY refactor of working
  enforcement code without a flagged P1 is net-negative risk. Left as-is intentionally.
- NOTE (still open, pre-existing): composed git path options (`-C a -C b`, `-C /repo --git-dir=.git`)
  use last-wins; git composes. /drive never emits these; ship gate (HEAD/whole-tree) backstops. See
  line 29. Genuine hardening vs adversarial input, not an omission gap.

## Run run-graph-20260604-164012 — Emit run graph (2026-06-04)
- [run-graph] OPTIONAL enhancement: persist codex review output per-round
  (`codex-review-<scope>-N.md`) IN ADDITION to the canonical bare `codex-review-<scope>.md`
  (keep the bare file so bin/drive-conformance.sh stays green). Would let the run graph show
  the codex P1 count for HISTORICAL rounds too, not only the terminal round. Current design
  handles this structurally (non-terminal rounds are FINDINGS by construction; `Codex —`),
  which is correct but loses historical codex counts. Low priority.

## Run main-20260604-223428 (autodrive quality sweep) — 2026-06-04/05


## Out-of-scope discoveries — hardening-sweep planning (main-20260604-223428)
- The repo has no CONTRIBUTING.md / dev-setup doc; testing instructions are absent entirely. Partially addressed by the planned README Testing section, but a fuller contributor guide is a separate follow-up.
- Component D (out-of-band, forgery-proof reviewer) is referenced in OPERATING.md/docs as a known limitation of the omission-proof (not forgery-proof) enforcement — remains a future work item, not part of this sweep.
- mission-control runtime is macOS-only (launchd/SwiftBar/iTerm/osascript); no portability layer. Out of scope here; note if cross-platform support is ever wanted.
- [P3, slice 1.1] test/drive-conformance.test.sh AC1 hermetic fixture now resembles the AC5 ship-absent-featureBranch case; optionally build a distinct ship-shaped fixture (phase-review artifacts + intentionally missing drive/<runId>) so AC1 is distinct coverage, not near-duplicate. Non-blocking.
- [P3, phase1 harden] Add a one-line note to bin/drive-stop-hook.py layered-guards docstring that DRIVE_STOP_HOOK_PATHS is a test-only scan-scope seam (no-op unset, fail-open-only if set), so a trust-boundary auditor sees it at the top of file.
- [doc drift, from 2.3 review] mission-control/skills/harvest/SKILL.md (~lines 67-69) still references the nonexistent `--prep` standup flag — same drift as the README fix (slice 2.3 owned only README). Fix the SKILL.md reference too.
- [doc drift, from 2.1 review] tests/_helpers.py:seed_mc_home docstring still says the scripts "never mkdir it (followup F2)" — stale after the 2.1 makedirs fix; update the docstring.
- [P2, slice 2.3 -> phase-2 harden] mission-control/README.md:95 launchd-job row understates the 6:45am job (`harvest --log`); real run is `standup --draft` + `harvest --log --summarize`. Align line 95 to morning.sh in harden.
- [P2, slice 2.5] standalone `--unbind` note at mission-control/README.md:31 isn't pinned by the contract test (no command anchor). Rewrite that doc mention to `mc bind --unbind` form in Phase-2 harden, or add a targeted rule.
- [P3, slice 2.5] test_cli_flag_doc_refs.py is a doc-scanning HEURISTIC, not a hardened parser: latent edge cases (space-separated `/mc a b c`, bare alias words followed by a real flag in a code span) could mis-attribute. None present in current docs. If the contract test ever false-fails/masks, consider narrowing its scan to a structured surface (the README Commands table + mc help) rather than free prose.
- [Phase-2 harden] Normalize bare Mission Control command forms in mission-control/README.md to `mc `-prefixed (`mc standup --draft`, `mc harvest --log --summarize` at :95,:141; the `--unbind` note at :31 → `mc bind --unbind`) so the round-4 mc-prefixed-only contract test covers them. (User chose the structural fix: robust test + mc-prefixed docs.)
- [P3, phase2 harden] _mc_help_heredoc anchors to help|-h|--help) but is not bounded to that arm; bound extraction to the arm terminator (;; / next case label) so a future heredoc in a later arm cannot be mis-bound. Latent (help arm has the only heredoc today).
- [P3, slice 3.1 -> phase-3 harden] README ## Testing `tests/` coverage cell understates scope ("Mission Control + the hooks"); tests/ also has contract (test_drive_command_refs, test_cli_flag_doc_refs) + installer tests. Broaden the cell.
- [P2, Phase-1 test robustness] tests/hooks/test_drive_stop_hook.py multi-run masking regression tests (the waiting/disabled/nondict-before-active cases) rely on the DRIVE_STOP_HOOK_PATHS seam to order the hazard first; if the seam ever stops taking effect they false-pass (run-mine/run-active sort before run-nondict/waiting/disabled naturally). Rename the fixture dirs so the hazard sorts FIRST even without the seam (or add explicit seam-activation assertion), so the tests keep proving the Phase-1 masking fixes.

## Run drive-followups-20260605-085318 — 2026-06-05
(promoted from $RUN_DIR/followups.md)

# Followups — drive-followups-20260605-085318

## Out-of-scope discoveries (design stage, 2026-06-05)

- [B / F6 remainder] The `module.py:NN` source-line citations in
  `tests/mc/test_weekly.py` (weekly.py:26/41-48), `tests/mc/test_session_summary.py`
  (session_summary.py:62-64/72), and `tests/contracts/test_cli_flag_doc_refs.py`
  (harvest.py:309/13) are the SAME rotting-citation class as F6 but are out of this batch's
  scope (task §B + F6 name only test_done.py / test_bucket.py). Fix by citing the function
  name when those files are next touched.

- [C residual, → Component D] Item C's test-presence gate is omission-proof, not
  forgery-proof: a trivial/empty test file (`def test_noop(): pass`) passes the gate. Quality
  (does the test exercise the slice's code) belongs to the harden phase's "add missing tests"
  lens and to Component D (out-of-band forgery-proof reviewer). Documented as a known residual.

- [C residual] `$GIT_DIR` / `$GIT_WORK_TREE` env-var repo targeting is NOT modeled by the
  gate (Item A scopes to the attacker-influenced command STRING, not the gate's own env;
  /drive never sets them). Known residual; note in docs/drive-enforcement.md.

## Run drive-followups-20260605-085318 — harden targets
- [P1 harden] test/fixtures/mkfixture.sh mk_linked_worktree() is dead (AC-A10 tests build the
  gitfile worktree inline). Drop it or wire AC-A10 through it. (Claude slice-1.1 review MINOR.)
- [DONE in r3] bin/drive-merge-gate.sh + docs/drive-enforcement.md comment inaccurately
  claimed a trailing bare backslash makes the shell reject the command; only unterminated
  QUOTES do. FIXED (item d): scoped the claim to quotes; trailing backslash now finalizes
  inert (matches bash `git push \`). (Claude slice-1.1 r2 review MINOR → resolved r3.)
- [P3, → Component D] sudo/env-WRAPPING of the binary is not recognized: `sudo git $'push'`
  / `env git push` have START binary `sudo`/`env` (not git), so the gate (incl. the new
  fail-closed catch-all) is inert. Same forgery/evasion class as the documented
  $GIT_DIR/symlink residuals — /drive never wraps its git calls; an out-of-band reviewer
  (Component D) is the real defense. Noted while implementing r3 fail-closed. (slice-1.1 r3.)
- [P3, → Component D] single-quoted `'~/repo'` is still tilde-resolved by git_target_repo's
  expand_tilde to $HOME/repo, but bash does NOT expand `~` inside single quotes (it's the
  literal dir `~/repo`). Marginal mis-resolution, non-exploitable (literal `~/repo` ~never
  exists → git errors → nothing ships). Threading quote-context into git_target_repo's tilde
  resolution would close it; deferred as gold-plating. (slice-1.1 r3 codex F4 residual.)
- [P3 harden] drive-merge-gate.sh:90 + docs/drive-enforcement.md:194-195 overclaim brace `{..}`
  RANGE detection (lexer flags only comma-in-brace). Not a bypass. Correct to comma-form-only, or
  add `.`-in-brace detection. (Claude slice-1.1 r3 MINOR.)
- [P1 harden Phase-1] drive-merge-gate.sh expansion taint scan: handle the ATTACHED short-option
  form `-b<val>`/`-B<val>`/`-c<val>` (checkout/switch/worktree add) — git accepts `-bslice/x`
  attached; the scan only checks `-b <sep>`/`-b=<eq>`. Taint-check the embedded value. Forgery-
  class (/drive uses separate literal form) but cheap + concrete. (codex slice-1.1 r4.)
- [HIGH followup — own run] gh/glab ship-detection keys runId off cwd HEAD, not an explicit
  `gh pr create --head <branch>` / `glab mr create --source-branch`. Pre-existing; push-gate
  backstops it (branch must be pushed first). Audit the gh/glab ship path for --head/--source-
  branch targeting in a dedicated run. (codex slice-1.1 r4.)
