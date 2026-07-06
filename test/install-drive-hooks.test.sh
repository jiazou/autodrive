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
TOOL_GATE="$REPO_DIR/bin/drive-tool-gate.sh"
WT_GATE="$REPO_DIR/bin/drive-worktree-gate.sh"
# Exact matcher strings the installer writes for the two tool-gate entries (AC-9). G2 adds the
# five GitLab merge_request-write suffixes to the MCP matcher (the pin reding is the PROOF G2
# bit — memory gate-tightening-reds-the-allow-tests).
MCP_MATCHER='^mcp__.+__(update_pull_request_branch|create_or_update_file|create_merge_request|accept_merge_request|rebase_merge_request|merge_merge_request|update_merge_request|create_pull_request|merge_pull_request|update_pull_request|create_branch|delete_file|push_files)$'
NATIVE_MATCHER='^(Agent|EnterWorktree)$'

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

# Canonicalize via cd&&pwd so a trailing-slash $TMPDIR (macOS default, e.g. /var/.../T/)
# cannot leave a double slash in $WORK — the installer normalizes its own paths with
# `cd && pwd`, so the exact-path AC-9 assertion must compare against the same canonical form.
WORK="$(cd "$(mktemp -d "${TMPDIR:-/tmp}/install-drive-hooks.XXXXXX")" && pwd)"
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

# existing PreToolUse hooks preserved (3 originals + merge gate + 2 tool-gate entries = 6)
pre_total=$(jq '.hooks.PreToolUse | length' "$SETTINGS")
check "existing PreToolUse hooks preserved (3 + merge + 2 tool = 6)" "$pre_total" "6"

for h in /existing/hook-one.sh /existing/hook-two.sh /existing/hook-three.sh; do
  found=$(jq --arg p "$h" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$SETTINGS")
  check "existing PreToolUse hook preserved: $h" "$found" "1"
done

# --- AC-9: both tool-gate entries present with the exact matcher strings ---
tool_total=$(jq --arg p "$TOOL_GATE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$SETTINGS")
check "tool gate injected TWICE (mcp + native entries)" "$tool_total" "2"
mcp_present=$(jq --arg p "$TOOL_GATE" --arg m "$MCP_MATCHER" '[.hooks.PreToolUse[] | select(.matcher==$m and (.hooks[]?.command==$p))] | length' "$SETTINGS")
check "MCP-write matcher entry present with exact string" "$mcp_present" "1"
native_present=$(jq --arg p "$TOOL_GATE" --arg m "$NATIVE_MATCHER" '[.hooks.PreToolUse[] | select(.matcher==$m and (.hooks[]?.command==$p))] | length' "$SETTINGS")
check "native (Agent|EnterWorktree) matcher entry present with exact string" "$native_present" "1"

# --- AC-9: WorktreeCreate gate wired (matcher-less), preserves shipped entries ---
wt_total=$(jq --arg p "$WT_GATE" '[.hooks.WorktreeCreate[]?.hooks[]? | select((.command//"")==$p)] | length' "$SETTINGS")
check "WorktreeCreate gate injected (1 entry)" "$wt_total" "1"
wt_len=$(jq '.hooks.WorktreeCreate | length' "$SETTINGS")
check "WorktreeCreate has exactly one managed entry" "$wt_len" "1"
# matcher-less: the entry carries NO .matcher key (like Stop)
wt_matcherless=$(jq '[.hooks.WorktreeCreate[] | select(has("matcher")|not)] | length' "$SETTINGS")
check "WorktreeCreate entry is matcher-less" "$wt_matcherless" "1"
# the shipped PreToolUse (merge + 2 tool) and Stop entries all survive alongside WorktreeCreate
survived_merge=$(jq --arg p "$MERGE_GATE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$SETTINGS")
check "AC-9 merge gate survives WorktreeCreate wiring" "$survived_merge" "1"
survived_tool=$(jq --arg p "$TOOL_GATE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$SETTINGS")
check "AC-9 both tool-gate entries survive WorktreeCreate wiring" "$survived_tool" "2"

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

tool_count2=$(jq --arg p "$TOOL_GATE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$SETTINGS")
check "second run keeps EXACTLY two tool-gate entries (no duplicate)" "$tool_count2" "2"

wt_count2=$(jq --arg p "$WT_GATE" '[.hooks.WorktreeCreate[]?.hooks[]? | select((.command//"")==$p)] | length' "$SETTINGS")
check "second run adds NO duplicate WorktreeCreate gate" "$wt_count2" "1"
wt_len2=$(jq '.hooks.WorktreeCreate | length' "$SETTINGS")
check "WorktreeCreate length stable after re-run (1)" "$wt_len2" "1"

pre_total2=$(jq '.hooks.PreToolUse | length' "$SETTINGS")
check "PreToolUse count stable after re-run (6)" "$pre_total2" "6"

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
OLD_TOOL="/Users/someone/workspace/claude-harness/bin/drive-tool-gate.sh"
OLD_WT="/Users/someone/workspace/claude-harness/bin/drive-worktree-gate.sh"
cat > "$MIG" <<JSON
{
  "model": "opus",
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [ { "type": "command", "command": "/existing/keep.sh" } ] },
      { "matcher": "Bash", "hooks": [ { "type": "command", "command": "$OLD_MERGE" } ] },
      { "matcher": "$MCP_MATCHER", "hooks": [ { "type": "command", "command": "$OLD_TOOL" } ] },
      { "matcher": "$NATIVE_MATCHER", "hooks": [ { "type": "command", "command": "$OLD_TOOL" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "$OLD_STOP" } ] }
    ],
    "WorktreeCreate": [
      { "hooks": [ { "type": "command", "command": "$OLD_WT" } ] }
    ]
  }
}
JSON
bash "$INSTALLER" "$MIG" >/dev/null 2>&1
check "installer exits 0 migrating stale paths" "$?" "0"
# WorktreeCreate stale path migrated to current path (count 1), stale path gone
mig_wt_new=$(jq --arg p "$WT_GATE" '[.hooks.WorktreeCreate[]?.hooks[]? | select((.command//"")==$p)] | length' "$MIG")
check "WorktreeCreate gate migrated to current path (count 1)" "$mig_wt_new" "1"
mig_wt_old=$(jq --arg p "$OLD_WT" '[.hooks.WorktreeCreate[]?.hooks[]? | select((.command//"")==$p)] | length' "$MIG")
check "stale WorktreeCreate path removed" "$mig_wt_old" "0"
mig_wt_len=$(jq '.hooks.WorktreeCreate | length' "$MIG")
check "WorktreeCreate has exactly one entry after migration (no dup)" "$mig_wt_len" "1"
# new (current) paths present exactly once
mig_merge_new=$(jq --arg p "$MERGE_GATE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$MIG")
check "merge gate migrated to current path (count 1)" "$mig_merge_new" "1"
mig_stop_new=$(jq --arg p "$STOP_GUARD" '[.hooks.Stop[].hooks[]? | select((.command//"")==$p)] | length' "$MIG")
check "stop guard migrated to current path (count 1)" "$mig_stop_new" "1"
# tool gate migrated to current path (both stale entries → the two current entries)
mig_tool_new=$(jq --arg p "$TOOL_GATE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$MIG")
check "tool gate migrated to current path (count 2)" "$mig_tool_new" "2"
mig_tool_old=$(jq --arg p "$OLD_TOOL" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$MIG")
check "stale tool-gate path removed" "$mig_tool_old" "0"
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
ENV_TOOL="env STRICT=1 /opt/custom/bin/drive-tool-gate.sh"
cat > "$WRAP" <<JSON
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [ { "type": "command", "command": "$PIPED_MERGE" } ] },
      { "matcher": "Bash", "hooks": [ { "type": "command", "command": "$ENV_MERGE" } ] },
      { "matcher": "$MCP_MATCHER", "hooks": [ { "type": "command", "command": "$ENV_TOOL" } ] }
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
env_tool_kept=$(jq --arg p "$ENV_TOOL" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$WRAP")
check "env-prefixed tool-gate command preserved (not collapsed)" "$env_tool_kept" "1"
subst_kept=$(jq --arg p "$SUBST_STOP" '[.hooks.Stop[].hooks[]? | select((.command//"")==$p)] | length' "$WRAP")
check "command-substitution stop-guard preserved (not collapsed)" "$subst_kept" "1"
# AND the two stock tool-gate entries are added alongside the wrapped one (enforcement present)
wrap_canon_tool=$(jq --arg p "$TOOL_GATE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$WRAP")
check "stock tool gate (2 entries) added alongside wrapped one" "$wrap_canon_tool" "2"
# AND the canonical stock gate/guard is still added alongside (enforcement present)
wrap_canon_merge=$(jq --arg p "$MERGE_GATE" '[.hooks.PreToolUse[].hooks[]? | select((.command//"")==$p)] | length' "$WRAP")
check "stock merge gate still added alongside wrapped ones" "$wrap_canon_merge" "1"
wrap_canon_stop=$(jq --arg p "$STOP_GUARD" '[.hooks.Stop[].hooks[]? | select((.command//"")==$p)] | length' "$WRAP")
check "stock stop guard still added alongside substitution one" "$wrap_canon_stop" "1"

# --- Idempotency for a repo path CONTAINING A SPACE (finding #4) -----------------
# The managed-hook metachar guard treated ANY command with whitespace as NOT managed, so a
# legitimate spaced install path (`/Users/My Name/...`, common on macOS) was never stripped
# on re-run → each run APPENDED another gate. is_managed now also matches the EXACT current
# path, so an exact re-run is idempotent regardless of spaces. Run the installer FROM a
# spaced directory so its computed MERGE_GATE/STOP_GUARD paths contain a space.
SPACED_ROOT="$WORK/sp ace root/bin"
mkdir -p "$SPACED_ROOT"
cp "$REPO_DIR/bin/install-drive-hooks.sh" "$REPO_DIR/bin/drive-merge-gate.sh" \
   "$REPO_DIR/bin/drive-stop-guard.sh" "$REPO_DIR/bin/drive-tool-gate.sh" \
   "$REPO_DIR/bin/drive-worktree-gate.sh" "$SPACED_ROOT/" 2>/dev/null
SPACED_WT_GATE="$SPACED_ROOT/drive-worktree-gate.sh"
SPACED_SETTINGS="$WORK/spaced-settings.json"
bash "$SPACED_ROOT/install-drive-hooks.sh" "$SPACED_SETTINGS" >/dev/null 2>&1
sp_merge1=$(jq '[.hooks.PreToolUse[].hooks[]? | select((.command//"")|test("drive-merge-gate.sh$"))] | length' "$SPACED_SETTINGS")
sp_stop1=$(jq '[.hooks.Stop[].hooks[]? | select((.command//"")|test("drive-stop-guard.sh$"))] | length' "$SPACED_SETTINGS")
sp_tool1=$(jq '[.hooks.PreToolUse[].hooks[]? | select((.command//"")|test("drive-tool-gate.sh$"))] | length' "$SPACED_SETTINGS")
sp_wt1=$(jq '[.hooks.WorktreeCreate[]?.hooks[]? | select((.command//"")|test("drive-worktree-gate.sh$"))] | length' "$SPACED_SETTINGS")
sp_wt_len1=$(jq '.hooks.WorktreeCreate | length' "$SPACED_SETTINGS")
sp_wt_ml1=$(jq '[.hooks.WorktreeCreate[] | select(has("matcher")|not)] | length' "$SPACED_SETTINGS")
sp_wt_path1=$(jq --arg p "$SPACED_WT_GATE" '[.hooks.WorktreeCreate[]?.hooks[]? | select((.command//"")==$p)] | length' "$SPACED_SETTINGS")
check "spaced-path install: one merge gate after run 1" "$sp_merge1" "1"
check "spaced-path install: one stop guard after run 1" "$sp_stop1" "1"
check "spaced-path install: two tool-gate entries after run 1" "$sp_tool1" "2"
check "spaced-path install: one WorktreeCreate gate after run 1" "$sp_wt1" "1"
check "spaced-path install: WorktreeCreate has exactly one entry after run 1" "$sp_wt_len1" "1"
check "spaced-path install: WorktreeCreate entry is matcher-less" "$sp_wt_ml1" "1"
check "spaced-path install: WorktreeCreate points at the spaced-path gate (correct path)" "$sp_wt_path1" "1"
bash "$SPACED_ROOT/install-drive-hooks.sh" "$SPACED_SETTINGS" >/dev/null 2>&1
sp_merge2=$(jq '[.hooks.PreToolUse[].hooks[]? | select((.command//"")|test("drive-merge-gate.sh$"))] | length' "$SPACED_SETTINGS")
sp_stop2=$(jq '[.hooks.Stop[].hooks[]? | select((.command//"")|test("drive-stop-guard.sh$"))] | length' "$SPACED_SETTINGS")
sp_tool2=$(jq '[.hooks.PreToolUse[].hooks[]? | select((.command//"")|test("drive-tool-gate.sh$"))] | length' "$SPACED_SETTINGS")
sp_wt2=$(jq '[.hooks.WorktreeCreate[]?.hooks[]? | select((.command//"")|test("drive-worktree-gate.sh$"))] | length' "$SPACED_SETTINGS")
sp_wt_len2=$(jq '.hooks.WorktreeCreate | length' "$SPACED_SETTINGS")
check "spaced-path install is IDEMPOTENT: still one merge gate after run 2 (no duplicate)" "$sp_merge2" "1"
check "spaced-path install is IDEMPOTENT: still one stop guard after run 2 (no duplicate)" "$sp_stop2" "1"
check "spaced-path install is IDEMPOTENT: still two tool-gate entries after run 2 (no duplicate)" "$sp_tool2" "2"
check "spaced-path install is IDEMPOTENT: still one WorktreeCreate gate after run 2 (whitespace strip_managed regression guard)" "$sp_wt2" "1"
check "spaced-path install is IDEMPOTENT: WorktreeCreate still exactly one entry after run 2" "$sp_wt_len2" "1"

# --- AC-11: READ-ONLY deployment-drift preflight (WARN-only; never blocks) -------
has_warn() { grep -qF "$2" "$1" && echo yes || echo no; }
WARN_TAG="WARN(drive-hooks drift):"

# Variant 2 + 3: settings point the live gates at a FAKE dir that lacks the sibling hook
# and has no tool-gate entry → migrate-hazard WARN + missing-sibling WARN; the whole run
# still makes EXACTLY ONE backup (the preflight is read-only, churns no backup); exit 0.
FAKE_LIVE="/no/such/live/enforcement/bin"
DRIFT23="$WORK/drift23.json"
cat > "$DRIFT23" <<JSON
{ "hooks": { "PreToolUse": [
  { "matcher": "Bash", "hooks": [ { "type": "command", "command": "$FAKE_LIVE/drive-merge-gate.sh" } ] }
] } }
JSON
D23_ERR="$WORK/drift23.err"
bash "$INSTALLER" "$DRIFT23" 2>"$D23_ERR" >/dev/null; d23_rc=$?
check "drift variant 2+3: installer still exits 0 (warn-only)" "$d23_rc" "0"
check "drift variant 2 (migrate hazard) WARN fires" "$(has_warn "$D23_ERR" "live gates run from $FAKE_LIVE")" "yes"
check "drift variant 3 (missing sibling) WARN fires" "$(has_warn "$D23_ERR" "live enforcement worktree lacks drive-tool-gate.sh")" "yes"
d23_bak=$(ls "$DRIFT23".bak.* 2>/dev/null | wc -l | tr -d ' ')
check "drift preflight churns NO extra backup (exactly one for the whole run)" "$d23_bak" "1"

# Fresh (entry-less) settings → NO drift output at all.
FRESH_DRIFT="$WORK/fresh-drift.json"
printf '{}\n' > "$FRESH_DRIFT"
FD_ERR="$WORK/fresh-drift.err"
bash "$INSTALLER" "$FRESH_DRIFT" 2>"$FD_ERR" >/dev/null
check "fresh (entry-less) settings → no drift WARN" "$(has_warn "$FD_ERR" "$WARN_TAG")" "no"

# Variant 4 (settings-lag): live dir IS this checkout's bin (sibling present) but no
# tool-gate entry is registered yet → settings-lag WARN, and NO migrate/missing-sibling WARN.
DRIFT4="$WORK/drift4.json"
cat > "$DRIFT4" <<JSON
{ "hooks": { "PreToolUse": [
  { "matcher": "Bash", "hooks": [ { "type": "command", "command": "$MERGE_GATE" } ] }
] } }
JSON
D4_ERR="$WORK/drift4.err"
bash "$INSTALLER" "$DRIFT4" 2>"$D4_ERR" >/dev/null; d4_rc=$?
check "drift variant 4: installer exits 0 (warn-only)" "$d4_rc" "0"
check "drift variant 4 (settings-lag) WARN fires" "$(has_warn "$D4_ERR" "settings lag — the tool gate is not registered")" "yes"
check "drift variant 4: NO migrate-hazard WARN" "$(has_warn "$D4_ERR" "live gates run from")" "no"
check "drift variant 4: NO missing-sibling WARN" "$(has_warn "$D4_ERR" "lacks drive-tool-gate.sh")" "no"

# Variant 4b (partial registration): live dir IS this checkout's bin (sibling present) and
# the tool gate is wired on ONLY ONE of the two required matchers (MCP present, native
# absent) → partial-registration WARN, and NOT the zero-entry settings-lag WARN.
DRIFT4B="$WORK/drift4b.json"
cat > "$DRIFT4B" <<JSON
{ "hooks": { "PreToolUse": [
  { "matcher": "Bash", "hooks": [ { "type": "command", "command": "$MERGE_GATE" } ] },
  { "matcher": "$MCP_MATCHER", "hooks": [ { "type": "command", "command": "$TOOL_GATE" } ] }
] } }
JSON
D4B_ERR="$WORK/drift4b.err"
bash "$INSTALLER" "$DRIFT4B" 2>"$D4B_ERR" >/dev/null; d4b_rc=$?
check "drift variant 4b: installer exits 0 (warn-only)" "$d4b_rc" "0"
check "drift variant 4b (partial registration) WARN fires" "$(has_warn "$D4B_ERR" "partial tool-gate registration")" "yes"
check "drift variant 4b: NO zero-entry settings-lag WARN (one matcher present)" "$(has_warn "$D4B_ERR" "settings lag — the tool gate is not registered")" "no"

# Variant 5 (cmp-differs): a live dir whose drive-merge-gate.sh differs byte-wise from this
# checkout's (worktree lags/diverged). Give it a sibling drive-tool-gate.sh so variant 3
# stays quiet and variant 5 is isolated → cmp-differs WARN; warn-only (exit 0).
FAKE5="$WORK/lagging-live-bin"; mkdir -p "$FAKE5"
printf '#!/usr/bin/env bash\n# a DIFFERENT (lagging) merge gate\nexit 0\n' > "$FAKE5/drive-merge-gate.sh"
cp "$REPO_DIR/bin/drive-tool-gate.sh" "$FAKE5/drive-tool-gate.sh"
DRIFT5="$WORK/drift5.json"
cat > "$DRIFT5" <<JSON
{ "hooks": { "PreToolUse": [
  { "matcher": "Bash", "hooks": [ { "type": "command", "command": "$FAKE5/drive-merge-gate.sh" } ] }
] } }
JSON
D5_ERR="$WORK/drift5.err"
bash "$INSTALLER" "$DRIFT5" 2>"$D5_ERR" >/dev/null; d5_rc=$?
check "drift variant 5: installer exits 0 (warn-only)" "$d5_rc" "0"
check "drift variant 5 (cmp-differs) WARN fires" "$(has_warn "$D5_ERR" "live drive-merge-gate.sh differs from this checkout")" "yes"
check "drift variant 5: NO missing-sibling WARN (sibling present)" "$(has_warn "$D5_ERR" "lacks drive-tool-gate.sh")" "no"

# Variant 6 (missing WorktreeCreate): live dir IS this checkout's bin (both siblings present),
# the tool gate is wired on BOTH matchers, but the authoritative WorktreeCreate gate is NOT
# registered → WorktreeCreate-not-registered WARN; warn-only (exit 0). Mirrors variant 4 for
# the G1 gate the installer also manages.
DRIFT6="$WORK/drift6.json"
cat > "$DRIFT6" <<JSON
{ "hooks": { "PreToolUse": [
  { "matcher": "Bash", "hooks": [ { "type": "command", "command": "$MERGE_GATE" } ] },
  { "matcher": "$MCP_MATCHER", "hooks": [ { "type": "command", "command": "$TOOL_GATE" } ] },
  { "matcher": "$NATIVE_MATCHER", "hooks": [ { "type": "command", "command": "$TOOL_GATE" } ] }
] } }
JSON
D6_ERR="$WORK/drift6.err"
bash "$INSTALLER" "$DRIFT6" 2>"$D6_ERR" >/dev/null; d6_rc=$?
check "drift variant 6: installer exits 0 (warn-only)" "$d6_rc" "0"
check "drift variant 6 (missing WorktreeCreate) WARN fires" "$(has_warn "$D6_ERR" "the WorktreeCreate gate is not registered")" "yes"

# --- AC-10: installer disclosure banner enumerates the four hooks / five entries + BOTH
#     new matcher classes (the GitHub-MCP write matcher + Agent/EnterWorktree). Slice-owned:
#     tests/installers/test_install_banner_confirm.py pins only generic tokens by design
#     (DIV-p2-1), so this is where a disclosure-text regression is caught. The banner prints
#     to STDERR before the (skipped, explicit-target) confirm gate. FAILs if the text regresses.
BANNER_SET="$WORK/banner-settings.json"
BANNER_ERR="$WORK/banner.err"
bash "$INSTALLER" "$BANNER_SET" 2>"$BANNER_ERR" >/dev/null
check "AC-10 banner enumerates 'four hooks'" "$(grep -qF 'four hooks' "$BANNER_ERR" && echo yes || echo no)" "yes"
check "AC-10 banner enumerates 'five settings entries'" "$(grep -qF 'five settings entries' "$BANNER_ERR" && echo yes || echo no)" "yes"
check "AC-10 banner names the GitHub/GitLab-MCP write matcher class" "$(grep -qF 'GitHub/GitLab-MCP writes' "$BANNER_ERR" && echo yes || echo no)" "yes"
check "AC-10 banner names the Agent/EnterWorktree matcher class" "$(grep -qF 'Agent/EnterWorktree' "$BANNER_ERR" && echo yes || echo no)" "yes"
check "AC-10 banner names the WorktreeCreate gate" "$(grep -qF 'WorktreeCreate' "$BANNER_ERR" && echo yes || echo no)" "yes"

# --- AC-11: drift_preflight makes ZERO byte changes to the target BEFORE the write path.
#     The timestamped backup is cp'd AFTER the preflight ran but BEFORE the jq mutation
#     (installer order: preflight -> confirm -> jq-valid -> BACKUP cp -> mutate -> mv), so the
#     .bak captures the exact post-preflight / pre-mutation state. If the (read-only) preflight
#     ever wrote, .bak would DIFFER from the pre-install snapshot. Seed a merge-gate entry at a
#     fake live dir so the preflight actually RUNS (drift variants 2+3), not the silent path.
PREF_SET="$WORK/preflight-identical.json"
cat > "$PREF_SET" <<JSON
{ "hooks": { "PreToolUse": [
  { "matcher": "Bash", "hooks": [ { "type": "command", "command": "/no/such/live/bin/drive-merge-gate.sh" } ] }
] } }
JSON
PREF_SNAP="$WORK/preflight-snapshot"
cp "$PREF_SET" "$PREF_SNAP"
bash "$INSTALLER" "$PREF_SET" >/dev/null 2>&1
PREF_BAK="$(ls "$PREF_SET".bak.* 2>/dev/null | head -1)"
check "AC-11 preflight pre-mutation backup exists" "$( [ -n "$PREF_BAK" ] && echo yes || echo no )" "yes"
check "AC-11 preflight made ZERO byte changes before the write path (bak == pre-install snapshot)" \
  "$( [ -n "$PREF_BAK" ] && cmp -s "$PREF_SNAP" "$PREF_BAK" && echo identical || echo differ )" "identical"
# non-vacuous guard: the mutation step DID change the file (else 'identical' above proves nothing)
check "AC-11 mutation step DID change the file (identical-check is non-vacuous)" \
  "$(cmp -s "$PREF_SNAP" "$PREF_SET" && echo unchanged || echo changed)" "changed"

# --- Summary --------------------------------------------------------------
echo "----------------------------------------"
echo "PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -eq 0 ] || exit 1
