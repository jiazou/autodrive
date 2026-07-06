#!/usr/bin/env bash
# Idempotently wire the four /drive enforcement hooks into a settings.json (five entries):
#   - PreToolUse(matcher "Bash") -> bin/drive-merge-gate.sh   (merge/ship/plan gate)
#   - Stop                        -> bin/drive-stop-guard.sh   (review backstop)
#   - PreToolUse(GitHub/GitLab-MCP writes) + PreToolUse(Agent|EnterWorktree)
#                                 -> bin/drive-tool-gate.sh   (non-Bash tool gate; two entries)
#   - WorktreeCreate              -> bin/drive-worktree-gate.sh (authoritative native-worktree gate)
# Mirrors bin/install-operating-rules.sh: set -euo pipefail, REPO_DIR from BASH_SOURCE,
# a timestamped backup before mutating. Keyed on the script BASENAME (not the full
# path): re-running is a no-op when the path is unchanged, and when the repo has moved
# or been renamed (e.g. claude-harness -> autodrive) it MIGRATES the existing entry to
# the new path instead of leaving a stale, dead path behind and adding a duplicate.
# All non-managed hooks are preserved. Fails loudly on malformed JSON. The repo never
# commits ~/.claude/settings.json.
#
# Target: $1 (if given) else $DRIVE_HOOKS_SETTINGS (so tests can point at a temp file)
# else $HOME/.claude/settings.json.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETTINGS="${1:-${DRIVE_HOOKS_SETTINGS:-$HOME/.claude/settings.json}}"

MERGE_GATE="$REPO_DIR/bin/drive-merge-gate.sh"
STOP_GUARD="$REPO_DIR/bin/drive-stop-guard.sh"
TOOL_GATE="$REPO_DIR/bin/drive-tool-gate.sh"
WT_GATE="$REPO_DIR/bin/drive-worktree-gate.sh"

# The MCP write-tool matcher (D-p2-3): enumerated, longest-first alternation, server-segment
# wildcarded (`mcp__.+__` — the server name is user-chosen at install). Longest-first so
# update_pull_request cannot shadow update_pull_request_branch under any regex engine. Covers
# the GitHub PR-write tools AND (G2) the GitLab merge_request-write tools.
TOOL_GATE_MCP_MATCHER='^mcp__.+__(update_pull_request_branch|create_or_update_file|create_merge_request|accept_merge_request|rebase_merge_request|merge_merge_request|update_merge_request|create_pull_request|merge_pull_request|update_pull_request|create_branch|delete_file|push_files)$'
TOOL_GATE_NATIVE_MATCHER='^(Agent|EnterWorktree)$'

# --- Disclosure banner (ALWAYS printed) ---------------------------------------
# Tell the user exactly what this touches before anything is modified.
cat >&2 <<BANNER
============================================================
  /drive enforcement hooks — installer
============================================================
This modifies your Claude Code settings file:
  $SETTINGS

It adds four hooks (five settings entries; existing hooks are
preserved; a timestamped backup of the settings file is written first):

  • PreToolUse(Bash) -> $MERGE_GATE
      Fires on every Bash tool call. The gate itself decides whether
      to act — only /drive plan/merge/ship git operations are gated;
      everything else passes straight through.
  • Stop             -> $STOP_GUARD
      A review backstop that runs when a session stops.
  • PreToolUse(GitHub/GitLab-MCP writes; Agent/EnterWorktree) -> $TOOL_GATE
      Two entries. Deny-routes GitHub- and GitLab-MCP write tools and native
      worktree tools back to the gated Bash paths while a /drive run is active
      on the same repo; passes everything else silently.
  • WorktreeCreate   -> $WT_GATE
      Blocks native worktree creation (--worktree / subagent isolation:"worktree")
      while a /drive run is active — the authoritative interception the PreToolUse
      gate can miss for the frontmatter path; provisions normally when idle
      (recoverable route-to-Bash: git worktree add … -b slice/<runId>/<id>).

The repo never commits ~/.claude/settings.json.
What these hooks do and their threat model: see SECURITY.md.
============================================================
BANNER

# --- Deployment-drift preflight (READ-ONLY; D-p2-7 / D8) -----------------------
# Run AFTER the banner and BEFORE the confirm prompt (the human sees drift before
# consenting) and before any backup/mutation. WARN-ONLY: it never changes the exit
# status, never writes, never copies. Two-artifact read surface: the target $SETTINGS
# (to derive LIVE_DIR = where the live gates actually run from) and the files under
# LIVE_DIR — it NEVER assumes LIVE_DIR == $REPO_DIR/bin. cmp/test/jq only (no copy-class
# op — layout-suite assertion 5 stays green). set -e-safe: every check is an if/|| so a
# nonzero cmp/[ -f ]/jq WARNs and CONTINUES rather than aborting the whole install.
drift_preflight() {
  # Nothing to compare against before the settings file exists (this runs BEFORE the
  # create-settings step, so a fresh install has no file to read yet).
  [ -f "$SETTINGS" ] || return 0

  # (a) LIVE_DIR = dirname of the FIRST PreToolUse command that is a LONE path ending in
  # /drive-merge-gate.sh (no whitespace/shell metachars — a wrapped custom hook is skipped).
  local live_cmd live_dir have_tool have_mcp have_native
  live_cmd="$(jq -r '
    [ .hooks.PreToolUse[]?.hooks[]?.command // ""
      | select((endswith("/drive-merge-gate.sh") or . == "drive-merge-gate.sh")
               and (test("[[:space:]|&;<>()`$]") | not)) ]
    | first // ""' -- "$SETTINGS" 2>/dev/null || true)"
  # No prior managed merge-gate entry → nothing has drifted → silent.
  [ -n "$live_cmd" ] || return 0
  live_dir="$(dirname -- "$live_cmd")"

  # is a tool-gate entry already registered? (a LONE drive-tool-gate.sh path)
  have_tool="$(jq -r '
    [ .hooks.PreToolUse[]?.hooks[]?.command // ""
      | select((endswith("/drive-tool-gate.sh") or . == "drive-tool-gate.sh")
               and (test("[[:space:]|&;<>()`$]") | not)) ]
    | first // ""' -- "$SETTINGS" 2>/dev/null || true)"

  if [ "$live_dir" != "$REPO_DIR/bin" ]; then
    # Variant 2 — migrate hazard / installer-hijack: re-running THIS installer migrates the
    # live gates to this checkout's bin (basename-keyed canonicalization).
    printf 'WARN(drive-hooks drift): live gates run from %s, not this checkout — re-running THIS installer will MIGRATE them to %s/bin. If %s is the pinned enforcement worktree, ABORT (Ctrl-C / answer n) and re-run install-drive-hooks.sh from INSIDE that worktree.\n' "$live_dir" "$REPO_DIR" "$live_dir" >&2
    # Variant 3 — the live enforcement worktree lacks the sibling hook.
    if [ ! -f "$live_dir/drive-tool-gate.sh" ]; then
      printf 'WARN(drive-hooks drift): live enforcement worktree lacks drive-tool-gate.sh — advance that worktree, then re-run bin/install-drive-hooks.sh from INSIDE it.\n' >&2
    fi
    # Variant 3w — the live enforcement worktree lacks the authoritative worktree gate.
    if [ ! -f "$live_dir/drive-worktree-gate.sh" ]; then
      printf 'WARN(drive-hooks drift): live enforcement worktree lacks drive-worktree-gate.sh — advance that worktree, then re-run bin/install-drive-hooks.sh from INSIDE it.\n' >&2
    fi
    # Variant 5 — the live merge gate differs byte-wise from this checkout's (worktree lags).
    if [ -f "$live_dir/drive-merge-gate.sh" ]; then
      if ! cmp -s "$live_dir/drive-merge-gate.sh" "$REPO_DIR/bin/drive-merge-gate.sh"; then
        printf "WARN(drive-hooks drift): live drive-merge-gate.sh differs from this checkout's (worktree lags or diverged).\n" >&2
      fi
    fi
    return 0
  fi

  # LIVE_DIR == this checkout's bin.
  if [ ! -f "$live_dir/drive-tool-gate.sh" ]; then
    printf 'WARN(drive-hooks drift): live enforcement worktree lacks drive-tool-gate.sh — advance that worktree, then re-run bin/install-drive-hooks.sh from INSIDE it.\n' >&2
    return 0
  fi
  # Sibling present; check tool-gate registration completeness across BOTH required matchers.
  # The installer wires drive-tool-gate.sh on TWO matchers (MCP-write + Agent|EnterWorktree);
  # detect a lone (unwrapped) tool-gate command under EACH matcher separately.
  have_mcp="$(jq -r --arg m "$TOOL_GATE_MCP_MATCHER" '
    [ .hooks.PreToolUse[]? | select(.matcher == $m) | .hooks[]?.command // ""
      | select((endswith("/drive-tool-gate.sh") or . == "drive-tool-gate.sh")
               and (test("[[:space:]|&;<>()`$]") | not)) ]
    | (length > 0)' -- "$SETTINGS" 2>/dev/null || true)"
  have_native="$(jq -r --arg m "$TOOL_GATE_NATIVE_MATCHER" '
    [ .hooks.PreToolUse[]? | select(.matcher == $m) | .hooks[]?.command // ""
      | select((endswith("/drive-tool-gate.sh") or . == "drive-tool-gate.sh")
               and (test("[[:space:]|&;<>()`$]") | not)) ]
    | (length > 0)' -- "$SETTINGS" 2>/dev/null || true)"
  if [ -z "$have_tool" ]; then
    # Variant 4 — settings lag: no tool gate registered at all.
    printf 'WARN(drive-hooks drift): settings lag — the tool gate is not registered.\n' >&2
  elif [ "$have_mcp" != "$have_native" ]; then
    # Variant 4b — partial registration: the tool gate is wired on only ONE of the two
    # required matchers, so the settings-lag WARN (which only fires on zero entries) misses it.
    printf 'WARN(drive-hooks drift): partial tool-gate registration — drive-tool-gate.sh is wired on only one of the two required matchers (MCP-write / Agent|EnterWorktree); re-run bin/install-drive-hooks.sh to restore both.\n' >&2
  fi

  # Worktree gate (G1) drift — mirror the tool-gate presence + registration checks for the
  # AUTHORITATIVE WorktreeCreate gate this installer also manages. WorktreeCreate hooks carry
  # NO matcher, so the lone-path idiom scans .hooks.WorktreeCreate[]?.hooks[]?.command directly.
  # Variant 3w — sibling absent.
  if [ ! -f "$live_dir/drive-worktree-gate.sh" ]; then
    printf 'WARN(drive-hooks drift): live enforcement worktree lacks drive-worktree-gate.sh — advance that worktree, then re-run bin/install-drive-hooks.sh from INSIDE it.\n' >&2
  fi
  # Variant 4w — settings lag: the WorktreeCreate gate is not registered.
  local have_wt
  have_wt="$(jq -r '
    [ .hooks.WorktreeCreate[]?.hooks[]?.command // ""
      | select((endswith("/drive-worktree-gate.sh") or . == "drive-worktree-gate.sh")
               and (test("[[:space:]|&;<>()`$]") | not)) ]
    | first // ""' -- "$SETTINGS" 2>/dev/null || true)"
  if [ -z "$have_wt" ]; then
    printf 'WARN(drive-hooks drift): settings lag — the WorktreeCreate gate is not registered.\n' >&2
  fi
  return 0
}
drift_preflight

# --- Confirm gate -------------------------------------------------------------
# Prompt ONLY when run interactively by a human with no explicit target. Skip when:
#   - an explicit target path ($1) was given (scripted installs / the test suite),
#   - DRIVE_INSTALL_ASSUME_YES=1 is set,
#   - stdin/stdout is not a TTY (non-interactive / piped).
# On decline: exit 1 having changed nothing.
if [ -z "${1:-}" ] && [ "${DRIVE_INSTALL_ASSUME_YES:-}" != "1" ] && [ -t 0 ] && [ -t 1 ]; then
  printf 'Proceed and modify your settings? [y/N] ' >&2
  read -r _reply
  case "$_reply" in
    [yY] | [yY][eE][sS]) ;;
    *) echo "Aborted; nothing was changed." >&2; exit 1 ;;
  esac
fi

command -v jq >/dev/null 2>&1 || { echo "error: jq is required but not found in PATH" >&2; exit 1; }

# Create a valid minimal settings file if absent.
if [ ! -e "$SETTINGS" ]; then
  mkdir -p -- "$(dirname -- "$SETTINGS")"
  printf '{}\n' > "$SETTINGS"
  echo "Created new settings file: $SETTINGS"
fi

# Fail loudly on malformed JSON — do not clobber a file we cannot parse.
# `--` ends option parsing so a path beginning with `-` is treated as a filename.
if ! jq -e . -- "$SETTINGS" >/dev/null 2>&1; then
  echo "error: $SETTINGS is not valid JSON; refusing to modify it" >&2
  exit 1
fi

# Timestamped backup before any mutation (mirrors install-operating-rules.sh).
BACKUP="$SETTINGS.bak.$(date +%Y%m%d-%H%M%S)"
cp -- "$SETTINGS" "$BACKUP"
echo "Backed up existing settings -> $BACKUP"

# Inject both hooks idempotently, canonicalizing by script BASENAME: strip any prior
# entry for the managed script (at ANY path, incl. a stale pre-rename one) from the
# event, then append exactly one at the current path. This is idempotent AND migrates
# a moved/renamed path on re-run (no stale dead path, no duplicate).
# .hooks, .hooks.PreToolUse, .hooks.Stop are normalised to arrays so a partial /
# missing structure does not break the update.
TMP="$SETTINGS.tmp.$$"
jq \
  --arg merge "$MERGE_GATE" \
  --arg stop "$STOP_GUARD" \
  --arg tool "$TOOL_GATE" \
  --arg wtgate "$WT_GATE" \
  --arg mcpm "$TOOL_GATE_MCP_MATCHER" \
  --arg natm "$TOOL_GATE_NATIVE_MATCHER" \
  '
  # basename of a command path (everything after the last "/"; bare names unchanged).
  def bn($p): ($p | sub(".*/"; ""));
  # Is $cmd a LONE invocation of the managed script $base? True iff it is just a path
  # ending in "/<base>" (or the bare "<base>") with NO whitespace and NO shell
  # metacharacters. This recognises a stale-path copy of the managed gate (migrate it)
  # but deliberately does NOT match a wrapped / piped / substituted / env-prefixed /
  # arg-bearing command that merely ends in the same basename (a piped wrapper, an
  # "env FOO=1 .../gate.sh", or a stricter custom gate). Collapsing such a command into
  # the bare stock gate would silently WEAKEN enforcement. Match on script IDENTITY,
  # not just basename.
  # NOTE: keep this jq program free of apostrophes/backticks in comments -- it is in
  # shell single quotes, so a stray apostrophe would terminate it.
  # RESERVED-NAME CONTRACT: a LONE invocation of drive-merge-gate.sh / drive-stop-guard.sh /
  # drive-tool-gate.sh / drive-worktree-gate.sh is always treated as THE managed gate, wherever
  # it lives -- this is what lets a moved/renamed install migrate (the old entry is a lone
  # same-basename path at a different location, indistinguishable from any other). Do NOT name a
  # custom hook with these basenames; a re-install will canonicalize it to the stock gate. The
  # stock gate is always (re-)added, so enforcement is never removed -- only a same-named custom
  # override is not preserved.
  # $full is the EXACT current managed path; $base its basename. A command is managed iff
  # it EXACTLY equals $full (so a path CONTAINING A SPACE — common on macOS, e.g.
  # `/Users/My Name/...` — still canonicalizes idempotently), OR it is a lone same-basename
  # invocation with NO whitespace/shell metacharacters (the migrate-on-rename + stale-path
  # case). The metachar guard stays on the basename branch so a wrapped `env STRICT=1
  # .../gate.sh` (which contains a space) is NOT collapsed into the bare stock gate.
  def is_managed($cmd; $base; $full):
    ($cmd == $full)
    or ((($cmd | endswith("/" + $base)) or ($cmd == $base))
        and (($cmd | test("[[:space:]|&;<>()`$]")) | not));
  # Drop every hook that is a lone invocation of $base from each group, then drop
  # groups left empty. Keyed on the script identity so a moved/renamed repo
  # (e.g. claude-harness -> autodrive) MIGRATES the entry on re-run instead of leaving
  # the stale path behind and appending a duplicate. Non-managed hooks (other basenames,
  # e.g. mc-hook.py / drive-stop-hook.py, AND wrapped commands sharing the basename)
  # are untouched. (Migration of a renamed SPACED path is best-effort; exact re-run is not.)
  def strip_managed($arr; $base; $full):
    [ $arr[]?
      | .hooks = [ .hooks[]? | select(is_managed(.command // ""; $base; $full) | not) ]
      | select((.hooks | length) > 0) ];
  # ensure container shapes
  .hooks = (.hooks // {})
  | .hooks.PreToolUse = (.hooks.PreToolUse // [])
  | .hooks.Stop = (.hooks.Stop // [])
  | .hooks.WorktreeCreate = (.hooks.WorktreeCreate // [])
  # canonicalize the PreToolUse gates: strip any prior (incl. stale-path) merge-gate AND
  # tool-gate entries, then append the merge gate + BOTH tool-gate entries in a FIXED order
  # (deterministic for the tests). strip_managed is matcher-agnostic (keyed on the command
  # basename), so it strips BOTH tool-gate entries regardless of their matchers. Idempotent;
  # migrates a moved/renamed path on re-run. The tool gate is a BARE PATH, NO argv (is_managed
  # refuses arg-bearing commands — an arg-carrying registration would never canonicalize).
  | .hooks.PreToolUse =
      strip_managed(strip_managed(.hooks.PreToolUse; bn($merge); $merge); bn($tool); $tool)
      + [ { "matcher": "Bash", "hooks": [ { "type": "command", "command": $merge } ] } ]
      + [ { "matcher": $mcpm, "hooks": [ { "type": "command", "command": $tool } ] } ]
      + [ { "matcher": $natm, "hooks": [ { "type": "command", "command": $tool } ] } ]
  # canonicalize the Stop guard the same way.
  | .hooks.Stop = strip_managed(.hooks.Stop; bn($stop); $stop)
      + [ { "hooks": [ { "type": "command", "command": $stop } ] } ]
  # canonicalize the WorktreeCreate gate (matcher-less, like Stop). Keyed on the
  # drive-worktree-gate.sh basename, so it is idempotent/migrating INDEPENDENTLY of the other
  # entries and never strips the merge-gate / tool-gate / Stop entries.
  | .hooks.WorktreeCreate = strip_managed(.hooks.WorktreeCreate; bn($wtgate); $wtgate)
      + [ { "hooks": [ { "type": "command", "command": $wtgate } ] } ]
  ' -- "$SETTINGS" > "$TMP"

# Sanity: result must be valid JSON before we move it into place.
if ! jq -e . -- "$TMP" >/dev/null 2>&1; then
  rm -f -- "$TMP"
  echo "error: produced invalid JSON; left $SETTINGS untouched" >&2
  exit 1
fi
mv -- "$TMP" "$SETTINGS"

echo "Wired drive hooks into $SETTINGS:"
echo "  PreToolUse(Bash) -> $MERGE_GATE"
echo "  Stop             -> $STOP_GUARD"
echo "  PreToolUse(GitHub/GitLab-MCP writes; Agent/EnterWorktree) -> $TOOL_GATE (two entries)"
echo "  WorktreeCreate   -> $WT_GATE"
