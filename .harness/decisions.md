# Decision log

This file records decisions the agents made autonomously per the decision
policy in CLAUDE.md. The main session and subagents APPEND entries here as
decisions are made. The main session READS this file at the start of every
task and stage to maintain consistency.

## Rules

- Append-only. Do not edit or remove prior entries; supersede them with a
  new entry that references the prior one.
- One entry per decision. If a single design choice has several sub-decisions,
  one entry covers them -- don't fragment.
- If a new decision contradicts an earlier one, that IS an escalation. Surface
  the contradiction to the human before proceeding.

## Entry format

### YYYY-MM-DD HH:MM -- Short title
**Stage:** plan | implement | review | codex | ship
**Task:** brief reference to which task this decision belongs to
**Question:** what was being decided
**Options considered:** the alternatives, one line each
**Chosen:** which option
**Reasoning:** one or two sentences on why
**Reversibility:** easy (refactor) | medium (migration) | hard (public API, data)
**Supersedes:** (optional) link to prior entry this overrides

---

## Entries

(append below this line)

### 2026-06-02 -- D1: Drop wshobson agent-teams from the core
**Stage:** plan
**Task:** /drive autonomous lifecycle coordinator
**Question:** Use wshobson agent-teams (team-lead/implementer/reviewer) as the engine?
**Options considered:** (a) adopt as core; (b) drop it
**Chosen:** (b) drop
**Reasoning:** wshobson solves parallel multi-agent execution with file-ownership; our pipeline is sequential single-coordinator. Experimental-flag dependency + role overlap with gstack. Its one good idea (multi-dimension parallel review) is kept only as an optional plain-Agent fan-out.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-02 -- D2: gstack drives planning/advisory; harness owns execution
**Stage:** plan
**Task:** /drive
**Question:** Should gstack skills be the engine for EVERY lifecycle step?
**Options considered:** (a) gstack brain + harness-owned execution; (b) force gstack /review,/ship,/qa into every step; (c) hybrid per stage
**Chosen:** (a)
**Reasoning:** Two parallel reviews (Claude + codex) converged: gstack operational skills (review=fix-first+codex, ship=auto-push, qa=test-fix) are terminal/mutating and resist passive autonomous wrapping. gstack's advisory skills (autoplan + plan-reviews + codex) are its sweet spot. USER-CHALLENGE surfaced to and ratified by the user.
**Reversibility:** medium
**Classification:** User-Challenge (ratified 2026-06-02)

### 2026-06-02 -- D3: Planning = author rough design then autoplan reviews; Gate A == autoplan's gate
**Stage:** plan
**Task:** /drive
**Question:** How does the planning half work, given autoplan is a reviewer not an author?
**Options considered:** (a) feed raw task to autoplan (broken -- autoplan authors nothing); (b) planner subagent authors rough design.md, autoplan reviews it
**Chosen:** (b); Gate A is autoplan's own terminal approval gate, not a duplicate
**Reasoning:** autoplan is rough-plan-in/reviewed-plan-out; it needs an authored plan. Reusing its terminal gate avoids double-gating.
**Reversibility:** medium
**Classification:** Mechanical

### 2026-06-02 -- D4: Execute stages call codex CLI / git / test-runner directly, not gstack operational skills
**Stage:** plan
**Task:** /drive
**Question:** How to run review/ship/qa autonomously?
**Options considered:** (a) inline-execute gstack /review,/ship,/qa SKILL.md; (b) harness-owned thin stages calling underlying tools directly
**Chosen:** (b)
**Reasoning:** gstack operational skills carry preambles + interactive AUQ + hard non-decision STOPs and mutate/push; inline-wrapping is fragile and re-introduces interactivity. Direct tool calls preserve reviewer separation and real gates.
**Reversibility:** easy
**Classification:** Mechanical (consequence of D2)

### 2026-06-02 -- D5: Implement subagent gets a STATUS contract; spike it first
**Stage:** plan
**Task:** /drive
**Question:** How does the implement stage report progress/failure, and what is built first?
**Options considered:** (a) one-shot "write code"; (b) DONE/BLOCKED/NEEDS_CONTEXT contract + spike on a real task before full orchestration
**Chosen:** (b)
**Reasoning:** Implement is the actual unknown (everything downstream is conditioned on it); needs explicit non-DONE handling and a risk-first spike.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-02 -- D6: 6 principles + classification = single decision policy; non-decision STOPs exempt
**Stage:** plan
**Task:** /drive
**Question:** What decision policy governs auto-decisions, and how are hard blockers handled?
**Options considered:** (a) harness's bespoke escalation test; (b) autoplan's 6 principles + Mechanical/Taste/User-Challenge, with non-decision STOPs (red tests, conflicts) pausing regardless
**Chosen:** (b)
**Reasoning:** Unifies with autoplan, resolves the global-CLAUDE always-ask vs decide-and-document contradiction; facts (red build) are not decisions the principles can answer.
**Reversibility:** medium
**Classification:** Mechanical

### 2026-06-02 -- D7: Fix-loop iteration 1 done in main, not via an implementer subagent
**Stage:** implement
**Task:** /drive (self-review fix loop)
**Question:** Address the 8 review-1 findings via the /implement subagent path, or directly in main?
**Options considered:** (a) dispatch an implementer subagent per the pipeline; (b) edit directly in main
**Chosen:** (b) — for tightly-coupled, coherent edits spanning design.md (the spec) + 5 command files, main-context editing is more reliable; the subagent path was already validated by the Stage-2 spike. The re-review (iteration 2) is still a fresh subagent, so the reviewer-separation invariant holds.
**Reasoning:** Deviation from the normal /implement contract, flagged per the invariant. Pragmatic (P3) + explicit (P5).
**Reversibility:** easy
**Classification:** Taste

### 2026-06-02 -- D8: Run isolation = clear stale per-task artifacts on fresh runs (review #2 fix)
**Stage:** implement
**Task:** /drive
**Question:** codex BLOCKING #2 — `.harness/*` filenames are reused across tasks. Fix or document?
**Options considered:** (a) /drive clears stale review-*/codex-review/codex-raw/verify on a fresh-or-different-task run; (b) document a one-task-per-branch limitation only
**Chosen:** (a) — in blast radius and cheap (boil-lakes); makes /drive safe to re-run. User approved.
**Reasoning:** Prevents a new task inheriting prior review evidence/counts.
**Reversibility:** easy
**Classification:** Mechanical (user-approved)

### 2026-06-02 -- D9: Final fix pass — deliberate review-cap override for 3 verified-real findings
**Stage:** review
**Task:** /drive (self-review iteration 2 → fix)
**Question:** review-2 hit the N=2 cap with codex flagging 1 BLOCKING + 2 MAJOR (codex/Claude split). Stop at the cap, or override for one more pass?
**Options considered:** (a) stop and ship with known issues; (b) override the cap for one final pass since findings were verified-real (not a deadlock)
**Chosen:** (b), surfaced to and approved by the user
**Reasoning:** The cap guards against infinite implementer↔reviewer deadlock; here codex was simply correct (Claude missed an incomplete run-isolation BLOCKING). Fixing verified-real bugs is not what the cap is meant to block. Fixes: reset task.md+design.md on fresh run; ship gates on state.codexVerdict alone; broaden reviewCount fallback to unset/absent.
**Reversibility:** easy
**Classification:** User-Challenge (cap override, ratified 2026-06-02)

### 2026-06-02 -- D10: Final confirm + slop pass; stop the review spiral after cheap fixes
**Stage:** review
**Task:** /drive
**Question:** Codex confirmed the 3 fixes (no BLOCKING) but surfaced 3 new MAJORs + slop trims. Keep reviewing, or stop?
**Options considered:** (a) loop another full review round; (b) apply the cheap correctness fixes + genuine slop trims, then stop and ship
**Chosen:** (b)
**Reasoning:** Adversarial review surfaces marginal findings indefinitely; the /drive happy path is validated. Applied: changed-files from git (not ephemeral list), ship decisions scoped by Task field, ledgers marked never-cleared, manual-stepping claim made honest, 6-principles list de-duplicated to a CLAUDE.md reference. Per "if review scope balloons, re-establish the hierarchy" + anti-gold-plating. Kept agent-instruction precision (every binding/error-path explicit) over codex's terser rewrites.
**Reversibility:** easy
**Classification:** Taste (scope call)

### 2026-06-02 -- D11: Remove vestigial wshobson references outside this ledger
**Stage:** review
**Task:** /drive (PR-review cleanup)
**Question:** The repo never invokes wshobson, but command/README/CLAUDE files still mentioned it by negation ("NOT a wshobson team-*"). Keep or remove?
**Options considered:** (a) keep the clarifications (prior AC8 permitted them); (b) strip them — scar tissue from the migration; keep the rationale only here in D1
**Chosen:** (b), user-requested during PR review
**Reasoning:** The repo ships fresh; explaining-by-negation against an uninstalled tool is noise for a new reader. AC8 updated to "no wshobson reference outside this ledger"; D1 remains the single home for the rationale.
**Reversibility:** easy
**Classification:** Taste

### 2026-06-02 -- D12: Raise impl↔review loop cap from 2 to 8
**Stage:** review
**Task:** /drive (PR-review tuning)
**Question:** The non-convergence cap was 2, but real reviews legitimately run 5–6 rounds — we hit the cap and overrode it (see D9). What should it be?
**Options considered:** (a) bump the count to 8 (headroom above observed 5–6); (b) replace the raw count with content-based convergence (STOP when a round adds no NEW BLOCKING/MAJOR)
**Chosen:** (a) bump to 8, user-requested; (b) noted as a future option
**Reasoning:** Simple, matches observed reality with buffer; still flags a true runaway at 9+. Updated all references; de-magic-numbered the incidental review.md mention to prevent future drift.
**Reversibility:** easy
**Classification:** Taste (tuning)

### 2026-06-02 -- D13: Phase/slice execution + uniform dual-voice review primitive
**Stage:** implement (PR-review extension)
**Task:** /drive phase-awareness
**Question:** How should /drive handle designs broken into phases/slices, and the requirement that every review use Claude + codex and converge on no-P1?
**Options considered:** captured via two AskUserQuestion answers — extend PR #1 now; parallel independent slices + per-slice review; single ship at end; no phase-boundary checkpoints; P1 = BLOCKING + MAJOR
**Chosen:** (1) Plan emits a `## Phases & Slices` breakdown. (2) Execute = outer phase loop (sequential) + inner slice loop, with independent slices (disjoint file ownership) run in PARALLEL. (3) Review primitive = a Claude reviewer subagent + codex, **converged when neither flags a P1 (BLOCKING/MAJOR)**, applied to the design review AND every code review (per-slice + phase-integration). (4) Single ship after all phases converge; per-loop reviewCount; slice-boundary resume.
**Reasoning:** Matches how real implementation decomposes; makes dual-voice / no-P1 a first-class invariant. Slices are the natural home for the parallel-execution idea deferred in D6 — done with plain subagents, no wshobson.
**Reversibility:** medium
**Classification:** User-Challenge (ratified via two AUQ answers 2026-06-02)

### 2026-06-02 -- D14: Run model + worktree parallelism (external $RUN_DIR, coordinator-driven worktrees)
**Stage:** implement (PR-review extension)
**Task:** /drive parallel execution
**Question:** How to make parallel-slice execution coherent + context-clearable, per the user's "parallel + same PR" choice?
**Options considered:** captured + hardened by 3 rounds of dual-voice DESIGN review (R1: 4 structural P1s; R2: 1 integration-rollback P1; R3: CONVERGED on both voices) before any command-file build.
**Chosen:** (1) Run model — `run-id` + external `$RUN_DIR` (solves artifact-location from worktrees) + `event-log.jsonl` + durable `state.json` with per-slice `step` substate. (2) Coordinator-driven worktrees on **refs only, never the user's main tree**: `featureBranch` from a clean base; `phaseBaseSha = rev-parse featureBranch`; one worktree per parallel slice; **assemble-after-converge by rebuilding `phaseInt` idempotently from `phaseBaseSha`** (that rebuild is the conflict/crash rollback); `featureBranch` advances per phase; reconcile + GC on resume; concurrency cap 4; two test altitudes; call-count/wall-clock budget breaker; flaky-retry; plan-amendment for ownership-widening; context-clear points C1–C4. (3) Slices write run-local ledgers in `$RUN_DIR`; coordinator promotes to the repo `.harness/` ledgers at ship.
**Reasoning:** parallel slices forced the run model + worktrees; the design was found BLOCKING-incomplete twice and converged before building, exactly the harness's own design→review→implement discipline.
**Reversibility:** medium
**Classification:** User-Challenge (parallel + same-PR ratified; design dual-reviewed to convergence)

### 2026-06-03 -- D15: Per-phase HARDEN stage (/drive-harden) after the phase review converges
**Stage:** plan + implement (pipeline extension)
**Task:** add a quality-hardening step at the end of each phase (reduce AI slop, add missing tests, fix logic bugs)
**Question:** how to add a per-phase pass that reviews the phase's codebase to reduce AI slop, add missing tests, and fix logic bugs — without breaking the existing dual-voice review primitive or the worktree run model?
**Options considered:** (a) new `/drive-harden` stage command run per phase after the phase-integration review converges; (b) extend `/drive-review` with a 4th "harden" scope; (c) one harden pass at the end, before ship; cap choices: share the conformance cap-8 vs a dedicated cap.
**Chosen:** (a) — a SEPARATE mutating `/drive-harden phase <P>` stage (Stage 4.5), run in the `phaseInt/<P>` worktree after the phase review converges and before `featureBranch` advances; modeled on `drive-implement` (find→fix→verify) but reusing `/drive-review phase` as its regression guard. Dedicated **cap-3** loop (separate from the conformance cap-8); 3 lenses (de-slop / add tests / fix bugs); de-slop edits that would drop an acceptance criterion's coverage are **vetoed → followups** (kills oscillation); a hard scope-creep gate (edits only within the phase diff, no refactor without a flagged P1); `hardening` resume state restores from committed harden commits (not rebuild). Phase advances only when `hardened`.
**Reasoning:** `/drive-review` is a passive conformance audit scoped to acceptance criteria — folding a fix-first loop in would break its single responsibility and the reviewer-independence boundary. Per-phase (not end-of-run) was the user's directive and catches defects phase-by-phase. The dedicated cap + conformance-yield veto are what keep the loop terminating. Design dual-reviewed: architect subagent CONVERGED; codex (after an initial transient 429 throttle, then recovered) found 5 issues fixed before finalizing — (a) the cap must count FIX rounds with a free confirming audit (else an off-by-one false-STOPs a converged phase); (b) harden's regression re-review uses its own counter, NOT the conformance cap-8; (c) featureBranch advance changed from `merge --ff-only`/`reset --hard` to a pure ref move `git branch -f` (refs-only invariant — phaseInt is a provable FF descendant); (d) resume reconciles `hardenRound` from artifacts, not state alone; (e) scope gate loosened to allow test-support files + flagged root-cause fixes.
**Reversibility:** medium
**Classification:** User-Challenge (user-directed feature; design second-opinioned)

## Run drive-review-hooks-20260603-135659 (2026-06-03) — review-enforcement hooks

- **D1 git-truth, not state-trust** [Taste] — conformance derives merge/ship inventory + verdict from git refs + SHA-bound artifacts; never `step`/`phaseReview`. Root-cause fix.
- **D2 SHA-bound reviews** [Mechanical] — `reviewed-sha:` ties a review to the exact diffed tip.
- **D3 ref-keyed self-location, no sentinel** [Taste] — runId from `drive/<runId>`/`slice/<runId>/<id>` ref or HEAD.
- **D4 asymmetric fail mode** [Taste] — exit-2 fail-CLOSED for ship, open for slice/phase+Stop.
- **D5 deny-only gate** [Mechanical] — relies on platform deny>allow precedence.
- **D6 Stop = best-effort backstop** [Taste] — in-flight-phase audit only; gate chain is the guarantee.
- **D7 threat model = omission, not forgery** [User-Challenge — Gate A] — forgery → component D follow-up.
- **D8 skip full autoplan CEO/DX gauntlet** [Taste] — internal no-UI change; dual-voice design review only.
- **D9 bash+jq+git, plain-bash tests** [Mechanical] — no new dep; repo convention.
- **D10 Stop only, not SubagentStop** [Taste].
- **D11 run-keyed `phaseInt/<runId>/<P>`** [Taste] — isolates concurrent runs (also hardens a pre-existing /drive hazard).
- **D12 ship tolerates ledger commit, existential R, exact-2-file allowlist, ≤1 commit** [Mechanical] — round-2/3 fixes.
- **D13 phase-merge consumes the post-harden review** [Mechanical] — harden cannot advance unreviewed.

## Run: comprehensive test plan for autodrive (run harness-tests-20260604-070040)

D0 (Mechanical) Single runner = pytest 9.0.2; shell scripts driven via subprocess. No bats/shellcheck.
D1 (Taste, SUPERSEDED by D11) baseRef was chore/distribution-readiness@c1bda3f.
D2 (User) Scope = all 4 surfaces: MC Python, shell installers, hook plumbing, markdown contracts.
D3 (Taste) Reload-based env injection: mc_env sets HOME/MC_VAULT then importlib.reload in dep order.
D4 (Taste) Import functions directly; subprocess only for shell scripts + weekly --json + mc-hook stdin.
D5 (Mechanical) tests/ at repo root, per-surface subdirs; minimal pyproject [tool.pytest.ini_options].
D6 (Mechanical) conftest puts mission-control/bin on sys.path (autouse session).
D7 (Taste) Stub the environment not the code (iterm_tab_names->{}, real os.getpid(), never claude -p).
D8 (Taste) "two CLAUDE.md" = repo CLAUDE.md + generated ~/CLAUDE.md from installer.
D9 (Mechanical) Design-review r1 corrections: done.mark exit 2 not 3 (F1); mc-bind/mc-hook need
   ~/mission-control/ via seed_mc_home (F2); AC28 parse+core-key-set {runId,baseRef,featureBranch,phase};
   AC16 swiftbar |->/ ; AC5 waiting unsorted; AC20 bin/ path; today.py uses _obsidian_href call-time.
D10 (Taste) Collapse Phase-1 per-slice reviews into the phase-integration review (test-only, disjoint).
D11 (User-Challenge, approved) REBASE run onto main (9da9fb9) after chore/distribution-readiness was
   merged (PR #12) + deleted and main reworked 7 tested modules (c9a6921). Tests target main now.
   Re-target: bucket edge-8/scheduled-only now -> backlog (main else: catch-all). PR targets main.
D12 (Mechanical, incident) RUN_DIR + branches under the old run-id were deleted by a branch-name-keyed
   cleanup triggered by the chore/distribution-readiness merge/delete. Work recovered from
   /tmp patch + dangling commits; re-established under run-id harness-tests-* (collision-free).

## Run run-graph-20260604-164012 — Emit run graph at gates/STOPs (2026-06-04)
(promoted from $RUN_DIR/decisions.md)
# Decisions — run-graph

- D0 [Taste] Pipeline weight = LEAN /drive (user choice at Stage 0): design + dual-voice
  design review → Gate A; one implement pass; one dual-voice code review; ship PR → Gate B.
  No per-slice worktrees, no harden pass — nothing parallelizable, no test surface to harden.
- D1 [Mechanical] Canonical "Emit run graph" spec lives once in drive.md; drive-plan.md /
  drive-ship.md reference it with a one-line "what" + pointer (DRY).
- D2 [Taste] Graph derives PRIMARILY from structured artifacts (state.json + review/harden md
  files); event-log.jsonl is a best-effort chronological supplement only — its event names are
  provably inconsistent across runs, so parsing them as a contract would be brittle.
- D3 [Mechanical] Graph emitted to chat (task says "emit"); no new artifact file / flag.
- D4 [Mechanical] No sync step needed: ~/.claude/commands/drive*.md are symlinks into the repo.

## Round-1 design review resolutions (rev 2)
- D5 [Taste] Verify/Ship/phase-order get durable state.json homes (verify/ship/phaseList) —
  soft contract permits non-core keys; chosen over canonical event-log events (state.json is
  the graph's existing single-value source; no event-name dependency). Kills the drift BLOCKER.
- D6 [Mechanical] `‖` redefined = structural independence (disjoint owns + no inter-deps),
  explicitly NOT a wall-clock concurrency claim. Resolves codex's false-equivalence BLOCKER.
- D7 [Mechanical] Single "Present human pause" routine (emit graph → set waiting → present);
  emission is step 1 → omission-proof. AUQ gets waiting="ask:<header>" + a `? <header>` leaf.
- D8 [Mechanical] DRY pointer = HARD "read drive.md § Emit run graph" instruction + unreachable
  fallback; also covers drive-plan/drive-ship own STOPs. Drops false self-sufficiency claim.
- D9 [Mechanical] Combined dual-voice round verdict (CONVERGED iff BOTH voices zero P1) for all
  scopes; collapse LADDER with unconditional last rung (always ≤~45); general missing-artifact
  rule (verdict `?`, never fabricate) for all scopes; worked example renders added to ACs.

## Round-2/3 resolutions (rev 3, design CONVERGED)
- Pause routine reordered: set waiting → emit graph → present (← YOU ARE HERE needs waiting set
  first); aligned all prose + D7 (no "step 1" emission claim remains).
- Slice review glob corrected to review-<id>-*.md / codex-review-<id>*.md (bare-id scope).
- Budget ladder given unconditional rung 6 (spine-only, depth-bounded) → always ≤~45.
- Dropped state.mode (read-but-never-written); empty-slices disambiguated via stage.
- Missing-artifact "?" rule enumerates all families incl. harden-<P>-*.md / codex-harden-<P>*.md.

## Run main-20260604-223428 (autodrive quality sweep) — 2026-06-04/05

# Decisions — hardening-sweep planning (main-20260604-223428)

- D1: Fix the CI bash-suite gap first (Phase 1) before any de-slop, so later edits run under real coverage. Classification: Mechanical
- D2: Treat mc-hook.py's missing-dir write as a real bug (add os.makedirs), not slop. Classification: Mechanical
- D3: Keep all documented fail-closed/fail-open guards in the shell gates; de-slop only high-confidence dead code. Classification: Taste
- D4: Group slices by subsystem for disjoint file ownership; serialize phases after the CI fix. Classification: Mechanical
- D5: Document the test/ vs tests/ split rather than merging the directories (intentional bash-vs-pytest split). Classification: Taste

- D6: For this hardening-sweep design, run the dual-voice design review (Claude reviewer + codex) as the load-bearing Gate-A check and fold autoplan's completeness/scope lens into the reviewer, rather than invoking the full gstack autoplan CEO/Design/Eng/DX stack. Rationale: 6-principle pragmatic/bias-to-action — the design has no product/architecture tradeoffs autoplan adds value on; the P1 gate (ownership disjointness, dep cycles, buildability, coverage) is what matters. Classification: Taste. Surfaced at Gate A.

- D7: AC3 CLI-flag↔doc contract targets shell + Python entrypoints, not *.py only — flags like `mc bind --project/--task/--tab/--unbind` live in mc-bind.sh and the `mc` shell router. Classification: Mechanical
- D8: The mission-control/README.md `--prep` drift is owned by doc-fix Slice 2.3; new contract test (2.5) deps on it so it goes green on a corrected doc. Ownership disjoint from docs Slice 3.1 (top-level README + drive-enforcement.md). Classification: Mechanical
- D9: Dropped the drive-conformance.sh de-slop slice — full audit found no dead code (codex_present `return 0` is the load-bearing success path; all branches load-bearing). Classification: Taste
- D10: Included the `mc` router help-text sync (Slice 2.4) rather than deferring — cheap, file-disjoint, on-thesis. Classification: Taste

- D11 (plan-amendment): Slice 1.1 ownership expanded to include `test/drive-conformance.test.sh`. codex's slice-1.1 P1 (the new CI bash-suite job runs a non-hermetic test that hard-codes a machine-local leftover run-dir at line 44 and fails when absent) is rooted outside the original 1.1 ownership. The CI-green goal and the suite it runs are inseparable, so the cohesive fix folds the hermeticity repair into 1.1 rather than a separate slice (a per-slice re-review of 1.1's isolated branch could never converge while the test is non-hermetic on that branch). Re-convergence is delegated to the Phase-1 integration review (full suite + dual-voice), not a separate design re-converge, since the amendment is additive and ownership-disjoint (no other slice owns that file). Classification: Mechanical. Surfaced in the run log.
- Dual-voice value note: codex caught this; the Claude reviewer passed slice 1.1 because the leftover fixture exists locally — a "green for the wrong reason" the adversarial voice exposed.

- D12 (harden scope-widen): Phase-1 harden edits bin/drive-stop-hook.py (just OUTSIDE the phase diff) — it is the root cause of a flagged P1: `st.get` outside the per-file try lets a non-dict foreign state.json abort the scan and fail-OPEN past an owned not-done run (should BLOCK). Slice 1.2's testing work surfaced it; deferring would knowingly ship a fail-open bug in a security-relevant Stop hook. Fix = skip non-dict state.json in the per-file loop (same resilience as unreadable/unparseable) + regression test. Classification: Mechanical. Surface at Gate B.

- D13 (harden round 2, within D12's stop-hook scope): fix a same-session multi-run masking fail-open in bin/drive-stop-hook.py (loop breaks on first not-done run before checking blockability, so a waiting/disabled run masks a later active one). codex-only P1, verified against source. Move blockability checks into the scan loop; allow only if no blockable owned run. Also harden the prior regression test to be strictly red/green via the DRIVE_STOP_HOOK_PATHS scan-order env seam (the hook runs as a subprocess, so the child glob can not be monkeypatched). Classification: Mechanical (real fail-open correctness bug, on-thesis). Surface at Gate B.

## Run drive-followups-20260605-085318 (prioritize + fix top follow-ups) — 2026-06-05
(promoted from $RUN_DIR/decisions.md)

# Decisions — drive-followups (prioritize + fix top follow-ups)

- D0 [User] Scope = batch of 3 (user-composed at Stage 0 multi-select): (A) gate matcher
  composed git-path-option hardening [#1], (B) doc/comment drift sweep [#3-7,F6], (C) extend
  git-truth enforcement to IMPLEMENT-stage [#2]. Component D (forgery-proof reviewer) DEFERRED
  to its own run (large/architectural). Already-resolved followups (stop-hook seam #8/#9, CI
  wiring F4, CONTRIBUTING/Testing) excluded after a verification sweep vs the current tree.

## Design stage (2026-06-05)

- B0 [Mechanical] Three README §B items (L95 launchd row, L31 `--unbind`, ## Testing
  `tests/` coverage cell) were ALREADY fixed by run #28 (commit 229d6eb) — verified against
  the tree. EXCLUDED from the sweep (no-op churn = risk, not value). Only the genuinely-stale
  items remain in B: B1 tests/_helpers.py seed_mc_home docstring ("never mkdir it (followup
  F2)" stale after mc-hook.py:38 os.makedirs), B2 harvest/SKILL.md:67-73 `--prep`-as-flag
  heading, B3 F6 module.py:NN citations in test_done.py + test_bucket.py.
- A1 [Taste] Item A models only git's effective-cwd + gitdir/worktree override for bare-ref
  lookups, NOT a full git CLI emulation (no $GIT_DIR env, no gitdir-vs-worktree divergence) —
  conformance's ref ops resolve identically from <repo> or <repo>/.git. Minimal correct
  compose suffices. Surfaced at Gate A.
- A2 [Mechanical] Final $CWD anchoring stays in the existing caller case (drive-merge-gate.sh
  :337-342); git_target_repo composes only among git options, echoes abs-or-$CWD-relative. DRY.
- A3 [Taste] Echo worktree-preferred override (worktree→gitdir→-C base) to preserve the
  existing test-locked --git-dir/--work-tree/-C all-target-<repo> equivalence while composing
  the -C chain correctly per git's left-to-right (absolute-resets) rule.
- C1 [Taste] IMPLEMENT-stage invariant = test-presence (slice diff adds/modifies a test path)
  + explicit audited impl-waiver-<id> opt-out. Presence not coverage → cheap, omission-proof,
  git-truth. Coverage = harden/Component-D. Surfaced at Gate A.
- C2 [Mechanical] base = git merge-base slice/<runId>/<id> drive/<runId> (pure git), NOT
  state.json.phaseBaseSha — preserves git-truth-not-state-trust (D1).
- C3 [Mechanical] Fire impl-presence at the slice-merge boundary in the existing matcher,
  mid-build fail-OPEN, alongside the review check. One boundary, two checks; ship gate backstops.

## Round-1 design-review resolutions (rev 2 — codex found P1s Claude missed)
- DR1 [codex BLOCKING] Item A `--work-tree` excluded from repo-IDENTITY (was "worktree-preferred",
  a silent-allow bypass). Verified empirically: `git --work-tree=X rev-parse HEAD` keeps the
  cwd/gitdir's branch; --work-tree never retargets HEAD. Identity = --git-dir else composed -C
  else $CWD. The two test_ship_work_tree_*_reviewed_silent tests (which locked the bypass) flip to DENY.
- DR2 [codex MINOR] `-C=<p>` dropped — not real git syntax (git rejects it). -C is separate-arg only.
- DR3 [codex BLOCKING] Item C fail-CLOSED (rc1 AND rc2 -> DENY), not fail-open. Ship mode never
  re-derives test presence, so there is NO backstop -> the slice-merge boundary is irreversible for
  test-presence and must fail closed (OPERATING canonical rule). Documented posture asymmetry vs the
  fail-open review sibling (which ship DOES backstop).
- DR4 [codex MAJOR] Item C waiver = `Drive-Test-Waiver:` commit trailer (SHA-bound, in slice history),
  NOT a coordinator-writable `impl-waiver-<id>` RUN_DIR file. Same omission-proof bar as the review gates.
- DR5 [codex MAJOR] Item C tests use fixtures with a REAL `drive/<runId>` base + explicit
  clean/deny/rc-2/predicate cases (existing slice fixtures lack drive/<runId> -> a naive test would pass
  while the mode never runs). mkfixture.sh ownership -> slice 3.1.
- DR6 [codex MINOR + Claude MINOR] TEST-PATH predicate narrowed to runnable-test basenames (exclude
  _helpers.py/conftest.py/fixtures/.pyc); merge-base via git_or_die so rc>=1 -> exit 2 (no empty base).
- Both former Open Questions resolved by the above (merge-base safe under fail-closed; trailer = waiver).

## Round-2 design-review resolutions (rev 3 — codex found a new BLOCKING + MAJOR)
- DR7 [codex BLOCKING R2] Item A gitfile case: a --git-dir pointing at a LINKED-WORKTREE
  .git FILE breaks the directory-based callers (git -C / cd fail on a file) -> review gate
  fail-opens. Fix: after $CWD-anchoring, if REPO is a regular file (gitfile), reduce to its
  parent dir (dirname). Verified on the real worktree: dirname(<wt>/.git)=<wt>; git -C <wt>
  rev-parse reads the same branch the --git-dir command targets. + a linked-worktree fixture
  (mkfixture.sh -> slice 1.1). This is in-scope hardening: item A's mandate is wrong-target
  closure, and a gitfile --git-dir is the same adversarial-input axis as composed -C.
- DR8 [codex MAJOR R2] Item C waiver must be a REAL git trailer (git log
  --format='%(trailers:key=Drive-Test-Waiver...)' / interpret-trailers --parse), NOT a %B
  body substring (which falsely waives on quoted/example text). + a negative regression test.
- DR9 [codex MINOR R2] TEST-PATH predicate anchored to the repo's real runner roots
  (test/*.test.sh + tests/**/test_*.py), not bare basenames anywhere (test_root.py /
  docs/*.test.md must NOT count). Supersedes DR6's basename framing.
- DR10 [Claude MINOR R2] Split AC-A9 (was conflated): A9 = -C no =form; A9b = --work-tree
  consumed-not-identity; added AC-A11 (abs-then-rel compose -C /abs -C rel -> /abs/rel).

## Round-3 design-review resolution (rev 4 — converged on in-scope work)
- DR11 [User-Challenge, ratified at Stage-1 AUQ 2026-06-05] codex R3 BLOCKING = symlinked/
  non-canonical-gitfile --git-dir bypass of Item A's dirname reduction. RESOLUTION (user chose
  "tier per ratified threat model"): keep the canonical-worktree gitfile fix (closes the
  realistic /drive case; strict improvement, no regression — the symlink case was already
  bypassed pre-change via cd-fail fail-open); document the symlinked/non-canonical-gitfile +
  -f-follows-symlink TOCTOU as a FORGERY-CLASS residual in docs/drive-enforcement.md next to
  the $GIT_DIR residual (-> Component D). Consistent with the ratified omission-proof-not-
  forgery-proof threat model (D7). Item A ships compose + --work-tree + canonical-gitfile
  hardening. Surfaced + ratified before convergence; re-surfaced at Gate A.
- DR12 [codex MINOR+NIT R3] Decision C4 stale `*.test.*` corrected to the anchored predicate;
  waiver detection requires a NON-WHITESPACE trailer value (range format emits blank lines).
- DR0b [Taste, per prior D6/D8 precedent] Folded autoplan's completeness/scope lens INTO the
  dual-voice design review rather than running the full gstack autoplan CEO/Design/Eng/DX
  gauntlet — this batch is internal tooling (gate parser + conformance + doc fixes) with no
  product/UX/architecture tradeoffs autoplan adds value on; the load-bearing check is the
  adversarial dual-voice review (which found 3 real bypass classes). Surfaced at Gate A.

## Design-review convergence summary
- Items B (doc drift) + C (impl-presence): CONVERGED both voices, all 3 rounds (no in-scope P1).
- Item A: CONVERGED on the IN-SCOPE hardening (compose, --work-tree exclusion, canonical gitfile);
  both voices agree those are fixed. The one remaining codex P1 (symlink gitfile) is the
  user-ratified out-of-scope forgery residual (DR11). 3 design rounds; codex found a real
  bypass each of the first 3 — the adversarial voice was load-bearing throughout.

## Slice 1.1 (Item A) implement-stage decisions
- **[Mechanical]** Added `mk_linked_worktree` to `test/fixtures/mkfixture.sh` per the
  slice's file-ownership/AC mandate, but the merge-gate test is self-contained (it does
  NOT source mkfixture.sh — its RUN_DIR must live under `$HARNESS_RUNS` via `mk_rundir`),
  so AC-A10's gitfile fixtures are built inline in the test with its own helpers + a direct
  `git worktree add`. mkfixture's helper stays available for the conformance suite. DRY is
  honored within each suite's own helper namespace; duplicating the 2-line worktree-add
  inline avoids cross-sourcing two incompatible RUN_DIR conventions. (P5 explicit-over-clever.)
- **[Mechanical]** AC-A10(b)/AC-A10 push fixtures build the drive repo inline and check the
  MAIN repo out on `main` before `git worktree add … drive/<runId>`, because git refuses a
  linked worktree on a branch already checked out in the main repo (the stock `mk_ship_repo`
  leaves HEAD on drive/<runId>). Verified the resulting `.git` is a gitfile via `[ -f ]`.
- **[Mechanical]** Added a `$GIT_DIR`/`$GIT_WORK_TREE` env-residual bullet to
  docs/drive-enforcement.md alongside the new symlinked-gitfile residual note — the design's
  "Out of scope" lists both as forgery-class residuals to document there; the doc previously
  had neither. Completeness + DRY (both residuals sit together).
- Verified non-vacuousness: disabling the `[ -f "$REPO" ] && REPO=$(dirname …)` reduction
  makes AC-A10(a)+(b) FAIL (fail-open/inert), proving the gitfile bypass is real and closed.

## Slice 1.1 review round 1 (codex BLOCKING — fix, not tier)
- DR13 [Mechanical] codex slice-1.1 BLOCKING = raw `set -- $CMD` tokenization mis-handles
  quoted/empty args -> wrong-target bypass on LEGITIMATE input (spaces in paths, `-C ""`).
  Decision: FIX (not tier) — unlike the symlink residual this breaks legitimate commands (not
  a forgery construct), the root-cause fix is a proper shell-accurate tokenizer (structural >
  brittle word-split), and it's within slice 1.1's owned drive-merge-gate.sh. Re-dispatch
  implement (reviewCount 0->1, cap 8). Surface at Gate B.

## Slice 1.1 round 2 — shell-accurate tokenizer (BLOCKING fix)
- **Root-cause fix:** replaced raw `set -f; set -- $CMD` whitespace word-splitting in all
  four parsers (`subcommand_of`, `action_after`, `git_target_repo`, `push_ship_runid`)
  with ONE shared `tokenize_cmd` — a bash-3.2 char state machine (default/single/double/
  escape/dquote_escape). Splits on unquoted whitespace; treats `'…'`/`"…"` as literal
  (quotes removed, no `$var` expansion by design); handles backslash escapes; PRESERVES
  empty args from `""`/`''`. Reuse via `set_argv_from_cmd` → global `_TOKENS` → each fn
  `set -- "${_TOKENS[@]}"`.
- **set -u empty-array guard:** bash 3.2 errors on `"${_TOKENS[@]}"` when the array is
  empty under `set -u`. `set_argv_from_cmd` returns rc 1 on zero tokens (whitespace-only)
  OR unparseable, and every caller bails before the expansion on rc 1. (Mechanical.)
- **Fail-safe for unterminated quote:** return rc 1 / empty `_TOKENS` → callers treat as
  "no recognizable command" → gate goes INERT. Rationale: the real shell rejects an
  unterminated-quote command, so git never runs — going inert is safe and avoids emitting
  a mis-split argv that desyncs the gate from git. (Taste; explicit + tested.)
- **dquote_escape semantics:** inside `"…"`, backslash only escapes `" \ $ \``; any other
  backslash is preserved literally (close to bash). Adequate for the path/flag tokens the
  gate parses. (Mechanical.)
- **MINOR — dead `mk_linked_worktree`:** REMOVED from mkfixture.sh (not wired). The
  merge-gate test is self-contained (own `_gitc`/`_init_repo`, does NOT source mkfixture
  per its header), and the AC-A10 tests build worktrees inline; sourcing mkfixture just to
  reuse one helper would mix two harness conventions. Removal is the cleaner DRY outcome.
- **Tests:** +7 non-vacuous regression cases (empty `-C`, spaced `-C` path, quoted
  `--git-dir` = and space forms, quoted `-C` slice-merge, quoted `"push"` subcommand,
  `VAR="x y"` env prefix, unterminated-quote inert). Proven to FAIL against the pre-fix
  word-split (7/7) and PASS post-fix. Suite: 66/0 merge-gate, 32/0 conformance.

## Slice 1.1 review round 2 (codex 2 BLOCKING — structural fail-closed fix)
- DR14 [Taste, extends ratified DR11/D7] codex r2 found tokenize_cmd mis-handles shell-EXPANSION
  forms (tilde, ANSI-C $'...', line-continuation) the literal-string lexer can't reproduce — the
  unbounded tail of reimplementing bash lexing. Resolution (codex's own minimal-fix): fix the
  cheap deterministic ones (tilde->$HOME, strip \<newline>); for the rest ($'...', $var, $(...),
  backtick, ~user) that need unavailable context, FAIL-CLOSED (deny) for would-be-managed
  commands instead of silent bypass. This converts the whole class from bypass->deny (omission-
  safe) and ends the whack-a-mole, unifying with the pre-existing accepted $var-ref limitation
  (the gate sees the PRE-expansion string; full shell-expansion resolution is Component D). NOT
  reimplementing bash. reviewCount 1->2, cap 8. Surface prominently at Gate B.

## Slice 1.1 IMPLEMENT round 3 (DR14 executed — structural fail-closed)
- **(a) Line-continuation:** elide `\`+newline state-aware in tokenize_cmd (escape +
  dquote_escape states emit nothing for newline); NOT in single-quote state (literal, per
  POSIX). Bare `\` no longer pre-marks `started` (so a continuation-only token doesn't emit
  an empty arg, matching `git push \`↵ → `git push`). Verified empirically vs bash.
- **(b) Tilde:** new `expand_tilde` resolves leading `~/` and bare `~` → `$HOME`, applied to
  `-C`/`--git-dir` values in `git_target_repo` (and `--git-dir=`). `~user` NOT expanded
  (passwd) → caught fail-closed.
- **(c) Fail-closed catch-all `managed_git_expansion_deny`** (placed right after
  git_sub/gh_sub/glab_sub, BEFORE repo/ref resolution → unconditional emit_deny, not
  conformance-gated). Decision-critical tokens scanned = subcommand + `-C`/`--git-dir`/
  `--work-tree` values + managed-verb positional refs. Would-be-managed = managed verb OR
  unresolved subcommand OR drive/slice/phaseInt ref referenced. `_has_unresolved_expansion`
  flags `$`/backtick/`~user`. NON-git + non-managed-verb (`echo $X`, `ls $HOME`,
  `git commit -m "$msg"`, `git -C $x status`) stay inert — no over-deny.
- **(d) MINOR comment fix:** scoped the "shell rejects" claim to UNTERMINATED QUOTES only
  (bin:67 region + docs Limitations); trailing bare backslash now finalizes like default
  state (state=default|escape) → inert, NOT fail-closed (matches bash `git push \`).
- **(e) Docs:** rewrote the tokenization Limitations bullet — the boundary principle
  (resolve literal+line-cont+`~/`; fail-closed on unresolvable `$`/`(...)`/backtick/`$'...'`/
  `~user` for managed ops; full expansion → Component D).
- **Tests:** +15 non-vacuous cases (tilde target/bare/nondrive-inert; line-cont unquoted/
  split-flag/in-dquote; trailing-bs inert; fail-closed ANSI-C sub / tainted ref+drive /
  tainted -C / ~user / backtick; no-over-deny echo/ls/non-managed-git). Built a $HOME-rooted
  fixture (HOME_FIXROOT) for the `~/` tests; cleanup() extended to sweep it.
- **Suites:** merge-gate 81/0 (was 66), conformance 32/0. bash 3.2-safe throughout.

## Slice 1.1 IMPLEMENT round 3 — codex adversarial pass (4 findings, all fixed)
Ran codex adversarial review of the r3 diff; it found 4 real issues (2 High bypass, 2 over-deny):
- **F1 (High bypass): brace expansion** `git {push,}`/`{merge,}` expand deterministically →
  managed verb smuggled past the literal lexer. FIX: lexer now flags an unquoted
  brace-expansion `{…,…}` as expansion-active (cur_exp on `,` inside an open unquoted brace);
  the fail-closed catch-all denies it. Quoted `"{push,}"` stays literal → inert.
- **F2 (High bypass I INTRODUCED): line-continuation desync.** Eliding `\`<newline> in the
  tokenizer while the ref greps (slice_tokens/phaseint_token/drive_runid_from_command) still
  read RAW $CMD → a ref split across a continuation was missed → inert on a real managed merge.
  FIX: build CMD_LEX (lexed tokens, one per line) and feed ALL ref-extraction from it.
- **F3 (over-deny): read-only verb + managed ref.** `ref_seen` made any slice-ref token
  would-be-managed, so `git -C "$HOME/x" show slice/R/4a` wrongly denied. FIX: DROPPED ref_seen
  as a managed-ness trigger — would-be-managed = managed verb OR expansion-active subcommand
  ONLY (the gate only gates push/merge/branch/worktree, all literal verbs; an unresolved verb
  is still caught). No security loss; read-only verbs no longer over-deny.
- **F4 (over-deny): single-quoted literals.** Strip-then-rescan saw the `$` in `'slice/$run/4a'`
  and the `~` in `'~root/repo'` as expansions → false deny. FIX: lexer tracks expansion-active
  PER TOKEN in expansion-active CONTEXTS only (not inside single quotes), via the parallel
  _TOK_EXP array; catch-all + decision-token checks now consult _TOK_EXP (quote-aware) instead
  of re-scanning the stripped token.
- **Refactor:** managed_git_expansion_deny is now an index-walk over _TOKENS/_TOK_EXP (bash
  3.2-safe). _has_unresolved_expansion removed (replaced by the lexer's per-token flag).
- **Residual (→ Component D, documented):** single-quoted `'~/repo'` is still tilde-resolved
  (marginal, non-exploitable — literal `~/repo` dir ~never exists → git errors → nothing ships).
- **Tests:** +7 codex-finding regression guards (brace expand deny / quoted-brace inert /
  line-cont ref-split merge+phase deny / readonly-verb inert / single-quoted $-and-~user inert).
- **Suites:** merge-gate 88/0, conformance 32/0. All bash 3.2-safe.

## Slice 1.1 review round 3 (codex BLOCKING+MAJOR — make the fail-closed net PRECISE)
- DR15 [Mechanical] The round-3 fail-closed net was too broad on both ends: (a) it skipped
  gh/glab managed ship verbs (BLOCKING bypass), and (b) it scanned ALL post-subcommand
  positionals, false-denying incidental $-paths/values — critically /drive's OWN `git worktree
  add $RUN_DIR/wt/<id> -b slice/...`. Round-4 fix: taint-check expansion ONLY on the decision-
  critical tokens the gate already extracts (the verb/subcommand + the specific ref/refspec for
  merge/push/worktree-add + gh/glab pr|mr+create action) — never all positionals. This keeps the
  net omission-safe (verb/ref obfuscation -> deny) WITHOUT breaking /drive's literal-ref-but-
  $-path commands. reviewCount 2->3, cap 8.

## Slice 1.1 round-4 (IMPLEMENT) — fail-closed expansion net: gh/glab extension + precise taint scan

- **F1 (BLOCKING) gh/glab ship verbs bypassed the net.** Round-3 `managed_git_expansion_deny`
  bailed unless START binary == `git`, so `gh {pr,} create` / `gh pr {create,}` / `glab {mr,}
  create` (which expand to managed ship commands) stayed INERT. FIX: split the net into two
  binary branches via a `case "$bin"` dispatcher — `managed_git_expansion_deny_git` (unchanged
  git logic, refactored) + new `managed_cli_expansion_deny` for gh/glab. The gh/glab branch
  walks to the subcommand (pr/mr) and action (create) the same way `subcommand_of`/`action_after`
  do, and DENIES iff either token is `_TOK_EXP`-tainted AND the pair could be the managed
  `pr/mr create` shape (literal mismatches like `gh pr view --json $x` stay inert → no over-deny).
- **F2 (MAJOR over-deny — would wedge /drive) blanket positional scan.** Round-3 taint-checked
  EVERY non-flag positional after the subcommand as a ref, so `git worktree add $RUN_DIR/wt/<id>
  -b slice/.. <sha>` (/drive's OWN command) and `git merge -s $strategy slice/..` were wrongly
  DENIED. FIX: replaced the blanket scan with a PRECISE per-verb operand scan that taint-checks
  ONLY the real ref operand(s): push→refspecs after the remote; merge→ref positionals (skip
  -s/-X/--strategy*/-m/-F values); branch→name+start-point (skip -u/--set-upstream-to/-t);
  worktree add→the -b/-B branch VALUE only (path positional + start-point sha are NOT refs).
  An expansion-active (unknown-shape) subcommand still falls back to a conservative full scan.
- **Tests:** +7 (95 total, was 88). Vacuity proven: the 2 over-deny + 3 gh/glab tests FAIL
  against round-3 bin (over-deny → wrong shell-expansion DENY; gh/glab → empty/inert bypass).
  drive-conformance (32) + all other suites green.
- **Doc:** updated docs/drive-enforcement.md (expansion-net section) to describe the two binary
  branches + the precise per-verb ref-operand extraction, replacing the stale "every positional
  ref/refspec of a managed verb" wording. No deviation from the prompt scope.

## Slice 1.1 CONVERGED (round 4) — DR16
- DR16 [Taste, extends DR11/D7] Converge slice 1.1 after 4 review rounds. Claude r4 CONVERGED
  clean (zero findings); codex r4 died exit-144 (flaky infra) before a verdict but surfaced 2
  residuals, both ROUTED: (a) attached short-option `-b<val>` form -> Phase-1 HARDEN (cheap,
  concrete, forgery-class /drive-never-emits hardening); (b) gh `--head` ship-detection ->
  HIGH-sev followup (pre-existing, push-gate-backstopped, out-of-matcher-scope). Continuing the
  slice loop on the unbounded adversarial-parser tail is gold-plating a surface the ratified
  threat model excludes; the high-value hardening (--work-tree bypass, compose, gitfile, quoting,
  fail-closed net, gh/glab, precise taint) is shipped + dual-verified. Surface at Gate B.

## Phase 1 HARDENED — attached short-option + doc accuracy
- DR-H1 [Mechanical] Attached short-option `-b<val>`/`-B<val>` (git accepts `-bslice/x` as ONE
  token, verified). Fixed BOTH dimensions: (1) expansion taint — `managed_git_expansion_deny_git`
  worktree arm now taint-checks the attached token's own `_TOK_EXP` flag (`-b?*|-B?*`), so
  `git worktree add /p -b$branch` DENIES like the separate `-b $branch`; (2) literal-attached
  plan-gate detection — CMD_LEX now splits an attached `-b`/`-B` off its value onto a separate
  line so the slice ref grep's name-char boundary no longer misses `-bslice/<runId>/<id>` (was a
  literal-attached plan-gate/slice bypass). 4 new tests (tainted -b/-B DENY; literal-attached
  plan-gate DENY + reviewed-silent non-vacuous pair).
- DR-H2 [Mechanical] SCOPED to `-b`/`-B` only (NOT `-c`/`-C`): git's GLOBAL `-C`/`-c` REJECT the
  attached form (`-C/path` → "unknown option", verified), and attached `-c<branch>`/`-C<branch>`
  belong to `git checkout`/`git switch` — which are NOT managed verbs in this gate. So there is no
  managed-verb attached `-c`/`-C` ref to taint. The followup's mention of `-c<val>` is therefore
  out of the matcher's managed surface; no action needed beyond the `-b`/`-B` worktree fix.
- DR-H3 [Mechanical] Doc accuracy: corrected the brace-RANGE overclaim (gate:~90 + docs:194-195)
  to COMMA-form-only — the lexer flags only `,`-in-brace; a bash `{a..z}`/`{1..9}` range expands
  single chars/ints so it cannot build a managed verb/ref (no range-form bypass). Added the
  rationale comment at the `,`-in-brace lexer line. The trailing-backslash claim (target #2) was
  already correct in tree (gate 71-79 + docs 183-191) — no edit needed.
- HARDENED: full bash suite green (merge-gate 99/0, +4 new; conformance 33, hook-lib 30, e2e 24,
  install 49, stop-guard 10), pytest 263/0, all under bash 3.2.

## Phase 1 harden round 1 (codex harden-regress: revert a net-negative forgery-class fix) — DR17
- DR17 [Taste, extends DR11/D16] The harden's attached-`-b` closure (7959eaf) used a GLOBAL
  CMD_LEX split that codex harden-regress showed introduced a real wrong-review BYPASS
  (`git merge -m -bphaseInt/<id>/1 phaseInt/<id>/2`) + an over-deny (`worktree lock --reason
  -b$note`). The gap it closed is forgery-class (/drive uses the separate literal form). A
  forgery-class fix that introduces a real bypass is net-negative -> REVERT the attached-form
  code to converged 71eac86; KEEP the safe doc-accuracy fixes (brace-range comma-form-only +
  attached-form residual note). Attached-form -> documented out-of-scope residual (DR11 tier).
  (Pattern: don't gold-plate a forgery-class surface, esp. when the fix regresses. Claude
  harden-regress approved it; codex caught the over-broad split — adversarial voice load-bearing.)

## Phase 2 doc-drift slices CONVERGED — DR19
- DR19 [Mechanical] Phase-2 slices 2.1/2.2/2.3 are PURE doc/comment edits (helpers docstring,
  harvest SKILL --prep retitle, F6 line->function citations). Claude review verified all 3
  accurate vs code + docs-only (CONVERGED). codex infra was DOWN (2 consecutive network
  disconnects, retried once) -> CODEX_UNAVAILABLE for this round (documented degradation; zero
  P1; justified by zero logic/security surface). Will insist codex returns for the Phase-3
  impl-presence code. Surface at Gate B.

- 3.1 [Mechanical] impl-presence mode: waiver detection uses `git log base..tip
  --format='%(trailers:key=Drive-Test-Waiver,valueonly,separator=%x00)'`, then strips NULs +
  all whitespace and treats any leftover char as a real non-empty trailer value. This is
  REAL trailer parsing (empirically: a mid-body prose mention of the string yields no value),
  not a %B body substring — closes the AC-C3b forgery-by-prose path. NUL separator avoids a
  newline-in-value ambiguity across multiple commits.
- 3.1 [Mechanical] base = `git_or_die merge-base slice/<runId>/<id> drive/<runId>`; an empty
  merge-base (disjoint, rc=1) or unresolvable ref (rc=128) both exit 2 via git_or_die — never
  a silent empty base feeding a malformed `<empty>..tip` diff (fail-closed at the hook).
- 3.1 [Mechanical] is_test_path predicate anchored to runner roots, bash-3.2 `case`-globs only
  (no regex): `test/*.test.sh` rejects nested `test/sub/x.test.sh`; under `tests/` requires
  basename `test_*.py`/`*_test.py` and excludes `_helpers.py`/`conftest.py`/`*.pyc`/any
  `fixtures/` or `__pycache__/` segment. Verified across 13 edge paths.

## Codex infra outage during Item C — DR20
- DR20 [User-Challenge, ratified at Stage-3 AUQ 2026-06-05] codex (the load-bearing adversarial
  voice) went into a sustained infra outage during Item C (the security-relevant impl-presence
  gate). User chose "proceed + queue codex re-review": continue Item C on the adversarially-
  oriented Claude voice (single-voice, CODEX_UNAVAILABLE this round), but DO NOT ship Item C
  without a codex adversarial pass — retry codex at each review point; if still down at ship,
  surface PROMINENTLY at Gate B as a REQUIRED codex re-review of the Item C diff before merge.
  state.codexReReviewC=true tracks the obligation. (Phase 1/2 were full dual-voice / pure-doc;
  only Item C's codex coverage is deferred.)

## Slice 3.2 (Item C) — gate hook + matcher wiring (fail-CLOSED)
- 3.2 [Mechanical] No separate fail-closed VARIANT of run_conformance needed. run_conformance
  already normalizes the raw exit to 0|1|9, and the fail-closed-vs-fail-open posture lives at the
  CALL SITE (exactly like plan/ship use `rc -ne 0` and slice/phase-review use `rc -eq 1`). The
  impl-presence check therefore reuses run_conformance and tests `rc -ne 0 → DENY` (covers rc 1
  violation AND rc 9 abnormal = fail-CLOSED), placed right after the existing fail-OPEN
  `slice-merge:<id>` review check in the same per-slice loop. One boundary, two checks, deliberate
  posture asymmetry (Decision C3 / DR3). The review check's posture is untouched.
- 3.2 [Mechanical] THREE pre-existing slice-merge tests had to be updated because the boundary now
  runs a SECOND (fail-closed) check: (a) test_slicemerge_allow_silent now uses a complete fixture
  (real drive/<runId> base + a test-carrying slice) via a new mk_impl_slice_repo helper, since
  "silent" now requires BOTH checks to pass; (b)+(c) test_rcnorm_brokenconf_slice_silent and
  test_cdfail_slice_silent are RENAMED to *_failclosed_deny — a broken-checker/cd-fail (rc 9) is
  fail-OPEN for the review check but fail-CLOSED for impl-presence, so the boundary now DENYs via
  impl-presence (the correct new behavior per Decision C3). The unreviewed slice-merge DENY tests
  are unaffected (the review check denies first). Vacuity proven: flipping impl-presence to
  fail-open makes 8 merge-gate tests FAIL.
- 3.2 [Mechanical] mk_impl_slice_repo builds fixtures inline in the test (mkfixture.sh is NOT owned
  by 3.2) with content knobs test|notest|waiver|waiver-body. The waiver-body negative fixture puts
  the `Drive-Test-Waiver:` line in the MIDDLE of the body with prose AFTER it so git does NOT parse
  it as a trailer (guards the substring trap, AC-C3b's sibling at the gate layer).
- Suites: merge-gate 102/0 (+5 new Item-C cases, 3 updated), conformance 46/0. bash 3.2-safe.

## Phase 3 integration: e2e test plan-amendment — DR21
- DR21 [Mechanical, plan-amendment] The Phase-3 integration suite is RED: drive-enforcement-e2e.test.sh
  2 fails — its slice-merge scenarios encode PRE-impl-presence behavior (a reviewed-but-test-less slice
  was silent-allow; slice-merge on exit-2 was fail-open-silent). Item C INTENTIONALLY changes both
  (no-test -> DENY; abnormal -> fail-CLOSED DENY, Decision C3). The e2e fixtures also lack a
  drive/<runId> base branch, so impl-presence merge-base exits 2. The e2e test was owned by NO slice
  (plan gap — it should have been in slice 3.2's surface since 3.2 changed the gate). Amendment:
  extend the Phase-3 surface to include test/drive-enforcement-e2e.test.sh; update the 2 scenarios to
  the new enforcement (add a drive base + a test file to the happy-path slice fixture so both checks
  pass; flip the exit-2 fail-mode assertion to fail-CLOSED DENY). Test-only; production code is correct
  + reviewed. Fixed as a phase-integration fix in the phaseInt/3 worktree.

## Phase 3 HARDEN stage (2026-06-05)

- H3-1 [Mechanical] Doc root-cause exception applied: docs/drive-enforcement.md (owned by
  Phase 1 only — plan omission) updated for Item C's new impl-presence gate: usage/mode line,
  a conformance-section paragraph describing the mode (merge-base base, runner-anchored
  test-path predicate incl. nested-test/sub rejection, real trailer parsing, exit-2 abnormal),
  a gate-chain TABLE row + a "Posture asymmetry at the slice-merge boundary (C3)" paragraph
  (impl-presence fail-CLOSED vs the fail-OPEN review check; no ship backstop), and a Limitations
  bullet (impl-presence omission-proof not forgery-proof — forged trivial test passes).
- H3-2 [Mechanical] Doc↔code coherence: the rc-normalization comment block (~ln 909) AND the
  file-header D4 fail-mode comment (~ln 15) AND the variable-ref Limitations bullet all said
  "mid-build gates fail OPEN" as a blanket rule; corrected each to scope it to the REVIEW gates
  and carve out the impl-presence fail-CLOSED exception (propagate-the-fix-everywhere lens).
- H3-3 [Mechanical] Missing-coverage lens: added two test cases for previously-untested
  is_test_path branches — test_suffix (tests/foo/x_test.py → *_test.py form → clean) and
  test_sh_nested (test/sub/x.test.sh → nested, runner globs only test/*.test.sh → violation).
  New fixture variants in mkfixture.sh. No production logic changed (the Item C code had only
  doc-coherence findings; no slop/dead-code/logic bugs found). Suite stays green: bash
  conformance 48, e2e 25, merge-gate 102, stop-guard 9, install 48, hook-lib PASS; pytest 263.

## Phase 3 harden round 2 (codex recovered, found 3 Item-C bypasses) — DR22
- DR22 [Mechanical] codex infra recovered; the DR20-required Item-C adversarial pass ran and found 3
  real bypasses Claude single-voice missed (deleted-test counts; dotfile test counts; multi-runId
  octopus checks only the first runId). Fix in harden round 2: (1) impl-presence diff uses
  --diff-filter=AM (deletions don't count) — supersedes design edge-case-3's weak "deletion counts";
  (2) is_test_path rejects dotfile basenames (match the real runner glob); (3) gate resolves each
  slice token's own runId (or fail-closed on a multi-runId merge). + regression tests for all 3.
  This VALIDATES DR20 (requiring codex on Item C) — the adversarial voice was load-bearing.

## Phase 3 HARDEN — Item C codex adversarial fixes (2026-06-05)

- H-C1 [Mechanical] Finding 1 (BLOCKING): impl-presence counted DELETED test paths as
  evidence. Fixed by changing the slice diff to `git diff --diff-filter=AM --name-only`
  (added/modified only) in bin/drive-conformance.sh — deleting tests/test_auth.py no longer
  satisfies the invariant. Regression: mkfixture `del_test` variant + conformance test.
- H-C2 [Mechanical] Finding 2 (BLOCKING): is_test_path matched dotfile basenames
  (`test/.noop.test.sh`, `tests/mc/.foo_test.py`) on bash 3.2 `case`, but the real bash
  runner glob + pytest collection SKIP dotfiles. Fixed by rejecting any `.*` basename up
  front in is_test_path (covers both branches). Regression: `dot_test_sh` + `dot_test_py`
  fixtures (the pytest one uses `.foo_test.py` so it MATCHES `*_test.py` — non-vacuous).
- H-C3 [Taste→chose option (b)] Finding 3 (MAJOR): multi-slice octopus merge across
  different runIds checked only the first runId in bin/drive-merge-gate.sh. Chose the
  simpler-safe option (b): a merge naming >1 distinct runId fails CLOSED (deny) — it is
  never a normal /drive op (/drive emits one `git merge slice/<runId>/<id>` per slice).
  slice_runids tracks the distinct-runId set; >1 → emit_deny before the per-slice loop.
  Regression: multi-runId octopus DENY + single-runId multi-slice not-over-denied tests.
- H-C4 [Mechanical] docs/drive-enforcement.md: impl-presence row now states ADD/MODIFY
  (`--diff-filter=AM`, deleted/dotfile excluded); added a paragraph documenting the
  multi-runId octopus fail-closed posture under "per slice token".
- Verify: full bash suite (104+51+25+9+48 + hook-lib PASS) + pytest (263) all green;
  all 4 new positive tests proven to FAIL against pre-fix code (non-vacuous).

## Phase 3 harden round 3 (refine the round-2 fixes — both voices) — DR23
- DR23 [Mechanical] Dual-voice harden-regress on the round-2 fixes found 2 edges: (a) --diff-filter=AM
  over-blocks R/C/T test additions (Claude: rename false-deny; codex: R/C/T) -> use --diff-filter=d
  (exclude deletions only); (b) the multi-runId octopus deny is order-dependent + fires AFTER the
  single-runId inert-exit, so a stale-first octopus bypasses (codex) -> move the distinct-runId
  fail-closed deny BEFORE single-runId resolution. + R/C-into-test and stale-first-octopus regression
  tests. Round 3 (harden cap). Dotfile + delete-only fixes confirmed good.

## Ship: dedicated de-slop pass — DR24
- DR24 [Taste, user-requested at Gate B] Ran a dedicated conservative de-slop/simplify pass over the
  full diff before push (harden's de-slop lens had run but was overshadowed by the security findings).
  Outcome: the diff was already clean — only 3 comment-only fixes (stale --diff-filter=AM -> =d
  references in 2 test files). Gate logic, postures, fixtures all deliberately LEFT (load-bearing /
  meaningfully-distinct). Suite stayed 270/0 + 263/0. Confirms the iterative-patching slop was minimal
  (the harden passes + dual-voice reviews kept it clean). Comment-only delta -> phase-3 review re-bound.
