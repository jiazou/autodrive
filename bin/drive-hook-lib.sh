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
