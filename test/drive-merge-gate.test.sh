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
  if is_deny "$out" && printf '%s' "$out" | grep -q '/drive-review phase'; then
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
# Inserted-flag bypass (global flags/options between binary and subcommand)
# ---------------------------------------------------------------------------------

# `gh --repo o/r pr create` (global --repo before subcommand) on an unreviewed ship → DENY.
test_ship_gh_repo_flag() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "gh --repo o/r pr create --title x" "$repo"; out="$GATE_OUT"
  if is_deny "$out" && printf '%s' "$out" | grep -q '/drive-review phase'; then
    pass "ship denies gh --repo o/r pr create (global flag before subcommand)"
  else
    fail "ship should deny gh --repo … pr create; got: $out"
  fi
}

# `glab -R x mr create` (global -R <x> before subcommand) on unreviewed ship → DENY.
test_ship_glab_R_flag() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "glab -R x mr create --fill" "$repo"; out="$GATE_OUT"
  if is_deny "$out"; then
    pass "ship denies glab -R x mr create (global -R before subcommand)"
  else
    fail "ship should deny glab -R x mr create; got: $out"
  fi
}

# `git -C /path push` (global -C <path> before push) on a drive HEAD → DENY.
test_ship_git_C_push() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "git -C $repo push" "$repo"; out="$GATE_OUT"
  if is_deny "$out"; then
    pass "ship denies git -C /path push (global -C before subcommand)"
  else
    fail "ship should deny git -C /path push; got: $out"
  fi
}

# `git -c k=v push` (global -c <kv> before push) on a drive HEAD → DENY.
test_ship_git_c_kv_push() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "git -c k=v push" "$repo"; out="$GATE_OUT"
  if is_deny "$out"; then
    pass "ship denies git -c k=v push (global -c before subcommand)"
  else
    fail "ship should deny git -c k=v push; got: $out"
  fi
}

# `git -C /path merge slice/R/4a` (global -C before merge) unreviewed → DENY.
test_slicemerge_git_C() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_slice_repo "$runid" unreviewed)"; repo="${info%% *}"
  run_gate "git -C $repo merge slice/$runid/4a" "$repo"; out="$GATE_OUT"
  if is_deny "$out" && printf '%s' "$out" | grep -q '/drive-review slice 4a'; then
    pass "slice-merge denies git -C /path merge slice/R/4a (global -C before subcommand)"
  else
    fail "slice-merge should deny git -C … merge; got: $out"
  fi
}

# Env VAR=val prefix before the binary must still resolve the subcommand → DENY.
test_ship_env_prefix() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "GIT_TRACE=1 git -c k=v push" "$repo"; out="$GATE_OUT"
  if is_deny "$out"; then
    pass "ship denies VAR=val git -c k=v push (env prefix + global flag)"
  else
    fail "ship should deny env-prefixed git push; got: $out"
  fi
}

# ---------------------------------------------------------------------------------
# -C / --git-dir / --work-tree honored as the TARGET REPO (round-2 finding 1)
# ---------------------------------------------------------------------------------

# `git -C <unreviewed_drive_repo> push` invoked with cwd OUTSIDE that repo → DENY.
# The repo's HEAD is drive/<runId> and unreviewed; cwd is a non-git dir. Before the
# fix the gate resolved runId-from-HEAD against cwd (not a drive repo) → bypass.
test_ship_git_C_outside_cwd_deny() {
  local runid info repo out outside
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  outside="$TMPROOT/outside-$runid"; mkdir -p "$outside"   # NOT a git repo
  run_gate "git -C $repo push" "$outside"; out="$GATE_OUT"
  if is_deny "$out" && printf '%s' "$out" | grep -q '/drive-review phase'; then
    pass "ship denies git -C <drive_repo> push when cwd is OUTSIDE the repo (finding 1)"
  else
    fail "ship should deny git -C <drive_repo> push from outside cwd; got: $out"
  fi
}

# `git -C <other_nonDrive_repo> push` from a drive-branch cwd → inert/silent.
# git operates on the OTHER repo (HEAD = main, not a managed run) → no runId → inert.
# Before the fix the gate evaluated cwd's drive HEAD and could DENY the wrong repo.
test_ship_git_C_other_repo_inert() {
  local runid info drive_repo out other
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; drive_repo="${info%% *}"
  other="$TMPROOT/other-$runid-repo"; _init_repo "$other"
  _commit "$other" README base base >/dev/null   # other stays on main (non-drive)
  run_gate "git -C $other push" "$drive_repo"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ]; then
    pass "ship inert for git -C <other_nonDrive_repo> push from a drive cwd (finding 1)"
  else
    fail "ship should be inert for git -C <other_repo> push; got rc=$GATE_RC out='$out'"
  fi
}

# --git-dir / --work-tree resolve the TARGET REPO exactly like -C. conformance runs
# via `cd "$REPO" && drive-conformance`, doing only SHA/ref ops (rev-parse, for-each-ref,
# diff R..tip) — which resolve identically whether REPO is a worktree root OR a .git dir.
# These lock that in: the gate's decision via --git-dir/--work-tree must match the bare
# form (deny when unreviewed, silent when reviewed, inert for a non-drive target), with
# cwd OUTSIDE the repo so resolution MUST come from the flag, not cwd. Covers both the
# `--opt=val` and the space `--opt val` parse branches.

# `git --git-dir=<repo>/.git push` (=form), unreviewed, cwd outside → DENY.
test_ship_git_dir_eq_outside_cwd_deny() {
  local runid info repo out outside
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  outside="$TMPROOT/outside-gd-$runid"; mkdir -p "$outside"   # NOT a git repo
  run_gate "git --git-dir=$repo/.git push" "$outside"; out="$GATE_OUT"
  if is_deny "$out" && printf '%s' "$out" | grep -q '/drive-review phase'; then
    pass "ship denies git --git-dir=<repo>/.git push from outside cwd (=form)"
  else
    fail "ship should deny git --git-dir=… push from outside cwd; got: $out"
  fi
}

# Reviewed-silent via a repo-locating flag — NON-VACUOUS construction. cwd is set to a
# DIFFERENT, UNREVIEWED drive repo. If the flag resolves correctly → REPO = the reviewed
# repo → silent. If the flag were IGNORED → REPO falls back to cwd (the unreviewed drive
# repo) → DENY. So "silent" can ONLY happen when the flag actually retargets resolution.
# (Resolving to a non-git cwd would go inert/empty too — which is why cwd must itself be
# an unreviewed DRIVE repo, making ignore→deny and resolve→silent distinguishable.)

# `git --git-dir <reviewed>/.git push` (space form), cwd = unreviewed drive repo → silent.
test_ship_git_dir_space_reviewed_silent() {
  local ra rb rinfo repo cwdrepo out
  ra="$(new_runid)"; rinfo="$(mk_ship_repo_reviewed "$ra")"; repo="${rinfo%% *}"
  rb="$(new_runid)"; cwdrepo="$(mk_ship_repo "$rb")"; cwdrepo="${cwdrepo%% *}"
  run_gate "git --git-dir $repo/.git push" "$cwdrepo"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ] && ! is_allow "$out"; then
    pass "ship silent via git --git-dir <reviewed>/.git from an UNREVIEWED-drive cwd (non-vacuous, space form)"
  else
    fail "ship via --git-dir should resolve to the reviewed repo (silent); got rc=$GATE_RC out='$out'"
  fi
}

# `git --work-tree=<reviewed> push` (=form), cwd = unreviewed drive repo → silent.
test_ship_work_tree_eq_reviewed_silent() {
  local ra rb rinfo repo cwdrepo out
  ra="$(new_runid)"; rinfo="$(mk_ship_repo_reviewed "$ra")"; repo="${rinfo%% *}"
  rb="$(new_runid)"; cwdrepo="$(mk_ship_repo "$rb")"; cwdrepo="${cwdrepo%% *}"
  run_gate "git --work-tree=$repo push" "$cwdrepo"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ] && ! is_allow "$out"; then
    pass "ship silent via git --work-tree=<reviewed> from an UNREVIEWED-drive cwd (non-vacuous, =form)"
  else
    fail "ship via --work-tree= should resolve to the reviewed repo (silent); got rc=$GATE_RC out='$out'"
  fi
}

# `git --work-tree <reviewed> push` (SPACE form), cwd = unreviewed drive repo → silent.
test_ship_work_tree_space_reviewed_silent() {
  local ra rb rinfo repo cwdrepo out
  ra="$(new_runid)"; rinfo="$(mk_ship_repo_reviewed "$ra")"; repo="${rinfo%% *}"
  rb="$(new_runid)"; cwdrepo="$(mk_ship_repo "$rb")"; cwdrepo="${cwdrepo%% *}"
  run_gate "git --work-tree $repo push" "$cwdrepo"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ] && ! is_allow "$out"; then
    pass "ship silent via git --work-tree <reviewed> from an UNREVIEWED-drive cwd (non-vacuous, space form)"
  else
    fail "ship via --work-tree (space) should resolve to the reviewed repo (silent); got rc=$GATE_RC out='$out'"
  fi
}

# `git --git-dir=<other_nonDrive>/.git push` from a drive cwd → inert (targets OTHER repo).
test_ship_git_dir_other_repo_inert() {
  local runid info drive_repo out other
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; drive_repo="${info%% *}"
  other="$TMPROOT/other-gd-$runid-repo"; _init_repo "$other"
  _commit "$other" README base base >/dev/null   # other stays on main (non-drive)
  run_gate "git --git-dir=$other/.git push" "$drive_repo"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ]; then
    pass "ship inert for git --git-dir=<other_nonDrive>/.git push from a drive cwd"
  else
    fail "ship should be inert for git --git-dir=<other_repo> push; got rc=$GATE_RC out='$out'"
  fi
}

# ---------------------------------------------------------------------------------
# Tightened matching kills false positives (round-2 finding 2)
# ---------------------------------------------------------------------------------

# `echo git push` in a drive run → inert. The binary is `echo` (START word), not a
# later bare `git` token; subcommand_of git must NOT rescan past `echo`.
test_echo_git_push_inert() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "echo git push" "$repo"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ]; then
    pass "echo git push is inert (binary is echo, no rescan to git) (finding 2a)"
  else
    fail "echo git push should be inert; got rc=$GATE_RC out='$out'"
  fi
}

# `gh pr view --json createdAt` in a drive run → inert. Action is `view` (not
# `create`); ship must match the `pr create` PAIR, not the `*create*` substring.
test_gh_pr_view_createdAt_inert() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "gh pr view --json createdAt" "$repo"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ]; then
    pass "gh pr view --json createdAt is inert (action view, not create) (finding 2b)"
  else
    fail "gh pr view --json createdAt should be inert; got rc=$GATE_RC out='$out'"
  fi
}

# ---------------------------------------------------------------------------------
# Phase-advance with a generically-extracted phaseInt ref
# ---------------------------------------------------------------------------------

# The phaseInt ref in the command may carry a non-3-segment form; the gate must take
# its LAST segment as P, derive runId from drive/<runId>, and gate phase-merge:<P>.
# Build phaseInt/<runId>/2 and advance via `git branch -f drive/<runId> phaseInt/<runId>/2`.
mk_phase_repo_P() {
  local runid="$1" P="$2" reviewed="$3" rd repo tip
  rd="$(mk_rundir "$runid")"
  repo="$TMPROOT/$runid-repo"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null
  _gitc "$repo" checkout -q -b "drive/$runid"
  _gitc "$repo" checkout -q -b "phaseInt/$runid/$P"
  tip="$(_commit "$repo" code.sh "echo phase$P" "phase $P")"
  _gitc "$repo" checkout -q "drive/$runid"
  if [ "$reviewed" = reviewed ]; then
    _write_review "$rd" "phase$P" 1 "$tip"
    _write_codex "$rd" "phase$P"
  fi
  printf '%s %s\n' "$repo" "$rd"
}

test_phasemerge_generic_ref() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_phase_repo_P "$runid" 2 unreviewed)"; repo="${info%% *}"
  # -C global flag inserted too, to prove subcommand detection + generic P together.
  run_gate "git -C $repo branch -f drive/$runid phaseInt/$runid/2" "$repo"; out="$GATE_OUT"
  if is_deny "$out" && printf '%s' "$out" | grep -q '/drive-review phase 2'; then
    pass "phase-merge denies generically-extracted phaseInt ref (P=2, via -C)"
  else
    fail "phase-merge should deny generic phaseInt ref; got: $out"
  fi
}

# ---------------------------------------------------------------------------------
# rc normalization (D4): broken checker + cd-fail
# ---------------------------------------------------------------------------------

# Run the gate against a SHIM bin dir whose drive-conformance.sh is missing/non-exec,
# so run_conformance returns the "abnormal" rc. plan/ship must DENY (fail-CLOSED);
# slice/phase must stay SILENT (fail-OPEN).
# We shim by copying the gate+lib into a temp bin with a NON-executable conformance.
run_gate_brokenconf() {
  local cmd="$1" cwd="$2" shimbin json
  shimbin="$TMPROOT/shimbin-$(new_runid)"; mkdir -p "$shimbin"
  cp "$BIN/drive-merge-gate.sh" "$shimbin/"
  cp "$BIN/drive-hook-lib.sh" "$shimbin/"
  # Non-executable conformance (chmod 000) → -x test fails → abnormal rc.
  printf '#!/bin/sh\nexit 0\n' > "$shimbin/drive-conformance.sh"
  chmod 000 "$shimbin/drive-conformance.sh"
  json="$(jq -n --arg c "$cmd" --arg w "$cwd" '{tool_input:{command:$c},cwd:$w}')"
  printf '%s' "$json" | bash "$shimbin/drive-merge-gate.sh" > "$TMPROOT/.gateout" 2>/dev/null
  GATE_RC=$?
  GATE_OUT="$(cat "$TMPROOT/.gateout")"
}

test_rcnorm_brokenconf_plan_deny() {
  local runid rd repo out
  runid="$(new_runid)"; rd="$(mk_rundir "$runid")"
  repo="$TMPROOT/$runid-repo"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null
  _write_review "$rd" design 1 "$(printf '0%.0s' {1..40})"; _write_codex "$rd" design
  run_gate_brokenconf "git worktree add ../wt/4a -b slice/$runid/4a" "$repo"; out="$GATE_OUT"
  if is_deny "$out"; then
    pass "rc-norm: broken conformance → plan-gate DENY (fail-closed)"
  else
    fail "rc-norm: broken conformance should DENY plan-gate; got: $out"
  fi
}

test_rcnorm_brokenconf_ship_deny() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo_reviewed "$runid")"; repo="${info%% *}"
  run_gate_brokenconf "gh pr create" "$repo"; out="$GATE_OUT"
  if is_deny "$out"; then
    pass "rc-norm: broken conformance → ship DENY (fail-closed)"
  else
    fail "rc-norm: broken conformance should DENY ship; got: $out"
  fi
}

test_rcnorm_brokenconf_slice_silent() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_slice_repo "$runid" reviewed)"; repo="${info%% *}"
  run_gate_brokenconf "git merge --no-ff slice/$runid/4a" "$repo"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ]; then
    pass "rc-norm: broken conformance → slice-merge SILENT (fail-open)"
  else
    fail "rc-norm: broken conformance should be SILENT for slice-merge; got rc=$GATE_RC out='$out'"
  fi
}

test_rcnorm_brokenconf_phase_silent() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_phase_repo "$runid" reviewed)"; repo="${info%% *}"
  run_gate_brokenconf "git branch -f drive/$runid phaseInt/$runid/1" "$repo"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ]; then
    pass "rc-norm: broken conformance → phase-merge SILENT (fail-open)"
  else
    fail "rc-norm: broken conformance should be SILENT for phase-merge; got rc=$GATE_RC out='$out'"
  fi
}

# cd to a nonexistent cwd: a bare `cd` failure must NOT read as a conformance verdict.
# plan/ship → DENY (fail-closed); slice/phase → SILENT (fail-open).
# RUN_DIR must exist (so we reach the conformance step); the CWD is what's missing.
test_cdfail_plan_deny() {
  local runid rd out badcwd
  runid="$(new_runid)"; rd="$(mk_rundir "$runid")"
  _write_review "$rd" design 1 "$(printf '0%.0s' {1..40})"; _write_codex "$rd" design
  badcwd="$TMPROOT/does-not-exist-$runid"
  # runId resolves from the slice ref in the command (no cwd HEAD needed for plan-gate).
  run_gate "git worktree add ../wt/4a -b slice/$runid/4a" "$badcwd"; out="$GATE_OUT"
  if is_deny "$out"; then
    pass "cd-fail: nonexistent cwd → plan-gate DENY (fail-closed)"
  else
    fail "cd-fail should DENY plan-gate; got: $out"
  fi
}

test_cdfail_ship_deny() {
  local runid rd out badcwd
  runid="$(new_runid)"; rd="$(mk_rundir "$runid")"
  badcwd="$TMPROOT/does-not-exist-ship-$runid"
  # ship runId from the command ref (drive/<runId>) so HEAD-in-missing-cwd isn't needed.
  run_gate "git push origin drive/$runid" "$badcwd"; out="$GATE_OUT"
  if is_deny "$out"; then
    pass "cd-fail: nonexistent cwd → ship DENY (fail-closed)"
  else
    fail "cd-fail should DENY ship; got: $out"
  fi
}

test_cdfail_slice_silent() {
  local runid rd out badcwd
  runid="$(new_runid)"; rd="$(mk_rundir "$runid")"
  badcwd="$TMPROOT/does-not-exist-slice-$runid"
  run_gate "git merge slice/$runid/4a" "$badcwd"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ]; then
    pass "cd-fail: nonexistent cwd → slice-merge SILENT (fail-open, no false deny)"
  else
    fail "cd-fail should be SILENT for slice-merge; got rc=$GATE_RC out='$out'"
  fi
}

test_cdfail_phase_silent() {
  local runid rd out badcwd
  runid="$(new_runid)"; rd="$(mk_rundir "$runid")"
  badcwd="$TMPROOT/does-not-exist-phase-$runid"
  run_gate "git branch -f drive/$runid phaseInt/$runid/1" "$badcwd"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ]; then
    pass "cd-fail: nonexistent cwd → phase-merge SILENT (fail-open, no false deny)"
  else
    fail "cd-fail should be SILENT for phase-merge; got rc=$GATE_RC out='$out'"
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
# Finding #1: ship runId comes from HEAD, NOT a ref-shaped token in the PR body.
# ---------------------------------------------------------------------------------

# `gh pr create --body 'see slice/<OTHER>/4a'` from a drive cwd whose OWN run is
# UNREVIEWED, where <OTHER> is a SEPARATE clean run. Pre-fix the gate re-keyed runId
# from the body token (slice/<OTHER>/4a) → validated the clean OTHER run → wrongly
# ALLOWED. Post-fix the ship runId is from HEAD (the unreviewed run) → DENY.
test_ship_body_token_keys_head_not_body() {
  local runid info repo out
  local otherrun otherinfo
  # The clean OTHER run: a reviewed ship repo (its phase review covers its tip).
  otherrun="$(new_runid)"; otherinfo="$(mk_ship_repo_reviewed "$otherrun")"
  # The drive cwd's OWN run: UNREVIEWED ship.
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  # Body references the OTHER (clean) run's slice token. Post-fix the gate keys runId
  # from HEAD → names the OWN unreviewed run ($runid) and the /drive-review phase
  # remediation. Pre-fix it re-keyed to the OTHER run ($otherrun) from the body token
  # (and emitted the /drive-review ship text), so both checks below fail pre-fix.
  run_gate "gh pr create --title x --body 'see slice/$otherrun/4a'" "$repo"; out="$GATE_OUT"
  if is_deny "$out" \
     && printf '%s' "$out" | grep -q '/drive-review phase' \
     && printf '%s' "$out" | grep -q "run $runid " \
     && ! printf '%s' "$out" | grep -q "run $otherrun "; then
    pass "ship keys runId from HEAD not body token (names OWN run $runid, never OTHER run from body)"
  else
    fail "ship should DENY the OWN run via HEAD (not body's slice/$otherrun/4a); got: $out"
  fi
}

# ---------------------------------------------------------------------------------
# Finding #2: ship deny remediation names `/drive-review phase`, not `/drive-review ship`.
# ---------------------------------------------------------------------------------
test_ship_deny_names_phase_not_ship() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "gh pr create --title x --body y" "$repo"; out="$GATE_OUT"
  if is_deny "$out" \
     && printf '%s' "$out" | grep -q '/drive-review phase' \
     && ! printf '%s' "$out" | grep -q '/drive-review ship'; then
    pass "ship deny remediation names /drive-review phase (NOT the nonexistent /drive-review ship)"
  else
    fail "ship deny should name /drive-review phase and not /drive-review ship; got: $out"
  fi
}

# ---------------------------------------------------------------------------------
# Finding #3: `git push origin main` from a drive cwd is NOT gated as ship; bare
# `git push` on the drive branch IS gated.
# ---------------------------------------------------------------------------------

# `git push origin main` from a drive-branch cwd (own run UNREVIEWED) → inert/silent.
# The explicit pushed source ref is `main` (non-drive), so this is not a ship.
test_push_origin_main_not_ship() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "git push origin main" "$repo"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ]; then
    pass "git push origin main from a drive cwd is NOT gated as ship (inert)"
  else
    fail "git push origin main should be inert (non-drive source ref); got rc=$GATE_RC out='$out'"
  fi
}

# Bare `git push` on the same UNREVIEWED drive branch IS gated → DENY (HEAD == drive).
test_push_bare_on_drive_is_ship() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "git push" "$repo"; out="$GATE_OUT"
  if is_deny "$out"; then
    pass "bare git push on the drive branch IS gated as ship (deny unreviewed)"
  else
    fail "bare git push on drive branch should be gated as ship; got: $out"
  fi
}

# Multi-refspec push INCLUDING the drive branch anywhere (not just the 2nd word) must
# be gated — `git push origin main drive/<id>` still ships drive/<id>. Guards the
# regression where only the 2nd positional refspec was inspected (err-toward-gating).
test_push_multiref_includes_drive_is_ship() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "git push origin main drive/$runid" "$repo"; out="$GATE_OUT"
  if is_deny "$out"; then
    pass "multi-refspec push including drive/<id> IS gated (scans ALL refspecs)"
  else
    fail "git push origin main drive/<id> should be gated as ship; got rc=$GATE_RC out='$out'"
  fi
}

# Aggregate push (`--all`) pushes the drive branch implicitly → gated when HEAD is drive.
test_push_all_aggregate_is_ship() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "git push --all" "$repo"; out="$GATE_OUT"
  if is_deny "$out"; then
    pass "aggregate git push --all on the drive branch IS gated as ship"
  else
    fail "git push --all on drive branch should be gated as ship; got rc=$GATE_RC out='$out'"
  fi
}

# Aggregate push (`--mirror`) is in the same `--all|--mirror` aggregate branch as
# `--all` (drive-merge-gate.sh:231) → pushes the drive branch implicitly → gated when
# HEAD is the drive feature branch. Mirrors test_push_all_aggregate_is_ship.
test_push_mirror_aggregate_is_ship() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo "$runid")"; repo="${info%% *}"
  run_gate "git push --mirror" "$repo"; out="$GATE_OUT"
  if is_deny "$out"; then
    pass "aggregate git push --mirror on the drive branch IS gated as ship"
  else
    fail "git push --mirror on drive branch should be gated as ship; got rc=$GATE_RC out='$out'"
  fi
}

# `git push --mirror` is gated like `--all`, NOT blanket-denied: a REVIEWED ship tip
# → silent allow. Proves the deny is conformance-conditioned, not flag-conditioned.
test_push_mirror_reviewed_silent() {
  local runid info repo out
  runid="$(new_runid)"; info="$(mk_ship_repo_reviewed "$runid")"; repo="${info%% *}"
  run_gate "git push --mirror" "$repo"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ] && ! is_allow "$out"; then
    pass "git push --mirror on a REVIEWED drive tip is silent (gated, not blanket-denied)"
  else
    fail "git push --mirror should be silent when reviewed; got rc=$GATE_RC out='$out'"
  fi
}

# `--mirror` aggregate from a NON-drive HEAD → inert (runId from HEAD fails to
# resolve), exactly like a bare push from a non-drive branch. Confirms the aggregate
# gating is HEAD-conditioned, same as `--all`.
test_push_mirror_nondrive_head_inert() {
  local runid repo out
  runid="$(new_runid)"
  repo="$TMPROOT/$runid-mirror-nondrive"; _init_repo "$repo"
  _commit "$repo" README base base >/dev/null   # stays on main (non-drive HEAD)
  run_gate "git push --mirror" "$repo"; out="$GATE_OUT"
  if is_empty "$out" && [ "$GATE_RC" -eq 0 ]; then
    pass "git push --mirror from a non-drive HEAD is inert (HEAD-conditioned)"
  else
    fail "git push --mirror from non-drive HEAD should be inert; got rc=$GATE_RC out='$out'"
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
  # inserted-flag bypass
  test_ship_gh_repo_flag
  test_ship_glab_R_flag
  test_ship_git_C_push
  test_ship_git_c_kv_push
  test_slicemerge_git_C
  test_ship_env_prefix
  # -C/--git-dir/--work-tree target repo (finding 1)
  test_ship_git_C_outside_cwd_deny
  test_ship_git_C_other_repo_inert
  test_ship_git_dir_eq_outside_cwd_deny
  test_ship_git_dir_space_reviewed_silent
  test_ship_work_tree_eq_reviewed_silent
  test_ship_work_tree_space_reviewed_silent
  test_ship_git_dir_other_repo_inert
  # tightened matching false-positive guards (finding 2)
  test_echo_git_push_inert
  test_gh_pr_view_createdAt_inert
  # generic phaseInt ref extraction
  test_phasemerge_generic_ref
  # rc normalization (D4): broken checker
  test_rcnorm_brokenconf_plan_deny
  test_rcnorm_brokenconf_ship_deny
  test_rcnorm_brokenconf_slice_silent
  test_rcnorm_brokenconf_phase_silent
  # rc normalization (D4): cd-fail
  test_cdfail_plan_deny
  test_cdfail_ship_deny
  test_cdfail_slice_silent
  test_cdfail_phase_silent
  test_nonmatching_inert
  test_unmanaged_run_inert
  test_ship_nondrive_branch_inert
  test_never_allow
  # finding #1: ship runId from HEAD, not body token
  test_ship_body_token_keys_head_not_body
  # finding #2: ship deny remediation names /drive-review phase
  test_ship_deny_names_phase_not_ship
  # finding #3: explicit non-drive push target not gated; bare drive push gated
  test_push_origin_main_not_ship
  test_push_bare_on_drive_is_ship
  # multi-refspec / aggregate push must still gate the drive branch (err toward gating)
  test_push_multiref_includes_drive_is_ship
  test_push_all_aggregate_is_ship
  test_push_mirror_aggregate_is_ship
  test_push_mirror_reviewed_silent
  test_push_mirror_nondrive_head_inert

  echo
  echo "----------------------------------------"
  printf 'TOTAL: %d passed, %d failed\n' "$PASS" "$FAIL"
  [ "$FAIL" -eq 0 ]
}

main "$@"
