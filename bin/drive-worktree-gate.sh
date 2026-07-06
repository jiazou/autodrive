#!/usr/bin/env bash
# drive-worktree-gate.sh — WorktreeCreate hook: the AUTHORITATIVE native-worktree gate (G1).
#
# The PreToolUse tool gate (drive-tool-gate.sh) catches Agent tool_input.isolation:"worktree"
# and EnterWorktree, but the subagent FRONTMATTER isolation:"worktree" path is NOT reliably
# surfaced in tool_input (verified-hook-api.md §4), so PreToolUse can MISS it. WorktreeCreate
# is the authoritative interception point: it IGNORES matchers and fires on ACTUAL native
# worktree creation for BOTH `--worktree` AND frontmatter isolation:"worktree" (empirically
# proven: worktree-proof/RESULT.md). This gate DENIES native worktree creation with exit 2
# while a /drive run is active, routing it to the gated Bash `git worktree add`.
#
#   DENY (run active) = exit 2 + stderr reason (proven: exit 2 blocks creation for both
#                       --worktree and isolation:"worktree" — worktree-proof/RESULT.md).
#   ALLOW (no run)    = PROVISION so native creation still works. WorktreeCreate is a
#                       PROVISIONING hook: a bare `exit 0` with NO stdout path is itself an
#                       ERROR that blocks creation ("hook succeeded but returned no worktree
#                       path" — worktree-proof/claude-worktree.out), which would wedge ALL
#                       native worktree creation machine-wide. The allow path MUST return a
#                       worktree path. A bare `exit 0` here is a DESIGN VIOLATION.
#
# Deny is session-independent and NOT repo-scoped (D-w1): it fires while ANY run with a
# non-empty repoRoot is active (drive_scan_active_runs already skips no-repoRoot runs). Safe
# direction (over-deny of an unrelated repo's native worktree creation is recoverable via
# Bash `git worktree add`), and keeps provisioning off the active hot path.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/drive-hook-lib.sh"

INPUT="$(cat)"   # WorktreeCreate payload: {name, cwd, session_id, hook_event_name, ...}

# jq absent → the active-run scan cannot run. FAIL-CLOSED = DENY (exit 2), MATCHING the shipped
# PreToolUse gate's jq-absent posture (drive-tool-gate.sh: static deny). A fail-OPEN here would
# reopen the exact frontmatter-isolation bypass this AUTHORITATIVE gate exists to close. jq is a
# documented /drive precondition (D-w2).
if ! command -v jq >/dev/null 2>&1; then
  printf '/drive worktree gate: jq is required to evaluate active /drive runs but was not found in PATH. Failing CLOSED (denying native worktree creation) — jq is a documented /drive precondition, and this matches drive-tool-gate.sh. Install jq, or create the worktree via Bash: git worktree add <path> -b slice/<runId>/<id>.\n' >&2
  exit 2
fi

# Scan for active runs. Suppress the predicate's advisory per-dir corrupt/no-repoRoot warnings
# so they never pollute the provisioning stdout/stderr contract.
ACTIVE="$(drive_scan_active_runs 2>/dev/null)"

if [ -n "$ACTIVE" ]; then   # >=1 active run (with a repoRoot) on this machine → DENY
  runId="$(basename "$(printf '%s\n' "$ACTIVE" | sed -n '1p')")"
  printf '/drive run %s is active. Native worktree creation is blocked — create it via Bash: git worktree add <path> -b slice/<runId>/<id>, so the merge gate can enforce review.\n' "$runId" >&2
  exit 2
fi

# INACTIVE (jq present, scan clean, no active run) → PROVISION. WorktreeCreate is a provisioning
# hook: once installed it OWNS the outcome, so the hook must CREATE the worktree AND return its
# path to stdout. AC-8b spike (worktree-proof/RESULT-allow.md) resolved the create-vs-echo
# contract as I-a: echoing a path WITHOUT creating it FAILS (Claude Code expects the worktree to
# already exist at the echoed path — a bare echo hangs / creates nothing), so the hook runs
# `git worktree add` ITSELF, then echoes the path. A bare `exit 0` with NO path is a DESIGN
# VIOLATION (it would wedge ALL native worktree creation machine-wide —
# worktree-proof/claude-worktree.out).
#
# The payload carries {name, cwd} but no explicit path field (worktree-proof/wtc.log), so the
# path is DERIVED from name + cwd: a sibling of the repo dir named for the worktree.
NAME="$(printf '%s' "$INPUT" | jq -r '.name // ""' 2>/dev/null || true)"
CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // ""' 2>/dev/null || true)"
[ -n "$NAME" ] || NAME="worktree-$$"
if [ -n "$CWD" ] && [ -d "$CWD" ]; then
  PARENT="$(dirname "$CWD")"
else
  PARENT="${TMPDIR:-/tmp}"
fi
WT_PATH="$PARENT/$NAME"

# Create the worktree (I-a). Detached HEAD at cwd's current commit — no new branch (native
# worktrees are not slice/<runId>/<id> branches, and there is no active run to key one to).
# Best-effort: on any failure still echo the path (a bare exit 0 would wedge creation) and let
# Claude Code surface the underlying git error.
if [ -n "$CWD" ] && [ -d "$CWD" ]; then
  git -C "$CWD" worktree add --detach "$WT_PATH" >/dev/null 2>&1 || true
fi
printf '%s\n' "$WT_PATH"
exit 0
