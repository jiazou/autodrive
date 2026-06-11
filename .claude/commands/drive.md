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
  - **sessionId rebind (FIRST, on ANY resume into a new session):** rewrite
    `state.sessionId` to the live `$CLAUDE_CODE_SESSION_ID` (null if unset) BEFORE
    reconciling anything — the Stop hook attributes a run by exact sessionId match, so a
    stale id kills auto-continue and rebirth detection. In the SAME JSON-safe write (the jq
    rule below), reset `state.rebirth_pending = false` — uniformly on ANY fresh-session
    resume (keyed on `state.sessionId != $CLAUDE_CODE_SESSION_ID`), NOT gated on a
    `rebirth` waiting. `rebirth_pending` is derived from the OUTGOING session's transcript
    growth, gone on a fresh resume, so the signal is stale and the successor re-derives it
    from its own growth (the soft-check/hook re-set it). This is the SINGLE reset point
    (never re-done in the `rebirth`-continue step below): a Gate A/B/STOP/crash run carrying
    a stale `rebirth_pending = true` re-arms cleanly here, so the successor's safe-boundary
    handler does not fire a spurious empty handoff at its first boundary.
  - **Consume `checkpoint-complete.marker` (single-use):** if
    `$RUN_DIR/checkpoint-complete.marker` exists, validate it (JSON parses AND `proof.tip`
    equals the current `drive/<runId>` tip), then DELETE it — valid or invalid — before any
    reconciliation acts on its content. Resume never REQUIRES the marker: missing/invalid
    means reconcile from scratch. (Format + validity rules: § Durable checkpoint contract.)
  - **`waiting == "rebirth"` → normal CONTINUE, NOT a STOP.** A `rebirth`-waiting run found
    on resume is the outgoing session's context-pressure handoff, now picked up: clear
    `state.waiting = null` (JSON-safe write) and continue autonomous reconciliation exactly
    as any resume — do NOT surface it as a paused-for-human state, do NOT re-present the
    handoff. (Distinct from a `gateA`/`gateB`/`stop:`/`ask:` waiting found on resume, which
    is re-presented because the human is back to an open question; `rebirth`'s "human
    action" was *starting this fresh session*, which the resume itself proves happened.) The
    sessionId was already rebound and `rebirth_pending` already reset to `false` in that same
    rebind step (above); the `checkpoint-complete.marker` was already consumed (above).
    Reconcile phase / counters from git + artifacts as normal.
  - **Current phase:** `state.phase` = the lowest phase in `state.phaseList` whose
    `phaseInt/<runId>/<P>` is not yet an ancestor of `featureBranch` (branch absent, or
    `git merge-base --is-ancestor phaseInt/<runId>/<P> <featureBranch>` fails). All are
    ancestors → `stage = verify`.
  - **Derived phase-design status:** the current phase's design counts as converged ONLY if
    the epoch-aware `bin/drive-conformance.sh $RUN_DIR --mode phasedesign-gate:<P>` passes
    for the CURRENT epoch — `phaseDesign[<P>].status` is a hint, never the trigger. Gate
    fails → treat the phase as `designing` and re-run Execute step 1 (re-AUTHOR via
    `/drive-design`, not merely re-review) before dispatching slices.
  - **Redesign cap at resume:** artifact-derived `redesigns >= 3` (reconstruction rule 4
    below) with the current epoch unconverged → STOP — the step-4 handler's verdict,
    re-derived without re-entering the handler.
  - **Stranded in-flight markers:** at resume, every open `$RUN_DIR/inflight-*.marker` is
    stranded by definition (the dispatching session is gone). Apply the recovery rule in
    § Durable checkpoint contract — **adopt / re-dispatch / STOP, never wait** for a
    worker; adopt of a review unit requires BOTH the round's `review-<scope>-N.md` AND a
    non-empty `codex-review-<scope>.md` sibling.
  - **Worktrees:** classify each `$RUN_DIR/wt/` worktree by its checked-out branch and
    remove stale ones with `git worktree remove` only — never `branch -D` (branch cleanup is
    the guarded assemble/advance steps' job). A `slice/<runId>/<id>` worktree is live until
    its slice is `converged`; a `phaseInt/<runId>/<P>` worktree is live only for the current
    phase with `phaseReview[<P>].status` not yet `hardened`. A detached `wt/design<P>`
    worktree (the per-phase design read worktree) is never live across a pause → always
    `git worktree remove --force` it.
  - **Each slice, by `step`:** `queued` → leave it for the phase-loop to dispatch.
    `implementing` → if `git rev-list <phaseBaseSha>..slice/<runId>/<id>` is non-empty and
    slice-local tests pass, promote to `awaiting_review`, else re-dispatch IMPLEMENT.
    `awaiting_review` → run REVIEW. `needs_fix` → re-dispatch IMPLEMENT (if the worktree was
    removed, RE-ATTACH to the existing branch — `git worktree add $RUN_DIR/wt/<id>
    slice/<runId>/<id>`, no `-b`, no reset — to keep its committed work). `converged` → done
    (branch kept for assembly). `blocked` → STOP.
  - **Phase `hardening`:** resume HARDEN on `phaseInt/<runId>/<P>` (don't rebuild). If
    `status == hardened` but `phaseInt/<runId>/<P>` is not yet an ancestor of `featureBranch`,
    complete its `git branch -f` advance (Execute step 6) instead.
  - **Counter reconstruction (all five counters):** state.json is a resume-repair HINT,
    never a proof input. Repair each counter one-directionally —
    `counter = max(state hint, artifact-derived value)`: the hint may RAISE a counter
    (tightening a cap risks at worst a premature STOP — safe), never lower it (loosening
    a cap risks a loop overrunning it — unsafe). The checkpoint proof asserts ONLY the
    artifact-derived value. The run graph derives every round COUNT from the review/harden
    files (artifact-derived); state status fields pick glyphs only, and a state counter is
    a DISPLAY fallback solely in the missing-artifact `?` rule (labeled a hint there) —
    never a proof input.
    1. `slices[<id>].reviewCount` = max(state, count of `review-<id>-N.md`,
       pure-integer N).
    2. `phaseReview[<P>].round` = max(state, count of `review-phase<P>-N.md`
       (pure-integer N) MINUS count of `harden-<P>-*.md` with `AppliedEdits: yes`) —
       harden-regress reviews write into the same `review-phase<P>-N.md` family without
       incrementing the round, and each fix round's `AppliedEdits: yes` audit is its
       durable 1:1 marker, so the bare file count is only an upper bound. yes-count >
       review-file count is malformed → use 0 (checkpoint flags `regress-mismatch`).
    3. `phaseReview[<P>].hardenRound` = max(state, count of `harden-<P>-*.md` with
       `AppliedEdits: yes`) — a confirming clean audit writes `AppliedEdits: no` and
       does NOT count (cap-3 is on fix rounds); never count all harden files.
    4. `phaseDesign[<P>].redesigns` = max(state, HIGHEST epoch R among
       `redesign-<P>-r*.marker`) — highest-R, not file count: marker `rN` proves N
       redesigns even if an intermediate marker was lost (checkpoint flags `epoch-gap`).
    5. `phaseDesign[<P>].round` = max(state, count of `review-<T>-N.md`) where
       `T = phasedesign<P>` if artifact-derived redesigns == 0, else
       `phasedesign<P>-r<R>` for the current (highest) epoch R — count ONLY the current
       epoch's round files (a redesign resets the round with a fresh cap-8).
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
  "slices": {}, "phaseDesign": {}, "phaseReview": {}, "lastGate": null,
  "verify": { "attempts": [] }, "ship": { "suite": null, "conformance": null, "prUrl": null },
  "sessionId": null, "autoContinue": true, "waiting": null, "rebirth_pending": false,
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

`waiting = "rebirth"` is the lone CONTINUE exception: it is set-to-pause in the
OUTGOING session (so its turn can end at a safe boundary after a context-pressure
checkpoint) and auto-cleared-as-continue by the resume path in the INCOMING session —
it is NOT a STOP awaiting a human answer. The hook reads only `waiting`'s truthiness, so
it lets the turn end on `rebirth` exactly as on any pause; the resume path (§ Run setup &
resume) clears it and drives forward.

## Durable checkpoint contract (safe boundary)

Every checkpoint-proof input is a durable artifact (git refs + `$RUN_DIR` files), never
the coordinator's self-report. Two marker families carry the contract:

- **Redesign epoch markers — `$RUN_DIR/redesign-<P>-r<R>.marker`.** Written by the
  step-4 REDESIGN handler as its FIRST action, strictly BEFORE the
  `phaseDesign[<P>].redesigns`/`round` mutation; `R` = (highest existing epoch for
  `<P>`) + 1. Create-only and append-only for the life of the run — never modified or
  deleted; if the file already exists → STOP (a duplicate write means a state bug).
  Atomic write: `$RUN_DIR/.tmp.<name>` then `mv`. Content (informational — the NAME is
  the load-bearing datum):
  `{"phase": <P>, "epoch": R, "runId": "<runId>", "at": "<iso>", "trigger": "<what>"}`.
- **In-flight dispatch markers — `$RUN_DIR/inflight-<kind>-<scope>.marker`.** One marker
  per coordinator dispatch unit: `inflight-design-<P>.marker` (the whole `/drive-design
  phase <P>` run, spanning its author+review loop), `inflight-implement-<id>.marker`,
  `inflight-review-<scope>.marker` (scope = the review scope token — `design`, `<id>`,
  `phase<P>`, `phasedesign<P>[-r<R>]`; this ONE marker brackets the whole dual-voice
  chain: reviewer subagent → background codex → post-process → counter/state record),
  `inflight-harden-<P>.marker`, `inflight-verify.marker`, `inflight-ship.marker`.
  **Epoch resolution (single owner — the marker WRITER).** Whoever writes a
  `phasedesign<P>[-r<R>]` scope token resolves `<R>` at write time by the ONE rule: `R`
  = highest epoch among `$RUN_DIR/redesign-<P>-r*.marker` (0 → the bare `phasedesign<P>`;
  `R >= 1` → `phasedesign<P>-r<R>`). The coordinator applies this rule when it writes a
  remediation marker (Stage 2–4.5 gate) — the coordinator is the SOLE marker writer.
  drive-review.md applies the IDENTICAL rule only to resolve `<R>` for the phasedesign
  review/codex artifact filenames it writes; it never writes the in-flight marker.
  **Write-before-dispatch, clear-after-record:** the coordinator (main context) writes
  the marker (tmp + `mv`) immediately BEFORE the dispatch and `rm`s it only AFTER the
  result is fully recorded — artifact written + `state.json` updated + event-log line
  appended. No `pid`, no liveness probing. Content:
  `{"kind": "...", "scope": "...", "runId": "<runId>", "sessionId": "<dispatching session or null>", "startedAt": "<iso>"}`.

**Safe boundary** = no open `inflight-*.marker` AND no partial multi-step git mutation
detectable from git. Two steps carry NO marker by design: **assemble** — a partial phase
integration is git-detectable and inert (the step-5 rebuild-from-base is the rollback) —
and the **step-6 `git branch -f` advance** — a single atomic ref move whose not-yet-done
case resume already completes. **Finish-the-current-atomic-step:** a multi-write span
that must not be split (the REDESIGN handler's marker-write → state-write span) is one
atomic step — complete it before any checkpoint.

**The checkpoint proof:** `bin/drive-conformance.sh $RUN_DIR --mode checkpoint` — clean
iff no open in-flight marker, every `phaseInt/<runId>/<P>` ref resolves AND relates to
`drive/<runId>` by ancestry, every `slice/<runId>/<id>` ref resolves (slice branches are
cut from `phaseBaseSha`, so they are NOT ancestors of `drive/<runId>` — resolution only),
and every counter artifact is well-formed. Its `counters` output is the single
computation point for the artifact-derived counter values (it never reads `state.json`).
After it exits 0, write **`$RUN_DIR/checkpoint-complete.marker`** (tmp + `mv`; single
file, overwritten), content:
`{"at": "<iso>", "sessionId": "<outgoing>", "proof": <the mode's stdout JSON, incl. tip + counters>}`.
Validity rules:
- **A proof RECORD, never an authorization.** `proof.tip` must equal the current
  `drive/<runId>` tip — necessary, NOT sufficient (`drive/<runId>` moves only at the
  step-6 advance, so later work — even an open in-flight marker — can postdate a
  tip-matching file). Any consumer needing current safety MUST re-run
  `--mode checkpoint`; the marker attests only that a passing proof was computed at `at`.
- **SINGLE-USE — consumed at resume.** The resume path validates then DELETES it (valid
  or not) as its first act after the sessionId rebind; one marker covers at most one
  resume, and any later checkpoint re-proves from scratch and writes a fresh marker.

**Prove-then-pause:** a rebirth pause may be entered ONLY after a passing
`--mode checkpoint` plus a fresh `checkpoint-complete.marker`. If, after finishing the
current atomic step and ONE stranded-marker recovery attempt, the proof still fails →
STOP via Present human pause with `waiting = "stop:checkpoint-unprovable"` + the
violations JSON. Never set `waiting = "rebirth"` on a failing proof.

**Stranded-marker recovery (adopt / re-dispatch / STOP — never wait):** an open marker
with no live worker (died before the dispatch ran, or died after the work but before the
clear — indistinguishable on disk, treated the same):
1. **Adopt** only if the unit's COMPLETE artifact set exists and parses — for a review
   unit BOTH the round's `review-<scope>-N.md` (verdict line) AND a non-empty
   `codex-review-<scope>.md` sibling (any non-empty content satisfies; the first-line
   `CODEX_UNAVAILABLE` is the degradation convention, not a parsed gate token); for an
   implement unit, slice commits past `phaseBaseSha` with
   green slice tests. Then finish the recording (counters self-repair via the resume
   reconstruction rules), clear the marker, continue. A Claude review file WITHOUT its
   codex sibling is an unfinished dual-voice chain → step 2.
2. **Re-dispatch** otherwise: clear the marker and re-run the unit per the resume rules.
   For a review unit, first `mv` the scope's `codex-raw-<scope>.log` aside — an orphaned
   background codex may still be appending to it.
3. **STOP** if re-dispatch would breach the scope's cap (per the reconstructed counter) —
   the cap logic, not the marker, makes that call.

At resume, every open marker is stranded by definition (the dispatching session is
gone). In-session, a marker the coordinator is not actively awaiting gets the same rule.

## Coordinator soft-check (context-pressure, signal-only)

The SECONDARY context-pressure detection surface (the Stop hook is primary). At each
**safe boundary** in the Execute loop — after each per-slice review verdict is recorded,
after the phase-integration review verdict, after each HARDEN round verdict, and after the
phase advance — the coordinator reads its OWN latest transcript line and self-signals
`rebirth_pending` if the SOFT threshold is crossed:

1. Read the coordinator's own transcript (`$CLAUDE_CODE_SESSION_ID` → the project JSONL,
   or the harness-exposed `transcript_path`). `tokens` = the canonical sum over that
   transcript: the LAST assistant line's `input_tokens + cache_creation_input_tokens +
   cache_read_input_tokens` (jq `// 0` per absent field). No completed assistant line with
   `usage` → skip this boundary.
2. `model` = that line's `.message.model`. Resolve `window` from `bin/rebirth-thresholds.json`
   (the I1 substring rule over `model`; no `windows[].match` hit → `defaultWindow`).
3. If `tokens >= window * softThresholdFraction` AND `state.rebirth_pending` is not already
   `true`: set `state.rebirth_pending = true` (JSON-safe write) and append one event-log
   line `{"event":"rebirth_pending","via":"coordinator-soft","pct":<tokens*100/window>}`.

**SIGNAL-ONLY:** setting the flag does NOT checkpoint, hand off, or pause — the coordinator
CONTINUES autonomous work normally. Phase 3's safe-boundary handler consumes
`rebirth_pending` to checkpoint + pause; this surface only records the signal. **Idempotent:**
never re-set an already-`true` flag and never log a duplicate (the Stop hook's steer and this
self-check suppress each other once either fires).

Honest-coverage residuals: a single catastrophic turn can overshoot the window before any
boundary or Stop-hook firing; when the Stop hook is ABSENT this self-check is the ONLY
detection surface, firing only when the coordinator reaches a boundary.

### I1 — Safe-boundary rebirth handler (consume `rebirth_pending`)

The single site that CONSUMES `rebirth_pending` and ACTS. It runs at the SAME enumerated
safe boundaries as the Coordinator soft-check (after each per-slice review verdict, the
phase-integration review verdict, each HARDEN round verdict, and the phase advance),
IMMEDIATELY AFTER the soft-check (so the soft-check may set the flag and this handler
consumes it in the same boundary), plus any Stage-0/Plan/Verify/Ship natural boundary where
the coordinator is between dispatch units with no open marker. Steps, in this exact order
(this handler NEVER sets `rebirth_pending` — phase-2 detection does):

1. **Gate on the signal + the boundary.** Proceed ONLY if `state.rebirth_pending == true`
   AND this is a genuine safe boundary (no open `inflight-*.marker`). Falsy → do nothing,
   continue the pipeline.
2. **Finish the current atomic step** (§ Durable checkpoint contract). Let any in-flight
   unit return + record + clear its marker; finish a REDESIGN marker-write → state-write
   span. Do NOT enter the sequence mid-dispatch.
3. **PROVE resumability.** Run `bin/drive-conformance.sh $RUN_DIR --mode checkpoint`. On a
   FAILING proof (exit 1) make ONE stranded-marker recovery attempt (§ Durable checkpoint
   contract — adopt / re-dispatch / STOP, never wait), then re-prove. Still failing, or
   exit 2 (usage/IO/git error) → **fail closed: Never set `waiting = "rebirth"` on a
   failing proof.** A
   transient open-marker failure → continue the pipeline and re-attempt at the next safe
   boundary; a structural violation (`phaseInt-divergent`/`epoch-gap`/`regress-mismatch`/
   `unparseable-*`/`epoch-unmarked`) or exit 2 → STOP via Present human pause with
   `waiting = "stop:checkpoint-unprovable"` + the violations JSON (§ Durable checkpoint
   contract, Prove-then-pause).
4. **WRITE the durable marker.** On a passing proof (exit 0) write
   `$RUN_DIR/checkpoint-complete.marker` (§ Durable checkpoint contract — tmp + `mv`, single
   file, content `{"at": …, "sessionId": <outgoing>, "proof": <the mode's stdout JSON incl.
   tip + counters>}`).
5. **THEN set `waiting = "rebirth"`.** Only after the marker is written AND validated
   (re-read it; JSON parses AND `proof.tip` equals the `drive/<runId>` tip) set
   `state.waiting = "rebirth"` (JSON-safe write). The ordering is load-bearing and
   fail-closed: the marker write is step 4 and the `waiting` set is step 5 — marker BEFORE
   `waiting`, adjacent. (Setting `waiting` first would let the turn end before resumability
   is durable.)
6. **Present the handoff via Present human pause.** `waiting` is already set (step 5), so
   the routine emits the run graph (rendering the `↻ REBIRTH` node from
   `waiting=="rebirth"`) and presents the **rebirth handoff block** (the literal `/drive
   <runId>` resume line + re-armed `/goal`), then ENDS THE TURN. Do NOT clear `waiting`
   here — the OUTGOING session leaves it set; the INCOMING session's resume clears it
   (§ Run setup & resume).

**Leave-pending semantics:** within the SAME (outgoing) session `rebirth_pending` STAYS SET
through the pause — it is consumed at the next safe boundary (where this handshake fires)
and is NEVER reset inside the outgoing session; it is reset to `false` exactly ONCE, at the
sessionId-rebind step on a fresh-session resume (§ Run setup & resume). If the human ignores
the handoff and the outgoing session keeps going, `waiting="rebirth"` +
`checkpoint-complete.marker` persist; the next safe boundary re-observes `rebirth_pending`
still true and re-presents (re-proving — the marker is record-not-authorization). No
double-handoff: the marker is single-use, consumed only by a `/drive <runId>` resume.

**Gate/STOP precedence over rebirth.** At a boundary where BOTH `rebirth_pending == true`
AND the next pipeline action is a Gate A / Gate B / a non-decision STOP: the **gate/STOP
wins** — present the gate/STOP (its own `waiting` value), NOT `waiting="rebirth"`. The
human is present at that pause and can resume in a fresh session if they wish: BOTH Gate A
and Gate B hand the next leg's `/goal` line on approval, and the user, knowing the runId,
pastes `/drive <runId>` into a fresh session themselves — NEITHER gate emits a `/drive
<runId>` resume token (that runId resume line is the rebirth handshake's distinct
contribution). `rebirth_pending` does NOT carry forward: on the fresh-session resume it is
reset to `false` at the sessionId-rebind step, so a still-pressured run re-detects pressure
from the successor's own transcript growth and hands off at the next safe boundary there —
no handoff is lost; the flag is re-derived, not persisted.

## Present human pause (shared routine)

This is the **ONLY** way `/drive` pauses for the human — Gate A, Gate B, every
non-decision STOP, and every `AskUserQuestion`. Go through these steps in this exact
order; emitting the run graph is a mandatory step (step 2) so it can never be
forgotten:

1. **Set `state.waiting` FIRST** to the pause reason — `"gateA"`, `"gateB"`,
   `"stop:<short>"`, `"ask:<header>"`, or `"rebirth"`. This satisfies the
   autonomous-continuation contract above (set `waiting` before pausing) and lets the run
   graph derive `← YOU ARE HERE` from it. Unlike the others — which await a human ANSWER —
   `"rebirth"` awaits a FRESH-SESSION RESUME: the resume path auto-clears it and continues
   (§ Run setup & resume), so it is set-to-pause in the outgoing session and
   auto-cleared-as-continue on resume, never a STOP.
2. **Emit the run graph** (per § *Emit run graph (shared step)* below) — it reads the
   just-set `state.waiting`.
3. **Present** the gate text / STOP reason, or call `AskUserQuestion`; then end the
   turn. Clear `waiting = null` the instant autonomous work resumes. When
   `waiting == "rebirth"`, present the **rebirth handoff block** below (no `AskUserQuestion`
   — the user pastes or ignores) and end the turn WITHOUT clearing `waiting` (the incoming
   session's resume clears it, § Run setup & resume). Substitute `<runId>` = `state.runId`
   literally (the same value the run graph's `↻ REBIRTH` node shows):

   ```
   ↻ REBIRTH — this /drive run is approaching its context budget and has checkpointed
   to hand off to a fresh session. Your run is proven resumable (checkpoint passed).

   To continue, paste this into a FRESH Claude Code session:

     /drive <runId>

   Then re-arm the goal for the next autonomous leg:

     /goal The /drive run <runId> is resuming after a context-pressure rebirth and is
     driving the pipeline autonomously toward its next human gate (Gate A/B) or a
     non-decision STOP, OR is paused at a rebirth handoff (waiting="rebirth") awaiting my
     paste of the resume line. NOT met while autonomous implement/review/harden/verify work remains.

   (This session can stop now; the fresh session owns the run once it resumes.)
   ```

   The `/drive <runId>` line is the EXACT resume invocation (the resume path keys on an
   existing-runId `$RUN_DIR/state.json`); the `/goal` line re-arms the SUCCESSOR's leg goal,
   mirroring the Gate A/B re-arm.

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
   `phase`, `phaseList`, `designReview`, `phaseDesign[<P>].status`,
   `slices[<id>].{step,owns,deps}`, `phaseReview[<P>].status`, `verify`, `ship`.
   **The status fields pick glyphs only.** Every round COUNT
   (`designReview`, `slices[<id>].reviewCount`, `phaseDesign[<P>].round`,
   `phaseReview[<P>].{round, hardenRound}`) is artifact-derived (rule below); the matching
   state counter is read ONLY as the labeled DISPLAY fallback in the missing-artifact rule
   — never as a proof of a count.
2. **Fixed-format markdown files** (scope-token naming):
   - `design.md` (Goal → root cause). (`task.md` may also exist, but the Premises line is
     taken from `state.task`, which always has a writer — never an unsourced node.)
   - `review-<scope>-N.md` (`## Verdict: CONVERGED|FINDINGS`; `### [SEVERITY]` where
     BLOCKING/MAJOR = P1) — the Claude reviewer file, **persisted per round** (the `-N`
     suffix) — and its codex sibling `codex-review-<scope>.md` (same tags, or bare
     first-line token `CODEX_UNAVAILABLE`).
   - `design-phase<P>.md` (the per-phase detailed design) and its CURRENT-epoch review
     family `review-phasedesign<P>[-r<R>]-N.md` (`## Verdict: CONVERGED|FINDINGS`) +
     `codex-review-phasedesign<P>[-r<R>].md`, `R` = highest `redesign-<P>-r*.marker` in
     `$RUN_DIR` (no marker → the bare `phasedesign<P>` token).
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
  `[✓ done · ◐ current · ✗ stop · ↻ rebirth · ? unknown]`, plus the `‖` note (below).
- **One branch per stage that has STARTED**, in order
  `Premises · Plan · Execute · Verify · Ship` (a not-yet-started stage is omitted).
  "Started" = `state.stage` has reached/passed it OR its artifacts exist.
- **Premises:** one line — the resolved problem (first non-empty line of `state.task`,
  truncated).
- **Plan:** a `root cause:` one-liner (first sentence of `design.md` Goal; else
  `(pending)`); then the design-review rounds (combined verdict); then an explicit
  **`Gate A:` node line** — `APPROVED` when `state.lastGate=="A"` (or beyond), else
  `awaiting approval`. `waiting=="gateA"` anchors `← YOU ARE HERE` to this line.
- **Execute:** each phase (from `state.phaseList`) → first a **`design:`** child line from
  `phaseDesign[<P>]` (`✓ design: CONVERGED (k rounds)` when `status=="converged"`, else
  `◐ design: designing` — rounds/verdict from the CURRENT epoch's
  `review-phasedesign<P>[-r<R>]-*.md` + its codex sibling (`R` = highest
  `redesign-<P>-r*.marker`), same dual-voice rule as any review; **older epochs render
  ONLY as a redesign count on the `design:` line** — e.g. `✓ design: CONVERGED (2 rounds,
  1 redesign)` — old-epoch files never render as rounds) → then its slices (`state.slices` keyed by
  id-prefix == phase; `‖` between independent slices — see below). **Under each slice**
  (and each phase-integration), as child lines: one line per review round + combined
  dual-voice verdict, then `fix round k` child lines (or the numeric summary), then —
  at the phase level — an `assemble` line and an `advance` line (the latter iff
  `phaseReview[<P>].status=="hardened"`). Per-phase status from `phaseReview[<P>].status`
  (absent/no-status ⇒ `◐` in-progress). `stage==execute` + the current phase has empty
  `slices` ⇒ it is still in Tier-2 design (`phaseDesign[<P>].status != converged`) → render
  `◐ Phase N (designing…)` under the `design:` line; `stage` past execute + empty `slices` ⇒
  `(no slices recorded)`. Harden rounds from `harden-<P>-*.md` (`AppliedEdits: yes`
  count) + `codex-harden-<P>*.md`; `phaseReview[<P>].status` picks the glyph and
  `hardenRound` is the missing-artifact display fallback only.
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
  Stage 0); `rebirth` → a `↻ REBIRTH` CONTINUATION node (NOT a `✗ STOP` leaf) under the
  current stage's active node — the active Execute node (the current phase, or the current
  slice if the boundary was a per-slice review verdict) when `stage==execute`, else the
  active Plan/Verify/Ship node. Its node text is
  `↻ REBIRTH: context-pressure handoff (resume: /drive <runId>) ← YOU ARE HERE`, with
  `<runId>` = `state.runId`. It derives purely from `state.waiting=="rebirth"` +
  `state.runId` + `state.stage`/`phase` — no new artifact, no event-log parse. An
  unrecognized `waiting` still renders, with `← YOU ARE HERE` on a generic `✗ STOP:
  <reason>` leaf under the current stage (`rebirth` is RECOGNIZED, so it is NOT caught by
  this fallback).
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
`review-<id>-*.md`, `review-phase<P>-*.md`, the current-epoch
`review-phasedesign<P>[-r<R>]-*.md` (`R` = highest `redesign-<P>-r*.marker`),
`harden-<P>-*.md`, and their codex siblings (`codex-review-<scope>*.md`,
`codex-harden-<P>*.md`) — show the matching state counter as a DISPLAY HINT (its sole
graph use) with verdict `?`; never fabricate a verdict, never treat this fallback count
as proof.

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
/drive run graph  [✓ done · ◐ current · ✗ stop · ↻ rebirth · ? unknown]
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
/drive run graph  [✓ done · ◐ current · ✗ stop · ↻ rebirth · ? unknown]
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
   > /goal The /drive run for "<task>" has reached Gate A and is presenting the plan for my approval, OR is paused awaiting my input at a non-decision STOP or an AskUserQuestion, OR is paused at a rebirth handoff (waiting="rebirth") awaiting my paste of the resume line. NOT met while autonomous planning (design, autoplan, dual-voice review) work remains.
   > ```

   This complements the gates rather than overriding them: `/goal` continues the
   autonomous stages, while Gate A / Gate B / STOPs still pause for you (an
   AskUserQuestion blocks the turn regardless of any goal). The user may skip the goal;
   `/drive` still advances — it just won't auto-continue across turns.

   → `stage = plan`

### Stage 1 — Plan (gstack brain)
Run the PLAN stage (`/drive-plan` — `~/.claude/commands/drive-plan.md`): planner authors a
**high-level** `$RUN_DIR/design.md` (goal · approach · an ordered **`## Phases`** breakdown
— **no slice/interface detail**), autoplan reviews it, then the dual-voice **design-review**
primitive converges it (no open P1). **Gate A** = autoplan approved AND design converged —
the one human gate here. If no approved/converged design → STOP. → `lastGate = "A"`,
`stage = execute`

Parse the `## Phases` breakdown into the ordered phase ids in `state.phaseList`. **Slices
are NOT defined here** — `state.slices` stays empty; each phase's `/drive-design` (Execute
step 1) produces and records its own slices, in detail, against the real prior-phase code.

### Stage 2–4.5 — Execute (per phase; refs + worktrees only)

**Plan-gate + phase-design gate (defense-in-depth).** A `git worktree add … -b
slice/<runId>/<id>` is gated by BOTH the run-level **plan-gate** (whole-run design
converged) AND the per-phase **phasedesign-gate** (that phase's detailed design
converged). Before dispatching a phase's first IMPLEMENT, run
`bin/drive-conformance.sh $RUN_DIR --mode plan-gate` and `… --mode phasedesign-gate:<P>`
and proceed only if both report clean — plan-gate requires a `review-design-N.md`
`## Verdict: CONVERGED` + `codex-review-design.md`; phasedesign-gate requires the same for
the CURRENT epoch's family — `review-phasedesign<P>[-r<R>]-N.md` +
`codex-review-phasedesign<P>[-r<R>].md`, `R` = highest `redesign-<P>-r*.marker` in
`$RUN_DIR` (no marker → the bare `phasedesign<P>` token). On a violation, run the
named review (`/drive-review design` or `/drive-review phase <P> design` — drive-review.md
resolves the epoch itself) until it converges, then retry. At this remediation dispatch
the coordinator writes/clears `inflight-review-phasedesign<P>[-r<R>].marker` around the
`/drive-review` call, resolving `<R>` by the single epoch-resolution rule (§ Durable
checkpoint contract, In-flight dispatch markers) (in the normal flow a phase's design
reviews are bracketed by the
outer `inflight-design-<P>` marker — no separate review marker there). The PreToolUse
hook enforces both on the `git worktree add -b slice/…` (deriving `<P>` from the slice
id prefix); the in-prose check degrades gracefully
where the hooks aren't installed. (`/drive-design` already converges the phase design in
step 1, so this is a backstop in the normal flow.)

**Literal refs in gated commands.** Every command the gate inspects (the `git worktree
add -b slice/<runId>/<id>`, each per-slice `git merge slice/<runId>/<id>`, the
`git branch -f drive/<runId> phaseInt/<runId>/<P>` advance, and the ship push/PR) MUST
spell the refs out as **literal strings** with `<runId>`/`<P>` already substituted — NO
shell variables in the ref (e.g. `slice/$runId/$id`). The PreToolUse gate parses the
unexpanded command string, so a variable ref is invisible to it and silently bypasses
the gate.

For each PHASE in order (step 1 designs it, steps 2–5 build & review it, step 6 HARDENS
it before it advances). At each safe boundary in this loop — after a per-slice review
verdict (step 4), the phase-integration review verdict (step 5), a HARDEN round verdict and
the phase advance (step 6) — run the **Coordinator soft-check** (§ above), then the
**Safe-boundary rebirth handler** (§ I1 above — it consumes any `rebirth_pending` the
soft-check just set), before proceeding:

1. **Design the phase (detailed, against real code):** initialize
   `state.phaseDesign[<P>] = { "round": 0, "redesigns": 0, "status": "designing" }` if absent,
   then set `status = "designing"` (every entry — so a mid-design crash resumes as
   `designing`, not skipped). Do NOT reset `round` here: on resume it must keep counting so
   the design-review cap-8 holds; a fresh design pass (first entry, or a REDESIGN) gets its
   `round = 0` from the init / the REDESIGN handler. Create a **detached** read
   worktree at the featureBranch tip (force-clean any leftover:
   `git worktree remove --force $RUN_DIR/wt/design<P> 2>/dev/null; git worktree prune`, then
   `git worktree add --detach $RUN_DIR/wt/design<P> <featureBranch>` — detached so
   `featureBranch` stays checked out in NO worktree, which the step-6 advance needs). Run the
   DESIGN stage (`/drive-design phase <P>` — `~/.claude/commands/drive-design.md`) with that
   worktree as the subagent's cwd: it authors + dual-voice-reviews `design-phase<P>.md`
   against the real prior-phase code and populates `state.slices` for `<P>` (cap 8, no human
   gate; can't converge → STOP). Bracket the whole `/drive-design` unit with
   `inflight-design-<P>.marker` (write-before-dispatch, clear-after-record — § Durable
   checkpoint contract; the same discipline applies to EVERY dispatch below). Then
   `git worktree remove --force $RUN_DIR/wt/design<P>`.
2. **Freeze base:** `phaseBaseSha = git rev-parse <featureBranch>`; initialize
   `state.phaseReview[<P>] = { "round": 0 }` if absent.
3. **Dispatch slices** whose `deps` are CONVERGED, ≤ `concurrencyCap` in flight.
   Slices with **disjoint `owns`** run in PARALLEL. A `queued` slice is a **fresh build**, so
   FRESH-CREATE its worktree from base: branch absent → `git worktree add $RUN_DIR/wt/<id> -b
   slice/<runId>/<id> <phaseBaseSha>`; branch already exists (a REDESIGN re-queued this id
   from a prior build) → `git worktree remove --force` any stale `$RUN_DIR/wt/<id>`, reset the
   branch (`git branch -f slice/<runId>/<id> <phaseBaseSha>`), then `git worktree add
   $RUN_DIR/wt/<id> slice/<runId>/<id>` (no `-b`). Then copy
   the declared gitignored config allowlist (`.env`, …) in, and dispatch IMPLEMENT
   (`/drive-implement` — `~/.claude/commands/drive-implement.md`) with cwd = that worktree
   (`step=implementing`; marker `inflight-implement-<id>.marker`).
   Overlapping-`owns` ready slices are NOT parallelized — run by dep order; if the
   design left them unsequenced, STOP (planning bug). Excess past the cap queue.
4. **Per-slice loop:** when a slice's IMPLEMENT returns:
   - `DONE` → `step=awaiting_review`; run REVIEW scoped `slice <id>` (slice-local
     tests; marker `inflight-review-<id>.marker` brackets the whole dual-voice chain,
     and each re-run IMPLEMENT gets `inflight-implement-<id>.marker`).
     CONVERGED → `step=converged`, then **`git worktree remove` its worktree
     (keep the slice branch for assembly)** — frees a concurrency slot + disk, so
     worktree count stays ≤ cap regardless of slices-per-phase. FINDINGS →
     `step=needs_fix`; if its `reviewCount < 8` re-run IMPLEMENT then REVIEW; if `>=8` → STOP.
     A `needs_fix` re-run is **addressing findings, not starting fresh** — its branch holds
     committed work to keep. The worktree normally still exists (only CONVERGED removes it);
     if it was removed (crash/resume), **RE-ATTACH** to the existing branch — `git worktree
     add $RUN_DIR/wt/<id> slice/<runId>/<id>` (no `-b`, NO `branch -f` reset) — never reset to
     `phaseBaseSha`, which would discard the commits the fix builds on.
   - `REDESIGN` → the slice's assumption-check hit a big divergence (the phase design is
     stale vs the real prior-slice code, or a slice needs files outside its ownership).
     FIRST action — strictly BEFORE the `redesigns`/`round` mutation — write the epoch
     marker `$RUN_DIR/redesign-<P>-r<R>.marker` (`R` = highest existing epoch for `<P>`
     + 1; create-only, tmp + `mv`; marker already exists → STOP, state bug). The
     marker-write → state-write span is one atomic step w.r.t. checkpointing (§ Durable
     checkpoint contract); re-queue may follow a checkpoint.
     Then `phaseDesign[<P>].redesigns += 1`; at `>= 3` → STOP (a phase that
     keeps breaking its own design needs a human). Else set `phaseDesign[<P>].round = 0`
     (this redesign is a fresh design pass → fresh cap-8) and re-run step 1's design (it
     merge-updates `state.slices`) — every subsequent phasedesign review for `<P>` uses
     the epoch-qualified scope token `phasedesign<P>-r<R>` (resolved by drive-review.md);
     `git worktree remove --force` the worktree of any slice id the redesign dropped (leave
     its branch — assemble only merges ids still in `state.slices`). Re-dispatch from step 3.
   - `BLOCKED`/`NEEDS_CONTEXT` → `step=blocked`, STOP that slice + surface; other
     in-flight slices continue; the phase can't integrate until it resolves.
5. **Assemble (idempotent)** once ALL slices in the phase are `converged`:
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
   worktree (marker `inflight-review-phase<P>.marker`).
   - CONVERGED → `phaseReview[<P>].status = converged`, then **HARDEN** (step 6).
   - FINDINGS → route each P1 to the responsible slice (`step=needs_fix`, re-dispatch —
     re-attaching its worktree to the existing branch per step 4, preserving its commits —
     loop its cap-8), then **re-assemble from scratch**.
6. **Harden (per phase, after the phase review converges)** — run the HARDEN stage
   (`/drive-harden phase <P>` — `~/.claude/commands/drive-harden.md`) IN the
   `phaseInt/<runId>/<P>` worktree (`phaseReview[<P>].status = hardening`; each
   `/drive-harden` invocation gets `inflight-harden-<P>.marker`). It is a mutating
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
`featureBranch` tree (marker `inflight-verify.marker`); write `$RUN_DIR/verify.md`.
Report-only. Honor "no qa".
Append each e2e/QA attempt's outcome to `state.verify.attempts`
(`{result:"PASS"|"FAIL"}`) — the ordered array is the run graph's Verify source and its
false-negative → re-verify saga.
→ `stage = ship`

### Stage 5 — Ship (once)
Run the SHIP stage (`/drive-ship` — `~/.claude/commands/drive-ship.md`) on `featureBranch`
(marker `inflight-ship.marker`): promote
`$RUN_DIR/decisions.md`+`followups.md` into the repo ledgers, run the full suite
(red → retry once → STOP), build the **single** commit + PR, **Gate B** (approve
diff), then push/open PR. → `lastGate = "B"`, `stage = done`

## Completion

Report: design path, per-phase verdicts, PR link; a one-line summary of every
decision promoted this run; `followups.md` entries; the event-log path; anything
uncertain. Note any worktrees/branches left for inspection.
