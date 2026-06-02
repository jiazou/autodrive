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