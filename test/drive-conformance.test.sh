#!/usr/bin/env bash
# Plain-bash test runner for bin/drive-conformance.sh.
# Asserts acceptance criteria 0,1,2,3,4,4b,4c,5,10, Item-C C1..C4b, and the Phase-1
# checkpoint criteria (CK1..CK6: --mode checkpoint, epoch-aware phasedesign-gate, audit
# ancestry, the epoch-unmarked fail-closed check, the dangling-symlink inflight marker,
# and audit cross-live-ref dedup). Prints PASS/FAIL per case and exits nonzero if any fail. Builds hermetic
# throwaway repos via test/fixtures/mkfixture.sh.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
CONF="$ROOT/bin/drive-conformance.sh"
# shellcheck source=test/fixtures/mkfixture.sh
source "$HERE/fixtures/mkfixture.sh"
set +e   # mkfixture.sh enables -e; the runner captures exit codes itself, so disable it

PASS=0; FAIL=0
trap '[ -n "${FIXROOT:-}" ] && rm -rf "$FIXROOT"' EXIT

# Run conformance for a fixture repo+rundir. Sets RC and OUT. Args: repo rundir mode...
run_conf() {
  local repo="$1" rd="$2"; shift 2
  OUT="$(cd "$repo" && "$CONF" "$rd" "$@" 2>/dev/null)"
  RC=$?
}

# Seed a CONVERGED finalize artifact (the ship gate's terminal tip-binding candidate-R).
# A finalize review carries a Verdict, an AppliedEdits marker, and a reviewed-sha, plus a
# non-empty codex sibling. $1=run_dir $2=N $3=reviewed-sha $4=applied(yes|no, default no).
# Mirrors mkfixture.sh's _write_review/_write_codex shape for the `finalize` scope.
seed_finalize() {
  local rd="$1" n="$2" sha="$3" applied="${4:-no}"
  mkdir -p "$rd"
  {
    echo "# Review finalize round $n"
    echo
    echo "## Verdict: CONVERGED"
    echo "## AppliedEdits: $applied"
    echo
    echo "reviewed-sha: $sha"
  } > "$rd/review-finalize-$n.md"
  { echo "codex review for finalize"; echo "looks fine"; } > "$rd/codex-review-finalize.md"
}

# Seed a FINDINGS finalize artifact (NOT converged) — same shape as seed_finalize but the
# Verdict is FINDINGS, so the ship gate's b-ii finalize candidate-R scan rejects it (no
# converged finalize -> candidate_R="" -> no-review). Mirrors mkfixture.sh's
# _write_review_findings shape for the `finalize` scope. $1=run_dir $2=N $3=reviewed-sha.
seed_finalize_findings() {
  local rd="$1" n="$2" sha="$3"
  mkdir -p "$rd"
  {
    echo "# Review finalize round $n"
    echo
    echo "## Verdict: FINDINGS"
    echo "## AppliedEdits: no"
    echo
    echo "reviewed-sha: $sha"
  } > "$rd/review-finalize-$n.md"
  { echo "codex review for finalize"; echo "looks fine"; } > "$rd/codex-review-finalize.md"
}

# Seed a CONVERGED finalize artifact that OMITS its `reviewed-sha:` line -> reviewed_sha_of
# fails in the ship gate's b-ii scan -> candidate_R="" -> no-review. Same shape as
# seed_finalize but the sha line is absent (codex sibling still present). $1=run_dir $2=N.
seed_finalize_no_sha() {
  local rd="$1" n="$2"
  mkdir -p "$rd"
  {
    echo "# Review finalize round $n"
    echo
    echo "## Verdict: CONVERGED"
    echo "## AppliedEdits: no"
  } > "$rd/review-finalize-$n.md"
  { echo "codex review for finalize"; echo "looks fine"; } > "$rd/codex-review-finalize.md"
}

# Assert exit code. $1=desc $2=expected-rc $3=actual-rc
assert_rc() {
  if [ "$2" = "$3" ]; then
    echo "PASS: $1 (exit $3)"; PASS=$((PASS+1))
  else
    echo "FAIL: $1 (expected exit $2, got $3) :: ${OUT:-}"; FAIL=$((FAIL+1))
  fi
}

# Assert $OUT contains substring. $1=desc $2=needle
assert_out_contains() {
  case "$OUT" in
    *"$2"*) echo "PASS: $1"; PASS=$((PASS+1)) ;;
    *)      echo "FAIL: $1 (missing '$2') :: ${OUT:-}"; FAIL=$((FAIL+1)) ;;
  esac
}

# Assert two strings are equal. $1=desc $2=expected $3=actual
assert_eq() {
  if [ "$2" = "$3" ]; then
    echo "PASS: $1"; PASS=$((PASS+1))
  else
    echo "FAIL: $1 (expected '$2', got '$3')"; FAIL=$((FAIL+1))
  fi
}

# Assert $OUT is valid JSON. $1=desc
assert_valid_json() {
  if printf '%s' "$OUT" | jq -e . >/dev/null 2>&1; then
    echo "PASS: $1"; PASS=$((PASS+1))
  else
    echo "FAIL: $1 (not valid JSON) :: ${OUT:-}"; FAIL=$((FAIL+1))
  fi
}

# Assert $OUT contains needle EXACTLY $3 times. $1=desc $2=needle $3=expected-count
assert_out_count() {
  local n; n="$(printf '%s' "$OUT" | grep -o -- "$2" | wc -l | tr -d ' ')"
  if [ "$n" = "$3" ]; then
    echo "PASS: $1"; PASS=$((PASS+1))
  else
    echo "FAIL: $1 (expected $3 '$2', got $n) :: ${OUT:-}"; FAIL=$((FAIL+1))
  fi
}

# Assert OUT (the JSON verdict) contains a substring. $1=desc $2=needle (from PR #38)
assert_out() {
  if printf '%s' "${OUT:-}" | grep -q "$2"; then
    echo "PASS: $1"; PASS=$((PASS+1))
  else
    echo "FAIL: $1 (output missing '$2') :: ${OUT:-}"; FAIL=$((FAIL+1))
  fi
}
echo "=== AC0: plan-gate (design review omission-proof) ==="
read -r repo rd < <(mk_plan clean)
run_conf "$repo" "$rd" --mode plan-gate;            assert_rc "AC0 plan-gate clean" 0 "$RC"
read -r repo rd < <(mk_plan nodesign)
run_conf "$repo" "$rd" --mode plan-gate;            assert_rc "AC0 plan-gate no design review" 1 "$RC"
read -r repo rd < <(mk_plan nocodex)
run_conf "$repo" "$rd" --mode plan-gate;            assert_rc "AC0 plan-gate no codex" 1 "$RC"
read -r repo rd < <(mk_plan findings)
run_conf "$repo" "$rd" --mode plan-gate;            assert_rc "AC0 plan-gate highest-N FINDINGS" 1 "$RC"

# AC0b: a FINDINGS review whose BODY contains a later standalone '## Verdict: CONVERGED'
# heading line (e.g. quoting/echoing a prior round) must NOT count as converged — only the
# FIRST verdict line decides. Pre-fix, verdict_converged grepped the whole file line-anchored
# and the later heading flipped a FINDINGS file to "converged" (a real omission hole).
read -r repo rd < <(mk_plan clean)
{ echo "# Review design round 2"; echo; echo "## Verdict: FINDINGS"; echo;
  echo "reviewed-sha: $(printf '0%.0s' {1..40})"; echo;
  echo "### [BLOCKING] unresolved item"; echo;
  echo "Round 1 had been:"; echo "## Verdict: CONVERGED"; } > "$rd/review-design-1.md"
run_conf "$repo" "$rd" --mode plan-gate;            assert_rc "AC0b later standalone CONVERGED line in FINDINGS still blocked" 1 "$RC"

# AC0d: highest_review_file fail-closed on a DANGLING higher-N review symlink. A CONVERGED
# review-design-1.md plus a DANGLING (broken) review-design-2.md is corruption at the real
# highest round; an `-e`-only scan skips the broken link and drops to the N=1 CONVERGED round,
# so plan-gate PASSES (fail-OPEN). `-e || -L` counts N=2 as `best`; it is unreadable so
# verdict_converged fails -> block. Regression validity: against tip 109c0ed highest_review_file
# was `-e`-only, so this exits 0 (false clean); the assertion below flips to rc 1.
read -r repo rd < <(mk_plan dangling_highest)
run_conf "$repo" "$rd" --mode plan-gate;            assert_rc "AC0d dangling higher-N review drops to lower CONVERGED round -> blocked (fail closed)" 1 "$RC"
assert_out_contains "AC0d dangling highest-N reads as verdict-not-converged" '"reason":"verdict-not-converged"'

echo "=== AC0c: phasedesign-gate (per-phase Tier-2 design review, omission-proof) ==="
read -r repo rd < <(mk_phasedesign clean 1)
run_conf "$repo" "$rd" --mode phasedesign-gate:1;   assert_rc "AC0c phasedesign-gate clean" 0 "$RC"
read -r repo rd < <(mk_phasedesign nodesign 1)
run_conf "$repo" "$rd" --mode phasedesign-gate:1;   assert_rc "AC0c phasedesign-gate no phase-design review" 1 "$RC"
read -r repo rd < <(mk_phasedesign nocodex 1)
run_conf "$repo" "$rd" --mode phasedesign-gate:1;   assert_rc "AC0c phasedesign-gate no codex" 1 "$RC"
read -r repo rd < <(mk_phasedesign findings 1)
run_conf "$repo" "$rd" --mode phasedesign-gate:1;   assert_rc "AC0c phasedesign-gate highest-N FINDINGS" 1 "$RC"
# a clean phase-1 design does NOT satisfy a DIFFERENT phase's gate (scope is per-P)
read -r repo rd < <(mk_phasedesign clean 1)
run_conf "$repo" "$rd" --mode phasedesign-gate:2;   assert_rc "AC0c phasedesign-gate is per-phase (P1 review ≠ P2 gate)" 1 "$RC"

echo "=== AC1: regression — run dir whose featureBranch ref is absent ship gate BLOCKS (exit 2) ==="
# Hermetic reconstruction of the phase3-slice4 regression: a run dir whose
# featureBranch (drive/<runId>) does NOT resolve in the repo. Under --mode ship that
# unresolvable ref MUST fail closed (exit 2 = block), never silently pass. The fixture
# repo built by mk_slice_clean only has slice/<runId>/4a — no drive/<runId> branch —
# so `rev featureBranch` errors. Zero dependence on any machine-local leftover dir.
read -r repo rd < <(mk_slice_clean ac1ship)
run_conf "$repo" "$rd" --mode ship;                 assert_rc "AC1 absent featureBranch ship fail-closed (exit 2)" 2 "$RC"

echo "=== AC2: slice-merge sha-binding ==="
read -r repo rd < <(mk_slice_clean)
run_conf "$repo" "$rd" --mode slice-merge:4a;       assert_rc "AC2 slice-merge clean" 0 "$RC"
read -r repo rd < <(mk_slice_sha_mismatch)
run_conf "$repo" "$rd" --mode slice-merge:4a;       assert_rc "AC2 slice-merge sha-mismatch" 1 "$RC"
read -r repo rd < <(mk_slice_missing_review)
run_conf "$repo" "$rd" --mode slice-merge:4a;       assert_rc "AC2 slice-merge missing review" 1 "$RC"
read -r repo rd < <(mk_slice_no_codex)
run_conf "$repo" "$rd" --mode slice-merge:4a;       assert_rc "AC2 slice-merge no codex" 1 "$RC"

echo "=== AC3: codex_present rule — ANY non-empty codex file satisfies; empty does not ==="
# The gate does NOT parse the marker: a first-line CODEX_UNAVAILABLE degradation file is
# non-empty -> clean.
read -r repo rd < <(mk_plan codex_unavailable)
run_conf "$repo" "$rd" --mode plan-gate;            assert_rc "AC3 non-empty CODEX_UNAVAILABLE file satisfies codex" 0 "$RC"
# A real review whose body merely mentions the word is just a non-empty file -> clean
# (identical to the degradation file: codex_present() inspects only non-emptiness).
read -r repo rd < <(mk_plan codex_buried)
run_conf "$repo" "$rd" --mode plan-gate;            assert_rc "AC3 non-empty real codex file satisfies (marker not parsed)" 0 "$RC"
# EMPTY codex file (bare touch) does NOT satisfy -> plan-gate blocks (exit 1).
read -r repo rd < <(mk_plan codex_empty)
run_conf "$repo" "$rd" --mode plan-gate;            assert_rc "AC3 empty codex file does NOT satisfy (blocked)" 1 "$RC"

echo "=== AC4: ship ledger-tolerance + tight allowlist + ≤1-commit ==="
# Ship's terminal tip-binding candidate-R is now the CONVERGED finalize artifact (the phase
# review is demoted to a no-phase-review precondition). The mk_ship `clean` fixture already
# seeds a counting phase1 review (the precondition); add a CONVERGED review-finalize bound to
# R = the phase code commit (parent of the ledger tip), so R..tip = the single ledger commit
# ⊆ the allowlist -> clean. Without a finalize artifact the gate now blocks (no-review).
read -r repo rd < <(mk_ship clean)
seed_finalize "$rd" 1 "$(git -C "$repo" rev-parse 'HEAD^')"
run_conf "$repo" "$rd" --mode ship;                 assert_rc "AC4.i ship ledger-only clean" 0 "$RC"
# AC4.ii/iii/iv must EXERCISE the (a)(b)(c) allowlist-tightness logic, not stop at the b-ii
# finalize-absent short-circuit. Each seeds a counting phase1 review (b-i precondition, via
# mk_ship) PLUS a CONVERGED finalize bound to R = the phase1 code commit, chosen so b-i + b-ii
# both PASS and the candidate enters the (a)(b)(c) loop, where the offending content blocks it.
# The gate emits a single `no-review` token for ANY (a)(b)(c) failure (it does not differentiate
# the three checks), so we assert `"reason":"no-review"` AND that it is NOT `no-phase-review`
# (which would mean the b-i precondition fired and the (a)(b)(c) logic never ran — the very
# wrong-reason green these cases used to be). Each case is non-vacuous against its specific check
# (per-case mutation note).

# AC4.ii — (b) allowlist: R = phase1 code (HEAD^); R..tip = the single `extra.sh` commit. (a)
# ancestor ✓, (c) ≤1 commit ✓ (1 commit), (b) FAILS (extra.sh ∉ allowlist). MUTATION: drop the
# (b) subset check and R..tip = {extra.sh} passes subset -> ship CLEAN -> rc 0 (reds this).
read -r repo rd < <(mk_ship code_past_r)
seed_finalize "$rd" 1 "$(git -C "$repo" rev-parse 'HEAD^')"
run_conf "$repo" "$rd" --mode ship;                 assert_rc  "AC4.ii ship code past R blocked at (b) allowlist" 1 "$RC"
                                                    assert_out "AC4.ii reason is no-review (reached (a)(b)(c), not the b-i precondition)" '"reason":"no-review"'
                                                    case "$OUT" in *'no-phase-review'*) echo "FAIL: AC4.ii must NOT be no-phase-review ((a)(b)(c) skipped) :: $OUT"; FAIL=$((FAIL+1));; *) echo "PASS: AC4.ii reached (a)(b)(c) (not no-phase-review)"; PASS=$((PASS+1));; esac

# AC4.iii — (b) allowlist tightness: R = phase1 code (HEAD^); R..tip = the single `.harness/foo.md`
# commit. (a) ✓, (c) ✓ (1 commit), (b) FAILS (.harness/foo.md ∉ the 3-file allowlist — the WHOLE
# .harness/ dir is NOT blanket-allowed). MUTATION: widen the allowlist to a `.harness/` prefix and
# foo.md passes subset -> ship CLEAN -> rc 0 (reds this — guards the per-file tightness).
read -r repo rd < <(mk_ship other_harness_past_r)
seed_finalize "$rd" 1 "$(git -C "$repo" rev-parse 'HEAD^')"
run_conf "$repo" "$rd" --mode ship;                 assert_rc  "AC4.iii(tight) ship other .harness file blocked at (b) allowlist" 1 "$RC"
                                                    assert_out "AC4.iii reason is no-review (reached (a)(b)(c) allowlist)" '"reason":"no-review"'
                                                    case "$OUT" in *'no-phase-review'*) echo "FAIL: AC4.iii must NOT be no-phase-review :: $OUT"; FAIL=$((FAIL+1));; *) echo "PASS: AC4.iii reached (a)(b)(c) (not no-phase-review)"; PASS=$((PASS+1));; esac

# AC4.iv — (c) ≤1-commit: R = phase1 code (HEAD~2); R..tip = TWO ledger commits, BOTH allowlisted
# files. (a) ✓, (c) FAILS (2 > 1) — and (c) is checked BEFORE (b), so it fires first; (b) would
# pass since both files are allowlisted. MUTATION: drop the `ncommits -le 1` check and the two
# all-allowlisted commits pass (a)+(b) -> ship CLEAN -> rc 0 (reds this — guards the ≤1-commit rule).
read -r repo rd < <(mk_ship two_ledger_commits)
seed_finalize "$rd" 1 "$(git -C "$repo" rev-parse 'HEAD~2')"
run_conf "$repo" "$rd" --mode ship;                 assert_rc  "AC4.iv(≤1) ship two ledger commits blocked at (c) commit-count" 1 "$RC"
                                                    assert_out "AC4.iv reason is no-review (reached (a)(b)(c) commit-count)" '"reason":"no-review"'
                                                    case "$OUT" in *'no-phase-review'*) echo "FAIL: AC4.iv must NOT be no-phase-review :: $OUT"; FAIL=$((FAIL+1));; *) echo "PASS: AC4.iv reached (a)(b)(c) (not no-phase-review)"; PASS=$((PASS+1));; esac

echo "=== AC4b: multi-phase existential R (no highest-N false-block) ==="
# The terminal tip-binding R is now the finalize artifact (not a phase R); the multi-phase
# phase1/phase2 reviews now satisfy ONLY the no-phase-review precondition (≥1 counting phase
# review). Seed a CONVERGED finalize bound to R2 = the phase2 code commit (parent of the
# ledger tip), whose R2..tip = the single ledger commit ⊆ allowlist -> clean.
read -r repo rd < <(mk_ship_multiphase)
seed_finalize "$rd" 1 "$(git -C "$repo" rev-parse 'HEAD^')"
run_conf "$repo" "$rd" --mode ship;                 assert_rc "AC4b multi-phase existential picks phase2 R (clean)" 0 "$RC"

echo "=== W1(audit): ship must NOT count a phasedesign DESIGN review as the integration review ==="
read -r repo rd < <(mk_ship_phasedesign_only)
run_conf "$repo" "$rd" --mode ship;                 assert_rc "W1 ship blocks when only a review-phasedesign<P> (with sha) exists, no integration review" 1 "$RC"

echo "=== Finalize (Phase 3): ship-gate finalize/phase-review preconditions (AC32-AC35) ==="
# The D27-deferred decisive cases NOT covered by any Phase-2 fixture (every Phase-2 ship
# fixture seeds BOTH a counting phase review AND a CONVERGED finalize, so the b-i
# no-phase-review / absent-or-FINDINGS-finalize no-review / unparseable-finalize branches
# were untaken). Each asserts the SPECIFIC reason token (the load-bearing distinction:
# WHICH guard fired) — an rc-only assert would pass green-for-the-wrong-reason (D-P3-3).
# Regression validity: the no-phase-review precondition (keyed on the COUNTING candidate_R)
# and the finalize terminal candidate-R did not exist pre-Phase-2; these cases fail against
# the pre-Phase-2 ship gate.

# AC32 (AC23 negative — absent): a counting phase1 review present but NO review-finalize-*.md.
# b-i passes (candidate_R holds phase1's R), then b-ii finds no converged finalize ->
# candidate_R="" -> ship blocks no-review (b-ii emptied it AFTER b-i passed).
read -r repo rd < <(mk_ship clean ac32-ship)   # seeds a counting phase1 review; NO finalize artifact
run_conf "$repo" "$rd" --mode ship;                 assert_rc  "AC32 ship absent finalize (phase review present) blocked" 1 "$RC"
                                                    assert_out "AC32 reason is no-review (b-ii, finalize absent)" '"reason":"no-review"'

# AC33 (AC23 negative — FINDINGS): a counting phase1 review present + a FINDINGS
# review-finalize-1.md (+ codex). b-ii rejects the non-converged finalize -> candidate_R="" ->
# no-review. (Distinct from AC32 only in that the finalize artifact EXISTS but is FINDINGS.)
read -r repo rd < <(mk_ship clean ac33-ship)
seed_finalize_findings "$rd" 1 "$(git -C "$repo" rev-parse 'HEAD^')"
run_conf "$repo" "$rd" --mode ship;                 assert_rc  "AC33 ship FINDINGS finalize (phase review present) blocked" 1 "$RC"
                                                    assert_out "AC33 reason is no-review (b-ii, finalize FINDINGS)" '"reason":"no-review"'

# AC33b (b-ii — malformed CONVERGED finalize, missing reviewed-sha): a counting phase1 review
# present + a CONVERGED review-finalize-1.md that OMITS its `reviewed-sha:` line (codex sibling
# present). b-ii's reviewed_sha_of fails -> the AND-chain short-circuits -> candidate_R="" ->
# no-review.
# WHAT IT GUARDS (precise): the REALISTIC regression — a no-sha finalize falling back to a USABLE
# candidate R (e.g. `candidate_R="$tip "`, or R->tip when the sha is absent). Under such a fallback
# R=tip gives R..tip = 0 commits (≤1 ✓) and an empty diff (subset ✓) -> ship CLEAN, flipping this
# assert. It does NOT independently guard a bare drop of the `&& fin_rsha=$(reviewed_sha_of ...)`
# conjunct: with the conjunct gone, fin_rsha stays empty, so candidate_R=" " yields NO loop token
# and the gate still blocks no-review (the property is coupled — a no-sha finalize cannot legitimately
# bind a candidate). Per the harden assessment that coupled residual is intrinsic, not over-engineered
# around; this case asserts the valid, load-bearing property: a no-sha CONVERGED finalize must NOT ship.
read -r repo rd < <(mk_ship clean ac33b-ship)
seed_finalize_no_sha "$rd" 1
run_conf "$repo" "$rd" --mode ship;                 assert_rc  "AC33b ship CONVERGED finalize missing reviewed-sha blocked" 1 "$RC"
                                                    assert_out "AC33b reason is no-review (b-ii, finalize sha unreadable)" '"reason":"no-review"'

# AC33c (b-ii — malformed CONVERGED finalize, missing codex sibling): a counting phase1 review
# present + a VALID CONVERGED review-finalize-1.md (valid reviewed-sha) but its
# codex-review-finalize.md DELETED. b-ii's codex_present finalize fails -> candidate_R="" ->
# no-review. NON-VACUOUS: the only thing the fixture withholds is the finalize codex sibling; if
# the gate stopped requiring `&& codex_present finalize`, candidate_R would hold the valid
# finalize R (an ancestor of the tip with only the ledger commit past it) -> ship CLEAN, flipping
# both asserts.
read -r repo rd < <(mk_ship clean ac33c-ship)
seed_finalize "$rd" 1 "$(git -C "$repo" rev-parse 'HEAD^')"   # valid CONVERGED finalize (writes codex sibling)
rm -f "$rd/codex-review-finalize.md"                          # drop the finalize codex sibling
run_conf "$repo" "$rd" --mode ship;                 assert_rc  "AC33c ship CONVERGED finalize missing codex sibling blocked" 1 "$RC"
                                                    assert_out "AC33c reason is no-review (b-ii, finalize codex missing)" '"reason":"no-review"'

# AC34 (AC24 — non-counting phase review, FINDINGS): a CONVERGED tip-binding finalize exists,
# but the ONLY review-phase1 is FINDINGS (so candidate_R empties at b-i) -> ship blocks
# no-phase-review. Built INLINE from mk_ship clean (D-P3-4): overwrite review-phase1-1.md to
# FINDINGS (candidate_R empties), then seed_finalize at HEAD^ (the phase code commit, parent of
# the ledger tip — a VALID finalize R, so the ONLY blocking cause is the non-counting phase
# review). Reason MUST be no-phase-review (b-i fires FIRST and exits before b-ii), NOT no-review.
read -r repo rd < <(mk_ship clean ac34-ship)
_write_review_findings "$rd" phase1 1 "$(git -C "$repo" rev-parse 'HEAD^')"   # flip phase1 to FINDINGS
seed_finalize "$rd" 1 "$(git -C "$repo" rev-parse 'HEAD^')" yes              # valid CONVERGED finalize
run_conf "$repo" "$rd" --mode ship;                 assert_rc  "AC34 ship CONVERGED finalize + only FINDINGS phase review blocked" 1 "$RC"
                                                    assert_out "AC34 reason is no-phase-review (b-i keys off COUNTING set)" '"reason":"no-phase-review"'

# AC35 (AC24 — non-counting phase review, missing codex): same as AC34 but the phase1 review
# stays CONVERGED while its codex sibling is DELETED -> codex_present fails -> candidate_R
# empties at b-i -> no-phase-review. Proves b-i keys off the FULL counting check (verdict + sha
# + codex), not bare review-phase1 pathname presence.
read -r repo rd < <(mk_ship clean ac35-ship)
rm -f "$rd/codex-review-phase1.md"                                            # drop the phase codex sibling
seed_finalize "$rd" 1 "$(git -C "$repo" rev-parse 'HEAD^')" yes              # valid CONVERGED finalize
run_conf "$repo" "$rd" --mode ship;                 assert_rc  "AC35 ship CONVERGED finalize + phase review missing codex blocked" 1 "$RC"
                                                    assert_out "AC35 reason is no-phase-review (missing phase codex)" '"reason":"no-phase-review"'

echo "=== AC4c: HARDEN->advance consumes post-harden review ==="
read -r repo rd < <(mk_phase_harden post_harden_ok 1)
run_conf "$repo" "$rd" --mode phase-merge:1;        assert_rc "AC4c phase-merge post-harden review matches tip" 0 "$RC"
read -r repo rd < <(mk_phase_harden stale_only 1)
run_conf "$repo" "$rd" --mode phase-merge:1;        assert_rc "AC4c phase-merge stale-only review blocked" 1 "$RC"

echo "=== AC-findings: a sha-matching FINDINGS review is NOT converged (slice/phase/audit) ==="
# A review whose reviewed-sha MATCHES the tip but whose verdict is FINDINGS must block with
# reason verdict-not-converged — never pass on the sha match alone (the not-converged branch of
# check_scope_counts, previously untested for slice-merge / phase-merge / audit).
read -r repo rd < <(mk_slice_findings)
run_conf "$repo" "$rd" --mode slice-merge:4a;       assert_rc  "AC-findings slice-merge FINDINGS blocked" 1 "$RC"
                                                    assert_out "AC-findings slice-merge reason is verdict-not-converged" "verdict-not-converged"
read -r repo rd < <(mk_phase_harden findings 1)
run_conf "$repo" "$rd" --mode phase-merge:1;        assert_rc  "AC-findings phase-merge FINDINGS blocked" 1 "$RC"
                                                    assert_out "AC-findings phase-merge reason is verdict-not-converged" "verdict-not-converged"
read -r repo rd < <(mk_audit findings)
run_conf "$repo" "$rd" --mode audit;                assert_rc  "AC-findings audit flags merged slice with FINDINGS review" 1 "$RC"

echo "=== AC-audit-skip: an unreviewed slice NOT merged into the live phase is NOT flagged ==="
# audit reports ONLY slices merged into the live phaseInt; an unreviewed sibling that the phase
# never integrated must be SKIPPED (the 'not an ancestor' branch, previously unexercised).
read -r repo rd < <(mk_audit not_merged)
run_conf "$repo" "$rd" --mode audit;                assert_rc "AC-audit-skip unmerged unreviewed slice not flagged (clean)" 0 "$RC"

# AC-ship-skip REMOVED (Phase-3 harden): it tested "ship skips a FINDINGS phase review as a
# candidate R" — but after the finalize wiring (D17) phase reviews are NO LONGER candidate Rs;
# the (a)(b)(c) candidate is the finalize artifact, and a phase review only feeds the b-i
# precondition. The live equivalent — a FINDINGS phase review must not count toward b-i, so a run
# whose only phase review is FINDINGS blocks with `no-phase-review` — is covered NON-VACUOUSLY by
# AC34 (which asserts the specific `no-phase-review` token). The old fixture mk_ship_findings_only
# only exercised the b-ii finalize-absent path (redundant with AC32), so this case tested nothing
# meaningful; removed along with the now-orphaned fixture.

echo "=== AC5: exit-2 behavior (absent ref => git error) ==="
read -r repo rd < <(mk_slice_clean ac5)
# slice-merge for a nonexistent slice id -> ref unresolvable -> exit 2 (gate fails open)
run_conf "$repo" "$rd" --mode slice-merge:nope;     assert_rc "AC5 slice-merge absent ref exit 2" 2 "$RC"
# phase-merge for a nonexistent phase ref -> exit 2
run_conf "$repo" "$rd" --mode phase-merge:9;        assert_rc "AC5 phase-merge absent ref exit 2" 2 "$RC"
# ship with absent featureBranch -> exit 2 (gate fails CLOSED)
read -r repo rd < <(mk_slice_clean ac5ship)
run_conf "$repo" "$rd" --mode ship;                 assert_rc "AC5 ship absent featureBranch exit 2" 2 "$RC"
# audit with no live phaseInt -> clean exit 0 (no false block)
run_conf "$repo" "$rd" --mode audit;                assert_rc "AC5 audit no live phase exit 0" 0 "$RC"
# audit positive: a slice merged into the live phaseInt with NO counting review -> exit 1
read -r repo rd < <(mk_audit unreviewed)
run_conf "$repo" "$rd" --mode audit;                assert_rc "AC5 audit flags merged-but-unreviewed slice" 1 "$RC"
# audit negative: same shape but slice IS reviewed -> exit 0
read -r repo rd < <(mk_audit reviewed)
run_conf "$repo" "$rd" --mode audit;                assert_rc "AC5 audit clean when merged slice reviewed" 0 "$RC"

echo "=== AC5b: induced git/IO error (corrupt object) -> exit 2, never a clean/violation verdict ==="
# ship: R resolves + is ancestor + R..tip=1 commit, but the tip's TREE is corrupt so the
# `git diff --name-only R..tip` allowlist check ERRORS. That git/IO error MUST surface as
# exit 2 (fail-closed) -- proc-substitution would have swallowed it into a false-clean.
# Ship now short-circuits to no-review (empty candidate_R) BEFORE the git diff when there is
# no CONVERGED finalize artifact; to still exercise the git-error path the fixture must seed a
# finalize R (= the phase code commit, parent of the corrupt tip; its tree is intact) so
# candidate_R is non-empty and the (a)(b)(c) loop reaches the failing diff against the corrupt tip.
read -r repo rd < <(mk_ship_git_error)
seed_finalize "$rd" 1 "$(git -C "$repo" rev-parse 'HEAD^')"
run_conf "$repo" "$rd" --mode ship;                 assert_rc "AC5b ship git-error (corrupt tree -> diff fails) exit 2" 2 "$RC"
# audit: live phaseInt ref enumerates but its tip object is corrupt -> exit 2,
# NOT exit 0 clean (which would swallow a broken repo into 'nothing to audit').
read -r repo rd < <(mk_audit_git_error)
run_conf "$repo" "$rd" --mode audit;                assert_rc "AC5b audit git-error (corrupt live tip) exit 2" 2 "$RC"

echo "=== AC10: concurrency — run-keyed phaseInt isolation ==="
read -r repo rd1 rd2 < <(mk_two_concurrent)
run_conf "$repo" "$rd1" --mode phase-merge:1;       assert_rc "AC10 R1 phase-merge clean (own ref)" 0 "$RC"
run_conf "$repo" "$rd2" --mode phase-merge:1;       assert_rc "AC10 R2 phase-merge blocked (own ref)" 1 "$RC"

echo "=== AC-C: impl-presence (test-presence invariant) ==="
# AC-C1: slice diff adds a runnable test path -> exit 0 (clean).
read -r repo rd < <(mk_impl_presence test)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C1 slice with pytest test -> clean" 0 "$RC"
read -r repo rd < <(mk_impl_presence test_sh)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C1 slice with bash test -> clean" 0 "$RC"
# *_test.py suffix form (the other runnable pytest basename) -> clean.
read -r repo rd < <(mk_impl_presence test_suffix)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C1 slice with *_test.py suffix form -> clean" 0 "$RC"
# Nested test/sub/x.test.sh: the bash runner globs only test/*.test.sh, so a NESTED path
# is NOT a runnable test -> violation (proves the predicate anchors to the runner glob,
# not a bare `.test.sh` substring).
read -r repo rd < <(mk_impl_presence test_sh_nested)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C4b nested test/sub/x.test.sh not runner-globbed -> violation" 1 "$RC"
# AC-C2: no test path AND no waiver trailer -> exit 1 (violation).
read -r repo rd < <(mk_impl_presence notest)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C2 slice code-only no waiver -> violation" 1 "$RC"
# AC-C3: no test path but a real Drive-Test-Waiver: commit TRAILER -> exit 0.
read -r repo rd < <(mk_impl_presence waiver)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C3 real waiver trailer -> clean" 0 "$RC"
# AC-C3b: waiver string in body PROSE (not a trailer block) -> exit 1 (NOT waived).
read -r repo rd < <(mk_impl_presence waiver_prose)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C3b waiver in body prose (not trailer) -> violation" 1 "$RC"
# AC-C4: unresolvable ref / missing drive/<runId> -> exit 2 (abnormal, explicit rc-2 case).
read -r repo rd < <(mk_impl_presence no_drive)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C4 missing drive/<runId> merge-base -> exit 2" 2 "$RC"
# AC-C4 (unresolvable slice ref): a slice id that does not exist -> exit 2.
read -r repo rd < <(mk_impl_presence test impl-absent-ref)
run_conf "$repo" "$rd" --mode impl-presence:nope;   assert_rc "AC-C4 absent slice ref -> exit 2" 2 "$RC"
# AC-C4b (predicate anchored to runners): support/non-runnable paths do NOT count -> exit 1.
read -r repo rd < <(mk_impl_presence pred_helpers)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C4b tests/_helpers.py excluded -> violation" 1 "$RC"
read -r repo rd < <(mk_impl_presence pred_conftest)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C4b tests/conftest.py excluded -> violation" 1 "$RC"
read -r repo rd < <(mk_impl_presence pred_fixtures)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C4b tests/fixtures/* excluded -> violation" 1 "$RC"
read -r repo rd < <(mk_impl_presence pred_pyc)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C4b *.pyc excluded -> violation" 1 "$RC"
read -r repo rd < <(mk_impl_presence pred_root)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C4b root test_root.py not under tests/ -> violation" 1 "$RC"
read -r repo rd < <(mk_impl_presence pred_docs)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C4b docs/*.test.md (no runner) -> violation" 1 "$RC"
# Finding 1 (BLOCKING): a DELETED test path is NOT test evidence (--diff-filter=d excludes D). A slice
# whose only test-path change is deleting tests/foo/test_existing.py (+ a code edit), with no
# new test + no waiver -> violation. (Pre-fix the plain `git diff --name-only` listed the
# deleted path and is_test_path matched it, falsely passing.)
read -r repo rd < <(mk_impl_presence del_test)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C(del) deleted test path is NOT evidence -> violation" 1 "$RC"
# Harden round-3 (MAJOR): a slice that adds coverage by RENAMING a runnable test INTO another
# runnable test path (test/foo.test.sh -> test/bar.test.sh, with a real edit so git classes it R)
# + a code change must be CLEAN. The old --diff-filter=AM EXCLUDED R/C/T and false-DENIED this;
# --diff-filter=d (exclude deletions only) keeps the rename DESTINATION -> counted. NON-VACUOUS:
# this fails under the old AM filter (the R rename's dest is dropped, leaving only the code file).
read -r repo rd < <(mk_impl_presence rename_test)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C(rename) rename runnable test INTO test path (R) is evidence -> clean" 0 "$RC"
# Finding 2 (BLOCKING): a dotfile-basename test path is NOT runnable (the real runners skip
# dotfiles), so it must NOT count even though bash 3.2 `case test/*.test.sh` matches it.
read -r repo rd < <(mk_impl_presence dot_test_sh)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C(dot) test/.noop.test.sh dotfile not runnable -> violation" 1 "$RC"
read -r repo rd < <(mk_impl_presence dot_test_py)
run_conf "$repo" "$rd" --mode impl-presence:3a;     assert_rc "AC-C(dot) tests/mc/.foo_test.py dotfile not runnable -> violation" 1 "$RC"
# usage guard: empty id after impl-presence: -> exit 2
read -r repo rd < <(mk_impl_presence test impl-empty-id)
OUT="$(cd "$repo" && "$CONF" "$rd" --mode "impl-presence:" 2>/dev/null)"; RC=$?
assert_rc "AC-C empty impl-presence id -> exit 2" 2 "$RC"

echo "=== CK1: --mode checkpoint — safe-boundary proof + artifact-derived counters ==="
# Regression-guard validity: every CK case expecting exit 0/1 FAILS against the
# pre-change script — `--mode checkpoint` did not exist (usage exit 2).
read -r repo rd < <(mk_checkpoint clean)
run_conf "$repo" "$rd" --mode checkpoint
assert_rc "CK1 quiescent well-formed fixture clean (state.json corrupt — never read)" 0 "$RC"
assert_out_contains "CK1 clean envelope" '"clean":true,"mode":"checkpoint"'
# All six I3 rules in one assertion: reviewCount from pure-integer-N counts (the
# review-1.1-final.md non-round file does NOT count); phaseReviewRound = 3 review-phase1
# files MINUS the 1 AppliedEdits:yes regress marker (regress files don't overcount the
# round); hardenRound counts ONLY yes (one yes + one no -> 1); phaseDesignRound epoch-0;
# finalizeRound = 0 (a bare integer — the run-singleton 6th counter — this fixture seeds no
# review-finalize-*.md, so the AppliedEdits:yes count over that family is 0).
assert_out_contains "CK1 counters per I3" \
  '"counters":{"redesigns":{},"phaseDesignRound":{"1":1},"phaseReviewRound":{"1":2},"hardenRound":{"1":1},"reviewCount":{"1.1":2},"finalizeRound":0}'

# (a) an open in-flight marker fails the checkpoint — never probe, never wait.
read -r repo rd < <(mk_checkpoint inflight)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "CK1 open in-flight marker -> exit 1" 1 "$RC"
assert_out_contains "CK1 inflight-open violation" '"reason":"inflight-open"'
# (a) a DANGLING symlink named inflight-*.marker still reads as open (fail closed). The
# `-e` glob guard follows the link and fails, so the marker-only glob would skip it and
# read clean; the `-L` guard fails it closed. Regression validity: pre-change had only
# `-e`, so this exits 0 (false clean); the assertion below flips to rc 1.
read -r repo rd < <(mk_checkpoint inflight_symlink)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "CK1 dangling-symlink inflight marker -> exit 1 (not clean)" 1 "$RC"
assert_out_contains "CK1 dangling-symlink reads as inflight-open" '"reason":"inflight-open"'

# (c) artifact well-formedness violations
read -r repo rd < <(mk_checkpoint unparseable_review)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "CK1 round file w/o verdict -> exit 1" 1 "$RC"
assert_out_contains "CK1 unparseable-review violation" '"reason":"unparseable-review"'
read -r repo rd < <(mk_checkpoint unparseable_harden)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "CK1 harden file w/o AppliedEdits -> exit 1" 1 "$RC"
assert_out_contains "CK1 unparseable-harden violation" '"reason":"unparseable-harden"'
# (c) DANGLING review/harden dirents are corruption, not absence: the round scans must COUNT
# them present-but-unparseable (fail closed), never skip them (which would undercount the I3
# counters the resume path reads and read CLEAN on corruption). Regression validity: against
# tip 109c0ed both scans were `-e`-only, so the broken symlink is skipped and the otherwise-
# quiescent fixture reads clean (rc 0); the assertions below flip to rc 1.
read -r repo rd < <(mk_checkpoint dangling_review)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "CK1 dangling review-*.md symlink -> exit 1 (counted, not skipped)" 1 "$RC"
assert_out_contains "CK1 dangling review reads as unparseable-review" '"reason":"unparseable-review"'
read -r repo rd < <(mk_checkpoint dangling_harden)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "CK1 dangling harden-*.md symlink -> exit 1 (counted, not skipped)" 1 "$RC"
assert_out_contains "CK1 dangling harden reads as unparseable-harden" '"reason":"unparseable-harden"'

# (b) divergent phaseInt (related to drive/<runId> in neither direction)
read -r repo rd < <(mk_checkpoint divergent)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "CK1 divergent phaseInt -> exit 1" 1 "$RC"
assert_out_contains "CK1 phaseInt-divergent violation" '"reason":"phaseInt-divergent"'

# (b) non-numeric phase id accepted by the ancestry rule (no numeric ordering anywhere)
read -r repo rd < <(mk_checkpoint fourA)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "CK1 non-numeric phaseInt 4a accepted (clean)" 0 "$RC"

# usage/IO: a run dir with no drive/<runId> branch -> exit 2
read -r repo rd < <(mk_slice_clean ckpt-nodrive)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "CK1 absent featureBranch -> exit 2" 2 "$RC"

echo "=== CK2: counters — regress subtraction edge + epoch-scoped design rounds ==="
# yes-count exceeding the review-file count is malformed: regress-mismatch, value 0.
read -r repo rd < <(mk_checkpoint regress_mismatch)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "CK2 yes-count > review count -> exit 1" 1 "$RC"
assert_out_contains "CK2 regress-mismatch violation" '"reason":"regress-mismatch"'
assert_out_contains "CK2 phaseReviewRound reported 0" '"phaseReviewRound":{"1":0}'
assert_out_contains "CK2 hardenRound counts both yes files" '"hardenRound":{"1":2}'
# phaseDesignRound counts ONLY the current epoch's files once an r1 marker exists.
read -r repo rd < <(mk_checkpoint epoch_files)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "CK2 epoch_files fixture clean" 0 "$RC"
assert_out_contains "CK2 epoch-0 round file does not count under r1" '"phaseDesignRound":{"1":2}'
assert_out_contains "CK2 redesigns from marker" '"redesigns":{"1":1}'
# Markerless epoch artifact: epoch-r1 review+codex present, redesign-1-r1.marker MISSING.
# highest_epoch() falls back to 0 and the run reads clean — the proof must fail closed.
# Regression validity: pre-change has no epoch-unmarked check, resolves epoch 0, and the
# fixture is otherwise quiescent/well-formed -> exit 0 (false clean); this flips to rc 1.
read -r repo rd < <(mk_checkpoint epoch_unmarked)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "CK2 markerless epoch artifact -> exit 1 (fail closed, not clean)" 1 "$RC"
assert_out_contains "CK2 epoch-unmarked violation" '"reason":"epoch-unmarked"'
# Dangling redesign-1-r1.marker (broken symlink) + a stale well-formed epoch-0 review;
# otherwise quiescent. An `-e`-only marker scan follows the broken link, fails `-e`, SKIPS it,
# sees no redesign marker, and reads clean (fail-OPEN). `-e || -L` counts it -> highest_epoch=1
# and the gapless epoch check's `-e` probe of the broken r1 marker fails -> epoch-gap. Regression
# validity: against the pre-fix tip 77a7476 the marker scan's `-e`-only guard skips the symlink
# and the run reads clean (rc 0); this flips to rc 1.
read -r repo rd < <(mk_checkpoint epoch_marker_dangling)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "CK2 dangling epoch marker counts -> exit 1 (fail closed, not clean)" 1 "$RC"
assert_out_contains "CK2 dangling epoch marker reports epoch-gap" '"reason":"epoch-gap"'

# FIX 1: a phase id containing `-r` (`4-r1`) with a markerless epoch artifact must be flagged
# epoch-unmarked under the CORRECT scope `phasedesign4-r1`. The pre-fix `%%-r*` phase-id split
# truncates to `4` and emits the violation under the WRONG scope `phasedesign4` (and resolves
# the wrong epoch glob). Regression validity: against the pre-fix script the violation object
# carries `"scope":"phasedesign4"` — the exact-scope assertion below flips with the fix.
read -r repo rd < <(mk_checkpoint epoch_unmarked_phaseid_dash_r)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "CK2 markerless epoch on a -r-containing phase id -> exit 1 (fail closed)" 1 "$RC"
assert_out_contains "CK2 epoch-unmarked attributed to the FULL phase id phasedesign4-r1 (not mis-truncated to phasedesign4)" \
  '{"scope":"phasedesign4-r1","reason":"epoch-unmarked",'
# FIX 2: the codex-half of the epoch-unmarked scan, exercised INDEPENDENTLY — ONLY a codex
# sibling (codex-review-phasedesign1-r1.md) with no review file and no r1 marker. A regression
# dropping the codex glob from unmarked_epochs()/the phase-derivation loop would otherwise stay
# green (every other epoch-unmarked fixture also seeds a review file that masks the codex path).
read -r repo rd < <(mk_checkpoint epoch_unmarked_codex_only)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "CK2 codex-only markerless epoch -> exit 1 (codex-half fails closed)" 1 "$RC"
assert_out_contains "CK2 codex-only epoch-unmarked violation" '{"scope":"phasedesign1","reason":"epoch-unmarked",'

# FIX 3: the phaseDesignRound COUNTER on a `-r`-containing phase id (`4-r1`) at epoch 0. The
# pd_key is `4-r1`; the pre-fix `${t##*-r}` split mis-keys the counter to phase `4` with count 0
# ('"phaseDesignRound":{"4":0}'). The marker-anchored phase_of_pd_key keeps the literal phase id,
# so the counter is '"phaseDesignRound":{"4-r1":2}'. Regression validity: against the pre-fix tip
# f5c8f25 the output carries {"4":0}; the {"4-r1":2} assertion below flips with the fix. (The run
# is exit 1 from the epoch-unmarked detector's by-design fail-closed residual on a terminal-`-r`
# phase id — that is the corruption-detector site, deliberately NOT marker-anchored; the counter
# value is the thing under test here.)
read -r repo rd < <(mk_checkpoint epoch_phaseid_dash_r_round)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "CK2 -r-phase-id counter run -> exit 1 (detector residual)" 1 "$RC"
assert_out_contains "CK2 phaseDesignRound counts the FULL -r phase id 4-r1 (not mis-keyed to 4)" \
  '"phaseDesignRound":{"4-r1":2}'

echo "=== Finalize (Phase 3): checkpoint (finalize) arm (AC36/AC37) ==="
# AC36 (AC25 positive): a CONVERGED review-finalize-1.md with `## AppliedEdits: yes` + codex,
# NO slice/<name>/finalize branch. Assert the POSITIVE observables (D-P3-3/P1#3): checkpoint
# does NOT validate review scopes against slice branches (a misclassified finalize would
# silently land in reviewCount, raising no violation), so the vacuous "no slice violation"
# pin is meaningless. Assert (i) counters.finalizeRound==1 AND (ii) reviewCount has NO
# `finalize` key (the minimal fixture's reviewCount is {} -> assert the exact "reviewCount":{}).
# If the (finalize) arm were deleted, reviewCount would gain "finalize":1 and finalizeRound
# would be 0 -> both assertions flip. Regression validity: pre-Phase-2 there was no (finalize)
# arm (finalize counted as a slice).
read -r repo rd < <(mk_checkpoint finalize_round)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "AC36 checkpoint finalize_round clean" 0 "$RC"
assert_out_contains "AC36 finalizeRound counts the AppliedEdits:yes finalize round" '"finalizeRound":1'
assert_out_contains "AC36 reviewCount has NO finalize key (diverted by the (finalize) arm, not slice-classified)" '"reviewCount":{}'
# AC37 (AC25 negative): review-finalize-1.md keeps `## Verdict:` (passes the unparseable-review
# Verdict grep) but OMITS the `AppliedEdits:` line -> the (finalize) arm fails closed
# -> unparseable-finalize, exit 1. Assert the SPECIFIC reason (mirrors unparseable-harden).
read -r repo rd < <(mk_checkpoint finalize_unparseable)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "AC37 checkpoint finalize missing AppliedEdits -> exit 1" 1 "$RC"
assert_out_contains "AC37 unparseable-finalize violation" '"reason":"unparseable-finalize"'

echo "=== CK3/CK4: epoch-gap + dropped-increment recovery; state.json never read ==="
# Markers r1+r3 with state.json claiming redesigns:2 — the dropped 3rd increment is
# recovered from the artifact (highest-R wins), the gap is flagged for a human.
read -r repo rd < <(mk_checkpoint epoch_gap)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "CK3 gapped epoch markers -> exit 1" 1 "$RC"
assert_out_contains "CK3 epoch-gap violation" '"reason":"epoch-gap"'
assert_out_contains "CK3 redesigns = highest R (3), not state's 2 or the file count 2" '"redesigns":{"1":3}'
OUT_WITH_STATE="$OUT"
rm -f "$rd/state.json"
run_conf "$repo" "$rd" --mode checkpoint
assert_rc "CK4 state.json deleted -> same exit" 1 "$RC"
assert_eq "CK4 output byte-identical without state.json (state never a proof input)" \
  "$OUT_WITH_STATE" "$OUT"

echo "=== CK5: epoch-aware phasedesign-gate ==="
# Regression-guard validity: pre-change the gate had no epoch concept — epoch1_stale's
# stale epoch-0 CONVERGED pair PASSED (exit 0), and epoch1_clean's r1-scoped files were
# invisible to the bare-token glob (exit 1). Both assertions flip on the pre-change script.
read -r repo rd < <(mk_phasedesign epoch1_clean 1)
run_conf "$repo" "$rd" --mode phasedesign-gate:1;   assert_rc "CK5 current-epoch (r1) CONVERGED pair satisfies the gate" 0 "$RC"
read -r repo rd < <(mk_phasedesign epoch1_stale 1)
run_conf "$repo" "$rd" --mode phasedesign-gate:1;   assert_rc "CK5 stale epoch-0 pair does NOT satisfy after a redesign" 1 "$RC"
assert_out_contains "CK5 stale epoch reports no-review for the current epoch" '"reason":"no-review"'
# Markerless epoch artifact (corruption / deleted marker): r1 review+codex present but
# redesign-1-r1.marker MISSING. highest_epoch() falls back to bare phasedesign1 and the
# seeded CONVERGED epoch-0 pair would PASS — the gate must instead fail closed. Regression
# validity: pre-change the gate has no markerless-epoch check, resolves epoch 0, and PASSES
# (rc 0); the assertion below flips to rc 1.
read -r repo rd < <(mk_phasedesign epoch1_unmarked 1)
run_conf "$repo" "$rd" --mode phasedesign-gate:1;   assert_rc "CK5 markerless r1 artifact fails the gate closed (not a stale epoch-0 PASS)" 1 "$RC"
assert_out_contains "CK5 markerless epoch reports epoch-unmarked" '"reason":"epoch-unmarked"'
# Dangling r1 marker (broken symlink) + ONLY a stale epoch-0 CONVERGED pair. An `-e`-only
# highest_epoch() follows the broken link, fails the `-e` test, SKIPS it, resolves epoch 0,
# and the stale epoch-0 pair PASSES (fail-OPEN). `-e || -L` counts the dangling marker ->
# epoch 1 -> scope phasedesign1-r1 has no review -> fail closed. Regression validity: against
# the pre-fix tip 77a7476 highest_epoch's `-e`-only guard skips the symlink and the gate
# PASSES (rc 0); this flips to rc 1.
read -r repo rd < <(mk_phasedesign epoch1_marker_dangling 1)
run_conf "$repo" "$rd" --mode phasedesign-gate:1;   assert_rc "CK5 dangling r1 marker counts -> gate fails closed (not a stale epoch-0 PASS)" 1 "$RC"
assert_out_contains "CK5 dangling-marker epoch resolves r1 -> no-review for current epoch" '"reason":"no-review"'

echo "=== CK6: audit live-phase selection by ancestry (criterion 11) ==="
# Regression-guard validity: pre-change audit picked the live phase by highest
# pure-NUMERIC <P> — the 4a fixture was skipped entirely (false clean, exit 0) and the
# completed-phase fixture was picked as live (false flag, exit 1). Both flip pre-change.
read -r repo rd < <(mk_audit_4a)
run_conf "$repo" "$rd" --mode audit;                assert_rc "CK6 non-numeric live phaseInt 4a IS audited (unreviewed slice flagged)" 1 "$RC"
read -r repo rd < <(mk_audit_completed)
run_conf "$repo" "$rd" --mode audit;                assert_rc "CK6 completed phaseInt (STRICT ancestor of drive) skipped -> clean" 0 "$RC"
# Equality (advance done, drive not yet past) classifies LIVE — still audited; this is
# the pre-retrofit behavior for a just-advanced phase and what the stop-guard relies on.
read -r repo rd < <(mk_audit_equal_tip)
run_conf "$repo" "$rd" --mode audit;                assert_rc "CK6 equal-tip phaseInt audits as live" 1 "$RC"
# Dedup: one unreviewed slice s1 merged into TWO live refs (the just-advanced equal-tip
# phaseInt/1 AND the descending phaseInt/2) is flagged ONCE, not twice (the raw violations
# JSON is the human-facing STOP evidence). The dedup is load-bearing ONLY under the
# ancestry audit (multiple live refs) — the same ancestry code with the seen_slice dedup
# removed emits TWO identical slice:s1 objects on this fixture, so the exact-1 assertions
# below flip (2 -> 1) against a no-dedup regression. (Two live refs sharing the slice are a
# precondition, asserted via the pair of phaseInt branches the fixture builds.)
read -r repo rd < <(mk_audit_multi_live)
run_conf "$repo" "$rd" --mode audit;                assert_rc "CK6 slice merged into two live refs -> exit 1" 1 "$RC"
assert_out_count "CK6 shared slice flagged once (deduped across live refs)" 'slice:s1' 1
assert_out_count "CK6 exactly one violation object (no-dedup regression would emit 2)" '"reason":"no-review"' 1

echo "=== SL: --mode state-lint (routing-field validator; the ONLY mode that reads state.json) ==="
# Regression-guard validity: every SL case expecting exit 0/1 FAILS against the pre-change
# script — `--mode state-lint` did not exist (usage exit 2).
read -r repo rd < <(mk_state_lint clean)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL well-formed executing state.json clean" 0 "$RC"
assert_out_contains "SL clean envelope" '"clean":true,"mode":"state-lint"'
# stage-aware: a premises run with empty phaseList + empty slices is well-formed-empty.
read -r repo rd < <(mk_state_lint early_clean)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL early (stage=premises) empty phaseList clean" 0 "$RC"
# corrupt state.json is a VERDICT (exit 1 unparseable-state), NOT a usage error (exit 2).
read -r repo rd < <(mk_state_lint unparseable)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL corrupt state.json -> exit 1 (verdict, not usage)" 1 "$RC"
assert_out_contains "SL unparseable-state violation" '"reason":"unparseable-state"'
# the strengthened (meaningful-routability) checks bite, not just bare types:
# phaseList:[] WHILE executing is unroutable -> fail.
read -r repo rd < <(mk_state_lint phaselist_empty_executing)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL phaseList:[] while executing -> exit 1" 1 "$RC"
assert_out_contains "SL phaselist-malformed violation" '"reason":"phaselist-malformed"'
# an out-of-enum slice step is unroutable -> slice-routing-malformed (scoped to the slice id).
read -r repo rd < <(mk_state_lint step_bogus)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL step:\"bogus\" -> exit 1" 1 "$RC"
assert_out_contains "SL slice-routing-malformed scoped to the slice id" '{"scope":"1.1","reason":"slice-routing-malformed"'
# empty owns is unroutable -> slice-routing-malformed.
read -r repo rd < <(mk_state_lint owns_empty)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL empty owns -> exit 1" 1 "$RC"
assert_out_contains "SL empty-owns slice-routing-malformed" '"reason":"slice-routing-malformed"'
# a non-object slice VALUE (scalar) must emit a NAMED violation, not crash jq (exit 5).
read -r repo rd < <(mk_state_lint slice_scalar)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL non-object slice value -> exit 1 (not a jq crash)" 1 "$RC"
assert_out_contains "SL non-object slice value slice-routing-malformed scoped to id" '{"scope":"1.1","reason":"slice-routing-malformed"'
# a non-object .slices CONTAINER (array) while executing must NOT false-clean -> slices-malformed.
read -r repo rd < <(mk_state_lint slices_array)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL non-object .slices container -> exit 1" 1 "$RC"
assert_out_contains "SL non-object .slices container slices-malformed" '{"scope":"slices","reason":"slices-malformed"'
# stage-aware: an EMPTY slices object ({}) is legitimate mid-design -> must PASS even at execute.
read -r repo rd < <(mk_state_lint slices_empty_executing)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL empty slices {} at execute (pre-design) clean" 0 "$RC"
assert_out_contains "SL empty slices {} clean envelope" '"clean":true,"mode":"state-lint"'
# malformed verify -> verify-malformed.
read -r repo rd < <(mk_state_lint verify_bad)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL malformed verify -> exit 1" 1 "$RC"
assert_out_contains "SL verify-malformed violation" '"reason":"verify-malformed"'
# ship missing a required key -> ship-malformed.
read -r repo rd < <(mk_state_lint ship_bad)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL ship missing prUrl key -> exit 1" 1 "$RC"
assert_out_contains "SL ship-malformed violation" '"reason":"ship-malformed"'
# cardinality (D44): TWO malformed slices -> TWO slice-routing-malformed objects.
read -r repo rd < <(mk_state_lint multi_bad_slice)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL two malformed slices -> exit 1" 1 "$RC"
assert_out_count "SL one slice-routing-malformed object PER malformed slice (D44)" '"reason":"slice-routing-malformed"' 2
# P1-A: a parseable-but-non-object ROOT (JSON array / scalar) must NOT crash jq (exit 5,
# no envelope) — it is unparseable-state (exit 1). NEVER-crashes invariant at the root.
read -r repo rd < <(mk_state_lint toplevel_array)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL top-level array root -> exit 1 (not a jq crash 5)" 1 "$RC"
assert_out_contains "SL top-level array root -> unparseable-state" '"reason":"unparseable-state"'
assert_out_contains "SL top-level array root still emits the envelope" '"mode":"state-lint"'
read -r repo rd < <(mk_state_lint toplevel_scalar)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL top-level scalar root -> exit 1 (not a jq crash 5)" 1 "$RC"
assert_out_contains "SL top-level scalar root -> unparseable-state" '"reason":"unparseable-state"'
# P1-B: stage itself must be in the real enum — an out-of-enum stage is unroutable.
read -r repo rd < <(mk_state_lint stage_bogus)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL stage:\"bogus\" -> exit 1" 1 "$RC"
assert_out_contains "SL out-of-enum stage -> stage-malformed" '{"scope":"stage","reason":"stage-malformed"'
read -r repo rd < <(mk_state_lint stage_done_clean)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL stage:\"done\" (real stage) clean" 0 "$RC"
assert_out_contains "SL real stage clean envelope" '"clean":true,"mode":"state-lint"'
# AC38 (AC26): stage=="finalize" (Stage 4c) is in the real enum -> clean (no stage-malformed).
# Regression validity: pre-Phase-2 the enum lacked `finalize`, so this would have hit
# stage-malformed (exit 1); the clean assertion flips with the enum add.
read -r repo rd < <(mk_state_lint stage_finalize_clean)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "AC38 stage:\"finalize\" (Stage 4c) clean" 0 "$RC"
assert_out_contains "AC38 finalize-stage clean envelope" '"clean":true,"mode":"state-lint"'
# P1-C: phaseList element must be a REF-SAFE phase id — a value with spaces forms an
# invalid phaseInt/<runId>/<P> ref.
read -r repo rd < <(mk_state_lint phaselist_badref)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL phaseList element \"bad ref name\" -> exit 1" 1 "$RC"
assert_out_contains "SL non-ref-safe phaseList element -> phaselist-malformed" '"reason":"phaselist-malformed"'
read -r repo rd < <(mk_state_lint phaselist_epoch_clean)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL phaseList epoch id \"4a\" (ref-safe) clean" 0 "$RC"
assert_out_contains "SL ref-safe epoch phase id clean envelope" '"clean":true,"mode":"state-lint"'
# P1-C: slice-id KEY must be ref-safe — a key with a space forms an invalid slice/<runId>/<id>
# ref; scoped to the offending key.
read -r repo rd < <(mk_state_lint slice_key_badref)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL slice key \"1 bad\" -> exit 1" 1 "$RC"
assert_out_contains "SL non-ref-safe slice key -> slice-routing-malformed scoped to key" '{"scope":"1 bad","reason":"slice-routing-malformed"'
# A slice-id KEY carrying a JSON metachar (`"`) is corruption-controlled and flows into the
# violation `scope`: violation() must JSON-ESCAPE it so the envelope stays VALID JSON (the
# old printf path emitted a syntactically-broken envelope -> downstream jq parse breaks).
read -r repo rd < <(mk_state_lint slice_key_metachar)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL slice key with \" metachar -> exit 1" 1 "$RC"
assert_valid_json "SL metachar slice key -> envelope is still VALID JSON (violation() escapes scope)"
assert_out_contains "SL metachar slice key still fires slice-routing-malformed" '"reason":"slice-routing-malformed"'
# deps elements must be slice-id strings (D-deps): a non-string (42) or non-grammar ("1 bad")
# element is unroutable — /drive dispatches on CONVERGED deps to look up sibling slices.
read -r repo rd < <(mk_state_lint deps_nonstring)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL deps:[42] (non-string) -> exit 1" 1 "$RC"
assert_out_contains "SL non-string deps elem -> slice-routing-malformed scoped to slice" '{"scope":"1.1","reason":"slice-routing-malformed"'
read -r repo rd < <(mk_state_lint deps_badref)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL deps:[\"1 bad\"] (non-grammar) -> exit 1" 1 "$RC"
assert_out_contains "SL non-grammar deps elem -> slice-routing-malformed scoped to slice" '{"scope":"1.1","reason":"slice-routing-malformed"'
read -r repo rd < <(mk_state_lint deps_clean)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL valid deps [\"1.1\"] still clean (no over-rejection)" 0 "$RC"
assert_out_contains "SL valid deps clean envelope" '"clean":true,"mode":"state-lint"'
# P1-final: an EMPTY-STRING slice-id KEY ("") is unroutable but jq emits an empty token for
# it — the OLD newline-split loop did `[ -n "$sid" ] || continue` and DROPPED it (false-clean).
# The NUL-delimited loop must fire slice-routing-malformed instead of silently passing.
read -r repo rd < <(mk_state_lint slice_key_empty)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL empty-string slice key -> exit 1 (not false-clean)" 1 "$RC"
assert_valid_json "SL empty-string slice key -> envelope is still VALID JSON"
assert_out_contains "SL empty-string slice key fires slice-routing-malformed" '"reason":"slice-routing-malformed"'
# A slice-id KEY containing a NEWLINE must be consumed losslessly (NUL-delimited) — a
# newline-split loop would shred it; exactly one slice-routing-malformed fires.
read -r repo rd < <(mk_state_lint slice_key_newline)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL newline slice key -> exit 1" 1 "$RC"
assert_valid_json "SL newline slice key -> envelope is still VALID JSON"
assert_out_count "SL newline slice key -> exactly one slice-routing-malformed (no shredding)" '"reason":"slice-routing-malformed"' 1
# `waiting` validation: resume AND the stop hook BRANCH on this field, so a malformed value
# misroutes both -> it must fail closed. Canonical shape: null / gateA / gateB / rebirth /
# stop:<short> / ask:<header>. A non-null-non-string OR an off-grammar string is malformed.
read -r repo rd < <(mk_state_lint waiting_bad_type)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL waiting:42 (non-string) -> exit 1" 1 "$RC"
assert_out_contains "SL non-string waiting -> waiting-malformed" '{"scope":"waiting","reason":"waiting-malformed"'
read -r repo rd < <(mk_state_lint waiting_bad_string)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL waiting:\"frobnicate\" (off-grammar) -> exit 1" 1 "$RC"
assert_out_contains "SL off-grammar waiting string -> waiting-malformed" '{"scope":"waiting","reason":"waiting-malformed"'
# The rebirth-CONTINUE value (and other valid shapes) must NOT be over-rejected.
read -r repo rd < <(mk_state_lint waiting_rebirth_clean)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL waiting:\"rebirth\" (the continue value) clean" 0 "$RC"
assert_out_contains "SL rebirth waiting clean envelope" '"clean":true,"mode":"state-lint"'
read -r repo rd < <(mk_state_lint waiting_stop_clean)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL waiting:\"stop:...\" (prefixed reason) clean" 0 "$RC"
assert_out_contains "SL stop: waiting clean envelope" '"clean":true,"mode":"state-lint"'
read -r repo rd < <(mk_state_lint waiting_null_clean)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL waiting:null (explicit) clean" 0 "$RC"
assert_out_contains "SL explicit-null waiting clean envelope" '"clean":true,"mode":"state-lint"'
# missing state.json (no file, but drive/<runId> resolves) -> exit 2 (IO error, not a verdict).
read -r repo rd < <(mk_state_lint no_state)
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL absent state.json -> exit 2 (IO error)" 2 "$RC"

echo "=== SL/CK4: checkpoint is UNCHANGED — a state-lint FAILURE still passes checkpoint ==="
# A state.json that FAILS state-lint (phaseList:[] while executing) must still PASS
# --mode checkpoint on a quiescent fixture: the two modes are independent (D8 — checkpoint
# never reads state.json). Reuse the quiescent checkpoint `clean` fixture (its state.json is
# corrupt garbage) and confirm checkpoint clean while state-lint fails on the same dir.
read -r repo rd < <(mk_checkpoint clean slck4-ckpt)
run_conf "$repo" "$rd" --mode checkpoint;           assert_rc "SL/CK4 checkpoint clean despite a state-lint-failing state.json" 0 "$RC"
run_conf "$repo" "$rd" --mode state-lint;           assert_rc "SL/CK4 the SAME dir's corrupt state.json FAILS state-lint" 1 "$RC"
assert_out_contains "SL/CK4 corrupt state.json -> unparseable-state" '"reason":"unparseable-state"'

echo
echo "=== usage/error guards ==="
OUT="$("$CONF" 2>/dev/null)"; RC=$?;                 assert_rc "no args -> usage exit 2" 2 "$RC"
OUT="$("$CONF" /nonexistent/dir --mode ship 2>/dev/null)"; RC=$?
assert_rc "absent RUN_DIR -> exit 2" 2 "$RC"
OUT="$("$CONF" "$ROOT" --mode bogus 2>/dev/null)"; RC=$?
assert_rc "bogus mode -> exit 2" 2 "$RC"

echo
echo "===================================="
echo "PASS=$PASS  FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
