#!/usr/bin/env bash
# Idempotently wire the two /drive enforcement hooks into a settings.json:
#   - PreToolUse(matcher "Bash") -> bin/drive-merge-gate.sh   (merge/ship/plan gate)
#   - Stop                        -> bin/drive-stop-guard.sh   (review backstop)
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
  '
  # basename of a command path (everything after the last "/"; bare names unchanged).
  def bn($p): ($p | sub(".*/"; ""));
  # Drop every hook whose command BASENAME matches $base from each group, then drop
  # groups left empty. Keyed on the basename (not the full path) so a moved/renamed
  # repo (e.g. claude-harness -> autodrive) MIGRATES the entry on re-run instead of
  # leaving the stale path behind and appending a duplicate. Non-managed hooks (other
  # basenames, e.g. mc-hook.py / drive-stop-hook.py) are untouched.
  def strip_managed($arr; $base):
    [ $arr[]?
      | .hooks = [ .hooks[]? | select(bn(.command // "") != $base) ]
      | select((.hooks | length) > 0) ];
  # ensure container shapes
  .hooks = (.hooks // {})
  | .hooks.PreToolUse = (.hooks.PreToolUse // [])
  | .hooks.Stop = (.hooks.Stop // [])
  # canonicalize the PreToolUse merge gate: strip any prior (incl. stale-path)
  # entries, then append exactly one at the current path. Idempotent; migrates on rename.
  | .hooks.PreToolUse = strip_managed(.hooks.PreToolUse; bn($merge))
      + [ { "matcher": "Bash", "hooks": [ { "type": "command", "command": $merge } ] } ]
  # canonicalize the Stop guard the same way.
  | .hooks.Stop = strip_managed(.hooks.Stop; bn($stop))
      + [ { "hooks": [ { "type": "command", "command": $stop } ] } ]
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
