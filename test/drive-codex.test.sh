#!/usr/bin/env bash
# Plain-bash test runner for bin/drive-codex.sh — the supervised codex-dispatch helper.
#
# Dep-INDEPENDENT of the real codex CLI: every case injects a fake `DRIVE_CODEX_CMD` (a
# log-writing shim), so the closed contract is exercised without codex installed. Covers the
# helper's acceptance criteria: AC-H1..AC-H23 (incl. AC-H12b/AC-H12c behavioral halves) and the
# helper halves of AC-P1/AC-P4, plus the `--mode probe` standalone health query (§A.5) and the
# `--no-watchdog`/`DRIVE_CODEX_WATCHDOG=off` stall-detector kill switch (§A.7/D-32: the backstop
# still bounds). Prints PASS/FAIL per case; exits nonzero if any fail.
#
# Determinism: sub-second --stall-secs/--backstop-secs + a small --poll-secs drive the watchdog by
# poll count (awk float math), not wall clock. `set -m` group kills reap forked children. A fake
# that TRAPS SIGTERM and exits 0 models a codex self-exit in the kill window (kill_confirmed=0).
#
# Supervision-contract scope: the reaping cases (AC-H21/H23, FIX-C, R3-A) assert the honest contract
# "no SAME-PROCESS-GROUP descendant survives helper return" — the fakes fork children in the helper's
# PGID (no `setsid`). A `setsid()`-detached child ESCAPES PGID reaping and is an ACCEPTED, out-of-scope
# residual (real codex never detaches; see bin/drive-codex.sh header CLASS-AUDIT) — deliberately NOT
# asserted here.
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

# doctor HANGS + FORKS a same-PGID child that would touch $SURVIVOR after 30s (⇒ hung-probe; the
# same-PGID child is reaped by the group-kill).
mkfake fake_probe_hang \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) ( sleep 30; touch "$SURVIVOR" ) & sleep 30; exit 0 ;; esac' \
  'printf "x\n"; exit 0'

# doctor HANGS + FORKS a child that touches $SURVIVOR after a SHORT 2s (⇒ a TERM-during-the-PROBE
# window must reap the doctor group FAST, before the child touches — non-vacuous FIX-C repro).
mkfake fake_probe_hang_fast \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) ( sleep 2; touch "$SURVIVOR" ) & sleep 30; exit 0 ;; esac' \
  'printf "x\n"; exit 0'

# exec streams, FORKS a child that touches $SURVIVOR after a SHORT 2s, then sleeps (⇒ helper-death
# must reap it before the child touches — non-vacuous: a leaked child WOULD touch within the wait).
mkfake fake_forking_stream \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  '( sleep 2; touch "$SURVIVOR" ) &' \
  'printf "streaming\n"; sleep 60'

# exec FORKS a SAME-PGID bg child that (after 2s) APPENDS to raw.log AND touches $SURVIVOR, then the
# LEADER exits 0 (⇒ clean OK). The child inherits the exec's fd1 (raw.log). Proves FIX A supervises the
# whole PGID on the OK path: the same-PGID descendant is reaped (no survivor, no post-OK raw.log append).
mkfake fake_fork_then_ok \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  '( sleep 2; echo "LATE-APPEND-AFTER-OK"; touch "$SURVIVOR" ) &' \
  'printf "the real review\nMINOR nit\n"; exit 0'

# doctor FORKS a bg child (sleep 2; touch $SURVIVOR) then exits 0 (clean probe); exec streams OK.
# Proves the probe path reaps forked doctor descendants (group-kill after the probe) on the clean path.
mkfake fake_probe_fork_ok \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) ( sleep 2; touch "$SURVIVOR" ) & exit 0 ;; esac' \
  'printf "review\nok\n"; exit 0'

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

# TRANSIENT launch-gate blip: doctor OK(1)/FAIL(2)/OK(3), exec STALL(1)/OK(2). The post-stall launch
# gate must RETRY the probe (§A.4-1): call-2 FAILs, call-3 OKs ⇒ the retry proceeds ⇒ attempt-2 streams
# OK. A single-shot probe would confirm outage on call-2 and falsely KILL a recoverable round. exec runs
# are counted in $XCNT (⇒ 2).
mkfake fake_stall_then_transient_probe \
  '#!/usr/bin/env bash' \
  'if [ "$1" = doctor ]; then n=$(cat "$DCNT" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > "$DCNT"; [ "$n" = 2 ] && exit 1 || exit 0; fi' \
  'n=$(cat "$XCNT" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > "$XCNT"' \
  'if [ "$n" = 1 ]; then printf "start\n"; sleep 60; else printf "recovered\nok\n"; exit 0; fi'

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
# (c) round-7 FIX A: stall-kill then a TRANSIENT launch-gate probe blip (FAIL then OK on retry) must
# RECOVER — the retrying probe proceeds and attempt-2 streams OK ⇒ final OK, exec_calls=2, NO killed
# marker. Proven RED against the pre-FIX-A single-shot-probe helper (returns KILLED, exec_calls=1).
DCNT="$WORK/dcnt_h18c"; : > "$DCNT"; XCNT="$WORK/xcnt_h18c"; : > "$XCNT"
DCNT="$DCNT" XCNT="$XCNT" disp fake_stall_then_transient_probe h18c slice "$WORK/codex-review-h18c.md" --poll-secs 0.05 --stall-secs 0.2 --backstop-secs 100 --probe-timeout-secs 1
check "AC-H18c transient launch-gate probe recovers ⇒ OK (retrying probe)" "$OUT" "OK"
check "AC-H18c exec ran TWICE (attempt-2 launched after the probe retry recovered)" "$(cat "$XCNT")" "2"
if [ ! -f "$WORK/codex-review-h18c.md" ]; then pass "AC-H18c recovered OK ⇒ NO killed marker"; else fail "AC-H18c a killed marker appeared (round falsely killed)"; fi

echo "=== AC-H18d: gate-enforced probe-outage forces ONE bounded attempt; that attempt STALLS ⇒ terminal KILLED, no retry ==="
# STEP-1 probe reports outage AND the scope is GATE-ENFORCED (phase/finalize/sensitive) ⇒ the helper
# forces max_attempts=1 (one bounded attempt, NO stall-retry). AC-H8 covers only the sub-case where
# that single forced attempt STREAMS OK; THIS covers the KILL sub-case — the forced single attempt
# goes byte-silent and is stall-killed. With attempt==max_attempts==1 the `attempt < max_attempts`
# launch-gate guard is FALSE, so there is NO retry probe and the terminal outcome is
# CODEX_KILLED_TIMEOUT — the marker family, NOT CODEX_UNAVAILABLE (a killed round must NEVER
# masquerade as an availability failure).
mkfake fake_probe_outage_then_stall \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) exit 1 ;; esac' \
  'printf "start\n"; sleep 60'
disp fake_probe_outage_then_stall h18d phase "$WORK/codex-review-h18d.md" --poll-secs 0.05 --stall-secs 0.2 --backstop-secs 100 --probe-timeout-secs 1
check "AC-H18d gate-enforced probe-outage + forced single attempt STALLS ⇒ KILLED (NOT UNAVAILABLE)" "$OUT" "CODEX_KILLED_TIMEOUT"
check "AC-H18d KILLED exit 1" "$RC" "1"
check "AC-H18d marker 1st line == token" "$(head -1 "$WORK/codex-review-h18d.md")" "CODEX_KILLED_TIMEOUT"
check_contains "AC-H18d marker attempts=1 (single forced attempt, no retry)" "$(cat "$WORK/codex-review-h18d.md")" "attempts=1"
# NO stall-RETRY happened after the forced single attempt: the attempt log carries NO op=retry line for
# this scope ("scope":"h18d" is emitted immediately before "op":<op> on every log_attempt line).
h18d_retries=$(grep -F '"scope":"h18d","op":"retry"' "$ALOG" 2>/dev/null | wc -l | tr -d ' ')
check "AC-H18d forced single attempt ⇒ NO retry op logged" "$h18d_retries" "0"
# exactly ONE killed log (${raw%.log}.killed-1.log, N=1) — no killed-2.log, because no retry launched.
if [ -f "$WORK/codex-raw-h18d.killed-1.log" ] && [ ! -f "$WORK/codex-raw-h18d.killed-2.log" ]; then
  pass "AC-H18d exactly one killed log (killed-1.log, N=1) — no retry attempt launched"
else fail "AC-H18d expected exactly one killed-1.log (a retry must NOT have launched)"; fi
# and the STEP-1 probe DID log the outage that forced the single-attempt (max_attempts=1) path.
check_contains "AC-H18d step-1 probe logged the outage (probed-outage)" "$(grep -F '"scope":"h18d","op":"probe"' "$ALOG")" "outage"

echo "=== AC-H19: marker-WRITE fail-closed (writable parent, --marker is a DIRECTORY) ==="
mkdir -p "$WORK/marker-is-a-dir"
disp fake_stall h19 slice "$WORK/marker-is-a-dir" --poll-secs 0.05 --stall-secs 0.2 --backstop-secs 100
check "AC-H19 fail-closed exit 1" "$RC" "1"
check_contains "AC-H19 stdout still a closed degraded token (no 5th token)" "OK CODEX_KILLED_TIMEOUT CODEX_UNAVAILABLE HELPER_ERROR" "$OUT"
# NON-VACUOUS (round-7 FIX C): the path stays a dir, so `-f` is trivially false even if a regressed
# helper did `mv "$tmp" "$MARKER"` (which puts `$tmp` INSIDE the dir). Assert the dir stays EMPTY — no
# marker/tmp entry was written into it — so a dropped `[ -d "$MARKER" ]` guard would RED here.
if [ -d "$WORK/marker-is-a-dir" ] && [ -z "$(ls -A "$WORK/marker-is-a-dir" 2>/dev/null)" ]; then
  pass "AC-H19 marker path stays an EMPTY dir (no marker/tmp written into it)"
else fail "AC-H19 the marker dir gained an entry (a marker/tmp was written)"; fi
check_contains "AC-H19 stderr fail-closed diagnostic" "$ERR" "fail-closed"

echo "=== AC-H20: prompt-file pre-launch validation (empty prompt ⇒ HELPER_ERROR, un-spawned) ==="
: > "$WORK/empty-prompt.txt"
OUT="$(DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch --scope h20 --scope-class slice --attempt-log "$ALOG" \
   --raw-log "$WORK/codex-raw-h20.log" --marker "$WORK/codex-review-h20.md" --prompt-file "$WORK/empty-prompt.txt" 2>/dev/null)"; RC=$?
check "AC-H20 empty prompt ⇒ HELPER_ERROR" "$OUT" "HELPER_ERROR"
check "AC-H20 empty prompt exit 2" "$RC" "2"
if [ ! -f "$WORK/codex-raw-h20.log" ]; then pass "AC-H20 codex un-spawned (no raw log)"; else fail "AC-H20 codex spawned"; fi

echo "=== AC-H21: hung-probe bound + no SAME-PGID forked probe child survives ==="
SURV="$WORK/survivor_h21"; rm -f "$SURV"
t0=$(date +%s)
OUT="$(SURVIVOR="$SURV" DRIVE_CODEX_CMD="$BIN/fake_probe_hang" "$HELPER" --mode dispatch --scope h21 --scope-class slice \
   --attempt-log "$ALOG" --raw-log "$WORK/codex-raw-h21.log" --marker "$WORK/codex-review-h21.md" \
   --prompt-file "$PROMPT" --poll-secs 0.05 --probe-timeout-secs 0.3 2>/dev/null)"; RC=$?
t1=$(date +%s)
check "AC-H21 hung probe ⇒ CODEX_UNAVAILABLE (fail-toward-degrade)" "$OUT" "CODEX_UNAVAILABLE"
if [ $((t1 - t0)) -le 10 ]; then pass "AC-H21 dispatch returned BOUNDED (<=10s, no wedge)"; else fail "AC-H21 wedged ($((t1-t0))s)"; fi
sleep 0.5
if [ ! -f "$SURV" ]; then pass "AC-H21 NO same-PGID forked probe child survived the group-kill"; else fail "AC-H21 same-PGID forked child survived"; fi

echo "=== AC-H22: marker-parent pre-launch guard (structurally-unwritable parent) ==="
mkdir -p "$WORK/rodir"; chmod 555 "$WORK/rodir"
OUT="$(DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch --scope h22 --scope-class slice --attempt-log "$ALOG" \
   --raw-log "$WORK/codex-raw-h22.log" --marker "$WORK/rodir/m.md" --prompt-file "$PROMPT" 2>/dev/null)"; RC=$?
check "AC-H22 unwritable marker parent ⇒ HELPER_ERROR" "$OUT" "HELPER_ERROR"
check "AC-H22 exit 2 PRE-LAUNCH" "$RC" "2"
if [ ! -f "$WORK/codex-raw-h22.log" ]; then pass "AC-H22 codex un-spawned"; else fail "AC-H22 codex spawned"; fi
chmod 755 "$WORK/rodir"

echo "=== AC-H23: helper-death reaping — SIGTERM mid-watch reaps the codex child PGID ==="
# NON-VACUOUS: the survivor child touches after 2s; TERM lands at 0.6s and we observe past the 2s
# touch, so a LEAKED (un-reaped) child WOULD create the survivor within the window (proven RED
# against a helper without the reaper). Reaping kills the child group before its 2s touch.
SURV23="$WORK/survivor_h23"; rm -f "$SURV23"
SURVIVOR="$SURV23" DRIVE_CODEX_CMD="$BIN/fake_forking_stream" "$HELPER" --mode dispatch --scope h23 --scope-class slice \
  --attempt-log "$ALOG" --raw-log "$WORK/codex-raw-h23.log" --marker "$WORK/codex-review-h23.md" \
  --prompt-file "$PROMPT" --poll-secs 0.1 --stall-secs 100 --backstop-secs 100 >/dev/null 2>&1 &
hpid=$!
sleep 0.6
kill -TERM "$hpid" 2>/dev/null
wait "$hpid" 2>/dev/null
sleep 2.5
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

echo "=== FIX3 (codex BLOCKING): --poll-secs coarser than its stall/backstop bound ⇒ HELPER_ERROR pre-launch ==="
# A --poll-secs >= backstop_secs (or stall_secs) sleeps PAST the deadline before the watchdog checks
# it ⇒ the stall/backstop kill NEVER fires (a per-attempt-backstop bypass). --poll-secs is now
# validated strictly LESS than BOTH thresholds PRE-LAUNCH ⇒ HELPER_ERROR (exit 2, no marker, codex
# never spawned). The equal case (poll == backstop) is ALSO rejected (strictly-less boundary).
for badpoll in "--poll-secs 0.5 --backstop-secs 0.2 --stall-secs 100" \
               "--poll-secs 0.5 --stall-secs 0.2 --backstop-secs 100" \
               "--poll-secs 0.2 --backstop-secs 0.2 --stall-secs 100"; do
  rm -f "$WORK/codex-raw-f3.log"
  # shellcheck disable=SC2086
  OUT="$(DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch --scope f3 --scope-class slice --attempt-log "$ALOG" \
      --raw-log "$WORK/codex-raw-f3.log" --marker "$WORK/codex-review-f3.md" --prompt-file "$PROMPT" $badpoll 2>/dev/null)"
  RC=$?
  check "FIX3 [$badpoll] ⇒ HELPER_ERROR" "$OUT" "HELPER_ERROR"
  check "FIX3 [$badpoll] exit 2" "$RC" "2"
  if [ ! -f "$WORK/codex-raw-f3.log" ]; then pass "FIX3 [$badpoll] codex un-spawned"; else fail "FIX3 [$badpoll] codex spawned"; fi
done
# a normal small poll (poll < min(stall,backstop)) still runs (guards against over-rejection).
disp fake_ok f3ok slice "$WORK/codex-review-f3ok.md" --poll-secs 0.05 --stall-secs 0.2 --backstop-secs 100
check "FIX3 small poll < min(stall,backstop) still runs ⇒ OK" "$OUT" "OK"

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

echo "=== FIX-A (codex MAJOR/SECURITY): numeric env vars are NOT command-injection surfaces ==="
# DRIVE_CODEX_STALL_MINS / _BACKSTOP_HOURS were interpolated into an awk PROGRAM before validation ⇒
# RCE (a `1; system("touch X"); 1` payload executed). Now each is validated as a plain positive
# number BEFORE use and multiplied via `awk -v` (parameterized). An injection payload does NOT
# execute (no side-effect file) and yields HELPER_ERROR (config-resolution, pre-launch, un-spawned).
INJ="$WORK/injected_stall"; rm -f "$INJ" "$WORK/codex-raw-fa1.log"
OUT="$(DRIVE_CODEX_STALL_MINS="1; system(\"touch $INJ\"); 1" DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch \
   --scope fa1 --scope-class slice --attempt-log "$ALOG" --raw-log "$WORK/codex-raw-fa1.log" \
   --marker "$WORK/codex-review-fa1.md" --prompt-file "$PROMPT" --poll-secs 0.05 2>/dev/null)"; RC=$?
check "FIX-A STALL_MINS injection ⇒ HELPER_ERROR" "$OUT" "HELPER_ERROR"
check "FIX-A STALL_MINS injection exit 2" "$RC" "2"
if [ ! -f "$INJ" ]; then pass "FIX-A STALL_MINS injection did NOT execute (no side-effect file)"; else fail "FIX-A STALL_MINS injection EXECUTED (RCE)"; fi
if [ ! -f "$WORK/codex-raw-fa1.log" ]; then pass "FIX-A STALL_MINS injection ⇒ codex un-spawned"; else fail "FIX-A codex spawned"; fi
INJ2="$WORK/injected_backstop"; rm -f "$INJ2" "$WORK/codex-raw-fa2.log"
OUT="$(DRIVE_CODEX_BACKSTOP_HOURS="2; system(\"touch $INJ2\"); 2" DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch \
   --scope fa2 --scope-class slice --attempt-log "$ALOG" --raw-log "$WORK/codex-raw-fa2.log" \
   --marker "$WORK/codex-review-fa2.md" --prompt-file "$PROMPT" --poll-secs 0.05 2>/dev/null)"; RC=$?
check "FIX-A BACKSTOP_HOURS injection ⇒ HELPER_ERROR" "$OUT" "HELPER_ERROR"
if [ ! -f "$INJ2" ]; then pass "FIX-A BACKSTOP_HOURS injection did NOT execute"; else fail "FIX-A BACKSTOP_HOURS injection EXECUTED (RCE)"; fi
# a garbage (non-numeric) env is ALSO rejected pre-launch (not silently defaulted).
OUT="$(DRIVE_CODEX_STALL_MINS="abc" DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch --scope fa2b --scope-class slice \
   --attempt-log "$ALOG" --raw-log "$WORK/codex-raw-fa2b.log" --marker "$WORK/codex-review-fa2b.md" --prompt-file "$PROMPT" --poll-secs 0.05 2>/dev/null)"
check "FIX-A non-numeric STALL_MINS ⇒ HELPER_ERROR" "$OUT" "HELPER_ERROR"
# a VALID numeric env still resolves + runs (sub-second, so it stays fast) — guards over-rejection.
DRIVE_CODEX_STALL_MINS=0.004 disp fake_ok fa3 slice "$WORK/codex-review-fa3.md" --poll-secs 0.05 --backstop-secs 100
check "FIX-A valid DRIVE_CODEX_STALL_MINS still runs ⇒ OK" "$OUT" "OK"

echo "=== FIX-B (codex BLOCKING): explicit --sandbox beats DRIVE_CODEX_SANDBOX=off (precedence) ==="
# §A.3 precedence is explicit --flag > env > default; env-off must NOT drop an explicit --sandbox.
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" DRIVE_CODEX_SANDBOX=off disp fake_argv fb1 slice "$WORK/codex-review-fb1.md" --poll-secs 0.05 --sandbox read-only
check_contains "FIX-B explicit --sandbox read-only + env off ⇒ exec STILL carries --sandbox read-only" "$(cat "$WORK/argv.log")" "--sandbox read-only"

echo "=== FIX-C (codex BLOCKING): TERM during the PROBE window reaps the probe child (no survivor) ==="
# The reaping trap used to be installed only AFTER codex exec launched; during the doctor probe an
# external TERM leaked a forking-doctor child. Now the reaper trap covers the probe window too.
# NON-VACUOUS: the forked doctor child touches after 2s; TERM lands at 0.6s and we observe past 2s.
SURV_P="$WORK/survivor_probe"; rm -f "$SURV_P"
SURVIVOR="$SURV_P" DRIVE_CODEX_CMD="$BIN/fake_probe_hang_fast" "$HELPER" --mode dispatch --scope fc3 --scope-class slice \
  --attempt-log "$ALOG" --raw-log "$WORK/codex-raw-fc3.log" --marker "$WORK/codex-review-fc3.md" \
  --prompt-file "$PROMPT" --poll-secs 0.05 --probe-timeout-secs 30 >/dev/null 2>&1 &
hp3=$!
sleep 0.6
kill -TERM "$hp3" 2>/dev/null
wait "$hp3" 2>/dev/null
sleep 2.5
if [ ! -f "$SURV_P" ]; then pass "FIX-C TERM during probe reaped the doctor child group (no survivor)"; else fail "FIX-C probe child survived an external TERM"; fi

echo "=== FIX-D (codex MAJOR): invalid sandbox rung ⇒ HELPER_ERROR pre-launch (codex un-spawned) ==="
# --sandbox / DRIVE_CODEX_SANDBOX are validated against {read-only,workspace-write,danger-full-access,
# off} PRE-LAUNCH. A garbage rung used to be passed to codex and fail POST-launch (CODEX_UNAVAILABLE
# + codex spawned); config-resolution failures are pre-launch HELPER_ERROR, codex un-spawned.
rm -f "$WORK/codex-raw-fd1.log"
OUT="$(DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch --scope fd1 --scope-class slice --attempt-log "$ALOG" \
   --raw-log "$WORK/codex-raw-fd1.log" --marker "$WORK/codex-review-fd1.md" --prompt-file "$PROMPT" --poll-secs 0.05 --sandbox garbage 2>/dev/null)"; RC=$?
check "FIX-D --sandbox garbage ⇒ HELPER_ERROR" "$OUT" "HELPER_ERROR"
check "FIX-D --sandbox garbage exit 2" "$RC" "2"
if [ ! -f "$WORK/codex-raw-fd1.log" ]; then pass "FIX-D --sandbox garbage ⇒ codex un-spawned"; else fail "FIX-D codex spawned on invalid rung"; fi
rm -f "$WORK/codex-raw-fd2.log"
OUT="$(DRIVE_CODEX_SANDBOX=garbage DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch --scope fd2 --scope-class slice --attempt-log "$ALOG" \
   --raw-log "$WORK/codex-raw-fd2.log" --marker "$WORK/codex-review-fd2.md" --prompt-file "$PROMPT" --poll-secs 0.05 2>/dev/null)"; RC=$?
check "FIX-D DRIVE_CODEX_SANDBOX=garbage ⇒ HELPER_ERROR" "$OUT" "HELPER_ERROR"
if [ ! -f "$WORK/codex-raw-fd2.log" ]; then pass "FIX-D env garbage rung ⇒ codex un-spawned"; else fail "FIX-D codex spawned on invalid env rung"; fi
# a VALID explicit rung still composes on the exec argv; explicit `--sandbox off` = no flag.
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" disp fake_argv fd3 slice "$WORK/codex-review-fd3.md" --poll-secs 0.05 --sandbox danger-full-access
check_contains "FIX-D valid --sandbox danger-full-access composes" "$(cat "$WORK/argv.log")" "--sandbox danger-full-access"
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" disp fake_argv fd4 slice "$WORK/codex-review-fd4.md" --poll-secs 0.05 --sandbox off
check_absent "FIX-D --sandbox off (explicit kill switch) ⇒ no --sandbox flag" "$(cat "$WORK/argv.log")" "--sandbox"

echo "=== R3-A (codex BLOCKING): SAME-PGID descendant leak on the clean-OK path — supervise the PGID ==="
# codex forks a SAME-PGID bg child then exits 0. The watchdog/wait track the LEADER only, so pre-fix
# the child survived PAST the backstop and could append to raw.log AFTER OK (corrupting the
# post-process read). FIX A reaps any surviving PGID member on EVERY terminal path (incl. OK) before
# classifying. NON-VACUOUS: the child touches + appends after 2s; we observe past that. Proven RED on
# round-2. (A `setsid`-detached child would ESCAPE — accepted residual, NOT asserted here.)
SURV_A="$WORK/survivor_okfork"; rm -f "$SURV_A"
SURVIVOR="$SURV_A" disp fake_fork_then_ok r3a slice "$WORK/codex-review-r3a.md" --poll-secs 0.05 --stall-secs 100 --backstop-secs 100
check "R3-A forked-child-then-exit-0 still classifies OK" "$OUT" "OK"
sleep 2.6
if [ ! -f "$SURV_A" ]; then pass "R3-A OK-path SAME-PGID forked descendant REAPED (no survivor)"; else fail "R3-A same-PGID descendant survived the clean-OK path"; fi
check_absent "R3-A no post-OK SAME-PGID append reached raw.log (post-process read uncorrupted)" "$(cat "$WORK/codex-raw-r3a.log" 2>/dev/null)" "LATE-APPEND-AFTER-OK"

echo "=== R3-A(probe): clean-probe forked doctor descendant is reaped too (process-supervision class) ==="
SURV_AP="$WORK/survivor_probefork"; rm -f "$SURV_AP"
SURVIVOR="$SURV_AP" disp fake_probe_fork_ok r3ap slice "$WORK/codex-review-r3ap.md" --poll-secs 0.05 --probe-timeout-secs 30
check "R3-A(probe) exec runs after the clean probe ⇒ OK" "$OUT" "OK"
sleep 2.6
if [ ! -f "$SURV_AP" ]; then pass "R3-A(probe) forked doctor descendant reaped on the clean probe path"; else fail "R3-A(probe) doctor descendant survived"; fi

echo "=== R3-B (codex MAJOR): non-empty but UNREADABLE --prompt-file ⇒ HELPER_ERROR pre-launch ==="
# A chmod-000 non-empty prompt passes -s but cat's to "" ⇒ pre-fix a degenerate empty-prompt exec ⇒
# false OK (defeats AC-H20). FIX B reads the prompt PRE-LAUNCH and fails closed on a read error.
UNREAD="$WORK/unreadable-prompt.txt"; printf 'a real non-empty prompt body' > "$UNREAD"; chmod 000 "$UNREAD"
rm -f "$WORK/codex-raw-r3b.log"
OUT="$(DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch --scope r3b --scope-class slice --attempt-log "$ALOG" \
   --raw-log "$WORK/codex-raw-r3b.log" --marker "$WORK/codex-review-r3b.md" --prompt-file "$UNREAD" --poll-secs 0.05 2>/dev/null)"; RC=$?
check "R3-B unreadable non-empty prompt ⇒ HELPER_ERROR" "$OUT" "HELPER_ERROR"
check "R3-B unreadable prompt exit 2" "$RC" "2"
if [ ! -f "$WORK/codex-raw-r3b.log" ]; then pass "R3-B unreadable prompt ⇒ codex un-spawned"; else fail "R3-B codex spawned on unreadable prompt"; fi
chmod 644 "$UNREAD"   # readable now — must run (no over-rejection)
disp fake_ok r3bok slice "$WORK/codex-review-r3bok.md" --poll-secs 0.05
check "R3-B readable non-empty prompt still runs ⇒ OK" "$OUT" "OK"

echo "=== R3-C (required-file-read class): an UNREADABLE clean --prior-codex ⇒ FULL effort (not down-tier) ==="
# Pre-fix an unreadable prior's failed grep fell through to || EFFORT_LOW=1 and WRONGLY down-tiered.
# The -r guard fails toward FULL effort (conservative) when the prior can't be read/confirmed clean.
PRIOR_UNR="$WORK/codex-review-prior-unread.md"; printf 'Codex review\nLooks fine; nothing to change.\n' > "$PRIOR_UNR"; chmod 000 "$PRIOR_UNR"
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" disp fake_argv r3c slice "$WORK/codex-review-r3c.md" --poll-secs 0.05 --confirmation-class --prior-codex "$PRIOR_UNR"
check_absent "R3-C unreadable clean prior ⇒ FULL effort (no -c down-tier)" "$(cat "$WORK/argv.log")" "model_reasoning_effort"
chmod 644 "$PRIOR_UNR"   # readable clean prior STILL down-tiers (no over-correction)
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" disp fake_argv r3cok slice "$WORK/codex-review-r3cok.md" --poll-secs 0.05 --confirmation-class --prior-codex "$PRIOR_UNR"
check_contains "R3-C readable clean prior still down-tiers" "$(cat "$WORK/argv.log")" "model_reasoning_effort=medium"

echo "=== R4-A (codex MAJOR): --raw-log preflight — a dir/FIFO ⇒ HELPER_ERROR pre-launch (un-spawned) ==="
# --raw-log was NOT pre-validated: a directory --raw-log fails the exec `> "$RAW_LOG"` redirect at
# launch (codex never starts) yet classified exec-failed ⇒ CODEX_UNAVAILABLE + a degraded marker the
# coordinator accepts — silently dropping the codex voice instead of the broken-helper STOP lane. Now
# --raw-log is preflighted (regular writable/creatable; reject dir/FIFO/socket) ⇒ HELPER_ERROR.
mkdir -p "$WORK/rawlog-is-a-dir"
OUT="$(DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch --scope r4a --scope-class slice --attempt-log "$ALOG" \
   --raw-log "$WORK/rawlog-is-a-dir" --marker "$WORK/codex-review-r4a.md" --prompt-file "$PROMPT" --poll-secs 0.05 2>/dev/null)"; RC=$?
check "R4-A directory --raw-log ⇒ HELPER_ERROR" "$OUT" "HELPER_ERROR"
check "R4-A directory --raw-log exit 2 PRE-LAUNCH" "$RC" "2"
if [ ! -f "$WORK/codex-review-r4a.md" ]; then pass "R4-A directory --raw-log ⇒ NO degraded marker (broken-helper STOP lane, not CODEX_UNAVAILABLE)"; else fail "R4-A a degraded marker appeared (voice silently dropped)"; fi
# a FIFO --raw-log must ALSO be rejected pre-launch and must NOT wedge (the `-f` guard rejects it
# BEFORE the `:>` truncate that would block on a reader-less FIFO — if it regressed this would hang).
RAWFIFO="$WORK/rawlog.fifo"; rm -f "$RAWFIFO"; mkfifo "$RAWFIFO"
OUT="$(DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch --scope r4af --scope-class slice --attempt-log "$ALOG" \
   --raw-log "$RAWFIFO" --marker "$WORK/codex-review-r4af.md" --prompt-file "$PROMPT" --poll-secs 0.05 2>/dev/null)"; RC=$?
check "R4-A FIFO --raw-log ⇒ HELPER_ERROR (no wedge)" "$OUT" "HELPER_ERROR"
check "R4-A FIFO --raw-log exit 2" "$RC" "2"
rm -f "$RAWFIFO"
# a normal creatable --raw-log still runs (no over-rejection) — the OK cases above already exercise this,
# but assert once more against a FRESH path to guard the new create+truncate preflight.
disp fake_ok r4aok slice "$WORK/codex-review-r4aok.md" --poll-secs 0.05
check "R4-A fresh regular --raw-log still runs ⇒ OK" "$OUT" "OK"

echo "=== R5-A (codex MAJOR): a writable --raw-log inside a READ-ONLY dir ⇒ HELPER_ERROR pre-launch ==="
# --raw-log validated the FILE but not its DIR. The probe writes a sibling ${raw%.log}.probe.log (and
# killed-log renames land) in that dir, so a writable raw.log inside a read-only (555) dir failed those
# POST-launch ⇒ a false CODEX_UNAVAILABLE degrade + a marker the coordinator accepts. Now the raw-log
# PARENT dir is required writable PRE-LAUNCH ⇒ HELPER_ERROR (broken-helper STOP lane, no degraded marker).
mkdir -p "$WORK/r5rodir"; : > "$WORK/r5rodir/raw.log"; chmod 555 "$WORK/r5rodir"
OUT="$(DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch --scope r5a --scope-class slice --attempt-log "$ALOG" \
   --raw-log "$WORK/r5rodir/raw.log" --marker "$WORK/codex-review-r5a.md" --prompt-file "$PROMPT" --poll-secs 0.05 --probe-timeout-secs 1 2>/dev/null)"; RC=$?
check "R5-A read-only raw-log dir ⇒ HELPER_ERROR" "$OUT" "HELPER_ERROR"
check "R5-A read-only raw-log dir exit 2 PRE-LAUNCH" "$RC" "2"
if [ ! -f "$WORK/codex-review-r5a.md" ]; then pass "R5-A read-only raw-log dir ⇒ NO degraded marker (STOP lane, not CODEX_UNAVAILABLE)"; else fail "R5-A a degraded marker appeared (voice silently dropped)"; fi
chmod 755 "$WORK/r5rodir"

echo "=== R5-B (codex MINOR): a control char in a logged field ⇒ still VALID JSONL ==="
# _jstr escaped only \ and " ⇒ a control char (a newline in the basename-derived runId here) produced
# INVALID JSONL (the raw newline split the record across physical lines). _jstr now escapes all C0
# control chars ⇒ every line parses. (Uses a DEDICATED attempt-log whose basename carries a newline.)
R5NLALOG="$WORK/codex-attempts-run"$'\n'"id.jsonl"; rm -f "$R5NLALOG"
DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode dispatch --scope r5b --scope-class slice \
  --attempt-log "$R5NLALOG" --raw-log "$WORK/codex-raw-r5b.log" --marker "$WORK/codex-review-r5b.md" \
  --prompt-file "$PROMPT" --poll-secs 0.05 >/dev/null 2>&1
python3 - "$R5NLALOG" <<'PY'
import json, sys
n = bad = 0
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    line = line.strip()
    if not line: continue
    n += 1
    try: json.loads(line)
    except Exception: bad += 1
sys.exit(1 if (bad or n == 0) else 0)
PY
check "R5-B control char (newline in runId) ⇒ every attempt-log line is valid JSON" "$?" "0"

echo "=== R6-A (codex MAJOR): an EMPTY/whitespace --prior-codex ⇒ FULL effort (not a wrong down-tier) ==="
# The clean-prior gate excluded degraded first lines + severity tags, but an EMPTY (or whitespace-only)
# --prior-codex fell through ⇒ EFFORT_LOW=1 (medium). An empty prior is NOT a completed clean review;
# per D-16 it must fail toward FULL effort. `_log_nonempty` now gates the down-tier. Proven RED on round-5.
: > "$WORK/prior-empty.md"
printf '   \n\t\n' > "$WORK/prior-ws.md"
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" disp fake_argv r6ae slice "$WORK/codex-review-r6ae.md" --poll-secs 0.05 --confirmation-class --prior-codex "$WORK/prior-empty.md"
check_absent "R6-A empty --prior-codex ⇒ FULL effort (no -c down-tier)" "$(cat "$WORK/argv.log")" "model_reasoning_effort"
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" disp fake_argv r6aw slice "$WORK/codex-review-r6aw.md" --poll-secs 0.05 --confirmation-class --prior-codex "$WORK/prior-ws.md"
check_absent "R6-A whitespace-only --prior-codex ⇒ FULL effort (no -c)" "$(cat "$WORK/argv.log")" "model_reasoning_effort"
mkclean "$WORK/prior-clean-r6.md"   # a real CLEAN non-empty prior STILL down-tiers (no over-correction)
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" disp fake_argv r6ac slice "$WORK/codex-review-r6ac.md" --poll-secs 0.05 --confirmation-class --prior-codex "$WORK/prior-clean-r6.md"
check_contains "R6-A clean non-empty prior still down-tiers (no over-correction)" "$(cat "$WORK/argv.log")" "model_reasoning_effort=medium"

echo "=== R6-B (P3): max_gap_secs is valid JSON regardless of the inbound numeric locale ==="
# awk number formatting is locale-sensitive; under a comma-locale a fractional max_gap prints `0,05` ⇒
# invalid JSON. The helper runs its numeric awk under LC_ALL=C (_awk), so the field is dot-decimal in
# ANY locale. Run under an installed comma-locale (a genuine regression — reds on the pre-_awk helper);
# else fall back to C. The fake pauses 0.25s then keeps streaming ⇒ a reliably-FRACTIONAL observed gap.
R6LOC="C"; _r6locs=" $(locale -a 2>/dev/null | tr '\n' ' ') "   # space-delimited; no early-closing pipe (pipefail-safe)
for L in de_DE.UTF-8 fr_FR.UTF-8 nl_NL.UTF-8 es_ES.UTF-8 it_IT.UTF-8; do
  case "$_r6locs" in *" $L "*) R6LOC="$L"; break ;; esac
done
mkfake fake_gap \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  'printf "start\n"; sleep 0.25; for i in 1 2 3 4 5 6; do printf "chunk%s\n" "$i"; sleep 0.05; done; exit 0'
R6LOG="$WORK/codex-attempts-r6loc.jsonl"; rm -f "$R6LOG"
LC_ALL="$R6LOC" DRIVE_CODEX_CMD="$BIN/fake_gap" "$HELPER" --mode dispatch --scope r6b --scope-class slice \
  --attempt-log "$R6LOG" --raw-log "$WORK/codex-raw-r6b.log" --marker "$WORK/codex-review-r6b.md" \
  --prompt-file "$PROMPT" --poll-secs 0.05 --stall-secs 5 --backstop-secs 100 >/dev/null 2>&1
python3 - "$R6LOG" <<'PY'
import json, sys
n = bad = 0
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    line = line.strip()
    if not line: continue
    n += 1
    try: json.loads(line)
    except Exception: bad += 1
sys.exit(1 if (bad or n == 0) else 0)
PY
check "R6-B max_gap_secs valid JSON under LC_ALL=$R6LOC (locale-independent numeric awk)" "$?" "0"

echo "=== PM (§A.5): --mode probe standalone health query — closed-set member, marker-free ==="
# --mode probe runs the health probe in ISOLATION and prints OK|CODEX_UNAVAILABLE (no marker). It
# requires NEITHER --marker NOR --raw-log NOR --scope-class (dispatch-only flags) — so an OK/exit-0
# here also proves probe's required-flag set is distinct from dispatch (else it would HELPER_ERROR).
OUT="$(DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode probe --scope pmok --attempt-log "$ALOG" \
   --poll-secs 0.05 --probe-timeout-secs 1 2>/dev/null)"; RC=$?
check "PM probe doctor-OK ⇒ OK" "$OUT" "OK"
check "PM probe doctor-OK exit 0 (no --marker/--raw-log/--scope-class needed)" "$RC" "0"
OUT="$(DRIVE_CODEX_CMD="$BIN/fake_probe_outage" "$HELPER" --mode probe --scope pmout --attempt-log "$ALOG" \
   --poll-secs 0.05 --probe-timeout-secs 1 2>/dev/null)"; RC=$?
check "PM probe outage (after retry-with-backoff) ⇒ CODEX_UNAVAILABLE" "$OUT" "CODEX_UNAVAILABLE"
check "PM probe outage exit 1" "$RC" "1"
OUT="$(DRIVE_CODEX_CMD=/nonexistent-codex-pm "$HELPER" --mode probe --scope pmabs --attempt-log "$ALOG" 2>/dev/null)"; RC=$?
check "PM probe cli-absent ⇒ CODEX_UNAVAILABLE" "$OUT" "CODEX_UNAVAILABLE"
check "PM probe cli-absent exit 1" "$RC" "1"
echo "=== PM-RO (finalize r2 codex P1): --mode probe writable --attempt-log inside a READ-ONLY dir ⇒ HELPER_ERROR (no false CODEX_UNAVAILABLE) ==="
# probe mode writes codex-probe-<scope>.log as a sibling of --attempt-log (dispatch mode uses the
# R5-A-preflighted raw-log sibling). A writable attempt-log FILE inside a read-only (555) dir passes
# the file check, but the sibling create would fail POST-launch ⇒ a false CODEX_UNAVAILABLE (a LOCAL
# fs fault masquerading as a remote outage, silently dropping the voice). The probe-log DIR is now
# required writable PRE-LAUNCH ⇒ HELPER_ERROR (broken-helper STOP lane). SAME structural class R5-A
# closed for dispatch's raw-log. Proven RED against the pre-fix helper (returns CODEX_UNAVAILABLE/1).
mkdir -p "$WORK/pmrodir"; : > "$WORK/pmrodir/attempts.jsonl"; chmod 555 "$WORK/pmrodir"
OUT="$(DRIVE_CODEX_CMD="$BIN/fake_ok" "$HELPER" --mode probe --scope pmro \
   --attempt-log "$WORK/pmrodir/attempts.jsonl" --poll-secs 0.05 --probe-timeout-secs 1 2>/dev/null)"; RC=$?
check "PM-RO read-only probe-log dir ⇒ HELPER_ERROR (not false CODEX_UNAVAILABLE)" "$OUT" "HELPER_ERROR"
check "PM-RO HELPER_ERROR exit 2 PRE-LAUNCH" "$RC" "2"
if [ ! -f "$WORK/pmrodir/codex-probe-pmro.log" ]; then pass "PM-RO ⇒ NO probe log spawned (un-spawned, STOP lane)"; else fail "PM-RO a probe log appeared (probe launched despite unwritable dir)"; fi
chmod 755 "$WORK/pmrodir"

echo "=== WD (§A.7 / D-32): --no-watchdog disables the STALL detector ONLY — the backstop still bounds ==="
# CONTROL — SAME knobs, watchdog ON: a byte-silent fake is STALL-killed (stall 0.2 fires before
# backstop 0.5). Isolates the flag as the ONLY variable in the --no-watchdog contrast below.
wdcause() { sed -n '2p' "$1" 2>/dev/null; }
disp fake_stall wdctl slice "$WORK/codex-review-wdctl.md" --poll-secs 0.05 --stall-secs 0.2 --backstop-secs 0.5
check "WD control (watchdog on) ⇒ KILLED" "$OUT" "CODEX_KILLED_TIMEOUT"
check_contains "WD control cause=stall (stall fires before backstop)" "$(wdcause "$WORK/codex-review-wdctl.md")" "Codex killed (stall)"
# --no-watchdog: STALL detector OFF ⇒ the SAME silent fake is NOT stall-killed at 0.2s; the per-attempt
# BACKSTOP still fires at 0.5s ⇒ KILLED cause=BACKSTOP. Proves BOTH halves of D-32: the stall detector
# is off (cause flips stall→backstop) AND the backstop remains the unconditional bound (bounded-run
# bypass guard). Mutation-verify: ignore --no-watchdog ⇒ cause reverts to stall ⇒ reds.
disp fake_stall wdnw slice "$WORK/codex-review-wdnw.md" --poll-secs 0.05 --stall-secs 0.2 --backstop-secs 0.5 --no-watchdog
check "WD --no-watchdog ⇒ still KILLED (backstop is unconditional)" "$OUT" "CODEX_KILLED_TIMEOUT"
check_contains "WD --no-watchdog ⇒ cause=BACKSTOP (stall off, backstop bounds)" "$(wdcause "$WORK/codex-review-wdnw.md")" "Codex killed (backstop)"
check_absent "WD --no-watchdog did NOT stall-kill" "$(wdcause "$WORK/codex-review-wdnw.md")" "Codex killed (stall)"
# DRIVE_CODEX_WATCHDOG=off env hatch is equivalent to --no-watchdog.
mwenv="$WORK/codex-review-wdenv.md"
OUT="$(DRIVE_CODEX_WATCHDOG=off DRIVE_CODEX_CMD="$BIN/fake_stall" "$HELPER" --mode dispatch --scope wdenv --scope-class slice \
   --attempt-log "$ALOG" --raw-log "$WORK/codex-raw-wdenv.log" --marker "$mwenv" --prompt-file "$PROMPT" \
   --poll-secs 0.05 --stall-secs 0.2 --backstop-secs 0.5 2>/dev/null)"
check "WD DRIVE_CODEX_WATCHDOG=off ⇒ KILLED (env hatch = --no-watchdog)" "$OUT" "CODEX_KILLED_TIMEOUT"
check_contains "WD env-off ⇒ cause=BACKSTOP" "$(wdcause "$mwenv")" "Codex killed (backstop)"

# ============================================================================= #
echo "=== FIX-1/2/3: stdin-hang + false-OK-on-degenerate-review (.harness/followups.md F5) ==="

# The codex stdin banner (pinned literal, codex v0.142.5). Real codex prints this whenever stdin
# is a non-TTY; a degenerate (inherited-open-stdin) dispatch writes ONLY this and exits rc0.
BANNER='Reading additional input from stdin...'

# fd0-SENSITIVE fake — models real codex: with inherited stdin CONTENT it degenerates to a
# banner-only log (the bug); with /dev/null EOF (FIX-1) it produces a real review. doctor never
# reads stdin (returns before the cat), so the shared inherited fd is untouched for the exec.
mkfake fake_stdin_banner \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  'data="$(cat)"' \
  'if [ -n "$data" ]; then printf "Reading additional input from stdin...\n"; exit 0; fi' \
  'printf "reviewing\nMINOR: nit\ndone\n"; exit 0'

# always banner-only regardless of stdin (the pure OK-gate degeneracy).
mkfake fake_banner_only \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  'printf "Reading additional input from stdin...\n"; exit 0'

# a REAL review whose line QUOTES the banner substring — must NOT be mis-classified banner-only
# (full-line anchored match, not a substring strip).
mkfake fake_quote_banner \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  'printf "MINOR: helper prints \"Reading additional input from stdin...\" on an inherited fd\ndone\n"; exit 0'

# DEGENERATE banner + a hidden byte (NUL) — the fail-OPEN bypass (codex adversarial). The stray byte
# must NOT let the banner text read as "real content" and slip a false OK past the gate.
mkfake fake_banner_nul \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  'printf "Reading additional input from stdin...\0\n"; exit 0'

# DEGENERATE banner wrapped in ANSI color escapes — the printable [0m residue must NOT read as content.
mkfake fake_banner_ansi \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  'printf "\033[0mReading additional input from stdin...\033[0m\n"; exit 0'

# a REAL review that is ANSI-COLORED — the ANSI strip must NOT over-strip it into a false degenerate.
mkfake fake_colored_review \
  '#!/usr/bin/env bash' \
  'case "$1" in doctor) echo ok; exit 0 ;; esac' \
  'printf "\033[31mMAJOR\033[0m: a real bug at x.py:10\n"; exit 0'

# --- FIX-1 (raw-log CONTENT; a token-only assertion is VACUOUS — OK pre AND post). The helper is
# invoked with an INHERITED OPEN-FILE stdin (content); pre-fix the backgrounded exec inherits it →
# banner-only raw log; post-fix (< /dev/null) → real review. RED pre-fix: raw lacks "MINOR". ---
printf 'inherited open stdin that never came from a prompt\n' > "$WORK/openstdin.txt"
OUT="$(timeout 30 env DRIVE_CODEX_CMD="$BIN/fake_stdin_banner" "$HELPER" --mode dispatch --scope si1 \
   --scope-class slice --attempt-log "$ALOG" --raw-log "$WORK/codex-raw-si1.log" \
   --marker "$WORK/codex-review-si1.md" --prompt-file "$PROMPT" --poll-secs 0.05 \
   < "$WORK/openstdin.txt" 2>/dev/null)"; RC=$?
if [ "$RC" = 124 ]; then fail "FIX-1 no hang on inherited open stdin (timeout hit)"; else pass "FIX-1 no hang on inherited open stdin (bounded completion)"; fi
check_contains "FIX-1 inherited open stdin ⇒ raw log holds the REAL review (redirect worked)" "$(cat "$WORK/codex-raw-si1.log" 2>/dev/null)" "MINOR"
check_absent   "FIX-1 inherited open stdin ⇒ raw log is NOT the stdin banner" "$(cat "$WORK/codex-raw-si1.log" 2>/dev/null)" "$BANNER"
check "FIX-1 inherited open stdin ⇒ token OK (real review)" "$OUT" "OK"

# --- FIX-2 (token; the OK-gate degeneracy guard). A banner-only raw log must fail CLOSED, never OK. ---
disp fake_banner_only bo1 slice "$WORK/codex-review-bo1.md" --poll-secs 0.05
check "FIX-2 banner-only raw log ⇒ CODEX_UNAVAILABLE (no false OK)" "$OUT" "CODEX_UNAVAILABLE"
check "FIX-2 banner-only ⇒ exit 1" "$RC" "1"
check "FIX-2 banner-only ⇒ marker 1st line == token" "$(head -1 "$WORK/codex-review-bo1.md" 2>/dev/null)" "CODEX_UNAVAILABLE"
check_contains "FIX-2 honest cause=degenerate-log (rc was 0, NOT exec-failed)" "$(cat "$WORK/codex-review-bo1.md" 2>/dev/null)" "degenerate-log"

# --- FIX-2 precision: a real review that QUOTES the banner is NOT banner-only ⇒ OK (guards against a
# naive substring strip, which would delete the line → banner-only → CODEX_UNAVAILABLE ⇒ this reds). ---
disp fake_quote_banner qb1 slice "$WORK/codex-review-qb1.md" --poll-secs 0.05
check "FIX-2 precision: real review quoting the banner ⇒ OK (full-line match, not substring)" "$OUT" "OK"

# --- FIX-2 robustness: banner + a hidden byte (NUL) is STILL degenerate ⇒ CODEX_UNAVAILABLE, never a
# false OK. RED against the CR-only normalizer (the stray byte broke the full-line match ⇒ false OK). ---
disp fake_banner_nul bn1 slice "$WORK/codex-review-bn1.md" --poll-secs 0.05
check "FIX-2 robustness: banner+hidden-byte (NUL) ⇒ CODEX_UNAVAILABLE (no fail-open bypass)" "$OUT" "CODEX_UNAVAILABLE"
check "FIX-2 robustness: banner+NUL ⇒ exit 1" "$RC" "1"
disp fake_banner_ansi ba1 slice "$WORK/codex-review-ba1.md" --poll-secs 0.05
check "FIX-2 robustness: banner+ANSI escapes ⇒ CODEX_UNAVAILABLE (residue not content)" "$OUT" "CODEX_UNAVAILABLE"
# guard the ANSI strip does NOT over-strip a real colored review into a false degenerate:
disp fake_colored_review cr1 slice "$WORK/codex-review-cr1.md" --poll-secs 0.05
check "FIX-2 precision: ANSI-colored REAL review ⇒ OK (strip removes color, keeps content)" "$OUT" "OK"

# --- FIX-3: a banner-only --prior-codex must NOT down-tier (degenerate prior ⇒ fail toward FULL
# effort). RED pre-fix: banner-only passes _log_nonempty + zero tags ⇒ EFFORT_LOW ⇒ argv shows medium. ---
PRIOR_BANNER="$WORK/codex-review-prior-banner.md"; printf 'Reading additional input from stdin...\n' > "$PRIOR_BANNER"
: > "$WORK/argv.log"; ARGVLOG="$WORK/argv.log" disp fake_argv fx3 slice "$WORK/codex-review-fx3.md" --poll-secs 0.05 --confirmation-class --prior-codex "$PRIOR_BANNER"
check_absent "FIX-3 banner-only --prior-codex ⇒ FULL effort (no down-tier on a degenerate prior)" "$(cat "$WORK/argv.log")" "model_reasoning_effort"

echo ""
echo "===================================================================="
printf 'drive-codex.test.sh: %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
