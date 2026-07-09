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
- [P1→Phase4] The /goal templates in drive-plan.md (Gate A leg-2, ~:96) and drive-ship.md (Gate B re-arm) must ALSO admit a rebirth pause as a satisfying state ("OR is paused at a rebirth handoff (waiting=\"rebirth\") awaiting my paste of the resume line"), matching the drive.md templates slice 3.1 fixed. Otherwise a user-pasted leg-2/Gate-B goal would force the session past a rebirth handoff. Out of slice-3.1 scope (owns drive.md only); Phase 4 (docs/install/cross-command wiring) owns these files. (codex-review-3.1) — SUPERSEDED by drive-ctx-summary run: `/goal` removed entirely (`design-phase1.md`); there are no `/goal` templates left to propagate a rebirth clause into.

## Phase 4 detailed design — out-of-scope discoveries
- [P3] Deep state.json validation (cross-checking every slice's `owns`/`deps` graph against git refs, verify-attempt/ship-field VALUE consistency) is out of `--mode state-lint` scope — state-lint validates parses + routing fields PRESENT + WELL-FORMED (type/shape) only, the subset resume actually keys on. Full graph cross-validation is a follow-up, not a blocker (D40).
- [P3] Optional belt-and-suspenders: a one-sentence Gate-B cross-reference in drive-ship.md that a rebirth handoff during ship is governed by the leg-2 goal's rebirth-pause clause. Non-load-bearing (the leg-2 clause already covers it, D41); add only if a reviewer insists. — SUPERSEDED by drive-ctx-summary run: `/goal` removed entirely (`design-phase1.md`); the leg-2 goal no longer exists, so this belt-and-suspenders is moot.
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
## Run drive/p3-followup-cleanup (2026-06-23)

- [VETOED][P2 slop] bin/drive-conformance.sh:449 — codex flagged the rewritten ship)-case banner as
  "comment-only churn." OVERRULED at the integrated path: the banner IS this run's deliverable (the old
  banner described the stale pre-finalize "EXISTS a counting phase review" model); removing it would
  restore the stale comment or drop slice 1.2's acceptance criterion → VETOED, non-blocking, KEEP.


# Follow-ups — run todo-triage-20260704T135831

## Slice 1.1 round-2 review — out-of-diff discovery
- [P2] `.harness/followups.md:262` (committed ledger, pre-existing at baseRef 9beeac4, NOT in the slice diff and NOT owned by slice 1.1) is a surviving instance of the superseded claim class the phase P1 removed from docs/drive-enforcement.md: it states `defaultWindow=200_000 (conservative)` — contradicting the shipped `defaultWindow=1000000` fail-open semantics — and directs "When a new large-window model ships, add one `windows[].match` entry" + "Phase 4 docs should note this one-line maintenance point"; executing that stale entry would reintroduce the exact docs claim commit c5ae91c deleted. Fix: mark the ledger entry superseded (unknown model → 1M fail-open; a future 200k family is the case needing an entry, owned by the C1 arming-by-window-match follow-up). Also note: c5ae91c's commit-message claim "Tree-wide sweep confirms no third occurrence" held only for docs/code — this ledger occurrence survived.
  **SHIP ACTION (binding, D-coord-2):** drive-ship's ledger promotion MUST append a premise-stale annotation to this `.harness/followups.md` entry (do not rewrite the entry body): note that post-C2 (this run) `defaultWindow=1000000` (fail-open), the add-an-entry direction is inverted (a future 200k family is the case needing an entry), and the C1 arming-by-window-match follow-up owns the residual.

## slop (deferred to finalize)
- tests/hooks/test_drive_stop_hook.py:454-456 — in-function `sys.path.insert` + import (sibling suite does it once at module level; inconsistent placement)
- test/statusline-window.test.sh:147-160 — three near-identical copy-pasted MODEL_ID sample pipelines; an id-payload helper (mirroring `rendered_pct`) would fold them
- bin/rebirth-thresholds.json:3-8 — speculative dot-form id entries extended to families that never had them (design-mandated convention carry-over)
- tests/hooks/test_rebirth_thresholds.py:114 — stale name `test_resolve_thresholds_default` (resolves the Sonnet 4.5 200k rule, not the default)
- test/statusline-window.test.sh:37 — (codex) flagged, unspecified slop site
- test/rebirth-install-layout.test.sh:181 — (codex) flagged, unspecified slop site
- tests/hooks/test_rebirth_thresholds.py:247 — (codex) flagged, unspecified slop site
- tests/hooks/test_drive_stop_hook.py:439 — (codex) flagged, unspecified slop site

## Harden phase-1 deferrals
- [P2, D-coord-3] bin/statusline.sh inline fallback matches display-name only (jq path matches display OR id): in degraded mode (json unreadable) an unrecognized display + 200k id resolves 1M. PRE-EXISTING asymmetry (old case identical), compound corner, load-bearing Stop-hook path unaffected (rebirth_thresholds.py matches both forms). C1-adjacent: extend the case to `"$MODEL:$MODEL_ID"` arms + degraded-mode id samples when C1 reworks arming.
- [P3] Case-sensitive matching contract documented (bin/rebirth_thresholds.py:12) but unpinned — add a lowercase-display sample asserting the 1M-default fallthrough with a contract-naming comment.
- [P3, C1-adjacent] Opus 4.0 (200k) resolves defaultWindow=1M — same gap class as the pre-existing table (no regression); either add "Opus 4"/"opus-4" 200k entries + derived boundary samples, or extend D-design-7(a)'s named residual class to Opus 4.0.
- tests/contracts/test_drive_ship_trailer.py:1-21 — module docstring carries ~20 lines of C6 bug-history + mutation-verify narration; pins suffice
- tests/hooks/test_rebirth_thresholds.py:74-78 — 5-line date-stamped rationale comment inside a parametrize list (same class at :93-95)
- (codex) new test files: verbose docstrings/comments — 3 sites noted in codex-harden-1.md invocation-2

## Phase-2 design — out-of-scope discoveries (2026-07-04)
- Bash `gh pr merge` / `gh pr edit` are UNGATED while their MCP twins
  (merge_pull_request / update_pull_request) now deny during active runs — an
  asymmetry to decide deliberately in a follow-up (PR content lands only via the gated
  push/create, so accepting it may be fine; decide, don't drift).
- GitLab-MCP write tools (create_merge_request, …) are the same bypass class under
  different tool names — not covered by C7's GitHub-named matcher alternation.
- Refuse-on-drift installer variant (fail-closed deployment-drift gate) — reaffirmed as
  the logged D8 follow-up option; this run ships warn-only.

## Phase-2 design-review r2 — out-of-scope discovery (2026-07-05)
- SSH host-alias reconciliation in the pinned origin parse: the canonical parse
  (Foundation C) keys on `host/owner/repo` as literally written in `origin`, so two clones
  of the same GitHub repo whose origins use DIFFERENT hosts for the same remote —
  `github.com` vs an `~/.ssh/config` alias like `github.com-work` or `ssh.github.com` —
  produce different `host` segments and do NOT match as same-repo (worktree/MCP origin
  scope silently under-matches). Documented as a residual in the design (§ Docs); reconciling
  aliases would need to resolve `~/.ssh/config Host` → real hostname (or canonicalize known
  GitHub host aliases). Out of C7 scope; decide deliberately in a follow-up (the common-dir
  fast-match still catches linked worktrees of the run's own clone form-independently).

- **C7 no-origin-fallback renamed-checkout residual (design r4, codex MINOR):** the MCP
  no-origin fallback keys off `basename(RUN_COMMONDIR sans /.git)` = the owning CHECKOUT
  directory name. For a renamed clone directory or a renamed submodule path this mis-derives
  the repo name, so an origin-less run under-matches same-repo MCP writes (the worktree class
  still matches by common-dir path). A run with a normal `origin` is unaffected. Documented as
  a best-effort no-origin-fallback residual; not fixed (an origin-less GitHub run is atypical).

- **C7 literal-`.git`-named repo over-collapse (slice 2.1 review r5, codex MINOR — FINALIZE owns):**
  parse_origin strips a trailing `.git` unconditionally, so a repo literally NAMED `repo.git`
  canonicalizes identically to `repo`. Inherent git-URL ambiguity (clone-suffix vs literal name,
  indistinguishable without host query); SAFE direction (over-deny, never fail-open); OUT OF GITHUB
  SCOPE (GitHub forbids `.git`-suffixed repo names, so it cannot arise for the GitHub MCP tools the
  gate targets, per D9). Resolution: FINALIZE adds an explicit documentation scope-bound to
  docs/drive-enforcement.md's residual section + a `repo` vs literal-`repo.git` negative-control test
  pinning the accepted boundary. Not a code fix (the ambiguity is unfixable in general).
bin/drive-tool-gate.sh:241 — dead IPv6 second port-strip; only fires on multi-colon IPv6 host, corrupts it (KNOWN)
bin/drive-tool-gate.sh:305 — SC2016 literal $RUN_DIR/$phaseBaseSha/<runId> tokens in single-quoted printf (intentional AC-3 verbatim); no shellcheck-disable landed (KNOWN)
bin/drive-tool-gate.sh:296 — redundant printf '%s' wrapper around basename subshell
bin/drive-tool-gate.sh:282 — common_dir_of local var named 'cd' shadows the cd builtin (confusing naming)
bin/install-drive-hooks.sh:98 — missing-sibling variant-3 WARN printf duplicated verbatim across two branches
bin/drive-tool-gate.sh:251 — overlong essay comment in the normalization block (codex)
test/drive-tool-gate.test.sh:300 — very long mutation-verification narration above the 36-form sweep (codex)
test/drive-tool-gate.test.sh:408 — repeated narrative prose around the codex-reproduced over-deny case (codex)
docs/drive-enforcement.md:242 — verbose repeated AC/residual discharge prose (codex)

## Harden phase-2 — out-of-diff root cause (2026-07-05)
- **[P1, PRE-EXISTING] Spaced-path cross-checkout install duplicates managed hooks.** Install the
  drive hooks from a checkout whose path contains a space (e.g. `/…/sp ace/bin`), then re-run the
  installer from a DIFFERENT checkout → the stale spaced entries are NOT stripped and the new ones
  are appended → duplicate managed hooks (REPRODUCED: 2 merge-gate, 4 tool-gate, 2 stop-guard),
  with NO drift WARN. ROOT CAUSE (out of phase-2 diff): `is_managed` (bin/install-drive-hooks.sh)
  recognizes a spaced-path command as managed ONLY when it EXACTLY equals the current `$full`; a
  cross-checkout re-run has a different `$full`, and the basename branch's metachar guard
  `test("[[:space:]|&;<>()`$]")` rejects ANY command containing a space, so a legit spaced LONE path
  is treated like a wrapped/foreign command and survives. The drift preflight's own `live_cmd`
  derivation uses the same guard, so it also can't warn about a spaced live dir. PRE-EXISTING on
  origin/main: the metachar guard was introduced in f1eee81 (#24) and the `$cmd == $full` clause in
  a6bad23 (2026-06-06), both before this run; REPRODUCED to affect drive-merge-gate.sh +
  drive-stop-guard.sh IDENTICALLY (two distinct merge-gate paths after the cross-checkout re-run),
  so it is NOT introduced by phase-2's tool-gate addition (the phase-2 diff vs merge-base leaves
  is_managed's matching logic untouched — it only extends strip_managed to the tool-gate + adds the
  read-only preflight). NOT FIXED in harden (scope call): the fix must loosen a SECURITY-sensitive
  matcher (is_managed decides collapse-vs-preserve; a false-positive collapse silently WEAKENS
  enforcement — the exact case the existing `env_kept`/`piped_kept` wrapped-command tests protect).
  A plausible fix ("managed iff ends in `/<base>`, contains no `[|&;<>()`$]`, AND starts with `/`" —
  accepts a lone spaced path while still rejecting `env STRICT=1 …/gate.sh` and `wrapper | …/gate.sh`)
  changes matcher semantics and needs its OWN adversarial find-the-bypass review round — beyond a
  cheap harden fix, net-negative risk in a quality-only pass. Also fix the preflight `live_cmd`
  derivation (same guard). Decide deliberately in a follow-up.

- **Committed pytest scratch pollution (harden phase 2, coordinator-caught):** a subagent's
  `git add -A && git commit` swept 1497 in-tree pytest/bash scratch files (`.tmp-py/`, `.tmp-e2e/`,
  `.tmp-home*`, etc.) into phaseInt/2 (commit 7f0abff). Root cause: test suites use in-worktree
  TMPDIR/HOME scratch AND subagents run `git add -A`. FIXED this run: reset the commit, purged the
  scratch, added `.gitignore` `.tmp*/`, re-committed only the real change. PREVENTION follow-up:
  subagents should `git add <explicit paths>` not `git add -A`, OR point test TMPDIR outside the
  worktree. The drive-implement/harden SKILL prompts could pin this.
- **test_skill_frontmatter.py globs on-disk untracked scratch (pre-existing test-isolation bug):**
  `tests/contracts/test_skill_frontmatter.py` rglobs REPO_ROOT for SKILL.md including untracked
  `.tmp*/` scratch left by other suites → false "expected 5, discovered 51" failure when scratch is
  present. Not in this run's diff. Fix: scope the glob to git-tracked files (or skip `.tmp*/`).
  Out of C7 scope — verify runs must purge scratch or use external TMPDIR first.

## Finalize round 1 — codex P1 refuted + P2 deferred (2026-07-05)
- **codex P1 REFUTED as P1 → known limitation: drive-tool-gate.sh MCP match is host-blind.**
  The MCP owner/repo match (drive-tool-gate.sh:358) compares owner+repo only, so a GitHub MCP
  write to `foo/bar` is denied even when the active run's origin is `gitlab.com/foo/bar` or a GHE
  host (same owner/repo, different host). This is an OVER-DENY (fail-CLOSED): it blocks a
  legitimate cross-host write and points the user at the gated Bash path — NOT a bypass/fail-open.
  The GitHub MCP write tools carry only `owner`/`repo` in their input (no host — the host is fixed
  by the MCP server config), so the gate has no host to compare and cannot tighten without input
  it is not given. Consistent with the gate's documented uniform fail-closed over-deny posture
  (drive-tool-gate.sh:22-28, 348-351). Claude's independent audit found no fail-open. Overruled as
  P1 with evidence. If a future MCP schema carries a host, tighten the match to include it.
- **codex P2 deferred (non-blocking): compress drive-tool-gate.sh design-history comment blocks
  + test/drive-tool-gate.test.sh mutation-diary prose.** The gate deliberately carries its
  design-rationale comments for auditability of a security matcher (a stated design value);
  trimming them is a taste edit that reduces auditability. Not applied in finalize — cosmetic,
  behavior-preserving de-slop should not degrade a security gate's auditability. Leave as-is.

## Finalize round 2 — codex P1 #2 overruled + P2 deferred (2026-07-05)
- **codex P1 #2 OVERRULED as P1 → advisory-completeness followup: install-drive-hooks.sh drift_preflight
  misses a stale-path tool-gate registration.** After round-1 fix (d) added per-matcher
  `have_mcp`/`have_native`, those detect a lone `drive-tool-gate.sh` at ANY path, not specifically
  `live_dir`; so a split-brain settings file with BOTH tool-gate entries pointing at an OLD checkout
  (while the merge-gate is current) emits no drift WARN (Variant 2 keys on the merge-gate's live_dir).
  NOT a P1: `drift_preflight` is WARN-ONLY (never blocks/mutates — install-drive-hooks.sh:60-67), the
  install itself RE-CANONICALIZES all managed entries to the current path (self-healing), and a
  stale-path gate is either running-old-code or the already-documented dead-path fail-OPEN residual
  (drive-tool-gate.sh:27-28) — no NEW runtime enforcement failure. Advisory-completeness gap →
  followup: extend the preflight to compare each tool-gate entry's dir to live_dir. Not fixed in
  finalize (WARN-only, self-healing; avoid churning advisory logic).
- **codex P2 deferred (non-blocking): trim leftover mutation-verification/review-diary prose in
  test/drive-tool-gate.test.sh + tests/hooks/test_rebirth_thresholds.py.** These notes document the
  RED-then-green mutation checks (a deliberate audit trail); trimming has no coverage value and loses
  the provenance. Left as-is (same disposition as round-1's codex comment-slop P2).
## Run main-20260704-180725 (leverage Trellis in autodrive → /drive-retro trace-mining command) — 2026-07-05

# Run followups — main-20260704-180725

- [ ] **P3 (cosmetic, from harden 1-1)** docs/trellis-analysis.md:175 says the TR-9
  graduated-stakes tier is "M/L effort" while the Recommendations table row (line 337)
  commits to Effort = L. Align the prose to the table's single-value {S,M,L} domain.
  Not load-bearing: TR-9 is wait-tier, so TODO routing and Phase-2 selection are
  unaffected either way.

- [ ] **P3 (cosmetic, from harden 1-2)** docs/trellis-analysis.md:322-324 vs :333 — the
  Recommendations rules paragraph states the L1 default unconditionally ("L1-tagged recs
  default ignore/wait unless a written non-absorption rebuttal is given") while the fixed
  TR-4 cell scopes it ("the L1 default governs adopt-pattern recs — run-alongside is E6's
  sanctioned L1-safe route"). The cell's scoping matches design-phase1.md E6/DP1-4 intent
  and the resolution is stated inline, so no reader is misled and no routing/selection
  changes under either reading — but a mechanical audit of the table against the rules
  paragraph flags TR-4. One-clause fix: add the run-alongside carve-out to the rules
  paragraph.

## slop (deferred to finalize)

- docs/trellis-analysis.md:69 — "the discipline is already ours" — first-person-possessive voice drift in an otherwise third-person analysis.
- docs/trellis-analysis.md:97 — "Trellis also documents its own dead code honestly" — editorializing adverb; "honestly" adds no information over "documents its own dead code".
- docs/trellis-analysis.md:180 — "the repo's moat per TODO.md's layer framing" — buzzword + loose attribution: TODO.md's framing says "Keep"/"re-target layer 3", never "moat".
- docs/trellis-analysis.md:278 — "One corroborating detail worth keeping:" — filler self-justifying lead-in; the detail's relevance is already argued in the sentence that follows.
- docs/trellis-analysis.md:175 — "M/L effort" for TR-9 where the table (line 337) says "L" — inconsistent effort vocabulary (also recorded as the P3 finding above).
- docs/trellis-analysis.md:219 — bullets re-explain ranking mechanics already stated (codex).
- docs/trellis-analysis.md:321 — table-rules paragraph repeats prior sections (codex).
- docs/trellis-analysis.md:303 — portability section over-padded (codex).
- docs/trellis-analysis.md:371 — trailing cleanup prose after the one-decision close (codex).
- [ ] **P2 (from harden-regress, phase 1)** docs/trellis-analysis.md:332,348 — the TR-3
  invocation reword says "manual, operator-invoked … like /decant today", but OPERATING.md
  makes /decant a standing BY-DEFAULT wrap step (Claude-run, not operator-typed) and the
  doc's own dim 5 says so; imprecise analogy, spike contract unaffected. Cheap wording fix
  — candidate for the finalize whole-run pass.
- docs/trellis-analysis.md:333 — "free search/slice" — marketing-ish shorthand (codex, harden r2).
- [ ] **Process signal (this run, for TR-3/retro):** the drive stop-hook nags on every
  turn-end while the coordinator is legitimately waiting on background codex/subagent work
  (~8 nag turns this leg); the hook reads only state.json and cannot see harness-tracked
  background tasks. Candidate: teach bin/drive-stop-hook.py to stay quiet when an
  inflight-*.marker is open (the marker IS the "work in flight" signal).

- [ ] **Divergence (from phase-2 design):** CLAUDE.md documents event-log.jsonl as
  "append-only dispatch/verdict/merge/gate timeline" (JSONL), but the coordinator in
  practice appends pretty-printed MULTI-LINE JSON objects alongside single-line records
  (this run: 46 objects; a naive line parser flags 192 "malformed" lines). Either pin the
  writer to compact single-line JSON in drive.md's event-append instruction, or document
  the mixed shape. /drive-retro v1 absorbs it with a tolerant raw_decode stream parser
  (DP2-2); fixing the writer is out of Phase 2's boundary.

- [ ] **Follow-on (named in docs/trellis-analysis.md TR-3 + design-phase2.md, not built):**
  automatic run-wrap wiring for /drive-retro — a drive.md Completion-step edit invoking it
  in the sequence where /decant already runs. v2 candidate: cross-run aggregation.
  DP2-5 names bin/drive-retro-stats.py if the inline parse snippet grows a second consumer.

- [ ] **Follow-on (from phase-2 design r1, DP2-8 — not built):** /drive-retro in-flight
  mode — mining a stuck/in-flight run for STOP causes (the use case the dropped v1
  `partial` argument served). v1 is completed-run-only per TR-3; an in-flight mode needs
  its own design (non-final stats banner, no-overwrite-of-a-completed-retro guard).

- [ ] **Harness gap (from phase-2 design review r2, out of phase scope):** STOP pauses are
  not durably recorded anywhere — Present human pause (drive.md §595) sets
  `state.waiting = "stop:<short>"` transiently (cleared on resume) and the event-log append
  rule covers only dispatch/verdict/merge/gate, so a completed run retains zero STOP history.
  This blinds any post-hoc trace mining (retro v1's STOP stats had to be cut) AND the
  in-flight retro follow-on would see only the CURRENT stop. Candidate: Present human pause
  step 1 also appends one event-log line ({"event":"stop","reason":waiting,"at":...}) —
  cheap, append-only, makes STOP causes first-class trace data.

- .claude/commands/drive-retro.md:70 — `re.compile(r"[ \t\r\n]*")` rebuilt on every loop iteration inside the inline decode snippet; hoist the compiled pattern above the `while`
- tests/contracts/test_drive_retro_contract.py:1 — over-explanatory module docstring
- tests/contracts/test_drive_retro_contract.py:277 — padded `test_class_to_destination_routing` docstring
- .claude/commands/drive-retro.md:143 — "never grounds to re-architect the rule" reads editorial- (harden-2 r2, codex P2 notes) test_drive_retro_contract.py — AC9's "decant checklist NOT duplicated" half unpinned; Step-7 recurrence grouping-key details / Draft "≤2 sentences" constraint / terminal-report contract unasserted. Non-criterion gaps; deferred.

- tests/contracts/test_drive_retro_contract.py:304 — docstring restates the invariant the asserts already encode
- tests/contracts/test_drive_retro_contract.py:236 — inline comment block narrates guard-3/guard-4 semantics the assertions already pin
- .claude/commands/drive-retro.md:155 — section 7 packs independent contracts into overwritten bullet prose- (harden-2 r3, codex P2 notes — routed, not applied) test_drive_retro_contract.py deeper-pin gaps: AC2 exact-match branch; AC8 Evidence ≥2-citation + Draft ≤2-sentence sub-clauses; AC14 "never a STOP" guarantee. Cheap individually, but the pin treadmill is at diminishing returns (r1: 12 pins, r2: 1 rewrite; each round spawns deeper-pin wishes) — deferred rather than consuming the last harden fix round.

## finalize round 1 — routed non-fix items (2026-07-05T04:10:44Z)

- [ ] **P2 (codex finalize, dedup read-set breadth)** `.claude/commands/drive-retro.md:50-58` vs `:163` —
  the Overlap dedup reference set is a FIXED read-only {OPERATING.md, TODO.md, .harness/decisions.md,
  .harness/followups.md, MEMORY.md}, but the **Destination** vocabulary also allows `project
  CLAUDE.md/docs` and `skill/command file <name>`, which are NOT in the read-set — so a proposal
  targeting a skill/command file can render `Overlap: none` without that file being checked.
  DECIDED scope (DP2-22: "an unchecked Overlap field is theater"; extend-vs-duplicate over the
  available set) and non-load-bearing (retro emits PROPOSALS ONLY, human reviews before applying).
  Non-blocking. Candidate clarity tweak: make the Overlap instruction say destinations outside the
  fixed reference set render "not checked (destination not in dedup set)".
- [ ] **P3 (Claude finalize, pseudocode micro-slop)** `.claude/commands/drive-retro.md:70` — the
  event-log stream-decode pseudocode rebuilds `re.compile(r"[ \t\r\n]*")` inside the `while` loop;
  hoisting it to a module-level constant is a behavior-preserving micro-opt. DEFERRED, not applied:
  the file is a heavily string-pinned command SPEC (119 asserts) and codex flagged it as an unsafe
  de-slop surface; the slop is illustrative pseudocode, not shipped runtime code.

## finalize round 2 — routed non-fix item (2026-07-05)

- [ ] **P2 (codex finalize r2, broad mining-input pinning)** `tests/contracts/test_drive_retro_contract.py`
  `test_mining_inputs_durable_only` — round 2 added a positive pin for the load-bearing
  `event-log.jsonl` input. The full positive set (state.json, decisions.md, followups.md,
  finalize-todo.md, redesign-*.marker, inflight-*.marker, checkpoint-complete.marker) is NOT
  individually pinned. Deliberately deferred: pinning every named input verbatim over-pins a
  prose contract already reviewed through 8 phasedesign rounds; no evidence of a
  silent-drop regression. Candidate if the input list later regresses.

## Design-doc handoff audit (ship, 2026-07-05)

HANDOFF: [/drive-retro] new command `.claude/commands/drive-retro.md` shipped (v1: manual, completed-run-only, no shipped code) — the automatic run-wrap wiring (a drive.md Completion-step edit invoking it BEFORE the wrap-decant, per finalize-todo.md) must land in drive.md before the retro loop is closed; string-pin contract tests apply.


## /drive run main-20260705-130712 — followups (promoted at ship 2026-07-05T14:24:36Z)

## F1 — drive-retro.md carries stale "not built / not invoked by /drive (v1)" status notes
Once retro is wired into Completion, drive-retro.md's frontmatter ("Not invoked by /drive
(v1)") and its role paragraph ("automatic run-wrap wiring … is a named follow-on, not
built") become factually stale, and the latter phrase is string-pinned by
test_drive_retro_contract.py::test_role_paragraph_scope_guards_and_decant_boundary.
This run scopes retro's own spec OUT (per task). Followup: refresh those status notes +
move the pin, OR decide the notes describe retro-as-a-standalone-command and leave them.

## Path A ship-side wrap reorder (drive-ship.md scope — deferred)
Source: design-phase1.md review r3 P1-B (Claude). Path B (resume teardown) reorders the
retro→decant wrap to run BETWEEN `completedAt` (step 4) and `stage="done"` LAST (step 5), the
stop-hook-forced window, so the wrap is guaranteed to complete. Path A (normal Gate-B ship)
still runs the wrap via `## Completion` AFTER `drive-ship.md § After approval` returns —
post-`stage=done`, same coordinator turn immediately after Gate B (no context-clear seam), so
the drop risk is a narrow, tolerated best-effort window. Applying the SAME pre-`stage=done`
reorder to drive-ship.md's After-approval (run the wrap between its step 4 `completedAt` and
step 5 `stage="done"`) would close it symmetrically. DEFERRED: out of this slice's scope
(drive.md/drive-retro.md/test/ledger only); drive-ship.md internals are explicitly out of
scope for run main-20260705-130712. Classification: Taste (best-effort hardening, not a
correctness bug on an advisory pass).

## docs/trellis-analysis.md stale /drive-retro status (surfaced by phase-1 review, out of slice scope)
- [P2] docs/trellis-analysis.md:330 still calls `/drive-retro` "v1 manual … automatic wiring … a deferred follow-on" — now FALSE after this run wired retro into drive.md Completion. Unpinned, outside the four owned files. Refresh in a separate doc-consistency pass (finalize may route to TODO.md).

## AC13 decisions.md ledger internal-consistency (phase-1 review P2, for finalize sweep)
- [P2] .harness/decisions.md:3198,:3205 still cite `REVIEWED_OVERAGE_LINES = 183` / `n==183` (harden-2 historical entries), while this run's entry (:3180) and the live pin moved to 184. Append-only ledger, so no history rewrite — add a one-line supersede pointer on the AC13 entries (→ 184; see the SLOC-overage update) during the finalize consistency sweep so a top-down reader isn't misled.

## slop (deferred to finalize)
.claude/commands/drive.md:1203-1215 — hook-protected-window explanation restated ~3x in Completion (DRY candidate; some redundancy is deliberate P2-softening nuance)
.claude/commands/drive.md:212 — (codex) slop note in teardown region
.claude/commands/drive.md:1208 — (codex) slop note in Completion gate region
tests/contracts/test_drive_retro_contract.py:71 — (codex) slop note
tests/contracts/test_drive_retro_contract.py:91 — (codex) slop note
.harness/decisions.md:3180 — (codex) slop note in SLOC ledger line
tests/contracts/test_drive_retro_contract.py:87 — verbose mutation-explainer comment block (codex harden r2)
tests/contracts/test_drive_retro_contract.py:114 — verbose mutation-explainer comment block (codex harden r2)

## AC9 ledger-update entry unpinned (harden r2 P2)
- [P2] .harness/decisions.md:3180 `drive-retro SLOC overage` update not asserted by a test; the exact `REVIEWED_OVERAGE_LINES==184` pin forces re-review on drift, and a decisions.md substring pin is CI-unreachable/vacuous-post-promotion (prior decision 3198-3200). Left unpinned by design.

## Contract-pin brittleness to rewording (harden-regress r2 codex P2)
- [P2] The AC5/AC6 (and role-paragraph) substring pins in tests/contracts/test_drive_retro_contract.py red on benign semantic rewording, not just phrase removal. By-design for string-pin contracts on load-bearing status claims (a reword should trigger re-review), but noted as a known brittleness property of the pin battery.

## Finalize r1 — codex P2s (non-blocking, deliberate / by-design)
- [P2] drive.md:~218 "Best-effort/non-fatal still holds…" (teardown step 5) restates the non-fatal
  contract that ## Completion states globally. NOT applied: the r3 dual-voice review MANDATED
  honest per-surface best-effort framing (teardown INSTRUCTION vs Completion cross-path OVERVIEW);
  removing it strips reviewer-required nuance (net-negative risk). Left as deliberate per-surface
  statement. (Codex finalize r1.)
- [P2] test_drive_retro_contract.py contract-pin brittleness: exact token-count asserts
  (count("/drive-retro <runId>")==1 in Completion; ==2 whole-file) + frontmatter substrings red on
  benign rewording. By-design for load-bearing status/exclusivity claims — a reword SHOULD trigger
  re-review. Already noted under "Contract-pin brittleness to rewording". (Codex finalize r1.)
## Run drive-ctx-summary-20260705-035515 (2026-07-05) — context-of-execution summary + /goal removal


## Out-of-scope discoveries

- **Mission Control's own "session goal" concept is a separate, unrelated `goal`**
  (`mission-control/bin/harvest.py`, `tests/mc/test_today.py`, `tests/mc` fixtures). It is the
  harvest/standup session-label feature, NOT the `/drive` `/goal` printout. Confirmed unrelated
  during blast-radius scan — intentionally NOT touched by this run. Logged so a future grep for
  `goal` does not mistake it for a dangling `/drive` reference.

- **`drive-design.md` line 24 "goal"** ("the high-level design — find phase `<P>`'s
  scope/boundary/goal") is the design-goal noun, unrelated to the `/goal` command. Not touched.

- **`.harness/decisions.md` / `.harness/followups.md`** contain historical `/goal` references
  (records of prior lever-2 rebirth work). These are append-only run-history ledgers, not live
  spec; leaving them is correct (they record what was decided at the time). Not edited.


<!-- ===== promoted from /drive run c7-gate-bypass-20260705-225936 (2026-07-06T09:45:21Z) ===== -->
### C7 phase1 followups (2026-07-06)
- Unify the completedAt/parse_ts parse across drive-retention.sh + drive-hook-lib.sh onto ONE pure lib (retention sources it), removing the D-h (~20-line) duplication.
- Retention enhancement: reap aged, quiet, no-inflight run dirs lacking completedAt REGARDLESS of stage (bounded by age + liveness gates), so an abandoned never-done run self-heals the tool/worktree gate's fail-closed hot state (design-phase1 E-10) without manual run-dir removal.

### C7-RESCOPE phase1 followups (2026-07-06)
- worktree-gate repo-scoping (D-w1 residual): optionally scope the exit-2 deny to the WorktreeCreate payload `cwd`'s repo identity so native worktree creation in an unrelated repo is not blocked while a run is active elsewhere; requires sharing parse_origin/common_dir_of. Defer until the over-deny bites.
- jq-absent DENY residual (D-w2, REVISED r1): the worktree-gate now FAIL-CLOSES (exit 2, denies native worktree creation) when jq is absent — a jq-less machine cannot create native worktrees. CONSISTENT with the shipped PreToolUse gate's identical jq-absent fail-closed; jq is a documented /drive precondition, so this is the accepted safe direction (recoverable route-to-Bash), not a bug. The narrower corrupt-active-run fail-open (a genuinely-active run whose OWN state.json is corrupted, when it is the only run) is the shared predicate's own-logic-only posture — inherited, not new.
- Hook-chosen worktree path (D-w3 residual): with the WorktreeCreate gate installed, native worktree location is hook-chosen; reconcile with Claude Code's documented default path convention if divergence annoys.
- Installer drift-preflight does not yet warn on a missing/partial WorktreeCreate registration (covers merge-gate + tool-gate only). Add a parallel check — nicety, not correctness.
- G2 vendor-schema drift (inherited): the exact-enumeration matcher fingerprints vendor tool names; a GitLab MR tool rename silently fails open — the same schema-drift residual the shipped gate documents; retire when managed tool policy ships.

### C7-RESCOPE slice-1.1 review-r2 followup (2026-07-06)
- Harden the SHIPPED drive-tool-gate.sh (and the shared drive_scan_active_runs) to fail-closed on scan-tool absence / scan I/O error (missing find/sort/dirname/jq, or an unreadable RUNS_ROOT), with shared-scan-failure test coverage — a separate change from the C7 non-Bash gap-closing run, since it changes shipped PreToolUse-gate behavior and is forgery-class. The WorktreeCreate gate (drive-worktree-gate.sh) already fails-closed on these; the shipped PreToolUse gate does not (inherited pre-existing fail-open).

## slop (deferred to finalize)
bin/install-drive-hooks.sh:53 — banner still says "GitHub-MCP writes" (now GitHub+GitLab)
docs/drive-enforcement.md:184 — says drive-tool-gate.sh "sources nothing" (now sources drive-hook-lib.sh)
bin/drive-hook-lib.sh:2-5 — header still describes pure ref-parsing/existence only
bin/drive-tool-gate.sh:2-8,337 — GitHub-only wording on now-shared GitHub/GitLab paths
docs/drive-enforcement.md:108,157,302 — old lib/worktree fail-closed contract wording
test/install-drive-hooks.test.sh:420-423 — comment says three hooks/four entries
### C7 finalize round-2 P3 residuals (2026-07-06T08:43:59Z) — non-blocking
- docs/drive-enforcement.md:~166 illustrative bullet still says "GitHub-MCP" (behavior documented accurately in the gate table ~106 + the G2 section); cosmetic doc-consistency nicety.
- test/install-drive-hooks.test.sh: the variant-3w sibling-absent (missing drive-worktree-gate.sh file) WARN lacks a dedicated test mirror; the WorktreeCreate-registration variant-6 test covers the registration warn. Add a file-absent mirror if drift-preflight test depth is revisited.
### C7 finalize round-3 residuals (2026-07-06T09:15:53Z) — non-blocking
- [ROUTED, forgery-class] bin/drive-worktree-gate.sh:88 active-run deny path shells out to
  `sed`/`basename` unguarded (precheck at :56 covers jq/find/sort/dirname/git). If sed/basename
  are absent the hook STILL exits 2 (deny — fail-closed direction preserved), but stderr gets
  "command not found" noise and the runId drops from the message. Same coreutils-absent
  degraded-env / forgery-class scenario as D-finalize4 (find/sort). Behavior is correct; only
  message quality degrades in an unreachable-in-practice env → deferred. Add sed/basename to
  the precheck + a test when the shipped-gate coreutils-absent hardening lands.
- [P3, cosmetic] drive-hook-lib.sh drive_scan_active_runs emits skip-warning stderr with a
  hardcoded `drive-tool-gate:` prefix; worktree-gate caller suppresses it (2>/dev/null), so it
  never mis-surfaces — byte-faithful-to-shipped by design.
- [P3, cosmetic] install-drive-hooks.sh: the `== $REPO_DIR/bin` branch variant-3w check is
  effectively unreachable (tool-gate-presence return precedes it); mirrors the tool-gate
  pattern defensively at zero cost.
### C7 finalize round-4 P3 residuals (2026-07-06T09:30:03Z) — non-blocking, illustrative
- docs/drive-enforcement.md:202 — worktree-class origin-identity match "catches a second
  independent clone of the same GitHub repo"; mechanism is host-agnostic (host/owner/repo key,
  now covers GitLab clones too). Illustrative single-host example, mechanism-accurate. Trivial
  s/GitHub repo/repo/ if a future doc touch lands here; not worth a dedicated de-slop round
  (both finalize voices agreed it is an example, not a scope claim).
- bin/drive-tool-gate.sh:250 — parse_origin lowercasing rationale comment cites "GitHub treats
  host/owner/repo so"; GitLab origins lowercased by the same pass. Factual example, not a scope
  claim.
- test/drive-tool-gate.test.sh:594,643 — comments describe the file/branch suffixes as "shared
  GitHub suffixes (server-wildcarded)"; historically accurate provenance (enumerated for GitHub
  in the shipped gate, reused by GitLab via server-wildcard). Optional s/GitHub/shared/ nicety.

## slop (deferred to finalize)
- bin/drive-conformance.sh:~223-231 — reviewed_sha_of comment narrates iteration history ("This removes the last whole-file/EOF fallback", "closing the body-only-sha bypass for no-`## Findings` files"); trim to the contract, drop the what-it-used-to-do narration.
- bin/drive-conformance.sh:~700 — PARSEABILITY BOUNDARY comment tagged "(root fix, COMPLETED)"; iteration-status narration, cut to the invariant.
- tests/contracts/test_checkpoint_contract.py — pervasive round-history narration in docstrings across the new fixtures ("round-3 BLOCKING", "Round-5 BLOCKING", "Round-6 boundary completion", "codex's (i)/(ii)", "codex's round-5/6 reproduction, CLOSED", "the round-4 behavior … was itself UNSAFE"); reduce to the intent each test pins, not the review-round provenance.
- tests/contracts/test_checkpoint_contract.py:26-37 — `_findings_review` docstring aside that `_helpers._review` "predates the `## Findings` schema pin"; historical aside, state only the helper's contract.
- tests/contracts/test_checkpoint_contract.py:367 — provenance/iteration-history narration in docstring
- tests/contracts/test_checkpoint_contract.py:552 — provenance/iteration-history narration in docstring
- tests/contracts/test_checkpoint_contract.py:1297 — provenance/iteration-history narration in docstring
- test/drive-conformance.test.sh:483-484 — CK1 comment still frames phaseReviewRound as "3 review-phase1 files MINUS the 1 AppliedEdits:yes regress marker" (old subtraction rationale, conflates a harden-yes file with the now-MARKED review). Asserted value {"1":2} is correct under count(unmarked); reword to the marker rule (2 unmarked + 1 marked harden-regress → round 2, no subtraction).
- test/drive-conformance.test.sh:535-538 — CK2 header "regress subtraction edge" + comment "yes-count exceeding the review-file count is malformed" + assert label "CK2 yes-count > review count -> exit 1" describe the OLD deficit premise; the fixture is now SURPLUS (3 distinct marked reviewed-shas > 2 harden-yes). Assertions bite correctly; retitle to the surplus semantics.

## followups
- tests/_helpers.py:59 — _review emits reviewed-sha for design/phasedesign fixtures (real writer omits it); shared-fixture fidelity, no live failure
- test/fixtures/mkfixture.sh + test/drive-conformance.test.sh + tests/_helpers.py — review-artifact schema duplicated across 3 emitters (drift vector); structural dedup
- test/drive-conformance.test.sh:491 — CK1 comment narrates subtraction-era 'files MINUS regress marker'; fixture is now marker-aware, update wording
- test/drive-conformance.test.sh:544,547 — CK2 labeled 'regress subtraction edge'/'yes-count > review count'; no longer matches the marked-surplus fixture semantics

## Finalize round-2 deferrals (2026-07-07T16:56:47Z) — non-blocking (audit CONVERGED; both voices 0 P1)
- tests/contracts/test_checkpoint_contract.py:97 / tests/_helpers.py — `_findings_review` helper name still reads as "emits FINDINGS" though it defaults CONVERGED. Round 1 corrected the docstring; the NAME remains. Deferred: rename is churn across 2 call sites for a test-helper, zero production impact, and the two finalize voices split on it. (codex P2, round 1+2.)
- test/drive-conformance.test.sh (slice-merge ~193 / audit ~398) — non-criterion matrix gap: the bash suite pins the body-only-sha variant for slice-merge+audit but not the no-`## Findings`/EOF variant through those same entrypoints. Both inputs reach the IDENTICAL `check_scope_counts`→`reviewed_sha_of` rc1 branch that round 1's body-only-sha tests already exercise there, and the shared path is proven in pytest (test_checkpoint_contract.py:692). codex itself rated it P2 and conceded the shared path is proven. (codex P2, round 2.)
- bin/drive-conformance.sh:210, test/fixtures/mkfixture.sh:38, tests/contracts/test_checkpoint_contract.py:412 — codex flagged the long rationale blocks as removable slop; RETAINED as load-bearing "why" (awk exit→END fall-through / header-region binding / fail-closed rationale) per the Claude voice + OPERATING's "comments keep the non-obvious why". Recorded as a considered-and-declined de-slop, not a pending fix. (codex P2 vs Claude split, round 2.)
- .claude/commands/drive-review.md:139, .claude/commands/drive.md:281 — further prose trims are VETOED: the wording is exact-string-pinned by tests/contracts/test_checkpoint_contract.py:1481 and test_state_json_shape.py:102; trimming reds those pins. (codex P2, rounds 1+2 — the "unsafe de-slop" warning.)

## /drive run finalize-verdict-integrity-20260709 — finalize Verdict/AppliedEdits gate (2026-07-09T16:01:23Z)
- codex-unavailable terminal degradation (drive-finalize.md:232): a finalize no-fix confirming round whose codex times out (CODEX_UNAVAILABLE, accepted as present) degrades the terminal re-audit to single-voice. Pre-existing repo-wide codex-degradation policy; tightening finalize-terminal only is out of this fix's scope. Consider a stronger run-wide terminal codex condition separately.
- bin/drive-conformance.sh header readers (verdict_converged, applied_edits_no, reviewed_sha_of, AppliedEdits counter) use `[[:space:]]*` spacing tolerance, not exact producer-literal match. Zero-space variants (`## AppliedEdits:no`) pass — harmless under the omission/crash threat model (not producer-reachable); a maximally-strict posture would pin ALL readers + producer output uniformly (run-wide decision). (codex slice/finalize r2/r3.)
- AC44 `_REQUIRED_CARRIERS["## AppliedEdits: no"]` requires the literal in bin/drive-conformance.sh via a COMMENT (like the sibling `## AppliedEdits: yes` carrier). A future de-slop comment reflow must preserve the literal. Established convention — not changed (codex finalize P2, refuted).
- tests/contracts/test_drive_finalize_contract.py producer spec-pin: further micro-anchoring beyond the per-branch mutation-verified form is within the stated spec-pin imprecision budget (P3, non-blocking; codex finalize r4).

## From high-level design (2026-07-08)
- TODO C12 residual after R4 lands: the independent-Claude-reviewer degraded second-voice tier +
  per-role model/effort capability-class prose remain open (R4 lands only the distinct-marker
  tier of C12's mechanism). Update C12's x-ref when promoting ledgers at ship.
- [retention] Tier-L heavy-log glob (drive-retention.sh heavy_logs: codex-raw-*.log,
  codex-harden-*.log) misses the `.stranded` mv-aside FAMILIES — pre-existing blind spot, kept in
  this run because the R2 premise pins stranded-log mechanics byte-identical; fix in a retention
  follow-up together with any new family audit. The stranded-quarantine now creates FOUR unswept
  families (round-5 Claude NIT — breadth extension of the original `.log.stranded`-only note):
  `<raw>.log.stranded` (raw-log rename), `helper-<scope>.out.stranded` / `helper-<scope>.err.stranded`
  (token-file rename, §A.8), and `codex-review-<scope>.md.stranded` / `codex-harden-<P>.md.stranded`
  (the §B / AC-P2 stale-sibling quarantine). None match the Tier-L globs and none are KEEP names, so
  none are swept; the retention audit must cover all four. Bounded (one per scope, mv overwrites),
  non-blocking. (r2r4 DX phase, 2026-07-09; families broadened round-5, 2026-07-09)
- [drive-codex helper] Out-of-process codex-reaper / PGID-persist-for-resume-kill for the SIGKILL
  residual — the helper installs an EXIT/INT/TERM/HUP trap that group-kills its codex PGID (§A.4-2),
  but an uncatchable `kill -9` of the helper orphans the codex child, and that orphan is NOT reaped by
  the trap, OS reaping, stranded-log recovery, or the fresh watchdog (round-7 codex BLOCKING corrected
  the earlier false "bounded in practice" claim) — it runs to its OWN codex completion (from-/drive's-
  view UNBOUNDED). Candidate fix: persist the codex PGID to $RUN_DIR so a resume can `kill -<pgid>` a
  known orphan. DEFERRED as over-engineering for a rare chaos case (SIGKILL-during-dispatch). Revisit
  only if attempt-log data shows real orphaned-codex incidents. (r2r4 phasedesign round-6/7, 2026-07-09)
- [drive-codex helper — DEFERRED per human decision D-r2r4-70; SECURITY-RELEVANT] Attempt-scoped /
  freshness-token markers to close the CROSS-SESSION orphan-marker race at the TERMINAL ship gate for
  gate-enforced scopes (§G.0 edge-12; round-8 codex BLOCKING). THE RESIDUAL: a helper orphaned by a
  session crash (its bash process still alive) can, after a resume re-dispatches the SAME scope, write
  a fresh DEGRADED marker to the shared `--marker` path (path-based `mv`, unlike the fd/inode-based
  token file which is immune) that the new session honors. For NON-terminal scopes it is superseded by
  the downstream re-review; **for the FINALIZE / terminal scope it is NOT bounded downstream** —
  finalize IS terminal, nothing re-reviews it, so an orphan can repopulate `codex-review-finalize.md`
  and the `-s`-only ship gate (`codex_present`, content NOT parsed) HONORS a foreign/degraded codex
  voice at the ship gate. **R4 introduces this vector** (pre-R4 the marker writer was a session-bound
  subagent that dies with the crash; R4's surviving bash helper can outlive its session). CANDIDATE
  FIX: the coordinator passes an attempt/freshness token, the helper stamps the marker with it, and the
  ship GATE parses + honors ONLY the current attempt's token. WHY DEFERRED (not a quick add): the fix
  requires the ship gate to PARSE the marker, which BREAKS the design's load-bearing "gate untouched /
  byte-compatible" premise and is a HARNESS-WIDE change out of scope for R2/R4. Evaluate as a
  standalone task. (r2r4 phasedesign round-8 / human decision D-r2r4-70, 2026-07-09)

## From slice 1.1 review (2026-07-10) — setsid-detached descendant residual (deferred)
- `bin/drive-codex.sh` reaps codex/probe descendants by PROCESS GROUP (`kill -…-<pgid>`). A child that
  calls `setsid()` / opens a NEW session escapes PGID-based reaping and can survive helper return
  (round-4 codex BLOCKING: a setsid exec-child appended to raw.log ~2.5s after `OK`). ACCEPTED,
  out-of-scope residual: the real codex CLI does not detach children to outlive itself; full
  descendant-tree reaping is non-portable (Linux cgroups only) over-engineering. The "no child
  survives" contract was NARROWED to "no SAME-PROCESS-GROUP child survives" (AC-H21/H23). Revisit only
  if a codex CLI version starts detaching workers, or as a harness-wide process-supervision hardening.

## From finalize round 1 (codex + Claude audit, 2026-07-09T21:06:33Z) — non-blocking P2/P3
- [drive-codex helper — P2, LATENT/unreachable] Leading-dash pathname option-injection: `grep`
  (`bin/drive-codex.sh:268`), marker/raw-log `mv` (:381, :527), prompt/prior reads (:561, :611,
  :614), attempt-log parent (:763) do not use `--` end-of-options guards, so a `-`-prefixed path
  would be parsed as a flag. NOT currently reachable: in normal `/drive` use the coordinator passes
  absolute `$RUN_DIR/...` paths (leading `/`). Hardening (`-- "$path"` guards) is cheap but
  the failure does not occur on any real path — deferred as edge-hardening without evidence of the
  failure. (codex finalize r1)
- [drive-codex — P2, non-criterion test gap] The coordinator-side channel branch ("outcome token =
  the LAST line of `helper-<scope>.out`; `.err` never merged") is helper-tested (AC-H15 proves
  `.out` is not corrupted by trailing stderr) but not coordinator-contract-pinned. Non-criterion;
  the helper-side guarantee already covers the load-bearing risk. (codex finalize r1)
- [drive specs — P2, VETOED de-dup] The snapshot→quarantine→dispatch blocks and the combine prose are
  near-verbatim across drive-review/harden/finalize.md. De-duping is NOT behavior-preserving w.r.t.
  the tests: the order-anchored contract pins (test_drive_codex_contract.py:248/279/358) assert the
  inline ordered snippets per-file, so extraction would red them. The duplication is intentional
  (each spec runner is self-contained + independently pinned). (codex finalize r1)
- [drive-codex — P3, cosmetic] Attempt-log `killed_log` schema field (`bin/drive-codex.sh:355`)
  holds a comma-joined multi-log list in the degraded emit paths (:681, :685, :705). Cosmetic naming
  inconsistency; renaming would ripple to the AC-H14 schema pin. (codex finalize r1)
- [drive-codex — P3, cosmetic; do NOT apply] Round-N archaeology tokens in security-guard comments
  (`bin/drive-codex.sh` ~:455/:514/:621/:665, e.g. "round-4 codex MAJOR"). Each is co-located with
  the load-bearing security rationale that stops a future editor from deleting the guard; trimming the
  bare round tags risks the rationale. Not worth churn. (Claude finalize r1)

## From finalize round 3 (codex, 2026-07-09T22:15:57Z) — defense-in-depth residual (overruled, non-blocking)
- [drive-codex helper — DEFENSE-IN-DEPTH, overruled D-r2r4-75] The exact probe-log NODE
  (`${raw-log%.log}.probe.log` dispatch / `codex-probe-<scope>.log` probe-mode) is not preflighted
  for its node TYPE the way R4-A preflights the raw-log node. If that exact path pre-existed as a
  dir/FIFO/socket/non-writable file, the `doctor` redirect would fail locally ⇒ a false
  CODEX_UNAVAILABLE degrade instead of HELPER_ERROR. NOT reachable in the real pipeline: it is the
  helper's own derived scratch path (never coordinator-created; written fresh each run), the actual
  raw-log input + both probe-log PARENTS are preflighted, and `--mode probe` is test-only. Safe
  failure mode (single-voice degrade). If ever wiring `--mode probe` into the pipeline or hardening
  against $RUN_DIR tampering, add a node-type preflight of the derived probe-log (mirror R4-A). (codex
  finalize r3; overruled with evidence, imprecision budget stated.)
