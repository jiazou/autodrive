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

echo "---"
if [ "$fail" -ne 0 ]; then
  echo "RESULT: FAIL"
  exit 1
fi
echo "RESULT: PASS"
