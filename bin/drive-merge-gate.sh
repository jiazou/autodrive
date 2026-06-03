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

# detect_subcommand <binary> <words...> : echo the real subcommand for a binary
# invocation, i.e. the first NON-flag word AFTER the binary, skipping:
#   - env `VAR=val` prefixes that precede the binary (handled by the caller, which
#     scans for the binary first; this fn is called with the binary as $1),
#   - global options that take a separate argument: `-C <path>`, `-c <kv>`,
#     `-R <x>`, `--repo <x>` (consume the following word),
#   - inline global options: `--git-dir=…`, `--work-tree=…`, `--repo=…`,
#   - generic short `-x` and long `--x` / `--x=y` flags.
# Returns the subcommand on stdout (empty if none). bash 3.2-safe (positional args).
detect_subcommand() {
  shift                                   # drop the binary itself ($1)
  while [ "$#" -gt 0 ]; do
    case "$1" in
      # global options that consume the NEXT word as their value:
      -C|-c|-R|--repo|--git-dir|--work-tree)
        shift; [ "$#" -gt 0 ] && shift; continue ;;
      # inline `--opt=value` (and `--opt` with no value): a single flag word.
      --*=*|--*) shift; continue ;;
      # short flags `-x` (incl. clustered like `-xyz`): a single flag word.
      -?*) shift; continue ;;
      # bare `-` or empty → not a subcommand; stop.
      -|"") break ;;
      # first non-flag word → this is the real subcommand.
      *) printf '%s' "$1"; return 0 ;;
    esac
  done
  return 0
}

# subcommand_of <binary> : tokenize $CMD (word-split is intentional here — we only
# read the leading binary+flags region), locate the FIRST occurrence of <binary> as
# a bare word (skipping any leading env VAR=val prefixes), then return the real
# subcommand via detect_subcommand. Echoes empty if the binary isn't invoked.
# NOTE: this inspects the *literal* command; runtime-variable refs in later args are
# handled elsewhere. bash 3.2-safe.
subcommand_of() {
  local bin="$1" w found=false
  set -f                                   # noglob: a literal `*` in $CMD must not expand.
  # shellcheck disable=SC2086  # intentional word-split of the command string.
  set -- $CMD
  set +f
  local -a after=()
  while [ "$#" -gt 0 ]; do
    w="$1"; shift
    if [ "$found" = false ]; then
      case "$w" in
        "$bin") found=true; after=("$w" "$@"); break ;;
        *) continue ;;                    # env VAR=val prefix or other leading token
      esac
    fi
  done
  [ "$found" = true ] || { printf ''; return 0; }
  detect_subcommand "${after[@]}"
}

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

# Identify the REAL subcommand for each candidate binary (first non-flag word after
# the binary, skipping env VAR=val prefixes + global options). This is what defeats
# the contiguous-binary+subcommand bypass: `git -C repo push`, `git -c k=v push`,
# `gh --repo o/r pr create`, `glab -R x mr create` all resolve their subcommand here.
git_sub="$(subcommand_of git)"
gh_sub="$(subcommand_of gh)"
glab_sub="$(subcommand_of glab)"

# Extract every slice/<runId>/<id> token (3-segment) appearing in the command.
# Used both for matching AND for gating EACH slice in a multi-slice merge.
slice_tokens="$(printf '%s' "$CMD" | grep -oE '(^|[^A-Za-z0-9._-])slice/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+' 2>/dev/null || true)"

# Extract the FIRST phaseInt/... token as it appears in the command. We accept ANY
# phaseInt/<...> arg form (not only the 3-segment phaseInt/<runId>/<P>) so the gate
# stays correct regardless of phaseInt naming (Slice 3.1 ordering). The last path
# segment is taken as P and passed to conformance, which keys phase-merge by P.
phaseint_token="$(printf '%s' "$CMD" | grep -oE '(^|[^A-Za-z0-9._-])phaseInt/[A-Za-z0-9._/-]+' 2>/dev/null | head -n1 || true)"

# --- ship detection ---
# `gh pr create` / `glab mr create` / any `git push` (incl bare, -u origin HEAD).
# Subcommand-based so global flags before the subcommand don't bypass.
case "$gh_sub" in pr) case "$CMD" in *create*) is_ship=true ;; esac ;; esac
case "$glab_sub" in mr) case "$CMD" in *create*) is_ship=true ;; esac ;; esac
[ "$git_sub" = push ] && is_ship=true

# --- plan-gate detection: `git worktree add ... -b slice/<runId>/<id>` ---
if [ "$git_sub" = worktree ] && [ -n "$slice_tokens" ]; then
  is_plan_gate=true
fi

# --- phase-merge detection ---
# `git branch -f drive/<runId> <phaseIntRef>` OR `git merge ... <phaseIntRef>`.
# runId is derived (in the resolve step) from the drive/<runId> token; here we only
# extract P = last segment of the phaseInt ref AS IT APPEARS in the command.
if [ -n "$phaseint_token" ] && { [ "$git_sub" = branch ] || [ "$git_sub" = merge ]; }; then
  is_phase_merge=true
  pt="$phaseint_token"
  case "$pt" in phaseInt/*) ;; *) pt="${pt#?}" ;; esac   # strip leading boundary char
  phase_P="${pt##*/}"            # P = final path segment of the phaseInt ref
fi

# --- slice-merge detection: `git merge ... slice/<runId>/<id>` (and NOT a worktree add).
if [ "$is_plan_gate" = false ] && [ "$git_sub" = merge ] && [ -n "$slice_tokens" ]; then
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
# run_conformance <mode-arg> : runs the checker from $CWD and returns a NORMALIZED rc
# (D4). We must distinguish three things the raw exit code conflates:
#   - a real conformance verdict (0 clean / 1 violation / 2 git-IO error),
#   - a broken checker (missing/non-exec → 126/127),
#   - a `cd "$CWD"` failure (e.g. cwd was deleted), which must NOT masquerade as a
#     conformance verdict (a bare `cd` failure yields rc 1 ≡ "violation", which would
#     wrongly DENY the mid-build gates).
# Normalized rc contract:
#   0 = clean | 1 = violation | 9 = abnormal (checker broken, cd-fail, or any other rc)
# Callers map 9 per-mode: run-boundary gates (plan/ship) treat 9 as fail-CLOSED (deny);
# mid-build gates (slice/phase) treat 9 as fail-OPEN (silent). 2 is folded into 9
# (D4 treats exit-2 and the other abnormal rcs identically per gate class).
# Run from $CWD so conformance's bare-`git` ref lookups resolve against the target repo.
run_conformance() {
  # Verify the checker is present + executable up front; otherwise it's "abnormal".
  [ -x "$CONFORMANCE" ] || return 9
  # Probe the cd separately so a cd failure can't be read as a conformance verdict.
  ( cd "$CWD" ) 2>/dev/null || return 9
  local rc
  ( cd "$CWD" && "$CONFORMANCE" "$RUN_DIR" --mode "$1" ) >/dev/null 2>&1
  rc=$?
  case "$rc" in
    0) return 0 ;;
    1) return 1 ;;
    *) return 9 ;;     # 2, 126, 127, or anything else → abnormal
  esac
}

if [ "$is_plan_gate" = true ]; then
  run_conformance "plan-gate"; rc=$?
  # Run-boundary gate, fail-CLOSED: rc 1 (violation) OR 9 (abnormal: error / broken
  # checker / cd-fail) → DENY. Only rc 0 (clean) allows (silent).
  if [ "$rc" -ne 0 ]; then
    emit_deny "Plan/design review not converged for run $runId. Run \`/drive-review design\` until it converges, then retry: implementation cannot begin until the design review is CONVERGED (with codex)."
  fi
  exit 0
fi

if [ "$is_slice_merge" = true ]; then
  # Mid-build per-unit gate, fail-OPEN: gate EACH slice id; DENY only on rc 1 (true
  # violation). rc 9 (abnormal: error / broken checker / cd-fail) → silent allow
  # (the ship gate backstops). NOTE: runtime-variable slice refs in $CMD (e.g.
  # `git merge "slice/$v/$id"`) cannot be expanded by the hook from the literal
  # command, so such merges silently pass here — they are backstopped by the ship
  # gate (HEAD-based, whole-tip diff) plus the drive.md literal-ref instruction
  # (Slice 3.1 owns that doc note).
  for sid in $slice_ids; do
    [ -n "$sid" ] || continue
    run_conformance "slice-merge:$sid"; rc=$?
    if [ "$rc" -eq 1 ]; then
      emit_deny "Slice $sid is not reviewed for its current tip. Run \`/drive-review slice $sid\` until it converges, then retry the merge."
    fi
  done
  exit 0
fi

if [ "$is_phase_merge" = true ]; then
  # Mid-build per-unit gate, fail-OPEN: DENY only on rc 1; rc 9 → silent allow.
  # (Same runtime-variable-ref limitation as slice-merge above; ship gate backstops.)
  run_conformance "phase-merge:$phase_P"; rc=$?
  if [ "$rc" -eq 1 ]; then
    emit_deny "Phase $phase_P is not reviewed for its current integration tip. Run \`/drive-review phase $phase_P\` until it converges, then retry the advance."
  fi
  exit 0
fi

if [ "$is_ship" = true ]; then
  run_conformance "ship"; rc=$?
  # Run-boundary gate, fail-CLOSED: rc 1 OR 9 → DENY; only rc 0 allows (silent).
  if [ "$rc" -ne 0 ]; then
    emit_deny "The code being shipped for run $runId is not fully covered by a converged review. Run \`/drive-review ship\` (review the shipped diff) until it converges, then retry the push/PR."
  fi
  exit 0
fi

exit 0
