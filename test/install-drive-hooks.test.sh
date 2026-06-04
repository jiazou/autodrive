#!/usr/bin/env bash
# AC11: install-drive-hooks.sh injects both hooks into a temp settings.json via jq,
# preserves existing hooks, re-run adds no duplicates, writes a backup.
# bash 3.2-safe; never touches the real ~/.claude/settings.json (uses mktemp).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALLER="$REPO_DIR/bin/install-drive-hooks.sh"

MERGE_GATE="$REPO_DIR/bin/drive-merge-gate.sh"
STOP_GUARD="$REPO_DIR/bin/drive-stop-guard.sh"

PASS=0
FAIL=0
check() { # check <desc> <actual> <expected>
  if [ "$2" = "$3" ]; then
    echo "PASS: $1"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $1 (expected '$3', got '$2')"
    FAIL=$((FAIL + 1))
  fi
}

WORK="$(mktemp -d "${TMPDIR:-/tmp}/install-drive-hooks.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

SETTINGS="$WORK/settings.json"

# Seed a settings.json with real-style existing hooks: a PreToolUse(Bash) array of
# three pre-existing hooks (copied structure from the real settings) plus Stop +
# Notification events, so we can prove existing hooks survive.
cat > "$SETTINGS" <<'JSON'
{
  "permissions": { "allow": ["Bash(git *)"] },
  "model": "opus",
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [ { "type": "command", "command": "/existing/hook-one.sh" } ] },
      { "matcher": "Bash", "hooks": [ { "type": "command", "command": "/existing/hook-two.sh" } ] },
      { "matcher": "Bash", "hooks": [ { "type": "command", "command": "/existing/hook-three.sh" } ] }
    ],
    "Notification": [
      { "hooks": [ { "type": "command", "command": "/existing/notify.sh" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "/existing/stop-one.sh" } ] }
    ]
  }
}
JSON

# --- Run 1 ----------------------------------------------------------------
bash "$INSTALLER" "$SETTINGS" >/dev/null 2>&1
check "installer exits 0 on first run" "$?" "0"

# valid JSON afterwards
jq -e . "$SETTINGS" >/dev/null 2>&1
check "settings is valid JSON after install" "$?" "0"

# merge gate injected into PreToolUse
merge_count=$(jq --arg p "$MERGE_GATE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$SETTINGS")
check "merge gate injected (PreToolUse)" "$merge_count" "1"

# stop guard injected into Stop
stop_count=$(jq --arg p "$STOP_GUARD" '[.hooks.Stop[].hooks[]? | select((.command//"")==$p)] | length' "$SETTINGS")
check "stop guard injected (Stop)" "$stop_count" "1"

# merge gate entry carries matcher "Bash"
matcher=$(jq -r --arg p "$MERGE_GATE" '.hooks.PreToolUse[] | select(.hooks[]?.command==$p) | .matcher' "$SETTINGS")
check "merge gate matcher is Bash" "$matcher" "Bash"

# existing PreToolUse hooks preserved (3 originals + 1 new = 4)
pre_total=$(jq '.hooks.PreToolUse | length' "$SETTINGS")
check "existing PreToolUse hooks preserved (3 + 1)" "$pre_total" "4"

for h in /existing/hook-one.sh /existing/hook-two.sh /existing/hook-three.sh; do
  found=$(jq --arg p "$h" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$SETTINGS")
  check "existing PreToolUse hook preserved: $h" "$found" "1"
done

# existing Stop hook preserved (1 original + 1 new = 2)
stop_total=$(jq '.hooks.Stop | length' "$SETTINGS")
check "existing Stop hooks preserved (1 + 1)" "$stop_total" "2"

# existing Notification untouched
notify=$(jq -r '.hooks.Notification[0].hooks[0].command' "$SETTINGS")
check "existing Notification hook preserved" "$notify" "/existing/notify.sh"

# unrelated keys preserved
model=$(jq -r '.model' "$SETTINGS")
check "unrelated key (model) preserved" "$model" "opus"

# a backup file was written
backups=$(ls "$SETTINGS".bak.* 2>/dev/null | wc -l | tr -d ' ')
check "backup file written on first run" "$backups" "1"

# --- Run 2 (idempotency) --------------------------------------------------
bash "$INSTALLER" "$SETTINGS" >/dev/null 2>&1
check "installer exits 0 on second run" "$?" "0"

merge_count2=$(jq --arg p "$MERGE_GATE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$SETTINGS")
check "second run adds NO duplicate merge gate" "$merge_count2" "1"

stop_count2=$(jq --arg p "$STOP_GUARD" '[.hooks.Stop[].hooks[]? | select((.command//"")==$p)] | length' "$SETTINGS")
check "second run adds NO duplicate stop guard" "$stop_count2" "1"

pre_total2=$(jq '.hooks.PreToolUse | length' "$SETTINGS")
check "PreToolUse count stable after re-run (4)" "$pre_total2" "4"

stop_total2=$(jq '.hooks.Stop | length' "$SETTINGS")
check "Stop count stable after re-run (2)" "$stop_total2" "2"

# --- Absent settings file gets created ------------------------------------
FRESH="$WORK/sub/dir/settings.json"
bash "$INSTALLER" "$FRESH" >/dev/null 2>&1
check "installer creates absent settings file (exit 0)" "$?" "0"
jq -e . "$FRESH" >/dev/null 2>&1
check "created settings file is valid JSON" "$?" "0"
fresh_merge=$(jq --arg p "$MERGE_GATE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$FRESH")
check "fresh file has merge gate" "$fresh_merge" "1"
fresh_stop=$(jq --arg p "$STOP_GUARD" '[.hooks.Stop[].hooks[]? | select((.command//"")==$p)] | length' "$FRESH")
check "fresh file has stop guard" "$fresh_stop" "1"

# --- Malformed JSON fails loudly, leaves file untouched -------------------
BAD="$WORK/bad.json"
printf '{ this is not json' > "$BAD"
bad_before=$(cat "$BAD")
bash "$INSTALLER" "$BAD" >/dev/null 2>&1
rc=$?
check "installer fails (nonzero) on malformed JSON" "$([ "$rc" -ne 0 ] && echo nonzero || echo zero)" "nonzero"
bad_after=$(cat "$BAD")
check "malformed settings left untouched" "$bad_after" "$bad_before"
no_bak=$(ls "$BAD".bak.* 2>/dev/null | wc -l | tr -d ' ')
check "no backup written for malformed file" "$no_bak" "0"

# --- Path beginning with '-' is treated as a filename, not an option ------
# A caller-supplied path starting with '-' must not be parsed as an option by
# jq/cp/mv. Run from inside $WORK so the relative path passed to the installer
# literally begins with '-' (an absolute path under mktemp never would).
DASH_NAME="-dash-settings.json"
DASH="$WORK/$DASH_NAME"
# Seed an existing valid file so cp (backup), jq (read/write), and mv (move into
# place) are all exercised against a path that begins with '-'.
printf '{ "model": "opus" }\n' > "$DASH"
( cd "$WORK" && bash "$INSTALLER" "$DASH_NAME" >/dev/null 2>&1 )
check "installer handles path beginning with '-' (exit 0)" "$?" "0"
jq -e . -- "$DASH" >/dev/null 2>&1
check "dash-prefixed settings is valid JSON" "$?" "0"
dash_merge=$(jq --arg p "$MERGE_GATE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' -- "$DASH")
check "dash-prefixed file has merge gate" "$dash_merge" "1"
dash_stop=$(jq --arg p "$STOP_GUARD" '[.hooks.Stop[].hooks[]? | select((.command//"")==$p)] | length' -- "$DASH")
check "dash-prefixed file has stop guard" "$dash_stop" "1"
dash_bak=$(ls "$DASH".bak.* 2>/dev/null | wc -l | tr -d ' ')
check "backup written for dash-prefixed file" "$dash_bak" "1"

# --- macOS/BSD utility guard: installer's `mkdir -p --` / `cp --` / `mv --` ----
# Codex's holistic review claimed these GNU-style `--` separators fail on macOS/BSD
# ("illegal option -- -"). They do NOT here — but the existing tests never exercised
# `mkdir -p --` (it only runs when the settings PARENT dir is absent). This guards it
# explicitly: install into a NONEXISTENT nested directory so the installer's
# `mkdir -p -- "$(dirname -- "$SETTINGS")"` runs on whatever real mkdir/cp/mv this
# platform ships. If `--` were rejected, the installer would exit nonzero and never
# create the file — so this fails loudly on a genuinely broken host.
NESTED="$WORK/no/such/dir/yet/settings.json"
bash "$INSTALLER" "$NESTED" >/dev/null 2>&1
check "installer creates absent parent dir via 'mkdir -p --' (exit 0)" "$?" "0"
check "nested parent dir was created" "$( [ -d "$WORK/no/such/dir/yet" ] && echo yes || echo no )" "yes"
jq -e . -- "$NESTED" >/dev/null 2>&1
check "nested settings is valid JSON (cp/mv/jq '--' all ran)" "$?" "0"
nested_gate=$(jq --arg p "$MERGE_GATE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' -- "$NESTED")
check "nested settings has merge gate" "$nested_gate" "1"

# --- Migrate-on-rename: stale-path entries are updated, not duplicated ----------
# The rename-safety contract: a settings.json whose drive hooks point at an OLD path
# (e.g. left over from before claude-harness -> autodrive) must, on re-run, MIGRATE to
# the current path — the stale dead path removed, no duplicate added. Keyed on the
# script BASENAME, so the installer recognises the moved entry as the same hook.
MIG="$WORK/migrate-settings.json"
OLD_MERGE="/Users/someone/workspace/claude-harness/bin/drive-merge-gate.sh"
OLD_STOP="/Users/someone/workspace/claude-harness/bin/drive-stop-guard.sh"
cat > "$MIG" <<JSON
{
  "model": "opus",
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [ { "type": "command", "command": "/existing/keep.sh" } ] },
      { "matcher": "Bash", "hooks": [ { "type": "command", "command": "$OLD_MERGE" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "$OLD_STOP" } ] }
    ]
  }
}
JSON
bash "$INSTALLER" "$MIG" >/dev/null 2>&1
check "installer exits 0 migrating stale paths" "$?" "0"
# new (current) paths present exactly once
mig_merge_new=$(jq --arg p "$MERGE_GATE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$MIG")
check "merge gate migrated to current path (count 1)" "$mig_merge_new" "1"
mig_stop_new=$(jq --arg p "$STOP_GUARD" '[.hooks.Stop[].hooks[]? | select((.command//"")==$p)] | length' "$MIG")
check "stop guard migrated to current path (count 1)" "$mig_stop_new" "1"
# stale paths GONE (the core of the contract)
mig_merge_old=$(jq --arg p "$OLD_MERGE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$MIG")
check "stale merge-gate path removed" "$mig_merge_old" "0"
mig_stop_old=$(jq --arg p "$OLD_STOP" '[.hooks.Stop[].hooks[]? | select((.command//"")==$p)] | length' "$MIG")
check "stale stop-guard path removed" "$mig_stop_old" "0"
# no duplicate merge gates anywhere; non-managed hook preserved
mig_merge_total=$(jq '[.hooks.PreToolUse[].hooks[]? | select((.command//"")|test("drive-merge-gate.sh$"))] | length' "$MIG")
check "exactly one merge gate after migration (no dup)" "$mig_merge_total" "1"
mig_keep=$(jq '[.hooks.PreToolUse[].hooks[]? | select((.command//"")=="/existing/keep.sh")] | length' "$MIG")
check "non-managed PreToolUse hook preserved across migration" "$mig_keep" "1"
mig_model=$(jq -r '.model' "$MIG")
check "unrelated key preserved across migration" "$mig_model" "opus"

# --- Wrapped / env-prefixed / substituted commands are NOT collapsed ----------
# A foreign hook whose command merely ENDS in the managed basename but is wrapped,
# piped, env-prefixed, arg-bearing, or command-substituted must be preserved — only a
# LONE path invocation (no whitespace, no shell metacharacters) is the managed gate.
# Collapsing such a command into the bare stock gate would silently weaken enforcement.
WRAP="$WORK/wrapped-settings.json"
PIPED_MERGE="/usr/local/bin/strict-wrapper.sh | /opt/custom/bin/drive-merge-gate.sh"
ENV_MERGE="env STRICT=1 /opt/custom/bin/drive-merge-gate.sh"
SUBST_STOP="\$(echo /x)/drive-stop-guard.sh"
cat > "$WRAP" <<JSON
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [ { "type": "command", "command": "$PIPED_MERGE" } ] },
      { "matcher": "Bash", "hooks": [ { "type": "command", "command": "$ENV_MERGE" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "$SUBST_STOP" } ] }
    ]
  }
}
JSON
bash "$INSTALLER" "$WRAP" >/dev/null 2>&1
check "installer exits 0 with wrapped same-basename commands" "$?" "0"
piped_kept=$(jq --arg p "$PIPED_MERGE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$WRAP")
check "piped merge-gate command preserved (not collapsed)" "$piped_kept" "1"
env_kept=$(jq --arg p "$ENV_MERGE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$WRAP")
check "env-prefixed merge-gate command preserved (not collapsed)" "$env_kept" "1"
subst_kept=$(jq --arg p "$SUBST_STOP" '[.hooks.Stop[].hooks[]? | select((.command//"")==$p)] | length' "$WRAP")
check "command-substitution stop-guard preserved (not collapsed)" "$subst_kept" "1"
# AND the canonical stock gate/guard is still added alongside (enforcement present)
wrap_canon_merge=$(jq --arg p "$MERGE_GATE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$WRAP")
check "stock merge gate still added alongside wrapped ones" "$wrap_canon_merge" "1"
wrap_canon_stop=$(jq --arg p "$STOP_GUARD" '[.hooks.Stop[].hooks[]? | select((.command//"")==$p)] | length' "$WRAP")
check "stock stop guard still added alongside substitution one" "$wrap_canon_stop" "1"

# --- Summary --------------------------------------------------------------
echo "----------------------------------------"
echo "PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -eq 0 ] || exit 1
