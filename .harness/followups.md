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

## Quality-pass deferrals (chore/quality-pass) — enforcement scripts, separate PR
- drive-merge-gate.sh: `--git-dir`/`--work-tree` relative-path resolution feeds `cd "$REPO"` then worktree-relative `git diff` in conformance; for a `--git-dir` (bare git dir) this can mis-target. Drive emits `git -C`/plain push so low-likelihood, but harden: pass --git-dir/--work-tree through to the conformance git invocation instead of cd-ing. (P2, needs its own dual-voice PR.)
- drive-merge-gate.sh: the env-prefix + git-global-option skip loop is copy-pasted 4x (detect_subcommand/action_after/git_target_repo/push_ship_runid) and already slightly out of sync; factor one `_skip_to_subcommand` helper. (P2 refactor; no flagged P1, so deferred per scope-creep gate.)
