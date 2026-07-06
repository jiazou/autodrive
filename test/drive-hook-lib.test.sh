#!/usr/bin/env bash
# Tests for bin/drive-hook-lib.sh (AC6). Plain bash, no bats.
# Prints PASS/FAIL per case; exits nonzero on any failure.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$HERE/../bin/drive-hook-lib.sh"

# shellcheck source=/dev/null
source "$LIB"

fail=0
pass() { printf 'PASS: %s\n' "$1"; }
bad()  { printf 'FAIL: %s\n' "$1"; fail=1; }

# assert_eq <name> <expected> <actual> <rc>
assert_eq() {
  local name="$1" expected="$2" actual="$3" rc="$4"
  if [ "$rc" -eq 0 ] && [ "$actual" = "$expected" ]; then
    pass "$name (=> '$actual', rc0)"
  else
    bad "$name (expected '$expected' rc0; got '$actual' rc$rc)"
  fi
}

# assert_rc1 <name> <actual> <rc>
assert_rc1() {
  local name="$1" actual="$2" rc="$3"
  if [ "$rc" -ne 0 ]; then
    pass "$name (rc$rc, out='$actual')"
  else
    bad "$name (expected rc1; got rc0 out='$actual')"
  fi
}

# --- drive_runid_from_command: positives ---
out="$(drive_runid_from_command "git merge x slice/R/4a")"; rc=$?
assert_eq "from_command slice/R/4a" "R" "$out" "$rc"

out="$(drive_runid_from_command "git branch -f drive/R phaseInt/R/1")"; rc=$?
assert_eq "from_command drive/R first-token" "R" "$out" "$rc"

# dotted slice id
out="$(drive_runid_from_command "git merge --no-ff slice/myrun-123/1.2")"; rc=$?
assert_eq "from_command slice dotted id 1.2" "myrun-123" "$out" "$rc"

# realistic runId with timestamp
RID="drive-review-hooks-20260603-135659"
out="$(drive_runid_from_command "git worktree add wt -b slice/$RID/4a")"; rc=$?
assert_eq "from_command realistic runId" "$RID" "$out" "$rc"

# phaseInt token alone
out="$(drive_runid_from_command "git merge phaseInt/$RID/2")"; rc=$?
assert_eq "from_command phaseInt token" "$RID" "$out" "$rc"

# --- drive_runid_from_command: negatives ---
out="$(drive_runid_from_command "git commit -m 'no drive ref here'")"; rc=$?
assert_rc1 "from_command non-drive command" "$out" "$rc"

out="$(drive_runid_from_command "git push origin main")"; rc=$?
assert_rc1 "from_command unrelated branch" "$out" "$rc"

out="$(drive_runid_from_command "")"; rc=$?
assert_rc1 "from_command empty string" "$out" "$rc"

# bare 'slice/X' with no id should NOT match (needs slice/<runId>/<id>)
out="$(drive_runid_from_command "git checkout slice/onlyrun")"; rc=$?
assert_rc1 "from_command slice/ without id" "$out" "$rc"

# --- drive_runid_from_command: quoting / refspec / glob safety (BLOCKING fix) ---
# double-quoted ref: must NOT bypass (no word-split => quotes excluded from token)
out="$(drive_runid_from_command 'git merge "slice/R/4a"')"; rc=$?
assert_eq "from_command double-quoted slice ref" "R" "$out" "$rc"

# single-quoted ref
out="$(drive_runid_from_command "git merge 'slice/R/4a'")"; rc=$?
assert_eq "from_command single-quoted slice ref" "R" "$out" "$rc"

# refspec src:dst — stops at ':' so resolves the src side (drive/R), not 'R:drive'
out="$(drive_runid_from_command "git push origin drive/R:drive/R")"; rc=$?
assert_eq "from_command refspec drive/R:drive/R" "R" "$out" "$rc"

# refspec HEAD:refs/heads/slice/R/4a — token starts at slice/, resolves R
out="$(drive_runid_from_command "git push origin HEAD:refs/heads/slice/R/4a")"; rc=$?
assert_eq "from_command refspec HEAD:refs/heads/slice" "R" "$out" "$rc"

# a literal '*' in the command must not glob and must still resolve the ref
out="$(drive_runid_from_command "git log --grep=* drive/R")"; rc=$?
assert_eq "from_command with literal star" "R" "$out" "$rc"

# --- drive_runid_from_command: exact-segment rejection (MINOR fix) ---
out="$(drive_runid_from_command "git checkout drive/R/extra")"; rc=$?
assert_rc1 "from_command drive/R/extra rejected" "$out" "$rc"

out="$(drive_runid_from_command "git merge slice/R/4a/extra")"; rc=$?
assert_rc1 "from_command slice/R/4a/extra rejected" "$out" "$rc"

out="$(drive_runid_from_command "git merge phaseInt/R/1/extra")"; rc=$?
assert_rc1 "from_command phaseInt/R/1/extra rejected" "$out" "$rc"

# bare phaseInt/<runId> with no <P> should NOT match
out="$(drive_runid_from_command "git checkout phaseInt/onlyrun")"; rc=$?
assert_rc1 "from_command phaseInt/ without P" "$out" "$rc"

# --- drive_runid_from_command: LEFT segment boundary (MAJOR fix) ---
# keyword must be at a left segment boundary (start-of-string OR a char that is
# NOT [A-Za-z0-9._-]). Larger unmanaged names must NOT match.
out="$(drive_runid_from_command "git checkout nondrive/R")"; rc=$?
assert_rc1 "from_command nondrive/R rejected" "$out" "$rc"

out="$(drive_runid_from_command "git checkout noslice/R/4a")"; rc=$?
assert_rc1 "from_command noslice/R/4a rejected" "$out" "$rc"

out="$(drive_runid_from_command "git checkout foo-phaseInt/R/1")"; rc=$?
assert_rc1 "from_command foo-phaseInt/R/1 rejected" "$out" "$rc"

# '/' IS a valid boundary: path-prefixed managed refs still resolve.
out="$(drive_runid_from_command "git checkout refs/heads/drive/R")"; rc=$?
assert_eq "from_command refs/heads/drive/R resolves" "R" "$out" "$rc"

out="$(drive_runid_from_command "git push origin HEAD:refs/heads/slice/R/4a")"; rc=$?
assert_eq "from_command path-prefixed slice resolves" "R" "$out" "$rc"

# --- drive_runid_from_head: positive (throwaway repo) ---
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
(
  git -C "$TMP" init -q
  git -C "$TMP" config user.email t@t.t
  git -C "$TMP" config user.name t
  : > "$TMP/f"
  git -C "$TMP" add -A
  git -C "$TMP" commit -qm init
  git -C "$TMP" checkout -q -b "drive/$RID"
) >/dev/null 2>&1

out="$(drive_runid_from_head "$TMP")"; rc=$?
assert_eq "from_head drive/<runId> checkout" "$RID" "$out" "$rc"

# non-drive HEAD
git -C "$TMP" checkout -q -b feature/other >/dev/null 2>&1
out="$(drive_runid_from_head "$TMP")"; rc=$?
assert_rc1 "from_head non-drive branch" "$out" "$rc"

# drive/<runId>/extra is NOT the feature branch (exact 2-segment required)
git -C "$TMP" checkout -q -b "drive/$RID/extra" >/dev/null 2>&1
out="$(drive_runid_from_head "$TMP")"; rc=$?
assert_rc1 "from_head drive/<runId>/extra rejected" "$out" "$rc"

# not a git repo
NOGIT="$(mktemp -d)"
out="$(drive_runid_from_head "$NOGIT")"; rc=$?
assert_rc1 "from_head non-git dir" "$out" "$rc"
rm -rf "$NOGIT"

# --- drive_run_dir ---
# existing dir (this run's own dir resolves under $HOME)
out="$(drive_run_dir "$RID")"; rc=$?
if [ -d "$HOME/.claude/harness-runs/$RID" ]; then
  assert_eq "run_dir existing" "$HOME/.claude/harness-runs/$RID" "$out" "$rc"
else
  # Fabricate one to exercise the positive path deterministically.
  FAKE="$HOME/.claude/harness-runs/__hooklib_test_$$"
  mkdir -p "$FAKE"
  out="$(drive_run_dir "__hooklib_test_$$")"; rc=$?
  assert_eq "run_dir existing (fabricated)" "$FAKE" "$out" "$rc"
  rmdir "$FAKE"
fi

# missing dir
out="$(drive_run_dir "definitely-not-a-real-run-$$")"; rc=$?
assert_rc1 "run_dir missing" "$out" "$rc"

# empty arg
out="$(drive_run_dir "")"; rc=$?
assert_rc1 "run_dir empty arg" "$out" "$rc"

# --- drive_scan_active_runs (AC-1/AC-3): the SHARED active-run predicate extracted from the
#     shipped drive-tool-gate.sh inline scan. Byte-faithful: state.json a regular file that
#     jq-parses with .stage non-empty and != "done" AND .repoRoot non-empty, within the
#     DRIVE_TOOL_GATE_LIVE_HOURS mtime window; corrupt/no-repoRoot skip WITH a stderr warning.
#     Dedicated HOME so the scan root is isolated (the function keys on $HOME). ---
SCAN_HOME="$(mktemp -d)"
OLD_HOME="$HOME"
export HOME="$SCAN_HOME"
SRUNS="$HOME/.claude/harness-runs"; mkdir -p "$SRUNS"
sc_mkrun() { # sc_mkrun <id> <stage> <repoRoot>  — fresh-mtime run dir
  local rd="$SRUNS/$1"; mkdir -p "$rd"
  printf '{"stage":"%s","repoRoot":"%s"}\n' "$2" "$3" > "$rd/state.json"
  printf '' > "$rd/event-log.jsonl"
}

# (a) one fresh active run → emitted, rc 0
rm -rf "$SRUNS"/*; sc_mkrun run-a execute /some/repo
out="$(drive_scan_active_runs 2>/dev/null)"; rc=$?
assert_eq "scan: active run emitted" "$SRUNS/run-a" "$out" "$rc"

# (b) stage=done → not emitted, rc 1
rm -rf "$SRUNS"/*; sc_mkrun run-done done /some/repo
out="$(drive_scan_active_runs 2>/dev/null)"; rc=$?
assert_rc1 "scan: stage=done not active" "$out" "$rc"

# (c) no repoRoot → not emitted (rc1) + stderr warning names the dir
rm -rf "$SRUNS"/*; mkdir -p "$SRUNS/run-noroot"
printf '{"stage":"execute"}\n' > "$SRUNS/run-noroot/state.json"; printf '' > "$SRUNS/run-noroot/event-log.jsonl"
err="$(mktemp)"; out="$(drive_scan_active_runs 2>"$err")"; rc=$?
assert_rc1 "scan: no-repoRoot not active" "$out" "$rc"
case "$(cat "$err")" in *"no repoRoot"*"run-noroot"*) pass "scan: no-repoRoot warns naming the dir" ;; *) bad "scan: no-repoRoot warning missing (got '$(cat "$err")')" ;; esac

# (d) corrupt state.json → not emitted (rc1) + skip-with-warning; a healthy run alongside still emits
rm -rf "$SRUNS"/*; mkdir -p "$SRUNS/run-corrupt"
printf 'GARBAGE {{{ not json' > "$SRUNS/run-corrupt/state.json"; printf '' > "$SRUNS/run-corrupt/event-log.jsonl"
sc_mkrun run-healthy execute /some/repo
err="$(mktemp)"; out="$(drive_scan_active_runs 2>"$err")"; rc=$?
assert_eq "scan: healthy run emitted past corrupt one" "$SRUNS/run-healthy" "$out" "$rc"
case "$(cat "$err")" in *"unreadable/corrupt state.json"*"run-corrupt"*) pass "scan: corrupt dir skip-with-warning names it" ;; *) bad "scan: corrupt warning missing (got '$(cat "$err")')" ;; esac

# (e) stale mtime (year 2000) → outside the 24h window → not emitted
rm -rf "$SRUNS"/*; sc_mkrun run-stale execute /some/repo
touch -t 200001010000 "$SRUNS/run-stale/state.json" "$SRUNS/run-stale/event-log.jsonl"
out="$(drive_scan_active_runs 2>/dev/null)"; rc=$?
assert_rc1 "scan: stale-mtime run not active (liveness window)" "$out" "$rc"

# (f) two active runs → both emitted (newline-separated; trailing newline preserved, which
#     the tool-gate's $(...) strips — the same shape as the shipped inline scan)
rm -rf "$SRUNS"/*; sc_mkrun run-x execute /r1; sc_mkrun run-y execute /r2
allout="$(drive_scan_active_runs 2>/dev/null)"
n="$(printf '%s' "$allout" | grep -c 'harness-runs/run-')"
assert_eq "scan: two active runs both emitted" "2" "$n" "0"
case "$allout" in *run-x*) case "$allout" in *run-y*) pass "scan: both run-x and run-y present" ;; *) bad "scan: run-y missing" ;; esac ;; *) bad "scan: run-x missing" ;; esac

# AC-3 (mutation-verify, documented): breaking drive_scan_active_runs (e.g. dropping the
# `[ "$stage" = "done" ] && continue` line, or the repoRoot check) REDs the shipped
# drive-tool-gate.test.sh AC-5 (stage=done → silent) / Fix5 (no-repoRoot skip) cases, since
# the tool gate now calls this extracted function — proving the tool-gate suite exercises the
# extracted path. Confirmed RED during implement, then restored.

export HOME="$OLD_HOME"
rm -rf "$SCAN_HOME"

echo "---"
if [ "$fail" -ne 0 ]; then
  echo "RESULT: FAIL"
  exit 1
fi
echo "RESULT: PASS"
