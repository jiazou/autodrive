# TODO

Architectural follow-ups deferred by /drive finalize passes.

## Trellis pattern adoption — from docs/trellis-analysis.md (2026-07-04)

- [ ] **TR-2 (S/L2)** Per-turn `<drive-state>` breadcrumb: a UserPromptSubmit hook reading
  `$RUN_DIR/state.json`'s real fields (runId, stage, phase, waiting) and deriving the expected
  next step from stage/phase (as the run-graph does), breadcrumb bodies pinned by a contract
  test — kills T-1 (coordinator drift corrected pre-violation,
  between gate denies; survives auto-summarization context loss); lands on `bin/` new hook +
  `bin/install-drive-hooks.sh` + `tests/contracts`; x-ref C11 (extend, not duplicate: C11
  trims /goal ceremony, TR-2 adds hook-supplied steering; land compatibly with C11's pinned
  clauses); rec detail: docs/trellis-analysis.md §Recommendations. **Trigger:** next /drive
  run that trips a coordinator-drift STOP, a merge-gate deny on a forgotten review, or a
  Stop-hook nag loop.

## Fable 5 / Claude 5 harness compatibility audit (2026-07-03)

12 verified findings (none refuted on a two-lens adversarial verify). Baseline: the
current harness auto-summarizes context (sessions no longer hard-die), subagents run in
the background by default and are reliable, fresh-session triggers exist (create_trigger
with create_new_session_on_fire), Workflow orchestration exists on some surfaces (verify
on the live harness), and the Claude 5 family is 1M-context.

**Framing:** autodrive is THREE layers. Each item below is tagged L1 or L3; layer 2 is
untouched by the audit, by design.
1. *Dispatch mechanics* (spawn/babysit/collect/retry loops, STATUS text contracts,
   flakiness workarounds, class-A context-pressure rebirth — class-B seams and the
   checkpoint proofs are layers 2–3 and stay) — natively owned by the harness; shed.
2. *Direction control* — premises → plan (Gate A) → per-phase design against the REAL
   prior-phase code → slice assumption check with REDESIGN escalation, plus fresh-context
   role separation (designer ≠ implementer ≠ reviewer; reviewer never sees implementer
   rationale). Keep — appreciates with model capability: cheap direction checks before
   expensive commitment; fresh-context checks beat self-critique.
3. *Verification + enforcement* — git-truth omission-proof gates, independent second
   voice, fail-closed ship gating, durable $RUN_DIR state, human gates A/B. Keep —
   layer 3 verifies the thing was built right; layer 2 verifies it's the right thing.
Refactor direction: shed layer 1 (C1 C2 C3 C5 C8 C9 C11 C12); keep and re-target
layer 3 (C4 C6 C7 C10) — the coordinator states contracts and checks direction at the
seams; the model/harness owns how work gets dispatched.

### Tier 1 — wrong today, small fixes
- [x] **C6 (P1/small/L3)** drive-ship.md:133 hardcodes `Co-Authored-By: Claude Opus 4.8` into
  every shipped commit — sole occurrence, nothing pins it; make harness-agnostic.
- [x] **C4 (P2/small/L3)** Prose sweep: "Claude Code cannot self-initiate a fresh session"
  (CLAUDE.md, docs/flow.md, docs/drive-enforcement.md; decisions.md D3) is stale — reword
  as capability-conditional; annotate D3 premise-stale (don't rewrite); also fix the
  8-consecutive-block-cap comments in bin/drive-stop-guard.sh + bin/drive-stop-hook.py.
- [x] **C2 (P2/medium/L1)** bin/rebirth-thresholds.json maps bare "Sonnet" → 200k, but
  Sonnet 5 / Sonnet 4.6 are 1M models (rebirth steer would fire at ~17% real usage);
  claude-fable-5 gets defaultWindow=1M only by fallthrough (happens to be correct: 1M).
  Version-qualify the legacy 200k substrings, add verified Claude-5-family entries, keep
  statusline.sh inline fallback in sync (AC6), update the
  five pinned test files in ONE review unit. Sequence after C1.

### Tier 2 — correctness under the new harness
- [ ] **C9 (P2/small/L1)** drive.md:437 in-session stranded-inflight-marker rule
  ("not actively awaiting" → adopt/re-dispatch) double-dispatches over LIVE background
  workers (background-default dispatch + auto-summarization can erase coordinator memory).
  In-session stranded must require positive worker-death evidence from the harness surface
  (completion notification / Monitor); at-resume rule unchanged; keep the
  test_checkpoint_contract.py pinned phrases.
- [x] **C7 (P1/medium/L3)** Enforcement gates are PreToolUse(Bash)-only
  (install-drive-hooks.sh:140): GitHub MCP write tools (create_pull_request, push_files,
  merge_pull_request, …) ship with the merge gate never firing, and Agent
  isolation:"worktree" / EnterWorktree create worktrees off the gated slice/<runId>/<id>
  refs — both omission-class bypasses of the gate chain's core guarantee. Add a sibling
  hook (distinct basename — the installer strips/re-appends drive-merge-gate.sh entries)
  that deny-routes MCP writes + native-worktree tools back to the canonical Bash paths
  while a drive run is active; extend install-drive-hooks.sh to manage it.
  *(closed: GitHub-MCP write class gated by bin/drive-tool-gate.sh; worktree claim resolved
  KEPT — recorded trace shows the harness-branch chain voids the plan/design + slice
  review/impl-presence gates.)*

### Tier 3 — shed the dead-premise machinery (do C1 + C11 together)
- [ ] **C1 (P1/large/L1)** Class-A context-pressure rebirth assumes sessions hard-die at
  context exhaustion — false under auto-summarization, which also breaks the token math
  (compaction drops the token sum below the high-water mark and stales the one-way
  rebirth_pending latch). Arm class A by the existing window match table (legacy 200k
  models keep it; unmatched/1M models disarm), add explicit override, then run the
  deferred leaner-rebirth-v2 cut. KEEP: class-B deterministic seams (lossless $RUN_DIR
  handoff > lossy auto-summary), /decant at boundaries, checkpoint/state-lint proofs,
  inflight-marker crash-safety, the /goal rebirth-pause clause (class B still uses it).
- [ ] **C11 (P3/small/L1)** Demote the per-leg /goal ceremony (leg-condition table, re-arm
  choreography) to optional reinforcement — the harness now bakes in the autonomous
  continuation contract, and drive.md documents the Stop-hook contract as working without
  /goal. Must land with C1 (same AC7/AC12-pinned clauses in test_rebirth_handshake.py).
- [ ] **C5 (P2/small/L1)** "Subagents bail ~50%" (OPERATING.md:44) is stale; relax
  codex-never-in-a-subagent to an either/or dispatch note AROUND the canonical fenced
  codex blocks (AC13 pins the mkdir/TMPDIR/redirect block text — do not rewrite it), and
  relax the 150-word digest cap.

### Tier 4 — new-capability adoption (opt-in, staged)
- [ ] **C3 (P1/medium/L1)** Self-scheduled seam resume: at non-gate context-clear seams,
  feature-detect fresh-session triggers (create_trigger with create_new_session_on_fire —
  send_later is same-session, not a seam) and schedule `/drive <runId>` instead of
  requiring the human paste; the fail-closed resume path (single-use checkpoint marker +
  re-prove) is already initiator-agnostic. Keep the fenced ↻ REBIRTH block as the
  plain-CLI fallback, byte-for-byte; edit inside drive.md I1 step 6 only. Gates A/B
  stay human.
- [ ] **C12 (P3/medium/L1)** Per-role model/effort hints (log-summarizer subagents =
  small/fast+low effort; adversarial reviewers = high effort) as capability-class prose,
  never hardcoded IDs; degraded second-voice tier when codex is unavailable (independent
  Claude reviewer, distinct first-line marker — NOT under CODEX_UNAVAILABLE, which the
  combined-verdict rule reads as "contributes zero").
- [ ] **C8 (P2/large/L1)** Opt-in `/drive --workflow` backend for the Stage-2/3 slice layer:
  Workflow parallel() over implementers with schema-validated returns replaces the manual
  concurrencyCap loop + fragile `STATUS:` first-line contract. HARD preconditions: verify the
  orchestration primitive (Workflow parallel() + schema returns) on the live harness;
  land C7 first; git topology (worktree add, merges, literal slice/<runId>/<id> refs) stays
  main-session Bash so the gates fire; one inflight marker per Workflow invocation;
  dual-voice loop crossing the Workflow boundary decided explicitly. Default OFF.
- [ ] **C10 (P3/large/L3)** Component D (forgery-proof out-of-band reviewer) re-costed on
  native primitives: opt-in ship-mode predicate requiring an independent-session review
  whose provenance comes from harness-owned evidence (Workflow journal / trigger firing
  records), NOT a $RUN_DIR file the coordinator can write. Append a new dated
  followups.md entry (keep :27 intact); with the marker absent, ship mode stays
  byte-identical (141 ship pins across 4 bash suites stay green).

Full audit with per-candidate evidence and both lens verdicts: session artifact
`fable5-compat-audit.md` (2026-07-03).

## /drive run drive-retention-hygiene-20260622T073209 — architectural follow-ups (2026-06-23T18:50:09Z)
- bin/drive-retention.sh + .claude/commands/drive.md + .claude/commands/drive-ship.md +
  tests/contracts/test_drive_retention*.py — the retention/teardown contract (done-signal,
  completedAt-after-proven-removal gate, Tier-W/Tier-L eligibility) is expressed in THREE
  authority layers: the executable policy (bin/drive-retention.sh), the lifecycle prose
  (drive.md §E + drive-ship.md "After approval"), and large string-pin contract tests. They can
  drift independently (the round-1 finalize audit's own done-signal confusion is an instance of
  reading one layer without the others). Out of THIS run's blast radius to unify; consider a
  single machine-checked source of truth (e.g. generate the doc-pinned tokens from the script, or
  a single contract fixture both the script and docs are checked against) in a dedicated follow-up.

## /drive run todo-triage-20260704T135831 — architectural follow-ups (2026-07-05T14:14:46Z)

- **bin/install-drive-hooks.sh `is_managed` — spaced-path cross-checkout duplicate.** A
  cross-checkout re-run from a space-containing checkout path leaves stale managed entries
  un-stripped → duplicate hooks with no drift WARN. Pre-existing (on origin/main before this
  run's C7 work), affects the merge-gate + stop-guard identically. Loosening the
  metachar/`$cmd == $full` collapse matcher is a security-sensitive change needing its own
  adversarial find-the-bypass review. Already recorded in followups + decisions D-coord-4;
  listed here to discharge finalize's TODO-routing duty. Out of this run's diff — not fixed.
- **bin/drive-tool-gate.sh — ungated Bash `gh pr merge`/`gh pr edit` twins + GitLab-MCP writes.**
  The MCP `merge_pull_request`/`update_pull_request` denies close the MCP omission path, but
  their Bash `gh pr merge`/`gh pr edit` twins stay ungated (drive-merge-gate.sh gates only
  `pr create`/`mr create`), and GitLab-MCP write tools are the same bypass class under different
  names, uncovered by the GitHub-named matcher. Deliberate, decision-logged asymmetry (the deny
  wording states it truthfully); named residuals in followups. Decide in a follow-up, not a code
  fix here.
- **bin/statusline.sh + bin/rebirth-thresholds.json — duplicated window table.** The deployed
  statusline is symlinked away from its `rebirth-thresholds.json` sibling, so the window
  "single source of truth" is actually a duplicated inline `case` table (statusline.sh:34-38)
  requiring dual maintenance with the json. AC6 pins them to identical numbers as an accepted
  stopgap; the durable fix (a single source resolved at deploy time) is deferred (codex ARCH).
# Finalize TODO routing (promoted to repo-root TODO.md at ship)

- **Wire `/drive-retro` into the run-wrap sequence, ordered BEFORE the wrap-decant**
  (user-directed, 2026-07-05). At the TRUE run-wrap only (after Gate B, once
  `completedAt` / `stage=done` exist — retro's completeness gate requires a finished
  run): `/drive` Completion runs `/drive-retro <runId>` first, then the standing
  wrap-`/decant`, so retro's classified proposals in `retro-<runId>.md` are on disk as
  INPUT EVIDENCE for decant's survey/promotion pass. Per-seam rebirth decants (I1
  step 5.5) are unaffected — retro cannot run mid-run. Touches drive.md's Completion
  step (string-pin contract tests apply). Supersedes the bare "automatic run-wrap
  wiring" line in followups.md by adding the ordering contract.

## /drive run main-20260704-180725 — architectural follow-ups (2026-07-05T04:10:44Z)

- **`.claude/commands/drive-retro.md` + `tests/contracts/test_drive_retro_contract.py`** — the
  feature's hard part is an algorithmic spec (tolerant stream-JSON decode, Rule-U line-level
  extraction, recurrence grouping, proposal routing), but v1 deliberately ships PROSE + STRING
  PINS only (TR-3's stated "no shipped code" boundary; DP2-23/AC17). Residual risk (codex ARCH,
  finalize r1): the most failure-prone semantics can drift while all string-pin tests stay green —
  there is no fixture-driven behavioral oracle over sample $RUN_DIR artifacts. Follow-on if
  /drive-retro grows an executable extractor (the DP2-5 `bin/drive-retro-stats.py` path): add a
  golden-fixture oracle over a captured $RUN_DIR so the extraction contract is behaviorally, not
  just lexically, pinned. Out of this run's scope (would breach the no-shipped-code boundary).

## 2026-07-05 — drive-ctx-summary run (finalize follow-ups)


Architectural / out-of-scope findings routed at the finalize stage (NOT fixed in-run;
promoted to repo-root TODO.md at ship).

- [P3][docs/test-accuracy] `tests/contracts/test_rebirth_handshake.py` module docstring
  (line ~18) claims "Each load-bearing pin is proven to RED against a mutated COPY … in the
  accompanying `test_*_flips_on_*` cases." No function in THIS file follows that naming
  convention — the pins are inline section-bounded string-pins, and the `*_flips_on_*`
  mutation-proof convention actually lives in sibling `test_checkpoint_contract.py`. This
  inaccuracy is PRE-EXISTING (byte-identical in base 9beeac4), not introduced by this run —
  hence routed, not fixed here. Fix: either add per-pin mutation-proof `test_*_flips_on_*`
  cases for the load-bearing pins, or reword the docstring to describe the actual
  inline-string-pin methodology. Out of the whole-run diff's introduced surface.

## /drive run c7-gate-bypass-20260705-225936 — architectural follow-ups (2026-07-06T08:19:47Z)
- bin/drive-tool-gate.sh (MCP repo-scoping, ~line 344-356): the GitHub/GitLab MCP write
  scoping matches owner/repo only and is FORGE-HOST-BLIND, because the MCP tool_input exposes
  no forge host. Consequence: an owner/repo collision across forges (e.g. github.com/acme/x
  active-run vs a gitlab.com/acme/x MR) over-denies (safe direction, recoverable route-to-Bash),
  and real project_id-only GitLab payloads fail-closed-deny. Distinguishing gitlab.com from
  gitlab.internal from foo/bar is impossible from current hook input alone. Out of scope for
  this run (needs a richer hook input contract / managed tool policy). Related: the existing
  "G2 vendor-schema drift" followup.
- bin/drive-hook-lib.sh / drive-tool-gate.sh / drive-worktree-gate.sh (shared active-run
  predicate): the fail-closed PRECONDITIONS around drive_scan_active_runs (scan-tool present,
  runs-root readable) are NOT centralized — drive-worktree-gate.sh hardens them locally,
  drive-tool-gate.sh (shipped) does not. Centralizing the fail-closed guard into the shared
  predicate (or a shared wrapper) would close the residual shipped-tool-gate fail-open uniformly.
  Forgery-class; out of scope for this omission-focused run. Pairs with the deferred
  "harden shipped drive-tool-gate.sh fail-closed" followup.
