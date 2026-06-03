#!/usr/bin/env bash
# Plain-bash test runner for bin/drive-stop-guard.sh (AC9).
#
# The Stop guard reads Stop-hook JSON on stdin (.cwd, .stop_hook_active), resolves the
# runId from `git HEAD` in .cwd, locates RUN_DIR at $HOME/.claude/harness-runs/<runId>,
# runs drive-conformance.sh --mode audit, and emits {"decision":"block",...} ONLY when a
# slice merged into the live phaseInt lacks a counting review.
#
# AC9 assertions:
#   - BLOCKS (emits decision:block) when a slice is merged into the live phaseInt but
#     unreviewed.
#   - exit 0, NO block when:
#       (a) no live phaseInt,
#       (b) merged slices all have counting reviews,
#       (c) HEAD is not a drive branch,
#       (d) audit hits exit 2 (fail-open).
#
# Hermetic: a temp dir is used as a fake $HOME so RUN_DIRs land at
# $HOME/.claude/harness-runs/<runId> without touching the real one. Each fixture is a
# real git repo with HEAD on drive/<runId>.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
GUARD="$ROOT/bin/drive-stop-guard.sh"

PASS=0; FAIL=0
WORK="$(mktemp -d "${TMPDIR:-/tmp}/drive-stop-guard.XXXXXX")"
FAKE_HOME="$WORK/home"
RUNS_ROOT="$FAKE_HOME/.claude/harness-runs"
mkdir -p "$RUNS_ROOT"
trap 'rm -rf "$WORK"' EXIT

# git with deterministic identity + no signing, scoped via -C.
_gitc() { git -C "$1" -c user.name=t -c user.email=t@t -c commit.gpgsign=false "${@:2}"; }

_init_repo() {
  local r="$1"; mkdir -p "$r"; git -C "$r" init -q -b main
  _gitc "$r" config user.name t; _gitc "$r" config user.email t@t
}
_commit() {
  local r="$1" p="$2" c="$3" m="$4"
  mkdir -p "$r/$(dirname "$p")"; printf '%s\n' "$c" > "$r/$p"
  _gitc "$r" add -A; _gitc "$r" commit -q -m "$m"; _gitc "$r" rev-parse HEAD
}
_write_review() {
  local rd="$1" scope="$2" n="$3" sha="$4"; mkdir -p "$rd"
  { echo "# review"; echo; echo "## Verdict: CONVERGED"; echo; echo "reviewed-sha: $sha"; } \
    > "$rd/review-$scope-$n.md"
}
_write_codex() {
  local rd="$1" scope="$2"; mkdir -p "$rd"
  { echo "codex review for $scope"; echo ok; } > "$rd/codex-review-$scope.md"
}

# Run the guard with a mock Stop JSON. Args: cwd [stop_hook_active(true|false)]
# Sets RC and OUT. Forces HOME=$FAKE_HOME so drive_run_dir resolves into our temp tree.
run_guard() {
  local cwd="$1" active="${2:-false}"
  local json; json="$(jq -nc --arg cwd "$cwd" --argjson a "$active" \
    '{cwd:$cwd, stop_hook_active:$a}')"
  OUT="$(printf '%s' "$json" | HOME="$FAKE_HOME" "$GUARD" 2>/dev/null)"
  RC=$?
}

# Assert exit 0 AND no block output.
assert_noblock() {
  local desc="$1"
  if [ "$RC" -eq 0 ] && [ -z "$OUT" ]; then
    echo "PASS: $desc (exit 0, no block)"; PASS=$((PASS+1))
  else
    echo "FAIL: $desc (expected exit 0 + empty output; got rc=$RC out=<$OUT>)"; FAIL=$((FAIL+1))
  fi
}

# Assert a block was emitted: exit 0 + JSON with .decision == "block".
assert_block() {
  local desc="$1" dec
  dec="$(printf '%s' "$OUT" | jq -r '.decision // empty' 2>/dev/null || true)"
  if [ "$RC" -eq 0 ] && [ "$dec" = "block" ]; then
    echo "PASS: $desc (decision:block)"; PASS=$((PASS+1))
  else
    echo "FAIL: $desc (expected exit 0 + decision:block; got rc=$RC out=<$OUT>)"; FAIL=$((FAIL+1))
  fi
}

# --- Fixture builders. Each builds a repo with HEAD on drive/<runId> and a RUN_DIR at
#     $RUNS_ROOT/<runId>. Echo the repo path (= cwd for the mock Stop JSON). ---

# A slice merged into a live phaseInt/<runId>/1, slice variant: reviewed | unreviewed.
# Leaves HEAD checked out on drive/<runId> (the /drive session's branch).
mk_run() {
  local name="$1" slicevar="$2"
  local repo="$WORK/$name-repo" rd="$RUNS_ROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  # slice branch with work
  _gitc "$repo" checkout -q -b "slice/$name/4a"
  local stip; stip="$(_commit "$repo" "feature.sh" "echo hi" "slice 4a")"
  # live phaseInt that fast-forward-merged the slice (slice tip is ancestor of phaseInt)
  _gitc "$repo" checkout -q -b "phaseInt/$name/1"
  _write_codex "$rd" "4a"
  case "$slicevar" in
    reviewed)   _write_review "$rd" "4a" 1 "$stip" ;;
    unreviewed) : ;;
  esac
  # the /drive session sits on the feature branch
  _gitc "$repo" checkout -q -b "drive/$name"
  echo "$repo"
}

# A run with NO live phaseInt at all (only a queued/in-flight slice). HEAD on drive/<id>.
mk_run_no_phase() {
  local name="$1"
  local repo="$WORK/$name-repo" rd="$RUNS_ROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" checkout -q -b "slice/$name/4a"
  _commit "$repo" "feature.sh" "echo hi" "slice 4a" >/dev/null
  _write_codex "$rd" "4a"   # rundir exists, no phaseInt
  _gitc "$repo" checkout -q -b "drive/$name"
  echo "$repo"
}

# A NON-drive repo: HEAD on main (not drive/*). RUN_DIR irrelevant.
mk_nondrive() {
  local name="$1"
  local repo="$WORK/$name-repo"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  echo "$repo"   # HEAD = main
}

# An audit-exit-2 run: live phaseInt exists & enumerates via for-each-ref, but its tip
# commit object is corrupt so audit's rev-parse errors → conformance exit 2 → fail-open.
mk_run_git_error() {
  local name="$1"
  local repo="$WORK/$name-repo" rd="$RUNS_ROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" checkout -q -b "phaseInt/$name/1"
  local tip; tip="$(_commit "$repo" "phase.sh" "echo phase" "phase 1")"
  mkdir -p "$rd"; _write_codex "$rd" "phase1"
  # Corrupt the live phaseInt tip object so for-each-ref lists it but rev-parse errors.
  local obj="$repo/.git/objects/${tip:0:2}/${tip:2}"
  if [ -f "$obj" ]; then chmod -R u+w "$repo/.git/objects/${tip:0:2}"; rm -f "$obj"; else
    local p; for p in "$repo"/.git/objects/pack/*.pack; do [ -f "$p" ] || continue; chmod u+w "$p"; : > "$p"; done
  fi
  _gitc "$repo" checkout -q -b "drive/$name" 2>/dev/null || _gitc "$repo" symbolic-ref HEAD "refs/heads/drive/$name"
  echo "$repo"
}

echo "=== AC9: drive-stop-guard ==="

# BLOCK: a slice merged into the live phaseInt but unreviewed.
repo="$(mk_run unreviewedrun unreviewed)"
run_guard "$repo"
assert_block "AC9 blocks: merged-but-unreviewed slice in live phaseInt"

# Persistence: block still fires even when .stop_hook_active=true (no suppression).
run_guard "$repo" true
assert_block "AC9 blocks even with stop_hook_active=true (persistence, edge 7)"

# (b) NO block: merged slice HAS a counting review.
repo="$(mk_run reviewedrun reviewed)"
run_guard "$repo"
assert_noblock "AC9 no block: merged slice is reviewed"

# (a) NO block: no live phaseInt (only a queued/in-flight slice).
repo="$(mk_run_no_phase nophaserun)"
run_guard "$repo"
assert_noblock "AC9 no block: no live phaseInt (paused at gate / in-flight)"

# (c) NO block: HEAD is not a drive branch (non-drive session).
repo="$(mk_nondrive nondriverun)"
run_guard "$repo"
assert_noblock "AC9 no block: HEAD not a drive branch"

# (d) NO block: audit hits exit 2 → fail-open.
repo="$(mk_run_git_error giterrorrun)"
run_guard "$repo"
assert_noblock "AC9 no block: audit exit 2 fails open"

# Inert guards: missing cwd, RUN_DIR absent for a real drive HEAD.
OUT="$(printf '{}' | HOME="$FAKE_HOME" "$GUARD" 2>/dev/null)"; RC=$?
if [ "$RC" -eq 0 ] && [ -z "$OUT" ]; then
  echo "PASS: empty stdin (no cwd) -> inert exit 0"; PASS=$((PASS+1))
else
  echo "FAIL: empty stdin (no cwd) -> expected inert; rc=$RC out=<$OUT>"; FAIL=$((FAIL+1))
fi

# drive HEAD but RUN_DIR absent -> inert (not a managed run).
norun_repo="$WORK/norun-repo"
_init_repo "$norun_repo"
_commit "$norun_repo" "README" "base" "base" >/dev/null
_gitc "$norun_repo" checkout -q -b "drive/no-such-run-dir-xyz"
run_guard "$norun_repo"
assert_noblock "AC9 no block: drive HEAD but RUN_DIR absent (not managed)"

echo
echo "===================================="
echo "PASS=$PASS  FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
