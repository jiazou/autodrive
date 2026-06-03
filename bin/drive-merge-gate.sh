#!/usr/bin/env bash
# drive-merge-gate.sh — PreToolUse(Bash) hook: the primary /drive enforcement gate.
#
# Reads the hook JSON on stdin (.tool_input.command, .cwd via jq). Matches the
# command against the gate matcher table, resolves the runId of the /drive run, runs
# drive-conformance.sh for the matched mode, and — ONLY on a conformance violation —
# emits a PreToolUse `deny` whose reason names the scope + the exact /drive-review
# command to run before retrying.
#
# Composition contract (D5): the gate emits `deny` ONLY. Clean OR non-matching
# command → NO output, exit 0. This lets it compose with the existing Bash PreToolUse
# hooks (which emit `allow`/`ask`) and never override their decisions; correctness
# relies on Claude Code's documented deny-beats-allow precedence for same-event hooks.
#
# Fail mode (D4, asymmetric): plan-gate + ship are RUN-BOUNDARY gates → on a
# conformance exit 2 (git/IO error) they fail CLOSED (DENY). slice-merge + phase-merge
# are mid-build per-unit gates → on exit 2 they fail OPEN (silent, exit 0) so a
# transient git error cannot wedge a mid-build run; the ship gate backstops them.
#
# Locate sibling scripts robustly (works installed or in a worktree).
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
. "$SCRIPT_DIR/drive-hook-lib.sh"
CONFORMANCE="$SCRIPT_DIR/drive-conformance.sh"

# Emit a PreToolUse deny with the given reason (JSON-escaped) and exit 0.
# (We exit 0 because the *hook* ran fine — the deny verdict is carried in the JSON,
# not in the hook's exit code.)
emit_deny() {
  local reason="$1"
  # JSON-escape: backslash, double-quote, then control chars (newline/tab/CR).
  reason="${reason//\\/\\\\}"
  reason="${reason//\"/\\\"}"
  reason="${reason//$'\n'/\\n}"
  reason="${reason//$'\t'/\\t}"
  reason="${reason//$'\r'/\\r}"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$reason"
  exit 0
}

# --- read hook JSON from stdin ---
INPUT="$(cat)"
CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)"
[ -n "$CMD" ] || exit 0
[ -n "$CWD" ] || CWD="$PWD"

# --- match the command to a gate mode ---------------------------------------------
# We classify by structural git/ship intent. A command that matches no class →
# exit 0 silent (inert; not a managed-run transition).

is_plan_gate=false
is_slice_merge=false
is_phase_merge=false
is_ship=false
phase_P=""

# Collect slice ids (multi-slice merge support) into a plain string (bash 3.2-safe).
slice_ids=""

# Extract every slice/<runId>/<id> token (3-segment) appearing in the command.
# Used both for matching AND for gating EACH slice in a multi-slice merge.
slice_tokens="$(printf '%s' "$CMD" | grep -oE '(^|[^A-Za-z0-9._-])slice/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+' 2>/dev/null || true)"

# Extract phaseInt/<runId>/<P> token (3-segment).
phaseint_token="$(printf '%s' "$CMD" | grep -oE '(^|[^A-Za-z0-9._-])phaseInt/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+' 2>/dev/null | head -n1 || true)"

# --- ship detection ---
# gh pr create / glab mr create / any `git push` (incl bare, -u origin HEAD, origin HEAD).
case "$CMD" in
  *"gh pr create"*) is_ship=true ;;
  *"glab mr create"*) is_ship=true ;;
esac
# git push (word-boundary): "git push", "git push ...". Avoid matching "git pushfoo".
if printf '%s' "$CMD" | grep -qE '(^|[^A-Za-z0-9._-])git[[:space:]]+push([[:space:]]|$)'; then
  is_ship=true
fi

# --- plan-gate detection: `git worktree add ... -b slice/<runId>/<id>` ---
if printf '%s' "$CMD" | grep -qE '(^|[^A-Za-z0-9._-])git[[:space:]]+worktree[[:space:]]+add'; then
  if [ -n "$slice_tokens" ]; then
    is_plan_gate=true
  fi
fi

# --- phase-merge detection ---
# `git branch -f drive/<runId> phaseInt/<runId>/<P>` OR `git merge ... phaseInt/<runId>/<P>`.
if [ -n "$phaseint_token" ]; then
  if printf '%s' "$CMD" | grep -qE '(^|[^A-Za-z0-9._-])git[[:space:]]+branch([[:space:]]|$)' \
     || printf '%s' "$CMD" | grep -qE '(^|[^A-Za-z0-9._-])git[[:space:]]+merge([[:space:]]|$)'; then
    is_phase_merge=true
    # derive P (3rd segment) from the token, stripping a leading boundary char.
    pt="$phaseint_token"
    case "$pt" in phaseInt/*) ;; *) pt="${pt#?}" ;; esac
    rest="${pt#phaseInt/}"          # <runId>/<P>
    phase_P="${rest#*/}"            # <P>
  fi
fi

# --- slice-merge detection: `git merge ... slice/<runId>/<id>` (and NOT a worktree add).
if [ "$is_plan_gate" = false ] && [ -n "$slice_tokens" ]; then
  if printf '%s' "$CMD" | grep -qE '(^|[^A-Za-z0-9._-])git[[:space:]]+merge([[:space:]]|$)'; then
    is_slice_merge=true
    # collect each slice id (strip boundary char, take 3rd segment)
    while IFS= read -r st; do
      [ -n "$st" ] || continue
      case "$st" in slice/*) ;; *) st="${st#?}" ;; esac
      r="${st#slice/}"             # <runId>/<id>
      sid="${r#*/}"                # <id>
      [ -n "$sid" ] && slice_ids="$slice_ids$sid "
    done <<EOF
$slice_tokens
EOF
  fi
fi

# If nothing matched, inert.
if [ "$is_plan_gate" = false ] && [ "$is_slice_merge" = false ] \
   && [ "$is_phase_merge" = false ] && [ "$is_ship" = false ]; then
  exit 0
fi

# --- resolve runId + RUN_DIR ------------------------------------------------------
# From the command ref first; for ship commands that carry no slice/drive/phaseInt
# token (bare `git push`, `gh pr create`), fall back to the cwd HEAD.
runId=""
if runId="$(drive_runid_from_command "$CMD")"; then
  :
elif [ "$is_ship" = true ] && runId="$(drive_runid_from_head "$CWD")"; then
  :
else
  runId=""
fi
[ -n "$runId" ] || exit 0          # not a managed run → inert

RUN_DIR=""
if ! RUN_DIR="$(drive_run_dir "$runId")"; then
  exit 0                           # RUN_DIR absent → treat as not-a-managed-run
fi

# --- run conformance for the matched mode -----------------------------------------
# run_conformance <mode-arg> : runs the checker, returns its exit code, captures nothing.
# Caller inspects $? : 0 clean, 1 violation, 2 git/IO error.
# Run it from $CWD so its git ref lookups (slice/phaseInt/drive refs, diffs) resolve
# against the repo the command targets — conformance uses bare `git` (cwd-relative).
run_conformance() {
  ( cd "$CWD" 2>/dev/null && "$CONFORMANCE" "$RUN_DIR" --mode "$1" ) >/dev/null 2>&1
}

if [ "$is_plan_gate" = true ]; then
  run_conformance "plan-gate"; rc=$?
  if [ "$rc" -eq 1 ] || [ "$rc" -eq 2 ]; then
    # run-boundary gate: violation OR error (fail-closed) → DENY.
    emit_deny "Plan/design review not converged for run $runId. Run \`/drive-review design\` until it converges, then retry: implementation cannot begin until the design review is CONVERGED (with codex)."
  fi
  exit 0
fi

if [ "$is_slice_merge" = true ]; then
  # Gate EACH slice id; deny on the first that fails (fail-OPEN on exit 2).
  for sid in $slice_ids; do
    [ -n "$sid" ] || continue
    run_conformance "slice-merge:$sid"; rc=$?
    if [ "$rc" -eq 1 ]; then
      emit_deny "Slice $sid is not reviewed for its current tip. Run \`/drive-review slice $sid\` until it converges, then retry the merge."
    fi
    # rc==2 → fail-open: skip this slice (mid-build transient git error; ship backstops).
  done
  exit 0
fi

if [ "$is_phase_merge" = true ]; then
  run_conformance "phase-merge:$phase_P"; rc=$?
  if [ "$rc" -eq 1 ]; then
    emit_deny "Phase $phase_P is not reviewed for its current integration tip. Run \`/drive-review phase $phase_P\` until it converges, then retry the advance."
  fi
  # rc==2 → fail-open (mid-build).
  exit 0
fi

if [ "$is_ship" = true ]; then
  run_conformance "ship"; rc=$?
  if [ "$rc" -eq 1 ] || [ "$rc" -eq 2 ]; then
    # run-boundary gate: violation OR error (fail-closed) → DENY.
    emit_deny "The code being shipped for run $runId is not fully covered by a converged review. Run \`/drive-review ship\` (review the shipped diff) until it converges, then retry the push/PR."
  fi
  exit 0
fi

exit 0
