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
