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

# --- Disclosure banner (ALWAYS printed) ---------------------------------------
# Tell the user exactly what this touches before anything is modified.
cat >&2 <<BANNER
============================================================
  /drive enforcement hooks — installer
============================================================
This modifies your Claude Code settings file:
  $SETTINGS

It adds two hooks (existing hooks are preserved; a timestamped
backup of the settings file is written first):

  • PreToolUse(Bash) -> $MERGE_GATE
      Fires on every Bash tool call. The gate itself decides whether
      to act — only /drive plan/merge/ship git operations are gated;
      everything else passes straight through.
  • Stop             -> $STOP_GUARD
      A review backstop that runs when a session stops.

The repo never commits ~/.claude/settings.json.
What these hooks do and their threat model: see SECURITY.md.
============================================================
BANNER

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
  # RESERVED-NAME CONTRACT: a LONE invocation of drive-merge-gate.sh / drive-stop-guard.sh
  # is always treated as THE managed gate, wherever it lives -- this is what lets a
  # moved/renamed install migrate (the old entry is a lone same-basename path at a
  # different location, indistinguishable from any other). Do NOT name a custom hook with
  # these basenames; a re-install will canonicalize it to the stock gate. The stock gate
  # is always (re-)added, so enforcement is never removed -- only a same-named custom
  # override is not preserved.
  def is_managed($cmd; $base):
    (($cmd | endswith("/" + $base)) or ($cmd == $base))
    and (($cmd | test("[[:space:]|&;<>()`$]")) | not);
  # Drop every hook that is a lone invocation of $base from each group, then drop
  # groups left empty. Keyed on the script identity so a moved/renamed repo
  # (e.g. claude-harness -> autodrive) MIGRATES the entry on re-run instead of leaving
  # the stale path behind and appending a duplicate. Non-managed hooks (other basenames,
  # e.g. mc-hook.py / drive-stop-hook.py, AND wrapped commands sharing the basename)
  # are untouched.
  def strip_managed($arr; $base):
    [ $arr[]?
      | .hooks = [ .hooks[]? | select(is_managed(.command // ""; $base) | not) ]
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
