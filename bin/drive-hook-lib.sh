#!/usr/bin/env bash
# drive-hook-lib.sh — sourceable ref→run resolution library (D3: ref-keyed
# self-location, no sentinel). Pure ref parsing + existence checks; no mutable
# state, no side effects on source. Hooks source this to derive the runId of a
# /drive run from the git ref named in a command (or from the cwd's HEAD), then
# locate its run dir.
#
# runId is a SINGLE path segment (e.g. drive-review-hooks-20260603-135659).
# Refs are exactly:
#   drive/<runId>            — the feature branch
#   slice/<runId>/<id>       — a slice branch; <id> is one segment (4a, 1.2, …)
#   phaseInt/<runId>/<P>     — a run-keyed integration branch
#
# Functions echo the runId on success (rc 0) or return 1 if none resolves.

# drive_runid_from_command <cmd>
# Echo the runId parsed from the first drive/<runId>, slice/<runId>/<id>, or
# phaseInt/<runId>/<P> token in the command string. Return 1 if none found.
drive_runid_from_command() {
  local cmd="${1-}"
  # Extract candidate ref tokens WITHOUT word-splitting/globbing the raw command:
  # grep -oE over the literal string. The charset [A-Za-z0-9._/-] naturally stops
  # at quotes, spaces, and the `:` refspec separator, so:
  #   git merge "slice/R/4a"          -> slice/R/4a   (quotes excluded)
  #   git push origin drive/R:drive/R -> drive/R      (stops at ':')
  #   HEAD:refs/heads/slice/R/4a      -> slice/R/4a   (token starts at slice/)
  # A literal `*` in the command never reaches the shell as a glob (no $cmd split),
  # and `*` is not in the charset so it cannot pollute a token.
  # LEFT segment boundary: the keyword (drive|slice|phaseInt) must be at the
  # start of the string OR preceded by a char that is NOT [A-Za-z0-9._-]. This
  # rejects larger unmanaged names (nondrive/R, noslice/R/4a, foo-phaseInt/R/1)
  # while keeping '/' a valid boundary so refspec/path forms still resolve
  # (HEAD:refs/heads/slice/R/4a, refs/heads/drive/R). grep captures the single
  # leading boundary char (when not start-of-string); strip it before parsing.
  local tok runid
  while IFS= read -r tok; do
    [ -n "$tok" ] || continue
    # Strip one leading boundary char (anything that isn't part of a keyword/ref
    # token). start-of-string matches leave tok already keyword-leading.
    case "$tok" in
      drive/*|slice/*|phaseInt/*) ;;     # already keyword-leading
      *) tok="${tok#?}" ;;               # drop the captured boundary char
    esac
    case "$tok" in
      drive/*)
        # Require EXACTLY drive/<runId> (2 segments). Reject drive/R/extra.
        local rest="${tok#drive/}"
        case "$rest" in
          */*) continue ;;            # extra segment(s) -> not a bare drive ref
          "") continue ;;
        esac
        printf '%s\n' "$rest"; return 0
        ;;
      slice/*)
        # Require EXACTLY slice/<runId>/<id> (3 segments). Reject 2 or 4+.
        local rest="${tok#slice/}"    # want <runId>/<id> with no further slash
        case "$rest" in
          */*/*) continue ;;          # 4+ segments -> reject
          */*)
            runid="${rest%%/*}"
            [ -n "$runid" ] && { printf '%s\n' "$runid"; return 0; }
            ;;
          *) continue ;;              # only 2 segments (slice/<runId>) -> reject
        esac
        ;;
      phaseInt/*)
        # Require EXACTLY phaseInt/<runId>/<P> (3 segments). Reject 2 or 4+.
        local rest="${tok#phaseInt/}"
        case "$rest" in
          */*/*) continue ;;          # 4+ segments -> reject
          */*)
            runid="${rest%%/*}"
            [ -n "$runid" ] && { printf '%s\n' "$runid"; return 0; }
            ;;
          *) continue ;;              # only 2 segments -> reject
        esac
        ;;
    esac
  done <<EOF
$(printf '%s' "$cmd" | grep -oE '(^|[^A-Za-z0-9._-])(drive|slice|phaseInt)/[A-Za-z0-9._/-]+')
EOF
  return 1
}

# drive_runid_from_head <cwd>
# Resolve the current branch in <cwd>; if it is drive/<runId>, echo runId.
# Return 1 if not a drive branch or git fails.
drive_runid_from_head() {
  local cwd="${1-}"
  local branch
  branch="$(git -C "$cwd" rev-parse --abbrev-ref HEAD 2>/dev/null)" || return 1
  case "$branch" in
    drive/*)
      # Require EXACTLY drive/<runId> (2 segments). Reject drive/R/extra.
      local runid="${branch#drive/}"
      case "$runid" in
        */*) return 1 ;;            # extra segment(s) -> not the feature branch
        "") return 1 ;;
      esac
      printf '%s\n' "$runid"; return 0
      ;;
  esac
  return 1
}

# drive_run_dir <runId>
# Echo $HOME/.claude/harness-runs/<runId> if that directory exists; else rc 1.
drive_run_dir() {
  local runid="${1-}"
  [ -n "$runid" ] || return 1
  local dir="$HOME/.claude/harness-runs/$runid"
  [ -d "$dir" ] && { printf '%s\n' "$dir"; return 0; }
  return 1
}

# drive_scan_active_runs
#   Echo (stdout) the newline-separated list of ACTIVE /drive run directories under
#   $HOME/.claude/harness-runs; empty output iff none active. rc 0 if >=1 emitted, else 1.
#   The SHARED active-run predicate for both the PreToolUse tool gate (drive-tool-gate.sh)
#   and the WorktreeCreate gate (drive-worktree-gate.sh) — byte-faithful to the scan the
#   tool gate ran inline (see docs/drive-enforcement.md "Activation predicate"):
#     - window = DRIVE_TOOL_GATE_LIVE_HOURS hours (default 24; non-numeric/<=0 -> 24) -> MINS
#     - candidates = dirs with a state.json OR event-log.jsonl mtime within MINS
#       (find -maxdepth 2 ... -mmin "-$MINS" | dirname | sort -u)
#     - ACTIVE iff state.json is a REGULAR file that jq-parses with .stage a non-empty
#       string != "done" AND .repoRoot non-empty
#     - corrupt/unreadable state.json -> skip WITH a stderr warning ("drive-tool-gate:
#       skipping unreadable/corrupt state.json in <D>")
#     - empty repoRoot -> skip WITH a stderr warning ("drive-tool-gate: skipping active run
#       with no repoRoot in <D>")
#     - absent/non-regular state.json -> silent skip
#   PRECONDITION: jq present (callers guarantee it — the tool gate static-denies on jq-absent
#   before reaching the scan; the worktree gate fail-CLOSES on jq-absent itself). Pure read;
#   the only side effects are the two stderr warnings above (fail-closed = own logic only,
#   never fail-closed on third-party dir contents).
drive_scan_active_runs() {
  local RUNS_ROOT H MINS CAND_DIRS ACTIVE_RUNS D sj stage rr
  RUNS_ROOT="$HOME/.claude/harness-runs"

  H="${DRIVE_TOOL_GATE_LIVE_HOURS:-24}"
  case "$H" in ''|*[!0-9]*) H=24 ;; esac
  [ "$H" -gt 0 ] 2>/dev/null || H=24
  MINS=$((H * 60))

  # Liveness-bounded candidate dirs: run dirs with a state.json OR event-log.jsonl touched
  # within the window. macOS/BSD-safe (no -printf; dirname in a loop; <= tens of dirs).
  CAND_DIRS="$(
    find "$RUNS_ROOT" -maxdepth 2 \( -name state.json -o -name event-log.jsonl \) -mmin "-$MINS" 2>/dev/null \
      | while IFS= read -r f; do dirname "$f"; done | sort -u
  )"

  # Validate each candidate: state.json a regular file that PARSES with stage != "done".
  # Corrupt/unreadable state.json -> skip WITH a stderr warning (fail-closed = own logic
  # only, never third-party dir contents). Absent/non-regular state.json -> silent skip.
  ACTIVE_RUNS=""
  while IFS= read -r D; do
    [ -n "$D" ] || continue
    sj="$D/state.json"
    [ -e "$sj" ] || continue           # no state.json -> not an active run (silent)
    [ -f "$sj" ] || continue           # non-regular (symlink-to-fifo/device) -> skip, out of threat model
    if ! stage="$(jq -r '.stage // ""' "$sj" 2>/dev/null)"; then
      printf 'drive-tool-gate: skipping unreadable/corrupt state.json in %s\n' "$D" >&2
      continue
    fi
    [ -n "$stage" ] || continue        # parsed but no stage -> not routable-active (silent)
    [ "$stage" = "done" ] && continue  # explicitly done -> not active
    # Require a non-empty repoRoot: a run with stage!=done but no/empty repoRoot cannot be
    # repo-scoped, and passing "" downstream would make `git -C ""` resolve to the HOOK's own
    # cwd. Skip-with-warning (same visibility as a corrupt dir) so it can never mis-scope.
    rr="$(jq -r '.repoRoot // ""' "$sj" 2>/dev/null || true)"
    if [ -z "$rr" ]; then
      printf 'drive-tool-gate: skipping active run with no repoRoot in %s\n' "$D" >&2
      continue
    fi
    ACTIVE_RUNS="$ACTIVE_RUNS$D
"
  done <<EOF
$CAND_DIRS
EOF

  [ -n "$ACTIVE_RUNS" ] || return 1
  printf '%s' "$ACTIVE_RUNS"
  return 0
}
