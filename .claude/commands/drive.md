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
unavailable, report `BLOCKED — AUQ unavailable` rather than auto-deciding.

## Run setup & resume

Generate `runId = <branch>-<timestamp>` and `RUN_DIR = ~/.claude/harness-runs/<runId>/`
(`mkdir -p`). All per-run artifacts live in `$RUN_DIR` (absolute path), reachable
from any worktree. Append a line to `$RUN_DIR/event-log.jsonl` at every dispatch /
verdict / merge / gate.

- **Resume:** if invoked with an existing runId (its `$RUN_DIR/state.json` exists),
  load it, **reconcile worktrees** (`git worktree list` vs `state.slices[].worktree`
  / `phaseReview[].integrationWorktree`; `git worktree remove` + `branch -D`
  orphans; a phase left `integrating` is rebuilt from scratch — see Execute), and
  continue each slice from its `step`. A phase left `hardening` is **NOT** rebuilt —
  its harden commits live on `phaseInt/<runId>/<P>`; resume HARDEN on that branch (rebuilding
  would discard the harden work). **Reconcile `hardenRound` from artifacts, not state
  alone** (a crash can land a `harden-<P>-N.md` or a `phaseInt/<runId>/<P>` commit before the
  state write): `hardenRound = max(state value, count of `harden-<P>-*.md` with
  `AppliedEdits: yes`)`; the next round re-audits from the actual `phaseInt/<runId>/<P>` tree,
  so a partially-applied round is simply re-audited and completed.
- **Fresh run:** assert the clean-tree precondition; record `baseRef` (the repo's
  default/integration branch, e.g. `main`); create `featureBranch` from `baseRef`;
  initialize and write `$RUN_DIR/state.json` in this shape (set `sessionId` from the
  `$CLAUDE_CODE_SESSION_ID` env var so the Stop hook can attribute this run to this
  session; leave it `null` if unset):

```json
{ "runId": "<id>", "task": "<task>", "stage": "premises",
  "baseRef": "main", "featureBranch": "drive/<id>",
  "phase": 1, "phaseBaseSha": null, "concurrencyCap": 4, "designReview": 0,
  "budget": { "ceilingCalls": null, "ceilingMin": null, "calls": 0, "startedAt": "<iso>" },
  "slices": {}, "phaseReview": {}, "lastGate": null,
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
with each slice's `owns`/`deps`) and the ordered phase list.

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

1. **Freeze base:** `phaseBaseSha = git rev-parse <featureBranch>`.
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
     (slice worktrees were already removed on convergence), delete slice branches; next phase.
   - `STOP` (3 fix rounds exceeded / BLOCKED / NEEDS_CONTEXT) → STOP; the phase stays
     `hardening` and does **not** advance — its half-hardened state is preserved on
     `phaseInt/<runId>/<P>` for resume.

When all phases reach `status = hardened` → `stage = verify`.

### Stage 4b — Verify (optional)
If the change touches a UI/URL (auto-detect), run gstack `qa-only` / `browse` on the
`featureBranch` tree; write `$RUN_DIR/verify.md`. Report-only. Honor "no qa".
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
