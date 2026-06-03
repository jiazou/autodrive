#!/usr/bin/env bash
# drive-stop-guard.sh — a Claude Code **Stop** hook: best-effort backstop for the
# /drive code-review enforcement (D6). It is NOT the guarantee — the
# merge→advance→ship PreToolUse gate chain is. The Stop guard catches the narrow
# window where the hooks were installed mid-run inside an in-flight phase, by
# refusing to let the turn end while a slice already merged into the CURRENT LIVE
# phaseInt/<runId>/<P> still lacks a counting review.
#
# Stdin: the Stop hook JSON. We read `.cwd` (where the /drive session runs) and
# `.stop_hook_active` (whether a prior Stop block is already in flight). We do NOT
# suppress on .stop_hook_active — persistence across turns is desired; the platform's
# 8-consecutive-block cap is the escape that surfaces the run to the human (edge 7).
#
# Behavior:
#   - Resolve runId from `git HEAD` in .cwd (drive_runid_from_head). Not a drive
#     branch / git fails / no RUN_DIR  → exit 0 (inert; edge 2/6 — never false-block
#     an idle, queued, paused-at-gate, or non-drive session).
#   - Run drive-conformance.sh <RUN_DIR> --mode audit. Audit flags ONLY slices merged
#     into the live phaseInt that lack a counting review, so it can never false-block a
#     run with no live phaseInt or with only queued/in-flight/reviewed slices.
#   - exit 0 (clean)  → no block.
#   - exit 2 (audit fail-open per D4) → no block (don't wedge mid-build on a transient
#     git/IO error; the ship gate backstops code review).
#   - exit 1 (violations) → emit {"decision":"block","reason":"..."} naming the
#     merged-but-unreviewed scopes + the exact /drive-review commands, telling Claude
#     not to stop until `drive-conformance.sh <RUN_DIR> --mode audit` is clean.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=bin/drive-hook-lib.sh
. "$SCRIPT_DIR/drive-hook-lib.sh"
CONF="$SCRIPT_DIR/drive-conformance.sh"

# --- read stdin JSON; .cwd is where the /drive session is running ---
payload="$(cat)"
cwd="$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null || true)"
[ -n "$cwd" ] || exit 0   # no cwd → can't resolve a run → inert

# --- resolve runId from HEAD; not a drive branch → inert ---
runId="$(drive_runid_from_head "$cwd" 2>/dev/null)" || exit 0
[ -n "$runId" ] || exit 0

# --- locate the run dir; absent → not a managed run → inert ---
RUN_DIR="$(drive_run_dir "$runId" 2>/dev/null)" || exit 0
[ -n "$RUN_DIR" ] || exit 0

# --- audit: flags ONLY merged-but-unreviewed slices in the live phaseInt ---
# conformance's audit mode resolves git refs (for-each-ref / rev-parse / merge-base)
# against the CURRENT git repo, so it must run from the /drive session's cwd — the repo
# whose phaseInt/<runId>/<P> + slice/<runId>/<id> refs we audit. The RUN_DIR arg only
# locates the review artifacts.
#
# The cd-failure path MUST be distinct from the conformance-verdict path: a
# missing/mistyped cwd is NOT an audit violation. If `cd "$cwd"` fails we exit 0
# (inert) — never false-block (AC9). Only a conformance verdict of rc==1 (the
# conformance command actually having run) may block; rc==2 (fail-open) and any
# exec failure → exit 0. We therefore run the cd in its own step and bail inert on
# failure, so `rc` below reflects ONLY the conformance command's exit status.
cd "$cwd" 2>/dev/null || exit 0   # missing/mistyped cwd → inert, not a violation
out="$( "$CONF" "$RUN_DIR" --mode audit 2>/dev/null )"
rc=$?

# Only a real conformance violation (rc==1) blocks. exit 0 clean, exit 2 audit
# fail-open (D4), and any exec failure (126/127/…) → no block.
[ "$rc" -eq 1 ] || exit 0

# rc==1: real violations. Build the human/Claude-facing remediation reason.
# Each violation object carries a "scope" like "slice:4a"; map it to the exact
# /drive-review command. jq parses the conformance JSON; fall back gracefully if the
# payload is somehow unparseable (still block — rc==1 is an authoritative verdict).
scopes="$(printf '%s' "$out" | jq -r '.violations[]?.scope' 2>/dev/null | sort -u || true)"

cmds=""
names=""
if [ -n "$scopes" ]; then
  while IFS= read -r scope; do
    [ -n "$scope" ] || continue
    names="$names $scope"
    case "$scope" in
      slice:*) id="${scope#slice:}"; cmds="$cmds  /drive-review slice $id"$'\n' ;;
      phase:*) p="${scope#phase:}";  cmds="$cmds  /drive-review phase $p"$'\n' ;;
      *)       cmds="$cmds  /drive-review $scope"$'\n' ;;
    esac
  done <<EOF
$scopes
EOF
fi
names="${names# }"
[ -n "$names" ] || names="(see audit output)"

reason="/drive code-review enforcement (Stop backstop): the following scope(s) are merged into the live phase integration branch but have NO counting code review:
  $names

Do NOT stop. Run the missing review(s) now:
${cmds}then re-check with:
  $CONF $RUN_DIR --mode audit
Only stop once that audit reports clean (exit 0)."

# Emit the Stop-block decision. jq builds valid JSON regardless of newlines in reason.
jq -nc --arg reason "$reason" '{decision:"block",reason:$reason}'
exit 0
