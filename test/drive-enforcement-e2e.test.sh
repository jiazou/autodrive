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
# Seed a CONVERGED finalize artifact — ship-mode's terminal tip-binding candidate-R (the
# phase review is demoted to a no-phase-review precondition). $1=rd $2=N $3=reviewed-sha.
_write_finalize() {
  local rd="$1" n="$2" sha="$3"; mkdir -p "$rd"
  { echo "# review finalize $n"; echo; echo "## Verdict: CONVERGED"; echo "## AppliedEdits: no"; echo; echo "reviewed-sha: $sha"; } \
    > "$rd/review-finalize-$n.md"
  { echo "codex review for finalize"; echo ok; } > "$rd/codex-review-finalize.md"
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

# --- Run the conformance checker DIRECTLY (not via the gate), from a repo cwd, so we
# can prove the underlying verdict the gate composes from. The gate's rc=0+silent ALLOW
# is identical for "checker genuinely clean" and "fail-open over an abnormal exit", and
# its DENY is identical for "real violation (exit 1)" and "fail-closed error (exit 2)".
# Asserting on this checker's RAW exit + JSON disambiguates those.
# $1=RUN_DIR $2=mode-arg $3=cwd(repo). Sets CONF_OUT (stdout) and CONF_RC (raw exit).
run_conformance_direct() {
  local rd="$1" mode="$2" cwd="$3"
  CONF_OUT="$( cd "$cwd" && "$BIN/drive-conformance.sh" "$rd" --mode "$mode" 2>/dev/null )"
  CONF_RC=$?
}
conf_is_clean() { printf '%s' "$1" | grep -q '"clean":true'; }

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

  # Prove the deny below is the INTENDED-VIOLATION deny (exit 1), not a fail-closed
  # error deny (exit 2): the checker itself must return a genuine violation here.
  run_conformance_direct "$rd" "plan-gate" "$repo"
  if [ "$CONF_RC" -eq 1 ]; then
    pass "plan-gate: conformance returns exit 1 (genuine violation) with NO design review"
  else
    fail "plan-gate: expected conformance exit 1; got rc=$CONF_RC out='$CONF_OUT'"
  fi

  # No design review yet → DENY, naming /drive-review design.
  run_installed_gate "$INSTALLED_GATE" "$cmd" "$repo"
  if is_deny "$GATE_OUT" && printf '%s' "$GATE_OUT" | grep -q '/drive-review design'; then
    pass "plan-gate: DENY worktree add with NO design review (names /drive-review design)"
  else
    fail "plan-gate: expected DENY naming design review; got rc=$GATE_RC out='$GATE_OUT'"
  fi

  # Add CONVERGED design review + codex → still DENY: a worktree-add now ALSO requires the
  # slice's PHASE design review (Tier 2). Slice `4a` → phase P=`4a`.
  _write_review "$rd" design 1 "$(printf '0%.0s' {1..40})"
  _write_codex "$rd" design
  run_installed_gate "$INSTALLED_GATE" "$cmd" "$repo"
  if is_deny "$GATE_OUT" && printf '%s' "$GATE_OUT" | grep -q '/drive-review phase 4a design'; then
    pass "phasedesign-gate: DENY worktree add when phase design unreviewed (names /drive-review phase 4a design)"
  else
    fail "phasedesign-gate: expected DENY naming phase design; got rc=$GATE_RC out='$GATE_OUT'"
  fi

  # Add the phase design review too → silent ALLOW (exit 0, no output, never allow).
  _write_review "$rd" phasedesign4a 1 "$(printf '0%.0s' {1..40})"
  _write_codex "$rd" phasedesign4a
  run_installed_gate "$INSTALLED_GATE" "$cmd" "$repo"
  if is_empty "$GATE_OUT" && [ "$GATE_RC" -eq 0 ] && ! is_allow "$GATE_OUT"; then
    pass "plan+phasedesign gate: ALLOW (silent) once BOTH the design and phase design reviews CONVERGED + codex"
  else
    fail "plan-gate: expected silent allow once both reviewed; got rc=$GATE_RC out='$GATE_OUT'"
  fi
}

# =================================================================================
# STAGE 2: slice-merge — DENY (no slice review) then ALLOW once the slice is BOTH
# reviewed (reviewed-sha == slice tip) AND carries test evidence. Item C added the
# impl-presence test-presence check (fail-CLOSED) alongside the slice-merge review
# check (fail-OPEN) at this boundary, so the happy path must satisfy BOTH:
#   - a real drive/<runId> base branch exists (so impl-presence's
#     merge-base(slice, drive/<runId>) resolves instead of exiting 2 → fail-closed), and
#   - the slice's work commit adds a runnable TEST path (test/*.test.sh) so impl-presence
#     sees test evidence (exit 0) rather than denying for no-test.
# =================================================================================
stage_slice_merge() {
  local runid rd repo tip
  runid="$(new_runid)"; rd="$(mk_rundir "$runid")"
  repo="$TMPROOT/$runid-repo"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null
  # Real drive/<runId> base branch (the featureBranch impl-presence merge-bases against).
  _gitc "$repo" checkout -q -b "drive/$runid"
  # Slice branch cut from drive/<runId>; its work commit adds a TEST file so impl-presence
  # sees test evidence (Item C). The merge target (HEAD at merge time) is drive/<runId>.
  _gitc "$repo" checkout -q -b "slice/$runid/4a"
  tip="$(_commit "$repo" test/feature.test.sh "echo test" "slice 4a work + test")"
  _gitc "$repo" checkout -q "drive/$runid"

  local cmd="git merge --no-ff slice/$runid/4a"

  # No slice review yet → DENY. impl-presence is already satisfied (drive base + test), so
  # this DENY comes from the review-presence check naming /drive-review slice 4a.
  run_installed_gate "$INSTALLED_GATE" "$cmd" "$repo"
  if is_deny "$GATE_OUT" && printf '%s' "$GATE_OUT" | grep -q '/drive-review slice 4a'; then
    pass "slice-merge: DENY merge with NO slice review (names /drive-review slice 4a)"
  else
    fail "slice-merge: expected DENY naming slice 4a; got rc=$GATE_RC out='$GATE_OUT'"
  fi

  # Review bound to the EXACT slice tip + codex → BOTH checks pass (review present +
  # test present) → silent ALLOW.
  _write_review "$rd" 4a 1 "$tip"
  _write_codex "$rd" 4a
  run_installed_gate "$INSTALLED_GATE" "$cmd" "$repo"
  if is_empty "$GATE_OUT" && [ "$GATE_RC" -eq 0 ] && ! is_allow "$GATE_OUT"; then
    pass "slice-merge: ALLOW (silent) once reviewed-sha == slice tip + codex + test present"
  else
    fail "slice-merge: expected silent allow; got rc=$GATE_RC out='$GATE_OUT'"
  fi

  # Distinguish "gate allowed because checker passed" from "gate fell open" on this same
  # state: the underlying conformance must be GENUINELY clean (exit 0 AND "clean":true),
  # not abnormal. (A fail-open ALLOW would also be rc=0+silent at the gate.) Assert BOTH
  # the review-presence (slice-merge:4a) AND the test-presence (impl-presence:4a) checks
  # are genuinely clean for the allowed state.
  run_conformance_direct "$rd" "slice-merge:4a" "$repo"
  if [ "$CONF_RC" -eq 0 ] && conf_is_clean "$CONF_OUT"; then
    pass "slice-merge: review-presence conformance GENUINELY clean (exit 0 + \"clean\":true) for the allowed state"
  else
    fail "slice-merge: expected genuine clean (review-presence); got rc=$CONF_RC out='$CONF_OUT'"
  fi
  run_conformance_direct "$rd" "impl-presence:4a" "$repo"
  if [ "$CONF_RC" -eq 0 ] && conf_is_clean "$CONF_OUT"; then
    pass "slice-merge: impl-presence (test-presence) conformance GENUINELY clean (exit 0 + \"clean\":true) for the allowed state"
  else
    fail "slice-merge: expected genuine clean (impl-presence); got rc=$CONF_RC out='$CONF_OUT'"
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

  # Same fail-open-vs-genuine-clean disambiguation as slice-merge: the checker must be
  # genuinely clean (exit 0 + "clean":true) for the allowed phase-advance state.
  run_conformance_direct "$rd" "phase-merge:1" "$repo"
  if [ "$CONF_RC" -eq 0 ] && conf_is_clean "$CONF_OUT"; then
    pass "phase-merge: conformance GENUINELY clean (exit 0 + \"clean\":true) for the allowed state"
  else
    fail "phase-merge: expected genuine clean; got rc=$CONF_RC out='$CONF_OUT'"
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
  # Ship's terminal tip-binding candidate-R is now the CONVERGED finalize artifact (the phase
  # review above is demoted to the no-phase-review precondition). Bind it to rsha = the phase
  # code commit (the tip-binding R, parent of the eventual ledger tip). The uncovered/>1-commit
  # DENY cases below still deny on rules (b)/(c) — rsha..tip ⊄ allowlist / >1 commit; the
  # ledger-only case goes silent because rsha..tip is then the single allowlisted commit.
  _write_finalize "$rd" 1 "$rsha"

  # Prove the deny below is the INTENDED-VIOLATION deny (exit 1: tip uncovered), not a
  # fail-closed error deny (exit 2). Ship resolves runId from HEAD, so run the checker
  # in `--mode ship` from the repo (featureBranch resolves; diff R..tip ⊄ allowlist).
  run_conformance_direct "$rd" "ship" "$repo"
  if [ "$CONF_RC" -eq 1 ]; then
    pass "ship: conformance returns exit 1 (genuine violation) when tip is uncovered"
  else
    fail "ship: expected conformance exit 1; got rc=$CONF_RC out='$CONF_OUT'"
  fi

  run_installed_gate "$INSTALLED_GATE" "gh pr create --title x --body y" "$repo"
  if is_deny "$GATE_OUT" && printf '%s' "$GATE_OUT" | grep -q '/drive-finalize'; then
    pass "ship: DENY gh pr create when tip is NOT covered by a converged review"
  else
    fail "ship: expected DENY naming /drive-finalize; got rc=$GATE_RC out='$GATE_OUT'"
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

  # ≤1-commit rejection path: add a SECOND .harness/ ledger-only commit past R. Both
  # commits touch ONLY allowlisted files (so the allowlist (b) is satisfied), but now
  # R..tip is 2 commits, which violates the existential-R (c) `R..tip ≤ 1 commit` rule.
  # The ONLY counting R is rsha (the phase1 review); there is no R one commit behind tip
  # whose diff ⊆ allowlist, so ship must DENY. This isolates rule (c) from (b).
  _gitc "$repo" reset --hard "$rsha" >/dev/null 2>&1
  _commit "$repo" .harness/decisions.md "ship ledger 1" "ship: promote run ledger (1/2)" >/dev/null
  tip="$(_commit "$repo" .harness/followups.md "ship followups" "ship: promote run ledger (2/2)")"

  # Direct checker: genuine violation (exit 1), proving the deny is the ≤1-commit reject.
  run_conformance_direct "$rd" "ship" "$repo"
  if [ "$CONF_RC" -eq 1 ]; then
    pass "ship: conformance exit 1 when R..tip is 2 ledger-only commits (>1-commit reject)"
  else
    fail "ship: expected conformance exit 1 (>1 commit); got rc=$CONF_RC out='$CONF_OUT'"
  fi

  run_installed_gate "$INSTALLED_GATE" "gh pr create --title x --body y" "$repo"
  if is_deny "$GATE_OUT" && printf '%s' "$GATE_OUT" | grep -q '/drive-finalize'; then
    pass "ship: DENY when 2 ledger-only commits sit past R (R..tip >1 commit, even all allowlisted)"
  else
    fail "ship: expected DENY for >1-commit ledger window; got rc=$GATE_RC out='$GATE_OUT'"
  fi
}

# =================================================================================
# STAGE 5: asymmetric fail-mode — a genuine conformance exit-2 (git/IO error) makes the
# ship gate fail-CLOSED (DENY) while the slice-merge gate stays fail-OPEN (silent).
#
# CRITICAL (weakness 2): the run's runId must resolve CORRECTLY (real RUN_DIR + drive
# HEAD) so each gate actually RUNS conformance and reaches the exit-2 path — otherwise a
# gate can pass for the wrong reason (ship falling back to HEAD and denying a real
# violation; slice going inert/silent because RUN_DIR is absent, not because it failed
# open over an error). So we build ONE real, resolving drive run, then induce a genuine
# exit-2 in conformance and drive BOTH gates against that same condition, FIRST asserting
# the checker itself returns exit 2 directly.
#
#   ship exit-2:  R resolves + is an ancestor + R..tip ≤ 1 commit, so the existential-R
#                 loop reaches `git diff R..tip`; we corrupt tip's TREE object so the diff
#                 errors (git_or_die → exit 2). HEAD + R commit objects stay intact, so
#                 runId-from-HEAD and the candidate-R resolution still succeed.
#   slice exit-2: a slice ref slice/<runId>/9z that does NOT resolve to a commit (the
#                 runId still resolves from the command token, RUN_DIR exists) → conformance
#                 slice-merge:9z exits 2 at the `rev` step ("cannot resolve ref").
# =================================================================================
stage_fail_modes() {
  local runid rd repo rsha tip tree treeobj
  runid="$(new_runid)"; rd="$(mk_rundir "$runid")"
  repo="$TMPROOT/$runid-repo"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null
  _gitc "$repo" checkout -q -b "drive/$runid"
  rsha="$(_commit "$repo" feature.sh "echo hi" "phase 1 code")"
  # Exactly ONE ledger-only commit past R so rsha..tip is 1 commit ⊆ allowlist → the
  # existential-R loop passes (a)(b)(c) and reaches the `git diff R..tip` git_or_die.
  tip="$(_commit "$repo" .harness/decisions.md "ledger" "ship: promote run ledger")"
  _write_review "$rd" phase1 1 "$rsha"
  _write_codex "$rd" phase1
  # Ship now short-circuits to no-review (empty candidate_R) BEFORE the git diff when there is
  # no CONVERGED finalize artifact. Seed a finalize R = rsha (the phase code commit, parent of
  # the corrupt tip; its tree is intact) so candidate_R is non-empty and the (a)(b)(c) loop
  # reaches `git diff R..tip` against the corrupt tip → git_or_die → exit 2 (fail-closed).
  _write_finalize "$rd" 1 "$rsha"

  # Corrupt tip's TREE object: `git diff R..tip` cannot read it → git_or_die → exit 2.
  # Commit objects (HEAD, R) are untouched, so runId-from-HEAD + R resolution still work.
  tree="$(_gitc "$repo" rev-parse "$tip^{tree}")"
  treeobj="$repo/.git/objects/${tree:0:2}/${tree:2}"
  rm -f "$treeobj"

  # FIRST: prove the checker itself returns a genuine exit 2 (git/IO error), not exit 1
  # (a real coverage violation). runId resolves via drive HEAD; featureBranch resolves.
  run_conformance_direct "$rd" "ship" "$repo"
  if [ "$CONF_RC" -eq 2 ]; then
    pass "fail-mode: conformance --mode ship returns exit 2 (genuine git/IO error, corrupted tree)"
  else
    fail "fail-mode: expected conformance ship exit 2; got rc=$CONF_RC out='$CONF_OUT'"
  fi

  # ship fail-CLOSED: same exit-2 condition driven through the ship gate (bare gh pr
  # create → runId from drive HEAD) → DENY.
  run_installed_gate "$INSTALLED_GATE" "gh pr create --title x --body y" "$repo"
  if is_deny "$GATE_OUT"; then
    pass "fail-mode: ship fail-CLOSED (DENY) on conformance exit 2 (runId resolves via drive HEAD)"
  else
    fail "fail-mode: ship should DENY on exit 2; got rc=$GATE_RC out='$GATE_OUT'"
  fi

  # slice-merge exit-2 on the SAME resolving run: slice/$runid/9z does not resolve to a
  # commit (runId still resolves from the token; RUN_DIR exists), so conformance hits the
  # genuine "cannot resolve ref" exit 2 — NOT an inert/not-a-managed-run early exit.
  run_conformance_direct "$rd" "slice-merge:9z" "$repo"
  if [ "$CONF_RC" -eq 2 ]; then
    pass "fail-mode: conformance --mode slice-merge:9z returns exit 2 (cannot resolve ref, runId valid)"
  else
    fail "fail-mode: expected conformance slice-merge exit 2; got rc=$CONF_RC out='$CONF_OUT'"
  fi

  # slice-merge fail-CLOSED on exit 2 (Item C): the slice-merge boundary runs TWO checks —
  # the REVIEW-presence check (slice-merge:9z, fail-OPEN, backstopped by ship) AND the
  # TEST-presence check (impl-presence:9z, fail-CLOSED, NO ship backstop). The unresolvable
  # slice ref makes impl-presence:9z ALSO exit 2, and because impl-presence fails CLOSED the
  # gate now DENIES (the review check alone would have fallen open silently). This is the
  # irreversible test-presence boundary: an abnormal git result must not silently allow a
  # no-test merge with nothing catching it later.
  run_installed_gate "$INSTALLED_GATE" "git merge slice/$runid/9z" "$repo"
  if is_deny "$GATE_OUT" && printf '%s' "$GATE_OUT" | grep -q 'adds no test file'; then
    pass "fail-mode: slice-merge fail-CLOSED (DENY) on conformance exit 2 via impl-presence (runId resolves, RUN_DIR present)"
  else
    fail "fail-mode: slice-merge should fail-CLOSED DENY on exit 2 (impl-presence has no ship backstop); got rc=$GATE_RC out='$GATE_OUT'"
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
