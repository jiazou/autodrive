#!/usr/bin/env bash
# Mutation-verify for tests/contracts/test_drive_ship_gatea_precondition.py (RL-1).
# Proves the load-bearing pins are NON-VACUOUS: each CONCRETE bypass mutation of
# drive-ship.md precondition #1 MUST red the matching contract test. Without this, a future
# edit could re-vacuous the pins (an AND->OR or a widened stage set) and stay green — the
# exact defect codex caught on the first cut of this pin. Executed, both directions
# (baseline GREEN + each mutation RED).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SHIP="$ROOT/.claude/commands/drive-ship.md"
TESTFILE="tests/contracts/test_drive_ship_gatea_precondition.py"
PY="$(command -v python3 || command -v python || true)"
PASS=0; FAIL=0
WORK="$(mktemp -d "${TMPDIR:-/tmp}/drive-ship-gatea.XXXXXX")"
trap 'rm -rf "$WORK" 2>/dev/null' EXIT
pass() { PASS=$((PASS+1)); printf 'PASS: %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf 'FAIL: %s\n' "$1"; }

# pytest is required to run the pins; without it the mutation-verify cannot execute. Skip
# gracefully (the pytest phase of the suite is likewise absent) rather than false-fail.
if [ -z "$PY" ] || ! "$PY" -m pytest --version >/dev/null 2>&1; then
  echo "SKIP: pytest unavailable — RL-1 pin non-vacuity unverified in this env"
  echo "drive-ship-gatea-mutation.test.sh: 0 passed, 0 failed (skipped)"
  exit 0
fi

# run the named -k subset against an OVERRIDE drive-ship.md; echo red (failed) | green (passed)
run_k() { # $1=override-md  $2=-k expr
  if ( cd "$ROOT" && DRIVE_SHIP_MD_OVERRIDE="$1" "$PY" -m pytest "$TESTFILE" -k "$2" -q \
        >/dev/null 2>&1 ); then echo green; else echo red; fi
}

# 0) baseline — the unmutated precondition #1 is GREEN for the whole module
[ "$(run_k "$SHIP" gatea)" = green ] \
  && pass "baseline: unmutated precondition #1 GREEN" \
  || fail "baseline: unmutated precondition #1 must be GREEN (env/pattern problem)"

# 1) AND -> OR on clause (a): {phaseList:[], stage:execute} would bypass — MUST red the conjunction pin
M1="$WORK/and-to-or.md"
sed 's/NON-EMPTY \*\*and\*\* `state.stage`/NON-EMPTY **or** `state.stage`/' "$SHIP" > "$M1"
if cmp -s "$SHIP" "$M1"; then
  fail "AND->OR sed did not change the file (pattern drift — conjunction pin unverifiable)"
else
  [ "$(run_k "$M1" conjunction)" = red ] \
    && pass "AND->OR bypass mutation REDs the conjunction pin" \
    || fail "AND->OR bypass mutation did NOT red the conjunction pin (VACUOUS)"
fi

# 2) widen the allowed stage set (+`plan`): accepts a pre-approval run — MUST red the exact-set pin
M2="$WORK/plus-plan.md"
sed 's/`verify`, `ship`}/`verify`, `ship`, `plan`}/' "$SHIP" > "$M2"
if cmp -s "$SHIP" "$M2"; then
  fail "stage-set sed did not change the file (pattern drift — exact-set pin unverifiable)"
else
  [ "$(run_k "$M2" exact_allowed_stage_set)" = red ] \
    && pass "stage-set widening (+plan) REDs the exact-set pin" \
    || fail "stage-set widening (+plan) did NOT red the exact-set pin (VACUOUS)"
fi

echo ""
echo "===================================================================="
printf 'drive-ship-gatea-mutation.test.sh: %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
