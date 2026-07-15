---
description: REVIEW stage (Stage 3) of /drive — dual-voice review (Claude reviewer subagent + codex) over a design/slice/phase scope; converged when neither voice has an open P1. Usually invoked by /drive.
argument-hint: design | slice <id> | phase <P> [harden-regress] [base=<sha>]
---
You are running the REVIEW stage (Stage 3) — the harness's **dual-voice review
primitive** (a passive Claude reviewer + a direct codex pass over the same scope,
combined). NOT gstack `/review` (fix-first, mutates). `/drive`
(or `/drive-plan`) invokes it with a **scope** and passes `$RUN_DIR` + the scope's git
refs:

- `design` — review the **high-level** `$RUN_DIR/design.md` itself, before Gate A: a
  sound goal/approach and a sound ordered `## Phases` breakdown (no phase dependency
  cycle; phase boundaries that can deliver the goal). **Right-sized decomposition (both
  directions):** over-split is a P1 — a phase beyond the first whose `relies on:` cites no
  `fan-out`/`staged-risk` justification, a tests/docs-only phase, or a phase that is mere
  sequential dependency in one subsystem with no foundation needing its own verify. Under-split
  is a P2 — a single phase that bundles a foundation (a unit whose correctness must verify
  before dependents are safe) with its dependents. **Size band:** a design whose `Size estimate`
  is over-band (~150–500 / ≳500 production SLOC — comments + tests excluded) must either split
  on a real fan-out/staged-risk seam OR carry an explicit atomicity justification plus a
  `heightened-review:` note; an over-band design that did neither is a P1. A missing `Size
  estimate` section is itself a P1. High-level altitude — it does NOT demand slice/interface
  detail (that is each phase's own design). No code diff.
- `phase <P> design` — review the per-phase detailed design `$RUN_DIR/design-phase<P>.md`
  itself (invoked by `/drive-design`, before that phase implements): buildable interfaces,
  testable acceptance criteria, a sound slice breakdown (no slice dependency cycle; parallel
  slices own disjoint files; no slice contract that contradicts the real prior-phase code).
  **Right-sized + shared-contract:** flag any slice beyond the first lacking a `why:`
  (`fan-out`/`staged-risk`), any test-only slice, and — P1 — any two slices that share a
  contract new-in-this-phase and co-authored by both (a helper emitted/mirrored in both, a
  writer/reader pair, a value produced by one and consumed by another) instead of being one
  slice. P2: a single slice that bundles a must-verify-first foundation with its dependents.
  No code diff.
- `slice <id>` — review the slice's diff `git diff <phaseBaseSha>..slice/<runId>/<id>`
  against that slice's acceptance criteria (owned files only).
- `phase <P>` — review the assembled integration diff
  `git diff <diffBase>..phaseInt/<runId>/<P>` for integration issues (interfaces,
  cross-slice contracts). **Size reconciliation** (the estimate is self-reported — verify it
  against the real diff): measure the assembled phase's actual production SLOC (exclude tests,
  comments, blanks); if it crosses into a HIGHER band than the plan's `Size estimate` claimed
  (claimed ≲150 but actual > 150, or claimed ~150–500 but actual > 500) with no
  `heightened-review:` note, flag P2 — re-examine the decomposition on the true size.
- `phase <P> harden-regress` — same review as `phase <P>`, but invoked by
  `/drive-harden` as its regression guard. Identical scope/diff/mechanics, differing in
  TWO file-family-preserving ways: (a) it does NOT increment the conformance
  `phaseReview[<P>].round` counter (its bounding is owned by the harden loop, not the
  conformance cap), and (b) it emits the `harden-regress: yes` self-identifying control
  line into its `review-phase<P>-N.md` (the header-preamble marker the checkpoint reader
  classifies harden-regress vs integration reviews on — Step 2 below).

**Optional diff-base override (`base=<40-hex>`, strip-before-scope).** BEFORE deriving
`<scope>` from the invocation args, scan them for a single token matching
`^base=([0-9a-fA-F]{40})$`; if present, set `<diffBase>` = the captured 40-hex and REMOVE
that token from the arg list. `<scope>` and the `harden-regress` flag are then derived
from the REMAINING tokens EXACTLY as below — `base=` never participates in
scope/filename/log derivation (`phase <P> harden-regress base=<sha>` → `<scope>` =
`phase<P>`, harden-regress flag ON, `<diffBase>` = `<sha>`). If no `base=` token is
present, `<diffBase>` = the global `<phaseBaseSha>` (the unchanged default). This override
substitutes for `<phaseBaseSha>` ONLY in the phase-integration diff (the `phase <P>` diff
refs above/below); the slice-scope diffs are unaffected. ONLY the resume-sweep heal
supplies `base=`; normal build-time `phase <P>` / `phase <P> harden-regress` invocations
pass nothing and diff byte-identically to today.

Let `<scope>` be `design`, `<id>` (e.g. `1.2`), `phase<P>`, or the phasedesign token (the
per-phase design review of `design-phase<P>.md`). **Resolve the phasedesign token's
redesign epoch YOURSELF** by the single epoch-resolution rule (drive.md § Durable
checkpoint contract, In-flight dispatch markers) — invokers pass `phase <P> design`
unchanged: set `R` = the highest epoch among `$RUN_DIR/redesign-<P>-r*.marker` (0 if
none); `R == 0` → the bare `phasedesign<P>`, `R >= 1` → `phasedesign<P>-r<R>`. Use the
resolved token everywhere `<scope>` appears — the review file, the codex sibling, the
`codex-raw-<scope>.log`, and the file-count counter fallback. The coordinator writes the
in-flight marker, not this stage.

**Loop counter:** `N = (this scope's counter) + 1` — `state.designReview` for
`design`, `state.slices[<id>].reviewCount` for a slice, the `phaseReview[<P>]`
round for a `phase <P>` review, `state.phaseDesign[<P>].round` for a `phase <P> design`
review (fall back, if state is absent, to counting only the pure-integer-N round files
`$RUN_DIR/review-<scope>-<N>.md` where `<N>` is all digits — EXCLUDE any suffixed name
such as `review-<scope>-r<R>.md` or `review-<scope>-final.md` — and add 1, consistent
with how `bin/drive-conformance.sh` reconstructs the round count).
If N > 8, STOP — not converging; summarize each side.
**Exception — `harden-regress`:** do NOT read, increment, or cap against the
conformance `phaseReview[<P>].round`. The harden loop already bounds the number of
these passes (its 3-fix-round cap), so there is no N>8 STOP here; just run the review
and report CONVERGED/FINDINGS.

## Round form on eligible re-reviews (delta-focused prompt)

On an ELIGIBLE round (below), the CODEX voice's prompt leads with the prior round's fix
delta instead of the full-scope-first framing. Everything else about the round is
byte-identical to any other round: ONE codex dispatch per round via the unchanged Step-1
block, the same gate-visible `--marker` path `codex-review-<scope>.md`, the same
snapshot → quarantine → dispatch ordering, Step-3 post-process, degradation tiers, and
Adopt/recovery mechanics. This form changes PROMPT CONTENT ONLY — no artifact, marker,
counter, or gate text changes anywhere, and it names NO new filename of any kind.

**Eligibility (ALL must hold; anything else ⇒ the normal full prompt):**
- The scope is a CODE scope — `slice <id>` or `phase <P>` — at round N≥2, immediately
  following a FIX of this scope's prior-round findings. `design`/`phasedesign<P>` scopes
  are ineligible by construction (doc reviews, no code diff — the fresh design-scope
  re-read is a sole-catcher); a `phase <P> harden-regress` invocation is ineligible;
  `finalize` is not a drive-review scope.
- NOT a stranded-marker recovery re-dispatch — i.e. this `/drive-review` unit was
  re-dispatched by drive.md's Stranded-marker recovery (step 2) at resume, which the
  coordinator knows from its own context (equivalently: the marker the recovery found
  open AT RESUME — before this re-dispatch minted its own — carried a PRIOR session's
  `sessionId`; recovery step 2 clears it, so the test binds at the recovery ADJUDICATION
  point). The round's OWN `inflight-review-<scope>.marker`, written by this session
  immediately before this dispatch unit, does NOT make the round a recovery re-dispatch
  — else every round would classify as recovery and this form would be inert.
- The scope's diff (`git diff --name-only <diffBase|phaseBaseSha>..<tip>`, the scope's
  refs above) touches NO security-sensitive path: **any** file under `bin/`, any
  gate-hook/installer script, any settings/hook config, or any matcher/parser/classifier
  implementation ⇒ the WHOLE round is INELIGIBLE — full-scope codex every round, however
  small the sensitive fraction of the diff (diff-content-based, independent of the
  `--security-diff` effort flag).
- `deltaBase` resolves: `deltaBase` = the `reviewed-sha:` of `review-<scope>-(N-1).md`.
  A missing file, or a missing/non-40-hex sha ⇒ NOT eligible — fail closed to the
  normal full prompt.

**The delta-focused codex prompt (eligible rounds only).** The coordinator appends a
delta block to `$RUN_DIR/tmp/codex-prompt-<scope>.txt` AFTER writing the base heredoc
(`cat >>`); the Step-1 dispatch block itself stays byte-identical. The appended block
binds to ALL of the prior round's P1s, never a singular "the prior finding":
- (a) it LEADS with the delta focus: "review FIRST the fix delta
  `git diff <deltaBase>..<tip>` (`git log <deltaBase>..<tip>` for the fix commits), and
  FOR EACH prior-round P1: its fix's changed surface and consumer surface
  (callers/readers of the changed symbols), PLUS — where that P1's fix commit DECLARED a
  class boundary (the R5 contract: parser/validator/regex/classifier/reader/wording-class
  fixes declare one; other fixes legitimately do not) — that P1's full class."
- (b) a CONDITIONAL class-closure checklist item, included only when ≥1 prior-round fix
  declared a boundary: "for each declared class boundary, verify it is closed (re-run
  that boundary grep)." A P1 whose fix declared no class gets the delta +
  consumer-surface treatment and NO boundary grep.
- (c) the suite-rerun ban: "do NOT re-run the full test suites — spot-run only the tests
  pinning your prior findings" (the suites already ran green in the implement step). The
  ban applies ONLY on eligible rounds — ineligible/security rounds keep today's prompt,
  with no ban.
- (d) the full-scope license VERBATIM: "you MAY flag any P1 anywhere in scope" — where
  'scope' = the FULL reviewed diff of the scope (`<diffBase|phaseBaseSha>..<tip>`), never
  the delta focus's slice of it (the narrow reading would revive the refuted
  settled-scope prohibition).
Enrichment is unchanged: the prompt names `review-<scope>-(N-1).md` and the step-0
snapshot `tmp/codex-prior-<scope>.md` (PRIOR-round only), which is always current because
every completed round writes the gate-visible sibling exactly as today.

**The Claude voice runs FULL-scope every round** — the Step-2 reviewer prompt is the
normal full prompt (plus the R5 class-boundary checklist item), and it writes the round's
`review-<scope>-N.md` exactly as today. **Terminal invariant:** the terminal full-scope
pass is the CLAUDE voice's — full-scope every round, including the round that records
CONVERGED. The codex voice follows today's tier-table semantics UNCHANGED (a degraded
pass contributes zero P1); a delta-focused CLEAN codex pass on a CONVERGED round is
strictly MORE codex coverage than the already-gate-accepted degraded-round CONVERGED
(zero codex).

**Accounting (unchanged consumers):** ONE dispatch, one `review-<scope>-N.md`, one
counter tick per round, counted INSIDE cap-8 — never excluded, reset, or bypassed. Every
post-fix round remains a FRESH dual-voice dispatch: the delta form narrows the codex
PROMPT's focus, not the round's freshness, and the Claude voice re-reads the full scope
every round. A crash mid-round is today's seam exactly (an open marker with a complete
pair adopts; an incomplete pair re-dispatches) — and the recovery re-dispatch is
ineligible by the rule above, so a redo round runs the normal full prompt (the delta
focus is dropped on redo, never the artifact discipline).

## Step 1 — Cross-model codex pass FIRST (background helper, per-scope log)

**R2 (codex-first, overlap-reliable).** Dispatch codex FIRST as a background helper, then spawn
the Claude reviewer (Step 2) WHILE it runs, wait for BOTH, and Combine — post-processing the codex
raw log ONLY on `OK` (Step 3). Run the supervisor `bin/drive-codex.sh` from the MAIN context via
`Bash(run_in_background:true)` — NEVER inside a subagent that waits on it — then await its
completion notification. The helper watchdogs codex (stall/backstop kill) and prints ONE closed
outcome token (the LAST line of its stdout): `OK | CODEX_KILLED_TIMEOUT | CODEX_UNAVAILABLE |
HELPER_ERROR`. Use a **per-scope** log so parallel slice reviews don't collide.

The single authoritative **outcome → marker → post-process → verdict → rendering** tier TABLE
(`/drive-harden` and `/drive-finalize` REFERENCE this one, including its outcome tier TABLE):

| helper outcome | marker 1st line | post-process | combined-verdict | run-graph render |
|---|---|---|---|---|
| `OK` | none (real review) | YES | counts codex P1 normally | normal |
| `CODEX_KILLED_TIMEOUT` | `CODEX_KILLED_TIMEOUT` | NO | contributes **zero P1** | `Codex killed (stall)` / `Codex killed (backstop)` — never `(partial)` |
| `CODEX_UNAVAILABLE` | `CODEX_UNAVAILABLE` | NO | contributes **zero P1** | `Codex n/a` |
| `HELPER_ERROR` | none | N/A → **coordinator STOP (broken helper)** | (run halts) | **no codex tier rendered** |

First, ONCE per run, `mkdir -p "$RUN_DIR/tmp"`; the helper is TMPDIR-namespaced so codex's scratch
lands in the run dir, not the shared `/tmp`. The dispatch block (snapshot → quarantine → dispatch):

```
# 0. belt-and-suspenders: assert <scope> matches the HELPER's OWN PERMISSIVE charset BEFORE
#    composing any <scope>-derived temp/log filename — accepts design / phasedesign1 / phase1 /
#    slice 1.2; rejects path-traversal/injection chars. NOT the bare phase/slice-id grammar.
case "$scope" in *[!A-Za-z0-9._-]*) echo "non-decision STOP: invalid <scope> charset"; exit 2 ;; esac
# 1. codex FIRST (background), TMPDIR-namespaced.
mkdir -p "$RUN_DIR/tmp"
[ -f "$RUN_DIR/codex-raw-<scope>.log" ] && mv "$RUN_DIR/codex-raw-<scope>.log" "$RUN_DIR/codex-raw-<scope>.log.stranded"   # re-dispatch: mv the raw log aside BEFORE the dispatch (an orphaned codex may still be appending; matches harden/finalize ordering)
[ -f "$RUN_DIR/codex-review-<scope>.md" ] && cp "$RUN_DIR/codex-review-<scope>.md" "$RUN_DIR/tmp/codex-prior-<scope>.md"   # SNAPSHOT the prior sibling for --prior-codex BEFORE the quarantine mv hides it (else effort-tiering is dead). Ordering: snapshot → quarantine → dispatch
[ -f "$RUN_DIR/codex-review-<scope>.md" ] && mv "$RUN_DIR/codex-review-<scope>.md" "$RUN_DIR/codex-review-<scope>.md.stranded"   # QUARANTINE the STALE codex SIBLING so a crashed round leaves NO current sibling for stranded-adopt
for x in out err; do [ -f "$RUN_DIR/tmp/helper-<scope>.$x" ] && mv "$RUN_DIR/tmp/helper-<scope>.$x" "$RUN_DIR/tmp/helper-<scope>.$x.stranded"; done   # stale token/err file aside
# write the byte-identical review prompt to the prompt file (delivered via --prompt-file):
cat > "$RUN_DIR/tmp/codex-prompt-<scope>.txt" <<'PROMPT'
Review <scope>. For 'design': audit $RUN_DIR/design.md — high-level only
(sound goal/approach + ordered ## Phases, no phase cycle; FLAG over-split P1 — a phase beyond
the first with no fan-out/staged-risk justification, a test/docs-only phase, or mere sequential
dependency with no foundation needing its own verify; and under-split P2 — one phase bundling a
must-verify-first foundation with its dependents; and FLAG P1 an over-band Size estimate
(~150-500/>=500 production SLOC, comments+tests excluded) that neither split on a real seam nor
carries an atomicity justification + heightened-review note, or an absent Size estimate). For 'phasedesign<P>': audit
$RUN_DIR/design-phase<P>.md (buildable interfaces, testable criteria, sound Slices — no slice
cycle, disjoint owns, no contract contradicting real prior-phase code; FLAG a slice beyond the
first with no why:, a test-only slice, two slices sharing a new co-authored contract instead of
being one, or a slice bundling a must-verify-first foundation with its dependents).
For BOTH 'design' and 'phasedesign<P>': where the design ships a classifier/matcher rule, RUN
its calibration script against its corpus (precision) AND run your own independent recall probe
(shape enumeration the author didn't prescribe — the author's script inherits the rule's blind
spots); verify the claims transcript verify-design-claims-*.md exists, then: a claims-bearing
transcript => spot-check >=1 claim against it; a transcript declaring 'no citations / no quoted
snippets / no empirical claims' => VERIFY THAT DECLARATION against the design doc itself (any
citation, quoted snippet, or empirical claim found falsifies it — P1 against the transcript).
For 'phasedesign<P>' also flag P2 when the ACs lack the 'Pin depth per AC' assignments.
For a slice:
git diff <phaseBaseSha>..slice/<runId>/<id>, only its acceptance criteria + owned files. For
a phase: git diff <diffBase>..phaseInt/<runId>/<P>, integration; AND reconcile size — actual
production SLOC (excl tests/comments/blanks) crossing into a higher band than the plan's Size
estimate claimed with no heightened-review note is P2. Flag BLOCKING/MAJOR/
MINOR with file:line. Prioritized.
For any finding that is one instance of a class (parser/validator/regex/classifier/reader/
wording), enumerate ALL members of the class with file:line.
PROMPT
# --confirmation-class is a CONDITIONAL BRANCH, not an always-present flag: down-tier eligible ONLY
# on a clean FIRST dispatch of THIS round; OMIT on a RE-DISPATCH ⇒ FULL effort (the step-0 snapshot
# may be the CRASHED current attempt, not the prior COMPLETED round). "re-dispatch" ≔ a PRE-EXISTING
# OPEN inflight-review-<scope>.marker (a prior crashed attempt of THIS round's leg). Do NOT key off
# prior-round review-<scope>-N.md — a confirmation re-audit HAS those yet its FIRST dispatch IS
# down-tier-eligible. (Coordinator prompt enrichment may reference PRIOR rounds only — never the
# same-round Claude reviewer output.)
REDISPATCH=0; [ -e "$RUN_DIR/inflight-review-<scope>.marker" ] && REDISPATCH=1
if [ "$REDISPATCH" = 0 ]; then
  CONF=(--confirmation-class --prior-codex "$RUN_DIR/tmp/codex-prior-<scope>.md")   # CLEAN FIRST dispatch: down-tier eligible; --prior-codex = the step-0 SNAPSHOT (never the quarantined live sibling)
else
  CONF=()                                                                            # RE-DISPATCH (open inflight marker) ⇒ NO --confirmation-class ⇒ FULL effort
fi
TMPDIR="$RUN_DIR/tmp" bin/drive-codex.sh --mode dispatch \
  --scope <scope> --scope-class <design|slice|phase> [--security-diff] \
  --raw-log "$RUN_DIR/codex-raw-<scope>.log" --marker "$RUN_DIR/codex-review-<scope>.md" \
  --attempt-log "$RUN_DIR/codex-attempts-<runId>.jsonl" \
  --prompt-file "$RUN_DIR/tmp/codex-prompt-<scope>.txt" \
  "${CONF[@]}" \
  > "$RUN_DIR/tmp/helper-<scope>.out" 2> "$RUN_DIR/tmp/helper-<scope>.err"   # token on STDOUT only; stderr SEPARATE
```

**`--scope-class` per scope:** `design` / `phasedesign<P>` → `design`; a slice → `slice`; a `phase
<P>` (incl. the harden-regress guard) → `phase`. Pass `--security-diff` iff the scope's own diff
touches the security path set (a sensitive slice; a phase diff is gate-enforced regardless). The
`--confirmation-class`/`--prior-codex` flags (via `CONF`) ride ONLY a clean FIRST dispatch of a
confirmation round; on a `phase <P>` re-audit after a clean prior, the snapshot source is
`codex-review-phase<P>.md`.

## Step 2 — Claude reviewer (passive, separation-preserving) — spawned WHILE codex runs

WHILE the codex helper (Step 1) runs, spawn the passive Claude reviewer. CRITICAL BOUNDARY: do NOT
include any implementer notes/rationale in the reviewer's prompt. Pass PATHS + git refs only.
Spawn a generic reviewer subagent:

----- BEGIN SUBAGENT SCOPE -----
Audit the <scope>:
- `design`: audit the HIGH-LEVEL `$RUN_DIR/design.md` ITSELF — a sound goal/approach and
  a sound ordered `## Phases` breakdown (no phase dependency cycle; phase boundaries that
  can deliver the goal). Right-sized decomposition (both directions): P1 over-split = a phase
  beyond the first with no `fan-out`/`staged-risk` justification, a test/docs-only phase, or
  mere sequential dependency in one subsystem with no foundation needing its own verify; P2
  under-split = one phase bundling a must-verify-first foundation with its dependents. Size band:
  an over-band `Size estimate` (~150–500 / ≳500 production SLOC, comments+tests excluded) that
  neither split on a real seam nor carries an atomicity justification + `heightened-review:` note
  is P1; an absent `Size estimate` section is P1. High-level altitude — do NOT demand
  slice/interface detail. No code diff.
- `phasedesign<P>`: audit the per-phase detailed design `$RUN_DIR/design-phase<P>.md` ITSELF
  — interfaces buildable, acceptance criteria testable, the `Slices` breakdown sound (no
  slice dependency cycle; parallel slices own disjoint files; no slice contract that
  contradicts the real prior-phase code). Right-sized + shared-contract: a slice beyond the
  first with no `why:`, a test-only slice, or — P1 — two slices sharing a contract
  new-in-this-phase + co-authored (helper mirrored in both, writer/reader pair,
  produced-then-consumed value) rather than being one slice; P2 = one slice bundling a
  must-verify-first foundation with its dependents. No code diff.
- `design` / `phasedesign<P>` (BOTH, additionally): where the design ships a
  classifier/matcher rule, RUN its calibration script against its corpus (precision) AND
  run your own independent recall probe (shape enumeration the author didn't prescribe) —
  the author's script inherits the rule's blind spots. Also verify the claims transcript
  `verify-design-claims-*.md` exists, then CONDITIONALLY: a claims-bearing transcript ⇒
  spot-check ≥1 claim against it; a transcript declaring 'no citations / no quoted
  snippets / no empirical claims' ⇒ VERIFY THAT DECLARATION against the design doc itself
  (scan it for citations, quoted snippets, and empirical claims — any found falsifies the
  declaration and is a P1 against the transcript) instead of spot-checking. For
  `phasedesign<P>`: flag P2 a phase design whose ACs lack the `Pin depth per AC`
  assignments.
- a slice: audit `git diff <phaseBaseSha>..slice/<runId>/<id>` against THAT slice's
  acceptance criteria, restricted to its owned files.
- a phase: audit `git diff <diffBase>..phaseInt/<runId>/<P>` for integration correctness.
  Size reconciliation: measure actual production SLOC (exclude tests/comments/blanks); if it
  crosses into a higher band than the plan's `Size estimate` claimed with no `heightened-review:`
  note, flag P2.
- Round-N≥2 checklist (slice/phase scopes): when any prior-round fix declared a class
  boundary (the fix commit's stated grep pattern + file:line member list), VERIFY each
  stated class is closed — re-run its boundary grep — IN ADDITION TO, never instead of,
  your unchanged open-ended adversarial hunt.
Spec + prior decisions: the phase's detailed design `$RUN_DIR/design-phase<P>.md` (for a
slice/phase scope — the slice acceptance criteria live there; `$RUN_DIR/design.md` is the
high-level context), and `$RUN_DIR/decisions.md`. Derive the diff authoritatively from git
(the refs above) — never an ephemeral implementer list.

Severity (P-levels) — pick one, don't ask:
- BLOCKING (P1): prod incident risk, data loss, security hole, spec violation that
  breaks an acceptance criterion
- MAJOR (P1): clear bug, missing edge case the design listed, test gap on a criterion
- MINOR (P2): code quality / readability / perf with no spec impact
- NIT (P3): style; usually omit
For test-pin findings, "a pin exists" is defined by MUTATION SURVIVAL, not textual
presence: a pin counts only if it reds on deletion/partial-revert of the exact clause it
guards; a vacuous pin = NO pin = stays P1. "Could be stronger" (reds on the core mutation
but lacks permutation/exclusivity/composed-order coverage) = P2, logged for
harden/finalize — EXCEPT on fail-closed gate surfaces (drive-conformance contracts, gate
hooks, drive-retention safety clauses), where exclusivity/composed-order gaps STAY P1.
Out-of-scope real bugs → `$RUN_DIR/followups.md`.

Write `$RUN_DIR/review-<scope>-N.md`:
  # Review <scope> N
  ## Verdict: CONVERGED | FINDINGS
  reviewed-sha: <40-hex>
  harden-regress: yes      ← ONLY for a `phase <P> harden-regress` invocation (see below)
  ## Findings → ### [SEVERITY] Short title / **Where** file:line / Issue / Why / Fix
CONVERGED = no P1. Return: the path, verdict, one-line count.

**harden-regress self-identifying marker (harden-regress invocation ONLY).** When this
review is a `phase <P> harden-regress` invocation, emit a control line
`harden-regress: yes` at column 0 in the HEADER PREAMBLE — immediately after
`reviewed-sha:` and strictly BEFORE `## Findings`. A plain `phase <P>` integration review
MUST NOT write it. The checkpoint reader classifies harden-regress vs integration reviews
on this marker and is **header-region bound** (it scans only the lines before the first
`## Findings`), so the marker MUST stay above `## Findings` — a marker written below it is
silently ignored (the review would misclassify as integration). Write the whole file in
one `Write` call so the marker is atomic with `reviewed-sha:` and `## Verdict:` (no torn
"unmarked FINDINGS" state). Do NOT lead an ordinary findings line with the
`harden-regress:` token; the header-region bound already prevents a body-quoted
`harden-regress: yes` (e.g. inside a fenced code block) from misclassifying the file, so
this note is only belt-and-suspenders.

**`reviewed-sha:` (SHA-bound proof — the enforcement gate reads this).** Emit a line
`reviewed-sha: <40-hex>` = the **exact git tip this review diffed**, so a review only
counts for code whose tip equals it (a stale CONVERGED file can't cover newly-added
commits). Bind it by scope:
- **slice `<id>`:** `<40-hex>` = `git rev-parse slice/<runId>/<id>` (the slice tip the
  diff `<phaseBaseSha>..slice/<runId>/<id>` ended at).
- **phase `<P>`:** `<40-hex>` = `git rev-parse phaseInt/<runId>/<P>` (the assembled
  integration tip). The **harden-regress** re-review (run by HARDEN after it commits
  to `phaseInt/<runId>/<P>`) MUST re-emit `reviewed-sha:` at the **post-fix**
  `git rev-parse phaseInt/<runId>/<P>` tip — otherwise the phase-merge gate sees a
  stale pre-harden sha and blocks the advance.
- **design / phasedesign:** OMIT `reviewed-sha:` — these audit a design DOC
  (`design.md` / `design-phase<P>.md`), not a git tip. (`design` feeds the plan-gate,
  which requires only `## Verdict: CONVERGED` + the codex file; `phasedesign<P>` is
  consumed by `/drive-design` and the verdict-only `phasedesign-gate:<P>` (which
  reads the current-epoch `review-phasedesign<P>[-r<R>]-N.md` + codex pair — verdict +
  codex presence, no git tip to bind).)
----- END SUBAGENT SCOPE -----

## Step 3 — Combine & converge (post-process ONLY on `OK`)

Wait for BOTH: the helper's completion notification — the outcome token = the LAST line of
`$RUN_DIR/tmp/helper-<scope>.out` (stderr is in `.err`, never merged into the token) — AND the
reviewer subagent's return. Then branch via the AUTHORITATIVE coordinator outcome state-machine
(drive.md § Combined dual-voice round verdict) over (token, rc, marker presence), first-match:
- **`OK` (rc 0) + non-empty raw log** → run the bounded post-process subagent: "Read
  `$RUN_DIR/codex-raw-<scope>.log`, extract codex's final findings, write
  `$RUN_DIR/codex-review-<scope>.md` (same severity tags, <150 words)." The post-process WRITES
  ATOMICALLY — to `$RUN_DIR/tmp/codex-review-<scope>.md.tmp.$$` then `mv` into the `--marker` path
  `codex-review-<scope>.md`, so a mid-write crash leaves NO torn/partial marker (the complete new
  file, or none). THEN require a non-empty file at the passed `--marker` path (`codex_present`'s
  `-s` genuinely suffices now the write is atomic): NO marker after post-process (crashed subagent /
  unwritable) ⇒ **fail-closed non-decision STOP** (the codex voice was lost — never proceed).
- **A degraded token (`CODEX_KILLED_TIMEOUT` / `CODEX_UNAVAILABLE`) WITH a present marker** → render
  the degraded tier (the helper owns the marker); do NOT post-process.
- **A degraded token with an ABSENT/empty marker** (marker-write failed), OR an empty/unrecognized
  token with shell rc ∉ {126,127}, OR `OK`-with-empty-log ⇒ **fail-closed non-decision STOP**.
- **`HELPER_ERROR` (exit 2) OR shell rc 126/127** ⇒ **broken-helper NON-DECISION STOP**: fix
  `bin/drive-codex.sh` / `chmod +x` / reinstall, then resume — NO codex was launched, NO codex
  marker written, and there is NO `codex exec` fallback. Append an attempt-log op `helper_error`
  line, then surface the STOP.

Degradation (do NOT hard-fail): the helper writes a non-empty `codex-review-<scope>.md` whose FIRST
line is the conventional degradation marker `CODEX_UNAVAILABLE` (codex missing / probed outage) or
`CODEX_KILLED_TIMEOUT` (watchdog stall/backstop kill), optionally a warning note on later lines;
continue single-voice. The conformance codex check is satisfied by ANY non-empty
`codex-review-<scope>.md` (real review OR degradation note); it does NOT parse the marker — the
first-line `CODEX_UNAVAILABLE` / `CODEX_KILLED_TIMEOUT` are the human-readable convention, not gate
tokens.

Compare: both-flagged = high confidence; **codex-only = scrutinize hardest** (bugs Claude missed);
reviewer-only = claude-only. **Count tags, not prose:** the codex verdict is derived by COUNTING
the BLOCKING/MAJOR severity tags in `codex-review-<scope>.md`, never its prose summary line; on a
tag-vs-prose conflict, fail closed to the tags. Demoting a codex BLOCKING/MAJOR on pin depth
requires SHOWING the executed core-mutation red (an executed artifact in the round's record, not
an assertion). **Converged** when NEITHER voice has an open **P1** (BLOCKING/MAJOR); a
degraded token contributes zero P1; P2/P3 logged, not blocking. Record to `$RUN_DIR/state.json`:
this scope's verdict + increment its counter — `state.designReview` for `design`,
`state.slices[<id>].reviewCount` for a slice, `state.phaseReview[<P>].round` for a `phase <P>`
review, `state.phaseDesign[<P>].round` for a `phase <P> design` review.
**Exception — `harden-regress`:** increment nothing (the harden loop's 3-fix-round cap bounds it).

## Refutation ledger (R7)

When the coordinator OVERRULES a codex P1 with evidence (overrule-with-evidence), it
records the adjudication so a later re-flag replays the evidence instead of relitigating.

**Artifacts:**
- `$RUN_DIR/codex-refuted-<scope>.md` — the per-scope in-run family (one file per scope,
  appended per entry): the run's read surface for re-flag replay and review-scope
  enrichment. Per entry: the finding (verbatim substance), refutation evidence, `Repro:`
  (an executable check, or run-local doc-anchored cites-as-replay), `Env:` (a bounded
  non-secret manifest), a scope qualifier, and a voiding condition.
- `$RUN_DIR/codex-refutations-pending.md` — the promotion staging file: when an
  adjudication is DURABLE-qualifying (recurring-class evidence + hermetic repo-relative
  repro + non-secret manifest), the coordinator ALSO appends the entry here in the
  committed format. Ship promotes exactly this file; it is not created when nothing
  qualifies. Entry ids in this file are PROVISIONAL — ship's promotion RE-DERIVES each
  `CR-<n>` from the live committed ledger's max at promotion time (a rebase may land
  base-appended entries first), so a pending id never collides by construction.
- `.harness/codex-refutations.md` — the committed durable cross-run ledger (its purpose
  header carries the entry schema; promoted at ship by drive-ship.md's activation-aware
  step).

**Five hard bounds (each binding):**
1. Every entry records a REPLAYABLE check — an executable repro command + a bounded env
   manifest where the refutation is behavioral, OR (run-local `codex-refuted-<scope>.md`
   entries only) doc-anchored artifact cites (file:line at a named SHA) whose re-reading
   IS the replay. COMMITTED entries ALWAYS carry an executable hermetic `env -i` line
   (doc-anchored ones encode their cites as repo-relative greps). On any re-flag the
   coordinator RE-EXECUTES the recorded check — runs the command verbatim from the repo
   root at the reviewed tip, or re-reads the cites; a differing result (changed
   output/exit, or cited text that no longer supports the refutation) VOIDS the entry,
   and an executed red in the faithful env ALWAYS defeats the ledger.
2. Refutation content is NEVER injected into harden/finalize auditor prompts (voice
   independence). REVIEW-scope re-audit prompts MAY carry applicable entries as
   prior-round enrichment — this EXTENDS, and does not reword, the existing enrichment
   rule (PRIOR rounds only, never the same-round Claude reviewer output).
3. Entries are finding-specific, with evidence + run-scope qualifiers — never
   class-level "X-like findings are settled".
4. A P1→P2 downgrade requires the coordinator's OWN executed reproduction of the
   fail-safe direction; the threat-model arm applies only to verbatim
   `docs/drive-enforcement.md` exclusions.
5. A repro timeout leaves the finding UN-refuted — it mints nothing and voids nothing
   (the finding is adjudicated on its merits this round).

After this stage:
- **FINDINGS** → `/drive` loops `/drive-implement` on this scope (it owns the cap-8).
- **CONVERGED** → `/drive` proceeds (next slice → phase-integration → after all
  phases, verify/ship).
