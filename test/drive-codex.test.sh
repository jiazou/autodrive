#!/usr/bin/env bash
# Plain-bash test runner for bin/drive-codex.sh — the supervised codex-dispatch helper.
#
# Dep-INDEPENDENT of the real codex CLI: every case injects a fake `DRIVE_CODEX_CMD` (a
# log-writing shim), so the closed contract is exercised without codex installed. Covers the
# helper's acceptance criteria: AC-H1..AC-H23 (incl. AC-H12b/AC-H12c behavioral halves) and the
# helper halves of AC-P1/AC-P4. Prints PASS/FAIL per case; exits nonzero if any fail.
#
# Determinism: sub-second --stall-secs/--backstop-secs + a small --poll-secs drive the watchdog by
# poll count (awk float math), not wall clock. `set -m` group kills reap forked children. A fake
# that TRAPS SIGTERM and exits 0 models a codex self-exit in the kill window (kill_confirmed=0).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
HELPER="$ROOT/bin/drive-codex.sh"

PASS=0; FAIL=0
WORK="$(mktemp -d "${TMPDIR:-/tmp}/drive-codex-test.XXXXXX")"
trap 'rm -rf "$WORK" 2>/dev/null' EXIT

pass() { PASS=$((PASS + 1)); printf 'PASS: %s\n' "$1"; }
fail() { FAIL=$((FAIL + 1)); printf 'FAIL: %s\n' "$1"; }
check() { if [ "$2" = "$3" ]; then pass "$1"; else fail "$1 (want [$3] got [$2])"; fi; }
check_contains() { case "$2" in *"$3"*) pass "$1";; *) fail "$1 (missing [$3] in [$2])";; esac; }
check_absent() { case "$2" in *"$3"*) fail "$1 (unexpected [$3] in [$2])";; *) pass "$1";; esac; }

# ---- fake codex shims (written once; selected per case via DRIVE_CODEX_CMD) ----
BIN="$WORK/bin"; mkdir -p "$BIN"

mkfake() { local name="$1"; shift; printf '%s\n' "$@" > "$BIN/$name"; chmod +x "$BIN/$name"; }

# doctor OK; exec streams then exits 0 (⇒ OK)
mkfake fake_ok \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo "{\"ok\":true}"; exit 0 ;; esac' \
  'printf "reviewing\n"; sleep 0.1; printf "MINOR: nit\ndone\n"; exit 0'

# doctor OK; exec echoes then goes byte-silent forever (⇒ stall). Default TERM disposition ⇒ killed.
mkfake fake_stall \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  'printf "begin\n"; sleep 60'

# doctor OK; exec echoes, then goes silent to ARM the watchdog, but TRAPS TERM and exits 0 (⇒
# self-exit in the kill window ⇒ kill_confirmed=0 ⇒ OK, per AC-H17 / D-71).
mkfake fake_selfexit_race \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  'trap "exit 0" TERM' \
  'printf "started-review\n"; sleep 60'

# doctor OK; exec streams continuously (never silent), so STALL never fires but backstop does.
mkfake fake_stream_forever \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  'i=0; while :; do printf "line %s\n" "$i"; i=$((i+1)); sleep 0.03; done'

# doctor OK; exec exits NONZERO with empty log (⇒ CODEX_UNAVAILABLE exec-failed when never killed).
mkfake fake_execfail \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  'exit 3'

# doctor FAILS (outage). exec would stream OK if ever reached.
mkfake fake_probe_outage \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) exit 1 ;; esac' \
  'printf "reviewed\nok\n"; exit 0'

# doctor HANGS + FORKS a child that would touch $SURVIVOR after 30s (⇒ hung-probe; no child survives).
mkfake fake_probe_hang \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) ( sleep 30; touch "$SURVIVOR" ) & sleep 30; exit 0 ;; esac' \
  'printf "x\n"; exit 0'

# exec streams, FORKS a child that would touch $SURVIVOR after 30s, then sleeps (⇒ helper-death reaps it).
mkfake fake_forking_stream \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  '( sleep 30; touch "$SURVIVOR" ) &' \
  'printf "streaming\n"; sleep 60'

# logs its exec argv to $ARGVLOG (for sandbox/effort composition assertions); exec exits OK.
mkfake fake_argv \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  'echo "ARGV: $*" >> "$ARGVLOG"' \
  'printf "review\nok\n"; exit 0'

# exec writes to stdout AND emits trailing junk on stderr AFTER exiting-value (channel-sep test).
mkfake fake_trailing_stderr \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  'printf "the real review\nMINOR x\n"; echo "TRAILING STDERR NOISE" >&2; exit 0'

# counter-driven: stall on exec call 1, stream OK on call 2 (retry-success).
mkfake fake_stall_then_ok \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  'n=$(cat "$CNT" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > "$CNT"' \
  'if [ "$n" = 1 ]; then printf "start\n"; sleep 60; else printf "streamed ok\n"; exit 0; fi'

# counter-driven: stall on exec call 1, exec-FAIL (nonzero) on call 2 (killed-latch step-4 route).
mkfake fake_stall_then_execfail \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  'n=$(cat "$CNT" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > "$CNT"' \
  'if [ "$n" = 1 ]; then printf "start\n"; sleep 60; else printf ""; exit 5; fi'

# doctor OK on call 1 (step-1 probe), FAILS on call 2 (launch-gate); exec stalls on attempt 1.
mkfake fake_stall_then_probeoutage \
  '#!/usr/bin/env bash' \
  'if [ "$1" = doctor ]; then n=$(cat "$DCNT" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > "$DCNT"; [ "$n" = 1 ] && exit 0 || exit 1; fi' \
  'printf "start\n"; sleep 60'

PROMPT="$WORK/prompt.txt"; printf 'Review the scope.' > "$PROMPT"
ALOG="$WORK/codex-attempts-testrun.jsonl"

# Run dispatch. Sets RC + OUT (stdout) + ERR (stderr file). Args after the 3 fixed = extra flags.
# disp <fake> <scope> <scope-class> <marker> [extra flags...]
disp() {
  local fake="$1" scope="$2" cls="$3" marker="$4"; shift 4
  OUT="$(DRIVE_CODEX_CMD="$BIN/$fake" "$HELPER" --mode dispatch --scope "$scope" --scope-class "$cls" \
      --attempt-log "$ALOG" --raw-log "$WORK/codex-raw-$scope.log" --marker "$marker" \
      --prompt-file "$PROMPT" "$@" 2>"$WORK/err.$scope")"
  RC=$?
  ERR="$(cat "$WORK/err.$scope" 2>/dev/null)"
}

# ============================================================================= #
echo "=== AC-H1/H2: OK ⇒ token OK, exit 0, NO marker ==="
disp fake_ok okc slice "$WORK/codex-review-okc.md" --poll-secs 0.05
check "AC-H2 OK token" "$OUT" "OK"
check "AC-H2 OK exit 0" "$RC" "0"
if [ ! -f "$WORK/codex-review-okc.md" ]; then pass "AC-H2 OK ⇒ NO marker"; else fail "AC-H2 OK wrote a marker"; fi

echo "=== AC-H3: stall-kill + retry-success ⇒ OK; retry-also-stalls ⇒ KILLED(attempts=2) ==="
CNT="$WORK/cnt_h3"; : > "$CNT"
CNT="$CNT" disp fake_stall_then_ok h3ok slice "$WORK/codex-review-h3ok.md" --poll-secs 0.05 --stall-secs 0.2 --backstop-secs 100
check "AC-H3 retry-success token OK" "$OUT" "OK"
if [ -f "$WORK/codex-raw-h3ok.killed-1.log" ]; then pass "AC-H3 attempt-1 killed-log present"; else fail "AC-H3 killed-1 missing"; fi
if [ ! -f "$WORK/codex-review-h3ok.md" ]; then pass "AC-H3 retry-success ⇒ NO marker"; else fail "AC-H3 wrote a marker on OK"; fi
disp fake_stall h3kill slice "$WORK/codex-review-h3kill.md" --poll-secs 0.05 --stall-secs 0.2 --backstop-secs 100
check "AC-H3 retry-stall token KILLED" "$OUT" "CODEX_KILLED_TIMEOUT"
check "AC-H3 KILLED exit 1" "$RC" "1"
check "AC-H3 marker 1st line == token" "$(head -1 "$WORK/codex-review-h3kill.md")" "CODEX_KILLED_TIMEOUT"
check_contains "AC-H3 marker attempts=2" "$(cat "$WORK/codex-review-h3kill.md")" "attempts=2"
if [ -f "$WORK/codex-raw-h3kill.killed-1.log" ] && [ -f "$WORK/codex-raw-h3kill.killed-2.log" ]; then
  pass "AC-H3/H10 both killed-N.log present (\${raw%.log}.killed-N.log)"
else fail "AC-H3 expected both killed-1 and killed-2 logs"; fi

echo "=== AC-H4: backstop kill (streaming), cause=backstop, NO retry, ONE killed log ==="
disp fake_stream_forever h4 slice "$WORK/codex-review-h4.md" --poll-secs 0.03 --stall-secs 100 --backstop-secs 0.3
check "AC-H4 backstop token KILLED" "$OUT" "CODEX_KILLED_TIMEOUT"
check_contains "AC-H4 marker cause=backstop" "$(cat "$WORK/codex-review-h4.md")" "Codex killed (backstop)"
check_contains "AC-H4 marker attempts=1 (no retry)" "$(cat "$WORK/codex-review-h4.md")" "attempts=1"
if [ -f "$WORK/codex-raw-h4.killed-1.log" ] && [ ! -f "$WORK/codex-raw-h4.killed-2.log" ]; then
  pass "AC-H4 exactly one killed log (backstop = no retry)"; else fail "AC-H4 retry happened on backstop"; fi

echo "=== AC-H5/H6: a continuously-growing fake is NEVER stall-killed (positive-observation) ==="
# A streaming fake with a LARGE backstop and moderate stall: every poll sees growth ⇒ zero_polls
# resets ⇒ stall never fires ⇒ it must be killed only by backstop, never by stall. Here we give a
# generous stall AND backstop and cap the run: the fake self-terminates via a short total run.
mkfake fake_sawtooth \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  'for i in $(seq 1 12); do printf "b%s\n" "$i"; sleep 0.05; done; exit 0'
disp fake_sawtooth h5 slice "$WORK/codex-review-h5.md" --poll-secs 0.1 --stall-secs 0.5 --backstop-secs 100
check "AC-H5 sawtooth (byte every <stall) ⇒ OK, never killed" "$OUT" "OK"
if [ ! -f "$WORK/codex-raw-h5.killed-1.log" ]; then pass "AC-H6 no kill without positively-observed zero growth"; else fail "AC-H6 spurious kill on a growing log"; fi

echo "=== AC-H7: codex-absent (DRIVE_CODEX_CMD=/nonexistent) ⇒ CODEX_UNAVAILABLE(cli-absent) ==="
OUT="$(DRIVE_CODEX_CMD=/nonexistent-codex-xyz "$HELPER" --mode dispatch --scope h7 --scope-class slice \
   --attempt-log "$ALOG" --raw-log "$WORK/codex-raw-h7.log" --marker "$WORK/codex-review-h7.md" --prompt-file "$PROMPT" 2>/dev/null)"
RC=$?
check "AC-H7 cli-absent token" "$OUT" "CODEX_UNAVAILABLE"
check "AC-H7 cli-absent exit 1" "$RC" "1"
check_contains "AC-H7 marker cause cli-absent" "$(cat "$WORK/codex-review-h7.md")" "cli-absent"

echo "=== AC-H8: probe-outage per scope class ==="
# non-gate-enforced (slice, non-sensitive) ⇒ IMMEDIATE CODEX_UNAVAILABLE, exec never runs (no raw log).
disp fake_probe_outage h8ng slice "$WORK/codex-review-h8ng.md" --poll-secs 0.05 --probe-timeout-secs 1
check "AC-H8 non-gate-enforced probe-outage token" "$OUT" "CODEX_UNAVAILABLE"
check_contains "AC-H8 cause probed-outage" "$(cat "$WORK/codex-review-h8ng.md")" "probed-outage"
if [ ! -s "$WORK/codex-raw-h8ng.log" ]; then pass "AC-H8 non-gate-enforced ⇒ NO dispatch attempt (empty raw log)"; else fail "AC-H8 unexpected exec on non-gate-enforced outage"; fi
# gate-enforced (phase) ⇒ ONE bounded attempt runs; here that attempt streams OK ⇒ OK (proves it proceeded).
disp fake_probe_outage h8ge phase "$WORK/codex-review-h8ge.md" --poll-secs 0.05 --probe-timeout-secs 1
check "AC-H8 gate-enforced probe-outage ⇒ one attempt runs (OK)" "$OUT" "OK"

echo "=== AC-H9: killed marker byte-identity + mandated warning fields ==="
km="$WORK/codex-review-h3kill.md"
check_contains "AC-H9 warning threshold=" "$(cat "$km")" "threshold="
check_contains "AC-H9 warning killed_logs=" "$(cat "$km")" "killed_logs="
check_contains "AC-H9 warning attempt_log=" "$(cat "$km")" "attempt_log="
# NON-vacuous: assert EXACTLY zero lingering `.tmp.<pid>` files after the atomic tmp+mv write.
km_lingering=$(ls "$km".tmp.* 2>/dev/null | wc -l | tr -d ' ')
check "AC-H9 atomic write leaves NO lingering .tmp" "$km_lingering" "0"
check "AC-H9 marker exactly 2 lines" "$(wc -l < "$km" | tr -d ' ')" "2"

echo "=== AC-H10: fd-poll survives a mid-flight rename (then back) ⇒ still OK, no spurious kill ==="
mkfake fake_slowstream \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  'for i in $(seq 1 20); do printf "chunk%s\n" "$i"; sleep 0.05; done; exit 0'
( sleep 0.2; mv "$WORK/codex-raw-h10.log" "$WORK/codex-raw-h10.log.moved" 2>/dev/null
  sleep 0.3; mv "$WORK/codex-raw-h10.log.moved" "$WORK/codex-raw-h10.log" 2>/dev/null ) &
mvpid=$!
disp fake_slowstream h10 slice "$WORK/codex-review-h10.md" --poll-secs 0.05 --stall-secs 5 --backstop-secs 100
wait "$mvpid" 2>/dev/null
check "AC-H10 fd-poll survives mv-aside (OK, no spurious stall)" "$OUT" "OK"

echo "=== AC-H12/H12b/H12c: effort tiering ==="
mkclean() { printf 'Codex review\nLooks fine to me; nothing to change.\n' > "$1"; }  # non-degraded, ZERO severity tags
mkmajor() { printf 'Codex review\nMAJOR: a real bug at x.py:10\n' > "$1"; }  # a severity tag ⇒ full
mkdegraded() { printf 'CODEX_UNAVAILABLE\nnote\n' > "$1"; }
PRIOR_CLEAN="$WORK/codex-review-prior-clean.md"; mkclean "$PRIOR_CLEAN"
PRIOR_MAJOR="$WORK/codex-review-prior-major.md"; mkmajor "$PRIOR_MAJOR"
PRIOR_DEGR="$WORK/codex-review-prior-degr.md"; mkdegraded "$PRIOR_DEGR"

: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" disp fake_argv e1 slice "$WORK/codex-review-e1.md" --poll-secs 0.05 --confirmation-class --prior-codex "$PRIOR_CLEAN"
check_contains "AC-H12 clean prior + confirmation ⇒ -c model_reasoning_effort" "$(cat "$WORK/argv.log")" "model_reasoning_effort=medium"
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" disp fake_argv e2 slice "$WORK/codex-review-e2.md" --poll-secs 0.05 --confirmation-class --prior-codex "$PRIOR_MAJOR"
check_absent "AC-H12 MAJOR-tagged prior ⇒ FULL (no -c)" "$(cat "$WORK/argv.log")" "model_reasoning_effort"
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" disp fake_argv e3 slice "$WORK/codex-review-e3.md" --poll-secs 0.05 --confirmation-class --prior-codex "$PRIOR_DEGR"
check_absent "AC-H12 degraded prior ⇒ FULL (no -c)" "$(cat "$WORK/argv.log")" "model_reasoning_effort"
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" disp fake_argv e4 slice "$WORK/codex-review-e4.md" --poll-secs 0.05 --confirmation-class --prior-codex "$PRIOR_CLEAN" --security-diff
check_absent "AC-H12 --security-diff carve-out ⇒ FULL (no -c)" "$(cat "$WORK/argv.log")" "model_reasoning_effort"
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" disp fake_argv e5 slice "$WORK/codex-review-e5.md" --poll-secs 0.05 --confirmation-class --prior-codex "$PRIOR_CLEAN" --no-tiering
check_absent "AC-H12 --no-tiering ⇒ FULL (no -c)" "$(cat "$WORK/argv.log")" "model_reasoning_effort"
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" DRIVE_CODEX_EFFORT_TIER=off disp fake_argv e5b slice "$WORK/codex-review-e5b.md" --poll-secs 0.05 --confirmation-class --prior-codex "$PRIOR_CLEAN"
check_absent "AC-H12 DRIVE_CODEX_EFFORT_TIER=off ⇒ FULL (no -c)" "$(cat "$WORK/argv.log")" "model_reasoning_effort"
# AC-H12b: the scan reads the EXACT --prior-codex path — an ABSENT path ⇒ full effort (proves it
# does not silently read some other file). A clean codex-harden-<P>.md prior ⇒ downgrade.
PRIOR_HARDEN="$WORK/codex-harden-2.md"; mkclean "$PRIOR_HARDEN"
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" disp fake_argv e6 phase "$WORK/codex-review-e6.md" --poll-secs 0.05 --confirmation-class --prior-codex "$PRIOR_HARDEN"
check_contains "AC-H12b clean codex-harden-<P>.md prior ⇒ downgrade" "$(cat "$WORK/argv.log")" "model_reasoning_effort=medium"
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" disp fake_argv e7 phase "$WORK/codex-review-e7.md" --poll-secs 0.05 --confirmation-class --prior-codex "$WORK/does-not-exist.md"
check_absent "AC-H12b absent --prior-codex path ⇒ FULL (reads the EXACT file)" "$(cat "$WORK/argv.log")" "model_reasoning_effort"
# AC-H12c behavioral half: NO --confirmation-class (the coordinator's re-dispatch path) ⇒ full effort.
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" disp fake_argv e8 slice "$WORK/codex-review-e8.md" --poll-secs 0.05 --prior-codex "$PRIOR_CLEAN"
check_absent "AC-H12c no --confirmation-class (re-dispatch) ⇒ FULL (no -c)" "$(cat "$WORK/argv.log")" "model_reasoning_effort"

echo "=== AC-H13: usage/exit-2 guard + charset + env hatches ==="
"$HELPER" --mode dispatch --scope h13 --scope-class slice --attempt-log "$ALOG" --bogus-flag 2>/dev/null; check "AC-H13 unknown flag ⇒ exit 2" "$?" "2"
"$HELPER" --mode dispatch --scope 2>/dev/null; check "AC-H13 valueless --scope ⇒ exit 2" "$?" "2"
"$HELPER" --mode dispatch --scope --attempt-log 2>/dev/null; check "AC-H13 flag-shaped value ⇒ exit 2" "$?" "2"
OUT="$("$HELPER" --mode dispatch --scope 'bad/scope' --scope-class slice --attempt-log "$ALOG" \
   --raw-log "$WORK/codex-raw-bad.log" --marker "$WORK/codex-review-bad.md" --prompt-file "$PROMPT" 2>/dev/null)"; RC=$?
check "AC-H13 charset-invalid --scope token" "$OUT" "HELPER_ERROR"
check "AC-H13 charset-invalid --scope exit 2" "$RC" "2"
if [ ! -f "$WORK/codex-review-bad.md" ]; then pass "AC-H13 charset-invalid ⇒ NO marker"; else fail "AC-H13 charset wrote a marker"; fi
# env hatch: DRIVE_CODEX_SANDBOX=off ⇒ NO --sandbox flag in the exec argv.
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" DRIVE_CODEX_SANDBOX=off disp fake_argv h13s slice "$WORK/codex-review-h13s.md" --poll-secs 0.05
check_absent "AC-H13 DRIVE_CODEX_SANDBOX=off ⇒ no --sandbox flag" "$(cat "$WORK/argv.log")" "--sandbox"

echo "=== AC-H14: attempt log — well-formed JSONL, closed op enum, effort+sandbox recorded ==="
python3 - "$ALOG" <<'PY'
import json, sys
ok_ops = {"probe","dispatch","kill","retry","degrade","helper_error"}
bad = 0; n = 0
with open(sys.argv[1]) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        n += 1
        try:
            o = json.loads(line)
        except Exception as e:
            print(f"  UNPARSEABLE line: {e}"); bad += 1; continue
        if o.get("op") not in ok_ops:
            print(f"  BAD op: {o.get('op')}"); bad += 1
        for k in ("ts","scope","op","effort","sandbox","stall_secs","backstop_secs"):
            if k not in o:
                print(f"  MISSING field {k}"); bad += 1
sys.exit(1 if (bad or n == 0) else 0)
PY
check "AC-H14 attempt log well-formed + closed op enum + fields" "$?" "0"

echo "=== AC-H15: channel separation — trailing stderr does NOT corrupt the stdout token file ==="
DRIVE_CODEX_CMD="$BIN/fake_trailing_stderr" "$HELPER" --mode dispatch --scope h15 --scope-class slice \
  --attempt-log "$ALOG" --raw-log "$WORK/codex-raw-h15.log" --marker "$WORK/codex-review-h15.md" \
  --prompt-file "$PROMPT" --poll-secs 0.05 > "$WORK/h15.out" 2> "$WORK/h15.err"
check "AC-H15 stdout file LAST line is exactly the token" "$(tail -1 "$WORK/h15.out")" "OK"
check "AC-H15 stdout file is token-ONLY (1 line)" "$(wc -l < "$WORK/h15.out" | tr -d ' ')" "1"
# the fake's own stderr is merged (2>&1) into the RAW LOG (codex's channel), NEVER the token file.
check_contains "AC-H15 codex-side noise lands in the raw log, not the token file" "$(cat "$WORK/codex-raw-h15.log")" "TRAILING STDERR NOISE"
check_absent "AC-H15 the token file is uncorrupted by codex-side noise" "$(cat "$WORK/h15.out")" "TRAILING"

echo "=== AC-H16: HELPER_ERROR is PRE-LAUNCH-ONLY (post-launch internal fault ⇒ UNAVAILABLE internal) ==="
OUT="$(DRIVE_CODEX_INJECT_INTERNAL_FAULT=1 DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch --scope h16 \
   --scope-class slice --attempt-log "$ALOG" --raw-log "$WORK/codex-raw-h16.log" --marker "$WORK/codex-review-h16.md" \
   --prompt-file "$PROMPT" --poll-secs 0.05 2>/dev/null)"; RC=$?
check "AC-H16 post-launch internal fault ⇒ CODEX_UNAVAILABLE (not HELPER_ERROR)" "$OUT" "CODEX_UNAVAILABLE"
check_contains "AC-H16 cause=internal" "$(cat "$WORK/codex-review-h16.md")" "(internal)"
# every HELPER_ERROR path spawns NO codex (charset case: no raw log written)
if [ ! -f "$WORK/codex-raw-bad.log" ]; then pass "AC-H16 HELPER_ERROR ⇒ codex un-spawned (no raw log)"; else fail "AC-H16 codex spawned on HELPER_ERROR"; fi

echo "=== AC-H17: watchdog race keyed on kill_confirmed (self-exit in kill window ⇒ OK) ==="
disp fake_selfexit_race h17 slice "$WORK/codex-review-h17.md" --poll-secs 0.05 --stall-secs 0.2 --backstop-secs 100
check "AC-H17 self-exit-as-watchdog-fires ⇒ OK (not KILLED)" "$OUT" "OK"
if [ ! -f "$WORK/codex-review-h17.md" ]; then pass "AC-H17 no killed marker on the self-exit race"; else fail "AC-H17 wrote a killed marker on a self-exit"; fi

echo "=== AC-H18: killed-latch terminal across BOTH escape routes ==="
# (a) stall-kill then LAUNCH-GATE probe reports outage ⇒ terminal KILLED (never UNAVAILABLE).
DCNT="$WORK/dcnt_h18a"; : > "$DCNT"
DCNT="$DCNT" disp fake_stall_then_probeoutage h18a slice "$WORK/codex-review-h18a.md" --poll-secs 0.05 --stall-secs 0.2 --backstop-secs 100 --probe-timeout-secs 1
check "AC-H18a stall then probe-outage-on-retry ⇒ KILLED" "$OUT" "CODEX_KILLED_TIMEOUT"
# (b) stall-kill then retry EXEC-FAILS (nonzero/empty) ⇒ terminal KILLED, never UNAVAILABLE.
CNT="$WORK/cnt_h18b"; : > "$CNT"
CNT="$CNT" disp fake_stall_then_execfail h18b slice "$WORK/codex-review-h18b.md" --poll-secs 0.05 --stall-secs 0.2 --backstop-secs 100
check "AC-H18b stall then retry-exec-fail ⇒ KILLED (killed-latch)" "$OUT" "CODEX_KILLED_TIMEOUT"

echo "=== AC-H19: marker-WRITE fail-closed (writable parent, --marker is a DIRECTORY) ==="
mkdir -p "$WORK/marker-is-a-dir"
disp fake_stall h19 slice "$WORK/marker-is-a-dir" --poll-secs 0.05 --stall-secs 0.2 --backstop-secs 100
check "AC-H19 fail-closed exit 1" "$RC" "1"
check_contains "AC-H19 stdout still a closed degraded token (no 5th token)" "OK CODEX_KILLED_TIMEOUT CODEX_UNAVAILABLE HELPER_ERROR" "$OUT"
if [ ! -f "$WORK/marker-is-a-dir" ]; then pass "AC-H19 NO marker file written (path stays a dir)"; else fail "AC-H19 a marker file appeared"; fi
check_contains "AC-H19 stderr fail-closed diagnostic" "$ERR" "fail-closed"

echo "=== AC-H20: prompt-file pre-launch validation (empty prompt ⇒ HELPER_ERROR, un-spawned) ==="
: > "$WORK/empty-prompt.txt"
OUT="$(DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch --scope h20 --scope-class slice --attempt-log "$ALOG" \
   --raw-log "$WORK/codex-raw-h20.log" --marker "$WORK/codex-review-h20.md" --prompt-file "$WORK/empty-prompt.txt" 2>/dev/null)"; RC=$?
check "AC-H20 empty prompt ⇒ HELPER_ERROR" "$OUT" "HELPER_ERROR"
check "AC-H20 empty prompt exit 2" "$RC" "2"
if [ ! -f "$WORK/codex-raw-h20.log" ]; then pass "AC-H20 codex un-spawned (no raw log)"; else fail "AC-H20 codex spawned"; fi

echo "=== AC-H21: hung-probe bound + no forked child survives ==="
SURV="$WORK/survivor_h21"; rm -f "$SURV"
t0=$(date +%s)
OUT="$(SURVIVOR="$SURV" DRIVE_CODEX_CMD="$BIN/fake_probe_hang" "$HELPER" --mode dispatch --scope h21 --scope-class slice \
   --attempt-log "$ALOG" --raw-log "$WORK/codex-raw-h21.log" --marker "$WORK/codex-review-h21.md" \
   --prompt-file "$PROMPT" --poll-secs 0.05 --probe-timeout-secs 0.3 2>/dev/null)"; RC=$?
t1=$(date +%s)
check "AC-H21 hung probe ⇒ CODEX_UNAVAILABLE (fail-toward-degrade)" "$OUT" "CODEX_UNAVAILABLE"
if [ $((t1 - t0)) -le 10 ]; then pass "AC-H21 dispatch returned BOUNDED (<=10s, no wedge)"; else fail "AC-H21 wedged ($((t1-t0))s)"; fi
sleep 0.5
if [ ! -f "$SURV" ]; then pass "AC-H21 NO forked probe child survived the group-kill"; else fail "AC-H21 forked child survived"; fi

echo "=== AC-H22: marker-parent pre-launch guard (structurally-unwritable parent) ==="
mkdir -p "$WORK/rodir"; chmod 555 "$WORK/rodir"
OUT="$(DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch --scope h22 --scope-class slice --attempt-log "$ALOG" \
   --raw-log "$WORK/codex-raw-h22.log" --marker "$WORK/rodir/m.md" --prompt-file "$PROMPT" 2>/dev/null)"; RC=$?
check "AC-H22 unwritable marker parent ⇒ HELPER_ERROR" "$OUT" "HELPER_ERROR"
check "AC-H22 exit 2 PRE-LAUNCH" "$RC" "2"
if [ ! -f "$WORK/codex-raw-h22.log" ]; then pass "AC-H22 codex un-spawned"; else fail "AC-H22 codex spawned"; fi
chmod 755 "$WORK/rodir"

echo "=== AC-H23: helper-death reaping — SIGTERM mid-watch reaps the codex child PGID ==="
SURV23="$WORK/survivor_h23"; rm -f "$SURV23"
SURVIVOR="$SURV23" DRIVE_CODEX_CMD="$BIN/fake_forking_stream" "$HELPER" --mode dispatch --scope h23 --scope-class slice \
  --attempt-log "$ALOG" --raw-log "$WORK/codex-raw-h23.log" --marker "$WORK/codex-review-h23.md" \
  --prompt-file "$PROMPT" --poll-secs 0.1 --stall-secs 100 --backstop-secs 100 >/dev/null 2>&1 &
hpid=$!
sleep 0.6
kill -TERM "$hpid" 2>/dev/null
wait "$hpid" 2>/dev/null
sleep 0.5
if [ ! -f "$SURV23" ]; then pass "AC-H23 SIGTERM'd helper reaped its codex child PGID"; else fail "AC-H23 codex child orphaned after helper SIGTERM"; fi

echo "=== AC-P1 (helper half): HELPER_ERROR writes NO marker at --marker; rc-126/127 spawn no codex ==="
# HELPER_ERROR (bad scope-class) ⇒ no marker at the passed path, no raw log.
OUT="$(DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch --scope p1 --scope-class bogus --attempt-log "$ALOG" \
   --raw-log "$WORK/codex-raw-p1.log" --marker "$WORK/codex-review-p1.md" --prompt-file "$PROMPT" 2>/dev/null)"; RC=$?
check "AC-P1 HELPER_ERROR (bad scope-class) token" "$OUT" "HELPER_ERROR"
if [ ! -f "$WORK/codex-review-p1.md" ] && [ ! -f "$WORK/codex-raw-p1.log" ]; then pass "AC-P1 HELPER_ERROR ⇒ no marker, no codex"; else fail "AC-P1 HELPER_ERROR left a marker/raw-log"; fi
# rc-127: a non-existent helper path never runs (shell rc 127) ⇒ trivially no marker.
"$WORK/no-such-helper.sh" --mode dispatch 2>/dev/null; check "AC-P1 rc-127 (not found) shell rc" "$?" "127"
# rc-126: a non-executable helper copy (shell rc 126) never runs.
cp "$HELPER" "$WORK/noexec-helper.sh"; chmod -x "$WORK/noexec-helper.sh"
"$WORK/noexec-helper.sh" --mode dispatch 2>/dev/null; check "AC-P1 rc-126 (not executable) shell rc" "$?" "126"

echo "=== AC-P4 (helper half): the helper's marker write is atomic (tmp+mv, never torn) ==="
# A killed marker is written tmp+mv; on success no .tmp.$$ lingers and the marker is complete (2 lines).
lingering=$(ls "$WORK"/codex-review-h3kill.md.tmp.* 2>/dev/null | wc -l | tr -d ' ')
check "AC-P4 no lingering .tmp after a successful marker write" "$lingering" "0"

echo "=== FIX1 (codex BLOCKING): non-positive/non-numeric timing knobs ⇒ HELPER_ERROR, codex un-spawned ==="
# --poll-secs 0 (or any non-positive/non-numeric timing knob) would zero the awk poll math and
# disable BOTH the stall AND the backstop kill — a bounded-run bypass. Every timing knob is
# validated strictly-positive PRE-LAUNCH ⇒ HELPER_ERROR (exit 2, no marker, codex never spawned).
for badknob in "--poll-secs 0" "--poll-secs -1" "--poll-secs abc" "--stall-secs 0" \
               "--backstop-secs 0" "--backstop-secs xyz" "--probe-timeout-secs 0" "--max-attempts 0"; do
  rm -f "$WORK/codex-raw-f1.log"
  # shellcheck disable=SC2086
  OUT="$(DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch --scope f1 --scope-class slice --attempt-log "$ALOG" \
      --raw-log "$WORK/codex-raw-f1.log" --marker "$WORK/codex-review-f1.md" --prompt-file "$PROMPT" $badknob 2>/dev/null)"
  RC=$?
  check "FIX1 [$badknob] ⇒ HELPER_ERROR" "$OUT" "HELPER_ERROR"
  check "FIX1 [$badknob] exit 2" "$RC" "2"
  if [ ! -f "$WORK/codex-raw-f1.log" ]; then pass "FIX1 [$badknob] codex un-spawned"; else fail "FIX1 [$badknob] codex spawned"; fi
done
# valid sub-second floats still pass validation and run (guards against over-rejection).
disp fake_ok f1ok slice "$WORK/codex-review-f1ok.md" --poll-secs 0.05 --stall-secs 0.2 --backstop-secs 100
check "FIX1 valid float knobs still run ⇒ OK" "$OUT" "OK"

echo "=== FIX2 (codex MAJOR): a FIFO --attempt-log ⇒ HELPER_ERROR pre-launch (never wedges) ==="
# A FIFO with no reader would block the best-effort `>> "$ATTEMPT_LOG"` and wedge the helper before
# it emits any token. --attempt-log is validated as a regular writable file PRE-LAUNCH. (If the
# validation regressed the helper would WEDGE here — the test would hang — which is itself the alarm.)
FIFO="$WORK/attempt.fifo"; rm -f "$FIFO"; mkfifo "$FIFO"
rm -f "$WORK/codex-raw-f2.log"
OUT="$(DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch --scope f2 --scope-class slice --attempt-log "$FIFO" \
    --raw-log "$WORK/codex-raw-f2.log" --marker "$WORK/codex-review-f2.md" --prompt-file "$PROMPT" --poll-secs 0.05 2>/dev/null)"
RC=$?
check "FIX2 FIFO --attempt-log ⇒ HELPER_ERROR" "$OUT" "HELPER_ERROR"
check "FIX2 FIFO --attempt-log exit 2" "$RC" "2"
if [ ! -f "$WORK/codex-raw-f2.log" ]; then pass "FIX2 FIFO ⇒ codex un-spawned (no wedge)"; else fail "FIX2 codex spawned"; fi
rm -f "$FIFO"
# a REGULAR attempt-log that fails a write mid-run stays best-effort (no wedge) — covered by the
# normal OK/degrade cases above, which all append to the regular $ALOG without ever blocking.

echo ""
echo "===================================================================="
printf 'drive-codex.test.sh: %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
