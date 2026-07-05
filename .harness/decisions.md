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


## Run lever2-rebirth-20260610-145705 (2026-06-12) — proactive-rebirth trigger (lever 2)

# Decisions — lever2-rebirth (proactive-rebirth trigger)

### 2026-06-10 -- D1: Detection reuses the statusline transcript-token-sum
**Stage:** plan
**Task:** lever2-rebirth — proactive context-pressure trigger
**Question:** How does a running session learn it is near its context budget?
**Options considered:** (a) reuse the statusline's transcript-token-sum (latest assistant `input+cache_creation+cache_read` ÷ model window); (b) a new independent token estimator/probe
**Chosen:** (a)
**Reasoning:** Verified on a real transcript that the statusline formula = live context occupancy; reusing it (one shared source of truth) is DRY, keys off the deterministic upstream signal, and needs no new platform capability.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D2: Stop hook = primary detection surface; coordinator self-check = secondary
**Stage:** plan
**Task:** lever2-rebirth
**Question:** Where does the context-pressure check live?
**Options considered:** (a) Stop hook high-water check (fires every turn, sees run + transcript) as primary + coordinator self-check at checkpoint boundaries as backstop; (b) coordinator-only; (c) hook-only
**Chosen:** (a)
**Reasoning:** The continuation Stop hook already fires every turn, owns the keep-going-vs-pause decision, and receives the transcript — natural primary; the coordinator self-check catches a single huge turn and works if the hook is absent. Both share one threshold/window helper.
**Reversibility:** easy
**Classification:** Taste

### 2026-06-10 -- D3: Rebirth is a prompted handshake, not a self-restart
**Stage:** plan
**Task:** lever2-rebirth
**Question:** How does re-entry into a fresh session happen?
**Options considered:** (a) outgoing session checkpoints + surfaces a paste-ready `/drive <runId>` resume line; a user-pasted fresh session runs the lossless resume path; (b) programmatic self-restart
**Chosen:** (a)
**Reasoning:** Spike-verified there is NO programmatic session-spawn/restart/headless re-entry anywhere in the harness; a Stop hook can only block/allow, not launch a session. Re-entry must be human/externally initiated. We don't fabricate a capability the platform lacks.
**Reversibility:** medium
**Classification:** Taste

### 2026-06-10 -- D4: Reuse the waiting / Present-human-pause / run-graph / /goal machinery; add waiting="rebirth"
**Stage:** plan
**Task:** lever2-rebirth
**Question:** What channel carries the rebirth pause/handoff?
**Options considered:** (a) reuse the existing single pause routine, adding only a new `waiting="rebirth"` reason + run-graph node; (b) a bespoke rebirth pause path
**Chosen:** (a)
**Reasoning:** Every pause already flows through one routine (set waiting → emit graph → present; re-arm /goal at gates). Rebirth is just another reason — DRY, and inherits the omission-proof graph emission + autonomous-continuation contract for free.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D5: The rebirth handoff fails CLOSED on the checkpoint self-audit
**Stage:** plan
**Task:** lever2-rebirth
**Question:** What guards the irreversible "hand off to a fresh session" step?
**Options considered:** (a) gate the handoff on a positive checkpoint-complete ⇒ resumable signal; if unconfirmed, do NOT rebirth (continue / surface a STOP); (b) hand off optimistically and let resume sort it out
**Chosen:** (a)
**Reasoning:** Handing off a run the successor can't reconstruct is the irreversible hazard; place the hard gate at the irreversible boundary, failing closed — consistent with the harness enforcement posture.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D4 (amended, design review 2): rebirth reuses the pause routine WITH a pre-pause checkpoint-proof exception
**Stage:** plan
**Task:** lever2-rebirth
**Question:** Is rebirth literally "the shared pause routine + one new `waiting` reason," or does it differ from every other pause?
**Options considered:** (a) rebirth adds only a new `waiting="rebirth"` reason on the shared routine (original D4 wording); (b) rebirth reuses the routine but injects a checkpoint-proof step (compute+write+validate `checkpoint_complete`) BEFORE the `waiting` write — every other pause reason sets `waiting` directly
**Chosen:** (b)
**Reasoning:** Codex MINOR (D4/D5 contradiction) — after the D5 amendment, rebirth no longer literally "adds only a new reason"; it does the checkpoint proof first. Reconciled: still DRY (shared routine, omission-proof graph emission, autonomous-continuation contract) but with the explicit pre-pause exception making the proof precede the pause. Amends D4.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D8: the checkpoint_complete proof is narrator-independent — durable artifacts incl. a redesign epoch + in-flight markers
**Stage:** plan
**Task:** lever2-rebirth
**Question:** Is the `checkpoint_complete` proof actually independent of the coordinator's self-report, or does it still trust the narrator for the redesign count and the "nothing in flight" / "no partial mutation" conditions?
**Options considered:** (a) keep the uniform `max(state, artifact-count)` rule + safe-boundary conditions backed by the coordinator's assertion; (b) make every proof input a durable, independently-checkable artifact: a durable **redesign epoch** (append-only per-attempt marker written BEFORE the round/state mutation; phasedesign-review files scoped `review-phasedesign<P>-r<R>-N.md`) so `redesigns` is reconstructable from disk; **precise per-counter rules** (not one lossy formula) keeping `hardenRound`'s `AppliedEdits: yes` qualifier; a **per-dispatch in-flight marker** (written before each subagent/codex dispatch, cleared on result-recorded) so "nothing in flight" = "no open marker on disk"; partial-mutation detection from git/branch state
**Chosen:** (b)
**Reasoning:** Both voices converged on the harness's own core principle — an actor's self-reported "done" is not evidence. Claude+Codex MAJOR: `redesigns` had no artifact (a dropped 3rd-REDESIGN increment defeats the redesign-cap-3 STOP → infinite redesign loop), and the `review-phasedesign<P>-N` count is ambiguous across redesigns once `round` resets. Codex MAJOR: the safe-boundary conditions trusted the coordinator's assertion. Claude MINOR: the uniform formula dropped `hardenRound`'s `AppliedEdits: yes` qualifier (over-counts clean audits, false-trips cap-3). The proof must be re-runnable by an independent successor / external auditor to the same answer. Further amends D5; load-bearing principle of the build.
**Reversibility:** medium
**Classification:** Mechanical/Taste

### 2026-06-10 -- D5 (amended, design review 1): fail-closed ORDERING + narrator-independent proof
**Stage:** plan
**Task:** lever2-rebirth
**Question:** What exactly does the fail-closed checkpoint gate check, and when relative to the `waiting` pause?
**Options considered:** (a) set `waiting="rebirth"` first (to satisfy the continuation contract) then checkpoint — original; (b) write+validate a durable `checkpoint_complete` marker FIRST, then set `waiting`; and base the proof on narrator-independent durable artifacts (git refs + persisted review/harden files) rather than a self-read of `state.json`
**Chosen:** (b)
**Reasoning:** Codex MAJOR — ordering was backwards: `waiting`-first lets the turn END before resumability is proven (fail-open). Claude MINOR — a self-read of `state.json` trusts the narrator and can pass on a stale-but-well-formed file. Proving from durable artifacts before pausing makes the gate honest and fail-closed. Amends D5.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D6: detection is SIGNAL-ONLY, separated from handoff; coverage is honest not full
**Stage:** plan
**Task:** lever2-rebirth
**Question:** Should detection (which fires at an arbitrary turn boundary) act directly, and what coverage can it honestly claim?
**Options considered:** (a) the Stop hook / self-check hands off as soon as it detects pressure; (b) detection only RECORDS a durable `rebirth_pending` signal, and the coordinator hands off later at a proven safe boundary (no subagent/codex chain in flight, artifacts flushed); acknowledge residual single-catastrophic-turn + absent-hook gaps as known limits
**Chosen:** (b)
**Reasoning:** Claude MAJOR + Codex BLOCKING — a turn boundary is arbitrary (mid-slice/mid-assembly/mid-review); handing off there can lose context-only state (cap counters, mid-assembly position, the async in-flight review chain). Separating detection from handoff-execution and proving a safe boundary first is what makes "lossless" true. Codex MAJOR — boundary-only self-checks can't catch a single huge turn or an absent hook, so state the headroom/residual honestly rather than overclaim.
**Reversibility:** medium
**Classification:** Taste

### 2026-06-10 -- D7: resume rebinds state.sessionId to the live session before continuing
**Stage:** plan
**Task:** lever2-rebirth
**Question:** After rebirth, how does the run stay attributable to the (new) incoming session so the Stop hook keeps blocking and future rebirths keep detecting?
**Options considered:** (a) leave `state.sessionId` as the outgoing session's id; (b) the resume path rewrites `state.sessionId` to the live `$CLAUDE_CODE_SESSION_ID` before continuing
**Chosen:** (b)
**Reasoning:** Codex BLOCKING — confirmed against `drive-stop-hook.py` L97: the hook blocks only when `state.sessionId == payload.session_id`. With a stale outgoing id, the continuation hook never blocks (auto-continue dies) and rebirth detection (same match) never fires — so a run could rebirth at most once. Rebinding on resume (for any new-session resume, since crash-recovery has the same staleness) fixes multi-rebirth. Foundational → Phase 1.
**Reversibility:** easy
**Classification:** Mechanical
</content>

### 2026-06-10 14:5 -- Substitute 3-round dual-voice design review for gstack autoplan
**Stage:** plan
**Task:** proactive-rebirth trigger (lever 2)
**Question:** Run gstack /autoplan (CEO->Design->Eng->DX) before Gate A, or rely on the dual-voice design-review convergence?
**Options considered:** (a) full autoplan then dual-voice; (b) dual-voice design-review only.
**Chosen:** (b) -- ran 3 rounds of adversarial dual-voice (Claude + codex) to convergence.
**Reasoning:** This is an internal harness/tooling change; autoplan's CEO/DX/product lenses add little, and loading 4 review skills into the coordinator's own context is directly counter to THIS task's goal (reduce coordinator context). The Eng-altitude concerns autoplan would raise were covered adversarially by the dual-voice pass (4 P1s found+fixed). Classification: Taste -- surfaced at Gate A for override.
**Reversibility:** easy (can run autoplan on design.md before approving).

### 2026-06-10 15:3 -- Resume is explicit-by-runId; run discovery rejected
**Stage:** plan (Gate A)
**Task:** proactive-rebirth trigger (lever 2)
**Question:** Should /drive auto-discover in-progress runs on this repo (repoId-filtered list + liveness guard) when invoked without a runId, or resume ONLY via an explicit /drive <runId>?
**Options considered:** (a) repoId-tagged discovery + disambiguation list + live-run adoption guard; (b) explicit runId only, recovery documented (ls -t ~/.claude/harness-runs/ or git branch --list 'drive/*').
**Chosen:** (b) -- user call at Gate A.
**Reasoning:** Explicit-over-clever; discovery is disproportionate machinery for the lost-line case, and an explicit runId is inherently unambiguous under multiple concurrent runs on one repo (no adoption-guess hazard). Cost accepted: re-typing the task forks an inert, recoverable orphan run.
**Reversibility:** easy (discovery can be added later without changing the runId contract).

### 2026-06-10 -- D9: redesign epoch rides the review SCOPE TOKEN (phasedesign<P>-r<R>), bare for epoch 0
**Stage:** design (phase 1)
**Task:** lever2-rebirth
**Question:** How do epoch-scoped phasedesign review files coexist with the real consumers of review-<scope>-N.md naming?
**Options considered:** (a) bare filename change review-phasedesign<P>-r<R>-N.md as a new naming scheme (per design.md wording); (b) make the epoch part of the SCOPE TOKEN itself — phasedesign<P>-r<R> for R>=1, epoch 0 keeps the bare token.
**Chosen:** (b)
**Reasoning:** Real-code check: drive-conformance.sh highest_review_file accepts only pure-integer N suffixes, so (a) makes phasedesign-gate:<P> permanently fail; drive-review.md derives review file AND codex sibling from one <scope> token; the run graph names the family. With (b) every helper works unchanged on the qualified token, each epoch keeps its own codex file (today a redesign CLOBBERS prior-epoch review files), and a no-redesign run is byte-identical to today. Resulting filenames still match design.md's intent.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D10: checkpoint proof lives in bin/drive-conformance.sh --mode checkpoint
**Stage:** design (phase 1)
**Task:** lever2-rebirth
**Question:** Where does the narrator-independent checkpoint_complete proof live — a new bin/ script, prose-only in drive.md, or a conformance mode?
**Options considered:** (a) new bin/drive-checkpoint.sh; (b) prose procedure in drive.md; (c) a new --mode checkpoint in the existing conformance script, with a counters output key.
**Chosen:** (c)
**Reasoning:** Explicit-over-clever + DRY: drive-conformance.sh is already the pure function over git refs + RUN_DIR artifacts that every gate calls, never reads state.json (the proof's exact truth model), and has the {"clean","mode","tip","violations"} / exit 0-1-2 envelope. Prose-only would leave the proof re-implemented by each coordinator turn (narrator-adjacent); a new script duplicates the helpers. The counters output gives resume-repair and the Phase-3 handoff one shared computation point.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D11: checkpoint_complete = durable sha-bound marker FILE; rebirth_pending = state field
**Stage:** design (phase 1)
**Task:** lever2-rebirth
**Question:** Durable file vs state.json field for the two new flags (per D8: proofs derive from durable artifacts)?
**Options considered:** (a) both as state fields; (b) both as files; (c) checkpoint-complete.marker as a file (content embeds the proof JSON incl. tip; consumers reject a tip mismatch as no-proof), rebirth_pending as a state field.
**Chosen:** (c)
**Reasoning:** checkpoint_complete is a PROOF RECORD an independent successor must be able to trust/re-derive -> durable file, sha-bound so it can never cover later work. rebirth_pending is a SIGNAL in the hint class — it steers the live coordinator and is never a proof input — so a state field suffices and keeps the Phase-2 writers simple (state.json is already durable on disk for signal purposes).
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D12: in-flight marker = one per dispatch unit, no pid; stranded recovery = adopt / re-dispatch / STOP, never wait
**Stage:** design (phase 1)
**Task:** lever2-rebirth
**Question:** Marker granularity, schema, and the stranded-marker (process died after marker-write) recovery rule.
**Options considered:** (a) record worker pid + liveness probe, wait when alive; (b) no pid — any open marker at resume is stranded by definition; recovery adopts an already-complete on-disk artifact, else re-dispatches the unit per the existing resume rules, else STOPs when the cap would be breached.
**Chosen:** (b)
**Reasoning:** Followup P2 #1: died-before-dispatch and died-before-clear are indistinguishable on disk and both must fail closed; a pid invites a "wait for the worker" path the rule forbids. Adopting a parseable artifact is consistent (it trusts the work product, not the narrator) and avoids burning cap rounds re-running completed work. assemble + branch-advance carry no marker: partial assembly is git-detectable and idempotently rebuilt; the advance is a single atomic ref move resume already completes.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D13: redesigns reconstructs as max(state, HIGHEST epoch R), not marker count
**Stage:** design (phase 1)
**Task:** lever2-rebirth
**Question:** Is the redesign counter the COUNT of epoch markers (design.md wording) or the highest R?
**Options considered:** (a) count of distinct markers; (b) highest R among redesign-<P>-r*.marker, with an epoch-gap violation in the checkpoint proof when the set is not gapless.
**Chosen:** (b)
**Reasoning:** Epochs are sequential, so marker rN proves N redesigns even if an intermediate marker was lost; counting would under-count there and weaken the redesign-cap-3 (the unsafe direction). Equivalent when the append-only discipline holds; the proof flags the gap for a human either way.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D14: counter repair at resume is one-directional max(state-hint, artifact) for all five counters
**Stage:** design (phase 1)
**Task:** lever2-rebirth
**Question:** When state.json says MORE than the artifacts, which wins — and how does that square with "never read state.json for the proof"?
**Options considered:** (a) artifacts always win (state ignored entirely); (b) state is a resume-REPAIR HINT that can only RAISE a counter (max rule), while the checkpoint proof and run graph assert only artifact-derived values.
**Chosen:** (b)
**Reasoning:** Followup P2 #2. The counters bound loops: honoring a higher state value risks at worst a premature STOP (safe — a human looks); honoring a lower artifact count risks a loop overrunning its cap (unsafe). A hint may tighten a safety bound, never loosen a proof — this states explicitly why max(state, count) and "state is never a proof input" do not contradict.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D15: phaseReview round = review-phase file count MINUS AppliedEdits:yes harden files
**Stage:** design (phase 1, review round 1)
**Task:** lever2-rebirth
**Question:** harden-regress writes into the same review-phase<P>-N.md family without incrementing the round — how does the artifact rule stay a faithful mirror?
**Options considered:** (a) rename regress files (breaks the phase-merge gate's highest-N + post-harden-sha check); (b) keep the bare file count (overcounts every hardened phase); (c) subtract the count of harden-<P>-*.md with AppliedEdits: yes — the durable 1:1 marker of a regress pass (drive-harden.md Step 4 sets yes before dispatching the regress review).
**Chosen:** (c)
**Reasoning:** Both voices P1. Exact while the cap-8 is live (no harden file can exist before the phase review converges → no lost increment, no false STOP); once any harden artifact exists the counter is cap-dead, so the one crash window (yes written, regress review not yet) undercounts by 1 where no cap can be affected. yes-count > review-count → checkpoint violation regress-mismatch.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D16: resume derives phase-design convergence from current-epoch artifacts; redesign-cap re-derived at resume
**Stage:** design (phase 1, review round 1)
**Task:** lever2-rebirth
**Question:** A crash between the REDESIGN epoch-marker write and the state mutation leaves phaseDesign[<P>].status == "converged" — resume (keyed on that hint) would dispatch slices against the divergent design, and the recovered redesigns == 3 STOP had no firing mechanism outside the handler.
**Options considered:** (a) keep the status-hint check and rely on the I5 gate as backstop (hooks optional; its deny re-REVIEWS, not re-authors); (b) resume DERIVES the status — converged only if the epoch-aware phasedesign-gate:<P> passes for the current epoch (highest redesign marker R), else re-run Execute step 1 (re-author) — plus a resume-side STOP when artifact-derived redesigns >= 3 with the current epoch unconverged.
**Chosen:** (b)
**Reasoning:** Claude P1. The marker's recovered increment must drive the decisions it exists for (re-design, cap STOP) without re-entering the handler; delegating the derivation to the I5 gate keeps one computation point.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D17 (amends D11): checkpoint-complete.marker is record-not-authorization and SINGLE-USE
**Stage:** design (phase 1, review round 1)
**Task:** lever2-rebirth
**Question:** proof.tip binding under-detects staleness — drive/<runId> moves only at the step-6 advance, so a tip-matching marker can survive later mutations and be replayed across resumes.
**Options considered:** (a) bind to a wider fingerprint (ref census + inflight glob + nonce); (b) the marker never authorizes: tip-match is necessary not sufficient, consumers needing current safety re-run --mode checkpoint, and the marker is SINGLE-USE — the resume that validates it deletes it as its first act after the sessionId rebind (valid for exactly one resume; any later checkpoint re-proves from scratch).
**Chosen:** (b)
**Reasoning:** Codex P1. Re-proving is already one conformance call (cheap, the proof's native form); a wider fingerprint still ages the moment work resumes and adds schema for no authorization the design ever grants the marker.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D18: --mode checkpoint relates phaseInt refs by two-direction ancestry; no numeric phase-id ordering
**Stage:** design (phase 1, review round 1)
**Task:** lever2-rebirth
**Question:** "highest-P phaseInt" assumes numeric phase ids, but ids come from design.md ## Phases and may be non-numeric (e.g. 4a).
**Options considered:** (a) numeric/lexical max over phaseInt refs (silently skips 4a, like audit-mode's integer filter); (b) check EVERY phaseInt/<runId>/* ref: its tip must be an ancestor of drive/<runId> (completed/advanced) OR drive/<runId> an ancestor of it (live phase); neither → phaseInt-divergent. Coordinator current-phase selection stays state.phaseList order (hint) + git ancestry (truth).
**Chosen:** (b)
**Reasoning:** Codex P2. The ancestry relation needs no ordering at all, covers every ref instead of one "highest", and matches the mode's never-reads-state truth model.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D19: drive-review.md self-resolves the redesign epoch for the phasedesign scope token
**Stage:** design (phase 1, review round 2)
**Task:** lever2-rebirth
**Question:** The epoch-qualified review family had NO specified writer — the operative invoker chain (drive.md step 1 → /drive-design Step 2 → /drive-review `phase <P> design`) derives the BARE `phasedesign<P>` token, so after a REDESIGN the I5 gate would look for `-r<R>` files nobody writes (post-REDESIGN wedge).
**Options considered:** (a) amend drive-design.md Step 2 to bind and pass the epoch explicitly (adds drive-design.md to slice owns); (b) drive-review.md resolves R itself from `redesign-<P>-r*.marker` in $RUN_DIR when deriving the phasedesign token, using the resolved token for the review file, codex sibling, codex-raw log, in-flight marker, and counter fallback — invokers unchanged.
**Chosen:** (b)
**Reasoning:** Claude round-2 P1. One derivation point mirroring I5 (the gate already resolves the epoch from the same markers); no invoker edit, no new slice ownership, no cross-file inference required of a fresh-session re-author. drive.md's Stage-2–4.5 gate paragraph's family literal is amended to the current-epoch form; the remediation command stays valid.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D12 (amended, design review 2): stranded-review adopt requires the FULL dual-voice artifact set
**Stage:** design (phase 1, review round 2)
**Task:** lever2-rebirth
**Question:** I6's adopt accepted a complete `review-<scope>-N.md` alone, but the in-flight marker brackets the whole dual-voice chain and the gates require a non-empty codex sibling — a crash after the Claude review but before codex post-process would be adopted as finished.
**Options considered:** (a) adopt on the Claude review file alone; (b) adopt only when BOTH the review file AND `codex-review-<scope>.md` exist/parse (first-line `CODEX_UNAVAILABLE` is parseable-by-contract), else re-dispatch.
**Chosen:** (b)
**Reasoning:** Codex round-2 BLOCKING. Adopt must mirror what the gate will later demand (`codex_present`/`check_scope_counts`); adopting a half-finished chain wedges at the next gate. Amends D12.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D18 (amended, design review 2): the ancestry live-phase selection also replaces --mode audit's numeric filter
**Stage:** design (phase 1, review round 2)
**Task:** lever2-rebirth
**Question:** The numeric→ancestry fix covered checkpoint/coordinator selection but `--mode audit` still picks the live phaseInt by highest pure-numeric <P> (drive-conformance.sh ~L406) — a phase id like `4a` escapes the pre-assembly audit.
**Options considered:** (a) leave audit as a known residual; (b) apply the same D18 ancestry selection in audit mode (live = tip descends from drive/<runId>; completed = tip is its ancestor, skipped), with a `4a` fixture in the bash tests.
**Chosen:** (b)
**Reasoning:** Codex round-2 MAJOR — the fix wasn't end-to-end; same rule, same helper, in-scope for slice 1.1 which already owns the script. Amends D18; acceptance criterion 11.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D20: the COORDINATOR writes inflight-review-phasedesign<P>[-r<R>].marker at the gate-deny remediation dispatch
**Stage:** implement (slice 1.2)
**Task:** lever2-rebirth
**Question:** Followup P2 — who writes the in-flight marker when the Stage-2–4.5 gate deny dispatches `/drive-review phase <P> design` directly (normal flow is bracketed by the outer `inflight-design-<P>` marker)?
**Options considered:** (a) drive-review.md writes its own marker on every invocation (double-bracketing in the normal flow); (b) the coordinator writes/clears `inflight-review-phasedesign<P>[-r<R>].marker` around the remediation `/drive-review` call only; normal-flow phasedesign reviews stay bracketed by the outer design marker.
**Chosen:** (b)
**Reasoning:** I2 binds marker writer/clearer to the coordinator (one dispatch unit = one marker); (a) would nest a review marker inside the design marker, making "no open marker" ambiguous mid-design. drive-review.md still names the marker via its resolved scope token (D19).
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D20: audit ancestry — EQUAL tips classify LIVE; completed = STRICT ancestor; audit fixtures gain real drive/<runId> branches
**Stage:** implement (slice 1.1)
**Task:** lever2-rebirth
**Question:** D18's audit retrofit left the drive==phaseInt-tip case unpinned (equality satisfies BOTH "tip ancestor of drive" and "drive ancestor of tip"), and the existing audit fixtures (mk_audit, mk_two_concurrent, mk_audit_git_error) plus the non-owned stop-guard suite build phaseInt refs the ancestry rule must classify.
**Options considered:** (a) completed-first at equality (skip) — breaks test/drive-stop-guard.test.sh, whose fixture puts drive AT the live phaseInt tip and requires the merged-unreviewed block; (b) live-first at equality — a just-advanced phase re-audits harmlessly (its reviews are gate-guaranteed), matching pre-retrofit behavior and the fail-closed direction; completed = strict ancestor only.
**Chosen:** (b); also: audit exits 2 when phaseInt refs exist but drive/<runId> is unresolvable (classification impossible = broken run, mirroring the git-error convention), and the audit fixtures gain a drive/<runId> branch at the realistic position (test assertions unmodified). New CK6 case pins equality-live.
**Reasoning:** Bias-to-action + completeness: equality-live is the only choice that keeps every existing suite green without touching non-owned files, audits MORE (safe direction), and reflects the real run shape (equality exists only in the advance→next-work window).
**Reversibility:** easy
**Classification:** Mechanical

## Slice 1.1 fix round (7055a17 → next) — codex P1 + two Claude P2s

### 2026-06-10 -- D21: markerless epoch artifact fails CLOSED via a new `epoch-unmarked` violation
**Stage:** implement (slice 1.1 fix round)
**Task:** lever2-rebirth
**Question:** `highest_epoch()` trusts only `redesign-<P>-r*.marker`; an epoch-suffixed `review-phasedesign<P>-r*` / `codex-review-phasedesign<P>-r*` artifact with a MISSING marker (corruption / partial sweep / deleted marker) made `phasedesign-gate:<P>` fall back to bare `phasedesign<P>` and PASS on stale epoch-0 artifacts, and made `--mode checkpoint` count the current epoch as 0 — fail-OPEN in the exact mechanism this phase makes fail-closed (codex P1 BLOCKING).
**Options considered:** (a) trust the marker, ignore orphan artifacts (status quo); (b) detect epoch-suffixed phasedesign artifacts (review OR codex sibling) with no matching `redesign-<P>-r<R>.marker` and emit a new `epoch-unmarked` violation that FAILS both the gate (precedence over per-scope checks — the resolved scope is untrustworthy) and the checkpoint proof.
**Chosen:** (b) — new `unmarked_epochs()` helper consumed by both `phasedesign-gate:<P>` and `--mode checkpoint`; violation name `epoch-unmarked` documented with the other checkpoint violation reasons.
**Reasoning:** Anchors the gate/proof on the deterministic upstream marker AND refuses to silently fall back when an orphan artifact contradicts it — fail-closed at the irreversible boundary. New corruption-shape tests (`mk_phasedesign epoch1_unmarked`, `mk_checkpoint epoch_unmarked`) flip from rc 0 → rc 1 against the pre-fix script (proven).
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- D22: two Claude P2s folded in (cheap, <30min)
**Stage:** implement (slice 1.1 fix round)
**Task:** lever2-rebirth
**Question:** Fold the two logged Claude P2s if cheap.
**Chosen:** both folded. (1) Dangling-symlink `inflight-*.marker`: the `-e` glob guard follows the link and fails (reads clean) — added `|| [ -L "$f" ]` so any actual dirent fails closed as `inflight-open`. (2) Audit duplicate violation objects: a slice merged into two live refs (equal-tip advanced phase + next live phase) was checked twice — added a `seen_slice` dedup string (mirrors ship-mode `seen_phase`); `audit_tip` stays the first live ref's tip (deterministic by for-each-ref order). New tests `mk_checkpoint inflight_symlink` and `mk_audit_multi_live` both flip against pre-fix (rc 0→1; 2→1 occurrences).
**Reasoning:** Both are fail-open/JSON-quality gaps at the same safety boundary; trivial and proven.
**Reversibility:** easy
**Classification:** Mechanical

## Slice 1.2 fix round (913f9c8 → next)
- P1-1: drive-review.md L98 parenthetical now names the verdict-only `phasedesign-gate:<P>` (reads current-epoch family, no git tip) — was "not a conformance gate".
- P1-2: Scoped the artifact-derived claim — checkpoint proof asserts ONLY artifact-derived; run graph derives every round COUNT from review/harden files, state STATUS picks glyphs, state COUNTER is a display fallback solely in the missing-artifact `?` rule. Amended Data-sources field list (dropped counter fields, added the glyph/fallback note), the Harden render line (`AppliedEdits: yes` count, status=glyph), and the missing-artifact rule (added current-epoch `review-phasedesign<P>[-r<R>]-*.md`; relabeled state count as DISPLAY HINT).
- P1-3: Single owner = the marker WRITER. Stated the epoch-resolution rule once in the In-flight dispatch markers bullet; cross-referenced it at the coordinator remediation write site (Stage 2–4.5 gate) and in drive-review.md's self-resolution paragraph.
- P2: marker-content `runId: "<id>"` → `<runId>` (both marker JSON lines); aligned REDESIGN-handler atomic span to the contract's marker-write → state-write (dropped "→ re-queue").

### 2026-06-10 -- D-slice1.2-r2: Prose matched to the conformance script's real contract
**Stage:** implement (slice 1.2, fix round 2)
**Task:** spec-prose drift vs bin/drive-conformance.sh (slice 1.1 script is correct)
**Decisions:**
- Checkpoint proof prose (drive.md:194) narrowed: phaseInt/<runId>/<P> refs resolve AND relate to drive/<runId> by ancestry; slice/<runId>/<id> refs only resolve (cut from phaseBaseSha → not ancestors). Mirrors the script's audit-mode ancestry logic.
- designReview brought into the artifact-derived-unless-missing model in all three places (data-sources list, artifact-derived sentence, missing-artifact rule already covered review-design-*.md) so the root design-review round count is artifact-derived; state.designReview = display-hint fallback only.
- Marker-write attribution corrected (drive.md:178-179, drive-review.md:37): coordinator is the SOLE in-flight-marker writer (write-before-dispatch); drive-review.md only resolves <R> for its review/codex artifact filenames.
**Reversibility:** easy (prose only)

## slice 1.1 — fix round 2 (codex review P1 + P2)
- **P1 (BLOCKING) dangling-symlink epoch fail-open:** Added `|| [ -L "$f" ]` to the four
  epoch/marker dirent guards that fail OPEN when a dirent is a broken symlink: `highest_epoch`
  (a dangling redesign marker must still count its epoch, else fall back to a LOWER epoch),
  `unmarked_epochs` (a dangling epoch-suffixed artifact is still corruption to flag), the
  checkpoint redesign-marker scan, and the checkpoint phasedesign-artifact scan. Left the four
  remaining `-e`-only guards (`highest_review_file`, ship review-phase scan, checkpoint review-*
  and harden-* scans) as-is: skipping a dangling dirent there only REDUCES evidence/counts toward
  blocking (fail-closed), not toward a pass — no sibling fail-open. Two new fixtures
  (`mk_phasedesign epoch1_marker_dangling`, `mk_checkpoint epoch_marker_dangling`) + a
  `_write_redesign_marker_dangling` helper; both flip rc0(fail-open)->rc1 against pre-fix tip
  77a7476 (phasedesign-gate reports no-review for the resolved r1 epoch; checkpoint reports
  epoch-gap from the broken r1 marker failing the gapless `-e` probe).
- **P2->fix (MAJOR) dedup test not load-bearing:** The dedup (`seen_slice`) lives in 77a7476
  already and is meaningful ONLY under the ancestry audit (multiple live refs share a slice);
  the pre-7055a17 numeric audit selects one live ref so it can never emit 2 for one slice —
  hence `assert_out_count slice:s1 1` was green for the wrong reason vs that baseline. The
  `mk_audit_multi_live` fixture already seeds two live refs sharing s1 and DOES flip 2->1 against
  the same ancestry code with the dedup line removed (verified empirically). Added a sharper
  pin `assert_out_count '"reason":"no-review"' 1` (exactly one violation OBJECT; a no-dedup
  regression emits 2) and corrected the comment to state the real baseline.

## slice 1.1 — fix round 3 (codex review P1 ×2 — uniform dangling-symlink fail-closed)

### 2026-06-10 -- D23: ALL dirent loops where a valid artifact is expected now fail CLOSED on a dangling symlink
**Stage:** implement (slice 1.1 fix round 3)
**Task:** lever2-rebirth — close the dangling-symlink corruption class uniformly
**Question:** Round 2 added `|| [ -L "$f" ]` to 4 epoch/marker loops but left `highest_review_file` (~L62) and the checkpoint `review-*` (~L531) / `harden-*` (~L553) round scans `-e`-only, asserting they were "already fail-closed." Codex round-3 flagged the latter 2 as the LAST fail-open holes. Adjudicate against the real code.
**Adjudication (codex correct on both; round-2's counter-arguments wrong):**
- **`highest_review_file` L62 — codex RIGHT (was fail-OPEN).** The round-2 claim "a lower-N round is always FINDINGS by loop construction, so dropping to it still blocks" is false: a harden-regress round writes a CONVERGED verdict into the same `review-phase<P>-N.md` family at a LOWER N, and intermediate rounds' verdicts are not guaranteed FINDINGS. A dangling higher-N file `-e`-skipped → the function returns the lower-N CONVERGED file → every gate mode (plan/phasedesign/slice-merge/phase-merge/ship/audit) that reads that file's verdict passes when the real (corrupt) highest round should block. Fix: `|| [ -L "$f" ]`; the dangling file becomes `best`, is unreadable, so `verdict_converged`/`reviewed_sha_of` both fail → block.
- **checkpoint `review-*` L531 / `harden-*` L553 — codex RIGHT.** The round-2 "undercount is the safe-STOP direction" claim ignores that the counters are EMITTED in the `counters` JSON the resume-repair path consumes, and that a dangling artifact is corruption that must read as a violation, not silently vanish. A dangling `review-1.1-2.md` dropped reviewCount entirely (empirically `reviewCount:{}` pre-fix) and a dangling `harden-1-2.md` erased an `AppliedEdits: yes` round (undercounting hardenRound AND suppressing the regress-mismatch check) — both let checkpoint read CLEAN on corruption. Fix: `|| [ -L "$f" ]`; the unreadable file fails the `grep '## Verdict:'` / `grep 'AppliedEdits:'` → `unparseable-review` / `unparseable-harden` violation.
**Rule implemented (uniform, fail-closed):** a dirent where a VALID artifact is expected, present as a DANGLING symlink (unreadable), is CORRUPTION → counts as present-but-unparseable and drives toward FAIL/BLOCK; never silently skipped to a lower round/epoch, never silently dropped from a count.
**Genuinely-fail-closed loop left `-e`-only (with a clarifying comment + pinned by AC4 ship tests):** the ship candidate-discovery scan ~L398 only enumerates WHICH phase scopes exist (the verdict is re-derived via the now-`-L`-hardened `highest_review_file`); ship requires a POSITIVE existential R, so dropping a candidate can only WITHHOLD it → ship blocks. Skipping strictly tightens. The 4 round-2 epoch/marker loops + the checkpoint inflight loop already carry `-L`.
**Tests:** `mk_plan dangling_highest` (AC0d: dangling higher-N → verdict-not-converged → plan-gate blocks), `mk_checkpoint dangling_review` (unparseable-review), `mk_checkpoint dangling_harden` (unparseable-harden) + a `_write_dangling_dirent` helper. All three read CLEAN (rc 0) against tip 109c0ed and flip to rc 1 with the fix (verified by running the new fixtures against `git show 109c0ed:bin/drive-conformance.sh`). Full suite 108 PASS / 0 FAIL; sibling suites (merge-gate 107, e2e 26, stop-guard 9, install-hooks 48, hook-lib) all green. bash 3.2.57.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-10 -- Slice 1.3 cut from an integration base (deps-aware), not bare phaseBaseSha
**Stage:** implement
**Task:** proactive-rebirth trigger phase 1
**Question:** 1.3 is a contract test asserting 1.1's script + 1.2's prose shipped text; cut from phaseBaseSha it can't see them. How to base it?
**Options:** (a) bare phaseBaseSha (tests falsely fail in isolation); (b) integration base = phaseBaseSha + 1.1 + 1.2 merged (disjoint files, clean).
**Chosen:** (b). 1.3 owns ONLY the new test file; siblings are merge-inherited for context. Review diffs the owned test file. At assemble, 1.3 contains 1.1+1.2 so per-slice merges of 1.1/1.2 then 1.3 stay clean.
**Reasoning:** A test that pins sibling output must build against the integrated reality; deps already gate its dispatch after both converged. Classification: Mechanical.
**Reversibility:** easy.

### 2026-06-10 -- Slice 1.3 splits SCRIPT contracts (behavioral) from PROSE contracts (string-pin)
**Stage:** implement (slice 1.3)
**Task:** proactive-rebirth trigger phase 1 — contract pytest guard
**Question:** Pin the cross-file checkpoint contract by string-matching, or by exercising real behavior?
**Decisions:**
- SCRIPT side (mode name, `counters` derivation per I3, every violation NAME) is asserted BEHAVIORALLY: build a minimal git+RUN_DIR fixture in a tempdir (python replicas of mkfixture.sh::mk_checkpoint shapes), run `drive-conformance.sh --mode checkpoint` from inside the repo, assert JSON/exit code. 12 behavioral cases incl. clean+counters, never-reads-state (corrupt/valid/absent state.json → identical counters), inflight-open, regress-mismatch(+round 0), epoch-gap(+highest-R 3 not count 2), unparseable-review/harden, epoch-unmarked (D21 fail-closed), phaseInt-divergent, non-numeric 4a accepted, current-epoch-only phaseDesignRound, usage→exit 2.
- PROSE side (the five I3 reconstruction rules, sessionId-rebind-first, single-use marker / record-not-authorization, derived phasedesign status + redesigns>=3 STOP, REDESIGN epoch-marker-before-state ordering, adopt-needs-both-voices/never-wait, durable-contract section, drive-review.md epoch self-resolution, run-graph/gate current-epoch family) is string-pinned on the shipped prose (whitespace-normalized).
- AC9 violation-name pin SPLIT: ALL seven names pinned to exist in the SCRIPT source; only the two the coordinator prose actually cites (`regress-mismatch`, `epoch-gap`, in the reconstruction rules) are also pinned in drive.md — the other five are script-internal and intentionally not surfaced in prose (avoids over-pinning).
- AC10 drive-harden.md pins are READ-ONLY (file not edited): yes-before-regress-dispatch (ordered regex), one-regress-per-fix-round, cap-STOP-no-regress — protecting rule-2's round-subtraction from a future harden-ordering change.
- AC8 test part: state template parses as JSON + carries `rebirth_pending: false`.
**Verification:** 30 tests green; full pytest suite 304 green; bash drive-conformance suite 108 PASS (integrated baseline). Negative-checked that prose drift breaks the pins. Owns ONLY tests/contracts/test_checkpoint_contract.py.
**Reversibility:** easy.
**Classification:** Mechanical.

### 2026-06-11 -- D-slice1.3-fix: Tighten checkpoint contract tests into real regression guards
**Stage:** implement (fix round on e7b313d)
**Task:** slice 1.3 — reviewers (codex 3 MAJOR, Claude 2 P2) found tests too loose.
- **P1-1:** replaced `reason in _reasons()` membership checks with EXACT full-`violations`-JSON
  assertions (scope+reason+expected_sha+found_sha) per behavioral case via `_viol()` helper —
  catches right-reason/wrong-scope, extra, and duplicate violations. Verified flip by mutating
  a tmp COPY of the script to emit an extra-dup and a wrong-scope violation (membership passes,
  exact fails).
- **P1-2:** rebuilt the 4a test DIVERGENT (phaseInt/.../4a cut from main) and assert it is
  flagged `phaseInt-divergent` — proving the script PROCESSES the non-numeric id. Embedded proof:
  a tmp COPY with a numeric-id `continue` filter injected reads CLEAN, confirming the assertion
  is load-bearing on non-numeric processing.
- **P1-3:** pinned the five I3 reconstruction rules + the AC10 harden ordering clauses as
  CONTIGUOUS literal formulas (not scattered substrings); replaced the cap-STOP lazy `.*?` regex
  (spanned ~9KB to a distant clause) with the local contiguous `→ return STOP` clause; made
  sessionId-rebind FIRST-ness STRUCTURAL (rebind offset < marker-consume < current-phase), not
  just label text. Verified each flips on its drift via string/tmp-copy mutation; confirmed the
  cap-STOP pin no longer false-matches the distant line-70 clause.
- **P2-1:** assert `obj["tip"]` == resolved drive/<runId> tip in the clean + divergent cases.
  Verified flip via a tmp script copy emitting a bogus tip.
- **P2-2:** added a case planting a dangling `slice/<runId>/*` ref (listed by for-each-ref,
  unresolvable object) → asserts the exit-2 git-error path (distinct from verdict-1), with the
  `cannot resolve slice ref` stderr.
**Ownership:** ALL proofs run against tmp COPIES/strings of the non-owned files; the real
bin/drive-conformance.sh, drive.md, drive-harden.md, drive-review.md stay byte-identical.
git status shows ONLY tests/contracts/test_checkpoint_contract.py. 305 pytest + 108 bash PASS.

### 2026-06-11 -- D-slice1.3-r2: pin contract MEANING via structure/behavior, not incidental text
**Stage:** review (slice 1.3 fix round 2)
**Task:** lever2-rebirth — test_checkpoint_contract.py fixes for 3 codex MAJORs
- **P1-1 sessionId-FIRST:** replaced the lax `rebind < marker < phase` ordering with a
  STRUCTURAL check — enumerate ALL resume sub-bullets (`_RESUME_BULLET_RE` over the bounded
  `## Run setup & resume` section) and assert the rebind bullet is index 0 (the minimum).
  A bullet inserted BEFORE rebind now flips the test (proven via a mutated section copy).
- **P1-2 4a flip-proof:** dropped the brittle source-line-injection proof (`if ! ptip=…`
  coupling) AND its now-unused `_run_checkpoint_with_script` helper. Replaced with a
  BEHAVIORAL flip: a new test runs the real script on a descendant-`4a` (CLEAN) vs a
  divergent-`4a` (phaseInt-divergent) fixture and asserts the verdicts differ — a
  numeric-only script reads CLEAN on both (proven via mutated script copy), so the verdict
  difference IS the proof the non-numeric id is processed. No coupling to impl text.
- **P1-3 cap-STOP no-regress:** added `_harden_cap_stop_branch_body` to bound the cap-STOP
  bullet (to the next blank line) and assert the branch returns STOP but contains NO
  `harden-regress` dispatch — the contract rule-2's round-subtraction depends on. Adding a
  regress dispatch to that branch now flips the test (proven via mutated copy). Kept a
  sanity assert that the sibling "fix applied" branch lies outside the bound.
- Real bin/drive-conformance.sh / drive.md / drive-harden.md NEVER modified; all flips
  proven on COPIES/strings. `git status` shows ONLY the test file. 32/32 green.

## Slice 1.3 fix round 3 (codex MAJOR)
- Pinned the load-bearing harden-regress round-scheme contract in
  test_checkpoint_contract.py via new test
  `test_harden_regress_no_round_increment_contract_pinned_both_voices`:
  asserts BOTH prose voices as contiguous clauses (drive.md rule-2 "harden-regress
  reviews write into the same `review-phase<P>-N.md` family without incrementing the
  round"; drive-review.md "Exception — harden-regress: do NOT read, increment, or cap
  against the conformance `phaseReview[<P>].round`") AND cross-checks they describe the
  SAME contract as the script's rule-2 subtraction (review-file count MINUS AppliedEdits:
  yes harden count), including a behavioral 3-files−1-yes → round-2 assertion.
- Proved the pin flips: mutated COPIES (tmp dir) of drive.md (no-increment → incrementing
  scheme), drive-review.md (exception → DO increment), and the script comment (separate
  incrementing family) each independently FAIL the test; pristine copies pass.
- Kept the existing mention-check test_harden_one_regress_per_fix_round (still useful).
- Fixed the stale NIT docstring on test_checkpoint_nonnumeric_phase_id_4a_processed_not_skipped:
  removed the "tmp COPY with numeric-id filter injected" narration (that proof was
  replaced by the behavioral verdict-flip in the companion test); docstring now points at
  the companion verdict-flip test.

## slice 1.3 fix r4 (final) — symmetric harden-regress contract pin
- Codex MAJOR: harden-regress contract pinned the same-`review-phase<P>-N.md`-family half
  only on drive.md, not on drive-review.md (asymmetric — a family-reroute drift in
  drive-review.md could pass the string-pins). Behavioral cross-check still caught the
  consequence, but pins were not defense-in-depth symmetric.
- Fix: in `test_harden_regress_no_round_increment_contract_pinned_both_voices`, clause 1b
  (drive-review.md) now pins BOTH halves: half A (no-increment exception, existing) + half B
  (new) — the contiguous "same review as `phase <P>` … Identical scope/diff/mechanics; the
  ONLY difference is the counter" clause, which ties harden-regress's write to the same
  `<scope>`=`phase<P>` → `review-<scope>-N.md` = `review-phase<P>-N.md` family. Mechanical
  (test-only, defense-in-depth), 6 decision principle #1 completeness.
- Verified: baseline GREEN + 4 mutation checks on COPIES all RED (no-increment AND
  family-reroute drift in EITHER voice reds the test). Full suite 33 passed. Only
  tests/contracts/test_checkpoint_contract.py changed.

## Phase-1 integration fix (phaseInt review P1×2 — codex-review-phase1.md)

### 2026-06-11 -- D-int1: codex-degradation rule unified on codex_present() (ANY non-empty file counts)
**Stage:** integration (phaseInt/lever2-rebirth-.../1)
**Task:** P1-1 BLOCKING — three artifacts disagreed on what makes a codex file "count".
**Finding (PRE-EXISTING, not phase-induced):** `codex_present()` is BYTE-IDENTICAL in base
950b79c and the assembled tree — accepts any non-empty `codex-review-<scope>.md`, content not
inspected. The contradiction was the drive-review.md prose ("matches it anchored, so a buried
mention is NOT recognized"), which never matched the shipped checker; the bash AC3 assertions
were already correct (both anchored + buried files pass; empty fails). So the contradiction is
prose-vs-checker drift carried in from the slice-1.2 prose, not introduced by the assembly.
**Fix:** canonical rule = the checker's (load-bearing, per the truth-model comment). Rewrote
drive-review.md degradation prose: ANY non-empty codex file satisfies; first-line
`CODEX_UNAVAILABLE` is the human-readable degradation CONVENTION, not a parsed gate token.
Tightened drive.md:225 (adopt) to the same wording. Reframed the misleading "anchored/buried"
comments in test/drive-conformance.test.sh (AC3) + test/fixtures/mkfixture.sh helper docs
(assertions unchanged — already correct). Added contract pin
`test_drive_review_codex_rule_matches_codex_present`. Left drive.md:285/:369 (coordinator
glyph-derivation, distinct from the gate) as-is.
**Reversibility:** easy (prose+comments+test-pin). **Classification:** Mechanical.

## Phase-1 harden fix round (117ce5f → next) — codex-harden P1×1(in-scope) + P1 test + P2 slop

### 2026-06-11 -- D-hard1: epoch-scan phase-id parse anchored to a trailing -r<R>[ -<N>] suffix (FIX 1, codex P1 + Claude P3)
**Stage:** harden (phaseInt/lever2-rebirth-.../1)
**Task:** epoch-unmarked phase-derivation site (drive-conformance.sh L654) used `P="${core%%-r*}"`, splitting on the FIRST `-r` — a phase id containing `-r` (e.g. `4-r1`) mis-truncates to `4`, mis-attributing the `epoch-unmarked` violation scope and resolving the wrong epoch glob. The two OTHER P-extraction sites (redesign-marker scan ~L597, phaseDesignRound ~L671) already use a right-anchored greedy parse (`${core##*-r}` + `${core%-r$r}`) — the codex P1 and the Claude P3 are the same inconsistency.
**Fix:** new `phase_of_pd_core()` helper strips ONLY a right-anchored epoch/round suffix (`-<N>` review round, then `-r<R>`), used at the previously-divergent site. Sites 1 and 3 already parse consistently (verified: `redesigns:{"4-r1":2}`, `phaseDesignRound:{"4-r1":1}`, `epoch-unmarked` scope `phasedesign4-r1` now all agree). The Claude P3 is SUBSUMED — confirmed all three sites attribute a `-r` phase id identically.
**Test:** `mk_checkpoint epoch_unmarked_phaseid_dash_r` (phase `4-r1`, markerless epoch artifact) asserts the violation scope is `phasedesign4-r1`. Flip PROVEN against HEAD (117ce5f): pre-fix emits `{"scope":"phasedesign4",...}` (mis-truncated); the exact-scope assertion reds.
**Reversibility:** easy. **Classification:** Mechanical.

### 2026-06-11 -- D-hard2: codex-only epoch-unmarked guard (FIX 2, codex P1 test)
**Stage:** harden
**Task:** every existing epoch-unmarked fixture seeds BOTH a review file AND a codex sibling, so a regression on the codex-half of the scan (the `codex-review-phasedesign<P>-r*.md` glob in `unmarked_epochs()` and the checkpoint phase-derivation loop) stays green — the review file masks it.
**Fix:** new `mk_checkpoint epoch_unmarked_codex_only` seeds ONLY `codex-review-phasedesign1-r1.md` (no review, no marker) and asserts `epoch-unmarked`. GUARD PROVEN: against a mutated script copy with the codex glob dropped from both loops the fixture reads `clean:true` (rc 0) → the assertion reds; the existing `epoch_unmarked` fixture stays GREEN against that same broken copy (catches it via the review file), confirming the gap was real and unguarded.
**Reversibility:** easy. **Classification:** Mechanical.

### 2026-06-11 -- D-hard3: mkfixture _commit_msg dedup (FIX 3, codex P2 slop)
**Stage:** harden
**Task:** `test/fixtures/mkfixture.sh::_commit_msg()` was a verbatim duplicate of `_commit()` (both `git commit -m "$m"`, both preserve a multi-line message).
**Fix:** removed `_commit_msg`, repointed its 2 callers (waiver / waiver_prose fixtures) to `_commit`, folded the "verbatim multi-line message" note into `_commit`'s doc comment. All suites green (multi-line trailer fixtures unchanged).
**Reversibility:** easy. **Classification:** Mechanical.

### 2026-06-11 -- D-hard4: impl-presence hidden-dir false-pass ROUTED to followups (out of scope)
**Stage:** harden
**Task:** codex P1 — `is_test_path()` (~L247) matches a dot-prefixed basename but not a dot-prefixed path SEGMENT, so `tests/.hidden/test_x.py` false-passes the impl-presence gate (pytest skips hidden dirs → not runnable coverage).
**Decision:** NOT fixed — the impl-presence logic was added by `5870db5` (PRE-EXISTING), not this phase; the phase diff only added `checkpoint` to the usage line. Per the scope-creep hard gate, routed to followups.md as a P1 with the fix sketch (validate no path segment is dot-prefixed). The script's L247 logic is byte-untouched.
**Reversibility:** n/a (no code change). **Classification:** Mechanical (routing).

### 2026-06-11 -- D-int2: state-absent round-count fallback restricted to pure-integer-N files
**Stage:** integration
**Task:** P1-2 MAJOR — drive-review.md fallback globbed `review-<scope>-*.md` (counts epoch/
suffixed files), skewing N/cap-8 vs the script's pure-integer-N reconstruction.
**Fix:** drive-review.md fallback now counts only `review-<scope>-<N>.md` (all digits),
EXCLUDING suffixed names (`-r<R>`, `-final`), +1 — explicitly mirroring
bin/drive-conformance.sh highest_review_file (`case "$n" in (*[!0-9]*|'') continue`). Added
contract pin `test_drive_review_round_fallback_is_pure_integer_n`. Script already enforces the
rule (no script change needed).
**Reversibility:** easy. **Classification:** Mechanical.

### 2026-06-11 -- D-harden2: phaseDesignRound counter made marker-anchored (close -r-parse class)
**Stage:** harden phase1 (fix round 2)
**Task:** folded-in P1 (codex-review-phase1.md) — the round-1 epoch-scan parse fix was applied
at the corruption-detector sites but the phaseDesignRound reconstruction (~L689) still split on
any trailing `-r`, mis-keying a `-r`-containing epoch-0 phase id `4-r1` to phase `4` (count 0).
Parse was INCONSISTENT across sites.
**Investigation:** the string `review-phasedesign4-r1-1.md` is genuinely ambiguous (phase `4-r1`
epoch 0 vs phase `4` epoch r1) — only the redesign marker disambiguates. A codex adversarial pass
confirmed the two site-classes need OPPOSITE policies and must NOT share one rule:
  - COUNTING sites (phaseDesignRound; highest_epoch/redesign-scan already key off the authoritative
    marker name) → MARKER-anchored: a trailing `-r<R>` is the epoch only when redesign-<P>-r<R>.marker
    backs it, else it is part of the phase id.
  - CORRUPTION-DETECTOR sites (unmarked_epochs, phase_of_pd_core, the global epoch-unmarked scan) →
    deliberately suspicious right-anchored / fail-closed: they MUST treat any trailing `-r<R>` as an
    epoch CLAIM and flag a missing marker, else deleted-marker corruption becomes a bypass.
**Fix:** added one shared helper `phase_of_pd_key()` (marker-anchored) and routed the
phaseDesignRound reconstruction through it. Detector sites left unchanged (correct by design).
Added fixture `epoch_phaseid_dash_r_round` + test FIX 3 asserting `phaseDesignRound:{"4-r1":2}`
(not `{"4":0}`) — fails against tip f5c8f25, passes after. All 5 parse sites enumerated and
classified; no third drifting site.
**Residual (documented, by design):** a legit epoch-0 phase id ending `-r<digits>` is
string-indistinguishable from a phase-X deleted-marker epoch artifact, so the epoch-unmarked
detector still false-positives on such an id (run exits 1 on the detector, not the counter). The
safe choice is fail-closed detection + correct counting; terminal `-r<digits>` phase ids are thus
effectively unsupported by the gate (a full fix needs a phase-id naming change — out of scope).
**Reversibility:** easy. **Classification:** Mechanical (parse consistency).

### 2026-06-11 -- Harden phase 1 converges with a documented pathological-input residual
**Stage:** harden (phase 1)
**Task:** proactive-rebirth trigger
**Question:** codex harden-regress keeps finding deeper `-r`-in-phase-id parse sub-cases (round1 epoch-scan, round2 phaseDesignRound, round3 phase_of_pd_key colliding-marker). Keep chasing, or converge?
**Options:** (a) round-3 fix attempting full `-r`-phase-id correctness; (b) converge — realistic cases correct + both-voice-verified, pathological case fail-closes, canonical fix (phase-id naming constraint) routed to followups.
**Chosen:** (b).
**Reasoning:** The `<P>-r<R>` epoch naming is INHERENTLY ambiguous when <P> ends in `-r<digits>` — unresolvable from the filename alone; the only real fix is constraining phase ids at the source (drive.md phaseList parse), which is out of the phase-1 checkpoint/resume boundary. Phase ids never contain `-r` in real runs (they are 1/2/4a from the plan). Rounds 1-2 hardened the realistic cases (net-positive) and made the pathological case fail-closed (safe). Further rounds = net-negative oscillation on a non-occurring input. Classification: Taste — surfaced at Gate B.
**Reversibility:** easy (the naming-constraint followup can be done anytime).

### 2026-06-11 -- D24: Shared threshold/window truth = a declarative data file
**Stage:** design phase 2
**Task:** lever2-rebirth — context-pressure detection
**Question:** How do bash statusline.sh and python drive-stop-hook.py share the SAME window-by-model + threshold numbers without drift, given neither runtime sources the other's language?
**Options considered:** (a) a declarative `bin/rebirth-thresholds.json` read natively by each (bash via jq, python via json.load); (b) a sourced bash lib + a parallel python module duplicating the numbers; (c) generate one from the other
**Chosen:** (a)
**Reasoning:** DRY without cross-language sourcing; one file is the sole number source, both consumers read it; AC6 pins both to the same resolved numbers so any drift reds the suite. (b) duplicates the numbers (the exact drift we must prevent); (c) adds a build step for two constants.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-11 -- D25: Hook resolves model from the transcript, not the payload
**Stage:** design phase 2
**Task:** lever2-rebirth
**Question:** Where does the Stop hook get the model name for the window lookup?
**Options considered:** (a) the transcript's latest assistant `.message.model` (model id); (b) a payload model field
**Chosen:** (a)
**Reasoning:** The Stop payload's `.model.display_name` (what statusline uses) is NOT proven present in the Stop envelope; the transcript JSONL is already being read and carries `.message.model` authoritatively. The shared `windows[].match` list carries BOTH display-name (`Opus 4.8`) and id (`opus-4-8`/`opus-4.8`) forms so statusline (display name) and the hook (id) both classify correctly off one table.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-11 -- D26: statusline refactor extracts only the window lookup
**Stage:** design phase 2
**Task:** lever2-rebirth
**Question:** How much of statusline.sh moves to the shared helper?
**Options considered:** (a) only the window-by-model lookup moves to the data file; the token-sum jq + PCT + 80/50 display colors stay inline; (b) factor the whole context-% block out
**Chosen:** (a)
**Reasoning:** Only the window/threshold NUMBERS must be shared (the drift risk); the display PCT and colors are statusline's own concern and have no second consumer. No statusline output change (AC5); a bad data file falls back to the inline default window so the display never breaks.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-11 -- D27: Threshold defaults — hard 0.85, soft 0.75 of the window
**Stage:** design phase 2
**Task:** lever2-rebirth
**Question:** What are the hard high-water and soft self-check thresholds?
**Options considered:** (a) hard 0.85 / soft 0.75 of the model window; (b) other fractions
**Chosen:** (a) as safe defaults
**Reasoning:** soft < hard, both leaving headroom for one clean checkpoint below the real limit (D6 honest coverage). Compared on raw `tokens >= window * fraction` (no integer-pct rounding at the boundary). Exact model/usage-optimal tuning is an acknowledged out-of-scope followup (design.md L348).
**Reversibility:** easy
**Classification:** Taste

### 2026-06-11 -- D28: The Stop hook STEERS only; never writes the flag, never reads markers
**Stage:** design phase 2
**Task:** lever2-rebirth
**Question:** Does the Stop hook set `rebirth_pending` itself, and does it check in-flight markers?
**Options considered:** (a) the hook appends a signal-only instruction to its block reason and the COORDINATOR writes the flag; the hook never reads markers; (b) the hook writes state.json directly; (c) the hook checks safe-boundary markers
**Chosen:** (a)
**Reasoning:** Keeps the hook's hard fail-open bias intact — a detection failure becomes "no steer this turn", never a state mutation or a trapped turn. Only the coordinator writes state (single writer). Marker/handoff logic stays entirely in the coordinator/Phase 3; detection is pure signal (D6).
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-11 -- Slice 2.1: shared-thresholds-data implemented (AC6)
**Stage:** implement (slice 2.1)
**Task:** lever2-rebirth phase 2 — single source of truth for window/threshold numbers
**Decisions:**
- `bin/rebirth-thresholds.json` per I1 verbatim: windows match-list carries BOTH display-name (`Opus 4.7`/`Opus 4.8`) and id (`opus-4-7/-8`, `opus-4.7/.8`) forms (D25); defaultWindow 200000 (matches statusline.sh L20); hard 0.85 / soft 0.75 (D27).
- `bin/rebirth_thresholds.py`: pure readers — `load_thresholds` (raises on bad file; caller fail-opens, mirroring drive-stop-hook's degrade pattern), `resolve_window` (case-sensitive substring, None/empty model -> default), `resolve_thresholds` (window,hard,soft fractional bytes), `latest_usage_tokens` + `latest_model` (LAST assistant line, mirroring statusline's `jq | tail -1`; malformed line skipped, no-usage -> None). Stdlib-only, matches drive-stop-hook.py style. THRESHOLDS_PATH = sibling via `os.path.dirname(__file__)` (I1/divergence-5).
- Tests pin AC6 anti-drift LOAD-BEARING: `test_json_window_matches_statusline_case` reads statusline.sh's REAL inline `case` block and runs it via bash, asserting the json table resolves the IDENTICAL window (a drift on either side reds). `test_token_sum_matches_statusline_jq` runs statusline.sh's VERBATIM jq filter over the fixtures and asserts the python sum equals it. Plus `test_mutating_json_changes_resolution` proves nothing is hardcoded.
- Fixtures: over-water latest assistant sum = 909_200 (>= 850_000 hard for Opus-4.8 1M window); under-water = 315_000 (<). Earlier non-latest line present so the `tail -1`/last-wins rule is exercised. Shapes match `.message.usage.{input,cache_creation_input,cache_read_input}_tokens` + `.message.model` that statusline.sh/the hook read.
**Verification:** 23 slice tests green; full pytest suite 332 passed (no broader breakage). jq 1.7.1, bash 3.2/zsh.
**Reversibility:** easy. **Classification:** Mechanical.

### 2026-06-11 -- D27: Resolver matches statusline's jq byte-for-behavior on edge cases (slice 2.1 fix)
**Stage:** implement (fix on 6853ba5)
**Task:** lever2-rebirth — slice 2.1, AC6 no-drift
**Question:** On edge-case transcripts the python resolver drifted from statusline.sh's jq token-sum (codex-review-2.1, 3 findings). What is jq's exact behavior?
**Verified empirically against jq:** (P1-1) `select(.message.usage)` keeps a line whose usage is jq-truthy — empty `{}` PASSES and sums to 0; `null`/absent is dropped. So `{}` is a present-0 line, `null`/absent is not. Fixed `if not usage` → `if usage is None`. (P1-2) jq halts at the first malformed line; `tail -1` then yields the last value emitted BEFORE it — fixed skip-and-continue → `break`. (P1-3) `latest_model` now takes the LATEST assistant line's `.message.model` verbatim (None if that line omits it → resolve_window falls to defaultWindow), not last-truthy.
**Tests:** Added 3 edge-case anti-drift tests, each runs statusline's REAL jq pipeline (verbatim filter `| tail -1` via bash) AND the resolver on the same transcript and asserts agreement. All 3 proven to FAIL against the pre-fix committed resolver. Slice file 26/26 green; full suite 335 passed.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-11 -- Slice 2.1 fix round 2: non-dict usage/message + live token-filter extraction
**Stage:** implement (fix on 0a15fae)
**Task:** lever2-rebirth — slice 2.1, AC6 no-drift (codex-review-2.1.md round 2: 1 MAJOR + 1 MINOR)
**MAJOR — resolver crashed on non-dict `message`/`usage`; jq does not.** Verified empirically against jq:
  - `usage:false` (and any jq-falsy: null/absent/`""`/`0`-string-no) → dropped by `select`; `tail -1` keeps the prior value. Pre-fix `usage.get(...)` raised AttributeError on the bool.
  - a TRUTHY non-object `usage` (`"x"`, `5`) → PASSES `select` but errors when indexed by `.input_tokens`. Key finding: this is a per-line RUNTIME error — jq emits nothing for that line but KEEPS SCANNING (a later valid line still wins). Distinct from a JSON PARSE error, which HALTS the input stream (kept as `break`). Pre-fix raised AttributeError.
  - a non-object `message` (`false`, string) → `.message.usage` errors inside `select` → that line drops, scan continues. Pre-fix `.get("message",{}).get(...)` raised AttributeError on the bool.
  Fix: guard `message`/`usage` with `isinstance(..., dict)` → `continue` (drop the line, keep scanning) in both `latest_usage_tokens` and `latest_model`. `latest_model` on a non-object message keeps the prior model (no crash), matching the token scan's runtime-skip. The parse-error `break` (halts) stays — verified jq distinguishes the two.
**MINOR (load-bearing for AC6) — token anti-drift test compared against a COPIED filter, not statusline's live jq.** Fix: added `_statusline_token_filter()` that EXTRACTS the jq filter from statusline.sh's `TOKENS=$(jq -r '...')` line (same way the window test extracts the live `case` block); `JQ_TOKEN_FILTER` is now sourced from it. A change to statusline's token jq pipeline now reds the anti-drift tests (proven: mutating the shell filter reds `test_token_sum_matches_statusline_jq` + the edge-case drift tests).
**Tests:** +4 edge tests (usage:false, usage non-object-truthy-scan-continues, message non-object-scan-continues, latest_model non-object message). Each of the 4 proven to FAIL (AttributeError) against the pre-fix committed resolver 0a15fae and PASS against the fix. Slice file 30 passed; full suite 339 passed.
**Reversibility:** easy. **Classification:** Mechanical.

### 2026-06-11 -- D28: Structural close of the malformed-shape drift class (slice 2.1 fix round 3)
**Stage:** implement (fix on 0f000ab)
**Task:** lever2-rebirth — slice 2.1, AC6 no-drift (codex-review-2.1.md round 3 + the whack-a-mole pattern of rounds 1-2)
**Problem:** Rounds 1-2 patched the resolver's divergence from statusline.sh's jq one malformed-JSONL shape at a time (empty `{}` usage, non-dict message/usage, `usage:false`). Python's structured parsing inherently differs from jq's lenient streaming, and the malformed shapes are UNBOUNDED (top-level scalar lines, string token fields, arrays, …) — per-shape `isinstance` checks could never close the class. The resolver still CRASHED on a top-level scalar line (e.g. a bare `false`/`42`/`"x"`/`[..]`), where `obj.get("type")` raised AttributeError, and DIVERGED on a string `input_tokens:"7"`.
**Structural fix:** replicate jq's `jq -r '<filter>' file | tail -1` error model UNIFORMLY with exactly two guards, instead of per-shape casing:
  - Mode 1 (PARSE error) — a line that isn't valid JSON HALTS jq's input stream; `tail -1` keeps the last value emitted BEFORE it. => `json.loads` failure `break`s.
  - Mode 2 (per-line RUNTIME error) — indexing a non-object top-level scalar/array, a non-object `message`/`usage`, or string-vs-number arithmetic on a token field makes jq emit nothing for THAT line yet keep going. => the entire per-line extract+sum is wrapped in one `try/except Exception: continue`.
  jq's `select(.message.usage)` truthiness is replicated exactly: only `null`/`false` (and absent, already a KeyError) are falsy — `{}` is jq-truthy and sums to 0. The per-shape `isinstance(message/usage, dict)` checks from r2 are REMOVED; the uniform guards subsume them (behavior identical on those shapes, verified). Same two-mode guard applied to `latest_model`.
**Verified empirically against jq:** ran statusline.sh's exact L24 filter on 18 edge inputs (top-level `false`/`42`/`"hi"`/`[1,2,3]`/`null`, string `input_tokens`/cache field, non-object message/usage, `usage:false`/`null`/absent, empty `{}`, unparseable line) — resolver AGREES with jq on all 18, including the present-0 `{}` and the parse-halt cases.
**Tests:** replaced the per-shape proliferation with ONE parametrized sweep `test_drift_class_resolver_agrees_with_jq` (13 shapes) that runs statusline's REAL jq pipeline AND the resolver on the same transcript and asserts agreement. 7 of the 13 (all the scalar/array/string-token shapes) proven to FAIL against the pre-fix committed resolver 0f000ab (AttributeError / value divergence); all pass against the fix. statusline.sh byte-identical to base. Slice file 43 passed; full suite 352 passed.
**Reversibility:** easy. **Classification:** Mechanical.

## Slice 2.1 — fix round 4 (final): jq `// 0` token-field semantics (Mechanical)
`latest_usage_tokens` summed token fields with `usage.get(f) or 0`. Python `or 0`
collapses falsy-but-not-null values (the live FLIP: `input_tokens:""` → resolver 0,
but jq drops the line so the prior value wins) and diverges from statusline.sh's
`(.field // 0)`. Replaced with a `_jq_token` helper that matches jq exactly:
null/absent/false → 0 (jq `//` defaults on null AND false); a JSON number (int/float,
bool excluded — Python `True`/`False` are ints but jq treats them as non-numbers) →
the number; anything else (`""`, `true`, `[]`, `{}`) → raise, so the existing per-line
mode-2 guard DROPS the line (matching jq's arithmetic runtime-error). Extended the
parametrized drift sweep across all token-field value types on input + cache fields,
each pinned to the LIVE statusline jq filter. Empty-string cases flip vs pre-fix HEAD
976c337; `[]`/`{}`/`true` already agreed (old code crashed in arithmetic → drop).
statusline.sh byte-identical to base. 56 file tests + full suite (365) green.

### 2026-06-11 -- Slice 2.3: coordinator soft-check prose + doc-pin test (AC8)
**Stage:** implement (slice 2.3, phase 2)
**Task:** lever2-rebirth — coordinator soft-check (secondary/backstop detection surface)
**Decisions:**
- Placed the soft-check as a dedicated `## Coordinator soft-check (context-pressure,
  signal-only)` section in drive.md, immediately after the Durable checkpoint contract
  (which defines the safe boundary it depends on) and before Present human pause. Added a
  one-line pointer in the Execute-loop intro so the coordinator invokes it at the four
  enumerated boundaries (per-slice review verdict / phase-int review verdict / HARDEN round
  verdict / phase advance). No new script — prose only, per I4/D2.
- Contract pinned verbatim to 2.1's real names: reads `bin/rebirth-thresholds.json`,
  fires on `tokens >= window * softThresholdFraction`, sets `state.rebirth_pending = true`
  (the phase-1 state field, default `false` at drive.md L127). Signal-only (does NOT
  checkpoint/hand off/pause; CONTINUES); idempotent (skip if already true, no dup
  event-log line); handoff deferred to Phase 3. Honest-coverage residuals (single
  catastrophic turn; absent-hook degrades to soft-check only) acknowledged inline.
- No contradiction with phase-1 prose: it ships the field default + safe-boundary concept;
  2.3 is the sole writer of the flag. Canonical token-sum + `// 0` semantics restated to
  match statusline/resolver.
- test/drive-soft-check-doc.test.sh: 19 whitespace-normalized substring pins
  (bash 3.2-safe, read-only on drive.md), structured so removing/weakening any load-bearing
  clause reds the suite — proven by mutating the signal-only and idempotency clauses
  (both flip RED). 19 PASS; all sibling shell tests rc=0; pytest 365 passed.
**Reversibility:** easy (prose + test only).
**Classification:** Mechanical.

## Slice 2.2 stop-hook-detection (implement)

### 2026-06-11 -- D-slice2.2-1: hook detection is a self-contained fail-open helper appended to the reason
**Stage:** implement (slice 2.2)
**Task:** AC1-4/AC7 — Stop-hook hard-water signal-only steer.
- The rebirth check lives in `_rebirth_steer(run, payload)` which returns a sentence to APPEND or "" — never raises (outer try/except returns ""), never writes state.json, never inspects markers (D28/I2). Wired as `reason += _rebirth_steer(...)` immediately before the block print, so a detection failure degrades to the byte-identical pre-change reason (AC7). `sys.path.insert(0, dirname(__file__))` makes the sibling `rebirth_thresholds` import work from any cwd (hook runs cwd=repo in prod; fail-open if absent).
- Idempotency gate order (cheapest-first): `run.rebirth_pending` truthy -> "" before any file I/O (AC3); then missing/nonexistent transcript -> "" (AC1 fixtures use payload.transcript_path); then no-usage/`<=0` tokens -> "" (fresh transcript, AC7); then `tokens < hard` -> "" (AC2). PCT in the steer = `tokens*100//window` against the RESOLVED window (incl. defaultWindow for unknown models).
**Reversibility:** easy. **Classification:** Mechanical.

### 2026-06-11 -- D-slice2.2-2: statusline window de-dup — jq-from-json primary, dedented inline `case` fallback
**Stage:** implement (slice 2.2)
**Task:** AC5 + bash half of AC6 — window in ONE place (the data file).
**Question:** The refactor must read the window from `rebirth-thresholds.json`, but slice 2.1's `tests/hooks/test_rebirth_thresholds.py::_statusline_case_window` (NOT owned) extracts statusline's `case "$MODEL" in ... esac` via a column-0-anchored regex and runs it standalone as the bash classifier (AC6 no-drift pin).
**Chosen:** primary resolution = `jq` over the json (substring match -> window, else defaultWindow); the inline `case` is KEPT as a fallback for a missing/malformed file (I3) but DEDENTED to column 0 so the slice-2.1 regex still locates it and its numbers still equal the json by construction (the no-drift property holds, now against the fallback path). Output is byte-identical pre/post (AC5, verified vs git HEAD for Opus 4.8/4.7/default).
**Reasoning:** Honors slice-2.1 ownership (its test stays byte-unchanged and green) while genuinely moving the source of truth to the data file; the fallback `case`==json is a real invariant worth keeping pinned. AC6's bash-half is also pinned in the owned `test/statusline-window.test.sh` (statusline's rendered PCT tracks the data-file window; mutating defaultWindow flips the PCT — proves no hardcode).
**Reversibility:** easy. **Classification:** Mechanical.

## Slice 2.2 fix round (e404037 → next) — codex MAJOR + Claude/codex MINOR

### 2026-06-11 -- D-slice2.2-fix: real AC5 baseline (phaseBaseSha) + byte-strict AC7 fail-open
**Stage:** implement (slice 2.2 fix round)
**Task:** lever2-rebirth — two test-fidelity findings on committed slice 2.2 (test-only fix; statusline.sh + drive-stop-hook.py byte-unchanged).
- **P1 (MAJOR) AC5 self-comparison hollow guard (test/statusline-window.test.sh).** The guard compared the current statusline against `git show HEAD:bin/statusline.sh`, but HEAD == the slice tip (already de-dup'd), so it self-compared and could never catch an output-changing edit. Fix: baseline now = `statusline.sh` at the slice's `phaseBaseSha` (read from `../../state.json` → `8652455`, the ORIGINAL inline-`case` tree BEFORE the de-dup). Runs BOTH base and current statusline on the same payload across the 4 model cases + an unmatched default, asserting byte-identical displayed output. Skips gracefully (AC6 assertions stand alone) if the base ref is unresolvable. PROVEN real: a scratch mutation that changed the default window (PCT 454→363 for Sonnet/Haiku/unknown) REDS the guard; reverted → green.
- **P2 (MINOR) AC7 fail-open contract byte-strict.** Every detection error path now asserts the block reason is BYTE-IDENTICAL to the pre-change baseline (steer helper returned "") via a shared `_baseline_reason`/`_assert_failopen` pair — not merely "anchor absent" (a garbled partial steer could also lack the anchor). Strengthened: missing/nonexistent transcript, no-usage, malformed thresholds, unknown-model-under-water. Added the two MISSING paths: resolver **import failure** (copy of bin/ without `rebirth_thresholds.py`) and **any unexpected exception** in the steer helper (copy whose `latest_usage_tokens` raises `RuntimeError` → catch-all). PROVEN load-bearing: removing the steer's `except Exception: return ""` reds all three error-path tests (the exception escapes to the outer `__main__` backstop → exit 0 no output → allow → no block).
**Ownership:** ONLY the two owned test files changed; bin/statusline.sh, bin/rebirth-thresholds.json, bin/drive-stop-hook.py byte-identical (git status confirms). All proofs ran on COPIES/scratch mutations, reverted.
**Verification:** `bash test/statusline-window.test.sh` ALL PASS; `pytest tests/hooks/test_drive_stop_hook.py` 31 passed; full `pytest` 380 passed.
**Reversibility:** easy. **Classification:** Mechanical.

### 2026-06-11 -- D: slice 2.2 fix r2 — AC5 guard made self-contained (golden), no state.json
**Stage:** review-fix (slice 2.2, round 2)
**Finding:** codex P1/MAJOR — the AC5 "output unchanged" guard resolved its pre-refactor
baseline from `$REPO/../../state.json` (run RUN_DIR) and SKIPPED (`PASS: AC5 skipped`) when
absent. That path only exists inside this run's worktree; after merge into a normal checkout
(CI, main) the guard skips forever, so an output-changing bin/statusline.sh edit would go
uncaught — defeating AC5's durable-regression-guard purpose.
**Decision (principle: completeness + explicit-over-clever):** replace the git-ancestor/
state.json baseline with embedded GOLDEN expected outputs. For the 4 model cases (Opus 4.8/4.7
-> 1M window, Sonnet/Haiku/unknown -> 200k default) + a token-sum of 909200, hardcode the EXACT
displayed statusline line (cyan dir + `[model]` + red PCT%, byte-exact incl. ANSI) and assert the
current bin/statusline.sh reproduces each. Goldens captured from the current statusline.sh
(prior review confirmed byte-identical to pre-refactor), so they ARE the pre-refactor outputs.
Determinism pinned without any external baseline: FIXED non-git current_dir (empty git segment),
empty $HOME + ccusage-free $PATH (empty cost segment), payload without rate_limits (empty limit
segment). Fully self-contained — runs in a bare repo checkout, no git ref / no state.json.
**Verification:** `bash test/statusline-window.test.sh` green; scratch-mutating statusline's PCT
format (`%` -> `pct`) reds all 5 AC5 cases, then reverted; `python3 -m pytest -q` green; bin/
statusline.sh, bin/drive-stop-hook.py, bin/rebirth-thresholds.json byte-identical to HEAD
(test-only fix). AC6 bash half (window from rebirth-thresholds.json) left intact.

### 2026-06-11 -- D29: Hook binds window-model + token-sum to the SAME usage line (harden P1-1)
**Stage:** harden (phase 2 fix round)
**Task:** lever2-rebirth — context-pressure detection
**Class:** Mechanical
**Decision:** The Stop hook read the window model from `latest_model` (the LATEST assistant
line) but tokens from `latest_usage_tokens` (the LATEST USAGE-BEARING line). A usage-less /
synthetic line after the last usage line (different/absent model) split the resolved window
from the token source -> wrong context%. Added `latest_usage_model_and_tokens(transcript)`
returning `(model, tokens)` from one usage-bearing line; the hook now uses it. **statusline.sh
NOT touched** — statusline already reads its model from the PAYLOAD (`.model.display_name`),
not the transcript, so the hook's transcript-line mismatch never existed there; AC6 (substring
classifier) and AC5 (golden) are unaffected. resolver==statusline preserved. New regression
tests red against pre-fix code (pre-fix reported the wrong window in the steer).
**P1-3 finding:** the design DOES require the soft-check event-log write (drive.md step 3 +
AC8: `{"event":"rebirth_pending","via":"coordinator-soft","pct":...}`). The prose already
states it; only the doc-pin test was missing the assertion — added it (now reds if dropped).
No drive.md prose change needed.
**P2:** removed the strictly-weaker duplicate `test_failopen_unknown_model_uses_default_window_no_false_steer`
(byte-exact sibling kept).

### 2026-06-11 -- D30: rebirth safe-boundary handler shares the phase-2 soft-check boundaries
**Stage:** design phase 3
**Task:** lever2-rebirth — re-entry handshake & wiring
**Question:** Where does the handler that CONSUMES rebirth_pending (prove → marker → waiting=rebirth → present) run, and does it re-author the phase-1 prove-then-pause prose?
**Options considered:** (a) run it at the SAME enumerated safe boundaries as the phase-2 coordinator soft-check, immediately after it, referencing the phase-1 prove-then-pause + stop:checkpoint-unprovable prose; (b) a separate boundary set + re-stated ordering prose
**Chosen:** (a)
**Reasoning:** DRY — one boundary set for both detection-self-check and handoff-consume; the soft-check may set the flag and the handler consumes it in the same boundary. The fail-closed ordering (marker BEFORE waiting=rebirth) + the stop:checkpoint-unprovable STOP already shipped in phase 1's §Durable checkpoint contract; phase 3 invokes them, it does not re-author them (real code wins — divergence #1).
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-11 -- D31: waiting="rebirth" is the lone CONTINUE waiting value on resume
**Stage:** design phase 3
**Task:** lever2-rebirth
**Question:** How does the resume path treat a rebirth-waiting run vs every other waiting value?
**Options considered:** (a) resume clears waiting=rebirth, resets rebirth_pending=false, and drives forward without re-presenting; (b) re-present it like any other paused waiting
**Chosen:** (a)
**Reasoning:** A rebirth pause's "human action" is STARTING the fresh session — which the resume itself proves happened — so re-presenting would deadlock the handoff. Every other waiting (gateA/gateB/stop:/ask:) means the human is mid-question and resume re-presents (the human returned). rebirth is the one value that auto-continues. The sessionId rebind (phase-1, first resume act) + the single-use marker consume both precede this clear.
**Reversibility:** easy
**Classification:** Taste

### 2026-06-11 -- D32: Stop-hook splits _rebirth_steer into pre-flag set-flag vs post-flag handoff escalation
**Stage:** design phase 3
**Task:** lever2-rebirth
**Question:** The phase-2 hook returns "" once rebirth_pending is set (idempotent, no re-steer). How does phase 3's "escalation beyond signal-only set-flag" fit without breaking that?
**Options considered:** (a) split into two hard-water-gated steers — pre-flag = unchanged phase-2 set-flag sentence; post-flag (flag set, still over water) = a NEW "checkpoint + set waiting=rebirth at your next safe boundary" steer, replacing the current `return ""`; (b) keep return "" and rely on the coordinator alone
**Chosen:** (a)
**Reasoning:** The set-flag idempotency is preserved by SPLITTING the reasons (don't RE-emit the set-flag instruction; emit the handoff-escalation instead). The hook STILL never inspects markers, never writes state, never enacts the handoff (D28 intact) — the escalation is advisory, deferring to the coordinator's safe-boundary handler. Fail-open + signal-only invariants unchanged. Without the escalation, a coordinator that set the flag but stalled before a boundary gets no further nudge.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-11 -- D33: gate/STOP takes precedence over a pending rebirth at the same boundary
**Stage:** design phase 3
**Task:** lever2-rebirth
**Question:** At a boundary where rebirth_pending is true AND a real Gate A/B or non-decision STOP is also due — which pause fires?
**Options considered:** (a) the gate/STOP wins; rebirth_pending carries forward to the fresh session (started via the gate's re-armed /goal); (b) rebirth pause stacks on / precedes the gate
**Chosen:** (a)
**Reasoning:** A gate/STOP already ends the leg awaiting the present human, who can resume in a fresh session via the gate's re-armed /goal (the same /drive <runId> resume token the handoff block would show). A separate rebirth pause stacked on an already-human-pausing gate is redundant. Rebirth exists only to break an OTHERWISE-autonomous leg that would run past the budget; a gate-ending leg subsumes it.
**Reversibility:** easy
**Classification:** Taste

### 2026-06-11 -- D34: resume resets rebirth_pending=false when clearing a rebirth waiting
**Stage:** design phase 3
**Task:** lever2-rebirth
**Question:** Should the carried-in rebirth_pending flag survive into the successor session?
**Options considered:** (a) reset rebirth_pending=false on the rebirth-continue resume; (b) leave it true
**Chosen:** (a)
**Reasoning:** The successor's transcript starts near-empty; leaving the flag true would make the I1 handler spuriously re-hand-off at the successor's FIRST safe boundary before any real pressure. Resetting it gives a clean detection re-arm — the successor re-detects on its own context growth via the rebound sessionId (D7). Multi-rebirth works = rebind (re-attributes the run) + flag reset (clears prior pressure).
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-11 -- D35: no drive-conformance.sh change in phase 3
**Stage:** design phase 3
**Task:** lever2-rebirth
**Question:** Does the re-entry handshake need any conformance-script change?
**Options considered:** (a) consume the phase-1 --mode checkpoint proof + checkpoint-complete.marker format verbatim; (b) extend the script
**Chosen:** (a)
**Reasoning:** The proof tool and marker format are complete phase-1 contracts; phase 3 only INVOKES --mode checkpoint and WRITES the marker at the safe-boundary handler (I1). Phase 3's executable coverage is the stop-hook pytest (AC5-8); the drive.md changes are prose contracts (pinned + review-verified), never script-simulated. Boundaries stay drive.md + drive-stop-hook.py + new tests.
**Reversibility:** easy
**Classification:** Mechanical

## Phase-3 design review round 1 (dual-voice — codex BLOCKING + MAJOR, Claude 2×P2)

### 2026-06-11 -- D36 (amends D34): rebirth_pending re-arm moves to the sessionId-rebind point (ANY fresh-session resume), not gated on a rebirth waiting
**Stage:** design (phase 3, review round 1)
**Task:** lever2-rebirth — codex P1-1 BLOCKING / Claude P2
**Question:** D34 reset `rebirth_pending=false` only when resume cleared a `rebirth` waiting. A run paused at Gate A/B or a STOP (or crashed) with a STALE `rebirth_pending=true` (set by the soft-check/hook before the pause) and resumed in a FRESH session keeps the stale flag — the successor's I1 handler fires a spurious empty handoff at its first boundary before the new transcript has grown.
**Options considered:** (a) keep the reset gated on a `rebirth`-waiting resume (D34 as-is) — leaks across Gate/STOP/crash fresh resumes; (b) move the reset to the phase-1 sessionId-rebind step (the ONE place that fires on ANY fresh-session resume, keyed on `state.sessionId != $CLAUDE_CODE_SESSION_ID`), resetting `rebirth_pending=false` in the SAME write that rewrites `sessionId` — uniform across ALL `waiting` values and the no-`waiting` crash case.
**Chosen:** (b)
**Reasoning:** `rebirth_pending` is derived from the OUTGOING session's transcript growth; on ANY fresh-session resume that transcript is gone, so the signal is stale and must be re-derived from the NEW session's own growth. The single rebind point is exactly where staleness is detectable. Composes with the rebirth-resume path (it ALSO hits the rebind reset first → successor starts clean), so D34's intent is preserved and now sourced from one place. The reset is NOT additionally re-done in the `waiting`-clear step. Amends D34; adds edge case 9 + AC12.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-11 -- D37: the canonical `waiting` definition is amended EXPLICITLY (three sites) to enumerate rebirth with its dual nature
**Stage:** design (phase 3, review round 1)
**Task:** lever2-rebirth — codex MAJOR (P1-2)
**Question:** drive.md's canonical `waiting` definition (Autonomous-continuation contract + Present-human-pause step 1) and the drive-stop-hook.py docstring define `waiting` as a human-pause-ONLY set (gateA/gateB/stop:/ask:). Adding `rebirth` as a CONTINUE-exception there is real work — referenced-only, the slices wouldn't do it and nothing would guard it.
**Options considered:** (a) leave it as a referenced divergence (regression bait — un-slice-scoped, untested); (b) make it an EXPLICIT interface (I6 drive.md + I7 hook docstring), an acceptance criterion (AC11), and assigned slice owns (3.1 drive.md, 3.2 hook docstring), with a 3.3 + hook-test pin that the canonical definition enumerates `rebirth` and states its dual nature (set-to-pause outgoing; auto-cleared-as-continue on resume).
**Chosen:** (b)
**Reasoning:** A multi-file behavioural contract asserted in one place without wiring the sibling is a latent gap a file-by-file review misses; making it an explicit interface + AC + slice scope + test pin is the only way the edit lands and stays guarded. The hook BEHAVIOUR is unchanged (it reads only `waiting`'s truthiness); these are documentation-contract edits so the canonical definition no longer reads "human-pause only".
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-11 -- D38: AC1/AC3 upgraded from raw-offset substring pins to bounded/enumerated structural pins (slice-1.3 precedent)
**Stage:** design (phase 3, review round 1)
**Task:** lever2-rebirth — Claude P2
**Question:** AC1 ("marker-write clause precedes the waiting clause STRUCTURALLY (offset order)") and AC3 used a bare character-offset compare of two substrings — the brittle pattern the slice-1.3 fix rounds (D-slice1.3-fix P1-3 / D-slice1.3-r2 P1-1) explicitly replaced after a lax `a < b < c` offset check passed for the wrong reason.
**Options considered:** (a) keep the offset-order substring assertion; (b) bind the same bounded/enumerated standard — AC1 enumerates the I1 handler's numbered steps within the bounded `### I1` section and asserts marker-write is step 4 / waiting-set is step 5 (adjacent, by index); AC3 enumerates the `## Run setup & resume` sub-bullets (reusing test_checkpoint_contract.py's `_RESUME_BULLET_RE` structural rule) and asserts rebind=index 0 + marker-consume precede the rebirth-continue bullet by INDEX. AC12 likewise bounds the section and asserts the rebind-bullet re-arm clause + the absence of a second `rebirth`-gated reset.
**Chosen:** (b)
**Reasoning:** A raw-offset compare flips for the wrong reason and survives inserted/reordered clauses; the bounded/enumerated index assertion is the established slice-1.3 standard and makes drift actually red the test. Mechanical test-quality, slice 3.3 scope; not blocking.
**Reversibility:** easy
**Classification:** Mechanical

## Phase-3 detailed-design — round-2 review fix (codex 1 MAJOR + 1 MINOR)

### 2026-06-11 -- D-pd3-r2-P1: re-arm fix propagated to gate-precedence prose + D33 (no carry-forward)
**Stage:** design (phase 3, review round 2)
**Task:** lever2-rebirth — internal-consistency fix
**Question:** Round-1 added the I4/D36 re-arm (reset `rebirth_pending=false` at the sessionId-rebind step on ANY fresh-session resume), but edge case 5, AC9, and D33 still said `rebirth_pending` "carries forward / carries to the successor" — a direct contradiction (codex round-2 MAJOR, L366/L490/L583).
**Chosen:** Reconcile ALL three sites to the re-arm rule: `rebirth_pending` does NOT carry forward — on the fresh-session resume it is reset to `false` (D36 rebind re-arm) and a still-pressured run re-detects pressure from the SUCCESSOR session's own transcript growth, handing off at the next safe boundary there. Net behavior stated consistently: no handoff is lost, but the flag is re-derived, not literally persisted. D33 re-titled "(amended by D36 re-arm)".
**Reasoning:** A flag derived from the OUTGOING transcript (gone on any fresh resume) cannot honestly "carry forward"; the single re-arm point (D36) is the source of truth and every prose claim must agree with it. Edge case 9 (the leak D36 closes) already stated this correctly — the fix aligns the remaining three sites.
**Reversibility:** easy (prose only)
**Classification:** Mechanical

### 2026-06-11 -- D-pd3-r2-P2: gate-handoff-token claim corrected to ground truth (drive.md Gate A/B)
**Stage:** design (phase 3, review round 2)
**Task:** lever2-rebirth — factual-accuracy fix
**Question:** The gate-subsumes-rebirth rationale (edge case 5, D33) claimed a gate hands the user a `/drive <runId>` resume token and that "the gate re-arm line and the handoff `/drive <runId>` line are the SAME resume token." Ground truth (drive.md L508-518, L696-701): Gate A hands a `/goal` line only; Gate B hands no resume line (its push is immediate). Neither gate emits a `/drive <runId>` token (codex round-2 MINOR, L359).
**Chosen:** Correct the rationale to match the gates: Gate A re-arms the next leg's `/goal`; the user, knowing the runId, pastes `/drive <runId>` themselves; Gate B has no resume line. Removed the false "SAME resume token" sentence. The precedence argument does NOT depend on the false claim — a human present at the gate can still start a fresh session regardless of which line the gate emits — so the conclusion stands, only the mechanism is corrected.
**Reasoning:** Anchor the claim on the primary artifact (drive.md), not an assumed symmetry; the rebirth handoff block DOES emit `/drive <runId>` (I3), but the gates do not, and the rationale must not conflate them.
**Reversibility:** easy (prose only)
**Classification:** Mechanical

---

## phasedesign3 round-3 review revisions (codex FINDINGS)

### D-phasedesign3-r3 P1-1 — I1 leave-pending wording contradicted the single rebind reset
**Question:** I1's "Idempotent / leave-pending semantics" said `rebirth_pending` "is cleared only implicitly — the successor's resume reconciles a fresh run with no pressure," which reads as contradicting the single, explicit reset at the sessionId-rebind step (I4 L211, AC12, D36).
**Chosen:** Rewrote the I1 lifecycle to state it unambiguously and consistently with every other site: within the SAME (outgoing) session the flag STAYS SET after detection and through the pause (consumed at the next safe boundary where the handshake fires; never reset in the outgoing session); it is RESET to `false` exactly ONCE — at the sessionId-rebind step on a fresh-session resume (I4/D36). Removed the "cleared only implicitly" phrasing. I1, edge case 4/5/6/9, AC9/AC12, D33/D34/D36 now describe the identical lifecycle in compatible words.
**Reasoning:** A single canonical lifecycle statement keyed on the deterministic reset point (the rebind) removes the muddying "implicit clearing" reading; the reset is the one place the stale outgoing-transcript signal is dropped.
**Reversibility:** easy (prose only)
**Classification:** Mechanical

### D-phasedesign3-r3 P1-2 — gate-token claim was factually wrong vs drive.md ground truth
**Question:** Edge case 5 and D33 (as left by the round-2 revision) claimed "Gate A hands `/goal` only; Gate B hands no resume line at all since its push is immediate." Ground truth verified in drive.md L333-334: "scope one goal per autonomous leg, re-armed at each gate (Gate A and Gate B hand the user the next leg's line to paste on approval)." So BOTH gates hand a `/goal` line — the round-2 "Gate B hands none" was WRONG. (drive-plan.md L88 already agreed with the correct reading.)
**Chosen:** Corrected edge case 5 and D33 to match drive.md: BOTH Gate A and Gate B hand the next autonomous leg's `/goal` line on approval; NEITHER gate emits a `/drive <runId>` resume token. Re-derived the precedence/distinction on this basis: the rebirth handshake's DISTINCT contribution is precisely the paste-ready `/drive <runId>` resume line (no gate emits that) plus the re-armed goal — whereas a gate hands only the goal line. The gate-subsumes-rebirth conclusion is unchanged (a human present at the gate can start a fresh session regardless), only the mechanism is now factually correct. Grepped the whole design: every gate-handoff-token claim is consistent with drive.md ground truth.
**Reasoning:** Anchor load-bearing factual claims on the primary artifact (drive.md), verified in both directions; the round-2 revision over-corrected the original false symmetry into a different false claim (Gate B hands none).
**Reversibility:** easy (prose only)
**Classification:** Mechanical

## Slice 3.1 — rebirth-handshake-prose (drive.md only)

### 2026-06-11 -- D-slice3.1: I1 handler placed as `### I1` subsection after the soft-check
**Stage:** implement (slice 3.1)
**Task:** lever2-rebirth phase 3 — rebirth handshake prose in drive.md
**Decisions:**
- I1 safe-boundary handler authored as a `### I1 — Safe-boundary rebirth handler` subsection
  directly after the Coordinator soft-check section, with its 6 numbered steps so AC1's
  bounded/enumerated pin lands (marker write = step 4, `waiting="rebirth"` set = step 5,
  adjacent ordered items). Wired into the Execute-loop boundary prose ("run the soft-check,
  then the Safe-boundary rebirth handler") so the handler is actually INVOKED at the same
  boundaries, immediately after the soft-check (D30). Fail-closed step-3 carries the exact
  contiguous literal "Never set `waiting = "rebirth"` on a failing proof".
- I4 split into TWO resume edits: (a) the sessionId-rebind bullet (index 0) resets
  `rebirth_pending=false` in the SAME JSON-safe write, uniformly on ANY fresh-session resume
  (D36/AC12) — the SINGLE reset point; (b) a new `waiting=="rebirth"` → normal-CONTINUE
  bullet placed AFTER the marker-consume bullet (so rebind=0, marker-consume=1,
  rebirth-continue=2 — AC3 ordering). The rebirth-continue bullet explicitly notes rebind
  already reset the flag (no second reset gated on `rebirth` — AC12 negative side).
- I5 amended in BOTH canonical drive.md sites (Autonomous-continuation contract +
  Present-human-pause step 1), each enumerating `rebirth` with its dual nature contiguously
  (set-to-pause outgoing; auto-cleared-as-continue on resume) (D37/AC11 drive.md sites).
- I2 `↻ REBIRTH` continuation node added to the `← YOU ARE HERE` anchor enumeration (NOT a
  `✗ STOP` leaf) + `↻ rebirth` added to the legend in the render contract AND both worked
  examples (consistency — the legend is printed once per block).
- I3 handoff block authored in Present-human-pause step 3 (literal `/drive <runId>` resume
  line + re-armed `/goal` line; no AUQ).
- Gate/STOP precedence (AC9): both Gate A and Gate B hand the next leg's `/goal` line;
  NEITHER emits `/drive <runId>` — that runId resume line is rebirth's distinct contribution.
**Verification:** self-check grep confirms no contradiction with phase-1/2 prose; the
Leave-pending "STAYS SET … reset exactly ONCE at the rebind step" is consistent with the
I4 rebind reset. Only `.claude/commands/drive.md` changed. No test suite in this slice (3.3 pins).
**Reversibility:** easy (prose only).
**Classification:** Mechanical.

### 2026-06-11 -- slice 3.2 (stop-hook-escalation) implemented
**What:** Split `_rebirth_steer` into two hard-water-gated branches keyed on `rebirth_pending` (I7/D32): falsy -> the unchanged phase-2 set-flag steer; truthy -> the NEW escalation steer ("checkpoint + set state.waiting=\"rebirth\" at your next safe boundary"), replacing the prior `return ""`. Below hard water -> "" in both branches. The early `if run.get("rebirth_pending"): return ""` was removed; the branch now lives at the final return after the shared transcript/usage/hard-water gates, inside the same fail-open try/except. Amended the module docstring `waiting`/module-prose + the `_rebirth_steer` docstring to enumerate `rebirth`'s dual nature (I6/D37) and the two-steer split. Hook still never writes state, inspects markers, or enacts handoff (D28).
**Tests:** Rewrote the stale `test_already_pending_no_resteer_even_over_water` into `test_already_pending_over_water_emits_escalation_steer` (escalation present, set-flag absent); added below-water-when-pending (AC7), an escalation fail-open path (AC8), escalation-absent assertions on the pre-flag/below-water tests (AC6/AC7), and a docstring-enumeration test reading the module `__doc__` (AC11). Proved the escalation + docstring tests RED against the pre-change hook. Full suite green (387 passed).

## Slice 3.1 fix round (8c829de → next) — codex P1 (rebirth re-arm /goal omits rebirth as a leg-end state)

### 2026-06-11 -- D-slice3.1-fix: every /goal satisfying-condition template admits a rebirth pause
**Stage:** implement (slice 3.1 fix round)
**Task:** lever2-rebirth — drive.md:391 rebirth-handoff re-armed `/goal` counted only Gate A/B + non-decision STOP + AUQ as satisfying ("met") states, NOT a rebirth pause (`waiting="rebirth"`). A SUCCESSOR session that itself hits a SECOND rebirth would have an UNMET goal → the goal-checker forces it to keep driving PAST its own handoff (defeats multi-rebirth).
**Fix:** Added the clause `OR is paused at a rebirth handoff (waiting="rebirth") awaiting my paste of the resume line` to BOTH `/goal` templates that live in drive.md — (1) the rebirth handoff block re-arm (~391) and (2) the Stage-0 leg-1 template (~642). Existing satisfying states (Gate A/B, STOP, AUQ) kept intact (ADD, not remove); wording is consistent across both templates.
**Scope:** slice 3.1 owns ONLY `.claude/commands/drive.md`. The Gate A leg-2 (drive-plan.md:96) and Gate B re-arm (drive-ship.md) `/goal` templates live OUTSIDE this slice's ownership and are NOT touched here — flagged as a residual for the owning slice if needed.
**Verification:** grep of every `/goal … NOT met …` template in drive.md confirms each now includes the `waiting="rebirth"` rebirth-pause clause; no template contradicts another. Only `.claude/commands/drive.md` changed. No test suite in this slice (3.3 pins drive.md).
**Reversibility:** easy (prose only).
**Classification:** Mechanical.

### 2026-06-11 -- D: Rebirth handoff /goal is leg-aware (selected by state.stage)
**Stage:** execute (slice 3.1, fix round 2)
**Task:** lever2-rebirth — proactive context-pressure trigger
**Question:** The rebirth handoff is reachable from any safe boundary (Stage-0/Plan, Execute, Verify, Ship), but its re-armed successor `/goal` hardcoded the execute-leg completion condition — wrong for a rebirth that fires during planning or ship.
**Options considered:** (a) parameterize the handoff `/goal` by `state.stage` with a per-leg `<leg-condition>` selection table; (b) emit two separate full handoff blocks per leg.
**Chosen:** (a)
**Reasoning:** drive.md is instructions, not code — a single template with a stage-keyed `<leg-condition>` directive is DRY and mirrors the existing Stage-0 leg-1 / Gate A re-arm leg goals verbatim (planning-leg = drive.md Stage-0 line; execute-leg {execute,verify,ship} = drive-plan.md Gate A re-arm). Kept the rebirth-pause satisfying clause + Gate A/B/STOP/AUQ states intact.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-11 -- D: Fold `premises` into the planning-leg `<leg-condition>` row (slice 3.1 fix round 3)
**Stage:** implement (slice 3.1, fix round 3 on 9c88da3)
**Decision:** The rebirth-handoff `/goal` `<leg-condition>` selector had rows only for `stage == "plan"` and `stage ∈ {execute,verify,ship}`, leaving `stage == "premises"` (a Stage-0 boundary the I1 handler explicitly fires at) unmapped — the selector was not total over the canonical stage enum (`premises → plan → execute → verify → ship`). Folded `premises` into the planning-leg row → `stage ∈ {"premises","plan"}`. Premises is pre-Gate-A, so the planning-leg goal (drive planning → Gate A) is the correct condition. Selector is now total with exactly one branch per enum value (no gap, no overlap).
**Principle:** completeness; both reviewers (codex MAJOR, Claude P1) agreed.

### 2026-06-11 -- Slice 3.3 cut from integration base (3.1+3.2 merged); structural pins matching slice-1.3
**Stage:** implement (slice 3.3)
**Task:** lever2-rebirth phase 3 — rebirth-handshake contract test
**Question:** Pin the cross-file rebirth-handshake contract (drive.md prose 3.1 + hook escalation 3.2) without loose substrings.
**Decisions:**
- New `tests/contracts/test_rebirth_handshake.py` asserts against the REAL merged 3.1/3.2 text (worktree base = phaseBaseSha + 3.1 + 3.2, slice-1.3 precedent; owns ONLY the new file).
- AC1 fail-closed ordering: enumerate the I1 handler's numbered steps (`_I1_STEP_RE`, bounded to the `### I1 …` section) and assert by STEP INDEX that marker-write=step 4 < waiting-set=step 5 AND adjacent; plus the contiguous `fail closed: Never set waiting="rebirth" on a failing proof` clause. Flip-proof swaps the two labels in a COPY.
- AC2/AC3: run-graph `↻ REBIRTH` continuation-node anchor (explicitly NOT a STOP leaf) + legend `↻ rebirth` + node text `/drive <runId>`; handoff block (bounded to its ```fence) carries the paste-ready `/drive <runId>` resume line + re-armed `/goal`.
- AC4: resume rebirth-continue bullet enumerated by BULLET INDEX after rebind(0)+marker (reused slice-1.3 `_RESUME_BULLET_RE`, WIDENED to the bold SPAN `- **…**` since the rebirth bullet ends `NOT a STOP.**`, not `:**`); rebirth_pending=false re-arm pinned AT the rebind step as the SINGLE reset point (no second reset). Flip-proof injects a bullet ahead of rebind in a COPY.
- AC9: gate precedence — both gates hand `/goal`, NEITHER emits `/drive <runId>` (rebirth's distinct contribution), gate/STOP wins, rebirth_pending does not carry forward.
- AC11: canonical `waiting` dual-nature enumerated in BOTH drive.md sites (Autonomous-continuation contract + Present-human-pause step 1) AND the hook docstring; flip-proof strips the auto-clear half from a COPY.
- AC12: leg-condition `/goal` selector is TOTAL over the stage enum (premises,plan,execute,verify,ship) — collect covered stage tokens across selector bullets, assert exact partition (each stage exactly once). Flip-proof drops `verify` from a COPY.
- Cross-file invariant: the hook's ESCALATION steer (bounded to the `rebirth_pending` branch) names the SAME tokens the I1 handler uses (`--mode checkpoint`, `checkpoint-complete.marker`, `"rebirth"`) in proof-then-pause order — source-escaped `\"rebirth\"` matched in the raw `.py`. Flip-proof renames the marker token in a COPY.
- ALL flips run on COPIES/strings; real drive.md / drive-stop-hook.py byte-unchanged. 20 new tests green; full pytest 407 passed. `git status` shows ONLY tests/contracts/test_rebirth_handshake.py.
**Reversibility:** easy.
**Classification:** Mechanical.

### 2026-06-11 -- D39: Slice 3.3 fix round — genuine flip-proofs + structural single-reset negative
**Stage:** implement (review fix round, commit 73c7e47)
**Task:** lever2-rebirth — slice 3.3 cross-file rebirth-handshake contract pins
**Question:** Address the 3.3 review findings (P1-1 tautological flip-proofs, P1-2 unguarded single-reset negative, P2 over-tight `_LEG_BULLET_RE`) without touching non-owned merged files.
**Chosen:**
- **P1-1:** Factored each load-bearing pin into a reusable assertion (`_assert_ac11_dual_nature`, `_assert_steer_names_shared_tokens`) and made `_escalation_steer_text(src=None)` accept a source override. The two tautological flip-proofs now mutate a COPY of the REAL merged source the exact way the contract would drift (AC11: revert the auto-clear half to human-pause-only phrasing; cross-file: rename the marker token in the whole hook source) and assert the SAME pin/accessor RAISES (`pytest.raises(AssertionError)`) — proven genuine by neutering each pin and confirming the flip-proof reds.
- **P1-2:** Added `_resume_bullet_bodies` + `_REBIRTH_RESET_RE` (matches the `= false` ASSIGNMENT, not the JSON `:` default or prose) and a structural negative `_assert_single_reset_structural`: the reset write appears EXACTLY ONCE across the resume bullets, ONLY at the rebind bullet (idx 0), ABSENT from the rebirth-continue bullet (idx 2) AND from the I1 outgoing handler (flag STAYS SET). New flip-proof injects a redundant second reset into a COPY (prose `SINGLE reset point` left intact) and asserts the structural pin reds — adversarially confirmed it also catches a second reset injected into the I1 handler.
- **P2:** Loosened `_LEG_BULLET_RE` to pin the stage-set→condition partition MEANING (DOTALL, indentation-agnostic, wrap-tolerant body) instead of a hard-coded 3-space indent + single-line `:`-terminated body. Verified it still reds on dropping `verify` and now tolerates a reflowed multi-line condition.
**Reversibility:** easy (test-only)
**Classification:** Mechanical
**Verify:** `pytest tests/contracts/test_rebirth_handshake.py` 22 passed; full suite 409 passed. Only the owned test file changed.

### 2026-06-11 -- Slice 3.3 fix round 2: pin AC12 leg-aware successor-goal SEMANTICS (codex P1)
**Stage:** review-fix (slice 3.3)
**Finding (codex P1):** AC12 only asserted the `/goal` prefix + TOTAL stage coverage; dropping the trailing `<leg-condition>` placeholder OR swapping the planning-vs-execute condition texts stayed GREEN even though the handoff would re-arm the WRONG leg's goal.
**Fix (test-only, owned file):** Read the real merged drive.md leg-condition selector (`Select <leg-condition> by state.stage`) + canonical leg-goal definitions. Added:
- `test_handoff_block_goal_line_carries_leg_condition_placeholder` — the bounded handoff block's `/goal` re-arm line CONTAINS a bound `<leg-condition>` token (not a dropped/empty tail).
- `_leg_bullet_map` + `_assert_leg_condition_mapping` — beyond totality, the PLANNING stage-set {premises, plan} binds the PLANNING-leg condition (`NOT met while autonomous planning … design, autoplan, dual-voice review … work remains.`) and the EXECUTE stage-set {execute, verify, ship} binds the EXECUTE-leg condition (`… implement / review / harden / verify / ship work remains.`), and each leg is NOT the other's condition. Reuses the AC12 `_LEG_BULLET_RE`/`_STAGE_TOK_RE` enumeration; conditions matched as `_norm`'d meaning-bearing fragments (reflow-tolerant, wrong-mapping-tight).
- Three flip-proofs (mutate a COPY of the selector/handoff block, never the real file), each leaving totality intact so they bite on MAPPING: (a) drop the `<leg-condition>` placeholder → reds; (b) SWAP the two condition bodies → reds; (c) mis-map the execute row to the planning condition (one-sided) → reds.
**Reversibility:** easy (test-only)
**Classification:** Mechanical
**Verify:** `pytest tests/contracts/test_rebirth_handshake.py` 27 passed; full suite green. Only the owned test file changed.

### 2026-06-11 -- D-INT3: Phase-3 integration P1 fixes (rebirth handshake)
**Stage:** phase-3 integration (review FINDINGS → fix)
**Task:** lever2-rebirth — resolve 3 integration P1s from codex-review-phase3.md
**Question:** How to reconcile the rebirth_pending lifecycle prose, wire I1 at all claimed boundaries, and make fail-closed hold end-to-end?
**Chosen / changes (`.claude/commands/drive.md` only on the coordinator side; hook unchanged):**
- **P1-1 (prose contradiction):** the Gate/STOP-precedence sentence's blanket `rebirth_pending` "does NOT carry forward" now reads "does NOT carry forward ACROSS the fresh-session resume" and explicitly states the same-session PERSIST half (consistent with the I1 Leave-pending semantics) — ONE lifecycle: persists in-session (still-pressured ⇒ I1 re-hands-off at the next boundary), reset exactly once at the sessionId-rebind in the successor.
- **P1-2 (I1 had no consumer outside Execute):** I1 is restated as the ONE shared rebirth-checkpoint routine every safe-boundary site calls; its preamble enumerates Execute/Plan/Verify/Ship; the Coordinator soft-check is generalized to "ANY autonomous stage"; and the soft-check + I1 invocation is wired into Stage 1 Plan, Stage 4b Verify, and Stage 5 Ship (before the ship marker / Gate B), not just the Execute loop.
- **P1-3 (fail-closed not enforced at the resume/consumer side):** the resume `waiting=="rebirth"` bullet now RE-PROVES via `bin/drive-conformance.sh $RUN_DIR --mode checkpoint` before continuing — it does NOT trust the marker tip alone (per the Durable checkpoint contract, a tip-matching marker is necessary-NOT-sufficient: an open in-flight marker / mid-redesign span can postdate it). A failing/erroring proof OR a missing/stale marker FAILS CLOSED with `stop:checkpoint-unprovable`. This is the sole carve-out from the marker-consume "missing/invalid → reconcile from scratch" rule.
- **P1-3 outbound (adversarial-review tightening):** Present-human-pause step 1 now states it NEVER sets `waiting="rebirth"` itself — only I1 sets it after its passing proof + durable marker; `rebirth` is not a generic caller-supplied pause reason. Closes the sibling-caller bypass where a turn could end on `waiting="rebirth"` without I1's prove→marker→wait sequence.
**Adversarial review:** codex (read-only) found two real bypasses in the first plan — (A) trusting the marker tip alone defeats fail-closed (necessary-not-sufficient); (B) the outbound Present-human-pause path still set `rebirth` generically. Both fixed and re-reviewed on the corrected artifact.
**Tests:** updated `tests/contracts/test_rebirth_handshake.py` (corrected lifecycle, I1-wired-at-every-boundary, resume re-prove fail-closed, outbound I1-sole-setter) + `test/drive-soft-check-doc.test.sh` boundary pins; new pins proven RED against pre-fix prose (mutate-a-copy). Full suite: `pytest -q` green, `drive-conformance.test.sh` PASS=114, `drive-soft-check-doc.test.sh` PASS=21.
**Reversibility:** easy (coordinator prose + tests)
**Classification:** Mechanical (resolving review-flagged P1s against the design's stated contract)

## Phase-3 integration fix round 2 (2026-06-11)

- **P1-1 (I1 at phase-design boundary):** Added the per-phase DESIGN sub-stage to the I1
  preamble's Execute boundary list, and a real call site at Execute step 1 — after
  `/drive-design` converges (its `inflight-design-<P>.marker` cleared), BEFORE freezing base /
  dispatching slices. Mechanical (completeness): the boundary was missing a consumer; the
  shared I1 routine + soft-check are invoked there like every other safe boundary. Also added
  the boundary to the Execute-loop preamble enumeration for consistency. Left the
  Coordinator-soft-check section's representative enumeration unchanged (it is pinned by
  drive-soft-check-doc.test.sh, not in this surface; the I1 preamble is the authoritative
  per-stage call-site list).
- **P1-2 (same-session re-paste re-arm):** The `rebirth_pending=false` re-arm was gated on the
  sessionId-rebind (fresh-session only); a SAME-session `/drive <runId>` re-paste took the
  rebirth-continue CONTINUE path and skipped the reset. Fix: reset `rebirth_pending=false`
  UNCONDITIONALLY on the passing-proof rebirth-continue branch. Reconciled the "single reset
  point" contract → "reset-on-resume by the SAME logical re-arm on exactly two scoped paths
  (rebind for fresh-session; rebirth-continue for same-session re-paste)".
- **Codex adversarial review (gpt-5.4) findings acted on:** (F1) scoped the prose so a
  same-session NON-rebirth resume (Gate/STOP re-paste in the same session) does NOT clear —
  a deferred `rebirth_pending` PERSISTS so I1 still hands off; (F2) the same-session reset
  belongs ONLY on the passing-proof CONTINUE branch (never before re-prove, never on the
  fail-closed STOP); (F3) added the structural negative pin that the marker-consume bullet
  (same-session non-rebirth reconcile) carries NO reset, plus the prose negative pin.
- **Tests:** Rewrote the single-reset structural pin to the logical reset-on-resume contract
  (reset present at rebind index 0 AND rebirth-continue index 2; absent from marker-consume
  index 1 and the I1 outgoing handler); added P1-1 preamble + call-site pins with
  mutate-a-copy flip-proofs. All new pins proven RED against pre-fix drive.md (2ed774d).
  Verified: test_checkpoint_contract.py untouched (only pins rebind-is-first + template key).

### 2026-06-11 -- Act on codex holistic second-opinion (ship-with-caveats)
**Stage:** harden (phase 3) / planning Phase 4
**Task:** proactive-rebirth trigger
**Question:** codex 2nd opinion: design sound but "lossless" overclaimed (state.json unvalidated) + detect->handoff chain prose-only/unproven E2E. How to act?
**Chosen (user):** (1) EXPAND Phase 4 to close both P1s — executable E2E rebirth harness + state.json durability (atomic writes / validate routing fields at checkpoint) + cross-command /goal clause; (2) fix the phase-3 harden P1s NOW (wrong Gate B test assumption + add the /drive-plan rebirth call site).
**Reasoning:** the feature was exhaustively reviewed but never executed as a rebirth cycle; "lossless" leans on an unvalidated state.json. Phase 4 becomes the proof-of-correctness phase. Classification: User-Challenge (surfaced + decided with the user).
**Reversibility:** medium.

### 2026-06-11 -- Phase-3 harden scope-widening: edit /drive-plan (root-cause of Plan-boundary P1)
**Stage:** harden (phase 3)
**Question:** drive.md promises Plan-stage I1 but the delegated /drive-plan command has no rebirth call site -> a rebirth during planning has no consumer. /drive-plan is outside the phase-3 diff.
**Chosen:** edit /drive-plan in the phase-3 harden pass (flagged-P1 root-cause exception per the harden scope-creep gate), adding the rebirth-checkpoint call site at /drive-plan's safe boundaries.
**Reasoning:** the Plan boundary's handshake is unwired without it; deferring ships a broken Plan-stage boundary. Classification: Mechanical (root-cause exception, logged + surfaced at Gate B).
**Reversibility:** easy.

### 2026-06-11 -- Phase-3 harden round 2 fix: /drive-plan rebirth call site + drive-plan pin; Gate B pin already correct
**Stage:** harden (phase 3, fix round 2)
**Question:** Apply harden-3-1.md / codex-harden-3.md P1s — (P1-1) /drive-plan missing the rebirth call site; (P1-2) wrong Gate B test assumption + a drive-plan invocation pin. (Holistic P1s — E2E harness + state.json durability — routed to expanded Phase 4, NOT done here.)
**Chosen:**
- P1-1: added a "Rebirth checkpoint at the planning safe boundaries" paragraph to `.claude/commands/drive-plan.md` after the design-review convergence loop, before Gate A. It invokes the Coordinator soft-check + Safe-boundary rebirth handler at each planning safe boundary (after each design-review round, before Gate A), referencing drive.md's § *Coordinator soft-check* + § *I1* routine (prove `--mode checkpoint` → write `checkpoint-complete.marker` → set `waiting="rebirth"` → Present human pause with `/drive <runId>`) rather than duplicating I1 prose. Graceful-degrade-if-unreachable mirrors the existing Gate A run-graph fallback.
- P1-2 (test): the wrong-Gate-B-assumption pin was ALREADY corrected by harden round 1 (commit 2ed774d added `test_gate_precedence_neither_gate_emits_runid_resume` = AC9 ground truth: both Gate A and Gate B hand a `/goal` line, drive.md gate-precedence prose ~L402-406; NEITHER emits `/drive <runId>`; the runId resume line is the rebirth handshake's distinct contribution). Verified the committed pin matches drive.md and the suite is green — no further correction needed this round.
- Added `test_drive_plan_invokes_rebirth_handshake_at_planning_boundary` + a mutate-a-copy flip-proof in `tests/contracts/test_rebirth_handshake.py`. Proven to RED against the pre-fix `git show HEAD:.claude/commands/drive-plan.md` (no handshake clause) and GREEN against the fix.
**Verification:** `python3 -m pytest -q` 428 passed; `bash test/drive-conformance.test.sh` 114 PASS/0; `bash test/drive-soft-check-doc.test.sh` 21 PASS/0.
**Reversibility:** easy (prose + test only).
**Classification:** Mechanical (root-cause scope exception per L1034; already surfaced at Gate B).

### 2026-06-11 -- D40: state.json durability = atomic writes + SEPARATE --mode state-lint (not folded into checkpoint)
**Stage:** design (phase 4)
**Task:** lever2-rebirth phase 4 — proof-of-correctness, close the "lossless overclaim" P1
**Question:** (codex holistic P1) "lossless" leans on an unvalidated state.json. Validate the routing fields at checkpoint, or narrow the claim in docs?
**Options considered:** (a) fold routing-field validation INTO `--mode checkpoint`; (b) atomic writes + a SEPARATE `--mode state-lint` validator run alongside checkpoint; (c) narrow the claim to "state.json is a best-effort hint" in docs only.
**Chosen:** (b) VALIDATE+ATOMIC, pragmatic subset — atomic-write contract in drive.md + a new `--mode state-lint` (parses + routing fields `phaseList`/slice `step/owns/deps`/`verify`/`ship` present + well-formed), the rebirth handoff/resume run it ALONGSIDE `--mode checkpoint`. PLUS the docs caveat (c) for the residual.
**Reasoning:** `--mode checkpoint` is narrator-independent by hard phase-1 contract (NEVER reads state.json — D8, script header L4-5); folding state-validation in would break the proof's load-bearing invariant. A separate mode keeps the proof pristine while still catching a corrupt/incomplete state.json before a handoff. The prompt said "checkpoint validate the routing fields," but the primary artifact (the never-read-state.json contract) makes a separate mode the correct structural fix. Deep slice owns/deps graph cross-validation = out of scope (followup). User chose "close both P1s" → this closes the lossless-overclaim without compromising the proof.
**Reversibility:** easy.
**Classification:** Taste (recommendation executed; surface at Gate B).

### 2026-06-11 -- D41: drive-ship.md needs no /goal edit; rebirth-pause clause lands in drive-plan.md leg-2 only
**Stage:** design (phase 4)
**Question:** The routed followup names drive-ship.md (Gate B) for the cross-command /goal rebirth-pause clause, but does Gate B emit a goal?
**Chosen:** Inject the rebirth-pause clause into the drive-plan.md Gate A leg-2 goal ONLY; drive-ship.md gets no /goal edit.
**Reasoning:** Verified against the live file — Gate B (drive-ship.md L70-76) sets waiting="gateB" + presents, "After approval" pushes immediately; drive-plan.md L112 confirms "After Gate B the push is immediate, so no further goal is needed." The leg-2 goal is active through the ship leg, so the rebirth-pause clause there covers a rebirth during ship. A divergence from the prompt's "drive-ship.md (Gate B)" assumption, logged so the omission is explicit. An optional non-load-bearing Gate-B cross-reference sentence is permitted, not required.
**Reversibility:** easy.
**Classification:** Mechanical.

### 2026-06-11 -- D42: E2E harness proves the executable + state-reconstruction half, not the prose coordinator
**Stage:** design (phase 4)
**Question:** The coordinator is prompt-driven (drive.md is instructions, not code). What can an "executable end-to-end rebirth harness" actually prove?
**Chosen:** A scripted simulation (tests/contracts/test_rebirth_e2e.py) that runs the REAL executable pieces — drive-stop-hook.py (steer), drive-conformance.sh --mode checkpoint (proof), the scriptable handoff writes (marker + waiting="rebirth"), the scriptable resume acts (rebind + marker-consume + re-arm + waiting-clear) — and asserts the durable artifacts suffice for a fresh process to reconstruct + continue (the Stop hook re-attributes to the successor session; --mode checkpoint still passes). Chain-break negatives red the harness when any link is severed. The prose-driven coordinator STEPS stay pinned by the slice-1.3/3.3 contract suites.
**Reasoning:** A literal "run the coordinator" isn't a unit test. The harness proves the executable + state-reconstruction half honestly (header states the CAN/CANNOT scope); re-grepping prose adds nothing the contract suites don't already pin.
**Reversibility:** easy (test-only).
**Classification:** Mechanical.

### 2026-06-11 -- D43: no installer change for the rebirth machinery (asserted, not added)
**Stage:** design (phase 4)
**Question:** Does the new hook behavior / the rebirth_thresholds files need install/sync wiring?
**Chosen:** No installer change. Assert the sibling layout with a layout pin instead of adding install code.
**Reasoning:** The Stop hook is already registered by install-operating-rules.sh (the phase-2/3 edits are to the same already-installed script); bin/rebirth-thresholds.json + bin/rebirth_thresholds.py are reached by sibling path from the symlinked statusline.sh/drive-stop-hook.py (bin/ is canonical-by-reference — installers symlink, never copy bin/). Phase-1 divergence #5, Phase-2 divergence #5, routed P3 confirmation.
**Reversibility:** easy.
**Classification:** Mechanical.

## Phase 4 design — dual-voice review round 1 (codex 1 BLOCKING + 2 MAJOR + 1 MINOR; Claude 2 P2 + 1 P3)

### 2026-06-11 -- D40 (amended, phasedesign4 review r1): state-lint WIRED into the prove/re-prove chain + STRENGTHENED validation
**Stage:** design (phase 4, review round 1)
**Question:** Codex BLOCKING — the new `--mode state-lint` was added but the I1 prove step / resume re-prove still named `--mode checkpoint` ONLY, so state-lint would ship as DEAD CODE and the lossless gap stays open. Codex MAJOR — the validation was too weak (phaseList just an array, step any string), so `phaseList:[]` or `step:"bogus"` lints clean yet is unroutable.
**Chosen:** (a) WIRE state-lint into the handshake: the I1 prove step runs BOTH `--mode checkpoint` AND `--mode state-lint` (both clean is the precondition to write checkpoint-complete.marker + set waiting="rebirth"); the resume re-prove also runs BOTH; either non-clean fails closed identically. drive.md's prove (~L255/L361) + re-prove (~L77) prose edited to name both modes (owned by slice 4.2). (b) STRENGTHEN state-lint to MEANINGFUL routability: phaseList is a non-empty array of phase-id strings (stage-aware — empty only legal at premises/plan, fails at execute/verify/ship/done); each slice step ∈ {queued, implementing, awaiting_review, needs_fix, converged, blocked}; owns non-empty array; deps an array; verify/ship well-formed objects. A genuinely-unroutable state.json FAILS.
**Reasoning:** Both findings defeat the P1's purpose — dead code closes nothing, and a type-only check passes on unroutable state. Wiring + meaningful validation is what actually closes the lossless-overclaim gap. D8 preserved: checkpoint still NEVER reads state.json; the two modes stay separate, merely co-invoked at prove/re-prove. The enum/template checks are grounded in the real drive.md (step enum L130/819-865; template L174-181).
**Reversibility:** easy.
**Classification:** Mechanical (wiring/validation correctness; the original validate-vs-narrow split is unchanged Taste).

### 2026-06-11 -- D44 [Mechanical]: state-lint slice-routing violation cardinality = ONE per malformed slice
**Stage:** design (phase 4, review round 1)
**Question:** Claude P2 — I2b offered "first offender OR aggregate one per bad slice" without deciding; AC/tests could pin either (green test for an unpinned contract).
**Chosen:** ONE violation object per malformed slice, scope = the slice id — matching how audit/ship already emit per-offender violation objects (drive-conformance.sh dedup-then-emit-each). Pinned in I2b + AC3 so 4.1's harness Step-4 state-lint-clean assertion and 4.2's bash cases agree on count.
**Reasoning:** Per-offender is consistent with the existing multi-violation modes and gives a complete failure report in one run. Removes the green-for-wrong-reason gap.
**Reversibility:** easy.
**Classification:** Mechanical.

### 2026-06-11 -- D45 [Mechanical]: drive.md gate-precedence/Stage-0 prose + its pinned test corrected to "Gate B hands NO goal"
**Stage:** design (phase 4, review round 1)
**Question:** Codex MAJOR — D41 correctly says drive-ship.md emits no goal, but drive.md (gate-precedence ~L401-404 "BOTH Gate A and Gate B hand the next leg's /goal line"; Stage-0 ~L711-712 "re-armed at each gate (Gate A and Gate B hand …)") AND the pinned test `test_gate_precedence_neither_gate_emits_runid_resume` (test_rebirth_handshake.py ~L745) still assert "Gate B hands a goal" — a live contradiction against the ground truth.
**Chosen:** Slice 4.2 CORRECTS both drive.md prose sites to "Gate A hands the next leg's /goal line on approval; Gate B hands NONE (after Gate-B approval the push is immediate — no next leg)" and UPDATES the pinned test to assert that truth (preserving its load-bearing half: NEITHER gate emits a `/drive <runId>` token; the runId resume line is rebirth's distinct contribution). drive-ship.md goal surface stays byte-unchanged. The test file `tests/contracts/test_rebirth_handshake.py` is a slice-3.x contract test OUTSIDE phase-4 slice ownership — editing it is a flagged SCOPE-WIDENING ROOT-CAUSE EXCEPTION for slice 4.2 (the prose edit and its pinning test are one atomic contract change; splitting them reds the suite). Anchor all edits on prose, not line numbers (they shift).
**Reasoning:** A doc/test that contradicts the real Gate-B behavior — and a test that ENFORCES the falsehood — is the load-bearing half of the P1-3 contradiction. Correcting the upstream prose at its source (not the deployed copy) and re-pinning the test to the truth resolves it. Reconciles the routed cross-command /goal followup: drive-plan.md leg-2 GETS the rebirth-pause clause (Gate A leg), drive-ship.md correctly does NOT (D41); the followup's "Gate B re-arm" premise was itself wrong.
**Reversibility:** easy.
**Classification:** Mechanical.

### 2026-06-11 -- D-phase4-r1-misc [Mechanical]: jq prereq broadened; atomic-write stated as NEW; line-number anchors dropped
**Stage:** design (phase 4, review round 1)
**Question:** Codex MINOR + Claude P2-1 + Claude P3.
**Chosen:** (1) jq prereq — drive.md L18 scopes jq "for ship" only; state-lint runs jq at the rebirth handoff (outside ship), so 4.2 broadens the prereq to require jq for the conformance checker generally (ship + checkpoint + state-lint). (2) atomic-write — stated plainly as a genuinely NEW clause 4.2 ADDS to the state-write paragraph (the existing prose mandates jq for JSON-safety only, NOT mv/atomic-rename; the marker rule is the precedent, not state.json itself); dropped the inaccurate "already the convention" framing. (3) line numbers — design pins/edits anchor on prose/clause text, not drive.md Lnnn references (4.2's + 4.3's own edits shift them); the L97→L116 stop-hook fixup note already lives in I4.5.
**Reversibility:** easy.
**Classification:** Mechanical.

### 2026-06-11 -- phasedesign4 review round 2 (codex MAJOR + MINOR): state-lint wiring completeness + Gate-B scope
**Stage:** design (phase 4, review round 2)
**Task:** lever2-rebirth phase 4 — close the two round-2 review findings
**Question:** Codex MAJOR (Fix-1 incomplete: checkpoint-only surfaces remain) + codex MINOR (Fix-3 Gate-B clause site contradictory + under-pinned).
**Chosen:**
- **D40 amended r2** — the both-modes proof is defined ONCE in drive.md §"Durable checkpoint contract" (I1). EVERY drive.md surface naming the proof (prove step, resume re-prove, AND the rebirth-auth sentence "RE-PROVE via …") names BOTH `--mode checkpoint` AND `--mode state-lint`; non-drive.md surfaces REFERENCE the I1 routine rather than re-spell the modes — so no surface is left checkpoint-only. (Round-1 wired the 3 prove sites but left the rebirth-auth sentence + cross-command/hook surfaces checkpoint-only.)
- **D46 [Mechanical]** — drive-plan.md's rebirth call-site (slice 4.3) drops the inline `--mode checkpoint`-only spelling and references drive.md § *I1 — Safe-boundary rebirth handler* for the both-modes proof. DRY, one authoritative definition. The cleaner of the two prompt options (vs re-spelling both modes in drive-plan.md).
- **D47 [Mechanical]** — `bin/drive-stop-hook.py` stays byte-unchanged: its escalation steer is ADVISORY and points at the I1 routine ("run the rebirth handoff per the contract"); its "(bin/drive-conformance.sh --mode checkpoint)" is an illustrative parenthetical, not the authoritative proof definition (I1 is, naming both modes). No phase-4 slice owns the hook (a slice-2.x file) for this — point-at-I1, not enumerate-everywhere. Resolves "no slice owns the Stop-hook drift" by deciding there is no drift to own.
- **Gate-B scope (codex MINOR)** — removed the residual scope text landing a Gate-B `/goal` clause in drive-ship.md (contradicted D41/AC8): the Scope paragraph + I3 header now state drive-plan.md leg-2 ONLY; drive-ship.md byte-unchanged for the goal surface. AND the SECOND corrected drive.md prose site (Stage-0 §"Set the session goal") gets its OWN test pin (a sibling assertion or `test_stage0_goal_gateB_hands_none`) so BOTH corrected sites are guarded, not just the gate-precedence one (AC8 + slice 4.2).
- Trimmed the atomic-write "this is a genuinely NEW contract / NOT already the convention" over-narration (Claude flag) to a plain statement.
**Reversibility:** easy (design prose only).
**Classification:** Mechanical.

### 2026-06-11 -- Slice 4.3 implement: drive-plan.md leg-2 /goal rebirth-pause + I1 DRY (AC7, D46, D41)
**Stage:** implement (slice 4.3)
**Task:** lever2-rebirth — cross-command /goal rebirth-pause clause
- **AC7:** drive-plan.md Gate A leg-2 `/goal` template now admits a rebirth pause — inserted the verbatim drive.md clause `, OR is paused at a rebirth handoff (waiting="rebirth") awaiting my paste of the resume line` before `. NOT met while …`, keeping the existing satisfying states intact. Byte-aligned with drive.md's templates (the cross-file `/goal` consistency the AC7/edge-case-4 pin asserts).
- **D46:** drive-plan.md's rebirth call-site no longer re-spells the proof modes — CUT the inline `bin/drive-conformance.sh $RUN_DIR --mode checkpoint` spelling from the parenthetical; it now references drive.md § *I1 — Safe-boundary rebirth handler* as the sole proof-mode authority (drive-plan.md names NO `--mode` token — verified `grep -c -- '--mode' = 0`).
- **D41:** drive-ship.md goal surface byte-unchanged — Gate B emits no `/goal` (immediate push), so no rebirth clause added there. Verified `git diff HEAD -- drive-ship.md` empty. The optional non-load-bearing Gate-B cross-reference sentence was not added (not required).
**Owns:** .claude/commands/drive-plan.md (committed), .claude/commands/drive-ship.md (byte-unchanged, confirmed).
**Reversibility:** easy (prose only).
**Classification:** Mechanical.

### 2026-06-11 -- Slice 4.5 (installer-assertion) — sibling-layout pin, no install code
**Stage:** implement (slice 4.5)
**Task:** lever2-rebirth phase 4 — AC12
**Decision:** Implemented AC12 as a bash test (test/rebirth-install-layout.test.sh) matching the
existing test/*.test.sh conventions (REPO_DIR from BASH_SOURCE, PASS/FAIL check()). Verified
assumptions HOLD (no REDESIGN): no installer needs a change. Pins, against the REAL files:
(1) bin/rebirth-thresholds.json + bin/rebirth_thresholds.py are siblings of
bin/drive-stop-hook.py + bin/statusline.sh (same dir == bin/); (2) drive-stop-hook.py
sys.path.insert(0, dirname(__file__)) + import rebirth_thresholds (sibling module);
(3) rebirth_thresholds.py THRESHOLDS_PATH = dirname(__file__)/rebirth-thresholds.json;
(4) statusline.sh THRESHOLDS_FILE = dirname(BASH_SOURCE)/rebirth-thresholds.json;
(5) neither installer COPIES the rebirth files (cp grep == 0) — the Stop hook is registered as
an in-place `python3 "<repo>/bin/drive-stop-hook.py"` command and statusline is `ln -sfn`
symlinked, so bin/ is canonical-by-reference and the siblings resolve with no install step (D43).
**Real-guard proof:** 5 mutation copies (move json out of bin/, statusline→abspath,
resolver→cwd, installer cp of the json, drop the sys.path.insert) each flip the test rc 0→1;
restored tree passes. 17/17 PASS.
**Reversibility:** easy. **Classification:** Mechanical.

## Slice 4.2 implement (state-durability) — 2026-06-11

### D-slice4.2-1: state-lint slice-validation jq must bind the entry before `index()`
**Stage:** implement (slice 4.2)
**Task:** `--mode state-lint` slice step-enum check
**Decision:** `["…enum…"] | index(.value.step)` errors ("Cannot index array with string value") because inside `index(...)` the `.` is the enum ARRAY, not the entry. Bind the entry (`. as $e`) and the step (`($e.value.step) as $s`) first, then `$steps | index($s)`. All `.value.*` field reads under the slice select use `$e.value.*`. Verified clean fixture lints clean and bad fixtures emit `slice-routing-malformed` per malformed slice (D44).
**Classification:** Mechanical

### D-slice4.2-2: state-lint envelope + exit semantics
**Stage:** implement (slice 4.2)
**Decision:** state-lint emits the standard `{clean,mode,tip,violations}` envelope (tip = current drive/<runId> rev). Exit 0 clean / 1 any violation / 2 only on usage, missing RUN_DIR, missing state.json, or unresolvable featureBranch. A CORRUPT state.json is exit 1 `unparseable-state` (a verdict the handoff fails closed on), NOT exit 2 — only a genuinely-absent state.json file is the exit-2 IO case. phaseList-empty is stage-aware (well-formed at premises/plan, `phaselist-malformed` once stage ∈ {execute,verify,ship,done}). Proven flip: every new SL bash case is exit 2 (usage) against the pre-state-lint script.
**Classification:** Mechanical

### D-slice4.2-3: drive.md is the single both-modes proof authority; intra-section refs generalized
**Stage:** implement (slice 4.2)
**Decision:** §"Durable checkpoint contract" now defines the proof = `--mode checkpoint` AND `--mode state-lint`, both clean. The I1 prove step, the resume RE-PROVE sentence, and the rebirth-auth sentence all name BOTH modes. The two intra-section references that said "re-run `--mode checkpoint`" (the marker necessary-not-sufficient rule + Prove-then-pause) were generalized to "re-run the proof (both modes, above)" so NO drive.md surface is checkpoint-only (AC6). The SEPARATE-modes clause keeps `--mode checkpoint` named (it states checkpoint NEVER reads state.json — load-bearing D8). jq prereq broadened beyond ship. Atomic-write clause (tmp + mv over state.json) added to the state-write paragraph.
**Classification:** Mechanical

### D-slice4.2-4: Gate-B prose + pinned test corrected to D45 truth
**Stage:** implement (slice 4.2)
**Decision:** Both false "BOTH Gate A and Gate B hand the next leg's /goal" sites (gate-precedence prose + Stage-0 §"Set the session goal") corrected: Gate A hands the next leg's /goal; Gate B hands none (immediate push). `test_gate_precedence_neither_gate_emits_runid_resume` updated to pin the truth + assert the false claim is GONE; a sibling `test_stage0_goal_gateB_hands_none` pins the Stage-0 site (both corrected sites now guarded — the P2-fix). Two flip-proofs revert a COPY to the false claim (raw line-wrapped form) and confirm the live pin reds. Existing `test_resume_rebirth_continue_is_fail_closed_re_proven` updated to expect the both-modes RE-PROVE text (AC6). drive-ship.md goal surface byte-unchanged (not in 4.2's owns). 431 pytest + 135 bash green.
**Classification:** Mechanical

### D-slice4.5-fix: AC12 layout test guards made real (P1-1/P1-2)
**Stage:** implement (slice 4.5 fix on 74e56ee)
**Decision:** Two MAJOR codex findings closed in test/rebirth-install-layout.test.sh (only owned file).
- P1-1 (installer no-copy guard was a literal grep): replaced with a BROAD copy-class scan — strip comments, then match any copy verb (`cp`, `cp -R/-r`, `install`, `rsync`, `ditto`, python `shutil.copy*`/`copyfile`/`copyfileobj`) on a line that references bin/ or a rebirth file. Reference pattern catches `/bin` with no trailing slash (the `cp -R "$REPO_DIR/bin" dst` whole-dir-copy attack), `bin/` as a component, the rebirth/hook/statusline basenames, and `$BIN`/`${BIN}`. The two legit backup copies (`cp "$GLOBAL"`, `cp -- "$SETTINGS"`) name ~/CLAUDE.md and settings.json, so they don't match; `ln -sfn`/backup `mv` aren't copy verbs.
- P1-2 (sibling-path checks were appears-somewhere greps that false-pass on a later override): both now assert the EFFECTIVE runtime path. Resolver: import rebirth_thresholds and compare realpath(dirname(THRESHOLDS_PATH)) to bin/. Statusline: replay its THRESHOLDS_FILE= assignments in source order (last wins), textually substituting `${BASH_SOURCE[0]}`/`$BASH_SOURCE` with the real script path (the interpreter ignores a caller override of the BASH_SOURCE call-stack array inside eval), then resolve through dirname and compare to bin/.
**Proof:** mutated COPIES in /tmp scratch (never the real non-owned files). P1-1: cp -R bin / install json / shutil.copy resolver / rsync bin / cp $BIN json / ditto bin — all 6 RED. P1-2: resolver absolute override (sibling expr STILL present yet RED — old grep would false-pass), statusline absolute override, statusline sibling-style-but-wrong-dir override — all RED. Real tree 17/17 PASS; restored copies green; git status shows only the owned test file.
**Classification:** Mechanical

### 2026-06-11 -- D-slice4.2-fix: state-lint robustness + handoff both-modes pin
**Stage:** implement (fix round on 218bc02)
**Task:** slice 4.2 review findings P1-A / P1-B / P1-C
- **P1-A (non-object slice VALUE crashed jq, exit 5):** added `(($e.value | type) != "object")` as the first `select` clause so the `or` short-circuits before indexing `.step` — a scalar/array/bool slice value now emits the named `slice-routing-malformed` (exit 1) per slice (D44), never a crash.
- **P1-B (non-object `.slices` CONTAINER false-cleaned):** replaced the `if (.slices|type)=="object"` skip-on-else with an explicit else that emits a `slices-malformed` violation. **Stage-aware rule chosen:** an empty `{}` object is ALWAYS clean (a run may not have designed slices yet); a non-object container (null/array/scalar/missing) is `slices-malformed` ONLY once the run is past plan (stage ∉ {premises, plan}) — at premises/plan it is well-formed-absent, mirroring the empty-phaseList rule. New `slices-malformed` violation name (scope `slices`).
- **P1-C (drive.md:478 handoff still checkpoint-only):** rewrote the resumability claim to "proven resumable — both proof modes clean (checkpoint AND state-lint passed)"; added 2 contract pins (`test_handoff_block_resumability_claim_names_both_proof_modes` + flip-proof sibling) in tests/contracts/test_rebirth_handshake.py. Grepped drive.md: L478 was the only remaining checkpoint-only PROOF surface (L79-81/268-280 already name both modes from the prior commit).
- **P2-1 (violation-name set undocumented in usage):** DEFERRED — review says docs slice 4.4 owns the enumerated list; not folded here to avoid file-ownership overlap.
- Fixtures added: `slice_scalar`, `slices_array`, `slices_empty_executing`. Flips proven against pre-fix script (exit 5 / exit 0 → exit 1) and pre-fix drive.md (both pins red).

### 2026-06-11 -- D-slice4.2-fix3: state-lint completeness — JSON-safe violation() + deps grammar (FINAL state-lint round, on 8b0b7f2)
**Stage:** implement (fix round 3)
**Task:** slice 4.2 review findings P1-A (Claude BLOCKING) / P1-B (codex MAJOR)
- **P1-A (`violation()` emitted INVALID JSON for a metachar slice-id KEY):** `violation()` built its object via `printf` with raw `%s` interpolation, so a state.json-derived slice-id KEY (`$sid`, the only corruption-controlled scope) carrying `"`, `\`, or a control char produced a syntactically-broken `{clean,mode,tip,violations}` envelope — breaking downstream `jq`/marker parse at exactly the corrupt-state path state-lint defends. FIX: rebuilt `violation()` with `jq -cn --arg scope/reason/exp/found '{...}'` so scope/reason/expected_sha/found_sha are always JSON-escaped. **Output is byte-identical to the old printf for metachar-free input** (verified: `jq -cn` compact form matches the old key order exactly), so NO other mode's envelope changes — this is the single escaping chokepoint ALL 30 call sites flow through. The only state.json-derived scope is the slice-id KEY (line 932); every other scope is a literal or git/fs-derived (tip/ptip/rsha are SHAs).
- **P1-B (`deps` elements not validated as slice-ids):** the slice-routing jq checked `deps` is an array but not its elements, so `"deps":[42]` / `"deps":["1 bad"]` clean-passed despite /drive dispatching on CONVERGED deps to look up sibling slices. FIX: added a `select` clause rejecting any deps element that is a non-string OR a string not matching the slice-id grammar `^[0-9]+[a-z]?\.[0-9]+$` (same grammar as the slice-id KEY) → `slice-routing-malformed` scoped to the slice.
- **Comprehensiveness (final state-lint round):** re-confirmed EVERY state.json-derived violation value is now JSON-escaped (single `violation()` chokepoint), and every routing field is validated: root-object, stage-enum, phaseList container+elems, slices container+keys+values+step+owns+deps array+**deps elems**, verify, ship.
- Fixtures added: `slice_key_metachar` (`1.2"x` key → envelope stays valid JSON + violation fires), `deps_nonstring` (`[42]`), `deps_badref` (`["1 bad"]`), `deps_clean` (`["1.1"]` still passes). New `assert_valid_json` helper. Suites green: `bash test/drive-conformance.test.sh` PASS=165 FAIL=0; `python3 -m pytest` 433 passed.

## Slice 4.5 — fix round 2 (on a2007c6)

- **P1 (no-copy guard: indirected miss + over-match).** Replaced the single line-grep
  with a Python taint pass: pass 1 taints any var assigned a value referencing the REPO
  bin/ or a rebirth/hook/statusline file (handles both `VAR=...` shell and `var = ...`
  python forms); pass 2 flags a copy-class op (cp/install/rsync/ditto/shutil.copy*/
  copyfileobj) whose line names a rebirth literal OR a tainted var ($v/${v}/bare python
  `v`). Precision via a `bin/` anchor that only counts $BIN/${BIN} or `$VAR/bin/`-style
  REPO bin, with /usr/bin · /usr/local/bin · /bin · /sbin scrubbed out first — so
  `cp /usr/bin/foo`, `cp "$GLOBAL"` (~/CLAUDE.md), `cp -- "$SETTINGS"` stay green while
  `cp "$HOOK_PY"`, `install -m 755 "$HOOK_PY"`, `shutil.copy2(statusline_src, ...)`,
  `cp "$STATUSLINE_SRC"` all red. Guard python written to a mktemp file and invoked
  normally (a heredoc nested in $(...) trips bash 3.2's paren matcher).
- **P2 (statusline replay ignores export/readonly overrides).** Broadened the replay
  grep to match `export `/`readonly `/`declare[ -flags] `-prefixed THRESHOLDS_FILE=
  assignments and strip the keyword before eval so the override lands in-scope (last
  wins). Proven: a copy with `export THRESHOLDS_FILE=/abs/override` (and readonly/
  declare -x variants) reds; the real tree greens.
- Proof: flips/non-flips exercised on COPIES only; real-tree `bash test/rebirth-install-layout.test.sh` = 17/17, exit 0; git status shows only the owned test file.

## Slice 4.2 — fix round 2 (on 56ef9bf): close state-lint completeness class

Closed the remaining THREE state-lint holes so a parseable-but-unroutable state.json
ALWAYS fails with a named violation (exit 1) and NEVER crashes (0/1/2 + envelope only).

- **P1-A (top-level non-object crashed jq, exit 5).** The parse gate `jq -e . "$SJ"`
  proved valid JSON but NOT an object, so a root array `[1,2,3]` / scalar `42` passed,
  then `.stage` indexing crashed (exit 5, no envelope). FIX: tightened the gate to
  `jq -e 'type == "object"'`; a non-object root now emits `unparseable-state` (exit 1).
- **P1-B (`stage` never validated).** `{"stage":"bogus"}` reached clean. FIX: validate
  `stage` ∈ {premises, plan, execute, verify, ship, done} (the state.json template enum);
  out-of-enum emits the new `stage-malformed` violation (scope `stage`).
- **P1-C (phaseList elems + slice-id keys not ref-checked).** Non-empty-but-unsafe values
  (`"bad ref name"`, `"1 bad"`) passed yet form invalid `phaseInt/<runId>/<P>` /
  `slice/<runId>/<id>` refs and break scope-token parsing. FIX: each phaseList element must
  match the phase-id grammar `^[0-9]+[a-z]?$` (e.g. `1`, `2`, `4a`) → `phaselist-malformed`;
  each slice-id KEY must match the slice-id grammar `^[0-9]+[a-z]?\.[0-9]+$` (e.g. `1.2`,
  `4.3`) → `slice-routing-malformed` scoped to the key. Grammars derived from real run
  state.json values (phaseList `["1","2","3","4"]`, slices `["4.1".."4.5"]`); `4a`-style
  letter suffix admitted for redesign-epoch phase ids.
- **Comprehensiveness sweep:** every routing field read in state-lint is now type/grammar
  guarded — root (object), `stage` (enum), `phaseList` (array+elem grammar), `slices`
  (container type → key grammar + value shape), `verify`/`ship` (type-first). `featureBranch`
  is derived from RUN_DIR basename, not state.json, so a corrupt file can't poison it. No
  remaining crash or false-clean: combined bad-key+scalar-value and numeric-phaseList-elem
  edges stay exit 1, no exit 5. This is the last round on state-lint completeness.
- **Fixtures added** (mkfixture.sh): `toplevel_array`, `toplevel_scalar`, `stage_bogus`,
  `stage_done_clean`, `phaselist_badref`, `phaselist_epoch_clean`, `slice_key_badref`.
  All flip against the pre-fix script (PRE exit 5/0 → POST exit 1); valid inputs (`done`
  stage, `4a` phase, `4a.1` slice) still clean. Suite: 156/0; pytest 433 passed.

## Slice 4.5 fix round 3 (5842752 → next) — review P1×2 (Claude MAJOR + codex MAJOR)
**Stage:** implement (slice 4.5 fix round 3)
**Task:** lever2-rebirth — rebirth-install-layout.test.sh; owns ONLY test/rebirth-install-layout.test.sh
**Reversibility:** easy   **Classification:** Mechanical

- **P1-A (Claude MAJOR) — check #4 export/readonly replay was silently inert.** The
  THRESHOLDS_FILE path-replay grep (L121) buried the post-keyword `[[:space:]]+` INSIDE
  the `declare(...)` sub-branch: `^...(export|readonly|declare([[:space:]]+-[A-Za-z]+)*[[:space:]]+)?THRESHOLDS_FILE=`
  — so `export THRESHOLDS_FILE=` and `readonly THRESHOLDS_FILE=` lines NEVER matched (only
  bare + `declare -x` did). A copy with an `export`/`readonly` override to a non-sibling path
  was never read → effective-path assertion stayed GREEN on a layout-breaking override (the
  exact regression round 2 claimed to fix; its verify passed for the wrong reason — scratch
  copies lived OUTSIDE real bin/, so dir-pinning already produced the expected "no"). FIX:
  moved `[[:space:]]+` OUTSIDE the keyword alternation → `((export|readonly|declare([[:space:]]+-[A-Za-z]+)*)[[:space:]]+)?`.
  L119's strip sed was already correctly grouped (untouched). PROOF (mutating COPIES placed
  INSIDE the real bin/ — so dir-pinning alone returns "yes" and only a READ override can red):
  with the sibling L22 assignment intact + an appended override, OLD grep returns "yes"
  (export, readonly — dropped), NEW grep reds to "no" for all three (`export`, `readonly`,
  `declare -x`); no-override control stays "yes".
- **P1-B (codex MAJOR) — copy-guard taint was one-hop only.** Pass 1 tainted a var whose RHS
  held a rebirth/bin literal but did NOT propagate taint through ALIASES of an already-tainted
  var, so `HOOK_PY=…; SRC="$HOOK_PY"; install "$SRC" dst` and python `statusline_src=…;
  src=statusline_src; shutil.copy2(src,dst)` stayed green. FIX: made taint MULTI-HOP — collect
  all (lhs, rhs) assignments once, then iterate to a FIXPOINT (a var whose RHS references the
  repo bin/, a rebirth file, OR any already-tainted var becomes tainted; repeat until no new
  taint). PROOF: shell 2-hop, python 2-hop, AND a 3-hop chain all red (hits ≥1); legit
  ~/CLAUDE.md + settings.json backups and `/usr/bin` install do NOT false-red (0); real
  installers (install-operating-rules.sh, install-drive-hooks.sh) read 0.
- **Verification:** `bash test/rebirth-install-layout.test.sh` → 17/17 on the real tree. All
  proofs run against tmp COPIES/scratch; real bin/ files byte-identical. `git status` shows
  ONLY test/rebirth-install-layout.test.sh.

### 2026-06-11 -- D: Copy-guard ASSIGN regex now taints prefixed shell assignments (slice 4.5 fix r4, codex MAJOR)
**Stage:** implement (slice 4.5, fix round 4 final)
**Task:** rebirth-install-layout.test.sh copy-guard
The taint ASSIGN regex matched only bare `NAME=...`, missing `export`/`local`/`readonly`/`declare [-flags]`
prefixed assignments — so `export SRC="$HOOK_PY"; cp "$SRC" /x` stayed green, the same indirected-copy class
the test claims to close. Broadened ASSIGN to skip an optional leading shell declaration keyword before `NAME=`
(consistent with the THRESHOLDS_FILE replay prefix handling); python `var = ...` path unchanged. The fixpoint
now propagates a prefixed-assign tainted var multi-hop. Proven: `export SRC`, `local SRC`, and a prefixed-assign
2-hop chain all RED; pre-fix guard was green on all three (proves the gap); legit /usr/bin installs,
~/CLAUDE.md + settings backups, and the `ln` symlink stay green. Test green on real tree (17 PASS).

### 2026-06-11 -- D: state-lint no longer skips an empty/newline slice key (slice 4.2 fix r4, codex MAJOR)
**Stage:** implement (slice 4.2, fix round 4 final)
**Task:** drive-conformance state-lint completeness
The slice-key loop emitted each malformed key on its own line and did `[ -n "$sid" ] || continue`,
so an EMPTY-STRING slice key (`"": {...}`) -- which fails the `^[0-9]+[a-z]?\.[0-9]+$` grammar and is
unroutable -- was DISCARDED and state-lint returned clean (false-clean); a newline-containing key was
also lossily split into fragments. FIX: switched the emit to NUL-delimited output (jq -j emitting
`$e.key, U+0000` after each key) read by `while IFS= read -r -d '' sid`, dropping the empty-skip
`continue`. An empty or newline-bearing key now round-trips losslessly and fires exactly one
`slice-routing-malformed`; violation() (jq --arg) keeps the envelope valid JSON for the newline scope.
The source holds the printable jq escape (jq emits a real NUL at runtime), not a raw NUL byte.
Proven: new fixtures slice_key_empty + slice_key_newline -- pre-fix code returns clean (empty) /
two violations (newline shredded) -> both RED; post-fix exit 1, one named violation, valid envelope.
`bash test/drive-conformance.test.sh` 171 PASS; `python3 -m pytest -q` green.
Note: deps/owns GRAPH dangling/self-ref cross-validation remains DESIGN-SCOPED-OUT (D40) and routed
to followups -- NOT implemented here.

### 2026-06-11 -- D: copy-guard matches repo `bin` at a path boundary (not slash-only)
**Stage:** implement (slice 4.5, fix round 5)
**Task:** lever2-rebirth — installer-layout test copy-guard
**Question:** Why did a wholesale `cp -R "$REPO_DIR/bin" /dest` (no trailing slash) escape the no-copy guard the test claims to catch?
**Options considered:** (a) match `bin` as a path component at its right boundary — `bin` followed by `/` OR a word boundary (`bin(?:/|\b)`), so trailing slash is optional; (b) leave slash-required and only cover the slash form.
**Chosen:** (a) — `REPO_BIN` alternatives changed from `bin/` to `bin(?:/|\b)` for both the `$VAR/bin` and the bare-`bin` arms.
**Reasoning:** `cp -R src dst` (no trailing slash) is the canonical directory-copy idiom, so the slash-only guard left the exact layout-fork it exists to prevent undetected. The `\b` after `bin` matches the right boundary at `/`, quote, space, or end-of-token without re-tripping `/usr/bin`·`/usr/local/bin`·`/bin`·`/sbin` (those are scrubbed when slash-terminated, and the bare arm's `(?<![/\w])` lookbehind rejects the `/`-prefixed absolute system paths even with no trailing slash). Verified on an extracted COPY of the guard: both no-slash and slash wholesale copies RED; all four system-bin installs, both backups, and the `ln -sfn` symlink stay GREEN; real-tree suite 17/17.
**Reversibility:** easy
**Classification:** Mechanical

### 2026-06-12 -- Slice 4.4 docs (flow.md + drive-enforcement.md)
**Stage:** implement (slice 4.4)
**Task:** lever2-rebirth — docs for the proactive-rebirth trigger (AC9/10/11 + doc-half of 12)
- Assumption check: held. Read design-phase4.md I4 + the REAL shipped code; every documented
  mode/violation/field token (checkpoint, state-lint, inflight-open, phaseInt-divergent,
  unparseable-review/harden, epoch-gap, regress-mismatch, epoch-unmarked, unparseable-state,
  stage-malformed, phaselist-malformed, slice-routing-malformed, slices-malformed,
  verify-malformed, ship-malformed, defaultWindow=200000, rebirth_pending) was grep-verified
  present in bin/drive-conformance.sh / rebirth-thresholds.json / drive-stop-hook.py before
  citing — no aspirational behavior.
- flow.md: added a lean "Context-pressure rebirth" section (the map, not the spec) — detection
  signal-only (statusline token-sum, Stop-hook hard-water + coordinator soft-check setting
  rebirth_pending), the I1 prove→marker→waiting=rebirth→present-paste-ready-`/drive <runId>`
  handshake, prompted-not-self-restart, resume-as-continue + sessionId rebind, and where I1 fires.
- drive-enforcement.md: (1) un-staled the mode list (+checkpoint, +state-lint); (2) made the
  phasedesign-gate row epoch-aware (`phasedesign<P>[-r<R>]`) + added an "Epoch-aware phasedesign
  gate" para naming epoch-unmarked/epoch-gap/regress-mismatch; (3) new "Durable checkpoint &
  rebirth" section (both-mode proof = checkpoint AND state-lint both clean, never-reads-state.json
  checkpoint, markers, single-use checkpoint-complete.marker, state-lint routing fields, sessionId
  rebind, canonical-by-reference data file + windows[] maintenance); (4) "Rebirth residuals"
  honest-limits list (single-catastrophic-turn overshoot, absent-hook degradation, gate/STOP
  collision, lossless-precise + owns/deps-graph followup, prompted-not-programmatic handshake,
  legacy-run, stale-pre-redesign-CONVERGED-now-closed, window-table, -r<digits> phase id).
- Verified existing doc-pin tests still pass (drive-soft-check-doc.test.sh 21/21,
  test_cli_flag_doc_refs.py green) — neither pins my doc files; my edits regress neither.
**Reversibility:** easy (docs-only).
**Classification:** Mechanical.

**Flagged for owning slice / followups (NOT in 4.4's owns — docs-only):** AC9 + AC11 call for
NEW doc-content pins — a `test_cli_flag_doc_refs.py`-style grep asserting each documented
conformance mode/violation token is present in bin/drive-conformance.sh, plus doc-presence
string pins for the new section headings and each residual phrase. No such test exists yet
(test_cli_flag_doc_refs.py covers ONLY the `mc` CLI; no test pins drive-enforcement.md content).
4.4 owns ONLY docs/flow.md + docs/drive-enforcement.md, so this doc-pin test must be added by
the test-owning slice (4.1 owns the new contract test surface) or routed to followups.

### 2026-06-12 -- Slice 4.1 e2e-harness: implemented tests/contracts/test_rebirth_e2e.py (AC1+AC2)
**Stage:** implement (slice 4.1)
**Task:** lever2-rebirth — EXECUTABLE end-to-end rebirth harness (closes codex 'detect→handoff chain is advisory/unproven E2E' P1)
- Built `mid_run_fixture(home, *, inflight, rebirth_pending)` over a real git repo (drive/<runId> + a live phaseInt/<runId>/1 descendant) + a fake-HOME RUN_DIR with CONVERGED review/codex artifacts and the canonical mid-run state.json (mkfixture `clean` shape). RUN_DIR and the repo are SIBLINGS under harness-runs/ so the Stop hook's `harness-runs/*/state.json` glob does not pick up repo files.
- FORWARD chain (4 steps, each runs the REAL executable): step1 hook emits set-flag (pre-flag) + ESCALATION (rebirth_pending) steers over OVER_WATER; step2 both `--mode checkpoint` AND `--mode state-lint` clean on the resumable state (tip==drive/<runId>); step3 scriptable handoff writes (checkpoint-complete.marker tmp+mv carrying proof JSON, then waiting="rebirth") form a consistent on-disk pair (marker.proof.tip==tip before waiting set); step4 fresh-process resume — rebind sessionId, reset rebirth_pending, validate+DELETE single-use marker, re-prove both modes, clear waiting — then asserts the successor's Stop hook BLOCKS (re-attributed, D7), marker consumed, state-lint clean. Pre-rebind the successor hook ALLOWS (control).
- CHAIN-BREAK NEGATIVES (proven red against a regressed chain): (a) detection severed via a bin/ COPY with hardHighWaterFraction=2.0 → no steer over OVER_WATER; (a') under-water → no steer; (b) proof severed: open inflight marker → checkpoint exit 1 inflight-open; (b') state-lint malformed (bad slice step / empty phaseList executing / corrupt JSON) → exit 1, AND the SAME bad state.json still passes `--mode checkpoint` (D8 — proving state-lint is the gate, two-mode proof is load-bearing); (c) resume severed: stale-tip marker fails tip-match validation (D17, no replay) after the tip moves; (c') un-rebound sessionId → successor hook ALLOWS (cannot resume) with a rebind control that flips it to block.
- HONEST SCOPE per D42: file header states the harness proves the EXECUTABLE + state-reconstruction half (real hook steer, real both-mode proof, scriptable handoff/resume, fresh-process re-attribution) and does NOT run the prompt-driven coordinator — those steps stay pinned by test_checkpoint_contract.py / test_rebirth_handshake.py. No overclaim of "runs the coordinator."
**Verification:** `pytest tests/contracts/test_rebirth_e2e.py -v` = 13 passed; full `pytest` = 446 passed. Negatives flip-proven (a regressed always-clean state-lint reds the negative). git status shows ONLY the owned test file.
**Reversibility:** easy (new test file only).
**Classification:** Mechanical.

## Slice 4.4 fix round (on 8b58f92) — doc-accuracy

- **P1 (MAJOR) state-lint phaseList grammar (drive-enforcement.md:205).** Doc said "ref-safe phase ids" (vague/overstated). Corrected to the SHIPPED grammar in bin/drive-conformance.sh: phaseList element `^[0-9]+[a-z]?$`, slice-id key + each dep `^[0-9]+[a-z]?\.[0-9]+$`; off-grammar → `phaselist-malformed`/`slice-routing-malformed`. Mechanical (transcribe real checker).
- **P2 (MINOR) safe-boundary definition (flow.md:172).** Doc equated safe boundary with only "no open inflight-*.marker". Tightened to the full drive.md contract (drive.md:258,:381): no open in-flight marker AND no partial multi-step git mutation AND current atomic step finished (REDESIGN marker→state span never split). Mechanical (transcribe real contract).

### 2026-06-12 -- D47: Slice 4.1 fix — make the resume half's executable pieces REAL + guard the rebirth_pending re-arm
**Stage:** implement (fix round on commit 4585a3f)
**Task:** lever2-rebirth — slice 4.1 executable E2E rebirth harness
**Question:** Codex P1-A (resume half test-authored, not executable) + P1-B (rebirth_pending re-arm not actually proven).
**Chosen:**
- P1-A stale-marker negative: replaced the python `tip == tip_now` self-compare with the REAL tip source — advance drive/<runId> with a real git commit (fast-forwarding phaseInt/1 so the run stays a resumable D18 live-phase shape), re-derive the live tip from the REAL `--mode checkpoint` proof output cross-checked against real `git rev-parse`, and fail the marker's bound proof.tip against that live tip.
- P1-A re-prove: already invoked the real `--mode checkpoint` + `--mode state-lint` (kept).
- P1-A docstring: rewrote the honest-scope block to state PRECISELY which pieces are REAL (Stop hook, --mode checkpoint, --mode state-lint, git ref/marker tip checks) vs PROSE-pinned (the resume act SEQUENCE, pinned by test_checkpoint_contract.py / test_rebirth_handshake.py). Dropped the overstated "each link runs the real script."
- P1-B re-arm guard: built step-4's fixture with rebirth_pending=True (the realistic handoff state) so the step-(2) `rebirth_pending=False` reset is load-bearing; added positive guard (v) — on-disk rebirth_pending is false AND the REAL Stop hook emits the PRE-FLAG set-flag steer (not escalation) on the successor's next over-water crossing. Added chain-break negative test_chainbreak_resume_severed_missing_rearm_refires: a resume that skips the reset leaves rebirth_pending true, so the real hook spuriously RE-FIRES the escalation steer; control (reset applied) emits set-flag. Proved removing the step-4 reset reds guard (v).
**Reversibility:** easy (test-only, owned file tests/contracts/test_rebirth_e2e.py)
**Classification:** Mechanical

### 2026-06-12 -- D48: Slice 4.1 fix round 2 — isolate the sessionId rebind; fix the step-2 docstring
**Stage:** implement (fix round 2 on commit f91cb9c)
**Task:** lever2-rebirth — slice 4.1 executable E2E rebirth harness
**Question:** Codex P1 (MAJOR, ~:365) — the pre-rebind "hook allows / can't resume" control passed for the WRONG reason: at that point waiting=="rebirth" (truthy), and drive-stop-hook.py `continue`s past ANY waiting run regardless of sessionId, so the allow was dominated by the pause, not by the missing rebind. P2 (MINOR, ~:29) — docstring claimed checkpoint+state-lint "BOTH fail closed" on a malformed state.json, but checkpoint never reads state.json (D8) and stays clean.
**Chosen:**
- P1: in step4, the pre-rebind control now CLEARS waiting (=None) before the hook call, leaving sessionId at SID_OUT — so the hook's sessionId-MATCH branch is the variable under test (not waiting). With waiting empty + sessionId unrebound, the successor (SID_IN) does NOT own the run -> hook does not keep it driving (allows). After the rebind (sessionId=SID_IN), with waiting still empty, the hook BLOCKS-to-continue. The rebind is now the SOLE difference between the pre/post hook calls. Empirically proved: commenting out `st["sessionId"]=SID_IN` reds the post-rebind block assertion (`None is not None`). The redundant later `waiting=None` write became an `assert waiting is None` (CONTINUE semantics already established).
- P2: rewrote the step-2 docstring to state the TWO-MODE GATE fails closed: an open in-flight marker reds checkpoint; a malformed state.json reds state-lint while checkpoint stays CLEAN (D8) — so it is state-lint that catches it; either way the both-clean gate fails closed. Not "both modes fail."
**Verification:** `pytest tests/contracts/test_rebirth_e2e.py -v` = 14 passed; full `pytest` = 447 passed. Rebind-removal red-proof confirmed. git diff shows ONLY the owned test file.
**Reversibility:** easy (test-only, owned file tests/contracts/test_rebirth_e2e.py)
**Classification:** Mechanical

## D — phase-4 integration fix: re-pin drive-plan rebirth contract to D46 reality

**Decision (Mechanical, completeness):** `tests/contracts/test_rebirth_handshake.py::test_drive_plan_invokes_rebirth_handshake_at_planning_boundary` (a phase-3 cross-slice contract pin) asserted `"--mode checkpoint" in drive-plan.md`. Phase-4 slice 4.3 (D46) deliberately removed the inline `--mode checkpoint` spelling from drive-plan.md's rebirth call-site — it now says "prove the checkpoint" and defers to drive.md's `§ I1` as "the authority for the proof modes" (drive-plan.md names NO proof mode itself). The phase-3 pin therefore broke on integration of the assembled phase-4 branch.

**Fix:** updated ONLY the test to match the integrated reality — replaced the `"--mode checkpoint"` assertion with `"prove the checkpoint"` + a new assertion that drive-plan.md references "the I1 routine is the authority for the proof modes". The pin stays load-bearing: it still requires the soft-check + Safe-boundary rebirth handler invocation, "after each design-review round", "before presenting Gate A", the `§ I1` reference, and the durable steps (prove → `checkpoint-complete.marker` → `waiting="rebirth"` → paste-ready `/drive <runId>`). Flip-proof (`test_drive_plan_rebirth_pin_flips_on_dropped_clause_copy`) still reds on a dropped clause, so the test still guards the drive-plan rebirth invocation.

**Verify:** `python3 -m pytest` = 447 passed; drive-conformance (171/0), rebirth-install-layout (17/0), drive-soft-check-doc (21/0), statusline-window ALL PASS.

### 2026-06-12 -- Phase-4 integration: edit bin/drive-stop-hook.py steer (root-cause exception)
**Stage:** phase-4 integration
**Question:** the hook escalation steer text names "--mode checkpoint" only, contradicting the both-modes proof contract (proof = checkpoint AND state-lint). D47 had deemed the hook advisory/byte-unchanged, but its literal steer singles out checkpoint.
**Chosen:** edit bin/drive-stop-hook.py (no phase-4 slice owns it) to make the steer reference the I1 both-modes proof, not checkpoint-only -- a flagged root-cause exception (the hook is the root cause of the remaining checkpoint-only surface). Supersedes D47's byte-unchanged assumption.
**Reasoning:** an internally-contradictory checkpoint-only surface in a shipped proof-mode steer is a real correctness/consistency bug. Classification: Mechanical (root-cause exception, surfaced at Gate B).
**Reversibility:** easy.

## D — phase-4 integration fix: kill the last checkpoint-only proof surface + close two E2E/AC7 gaps (2026-06-12)

Three integration findings on the assembled phase-4 branch (codex-review-phase4.md + review-phase4-1.md). All test/spec edits; one hook source edit as a flagged root-cause exception. Classification: Mechanical.

**P1-A (codex BLOCKING) — hook escalation steer was checkpoint-only.** `bin/drive-stop-hook.py` escalation steer named `bin/drive-conformance.sh --mode checkpoint` only, contradicting the both-modes proof contract (proof = `--mode checkpoint` AND `--mode state-lint`, both clean). FIX (root-cause exception): the steer now says "perform the rebirth checkpoint + handoff per the drive.md § I1 routine (proof = bin/drive-conformance.sh --mode checkpoint AND --mode state-lint, both clean)"; the `_rebirth_steer` docstring's escalation bullet updated to the same both-modes wording. Hook stays SIGNAL-ONLY + FAIL-OPEN (no behavior change, only steer text). Tests updated: `test_hook_escalation_steer_directs_the_i1_handshake` now asserts the steer names BOTH modes + `--mode checkpoint AND --mode state-lint` + the `I1 routine`, and is NOT checkpoint-only; `_SHARED_STEER_TOKENS` gained `--mode state-lint`; `test_hook_escalation_and_i1_share_the_handshake_tokens` now also asserts the I1 section names state-lint; `test_drive_stop_hook.py::test_already_pending_over_water_emits_escalation_steer` and `test_rebirth_e2e.py::test_step1_detect_emits_escalation_steer_when_pending` now assert both modes (not checkpoint-only). Tree-wide grep: every remaining `--mode checkpoint` in a production proof surface (drive.md I1/contract line 79+384, flow.md:176, hook) is now paired with `--mode state-lint`; drive-plan.md defers to I1 (D46); drive.md 272/275/280 describe each mode's individual behavior (not proof surfaces). No checkpoint-only proof surface remains.

**P1-B (codex MAJOR) — E2E harness didn't gate the handoff on BOTH modes.** Added `_perform_handoff(repo, rd)` to `test_rebirth_e2e.py`: it proves BOTH `--mode checkpoint` AND `--mode state-lint` and writes `checkpoint-complete.marker` + sets `waiting="rebirth"` ONLY when BOTH are clean (returns `(handed_off, proof)`). Refactored step3 (`test_step3_handoff_gates_on_both_modes_then_writes_marker_and_waiting`) and step4's outgoing-handoff simulation to use it, so the integrated both-modes gate is proven E2E. Added chain-break negative `test_chainbreak_handoff_state_lint_failure_blocks_marker_and_waiting`: a malformed routing state.json keeps checkpoint clean (D8) but reds state-lint, so `_perform_handoff` refuses — NO marker, `waiting` never set to "rebirth" — proving state-lint genuinely gates the handoff in the integrated chain.

**P1-C (Claude MAJOR) — AC7 cross-file /goal consistency unpinned.** Added `test_goal_rebirth_pause_clause_consistent_across_drive_and_plan` + flip-proof `test_goal_rebirth_pause_pin_reds_on_one_sided_edit_copy` to `test_rebirth_handshake.py`. The pin asserts the leg-2 `/goal` rebirth-pause clause (`paused at a rebirth handoff (waiting="rebirth") awaiting my paste of the resume line`) appears with its expected per-file count — drive.md ×2 (Gate A + Gate B legs), drive-plan.md ×1 — so a one-sided edit to EITHER file (including dropping just one of drive.md's two) reds. Flip-proof exercises both sides (drive-plan wholesale removal; drive.md single-occurrence removal).

**Verify:** `python3 -m pytest` = 450 passed; drive-conformance 171/0; rebirth-install-layout 17/0; drive-soft-check-doc 21/0; statusline-window ALL PASS.
**Reversibility:** easy (one hook steer-text edit + test/pin edits).

### 2026-06-12 -- HARDEN phase4 (fix round) — codex-harden-4 P1×3 + P2

**P1-A (codex: state-lint never validated `waiting`) — bin/drive-conformance.sh.** Both resume and the Stop hook BRANCH on `state.waiting` (`rebirth`→continue; any truthy→pause), but state-lint validated phaseList/slices/verify/ship and NOT `waiting` — a malformed `waiting` passed clean and could misroute resume. Added a per-field guard: `waiting` must be null OR a string matching `^(gateA|gateB|rebirth|stop:.+|ask:.+)$` (the canonical grammar from drive.md I1 / the pause routine); otherwise a named `waiting-malformed` violation (exit 1). Added 5 fixtures (mk_state_lint: `waiting_bad_type` non-string, `waiting_bad_string` off-grammar, `waiting_rebirth_clean`, `waiting_stop_clean`, `waiting_null_clean`) + test cases. Flip-proofed against HEAD: the two malformed cases pass clean pre-fix (no guard) and red post-fix; valid shapes (rebirth/stop:/null) stay clean both ways (no over-reject). The base `clean` fixture omits `waiting` (absent ≡ null) so it stays green. Doc note for followups: the new `waiting-malformed` violation name should be added to the drive-enforcement.md violation list (docs owned by another slice).

**P1-B (codex: E2E never exercised the `waiting=="rebirth"` continue branch) — tests/contracts/test_rebirth_e2e.py.** The round-2 rebind-isolation control in `test_step4` CLEARS `waiting` before the simulated resume, so the actual `waiting=="rebirth"`→CONTINUE branch (the resume-as-continue the feature is about) was never exercised. Added `test_step4b_waiting_rebirth_is_a_continue_not_a_human_pause`: keeps `waiting=="rebirth"` through the handoff and asserts (a) the OUTGOING session's REAL Stop hook ALLOWS the turn to END *because* `waiting` is truthy (the handoff stop), and (b) the CONTINUE semantics — a fresh successor rebinds (D7), RE-PROVES BOTH modes clean while `waiting` is STILL "rebirth" (resumability needs no human answer; state-lint must accept "rebirth" — exercises P1-A's guard positively), then clears `waiting=null` in the re-proven CONTINUE branch, after which the hook blocks-to-continue (auto-resume). Kept the rebind-isolation control (waiting cleared) distinct. Flip-proofed: breaking the hook's waiting-skip reds the test.

**P1-C (codex: install-test masked the symlink case) — test/rebirth-install-layout.test.sh.** Section 4 pinned only the SOURCE-TREE BASH_SOURCE resolution (json sibling resolves), masking that the INSTALLED statusline is a symlink at ~/.claude/statusline.sh — and bash sets BASH_SOURCE[0] to the INVOCATION (symlink) path, not the resolved target, so dirname=~/.claude where rebirth-thresholds.json is NOT a sibling → the install falls to the inline `case`. Verified empirically (symlinked script → dirname=symlink dir). Rewrote section 4 to assert BOTH truths honestly: (4a) source-tree resolves to the bin/ sibling json; (4b) running statusline THROUGH a real symlink with no json sibling renders the correct window via the inline fallback (Opus 4.8 → 90%, proving the inline 1M window, not the 200k default, carried it), and the would-be sibling is asserted ABSENT; (4c) AC6 anti-drift: inline Opus window == json Opus window so the fallback matches. Also corrected the now-stale section-5 comment/label ("sibling json resolves" → "deploy-by-reference, not copied") and the header.

**P2 (codex: AC7 pin prose miscount) — tests/contracts/test_rebirth_handshake.py.** The AC7 cross-file pin's prose claimed drive.md's two clause occurrences were "Gate A + Gate B re-arm". The real locations: drive.md ×2 = the rebirth-handoff successor re-arm goal (L491) + the Stage-0 leg-1 goal (L750); drive-plan.md ×1 = the Gate-A→leg-2 goal (L108). Counts (2/1) were already correct; only the which-leg prose was wrong — corrected the docstring, assertion messages, and section header. No assertion behavior changed.

**Kept (per harden instruction):** the uncommitted docstring edit in test_rebirth_handshake.py (`test_resume_rebirth_continue_is_fail_closed_re_proven`: "via BOTH `--mode checkpoint` AND `--mode state-lint`") — included in this commit.

**Verify:** `python3 -m pytest` = 451 passed (was 450; +1 e2e); drive-conformance 181/0; rebirth-install-layout 20/0; drive-soft-check-doc 21/0; statusline-window ALL PASS.

## Run harden-20260612-210528 (2026-06-13) — end-of-flow aggregate FINALIZE stage (Stage 4c) + narrowed per-phase harden

# Decisions — add an end-of-flow aggregate hardening stage to /drive

## D1 — Premise (corrected; User-Challenge, clarified twice by user)
The feature is a CHANGE TO THE /drive SKILL: every drive run, on whatever PROJECT it drives,
ends with a final aggregate hardening pass over that driven project. NOT hardening the
autodrive repo's own scripts (that was a misread, twice). Implementation lands in this repo's
drive specs + tests; the capability runs on the driven project.

## D2 — End-stage role: de-slop moves to the END (user choice at the design fork)
Per-phase HARDEN (drive-harden.md) narrows to CORRECTNESS ONLY (lens 2 add-tests + lens 3
fix-bugs). Lens 1 (de-slop) is REMOVED from per-phase harden and done ONCE at the end, in a
new final aggregate stage that ALSO does a whole-run bug/test/TODO sweep over the full run
diff. Matches the canonical "dedicated de-slop pass when correctness dominated" rule + the
user's "de-slop at the end."

## D3 — Edit scope of the final stage (Taste; coordinator call): run-diff-focused, aggregate-aware
The final stage READS the whole driven codebase for aggregate context but EDITS only the run's
diff (baseRef..featureBranch) + a flagged-P1's true root cause just outside it (same scope-creep
HARD GATE as drive-harden). /drive builds a feature; it must not rewrite untouched user code.
"Look at the entire codebase in aggregate" = read-context, not edit-everything.

## D4 — Architectural findings → TODO in the DRIVEN project (Mechanical)
Major architectural problems the final stage finds are appended to a TODO in the driven
project's tree (not fixed in-run), surfaced at Gate B.

## D7 — Final-stage command name = `drive-finalize` (`/drive-finalize`) (Taste; Phase 1 design)
Resolves design.md Open Question 1 (separate command, name fixed). The stage LEADS with de-slop
but also runs the aggregate logic-bug + missing-test sweep and routes architectural findings to a
TODO — `drive-deslop` undersells that; `drive-finalize` names it by its pipeline ROLE (the final
aggregate quality pass before Verify/Ship). The shared dual-voice 3-lens body is re-stated inline
(not factored to a common include — no such mechanism exists; factoring would be a Phase-1 refactor
beyond the narrow), mirroring how drive-harden.md already restates drive-review.md's mechanics.

## D8 — Ship-gate scope token = `finalize`; artifacts review-finalize-N.md + codex-review-finalize.md (Mechanical)
`finalize` is disjoint from `phase<P>`/`phasedesign<P>`, so the existing `--mode ship`
`review-phase*` glob never matches it — Phase 2 adds it as a SEPARATE explicit candidate-R source.
Reuses drive-review.md's `review-<scope>-N.md` / `codex-review-<scope>.md` / `codex-raw-<scope>.log`
naming verbatim so the conformance helpers (highest_review_file/verdict_converged/reviewed_sha_of/
codex_present) work on it UNMODIFIED.

## D9 — Finalize fix-round cap = FINALIZE_CAP = 3; counter `state.finalizeRound` (Mechanical)
Mirrors HARDEN_CAP=3 (fix rounds only; the confirming clean audit is free). Run-singleton stage →
a single top-level state field (no per-phase map). Each `review-finalize-N.md` carries an
`## AppliedEdits: yes|no` marker so the counter is artifact-derivable like harden's. Phase 2 wires
the state field + run-graph node.

## D10 — architectural findings: durable $RUN_DIR/finalize-todo.md, promoted at ship (REVISED, phasedesign1 r1)
finalize APPENDS architectural findings to $RUN_DIR/finalize-todo.md (durable, worktree-reachable);
the SHIP stage promotes it into the driven project's repo-root TODO.md within the single ledger
commit (SHIP_LEDGER_ALLOWLIST extended to include TODO.md) and surfaces it at Gate B from the
$RUN_DIR copy. finalize NEVER writes/commits a worktree TODO.md (the old "working-tree note" design
was broken: ship runs in a separate wt/ship worktree and can't see an uncommitted wt/finalize note).


## D11 — Placement (Stage 4c, after all phases hardened, before Verify) is fixed by D6 (Taste)
Phase 1 encodes only the stage's self-contained contract (scope, artifact, cap, returns) in the
same shape drive-harden.md uses, so Phase 2 can drop it into the loop. The actual wiring (new Stage
4c, the "all phases hardened" precondition, Verify-reads-final-tree) is Phase 2.

## D12 — Fix slice-1.2 codex P2 (reviewed-sha replace-in-place) before converging (Taste)
codex flagged a load-bearing ambiguity: drive-finalize.md's "re-emit reviewed-sha" could be read as
APPEND, but reviewed_sha_of() reads the FIRST match → ship would bind the stale pre-fix sha,
defeating the omission-proofing. Chose to fix (not log-and-defer) since it's the feature's spine.

## D13 — per-slice re-review subsumed by phase re-review for the phase-scoped handoff fix (Taste)
The deferred-slop handoff is a CROSS-SLICE property only verifiable where both files coexist (the
phase integration). A per-slice dual-voice review can't see it (and codex re-raises a slice-isolation
false positive). So for these phase-finding reroutes (phase1 r1 P1 wiring, r2 P1 orphan-path), the
authoritative dual-voice gate is the phase re-review; per-slice fixes are mechanically verified
(only-its-file + waiver). Slice reviewCount unchanged for these fix rounds.

## D14 — finalize de-slop is AUDIT-DRIVEN; deferred-slop notes are a SEED, not a fix queue (phase1 r3, codex)
followups.md is append-only; treating its "## slop (deferred to finalize)" section as a standing
fix set never converges (applied items persist). Refinement: finalize convergence is keyed on the
round's re-audit of the run-diff CODE (an already-applied slop edit won't reappear); the deferred-slop
notes SEED the first audit (best-effort recall of harden's spots) but are not the convergence signal
and need no drain. General lesson: an append-only ledger used as a work queue needs a drain/done-marker
or an idempotent audit-driven convergence; otherwise it loops.

## D13-REVERTED — per-slice review IS required each fix round (git-truth gate)
D13 (subsume per-slice review into phase review) is WRONG: bin/drive-conformance.sh --mode audit
+ the merge gate require EVERY merged slice to have a counting dual-voice review whose reviewed-sha
== the slice's CURRENT tip. Skipping it flags sha-mismatch and blocks assembly. So each fix round
gets its own per-slice dual-voice review (reviewed-sha bound to the new tip), THEN the phase review
verifies the cross-slice handoff. The per-slice review is scoped to the slice's OWN change soundness
(codex prompted to not re-raise the cross-file slice-isolation false positive).

## D15 — `(finalize)` classifier case is CHECKPOINT-ONLY, not state-lint (Mechanical; Phase 2 design)
The real `case "$scope"` over `review-*.md` lives ONLY in bin/drive-conformance.sh `--mode checkpoint`
(~L610). `--mode state-lint` reads state.json and has NO review-scope classifier (it validates routing
fields). Phase-1 §Interfaces 3 / the prompt said "checkpoint/state-lint classifier" — imprecise; real
code wins. The phantom-slice `(finalize)` arm goes in checkpoint mode; state-lint's only finalize edit
is adding `finalize` to the stage enum.

## D16 — `finalizeRound` is a BARE INTEGER counter, not a per-phase map (Mechanical; Phase 2 design)
finalize is run-singleton, so `counters.finalizeRound` is `$frj` (an int), unlike the per-phase
`redesigns`/`hardenRound`/`phaseReviewRound` maps. Matches `state.finalizeRound`'s shape (D9) and the
resume `max(state, int)` repair.

## D17 — ship's finalize R REPLACES the phase Rs as tip-binding; phase reviews become a precondition (Taste; Phase 2 design)
Two roles split: the finalize R is the ONLY review whose reviewed-sha == post-finalize tip (the
tip-binding (a)(b)(c) test runs on it). The phase reviews can no longer tip-bind (finalize commits
moved the tip past them) but their EXISTENCE is still required (`no-phase-review` precondition),
preserving "every shipped phase had a counting integration review." Keep both — dropping the
precondition would let a finalize-only artifact ship a phase that never reviewed.

## D18 — `stage = finalize` is a new pipeline stage value (Mechanical; Phase 2 design)
Added to drive.md's flow AND state-lint's stage enum (the cross-slice contract: Slice 2.1 uses it,
Slice 2.2 validates it). Resume routes finalize-vs-verify by the finalize ARTIFACT (CONVERGED +
reviewed-sha == tip), not by `state.stage` (artifact-derived, per the run's git-truth discipline).

## D19 — OPERATING.md is NOT edited by Phase 2 (Taste; Phase 2 design)
The de-slop-at-end principle is already canonical in OPERATING.md. The finalize MECHANISM belongs in
the project CLAUDE.md invariant (Phase 2 D2/AC30), not a duplicate global rule (Principle 2/4).

## D20 — Phase-2 design fixes from phasedesign2 r1 (2 P1 + 2 P2)
(Claude P1) A1 now changes BOTH drive.md:920 (operative HARDENED-handler transition) AND :925
(restatement) to stage=finalize — else finalize never dispatches in the single-session happy path.
(Codex P1) the ship phase-review precondition keys off the COUNTING candidate_R (post
verdict/sha/codex checks), NOT seen_phase presence — a stale/FINDINGS phase artifact can't forge it.
(Codex P2) finalize ship candidate-R uses the existing (a)(b)(c) ancestor+≤1-commit+allowlist rule,
NOT strict reviewed-sha==tip (tolerates ship's later ledger commit); the strict == is only the
resume-time routing check (pre-ledger-commit). (Codex P2) finalizeRound reconstruction fails closed
(unparseable-finalize) on a review-finalize-N.md missing AppliedEdits, mirroring unparseable-harden.

## D21 — add slice 2.5 to update the 4 reddened existing conformance tests (Mechanical; discovered at implement)
Phase 2's conformance.sh change (slice 2.2) reds 4 existing test/drive-conformance.test.sh cases that
pin the OLD ship/counters behavior (AC4.i, AC4b, AC5b, CK1) — the expected "gate-tightening reds the
allow-tests" signal. test/drive-conformance.test.sh wasn't owned by a Phase-2 slice (test-ownership put
it in Phase 1), but Phase-2 integration requires a green suite, so the behavior change must carry its
test update. NEW slice 2.5 owns test/drive-conformance.test.sh and updates those 4 cases to the new
contract (finalize terminal R; no-phase-review keyed on counting; 6-key counters incl finalizeRound).
NEW finalize-specific coverage (checkpoint finalize fixture, unparseable-finalize, full pipeline
contract) stays in Phase 3. 2.5 is file-disjoint from 2.1-2.4 (deps:none), works against the design
contract.

## D22 — add slice 2.6 to update test_rebirth_handshake.py for the new finalize stage (Mechanical; discovered at phase-2 integration)
Phase 2's new `finalize` stage (slice 2.1 added it to drive.md's leg-condition selector) reds 2 existing
tests in tests/contracts/test_rebirth_handshake.py that hardcode the 5-stage enum (_STAGE_ENUM,
_EXECUTE_STAGES). finalize is a real execute-leg stage, so the selector add is correct and the test
constants are stale → add `finalize` (execute-leg) to both. NEW slice 2.6 owns test_rebirth_handshake.py
(file-disjoint, deps:none). Same "gate-add reds the contract test, update it" pattern as 2.5.

## D23 — add slice 2.7: the ship-contract change reds ship-fixtures in 2 more test files (discovered at phase-2 integration)
Phase 2's new ship contract (finalize artifact = terminal candidate-R) reds 5 ship-fixture cases across
test/drive-merge-gate.test.sh (3: ship-silent-when-reviewed, --git-dir ship, push --mirror) and
test/drive-enforcement-e2e.test.sh (2: ship silent allow after ledger-only commit; fail-mode expected
ship exit 2 — now short-circuits to no-review like AC5b). These are EXPECTED behavior-change reds (the
omission-proofing now requires a finalize artifact; the fixtures seed only phase reviews). The
enforcement behavior is CORRECT. Slice 2.5 only covered drive-conformance.test.sh; slice 2.7 owns the
2 remaining bash test files and updates their ship fixtures to seed a CONVERGED finalize artifact
(reviewed-sha bound so R..tip = the single ledger commit), matching the new contract. File-disjoint, deps:none.

## D24 — phase-2 integration P1: merge-gate ship-deny remediation must point at /drive-finalize (design gap)
codex phase-2 review: bin/drive-merge-gate.sh:1090's ship-deny message names `/drive-review phase <P>`,
but the new ship contract requires the finalize artifact — following it leaves ship blocked. bin/drive-merge-gate.sh
was never in Phase 2's file set (design gap). Fix: NEW slice 2.8 updates the merge-gate ship-deny remediation to
`/drive-finalize` (matching conformance/drive-ship); reopen 2.7 to update the ship-deny message assertions in
drive-merge-gate.test.sh + drive-enforcement-e2e.test.sh; reopen 2.1 for the P2 (drive.md Stage-5 summary 3-file
allowlist incl TODO.md). New canonical ship-deny remediation message defined in the slice prompts.

## D25 — phase-2 P1: finalize-CONVERGED check must be TOLERANT in resume + ship precondition (codex r2)
/drive-ship commits the ledger BEFORE suite-red STOP and Gate B, so a resume after those points has
tip = ledger commit (one past the finalize reviewed-sha). drive.md A2 resume routing + drive-ship.md C1
precondition used strict reviewed-sha==tip ("resume is pre-ledger") — false for a post-ledger resume →
false-stop/misroute back to finalize. Fix (reopen 2.1 drive.md + 2.3 drive-ship.md): the finalize-CONVERGED
determination uses the TOLERANT test (==tip OR ancestor with R..tip ⊆ 3-file allowlist ≤1 commit), the same
criterion the --mode ship gate uses. This is the root reviewed-sha-tolerance lesson applied to ALL finalize-
CONVERGED surfaces, not just the ship conformance gate.

## D26 — phase-2 P1: drive.md resume finalize-CONVERGED must also require the codex sibling (codex r3)
The 3 finalize-CONVERGED surfaces must be IDENTICAL. drive.md resume routing had the tolerant sha test but
omitted the non-empty codex-review-finalize.md requirement that conformance.sh ship gate + drive-ship.md
precondition both have → a finalize missing its codex sibling could resume to verify while ship rejects it.
Fix (reopen 2.1): add "AND a non-empty codex-review-finalize.md exists" to drive.md's resume finalize-CONVERGED check.

## D27 — phase-2 harden: codex/Claude flagged 3 finalize test gaps; CONFIRMED Phase-3 scope (harden triage)
Phase-2 harden audit (Claude 0 P1 / codex 3 P1) surfaced the SAME 3 finalize-specific test gaps,
all D21-deferred to Phase 3 ("Tests"): (AC24) the b-i `no-phase-review` precondition with a valid
finalize artifact but only a non-counting phase review → assert no-phase-review rc1; (AC25) checkpoint
`(finalize)` arm — positive `AppliedEdits: yes` → finalizeRound==1 + no phantom-slice, AND a missing
`AppliedEdits:` line → unparseable-finalize rc1; (AC23 negative) ship BLOCKS no-review when the finalize
artifact is absent/FINDINGS with phase reviews present. Per the harden HARD GATE these are NOT written
in Phase-2 harden (forbidden to reach into the unbuilt Phase 3). The Phase-3 detailed design MUST cover
these exact decisive cases — every updated Phase-2 fixture seeds BOTH a phase review AND a finalize
artifact, so the b-i / unparseable / no-review branches are currently untaken by any test.

## D28 — phase-2 harden-regress: reconcile design-phase2.md to D25/D26 (tolerant finalize-tip); codex BLOCKING was doc-staleness
The harden-regress codex pass raised BLOCKING: drive.md:113 + drive-ship.md:17 use the TOLERANT
finalize-CONVERGED test (R ancestor of tip, R..tip ⊆ 3-file allowlist ≤1 commit) while design-phase2.md
AC21/C1/D18/L135 still asserted strict `reviewed-sha == tip` at resume + ship-start (tolerant reserved
for --mode ship). Investigated against git truth: the CODE is correct per D25/D26 (decided at phase-2
implement, codex r2/r3) AND the CONVERGED round-4 conformance review (review-phase2-4.md: "THREE
finalize-CONVERGED surfaces now IDENTICAL ... tolerant"); drive-ship.md commits the ledger BEFORE its
suite-red STOP and Gate B, so a post-ledger resume has tip = R+1 and strict `==` would false-stop —
the tolerant test is provably correct. The acceptance-criteria DOC (AC21/C1/D18/L135) was stale: it
predates D25/D26 and was never reconciled. Per OPERATING ("update the doc when in-session decisions
diverge"), reconciled all four spec regions to the tolerant test this harden round. NO code change (the
code already implements the converged contract). The codex BLOCKING was a true divergence detection
that trusted the stale spec over the later-authoritative decisions + converged code. Doc-only edit —
no behavior change, no regression guard needed, hardenRound unchanged.

## D-P3-1 — EXTEND test/drive-conformance.test.sh + mkfixture.sh for the bash finalize cases (Mechanical; Phase 3 design)
The file IS the conformance behavioral suite (runner harness, seed_finalize, all mk_* fixtures,
section structure); a new bash test file would duplicate the harness (anti-DRY). Its Phase-2
owner (slice 2.5) is already converged, so a single Phase-3 slice may own it without a Phase-3
write-race. New finalize cases (AC32-AC38) extend it; two new mk_checkpoint variants + one
mk_state_lint variant extend mkfixture.sh.

## D-P3-2 — finalize spec-contract pins go in a NEW tests/contracts/test_drive_finalize_contract.py (Taste; Phase 3 design)
Pin `/drive-finalize` referenced in drive.md + the harden lens-narrowing + the finalize pipeline
contract (Stage 4c placement, artifact contract, ship precondition, CLAUDE.md invariant, cross-file
token consistency) in a dedicated new file — NOT by editing the generic test_drive_command_refs.py
(its `expected` set is a sanity floor; overloading it muddies a generic test) and NOT in the
checkpoint-scoped test_checkpoint_contract.py. Mirrors the existing one-contract-per-feature pattern.
Keeps Phase-3 ownership clean (test_drive_command_refs.py is owned by an earlier phase).

## D-P3-3 — assert the SPECIFIC violation reason, not just rc 1 (Mechanical; Phase 3 design)
The D27 mandate is about WHICH guard fires: AC23neg → `no-review` (b-ii empties candidate_R after
b-i passed), AC24 → `no-phase-review` (b-i fires first), AC25b → `unparseable-finalize`. An rc-only
assertion passes green-for-the-wrong-reason. Each negative case asserts its reason token.

## D-P3-4 — AC34/AC35 (AC24) build the fixture INLINE from mk_ship clean (Mechanical; Phase 3 design)
Flip review-phase1 to FINDINGS / delete its codex; seed_finalize at HEAD^. mk_ship clean already
builds the repo + ledger commit + tip-binding R; two inline edits suffice — no new mk_* builder for
two call sites.

## D-P3-5 — Slice 3.1 owns BOTH test/drive-conformance.test.sh and test/fixtures/mkfixture.sh (Mechanical; Phase 3 design)
The new cases call the new fixture builders — one write-unit. Splitting across two parallel slices
would race on the fixture call-site contract. Within Phase 3 these files are owned by exactly one
slice (3.2 owns only the new Python file) → disjoint.

## D-P3-6 — assert "finalizeRound":1 as a SUBSTRING, not full-JSON-equality, for AC36 (Mechanical; Phase 3 design)
The other counters are {}/0 by the minimal finalize_round fixture; pinning the whole counters object
would be brittle to base shape. Pin the one value under test (right-size at design).

## D-P3-7 — Phase 3 P1 design-review fixes (Mechanical; grounded in the real worktree)
Resolved the three dual-voice P1s by grounding each test re-spec on a worktree grep/read:
- **P1#1 (AC44 token consistency unrealizable).** Greps showed the tokens are NOT uniform across
  files: `inflight-finalize.marker` lives ONLY in drive.md+CLAUDE.md (not drive-finalize.md/
  conformance.sh); `## AppliedEdits: yes` is NOT in CLAUDE.md. Re-specified AC44 / test 9 to
  PER-FILE expectation sets (matched-file set EQUALS required set per token) so the test passes
  on correct code and reds only on a real drop/spelling-drift. Grounded on
  `grep -rln '<token>' .claude/commands/ bin/ CLAUDE.md`.
- **P1#2 (Stage-4c pins vacuous).** `/drive-finalize` and `stage = finalize` also appear in
  resume/recovery prose (drive.md:128/133/399-402), so a loose "appears somewhere" pin passed
  vacuously. Re-specified tests 2/3 + AC39/AC40 to SECTION-BOUND on real anchors: the
  `### Stage 4c — Finalize` header (drive.md:981), the dispatch `then invoke /drive-finalize`
  (drive.md:1011), and the Execute→Finalize transition `all phases … hardened → stage = finalize`
  (drive.md:979) — deleting the real wiring now reds despite the token surviving elsewhere.
- **P1#3 (AC25a "no slice violation" vacuous).** Confirmed checkpoint mode does NOT validate
  scopes against slice branches (conformance.sh:656 default arm); a misclassified `finalize`
  would silently land in `reviewCount`, raising no violation. Re-specified AC25a/AC36 + the
  helper + edge-notes to assert the POSITIVE: `counters.reviewCount` has NO `finalize` key AND
  `counters.finalizeRound == 1`. Grounded on the real `counters` JSON shape
  (conformance.sh:787) and the `(finalize)` case arm (conformance.sh:644).
Slice ownership UNCHANGED and disjoint (3.1 owns test/drive-conformance.test.sh +
test/fixtures/mkfixture.sh; 3.2 owns tests/contracts/test_drive_finalize_contract.py).

## AC44 P1 (both voices) — finalize-token consistency re-specced from exact-set-equality to per-token required-presence (required carriers MUST contain the token, extras tolerated); fixed `## AppliedEdits: yes` set to {drive.md, drive-finalize.md, bin/drive-conformance.sh} (drive-harden.md has `## AppliedEdits: pending` only) and made `review-finalize` require all six carriers incl. bin/drive-merge-gate.sh; grounded by grep, both AC44 locations (interfaces ~224 + AC list ~392) agree.

- [slice 3.2 / phase-3 integration] Flagged scope-widening to CLAUDE.md:178 — changed `harden-<P>-N.md -- per-phase harden audit (3-lens) outputs` to `(2-lens)` to match the narrowed harden model (drive-harden.md "The two hardening lenses"; de-slop deferred to /drive-finalize). True root cause of the AC43 P1 (vacuous test masked a real production-doc drift introduced in phase 1/2). Classification: Mechanical — phase-1/2 consistency drift exposed at phase-3 integration. (Authorized 1-line out-of-ownership edit per the slice prompt.)

## Slice 3.2 round 2 — tightened vacuous token-presence pins (Mechanical, P-completeness/P-explicit)
Phase-integration review found 2 P1 vacuous pins in test_drive_finalize_contract.py; fixed both + swept for the same defect class.
- AC42 `test_finalize_emits_shipgate_artifact_contract`: section-bound the full-suite-revert-on-red guard to `## Step 4 — Regression guard & converge` (was file-wide `full...suite`+`REVERT`, satisfied by Step-3/lens-1 prose at L77/316/353). Now reds if the Step-4 guard (FULL suite as regression guard + reddened→REVERT + "do not reconcile by editing the test") is deleted/weakened.
- AC43 `test_ship_spec_finalize_precondition_and_promotion`: section-bound (a) the tolerant finalize precondition #3 to `## Preconditions` (review-finalize-N.md + ANCESTOR-of-tip + R..tip ≤1 commit + explicit tolerate; reds if weakened to strict ==tip) and (b) the Gate-B finalize-todo surfacing bullet to `## Build the PR` (finalize-todo.md architectural follow-ups from durable $RUN_DIR copy before Gate B; reds if bullet deleted). Was `ancestor` anywhere + bare `"Gate B" in text`.
- SWEEP: found 1 additional weak pin — `test_finalize_scope_creep_gate_and_arch_todo` three-lenses check used norm-wide `de-slop`/`missing test`/`logic bug` (de-slop appears x14 file-wide); section-bound to `## The three lenses` with the 3 numbered lens definitions (reds if section deleted/lens dropped). Other norm-wide checks left as-is: they pin distinctive literal/multi-word tokens (review-finalize-N.md, baseRef..featureBranch, FINALIZE_CAP=3, SHIP_LEDGER_ALLOWLIST), not generic words — not the loose-token defect.
Each tightened assertion verified by mutation: deleting/weakening the real clause reds; correct code passes. Full tests/contracts/ green.

## slice 3.2 (loose-pin convergent fix)
- Section-bounded every clause-pinning assertion in test_drive_finalize_contract.py to its
  owning `##`/`###` header so a token recurring in OTHER sections cannot satisfy it. Fixed
  the 4 codex-flagged loose pins (harden lens-defs, finalize Step-1 artifact schema,
  finalize Scope diff-clause, CLAUDE.md run-state inventory) PLUS tightened the reviewed-sha
  binding (dropped the loose `featureBranch tip` prose OR-branch; pin only `rev-parse
  featureBranch`) and moved FINALIZE_CAP/finalizeRound presence into the `Loop counter`
  section slice. (P1: completeness.)
- CLAUDE.md run-state asserts the COLLAPSED `review-<scope>-N.md ... finalize` family form
  (run-state never carries a literal `review-finalize-N.md`; that literal lives only in the
  FINALIZE invariant, pinned separately by part (ii)).
- Self-mutation-tested EVERY assertion (in-memory section/line deletion + monkeypatched
  Path.read_text): every targeted clause-deletion reds its owning test; all 9 tests pass on
  the real files. No over-tightening — pins bind a header + distinctive clause, not line
  numbers or incidental wording.

## slice 3.2 (test-pin tightening) — 2026-06-13
- Fixed the 8 still-green clause-deletion mutations + 2 pre-existing loose pins (Scope
  diff-clause harness false-flag was harness-only; CLAUDE harden de-slop deferral was a
  real file-wide-norm vacuity, tightened to the HARDEN bullet). Principle 1 (completeness):
  achieved full mutation parity (63 mutations, 0 still-green) rather than fixing only the
  named 8, per the methodology brief.
- Added a `_slice_between(start_re, stop_re, inclusive_stop)` helper to pin sub-blocks WITHIN
  an already-sliced section (Step-1 schema block + codex command block); it asserts BOTH
  markers exist so deleting either reds. Principle 5 (explicit-over-clever).
- D-3.2-harden-drift: Fixed harden-narrowing consistency drift in `.claude/commands/drive.md` step-6 (~951): removed "reduce AI slop" from the harden-pass description and reconciled the immediately-following veto clause; harden now reads "add missing tests, fix logic bugs (de-slop is DEFERRED to the aggregate /drive-finalize stage)", matching drive-harden.md:45 and CLAUDE.md. AC41 (`test_harden_narrowed_to_two_lenses`) extended to pin this third surface. Classification: Mechanical — phase-1 harden-narrowing consistency drift in drive.md exposed at phase-3, sibling to the CLAUDE.md:178 fix.

## D31 — phase-3 integration: reconcile README.md + docs/flow.md to the new pipeline (Taste, completeness)
codex phase-3 review found the repo's entrypoint user docs (README.md, docs/flow.md) still describe the
PRE-finalize/pre-narrowing pipeline (omit /drive-finalize; harden "reduce AI slop"). Task scope named
.claude/commands+bin+tests, NOT README/docs — but per Completeness + boil-lakes (in blast radius, <1 day)
a pipeline feature must not ship with entrypoint docs describing the old pipeline. DECISION: reconcile both
docs now as a flagged completeness edit committed on phaseInt/3 (coordinator-level, like the CLAUDE.md/
drive.md harden reconciliations). NO new contract-test pins for them (user prose, not a load-bearing contract
surface; pinning would re-trigger the prose-pin churn seen in slice 3.2). Surfaced at Gate B.

## D32 — phase-3 doc sweep: fix drive-enforcement.md; REJECT summary-abstraction + history-rewrite findings (right-size)
codex round-4 repo-wide drift sweep found 3 doc surfaces. DECISIONS: (1) FIX docs/drive-enforcement.md —
its ship-contract section still describes the pre-finalize gate (2-file allowlist, /drive-review remediation);
reconcile to finalize-keyed + 3-file allowlist + /drive-finalize remediation (active reference doc, completeness).
(2) REJECT the "routes findings to project TODO.md" summary finding — one-line summaries are accurate at their
abstraction (findings DO reach TODO via finalize-todo.md→ship promotion); precise mechanism is in the stage body;
spelling it everywhere violates explicit≠verbose. (3) REJECT the .harness/decisions.md D15 finding — it is a
dated append-only HISTORICAL entry; rewriting it falsifies the audit trail (supersession = later entries).
DECLARED: after drive-enforcement.md, the doc-completeness sweep is DONE — any further ancillary-doc nitpick
routes to followups.md (behavioral feature + normative specs + entrypoint docs are all consistent; diminishing
returns beyond task scope, which was .claude/commands + bin + tests).

## D33 — phase-3 converged; stale gate-code comment routed to FINALIZE de-slop (not phase-3 harden)
Phase-3 integration CONVERGED at 5b23141 (Claude 0 P1; codex 0 P1, 1 MINOR). The MINOR — bin/drive-conformance.sh:448
ship-case banner comment still states the pre-fix "EXISTS a counting phase/integration review" model (logic at
:484 is correct: finalize candidate-R + no-phase-review precondition) — is in PHASE-2's file, NOT phase-3's diff,
so phase-3 harden (scoped to the phase-3 diff) won't touch it. It IS in the whole-run diff, so it's a FINALIZE
de-slop target (the aggregate stage over baseRef..featureBranch). Will be fixed in finalize.

## D34 — reconcile onto main (#42 preserved); 2 codex resume findings dispositioned pre-existing-out-of-scope
Per user choice (rebase+reconcile+re-review now): merged featureBranch onto main (post-#42), rewired the
finalize stage's I1 boundaries to #42's hook-only model (dropped the re-introduced Coordinator soft-check
refs), re-reviewed. #42's soft-check removal fully preserved (only the historical note remains). Round-2 fix
made ship-resume idempotent (force-clean wt/ship; skip already-promoted ledger) + added the wt/finalize
resume-classifier rule. codex then surfaced 2 deeper resume findings (router has no ship/done route;
classifier can't distinguish wt/ship by branch) — VERIFIED both are PRE-EXISTING in main's pre-finalize
drive.md (not introduced here) and the feature's paths are SAFE (verify-passthrough + ship force-clean).
Routed to followups as a focused /drive-resume-router hardening task. Surfaced at Gate B.


<!-- ===== promoted from /drive run drive-retention-hygiene-20260622T073209 (2026-06-24T01:35:55Z) ===== -->
# Decisions — drive-retention-hygiene

D1 (Mechanical): Run-completion teardown at the drive-ship done transition + drive.md resume path, with REMOVE-BEFORE-MARK ordering and a new `completedAt` marker. Root-cause CORRECTION (v1 was wrong): leftover `wt/` are FULL checkouts (registered, or ad-hoc-unregistered) — NOT empty dirs git leaves. The real defect is the ship ORDERING race (`stage="done"` written before `wt/ship` is unregistered). Fix: in the OWNING repo, `git worktree remove --force` drive-owned worktrees + `git worktree prune`, delete dead dirs, write `completedAt`, then `stage="done"` LAST. Reuses #57's remove/prune logic; does not re-own branch pruning.

D2 (Taste): Retention policy + REPORT-MODE-DEFAULT + TWO-TIER authorization. KEEP all .md/.json/.jsonl history; sweep heavy codex-raw-*.log / codex-harden-*.log (Tier-L, NO git gate — needs only waiting==null + no-inflight + done/completedAt + age) and drive-owned DEAD wt/ (Tier-W, full git-truth gate). Tiers authorized INDEPENDENTLY so the dominant log-reclaim is not hostage to owning-repo resolution. Read-only classify+report is the DEFAULT; destructive sweep behind explicit `--apply`. Default N = 14 days. N AND report-mode-default are the load-bearing Gate-A Taste items.

D7 (Mechanical): persist `repoRoot` = `git rev-parse --show-toplevel` (driven repo) in state.json at fresh-run setup. The deterministic upstream source the GC anchors owning-repo resolution on (harness-runs is global; state.json had only bare branch names). Historical runs lack it → Tier-W SKIP (fail-safe); Tier-L unaffected. #57 boundary: shares worktree remove/prune MECHANICS only, NOT mergedness authority (#57 = gh-PR-state because squash-merge defeats ancestry; retention Tier-W = completedAt OR skip-biased ancestry backstop).

D3 (Mechanical): GC invoked best-effort at fresh-run setup — AFTER runId claim + state.json write, in a swallowed subshell (`… || true`), NEVER on the mkdir critical path. Per-run soft-fail, time-bounded, ALWAYS exits 0. Explicitly NOT a `set -euo pipefail` hard-fail gate like drive-conformance.sh. GC failure must never abort a new run.

D4 (Mechanical): use `trash`, never `rm` (OPERATING.md; /usr/bin/trash).

D5 (Taste/User-Challenge): codex /tmp scratch OUT of pipeline scope. Pipeline namespaces into $RUN_DIR and honors TMPDIR (not /tmp on this host). Optional TMPDIR=$RUN_DIR/tmp export around direct `codex exec`; /tmp backlog is a manual one-shot.

D6 (Taste): one-shot backfill falls out of the age-GC (run helper manually, report then --apply); no bespoke script. Today's residue is all either registered (skipped) or ad-hoc-named (skipped) — immediate reclaim is heavy CODEX LOGS + any drive-owned dead worktrees.

--- Safety contract (load-bearing; supersedes v1's stage-keyed model) ---
A run's worktree residue is sweepable ONLY if ALL hold; ANY failure/unverifiable ⇒ SKIP (fail-safe):
(1) state.waiting == null; (2) NO open inflight-*.marker; (3) owning driven repo resolvable AND drive/<runId> merged into that run's OWN baseRef by git ancestry IN THE OWNING REPO (same authority as ship/#57); (4) NO wt/ child still registered in ANY repo; (5) ideally a positive completedAt marker. stage=="done" is at most a cheap pre-filter, never authorization. W7 CLEANLINESS (codex r3): an existing unregistered drive-owned wt/ dir is removed ONLY if completedAt-tied (locus-1 wrote it after a clean teardown) OR provably clean (git status --porcelain empty, no unpushed) — mirrors #57's dirty guard; ancestry-of-branch never authorizes trashing a dirty dir. Owning repo resolved per-run from registered wt/.git gitdir / state.baseRef. Age = max(run-dir mtime, newest event-log timestamp), completedAt preferred.

--- Phasing ---
TWO phases on staged-risk: Phase 1 = read-only classifier + report + guard tests; Phase 2 = destructive --apply path + drive-ship remove-before-mark + drive.md resume ordering + best-effort GC-at-setup wiring. Phase 2 relies on Phase 1 (staged-risk: the destructive sweep is authorized solely by Phase 1's classifier — guards must be test-proven before any trash/git-worktree-remove rides on them).

--- Phase 1 detailed-design decisions (design-phase1.md) ---
DP1 (Mechanical): bin/drive-retention.sh CLI seams = --root / --now / --age-days / --json. Pure-function-over-inputs: injectable root + clock make it tempdir-testable without $HOME/wall-clock surgery; --json is the stable schema the contract test asserts on (not brittle prose).
DP2 (Mechanical): report-only is STRUCTURAL — no --apply, no `trash`, no `worktree remove` token in the Phase-1 file at all. Safest report-only = absence of destructive code, not a flag guarding it; enforced by a grep-for-deletion acceptance test. Phase 2 ADDS the destructive path.
DP3 (Mechanical): best-effort isolation — NOT set -e / NOT set -euo pipefail; ALWAYS exit 0; per-run failures become skip:<reason>. The ONLY non-zero is exit 2 on an unknown CLI flag (caller programming error at the CLI boundary, distinct from a runtime per-run failure). Satisfies D3 (GC must never abort a new run).
DP4 (Mechanical): closed skip-reason vocabulary, scoped to ONLY Phase-1-emittable reasons now that ancestry runs in Phase 1: {waiting, inflight-open, not-done, not-aged, unresolvable-repo, wt-registered, not-drive-owned, dirty, unpushed, unreadable, not-ancestor, ancestry-unprovable}. REPLACED v1 placeholder `no-completedAt-and-no-ancestry` with the real `not-ancestor` outcome; RETAINED `ancestry-unprovable` (now a real Phase-1 outcome: baseRef absent / git rc>1). AC14 asserts the EXACT set. Makes --json testable + report's "skipped-because" honest/greppable.
DP5 (Mechanical, CORRECTED round-2 — v1 deferral REVERSED): the live `git merge-base --is-ancestor drive/<runId> <baseRef>` ancestry probe runs IN PHASE 1 (it is READ-ONLY). Report mode is the SAFETY PREVIEW of Phase 2 --apply, so the read-only classifier must exercise EVERY authorizer apply acts on — deferring ancestry made the v1 report UNFAITHFUL (could not preview the non-completedAt Tier-W path). Mapping: repo resolvable AND baseRef present → rc0 ancestor (eligible if other gates pass) · rc1 not-ancestor (skip:not-ancestor unless completedAt) · rc>1 git error (skip:ancestry-unprovable, NEVER sweep on error). Phase split PRESERVED + about DESTRUCTION only: Phase 1 = COMPLETE read-only classifier+report (no --apply/trash/worktree-remove token); Phase 2 = destructive ACTIONS gated on this verdict + drive*.md wiring (repoRoot persistence D7, remove-before-mark, GC-at-setup). Phase 1 only READS state.repoRoot (null-tolerant). report == apply.
DP6 (Mechanical): owning-repo resolution order = state.repoRoot (existing dir) -> registered wt/<n>/.git gitdir -> UNRESOLVABLE. Anchors on the deterministic upstream source (D7); never infers from the firing run's cwd (cross-repo branch-collision hazard).
DP7 (Mechanical): `verify*` honored in the drive-owned wt/ grammar (verify / verify[0-9]*) though drive.md emits no wt/verify today — costs nothing, future-proofs, cannot over-match ad-hoc names. Full grammar: slice-id ^[0-9]+[a-z]?\.[0-9]+$ | phase<P> | design<P> | ship | verify* | finalize.
PHASE-1 SLICING: ONE slice (1.1) — bin/drive-retention.sh + tests/contracts/test_drive_retention.py. Tests ride with the code; no fan-out, no internal staged-risk (the classifier->destroy seam IS the Phase1->Phase2 split).
DP8 (Mechanical, round-3 — supersedes round-2; "recorded children" REMOVED): ONE rule for `completedAt`, NO per-child inventory. Phase 1 has no persisted per-child worktree inventory, so round-2's "satisfies W7 only for recorded children" was UNIMPLEMENTABLE. Redefine: locus 1 (Phase 2) removes EVERY drive-owned worktree of the run BEFORE writing completedAt (design.md §Approach locus 1), so a PARSEABLE completedAt attests a clean teardown of ALL the run's drive-owned worktrees — it REPLACES ancestry at W4 AND satisfies W7 cleanliness for ANY drive-owned child of that run (no recording needed), and is the preferred age anchor. MISSING or UNPARSEABLE/torn ⇒ authorizes NOTHING (never a positive signal): W4 falls through to ancestry (or skip:unresolvable-repo), W7 requires a provably-clean dir, age falls back to the union. Closes round-2 P1 "the children that run recorded is undefined/unimplementable" + the v1 contradiction (edge11 OR-clean vs edge12 unparseable-counts).
DP9 (Mechanical, round-3 — supersedes round-2; TWO-way → THREE-way, closes W5 fail-open): `wt_registered_anywhere` is THREE-WAY on PATH EQUALITY, not name match. Round-2's two-way (registered vs not-registered→W7) FAILED OPEN — a genuinely-registered LIVE worktree whose admin back-reference is transiently unreadable, if clean, fell to W7 and was reported eligible. THREE outcomes: (a) NO `wt/<name>/.git` pointer at all ⇒ definitively NOT registered ⇒ the ONLY fall-through to W7 (orphaned-dir/provably-clean); (b) pointer resolves AND admin `gitdir` back-reference equals THIS run's `wt/<name>/.git` (path equality) ⇒ registered ⇒ skip:wt-registered; (c) ANY other case — pointer exists but admin dir missing / back-reference unreadable / dangling / different path / any error ⇒ AMBIGUOUS, cannot prove unregistered ⇒ fail-safe skip:registration-unprovable, NEVER W7. New skip reason `registration-unprovable` added to the closed enum (DP4) + pinned in AC14/15. Stops name-collision misreporting, stops an orphaned old wt/phase1 hidden behind a newer live phase1, AND closes the unreadable-back-reference fail-open.
DP10 (Mechanical, round-3 — NEW): W-tier gate order is "first-failing-gate-wins" with the CHEAP PER-CHILD STRUCTURAL gates FIRST. Round-2 ordered W4 (repo/ancestry) before W5/W6, contradicting the ACs (an ad-hoc child in the common UNRESOLVABLE run stopped at W4 skip:unresolvable-repo before the W6 name check ⇒ never emitted skip:not-drive-owned). ONE authoritative order: (1) W6 drive-owned name (no repo) → skip:not-drive-owned; (2) W5 registration three-way path equality → skip:wt-registered / skip:registration-unprovable; (3) W1/W2/W3 run-level liveness+age → skip:waiting / skip:inflight-open / skip:not-aged; (4) W4 authorization (completedAt OR repo+ancestry) → skip:unresolvable-repo / skip:not-ancestor / skip:ancestry-unprovable; (5) W7 cleanliness of an existing no-pointer dir → skip:dirty / skip:unpushed / skip:unreadable. Per-child structural gates precede run-level authorization so the emitted reason matches what each AC promises. Tier-L keeps its OWN independent L1–L4 order (judged independently of Tier-W). Stated once in design-phase1.md "W-tier gate-order precedence"; every edge/AC/interface defers to it. Also: ancestry helper ALWAYS attempts the probe (no baseRef pre-check; rc>1 incl. baseRef absent ⇒ ancestry-unprovable ⇒ SKIP) — round-2 MINOR fixed.

--- Round-4 corrections (codex r3 BLOCKINGs — design.md W7 + age contracts tightened to close two fail-opens; classification Mechanical) ---
DP8 (REVISED round-4, supersedes round-3): `completedAt` = W4 RUN-level AUTHORIZATION ONLY — never a W7 cleanliness bypass, never an age override. Round-3 overshot: a parseable completedAt had (a) satisfied W7 for ANY drive-owned no-pointer child — a CLEANLINESS fail-open, since the marker only attests worktrees were GONE at marker-write time, not that a dir SEEN LATER (recreated/restored/interrupted-delete) is the same dir or still clean; and (b) OVERRIDDEN the age union — a CLOCK fail-open, an OLD completedAt marking a recently-touched run aged. FIX (both docs): (1) W4 (run-level authorization) = parseable completedAt OR (repo-resolvable AND baseRef present AND ancestry); completedAt REPLACES ancestry here, nothing else. (2) W7 (dir-level cleanliness, W7b) = `git -C <dir> status --porcelain` succeeds AND empty AND no unpushed — ALWAYS required for an EXISTING dir, REGARDLESS of completedAt; completedAt does NOT bypass it. Strictly safer, loses no legitimate reclaim (a clean leftover passes W7b anyway; a dirty/unpushed one must never be swept). (3) run_age_epoch = max(run-dir mtime, newest event-log ts, completedAt-if-parseable) — most recent ALWAYS wins; completedAt is one input to the max, never preferred/override. The ONLY eligible Tier-W outcome: drive-owned + no-pointer + live-quiet (waiting null, no inflight) + done + aged + W4-authorized (completedAt OR ancestry) + W7b provably-clean. Reflected across design.md (W7 ~44-61, Age ~152-158), design-phase1.md (ground-truth note, per-run reads, run_age_epoch + completedAt_authorizes interfaces, gate-order W7 step + eligible-outcome line, edges 4/11/12, AC7/AC10/AC12, DP8).
MINOR (round-4): --json `registered` field is THREE-VALUED (`true | false | "unprovable"`) to represent the three-way W5 faithfully (a `registration-unprovable` child could not be encoded by a boolean); all three encodings pinned in AC14.

--- Round-5 corrections (codex r4 BLOCKING + MAJOR; classification Mechanical/safety) ---
DP11 (Mechanical, round-5 — adds the Tier-W DONE gate; closes the codex r4 BLOCKING live-quiet fail-open): Tier-W had NO explicit DONE gate. The round-4 order (W6→W5→W1/W2/W3→W4→W7b) checked waiting/inflight/age/W4-auth/W7b-clean but never a positive done signal, while the doc claimed the sole eligible outcome includes "done" and design.md:41 defined W1-W4 as "L1,L2,plus age,plus W4" (omitting L3=done). Against the REAL /drive contract `waiting==null` is NORMAL while a run is still actively running (stage!="done", drive.md:258) and /drive has safe-boundary windows with no open inflight marker before completion — so a stranded/aged LIVE run with a drive-owned no-pointer CLEAN dir would have been marked eligible (its worktree swept). FIX (both docs): add the Wd DONE gate to Tier-W mirroring Tier-L's L3 — positive done signal = parseable completedAt OR state.stage=="done" — placed AFTER liveness (W1/W2) and BEFORE age (W3): no done signal ⇒ skip:not-done; the child NEVER reaches W3/W4/W7 or becomes eligible. state.stage=="done" satisfies Wd but is NOT on its own the W4 worktree authorization (W4 still needs completedAt OR proven ancestry) — Wd and W4 are distinct. `not-done` (already in the closed enum for Tier-L) now also applies to Tier-W; the torn/missing-state.json edge is now CONSISTENT (no done signal ⇒ skip:not-done on both tiers). The ONLY eligible Tier-W outcome now requires: drive-owned name + NO registration pointer + waiting-null + no-inflight + DONE (completedAt OR stage==done) + aged + W4-authorized (completedAt OR ancestry) + W7b-provably-clean. Reflected across design.md (Tier-W contract ~35-53, W4/done discussion ~64-72, Age binding) and design-phase1.md (gate-order precedence W1/W2/Wd/W3, sole-eligible-outcome line, classify_tier_W interface, edges 1/2/4/7a, AC7/AC9, DP4/DP10).
MAJOR (round-5 — event-log age input = MAX over ALL parseable timestamps, not the last line): design-phase1.md:101 had defined the event-log age contribution as the LAST non-empty line's `.at`, but the age rule requires max(run-dir mtime, NEWEST event-log ts, completedAt-if-parseable). A torn/backdated tail line can hide a newer earlier timestamp, and appending to event-log.jsonl does NOT bump run-dir mtime, so a last-line read could make a recently-touched run look aged (fail-open on age). FIX (both docs): the event-log age contribution is the MAX over ALL parseable `.at` values across EVERY line (jq over all lines, unparseable lines ignored), robust to a torn/backdated tail. Propagated to design-phase1.md per-run reads (line 101), run_age_epoch interface (line 127), AC12 (added a recent-line-then-backdated-tail fixture), and design.md Age binding (~153).

- **DP12 (Mechanical/consistency, round-6): reconcile design.md UP to design-phase1.md's PER-CHILD Tier-W semantics + fix the W5 git-dependency story.** Round-5 dual-voice confirmed the classifier is sound (no fail-open); the only open items were design.md↔design-phase1.md drift (design-phase1.md is authoritative). Fixes: (1) design.md W5 (~:41) rewritten from a RUN-level registration veto to PER-CHILD three-way path-equality registration (a registered sibling does NOT veto a clean no-pointer drive-owned child); (2) design.md Repo-ownership :108 amended so an UNRESOLVABLE run is Tier-W-SKIPPED ONLY when it ALSO lacks a parseable `completedAt` — a parseable `completedAt` authorizes W4 WITHOUT the repo (REPLACES ancestry), removing the contradiction with design.md:46-47; (3) design.md :112 run-wide registration veto rewritten to per-child. MINOR (design-phase1.md edge 14, :438): clarified W5 needs NO git (pure pointer/back-reference FILE reads) — only W4 (`merge-base`) and W7b (`git status`/unpushed) require git; a missing git skips W4/W7b (→ SKIP, fail-safe) but W5 still detects registration via file reads (consistent with :172,:201). design-phase1.md NOT weakened; sole-eligible outcome and all settled gates unchanged. No new fail-open. Classification: **Mechanical (consistency/propagation).**

D-skip-vocab (Mechanical, round-7): Skip-token vocabulary swept for consistency across the DP4 enum, AC14/15 pinned set, the W-tier precedence mappings, and every edge case. FIX: edge 14 missing-git on a drive-owned no-pointer/no-completedAt child now emits `skip:ancestry-unprovable` (the W4 ancestry probe cannot run; repo resolution itself is file-only and may succeed) instead of `skip:unresolvable-repo` (reserved for repo-RESOLUTION failure). Sweep result: this was the ONLY mismatch; all 13 enum tokens are emitted (none dead), no token outside the enum is emitted (`no-completedAt-and-no-ancestry` is the REMOVED v1 placeholder, asserted never to appear), and the enum/AC15/emission sites are mutually consistent. Still fail-safe (every off-path input SKIPs). design.md untouched (no contradiction found there).

## Slice 1.1 review-fix round 1 (2026-06-22)
- **CLI trailing-valued-flag hang (P1 BLOCKING)**: bounds-check `[ $# -ge 2 ]` before each
  `shift 2` (--root/--age-days/--now); a valued flag as the last token ⇒ exit 2 (same lane
  as unknown flag), not an infinite loop. Mechanical/DP3 (best-effort, but a CLI usage error
  fails loud at the boundary, never hangs GC-at-setup).
- **Event-log torn-line robustness (codex hint)**: changed `jq -r '.at // empty'` (whole-file
  parse — errors on the FIRST torn line and STOPS, dropping every later .at ⇒ age fail-open)
  to per-line tolerant `jq -R -r 'fromjson? | .at // empty'`. A torn line is now skipped; the
  other lines' timestamps still count. Mechanical/fail-safe.
- **skip:unreadable test-pin (P1 MAJOR)**: added a real behavioral test (W4-authorized run via
  parseable completedAt + plain no-pointer non-repo dir ⇒ W7b `git status` fails ⇒
  reason=="unreadable", eligible==false). Code was already correct (reviewer-confirmed);
  test-gap fill. All three new tests mutation-verified RED against pre-fix code.

## Slice 1.1 round-2 review fixes (2026-06-22)
- **W7b unpushed probe `--branches` → `--all` (BLOCKING fix).** `git log --branches --not --remotes` missed a commit reachable only from a DETACHED HEAD (or refs/stash) — a /drive worktree is often on a detached HEAD, so a clean detached checkout carrying an unpushed local commit was wrongly reported clean→eligible (report==apply deletion-safety fail-open). `--all` covers HEAD+branches+stash; a genuinely-pushed-clean checkout still yields empty. Mutation-verified: new `test_tierW_detached_head_unpushed_skips` is RED against `--branches`, GREEN against `--all`.
- **Flag-shaped-value guard (nit).** A valued flag (`--root`/`--age-days`/`--now`) followed by another flag (e.g. `--root --json`) now exits 2 (`need_value` rejects a next token starting with `-`) instead of silently swallowing the flag as the value and scanning the wrong root. A flag-shaped `--age-days -5` thus exits 2 too (safer than the prior 14-fallback).
- **Edge 13 kept (non-numeric numeric-flag fallback).** A NON-flag non-numeric `--now`/`--age-days` value (e.g. `nope`) still falls back to the SAFE default (real clock / 14) with a stderr notice + exit 0 — confirmed not a fail-open by both reviewers (real clock cannot age a recent run; 14 never 0). Now pinned by `test_non_numeric_now_falls_back_to_clock` + `test_non_numeric_age_days_falls_back_to_14`.
- **Fail-safe pins added (P2):** detached-HEAD unpushed (P1 above), and a dangling `.git` symlink ⇒ `registration-unprovable` (never eligible). missing-jq/missing-git tool-absence pins NOT added — see followups.

--- Phase 2 detailed-design decisions (design-phase2.md) ---
DP-A1 (Mechanical): bin/drive-retention.sh --apply REUSES Phase 1's per-run/per-child verdicts (TIERL_VERDICT / TW_VERDICTS[]); adds destructive ACTIONS only, NO new authorization. The classifier is the sole authority (report==apply invariant, design-phase1.md DP5); re-deriving any gate in the apply path would let report and apply diverge — the one fail-open the contract forbids. Apply branches on the EXACT eligible/skip:* strings classify_run already computes.
DP-A2 (Mechanical/safety): re-verify not-registered + wt_cleanliness==clean IMMEDIATELY before `trash` (TOCTOU guard). The verdict was computed earlier in the run; a tiny window exists where a dir could go dirty/registered before the trash. Cheap re-check (file reads + one git status); on failure ⇒ skip:changed, leave the dir. Closes the "destructive gate before the decisive check" hazard.
DP-A3 (Mechanical): RETENTION_TRASH_CMD env override (default `trash`) for the destructive command, so apply-path tests inject an mv-to-graveyard shim and stay trash-independent/deterministic — same discipline as Phase 1's --root/--now seams. Production uses /usr/bin/trash (D4).
DP-A4 (Mechanical): GC-at-setup runs REPORT-ONLY (NO --apply) in a backgrounded swallowed subshell AFTER the first state.json write — per the Gate-A resolution (event-log gate-A note: "report-only, N=14d" accepted). Never on the mkdir critical path; `|| true` + output to $RUN_DIR/retention-gc.log; &-backgrounded so a slow scan never blocks setup. The destructive --apply is the manual D6 one-shot, NOT wired into the unattended call. (Corrects a naive auto-apply-at-setup reading; report-default was the load-bearing Gate-A Taste item, design Open Question 2.)
DP-A5 (Mechanical): completedAt written with `printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"`, AFTER worktree removal, BEFORE stage="done". Anchors on the strict format completedat_epoch parses (single clean ISO line + trailing newline, no interior whitespace). Order remove→mark→done-last is the D1 race fix and what gives completedAt's W4 authorization its meaning (worktrees gone at marker-write time).
DP-A6 (Taste): D5 TMPDIR=$RUN_DIR/tmp export around drive-review.md's codex exec is OPTIONAL/lowest-priority — include the one line only if the codex CLI is confirmed to honor TMPDIR on this host; else DEFER to followups (no behavior loss; /tmp backlog is a manual one-shot). Recommendation: include it (one line, harmless), confirm-then-commit. No new human gate.
DP-A7 (Mechanical): repoRoot added to BOTH drive.md fresh-run JSON example AND CLAUDE.md state.json description; written once at fresh-run setup, NEVER re-derived on resume (D7). test_state_json_shape.py is a subset/present check on both sides, so adding a key is safe + keeps the two artifacts consistent. Write-once means a resume re-pasted from any cwd keeps the correct root.
PHASE-2 SLICING: ONE slice (2.1) — bin/drive-retention.sh (--apply) + drive.md + drive-ship.md + drive-review.md(opt) + CLAUDE.md + test_drive_retention.py + drive*.md prose pins. The completedAt producer (ship/drive.md)→consumer (helper W4)→actor (--apply) loop and the repoRoot producer→consumer link are NEW shared contracts co-authored this phase ⇒ MUST be one review unit (OPERATING shared-contract rule); splitting the marker writer from the reader/actor is how a format-drift contract silently fails to transfer. No fan-out, no internal staged-risk (the staged-risk seam was the Phase1→Phase2 split, already taken).
PHASE-2 TEST-MUST-CHANGE: test_no_deletion_path_exists (Phase-1 structural "no deletion token" guard) goes RED by design — Phase 2 adds --apply/trash/worktree-remove. REPLACE it with AC12's guarded-deletion test (deletion verbs reachable only under APPLY=1, proving report-only is still the default). Run pytest tests/contracts/test_drive_retention.py during implement, not after CI.

--- Phase 2 design-review round-2 corrections (codex 2 BLOCKING + 2 MAJOR, Claude 1 MAJOR; classification Mechanical/safety) ---
DP-A1 (REVISED round-2, supersedes round-1; codex MAJOR finding-3 — report==apply was VIOLATED by re-classification): the round-1 apply path added a new `skip:changed` lane and flipped `eligible:true`→`eligible:false` on trash-failed/changed — that IS re-classification in apply mode, the one fail-open the contract forbids. FIX: model the apply-time safety recheck + trash failure as ACTION OUTCOMES (a SEPARATE field/enum), DISTINCT from the classifier's eligible/skip:* verdict which apply MUST NOT mutate. New invariant wording (settled): "The classifier verdict (eligible/skip:*) is IDENTICAL in report and apply mode — --apply NEVER mutates it. Apply ADDS a per-child/per-tier `action` field (closed enum {removed, swept, skipped-changed, trash-failed, none}); a fail-safe re-check or trash failure can DECLINE to act (changes only the `action`) but NEVER rewrites the verdict. An eligible:true child stays eligible:true regardless of action outcome." Closed-vocab reconciliation: the report-only CLOSED_VOCAB (test_all_skip_reasons_in_closed_vocab, run without --apply) is UNCHANGED — trash-failed/skipped-changed are NOT skip:* reasons; the action outcomes are a separate closed enum guarded by its own apply-scoped assertion (AC5). AC4/DP-A1/DP-A2 updated to match.
DP-A2 (REVISED round-2, supersedes round-1; codex BLOCKING finding-2 — destructive verbs ran BEFORE the re-verify): round-1 sequenced `git worktree remove --force` → trash → THEN the re-verify guard — backwards. The TOCTOU re-verify (not-registered + wt_cleanliness==clean, against LIVE state at apply time) MUST run BEFORE any destructive verb. FIXED sequence (settled, unmistakable in prose + AC3 pin): re-verify FIRST → (if still authorized) remove → prune → trash; (if re-verify now fails) NO destructive verb at all, record action outcome `skipped-changed`, leave the dir. "Destructive gate before the decisive check spawns false-positives" lesson.
DP-A5 (REVISED round-2, supersedes round-1; codex BLOCKING findings-1+4 — two coupled defects): (finding 1) ship runs with cwd=wt/ship (drive-ship.md:45-46), itself a drive-owned name the removal loop deletes — so §D/§E `cd` OUT to the owning repoRoot (fallback $RUN_DIR) BEFORE the removal loop, and all remaining steps run from repoRoot. (finding 4) the round-1 crash analysis was WRONG vs the REAL is_done() (drive-retention.sh:252-256): `completedat_authorizes "$1" && return 0` runs BEFORE the stage=="done" OR-branch, so a parseable completedAt ALONE makes a run done→sweepable — "write stage=done last" does NOT protect a crash that wrote completedAt before removals finished. SETTLED INVARIANT wording: "completedAt is written ONLY after every required drive-owned worktree removal has DEFINITELY SUCCEEDED (each wt/<name> verified gone on disk). If removal genuinely cannot complete, completedAt is NOT written (the run stays not-done / not-sweepable — fail-safe; at ship, STOP and report; on resume, re-attempt later). stage='done' after the marker is belt-and-suspenders, not the load-bearing gate." §D/§E both gate the marker on per-tree proven-removal; AC8/AC10 pin cd-before-remove + the proven-removal gate token (not mere sequencing).

DP-A5 (AMENDED round-3; codex BLOCKING round-2 finding — cd-out fail-closed completeness): the round-2 `cd`-out only fell back to $RUN_DIR when repoRoot was UNSET, NOT when state.repoRoot was PRESENT-but-stale (no longer a valid dir). A FAILED `cd "$repoRoot"` leaves cwd inside wt/ship, so the later absolute-path `git worktree remove`/`trash` can delete the live cwd. FIX (mirrors the helper's own guard `[ -n "$rr" ] && [ -d "$rr" ]`, drive-retention.sh:322-325): §D/§E select the cd target with an explicit `-d`-validity check — `target = (repoRoot non-empty AND [ -d "$repoRoot" ]) ? "$repoRoot" : "$RUN_DIR"` (fallback covers UNSET *and* PRESENT-but-invalid); verify `$RUN_DIR` exists before relying on it; `cd "$target"` is itself checked (`|| fail-closed`). FAIL-CLOSED branch: if NO valid stable dir can be entered (neither valid repoRoot nor valid $RUN_DIR), run NO destructive verb — skip teardown, leave the worktrees, write NO `completedAt`/`stage="done"` (run stays not-done/not-sweepable; resume re-attempts). The destructive loop runs ONLY AFTER a successful `cd` to a verified-stable dir outside any worktree being removed. AC8 gains clause (f) pinning the `-d`-validity check (fallback on present-but-invalid, not only unset) + checked `cd` + fail-closed branch; AC10 mirrors it. repoRoot is NOT re-derived (D7 write-once) — this is only a validity guard on the existing value. Round-1 fixes (Tier-W re-verify ordering, report==apply action-enum, completedAt-after-proven-removal) and one-slice decomposition UNCHANGED — converged, left intact.

## Phase 2 / Slice 2.1 implement (DP-A* applied)
- DP-A6 RESOLVED → INCLUDE D5 (Mechanical): codex CLI (`/opt/homebrew/bin/codex`, Rust) honors `$TMPDIR` (std tempdir convention; decisions D5 already noted "honors TMPDIR"). Per DP-A6's "include if honored" recommendation, drive-review.md now exports `TMPDIR=$RUN_DIR/tmp` around `codex exec` with a one-time `mkdir -p`. AC13 IS in scope (pinned in test_drive_retention_wiring.py).
- Action-outcome field is ALWAYS present in JSON (uniformly `none` under report-only), not omitted — keeps the schema stable and the report==apply parity test clean. Updated the Phase-1 AC14 exact-key schema assertions to include `action` (additive, expected by the phase split). Classification: Mechanical.

## Slice 2.1 FIX round (round-1 dual-voice P1s addressed)
- FIX-1 (codex BLOCKING — apply re-verify too narrow): `apply_tier_W_child`'s TOCTOU re-verify checked only registration+cleanliness. ADDED the full liveness gate the classifier uses — `is_waiting_quiet`/`has_open_inflight`/`is_done` (predicates REUSED, not duplicated) BEFORE the registration/cleanliness checks. A run RESUMED in the window (sets `.waiting`/writes `inflight-*.marker`/un-dones) but still clean+not-registered now → `skipped-changed`, no destructive verb. Age is NOT re-checked (cannot un-age in a window; not load-bearing). New test `test_apply_reverify_declines_run_gone_live_via_waiting` reds pre-fix.
- FIX-2 (codex MAJOR — Tier-L apply mutated report fields): `emit_json_run`/`report_run`/summary recomputed `heavy_logs()` AFTER deletion → `--apply` reported `logs:[]`/`bytes:0`/"SWEPT <0 files>". FIX: snapshot the Tier-L log set+bytes in `classify_run` BEFORE apply (`TIERL_LOGS_SNAPSHOT`/`TIERL_BYTES_SNAPSHOT`); all three renderers read the snapshot. report==apply field parity now holds (logs+bytes identical; only action/verbs differ). Parity test extended to assert full measured-field identity — reds pre-fix.
- FIX-3 (codex MAJOR — cd fail-closed incomplete on stale-but-present repoRoot): round-3's `$RUN_DIR` fallback let `cd` succeed while step-3 still ran `git -C "<stale repoRoot>"` (silent no-op) then `trash` (NOT fail-closed). FIX (chose codex option A — whole-teardown fail-closed): drive-ship.md §D & drive.md §E now REQUIRE a `-d`-valid repoRoot; if repoRoot empty OR NOT `[ -d ]`, fail-closed for the WHOLE teardown (no git verbs, no trash, no completedAt/stage=done). Removed the `$RUN_DIR` cd fallback (a stale repoRoot can never genuinely unregister, so trashing into it would write a completedAt attesting removal that never happened). AC8/AC10 pins strengthened to assert the empty-OR-`-d`-invalid → whole-teardown fail-closed (no trash) path. Classification: Mechanical (safety).
- FIX-4 (Claude P1 + codex MAJOR — test gap): replaced the two weak "reverify" tests (which only asserted `action:none` skip cases) with: `test_apply_reverify_declines_sibling_dirtied_in_toctou_window` (the verified sibling-dirtying shim repro — drives a child to `action==skipped-changed`; reds when re-verify stripped) and `test_apply_reverify_declines_run_gone_live_via_waiting` (covers FIX-1; reds vs literal pre-fix). Kept a `skip:dirty → action none` pin as `test_apply_tierW_dirty_child_is_skip_none_no_trash`. Parity test extended (FIX-2). NOTE: the sibling-dirtied test reds against a re-verify-stripped mutation (not the literal pre-fix code, which already had the cleanliness re-verify) — it is the load-bearing branch-coverage test for `skipped-changed`; the went-live test is the one that reds vs literal pre-fix.
- FIX-5 (P2 — AC10 prose-pin section-bounding dead): `_section` lstrips each line but the AC10 end-markers carried leading spaces → never fired, span ran to EOF (1025 lines). Stripped the leading spaces (`- **Each slice`/`- **Phase `/`- **Fresh run`); span now bounds to 37 lines containing the done-path tokens and excluding `Each slice`. Verified empirically (old=1025 lines incl. 'Each slice'; new=37, excludes it).

## Finalize round 1 — codex 3×P1 OVERRULED (refuted at the integrated/executable-contract path)
codex's finalize audit raised 3 P1s; all REFUTED with evidence (per OPERATING "an adversarial
BLOCKING is not authority — reproduce against the REAL integrated path; refuted-at-integration →
overrule WITH evidence, never silently drop"). The Claude reviewer independently reproduced the
two logic concerns and reached the same conclusion. Evidence:
- codex-P1 "is_done stage==done contradicts the completedAt-SOLE contract" → REFUTED. The
  executable contract pins the OR: `test_completedAt_satisfies_done_gate_when_stage_not_done`
  asserts `is_done = parseable completedAt OR stage==done` and pins the completedAt OR-branch
  explicitly; a sibling test pins the stage==done arm. drive-ship.md's actual wording is
  "is_done() treats a parseable completedAt ALONE as done, INDEPENDENT of stage" = completedAt
  *suffices on its own* (justifying the write-after-proven-removal GATE), NOT *exclusive signal*.
  codex misread "ALONE". The OR is also safe by defense-in-depth: destructive Tier-W is separately
  gated per-child by W4 (ancestry/completedAt) + W7b (clean+pushed), which fail-closed regardless
  of which done-arm fired. No code/test change.
- codex-P1 "loose marker parse (bare epoch / whitespace) fail-open" → REFUTED. The real fail-open
  vector (interior-whitespace near-valid corruption) is CLOSED and mutation-verified
  (`test_interior_whitespace_completedAt_does_not_authorize`, RED vs the pre-fix `tr -d` strip).
  Bare-integer epoch is a VALID timestamp by design (`parse_ts` accepts epoch|ISO), not corruption.
  No change.
- codex-P1 "W7b `git log --all --not --remotes` repo-global → false skip:unpushed" → REFUTED, and
  acting on it would be a P1 DATA-LOSS REGRESSION. W7b is unreachable for a linked worktree (a
  readable `.git` pointer resolves to wt-registered/registration-unprovable at W5); W7b runs ONLY
  on a STANDALONE checkout dir (`.git` is a directory), where `git -C <dir>` operates on that dir's
  OWN complete repo, so `--all --not --remotes` is correctly local AND the SAFE scope (apply trashes
  the whole standalone repo — `--all` protects every branch/stash/local-tag's unpushed history).
  Narrowing to HEAD would miss non-HEAD history before trashing. codex's own adversarial pass
  confirmed. No change.
- codex ARCH "triplicated retention contract" → routed to finalize-todo.md (architectural
  follow-up; not fixed in-run, out of the run's blast radius).
Finalize round-1 APPLICABLE fix set = de-slop only (cheap, in-scope, behavior-preserving):
drop dead `:-0` array defaults, inline `selfpath`, remove unused `line` var, extract a
`parse_gitdir_admin` DRY helper, collapse the near-verbatim duplicated TOCTOU rationale comment
(keep all load-bearing fail-safe why). Deferred to followups: `anc` default-arm (adding defensive
code = inverse of de-slop) and codex's renderer verdict-mapping consolidation (refactor on a
destructive script's output contract = behavior-change risk). (2026-06-23T18:50:09Z)

## Finalize round 2 — codex P1 ADOPTED (confirmed at the integrated path; net-positive close)
codex's confirming-round audit reproduced (git-shim) a data-loss race the Claude voice missed;
I verified the MECHANISM in the real code (per OPERATING "reproduce against the REAL integrated
path before acting": confirmed → fix). `apply_tier_W_child` re-checks `wt_cleanliness` at Step 1
(bin/drive-retention.sh:533) but the late pre-trash guard (556-557) re-checks ONLY liveness
(is_waiting_quiet/has_open_inflight), NOT cleanliness. We only reach the trash when
reg=="not-registered" (a standalone checkout), so the `git worktree remove --force` at 541 is a
no-op and the dir survives INTACT to `$TRASH_CMD` (561). ⇒ a child dirtied in the Step1→trash
window (e.g. a user manually editing a done run's leftover worktree) is trashed with uncommitted
content. The previously-ACCEPTED residual (followups) covers only the LIVENESS sub-syscall window;
the cleanliness side was asymmetrically unprotected across the whole Step1→trash span. NOT a
re-litigation of the accepted residual — that residual was scoped to liveness only; this closes
the distinct cleanliness gap. FIX (net-positive, cheap, behavior-preserving): add a symmetric late
`wt_cleanliness "$dir"` re-check immediately before the trash (mirrors line 534), shrinking the
cleanliness window to the same accepted sub-syscall residual as liveness; + a mutation-verified
test pinning the same-child post-Step1 dirtiness window (reds pre-fix). Security-sensitive
destructive code ⇒ adversarial voice load-bearing. Classification: Mechanical (safety). (2026-06-23T20:47:28Z)

## Finalize round 5 — user-directed comment de-slop (cap-3 overridden by explicit instruction) (2026-06-24T01:29:25Z)
At Gate B the user directed "let's clean up AI-slop". finalizeRound was already at cap 3; an
explicit user instruction outranks the automated cap guard (OPERATING: "an explicit user 'wait'
outranks an automated goal" — same principle, user authority over an auto-STOP). Dropped the
unpushed regenerable ledger commit (e91f343), reopened finalize at the code tip 7046a6a, and
applied a COMMENT-ONLY de-slop to bin/drive-retention.sh: stripped review-process meta-references
(finding-N, edge-N, fragile in-comment line-number refs) and internal design-decision-ID tags
(D3/D4/DP3/DP5/DP6/DP8/DP9/DP-A2/DP-A3) that a standalone-script reader cannot resolve. The r1
finalize audit had flagged the heavy comment narration as P3 slop but DEFERRED it as low-value;
the user reopened that gate. Behavior-preserving: zero code lines changed (verified comment-only),
full suite 383 green. Classification: Taste (de-slop). The load-bearing fail-safe *why* sentences
were preserved — the dual-voice review's job is to confirm none were over-cut. Re-promote ledgers
fresh after convergence.
## Run drive/p3-followup-cleanup (2026-06-23) — clear two deferred P3 followups

- **Two parallel slices (fan-out), not one.** [Mechanical] Disjoint files
  (`test/drive-merge-gate.test.sh` vs `bin/drive-conformance.sh`), no shared contract, no ordering →
  fan-out seam; parallel worktrees. Slice ids 1.1, 1.2. (pragmatic, bias-to-action)
- **Rename FULL symbol at both sites; leave already-correct comments.** [Mechanical] Banner/registration
  comments already said "finalize"; edited only the def + callsite. (explicit-over-clever, DRY)
- **B is comment-only; mirror docs/live-logic, no logic touch.** [Mechanical] Per D33 the L484+ logic is
  correct; scoped strictly to the L449–451 comment block; executable diff empty. (completeness w/o boiling ocean)
- **No new test coverage; reuse existing suites + grep as the regression guard.** [Mechanical] No exact-prose
  pin guards either edit; a banner-prose pin would be over-design. (right-size at design)
- **Finalize: codex P2 (remove the rewritten banner) VETOED.** [Mechanical] The banner IS task (B)'s
  deliverable; removal would restore the stale pre-finalize comment / drop slice 1.2's acceptance criterion →
  vetoed, non-blocking. Both voices zero P1; finalize CONVERGED at the free confirming round (0 fix rounds).


## Run main-20260704-180725 (leverage Trellis in autodrive → /drive-retro trace-mining command) — 2026-07-05

## D-0 (Stage 0, Taste) — deliverable shape for an "analyze X" premise
Task asks to ANALYZE how trellis (github.com/mindfold-ai/trellis, AGPL-3.0) can help autodrive.
Decision: deliverable = a committed comparative-analysis + recommendations doc (docs/), with
actionable follow-ups routed to TODO.md/followups — NOT implementation of the recommendations
(separate future run). Rationale: literal ask is "analyze"; AGPL-3.0 rules out vendoring code,
so recommendations will be pattern-adoption / run-alongside options. Surface at Gate A.
Trellis clone for reference: /private/tmp/claude-502/-Users-jiazou-workspace-autodrive/9dc15e21-289e-4dcc-b4ab-210f4d3caa09/scratchpad/trellis

## D-1 (Plan, Mechanical) — analysis dimensions
Seven comparison dimensions fixed from mechanisms verified in trellis SOURCE (hook wiring in
packages/cli/src/templates/claude/settings.json, workflow state machine in
packages/cli/src/templates/trellis/workflow.md, task/spec/journal systems), not the README
marketing table. Every trellis claim in the doc must cite a clone file path.
Classification: Mechanical

## D-2 (Plan, Taste) — recommendation schema
Each recommendation: tier (adopt-pattern / run-alongside / ignore) × effort (S/M/L) × value +
its autodrive landing surface + cross-reference to overlapping TODO.md C-items (Fable-5 audit)
so no rec duplicates already-scoped work. Surface at Gate A.
Classification: Taste

## D-3 (Plan, Mechanical) — deliverable location
docs/trellis-analysis.md (new) + TODO.md append. No README edit (kept lean per #58).
Classification: Mechanical

## D-4 (Plan, Mechanical) — one phase
Docs-only, ~3 touch-points, ~300–450 doc lines (150–500 band → seam-hunt mandated). Seam-hunt
found no fan-out/staged-risk seam (single doc; evidence→writing is one produced-then-consumed
review unit). ONE phase + heightened-review note (citation validity, rec schema completeness,
no-AGPL-vendoring check).
Classification: Mechanical

## D-5 (Plan, Taste) — license boundary as first-class section
AGPL-3.0 ⇒ adopt-pattern = reimplement-from-idea only (no code/template/prompt-text copying);
run-alongside = unmodified released npm tool in a driven project. Surface at Gate A with D-0.
Classification: Taste

## D-1a (Plan, Mechanical) — amends D-1: 7 → 8 dimensions
Deep-dive of trellis source surfaced `trellis channel` (packages/core/src/channel/ — event-sourced
spawn/send/watch/interrupt worker runtime) as a real mechanism the 7-dimension list missed. Added
dimension 7 "Parallel execution & multi-agent runtime" (vs autodrive's file-ownership slices in
worktrees); portability/consent shifts to dimension 8. Doc estimate now ~300–500 lines (same
band, same one-phase verdict).
Classification: Mechanical

## Autoplan CEO round (2026-07-04) — D-6..D-11
D-6 (Mechanical): citations pinned to trellis SHA dddeb6e0 + GitHub permalink base; never temp-clone paths.
D-7 (Mechanical): rec schema += layer tag (L1/L2/L3) + harness-absorption risk + triggering-problem; L1 recs default ignore/wait; new tier "wait".
D-8 (Mechanical): dims 4+8 reframed as hypotheses-to-falsify; depth tiering (deep: 1/2/5/6); economics/operator-burden lens in dim 4.
D-9 (Taste): anti-rot — ≤3 TODO-routed items w/ named next-run triggers; review-by +6mo; doc closes with ONE next decision.
D-10 (Mechanical): triggering-problems T-1..T-4 anchor; rec that can't name its pain = ignore.
D-11 (Taste): codex "portability is the moat" partially overruled (solo harness, not a product); dim 8 keeps the counter-question.
Pipeline: Design/DX autoplan phases skipped (no UI; docs-only); eng P1-hunt delegated to /drive-review design on the amended doc.
User-Challenge held for Gate A: deliverable shape — docs-only (D-0) vs +Phase-2 S-effort spike vs +run-alongside pilot; recommendation: spike (b).
Housekeeping deferred to Gate A notes: gstack upgrade 1.55.1→1.58.5 available; gstack offers CLAUDE.md routing-rules append (declined mid-run — repo tree must stay clean).

## Design-review round 1 fixes (2026-07-04)
r1-F1 (Mechanical): hook evidence re-pathed to shared-hooks/*.py implementing scripts (codex MAJOR 1).
r1-F2 (Mechanical): layer-classification rule = by layer SERVED, rebuttable L1 default; depth ≠ adopt (codex MAJOR 2).
r1-F3 (Taste): D-11 revised — solo-audience is a stated ASSUMPTION, not repo fact; codex #4 scoped, not overruled (codex MAJOR 3).
r1-F4 (Mechanical): platform count 16→17 per types/ai-tools.ts (both voices).
r1-F5 (Mechanical): single size estimate ~250–400; OQ-1(b) conditional-amendment note added (Claude P2s 2–3).
r2-F1 (Mechanical): GSTACK appendix "overruled with evidence/solo harness" line + audit row 6 updated to the r1-F3 scoped-assumption framing (codex r2 MAJOR; Claude r2 flagged same spot as P3).

## D-12 (Gate A, User-directed premise addition, 2026-07-04)
User asked whether trellis's trace-analysis ability can optimize autodrive. Verified in source: trellis mem
(packages/core/src/mem/ + commands/mem.ts, local read-only transcript indexing over Claude Code/Codex/Pi JSONL)
+ bundled-skills/trellis-session-insight (pattern-spotting) + required trellis-update-spec write-back. No
automated harness-optimizer exists — the composition is the leverage. Added T-5 (no trace-to-harness feedback
loop) + extended dim 5 to cover trace-mining, with the user's interest as an explicit rec-ranking weight.
Design amended POST-convergence → targeted dual-voice re-verify (round 4) required before Gate A approval acts.
r4 (targeted, post-D-12): both voices no-P1. Applied prescribed P2 fixes: OpenCode not-yet-indexable correction; T-5 loop-shape precision (mining discretionary, write-back required).

## D-13 (Gate A approval, 2026-07-04) — user chose OQ-1 (b)
Gate A APPROVED with Phase 2 spike: single top-ranked S-effort adopt-pattern item (Phase 1 output selects;
D-12 weight makes run-retro trace-mining the likely winner). Pre-reviewed (b) amendments applied to Phases /
Size estimate / Out-of-scope. Phase 2 relies on Phase 1 (staged-risk). Vacuous if no S-effort adopt-pattern rec.

## Phase-1 detailed design (2026-07-04) — DP1-1..DP1-7
DP1-1 (Mechanical): TODO.md append = FIRST ## section after intro (newest-first convention),
header "## Trellis pattern adoption — from docs/trellis-analysis.md (2026-07-04)", C-item-style
checkbox items with TR-n IDs shared with the doc; intro line untouched. Verified repo TODO.md
content is not string-pin-tested (tests/contracts pins target drive-finalize.md prose).
DP1-2 (Mechanical): Phase-2 selection is a REQUIRED "### Phase-2 spike selection" subsection
with an either/or contract — exactly one S-effort adopt-pattern item + item-spec, OR an explicit
"Phase 2 VACUOUS per D-13" declaration — making the Phase-1→Phase-2 produced-then-consumed
contract mechanically checkable.
DP1-3 (Mechanical): the ~250–400 line band is a soft check — trim compact dims first;
materially outside ⇒ ship + log a decision, never pad or cut evidence.
DP1-4 (Mechanical): D-12 T-5 weight vs D-7 L1-default precedence — layer/absorption test
filters FIRST; the user weight ranks among survivors only, never rebuts an L1 default
(operationalizes D-12's "subject to the same layer/absorption test").
DP1-5 (Mechanical): dimension→T mapping fixed (1→T-1/T-4, 2→T-1, 3→T-2, 4→T-2, 5→T-3/T-5,
6→T-4, 7→none, 8→none); dims 7/8 rec candidates must name a pain or tier ignore (D-10).
DP1-6 (Mechanical): review-by = 2027-01-04 (+6mo per D-9).
DP1-7 (Mechanical): flow.md's 44-invocation figure is cited WITH its shape qualifier (exact
for the idealized 2-phase×2-slice×3-round example; a floor for that shape) — not as a
universal constant, guarding dim 4's economics lens.

## Phase-1 design review round 1 fixes (2026-07-04) — DP1-8..DP1-9 + AC tightening
DP1-8 (Mechanical): TODO routing is L2/L3-only — a rebutted-L1 adopt-pattern rec stays doc-only
(still Phase-2-selectable, never TODO-routed); resolves the Interface-B `L2|L3` skeleton vs
AC6/AC9 contradiction in favor of TODO.md's shed-L1 direction (codex MINOR ≡ Claude M2).
DP1-9 (Mechanical): BLOCKING fix — docs-only Slice 1.1 satisfies the fail-closed impl-presence
merge gate (docs/drive-enforcement.md) via a real git trailer on the slice commit:
"Drive-Test-Waiver: docs-only deliverable — analysis doc + TODO routing, no runnable code surface"
(trailer block, not body prose); bound in Slice 1.1 implementer notes + AC12.
AC tightening (codex MAJOR): AC1 += Analyzed field + citation-base note (all 6 header fields);
AC2 += fixed whole-doc section order incl. `## How to read this` + `addresses: —` empty stanza
form for dims 7/8; AC5 restored to full column semantics (absorption = yes/no + clause; Kills =
one sentence naming the pain; x-ref states extend-vs-duplicate); AC9 += interface-B item body
shape incl. **Trigger:** line. Claude M1: clone-missing recovery path (re-clone + checkout
pinned SHA + submodule-status check) added to implementer notes; AC3 rebound from unbound
$SCRATCHPAD to "the clone path bound in Slice 1.1 notes" with the grep gate = no /private/tmp/
or scratchpad path in the shipped doc. Both NITs applied.

## Phase-1 design review round 2 fix (2026-07-04) — DP1-10
DP1-10 (Mechanical): Kills column empty form on ignore-tier rows = the literal
"— (no pain ⇒ ignore)" (all other tiers require the one-sentence pain), defined in Interface A
col 9 + AC5 — same pattern as round 1's "addresses: —" stanza fix (Claude r2 MINOR). Codex r2
MAJOR (interface literals untestable) closed by pinning: AC1 the exact H1 title
"# Trellis × autodrive — comparative analysis & recommendations" (+ NIT fix: "five header
bullets", count now matches the enumeration); AC5 the fixed column order 1–10; AC9 the exact
dated header "## Trellis pattern adoption — from docs/trellis-analysis.md (2026-07-04)".

## Slice 1.1 implementation decisions (2026-07-04)
- S1.1-a: TR-4 (`trellis mem` run-alongside) is L1-tagged yet tiered run-alongside rather than
  ignore/wait. AC6's rebuttal clause is satisfied in the E6-sanctioned form: the row carries an
  explicit written "L1-default rebuttal" (run-alongside = E6's L1-safe route; zero build
  investment, absorption strands nothing) instead of a non-absorption claim — per E6's
  "trellis mem run-alongside is the L1-safe route there". Classification: Mechanical.
- S1.1-b: Phase-2 selection = TR-3 (/drive-retro) scoped S as a single-run v1 (one new command
  file, no shipped code, cross-run aggregation out of scope). D-12 weight applied among the
  layer/absorption survivors {TR-3, TR-2} per DP1-4; TR-2 is runner-up and the sole TODO-routed
  item. Classification: Taste (matches D-13's anticipated likely winner).
- S1.1-c (E1 refinement, not a failed claim): design.md's "OpenCode not yet indexable — adapter
  pending" is refined by source — packages/core/src/mem/adapters/opencode.ts EXISTS but is a
  documented degraded no-op (SQLite reader reverted over a native-dep install break); the doc
  states the no-op form. All other design.md mechanism claims re-verified unchanged at the
  pinned SHA (17 platforms confirmed per types/ai-tools.ts; submodules confirmed empty).
  Classification: Mechanical.
- S1.1-d (DP1-3): first draft landed at 167 physical lines only because prose was one paragraph
  per line; rewrapped to the repo's ~98-col house style (content unchanged) → 358 lines, inside
  the ~250–400 band. No band deviation to log. Classification: Mechanical.

## Slice 1.1 review round 1 fixes (2026-07-04)
- S1.1-e (E1 divergence from design.md, per review r1 MAJOR-2 ≡ codex MAJOR): design.md's claim
  that trellis's required-step ↔ breadcrumb mapping "is itself test-enforced by a regression
  invariant" does NOT re-verify at the pinned SHA — packages/cli/test/regression.test.ts contains
  zero `[required · once]` references; it pins two historical instances (in_progress→Phase-3.4
  mention, planning-block content) plus block presence/degradation. The universal invariant is
  workflow.md's own contract comment (self-description). Doc narrowed in dims 2 and 4 with the
  correction recorded in-text; dim-4 hypothesis-(i) verdict kept but margin restated as thinner.
  Classification: Mechanical.
- S1.1-f (review r1 MAJOR-1): six verbatim trellis template/skill quotations replaced with
  own-words mechanism descriptions + citations (clean-room self-consistency, AC8); dim-6
  invented-wording quotation de-quoted (MINOR-1). Doc-wide sweep run: every remaining ≥8-char
  quoted string checked against the clone — none trellis-origin (remaining quotes are
  autodrive-source or hypothetical predicates). Classification: Mechanical.
- S1.1-g (review r1 MINOR-2/3): lifecycle-hook pointer corrected to workflow.md §Customizing
  Trellis; C9 characterization softened to "documents the hazard". All 3 MINORs fixed (cheap).
  Classification: Mechanical.

## Phase-2 detailed design (2026-07-04) — DP2-1..DP2-7
DP2-1 (Mechanical): retro output = single overwritten $RUN_DIR/retro-<runId>.md, no -N
versioning — retro is a pure function of an immutable completed run dir; name matches the
TR-3 acceptance sketch. Why Mechanical: no consumer for versions; ceremony otherwise.
DP2-2 (Mechanical): event-log parsing contract = tolerant json raw_decode STREAM decode;
line-split parsing forbidden — the REAL event-log.jsonl mixes single-line and
pretty-printed multi-line objects (this run: 46 objects; a line parser mislabels 192
lines). Writer-vs-CLAUDE.md "append-only jsonl" divergence routed to followups.md.
Why Mechanical: empirical artifact shape decides, no taste involved.
DP2-3 (Mechanical): completed-run authority = parseable completedAt OR stage=="done"
(drive-ship.md is_done semantics); unreadable state.json fails CLOSED (STOP); literal
`partial` arg is the sole override and brands the output PARTIAL. Why Mechanical: copies
the existing authority rather than inventing a second definition of done.
DP2-4 (Taste): proposal classification = OPERATING.md §Self-Improvement destination
matrix (+ process-signal → TODO.md), not decant's universal/workflow/domain split —
retro classifies WHERE a lesson lands; decant's scope test runs at promotion. Why Taste:
either vocabulary could work; this one keeps retro/decant complementary, not duplicative.
DP2-5 (Mechanical): no bin/ script in v1 (TR-3 scopes "no shipped code"); the ~15-line
parse snippet rides inline in the command prose. Follow-on named (bin/drive-retro-stats.py)
if a second consumer appears. Why Mechanical: TR-3's item-spec fixes this.
DP2-6 (Mechanical): the ≥1-lesson-proposal bar is conditional on mined signal (P1s,
STOPs, or multi-round scopes); a clean run may emit zero proposals with No-action notes.
Why Mechanical: anti-slop — never force a lesson to fill a quota.
DP2-7 (Mechanical): retro reads retention-durable artifacts only (.md/.json/.jsonl/
markers) — never wt/ or codex-raw-*.log (removed at run-done / Tier-L GC'd). Why
Mechanical: forced by drive-retention.sh + ship teardown reality.

## Phase-2 design review round 1 fixes (2026-07-04) — DP2-3 revised + DP2-8..DP2-10
DP2-3 (Mechanical, REVISED): completeness authority rebound to the REAL is_done() in
bin/drive-retention.sh — the standalone $RUN_DIR/completedAt marker FILE (parseable per
completedat_epoch) OR state.json.stage=="done". completedAt is NEVER a state.json key
(both voices' P1: the r1 design's state.json.completedAt clause was dead code — the key
never exists; the marker file is what drive-ship.md writes). Unknowable fails CLOSED.
Classification: Mechanical (the existing authority decides; the r1 text misread it).
DP2-8 (Mechanical): `partial` mode DROPPED (codex MAJOR-2 — unapproved scope growth on
the phase's only surface; TR-3 scopes v1 to ONE COMPLETED run). Stuck-run mining routed
to $RUN_DIR/followups.md as a named follow-on. Restores DP2-1's immutable-input
overwrite rationale. Classification: Mechanical (spec-conformance, not taste).
DP2-9 (Mechanical): codex-degradation stat redefined as derivable-only — count of scopes
whose SURVIVING codex-review-<scope>.md / codex-harden-<P>.md is a CODEX_UNAVAILABLE
stub (codex MAJOR-3: the files are overwritten per round and no event-log record exists,
so per-round degraded-round history is not derivable and is not promised).
Classification: Mechanical (durable-artifact reality decides).
DP2-10 (Mechanical): finding-heading rule recalibrated against the real corpus (Claude
MAJOR: ≥52/936 headings use compound forms — [P2 MINOR], [MAJOR/P1], [P1/BLOCKING]… —
the r1 single-token regex missed, including P1-bearing forms): ^### \[[^\]]*\]
candidates classified by word-bounded severity tokens, resolution/veto-tagged headings
(RESOLVED|VETOED|OVERRULED|REFUTED) excluded, one count per heading at highest severity.
Classification: Mechanical (empirical input space decides; mirrors DP2-2's discipline).
Also applied (Claude MINOR): codex-harden-<P>.md added to Inputs + E7 + the degraded stat.

## Phase-2 design review round 2 fixes (2026-07-04) — DP2-11..DP2-15 + DP2-10 case rule

DP2-11 — STOP-cause stats CUT (Claude MAJOR): STOP history is not durable on a completed
run — state.waiting is cleared on resume and the event-log append rule covers only
dispatch/verdict/merge/gate (verified: zero stop kinds in the real log). Durable residuals
stand in (final waiting if non-null, stranded inflight markers, redesign markers); AC8's
"≥1 STOP" trigger arm dropped; STOP-cause mining rides the DP2-8 in-flight follow-on;
make-STOPs-durable harness gap already in followups.md.
Classification: Mechanical (durable-artifact reality decides; same defect class DP2-9 fixed)

DP2-12 — input contract WIDENED to two classes (codex BLOCKING, recommended option taken):
mining inputs ($RUN_DIR durable artifacts, unchanged) + dedup references (fixed READ-ONLY
set: OPERATING.md, auto-memory MEMORY.md index, TODO.md, .harness/decisions.md,
.harness/followups.md) consulted only for proposals' Overlap field; absence tolerated as
"not checked (<file> unavailable)". Chosen over dropping the Overlap fields — TR-3's x-ref
discipline is extend-vs-duplicate and an unchecked Overlap field is theater; read-only
preserves the proposals-only invariant. Propagated to Inputs/Interface B/AC10/AC14.
Classification: Taste (widen-vs-drop; surfaced at next gate)

DP2-13 — ALL event-log-derived stats BEST-EFFORT (codex BLOCKING): per drive.md:705 the
event/field vocabulary varies per run, so each event-derived stat (gates+timestamps,
dispatches by kind, wall-clock) computes over whatever the tolerant decoder yields, no
stat requires a named event kind, explicit n/a fallback, never a hard failure. Wall-clock
= earliest→latest parseable `at` (replaces the run_created anchor; Claude MINOR).
Classification: Mechanical (drive.md's own disclaimer decides)

DP2-14 — recurrence themes DEMOTED to instructed synthesis (codex MAJOR): the computed
severity×subject table had no buildable subject-extraction rule. Now: the command
instructs the Claude operator agent to group the script-mined finding list by durable
keys (filename scope token, heading severity, normalized title), every citation required
to appear in the mined candidate list, ≥2 findings from ≥2 artifacts per theme. Counts
stay script-derived ("don't make the model the meter" governs metrics, not synthesis);
new AC15 pins the clauses.
Classification: Taste (compute-vs-instruct; surfaced at next gate)

DP2-15 — degraded done-path renderings specified (codex MAJOR + MINOR): completedAt
parseable + state.json unreadable ⇒ PROCEED with `?` header fields and
"n/a (state.json unreadable)" stat rows (state.json is a routing hint; artifacts are the
truth) — new E10; marker unparseable + stage=="done" ⇒ PROCEED, header renders
"completed: stage=done (marker unparseable)" — new E11. AC3 extended.
Classification: Mechanical

DP2-10 addendum (Claude MINOR) — severity tokens match CASE-SENSITIVELY (uppercase forms
only); only the resolution/veto exclusion is case-insensitive. Corpus-verified: "[MINOR ->
noted, not blocking]" and "[P3 — omitted from blocking scope]" grade MINOR/P3, not
BLOCKING. AC7 + implementer calibration note updated.
Classification: Mechanical (corpus decides)

DP2-16 — token→P-level mapping made the counted unit (Claude MAJOR, r3): per
drive-review.md's own taxonomy, P1 = {BLOCKING, MAJOR, P1}; P2 = {MINOR, P2};
P3 = {NIT, P3} — [MAJOR] IS a P1. Compound-heading dedupe operates on P-levels
(P1 > P2 > P3; BLOCKING > MAJOR is display-only), and the headline "P1 count" +
AC8's proposal trigger count under the mapping, so a MAJOR-only run fires them.
Negation-prefixed tokens ([non-P1 …]) do not classify (Claude MINOR folded in).
Stats rule, themes grouping key, AC7/AC8/AC15, DP2-10, and the calibration note
all updated.
Classification: Mechanical (the project's own emitting convention decides)

DP2-17 — rebind-on-resolve for unique-prefix runIds (codex MAJOR, r3): a prefix
argument is rebound to the resolved run dir's FULL basename before ANY downstream
use (retro-<runId>.md filename, # Retro title, header source line), so prefix and
full-id invocations write the identical single file. Interface, Writes clause,
AC2/AC4 updated.
Classification: Mechanical (the exactly-one-file invariant forces it)

DP2-18 — divergences consolidated to ONE contract (codex BLOCKING, r3): the TR-3
sketch stays authoritative for intent + boundary; the design supersedes its
mechanism details, with all three deliberate divergences (STOP-cause cut;
themes → instructed synthesis; conditional ≥1-proposal bar) listed once in a new
§Divergences subsection at the top; the scattered lone STOP-divergence parenthetical
was removed.
Classification: Mechanical (single-contract requirement; divergences themselves
were already decided as DP2-11/DP2-14/DP2-6)

r3 hygiene (codex MINOR + Claude MINOR/NIT) — AC10's mutation-verify clause marked
an explicit process note (implementer obligation, not an artifact property); AC13
made testable (wc -l ≤ 150 OR a decisions.md overage entry exists — "materially
over" dropped); E10/AC3/DP2-15's "?" header-field clause dropped (Interface B's
header has no state-derived field); the event-log "46 objects" literal rephrased
as ~46+ at design time, with a never-pin-literal-counts implementer note.
Classification: Mechanical

DP2-19 — codex siblings get their own extraction rule, Rule L (codex BLOCKING, r4):
empirical corpus enumeration (470 codex-review-*/codex-harden-* files across
~/.claude/harness-runs) shows 426 contain ZERO `### [` headings — findings are
bullet/prose lines (`- **BLOCKING** file:line — …`, `- MAJOR …`, `1. P1 …`,
`P1 `file`: …`, bare `P1:` label lines) — so the heading rule alone silently drops
codex-only findings from the P1 count, themes, and AC8's trigger. Rule L =
line-anchored UPPERCASE severity token after optional list marker/bold; grading from
the leading tag group only, once at highest P-level; UPPERCASE-only whole-line
resolution/veto guard (case-sensitive, inverse of Rule H's bracket guard: the
whole-line window collides with lowercase prose — corpus `resolved-skipped` is a true
P2 — while every corpus resolution marker is uppercase); bare label lines count once
(stated undercount for their untagged bullets, corpus = one run). Per-file precedence:
a codex file with ≥1 heading candidate (44/470; corpus-verified those contain zero
line-shaped findings) mines via Rule H ONLY, else Rule L — never both. Family→rule
mapping stated in the command; dedicated AC16 + AC10 pin.
Classification: Mechanical (the corpus's real shape decides; empirically enumerated)

DP2-20 — raw_decode inter-record whitespace advance (codex MAJOR, r4): the tolerant
decode advances the index past `[ \t\r\n]*` before EACH raw_decode — raw_decode raises
on leading whitespace (verified live with python3), so without the advance every
normal newline separator counts as a bogus "unparsed segment". Only decode errors at
non-whitespace content count; a well-formed mixed log reports 0 skipped. Parser spec,
E4, and AC6 updated.
Classification: Mechanical (Python stdlib semantics decide)

DP2-21 — non-null final `waiting` added to the proposal-trigger set (codex MAJOR =
Claude MINOR, r4): it is one of DP2-11's three same-class durable STOP residuals and
was already "reported as signal" in stats; trigger membership now matches the other
two residuals (no stats-only carve-out). E5's clean-run definition, AC8, and DP2-6
updated.
Classification: Mechanical (consistency between the design's own residual set and its
trigger set)

DP2-22 — dedup-reference paths bound exactly (Claude MINOR, r4): repo-side references
resolve under REPO_ROOT = state.json.repoRoot (OPERATING.md, TODO.md,
.harness/decisions.md, .harness/followups.md); auto-memory index =
~/.claude/projects/<proj>/memory/MEMORY.md with <proj> = absolute repoRoot, `/` and
`.` each replaced by `-` (munging verified against the real ~/.claude/projects
layout); unknown repoRoot (E10) ⇒ `not checked (repoRoot unknown)`, no cwd fallback.
E10/AC3's "nothing else degrades" phrasing reconciled (header never degrades; Overlap
renderings do). AC14 updated.
Classification: Mechanical (the design's own SKILL.md explicit-binding rule forces it)

r4 hygiene (Claude NIT) — the corpus's single `[MEDIUM]` heading noted as an accepted
token-free loss in the Rule-H calibration note (1 of ~940, cannot flip AC8).
Classification: Mechanical

## Phase-2 design review round 5 fixes (2026-07-05) — extraction contract RESTRUCTURED

DP2-23 — ONE unified line-level shape-agnostic extraction rule, Rule U (codex BLOCKING
+ coordinator structural directive): supersedes DP2-10's Rule H, DP2-19's Rule L, and
the per-file precedence. Three consecutive rounds each broke a per-family assumption
(r3 compound headings; r4 codex line shapes; r5 bracketed bullet tags in BOTH families
— census: 100+ `- [MINOR]`/`- [MAJOR]`/`- [BLOCKING]` bullets in Claude review/harden
files the old Rule H also missed — bracketless `### TOKEN` headings, and a mixed-file
counterexample to "Rule H if any heading exists") — the family/precedence STRUCTURE was
the recurring failure, not any one regex. Rule U = four empirically-enumerated carriers
(heading-bracket, heading-bare `###`+ [`##`-level token headings are corpus section
groupers, excluded], line-bracket, line-bare) + the ONE shared token→P-level mapping +
one uniform guard set + heading-vs-body per-line dedup (a candidate under a
finding-classified heading is not separately counted; bullets count when the nearest
heading is not a finding). No per-file or per-family rule selection exists to get wrong.
Classification: Mechanical (the corpus keeps electing line-level; structure follows)

DP2-24 — verdict-prose guard grounded in the round-5 false-positive census (Claude
MAJOR: ~23% of Rule-L P1-graded hits were verdict/resolution prose, incl. THIS run's
own codex-harden-1.md:3 `**P1 remains: NO**` — a phantom P1 that would have force-fired
AC8's proposal bar, the exact invented-lesson failure E5/DP2-6 guard against): (a) a
NAMED extendable verdict-continuation guard list, seeded `remains`, `remaining`,
`none`, `is addressed`, `closed`, `split correct` (post-tag-window, after skipping one
optional parenthesized token list + optional `:`); (b) a token-hyphen back-reference
guard on NON-heading carriers (`MAJOR-1(a)`, `BLOCKING-1.1:`, `P1-2`, `P1-sound.`,
`P1-NEW]`) with headings exempt — census shows `### P2-1 (MINOR) — …` is a REAL
numbered finding heading; (c) `CLOSED` added to the resolution/veto set (census:
`— CLOSED` headings, `P1 closed:` lines). The r4 claims "line-start anchoring
structurally excludes verdict prose" and "every corpus resolution marker is uppercase"
were empirically false and are withdrawn from the design.
Classification: Mechanical (the census decides)

DP2-25 — bounded imprecision budget + EXECUTABLE calibration AC (coordinator directive,
stops the whack-a-mole): ≤2% residual misgrades over graded findings accepted — mining
is signal, not accounting; a stray corpus line is a calibration-note entry +
guard-list addition, never a P1 against the design or a rule re-architecture. New AC17:
the implement slice runs the FINAL Rule-U spec as a throwaway script over the FULL real
corpus and appends a `Rule-U calibration` entry here (per-P-level figures indicative,
never pinned; ≥20-hit precision spot-check; carrier/false-positive exemplar
recall check incl. codex-harden-1.md:3 excluded; guard additions with their corpus
lines). Budget exceeded ⇒ extend guards and re-run, never ship over it. The design pins
rule INTENT + the seeded guard list, not literal counts.
Classification: Taste (budget size + where calibration evidence lands; surfaced at
next gate)

DP2-26 — AC8 trigger set += harden/finalize churn (codex MAJOR): ≥1 harden or finalize
FIX round — `phaseReview[*].hardenRound ≥ 1` or `finalizeRound ≥ 1`, artifact-derived
when state.json is unreadable as `## AppliedEdits: yes` counts in `harden-<P>-N.md` /
`review-finalize-N.md` (drive-harden.md:85 / drive-finalize.md:392's own derivation
rule). Stats table now dual-sources harden/finalize fix rounds (counter +
AppliedEdits file-count cross-check, mismatch = signal, file counts = E10 fallback);
E5's clean-run definition includes zero fix rounds.
Classification: Mechanical (the design's own dual-sourcing pattern extends)

r5 hygiene (Claude MINORs, both cheap) — the 3 legacy binary raw-CLI-dump
`codex-review-*.md` files named as a corpus shape (Rule U scans them, zero candidates,
harmless; the wrong 44/470 figure left with the precedence); completeness-gate
parenthetical += completedat_epoch's real strictness — any remaining interior
whitespace after trimming ⇒ unparseable (bin/drive-retention.sh:159-180).
Classification: Mechanical

DP2-27 — round-6 convergent P1 fixes (Claude MAJOR x2 + codex BLOCKING), both
full-corpus-measured above the ≤2% budget as single classes, both applied via Rule U's
own extension mechanisms (no re-architecture, still four carriers): (a) guard 3's
named verdict-continuation list += a digit, `count`/`counts`, `fix`/`fixes`/`fixed` —
kills the verdict-count/scoreboard lines drive-review.md's return contract emits every
round (`P1: 0 · P2: 2`, `P1 count: 0.`, `P1: 2 (both MAJOR) · P2: 1 (MINOR)`,
`P1 fixes in commit …`; ~43 phantom P1s ≈ 3.0% of graded, AC8 force-fires on clean
runs — the E5/DP2-6 invented-lesson failure; this run's own review-design-2.md:96);
(b) line-bracket carrier += optional `**` before the bracket, mirroring line-bare —
bold-before-bracket bullets `- **[BLOCKING] …` / `1. **[BLOCKING] …**` (36
guard-surviving real findings in BOTH families ≈ 2.5% dropped silently). Exemplars
added to Slice 2.1's must-catch/must-exclude lists and AC17(c).
Classification: Mechanical (both voices converge; the census decides)

DP2-28 — round-6 MINOR tightenings (all cheap, applied): E7 stub match stated as
first-line BEGINS WITH `CODEX_UNAVAILABLE` (prefix, not equality — corpus stubs carry
suffixes like `CODEX_UNAVAILABLE (rounds 2-3)`; suffixed form added to calibration
exemplars); severity-count unit stated once = FINDING-MENTIONS per artifact
(cross-round re-mentions are churn signal; `FIXED` deliberately NOT a resolution
token — harden's genuine found-and-fixed findings must count); AC13's SLOC-overage
path narrowed to overage DISCOVERED AT IMPLEMENT requiring a decisions.md entry titled
`drive-retro SLOC overage` naming the forcing design clause(s) — the ≤150-line cap is
contractual, not advisory (codex MINOR), testable form kept.
Classification: Mechanical

DP2-29 — round-7 guard-3 refinement (codex MAJOR + MINOR, Claude 2 MINORs; all
applied, corpus-verified before writing): (a) verdict-continuation forms
CARRIER-SCOPED — `fix`/`fixes`/`fixed` restricted to plain line-bare carriers (no
bracket, no `**`, non-heading): bracket-carrier fix re-listings are real
finding-mentions per the counted-unit contract and now count (`- [BLOCKING] fixed: …`
dependency-map-persist review-design-2.md:7; `- [MAJOR brittle A3 test] FIXED -> …`
checkmark-toggle-binding codex-review-finalize.md:26), while the corpus's one bare
fix-verdict line (`P1 fixes in commit 117ce5f.` lever2-rebirth review-phase1-2.md:7)
stays killed — scoping chosen over dropping fix* because dropping would re-admit that
line as a phantom P1; digit + `count`/`counts` restricted to non-heading carriers
(digit-titled heading findings `### [P1 BLOCKING] 4.2's …` — 4 corpus instances —
count; zero heading-carrier verdict-count lines exist). (b) The optional `:` skip
pinned token-adjacent (no intervening space) — `- P2 :462:` `:line:` metadata
(addressables-unit2 codex-harden-2.md:4-5, TRUE P2s) no longer digit-killed.
(c) Continuation-form match semantics stated: word-bounded, lowercase-as-written
(`fix` ≠ `fixture`; `none` ≠ title-case `None of the retries …`; corpus census found
zero uppercase verdict continuations). All rescued exemplars added to Slice 2.1
must-CATCH + AC17(c); scoreboard exemplars re-walked and still excluded.
Classification: Mechanical (corpus census decides; boundary unchanged)

## Slice 2.1 implementation decisions (2026-07-05)

### Rule-U calibration (AC17 — executable calibration over the FULL real corpus)
Throwaway script (scratchpad `rule_u_calibrate.py` + `rule_u_exemplars.py`, not shipped —
TR-3's no-shipped-code boundary holds) implementing the FINAL Rule-U spec, run over
`~/.claude/harness-runs/*/{review-*,harden-*,codex-review-*,codex-harden-*}.md`.
(a) Corpus figures (indicative only — never pinned in the command or test): 1478 files
    scanned across 64 run dirs; 1450 graded finding-mentions — P1=663, P2=598, P3=189;
    by carrier: heading-bracket 957, line-bracket 261, line-bare 200, heading-bare 32.
(b) Precision spot-check: 25 randomly sampled P1-graded hits (seed 17), each manually
    verified a true finding (real BLOCKING/MAJOR/P1 defect lines across 20+ distinct runs,
    all four carriers represented). Phantom rate in sample: 0/25 — within the ≤2% budget.
(c) Recall/exclusion exemplar check: ALL PASS — every must-CATCH carrier exemplar from the
    Slice 2.1 calibration bullet extracts at the right P-level (26 synthetic forms incl.
    compounds-once-at-highest, `2. **P1:**`, bare `P1:` label-once, `- P1/P2/P3` once-P1,
    harden `— FIXED.` findings), including the carrier-scoping must-CATCH set verified at
    their REAL corpus file:lines — dependency-map-persist `review-design-2.md:7`
    `- [BLOCKING] fixed:` (P1), checkmark-toggle-binding `codex-review-finalize.md:26`
    `- [MAJOR brittle A3 test] FIXED ->` (P1), digit-titled heading `### [P1 BLOCKING]
    4.2's …` (P1), addressables-unit2 `codex-harden-2.md:4` `- P2 :462:` (P2). Every
    census false-positive exemplar excludes (26 forms), including this run's own
    `codex-harden-1.md:3` `**P1 remains: NO**` and `review-design-2.md:96`
    `P1: 0 · P2: 0 · P3: 2` verified NOT findings at their real file:lines; the two
    must-KEEP true P2s (`resolved-skipped` prose, `[MINOR -> noted, not blocking]`) grade P2.
(d) Guard-list forms appended: NONE — the design's seeded list survived full-corpus
    calibration unchanged. Accepted losses (stated per the design): the corpus's single
    token-free `[MEDIUM]` heading; untagged child bullets under bare label lines;
    token-tagged sub-bullets deduped under a finding heading. One implementation note the
    spec text already implies: guard 4's hyphen check reads the ORIGINAL text following a
    bare carrier's tag group (the `-` sits past the group boundary), not the window content.
Classification: Mechanical (the corpus decides; budget met, no rule change).

### drive-retro SLOC overage (AC13 — discovered at implement)
`drive-retro.md` lands at 179 lines (`wc -l`), 29 over the ≤150 cap, after two dedicated
compression passes (house-style ~98-col wrap, merged bullets, compressed snippet). Forcing
clauses — the AC-mandated content exceeds the cap at readable wrap width:
- AC16's full Rule-U classification contract (four carriers + tag-window rule + four uniform
  guards with the named carrier-scoped continuation list + per-line dedup + budget): §6 = 55
  lines on its own;
- AC6's mandatory inline tolerant-decode snippet (10 fenced lines + FORBIDDEN/degrade prose);
- AC7+AC8's per-metric source naming, dual-sourced cross-checks, 5-field proposal contract
  and full 6-member signal-trigger set;
- AC3/AC14's exact degraded-path renderings and exact dedup-reference path bindings.
Cutting further would drop clauses AC10's section-bound pins (and the design review) require
present. Classification: Mechanical (cap vs mandated-content conflict resolved via the
design's own narrow overage path).
Update (slice 2.1 fix r2): now 183 lines — the round-2 marker-absent done-path clause (§2) added 4; forcing clauses unchanged.
Update (run main-20260705-130712, retro→Completion wiring): now 184 lines — the role-paragraph reword to the auto-invoked-at-run-wrap status (§ role paragraph, +1 physical line) shifted the reviewed size 183→184; `REVIEWED_OVERAGE_LINES` moved with it. Forcing clauses unchanged.

### S2.1-a — minor drift: _helpers.py location
Design/AC10 say "uses `tests/contracts/_helpers.py` REPO_ROOT like its siblings"; the real
helper lives at `tests/_helpers.py` (importable as `from _helpers import REPO_ROOT` via
conftest's sys.path insert — exactly how every sibling imports it). Adapted: same import
form, no new helper file. Classification: Mechanical.

### S2.1-b — AC13 pytest pin deliberately not shipped
AC13's "(Testable form: wc -l ≤ 150 OR a decisions.md entry …)" is verified at review time
against $RUN_DIR/decisions.md (this file). A shipped repo pytest cannot reference $RUN_DIR
(absent in CI) and pinning `.harness/decisions.md` would red pre-ship (run ledgers promote
at ship) — so the AC13 check stays a review-time obligation, like AC10's mutation-verify
and AC17's calibration. All other testable ACs carry pins in
tests/contracts/test_drive_retro_contract.py (21 pins, each mutation-verified red).
Classification: Mechanical.

- **S2.1-b superseded (harden-2 r1, Mechanical)** — AC13 now HAS a shipped CI-runnable pytest guard (`test_sloc_cap_or_logged_overage`): ≤150 lines OR the `drive-retro SLOC overage` entry present in the ship-promoted `.harness/decisions.md`, with the pre-promotion window bounded at 183 lines. Ship promotion must keep the entry title verbatim.
- **AC13 guard final form (harden-2 r2, Mechanical)** — `test_sloc_cap_or_exact_reviewed_overage`: pass iff ≤150 lines OR exactly the reviewed size (exact pin, `REVIEWED_OVERAGE_LINES = 183`); any drift up or down reds and forces a re-review that moves the pin and the `drive-retro SLOC overage` entry together. Supersedes the r1 ledger OR-leg form (whole-file grep of `.harness/decisions.md` — vacuous post-promotion) and the r1 ≤183 window; the ledger leg is REMOVED, so ship promotion no longer carries a title-verbatim obligation for this guard.

- **AC13 testable-form amendment (harden-2 regress r2, Mechanical)** — design-phase2.md AC13's parenthetical testable form amended to the exact-pin realization (`wc -l ≤ 150 OR == REVIEWED_OVERAGE_LINES`), because the originally-stated OR-leg (`$RUN_DIR/decisions.md` entry) is CI-unreachable and a `.harness/decisions.md` substring leg is vacuous post-promotion (codex regress r2 MAJOR). The prose overage-discipline clause is unchanged; the pin is strictly stronger (any drift reds). Doc updated per OPERATING.md's update-the-doc rule; codex finding resolved by contract unification, not overruled.

### Finalize r2 — codex P1 overrule (AC13 ledger message)
Codex round-2 flagged test_sloc_cap_or_exact_reviewed_overage (test:66) as an "unauditable pin"
because the `drive-retro SLOC overage` decisions.md entry it names is absent from committed branch
d04355cf. OVERRULED with evidence: (a) the assertion is a pure line-count check (n<=150 OR n==183)
that passes and does not read the ledger; (b) the `### drive-retro SLOC overage` entry exists at
$RUN_DIR/decisions.md (the run ledger) and drive-ship promotes it into .harness/decisions.md at
ship — codex inspected the PRE-promotion branch (ledger promotion is a ship-time step by design);
(c) the message's guidance to update that entry on a re-review is correct post-ship. Not fixed.
Classification: Mechanical (adversarial finding refuted at the integrated/ship path).


## /drive run main-20260705-130712 — wire /drive-retro into Completion (promoted at ship 2026-07-05T14:24:36Z)


## D1 — Make the wrap-decant explicit in Completion (not just implied by OPERATING.md)
Classification: Mechanical.
The Completion section today never names the standing wrap-`/decant`; it is only
implied by OPERATING.md's standing rule (and referenced from I1 step 5.5). To make the
retro→decant ORDERING load-bearing and pin-able, the Completion edit wires BOTH steps
explicitly and in order: `/drive-retro <runId>` first, then the standing wrap-`/decant`.
Principle: explicit-over-clever + completeness (an ordering you can't pin isn't enforced).

## D2 — Invert the existing negative pin rather than delete it
Classification: Mechanical.
`test_drive_md_does_not_reference_drive_retro` currently asserts drive.md does NOT
reference `/drive-retro` (v1 manual). Wiring retro in REDS it. Replace it with a POSITIVE
wiring pin (retro referenced inside Completion, ordered before the wrap-decant, gated on
done) so the contract keeps guarding the wiring instead of forbidding it. The data-driven
`test_drive_command_refs.py` needs no fixture change (drive-retro.md already exists).

## D3 — Gate the wrap sequence on the terminal-done signal, not on section position
Classification: Mechanical.
Completion runs retro→decant ONLY when the run is truly done (`completedAt` present OR
`state.stage=="done"`) — the same authority retro's own completeness gate uses. A run that
STOPs before done never reaches this terminal state, so both retro and the wrap-decant are
correctly skipped; the per-seam I1 step-5.5 rebirth decant stays retro-free.
# Decisions — main-20260705-130712 (wire /drive-retro before wrap-decant)

## D-0 (Stage 0) — premise clear, no clarification
Premise = TODO.md:134 (wire /drive-retro into /drive Completion, before wrap-decant, at true
run-wrap). Unambiguous; proceeded to plan without a premises AUQ.

## Plan decisions (design.md D1-D4)
- D1 (Mechanical) — name BOTH wrap steps explicitly in Completion (retro then /decant) so
  retro-first ordering is load-bearing + pin-able.
- D2 (Mechanical) — invert test_drive_md_does_not_reference_drive_retro into a positive
  section-bound wiring pin (keep a guard, don't delete).
- D3 (Mechanical) — gate the wrap sequence on terminal-done (completedAt OR stage=="done"),
  the same authority retro's completeness gate uses; STOPped runs skip both retro + wrap-decant.
- D4 (Mechanical; BOTH design-review voices round 1, consensus P1) — EXPAND scope to refresh
  drive-retro.md's now-false invocation-status claims (frontmatter "Not invoked by /drive (v1)"
  + role paragraph "named follow-on, not built") AND update the role-paragraph pin (test:353),
  in this run. Leaving them stale ships a self-contradicting command contract + a string pin
  enforcing the false claim (callee must match caller's asserted contract). Behavior/contract of
  retro unchanged; only invocation-STATUS prose moves. In blast radius, trivial effort.

## Phase-1 design decisions (design-phase1.md)
- D5 (Mechanical) — MOVE the SLOC pin (`REVIEWED_OVERAGE_LINES` 183→184) + the
  `.harness/decisions.md` `### drive-retro SLOC overage` ledger note TOGETHER, rather than
  squeezing the status reword back into 183 lines. The accurate reword is ~60 chars longer
  (adds "completed-run-only", "auto-invoked at the true run-wrap", "still operator-invocable",
  "wired into drive.md Completion"); the role paragraph goes 7→8 physical lines → file 184.
  Packing to 183 forces contrived >100-col lines / a brittle future-reflow hazard; the pin's
  own comment invites moving pin+ledger together (explicit-over-clever + pragmatic). Only test
  line 66 is load-bearing (the ledger OR-leg was already removed, decisions.md:3197); the
  ledger note is documentation hygiene. Expands slice 1.1's owned files to include
  `.harness/decisions.md`.
- D6 (Mechanical; review r2, both voices + verified P1) — EXPAND the drive.md edit boundary
  from "Completion only" to add explicit routes from BOTH terminal-done sites into the
  `## Completion` wrap sequence: Stage 5's ship line (Edit 1b) AND the Done-via-resume teardown
  step 5 (Edit 1c). The r1 Completion-only resolution was WRONG — the resume teardown lands
  `stage="done"` and RETURNS with no rule routing it into Completion (referenced nowhere else;
  Stop hook ends the turn at stage=done), so retro→decant would silently never fire for
  resume-completed runs. Both routes are in-file drive.md edits (same shared-contract unit →
  still ONE slice); the wiring pin is strengthened to bind both routes. Supersedes the r1 OQ2
  "Completion-only / no edit outside Completion" note.
- OQ2 resolved (design-phase1.md r2): the wrap sequence is DEFINED once in `## Completion`
  (retro → wrap-/decant → Report), gated on terminal-done as a defensive confirmation, and BOTH
  terminal-done sites (Stage 5 ship line + resume teardown step 5) EXPLICITLY route into it — a
  control-flow guarantee, not adjacency inference.
- D7 (Mechanical; review r3, both voices + Claude P1-B) — REORDER Path B (resume Done-via-resume
  teardown) so the retro→decant wrap runs BETWEEN step 4 (`completedAt` written — already
  satisfies retro's completeness gate) and the new final step (`stage="done"` written LAST). In
  that pre-`stage=done` window, with `waiting` empty, the stop-hook FORCES the coordinator
  forward, so the wrap is GUARANTEED to complete before turn-end — closes r2's post-done drop
  window with zero new machinery (pure sequencing). Path A (normal ship) keeps its post-done
  wrap via `## Completion` after drive-ship returns (same turn, immediately post-Gate-B, no
  seam); documented HONESTLY as a tolerated best-effort characteristic (interrupted-mid-wrap
  drop recovered ONLY by a manual re-run, NOT automatic §I1 recovery). Path A's symmetric
  ship-side reorder deferred to followups.md (drive-ship.md scope, out of this slice — task
  excludes drive-ship.md internals). Also (P1-A) the wiring pin is tightened: ordering anchored
  on the `/drive-retro <runId>` INVOCATION (not the possessive), and each route leg anchored to
  its ACTUAL line with `route_idx < write_idx` — mutation-verified (delete/reorder either route
  edge reds). Supersedes r2's post-done both-route framing. Still ONE slice.
- D8 (Mechanical; phase-review codex BLOCKING, confirmed) — The Completion done-gate wording
  tightened from "completedAt exists" to "parseable completedAt" to match the REAL contract:
  `is_done()` in `bin/drive-retention.sh` and retro's §2 completeness gate require a PARSEABLE
  `completedAt` (or `stage == "done"`), NOT mere file existence — an existing-but-unparseable
  marker does NOT authorize done. Applied to `## Completion` gate prose (Edit 1a) and the
  Done-via-resume teardown step 5 (Edit 1c), and the wiring pin strengthened with an
  `assert "parseable" in comp` so a future exists-vs-parseable regression reds (mutation-verified).
## Run drive-ctx-summary-20260705-035515 (2026-07-05) — context-of-execution summary + /goal removal


## D1 — ONE phase / one slice
- **Classification:** Mechanical
- Shared-contract spec (`drive.md`, `drive-plan.md`) + its string-pin tests
  (`test_rebirth_handshake.py`) + descriptive docs must move together; heavy same-file
  overlap between the two changes; no disjoint file ownership (no fan-out), no
  foundation-before-dependents (no staged-risk). Splitting risks a contract failing to transfer.

## D2 — Summary structural home = new shared step
- **Classification:** Taste (recommend; surface at Gate A)
- Add `## Emit context-of-execution summary (shared step)` to `drive.md`, sibling to
  `Emit run graph`, data-driven from the SAME durable sources (state.json / design.md /
  review artifacts / decisions.md), never event-log. Rejected inline-duplication at each site
  (DRY) and rejected folding into the run-graph section (distinct medium: prose vs ASCII chart).

## D3 — Emit at both fresh-session points
- **Classification:** Taste (recommend)
- Emit at the outgoing rebirth handoff (Present human pause step 3 / I1 step 6) AND the incoming
  resume (§ Run setup & resume). One handoff block serves Seam A + Seam B + context-pressure.
  Scope the resume emission to fresh-session resumes (`sessionId` changed) — a same-session
  re-paste already has context.

## D4 — Propagate `/goal` removal into descriptive docs
- **Classification:** Mechanical (completeness / DRY)
- Reconcile `CLAUDE.md`, `README.md`, `docs/flow.md`, `docs/drive-enforcement.md` in the SAME
  unit so no doc describes a removed mechanism (no dangling reference remains).

## D5 — Test blast radius of `/goal` removal
- **Classification:** Mechanical
- DELETE the goal-mechanism pins: AC7 (`test_goal_rebirth_pause_clause_single_sourced_in_drive_md`
  + `_assert_goal_rebirth_pause_consistent` + `_GOAL_REBIRTH_PAUSE_CLAUSE`) and the three AC12
  tests (`test_handoff_block_goal_line_carries_leg_condition_placeholder`,
  `test_leg_condition_selector_is_total_over_stage_enum`,
  `test_leg_condition_selector_maps_each_leg_to_its_own_condition`) with their helpers/consts
  (`_handoff_goal_line`, `_leg_selector_section`, `_LEG_BULLET_RE`, `_STAGE_TOK_RE`,
  `_STAGE_ENUM`, `_leg_bullet_map`, `_assert_leg_condition_mapping`, `_PLANNING_*`, `_EXECUTE_*`).
- UPDATE AC8 (`test_gate_precedence_gateA_emits_resume_via_seam_a`) + matching drive.md prose:
  Gate A emits the `/drive <runId>` resume line via Seam A but NO goal; Gate B hands neither.
- PRESERVE every rebirth/checkpoint pin (AC1, P1-2 wiring, AC4, AC9, AC11, cross-file steer) —
  none depends on `/goal`.

## D6 — Preserve AC4 bullet indices + AC1 step numbers
- **Classification:** Mechanical (test-safety constraint carried into detailed design)
- A new resume-path summary sub-bullet must sit at index ≥ 3 (AC4 reads bodies[0]=rebind,
  [1]=marker-consume, [2]=rebirth-continue). Do not renumber I1 steps 1–5.5 (AC1 pins marker=4,
  waiting=5, adjacent).

## D7 (Taste) — skip full autoplan; dual-voice design review is the review bar
This is a spec-doc change to /drive with no product/UX/DX surface autoplan (CEO→Design→Eng→DX)
is built to review. Two independent adversarial voices (Claude reviewer + codex) converged in
2 rounds after codex surfaced and we resolved 2 real P1s. Treating that convergence as Gate A's
review bar; skipping the full autoplan run. Surfaced at Gate A for override.
Classification: Taste.

## D8 (Taste) — continue Execute in-session; skip the Seam A context-clear handoff
Seam A/B are context-management mechanisms (fresh context per leg for long runs). This run's
coordinator context is far from pressure and the change is one small phase, so a forced
context-clear + manual `/drive <runId>` paste is ceremony with no benefit — and would demo the
pre-edit /goal handoff anyway. Continuing Execute in-session; the Stop hook still governs
turn-to-turn autonomy. Classification: Taste.

## D9 (Mechanical) — summary section placement
New `## Emit context-of-execution summary (shared step)` is a `## ` sibling inserted AFTER the
whole `## Emit run graph` section (after Worked example B) and BEFORE `## Pipeline` — not a
`### ` child of the run-graph section. Classification: Mechanical.

## D10 (Taste; recommend) — outgoing summary ABOVE the chart, wired at Present-human-pause step 2
Resolves design.md open-question #2 → summary ABOVE the run-graph chart (narrative-first). Wired
by a rebirth-scoped clause added to Present human pause **step 2** (keeps step numbering intact —
AC1 untouched), so the summary emits only when `waiting=="rebirth"` and prints before the chart;
I1 step 6 gets a descriptive echo only (single executor, no double emission). Classification: Taste.

## D11 (Mechanical) — resume emission = trailing sub-bullet + ephemeral fresh-session flag
The incoming-resume emission is a NEW indented resume sub-bullet placed LAST (after "Counter
reconstruction", before "- **Fresh run:**") — index ≥ 3, so AC4's bodies[0/1/2] indices are
preserved (D6 hard constraint honored). Chose a trailing bullet over a loose paragraph for
testability (section-bounded, pinnable). Fresh-session scoping reuses the sessionId-rebind step's
existing `state.sessionId != $CLAUDE_CODE_SESSION_ID` predicate, captured as an EPHEMERAL
coordinator variable (`freshSessionResume`) — NO new persisted state.json field. Classification:
Mechanical (with a minor surfaced taste point: bullet vs paragraph).

## D12 (Mechanical) — reworded Autonomous-continuation contract gets its own positive pin
Beyond the AC-6 removal grep, add `test_autonomous_continuation_contract_states_hook_sole` so the
rewrite is positively pinned (installed-hook-sole + hook-absent manual-continue degradation, no
`/goal`), while the preserved L332–336 dual-nature paragraph keeps AC11 green. Repurpose the
orphaned `_handoff_block` accessor for the AC5 paste-block pin rather than deleting it.
Classification: Mechanical.

## D13 (Mechanical) — followups.md L266–267 marked SUPERSEDED, not deleted
The Phase-4 `/goal` cross-command clause follow-up is mooted by the full `/goal` removal; annotate
it SUPERSEDED in place (history preserved) so no later work re-introduces the mechanism.
Classification: Mechanical (completeness/DRY).

## D14 (Mechanical) — site-15 reworded to keep AC-6 grep clean
design-phase1.md §1.4 site 15 prescribed replacing the drive-enforcement.md L447-449 text with
prose ending "no `/goal` anywhere (the installed Stop hook drives turn-to-turn continuation)".
That literal `/goal` token would RED the AC-6 heightened-review grep (`rg '/goal\b'` over
docs/), which permits only the incidental `drive-design.md:24 boundary/goal` hit. Reworded to
"no goal is handed at any gate (the installed Stop hook drives turn-to-turn continuation)" —
same meaning, zero `/goal` token. The grep (the load-bearing acceptance net) outranks the
prescribed prose. Classification: Mechanical.

## D15 (Mechanical) — rebase-at-ship onto main #62 + reviewed-sha re-bind
Main advanced to 0b13c65 (#62 Trellis analysis + /drive-retro) after this run's baseRef 9beeac4.
Rebased featureBranch onto 0b13c65 (clean — my core spec files have zero overlap with #62; only
.harness/followups.md overlapped and auto-merged into disjoint regions, verified). AC-6
anti-reintroduction pin re-verified GREEN with #62's docs/trellis-analysis.md (4 historical /goal
refs, carved out) and drive-retro.md (no /goal) present. Re-bound finalize reviewed-sha to the
post-rebase code tip 8d7696dd860d50880a2b3f0710a693be2220a2f4 (content byte-identical; per drive-ship-conformance-sha-binding).
Classification: Mechanical.
