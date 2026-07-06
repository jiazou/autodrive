#!/usr/bin/env bash
# drive-tool-gate.sh — PreToolUse hook for the NON-Bash tool surface: GitHub/GitLab-MCP write
# tools and the native worktree tools (Agent isolation:"worktree" / EnterWorktree).
#
# The primary /drive gate (drive-merge-gate.sh) fires on Bash only, so two tool classes
# can land run work WITHOUT tripping any gate while a /drive run is active on the same
# repo:
#   - GitHub/GitLab MCP writes (create_pull_request / push_files / create_merge_request / …)
#     reach the remote without ever issuing a Bash git/gh command — the merge/ship gate never
#     sees them.
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
# Sources drive-hook-lib.sh for the shared `drive_scan_active_runs` predicate (the
# WorktreeCreate gate drive-worktree-gate.sh reuses the SAME predicate — DRY). Reads only
# $HOME/.claude/harness-runs. bash 3.2-safe; set -u.
# Env knob: DRIVE_TOOL_GATE_LIVE_HOURS (default 24) — liveness window for active runs.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/drive-hook-lib.sh"

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

# trim_ws <string> : echo the string with OUTER (leading+trailing) whitespace stripped.
# A whitespace-padded but semantically-identical repo id (owner:"owner ", cwd:"<path> ")
# must still MATCH the active run → deny, not slip past on the padding (a fail-OPEN
# inconsistent with the class's malformed-input fail-closed posture). A whitespace-ONLY
# value trims to "" → the caller's unextractable/missing fail-closed branch.
trim_ws() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"   # ltrim
  s="${s%"${s##*[![:space:]]}"}"   # rtrim
  printf '%s' "$s"
}

# --- control flow step 1: read stdin; jq absent → static deny -----------------------
INPUT="$(cat)"
if ! command -v jq >/dev/null 2>&1; then
  printf '%s\n' "$STATIC_DENY_JSON"
  exit 0
fi

# --- control flow step 2: ONE jq extracts all fields (newline-separated) ---------------
# Six fields, ONE per line (read back with `IFS= read` so EMPTY MIDDLE fields are
# preserved verbatim — a tab/`@tsv` split would collapse them, since tab is IFS-
# whitespace, and mis-shift every later field). ALL fields (tool_name incl.) are extracted
# as STRING SCALARS ONLY (`s`) — a non-string value yields "" so it is treated as
# UNEXTRACTABLE downstream (fail-closed), never coerced to a bogus non-empty token via
# tostring (which would let tool_name:{} / owner:{} / cwd:[] skip the fail-closed checks).
# A non-string tool_name → "" → the empty-tool_name fail-closed deny below (defense-in-depth,
# uniform with the owner/repo/cwd/isolation malformed-input posture — the settings matcher
# regex-matches the tool_name STRING, so a non-string tool_name is also unreachable via the
# real platform). The isolation TYPE is emitted separately so the Agent dispatch can tell
# absent (hot path) from present-but-non-string (malformed → conservative worktree class).
# Each field's own newlines/CRs are squashed to spaces so a value can never leak an extra
# line. Robust against a non-object .tool_input; a genuine parse failure yields an empty
# tool_name (fail-closed).
FIELDS="$(printf '%s' "$INPUT" | jq -r '
  def s: if type == "string" then gsub("[\r\n]"; " ") else "" end;
  (if (.tool_input | type) == "object" then .tool_input else {} end) as $ti
  | (.tool_name | s), ($ti.isolation | type), ($ti.isolation | s), ($ti.owner | s), ($ti.repo | s), (.cwd | s)
' 2>/dev/null || true)"

TOOL_NAME=""; ISO_TYPE=""; ISOLATION=""; IN_OWNER=""; IN_REPO=""; PAYLOAD_CWD=""
{
  IFS= read -r TOOL_NAME
  IFS= read -r ISO_TYPE
  IFS= read -r ISOLATION
  IFS= read -r IN_OWNER
  IFS= read -r IN_REPO
  IFS= read -r PAYLOAD_CWD
} <<EOF
$FIELDS
EOF

# Empty OR non-string tool_name (unparseable/malformed stdin) → fail-CLOSED (in-script error).
[ -n "$TOOL_NAME" ] || emit_deny "drive-tool-gate: could not parse the tool call from stdin (empty or non-string tool_name). Failing CLOSED for write-class safety. If this recurs the hook input contract has drifted — re-run bin/install-drive-hooks.sh."

# --- control flow step 3: class dispatch on tool_name ---------------------------------
# CLASS ∈ { worktree, mcp }. Plain Agent (isolation absent, or a clean non-"worktree"
# isolation string) and any non-write tool exit HERE, BEFORE any run scan (the hot-path
# contract). A matched mcp__ suffix absent from the hook's own table denies UNCONDITIONALLY
# (settings/hook drift, fail-closed).
CLASS=""
SUFFIX=""
case "$TOOL_NAME" in
  Agent)
    # Route on the isolation TYPE (D-p2-5, fail-closed leaning):
    #   absent (null)                     → plain Agent HOT PATH (silent, before any scan)
    #   string == "worktree" (ws-trimmed) → worktree class
    #   string != "worktree"              → clean non-worktree isolation → HOT PATH
    #   present but NON-string (obj/arr/…) → MALFORMED → conservative worktree class
    # A `tostring` compare (the pre-fix code) turned isolation:{} into "{}" != "worktree" and
    # took the HOT PATH — silently reopening the worktree bypass. Keying on the type closes it.
    case "$ISO_TYPE" in
      null)
        exit 0 ;;                  # HOT PATH: no isolation → plain Agent → silent, before any scan
      string)
        iso="${ISOLATION#"${ISOLATION%%[![:space:]]*}"}"   # ltrim whitespace
        iso="${iso%"${iso##*[![:space:]]}"}"               # rtrim whitespace
        if [ "$iso" = worktree ]; then
          CLASS=worktree
        else
          exit 0                   # HOT PATH: a clean non-"worktree" isolation string → silent
        fi ;;
      *)
        CLASS=worktree ;;          # malformed (present but non-string) isolation → conservative worktree class
    esac ;;
  EnterWorktree)
    CLASS=worktree ;;
  mcp__*)
    SUFFIX="${TOOL_NAME##*__}"     # suffix after the LAST __
    case "$SUFFIX" in
      create_or_update_file|delete_file|push_files|create_branch|create_pull_request|update_pull_request_branch|merge_pull_request|update_pull_request|create_merge_request|merge_merge_request|accept_merge_request|update_merge_request|rebase_merge_request)
        CLASS=mcp ;;
      *)
        # Matched the write-tool gate but absent from the hook table → drift, fail-CLOSED.
        emit_deny "drive-tool-gate: the tool $TOOL_NAME matched the /drive write-tool gate but is absent from the hook's own tool table (settings/hook drift). Failing CLOSED for write-class safety. Use the canonical gated Bash path (git/gh), or re-run bin/install-drive-hooks.sh to resync the settings matcher with the hook table." ;;
    esac ;;
  *)
    exit 0 ;;                       # mis-registered non-write tool → silent (deny = pure DoS)
esac

# SOURCE-VERIFICATION FAIL-CLOSED. A stale/missing drive-hook-lib.sh can `source` WITHOUT
# defining drive_scan_active_runs; the $(drive_scan_active_runs) scan below would then be an
# undefined-command substitution yielding EMPTY — INDISTINGUISHABLE from "no active run" → a
# matched write-class tool would FALL THROUGH to a silent allow (fail-OPEN) even while a run IS
# active (codex repro: mcp__github__push_files passed with a stale lib). Checked HERE (not at the
# source line) so it fires ONLY for a matched CLASS ∈ {mcp,worktree} tool — non-matched tools
# already exited 0 above — fail-CLOSED via emit_deny (mirroring the jq-absent static-deny posture)
# without denying any non-matched tool.
if ! command -v drive_scan_active_runs >/dev/null 2>&1; then
  emit_deny "drive-tool-gate: drive_scan_active_runs is not defined after sourcing drive-hook-lib.sh (stale/missing library), so active /drive runs cannot be evaluated for this write-class tool ($TOOL_NAME). Failing CLOSED for write-class safety. Re-run bin/install-drive-hooks.sh, or use the canonical gated Bash path (git/gh)."
fi

# --- control flow step 4: active-run scan (Foundation C) ------------------------------
# The active-run predicate is the SHARED drive_scan_active_runs (drive-hook-lib.sh) — the
# same predicate the WorktreeCreate gate reuses (DRY). It echoes the newline-separated active
# run dirs (stage!=done + non-empty repoRoot + mtime liveness), emitting the same per-dir
# skip-with-warning stderr for corrupt / no-repoRoot dirs. $(...) strips the scan's trailing
# newline; the heredoc consumers below re-add one and the `[ -n "$D" ] || continue` guard
# drops the empty trailing line, so the SAME dirs are iterated.
ACTIVE_RUNS="$(drive_scan_active_runs)"

# No active run → the insurance lies dormant → silent pass.
[ -n "$ACTIVE_RUNS" ] || exit 0

# first_active_run : basename of the FIRST active run dir (for fail-closed deny messages).
# `printf '%s\n'` (NOT '%s') so a single-active-run ACTIVE_RUNS (one dir, trailing newline
# stripped by $(...)) is still read by `while read` — else the single-run deny names an
# EMPTY runId (AC-2b).
first_active_run() {
  printf '%s\n' "$ACTIVE_RUNS" | while IFS= read -r d; do
    [ -n "$d" ] && { basename "$d"; break; }
  done
}

# git is the OTHER hard dependency for repo scoping (parse_origin / common_dir_of). Reaching
# here means CLASS ∈ {mcp,worktree} AND ≥1 run is live; with git ABSENT, repo identity cannot
# be derived, so fail-CLOSED (mirrors the jq-absent posture) — never a silent pass of an
# unscoped write. Nearly unreachable in practice (a machine without git cannot run /drive to
# have a live run), but keeps the fail-closed posture uniform with D-p2-5.
if ! command -v git >/dev/null 2>&1; then
  emit_deny "drive-tool-gate: run $(first_active_run) is active on this repo, but git was not found in PATH so this write-class tool ($TOOL_NAME) cannot be repo-scoped against the active run. Failing CLOSED for write-class safety. Install git, or use the canonical gated Bash path (git/gh)."
fi

# --- repo-identity helpers (the PINNED canonical origin parse; shared common-dir) -----
_ORIGIN_HOST=""; _ORIGIN_OWNER=""; _ORIGIN_REPO=""

# parse_origin <dir> : parse `git -C <dir> remote get-url origin` into the canonical
# key parts, lowercased. rc 0 + sets _ORIGIN_HOST/_ORIGIN_OWNER/_ORIGIN_REPO on success;
# rc 1 (globals blanked) if the dir has no origin / is not a repo / the URL is unusable.
# Handles BOTH transport forms (AC-7 requires scp AND URL to key identically):
#   scp  : [user@]host:owner/repo[.git][/…]        (the ':' separates host from PATH)
#   URL  : scheme://[user@]host[:port]/owner/repo[.git][/…]
# scp: strip [user@] (up to LAST @), then host = up-to-FIRST ':', path = after it.
# URL: authority = up-to-first '/', strip userinfo (up to LAST @), strip trailing :port.
parse_origin() {
  local d="$1" url rest authority hostport host path owner repo
  _ORIGIN_HOST=""; _ORIGIN_OWNER=""; _ORIGIN_REPO=""
  [ -n "$d" ] || return 1                # empty dir → don't let `git -C ""` resolve to the hook cwd
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
      # Bracket-aware host extraction: an IPv6 literal is [addr] and itself contains ':',
      # so a bare `%:*` strip would eat part of the address. A bracketed authority keeps
      # everything up to and including the ']'; a normal host strips a trailing :port.
      case "$hostport" in
        \[*\]*) host="${hostport%%\]*}]" ;;   # bracketed IPv6 (with or without :port)
        *)      host="${hostport%:*}" ;;       # normal host[:port] (no colon → unchanged)
      esac
      ;;
    *:*)
      hostport="${url##*@}"              # strip [user@]; host:owner/repo[.git]  (or [ipv6]:owner/repo)
      case "$hostport" in
        \[*\]:*) host="${hostport%%\]:*}]"; path="${hostport#*\]:}" ;;  # bracketed IPv6 scp: ']:' separates
        *)       host="${hostport%%:*}";    path="${hostport#*:}" ;;    # normal scp host:path
      esac
      ;;
    *)
      return 1 ;;
  esac
  # --- Canonical normalization (ONE robust pass; order is load-bearing) --------------
  # Closes the WHOLE enumerated origin-form space at once. 2nd origin-norm finding: round
  # 1 was a case-sensitive `.git` strip BEFORE lowercasing; this round a single-trailing-
  # slash strip let `owner/repo.git//` keep an unstrippable `.git` (the trailing `/`
  # blocked the `%.git` match) → repo derived EMPTY → same-repo NON-match → silent fail-
  # OPEN. Both are subsumed by normalizing in this fixed order:
  #   2. lowercase host + path (case-INSENSITIVE key — GitHub treats host/owner/repo so;
  #      BEFORE the `.git` strip so `.git`/`.Git`/`.GIT` all become a plain `.git` suffix).
  #   3. strip ALL trailing slashes (not one) so `owner/repo.git//` reaches its `.git`.
  #   4. strip a single trailing (now-lowercase) `.git`.
  #   5. strip ALL trailing slashes AGAIN (defensive: `owner/repo/.git//` → step3
  #      `owner/repo/.git` → step4 `owner/repo/` → step5 `owner/repo`).
  host="$(printf '%s' "$host" | tr '[:upper:]' '[:lower:]')"
  path="$(printf '%s' "$path" | tr '[:upper:]' '[:lower:]')"
  while [ "${path%/}" != "$path" ]; do path="${path%/}"; done   # 3: strip ALL trailing slashes
  path="${path%.git}"                                           # 4: strip a trailing .git
  while [ "${path%/}" != "$path" ]; do path="${path%/}"; done   # 5: strip ALL trailing slashes again (defensive)
  owner="${path%%/*}"                    # first segment
  repo="${path##*/}"                     # last segment
  [ -n "$host" ] && [ -n "$owner" ] && [ -n "$repo" ] || return 1
  [ "$owner" != "$path" ] || return 1    # path had no '/' → not owner/repo → unusable
  _ORIGIN_HOST="$host"
  _ORIGIN_OWNER="$owner"
  _ORIGIN_REPO="$repo"
  return 0
}

# common_dir_of <dir> : realpath of the git COMMON dir (stable across every linked
# worktree of the clone). Echoes the resolved absolute dir (rc 0) or rc 1. NOT
# realpath(<dir>/.git): a linked worktree's .git is a gitFILE pointer, not the common dir.
common_dir_of() {
  local d="$1" cd
  [ -n "$d" ] || return 1                # empty dir → don't let `git -C ""` resolve to the hook cwd
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
    create_merge_request)
      printf 'drive-tool-gate: run %s is active on this repo. The GitLab MCP tool create_merge_request opens the MR outside Bash, bypassing the /drive ship gate. Retry: `glab mr create` from the ship worktree (gated: it verifies the finalize review covers the shipped tip).' "$runId" ;;
    merge_merge_request|accept_merge_request)
      printf 'drive-tool-gate: run %s is active on this repo. In the /drive flow the MR merge is human-owned at Gate B; the GitLab MCP tool %s is not the sanctioned route to merge the MR during an active run — merge after Gate B approval. (This denies the MCP omission path; the Bash `glab mr merge` twin stays ungated — a deliberately-deferred asymmetry, not a global prohibition.)' "$runId" "$suffix" ;;
    update_merge_request)
      printf 'drive-tool-gate: run %s is active on this repo. MR title/description/state/target edits are human-owned at Gate B; the GitLab MCP tool update_merge_request is not the sanctioned route to edit the MR during an active run — edit after Gate B approval. (This denies the MCP omission path; the Bash `glab mr update` twin stays ungated — a deliberately-deferred asymmetry, not a global prohibition.)' "$runId" ;;
    rebase_merge_request)
      printf 'drive-tool-gate: run %s is active on this repo. The GitLab MCP tool rebase_merge_request rewrites the MR source branch on the remote (the analog of GitHub update_pull_request_branch), bypassing the /drive ship gate. Retry: `git merge origin/<target>` / `git rebase` in the ship worktree, then the gated `git push`.' "$runId" ;;
  esac
}

worktree_deny_reason() {
  local tool="$1" runId="$2"
  printf 'drive-tool-gate: run %s is active on this repo. The native worktree tool %s creates a worktree on a harness-named branch, so the plan/phasedesign gates (`git worktree add … -b slice/…`) and the slice merge/test gates (keyed on slice/<runId>/<id> refs) never fire. Retry: `git worktree add $RUN_DIR/wt/<id> -b slice/<runId>/<id> <phaseBaseSha>` (gated), then dispatch the agent into that path WITHOUT worktree isolation (or `cd` into it).' "$runId" "$tool"
}

# worktree_failclosed_reason: a worktree-class tool whose cwd FIELD is absent / non-string /
# empty (no usable cwd string) while a run is live → fail-CLOSED (D-p2-5): a missing cwd on a
# worktree tool may default to the session's repo, so we cannot prove it is NOT the run's
# repo. (Edge-case-9's silent pass is for a PRESENT cwd string that resolves to no run-repo —
# a non-git dir, an unrelated repo, or a nonexistent path — which this fail-closed no longer
# sweeps up.)
worktree_failclosed_reason() {
  local tool="$1" runId="$2"
  printf 'drive-tool-gate: run %s is active on this repo, and the native worktree tool %s was dispatched WITHOUT a usable cwd (the cwd field is missing, non-string, or empty), so its repo identity cannot be scoped against the active run. Failing CLOSED for gate safety. Retry: `git worktree add $RUN_DIR/wt/<id> -b slice/<runId>/<id> <phaseBaseSha>` (gated), then dispatch the agent into that path WITHOUT worktree isolation (or `cd` into it).' "$runId" "$tool"
}

# --- control flow step 5: repo scoping over the active runs --------------------------
if [ "$CLASS" = mcp ]; then
  # Trim OUTER whitespace BEFORE comparing: a padded-but-same-repo id (owner:"owner ") is
  # semantically the SAME repo and must still MATCH → deny, not slip past on the padding.
  # (A whitespace-ONLY owner/repo trims to "" → the unextractable fail-closed branch below.)
  IN_OWNER_LC="$(printf '%s' "$(trim_ws "$IN_OWNER")" | tr '[:upper:]' '[:lower:]')"
  IN_REPO_LC="$(printf '%s' "$(trim_ws "$IN_REPO")"  | tr '[:upper:]' '[:lower:]')"
  # Unextractable owner/repo (empty OR non-string → "") while ≥1 run is live → fail-CLOSED
  # over-deny (names a run). A non-string owner/repo (owner:{} / repo:[]) is unextractable.
  if [ -z "$IN_OWNER_LC" ] || [ -z "$IN_REPO_LC" ]; then
    emit_deny "drive-tool-gate: run $(first_active_run) is active on this repo, and this git-hosting MCP write ($TOOL_NAME) carries no extractable owner/repo to scope it. Failing CLOSED for write-class safety (over-deny). Retry via the canonical gated Bash path (git/gh) from the run's worktree."
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

# Defense-in-depth (fix #3): ONLY the worktree class reaches here. A regressed/empty CLASS
# (e.g. a plain Agent that lost its hot-path early exit) must NOT fall through into a
# worktree deny — exit silently instead of denying every fan-out dispatch.
[ "$CLASS" = worktree ] || exit 0

# Trim OUTER whitespace from the cwd string BEFORE resolving it: a padded-but-same-repo cwd
# ("<run-repo-path> ") makes `git -C "<path> "` miss the real dir → silent-pass bypass;
# trimming lets it resolve and match → deny. A whitespace-ONLY cwd trims to "" → the
# missing-cwd fail-closed branch below (correct: an all-whitespace cwd is unusable).
PAYLOAD_CWD="$(trim_ws "$PAYLOAD_CWD")"

# CLASS = worktree (Agent isolation:"worktree" / EnterWorktree). Scope by the payload
# cwd's repo identity: origin identity UNION common-dir fast-match against each run.
CWD_ORIGIN_KEY=""
if parse_origin "$PAYLOAD_CWD"; then
  CWD_ORIGIN_KEY="$_ORIGIN_HOST/$_ORIGIN_OWNER/$_ORIGIN_REPO"
fi
CWD_COMMONDIR="$(common_dir_of "$PAYLOAD_CWD" 2>/dev/null || true)"

# Fail-CLOSED (fix #1, D-p2-5) ONLY when the cwd FIELD itself is absent / non-string / empty
# ($PAYLOAD_CWD came back empty from the jq `s` string-scalar extraction). A missing cwd on a
# worktree tool may default to the session's repo, so with ≥1 run live we cannot prove it is
# NOT the run's repo → DENY. A PRESENT non-empty cwd STRING — whether it resolves to a git
# repo, a non-git dir, an unrelated repo, or a nonexistent path — falls through to the per-run
# match below, which DENIES only on an origin/common-dir match and otherwise silent-passes
# (Edge-case-9: a valid non-run-repo cwd must PASS). Discriminating on the STRING being present
# (not on resolution succeeding) restores that Edge-9 pass while keeping the malformed-payload
# case fail-closed.
if [ -z "$PAYLOAD_CWD" ]; then
  emit_deny "$(worktree_failclosed_reason "$TOOL_NAME" "$(first_active_run)")"
fi

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
