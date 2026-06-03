#!/usr/bin/env bash
# Idempotently wire the two /drive enforcement hooks into a settings.json:
#   - PreToolUse(matcher "Bash") -> bin/drive-merge-gate.sh   (merge/ship/plan gate)
#   - Stop                        -> bin/drive-stop-guard.sh   (review backstop)
# Mirrors bin/install-operating-rules.sh: set -euo pipefail, REPO_DIR from BASH_SOURCE,
# a timestamped backup before mutating. Keyed on the script path so re-running is a
# no-op (no duplicate entries). All existing hooks are preserved. Fails loudly on
# malformed JSON. The repo never commits ~/.claude/settings.json.
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
  mkdir -p "$(dirname "$SETTINGS")"
  printf '{}\n' > "$SETTINGS"
  echo "Created new settings file: $SETTINGS"
fi

# Fail loudly on malformed JSON — do not clobber a file we cannot parse.
if ! jq -e . "$SETTINGS" >/dev/null 2>&1; then
  echo "error: $SETTINGS is not valid JSON; refusing to modify it" >&2
  exit 1
fi

# Timestamped backup before any mutation (mirrors install-operating-rules.sh).
BACKUP="$SETTINGS.bak.$(date +%Y%m%d-%H%M%S)"
cp "$SETTINGS" "$BACKUP"
echo "Backed up existing settings -> $BACKUP"

# Inject both hooks idempotently. Detection is keyed on the script path: an entry
# counts as already-present iff some hook under the event has command == the path.
# .hooks, .hooks.PreToolUse, .hooks.Stop are normalised to arrays so a partial /
# missing structure does not break the update.
TMP="$SETTINGS.tmp.$$"
jq \
  --arg merge "$MERGE_GATE" \
  --arg stop "$STOP_GUARD" \
  '
  # does any entry in the given event array already reference $path?
  def has_cmd($arr; $path):
    ([ $arr[]? | .hooks[]? | (.command // "") ] | any(. == $path));
  # ensure container shapes
  .hooks = (.hooks // {})
  | .hooks.PreToolUse = (.hooks.PreToolUse // [])
  | .hooks.Stop = (.hooks.Stop // [])
  # append PreToolUse Bash gate unless already present
  | (if has_cmd(.hooks.PreToolUse; $merge) then .
     else .hooks.PreToolUse += [ { "matcher": "Bash",
       "hooks": [ { "type": "command", "command": $merge } ] } ]
     end)
  # append Stop guard unless already present
  | (if has_cmd(.hooks.Stop; $stop) then .
     else .hooks.Stop += [ { "hooks": [ { "type": "command", "command": $stop } ] } ]
     end)
  ' "$SETTINGS" > "$TMP"

# Sanity: result must be valid JSON before we move it into place.
if ! jq -e . "$TMP" >/dev/null 2>&1; then
  rm -f "$TMP"
  echo "error: produced invalid JSON; left $SETTINGS untouched" >&2
  exit 1
fi
mv "$TMP" "$SETTINGS"

echo "Wired drive hooks into $SETTINGS:"
echo "  PreToolUse(Bash) -> $MERGE_GATE"
echo "  Stop             -> $STOP_GUARD"
