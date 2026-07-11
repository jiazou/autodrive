#!/usr/bin/env bash
# Plain-bash test suite for bin/drive-ci-wait.sh — the post-push CI gate for /drive-ship.
# Dep-independent of real `gh`: every case injects a fake via DRIVE_CI_WAIT_GH (a JSON-emitting shim),
# so the exit-code contract is exercised offline. Sub-second poll/grace/max drive it by count.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SUT="$ROOT/bin/drive-ci-wait.sh"
PASS=0; FAIL=0
WORK="$(mktemp -d "${TMPDIR:-/tmp}/drive-ci-wait-test.XXXXXX")"
trap 'rm -rf "$WORK" 2>/dev/null' EXIT
pass() { PASS=$((PASS+1)); printf 'PASS: %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf 'FAIL: %s\n' "$1"; }
ck()   { if [ "$2" = "$3" ]; then pass "$1"; else fail "$1 (want [$3] got [$2])"; fi; }
BIN="$WORK/bin"; mkdir -p "$BIN"
mkgh() { local n="$1"; shift; printf '%s\n' "$@" > "$BIN/$n"; chmod +x "$BIN/$n"; }

# workflow-present vs -absent repo roots (the 0-checks disambiguator)
WF="$WORK/wf"; mkdir -p "$WF/.github/workflows"; echo "on: push" > "$WF/.github/workflows/t.yml"
NWF="$WORK/nowf"; mkdir -p "$NWF"

run() { OUT="$(DRIVE_CI_WAIT_GH="$BIN/$1" "$SUT" --pr 1 --repo-root "$2" --poll-secs 0 --grace-secs 0 --max-secs 1 ${3:-} 2>&1)"; RC=$?; }

# --- static/arg guards ---
OUT="$("$SUT" --repo-root "$WF" 2>&1)"; ck "missing --pr ⇒ exit 2" "$?" "2"
OUT="$(DRIVE_CI_WAIT_GH=/nonexistent-gh-xyz "$SUT" --pr 1 --repo-root "$WF" 2>&1)"; ck "gh absent ⇒ exit 2 (best-effort proceed)" "$?" "2"
OUT="$(DRIVE_CI_WAIT_GH="$BIN/gh_green" "$SUT" --pr 1 --repo-root "$WF" --max-secs abc 2>&1)"; # need gh_green first
mkgh gh_green '#!/usr/bin/env bash' 'echo '\''[{"name":"a","bucket":"pass","state":"SUCCESS","link":""}]'\'''
OUT="$(DRIVE_CI_WAIT_GH="$BIN/gh_green" "$SUT" --pr 1 --repo-root "$WF" --max-secs abc 2>&1)"; ck "bad --max-secs ⇒ exit 2" "$?" "2"

# --- terminal states ---
mkgh gh_red '#!/usr/bin/env bash' 'echo '\''[{"name":"bash-suite","bucket":"fail","state":"FAILURE","link":"http://x/1"},{"name":"pytest","bucket":"pass","state":"SUCCESS","link":""}]'\'''
run gh_red "$WF"; ck "RED (a fail bucket) ⇒ exit 1" "$RC" "1"
case "$OUT" in *"bash-suite"*) pass "RED lists the failing check name";; *) fail "RED omits failing check ($OUT)";; esac
case "$OUT" in *"pytest"*) fail "RED wrongly lists the passing check";; *) pass "RED omits the passing check";; esac

run gh_green "$WF"; ck "GREEN (all pass) ⇒ exit 0" "$RC" "0"

# cancelled/skipped only (no fail, no pending) ⇒ non-red ⇒ 0
mkgh gh_skip '#!/usr/bin/env bash' 'echo '\''[{"name":"opt","bucket":"skipping","state":"SKIPPED","link":""},{"name":"c","bucket":"cancel","state":"CANCELLED","link":""}]'\'''
run gh_skip "$WF"; ck "all skipped/cancelled (none fail/pending) ⇒ exit 0 (non-red)" "$RC" "0"

# --- the P1 registration race: 0 checks must NEVER vacuously pass ---
mkgh gh_empty '#!/usr/bin/env bash' 'echo "[]"'
run gh_empty "$WF"; ck "0 checks + workflows PRESENT ⇒ exit 3 (PENDING, never proceed)" "$RC" "3"
run gh_empty "$NWF"; ck "0 checks + NO workflows ⇒ exit 2 (genuine no-CI, proceed)" "$RC" "2"
# empty STDOUT (gh error / no checks) behaves like []
mkgh gh_blank '#!/usr/bin/env bash' 'exit 1'
run gh_blank "$WF"; ck "blank gh output + workflows ⇒ exit 3 (not a false proceed)" "$RC" "3"

# --- pending → terminal (counter-driven fake; needs >0 poll to iterate) ---
CNT="$WORK/cnt"; : > "$CNT"
mkgh gh_pend_then_green '#!/usr/bin/env bash' \
  'n=$(cat "$CNT" 2>/dev/null||echo 0); n=$((n+1)); echo "$n">"$CNT"' \
  'if [ "$n" -lt 2 ]; then echo '\''[{"name":"a","bucket":"pending","state":"IN_PROGRESS","link":""}]'\''; else echo '\''[{"name":"a","bucket":"pass","state":"SUCCESS","link":""}]'\''; fi'
: > "$CNT"; OUT="$(CNT="$CNT" DRIVE_CI_WAIT_GH="$BIN/gh_pend_then_green" "$SUT" --pr 1 --repo-root "$WF" --poll-secs 0 --grace-secs 0 --max-secs 5 2>&1)"; ck "pending→green ⇒ exit 0 (polls to conclusion)" "$?" "0"

CNT2="$WORK/cnt2"; : > "$CNT2"
mkgh gh_pend_then_red '#!/usr/bin/env bash' \
  'n=$(cat "$CNT" 2>/dev/null||echo 0); n=$((n+1)); echo "$n">"$CNT"' \
  'if [ "$n" -lt 2 ]; then echo '\''[{"name":"a","bucket":"pending","state":"IN_PROGRESS","link":""}]'\''; else echo '\''[{"name":"a","bucket":"fail","state":"FAILURE","link":"http://x"}]'\''; fi'
OUT="$(CNT="$CNT2" DRIVE_CI_WAIT_GH="$BIN/gh_pend_then_red" "$SUT" --pr 1 --repo-root "$WF" --poll-secs 0 --grace-secs 0 --max-secs 5 2>&1)"; ck "pending→red ⇒ exit 1" "$?" "1"

# pending forever ⇒ hits max ⇒ exit 3
mkgh gh_pending '#!/usr/bin/env bash' 'echo '\''[{"name":"a","bucket":"pending","state":"QUEUED","link":""}]'\'''
OUT="$(DRIVE_CI_WAIT_GH="$BIN/gh_pending" "$SUT" --pr 1 --repo-root "$WF" --poll-secs 0 --grace-secs 0 --max-secs 1 2>&1)"; ck "pending past max ⇒ exit 3 (PENDING pause)" "$?" "3"

# --- FAIL-CLOSED (positive green-allowlist): a MISSING/unknown bucket must NEVER default to GREEN ---
# a failing check with NO bucket field (state only) ⇒ RED via state fallback (not a false GREEN).
mkgh gh_nobucket_fail '#!/usr/bin/env bash' 'echo '\''[{"name":"unit","state":"FAILURE","link":"http://x"}]'\'''
run gh_nobucket_fail "$WF"; ck "missing bucket + state FAILURE ⇒ exit 1 RED (no fail-open GREEN)" "$RC" "1"
# an in-progress check with NO bucket ⇒ UNKNOWN/pending ⇒ NOT green ⇒ exit 3 at max (never 0).
mkgh gh_nobucket_run '#!/usr/bin/env bash' 'echo '\''[{"name":"unit","state":"IN_PROGRESS","link":""}]'\'''
run gh_nobucket_run "$WF"; ck "missing bucket + state IN_PROGRESS ⇒ exit 3 (unknown≠green, fail-closed)" "$RC" "3"
# a passing check via STATE only (no bucket) ⇒ recognized-ok ⇒ GREEN.
mkgh gh_nobucket_pass '#!/usr/bin/env bash' 'echo '\''[{"name":"unit","state":"SUCCESS","link":""}]'\'''
run gh_nobucket_pass "$WF"; ck "missing bucket + state SUCCESS ⇒ exit 0 GREEN (state fallback)" "$RC" "0"
# a non-array JSON object (gh error / truncated) ⇒ NOT a pass ⇒ exit 3 at max (never GREEN/proceed).
mkgh gh_notarray '#!/usr/bin/env bash' 'echo '\''{"message":"Not Found"}'\'''
run gh_notarray "$WF"; ck "non-array JSON (gh error obj) ⇒ exit 3 (not a false GREEN)" "$RC" "3"
# an UNRECOGNIZED bucket AND unrecognized state (a future gh vocabulary) ⇒ unknown ⇒ NOT green.
mkgh gh_unknown '#!/usr/bin/env bash' 'echo '\''[{"name":"unit","bucket":"wat","state":"HUH"}]'\'''
run gh_unknown "$WF"; ck "unknown bucket+state ⇒ exit 3 (fail-closed, not GREEN)" "$RC" "3"
# mixed: one pass + one failing-by-state ⇒ RED (a real fail is never masked by a sibling pass).
mkgh gh_mixed '#!/usr/bin/env bash' 'echo '\''[{"name":"a","bucket":"pass","state":"SUCCESS"},{"name":"b","state":"TIMED_OUT"}]'\'''
run gh_mixed "$WF"; ck "one pass + one state-TIMED_OUT ⇒ exit 1 RED" "$RC" "1"

echo ""
echo "===================================================================="
printf 'drive-ci-wait.test.sh: %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
