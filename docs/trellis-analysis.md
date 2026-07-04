# Trellis × autodrive — comparative analysis & recommendations

- Trellis pinned SHA: dddeb6e0d701ea53fd22ef98e1233dcd2a14ac70 (2026-07-02)
- Permalink base: https://github.com/mindfold-ai/trellis/blob/dddeb6e0d701ea53fd22ef98e1233dcd2a14ac70/
  (all trellis citations below are repo-relative paths against this base)
- Licenses: trellis AGPL-3.0 · autodrive MIT — see §License boundary
- review-by: 2027-01-04 (re-verify claims against trellis HEAD or archive this doc)
- Analyzed: autodrive @ 9beeac42515fa8ec78df3ea5ad7fcd979c2eecdd

## How to read this

**Tiers** used in every verdict and recommendation:
- **adopt-pattern** — reimplement the idea in autodrive, clean-room from THIS doc's descriptions (§License boundary).
- **run-alongside** — use the released `@mindfoldhq/trellis` npm tool, unmodified, next to autodrive.
- **ignore** — evidenced non-adoption; the negative verdict is a first-class result.
- **wait** — real idea, wrong time; a named condition re-opens it.

**Depth tiering:** deep = dimensions 1, 2, 5, 6 (full mechanism trace); compact = 3, 4, 7, 8 (a
few paragraphs, hypothesis tested, verdict). Depth ≠ adopt — a deep dimension may verdict
*ignore*.

**Triggering problems** (every recommendation names the pain it kills, or is tiered *ignore*):

| ID | Pain (autodrive-side) |
|---|---|
| T-1 | Coordinator drift — the coordinator forgets/deviates from drive.md mid-run (the reason docs/drive-enforcement.md exists) |
| T-2 | Handoff/ceremony weight — context-clear handoffs cost manual paste + /goal re-arm (TODO C1/C3/C11 already scope fixes) |
| T-3 | Learning-loop latency — memory promotion is end-of-session (/decant) and skippable |
| T-4 | Sub-agent context assembly — "pass paths, not contents" is a prose invariant the coordinator can violate silently |
| T-5 | No trace-to-harness feedback loop — rich structured `$RUN_DIR` traces and session transcripts go unmined for harness-optimization signal (user-elevated at Gate A, D-12) |

Layer tags reuse TODO.md's three-layer framing: **L1** dispatch mechanics (harness absorbs; recs
default *ignore*/*wait*), **L2** direction control, **L3** verification + enforcement.
Classification is by the layer a rec SERVES, not the mechanism's origin.

## 1. Context/spec injection

depth: deep · hypothesis: hook-injected scoped context materially beats static imports + prompt-passed paths — or is L1 plumbing the harness absorbs · addresses: T-1, T-4

**Trellis mechanism.** Trellis wires three context-injection hooks for Claude Code in
`packages/cli/src/templates/claude/settings.json`: `SessionStart` (matchers
`startup`/`clear`/`compact`) → `session-start.py`, `UserPromptSubmit` →
`inject-workflow-state.py`, and `PreToolUse` on `Task`/`Agent` → `inject-subagent-context.py`. The
implementing scripts live in `packages/cli/src/templates/shared-hooks/`. `session-start.py`
injects a compact current-state block (developer, git state, active tasks) plus **spec-index
pointers, not bodies** — `_collect_spec_index_paths()` returns
`.trellis/spec/<pkg>/<layer>/index.md` *paths*, and the emitted context lists them for on-demand
reading rather than inlining content: a deliberate context-budget choice. Scoped guidelines live
under `.trellis/spec/<package>/<layer>/index.md`, fetchable stepwise via
`packages/cli/src/templates/trellis/scripts/get_context.py`.

**Autodrive counterpart.** Static imports (`CLAUDE.md` imports `OPERATING.md`; the machine-global
`~/CLAUDE.md` imports the same file) plus prompt-passed absolute `$RUN_DIR` paths, per the
invariant "Pass file **paths** between subagents, not file contents" (CLAUDE.md §Invariants).
There is no per-session assembly step: the harness itself loads project/user memory at session
start.

**L1-absorption question, answered.** The injection *plumbing* is already absorbed: trellis's own
mechanism is built entirely on the harness's native hook API (`SessionStart`, `UserPromptSubmit`,
`PreToolUse` are Claude Code surfaces), and the harness natively performs session-start context
assembly (CLAUDE.md/import chains, auto-memory, skills). Replicating a `session-start.py` for
autodrive would re-implement what the platform already does at session start — L1, absorption risk
high. What is NOT absorbed is trellis's *content discipline* — pointers-not-bodies, per-package
scoping — but autodrive already practices exactly that discipline through its paths-not-contents
invariant and `$RUN_DIR` layout. The marginal value of adopting the injection mechanism for
*static* context is nil.

**Verdict:** *ignore* for session-start/spec injection (TR-1) — the plumbing is the harness's, the
discipline is already ours. The one genuinely differentiated use of this hook family — per-turn
*state* (not spec) injection — is dimension 2's subject, where the content is autodrive-specific
and not absorbable.

## 2. Per-turn state steering

depth: deep · hypothesis: a `<workflow-state>` breadcrumb keyed off `state.json.stage` would harden drive.md adherence pre-violation (vs Stop-hook post-hoc + /goal) · addresses: T-1

**Trellis mechanism.** `packages/cli/src/templates/shared-hooks/inject-workflow-state.py` runs on
every user prompt. It resolves the active task, reads `task.json.status`, and emits a short
`<workflow-state>` block whose body is parsed from `[workflow-state:STATUS]` tag blocks embedded
in `packages/cli/src/templates/trellis/workflow.md` — the single source of truth; the script
deliberately has **no fallback dict**, degrading to a generic pointer-at-workflow.md line so a
broken workflow.md is visible rather than masked. Two properties are load-bearing:

1. **Pre-violation timing.** The breadcrumb arrives *before* the model acts each turn, telling it
which phase it is in and which required steps apply — versus catching a deviation after the fact.
2. **A partially test-pinned prompt-layer contract.** workflow.md's embedded contract comment
asserts a general invariant — every walkthrough step marked `[required · once]` must be reflected
in its phase's `[workflow-state:*]` block, on the stated grounds that the breadcrumb is the sole
per-turn channel and a mandatory step absent from it gets silently skipped; the comment attributes
two historical step-skip bugs (a planning-gate skip and a commit-step skip) to exactly that gap.
What `packages/cli/test/regression.test.ts` mechanically enforces is **narrower** than that
comment: it pins the two historically-bitten instances (the in_progress block must mention the
Phase-3.4 commit step; the planning block must mention the artifact gates and manifest curation)
plus block presence and generic-degradation behavior — no test iterates the required steps, so the
universal mapping is the comment's self-description, not test truth (E1 correction: design.md and
an earlier draft of this section relayed it as test-enforced). Trellis also documents its own
dead code honestly: the
`[workflow-state:completed]` block never fires because `task.py archive` flips status and moves
the directory in the same call.

**Autodrive counterpart.** Steering is (a) drive.md prose read at run start, (b) the Stop hook
(`bin/drive-stop-hook.py`) — which fires only when Claude *stops*, i.e. post-hoc, feeding back a
continuation instruction, (c) the human-pasted per-leg `/goal`, and (d) the PreToolUse deny gates
(`bin/drive-merge-gate.sh`), which block specific *transitions* but say nothing turn-to-turn.
Between a gate deny and a stop, a drifting coordinator gets zero mid-flight correction. Under
auto-summarization, drive.md's instructions can also fall out of the effective context mid-run —
exactly when a per-turn breadcrumb would re-anchor them (TODO C9 documents the hazard:
auto-summarization can erase coordinator memory mid-run).

**Analysis.** The hypothesis survives: the mechanisms are complementary, not competing.
Autodrive's gates are *enforcement* (L3, deny at the boundary); the breadcrumb is *direction* (L2,
steer before the boundary is ever hit). A `<drive-state>` block reading `$RUN_DIR/state.json`'s real
fields (runId, stage, phase, per-slice steps, `waiting`) and deriving the expected next step from
stage/phase — the same derivation the run-graph makes — is cheap to compute; the
state file already exists precisely so that context loss cannot destroy run state. The harness
owns the `UserPromptSubmit` surface (absorbed plumbing), but the *content* — autodrive's run-state
semantics — is not plausibly absorbable. Trellis's instance-pinning practice maps directly onto
autodrive's existing contract-pin practice (`tests/contracts` string-pins over drive*.md) — and an
autodrive implementation can go one better than trellis's comment-only universal claim by
mechanically pinning coverage itself: a contract test that iterates drive.md's pipeline stages and
asserts each has a breadcrumb body.

**Verdict:** *adopt-pattern* (TR-2): S-effort, kills T-1 pre-violation, lands on `bin/` +
`bin/install-drive-hooks.sh` + a contract test. Runner-up for Phase-2 selection (see
§Recommendations).

## 3. Task/run state model

depth: compact · hypothesis: `.trellis/tasks/` status machine + PRD/design/implement tiering offers nothing autodrive's `$RUN_DIR` + three design tiers lack · addresses: T-2

Trellis tasks live in `.trellis/tasks/<MM-DD-name>/` with a `task.json` status machine (`planning`
→ `in_progress` → `completed` at archive; schema in `packages/core/src/task/schema.ts`), artifact
tiering (`prd.md` always; `design.md` + `implement.md` required only for complex tasks —
`packages/cli/src/templates/trellis/workflow.md` §Planning Artifacts), parent/child task trees
(`parent` field; explicitly *not* a dependency system), and lifecycle hooks
(`task.json.hooks.after_create/start/finish/archive`, workflow.md §Customizing Trellis).
Autodrive's `$RUN_DIR/state.json` carries a strictly richer run model (per-slice steps and review
counters, per-phase design/review/harden status, redesign epochs, budget), the event-log timeline
covers what lifecycle hooks would, and the three design tiers (whole-run plan → per-phase detailed
design → per-slice assumption check) are a direct, deeper analog of PRD/design/implement tiering.
Parent/child trees ≈ phases/slices with file-ownership.

The hypothesis **holds** with one instructive nuance: trellis's tiering is *stakes-adaptive within
the workflow* (a lightweight task legitimately stays PRD-only), whereas an autodrive run always
carries the full pipeline weight — that observation feeds dimension 4's economics lens, not a rec
here. **Verdict:** *ignore* — no rec; autodrive's state model is a superset for its use case.

## 4. Verification & enforcement + economics

depth: compact · hypothesis: (i) autodrive's enforcement is strictly stronger (FALSIFY); (ii) the rigor's per-invocation cost is justified at all task stakes (FALSIFY) · addresses: T-2

**Enforcement.** Trellis verifies via a self-fixing check sub-agent (`trellis-check`, dispatched
at step 2.2 with a mandatory full-scope final pass — workflow.md §2.2), prompt-level `[required ·
once]` invariants, consent gates, and a batched commit protocol that forbids amending and pushing
(workflow.md §3.4). Autodrive verifies via dual-voice review (independent Claude
reviewer + codex), harden/finalize passes, and — categorically beyond trellis — **git-truth,
SHA-bound, fail-closed deny gates** (docs/drive-enforcement.md: reviews are proven by
`reviewed-sha` artifacts checked against the actual refs being merged, never coordinator-writable
state). Trellis's compliance layer is ultimately prompt trust; a forgetful model can skip a
`[required]` step and nothing blocks the commit. So hypothesis (i) is **falsified only at the
margins, and the margin is thinner than trellis's own docs suggest**: autodrive is strictly
stronger *at the boundaries it gates*, while trellis occupies a layer autodrive does not — the
per-turn channel — with regression tests that pin selected breadcrumb behaviors (the two
historically-bitten steps, block presence, degradation; dim 2's E1 correction), NOT the universal
required-step ↔ breadcrumb sync its workflow.md comment claims. Autodrive's contract-pin suite
pins drive.md prose, but no per-turn channel exists to pin. Dimension 2's rec closes exactly that
gap.

**Economics.** Autodrive's idealized-run floor is **44 slash-command invocations — exact for the
idealized 2-phase × 2-slice × 3-round example in docs/flow.md, and a floor *for that shape***
(plus a codex exec inside every review/harden/finalize audit); redesigns and extra rounds only add
to it. Trellis's whole loop is 3 phases with a handful of required steps, and its lightweight tier
drops to PRD-only. Hypothesis (ii) is **falsified**: the rigor is not justified at all stakes, and
autodrive already says so — OPERATING.md §Engineering workflows: "Match rigor to stakes — quick
fixes and mechanical edits need no pipeline." The existing mitigation is binary (use /drive or
don't); trellis demonstrates a *graduated* alternative. A /drive "lite" tier is real but M/L
effort and its pain is already being attacked from the other side by the L1 sheds (TODO C1/C3/C11)
— tiered *wait* (TR-9).

**Verdict:** keep autodrive's enforcement architecture (it is the stronger half of the comparison
and the repo's moat per TODO.md's layer framing); adopt nothing here directly; the per-turn gap
routes to dimension 2, the stakes-tiering observation to TR-9 (*wait*).

## 5. Memory / journaling / trace-mining & learning loops

depth: deep · hypothesis: required per-task write-back + `trellis mem` transcript indexing closes loops autodrive's skippable end-of-session /decant leaves open · addresses: T-3, T-5 (D-12 ranking weight)

**Trellis mechanism — three tiers plus an indexer.** (1) *Task dir* — per-task artifacts. (2)
*Journals* — per-developer `journal-N.md` under `.trellis/workspace/<developer>/`, appended by
`packages/cli/src/templates/trellis/scripts/add_session.py`, auto-rotating at a 2000-line cap
(workflow.md §Workspace System). (3) *Permanent spec* — `.trellis/spec/`, promoted to by workflow
step **3.3 Spec update `[required · once]`**: every task must load the `trellis-update-spec` skill
and walk through the update-worthiness judgment even when the outcome is that nothing needs
updating; step 3.4's spec-sync preamble re-asks the question before commit (workflow.md §3.3–3.4).
Alongside sits
**`trellis mem`** (`packages/core/src/mem/`, CLI in `packages/cli/src/commands/mem.ts`): local,
read-only indexing/search/task-boundary-slicing over native agent transcript JSONL, with adapters
for Claude Code, Codex, and Pi (`packages/core/src/mem/adapters/claude.ts`, `codex.ts`, `pi.ts`;
`opencode.ts` is a documented degraded no-op — OpenCode moved to SQLite and the native-dep reader
was reverted). The consumption instinct ships as the `trellis-session-insight` bundled skill
(`packages/cli/src/templates/common/bundled-skills/trellis-session-insight/SKILL.md`) —
pattern-spotting across past sessions, e.g. answering whether the same class of mistake keeps
recurring.

**The asymmetry, stated precisely.** Trellis forces the **write-back** (3.3 is `[required ·
once]`, per-task) but leaves **mining** discretionary — session-insight frames itself as a
capability to reach for when the moment warrants, not a required workflow step. Loop closure comes
from making promotion un-skippable at a workflow boundary, not from automated analysis.

**Autodrive counterpart.** Auto-memory + `/decant` → OPERATING.md promotion. Decant is wired into
the pipeline at every context-clear boundary (drive.md §I1 step 5.5) and at run-wrap, but as
prose, skippable, and it distills *what the coordinator noticed in session memory* — not what the
traces show. Meanwhile `$RUN_DIR` accumulates exactly the structured signal trellis's mem has to
reverse-engineer from raw transcripts: `event-log.jsonl` (dispatch/verdict/gate timeline),
per-round `review-*.md` findings, `harden-*.md`, round counters, `budget.calls`, decision ledgers.
Nothing mines them (T-5). This is the falsifiable core of T-5 and it stands: the loop's
*infrastructure half* is un-built on the autodrive side even though autodrive's raw material is
richer and already structured.

**E6/DP1-4 precedence, applied explicitly.** The layer/absorption test runs FIRST; the D-12 user
weight (T-5 elevated at Gate A) ranks only among survivors and never rebuts an L1 default:
- *Replicating transcript-indexing plumbing* (an autodrive mem clone over `~/.claude/projects/` JSONL) serves **L1** — the harness owns transcript storage and already ships auto-memory; native transcript recall is plausibly absorbed. Default *ignore/wait* holds → not a candidate.
- *Run-alongside `trellis mem`* is the **L1-safe route** to transcript recall: it reads Claude Code JSONL natively, zero integration, zero build investment — nothing is lost if the harness later absorbs the capability (TR-4).
- *A run-retro pass over `$RUN_DIR` artifacts* serves **L3** — it feeds verification/enforcement improvement from autodrive-owned, structured artifacts no harness feature will ever mine for us. Survives the layer test → adopt-pattern candidate (TR-3).
- *Enforcing the write-back* (trellis's actual forcing function) serves **L3**; but autodrive already runs decant at seams by pipeline prose, and there is no evidence yet that it gets skipped in practice — gate edge-hardening on evidence the failure occurs → *wait* (TR-5).

Only now does the D-12 weight rank: among the surviving adopt-pattern candidates (TR-3 here, TR-2
from dim 2), T-5's elevation puts **TR-3 first**.

**Verdict:** *adopt-pattern* TR-3 (run-retro over `$RUN_DIR`, S) — selected for Phase 2;
*run-alongside* TR-4 (`trellis mem` for the transcript half); *wait* TR-5 (write-back enforcement,
pending evidence decant-at-seams actually gets skipped).

## 6. Sub-agent context contracts

depth: deep · hypothesis: mechanical PreToolUse injection/redaction of curated manifests beats autodrive's prose invariants — or is L1 the harness absorbs · addresses: T-4

**Trellis mechanism.** `packages/cli/src/templates/shared-hooks/inject-subagent-context.py` fires
on `PreToolUse(Task|Agent)`. For each sub-agent role it inlines the task's *curated manifest* —
`implement.jsonl` / `check.jsonl` list exactly which spec/research files that role gets — plus
role-appropriate task artifacts, marking the payload `<!-- trellis-hook-injected -->`. The agent
templates carry a pull-based fallback:
`packages/cli/src/templates/claude/agents/trellis-implement.md` tells the agent that when the
marker is absent it must locate the active task itself and read the manifest plus each listed
artifact directly (hook injection can miss on
`--continue` resume, disabled hooks, etc.). The design intent per the script's own docstring:
context assembly is code-controlled, not prompt-controlled, so the sub-agent's inputs are
deterministic per role.

**Autodrive counterpart.** Two prose invariants (CLAUDE.md §Invariants): pass paths not contents,
and "Never include the implementer's notes/rationale in the reviewer's prompt." The coordinator
hand-assembles every dispatch prompt; nothing mechanical checks either invariant. A drifting
coordinator can silently paste a diff into a reviewer prompt or leak implementer rationale, and
only the (self-reported) review output might reveal it.

**L1-absorption question, answered — it splits.** The *injection* half (assembling role context
mechanically at dispatch) is L1: it is dispatch mechanics, precisely the layer TODO.md's framing
sheds, and the harness is actively absorbing it — per-agent-type definitions already carry
tools/model/prompt config natively, and richer native context contracts are the obvious
trajectory. Replicating trellis's injector → *ignore* under the L1 default; no rebuttal is
available. The *redaction/verification* half — mechanically **checking** that a reviewer prompt
satisfies autodrive's isolation invariants — serves L3 (it protects review integrity) and is not
absorbable (the invariants are autodrive's own). But a robust discriminator is not apparent:
"contains implementer rationale" has no crisp mechanical signature, and both OPERATING.md lessons
apply — don't make the model the meter, and a destructive gate before a decisive check spawns
false-positives (an abstain-biased warn is the strongest defensible form, and a warn nobody acts
on is ceremony).

**Verdict:** injection half *ignore* (L1, absorbed); redaction half *wait* (TR-6) — the idea
(mechanical > prose for a load-bearing invariant) is sound, but it waits on a concrete
discriminator and on observed T-4 violations to justify the gate.

## 7. Parallel execution & multi-agent runtime

depth: compact · hypothesis: `trellis channel` + parent/child task trees offer nothing over file-ownership slices in worktrees + native background subagents · addresses: —

`trellis channel` (`packages/core/src/channel/`) is an event-sourced worker runtime — spawn/send/watch/interrupt (`api/spawn.ts`, `api/send.ts`, `api/watch.ts`, `api/interrupt.ts`), dispatch-and-wait on system events, worker inbox/state machinery under `internal/store/`. It exists because trellis targets 17 platforms and cannot assume a native sub-agent runtime; autodrive assumes one and gets spawn/background/notify/Monitor from the harness, with parallelism disciplined by file-ownership slices in coordinator-created worktrees. The runtime is L1 by construction, and TODO C8 already scopes the native-orchestration upgrade path (Workflow parallel() with schema-validated returns). The hypothesis **holds**; no candidate can name a T-problem.

One corroborating detail worth keeping: the channel skill's own hard-won warning
(`packages/cli/src/templates/common/bundled-skills/trellis-channel/SKILL.md`) — completion signals
must be trellis-*emitted* system events (`--kind done`), never a worker-echoed tag, because in
trellis's experience an LLM worker often narrates the completion tag as prose instead of actually
running the signalling command. That
is an independent confirmation of C8's complaint against autodrive's own `STATUS:` first-line
contract and of the schema-validated-returns precondition. **Verdict:** *ignore* (TR-7); x-ref C8
(corroborates, adds no new work).

## 8. Portability & human-consent surfaces

depth: compact · hypothesis: portability is *ignore* under the stated assumption — to falsify · addresses: —

**Assumption, labeled as such:** autodrive is currently operated single-user on Claude Code. This
is an ASSUMPTION, not a repo fact — the repo declares no audience and the README presents a
general pipeline.

Trellis ships **17** platform configurators (`packages/cli/src/types/ai-tools.ts` `AITool` union:
claude-code, cursor, opencode, codex, kilo, kiro, gemini, antigravity, devin, qoder, codebuddy,
copilot, droid, pi, reasonix, zcode, trae; wired in `packages/cli/src/configurators/`; the
README's marketing table says 16 — source count wins). Its consent surfaces are two-stage
(task-creation consent ≠ implementation consent, workflow.md §Request Triage and §Guardrails; a
plan-confirm batched commit protocol that forbids amend and push) — structurally the same two-gate
discipline as autodrive's Gate A/Gate B, so nothing to adopt there.

**Counter-question, answered.** What autodrive loses by not being repo-native/cross-agent: (a)
*distribution* — a collaborator on another agent cannot run /drive at all (the pipeline lives in
`.claude/commands/` + Claude-specific hooks); (b) *installation locality* — trellis's `.trellis/`
layout makes the workflow travel with the repo, while autodrive's enforcement chain is
machine-installed (`bin/install-drive-hooks.sh`, "Install once per machine" — README): a fresh
clone on a new machine runs ungated until someone remembers the install. (b) is a real,
audience-independent lesson, but its fix (repo-carried enforcement bootstrap) is M-effort
hardening with no named pain today. What changes if the audience broadens: the L2/L3 content
(design tiers, review contracts, gates) is prose and portable in principle; the wiring would need
per-platform configurators — exactly the machinery that makes trellis heavy, and exactly what
TODO.md's shed-L1 direction says not to build.

**Verdict:** the hypothesis **survives scoped** — under the stated assumption, portability is
*ignore* (TR-8); if the audience assumption breaks, this dimension — not this doc — must be
redone.

## Recommendations

Rules applied to the table: layer is by the layer SERVED; **L1-tagged recs default
*ignore*/*wait*** unless a written non-absorption rebuttal is given; the D-12 user weight (T-5
elevated) ranks only among layer/absorption survivors and never rebuts an L1 default (DP1-4); a
rec that cannot name its pain is tiered *ignore* with the literal Kills form; x-ref states
extend-vs-duplicate on any C-item overlap.

| ID | Recommendation | Tier | Effort | Value | Landing surface | Layer | Absorption risk | Kills | TODO x-ref |
|---|---|---|---|---|---|---|---|---|---|
| TR-1 | Replicate hook-injected session-start context/spec-pointer assembly | ignore | S | none marginal — static imports + native session context already cover it | n/a (would be a `bin/` SessionStart hook) | L1 | yes — session-start context assembly is the harness's own surface (imports, auto-memory, skills) | — (no pain ⇒ ignore) | none |
| TR-2 | Per-turn `<drive-state>` breadcrumb: UserPromptSubmit hook reading `$RUN_DIR/state.json`'s real fields (runId, stage, phase, waiting) and deriving the expected next step from stage/phase (as the run-graph does), bodies pinned by a contract test | adopt-pattern | S | pre-violation drift correction between gate denies; survives auto-summarization context loss | `bin/` new hook + `bin/install-drive-hooks.sh` + `tests/contracts` pin | L2 | no — the hook surface is native but autodrive's run-state semantics are not plausibly shipped by the harness | Kills T-1: the coordinator is re-anchored to drive.md's expected next step every turn, before a deviation reaches a gate. | C11 — extend: C11 demotes /goal ceremony; the breadcrumb supplies the same steering with zero human re-arm; no duplicate (C11 trims prose, TR-2 adds a hook), must land compatibly with C11's pinned clauses |
| TR-3 | `/drive-retro`: single-run trace-mining pass over `$RUN_DIR` artifacts (event-log.jsonl, review/harden rounds, STOP causes, decisions) emitting classified harness-lesson proposals | adopt-pattern | S | closes the trace→harness loop on artifacts only autodrive will ever mine; structured input beats raw transcripts | `.claude/commands/drive-retro.md` (new command; v1 manual, operator-invoked post-run — automatic wiring into the run-wrap sequence, where /decant already runs, is a deferred follow-on) | L3 | no — mines autodrive-owned run artifacts, not transcripts; no harness feature reads `$RUN_DIR` | Kills T-5: recurring review-churn themes, STOP causes, and round-count hot spots become promotion candidates instead of dying in the run dir. | none — distinct from finalize's TODO routing (finalize routes *product* findings; retro mines *process* signal) |
| TR-4 | Run `trellis mem` alongside, unmodified, for cross-session transcript recall over past /drive sessions | run-alongside | S | free search/slice over Claude Code JSONL; covers the raw-transcript half TR-3 does not reach | operator workflow only (no repo change) | L1 | yes — native transcript recall is a plausible harness feature; the L1 default governs adopt-pattern recs — run-alongside is E6's sanctioned L1-safe route: zero build investment, so absorption strands nothing | Kills T-5 (transcript half): "have we hit this before" answered from past sessions without replaying them. | none |
| TR-5 | Enforce the learning write-back: require decant evidence at seam-resume (trellis's required-spec-update pattern) | wait | M | turns a standing preference into a proof | seam-resume proof chain (drive.md I1 / checkpoint lint) | L3 | no — autodrive-specific proof machinery | Kills T-3: promotion can no longer be skipped at the boundary where the context dies. | none — wait condition: evidence that step-5.5 decant is actually being skipped in real runs; until then this is ceremony (OPERATING: gate edge-hardening on evidence) |
| TR-6 | Mechanical reviewer-isolation check: abstain-biased PreToolUse warn on reviewer dispatches that embed implementer rationale/contents | wait | M | converts a silent prose-invariant violation into a visible signal | `bin/` PreToolUse hook on Agent dispatch | L3 | no — the isolation invariant is autodrive's own | Kills T-4: reviewer contamination is caught at dispatch, not inferred from review quality. | none — wait condition: a crisp discriminator + an observed T-4 violation; a vibes-gate here would false-positive (OPERATING: don't make the model the meter) |
| TR-7 | Event-sourced worker runtime / parent-child task trees (`trellis channel` analog) | ignore | L | none over native background subagents + Monitor + file-ownership slices | n/a | L1 | yes — dispatch/orchestration is the harness's core absorption zone (C8 scopes the native path) | — (no pain ⇒ ignore) | C8 — corroborates, not duplicates: trellis's tag-vs-kind warning independently confirms C8's schema-validated-returns precondition (system-emitted completion signals, never model-echoed prose) |
| TR-8 | Repo-native layout / multi-platform configurators | ignore | L | none under the stated solo-on-Claude-Code assumption | n/a | L1 | no — the harness will not ship cross-agent portability; killed by the assumption + shed-L1 direction, not absorption | — (no pain ⇒ ignore) | none |
| TR-9 | Graduated stakes tier for /drive (lightweight PRD-only-style path for small tasks) | wait | L | rigor proportional to stakes instead of binary use-/drive-or-don't | drive.md pipeline shape | L2 | no — the pipeline shape is autodrive's own | Kills T-2: small tasks stop paying the 44-invocation-class floor (idealized 2×2×3 shape) for full-pipeline ceremony. | C1/C3/C11 — extend, not duplicate: those shed L1 dispatch weight; TR-9 is a different axis (fewer stages). Wait condition: re-measure ceremony cost after the Tier-3 sheds land |

**Routed to TODO.md:** TR-2 only (the remaining S/M adopt-pattern rec after Phase-2 selection;
TR-4 is run-alongside, TR-5/TR-6/TR-9 are wait-tier — the ≤3 cap is a ceiling, not a quota).

### Phase-2 spike selection

**Selected: TR-3 — `/drive-retro`, a single-run trace-mining pass over `$RUN_DIR` artifacts.**

- **Scope (≲150 SLOC band):** one new command file, `.claude/commands/drive-retro.md` (~100–150 lines of command prose; no shipped code). v1 mines ONE completed run's `$RUN_DIR`; cross-run aggregation is explicitly out of scope.
- **Landing surface:** `.claude/commands/drive-retro.md`. v1 is a MANUAL, operator-invoked post-run command — `/drive-retro <runId>` on a completed run — so no drive.md edit is required for v1. Automatic run-wrap wiring (a drive.md Completion-step edit, into the sequence where /decant already runs automatically) is a named follow-on, explicitly not part of the spike.
- **Acceptance sketch:** given a completed run's `$RUN_DIR`, emits `retro-<runId>.md` containing (a) mechanically derived stats — review rounds per slice, redesign/STOP events, P1/P2 recurrence themes from `review-*.md`, harden findings classes, `budget.calls`; (b) ≥1 classified lesson candidate routed per OPERATING.md's Self-Improvement matrix (behavioral rule vs project doc vs skill vs auto-memory); (c) proposals only — it never mutates OPERATING.md or skill files without user sign-off.
- **String-pin-test exposure:** v1 adds a new file only, touching no pinned artifact; several drive*.md files carry string-pinned contract tests — run `python3 -m pytest tests/contracts` locally if any drive*.md wiring is touched during implement.
- **Ranking rationale:** among the S-effort adopt-pattern survivors (TR-3, TR-2), the D-12 user weight elevates T-5, putting TR-3 ahead of runner-up TR-2 — both passed the layer/absorption filter first (DP1-4), so the weight legitimately decides.

## License boundary

Trellis is AGPL-3.0; autodrive is MIT. Three rules govern every recommendation above:

1. **Adopt-pattern = clean-room from THIS doc.** Implementations are written from this document's
mechanism descriptions, never with trellis files open.
2. **Never copy code, templates, or prompt text — including close paraphrase.** Trellis's
prompt/template text is where its expression IS the mechanism; a close paraphrase of workflow.md
or a skill body risks derivative expression. Adopt the *idea* (a per-turn state block; a required
write-back step), express it in autodrive's own vocabulary against autodrive's own state model.
3. **Run-alongside = the released `@mindfoldhq/trellis` npm tool, unmodified**, in a driven
project (TR-4). Using the tool is not deriving from it.

No recommendation in this doc implies vendoring AGPL code or paraphrasing trellis prompt/template
text; TR-2 and TR-3 both operate on autodrive-native inputs (`state.json`, `$RUN_DIR` artifacts)
that trellis's implementations never touch.

## The one decision

**Implement one bet: TR-3 (`/drive-retro`) — this run's Phase 2 builds it.** Everything else in
this doc is evidence, a routed TODO item (TR-2), or a named wait condition; no further action is
open.
