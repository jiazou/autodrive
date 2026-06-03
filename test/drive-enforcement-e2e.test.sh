#!/usr/bin/env bash
# drive-enforcement-e2e.test.sh — END-TO-END integration test for the /drive
# review-enforcement chain.
#
# The per-component unit tests (drive-conformance / drive-merge-gate / drive-hook-lib /
# drive-stop-guard / install-drive-hooks) already exist. THIS test exercises the WHOLE
# lifecycle composed together: it installs the hooks the way `bin/install-drive-hooks.sh`
# does into a TEMP settings.json, reads back the EXACT installed hook command, and drives
# THAT real script the way Claude Code does — by piping Claude-Code-shaped hook JSON to
# its stdin — walking the full gate chain (plan-gate → slice-merge → phase-merge → ship),
# asserting DENY-then-ALLOW as the SHA-bound review artifacts are added, plus the
# asymmetric fail-mode (ship fail-closed / slice fail-open) and the Stop backstop.
#
# Hermeticity model:
#   - drive-hook-lib.sh hardcodes RUN_DIR resolution to $HOME/.claude/harness-runs/<runId>.
#     We do NOT override $HOME (the installed hook command is a bare path; we want it run
#     exactly as Claude Code would). Instead every RUN_DIR uses a unique, PID-scoped
#     runId prefix (e2e-test-$$-N) under the REAL $HOME/.claude/harness-runs, and the
#     EXIT trap glob-removes every fixture by that prefix.
#   - The settings.json is a TEMP file; the real ~/.claude/settings.json is NEVER touched.
#   - Throwaway git repos live under a mktemp dir, also trashed on EXIT.
#
# Plain bash, no bats, bash-3.2-safe (macOS /bin/bash). Prints PASS/FAIL per assertion;
# exits nonzero if any fail; ends with `TOTAL: N passed, M failed`.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
BIN="$ROOT/bin"
INSTALLER="$BIN/install-drive-hooks.sh"
STOP_GUARD_PATH="$BIN/drive-stop-guard.sh"
MERGE_GATE_PATH="$BIN/drive-merge-gate.sh"

command -v jq >/dev/null 2>&1 || { echo "FAIL: jq is required but not found"; exit 1; }

HARNESS_RUNS="$HOME/.claude/harness-runs"
mkdir -p "$HARNESS_RUNS"

TMPROOT="$(mktemp -d "${TMPDIR:-/tmp}/drive-e2e.XXXXXX")"

# Clean up ALL fixtures: every RUN_DIR under the PID prefix + the temp tree.
cleanup() {
  local d
  for d in "$HARNESS_RUNS"/e2e-test-$$-*; do
    [ -d "$d" ] && rm -rf "$d"
  done
  [ -d "$TMPROOT" ] && rm -rf "$TMPROOT"
}
trap cleanup EXIT

PASS=0
FAIL=0
pass() { PASS=$((PASS+1)); printf 'PASS: %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf 'FAIL: %s\n' "$1"; }

# Monotonic unique runId; counter in a FILE so it survives command-substitution subshells.
_NCOUNTER="$TMPROOT/.ncounter"; printf '0' > "$_NCOUNTER"
new_runid() {
  local n; n="$(cat "$_NCOUNTER")"; n=$((n+1)); printf '%s' "$n" > "$_NCOUNTER"
  printf 'e2e-test-%s-%s' "$$" "$n"
}

# git scoped via -C, deterministic identity, signing off.
_gitc() { git -C "$1" -c user.name=t -c user.email=t@t -c commit.gpgsign=false "${@:2}"; }
_init_repo() {
  local r="$1"; mkdir -p "$r"; git -C "$r" init -q -b main
  _gitc "$r" config user.name t; _gitc "$r" config user.email t@t
}
# Commit a file and echo the new HEAD sha.
_commit() {
  local r="$1" p="$2" c="$3" m="$4"
  mkdir -p "$r/$(dirname "$p")"; printf '%s\n' "$c" > "$r/$p"
  _gitc "$r" add -A; _gitc "$r" commit -q -m "$m"; _gitc "$r" rev-parse HEAD
}
# Write a COUNTING review artifact: CONVERGED verdict + reviewed-sha bound to $sha.
_write_review() {
  local rd="$1" scope="$2" n="$3" sha="$4"; mkdir -p "$rd"
  { echo "# review $scope $n"; echo; echo "## Verdict: CONVERGED"; echo; echo "reviewed-sha: $sha"; } \
    > "$rd/review-$scope-$n.md"
}
_write_codex() {
  local rd="$1" scope="$2"; mkdir -p "$rd"
  { echo "codex review for $scope"; echo ok; } > "$rd/codex-review-$scope.md"
}
mk_rundir() { local rd="$HARNESS_RUNS/$1"; mkdir -p "$rd"; printf '%s\n' "$rd"; }

# --- Drive the REAL installed gate. $1=hook-command-path $2=command $3=cwd.
# Sets globals GATE_OUT (stdout) and GATE_RC. We invoke the path read back from the
# installed settings.json — proving the test drives what Claude Code would actually run.
run_installed_gate() {
  local hook="$1" cmd="$2" cwd="$3" json
  json="$(jq -nc --arg c "$cmd" --arg w "$cwd" '{tool_input:{command:$c},cwd:$w}')"
  printf '%s' "$json" | "$hook" > "$TMPROOT/.gateout" 2>/dev/null
  GATE_RC=$?
  GATE_OUT="$(cat "$TMPROOT/.gateout")"
}

# Drive the REAL installed Stop guard. $1=hook-path $2=cwd. Sets STOP_OUT/STOP_RC.
run_installed_stop() {
  local hook="$1" cwd="$2" json
  json="$(jq -nc --arg cwd "$cwd" '{cwd:$cwd, stop_hook_active:false}')"
  STOP_OUT="$(printf '%s' "$json" | "$hook" 2>/dev/null)"
  STOP_RC=$?
}

is_deny()  { printf '%s' "$1" | grep -q '"permissionDecision":"deny"'; }
is_allow() { printf '%s' "$1" | grep -q '"permissionDecision":"allow"'; }
is_empty() { [ -z "$1" ]; }

# =================================================================================
# STAGE 0: install the hooks into a TEMP settings.json and read back the real paths.
# =================================================================================
SETTINGS="$TMPROOT/settings.json"
INSTALLED_GATE=""
INSTALLED_STOP=""

stage_install() {
  # Pre-seed an UNRELATED existing hook to prove preservation/idempotency composition.
  printf '%s\n' '{"hooks":{"PreToolUse":[{"matcher":"Read","hooks":[{"type":"command","command":"/pre-existing.sh"}]}]}}' \
    > "$SETTINGS"

  if ! bash "$INSTALLER" "$SETTINGS" >/dev/null 2>&1; then
    fail "installer exited nonzero writing $SETTINGS"
    return
  fi

  # Read back the EXACT installed commands from settings.json (this is what Claude Code runs).
  INSTALLED_GATE="$(jq -r '.hooks.PreToolUse[]? | select(.matcher=="Bash") | .hooks[]?.command' "$SETTINGS" 2>/dev/null | head -n1)"
  INSTALLED_STOP="$(jq -r '.hooks.Stop[]? | .hooks[]?.command' "$SETTINGS" 2>/dev/null | head -n1)"

  if [ "$INSTALLED_GATE" = "$MERGE_GATE_PATH" ] && [ -x "$INSTALLED_GATE" ]; then
    pass "install: PreToolUse(Bash) hook landed and points at $MERGE_GATE_PATH"
  else
    fail "install: PreToolUse(Bash) hook wrong; got '$INSTALLED_GATE' want '$MERGE_GATE_PATH'"
  fi
  if [ "$INSTALLED_STOP" = "$STOP_GUARD_PATH" ] && [ -x "$INSTALLED_STOP" ]; then
    pass "install: Stop hook landed and points at $STOP_GUARD_PATH"
  else
    fail "install: Stop hook wrong; got '$INSTALLED_STOP' want '$STOP_GUARD_PATH'"
  fi

  # The pre-existing unrelated hook must survive.
  if jq -e '.hooks.PreToolUse[]? | select(.matcher=="Read")' "$SETTINGS" >/dev/null 2>&1; then
    pass "install: pre-existing unrelated PreToolUse(Read) hook preserved"
  else
    fail "install: pre-existing PreToolUse(Read) hook was clobbered"
  fi

  # Idempotency: a second install must NOT duplicate the Bash gate entry.
  bash "$INSTALLER" "$SETTINGS" >/dev/null 2>&1
  local nbash
  nbash="$(jq '[.hooks.PreToolUse[]? | select(.matcher=="Bash") | .hooks[]? | select(.command==$g)] | length' \
    --arg g "$MERGE_GATE_PATH" "$SETTINGS" 2>/dev/null)"
  if [ "$nbash" = "1" ]; then
    pass "install: idempotent (re-run adds no duplicate Bash gate)"
  else
    fail "install: re-run duplicated the Bash gate (count=$nbash)"
  fi
}

# =================================================================================
# STAGE 1: plan-gate — DENY (no design review) then ALLOW (design review + codex).
# =================================================================================
stage_plan_gate() {
  local runid rd repo
  runid="$(new_runid)"; rd="$(mk_rundir "$runid")"
  repo="$TMPROOT/$runid-repo"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null
  _commit "$repo" design.md "the design" "add design" >/dev/null

  local cmd="git worktree add ../wt/4a -b slice/$runid/4a HEAD"

  # No design review yet → DENY, naming /drive-review design.
  run_installed_gate "$INSTALLED_GATE" "$cmd" "$repo"
  if is_deny "$GATE_OUT" && printf '%s' "$GATE_OUT" | grep -q '/drive-review design'; then
    pass "plan-gate: DENY worktree add with NO design review (names /drive-review design)"
  else
    fail "plan-gate: expected DENY naming design review; got rc=$GATE_RC out='$GATE_OUT'"
  fi

  # Add CONVERGED design review + codex → silent ALLOW (exit 0, no output, never allow).
  _write_review "$rd" design 1 "$(printf '0%.0s' {1..40})"
  _write_codex "$rd" design
  run_installed_gate "$INSTALLED_GATE" "$cmd" "$repo"
  if is_empty "$GATE_OUT" && [ "$GATE_RC" -eq 0 ] && ! is_allow "$GATE_OUT"; then
    pass "plan-gate: ALLOW (silent) once design review CONVERGED + codex present"
  else
    fail "plan-gate: expected silent allow; got rc=$GATE_RC out='$GATE_OUT'"
  fi
}

# =================================================================================
# STAGE 2: slice-merge — DENY (no slice review) then ALLOW (reviewed-sha == slice tip).
# =================================================================================
stage_slice_merge() {
  local runid rd repo tip
  runid="$(new_runid)"; rd="$(mk_rundir "$runid")"
  repo="$TMPROOT/$runid-repo"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null
  _gitc "$repo" checkout -q -b "slice/$runid/4a"
  tip="$(_commit "$repo" feature.sh "echo hi" "slice 4a work")"
  _gitc "$repo" checkout -q main

  local cmd="git merge --no-ff slice/$runid/4a"

  run_installed_gate "$INSTALLED_GATE" "$cmd" "$repo"
  if is_deny "$GATE_OUT" && printf '%s' "$GATE_OUT" | grep -q '/drive-review slice 4a'; then
    pass "slice-merge: DENY merge with NO slice review (names /drive-review slice 4a)"
  else
    fail "slice-merge: expected DENY naming slice 4a; got rc=$GATE_RC out='$GATE_OUT'"
  fi

  # Review bound to the EXACT slice tip + codex → silent ALLOW.
  _write_review "$rd" 4a 1 "$tip"
  _write_codex "$rd" 4a
  run_installed_gate "$INSTALLED_GATE" "$cmd" "$repo"
  if is_empty "$GATE_OUT" && [ "$GATE_RC" -eq 0 ] && ! is_allow "$GATE_OUT"; then
    pass "slice-merge: ALLOW (silent) once reviewed-sha == slice tip + codex present"
  else
    fail "slice-merge: expected silent allow; got rc=$GATE_RC out='$GATE_OUT'"
  fi
}

# =================================================================================
# STAGE 3: phase-merge — DENY (no phase review) then ALLOW (reviewed-sha == phaseInt tip).
# =================================================================================
stage_phase_merge() {
  local runid rd repo tip
  runid="$(new_runid)"; rd="$(mk_rundir "$runid")"
  repo="$TMPROOT/$runid-repo"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null
  _gitc "$repo" checkout -q -b "drive/$runid"
  _gitc "$repo" checkout -q -b "phaseInt/$runid/1"
  tip="$(_commit "$repo" code.sh "echo phase1" "phase 1 integration")"
  _gitc "$repo" checkout -q "drive/$runid"

  local cmd="git branch -f drive/$runid phaseInt/$runid/1"

  run_installed_gate "$INSTALLED_GATE" "$cmd" "$repo"
  if is_deny "$GATE_OUT" && printf '%s' "$GATE_OUT" | grep -q '/drive-review phase 1'; then
    pass "phase-merge: DENY branch -f advance with NO phase review (names /drive-review phase 1)"
  else
    fail "phase-merge: expected DENY naming phase 1; got rc=$GATE_RC out='$GATE_OUT'"
  fi

  _write_review "$rd" phase1 1 "$tip"
  _write_codex "$rd" phase1
  run_installed_gate "$INSTALLED_GATE" "$cmd" "$repo"
  if is_empty "$GATE_OUT" && [ "$GATE_RC" -eq 0 ] && ! is_allow "$GATE_OUT"; then
    pass "phase-merge: ALLOW (silent) once reviewed-sha == phaseInt tip + codex present"
  else
    fail "phase-merge: expected silent allow; got rc=$GATE_RC out='$GATE_OUT'"
  fi
}

# =================================================================================
# STAGE 4: ship — DENY (tip NOT covered) then ALLOW (tip covered by a ledger-only commit
# past the last counting review, exercising the existential-R + .harness allowlist + ≤1-commit rule).
# =================================================================================
stage_ship() {
  local runid rd repo rsha tip
  runid="$(new_runid)"; rd="$(mk_rundir "$runid")"
  repo="$TMPROOT/$runid-repo"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null
  _gitc "$repo" checkout -q -b "drive/$runid"
  rsha="$(_commit "$repo" feature.sh "echo hi" "phase 1 code")"
  # Add an UNREVIEWED commit past the reviewed sha → tip not covered.
  tip="$(_commit "$repo" extra.sh "echo more" "unreviewed extra code")"

  # Write a phase review bound to rsha (NOT the current tip) + codex. tip is uncovered:
  #   rsha..tip = 1 commit but extra.sh is NOT in the .harness allowlist → diff ⊄ allowlist.
  _write_review "$rd" phase1 1 "$rsha"
  _write_codex "$rd" phase1

  run_installed_gate "$INSTALLED_GATE" "gh pr create --title x --body y" "$repo"
  if is_deny "$GATE_OUT" && printf '%s' "$GATE_OUT" | grep -q '/drive-review ship'; then
    pass "ship: DENY gh pr create when tip is NOT covered by a converged review"
  else
    fail "ship: expected DENY naming /drive-review ship; got rc=$GATE_RC out='$GATE_OUT'"
  fi

  # Make the tip COVERED via the SHIP path: reset the unreviewed extra commit, then add a
  # single .harness/ ledger-only commit past the reviewed sha. Now rsha..tip is exactly 1
  # commit AND its only changed file is in the allowlist → existential R satisfies.
  _gitc "$repo" reset --hard "$rsha" >/dev/null 2>&1
  tip="$(_commit "$repo" .harness/decisions.md "ship ledger" "ship: promote run ledger")"

  run_installed_gate "$INSTALLED_GATE" "gh pr create --title x --body y" "$repo"
  if is_empty "$GATE_OUT" && [ "$GATE_RC" -eq 0 ] && ! is_allow "$GATE_OUT"; then
    pass "ship: ALLOW (silent) once tip covered (existential R + .harness ledger-only ≤1-commit)"
  else
    fail "ship: expected silent allow after ledger-only commit; got rc=$GATE_RC out='$GATE_OUT'"
  fi
}

# =================================================================================
# STAGE 5: asymmetric fail-mode — a git error makes ship fail-CLOSED (DENY) while
# slice-merge stays fail-OPEN (silent). We induce the error by pointing the command at
# an ABSENT ref so conformance hits exit 2 (cannot resolve ref).
# =================================================================================
stage_fail_modes() {
  local runid rd repo
  runid="$(new_runid)"; rd="$(mk_rundir "$runid")"
  repo="$TMPROOT/$runid-repo"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null
  _gitc "$repo" checkout -q -b "drive/$runid"
  _commit "$repo" feature.sh "echo hi" "drive work" >/dev/null
  # NOTE: deliberately do NOT create slice/$runid/9z or phaseInt — those refs are absent,
  # so conformance for slice-merge:9z exits 2 (cannot resolve ref).

  # ship fail-CLOSED: induce a git error in ship's existential-R path. We write a phase
  # review whose reviewed-sha is a NON-resolving artifact sha (skipped as a verdict), so
  # there is no counting R → ship denies. To get a genuine exit-2 we instead point ship at
  # a featureBranch that cannot resolve: run ship via a ref-bearing push to an absent drive
  # ref so runId resolves but featureBranch tip is unresolvable → conformance exit 2 → DENY.
  local absent_runid="e2e-test-$$-absent"
  local absent_rd; absent_rd="$(mk_rundir "$absent_runid")"
  # featureBranch drive/$absent_runid does NOT exist in $repo → rev() fails → exit 2.
  run_installed_gate "$INSTALLED_GATE" "git push origin drive/$absent_runid" "$repo"
  if is_deny "$GATE_OUT"; then
    pass "fail-mode: ship fail-CLOSED (DENY) on git error (unresolvable featureBranch → exit 2)"
  else
    fail "fail-mode: ship should DENY on git error; got rc=$GATE_RC out='$GATE_OUT'"
  fi

  # slice-merge fail-OPEN: the slice ref slice/$absent_runid/9z does not exist → conformance
  # exits 2 → the mid-build gate stays silent (exit 0, no output).
  run_installed_gate "$INSTALLED_GATE" "git merge slice/$absent_runid/9z" "$repo"
  if is_empty "$GATE_OUT" && [ "$GATE_RC" -eq 0 ]; then
    pass "fail-mode: slice-merge fail-OPEN (SILENT) on git error (unresolvable slice ref → exit 2)"
  else
    fail "fail-mode: slice-merge should be SILENT on git error; got rc=$GATE_RC out='$GATE_OUT'"
  fi
}

# =================================================================================
# STAGE 6: Stop backstop — a slice merged into a LIVE phaseInt without a review makes the
# Stop guard emit {"decision":"block"}; once reviewed, it exits 0 clean.
# =================================================================================
stage_stop_backstop() {
  local runid rd repo stip
  runid="$(new_runid)"; rd="$(mk_rundir "$runid")"
  repo="$TMPROOT/$runid-repo"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null
  _gitc "$repo" checkout -q -b "drive/$runid"
  # A slice branch with work.
  _gitc "$repo" checkout -q -b "slice/$runid/4a"
  stip="$(_commit "$repo" feature.sh "echo hi" "slice 4a work")"
  # A LIVE phaseInt with the slice merged in. HEAD must be drive/<runId> for the guard.
  _gitc "$repo" checkout -q "drive/$runid"
  _gitc "$repo" checkout -q -b "phaseInt/$runid/1"
  _gitc "$repo" merge -q --no-ff -m "merge slice 4a" "slice/$runid/4a"
  _gitc "$repo" checkout -q "drive/$runid"

  # Unreviewed slice merged into live phase → Stop guard BLOCKS.
  run_installed_stop "$INSTALLED_STOP" "$repo"
  local dec; dec="$(printf '%s' "$STOP_OUT" | jq -r '.decision // empty' 2>/dev/null || true)"
  if [ "$STOP_RC" -eq 0 ] && [ "$dec" = "block" ]; then
    pass "Stop backstop: BLOCK when a slice is merged into the live phaseInt unreviewed"
  else
    fail "Stop backstop: expected decision:block; got rc=$STOP_RC out='$STOP_OUT'"
  fi

  # Review the slice (reviewed-sha == slice tip) + codex → Stop guard clean, no block.
  _write_review "$rd" 4a 1 "$stip"
  _write_codex "$rd" 4a
  run_installed_stop "$INSTALLED_STOP" "$repo"
  if [ "$STOP_RC" -eq 0 ] && is_empty "$STOP_OUT"; then
    pass "Stop backstop: NO block (exit 0) once the merged slice is reviewed"
  else
    fail "Stop backstop: expected exit 0 + no block after review; got rc=$STOP_RC out='$STOP_OUT'"
  fi
}

# =================================================================================
main() {
  echo "=== /drive review-enforcement E2E (real installed hooks via stdin JSON) ==="
  stage_install
  # The gate-driving stages require the installed gate path to be resolved.
  if [ -z "$INSTALLED_GATE" ] || [ -z "$INSTALLED_STOP" ]; then
    echo "FAIL: hooks not installed; cannot drive the chain"
    FAIL=$((FAIL+1))
  else
    stage_plan_gate
    stage_slice_merge
    stage_phase_merge
    stage_ship
    stage_fail_modes
    stage_stop_backstop
  fi

  echo
  echo "----------------------------------------"
  printf 'TOTAL: %d passed, %d failed\n' "$PASS" "$FAIL"
  [ "$FAIL" -eq 0 ]
}

main "$@"
