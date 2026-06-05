---
description: Autonomous engineering lifecycle — premises → plan (Gate A) → implement → review+codex → harden → verify → ship (Gate B). Drives a task through all stages with two human gates.
argument-hint: <task to drive>
---
You are `/drive` — the autonomous lifecycle coordinator. Advance stages
autonomously; pause only at the gates and non-decision STOPs. You own the **run
model** and **worktree lifecycle**: operate on git **refs + worktrees**, NEVER
mutating the user's main working tree.

Argument: `$ARGUMENTS` is the task (the premise).

## Preconditions (non-decision STOPs)

- gstack installed at `~/.claude/skills/gstack` — else STOP ("gstack not installed").
- Inside a git repo with a **clean main working tree** (`git status --porcelain`
  empty) — else STOP (a run branches from a clean base; don't disturb the user's
  uncommitted work).
- `gh` (or `glab`) + `jq` on PATH for ship.

## Decision policy (every stage)

Apply autoplan's 6 Decision Principles + Mechanical/Taste/User-Challenge
classification (see the harness `CLAUDE.md`; autoplan also carries the canonical 6).
Log decisions to `$RUN_DIR/decisions.md` (promoted
to the repo `.harness/decisions.md` at ship).

**Non-decision STOPs** (red/flaky tests, merge conflict, implement BLOCKED, review
N>8, budget ceiling) pause regardless of policy. If `AskUserQuestion` is
unavailable, report `BLOCKED — AUQ unavailable` rather than auto-deciding. Every such
STOP — and every Gate and `AskUserQuestion` — pauses via the **Present human pause**
routine (set `waiting` → emit run graph → present), so the run graph is always emitted
before the pause.

## Run setup & resume

Generate `runId = <branch>-<timestamp>` and `RUN_DIR = ~/.claude/harness-runs/<runId>/`
(`mkdir -p`). All per-run artifacts live in `$RUN_DIR` (absolute path), reachable
from any worktree. Append a line to `$RUN_DIR/event-log.jsonl` at every dispatch /
verdict / merge / gate.

- **Resume:** if invoked with an existing runId (its `$RUN_DIR/state.json` exists), load it
  and reconcile from git — `git worktree list`, branch tips, and ancestry are authoritative;
  state fields are hints. Never re-dispatch, advance, or clean up on a state value alone:
  - **Current phase:** `state.phase` = the lowest phase in `state.phaseList` whose
    `phaseInt/<runId>/<P>` is not yet an ancestor of `featureBranch` (branch absent, or
    `git merge-base --is-ancestor phaseInt/<runId>/<P> <featureBranch>` fails). All are
    ancestors → `stage = verify`.
  - **Worktrees:** classify each `$RUN_DIR/wt/` worktree by its checked-out branch and
    remove stale ones with `git worktree remove` only — never `branch -D` (branch cleanup is
    the guarded assemble/advance steps' job). A `slice/<runId>/<id>` worktree is live until
    its slice is `converged`; a `phaseInt/<runId>/<P>` worktree is live only for the current
    phase with `phaseReview[<P>].status` not yet `hardened`.
  - **Each slice, by `step`:** `queued` → leave it for the phase-loop to dispatch.
    `implementing` → if `git rev-list <phaseBaseSha>..slice/<runId>/<id>` is non-empty and
    slice-local tests pass, promote to `awaiting_review`, else re-dispatch IMPLEMENT.
    `awaiting_review` → run REVIEW. `needs_fix` → re-dispatch IMPLEMENT (re-create the
    worktree if removed). `converged` → done (branch kept for assembly). `blocked` → STOP.
  - **Phase `hardening`:** resume HARDEN on `phaseInt/<runId>/<P>` (don't rebuild). If
    `status == hardened` but `phaseInt/<runId>/<P>` is not yet an ancestor of `featureBranch`,
    complete its `git branch -f` advance (Execute step 5) instead. Set `hardenRound =
    max(state, count of `harden-<P>-*.md` with `AppliedEdits: yes`)`.
- **Fresh run:** assert the clean-tree precondition; record `baseRef` (the repo's
  default/integration branch, e.g. `main`); create `featureBranch` from `baseRef`;
  initialize and write `$RUN_DIR/state.json` in this shape (set `sessionId` from the
  `$CLAUDE_CODE_SESSION_ID` env var so the Stop hook can attribute this run to this
  session; leave it `null` if unset):

```json
{ "runId": "<id>", "task": "<task>", "stage": "premises",
  "baseRef": "main", "featureBranch": "drive/<id>",
  "phase": 1, "phaseList": [], "phaseBaseSha": null, "concurrencyCap": 4, "designReview": 0,
  "budget": { "ceilingCalls": null, "ceilingMin": null, "calls": 0, "startedAt": "<iso>" },
  "slices": {}, "phaseReview": {}, "lastGate": null,
  "verify": { "attempts": [] }, "ship": { "suite": null, "conformance": null, "prUrl": null },
  "sessionId": null, "autoContinue": true, "waiting": null,
  "designPath": "$RUN_DIR/design.md" }
```

**Build it JSON-safely — never string-substitute `<task>` into the template.** The
task is arbitrary user text (it can contain `"`, `\`, or newlines) and naive
interpolation corrupts the file. Construct it with a JSON tool, e.g.
`jq -n --arg task "$TASK" --arg id "$RUNID" … '{runId:$id, task:$task, …}'`, and the
same for every later write. Apply the same rule anywhere run text is embedded in
JSON (event-log lines, etc.).

Update `state.json` after every transition. Increment `budget.calls` on each
subagent/codex dispatch; if `ceilingCalls`/`ceilingMin` is set and exceeded → STOP
with a spend summary (budget circuit-breaker).

**Autonomous-continuation contract (`waiting`).** The `drive-stop-hook` (installed by
`bin/install-operating-rules.sh`, no-op if absent) keeps a run driving across turns
*without* a `/goal` by reading `state.json`: it blocks the turn from ending while this
session's run has `stage != "done"` and `waiting` is empty, and allows it the moment
`waiting` is set or `stage = done`. So you MUST set `state.waiting` to a short reason
**before pausing for the human at any point** — Gate A, Gate B, every non-decision
STOP, or any AskUserQuestion — and clear it (`waiting = null`) the instant you resume
autonomous work. Forgetting to set it just means the hook nudges you to continue (it
biases toward letting you stop and fails open); it never forces you past a STOP. This
is independent of `/goal` — use either or both. Set `autoContinue:false` to disable
the hook for this run.

## Present human pause (shared routine)

This is the **ONLY** way `/drive` pauses for the human — Gate A, Gate B, every
non-decision STOP, and every `AskUserQuestion`. Go through these steps in this exact
order; emitting the run graph is a mandatory step (step 2) so it can never be
forgotten:

1. **Set `state.waiting` FIRST** to the pause reason — `"gateA"`, `"gateB"`,
   `"stop:<short>"`, or `"ask:<header>"`. This satisfies the autonomous-continuation
   contract above (set `waiting` before pausing) and lets the run graph derive
   `← YOU ARE HERE` from it.
2. **Emit the run graph** (per § *Emit run graph (shared step)* below) — it reads the
   just-set `state.waiting`.
3. **Present** the gate text / STOP reason, or call `AskUserQuestion`; then end the
   turn. Clear `waiting = null` the instant autonomous work resumes.

**Pre-run exception:** the **preconditions** STOPs (gstack missing, dirty tree) fire *before*
a run exists — there is no `$RUN_DIR`/`state.json` to render, so they STOP plainly (no graph).
The routine applies to every pause **once the run is initialized**.

## Emit run graph (shared step)

Render a single **data-driven** "run-so-far" ASCII flow graph immediately before the
human pause, so the user is oriented: where the run is, what each review round decided
(both voices), and the throughlines. `/drive-plan` (Gate A) and `/drive-ship` (Gate B)
MUST read THIS section and follow it.

### Data sources (the ONLY sources — never drift, never fabricate)

Every rendered node derives ONLY from durable, fixed-format artifacts:

1. **`state.json`** — the durable structured run-model. Fields the graph reads:
   `task` (→ Premises line — always written at run-setup), `stage`, `lastGate`, `waiting`,
   `phase`, `phaseList`, `designReview`, `slices[<id>].{step,reviewCount,owns,deps}`,
   `phaseReview[<P>].{status,round,hardenRound}`, `verify`, `ship`.
2. **Fixed-format markdown files** (scope-token naming):
   - `design.md` (Goal → root cause). (`task.md` may also exist, but the Premises line is
     taken from `state.task`, which always has a writer — never an unsourced node.)
   - `review-<scope>-N.md` (`## Verdict: CONVERGED|FINDINGS`; `### [SEVERITY]` where
     BLOCKING/MAJOR = P1) — the Claude reviewer file, **persisted per round** (the `-N`
     suffix) — and its codex sibling `codex-review-<scope>.md` (same tags, or bare
     first-line token `CODEX_UNAVAILABLE`).
   - `harden-<P>-N.md` (`## Verdict: HARDENED|FINDINGS`) and `codex-harden-<P>.md`.
   - **The slice scope token is the BARE id** — `review-<id>-*.md` /
     `codex-review-<id>*.md` (e.g. `review-1.2-3.md`, `codex-review-1.2.md`), per
     drive-review.md. Glob by prefix to tolerate round suffixes (`-r2`). (Design scope =
     `review-design-*.md` / `codex-review-design.md`; phase scope = `review-phase<P>-*.md`
     / `codex-review-phase<P>*.md`.)
   - **Codex persists ONE file per scope (`codex-review-<scope>.md`), overwritten each
     round** — only the Claude file carries per-round (`-N`) history. The graph never
     fabricates a historical codex count (see "Combined dual-voice round verdict").

**`event-log.jsonl` is NEVER required to render any node** — its event/field names vary
across runs, so it is unreliable. It may be used ONLY as an optional decorative
timestamp; if a value isn't in `state.json` or a fixed-format file, render it as
`?`/`pending` — never parse freeform event strings, never fabricate.

### Render contract

- A single **fenced code block** (terminal-friendly ASCII tree; **no mermaid**
  anywhere).
- Print the glyph legend once at the top of the block:
  `[✓ done · ◐ current · ✗ stop · ? unknown]`, plus the `‖` note (below).
- **One branch per stage that has STARTED**, in order
  `Premises · Plan · Execute · Verify · Ship` (a not-yet-started stage is omitted).
  "Started" = `state.stage` has reached/passed it OR its artifacts exist.
- **Premises:** one line — the resolved problem (first non-empty line of `state.task`,
  truncated).
- **Plan:** a `root cause:` one-liner (first sentence of `design.md` Goal; else
  `(pending)`); then the design-review rounds (combined verdict); then an explicit
  **`Gate A:` node line** — `APPROVED` when `state.lastGate=="A"` (or beyond), else
  `awaiting approval`. `waiting=="gateA"` anchors `← YOU ARE HERE` to this line.
- **Execute:** each phase (from `state.phaseList`) → its slices (`state.slices` keyed by
  id-prefix == phase; `‖` between independent slices — see below). **Under each slice**
  (and each phase-integration), as child lines: one line per review round + combined
  dual-voice verdict, then `fix round k` child lines (or the numeric summary), then —
  at the phase level — an `assemble` line and an `advance` line (the latter iff
  `phaseReview[<P>].status=="hardened"`). Per-phase status from `phaseReview[<P>].status`
  (absent/no-status ⇒ `◐` in-progress). `stage==execute` + empty `slices` ⇒
  `◐ Phase N (dispatching…)`; `stage` past execute + empty `slices` ⇒
  `(no slices recorded)`. (A change with no formal slice breakdown records its one unit
  as a `state.slices` entry, so it renders through the normal slice path.) Harden from
  `harden-<P>-*.md` + `codex-harden-<P>*.md` + `phaseReview[<P>].hardenRound/status`.
  A `stop:<r>` while in Execute anchors `← YOU ARE HERE` to a `✗ STOP: <r>` leaf under
  the responsible slice/phase node.
- **Verify:** from `state.verify.attempts[]` (ordered ⇒ saga); multiple attempts render
  the false-negative → re-verify saga, e.g. `e2e: FAIL → re-verify → PASS`.
- **Ship:** child lines `conformance: <state.ship.conformance or pending>` ·
  `suite: <state.ship.suite or pending>` · `PR: <state.ship.prUrl or pending>`, then an
  explicit **`Gate B:` node line** — `awaiting approval` until the PR is opened, then the
  PR url. `waiting=="gateB"` anchors `← YOU ARE HERE` to this `Gate B:` line.
- **`← YOU ARE HERE`** marks the node being presented, keyed off `state.waiting` — and
  EVERY value has a defined anchor node: `gateA` → the `Gate A:` line (Plan); `gateB` →
  the `Gate B:` line (Ship); `stop:<r>` → a `✗ STOP: <r>` leaf under the current stage's
  active node; `ask:<header>` → a `? <header>` leaf under the current stage (Premises if
  Stage 0). An unrecognized `waiting` still renders, with `← YOU ARE HERE` on a generic
  `✗ STOP: <reason>` leaf under the current stage.
- End with a **`key throughlines:` 2–3 bullet** synthesis derived from the rounds that
  had findings (a recurring P1 theme, a slice that needed many fix rounds, a verify
  false negative).

### `‖` precise meaning

`‖` joins slices in a phase that are **independent** — disjoint `owns` AND no `deps`
between them — i.e. the coordinator dispatches them as a parallel group. The legend
states verbatim: **"‖ = independent slices (disjoint ownership), dispatched as a
parallel group; wall-clock concurrency is bounded by `concurrencyCap`."** The graph
does NOT claim simultaneous wall-clock execution (state cannot prove it); it claims
structural independence, which `owns`/`deps` in `state.json` do prove. Slices with a
`deps` relationship are drawn stacked (sequential), never `‖`.

### Combined (dual-voice) round verdict

A round is **CONVERGED only when BOTH voices have zero P1** — count BLOCKING/MAJOR in
`review-<scope>-N.md` AND in `codex-review-<scope>.md` (a `CODEX_UNAVAILABLE` first-line
token ⇒ `Codex n/a`, contributes zero P1). **Never key the glyph off the Claude file's
`## Verdict:` alone.**

Per-round derivation handles codex's single-file persistence (above) **structurally**,
so it never drifts and never fabricates:
- The loop only runs round k+1 if round k was FINDINGS. Therefore **every non-terminal
  round (k < N) was FINDINGS by construction** — render it FINDINGS without needing that
  round's codex file. Show its **Claude** P1 count (from `review-<scope>-k.md`, persisted
  per round) and, when expanded, the first P1 title + `(Claude)`; the codex per-round
  count is not separately persisted, so render `Codex —` for non-terminal rounds (do NOT
  reuse the latest codex file for an old round).
- The **terminal round (k = N)** is the live one: BOTH `review-<scope>-N.md` and
  `codex-review-<scope>.md` are current, so render the full `(Claude P1:x · Codex P1:y)`
  and its combined CONVERGED/FINDINGS verdict.
- A FINDINGS round NEVER gets the `✓` glyph (✓ = "done-good"). Render the terminal
  CONVERGED round with `✓`, the current in-progress round with `◐`, and a past
  (superseded) FINDINGS round with no status glyph — its `FINDINGS` verdict word carries
  the state.

### Missing-artifact rule (general — never fabricate)

For ANY counted round whose artifact is absent — for ANY family: `review-design-*.md`,
`review-<id>-*.md`, `review-phase<P>-*.md`, `harden-<P>-*.md`, and their codex siblings
(`codex-review-<scope>*.md`, `codex-harden-<P>*.md`) — show the round count from state
with verdict `?`; never fabricate a verdict.

### Line budget — an ordered collapse LADDER (always terminates ≤ ~45)

Apply in order until the block is ≤ ~45 lines (the ladder cannot bottom out above
budget because the last rung is unconditional):

1. Truncate the premise/task to one line; print the glyph legend once.
2. Collapse each run of consecutive CONVERGED rounds to a single line; expand only
   FINDINGS rounds (one P1 line each).
3. Group independent slices on one `‖` line; summarize long fix chains numerically
   (`→ 4 fix rounds → CONVERGED`).
4. **Whole-phase collapse:** every `hardened` (fully-advanced) phase renders as ONE
   summary line `✓ Phase N: hardened (k slices, m rounds)`; expand slices/rounds only
   for the current phase and any phase that ended in a STOP.
5. Collapse completed stages (`Premises`, `Plan`, advanced phases) to one-line
   summaries, keeping the CURRENT stage detailed; emit a `… N earlier rounds collapsed`
   note.
6. **Hard cap (unconditional — always fits, regardless of run size):** if STILL over
   ~45, render ONLY the spine from the root to the `← YOU ARE HERE` node — each ancestor
   stage/phase as a single line — plus one `… M lines collapsed (full detail in
   $RUN_DIR artifacts)` note. The spine is bounded by tree DEPTH (≈ 5–7 lines), not by
   the number of phases/slices/rounds or the length of `verify.attempts[]`, so the block
   is guaranteed within budget even for a huge run. (This is the rung that makes
   "always ≤ ~45" true; rungs 2–5 are the graceful-degradation path before it.)

### Worked example A — a lean run paused at Gate A

```
/drive run graph  [✓ done · ◐ current · ✗ stop · ? unknown]
‖ = independent slices (disjoint ownership), dispatched as a parallel group;
    wall-clock concurrency is bounded by concurrencyCap

✓ Premises: emit a run-so-far flow graph before every human pause
◐ Plan
  root cause: a /drive pause shows only the local decision, no whole-run context
    design review r1: FINDINGS (Claude P1:1 · Codex —) — event-log unreliable as a source (Claude)
  ✓ design review r2: CONVERGED (Claude P1:0 · Codex P1:0)
  ◐ Gate A: awaiting approval ← YOU ARE HERE

key throughlines:
  • root-cause blocker (event-log drift) fixed: every node derives from state.json + fixed-format md
  • design converged in 2 rounds; both voices clean at the terminal round
```
(r1 is a past FINDINGS round → no `✓`, Claude count + `Codex —`; r2 is terminal → both voices.)

### Worked example B — a run paused at an AskUserQuestion

```
/drive run graph  [✓ done · ◐ current · ✗ stop · ? unknown]
‖ = independent slices (disjoint ownership), dispatched as a parallel group;
    wall-clock concurrency is bounded by concurrencyCap

✓ Premises: add OAuth login + session store
✓ Plan: root cause: no auth boundary · Gate A: APPROVED (2 design rounds)
◐ Execute
  ◐ Phase 1: auth boundary
    1.1 oauth-client ‖ 1.2 session-store   (disjoint owns, no inter-deps)
      ✓ 1.1 review: CONVERGED (1 round)
      1.2 review r2: FINDINGS (Claude P1:1 · Codex P1:0) — token TTL unbounded (Claude)
    ? Migration target: Redis or Postgres ← YOU ARE HERE

key throughlines:
  • slice 1.2 (session-store) flagged an unbounded-TTL P1 (Claude voice)
  • paused to ask the store backend before re-dispatching 1.2's fix
```
(`← YOU ARE HERE` sits on the live AUQ leaf, not the completed FINDINGS round above it.)

## Pipeline

### Stage 0 — Premises & session goal
1. **Premises:** if the task is ambiguous about WHAT problem to solve, pause and ask.
2. **Set the session goal** (do this once now, at the start — the session is fresh
   and the user is present). `/drive` is autonomous across many turns, and Claude
   Code's native **`/goal`** keeps a session driving turn-to-turn instead of stopping
   mid-pipeline (after each turn a fast model checks the condition; if unmet, it
   continues). Two facts about native `/goal` shape how we use it: it **cannot be set
   programmatically** (only the user can type it), and it **auto-clears the instant its
   condition is met**. A single whole-run goal therefore can't span a human gate — to
   let the run *pause* at Gate A the gate has to count as a satisfying state, but that
   same satisfaction auto-clears the goal, leaving the execute half with none. So we
   scope **one goal per autonomous leg**, re-armed at each gate (Gate A and Gate B hand
   the user the next leg's line to paste on approval).

   Present the **leg-1** goal (drives planning → Gate A). Bind `<task>` = the resolved
   premise (`$ARGUMENTS`), then **continue regardless** (never block waiting for them):

   > Paste this to drive planning autonomously up to Gate A:
   >
   > ```
   > /goal The /drive run for "<task>" has reached Gate A and is presenting the plan for my approval, OR is paused awaiting my input at a non-decision STOP or an AskUserQuestion. NOT met while autonomous planning (design, autoplan, dual-voice review) work remains.
   > ```

   This complements the gates rather than overriding them: `/goal` continues the
   autonomous stages, while Gate A / Gate B / STOPs still pause for you (an
   AskUserQuestion blocks the turn regardless of any goal). The user may skip the goal;
   `/drive` still advances — it just won't auto-continue across turns.

   → `stage = plan`

### Stage 1 — Plan (gstack brain)
Run the PLAN stage (`/drive-plan` — `~/.claude/commands/drive-plan.md`): planner authors
`$RUN_DIR/design.md` **with a `## Phases & Slices` breakdown**, autoplan reviews it,
then the dual-voice **design-review** primitive converges it (no open P1). **Gate A**
= autoplan approved AND design converged — the one human gate here. If no
approved/converged design → STOP. → `lastGate = "A"`, `stage = execute`

Parse the breakdown into `state.slices` (`{<id>: {step:"queued", reviewCount:0}}`
with each slice's `owns`/`deps`) and the ordered phase list. Record the ordered phase ids in `state.phaseList`.

### Stage 2–4.5 — Execute (per phase; refs + worktrees only)

**Plan-gate (defense-in-depth, once per run).** Before dispatching the FIRST IMPLEMENT
of the run (i.e. before the first `git worktree add … -b slice/<runId>/<id>`), run
`bin/drive-conformance.sh $RUN_DIR --mode plan-gate` and proceed only if it reports
clean — it requires the dual-voice **design** review to have CONVERGED (a
`review-design-N.md` with `## Verdict: CONVERGED` + a `codex-review-design.md`). On a
violation, run `/drive-review design` until it converges, then retry. The PreToolUse
hook enforces this same gate on the first `git worktree add -b slice/…`; running it
in-prose first makes enforcement degrade gracefully where the hooks aren't installed.

**Literal refs in gated commands.** Every command the gate inspects (the `git worktree
add -b slice/<runId>/<id>`, each per-slice `git merge slice/<runId>/<id>`, the
`git branch -f drive/<runId> phaseInt/<runId>/<P>` advance, and the ship push/PR) MUST
spell the refs out as **literal strings** with `<runId>`/`<P>` already substituted — NO
shell variables in the ref (e.g. `slice/$runId/$id`). The PreToolUse gate parses the
unexpanded command string, so a variable ref is invisible to it and silently bypasses
the gate.

For each PHASE in order (steps 1–4 build & review the phase; step 5 HARDENS it before
it advances):

1. **Freeze base:** `phaseBaseSha = git rev-parse <featureBranch>`; initialize
   `state.phaseReview[<P>] = { "round": 0 }` if absent.
2. **Dispatch slices** whose `deps` are CONVERGED, ≤ `concurrencyCap` in flight.
   Slices with **disjoint `owns`** run in PARALLEL; create a worktree per slice
   `git worktree add $RUN_DIR/wt/<id> -b slice/<runId>/<id> <phaseBaseSha>`, copy
   the declared gitignored config allowlist (`.env`, …) in, and dispatch IMPLEMENT
   (`/drive-implement` — `~/.claude/commands/drive-implement.md`) with cwd = that worktree (`step=implementing`).
   Overlapping-`owns` ready slices are NOT parallelized — run by dep order; if the
   design left them unsequenced, STOP (planning bug). Excess past the cap queue.
3. **Per-slice loop:** when a slice's IMPLEMENT returns:
   - `DONE` → `step=awaiting_review`; run REVIEW scoped `slice <id>` (slice-local
     tests). CONVERGED → `step=converged`, then **`git worktree remove` its worktree
     (keep the slice branch for assembly)** — frees a concurrency slot + disk, so
     worktree count stays ≤ cap regardless of slices-per-phase. FINDINGS →
     `step=needs_fix`; if its `reviewCount < 8` re-run IMPLEMENT then REVIEW
     (re-create the worktree first if it was removed); if `>=8` → STOP.
   - `BLOCKED`/`NEEDS_CONTEXT` → `step=blocked`, STOP that slice + surface; other
     in-flight slices continue; the phase can't integrate until it resolves. If the
     blocker needs files outside ownership → **plan-amendment** (amend the design's
     Phases & Slices, re-converge the design review, resume).
4. **Assemble (idempotent)** once ALL slices in the phase are `converged`:
   first run `bin/drive-conformance.sh $RUN_DIR --mode audit` and proceed only if it
   reports clean (defense-in-depth — flags any slice merged into the live phase that
   lacks a counting review, so enforcement degrades gracefully where the PreToolUse
   hooks aren't installed; on a violation, run the named `/drive-review slice <id>`
   then retry). Then delete any existing `phaseInt/<runId>/<P>` branch/worktree, then
   `git worktree add $RUN_DIR/wt/phase<P> -b phaseInt/<runId>/<P> <phaseBaseSha>`;
   merge each converged slice branch IN with **one `git merge` per slice** (never a
   single multi-slice merge — the gate requires every merged slice to count, and a
   per-slice merge keeps each transition individually gated). **Conflict → STOP** (the
   rebuild-from-base is the rollback; never `git merge --abort` to undo prior merges).
   Run the **FULL build + integration tests** + REVIEW scoped `phase <P>` in this
   worktree.
   - CONVERGED → `phaseReview[<P>].status = converged`, then **HARDEN** (step 5).
   - FINDINGS → route each P1 to the responsible slice (`step=needs_fix`,
     re-dispatch — re-creating its worktree — loop its cap-8), then
     **re-assemble from scratch**.
5. **Harden (per phase, after the phase review converges)** — run the HARDEN stage
   (`/drive-harden phase <P>` — `~/.claude/commands/drive-harden.md`) IN the
   `phaseInt/<runId>/<P>` worktree (`phaseReview[<P>].status = hardening`). It is a mutating
   find→fix→verify pass over the assembled phase to **reduce AI slop, add missing
   tests, and fix logic bugs** — beyond acceptance criteria — committing to
   `phaseInt/<runId>/<P>`. Its own 3-fix-round cap (independent of the conformance cap-8);
   de-slop edits that would drop a criterion's coverage are vetoed; after any code
   change it re-runs `/drive-review phase <P> harden-regress` as the regression guard.
   Act on its return:
   - `FINDINGS` → a fix round ran but the phase isn't clean yet. Keep
     `phaseReview[<P>].status = hardening` and **re-invoke `/drive-harden phase <P>`**
     on the same `phaseInt/<runId>/<P>` worktree (the loop owns its 3-fix-round cap). Repeat
     until `HARDENED` or `STOP`.
   - `HARDENED` → `phaseReview[<P>].status = hardened`; advance `featureBranch` to
     `phaseInt/<runId>/<P>` with a **pure ref move**: `phaseInt/<runId>/<P>` is always a fast-forward
     descendant of `featureBranch` (branched from `phaseBaseSha = rev-parse
     featureBranch`, then only added commits), so `git branch -f <featureBranch>
     phaseInt/<runId>/<P>` (refs-only; never `merge`/`reset --hard`, which require/disturb a
     working tree). Two guards before the ref move, else STOP: (a) `featureBranch` must
     be a **coordinator ref checked out in NO worktree** (`git worktree list` — git
     refuses `branch -f` on a checked-out branch); (b) `phaseInt/<runId>/<P>` must descend from
     `featureBranch` (`git merge-base --is-ancestor <featureBranch> phaseInt/<runId>/<P>`
     succeeds — exit 0; a non-zero exit means NOT a descendant → STOP, a concurrent ref
     move broke the invariant). Then `git worktree remove` the integration worktree
     (slice worktrees were already removed on convergence), delete slice branches, and
     advance `state.phase` to the next id in `state.phaseList` (if this was the last phase,
     `stage = verify`). Proceed to the next phase.
   - `STOP` (3 fix rounds exceeded / BLOCKED / NEEDS_CONTEXT) → STOP; the phase stays
     `hardening` and does **not** advance — its half-hardened state is preserved on
     `phaseInt/<runId>/<P>` for resume.

When all phases reach `status = hardened` → `stage = verify`.

### Stage 4b — Verify (optional)
If the change touches a UI/URL (auto-detect), run gstack `qa-only` / `browse` on the
`featureBranch` tree; write `$RUN_DIR/verify.md`. Report-only. Honor "no qa".
Append each e2e/QA attempt's outcome to `state.verify.attempts`
(`{result:"PASS"|"FAIL"}`) — the ordered array is the run graph's Verify source and its
false-negative → re-verify saga.
→ `stage = ship`

### Stage 5 — Ship (once)
Run the SHIP stage (`/drive-ship` — `~/.claude/commands/drive-ship.md`) on `featureBranch`: promote
`$RUN_DIR/decisions.md`+`followups.md` into the repo ledgers, run the full suite
(red → retry once → STOP), build the **single** commit + PR, **Gate B** (approve
diff), then push/open PR. → `lastGate = "B"`, `stage = done`

## Completion

Report: design path, per-phase verdicts, PR link; a one-line summary of every
decision promoted this run; `followups.md` entries; the event-log path; anything
uncertain. Note any worktrees/branches left for inspection.
