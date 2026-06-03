#!/usr/bin/env bash
# drive-merge-gate.test.sh — plain-bash tests for the PreToolUse merge/ship/plan gate.
# Covers AC0 (plan-gate deny/allow), AC7 (deny on all transitions + no-output cases +
# never `allow`), AC8 (deny>allow composition: multiline ship body still denies).
#
# The gate resolves RUN_DIR via $HOME/.claude/harness-runs/<runId> (drive_run_dir is
# hardcoded to that path), so each fixture's RUN_DIR lives THERE under a unique runId,
# and the matching git repo is checked out on the corresponding drive/slice/phaseInt
# refs. Everything created is tracked and trashed on exit.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$(cd "$HERE/../bin" && pwd)"
GATE="$BIN/drive-merge-gate.sh"

HARNESS_RUNS="$HOME/.claude/harness-runs"
mkdir -p "$HARNESS_RUNS"

TMPROOT="$(mktemp -d "${TMPDIR:-/tmp}/drive-gate-test.XXXXXX")"

# All RUN_DIRs this process creates share the prefix gatetest-<PID>- (mk_rundir runs
# inside command-substitution subshells, so tracking via a global var would be lost to
# the subshell — glob-remove by the PID-scoped prefix instead, which is robust).
cleanup() {
  local d
  for d in "$HARNESS_RUNS"/gatetest-$$-*; do
    [ -d "$d" ] && rm -rf "$d"
  done
  [ -d "$TMPROOT" ] && rm -rf "$TMPROOT"
}
trap cleanup EXIT

PASS=0
FAIL=0
pass() { PASS=$((PASS+1)); printf 'PASS: %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf 'FAIL: %s\n' "$1"; }

# Unique runId generator. Uses a counter FILE so it stays monotonic even when called
# from inside a command-substitution subshell (a plain global var would not persist).
_NCOUNTER="$TMPROOT/.ncounter"; printf '0' > "$_NCOUNTER"
new_runid() {
  local n; n="$(cat "$_NCOUNTER")"; n=$((n+1)); printf '%s' "$n" > "$_NCOUNTER"
  printf 'gatetest-%s-%s' "$$" "$n"
}

_gitc() { git -C "$1" -c user.name=t -c user.email=t@t -c commit.gpgsign=false "${@:2}"; }

_init_repo() {
  local r="$1"
  mkdir -p "$r"
  git -C "$r" init -q -b main
  _gitc "$r" config user.name t
  _gitc "$r" config user.email t@t
}

_commit() {
  local r="$1" p="$2" c="$3" m="$4"
  mkdir -p "$r/$(dirname "$p")"
  printf '%s\n' "$c" > "$r/$p"
  _gitc "$r" add -A
  _gitc "$r" commit -q -m "$m"
  _gitc "$r" rev-parse HEAD
}

_write_review() {
  local rd="$1" scope="$2" n="$3" sha="$4"
  mkdir -p "$rd"
  { echo "# Review $scope $n"; echo; echo "## Verdict: CONVERGED"; echo; echo "reviewed-sha: $sha"; } > "$rd/review-$scope-$n.md"
}
_write_codex() {
  local rd="$1" scope="$2"
  mkdir -p "$rd"
  { echo "codex review for $scope"; echo ok; } > "$rd/codex-review-$scope.md"
}

# Create a run dir under $HARNESS_RUNS (cleaned by the PID-prefix glob on EXIT). $1=runId
mk_rundir() {
  local runid="$1" rd="$HARNESS_RUNS/$1"
  mkdir -p "$rd"
  printf '%s\n' "$rd"
}

# Drive the gate. $1=command $2=cwd. Sets globals GATE_OUT (stdout) and GATE_RC.
# (Does NOT echo — callers read $GATE_OUT — so the hook exit code propagates to the
# current shell instead of being lost in a command-substitution subshell.)
run_gate() {
  local cmd="$1" cwd="$2" json
  json="$(jq -n --arg c "$cmd" --arg w "$cwd" '{tool_input:{command:$c},cwd:$w}')"
  printf '%s' "$json" | bash "$GATE" > "$TMPROOT/.gateout" 2>/dev/null
  GATE_RC=$?
  GATE_OUT="$(cat "$TMPROOT/.gateout")"
}

# Assert helpers operate on the captured output in $1 (the gate's stdout).
is_deny()    { printf '%s' "$1" | grep -q '"permissionDecision":"deny"'; }
is_allow()   { printf '%s' "$1" | grep -q '"permissionDecision":"allow"'; }
is_empty()   { [ -z "$1" ]; }

# ---------------------------------------------------------------------------------
# AC0 + AC7: plan-gate
# ---------------------------------------------------------------------------------

# Unreviewed plan-gate (no design review) → DENY on worktree add.
test_plangate_deny() {
  local runid rd repo
  runid="$(new_runid)"; rd="$(mk_rundir "$runid")"
  repo="$TMPROOT/$runid-repo"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null
  # No review-design-*.md written → unconverged.
  local out
  run_gate "git worktree add ../wt/4a -b slice/$runid/4a" "$repo"; out="$GATE_OUT"
  if is_deny "$out" && printf '%s' "$out" | grep -q '/drive-review design'; then
    pass "plan-gate denies unreviewed worktree add (names /drive-review design)"
  else
    fail "plan-gate should deny unreviewed worktree add; got: $out"
  fi
}

# Reviewed plan-gate → no output, exit 0.
test_plangate_allow_silent() {
  local runid rd repo
  runid="$(new_runid)"; rd="$(mk_rundir "$runid")"
  repo="$TMPROOT/$runid-repo"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null
  _write_review "$rd" design 1 "$(printf '0%.0s' {1..40})"
  _write_codex "$rd" design
  local out
  run_gate "git worktree add ../wt/4a -b slice/$runid/4a" "$repo"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ] && ! is_allow "$out"; then
    pass "plan-gate silent (no output, exit 0, never allow) when design reviewed"
  else
    fail "plan-gate should be silent when reviewed; got rc=$GATE_RC out='$out'"
  fi
}

# ---------------------------------------------------------------------------------
# AC7: slice-merge
# ---------------------------------------------------------------------------------

# Build a repo with a slice branch; optionally write its review. Echoes "repo rd tip".
mk_slice_repo() {
  local runid="$1" reviewed="$2" rd repo tip
  rd="$(mk_rundir "$runid")"
  repo="$TMPROOT/$runid-repo"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null
  _gitc "$repo" checkout -q -b "slice/$runid/4a"
  tip="$(_commit "$repo" feature.sh "echo hi" "slice 4a")"
  _gitc "$repo" checkout -q main
  if [ "$reviewed" = reviewed ]; then
    _write_review "$rd" 4a 1 "$tip"
    _write_codex "$rd" 4a
  fi
  printf '%s %s %s\n' "$repo" "$rd" "$tip"
}

test_slicemerge_deny() {
  local runid info repo
  runid="$(new_runid)"; info="$(mk_slice_repo "$runid" unreviewed)"; repo="${info%% *}"
  local out
  run_gate "git merge --no-ff slice/$runid/4a" "$repo"; out="$GATE_OUT"
  if is_deny "$out" && printf '%s' "$out" | grep -q '/drive-review slice 4a'; then
    pass "slice-merge denies unreviewed merge (names /drive-review slice 4a)"
  else
    fail "slice-merge should deny unreviewed; got: $out"
  fi
}

test_slicemerge_allow_silent() {
  local runid info repo
  runid="$(new_runid)"; info="$(mk_slice_repo "$runid" reviewed)"; repo="${info%% *}"
  local out
  run_gate "git merge --no-ff slice/$runid/4a" "$repo"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ] && ! is_allow "$out"; then
    pass "slice-merge silent when reviewed"
  else
    fail "slice-merge should be silent when reviewed; got rc=$GATE_RC out='$out'"
  fi
}

# ---------------------------------------------------------------------------------
# AC7: phase-merge
# ---------------------------------------------------------------------------------

mk_phase_repo() {
  local runid="$1" reviewed="$2" rd repo tip
  rd="$(mk_rundir "$runid")"
  repo="$TMPROOT/$runid-repo"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null
  _gitc "$repo" checkout -q -b "drive/$runid"
  _gitc "$repo" checkout -q -b "phaseInt/$runid/1"
  tip="$(_commit "$repo" code.sh "echo phase1" "phase 1")"
  _gitc "$repo" checkout -q "drive/$runid"
  if [ "$reviewed" = reviewed ]; then
    _write_review "$rd" phase1 1 "$tip"
    _write_codex "$rd" phase1
  fi
  printf '%s %s\n' "$repo" "$rd"
}

test_phasemerge_deny() {
  local runid info repo
  runid="$(new_runid)"; info="$(mk_phase_repo "$runid" unreviewed)"; repo="${info%% *}"
  local out
  run_gate "git branch -f drive/$runid phaseInt/$runid/1" "$repo"; out="$GATE_OUT"
  if is_deny "$out" && printf '%s' "$out" | grep -q '/drive-review phase 1'; then
    pass "phase-merge denies unreviewed branch -f advance (names /drive-review phase 1)"
  else
    fail "phase-merge should deny unreviewed; got: $out"
  fi
}

# ---------------------------------------------------------------------------------
# AC7 + AC8: ship (multiple forms) + deny>allow composition
# ---------------------------------------------------------------------------------

# Build a drive-branch repo whose tip is NOT covered by any converged review (unreviewed
# ship). Echoes "repo rd".
mk_ship_repo() {
  local runid="$1" rd repo
  rd="$(mk_rundir "$runid")"
  repo="$TMPROOT/$runid-repo"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null
  _gitc "$repo" checkout -q -b "drive/$runid"
  _commit "$repo" feature.sh "echo hi" "unreviewed code" >/dev/null
  # No phase review → ship conformance violation (exit 1).
  printf '%s %s\n' "$repo" "$rd"
}

test_ship_gh_pr_create() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "gh pr create --title x --body y" "$repo"; out="$GATE_OUT"
  if is_deny "$out" && printf '%s' "$out" | grep -q '/drive-review ship'; then
    pass "ship denies unreviewed gh pr create"
  else
    fail "ship should deny gh pr create; got: $out"
  fi
}

test_ship_bare_push() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "git push" "$repo"; out="$GATE_OUT"
  if is_deny "$out"; then
    pass "ship denies unreviewed bare git push (runId from HEAD)"
  else
    fail "ship should deny bare git push; got: $out"
  fi
}

test_ship_push_u_origin_head() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "git push -u origin HEAD" "$repo"; out="$GATE_OUT"
  if is_deny "$out"; then
    pass "ship denies unreviewed git push -u origin HEAD"
  else
    fail "ship should deny git push -u origin HEAD; got: $out"
  fi
}

test_ship_glab_mr_create() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "glab mr create --fill" "$repo"; out="$GATE_OUT"
  if is_deny "$out"; then
    pass "ship denies unreviewed glab mr create"
  else
    fail "ship should deny glab mr create; got: $out"
  fi
}

# Reviewed ship (phase review whose reviewed-sha == drive tip) → silent, exit 0.
mk_ship_repo_reviewed() {
  local runid="$1" rd repo tip
  rd="$(mk_rundir "$runid")"
  repo="$TMPROOT/$runid-repo"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null
  _gitc "$repo" checkout -q -b "drive/$runid"
  tip="$(_commit "$repo" feature.sh "echo hi" "phase 1 code")"
  _write_review "$rd" phase1 1 "$tip"   # reviewed-sha == drive tip → ship clean
  _write_codex "$rd" phase1
  printf '%s %s\n' "$repo" "$rd"
}

test_ship_reviewed_silent() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo_reviewed "$runid")"; repo="${info%% *}"
  run_gate "gh pr create --title x --body y" "$repo"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ] && ! is_allow "$out"; then
    pass "ship silent (no output, exit 0) when fully reviewed"
  else
    fail "ship should be silent when reviewed; got rc=$GATE_RC out='$out'"
  fi
}

# AC8: multiline body ship still denies (deny>allow composition).
test_ship_multiline_body() {
  local runid info repo out cmd
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  cmd="$(printf 'gh pr create --body %s' "$'a\nb'")"
  run_gate "$cmd" "$repo"; out="$GATE_OUT"
  if is_deny "$out"; then
    pass "AC8: multiline gh pr create --body \$'a\\nb' still denies"
  else
    fail "AC8: multiline ship should still deny; got: $out"
  fi
}

# ---------------------------------------------------------------------------------
# Negative / inert cases
# ---------------------------------------------------------------------------------

# Non-matching command → no output, exit 0.
test_nonmatching_inert() {
  local out
  run_gate "ls -la /tmp" "$TMPROOT"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ]; then
    pass "non-matching command is inert (no output, exit 0)"
  else
    fail "non-matching command should be inert; got rc=$GATE_RC out='$out'"
  fi
}

# A drive-shaped command whose runId has NO RUN_DIR → inert.
test_unmanaged_run_inert() {
  local out
  run_gate "git merge slice/nonexistent-run-xyz/4a" "$TMPROOT"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ]; then
    pass "unmanaged run (no RUN_DIR) is inert"
  else
    fail "unmanaged run should be inert; got rc=$GATE_RC out='$out'"
  fi
}

# Ship from a non-drive branch (HEAD not drive/*) → inert (no runId resolves).
test_ship_nondrive_branch_inert() {
  local runid repo out
  runid="$(new_runid)"
  repo="$TMPROOT/$runid-repo"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null   # stays on main
  run_gate "git push" "$repo"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ]; then
    pass "ship from non-drive branch is inert"
  else
    fail "ship from non-drive branch should be inert; got rc=$GATE_RC out='$out'"
  fi
}

# Never emits allow under any tested path (sanity sweep already covered per-test).
test_never_allow() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "gh pr create" "$repo"; out="$GATE_OUT"
  if ! is_allow "$out"; then
    pass "gate never emits allow (deny-only contract)"
  else
    fail "gate must never emit allow; got: $out"
  fi
}

# ---------------------------------------------------------------------------------
main() {
  command -v jq >/dev/null 2>&1 || { echo "FAIL: jq not found"; exit 1; }
  test_plangate_deny
  test_plangate_allow_silent
  test_slicemerge_deny
  test_slicemerge_allow_silent
  test_phasemerge_deny
  test_ship_gh_pr_create
  test_ship_bare_push
  test_ship_push_u_origin_head
  test_ship_glab_mr_create
  test_ship_reviewed_silent
  test_ship_multiline_body
  test_nonmatching_inert
  test_unmanaged_run_inert
  test_ship_nondrive_branch_inert
  test_never_allow

  echo
  echo "----------------------------------------"
  printf 'TOTAL: %d passed, %d failed\n' "$PASS" "$FAIL"
  [ "$FAIL" -eq 0 ]
}

main "$@"
