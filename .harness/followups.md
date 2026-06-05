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

## Next-level gate review (2026-06-05) — Tier-2 gate hardening, DEFERRED

Found during the dual-voice (Claude + codex-adversarial) next-level review of the whole
`/drive` system. The resume/crash-recovery P1s and the `verdict_converged` first-line fix
(below) were FIXED in that session; these two gate-matcher items were deferred because they
touch the load-bearing enforcement matcher and the canonical `/drive` flow does not trigger
them — they want their own focused change with a reliable adversarial codex pass.

- **FIXED (not a follow-up, noted for context):** `bin/drive-conformance.sh` `verdict_converged`
  matched `## Verdict: CONVERGED` on ANY line, so a FINDINGS review whose body contained a later
  standalone `## Verdict: CONVERGED` heading counted as converged. Fixed to decide on the FIRST
  `## Verdict:` line only; regression test AC0b in test/drive-conformance.test.sh (proven to fail
  pre-fix).

- **[A — P2, gate matcher reads `-m`/message bodies as refs]** `bin/drive-merge-gate.sh:319,325`
  (`slice_tokens` / `phaseint_token`) and `drive_runid_from_command` (drive-hook-lib.sh) extract
  ref tokens by **raw grep over the whole command string**, so a `(drive|slice|phaseInt)/X/Y`-shaped
  token inside `-m '…'` is read as a real ref. Effects: (1) **false-block** — `git merge -m '…slice/run/4a…' main`
  (honest commit message mentioning a ref) gets the slice-merge gate wrongly applied → can DENY a
  legitimate merge; (2) **wrong-runId inert / evasion** — `git merge -m 'slice/no-such-run/x' slice/REAL/4a`
  keys runId off the first (fake) token → RUN_DIR absent → the real slice merge goes ungated.
  The PUSH path was already hardened against this ("never read flag VALUES as refs", drive-merge-gate.sh:200);
  the merge/branch path never got the same treatment. **Design:** build a filtered token stream — walk
  the tokenized args like `push_ship_runid` does, skip the VALUES of free-text flags (`-m/--message`,
  `-F/--file`, and `--message=`/`--file=` forms), and grep THAT for refs instead of the raw command.
  Must KEEP `-b <slice>` values (worktree-add carries the slice ref as `-b`'s value) — only the
  message/file flags get their value skipped. Closes both the false-block and the evasion. **Risk:**
  re-architecting the core matcher; a slip could UNDER-gate (real review-skip bypass). Needs the
  adversarial codex pass + tests: false-block case, evasion case, `-b` slice preservation, and all
  existing drive-merge-gate.test.sh cases still green. Canonical `/drive` never emits `-m` on merges,
  so not hit in normal operation. **Severity: medium.**

- **[C — P2/P3, Stop-guard backstop blind outside `drive/<runId>` HEAD]** `bin/drive-stop-guard.sh:41`
  resolves the run ONLY via `drive_runid_from_head` (drive-hook-lib.sh:88-104), which returns a runId
  only when HEAD is `drive/<runId>`. The canonical phase assembly runs merges from a
  `phaseInt/<runId>/<P>` worktree (and the main session may sit on `baseRef`), so the audit backstop
  is **inert exactly during assembly** — when an unreviewed merged slice would be present. The PRIMARY
  PreToolUse gate still covers this; only the best-effort Stop backstop is thinner than the docs imply.
  **Design:** broaden run resolution to also derive runId from a `phaseInt/<runId>/<P>` (and/or
  `slice/<runId>/<id>`) HEAD, or audit by scanning `~/.claude/harness-runs/*/` rundirs rather than
  trusting `.cwd` HEAD. **Severity: medium (defense-in-depth, not an omission guarantee).**

- **[Threat-model doc reframe — from the same review]** The codex adversarial pass showed the gate's
  documented boundary ("omission-proof, not forgery-proof") understates the real limit: trivial
  command-shape evasion (`bash -lc 'git merge …'`, `/usr/bin/git`, `git -c alias.x=…`, `git update-ref`,
  `git push <sha>:refs/heads/main`) bypasses the literal-string matcher with ZERO artifact forging.
  The honest framing is **"omission-proof, not evasion-proof,"** and raising the bar requires enforcement
  BELOW the shell (a `reference-transaction`/`update-ref` git hook or server-side check) — the real
  shape of the existing "component D" follow-up (see line 27). Update docs/drive-enforcement.md to say
  this. **Severity: low (doc honesty), but it reframes component D.**
