#!/usr/bin/env bash
# Plain-bash test runner for bin/drive-conformance.sh.
# Asserts acceptance criteria 0,1,2,3,4,4b,4c,5,10 and Item-C C1..C4b. Prints PASS/FAIL per case and
# exits nonzero if any fail. Builds hermetic throwaway repos via test/fixtures/mkfixture.sh.
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

echo "=== AC0: plan-gate (design review omission-proof) ==="
read -r repo rd < <(mk_plan clean)
run_conf "$repo" "$rd" --mode plan-gate;            assert_rc "AC0 plan-gate clean" 0 "$RC"
read -r repo rd < <(mk_plan nodesign)
run_conf "$repo" "$rd" --mode plan-gate;            assert_rc "AC0 plan-gate no design review" 1 "$RC"
read -r repo rd < <(mk_plan nocodex)
run_conf "$repo" "$rd" --mode plan-gate;            assert_rc "AC0 plan-gate no codex" 1 "$RC"
read -r repo rd < <(mk_plan findings)
run_conf "$repo" "$rd" --mode plan-gate;            assert_rc "AC0 plan-gate highest-N FINDINGS" 1 "$RC"

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

echo "=== AC3: codex marker behavioral — anchored token vs buried substring vs empty ==="
# Anchored first-line CODEX_UNAVAILABLE = degraded-but-satisfied -> clean.
read -r repo rd < <(mk_plan codex_unavailable)
run_conf "$repo" "$rd" --mode plan-gate;            assert_rc "AC3 anchored CODEX_UNAVAILABLE satisfies codex" 0 "$RC"
# A real review whose body merely buries the substring = non-empty real review -> clean.
read -r repo rd < <(mk_plan codex_buried)
run_conf "$repo" "$rd" --mode plan-gate;            assert_rc "AC3 buried substring still a real present codex file (clean)" 0 "$RC"
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
# usage guard: empty id after impl-presence: -> exit 2
read -r repo rd < <(mk_impl_presence test impl-empty-id)
OUT="$(cd "$repo" && "$CONF" "$rd" --mode "impl-presence:" 2>/dev/null)"; RC=$?
assert_rc "AC-C empty impl-presence id -> exit 2" 2 "$RC"

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
