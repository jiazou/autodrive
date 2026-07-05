#!/usr/bin/env bash
# drive-tool-gate.sh — PreToolUse hook for the NON-Bash tool surface: GitHub-MCP write
# tools and the native worktree tools (Agent isolation:"worktree" / EnterWorktree).
#
# The primary /drive gate (drive-merge-gate.sh) fires on Bash only, so two tool classes
# can land run work WITHOUT tripping any gate while a /drive run is active on the same
# repo:
#   - GitHub MCP writes (create_pull_request / push_files / …) reach GitHub without ever
#     issuing a Bash git/gh command — the merge/ship gate never sees them.
#   - Agent isolation:"worktree" / EnterWorktree create worktrees on a harness-named
#     branch (not slice/<runId>/<id>), so plan/phasedesign gating and the slice
#     review + impl-presence checks never fire (a `git merge <harness-branch>` is inert
#     to drive-merge-gate.sh — it keys on slice/|phaseInt/ tokens).
# This sibling hook deny-ROUTES those tools back to the canonical gated Bash paths while
# a run is active on the actor's repo, and passes everything else silently.
#
# Composition contract (mirrors drive-merge-gate.sh, D5/D-p2-4): DENY-ONLY. On a
# violation it emits a PreToolUse `deny` JSON + exit 0; on every clean / non-matching /
# unrelated-repo path it emits NOTHING and exits 0. It NEVER emits `allow`/`ask`, so it
# composes with other PreToolUse hooks under Claude Code's deny-beats-allow precedence.
#
# Fail mode (D-p2-5, uniform fail-CLOSED for IN-SCRIPT detected errors on a matched
# write-class tool): jq absent, unparseable stdin, or a matched tool whose owner/repo
# can't be extracted while a run is live → DENY. These write-class tools have NO
# ship-gate backstop once they land remotely, so the mid-build fail-OPEN concession does
# NOT apply. Third-party corrupt run dirs are the ONE exception: skip-with-warning, never
# fail-closed on someone else's dir contents. Hook-INVOCATION failure (nonzero exit,
# rc 126/127, dead path) is fail-OPEN by platform protocol — a documented residual.
#
# Standalone: sources NOTHING (drive-hook-lib.sh is pure ref→runId parsing, no active-run
# predicate to reuse). Reads only $HOME/.claude/harness-runs. bash 3.2-safe; set -u.
# Env knob: DRIVE_TOOL_GATE_LIVE_HOURS (default 24) — liveness window for active runs.
set -u

# --- static deny used when jq is ABSENT (no jq → can't JSON-escape a dynamic reason) ---
# Pre-built constant JSON: no dynamic content, so printf alone suffices.
STATIC_DENY_JSON='{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"drive-tool-gate: jq is required to evaluate this hook but was not found in PATH. Failing CLOSED for write-class safety (these tools have no ship-gate backstop). Install jq, or use the canonical gated Bash path (git/gh) instead."}}'

# emit_deny <reason> : emit a PreToolUse deny with the JSON-escaped reason, then exit 0.
# (exit 0 because the HOOK ran fine — the deny verdict is carried in the JSON body, not
# the exit code. Mirrors drive-merge-gate.sh:33-43.)
emit_deny() {
  local reason="$1"
  reason="${reason//\\/\\\\}"
  reason="${reason//\"/\\\"}"
  reason="${reason//$'\n'/\\n}"
  reason="${reason//$'\t'/\\t}"
  reason="${reason//$'\r'/\\r}"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$reason"
  exit 0
}

# --- control flow step 1: read stdin; jq absent → static deny -----------------------
INPUT="$(cat)"
if ! command -v jq >/dev/null 2>&1; then
  printf '%s\n' "$STATIC_DENY_JSON"
  exit 0
fi

# --- control flow step 2: ONE jq extracts all fields (newline-separated) ---------------
# Five fields, ONE per line (read back with `IFS= read` so EMPTY MIDDLE fields are
# preserved verbatim — a tab/`@tsv` split would collapse them, since tab is IFS-
# whitespace, and mis-shift every later field). Each field is tostring'd + has its own
# newlines/CRs squashed to spaces so a value can never leak an extra line. Robust against
# a non-object .tool_input; a genuine parse failure yields an empty tool_name (fail-closed).
FIELDS="$(printf '%s' "$INPUT" | jq -r '
  def f: (. // "") | tostring | gsub("[\r\n]"; " ");
  (if (.tool_input | type) == "object" then .tool_input else {} end) as $ti
  | (.tool_name | f), ($ti.isolation | f), ($ti.owner | f), ($ti.repo | f), (.cwd | f)
' 2>/dev/null || true)"

TOOL_NAME=""; ISOLATION=""; IN_OWNER=""; IN_REPO=""; PAYLOAD_CWD=""
{
  IFS= read -r TOOL_NAME
  IFS= read -r ISOLATION
  IFS= read -r IN_OWNER
  IFS= read -r IN_REPO
  IFS= read -r PAYLOAD_CWD
} <<EOF
$FIELDS
EOF

# Empty tool_name = unparseable stdin → fail-CLOSED (in-script error).
[ -n "$TOOL_NAME" ] || emit_deny "drive-tool-gate: could not parse the tool call from stdin (empty tool_name). Failing CLOSED for write-class safety. If this recurs the hook input contract has drifted — re-run bin/install-drive-hooks.sh."

# --- control flow step 3: class dispatch on tool_name ---------------------------------
# CLASS ∈ { worktree, mcp }. Plain Agent (no worktree isolation) and any non-write tool
# exit HERE, BEFORE any run scan (the hot-path contract). A matched mcp__ suffix absent
# from the hook's own table denies UNCONDITIONALLY (settings/hook drift, fail-closed).
CLASS=""
SUFFIX=""
case "$TOOL_NAME" in
  Agent)
    if [ "$ISOLATION" = worktree ]; then
      CLASS=worktree
    else
      exit 0                       # HOT PATH: plain Agent → silent, before any scan
    fi ;;
  EnterWorktree)
    CLASS=worktree ;;
  mcp__*)
    SUFFIX="${TOOL_NAME##*__}"     # suffix after the LAST __
    case "$SUFFIX" in
      create_or_update_file|delete_file|push_files|create_branch|create_pull_request|update_pull_request_branch|merge_pull_request|update_pull_request)
        CLASS=mcp ;;
      *)
        # Matched the write-tool gate but absent from the hook table → drift, fail-CLOSED.
        emit_deny "drive-tool-gate: the tool $TOOL_NAME matched the /drive write-tool gate but is absent from the hook's own tool table (settings/hook drift). Failing CLOSED for write-class safety. Use the canonical gated Bash path (git/gh), or re-run bin/install-drive-hooks.sh to resync the settings matcher with the hook table." ;;
    esac ;;
  *)
    exit 0 ;;                       # mis-registered non-write tool → silent (deny = pure DoS)
esac

# --- control flow step 4: active-run scan (Foundation C) ------------------------------
RUNS_ROOT="$HOME/.claude/harness-runs"

H="${DRIVE_TOOL_GATE_LIVE_HOURS:-24}"
case "$H" in ''|*[!0-9]*) H=24 ;; esac
[ "$H" -gt 0 ] 2>/dev/null || H=24
MINS=$((H * 60))

# Liveness-bounded candidate dirs: run dirs with a state.json OR event-log.jsonl touched
# within the window. macOS/BSD-safe (no -printf; dirname in a loop; ≤ tens of dirs).
CAND_DIRS="$(
  find "$RUNS_ROOT" -maxdepth 2 \( -name state.json -o -name event-log.jsonl \) -mmin "-$MINS" 2>/dev/null \
    | while IFS= read -r f; do dirname "$f"; done | sort -u
)"

# Validate each candidate: state.json a regular file that PARSES with stage != "done".
# Corrupt/unreadable state.json → skip WITH a stderr warning (fail-closed = own logic
# only, never third-party dir contents). Absent/non-regular state.json → silent skip.
ACTIVE_RUNS=""
while IFS= read -r D; do
  [ -n "$D" ] || continue
  sj="$D/state.json"
  [ -e "$sj" ] || continue           # no state.json → not an active run (silent)
  [ -f "$sj" ] || continue           # non-regular (symlink-to-fifo/device) → skip, out of threat model
  if ! stage="$(jq -r '.stage // ""' "$sj" 2>/dev/null)"; then
    printf 'drive-tool-gate: skipping unreadable/corrupt state.json in %s\n' "$D" >&2
    continue
  fi
  [ -n "$stage" ] || continue        # parsed but no stage → not routable-active (silent)
  [ "$stage" = "done" ] && continue  # explicitly done → not active
  ACTIVE_RUNS="$ACTIVE_RUNS$D
"
done <<EOF
$CAND_DIRS
EOF

# No active run → the insurance lies dormant → silent pass.
[ -n "$ACTIVE_RUNS" ] || exit 0

# --- repo-identity helpers (the PINNED canonical origin parse; shared common-dir) -----
_ORIGIN_HOST=""; _ORIGIN_OWNER=""; _ORIGIN_REPO=""

# parse_origin <dir> : parse `git -C <dir> remote get-url origin` into the canonical
# key parts, lowercased. rc 0 + sets _ORIGIN_HOST/_ORIGIN_OWNER/_ORIGIN_REPO on success;
# rc 1 (globals blanked) if the dir has no origin / is not a repo / the URL is unusable.
# Handles BOTH transport forms (AC-7 requires scp AND URL to key identically):
#   scp  : [user@]host:owner/repo[.git]            (the ':' separates host from PATH)
#   URL  : scheme://[user@]host[:port]/owner/repo[.git][/]
# scp: strip [user@] (up to LAST @), then host = up-to-FIRST ':', path = after it.
# URL: authority = up-to-first '/', strip userinfo (up to LAST @), strip trailing :port.
parse_origin() {
  local d="$1" url rest authority hostport host path owner repo
  _ORIGIN_HOST=""; _ORIGIN_OWNER=""; _ORIGIN_REPO=""
  url="$(git -C "$d" remote get-url origin 2>/dev/null)" || return 1
  url="${url#"${url%%[![:space:]]*}"}"          # trim leading whitespace
  url="${url%"${url##*[![:space:]]}"}"          # trim trailing whitespace
  [ -n "$url" ] || return 1
  case "$url" in
    *://*)
      rest="${url#*://}"                 # [user@]host[:port]/owner/repo[.git][/]
      authority="${rest%%/*}"            # [user@]host[:port]
      path="${rest#*/}"                  # owner/repo[.git][/]
      hostport="${authority##*@}"        # strip [user@] userinfo (may carry :password)
      host="${hostport%:*}"              # strip a trailing :port (no colon → unchanged)
      case "$host" in *:*) host="${host%:*}" ;; esac
      ;;
    *:*)
      hostport="${url##*@}"              # strip [user@]; host:owner/repo[.git]
      host="${hostport%%:*}"             # host = up to the FIRST ':' (scp path separator)
      path="${hostport#*:}"              # owner/repo[.git]
      ;;
    *)
      return 1 ;;
  esac
  path="${path%/}"                       # strip ONE trailing slash
  path="${path%.git}"                    # strip a trailing .git
  owner="${path%%/*}"                    # first segment
  repo="${path##*/}"                     # last segment
  [ -n "$host" ] && [ -n "$owner" ] && [ -n "$repo" ] || return 1
  [ "$owner" != "$path" ] || return 1    # path had no '/' → not owner/repo → unusable
  _ORIGIN_HOST="$(printf '%s' "$host"  | tr '[:upper:]' '[:lower:]')"
  _ORIGIN_OWNER="$(printf '%s' "$owner" | tr '[:upper:]' '[:lower:]')"
  _ORIGIN_REPO="$(printf '%s' "$repo"  | tr '[:upper:]' '[:lower:]')"
  return 0
}

# common_dir_of <dir> : realpath of the git COMMON dir (stable across every linked
# worktree of the clone). Echoes the resolved absolute dir (rc 0) or rc 1. NOT
# realpath(<dir>/.git): a linked worktree's .git is a gitFILE pointer, not the common dir.
common_dir_of() {
  local d="$1" cd
  cd="$(git -C "$d" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || return 1
  [ -n "$cd" ] || return 1
  ( cd "$cd" 2>/dev/null && pwd -P ) || return 1
}

# noorigin_repo_name <commondir> : the run's no-origin repo name = basename of the common
# dir after stripping a trailing /.git (the owning CHECKOUT dir name), lowercased. Bare
# repos (common dir like `x.git`) degrade to basename(commondir). Echoes the name (may be
# empty for an empty arg).
noorigin_repo_name() {
  local cd="$1"
  case "$cd" in */.git) cd="${cd%/.git}" ;; esac
  printf '%s' "$(basename "$cd" 2>/dev/null)" | tr '[:upper:]' '[:lower:]'
}

# --- deny-reason builders (§A.3 per-tool table: problem + cause + exact retry path) ----
# Every reason names the active run and carries its row's verbatim retry path (AC-3).
mcp_deny_reason() {
  local suffix="$1" runId="$2"
  case "$suffix" in
    create_or_update_file)
      printf 'drive-tool-gate: run %s is active on this repo. The GitHub MCP tool create_or_update_file writes a file directly on the remote, bypassing the /drive gates (they fire on Bash git/gh commands only). Retry: edit + commit the file in the slice worktree, then land it via the gated `git merge slice/<runId>/<id>`; it reaches GitHub only through the gated `git push` at ship.' "$runId" ;;
    delete_file)
      printf 'drive-tool-gate: run %s is active on this repo. The GitHub MCP tool delete_file removes a file directly on the remote, bypassing the /drive gates (they fire on Bash git/gh commands only). Retry: `git rm` + commit in the slice worktree, then land it via the gated `git merge slice/<runId>/<id>`; it reaches GitHub only through the gated `git push` at ship.' "$runId" ;;
    push_files)
      printf 'drive-tool-gate: run %s is active on this repo. The GitHub MCP tool push_files pushes multiple files directly to the remote, bypassing the /drive ship gate. Retry: commit locally in the slice worktree, then `git push` from the ship worktree (gated: the finalize-review check runs on the pushed tip).' "$runId" ;;
    create_branch)
      printf 'drive-tool-gate: run %s is active on this repo. The GitHub MCP tool create_branch creates a branch directly on the remote, bypassing the /drive plan/design gates. Retry: `git worktree add $RUN_DIR/wt/<id> -b slice/<runId>/<id> <phaseBaseSha>` (gated) for a drive slice, or a plain local `git branch` for a non-drive ref.' "$runId" ;;
    create_pull_request)
      printf 'drive-tool-gate: run %s is active on this repo. The GitHub MCP tool create_pull_request opens the PR outside Bash, bypassing the /drive ship gate. Retry: `gh pr create` from the ship worktree (gated: it verifies the finalize review covers the shipped tip).' "$runId" ;;
    update_pull_request_branch)
      printf 'drive-tool-gate: run %s is active on this repo. The GitHub MCP tool update_pull_request_branch mutates the remote PR branch, bypassing the /drive ship gate. Retry: `git merge origin/<base>` in the ship worktree, then the gated `git push`.' "$runId" ;;
    merge_pull_request)
      printf 'drive-tool-gate: run %s is active on this repo. In the /drive flow the PR merge is human-owned at Gate B; the GitHub MCP tool merge_pull_request is not the sanctioned route to merge the PR during an active run — merge after Gate B approval. (This denies the MCP omission path; the Bash `gh pr merge` twin stays ungated — a deliberately-deferred asymmetry, not a global prohibition.)' "$runId" ;;
    update_pull_request)
      printf 'drive-tool-gate: run %s is active on this repo. PR title/body/state/base edits are human-owned at Gate B; the GitHub MCP tool update_pull_request is not the sanctioned route to edit the PR during an active run — edit after Gate B approval. (This denies the MCP omission path; the Bash `gh pr edit` twin stays ungated — a deliberately-deferred asymmetry, not a global prohibition.)' "$runId" ;;
  esac
}

worktree_deny_reason() {
  local tool="$1" runId="$2"
  printf 'drive-tool-gate: run %s is active on this repo. The native worktree tool %s creates a worktree on a harness-named branch, so the plan/phasedesign gates (`git worktree add … -b slice/…`) and the slice merge/test gates (keyed on slice/<runId>/<id> refs) never fire. Retry: `git worktree add $RUN_DIR/wt/<id> -b slice/<runId>/<id> <phaseBaseSha>` (gated), then dispatch the agent into that path WITHOUT worktree isolation (or `cd` into it).' "$runId" "$tool"
}

# --- control flow step 5: repo scoping over the active runs --------------------------
if [ "$CLASS" = mcp ]; then
  IN_OWNER_LC="$(printf '%s' "$IN_OWNER" | tr '[:upper:]' '[:lower:]')"
  IN_REPO_LC="$(printf '%s' "$IN_REPO"  | tr '[:upper:]' '[:lower:]')"
  # Unextractable owner/repo while ≥1 run is live → fail-CLOSED over-deny (names a run).
  if [ -z "$IN_OWNER_LC" ] || [ -z "$IN_REPO_LC" ]; then
    _first="$(printf '%s' "$ACTIVE_RUNS" | while IFS= read -r d; do [ -n "$d" ] && { basename "$d"; break; }; done)"
    emit_deny "drive-tool-gate: run $_first is active on this repo, and this GitHub MCP write ($TOOL_NAME) carries no extractable owner/repo to scope it. Failing CLOSED for write-class safety (over-deny). Retry via the canonical gated Bash path (git/gh) from the run's worktree."
  fi
  while IFS= read -r D; do
    [ -n "$D" ] || continue
    runId="$(basename "$D")"
    repoRoot="$(jq -r '.repoRoot // ""' "$D/state.json" 2>/dev/null || true)"
    if parse_origin "$repoRoot"; then
      if [ "$IN_OWNER_LC" = "$_ORIGIN_OWNER" ] && [ "$IN_REPO_LC" = "$_ORIGIN_REPO" ]; then
        emit_deny "$(mcp_deny_reason "$SUFFIX" "$runId")"
      fi
    else
      # No origin → common-dir repo-name fallback (repo-only, NOT basename(repoRoot)).
      cd_run="$(common_dir_of "$repoRoot" 2>/dev/null || true)"
      if [ -n "$cd_run" ]; then
        noorigin="$(noorigin_repo_name "$cd_run")"
        if [ -n "$noorigin" ] && [ "$IN_REPO_LC" = "$noorigin" ]; then
          emit_deny "$(mcp_deny_reason "$SUFFIX" "$runId")"
        fi
      fi
    fi
  done <<EOF
$ACTIVE_RUNS
EOF
  exit 0
fi

# CLASS = worktree (Agent isolation:"worktree" / EnterWorktree). Scope by the payload
# cwd's repo identity: origin identity UNION common-dir fast-match against each run.
CWD_ORIGIN_KEY=""
if parse_origin "$PAYLOAD_CWD"; then
  CWD_ORIGIN_KEY="$_ORIGIN_HOST/$_ORIGIN_OWNER/$_ORIGIN_REPO"
fi
CWD_COMMONDIR="$(common_dir_of "$PAYLOAD_CWD" 2>/dev/null || true)"
# cwd not a git repo → no identity → no match possible → falls through to silent exit.

while IFS= read -r D; do
  [ -n "$D" ] || continue
  runId="$(basename "$D")"
  repoRoot="$(jq -r '.repoRoot // ""' "$D/state.json" 2>/dev/null || true)"
  RUN_ORIGIN_KEY=""
  if parse_origin "$repoRoot"; then
    RUN_ORIGIN_KEY="$_ORIGIN_HOST/$_ORIGIN_OWNER/$_ORIGIN_REPO"
  fi
  RUN_COMMONDIR="$(common_dir_of "$repoRoot" 2>/dev/null || true)"
  matched=0
  if [ -n "$CWD_ORIGIN_KEY" ] && [ -n "$RUN_ORIGIN_KEY" ] && [ "$CWD_ORIGIN_KEY" = "$RUN_ORIGIN_KEY" ]; then
    matched=1
  fi
  if [ -n "$CWD_COMMONDIR" ] && [ -n "$RUN_COMMONDIR" ] && [ "$CWD_COMMONDIR" = "$RUN_COMMONDIR" ]; then
    matched=1
  fi
  if [ "$matched" = 1 ]; then
    emit_deny "$(worktree_deny_reason "$TOOL_NAME" "$runId")"
  fi
done <<EOF
$ACTIVE_RUNS
EOF

exit 0
