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

## Per-phase design gate (phasedesign-gate) — adversarial findings (2026-06-05)

Added the omission-proof per-phase design gate (Tier-2): a `git worktree add -b slice/<runId>/<id>`
now fires `phasedesign-gate:<P>` (P = id prefix before first `.`) requiring the phase's
`review-phasedesign<P>` converged + codex, mirroring plan-gate, fail-CLOSED. The honest-coordinator
OMISSION case is now gated (the goal; proven by AC0c conformance tests + merge-gate + e2e). The
adversarial codex pass surfaced three **pre-existing** matcher weaknesses that affect the EXISTING
plan-gate IDENTICALLY (`bin/drive-hook-lib.sh` is unchanged by this work) — they are deliberate-EVASION
(the threat model is "omission-proof, not evasion-proof"), the canonical `/drive` flow never triggers
them, and the ship gate backstops. Log here as matcher-hardening, NOT closed:

- **[matcher, P2] runId keyed from the first `slice/...` token anywhere in the command (incl. the
  worktree PATH), not the `-b` branch arg.** Attack: `git worktree add ../slice/evil/1.1 -b
  slice/<realRun>/1.1` → `drive_runid_from_command` returns `evil`; if `~/.claude/harness-runs/evil`
  absent → gate inert → real build ungated. Normal flow safe: `$RUN_DIR/wt/<id>` paths carry no
  `slice/` token, so runId resolves from `-b`. Root: full-command token scan + first-hit selection in
  drive-hook-lib.sh:60,80 (UNCHANGED by this diff — affects plan-gate too). Fix: derive runId from the
  `-b` value specifically for worktree-add; or parse argv structurally below the shell.

- **[matcher, P2] non-canonical slice-create forms bypass the gate entirely.** `git branch
  slice/<runId>/1.1 HEAD` then `git -C ../wt switch -c slice/...` — `branch`/`switch` are not gated
  modes and the `worktree add --detach` carries no `slice/` token, so `is_plan_gate` never sets.
  Bypasses plan-gate AND phasedesign-gate. Pre-existing (plan-gate only ever fired on `worktree add -b
  slice/...`). Fix: gate all ref-create paths that yield a `slice/<runId>/<id>` branch, or enforce
  below the shell (ties to the existing component-D / below-the-shell follow-up).

- **[matcher, P3] over-gating: any `worktree` subcommand with any `slice/` substring trips the gate.**
  `git worktree remove ../x/slice/<runId>/1.1`, `git worktree move …`, `git worktree add ../wt
  origin/slice/…` all false-trip plan+phasedesign. Pre-existing in the `git_sub=worktree && slice_tokens`
  detection; this diff widens it to also run phasedesign-gate. SAFE direction (false-block, not a hole)
  and normal flow unaffected (`/drive` removes use `$RUN_DIR/wt/<id>` paths, no `slice/` token). Fix:
  match specifically `worktree add … -b slice/<runId>/<id>` (the `-b` VALUE), not any slice substring.


## Run lever2-rebirth-20260610-145705 (2026-06-12) — proactive-rebirth trigger (lever 2)

## Phase 1 detailed-design refinements (design-review P2s, non-blocking)
- [P2] Stranded in-flight marker liveness: a process dying after marker-write but before dispatch leaves an open marker with nothing live. Fail-closed (reads "unsafe"), but Phase 1 must state the recovery: re-dispatch-or-STOP, not "wait for a worker." (codex-review-design.md)
- [P2] `max(state, artifact-count)` vs "never read state.json": state is a resume-repair HINT, never a proof input. Phase 1 must say this explicitly so the two rules don't read as contradictory. (codex-review-design.md)

## Phase 1 detailed design — out-of-scope discoveries
- [P3] Legacy runs (artifacts predating phase 1) have no in-flight/epoch markers: marker absence reads as "safe" and `redesigns` falls back to the state hint. Acceptable residual (such runs never had marker discipline); document in docs/drive-enforcement.md in Phase 4.
- [P3] design.md cites the stop-hook sessionId match as drive-stop-hook.py L97; in current code it is L116. Stale line reference only — behavior as described. Fix opportunistically in Phase 4 docs.
- [P3] Pre-existing hole closed as a side effect of epoch-aware phasedesign-gate (slice 1.1): today a stale pre-redesign CONVERGED review-phasedesign<P>-N.md satisfies the gate after a REDESIGN invalidated that design. Worth a one-line callout in docs/drive-enforcement.md (Phase 4).
- [P2] design-phase1 I2 vs I8: bind WHO writes `inflight-review-phasedesign<P>[-r<R>].marker` at the gate-deny remediation dispatch point (normal flow is bracketed by the outer `inflight-design-<P>` marker). One-sentence binding; slice 1.2 implementer should fold it in. (review-phasedesign1-3.md) **RESOLVED (slice 1.2, D20):** the coordinator writes/clears it around the remediation `/drive-review` call — bound in drive.md's Stage-2–4.5 gate paragraph.

## Slice 1.2 review — out-of-scope discoveries
- [P3] drive-review.md frontmatter `argument-hint` (`design | slice <id> | phase <P> [harden-regress]`) omits the `phase <P> design` invocation form the body documents (and which /drive-design uses). Pre-existing drift, not touched by slice 1.2. One-token fix.

## Phase-1 integration review — MUST verify (cross-slice contract, codex-flagged at slice 1.2 review)
- The prose in drive.md/drive-review.md (slice 1.2) describes `--mode checkpoint` and the epoch-aware `phasedesign-gate:<P>` (`phasedesign<P>-r<R>`). These are implemented in bin/drive-conformance.sh by slice 1.1. Slice-level review of 1.2 could NOT see 1.1's script (separate worktrees). At phase integration (both merged), CONFIRM prose ↔ script agree exactly: mode name, gate scope-token, violation names (epoch-unmarked, regress-mismatch, epoch-gap), and the checkpoint ref-ancestry contract. (codex-review-1.2 r3)

## Harden phase — optional pin tightening (slice 1.3, codex r5 residual, non-blocking)
- [P2] In test_checkpoint_contract.py, the drive-review.md half-B pin (harden-regress writes into the same review-phase<P>-N family) could bind the CONCRETE filename family token rather than a looser "same review" narrative — defense-in-depth. NOT a guard hole: Claude verified the family-reroute permutation reds the test, and the live-script behavioral cross-check guards the consequence. Tighten during harden if cheap. (codex-review-1.3 r5)

## Pre-existing — impl-presence test-evidence path-segment check (codex phase-1 harden, OUT OF SCOPE)
- [P1] `bin/drive-conformance.sh::is_test_path()` (~L247) rejects a dot-prefixed BASENAME but not a dot-prefixed path SEGMENT: `tests/.hidden/test_x.py` (or any hidden/nested-under-a-dotdir test) passes the `tests/**/test_*.py` pattern and counts as test evidence, yet pytest (`testpaths=["tests"]`) skips hidden directories — so it is NOT runnable coverage and the impl-presence gate false-passes. PRE-EXISTING: the impl-presence logic was added by `5870db5`, not this phase (the phase diff only added `checkpoint` to the usage line); routed here per the scope-creep gate, not touched in this harden. Fix: validate that NO path segment is dot-prefixed (e.g. reject `case "$p" in (*/.*/*|.*/*) return 1;; esac`), mirroring the existing dotfile-basename rejection, with a fixture asserting `tests/.hidden/test_x.py` → violation. (codex phase-1 harden)

## Phase 4 (docs) — MUST update docs/drive-enforcement.md (codex phase-1 integration finding)
- [P1→Phase4] docs/drive-enforcement.md (~L43, ~L91) is STALE vs the conformance script this run shipped: it omits `--mode checkpoint` and still documents the bare epoch-0 `phasedesign<P>` gate family instead of the current epoch-aware `phasedesign<P>[-r<R>]`. Phase 4's docs pass MUST bring it current (add checkpoint mode + the epoch-aware gate + the new violation names epoch-unmarked/regress-mismatch/epoch-gap). Out of phase-1 boundary (docs = phase 4). (codex-review-phase1 r2)

## Phase-id naming constraint (harden phase-1 residual, by-design fail-closed)
- [P2] The epoch naming scheme uses `-r<digits>` as the epoch delimiter, so a phase id ending in `-r<digits>` is ambiguous vs an epoch suffix. The conformance gate now fail-closes (flags) such ids rather than mis-handling them, making `-r<digits>`-suffixed phase ids effectively unsupported. Canonical fix = constrain/validate phase ids to exclude a trailing `-r<digits>` at the source (drive.md phaseList parse) + assert it once. Out of phase-1 harden scope. (harden-1-2, codex harden-regress)

## Phase 2 (detection) — out-of-scope discoveries
- [P3] Threshold tuning: hard 0.85 / soft 0.75 are safe defaults, not model/usage-optimal numbers (design.md L348). A real run should measure the typical per-turn growth between safe boundaries and tune the fractions so the headroom is "exactly one clean checkpoint" rather than conservative. Out of Phase 2 scope.
- [P3] Window table completeness: an unknown model falls back to defaultWindow=200_000 (conservative — earlier-firing, never a missed limit). When a new large-window model ships, add one `windows[].match` entry to `bin/rebirth-thresholds.json`. Phase 4 docs should note this one-line maintenance point.
- [P3] Acknowledged D6 residuals to DOCUMENT in Phase 4 (docs/drive-enforcement.md or a rebirth section): (i) single-catastrophic-turn overshoot — the Stop-hook steer fires at turn END, so one enormous turn can exhaust the window mid-turn before any steer/boundary; (ii) absent-hook degradation — the Stop hook is the SOLE detector (the coordinator soft-check fallback was removed for over-triggering false handoffs), so with no Stop hook installed there is NO context-pressure detection.
- [P3] Phase 4: confirm no installer change is needed — `bin/rebirth-thresholds.json` is reached by sibling path from statusline.sh/drive-stop-hook.py (bin/ is canonical-by-reference). If a future deploy ever copies the hook to a non-sibling location, the data-file path resolution breaks; assert the sibling layout once.

## Phase 4 — cross-command /goal rebirth-pause clause (slice 3.1 codex P1 residual)
- [P1→Phase4] The /goal templates in drive-plan.md (Gate A leg-2, ~:96) and drive-ship.md (Gate B re-arm) must ALSO admit a rebirth pause as a satisfying state ("OR is paused at a rebirth handoff (waiting=\"rebirth\") awaiting my paste of the resume line"), matching the drive.md templates slice 3.1 fixed. Otherwise a user-pasted leg-2/Gate-B goal would force the session past a rebirth handoff. Out of slice-3.1 scope (owns drive.md only); Phase 4 (docs/install/cross-command wiring) owns these files. (codex-review-3.1)

## Phase 4 detailed design — out-of-scope discoveries
- [P3] Deep state.json validation (cross-checking every slice's `owns`/`deps` graph against git refs, verify-attempt/ship-field VALUE consistency) is out of `--mode state-lint` scope — state-lint validates parses + routing fields PRESENT + WELL-FORMED (type/shape) only, the subset resume actually keys on. Full graph cross-validation is a follow-up, not a blocker (D40).
- [P3] Optional belt-and-suspenders: a one-sentence Gate-B cross-reference in drive-ship.md that a rebirth handoff during ship is governed by the leg-2 goal's rebirth-pause clause. Non-load-bearing (the leg-2 clause already covers it, D41); add only if a reviewer insists.
- [P3] Threshold-value empirical tuning (hard 0.85 / soft 0.75 → measured one-clean-checkpoint headroom) remains a follow-up (carried from Phase 2 followups; documented in Phase 4 docs as a residual, not tuned here).

## state-lint deps/owns GRAPH cross-validation (design-scoped out, D40)
- [P2] --mode state-lint validates deps/owns SYNTACTICALLY (each element a valid slice-id string). It does NOT do deep GRAPH cross-validation: a dangling dep (deps:["9.9"] with no slice 9.9), a self-ref (deps:["1.1"] in slice 1.1), or an unresolvable owns graph passes state-lint. The phase-4 design (D40) explicitly scoped deep owns/deps graph cross-validation OUT of state-lint (the goal was present/well-formed routing fields, not full graph consistency). Add a deps/owns graph validator (resolve every dep to an existing sibling, no self-ref, acyclic) as a follow-up if the resume path needs it. (codex 4.2 r4)
- [P3] test_rebirth_e2e.py honest-scope docstring: the resume-sequence narration still lists clear-waiting LAST, but the fix clears waiting BEFORE rebind. Reorder the narration. (codex 4.1 r3, harden)
- [P2] stale docstring "via --mode checkpoint" at tests/contracts/test_rebirth_handshake.py:578 (the assertion below correctly pins both modes) — reword. (codex/claude phase4 r2, harden)
- [P2] state-lint gained a `waiting-malformed` violation (harden phase4 P1-A): add this violation name to the drive-enforcement.md violation list (docs/ owned by another slice; the conformance script + tests carry it now). (harden 4 fix round)

## Over-design audit — deferred "leaner-rebirth v2" cuts (lever2-rebirth, 2026-06-12)
A dual-voice over-design audit (Claude: "mildly-to-moderately over-built"; codex: "massively
over-designed") ran at pre-ship. The CORE (stop-hook detection, checkpoint proof, routable-state
validation, fresh-session handoff) is load-bearing. Done in THIS PR: removed verified dead code
(latest_usage_tokens delegated, latest_model deleted) + the decoupled-safe test trim (flip-proof
twins, granular prose pins, jq-matrix-subsumed drift tests) — ~750 lines, behavior-preserving.
DEFERRED here because each is coupled to a production-logic simplification or is a load-bearing
executable proof — do them as one coherent pass that cuts logic AND its tests together:
- [P2] Epoch-redesign machinery in drive-conformance.sh (redesign-<P>-r<R> markers, epoch-unmarked/
  epoch-gap violations, highest-epoch reconstruction): edge-case hardening for redesign-DURING-rebirth,
  a path with 0 real occurrences. Simplify to basic current-epoch awareness; cut its tests in
  test_checkpoint_contract.py + mkfixture mk_checkpoint epoch cases together. ~140-250 logic + ~250 test.
- [P2] state-lint deep validation drifts toward full-schema policing (verify/ship/per-slice grammar,
  future-stage fields). Narrow to the routing fields resume actually keys on (parse+object, stage enum,
  waiting grammar); cut mk_state_lint exhaustive fixtures (~408 lines) with it. ~80 logic + many fixtures.
- [P2] Duplicate behavioral coverage of checkpoint/state-lint: both the bash suite (drive-conformance.test.sh
  + mkfixture) AND the python contract tests exercise the same modes. Keep ONE executable layer. ~600-800,
  but verify per-case overlap first (the bash suite is the pre-existing security-gate guard).
- [P3] rebirth_thresholds.py jq/statusline byte-parity (~120 logic + ~250 test, the _DRIFT_SHAPES matrix):
  exact-parity is rigor for a signal-only nudge. Claude DEFENDS it (AC6 keeps hook ↔ statusline numbers
  identical so the user isn't shown two token counts). Decide intent before cutting.
- [P3] e2e granularity (~400) — codex would cut to ~4 integrated tests; Claude calls it the single most
  valuable test (the only executable proof of the chain). Lean KEEP; trim only redundant stepwise negatives.
- [P3] Cross-file rebirth prose duplication across drive.md/drive-plan.md/drive-review.md (~150-250):
  collapse into one authoritative section. Coupled to the prose-pin tests.
Audit artifacts: $RUN_DIR/codex-overdesign-audit.log + the Claude audit in the session transcript.

## Run harden-20260612-210528 (2026-06-13) — finalize stage

# Follow-ups (promoted to .harness/followups.md at ship)
## slop-label-drift (P2, non-blocking) — drive-harden.md reviewer-prompt ~L119 says 'slop (deferred)'; canonical followups heading is 'slop (deferred to finalize)'. Align for tidiness; finalize consumes the correct heading so behavior is unaffected.
## main-tree leak (process) — a slice implementer edited main's .claude/commands/drive-harden.md (absolute-path hazard) despite cwd=worktree; coordinator restored main to clean. Slice branch content was intact. LESSON: verify main tree clean after parallel slice dispatches.
## drive-harden.md vestigial Veto wording (P2) — '## Findings ... / Veto?' schema field + 'vetoed items' in Step-3 STATUS line are leftovers from when de-slop could be VETOED; no actionable veto remains in the 2-lens model. Cosmetic.
## drive-finalize.md FINALIZE_CAP soft for P2 (P2) — the cap-3 STOP fires only on cap+open-P1; a lens-1 P2-slop-only round can exceed 3 fix rounds. Mirrors harden's HARDEN_CAP convention; consider tightening both consistently if it ever loops.
## Phase 3: pin finalizeRound in tests/contracts/test_state_json_shape.py CORE_KEYS (codex 2.4 P2) — the new top-level run-state field is currently unguarded; add it so drift (drive.md example or CLAUDE.md enumeration dropping finalizeRound) reds the contract test.
## Phase 3: re-pin ship negative branches AC4.ii/iii/iv (codex 2.5 P2) — they now short-circuit at no-review (no finalize artifact) and assert only a generic exit 1; seed a CONVERGED finalize R that violates each (a)(b)(c) condition (code-past-R / non-allowlisted file / >1 commit) so the finalize-R ship logic is pinned.
## Phase-3/cosmetic: 2 stale comments in test_rebirth_handshake.py (~L616, L675) still say (execute,verify,ship) without finalize — non-load-bearing comment text.
## Phase 3: update 'five I3 rules' → six (mkfixture.sh:562, test_checkpoint_contract.py:499/514) and add a python pin for the finalizeRound (6th counter) reconstruction rule — currently documented in drive.md/drive-finalize.md but not asserted by a test (codex/Claude phase-2 P2).

## harden phase 2 — deferred (not applied this stage)
- [P2 slop, VETOED] finalize-CONVERGED rule appears in 3 surfaces (drive.md ~L113,
  drive-ship.md ~L17, CLAUDE.md ~L131). Codex proposed collapsing to one canonical
  rule + cross-ref. NOT applied: D26 mandates the 3 surfaces be IDENTICAL and each is
  an independently load-bearing gate surface; a cross-ref refactor risks dropping a
  load-bearing clause (ancestor-of-tip / allowlist subset / ≤1 commit / phase-review
  precondition) from one surface — the exact drift D26 closed. Revisit only as a
  whole-doc DRY pass with a test pinning the three surfaces equal.
- [P3 cosmetic] test/drive-merge-gate.test.sh fn `test_ship_deny_names_phase_not_ship`
  (+ its main() registration comment) still says "phase" but now asserts /drive-finalize.
  Rename to `test_ship_deny_names_finalize_not_ship`. Cosmetic; defer (harden never fixes P3).

## de-slop-before-ship (pre-finalize run — residuals deferred, cannot land post-harden commits)
This run implements the finalize stage but EXECUTES the pre-finalize pipeline, so featureBranch tip == the
phase-3 review's reviewed-sha (R==tip). A de-slop commit would make R..tip a non-ledger code change →
breaks the ship gate's `R..tip ⊆ ledger-allowlist` invariant (no finalize artifact exists to re-cover the
tip in a pre-finalize run). So end-of-run de-slop has nowhere to land — exactly the gap /drive-finalize
closes for FUTURE runs. Residuals deferred:
- [P3 slop] bin/drive-conformance.sh:448 — ship-case banner comment still states the pre-fix "EXISTS a
  counting phase/integration review" model; the logic at :484 correctly uses the finalize candidate-R +
  no-phase-review precondition. Stale comment, no behavior impact. (codex phase3-r5 MINOR; D33.)

## /drive resume-router hardening (PRE-EXISTING; surfaced by codex during the finalize-feature reconcile)
Not introduced by this feature (verified against main's pre-finalize drive.md); the feature's own paths are
made SAFE by the round-2 idempotency fixes. A focused follow-up should tighten the EXISTING resume design:
- [P2] drive.md resume router (§ Current phase) has no explicit `stage = ship`/`stage = done` route — a
  gateB/suite-red resume re-enters via verify (harmless passthrough; ship is now idempotent). Add explicit
  ship/done routes so the 4 resume surfaces agree end-to-end.
- [P2] drive.md worktree classifier classifies wt/* by checked-out branch, but wt/finalize AND wt/ship are
  both on featureBranch — add an explicit `wt/ship` case (path-aware), mirroring the new wt/finalize rule.
  (Ship already force-cleans wt/ship on entry, so this is a clarity/robustness cleanup, not a live bug.)

## Run drive/runid-collision-guard (2026-06-21) — runId collision hardening

- **[P3, pre-existing] `<branch>` slug normalization into the runId is unpinned.** drive.md
  generates `runId = <branch>-<timestamp>` but never specifies how `<branch>` (the
  task-derived slug) is normalized into a single git-ref-safe / path-safe segment. The new
  atomic `mkdir` claim makes a *colliding* id safe (disambiguate or STOP), but two
  *different* tasks could still normalize to the same slug, and an unsanitized slug could
  yield an illegal ref/path. Surfaced by codex during the collision-guard review.
  **Suggested:** pin a deterministic slug rule (lowercase, `[a-z0-9-]`, collapse/truncate)
  where runId is minted. **Severity:** low.


<!-- ===== promoted from /drive run drive-retention-hygiene-20260622T073209 (2026-06-24T01:35:55Z) ===== -->
# Followups — drive-retention-hygiene

- MANUAL ONE-SHOT: 166 loose /tmp/codex_*/autoplan_* scratch files (~ad-hoc interactive, NOT pipeline-emitted) — sweep manually with `trash /tmp/codex_* /tmp/autoplan_*`. Not pipeline scope (D5).
- VERIFY (phase design): confirm the codex CLI honors TMPDIR for its own session scratch before adding the optional TMPDIR=$RUN_DIR/tmp export to drive-review.md (+ other direct-codex callers); if it does not, drop the edit as inert (Open Q2).
- OUT OF SCOPE (noted): decant Step 7 (#57) already owns registered-worktree + merged/closed-branch pruning; this task must not duplicate or touch branch pruning.
- DISCOVERY: this retention branch forked from #56 (781913f), BEFORE #57 landed on main (0fd3310). #57's decant Step 7 will be in the merge base — design assumes its presence and stays non-overlapping. Implementer should confirm no merge conflict in skills/decant/SKILL.md (this task does not edit it).

- PHASE-2 HANDOFF (from phase-1 design): the live `merge-base --is-ancestor <baseRef>` Tier-W ancestry backstop is DEFERRED to Phase 2's --apply path (Phase 1 reports skip:no-completedAt-and-no-ancestry instead of fabricating an ancestry verdict with no consumer). Phase 2 must add the ancestry probe in the owning repo AND handle a missing remote-tracking baseRef as ancestry-unprovable => SKIP (design.md Repo-ownership bullet).
- GROUND-TRUTH (phase-1 design, verified on disk): state.repoRoot is null on every existing run; registered wt/<name>/.git is a gitdir-pointer file (e.g. `gitdir: /Users/.../unity2rbxlx/.git/worktrees/wt`); no completedAt markers exist yet; event-log lines carry `"at":"<ISO8601 Z>"`; trash is /usr/bin/trash. Reusable teardown mechanics: `git worktree remove --force <dir> 2>/dev/null; git worktree prune` (drive-ship.md:44, drive.md:938) — Phase 2 CALLS these, Phase 1 does not.

## Slice 1.1 round-2 — deferred
- **missing-jq / missing-git tool-absence pins.** The script handles a missing jq (notice + exit 0, :81) and missing git (W4→`ancestry-unprovable`, W7b→`unreadable`, fail-safe) correctly and the reviewer verified both live, but no test pins them. A PATH-restricted simulation (hiding jq/git) wasn't added this round to avoid a brittle env-mutation pattern that could falsely red on CI hosts lacking a clean way to shadow tools. The dangling/unreadable `.git` fail-safe IS pinned. Consider a `PATH=`-shadowed test or a `_helpers` tool-absence harness if the cleanliness/jq guards are touched again.

## Slice 1.1 round-3 — deferred (residual, NOT a fail-open)
- **W7b reflog-only unpushed gap (acceptable NIT, Phase-2 awareness).** `wt_cleanliness`'s `git log --all --not --remotes` covers HEAD + branches + tags + refs/stash, but NOT a commit reachable only from the reflog (HEAD was `reset --hard`/`checkout`'d off it). This is intentionally-discarded work (working tree sits at the clean pushed HEAD), not crash-residue (a crash leaves work ON HEAD as a detached commit, which `--all` catches). Adding `--reflog` would over-skip every recently-reset worktree as `unpushed` (a conservative over-skip, never a fail-OPEN). Phase 1 is report-only; Phase 2's removal is `git worktree remove --force` which discards the reflog anyway. No action needed unless Phase 2 wants belt-and-suspenders.

## [Phase 2 / --apply] W7b reflog-only & standalone-checkout residue (from slice 1.1 codex r3 BLOCKING, overruled-to-followup in Phase 1)
codex r3 flagged: W7b `git log --all --not --remotes` does NOT catch a commit reachable ONLY from the reflog (e.g. local commit then `git reset --hard origin/main`) — such a clean checkout would report `eligible`, and Phase-2 `--apply` deletion would drop recoverable local history. OVERRULED as a Phase-1 P1 because: (a) Phase 1 is REPORT-ONLY (no deletion → no data loss); (b) the `eligible` outcome via the no-pointer→W7b path requires the dir to be a STANDALONE `.git`-DIRECTORY checkout — a real /drive worktree leftover has a pointer file (→registered/unprovable) or no `.git` (→`git status` fails→`skip:unreadable`), so this case is NOT producible by the /drive lifecycle; (c) the naive `--reflog` fix is NET-NEGATIVE — post-squash reflog SHAs would flag nearly every worktree `unpushed`, neutering Tier-W reclaim.
PHASE 2 MUST: model the real residue classes locus 1 actually leaves, and decide the standalone-checkout / reflog-only W7b case before `--apply` deletes — recommend treating a no-pointer `wt/<name>` that has its OWN `.git` directory (a non-/drive standalone repo) as AMBIGUOUS → skip, rather than a blanket `--reflog` (which over-skips). Re-confirm whether the `eligible` Tier-W path is even reachable by genuine /drive residue (real leftovers may all route to registered/unreadable), and if not, document that Tier-W reclaim is effectively completedAt-gated.
## slop (deferred to finalize)
- bin/drive-retention.sh:444,507,597 — `${#ARRAY[@]:-0}` the `:-0` is dead/redundant
- bin/drive-retention.sh:429 — `line` declared but never used in emit_json_run
- bin/drive-retention.sh:257 — `selfpath="$ptr"` needless indirection
- bin/drive-retention.sh:388-392 — `case "$anc"` has no default arm (add explicit `*) ancestry-unprovable`)
- bin/drive-retention.sh:283-289/246-249 — duplicated gitdir-admin parse+strip in wt_registered_anywhere & resolve_owning_repo; extract a helper (DRY)
- bin/drive-retention.sh:35-42, 146-151, 319-324 — (codex) slop refs
- tests/contracts/test_drive_retention.py:1-12, 479-486, 761-763 — (codex) slop refs
- bin/drive-retention.sh:109 + tests/contracts/test_drive_retention.py:886-891 — comment/test overclaim `0` collapse (jq `0//empty`→0; real bypass false/null) [codex harden r2]
- bin/drive-retention.sh:112-114 — torn-state "never done signal" comment drifts vs :230-232 completedAt acceptance [codex harden r2]

--- Phase 2 design follow-ups ---
- gh-PR-state historical worktree reclaim (design.md Open Question 5): squash-merge defeats the ancestry backstop, so Tier-W reclaims ~no historical worktrees; consulting `gh pr` state (like #57) would reclaim them but adds a gh dependency to an unattended GC. Deferred unless the reclaim gap proves material — new runs self-clean via completedAt.
- D5 /tmp/codex_* interactive-scratch backlog: manual one-shot cleanup (out of pipeline scope). If DP-A6's TMPDIR export is deferred (codex CLI does not honor TMPDIR on host), record that here too.

## phasedesign2 r3 review — sub-threshold (NIT, non-blocking)
- §D/§E removal-success proof uses `[ ! -e "$RUN_DIR/wt/<name>" ]`; `-e` reads a
  dangling symlink as "gone", so a (highly implausible) dangling symlink left at
  `wt/<name>` would be treated as a successful removal and allow `completedAt`.
  Benign — a worktree is never a symlink and a dangling symlink is not a registered
  worktree, so W4's attestation is not materially violated. At implement, mirror the
  helper's own `-e`/`-L` discipline (drive-retention.sh:292) with a `-L`-aware check
  if cheap.

## Slice 2.1 round-2 — residual (accepted)
- **Irreducible lockless-TOCTOU residual in `apply_tier_W_child`.** The apply path now re-checks the cheapest, earliest-written liveness signals (`is_waiting_quiet` + `has_open_inflight`) IMMEDIATELY before the destructive `$TRASH_CMD` (bin/drive-retention.sh, after `git worktree remove/prune`), MINIMIZING the check-then-act window to a sub-syscall gap between that re-check and the trash. A check-then-act window is IRREDUCIBLE in a lockless shell GC — it is MINIMIZED, never closed/eliminated. The residual is ACCEPTED: the GC is report-only by default and `--apply` is a manual, ≥14-day-aged, done-run one-shot. Closing it fully would require a lock (deliberately not added — no over-engineering). If `--apply` ever becomes automated/unattended, revisit with a per-run advisory lock (flock on `$RUN_DIR/.gc.lock`) around the re-check→trash span.

## slice 2.1 P2 (for HARDEN phase 2) — apply summary over-claims
bin/drive-retention.sh:800,827 — apply-mode top-level summary tallies from pre-apply `eligible` verdicts + swaps verbs to reclaimed/removed, so trash-failed/skipped-changed cases over-claim bytes/worktrees reclaimed though they remain on disk (per-run detail is correct). Fix: tally summary from actual action outcomes (removed/swept only).
- bin/drive-retention.sh:515,543,576,586 — apply-path comments/structure; de-slop pass
- bin/drive-retention.sh (apply_tier_W_child + apply_tier_L) — duplicated 2-line late-recheck liveness pair across both apply fns; extract a shared helper (Claude harden r4)
- tests/contracts/test_drive_retention.py:1532,1588,1813,2145,2187 — test-helper/structure de-slop (codex harden r4)

## finalize round 1 — deferred (non-cheap / inverse-of-deslop; NON-BLOCKING)
- bin/drive-retention.sh `case "$anc"` (no default arm) — NOT applied: adding a defensive `*)`
  arm is the inverse of de-slop, and the producer `is_ancestor_in_owning_repo` is a closed
  yes|no|unprovable enum so no out-of-enum value reaches it. Taste; leave as-is.
- bin/drive-retention.sh JSON renderer vs human renderer (verdict/action→output mapping
  duplicated; extra per-entry jq in the JSON path) [codex P2] — NOT applied in-run: consolidating
  the two renderers is a refactor on a destructive script's OUTPUT CONTRACT (heavily string-pinned),
  so behavior-change risk outweighs the DRY win for a finalize de-slop pass. Revisit as a standalone
  reuse cleanup.
