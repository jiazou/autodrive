# TODO

Architectural follow-ups deferred by /drive finalize passes.

## Fable 5 / Claude 5 harness compatibility audit (2026-07-03)

12 verified findings from a 33-agent audit (8 subsystem readers → 74 raw findings →
12 deduplicated candidates → 2 adversarial verify lenses each; none refuted). Baseline:
the current harness auto-summarizes context (sessions no longer hard-die), subagents run
in the background by default and are reliable, Workflow-tool orchestration + fresh-session
triggers exist, and the Claude 5 family is 1M-context.

**Framing (the strategic lens):** the model/harness now natively owns the *orchestration
mechanics* autodrive hand-rolls (spawn/parallelize/collect/retry) — that layer is the
redundant part to shed. What stays load-bearing is the *policy + verification* layer the
model cannot self-supply: git-truth omission-proof gates, independent second-voice review,
fail-closed ship gating, durable $RUN_DIR state, human gates A/B. Refactor direction:
autodrive stops micromanaging dispatch and becomes the verification harness around a
natively-orchestrating model.

### Tier 1 — wrong today, small fixes
- [ ] **C6 (P1/small)** drive-ship.md:133 hardcodes `Co-Authored-By: Claude Opus 4.8` into
  every shipped commit — sole occurrence, nothing pins it; make harness-agnostic.
- [ ] **C4 (P2/small)** Prose sweep: "Claude Code cannot self-initiate a fresh session"
  (CLAUDE.md, docs/flow.md, docs/drive-enforcement.md; decisions.md D3) is stale — reword
  as capability-conditional; annotate D3 premise-stale (don't rewrite); also fix the
  8-consecutive-block-cap comments in bin/drive-stop-guard.sh + bin/drive-stop-hook.py.
- [ ] **C2 (P2/medium)** bin/rebirth-thresholds.json maps bare "Sonnet" → 200k, but
  Sonnet 5 / Sonnet 4.6 are 1M models (rebirth steer would fire at ~17% real usage);
  claude-fable-5 gets defaultWindow=1M only by fallthrough (happens to be correct — 1M
  context, 128K output). Version-qualify the legacy 200k substrings, add verified
  Claude-5-family entries, keep statusline.sh inline fallback in sync (AC6), update the
  five pinned test files in ONE review unit. Sequence after C1.

### Tier 2 — correctness under the new harness
- [ ] **C9 (P2/small)** drive.md:437 in-session stranded-inflight-marker rule
  ("not actively awaiting" → adopt/re-dispatch) double-dispatches over LIVE background
  workers (background-default dispatch + auto-summarization can erase coordinator memory).
  In-session stranded must require positive worker-death evidence from the harness surface
  (completion notification / Monitor); at-resume rule unchanged; keep the
  test_checkpoint_contract.py pinned phrases.
- [ ] **C7 (P1/medium)** Enforcement gates are PreToolUse(Bash)-only
  (install-drive-hooks.sh:140): GitHub MCP write tools (create_pull_request, push_files,
  merge_pull_request, …) ship with the merge gate never firing, and Agent
  isolation:"worktree" / EnterWorktree create worktrees off the gated slice/<runId>/<id>
  refs — both omission-class bypasses of the gate chain's core guarantee. Add a sibling
  hook (distinct basename — the installer strips/re-appends drive-merge-gate.sh entries)
  that deny-routes MCP writes + native-worktree tools back to the canonical Bash paths
  while a drive run is active; extend install-drive-hooks.sh to manage it.

### Tier 3 — shed the dead-premise machinery (do C1 + C11 together)
- [ ] **C1 (P1/large)** Class-A context-pressure rebirth assumes sessions hard-die at
  context exhaustion — false under auto-summarization, which also breaks the token math
  (compaction drops the last-usage sum below the high-water mark; the one-way
  rebirth_pending latch goes stale → next crossing jumps to the ESCALATION handoff for
  pressure already relieved). Arm class A by the existing window match table (legacy 200k
  models keep it; unmatched/1M models disarm), add explicit override, then run the
  deferred leaner-rebirth-v2 cut. KEEP: class-B deterministic seams (lossless $RUN_DIR
  handoff > lossy auto-summary), /decant at boundaries, checkpoint/state-lint proofs,
  inflight-marker crash-safety, the /goal rebirth-pause clause (class B still uses it).
- [ ] **C11 (P3/small)** Demote the per-leg /goal ceremony (leg-condition table, re-arm
  choreography) to optional reinforcement — the harness now bakes in the autonomous
  continuation contract, and drive.md documents the Stop-hook contract as working without
  /goal. Must land with C1 (same AC7/AC12-pinned clauses in test_rebirth_handshake.py).
- [ ] **C5 (P2/small)** "Subagents bail ~50%" (OPERATING.md:44) is stale; relax
  codex-never-in-a-subagent to an either/or dispatch note AROUND the canonical fenced
  codex blocks (AC13 pins the mkdir/TMPDIR/redirect block text — do not rewrite it), and
  relax the 150-word digest cap.

### Tier 4 — exploit the new capabilities (opt-in, additive)
- [ ] **C3 (P1/medium)** Self-scheduled seam resume: at non-gate context-clear seams,
  feature-detect fresh-session triggers (create_trigger create_new_session_on_fire /
  send_later) and schedule `/drive <runId>` instead of requiring the human paste; the
  fail-closed resume path (single-use checkpoint marker + re-prove) is already
  initiator-agnostic. Keep the fenced ↻ REBIRTH block as the plain-CLI fallback,
  byte-for-byte; edit inside drive.md I1 step 6 only. Gates A/B stay human.
- [ ] **C12 (P3/medium)** Per-role model/effort hints (log-summarizer subagents =
  small/fast+low effort; adversarial reviewers = high effort) as capability-class prose,
  never hardcoded IDs; degraded second-voice tier when codex is unavailable (independent
  Claude reviewer, distinct first-line marker — NOT under CODEX_UNAVAILABLE, which the
  combined-verdict rule reads as "contributes zero"). Drop the ExitWorktree item.
- [ ] **C8 (P2/large)** Opt-in `/drive --workflow` backend for the Stage-2/3 slice layer:
  Workflow parallel() over implementers with schema-validated returns replaces the manual
  concurrencyCap loop + fragile `STATUS:` first-line contract. HARD preconditions: land
  C7 first; git topology (worktree add, merges, literal slice/<runId>/<id> refs) stays
  main-session Bash so the gates fire; one inflight marker per Workflow invocation;
  dual-voice loop crossing the Workflow boundary decided explicitly. Default OFF.
- [ ] **C10 (P3/large)** Component D (forgery-proof out-of-band reviewer) re-costed on
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
