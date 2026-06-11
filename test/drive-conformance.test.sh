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

# Assert $OUT contains needle EXACTLY $3 times. $1=desc $2=needle $3=expected-count
assert_out_count() {
  local n; n="$(printf '%s' "$OUT" | grep -o -- "$2" | wc -l | tr -d ' ')"
  if [ "$n" = "$3" ]; then
    echo "PASS: $1"; PASS=$((PASS+1))
  else
    echo "FAIL: $1 (expected $3 '$2', got $n) :: ${OUT:-}"; FAIL=$((FAIL+1))
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
read -r repo rd < <(mk_ship clean)
run_conf "$repo" "$rd" --mode ship;                 assert_rc "AC4.i ship ledger-only clean" 0 "$RC"
read -r repo rd < <(mk_ship code_past_r)
run_conf "$repo" "$rd" --mode ship;                 assert_rc "AC4.ii ship code past R blocked" 1 "$RC"
read -r repo rd < <(mk_ship other_harness_past_r)
run_conf "$repo" "$rd" --mode ship;                 assert_rc "AC4.iii(tight) ship other .harness file blocked" 1 "$RC"
read -r repo rd < <(mk_ship two_ledger_commits)
run_conf "$repo" "$rd" --mode ship;                 assert_rc "AC4.iv(≤1) ship two ledger commits blocked" 1 "$RC"

echo "=== AC4b: multi-phase existential R (no highest-N false-block) ==="
read -r repo rd < <(mk_ship_multiphase)
run_conf "$repo" "$rd" --mode ship;                 assert_rc "AC4b multi-phase existential picks phase2 R (clean)" 0 "$RC"

echo "=== AC4c: HARDEN->advance consumes post-harden review ==="
read -r repo rd < <(mk_phase_harden post_harden_ok 1)
run_conf "$repo" "$rd" --mode phase-merge:1;        assert_rc "AC4c phase-merge post-harden review matches tip" 0 "$RC"
read -r repo rd < <(mk_phase_harden stale_only 1)
run_conf "$repo" "$rd" --mode phase-merge:1;        assert_rc "AC4c phase-merge stale-only review blocked" 1 "$RC"

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
read -r repo rd < <(mk_ship_git_error)
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
# All five I3 rules in one assertion: reviewCount from pure-integer-N counts (the
# review-1.1-final.md non-round file does NOT count); phaseReviewRound = 3 review-phase1
# files MINUS the 1 AppliedEdits:yes regress marker (regress files don't overcount the
# round); hardenRound counts ONLY yes (one yes + one no -> 1); phaseDesignRound epoch-0.
assert_out_contains "CK1 counters per I3" \
  '"counters":{"redesigns":{},"phaseDesignRound":{"1":1},"phaseReviewRound":{"1":2},"hardenRound":{"1":1},"reviewCount":{"1.1":2}}'

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
