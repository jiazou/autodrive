---
description: HARDEN stage (Stage 4.5) of /drive — per-phase quality-hardening pass that runs AFTER the phase-integration review converges. Find→fix→verify over the assembled phase to (1) add missing tests, (2) fix logic bugs; notes AI slop and DEFERS it to the final aggregate stage (`/drive-finalize`). Mutating, beyond acceptance criteria. Usually invoked by /drive.
argument-hint: phase <P> (within an existing run)
---
You are running the HARDEN stage (Stage 4.5) for **one phase**. Harness-owned — no
gstack skill. Unlike `/drive-review` (a PASSIVE conformance audit scoped to
acceptance criteria), HARDEN is a **mutating find→fix→verify loop** that hunts
quality defects **beyond** the spec — (1) add missing tests, (2) fix logic bugs;
it **notes (does not fix) AI slop, deferring it to the end-of-run `/drive-finalize`
aggregate pass**. `/drive` invokes it once per phase, AFTER the
phase-integration review CONVERGED and BEFORE `featureBranch` advances, operating on
the assembled `phaseInt/<runId>/<P>` worktree (so its commits land on that branch — the same
branch `featureBranch` will fast-forward to).

`/drive` passes: `phase <P>`, `<runId>` (the run identifier), the absolute
**`phaseInt/<runId>/<P>` worktree path** (the implementer subagent's cwd),
`phaseBaseSha`, and `$RUN_DIR` (absolute). The phase's spec (acceptance criteria, slices)
lives in `$RUN_DIR/design-phase<P>.md`; `$RUN_DIR/design.md` is the high-level context.

The scope is the **assembled phase diff** `git diff <phaseBaseSha>..phaseInt/<runId>/<P>` and
the files it touches — the "relevant codebase" for this phase. Derive it
authoritatively from git, never an ephemeral implementer list.

## Preconditions (non-decision STOPs)

This is a sub-stage of `/drive`, not a standalone tool — it hardens an assembled phase
*in flight*, so it needs that run's context. On invocation, bind and verify, in order;
**STOP with the stated message** (do not guess, fabricate a run, or harden an arbitrary
tree) if any fails:
- `<P>` = the phase number from `$ARGUMENTS` (the `phase <P>` argument). Missing/unparseable
  → STOP: "no phase given — usage: `/drive-harden phase <P>` within an active `/drive` run."
- `$RUN_DIR` is provided (by `/drive`) or inferable from a single in-progress run under
  `~/.claude/harness-runs/`. None, or only runs with `state.stage == "done"`/`"ship"` →
  STOP: "no active /drive run to harden — `/drive-harden` runs inside an in-flight run, after a phase review converges. Start one with `/drive <task>`."
- That run's `state.json` shows phase `<P>` `phaseReview[<P>].status == "converged"` (or
  `"hardening"` on resume). Not converged / not yet assembled → STOP: "phase <P> hasn't
  passed its integration review yet — harden runs only after `/drive-review phase <P>` converges."
- The `phaseInt/<runId>/<P>` worktree exists (`git worktree list`) and `$RUN_DIR/design-phase<P>.md`
  is present. Missing → STOP naming what's absent (the run is mid-rebuild or corrupt; let
  `/drive` reconcile on resume).

When `/drive` invokes this stage it passes all of the above directly, so these checks
pass by construction; they exist for a bare/manual invocation.

## The two hardening lenses (+ a deferred slop NOTE)

- **NOTE AI slop → DEFER to `/drive-finalize`** (not a fix lens here): Per-phase harden
  no longer REMOVES slop. When the audit spots slop (speculative fallbacks, needless
  try/catch, defensive "just in case" code, dead code, over-abstraction, redundant
  comments, copy-paste, inconsistent naming), it is RECORDED under the canonical heading
  `## slop (deferred to finalize)` — never fixed — and Step 2's always-runs persist
  transcribes it to `$RUN_DIR/followups.md`, from which `/drive-finalize` applies de-slop
  ONCE at end-of-run over the whole-run diff (doing it per-phase would do it twice). See
  Step 2 for the authoritative persist rule (the guaranteed transcribe source + the
  always-runs guarantee).
1. **Add missing tests**: acceptance criteria, branches, edge cases, and error paths
   with no test → add them. A test that guards a bug MUST **fail against the pre-fix
   code** (per OPERATING.md "a green test can pass for the wrong reason" — drive the
   real production wiring, not seeded/stubbed state).
2. **Fix logic issues & bugs**: off-by-one, wrong conditionals, unhandled
   null/empty, races, incorrect error handling, contract violations the conformance
   review missed.

## Loop counter & cap

`N` = this invocation's index = (count of existing `$RUN_DIR/harden-<P>-*.md`) + 1;
each invocation writes exactly one `harden-<P>-N.md`.

`hardenRound` counts **fix rounds only** — invocations that actually changed code. The
cap is **HARDEN_CAP = 3** fix rounds. A round that audits clean and applies nothing
(the confirming audit) is **free** — it does NOT increment `hardenRound`, so N fix
rounds don't need an N+1th to confirm clean. Harden therefore allows up to 3
code-changing rounds plus the final clean audit that declares HARDENED. If
`hardenRound >= HARDEN_CAP` AND this invocation's audit still has open P1 → STOP and
summarize what is open per lens (a flagged half-hardened phase beats a silent advance).

This counter is **independent of the conformance `phaseReview[<P>].round` (cap-8)**:
the Step-4 regression guard runs `/drive-review phase <P> harden-regress`, which by
contract does not touch `round` — so a phase whose integration already used 6–8
conformance rounds is not false-STOPped when harden re-reviews it.

Reconcile `hardenRound` from artifacts, not state alone (a crash can write
`harden-<P>-N.md` or land a `phaseInt/<runId>/<P>` commit before the state write): on entry,
`hardenRound = max(state.phaseReview[<P>].hardenRound or 0, count of `harden-<P>-*.md`
with `AppliedEdits: yes`)`. The `AppliedEdits` line in each audit file (see Step 1
schema) is the machine-readable marker of a fix round; clean confirming audits carry
`AppliedEdits: no` and don't count.

## Scope-creep HARD GATE (not a guideline)

Bind every edit to the 6 Decision Principles' blast-radius + boil-lakes test as a
**gate**, not advice. The gate's purpose is to stop "fix logic bugs" from mutating
into "rewrite the codebase" — NOT to block correctness work the phase genuinely needs.
Allowed to edit:
- The files in `git diff <phaseBaseSha>..phaseInt/<runId>/<P>` (the phase's own surface).
- New **test files** + existing **test-support** (fixtures, harnesses, snapshots)
  needed to cover those files — lens 1 legitimately adds and wires up tests.
- A file **just outside** the diff ONLY when it is the true root cause of a **flagged
  P1** in the phase and deferring would knowingly ship a broken phase. This widens
  scope, so **log it to `$RUN_DIR/decisions.md`** (Classification) and surface at
  Gate B. Never reach forward into another *unbuilt* phase's planned files.
Forbidden: any **refactor / taste edit without a flagged P1**, and editing unrelated
working code. A non-P1 improvement outside the diff → `$RUN_DIR/followups.md`, skip it.

## Step 1 — Audit (dual-voice, 2-lens + slop-note)

Run the **same dual-voice mechanics as `/drive-review`** (codex FIRST as a background helper + a
passive Claude reviewer spawned WHILE it runs), **including its outcome tier TABLE** (`/drive-review`
Step 1 — the `OK` / `CODEX_KILLED_TIMEOUT` / `CODEX_UNAVAILABLE` / `HELPER_ERROR` tier), but with the
**harden 2-lens prompt** below instead of the conformance prompt. CRITICAL BOUNDARY: pass PATHS +
git refs only — never any implementer's or harden-fixer's notes/rationale (preserves
the reviewer's independent judgment, exactly as conformance review does).

Codex FIRST (run `bin/drive-codex.sh` from the MAIN context via `Bash(run_in_background:true)`,
NEVER inside a subagent that waits on it). First `mkdir -p "$RUN_DIR/tmp"` (TMPDIR-namespaced). The
dispatch block (snapshot → quarantine → dispatch):

```
case "$scope" in *[!A-Za-z0-9._-]*) echo "non-decision STOP: invalid <scope> charset"; exit 2 ;; esac   # belt-and-suspenders: HELPER's permissive charset BEFORE composing any <scope>-derived filename
mkdir -p "$RUN_DIR/tmp"
[ -f "$RUN_DIR/codex-harden-<P>.log" ] && mv "$RUN_DIR/codex-harden-<P>.log" "$RUN_DIR/codex-harden-<P>.log.stranded"   # re-dispatch: mv the raw log aside (an orphaned codex may still be appending)
[ -f "$RUN_DIR/codex-harden-<P>.md" ] && cp "$RUN_DIR/codex-harden-<P>.md" "$RUN_DIR/tmp/codex-prior-<scope>.md"   # SNAPSHOT the prior sibling for --prior-codex BEFORE the quarantine hides it. Ordering: snapshot → quarantine → dispatch
[ -f "$RUN_DIR/codex-harden-<P>.md" ] && mv "$RUN_DIR/codex-harden-<P>.md" "$RUN_DIR/codex-harden-<P>.md.stranded"   # QUARANTINE the STALE codex SIBLING so a crashed round leaves NO current sibling for stranded-adopt
for x in out err; do [ -f "$RUN_DIR/tmp/helper-<scope>.$x" ] && mv "$RUN_DIR/tmp/helper-<scope>.$x" "$RUN_DIR/tmp/helper-<scope>.$x.stranded"; done   # stale token/err file aside
cat > "$RUN_DIR/tmp/codex-prompt-<scope>.txt" <<'PROMPT'
Harden phase <P>: review git diff <phaseBaseSha>..phaseInt/<runId>/<P> for (1)
missing tests to add (acceptance criteria, branches, edge/error paths), (2) logic
bugs. Flag P1 (real bug / missing test on a criterion) vs P2 (non-criterion test gap)
with file:line. Also LIST (do not propose removing) any AI slop you see (file:line) —
it is deferred to a later aggregate pass. Prioritized.
PROMPT
REDISPATCH=0; [ -e "$RUN_DIR/inflight-review-<scope>.marker" ] && REDISPATCH=1   # re-dispatch = a PRE-EXISTING OPEN inflight marker (a prior crashed attempt of THIS round)
if [ "$REDISPATCH" = 0 ]; then
  CONF=(--confirmation-class --prior-codex "$RUN_DIR/tmp/codex-prior-<scope>.md")   # CLEAN FIRST dispatch (incl. a confirming re-audit): --prior-codex = the step-0 SNAPSHOT of codex-harden-<P>.md
else
  CONF=()                                                                            # RE-DISPATCH ⇒ NO --confirmation-class ⇒ FULL effort
fi
TMPDIR="$RUN_DIR/tmp" bin/drive-codex.sh --mode dispatch \
  --scope <scope> --scope-class phase [--security-diff] \
  --raw-log "$RUN_DIR/codex-harden-<P>.log" --marker "$RUN_DIR/codex-harden-<P>.md" \
  --attempt-log "$RUN_DIR/codex-attempts-<runId>.jsonl" \
  --prompt-file "$RUN_DIR/tmp/codex-prompt-<scope>.txt" \
  "${CONF[@]}" \
  > "$RUN_DIR/tmp/helper-<scope>.out" 2> "$RUN_DIR/tmp/helper-<scope>.err"   # token on STDOUT only; stderr SEPARATE
```

(`<scope>` = `phase<P>`; a phase scope is gate-enforced regardless, `--security-diff` iff the phase
diff is sensitive. The `--prior-codex` snapshot source is **`codex-harden-<P>.md`** — harden's OWN
prior sibling, NOT `codex-review-<scope>.md`. Coordinator prompt enrichment may reference PRIOR
rounds only — never the same-round Claude reviewer output.)

Spawn a generic reviewer subagent WHILE the codex helper runs:

----- BEGIN SUBAGENT SCOPE -----
Audit `git diff <phaseBaseSha>..phaseInt/<runId>/<P>` and the files it touches, against the
TWO hardening lenses (NOT just acceptance-criterion conformance) + a slop NOTE:
- AI slop (NOTE, not a lens) — RECORD each instance (file:line + one-liner) but propose
   NO edit; these are DEFERRED to `/drive-finalize`. List them under a
   `## slop (deferred to finalize)` section (file:line — one-line description), not as
   fixable findings — Step 2 (Triage) transcribes this section into
   `$RUN_DIR/followups.md`. (Slop kinds: speculative fallbacks, needless try/catch,
   defensive "just in case" code, dead code, over-abstraction, redundant comments,
   copy-paste, inconsistent naming.)
1. Missing tests (lens 1) — acceptance criteria / branches / edge cases / error paths
   with no test. Name the exact case to cover.
2. Logic & bugs (lens 2) — off-by-one, wrong conditionals, unhandled null/empty, races,
   bad error handling, contract violations.
Spec + prior decisions: `$RUN_DIR/design-phase<P>.md` (the phase's acceptance criteria +
slices; `$RUN_DIR/design.md` is high-level context), `$RUN_DIR/decisions.md`.

Severity — pick one, don't ask:
- P1 (actionable this stage): a real bug (lens 2), or a missing test on an acceptance
  criterion / on a bug being fixed (lens 1).
- P2: a missing test on a non-criterion path — fix only if cheap AND in the phase's
  blast radius; otherwise → followups. (Slop is NOT a P-finding here — it is recorded
  to followups as a finalize-deferred note, never fixed.)
- P3: cosmetic; → followups, never fix.
Out-of-phase / out-of-diff real bugs → `$RUN_DIR/followups.md`.

Write `$RUN_DIR/harden-<P>-N.md`:
  # Harden phase <P> N
  ## Verdict: HARDENED | FINDINGS
  ## AppliedEdits: pending          (Step 4 finalizes this to yes|no — the resume marker)
  ## Findings → ### [SEVERITY][LENS] Short title / **Where** file:line / Issue / Fix
  ## slop (deferred to finalize)    (REQUIRED — one line per slop item as `file:line — one-line description`; empty section if none)
You MUST write the `## slop (deferred to finalize)` section listing EVERY slop instance you
spotted (one line each, `file:line — one-line description`); this section is the GUARANTEED
transcribe source Step 2 reads — anything not listed here is not reliably carried to finalize.
HARDENED = no open P1 AND nothing cheap-P2 left to apply. Return: path, verdict, one-line count.
----- END SUBAGENT SCOPE -----

Wait for BOTH the helper's completion notification (the outcome token = the LAST line of
`$RUN_DIR/tmp/helper-<scope>.out`; stderr is in `.err`, never merged) AND the reviewer's return,
then Combine — post-process the codex raw log ONLY on `OK`, branching via drive-review.md's outcome
tier TABLE + coordinator state-machine. `OK` + non-empty raw log → run a bounded post-process
subagent: "Read `$RUN_DIR/codex-harden-<P>.log`, extract codex's final findings, write
`$RUN_DIR/codex-harden-<P>.md` (same severity/lens tags, <150 words)." The post-process WRITES
ATOMICALLY — to `$RUN_DIR/tmp/codex-harden-<P>.md.tmp.$$` then `mv` into the `--marker` path — so a
mid-write crash leaves NO torn/partial marker (the complete file, or none); THEN require a non-empty
`codex-harden-<P>.md` at that path (crashed subagent / unwritable ⇒ **fail-closed non-decision
STOP**). `HELPER_ERROR` (exit 2) OR shell rc 126/127 ⇒ **broken-helper NON-DECISION STOP** (fix
`bin/drive-codex.sh` / `chmod +x` / reinstall, then resume — NO codex launched, NO marker written,
NO `codex exec` fallback).

Degradation (do NOT hard-fail): the helper writes `codex-harden-<P>.md` with the first-line token
`CODEX_UNAVAILABLE` (codex missing / probed outage) or `CODEX_KILLED_TIMEOUT` (watchdog
stall/backstop kill) — exactly that bare token as the file's FIRST line, the same form
drive-review.md emits, so the run-graph's codex-n/a detection is uniform across review and harden;
optionally an explanatory note on later lines; continue.

## Step 2 — Triage

**Persist deferred slop FIRST (always-runs — this is the authoritative write).** Before
deciding HARDENED-vs-fix, transcribe slop into `$RUN_DIR/followups.md` under the canonical
heading `## slop (deferred to finalize)`, one line per item as `file:line — one-line
description` (create the heading once if absent; never duplicate it; dedup — skip any item
whose `file:line — description` line is already present). The GUARANTEED transcribe source
is the Claude audit's `## slop (deferred to finalize)` section in
`$RUN_DIR/harden-<P>-N.md` (Step-1 schema requires it) — EVERY item it lists MUST be
written. Then fold in any codex slop from `$RUN_DIR/codex-harden-<P>.md` BEST-EFFORT (the
codex summary is capped/best-effort and may not carry a structured slop list, so it is an
opportunistic add, not the guaranteed source). This runs on EVERY round regardless of the
fix set — **even when the fix set is empty / the round returns HARDENED** (Step 3, the fix
step, is skipped on a slop-only or final clean round) — so every slop item the Claude audit
lists reliably lands in `$RUN_DIR/followups.md` for `/drive-finalize`, with no orphaning.

Then combine voices: both-flagged = high confidence; **codex-only = scrutinize hardest**
(bugs Claude missed); reviewer-only = claude-only. Build the fix set from:
- All open **P1** from this round's audit (lens 2 bugs + lens 1 criterion/bug tests).
- **Any P1 conformance regression** the prior round's Step-4 re-review left open
  (recorded in `$RUN_DIR/review-phase<P>-*.md` / state) — fold it in so a harden edit
  that dropped a criterion gets repaired, not lost.
- **P2** non-criterion tests — only if cheap AND in the phase blast radius
  (6 principles); else → `$RUN_DIR/followups.md`.
- **P3** → `$RUN_DIR/followups.md`; recorded slop notes were ALREADY persisted to
  followups by the always-runs step above (deferred to finalize) — never applied here.

If the fix set is empty (no open P1 from the audit, no outstanding regression, nothing
cheap-P2 left) → **HARDENED** (this is the free confirming round — return per Step 4,
do not increment `hardenRound`). Otherwise classify each kept item Mechanical / Taste /
User-Challenge (6 principles); Taste → log to `$RUN_DIR/decisions.md`, surface at
Gate B; User-Challenge → STOP and surface.

## Step 3 — Fix (implementer subagent, cwd = phaseInt worktree)

Spawn a generic implementer subagent with **cwd = the `phaseInt/<runId>/<P>` worktree**. Pass
file PATHS + the harden + codex finding paths, never contents.

----- BEGIN SUBAGENT SCOPE -----
You are hardening phase <P>. Your cwd is its assembled integration worktree on branch
`phaseInt/<runId>/<P>`. Code paths are relative to this worktree; artifact paths are the
absolute `$RUN_DIR` (never edit code via absolute paths to the main repo). Read:
- $RUN_DIR/design-phase<P>.md (acceptance criteria for the phase's slices)
- $RUN_DIR/decisions.md (stay consistent)
- $RUN_DIR/harden-<P>-N.md + codex-harden-<P>.md (the fix set; codex-only items live
  only in the codex file, so read it)

Apply ONLY the fix set, honoring the scope-creep HARD GATE (see above): the phase-diff
files; new test files + existing test-support (fixtures/harnesses/snapshots) for them;
and a file just outside the diff ONLY as the root cause of a flagged P1 (then append a
scope-widening note to `$RUN_DIR/decisions.md`). No refactor / taste edit without a
flagged P1 — a non-P1 improvement outside the diff → `$RUN_DIR/followups.md`, skip it.
- Lens 2 bugs: fix them; add a test that FAILS against the pre-fix code, then passes.
- Lens 1 tests: add the named tests, driving real production wiring (not stubbed state).
- Slop: do NOT remove any slop in this pass — it is DEFERRED to `/drive-finalize`. The
  audit's slop items are persisted to `$RUN_DIR/followups.md` (under
  `## slop (deferred to finalize)`) by the always-runs Step-2 persist rule — that is the
  SINGLE authoritative slop-persist path; do NOT write followups here. If you notice NEW
  slop while fixing, do not edit the slop and do not append it yourself — list it in your
  "Flagged:" return line so the next round's audit surfaces it and Step-2's always-runs
  persist (with its dedup rule) records it. Never write a second slop-persist path from
  this step.
Run the FULL suite — **`bin/run-tests.sh`** (the canonical runner: `python3 -m pytest
tests/` AND every `test/*.test.sh`, all suites, no early-exit) — plus any build step,
until green; do NOT hand-pick a subset. Commit to `phaseInt/<runId>/<P>`
(`git add -A && git commit`) before returning.

Return STATUS as the FIRST line, then the changed-file list:
- `STATUS: DONE` — fix set applied, tests green, committed. List changed files (within
  the allowed scope above). "Flagged:" line for deviations / Taste / any
  scope-widening root-cause edit (also logged to `$RUN_DIR/decisions.md`).
- `STATUS: BLOCKED — <reason>` — non-decision blocker (env/tool/test failure you
  can't resolve). State it + what would unblock.
- `STATUS: NEEDS_CONTEXT — <question>` — a User-Challenge, or a needed fix is out of
  the allowed scope (another phase's files / can't be deferred). State the one question.
----- END SUBAGENT SCOPE -----

## Step 4 — Regression guard & converge

One round per invocation; `/drive` owns the loop. Decide the return per the cap rules
in **Loop counter & cap**, then finalize the round's `AppliedEdits` marker:

- **No fix applied this invocation** (Step-2 fix set was empty — the free confirming
  audit) → set `harden-<P>-N.md` `AppliedEdits: no` → return `HARDENED`.
- **A fix was applied** → `hardenRound += 1`; set `AppliedEdits: yes`. Re-run
  `/drive-review phase <P> harden-regress` as the regression guard (catches a
  conformance break the tests can't — e.g. a bug-fix that silently changed an
  asserted-elsewhere behavior).
  Any P1 it finds is folded into the next round's fix set. Return `FINDINGS` (the next
  invocation re-audits; a subsequent clean audit returns HARDENED).
- **`hardenRound >= HARDEN_CAP` and this audit still has open P1** → return `STOP`.

Record `phaseReview[<P>].hardenRound` to `$RUN_DIR/state.json` each invocation.
`/drive` sets `phaseReview[<P>].status = hardened` on the `HARDENED` return.

## Return contract to /drive

- `HARDENED` — audit clean + conformance still converged. `/drive` advances
  `featureBranch` to `phaseInt/<runId>/<P>`, removes the worktree, deletes slice branches,
  proceeds to the next phase.
- `FINDINGS` — still looping (a fix round ran; not yet clean). `/drive` re-invokes
  HARDEN for this phase (the loop owns its cap of 3 fix rounds).
- `STOP — <reason>` — cap exceeded, BLOCKED, or NEEDS_CONTEXT. Surface; the phase does
  NOT advance until resolved.

Budget: increment `state.budget.calls` per harden subagent/codex dispatch; if a
ceiling is set and exceeded → STOP with a spend summary (the half-hardened phase is
left on `phaseInt/<runId>/<P>` for inspection — see /drive resume).

Never include the harden-implementer's notes/rationale in any audit or review prompt.
