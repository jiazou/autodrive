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
- `jq` on PATH (used by the conformance checker — ship, checkpoint, and state-lint);
  `gh` (or `glab`) on PATH for ship.

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
(fresh run only — a resume reuses an existing id). **Atomic collision claim:**
`<timestamp>` is second-resolution, so the runId is NOT unique by construction — claim it
atomically. `mkdir -p` the parent `~/.claude/harness-runs/`, then claim the leaf with
**plain `mkdir "$RUN_DIR"` (NOT `mkdir -p`)** — an atomic test-and-create that fails if the
dir already exists. This claim is the FIRST setup step — it **precedes** `featureBranch`
creation and the first `state.json` write. On an **already-exists** failure (EEXIST — a
prior or concurrent run owns the id) append a numeric disambiguator (`-2`, `-3`, …) to the
runId and retry the leaf `mkdir`; that success is the claim. Any OTHER `mkdir` error
(permissions, bad path) is a real failure → STOP, never retry. Never reuse an existing
run's `$RUN_DIR`. All per-run artifacts live in `$RUN_DIR` (absolute path), reachable from
any worktree. Append a line to `$RUN_DIR/event-log.jsonl` at every dispatch /
verdict / merge / gate.

- **Resume:** if invoked with an existing runId (its `$RUN_DIR/state.json` exists), load it
  and reconcile from git — `git worktree list`, branch tips, and ancestry are authoritative;
  state fields are hints. Never re-dispatch, advance, or clean up on a state value alone:
  **Auto-trigger CID gate (parent — evaluated BEFORE the child steps; the child index map is
  untouched).** If this resume was fired by an auto-resume trigger (it carries a resume payload
  `CID_N` — an env var / command arg the scheduling capability set on the fired session,
  § I1 step 5.7, D2), proceed to the reconciliation below ONLY IF `state.pendingCID == CID_N`
  AND `waiting == "rebirth"`. Otherwise EXIT immediately, writing NO `state.json` — the
  checkpoint was already resumed/advanced; a late/duplicate auto-trigger is a clean no-op and
  NEVER reconciles as the sole resumer (an auto-trigger NEVER takes the sole-resumer path). A
  HUMAN paste `/drive <runId>` carries no `CID_N` and is the GENERAL resume, unaffected.
  **`state.pendingCID` lifecycle (a resume-ROUTING HINT, never a proof input).** I1 records
  `state.pendingCID = CID` in the SAME JSON-safe write that sets `waiting="rebirth"` (I1 step 5;
  CID from the step-4 marker content, § I1 step 5.7). A completed rebirth resume CLEARS
  `state.pendingCID` in the same write that sets `waiting=null` (the rebirth-continue bullet).
  `pendingCID` is a TOLERATED-EXTRA state.json field (template default `null`); it is NOT a
  CORE key and NOT state-lint-required (state-lint tolerates it) and is NOT documented in
  CLAUDE.md. The fail-closed dual-mode re-prove stays the CONTINUE authority; `--mode
  checkpoint` never reads state.json.
  - **sessionId rebind (FIRST, on ANY resume into a new session):** **Atomic rebirth CLAIM
    (the FIRST action of this bullet, ONLY when `waiting == "rebirth"` — D26).** The
    marker-claim is a REBIRTH-resume mechanism: the claim is rebirth-gated (a non-rebirth
    resume never claims). The WRITE-DISCIPLINE INVARIANT is that only the rename-winner or the
    non-rebirth sole-resumer writes state.json; a loser to a current-CID claim-target writes
    NOTHING and exits; an auto-trigger never takes the sole-resumer path; detection is
    glob-by-CID + proof.tip==tip.
    (a) When `waiting != "rebirth"`: SKIP the claim entirely and proceed straight to the
    capture/rewrite below → normal reconcile. A leftover `checkpoint-complete.marker` from an
    I1 step-4→step-5 crash is inert (ignored, overwritten by the next I1 checkpoint) — NO
    claim, NO loser path, NO clobber.
    (b) When `waiting == "rebirth"` (a real rebirth resume ALWAYS carries `state.pendingCID` —
    I1 sets it atomically with `waiting="rebirth"` at step 5): IF
    `$RUN_DIR/checkpoint-complete.marker` is PRESENT, read its content, compute `CID`
    (§ Durable checkpoint contract), then VERIFY `CID == state.pendingCID` BEFORE claiming
    (the routing hint I1 set atomically with `waiting="rebirth"` at step 5; a real rebirth
    resume's marker-content CID ALWAYS equals `pendingCID`). On a MATCH (`CID ==
    state.pendingCID`) atomically `os.replace` it →
    `$RUN_DIR/checkpoint-claimed-<$CLAUDE_CODE_SESSION_ID>-<CID>.marker`; the winner claims
    ONLY on a match, so its claim-target is ALWAYS keyed on `pendingCID` and the loser's
    `pendingCID`-keyed glob always matches it → no double-drive. On a MISMATCH (`CID !=
    state.pendingCID` — a stale / forged / wrong-handoff marker) do NOT claim and do NOT
    continue: STOP fail-closed via Present human pause with `waiting =
    "stop:checkpoint-unprovable"` (both racers hit the same mismatch and STOP → no
    double-drive; failing closed is safer than claiming under the wrong key). Exactly one
    racer's rename succeeds — the WINNER.
    · Winner (rename succeeded) → continue to the capture/rewrite below → the marker-consume
    and rebirth-continue bullets → drive.
    · Loser (`os.replace` raised ENOENT on the source): a REAL winner of the CURRENT checkpoint
    exists IFF a claim-target `checkpoint-claimed-*-<state.pendingCID>.marker` exists whose
    content `proof.tip` equals the `drive/<runId>` tip — glob the CURRENT `state.pendingCID` +
    content (NOT the tip, NOT a name rebuilt from `state.sessionId`; a stale same-tip leftover
    of an OLDER CID is IGNORED; glob+content only, NO liveness). Match → write NOTHING, leave an
    advisory note, and EXIT (safe — drive-stop-hook.py `_allow()`s a run-less session; a
    crashed-winner recovery is MANUAL: `mv $RUN_DIR/checkpoint-claimed-<sid>-<CID>.marker
    $RUN_DIR/checkpoint-complete.marker` then re-paste `/drive <runId>`). No match, OR
    `state.pendingCID` absent (a FORGED rebirth — UNREACHABLE for a real rebirth resume, which
    always has pendingCID) → fall through to the rebirth-continue bullet's fail-closed re-prove
    → `stop:checkpoint-unprovable`, exactly as today (no live winner to clobber).
    **Then, before the
    overwrite below, capture the ephemeral fresh-session flag** `freshSessionResume =
    (state.sessionId != $CLAUDE_CODE_SESSION_ID)` reading the OLD persisted
    `state.sessionId` — computed UNCONDITIONALLY so it is defined on BOTH branches (`true` →
    a fresh-session resume; `false` → a same-session re-paste), consumed by the
    Fresh-session-orientation bullet below. It is an ephemeral coordinator variable — NO new
    `state.json` field. Then rewrite
    `state.sessionId` to the live `$CLAUDE_CODE_SESSION_ID` (null if unset) BEFORE
    reconciling anything — the Stop hook attributes a run by exact sessionId match, so a
    stale id kills auto-continue and rebirth detection. In the SAME JSON-safe write (the jq
    rule below), reset `state.rebirth_pending = false` — uniformly on ANY fresh-session
    resume (keyed on `state.sessionId != $CLAUDE_CODE_SESSION_ID`), NOT gated on a
    `rebirth` waiting. `rebirth_pending` is derived from the OUTGOING session's transcript
    growth, gone on a fresh resume, so the signal is stale and the successor re-derives it
    from its own growth (the Stop hook's steer re-sets it). `rebirth_pending` is reset to `false`
    by the RESUME consumer on exactly two scoped paths — the SAME logical re-arm (idempotent),
    re-derived by the current driver's own detection: (a) HERE at the sessionId-rebind, on any
    FRESH-session resume (`state.sessionId != $CLAUDE_CODE_SESSION_ID`), uniform over all
    `waiting` values; (b) on the passing-proof `rebirth`-continue path below, which covers the
    SAME-session re-paste the rebind skips. It is NOT reset on any other resume: a same-session
    NON-`rebirth` resume (a Gate A/B/STOP run re-pasted in the same session) hits neither path,
    so a legitimately-deferred `rebirth_pending` PERSISTS and I1 still hands off at the next
    safe boundary (§ I1 Gate/STOP precedence). A Gate A/B/STOP/crash run resumed in a FRESH
    session carrying a stale `rebirth_pending = true` re-arms cleanly here (path a), so the
    successor's safe-boundary handler does not fire a spurious empty handoff at its first
    boundary.
  - **Consume `checkpoint-complete.marker` (single-use):** on a `rebirth` WINNER path the
    marker was already CLAIMED (the atomic rebirth-gated `os.replace` that is the FIRST action
    of the sessionId-rebind bullet), so the marker file has MOVED to the claim-target
    `checkpoint-claimed-<sid>-<CID>.marker`: validate it FROM THE CLAIM-TARGET the winner
    renamed to (JSON parses AND `proof.tip` equals the current `drive/<runId>` tip) — record
    this validity as `markerValid`. The winner REMOVES the claim-target on completion
    (single-use); a stale same-tip leftover of an OLDER CID is harmless because loser-matching
    is CID-keyed (§ sessionId-rebind bullet). Resume never REQUIRES the marker for a
    non-`rebirth` resume: no claim happened, so missing/invalid means reconcile from scratch.
    (Format + validity rules: § Durable checkpoint contract.)
  - **`waiting == "rebirth"` → re-proven CONTINUE (fail closed), NOT a STOP.** A
    `rebirth`-waiting run found on resume is the outgoing session's context-clear handoff —
    either a context-pressure rebirth (class A) or a deterministic seam (class B: Gate A
    approval, phase advance); the resume is identical for both.
    `waiting = "rebirth"` is set ONLY by the I1 handler AFTER a passing proof + a durable
    `checkpoint-complete.marker` (§ I1), so the resume consumer RE-PROVES resumability before
    continuing — it does NOT trust the marker's tip alone (per § Durable checkpoint contract,
    a tip-matching marker is *necessary, NOT sufficient*: later work — an open in-flight
    marker, a mid-flight redesign span — can postdate a tip-matching file, so any consumer
    needing current safety MUST re-run the proof). **RE-PROVE via BOTH
    `bin/drive-conformance.sh $RUN_DIR --mode checkpoint` AND `bin/drive-conformance.sh
    $RUN_DIR --mode state-lint`** (§ Durable checkpoint contract, the proof = both modes,
    both clean — a `state-lint` failure on resume fails closed exactly like a checkpoint
    failure; the winner re-sources `markerValid` from the CLAIM-TARGET it renamed to, and that
    `markerValid` is corroborating evidence only, never the authorization): a passing proof
    (BOTH exit 0) re-establishes resumability → clear `state.waiting = null`, clear
    `state.pendingCID = null`, AND reset `state.rebirth_pending = false` (one JSON-safe write),
    then as its FINAL acts REMOVE the claim-target `checkpoint-claimed-<sid>-<CID>.marker` it
    validated `markerValid` from and CONSUME this checkpoint's
    `auto-resume-scheduled-<CID>.marker` (§ I1 step 5.7), and continue autonomous reconciliation
    exactly as any resume. The `rebirth_pending` reset belongs ONLY on this passing-proof
    CONTINUE branch (never before the re-prove, never on the fail-closed branch below — those
    must leave the signal intact), and it is UNCONDITIONAL w.r.t. the sessionId-rebind: it does
    NOT depend on the rebind having fired (a SAME-session re-paste of `/drive <runId>` keeps
    `state.sessionId` unchanged, so the rebind-step reset is skipped, yet the run still drained
    the outgoing handoff and must re-arm). A `rebirth`-continue resume re-detects fresh in
    whoever drives now (same-session driver included), so the re-arm is guaranteed across both
    resume paths. **A failing/erroring proof, or
    a missing/stale marker, FAILS CLOSED** — do NOT silently clear+continue (a
    `waiting="rebirth"` set by a bug/sibling path without I1's prove→marker→wait sequence has
    no proof of resumability): STOP via Present human pause with
    `waiting = "stop:checkpoint-unprovable"` + the violations JSON (§ Durable checkpoint
    contract, Prove-then-pause). On the passing-proof CONTINUE path do NOT surface it as a
    paused-for-human state, do NOT re-present the handoff. (Distinct from a
    `gateA`/`gateB`/`stop:`/`ask:` waiting found on resume, which is re-presented because the
    human is back to an open question; `rebirth`'s "human action" was *starting this
    session*, which the resume itself proves happened — whether a fresh session or a same-session
    re-paste.) On a fresh-session resume the sessionId was already rebound and `rebirth_pending`
    already reset in that rebind step; on a same-session re-paste the rebind reset is skipped, so
    the unconditional reset above is the one that re-arms — either way `rebirth_pending` is `false`
    by the time autonomous work resumes (the SAME logical re-arm). This
    re-prove is the SOLE carve-out from the marker-consume bullet's "missing/invalid →
    reconcile from scratch" rule: a `rebirth` waiting requires a passing proof, not a
    from-scratch reconcile. Reconcile phase / counters from git + artifacts as normal.
  - **Pre-Execute resume route (phaseList × stage matrix — runs BEFORE Current phase):** the
    "not-started" boundary cannot be derived from absence-of-artifact (an empty `∀` over
    `phaseList` is vacuously true), so branch on `state.phaseList` emptiness HERE, before the
    ancestry-based Current-phase derivation. `phaseList` becomes non-empty ONLY at the atomic
    Gate-A transition, which sets `stage = execute` in the SAME `state.json` write, so in a
    well-formed run a non-empty `phaseList` ⟹ `stage ∈ {execute, finalize, verify, ship,
    done}` and an empty `phaseList` ⟹ `stage ∈ {premises, plan}`. This guard is a TOTAL
    function over the (emptiness × `stage`) matrix and FAILS CLOSED on BOTH malformed corners.
    Do **NOT** key this route on `state.lastGate` (D1: it false-routes done runs, false-blocks
    stale-gate execute runs, and is not on the `--mode state-lint` validated routing surface).
    **Each case below TERMINATES the resume in its branch — do NOT fall through to the
    Current-phase or any later Execute-oriented reconcile bullet except where it explicitly
    says "fall through".**
    - `state.phaseList` **empty** → branch by `state.stage`, mirroring the `--mode state-lint`
      rule (`bin/drive-conformance.sh`, empty phaseList legitimate ONLY at `premises`/`plan`):
      - `stage ∈ {premises, plan}` — the legitimate pre-Execute case:
        - Parked human pause — `state.waiting` ∈ {`gateA`, `ask:*`, `stop:*`} → **RE-PRESENT
          that pause** via the Present human pause routine (the human is back to an open
          question — the existing resume contract). Do NOT re-enter a stage or re-invoke a
          command. (`rebirth` cannot appear here — its own earlier bullet consumed it; `gateB`
          is impossible pre-Execute.)
        - Autonomous — `waiting == null` → re-enter the pipeline at the reconciled pre-Execute
          point: `stage == premises` → resume **Stage 0 (Premises)**; `stage == plan` → set
          `stage = plan` and **re-invoke `/drive-plan`** to continue design-review convergence.
          Do **NOT** re-enter Stage 0 Premises when `task.md`/`design.md` already exist (that
          would re-ask the human the premise).
      - `stage ∈ {execute, finalize, verify, ship, done}` or unknown → an empty `phaseList`
        here is the exact malformed state `--mode state-lint` flags `phaselist-malformed` (the
        Gate-A transition writes `stage=execute` + parsed `phaseList` in ONE atomic write, so a
        clean `{stage:execute, phaseList:[]}` is unreachable). **Fail closed: STOP** via the
        Present human pause routine (`waiting = "stop:phaselist-malformed"`) with the
        inconsistency — **never silently restart at Plan** (which would DISCARD real
        Execute/Finalize progress, a wrong-outcome mirroring the bug this fix removes).
    - `state.phaseList` **non-empty** → branch by `state.stage` (the symmetric malformed corner
      `--mode state-lint` UNDER-polices — it flags only the EMPTY case outside premises/plan,
      NOT a non-empty phaseList at premises/plan):
      - `stage ∈ {execute, finalize, verify, ship, done}` → **fall through UNCHANGED** to the
        Current-phase / PAST-Execute derivation below (the ancestry `∀` is now over a non-empty
        set, so it can no longer be vacuously true). Done / mid-Execute / finalize / verify /
        ship resumes all take this path exactly as today.
      - `stage ∈ {premises, plan}` or unknown → **fail-closed STOP**
        (`waiting = "stop:phaselist-malformed"`): a non-empty `phaseList` at a pre-Execute
        stage is the SYMMETRIC malformed corner. The atomic Gate-A write makes it unreachable
        in a clean run — a legitimate resume's non-empty `phaseList` ALWAYS carries
        `stage ≥ execute`, so this NEVER false-blocks a legitimate resume; it fires only on
        genuine corruption. Never fall through to the Current-phase derivation from here.
  - **Current phase (reached ONLY when `state.phaseList` is non-empty — the pre-Execute route above terminates every empty-`phaseList` resume in its own branch):** `state.phase` = the lowest phase in `state.phaseList` whose
    `phaseInt/<runId>/<P>` is not yet an ancestor of `featureBranch` (branch absent, or
    `git merge-base --is-ancestor phaseInt/<runId>/<P> <featureBranch>` fails). All are
    ancestors → the run is PAST Execute; distinguish **finalize** (Stage 4c) from
    **verify** (Stage 4b) by the finalize ARTIFACT, NOT `state.stage` alone (the run's
    git-truth discipline): finalize has CONVERGED iff the highest-N `review-finalize-*.md`
    exists, its first `## Verdict:` line is `CONVERGED`, AND its **first `## AppliedEdits:`
    (header) line reads exactly `## AppliedEdits: no`** (a fix round is non-terminal), AND a
    NON-EMPTY
    `$RUN_DIR/codex-review-finalize.md` exists (the codex sibling — matching
    `bin/drive-conformance.sh`'s `--mode ship` `codex_present` check and `drive-ship.md`
    precondition #3, so all three finalize-CONVERGED surfaces use the IDENTICAL criterion),
    AND its `reviewed-sha` (call it
    `R`) is an ANCESTOR of the current `featureBranch` tip with `R..tip` ⊆ the 4-file
    `SHIP_LEDGER_ALLOWLIST` {`.harness/decisions.md`, `.harness/followups.md`, `TODO.md`, `.harness/codex-refutations.md`}
    and ≤ 1 commit — the SAME tolerant (a)(b)(c) ancestor + allowlist + `≤ 1 commit`
    criterion the `--mode ship` gate uses, NOT strict `reviewed-sha == tip`. Finalize
    CONVERGED → `stage = verify`; otherwise (no finalize artifact, a FINDINGS terminal
    artifact, a first `## AppliedEdits:` line that is not `## AppliedEdits: no` (a fix round
    `yes`, mid-flight `pending`, or missing), a missing/empty `codex-review-finalize.md`
    sibling, or a `reviewed-sha` that is not such a tolerant ancestor of the tip) →
    `stage = finalize`. **The tolerant test (not strict `==`) is load-bearing at resume**
    because ship commits the ledger BEFORE its suite-red STOP and BEFORE Gate B — so a
    resume CAN land post-ledger-commit. It covers BOTH cases: the just-converged
    pre-ledger case (`R == tip`, `R..tip` empty) AND a resume after ship's single ledger
    commit (suite-red STOP or Gate-B pause, where `R..tip` is the lone allowlisted ledger
    commit). Strict `==` would misroute that post-ledger resume back to `stage = finalize`
    and re-run finalize on an already-ledger-committed tree. This determination stays
    derived from artifacts, not `state.stage`.
  - **Derived phase-design status:** the current phase's design counts as converged ONLY if
    the epoch-aware `bin/drive-conformance.sh $RUN_DIR --mode phasedesign-gate:<P>` passes
    for the CURRENT epoch — `phaseDesign[<P>].status` is a hint, never the trigger. Gate
    fails → treat the phase as `designing` and re-run Execute step 1 (re-AUTHOR via
    `/drive-design`, not merely re-review) before dispatching slices.
  - **Redesign cap at resume:** artifact-derived `redesigns >= 3` (reconstruction rule 4
    below) with the current epoch unconverged → STOP — the step-4 handler's verdict,
    re-derived without re-entering the handler.
  - **Stranded in-flight markers:** at resume, every open `$RUN_DIR/inflight-*.marker`
    **EXCEPT `inflight-heal-<P>.marker`** is stranded by definition (the dispatching
    session is gone). Apply the recovery rule in § Durable checkpoint contract — **adopt /
    re-dispatch / STOP, never wait** for a worker; adopt of a review unit requires BOTH the
    round's `review-<scope>-N.md` AND a non-empty `codex-review-<scope>.md` sibling.
    `inflight-heal-<P>.marker` is CARVED OUT of this generic recovery — it is owned by the
    resume all-phases heal sweep below (which recovers it keyed on the open marker,
    recomputing `base(P)` deterministically); re-dispatching it here by scope alone would
    strip the heal's `harden-regress` flag and `base=` override. A stranded `inflight-finalize.marker` is
    a review unit (scope `finalize`): adopt only if BOTH `review-finalize-N.md` (verdict
    line) AND a non-empty `codex-review-finalize.md` exist; else re-dispatch (first `mv`
    the `codex-raw-finalize.log` aside, as for any review unit); STOP if re-dispatch would
    breach `FINALIZE_CAP` per the reconstructed `finalizeRound`.
  - **Worktrees:** classify each `$RUN_DIR/wt/` worktree by its checked-out branch and
    remove stale ones with `git worktree remove` only — never `branch -D` (branch cleanup is
    the guarded assemble/advance steps' job). A `slice/<runId>/<id>` worktree is live until
    its slice is `converged`; a `phaseInt/<runId>/<P>` worktree is live only for the current
    phase with `phaseReview[<P>].status` not yet `hardened`. A `wt/finalize` worktree
    (checked out at `featureBranch`) is live while `stage == finalize` AND finalize has
    not CONVERGED (the run is still in/at the finalize stage — finalize-CONVERGED uses the
    § Current phase artifact criterion); otherwise it is stale →
    `git worktree remove --force`. A detached `wt/design<P>`
    worktree (the per-phase design read worktree) is never live across a pause → always
    `git worktree remove --force` it.

    **Done-via-resume teardown (mirrors drive-ship.md § After approval).** When the resume
    is the leg that brings the run to its terminal DONE state (it lands `stage="done"`),
    apply the SAME cd-out → remove → verify-removal → gated-`completedAt` → done-last
    sequence as drive-ship.md, anchored on the same proven-removal gate. The resume's
    existing stale-worktree removal for NON-terminal pauses (above) is UNCHANGED — those run
    `git worktree remove` WITHOUT a `completedAt` (the run is not done). The done-path adds:
    1. **Require a `-d`-VALID `repoRoot`, then `cd` OUT of any `wt/<name>` to it FIRST**, BEFORE
       any destructive verb. Validate `repoRoot` with an explicit `-d` check — mirror the
       helper's guard `[ -d "$rr" ]` EXACTLY; do NOT treat "`repoRoot` is set" as sufficient (a
       stale/deleted-but-present `state.repoRoot` makes the `git -C "<repoRoot>" worktree
       remove` calls FAIL yet leaves `trash` reachable — NOT fail-closed — and the absolute-path
       removals could delete the live cwd). **The destructive teardown REQUIRES a `-d`-valid
       `repoRoot`: if `repoRoot` is empty OR NOT `[ -d "$repoRoot" ]`, fail-closed for the WHOLE
       teardown — run NO `git worktree remove`/`prune`, NO `trash`, and DO NOT write
       `completedAt` / `stage="done"`.** Only with a valid `repoRoot`: select `target =
       "$repoRoot"` (a stable dir OUTSIDE every `wt/<name>` being removed); the `cd` is itself
       CHECKED (`cd "$target" || <fail-closed>`). **Fail-closed branch — invalid `repoRoot` OR a
       failed `cd`:** run NO destructive verb (no `git worktree remove`, no `trash`), leave the
       worktrees, and DO NOT write `completedAt` / `stage="done"` — the run stays NOT-done /
       not-sweepable, re-attempted on a later resume. (`repoRoot` is NOT re-derived — D7
       write-once; this is only the `-d` guard on the existing value.) The destructive steps 2-5
       run ONLY AFTER a `-d`-valid `repoRoot` AND a successful `cd` to it.
    2. Remove ALL drive-owned worktrees via `git -C "<repoRoot>" worktree remove --force` +
       `git -C "<repoRoot>" worktree prune` (extend the stale-only removal above to ALL
       drive-owned at done).
    3. `trash` the dead drive-owned `wt/<name>` dirs, and **VERIFY each `$RUN_DIR/wt/<name>`
       is gone on disk** (`[ ! -e "$RUN_DIR/wt/<name>" ]` — the per-tree removal-success proof).
    4. **GATE: write `completedAt` ONLY IF every required drive-owned worktree removal is
       PROVEN done** (all `wt/<name>` dirs gone) and not already present. If ANY removal could
       not complete (a dir still exists), DO NOT write `completedAt` and DO NOT write
       `stage="done"`; the run stays NOT-done / not-sweepable (fail-safe), re-attempted later.
       The marker is `printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$RUN_DIR/completedAt"`
       (one clean ISO line + trailing newline — the strict format the helper parses). The
       gate is load-bearing because the helper's `is_done()` keys off a parseable
       `completedAt` ALONE: a marker written before removals finished would itself make the
       run sweepable.
    5. **Run the `## Completion` wrap sequence NOW — BEFORE writing `stage="done"`**
       (`/drive-retro <runId>` → wrap-`/decant`). Step 4 wrote a **parseable** `completedAt`
       (the ISO marker), which already satisfies retro's completeness gate / `is_done()`, so the
       wrap is valid here; running it while `stage != "done"` and `waiting` is empty is the hook-protected
       window — the stop-hook keeps the coordinator working across turns, closing the
       turn-end/rebirth drop window (the hook fails open, so a hard crash is not prevented, but
       `stage` stays not-`done` and a resume retries this teardown). Best-effort/non-fatal still
       holds — a retro/decant failure is noted and does not block step 6.
    6. Write `stage="done"` LAST (after the marker AND after the wrap sequence). The wrap already
       ran, so `## Completion` emits only the Report — it is not re-invoked.
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
  - **Finalize (`stage == finalize`, not CONVERGED):** resume finalize on the preserved
    `$RUN_DIR/wt/finalize` worktree (don't rebuild); re-dispatch `/drive-finalize` per
    Stage 4c (its `FINALIZE_CAP = 3` reconstructed from `finalizeRound`, counter rule 6).
    If `wt/finalize` is absent (removed mid-pause), re-create it per Stage 4c step 1
    (`git worktree add $RUN_DIR/wt/finalize <featureBranch>`) before re-dispatching.
  - **Counter reconstruction (all six counters):** state.json is a resume-repair HINT,
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
    2. `phaseReview[<P>].round` = max(state, count of `review-phase<P>-N.md` files
       (pure-integer N) WITHOUT the `harden-regress: yes` marker) — no subtraction. A
       harden-regress review self-identifies with the `harden-regress: yes` header marker
       and is counted separately as marked-regress (the DISTINCT `reviewed-sha` among
       marked files); it never inflates the integration round. `distinct-marked-sha >
       harden-yes` is malformed → checkpoint flags `regress-mismatch` (a surplus only; a
       deficit is diagnosed, never STOPped).
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
    6. `finalizeRound` = max(state, count of `review-finalize-*.md` (pure-integer N) with
       `## AppliedEdits: yes`) — a confirming clean audit writes `AppliedEdits: no` and
       does NOT count (cap-3 is on fix rounds); never count all `review-finalize` files.
       (Mirrors rule 3's harden rule, but over the `review-finalize-*.md` family — NOT the
       harden loop. The checkpoint proof asserts ONLY the artifact-derived value;
       `state.finalizeRound` is a one-directional resume hint.)
  - **All-phases harden-regress heal sweep (after Counter-reconstruction and
    Stranded-marker recovery, before Fresh-session-orientation).** A stale harden-regress
    review — dropped between `AppliedEdits: yes` and the regress-review write — leaves a
    genuinely-hardened phase with a stale FINDINGS `review-phase<P>-N.md` terminal that
    false-blocks ship `no-phase-review` on resume, even for an already-**advanced** phase
    (whose `phaseInt/<runId>/<P>` ref survives advance — Execute step 6 removes only the
    integration worktree + slice branches, never the ref). This sweep heals it. It runs on
    resume BEFORE routing re-enters Execute (so it precedes any Execute-step-2
    `phaseBaseSha` overwrite) and observes every phase's frozen `phaseInt/<runId>/<P>` tip.
    Per phase `P` in `state.phaseList` (**advanced phases included**), in this ORDER
    (**marker-recovery BEFORE the trigger**):
    1. **FIRST recover any OPEN `inflight-heal-<P>.marker`** — keyed on the OPEN MARKER, not
       the trigger (the sweep OWNS this marker; generic recovery is carved out of it). The
       crash window is not covered by the trigger alone: `/drive-review` writes the marked
       Claude `review-phase<P>-N.md` BEFORE its codex sibling, so a crash after the marked
       file lands at the hardened tip leaves the terminal at `reviewed-sha == tip` (CONVERGED
       or FINDINGS) — which the stale-FINDINGS trigger (step 3, `reviewed-sha ≠ tip`) SKIPS,
       orphaning the marker (checkpoint never clean while it is open). Apply the
       stranded-marker rule (§ Durable checkpoint contract — **adopt / re-dispatch, never
       wait**; the heal has NO cap so STOP is unreachable):
       - **Adopt** if the COMPLETE artifact set exists — the marked `review-phase<P>-N.md`
         at the hardened tip (`reviewed-sha == git rev-parse phaseInt/<runId>/<P>`) AND a
         non-empty `codex-review-phase<P>.md` sibling. The heal COMPLETED (both artifacts
         are durable), so clear `inflight-heal-<P>.marker`; THEN inspect the adopted
         terminal's `## Verdict:` (first line) to decide continue-vs-STOP — the stale-FINDINGS
         trigger (step 3) will NOT make this call: it self-terminates on this at-tip terminal
         (`reviewed-sha == tip`).
         - **Adopted terminal CONVERGED (at the hardened tip) → healed:** continue (the same
           outcome as the fresh CONVERGED heal, step 5).
         - **Adopted terminal FINDINGS (at the hardened tip) → HONEST terminal NON-DECISION
           STOP, routed to MANUAL recovery** (the SAME path as the fresh-dispatch FINDINGS
           outcome, step 5): a genuine open P1 at the hardened tip — NOT automated closure and
           NOT a new false block (the terminal was ALREADY FINDINGS/ship-blocking before the
           heal). Surface a non-decision STOP (Present human pause, `waiting = "stop:<short>"`)
           reporting the phase + hardened tip and the documented MANUAL harden-regress
           recovery (bind the hardened tip, re-review/fix for real, NEVER forge). Shippability
           is UNCHANGED. Self-terminating: the at-tip `reviewed-sha` keeps the trigger from
           re-firing.
       - **Re-dispatch** otherwise (marked file at the tip but codex sibling missing/empty,
         OR no marked file): recompute `base(P)` deterministically (step 4 — it need NOT
         have survived the crash), first `mv` the `codex-raw-phase<P>.log` aside (an orphaned
         background codex may still be appending), re-run
         `/drive-review phase <P> harden-regress base=<base(P)>` at the hardened tip, then
         clear the marker. Idempotent: it binds the SAME hardened tip → SAME `reviewed-sha`
         → any stranded duplicate marked file is deduped by distinct-`reviewed-sha` → never
         trips the surplus guard. THEN inspect the re-dispatched terminal's `## Verdict:`
         (first line) to decide continue-vs-STOP — the stale-FINDINGS trigger (step 3) will
         NOT make this call: the re-dispatched terminal lands at the hardened tip
         (`reviewed-sha == tip`), which the trigger self-terminates on and SKIPS.
         - **Re-dispatched terminal CONVERGED (at the hardened tip) → healed:** continue (the
           same outcome as the fresh CONVERGED heal, step 5).
         - **Re-dispatched terminal FINDINGS (at the hardened tip) → HONEST terminal
           NON-DECISION STOP, routed to MANUAL recovery** (the SAME path as the fresh-dispatch
           FINDINGS outcome, step 5): a genuine open P1 at the hardened tip — NOT automated
           closure and NOT a new false block (the terminal was ALREADY FINDINGS/ship-blocking
           before the heal). Surface a non-decision STOP (Present human pause, `waiting =
           "stop:<short>"`) reporting the phase + hardened tip and the documented MANUAL
           harden-regress recovery (bind the hardened tip, re-review/fix for real, NEVER
           forge). Shippability is UNCHANGED. Self-terminating: the at-tip `reviewed-sha`
           keeps the trigger from re-firing.
    2. **Skip the fresh trigger (steps 3–5) for a phase with an open
       `inflight-harden-<P>.marker`** (single owner) — that phase is owned by the harden
       loop's stranded-marker recovery (harden persists `## Verdict: HARDENED` before
       clearing its marker, so a crash in that window leaves open-harden + hardened +
       FINDINGS; letting BOTH recover would double-dispatch → `marked > yes` → a HARD STOP).
       Step 1's heal-marker recovery is unconditional; this skip governs only the fresh
       trigger. (MAY also skip on an open `inflight-review-phase<P>.marker` to avoid
       co-dispatch — benign under distinct-sha; recommended.)
    3. **Compute the trigger** (all three required, else skip the phase):
       - **hardened(P):** the highest-N `harden-<P>-*.md` first `## Verdict:` line is
         `HARDENED` (no harden file / highest is FINDINGS → not hardened → skip).
       - **terminal FINDINGS:** the highest-N `review-phase<P>-N.md` first `## Verdict:`
         line is NOT CONVERGED.
       - **stale:** that terminal's `reviewed-sha` ≠ `git rev-parse phaseInt/<runId>/<P>`
         (a missing `reviewed-sha` counts as ≠tip).
       A CONVERGED terminal (marked OR unmarked) is NEVER re-reviewed (it already satisfies
       marker-agnostic ship b-i). A FINDINGS terminal already bound to the hardened tip
       (`reviewed-sha == tip`) is already-healed-or-genuinely-blocked → NEVER re-reviewed
       (self-termination).
    4. **Recover `base(P)` — keyed off `state.phaseList` ORDER (never arithmetic `P−1`; ids
       may be suffixed like `4a`/`4b`).** Let `prev` = the phaseList entry IMMEDIATELY
       PRECEDING `P`. `P` is NOT the first entry → `base(P) = git rev-parse
       phaseInt/<runId>/<prev>` (this ref survives advance, and equalled phase P's frozen
       `phaseBaseSha` at P's start). `P` IS the first entry → `base(P) = state.baseSha`.
       **LEGACY fail-closed:** if `P` is the FIRST phaseList entry AND `state.baseSha` is
       ABSENT, there is no durable base(1) and re-deriving is forbidden → do NOT auto-heal;
       surface a **NON-DECISION STOP** (Present human pause, `waiting = "stop:<short>"`)
       reporting the phase + hardened tip (`git rev-parse phaseInt/<runId>/<firstPhase>`)
       and the documented MANUAL harden-regress recovery (bind the hardened tip, re-review
       for real, NEVER forge — memory *drive-harden-regress-must-persist-terminal-converged*).
       Scoped to the first entry of a baseSha-absent run ONLY (P>1 heals off
       `phaseInt/<prev>`; a NEW run heals its first phase off `state.baseSha`).
    5. **Heal = ONE dual-voice re-review per resume leg** (NO `HEAL_CAP`, NO
       `state.healRound`): invoke `/drive-review phase <P> harden-regress base=<base(P)>` at
       the hardened tip, bracketed by a DISTINCT `inflight-heal-<P>.marker`
       (write-before-dispatch, clear-after-record). It writes into the
       `review-phase<P>-N.md` MARKED family (marker + `reviewed-sha == hardened tip`).
       Outcomes, both SELF-TERMINATING (the new highest-N carries `reviewed-sha == hardened
       tip`, so the trigger cannot re-fire next resume — no re-heal loop, no marked
       accumulation):
       - **CONVERGED → healed:** the terminal is now a CONVERGED marked regress at the
         hardened tip → ship b-i passes → the next sweep sees CONVERGED and does not
         re-trigger.
       - **FINDINGS → HONEST terminal NON-DECISION STOP, routed to MANUAL recovery.** A
         genuine open P1 at the hardened tip. This is NOT automated closure and NOT a new
         false block — the terminal was ALREADY FINDINGS/ship-blocking before the heal; the
         heal merely REPLACES a STALE block (an earlier tip) with a REAL one at the hardened
         tip. Because `state.phase` re-opens only the current/unadvanced phase, an advanced
         phase's real-FINDINGS is surfaced as a non-decision STOP (Present human pause) and
         routed to the documented MANUAL harden-regress recovery (bind the hardened tip,
         re-review/fix for real, NEVER forge). Shippability is UNCHANGED by the heal.
  - **Fresh-session orientation (LAST — after reconciliation, before autonomous work):**
    once all the reconciliation above has completed AND the run is proceeding to autonomous
    work (a reconcile that ends in a STOP takes the Present-human-pause path instead, which
    emits its own run graph), **if this is a fresh-session resume** (`freshSessionResume ==
    true`, captured at the sessionId-rebind bullet above), emit the context-of-execution
    summary (per § *Emit context-of-execution summary (shared step)*) so the zero-context
    successor session (and the watching user) is oriented from the reconciled git-truth
    state. Skip on a same-session re-paste (`freshSessionResume == false` — it already has
    conversational context, so a summary would be noise).
- **Fresh run:** assert the clean-tree precondition; record `baseRef` (the repo's
  default/integration branch, e.g. `main`); **pre-flight the base** (fast-forward
  `baseRef` to its remote — see below); create `featureBranch` from the (possibly
  fast-forwarded) `baseRef`;
  initialize and write `$RUN_DIR/state.json` in this shape (set `sessionId` from the
  `$CLAUDE_CODE_SESSION_ID` env var so the Stop hook can attribute this run to this
  session; leave it `null` if unset):

```json
{ "runId": "<id>", "task": "<task>", "stage": "premises",
  "baseRef": "main", "baseSha": "<git rev-parse baseRef>", "featureBranch": "drive/<id>", "repoRoot": "<git rev-parse --show-toplevel>",
  "phase": 1, "phaseList": [], "phaseBaseSha": null, "concurrencyCap": 4, "designReview": 0,
  "budget": { "ceilingCalls": null, "ceilingMin": null, "calls": 0, "startedAt": "<iso>" },
  "slices": {}, "phaseDesign": {}, "phaseReview": {}, "finalizeRound": 0, "lastGate": null,
  "verify": { "attempts": [] }, "ship": { "suite": null, "conformance": null, "prUrl": null },
  "sessionId": null, "autoContinue": true, "waiting": null, "rebirth_pending": false,
  "pendingCID": null,
  "designPath": "$RUN_DIR/design.md" }
```

**Build it JSON-safely — never string-substitute `<task>` into the template.** The
task is arbitrary user text (it can contain `"`, `\`, or newlines) and naive
interpolation corrupts the file. Construct it with a JSON tool, e.g.
`jq -n --arg task "$TASK" --arg id "$RUNID" … '{runId:$id, task:$task, …}'`, and the
same for every later write. Apply the same rule anywhere run text is embedded in
JSON (event-log lines, etc.).

**Record `repoRoot` (write-once at fresh-run setup).** Set `repoRoot = git rev-parse
--show-toplevel` (the driven repo — `/drive` runs inside it, so cwd at setup IS the driven
repo). Build it JSON-safely via `jq` like every other field (the never-string-substitute rule
above). It is **write-once at fresh-run setup and NEVER re-derived on resume** — a resume
re-pasted from any cwd reuses the persisted value. It feeds the retention helper's
`resolve_owning_repo` and the ship/resume teardown's cd-target selection.

**Record `baseSha` (write-once at fresh-run setup).** Set `baseSha = git rev-parse
<baseRef>` at the exact moment `featureBranch` is cut from the (possibly fast-forwarded)
`baseRef`. Build it JSON-safely via `jq`. It is the durable run-start base commit — the
first phase's heal diff base (§ resume all-phases heal sweep, `base(P)`). It is
**write-once at fresh-run setup and NEVER re-derived on resume** (mirrors the `repoRoot`
discipline) — `state.baseRef` is only a movable branch NAME, so a `main` that moves after
run start must not change `baseSha`. It is an OPTIONAL field: it is NOT a checkpoint proof
input (`--mode checkpoint` never reads `state.json`) and NOT a counter (no
`max(state,derived)` rule), and `--mode state-lint` does NOT require it (a legacy run that
predates the field routes and resumes normally; requiring it would false-reject every such
run).

**Atomic write — every `state.json` write goes through a temp file + `mv`.** Write to
`$RUN_DIR/.tmp.state.json.$$` (or equivalent) and `mv` it over `state.json`; never an
in-place redirect/truncate (`> state.json`) that can leave a torn file if the turn dies
mid-write. Resume reads `state.json` as a routing hint and a torn hint must never
half-parse — `--mode state-lint` would flag it `unparseable-state`. Mirrors the marker
tmp + `mv` discipline.

**Pre-flight the base (fast-forward `baseRef` to its remote — FRESH RUN ONLY, before
cutting `featureBranch`; NEVER on resume).** A run branches from the *local* `baseRef`;
without this it silently builds on a stale local `main`. Bring `baseRef` up to date with
its remote, but **fail-closed — never discard a local commit, never STOP or HANG the run
over it** (offline / no-remote / no-upstream / creds-required dev is all legitimate; this is
a convenience, not a gate). **Best-effort / fail-open-to-local:** any git error at any step
below — fetch failure, an unresolvable or ambiguous ref, `baseRef` absent as a local branch,
or a `branch -f` refused because `baseRef` is checked out in another worktree — folds to
*warn + proceed on the local `baseRef`*; the step never STOPs and never leaves `baseRef`
half-moved.

1. **Resolve the upstream.** `UP=$(git rev-parse --abbrev-ref "$baseRef@{upstream}" 2>/dev/null)`;
   if empty, fall back to `origin/$baseRef` when a remote named `origin` exists. **No remote
   or no upstream ref → skip** (log `preflight: local-only, skipped`) and proceed on the
   local `baseRef`. Split it: `REMOTE=${UP%%/*}`, `RBRANCH=${UP#*/}` — the upstream's OWN
   branch name, which need not equal `baseRef` (a local `main` may track `origin/trunk`, a
   fork may track `upstream/main`).
2. **Fetch — non-interactively.** `GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -oBatchMode=yes'
   git fetch --quiet "$REMOTE" "$RBRANCH"` — fetch the upstream's own branch (so the ref you
   reconcile against, `$UP`, is exactly the one just fetched) with prompts disabled: a
   creds/passphrase prompt must fail fast, never block the run. **Fetch fails**, or `$UP` still
   does not resolve afterward (remote with no fetch refspec) → warn, skip, proceed on local
   `baseRef`.
3. **Reconcile** — fully-qualify the local branch as `LB=refs/heads/$baseRef` (an unqualified
   `$baseRef` can bind to a same-named *tag*, and force-moving the branch after an ancestor
   test that resolved the tag would orphan a local commit). If `LB` does not resolve (no local
   `baseRef` branch / unborn repo) → skip. Rev-parse `LB` and `$UP` AFTER the fetch and compare:
   - **Equal** → already current; nothing to do.
   - **Local strictly behind** — `git merge-base --is-ancestor "$LB" "$UP"` true and the two
     SHAs differ → fast-forward the local branch to `$UP`: if `baseRef` is THIS worktree's
     checked-out branch (`git symbolic-ref --short -q HEAD` == `$baseRef`), `git merge --ff-only
     "$UP"`; else, provided `baseRef` is checked out in NO worktree (`git worktree list` — git
     refuses `branch -f` on a branch checked out anywhere; if it is, fold to warn+proceed),
     `git branch -f "$baseRef" "$UP"` (proven fast-forward by the ancestor test). Log
     `preflight: fast-forwarded <baseRef> <old>..<new>`.
   - **Diverged** — local `baseRef` has commit(s) not on `$UP` (the ancestor test is false;
     this also covers a purely-ahead unpushed `baseRef`) → **do NOT touch `baseRef`**;
     fast-forwarding would drop those commits. Proceed on the local base and **warn** (log +
     surface at Gate A): `preflight: local <baseRef> has N commit(s) not on <UP>; run proceeds
     on the local base`.

This fast-forward is the ONE sanctioned mutation of the user's base branch — reconciled with
the "never mutate the user's main working tree" invariant by the clean-tree precondition
asserted just above: a checked-out `baseRef` has no uncommitted work, so a `--ff-only` advance
is pull-equivalent and clobbers nothing, and being a fast-forward (never rebase/merge-commit/
`reset`) it can only ADD the remote's commits, never rewrite the user's. Because the
fast-forward moves the local `baseRef` branch itself, the recorded `baseRef` name still points
at the branch the run cut `featureBranch` from, so the `baseRef..featureBranch` diff (finalize,
ship) is honest at branch-cut time; the pre-existing caveat that `baseRef` is a *name* — a
concurrent session moving it mid-run, the shared-clone hazard — is unchanged by this step.

**GC-at-setup (best-effort, REPORT-ONLY, backgrounded).** AFTER the first `state.json`
write completes (NEVER on the `mkdir` claim critical path — a GC failure must never abort a
new run's setup), fire a best-effort retention sweep of stale sibling runs:

```
( bin/drive-retention.sh >>"$RUN_DIR/retention-gc.log" 2>&1 || true ) &
```

It is **REPORT-ONLY (no `--apply`)** per the Gate-A resolution (report-only default
accepted): it emits the would-sweep report to `$RUN_DIR/retention-gc.log` for visibility and
performs NO deletion. It is **swallowed** (`|| true`, stdout+stderr to `retention-gc.log` so
it never pollutes the coordinator's turn) and **backgrounded (`&`)** so setup never blocks on
a slow scan. The helper is always-exit-0 and time-bounded. The firing run's own residue is
live (not aged, not done) so it is never swept; every other live sibling is protected by the
classifier's waiting/inflight/done/age gates. The destructive `--apply` sweep is a manual
one-shot (run the helper by hand, report-then-`--apply`), NOT wired into this at-setup call.

Update `state.json` after every transition. Increment `budget.calls` on each
subagent/codex dispatch; if `ceilingCalls`/`ceilingMin` is set and exceeded → STOP
with a spend summary (budget circuit-breaker).

**Autonomous-continuation contract (`waiting`).** The `drive-stop-hook` (installed by
`bin/install-operating-rules.sh`, no-op if absent) keeps a run driving across turns
by reading `state.json`: it blocks the turn from ending while this
session's run has `stage != "done"` and `waiting` is empty, and allows it the moment
`waiting` is set or `stage = done`. So you MUST set `state.waiting` to a short reason
**before pausing for the human at any point** — Gate A, Gate B, every non-decision
STOP, or any AskUserQuestion — and clear it (`waiting = null`) the instant you resume
autonomous work. Forgetting to set it just means the hook nudges you to continue (it
biases toward letting you stop and fails open); it never forces you past a STOP. The
installed Stop hook is the SOLE turn-to-turn continuation mechanism; with the hook
**absent** an autonomous leg pauses at each turn-end and the user types "continue" to
advance — a manual-continue degradation consistent with the accepted no-hook posture. Set `autoContinue:false` to disable the hook for this run.

`waiting = "rebirth"` is the lone CONTINUE exception: it is set-to-pause in the
OUTGOING session (so its turn can end at a safe boundary after a context-clear checkpoint —
context-pressure OR a deterministic seam) and auto-cleared-as-continue by the resume path in
the INCOMING session —
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
  `inflight-harden-<P>.marker`, `inflight-finalize.marker`, `inflight-verify.marker`,
  `inflight-ship.marker`, and `inflight-heal-<P>.marker` (a DISTINCT kind bracketing the
  resume all-phases heal sweep's per-phase re-review — NOT the generic
  `inflight-review-phase<P>.marker`). **`inflight-heal-<P>.marker` is EXCLUDED from generic
  stranded-marker recovery** (below): it is owned SOLELY by the resume heal sweep, which
  recovers it keyed on the open marker (adopt / re-dispatch, recomputing `base(P)`
  deterministically). Re-dispatching it by scope alone as a plain `phase <P>` review would
  strip the heal's `harden-regress` flag AND its `base=` override → a new false ship-block.
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

**Observability sub-events (event-log vocabulary — ONE authoritative rule).** Sub-events extend
the `event-log.jsonl` VOCABULARY only: each is `date -u`-timestamped, jq-built (JSON-safe, like
every event-log line), APPEND-only, and **WRITE-ONLY — nothing parses them (`NEVER parse
event-log.jsonl` holds)**. Schemas (`<iso>` = `date -u +%Y-%m-%dT%H:%M:%SZ`):

| kind | schema | emitted at |
|---|---|---|
| subagent-started | `{"event":"subagent-started","kind":"<implement\|review\|design\|harden\|finalize\|verify\|ship\|heal>","scope":"<scope>","at":"<iso>"}` | write-before-dispatch, after the inflight marker is written + the subagent dispatched |
| codex-started | `{"event":"codex-started","scope":"<scope>","at":"<iso>"}` | when the background codex launches in a review/harden/finalize scope |
| suite-run-started | `{"event":"suite-run-started","scope":"<scope>","at":"<iso>"}` | immediately before a `bin/run-tests.sh` invocation |
| suite-run-finished | `{"event":"suite-run-finished","scope":"<scope>","result":"pass\|fail","at":"<iso>"}` | immediately after that suite run returns |
| fix-applied | `{"event":"fix-applied","scope":"<scope>","round":<int>,"at":"<iso>"}` | when a review/harden/finalize fix round commits an edit |
| idle_detected | `{"event":"idle_detected","kind":"<kind>","scope":"<scope>","startedAt":"<iso>","elapsedMin":<int>,"at":"<iso>"}` | the § idle seam below |

**`idle_detected` seam.** Bind it to the ONE universal clear-after-record step above: before
`rm`ing ANY `inflight-<kind>-<scope>.marker`, read its `startedAt`; if it parses as ISO AND
`date -u` minus `startedAt` > 30 min, append one `idle_detected` line
(`elapsedMin = floor(elapsed/60)`). **An absent/unparseable `startedAt` → NO line (fail-open)** —
never block or error on the observation. One rule, uniform across every inflight kind (D4/D15).

**Safe boundary** = no open `inflight-*.marker` AND no partial multi-step git mutation
detectable from git. Two steps carry NO marker by design: **assemble** — a partial phase
integration is git-detectable and inert (the step-5 rebuild-from-base is the rollback) —
and the **step-6 `git branch -f` advance** — a single atomic ref move whose not-yet-done
case resume already completes. **Finish-the-current-atomic-step:** a multi-write span
that must not be split (the REDESIGN handler's marker-write → state-write span) is one
atomic step — complete it before any checkpoint.

**The proof = BOTH modes, both clean** (the single authoritative definition every other
surface references): the handoff/resume proof is `bin/drive-conformance.sh $RUN_DIR --mode
checkpoint` (narrator-independent: git refs + durable artifacts, proves resumability) AND
`bin/drive-conformance.sh $RUN_DIR --mode state-lint` (the routing-hint sanity check —
guards the `state.json` routing fields the successor's resume reads). Both must exit 0
(clean) at the prove AND the re-prove points; either non-clean fails closed identically.
The two modes stay SEPARATE — `--mode checkpoint` still NEVER reads `state.json`;
`state-lint` is the ONLY mode that does — they are merely co-invoked at the same boundaries.

The `--mode checkpoint` half is clean iff no open in-flight marker, every
`phaseInt/<runId>/<P>` ref resolves AND relates to `drive/<runId>` by ancestry, every
`slice/<runId>/<id>` ref resolves (slice branches are cut from `phaseBaseSha`, so they are
NOT ancestors of `drive/<runId>` — resolution only), and every counter artifact is
well-formed. Its `counters` output is the single computation point for the artifact-derived
counter values (it never reads `state.json`). The `--mode state-lint` half is clean iff
`state.json` parses and its routing fields are present + meaningfully routable (non-empty
stage-aware `phaseList`, each slice's `step` in the valid enum, non-empty `owns`, array
`deps`, well-formed `verify`/`ship`).
After it exits 0, write **`$RUN_DIR/checkpoint-complete.marker`** (tmp + `mv`; single
file, overwritten), content:
`{"at": "<iso>", "sessionId": "<outgoing>", "nonce": "<32hex>", "proof": <the mode's stdout JSON, incl. tip + counters>}`.
The additive `"nonce"` (a 128-bit value `nonce="$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"`
— 32 hex, PORTABLE on macOS+Linux; NEVER `date +%s%N`, GNU-only) makes the marker's content
UNIQUE per handoff (the reader picks `proof.tip` only, so the nonce is transparent to it).

**CID — the per-handoff identity (nonce-unique).** `CID` = `shasum -a 256` over the WHOLE
marker content, first 12 hex (`shasum -a 256 <marker> | cut -c1-12`); **shasum absent → CID =
the first 12 hex of the `nonce`** (itself unique — never a bare `at`). Because the nonce is
unique per checkpoint, two same-tip/same-second checkpoints from the same session NEVER
collide. CID keys the claim-target (§ Run setup & resume), the scheduled-marker + auto-trigger
payload (§ I1 step 5.7), and `state.pendingCID`.

Validity rules:
- **A proof RECORD, never an authorization.** `proof.tip` must equal the current
  `drive/<runId>` tip — necessary, NOT sufficient (`drive/<runId>` moves only at the
  step-6 advance, so later work — even an open in-flight marker — can postdate a
  tip-matching file). Any consumer needing current safety MUST re-run the proof (both
  modes, above); the marker attests only that a passing proof was computed at `at`.
- **SINGLE-USE — CLAIMED at a REBIRTH resume via an atomic content-preserving rename.** ONLY
  a `waiting=="rebirth"` resume claims it — via an atomic `os.replace` to
  `checkpoint-claimed-<claimerSid>-<CID>.marker` (CID = hash of the marker content incl. its
  per-handoff nonce, above) as the FIRST action of the sessionId-rebind bullet, before the
  `state.sessionId` write. A session that LOST the rename to a content-valid claim-target for
  the CURRENT checkpoint (`state.pendingCID`, `proof.tip==tip`) writes NOTHING and exits; a
  stale same-tip leftover of an OLDER CID is ignored; a genuinely-absent/forged rebirth falls
  closed to `stop:checkpoint-unprovable`. A non-rebirth resume never claims (a leftover marker
  is inert). The winner re-sources `markerValid` from the claim-target and removes it on
  completion — single-use; any later checkpoint writes a fresh marker (a new CID).

**Prove-then-pause:** a rebirth pause may be entered ONLY after a passing proof (both
modes, above) plus a fresh `checkpoint-complete.marker`. If, after finishing the
current atomic step and ONE stranded-marker recovery attempt, the proof still fails →
STOP via Present human pause with `waiting = "stop:checkpoint-unprovable"` + the
violations JSON. Never set `waiting = "rebirth"` on a failing proof.

**Stranded-marker recovery (adopt / re-dispatch / STOP — never wait):** an open marker
with no live worker (died before the dispatch ran, or died after the work but before the
clear — indistinguishable on disk, treated the same). This generic recovery handles the
kinds it can re-dispatch by scope
(design/implement/review/harden/finalize/verify/ship) and **EXCLUDES
`inflight-heal-<P>.marker`**, which is owned solely by the resume all-phases heal sweep
(§ Run setup & resume) — recovering a stranded heal here by scope alone would strip its
`harden-regress` flag and `base=` override:
1. **Adopt** only if the unit's COMPLETE artifact set exists and parses — for a review
   unit BOTH the round's `review-<scope>-N.md` (verdict line) AND a non-empty
   `codex-review-<scope>.md` sibling (any non-empty content satisfies; the first-line
   `CODEX_UNAVAILABLE`/`CODEX_KILLED_TIMEOUT` are degradation conventions, not parsed gate
   tokens); for an
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

## Context-pressure detection (Stop hook only)

Context-pressure detection is the **deterministic Stop hook** (`bin/drive-stop-hook.py`)
alone. The coordinator NEVER measures its own transcript to self-signal — eyeballing "this
session feels long" systematically over-triggers (subagent/codex volume lives in OTHER
contexts; the coordinator's own transcript grows far slower than the visible churn suggests).
The hook computes the real number: `tokens >= window * hardHighWaterFraction` over the actual
transcript via `bin/rebirth_thresholds.py` + `bin/rebirth-thresholds.json`, and APPENDS a steer
to its Stop block reason.

When the hook's steer instructs it, the coordinator sets `state.rebirth_pending = true` (a
plain JSON-safe field write — **signal-only:** do NOT checkpoint, hand off, or pause) and
appends one event-log line `{"event":"rebirth_pending","via":"stop-hook","pct":<the pct from
the steer>}`. The § I1 Safe-boundary rebirth handler consumes the flag at the next safe
boundary. **Idempotent:** never re-set an already-`true` flag, never log a duplicate.

Honest-coverage residual: the Stop hook is the SOLE detector — if it is not installed
(`bin/install-operating-rules.sh`), context-pressure rebirth does not trigger; and a single
catastrophic turn can overshoot the window before the hook fires at turn end.

## I1 — Safe-boundary rebirth handler (the checkpoint-and-handoff routine)

The single shared **checkpoint-and-handoff routine** — ONE routine every safe-boundary site
calls (stated here once, referenced from each stage) to checkpoint, distill the outgoing
leg's learnings (`/decant`), and hand off to a fresh session. It has **two trigger classes**,
both routing through the SAME steps 2–6 below — so both set `waiting="rebirth"` only after a
passing proof + a durable marker, and the resume path is identical and never depends on WHICH
trigger fired:

- **(A) Context-pressure** — the Stop hook sets `rebirth_pending` when the transcript crosses
  its token threshold (§ Context-pressure detection). Stage-agnostic: it can arm in ANY stage,
  so EVERY autonomous safe boundary must invoke this handler to consume it.
- **(B) Deterministic seam** — a PLANNED context-clear at a fixed pipeline boundary,
  independent of token pressure: **after Gate A approval** (plan→execute) and **after each
  phase advance** (§ Stage 1; § Stage 2–4.5 step 6). The seam itself is the trigger — no
  `rebirth_pending` flag is involved; it fires every time the boundary is reached.

It runs at each safe boundary below, consuming any `rebirth_pending` the hook's steer has set
AND firing unconditionally at the two deterministic seams:
- **Execute** — after the per-phase detailed design converges (its `inflight-design-<P>.marker`
  cleared, BEFORE freezing base + dispatching slices), after each per-slice review verdict, the
  phase-integration review verdict, each HARDEN round verdict, and the phase advance
  (§ Stage 2–4.5). The phase-design sub-stage runs MULTIPLE dual-voice review rounds, so a rebirth
  signalled there is consumed at this boundary rather than running on into slice dispatch.
  **The phase advance is also a deterministic seam — Seam B (a trigger-class-B handoff) — it
  fires UNCONDITIONALLY (not gated on `rebirth_pending`) so each phase's successor — the next
  phase's design, or Finalize after the last phase — starts in a fresh session.**
- **Finalize** — at the finalize dispatch boundary, BEFORE `/drive-finalize` is dispatched
  (before `inflight-finalize.marker` is written), and after each finalize round verdict
  (CONVERGED / FINDINGS / STOP) once its marker is cleared (§ Stage 4c). Once
  `/drive-finalize` is dispatched its `inflight-finalize.marker` is open, so there is no
  safe boundary INSIDE a finalize round until it returns.
- **Plan** — between plan-stage steps, after each design-review round, and at the **Gate A
  approval transition** (plan→execute), which is the deterministic Seam A (a trigger-class-B
  handoff): the handoff fires UNCONDITIONALLY on approval (not gated on `rebirth_pending`) so
  Execute starts in a fresh session (§ Stage 1).
- **Verify** — after each QA/e2e attempt (§ Stage 4b).
- **Ship** — at the ship dispatch boundary, BEFORE `/drive-ship` is dispatched (before the
  `inflight-ship.marker` is written) (§ Stage 5). Once `/drive-ship` is dispatched its
  `inflight-ship.marker` is open, so there is no safe boundary INSIDE ship until Gate B —
  and Gate B is a human pause where **gate/STOP precedence** applies (the gate wins; a
  rebirth that arises during ship work is deferred and the human resumes in a fresh session),
  so no post-dispatch rebirth is lost.
Each of those sites is a genuine safe boundary (the coordinator is between dispatch units
with no open `inflight-*.marker`). Steps, in this exact order (this handler NEVER sets
`rebirth_pending` — phase-2 detection does):

1. **Gate on the trigger + the boundary.** Proceed ONLY if this is a genuine safe boundary
   (no open `inflight-*.marker`) AND a trigger fired — EITHER `state.rebirth_pending == true`
   (class A) OR this invocation is one of the two deterministic seams (class B: Gate A
   approval, phase advance). Neither trigger at a safe boundary → do nothing, continue the
   pipeline. (A class-B seam fires every time it is reached, independent of `rebirth_pending`;
   if pressure ALSO armed the flag at a seam, this one handoff covers both.)
2. **Finish the current atomic step** (§ Durable checkpoint contract). Let any in-flight
   unit return + record + clear its marker; finish a REDESIGN marker-write → state-write
   span. Do NOT enter the sequence mid-dispatch.
3. **PROVE resumability.** Run BOTH `bin/drive-conformance.sh $RUN_DIR --mode checkpoint`
   AND `bin/drive-conformance.sh $RUN_DIR --mode state-lint` (§ Durable checkpoint contract,
   the proof = both modes, both clean). On a
   FAILING proof — EITHER mode non-clean, incl. a `state-lint` `unparseable-state`/routing
   violation, treated identically to a checkpoint violation — (exit 1) make ONE
   stranded-marker recovery attempt (§ Durable checkpoint
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
   file, content `{"at": …, "sessionId": <outgoing>, "nonce": "<32hex>", "proof": <the mode's
   stdout JSON incl. tip + counters>}`), including the additive per-handoff `"nonce"`
   (`nonce="$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"`, § Durable checkpoint contract).
   Compute `CID` = `shasum -a 256` of the marker content, first 12 hex (shasum absent →
   nonce[:12]) — the per-handoff identity threaded into step 5's `state.pendingCID` and step
   5.7's auto-resume trigger.
5. **THEN set `waiting = "rebirth"`.** Only after the marker is written AND validated
   (re-read it; JSON parses AND `proof.tip` equals the `drive/<runId>` tip) set
   `state.waiting = "rebirth"` AND `state.pendingCID = CID` (the step-4 value) in ONE JSON-safe
   write. The ordering is load-bearing and
   fail-closed: the marker write is step 4 and the `waiting` set is step 5 — marker BEFORE
   `waiting`, adjacent. (Setting `waiting` first would let the turn end before resumability
   is durable.) A real rebirth resume therefore ALWAYS carries `state.pendingCID` set together
   with `waiting="rebirth"` — the resume's claim gate keys on it (§ Run setup & resume).
5.5. **Run `/decant`** (EVERY trigger — pressure or deterministic seam). Now that
   resumability is durable (marker written, `waiting="rebirth"` set), distill the OUTGOING
   leg's learnings before the context clears: invoke the `decant` skill in its default
   autonomous mode (survey this session's memory entries, dedupe, write any genuine new
   memory, surface promotion recommendations in the handoff output). It writes ONLY to memory
   / `OPERATING.md` — outside `$RUN_DIR` and the run's feature branch — so it cannot affect
   the just-proven resumability and cannot bloat the minimal handoff prompt, and it self-skips
   when nothing meaningful was learned. Do NOT let a decant recommendation pause or block the
   handoff (it is advisory; the user acts on it later). A decant failure is non-fatal — note
   it and proceed to step 6 (resumability is already proven; learnings-distillation is
   best-effort). **This step-5.5 decant IS the context-clear decant for this boundary** — it
   satisfies the standing "run `/decant` on context-clear" rule for this handoff, so do NOT
   additionally run a wrap-decant at the same clear. (The standing run-wrap decant fires only
   at the TRUE run-wrap — after Gate B / `stage=done` — which is not a handoff seam.)
5.7. **Schedule the fresh-session auto-resume trigger (capability-detected).** `CID` = the
   step-4 value (also stored in `state.pendingCID` at step 5). **Feature-detect a harness-native
   trigger capability that satisfies ALL of:** (a) spawns a NEW Claude Code session firing
   `/drive <runId>`; (b) can carry a resume PAYLOAD `CID_N` (env/arg) on that session; **(c) is
   HOST-LOCAL — the spawned session runs on THIS host and can reach this run's local `$RUN_DIR`
   (`~/.claude/harness-runs/<runId>/state.json`)** — run state is local/non-portable, and
   drive.md only takes the resume branch when the local `state.json` exists, so a cloud/remote
   trigger (satisfies a+b but not c) would no-op at best or treat `/drive <runId>` as a FRESH
   run on the wrong host. Described by **capability, never a hardcoded tool id** (D2); a
   same-session/in-memory scheduler (`CronCreate`), a cloud routine, or any capability missing
   (a)/(b)/(c) does NOT qualify → **degrade to the fenced block only**.
   - Capability absent / not (a+b+c) → present the fenced block only.
   - Capability present:
     - `$RUN_DIR/auto-resume-scheduled-<CID>.marker` exists → already scheduled for THIS
       checkpoint (a leave-pending re-presentation) → do NOT schedule a second (pure per-CID
       dedup) → present the fenced block.
     - Else → schedule EXACTLY ONE trigger carrying `CID_N = CID`, write
       `$RUN_DIR/auto-resume-scheduled-<CID>.marker` (create-only, tmp+mv), THEN proceed to
       step 6.
   A SUCCESSFUL resume CONSUMES its `auto-resume-scheduled-<CID>.marker` (§ Run setup & resume,
   rebirth-continue bullet). A late/already-resumed trigger no-ops at the § Run setup & resume
   CID gate — NO "scheduled-marker still exists ⇒ prior failed" inference (DROPPED, unsound).
   Repeated-failure-notify + backoff stay DESCOPED to `followups.md` (F1).
   `auto-resume-scheduled-*.marker` is NOT an `inflight-*` marker. Step 6 + the fenced
   `↻ REBIRTH` block stay BYTE-FOR-BYTE.
6. **Present the handoff via Present human pause.** `waiting` is already set (step 5), so
   the routine emits the context-of-execution summary + the run graph (rendering the
   `↻ REBIRTH` node from `waiting=="rebirth"`) and presents the **rebirth handoff block**
   (the literal `/drive <runId>` resume line), then ENDS THE TURN. Do NOT clear `waiting`
   here — the OUTGOING session leaves it set; the INCOMING session's resume clears it
   (§ Run setup & resume).

**Leave-pending semantics:** within the SAME (outgoing) session `rebirth_pending` STAYS SET
through the pause — it is consumed at the next safe boundary (where this handshake fires)
and is NEVER reset inside the outgoing session; it is reset to `false` only on RESUME, by the
SAME logical re-arm whichever resume path runs — the sessionId-rebind step on a fresh-session
resume, or the `rebirth`-continue path on a same-session re-paste (§ Run setup & resume). If the human ignores
the handoff and the outgoing session keeps going, `waiting="rebirth"` +
`checkpoint-complete.marker` persist; the next safe boundary re-observes `rebirth_pending`
still true and re-presents (re-proving — the marker is record-not-authorization). No
double-handoff: the marker is single-use, consumed only by a `/drive <runId>` resume. (A
class-B deterministic seam sets no `rebirth_pending` flag, so it has no leave-pending state —
it fires once on reaching the boundary, and the resume clears `waiting` as for any handoff.)

**Gate/STOP precedence over rebirth.** At a boundary where BOTH `rebirth_pending == true`
AND the next pipeline action is a Gate A / Gate B / a non-decision STOP: the **gate/STOP
wins** — present the gate/STOP (its own `waiting` value), NOT `waiting="rebirth"`.
(Detection is hook-only: the Stop hook does NOT steer a turn that ends in a human pause —
`main()` skips a run with truthy `waiting` — so `rebirth_pending` is `true` at a gate/STOP
boundary only when a PRIOR turn's Stop already armed it. A rebirth that would FIRST arise on
the very turn that ends in the gate/STOP is therefore armed at the next autonomous, non-pause
Stop instead — deferred by at most one turn, never lost.) The
human is present at that pause and can resume in a fresh session: **Gate A** — on approval
the deterministic Seam A fires (§ Stage 1), so Gate A DOES emit the `/drive <runId>` resume
line (NO goal) and hands off (Execute starts fresh) regardless of whether
pressure was also pending; **Gate B** hands NO goal and NO resume token (after Gate-B approval
the push is immediate — there is no next leg). A STOP is not a deterministic-clear seam: after
the human resolves it the run continues, and any pending pressure-rebirth (class A) is
consumed at the next safe boundary. `rebirth_pending` does NOT carry forward ACROSS the fresh-session resume:
it is reset to `false` exactly once at the sessionId-rebind step (the successor re-derives
pressure from its own transcript growth and hands off at the next safe boundary there — no
handoff is lost). WITHIN the same outgoing session it does PERSIST (per Leave-pending
semantics above): if the human ignores the gate/STOP and keeps driving in this session, a
still-pressured run re-observes `rebirth_pending == true` at the next safe boundary and I1
hands off there — the flag is reset only on RESUME (the fresh-session rebind, or the
same-session `rebirth`-continue re-arm), never inside the outgoing session.

## Present human pause (shared routine)

This is the **ONLY** way `/drive` pauses for the human — Gate A, Gate B, every
non-decision STOP, and every `AskUserQuestion`. Go through these steps in this exact
order; emitting the run graph is a mandatory step (step 2) so it can never be
forgotten:

1. **Set `state.waiting` FIRST** to the HUMAN-pause reason this routine is setting —
   `"gateA"`, `"gateB"`, `"stop:<short>"`, or `"ask:<header>"`. This satisfies the
   autonomous-continuation contract above (set `waiting` before pausing) and lets the run
   graph derive `← YOU ARE HERE` from it. **`"rebirth"` is NOT in this set-here list — this
   routine NEVER sets `waiting = "rebirth"` itself.** Only the I1 handler sets `"rebirth"`
   (§ I1 step 5), and ONLY after I1's passing proof + durable `checkpoint-complete.marker`
   (steps 3–4) — `rebirth` is NOT a generic caller-supplied pause reason a sibling path may
   pass in (a `waiting="rebirth"` without I1's prove→marker→wait sequence has no proof of
   resumability and is rejected fail-closed by the resume consumer, § Run setup & resume).
   When this routine is reached for a rebirth handoff `waiting` is ALREADY `"rebirth"` (I1
   pre-set it in its step 5, then calls this routine at step 6); this routine only emits the
   graph + handoff block (steps 2–3), never (re)sets the value. So the full set of `waiting`
   values the run graph may read is `"gateA"`, `"gateB"`, `"stop:<short>"`, `"ask:<header>"`,
   or `"rebirth"` — but only the first four are set HERE; `"rebirth"` arrives pre-set from I1.
   Unlike the human-answer reasons — which await a human ANSWER —
   `"rebirth"` awaits a FRESH-SESSION RESUME: the resume path re-proves then auto-clears it
   and continues (§ Run setup & resume), so it is set-to-pause (by I1) in the outgoing
   session and re-proven-then-cleared on resume, never a STOP.
2. **Emit the run graph** (per § *Emit run graph (shared step)* below) — it reads the
   just-set `state.waiting`. When `waiting == "rebirth"`, FIRST emit the
   context-of-execution summary (per § *Emit context-of-execution summary (shared step)*
   below) IMMEDIATELY ABOVE the run graph, then emit the run graph; all other pauses
   (`gateA`/`gateB`/`stop`/`ask`) emit the run graph alone.
3. **Present** the gate text / STOP reason, or call `AskUserQuestion`; then end the
   turn. Clear `waiting = null` the instant autonomous work resumes. When
   `waiting == "rebirth"`, present the **rebirth handoff block** below (no `AskUserQuestion`
   — the user pastes or ignores) and end the turn WITHOUT clearing `waiting` (the incoming
   session's resume clears it, § Run setup & resume). Substitute `<runId>` = `state.runId`
   literally (the same value the run graph's `↻ REBIRTH` node shows):

   ```
   ↻ REBIRTH — this /drive run has checkpointed and is clearing context to continue in a
   fresh session (planned boundary, or context pressure). Proven resumable — both proof
   modes clean (checkpoint AND state-lint).

   To continue, paste this into a FRESH Claude Code session:

     /drive <runId>

   (This session can stop now; the fresh session owns the run once it resumes.)
   ```

   **Notify side-effect (R3, decision-bearing parks only).** For `waiting` matching the
   ANCHORED `^(gateA|gateB|stop:.+|ask:.+)$` (NEVER `rebirth`), fire a backgrounded best-effort
   notification AFTER `waiting` is set (step 1) and the graph is emitted (step 2): build `MSG`
   per pause kind — **gateB: the gate QUESTION + "reply 'approve' after reviewing the diff"
   (NEVER a `/drive <runId>` paste line)**; gateA / `stop:` / `ask:` per kind — then
   `bin/drive-notify.sh --run-dir "$RUN_DIR" --waiting "$waiting" --tip "$(git rev-parse <featureBranch tip>)" --message "$MSG" >/dev/null 2>&1 &`.
   SIDE-EFFECT ONLY: it does not gate, block, or write `state.json`; a missing/failed
   `drive-notify.sh` is silently ignored. No notify message carries a `/drive <runId>` line.
   `rebirth` is EXCLUDED (it auto-resumes, § I1 step 5.7) — never notify on rebirth.

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
   `slices[<id>].{step,owns,deps}`, `phaseReview[<P>].status`, `finalizeRound`, `verify`,
   `ship`. **The status fields pick glyphs only.** Every round COUNT
   (`designReview`, `slices[<id>].reviewCount`, `phaseDesign[<P>].round`,
   `phaseReview[<P>].{round, hardenRound}`, `finalizeRound`) is artifact-derived (rule below); the matching
   state counter is read ONLY as the labeled DISPLAY fallback in the missing-artifact rule
   — never as a proof of a count.
2. **Fixed-format markdown files** (scope-token naming):
   - `design.md` (Goal → root cause). (`task.md` may also exist, but the Premises line is
     taken from `state.task`, which always has a writer — never an unsourced node.)
   - `review-<scope>-N.md` (`## Verdict: CONVERGED|FINDINGS`; `### [SEVERITY]` where
     BLOCKING/MAJOR = P1) — the Claude reviewer file, **persisted per round** (the `-N`
     suffix) — and its codex sibling `codex-review-<scope>.md` (same tags, or a bare
     first-line degradation token (`CODEX_UNAVAILABLE` | `CODEX_KILLED_TIMEOUT`)).
   - `design-phase<P>.md` (the per-phase detailed design) and its CURRENT-epoch review
     family `review-phasedesign<P>[-r<R>]-N.md` (`## Verdict: CONVERGED|FINDINGS`) +
     `codex-review-phasedesign<P>[-r<R>].md`, `R` = highest `redesign-<P>-r*.marker` in
     `$RUN_DIR` (no marker → the bare `phasedesign<P>` token).
   - `harden-<P>-N.md` (`## Verdict: HARDENED|FINDINGS`) and `codex-harden-<P>.md`.
   - `review-finalize-<N>.md` (`## Verdict: CONVERGED|FINDINGS`; `## AppliedEdits:
     yes|no`) and its codex sibling `codex-review-finalize.md` — the run-singleton
     Finalize node's source, same dual-voice rule as any review scope (CONVERGED only when
     BOTH voices have zero P1; a bare first-line `CODEX_UNAVAILABLE` ⇒ `Codex n/a`,
     `CODEX_KILLED_TIMEOUT` ⇒ `Codex killed (stall/backstop)` — both contribute zero P1).
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
  `Premises · Plan · Execute · Finalize · Verify · Ship` (a not-yet-started stage is omitted).
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
- **Finalize:** the run-singleton aggregate-harden node, rendered between Execute and
  Verify (a not-yet-started Finalize stage is omitted, same "started" rule). Derive it
  from the `review-finalize-*.md` family + `codex-review-finalize.md` (same per-round
  dual-voice verdict derivation as any review scope — non-terminal rounds are FINDINGS by
  construction → Claude count + `Codex —`; the terminal round renders both voices):
  `✓ Finalize: CONVERGED (k fix rounds)` when its terminal `review-finalize-N.md` is
  CONVERGED (k = `finalizeRound` = the `## AppliedEdits: yes` count); `◐ Finalize: round
  N` while in progress; `✗ Finalize: STOP (cap)` on a finalize STOP. `state.finalizeRound`
  is the missing-artifact DISPLAY fallback only (the general missing-artifact rule below).
  A `stop:finalize-*` while `stage==finalize` anchors `← YOU ARE HERE` to a `✗ STOP: <r>`
  leaf under the Finalize node.
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
  slice if the boundary was a per-slice review verdict) when `stage==execute`, the Finalize
  node when `stage==finalize`, else the active Plan/Verify/Ship node. Its node text is
  `↻ REBIRTH: context-clear handoff — planned boundary or pressure (resume: /drive <runId>) ← YOU ARE HERE`, with
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
`review-<scope>-N.md` AND in `codex-review-<scope>.md` (a `CODEX_UNAVAILABLE` OR
`CODEX_KILLED_TIMEOUT` first-line token ⇒ contributes zero P1: `CODEX_UNAVAILABLE` renders
`Codex n/a`, `CODEX_KILLED_TIMEOUT` renders `Codex killed`). **Never key the glyph off the
Claude file's `## Verdict:` alone.**

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
`harden-<P>-*.md`, `review-finalize-*.md`, and their codex siblings
(`codex-review-<scope>*.md`, `codex-harden-<P>*.md`, `codex-review-finalize.md`) — show
the matching state counter (`finalizeRound` for the finalize family) as a DISPLAY HINT (its sole
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

## Emit context-of-execution summary (shared step)

A short **prose** "context of execution" summary that complements — never duplicates — the
run graph: it orients a zero-context successor session (and the watching user) in words,
where the run graph orients them with a chart. It is emitted ONLY at the two fresh-session
boundaries (the outgoing rebirth handoff — Present human pause step 2 when
`waiting=="rebirth"` — and the incoming fresh-session resume — § Run setup & resume), NOT at
ordinary gate/STOP/ask pauses.

### Data sources (the ONLY sources — mirrors the run graph's discipline)

The summary reads the **SAME FULL durable surface** the run graph reads (§ *Emit run graph
(shared step)* § *Data sources*), never a narrower subset:

1. **`state.json` in full** — the identical field set the run graph reads: `task`, `stage`,
   `lastGate`, `waiting`, `phase`, `phaseList`, `designReview`, `phaseDesign[<P>].status`,
   `slices[<id>].{step,owns,deps}`, `phaseReview[<P>].status`, `finalizeRound`, `verify`,
   `ship`. Status fields describe position; every count is artifact-derived, never proof.
2. **`design.md`** — its `## Goal` (→ the *problem* part; the SAME first-sentence derivation
   the run graph's `root cause:` line uses).
3. **The fixed-format review/harden/finalize artifacts** — `review-<scope>-N.md`
   (`## Verdict:`), `design-phase<P>.md` + `review-phasedesign<P>[-r<R>]-N.md`,
   `harden-<P>-N.md` (`## Verdict:`), `review-finalize-<N>.md` (`## Verdict:` +
   `## AppliedEdits:`) and their codex siblings — the "what has converged / hardened" source.
4. **`decisions.md`** — the run-local decision ledger (→ the *decided* part: the `## D…`
   titles).

**NEVER parse `event-log.jsonl`** — event/field names drift across runs (the identical rule
`## Emit run graph` states). No new `state.json` field, no invented data. This section
**inherits the run graph's `### Missing-artifact rule (general — never fabricate)`
verbatim**: any absent/unknown value renders `pending` / `?`, never fabricated — the two
stay single-sourced on that one rule.

### Prose shape — 4 short labeled parts

Each part maps to concrete fields and degrades to `pending` when its source is absent:

- **Problem** — what this run is solving: first sentence of `design.md` `## Goal`; else
  `state.task`; else `pending`.
- **Where we are** — the run's current position, in words: `state.stage` + `state.waiting` +
  `state.phase`/`phaseList`; per-stage detail from the current phase's
  `phaseDesign[<P>].status` / `slices[<id>].step` / `phaseReview[<P>].status`, or
  `finalizeRound` / `verify.attempts` / `ship` past Execute — the SAME node the run graph
  anchors `← YOU ARE HERE` on, rendered as a sentence.
- **Done / decided** — what has completed + what was decided: the converged/hardened
  artifacts (phases with `phaseReview[<P>].status=="hardened"`; CONVERGED `review-*-N.md`;
  the converged design) + the `## D…` titles from `decisions.md`.
- **Next** — the immediate next pipeline action: derived from `state.stage` + the reconciled
  position + `state.waiting` (e.g. "resume Phase 2 detailed design", "dispatch slice 1.3
  fix", "present Gate B").

### Render note (kept OUT of any fenced block)

The summary is **prose** (~4–8 lines, one per part), NOT an ASCII chart — it does not need
the run graph's collapse ladder. It is emitted **outside** the fenced run-graph code block
AND outside the fenced `/drive <runId>` handoff paste block (so it never bloats the minimal
paste). At the **outgoing handoff** it is placed **ABOVE** the run-graph chart
(narrative-first orientation).

## Pipeline

### Stage 0 — Premises
1. **Premises:** if the task is ambiguous about WHAT problem to solve, pause and ask.

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

This Gate-A transition is a **single atomic `state.json` write**: `stage = "execute"`,
`lastGate = "A"`, `waiting = null`, and the parsed `phaseList` are committed TOGETHER (never
`stage=execute` first and `phaseList` in a later write). This closes the crash-intermediate
`{stage:execute, phaseList:[]}` so the resume guard's later-stage fail-closed STOP is a
genuine-malformed backstop, not a false-STOP of an interrupted handoff — and it matches what
the Seam-A `--mode state-lint` gate already requires (it rejects an empty `phaseList` once
`stage ≠ premises/plan`).

**Seam A — deterministic handoff after Gate A approval.** Once approved (`lastGate="A"`,
`stage="execute"`, `phaseList` parsed) the plan is fully recorded and no `inflight-*.marker`
is open — a genuine safe boundary. Invoke the **checkpoint-and-handoff routine** (§ I1 steps
2–6) UNCONDITIONALLY (class-B deterministic seam, NOT gated on `rebirth_pending`): it proves
resumability, runs `/decant`, sets `waiting="rebirth"`, presents the handoff (`/drive
<runId>` resume line, NO goal), and ends the turn — so **Execute begins in the fresh
session** the user resumes into. (A failing proof fails closed → STOP per § I1 step 3, do NOT
hand off.) `/drive-plan` presents Gate A — direction + any Taste/Challenge items — and this
Seam A handoff is the single source of the `/drive <runId>` resume line (Execute begins
fresh); no goal is emitted.

At each Plan safe boundary — between plan-stage steps and after each design-review round
(the coordinator is between dispatch units with no open `inflight-*.marker`) — run the
**Safe-boundary rebirth handler** (§ I1) so a
rebirth signalled during planning is consumed and handed off (Gate A precedence still holds —
§ I1 Gate/STOP precedence).

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
it before it advances). At each safe boundary in this loop — after the per-phase detailed
design converges (step 1), after a per-slice review verdict (step 4), the phase-integration
review verdict (step 5), a HARDEN round verdict and the phase advance (step 6) — run the
**Safe-boundary rebirth handler** (§ I1 above —
it consumes any `rebirth_pending` the hook's steer set), before proceeding:

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
   `git worktree remove --force $RUN_DIR/wt/design<P>`. This is a safe boundary (the design's
   `inflight-design-<P>.marker` is cleared, no open `inflight-*.marker`): run the
   **Safe-boundary rebirth handler** (§ I1 above — it consumes any
   `rebirth_pending` the hook's steer set during the multi-round design review) BEFORE freezing base / dispatching
   slices.
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
   find→fix→verify pass over the assembled phase to **add missing tests, fix logic
   bugs** — beyond acceptance criteria (de-slop is DEFERRED to the aggregate
   `/drive-finalize` stage) — committing to
   `phaseInt/<runId>/<P>`. Its own 3-fix-round cap (independent of the conformance cap-8);
   a fix that would drop a criterion's coverage is vetoed; after any code
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
     `stage = finalize`). **Seam B — deterministic handoff after the phase advance.** With
     the advance complete (its atomic ref move recorded) and no `inflight-*.marker` open —
     a genuine safe boundary — invoke the **checkpoint-and-handoff routine** (§ I1 steps 2–6)
     UNCONDITIONALLY (class-B deterministic seam, NOT gated on `rebirth_pending`): it proves
     resumability, runs `/decant`, sets `waiting="rebirth"`, presents the handoff (`/drive
     <runId>` resume line, NO goal), and ends the turn — so the successor (the next
     phase's `/drive-design` step 1, or Finalize / Stage 4c after the last phase) **begins in
     the fresh session** the user resumes into. (A failing proof fails closed → STOP per § I1
     step 3, do NOT hand off; the advance is already durable, so resume picks up at the next
     phase / finalize.)
   - `STOP` (3 fix rounds exceeded / BLOCKED / NEEDS_CONTEXT) → STOP; the phase stays
     `hardening` and does **not** advance — its half-hardened state is preserved on
     `phaseInt/<runId>/<P>` for resume.

When all phases reach `status = hardened` → `stage = finalize`.

### Stage 4c — Finalize (aggregate harden; once, before Verify)

Runs ONCE per run, AFTER every phase reached `status = hardened` (Stage 2–4.5 step 6),
and BEFORE Verify (Stage 4b). It is the end-of-run aggregate quality pass over the
WHOLE-RUN diff (`baseRef..featureBranch`) — `/drive-finalize`
(`~/.claude/commands/drive-finalize.md`) LEADS with de-slop (the lens per-phase harden
defers here) plus an aggregate logic-bug + missing-test sweep, and emits the **terminal
SHA-bound review artifact the ship gate consumes** (`review-finalize-N.md` with
`reviewed-sha == featureBranch tip`).

At the finalize dispatch boundary — BEFORE `inflight-finalize.marker` is written, so the
coordinator is between dispatch units with no open `inflight-*.marker` — run the
**Safe-boundary rebirth handler** (§ I1) so
a rebirth signalled before finalize is consumed and handed off. Once `/drive-finalize` is
dispatched its `inflight-finalize.marker` is open → there is no safe boundary INSIDE a
finalize round until it returns; after each finalize round verdict (CONVERGED / FINDINGS /
STOP) is recorded the marker is cleared, which is again a safe boundary → run the
**Safe-boundary rebirth handler** (§ I1) there too.

1. **Worktree precondition.** Finalize runs in `$RUN_DIR/wt/finalize` checked out at
   `featureBranch`. The last phase already advanced (step 6), so `featureBranch` is
   checked out in NO worktree and is free; create it:
   `git worktree add $RUN_DIR/wt/finalize <featureBranch>` (literal `featureBranch` =
   `drive/<runId>` with `<runId>` substituted). This is the ONLY worktree where
   `featureBranch` is live during finalize — correct, because finalize is terminal (no
   further `branch -f` advance needs `featureBranch` free).
2. **Init the state field:** `state.finalizeRound = 0` if absent (JSON-safe write).
3. **Dispatch:** write `inflight-finalize.marker` (write-before-dispatch, tmp + `mv`;
   content
   `{"kind":"finalize","scope":"finalize","runId":"<runId>","sessionId":"<this session or null>","startedAt":"<iso>"}`),
   then invoke `/drive-finalize` (`~/.claude/commands/drive-finalize.md`) with cwd =
   `$RUN_DIR/wt/finalize`, passing `<runId>`, `$RUN_DIR`, `baseRef`, `featureBranch`.
   Increment `budget.calls`. Append a dispatch line to `$RUN_DIR/event-log.jsonl`.
4. **Return handling (the loop /drive owns):**
   - `CONVERGED` → record `state.finalizeRound`, append a verdict line to
     `event-log.jsonl`, clear `inflight-finalize.marker` (clear-after-record: artifact
     written + state updated + event-log line), `git worktree remove
     $RUN_DIR/wt/finalize` → `stage = verify`.
   - `FINDINGS` → record `state.finalizeRound`, append a verdict line, clear
     `inflight-finalize.marker`, then **re-invoke `/drive-finalize`** on the SAME
     `$RUN_DIR/wt/finalize` worktree (the stage owns its own `FINALIZE_CAP = 3`
     fix-round cap; /drive just re-dispatches until CONVERGED or STOP). Re-write
     `inflight-finalize.marker` around each re-dispatch.
   - `STOP — <reason>` → STOP via **Present human pause** (`waiting =
     "stop:finalize-<short>"`); the run stays in `stage = finalize`,
     `$RUN_DIR/wt/finalize` is preserved for resume, and the run does NOT advance to
     Verify/Ship. (Omission-/non-convergence-proof at ship: with no CONVERGED finalize
     artifact binding the tip, the `--mode ship` gate's finalize candidate-R is absent →
     ship blocks.)

### Stage 4b — Verify (optional)
If the change touches a UI/URL (auto-detect), run gstack `qa-only` / `browse` on the
`featureBranch` tree (marker `inflight-verify.marker`); write `$RUN_DIR/verify.md`.
Report-only. Honor "no qa".
Append each e2e/QA attempt's outcome to `state.verify.attempts`
(`{result:"PASS"|"FAIL"}`) — the ordered array is the run graph's Verify source and its
false-negative → re-verify saga.
After each QA/e2e attempt — a Verify safe boundary (between dispatch units, no open
`inflight-*.marker`) — run the **Safe-boundary rebirth handler** (§ I1) so a rebirth
signalled during Verify is consumed and handed off.
→ `stage = ship`

### Stage 5 — Ship (once)
At the ship dispatch boundary — before the `inflight-ship.marker` is written, so the
coordinator is between dispatch units with no open `inflight-*.marker` — run the
**Safe-boundary rebirth handler** (§ I1) so a
rebirth signalled before ship is consumed and handed off (Gate B precedence still holds —
§ I1 Gate/STOP precedence).

Run the SHIP stage (`/drive-ship` — `~/.claude/commands/drive-ship.md`) on `featureBranch`
(marker `inflight-ship.marker`): promote
`$RUN_DIR/decisions.md`+`followups.md` into the repo ledgers (and
`$RUN_DIR/finalize-todo.md` → repo-root `TODO.md` when present) — the 4-file
`SHIP_LEDGER_ALLOWLIST` {`.harness/decisions.md`, `.harness/followups.md`, `TODO.md`, `.harness/codex-refutations.md`},
run the full suite
(red → retry once → STOP), build the **single** commit + PR, **Gate B** (approve
diff), then push/open PR. → `lastGate = "B"`, `stage = done` → then run the `## Completion`
wrap sequence (the ship path's terminal-done site).

## Completion

This is the run's terminal wrap — the wrap sequence (retro then the wrap-decant) plus the
Report. It is gated on the terminal-done signal (a **parseable** `$RUN_DIR/completedAt` OR
`state.stage == "done"`) — the same authority `is_done()` and retro's own completeness gate use
(a completedAt that merely EXISTS but is unparseable does NOT authorize done) — so it only
ever fires once the run is effectively done; re-invoking it is idempotent-safe (retro
overwrites its single `retro-<runId>.md`, and the wrap-decant self-skips when nothing new was
learned). Both terminal-done sites reach this same wrap sequence:
- the resume `Done-via-resume teardown` (§ Run setup & resume) invokes it BETWEEN writing
  `completedAt` and writing `stage="done"` — the hook-protected window where, with
  `stage != "done"` and `waiting` empty, the stop-hook keeps the coordinator working across
  turns, closing the turn-end/rebirth drop window (a hard crash is not hook-prevented, but
  `stage` stays not-`done`, so a resume retries);
- Stage 5's ship (§ Stage 5 — Ship) reaches it after `drive-ship.md` returns — post-`stage=done`
  but in the same coordinator turn immediately after Gate B (no context-clear seam there). This
  is a tolerated best-effort characteristic: a rare interruption in that narrow post-done window
  drops the wrap for that run, recovered only by a manual re-run, not automatically.

**Wrap sequence (ordered; best-effort / non-fatal, mirroring the wrap-decant's existing
non-fatal contract — neither step may block the wrap, the Report, or each other):**
1. `/drive-retro <runId>` — mine this run's durable `$RUN_DIR` traces into classified lesson
   proposals at `retro-<runId>.md`, putting that file on disk as input evidence for decant's
   survey. If retro fails or writes nothing, note it and CONTINUE.
2. the standing wrap-`/decant` — distill this run's session learnings (it reads
   `retro-<runId>.md` as ordinary session evidence when present — no new interface). If decant
   fails, note it and CONTINUE.

The retro-before-decant ORDER is load-bearing (retro's file feeds decant) but not gating: a
retro failure never blocks decant. This is the TRUE run-wrap decant only — distinct from the
per-seam I1 step-5.5 rebirth decant (UNCHANGED, retro-free: a mid-run seam fails retro's
completeness gate).

Report: design path, per-phase verdicts, PR link; a one-line summary of every decision promoted
this run; `followups.md` entries; the event-log path; anything uncertain. Note any
worktrees/branches left for inspection.
