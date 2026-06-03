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
  local tok
  # Scan whitespace-separated tokens; pick the first that names a drive ref.
  # A token may have leading refspec decoration (e.g. +refs/…) but the gate
  # commands name bare branch refs, so match the ref form directly.
  for tok in $cmd; do
    case "$tok" in
      drive/*)
        # drive/<runId> — runId is everything after "drive/", first segment.
        local rest="${tok#drive/}"
        rest="${rest%%/*}"
        [ -n "$rest" ] && { printf '%s\n' "$rest"; return 0; }
        ;;
      slice/*/*)
        # slice/<runId>/<id> — runId is the segment between slice/ and /<id>.
        local rest="${tok#slice/}"     # <runId>/<id>[/...]
        local runid="${rest%/*}"       # strip the final /<id>
        runid="${runid%%/*}"           # runId is a single segment
        [ -n "$runid" ] && { printf '%s\n' "$runid"; return 0; }
        ;;
      phaseInt/*/*)
        # phaseInt/<runId>/<P> — runId is the segment after phaseInt/.
        local rest="${tok#phaseInt/}"
        local runid="${rest%%/*}"
        [ -n "$runid" ] && { printf '%s\n' "$runid"; return 0; }
        ;;
    esac
  done
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
      local runid="${branch#drive/}"
      runid="${runid%%/*}"
      [ -n "$runid" ] && { printf '%s\n' "$runid"; return 0; }
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
