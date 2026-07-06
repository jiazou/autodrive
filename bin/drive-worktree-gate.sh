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

# REQUIRED-TOOL FAIL-CLOSED (D-w2). drive_scan_active_runs suppresses its find/dirname/sort/jq
# pipeline errors to /dev/null, so a MISSING scan binary yields an EMPTY result —
# INDISTINGUISHABLE from "no active run" → a FAIL-OPEN provision even while a run IS active
# (codex adversarial repro: PATH without `find`/`sort` + an active run → the gate provisioned).
# An empty scan is only trustworthy when the scan could actually RUN. So before trusting any
# scan result, require every binary the active-run DECISION depends on — jq, find, sort,
# dirname — PLUS git (needed to provision the idle path). Any missing → FAIL-CLOSED DENY
# (exit 2), exactly like the shipped PreToolUse gate's jq-absent posture. A fail-OPEN here would
# reopen the exact frontmatter-isolation bypass this AUTHORITATIVE gate exists to close.
# RESIDUAL (consistent with D-w2): a machine missing jq/find/sort/dirname/git denies native
# worktree creation — these are all documented /drive preconditions, the accepted safe direction
# (recoverable route-to-Bash), not a bug.
_missing=""
for _t in jq find sort dirname git; do
  command -v "$_t" >/dev/null 2>&1 || _missing="$_missing $_t"
done
if [ -n "$_missing" ]; then
  printf '/drive worktree gate: required tool(s) not found in PATH:%s. The active-run scan cannot run reliably, so an empty result cannot be trusted as "no active run". Failing CLOSED (denying native worktree creation) — matches the drive-tool-gate.sh jq-absent posture (D-w2); these are documented /drive preconditions. Install the missing tool(s), or create the worktree via Bash: git worktree add <path> -b slice/<runId>/<id>.\n' "$_missing" >&2
  exit 2
fi

# BLIND-ROOT FAIL-CLOSED (D-w2). The scan's `find "$RUNS_ROOT"` suppresses errors, so if the
# runs root EXISTS but is unreadable/unsearchable (`chmod 000 ~/.claude/harness-runs` — codex
# repro), find enumerates NOTHING → an EMPTY scan → the gate would conclude "no active run" and
# provision even while a run IS active. An empty scan is only trustworthy when the root could
# actually be searched. So: if RUNS_ROOT EXISTS but is not both readable AND searchable → the
# scan is BLIND → FAIL-CLOSED DENY (exit 2), like the tool-presence pre-check. An ABSENT root is
# NOT a blind scan — it genuinely means no runs on this machine → allow/provision. Kept surgical:
# a single unreadable SUBDIR is NOT guarded here (find still enumerates the rest of the root); a
# self-hidden run subdir is deliberate-evasion / forgery-class, out of scope (§ Limitations).
RUNS_ROOT="$HOME/.claude/harness-runs"
if [ -e "$RUNS_ROOT" ] && { [ ! -r "$RUNS_ROOT" ] || [ ! -x "$RUNS_ROOT" ]; }; then
  printf '/drive worktree gate: the /drive runs root %s exists but is not readable+searchable, so the active-run scan is BLIND (it cannot tell whether a run is active). Failing CLOSED (denying native worktree creation) — matches the tool-absent posture (D-w2). Fix the directory permissions, or create the worktree via Bash: git worktree add <path> -b slice/<runId>/<id>.\n' "$RUNS_ROOT" >&2
  exit 2
fi

# Scan for active runs. Suppress the predicate's advisory per-dir corrupt/no-repoRoot warnings
# so they never pollute the provisioning stdout/stderr contract. Its scan binaries are now
# guaranteed present (the required-tool check above) and the runs root is scannable (the
# blind-root check above), so an empty result genuinely means "no active run", not "the scan
# silently failed / was blind".
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

# Validate NAME is a SINGLE safe path segment before it becomes a path component. An unsafe name
# (path separator, traversal `..`, leading `-` option-injection, or any char outside
# [A-Za-z0-9._-]) must NOT be silently rewritten into a bogus success — reject it and let Claude
# Code surface the real reason. (The observed native names — `wtc-probe`, `agent-<hash>` — are
# all inside this charset.) Exit 1 (a provisioning ERROR, NOT the exit-2 policy DENY).
case "$NAME" in
  .|..|-*|*/*|*..*)
    printf '/drive worktree gate: refusing to provision — worktree name "%s" is unsafe (path separator, traversal, or leading dash). No worktree created.\n' "$NAME" >&2
    exit 1 ;;
  *[!A-Za-z0-9._-]*)
    printf '/drive worktree gate: refusing to provision — worktree name "%s" contains characters outside [A-Za-z0-9._-]. No worktree created.\n' "$NAME" >&2
    exit 1 ;;
esac

# Provisioning REQUIRES a real repo cwd to `git worktree add` against. A missing / non-directory
# cwd cannot be provisioned — fail loudly (exit 1) rather than echo a bogus path Claude Code
# would treat as a real worktree.
if [ -z "$CWD" ] || [ ! -d "$CWD" ]; then
  printf '/drive worktree gate: cannot provision a worktree — the payload cwd is missing or not a directory ("%s"). No worktree created.\n' "$CWD" >&2
  exit 1
fi
WT_PATH="$(dirname "$CWD")/$NAME"

# Create the worktree (I-a). Detached HEAD at cwd's current commit — no new branch (native
# worktrees are not slice/<runId>/<id> branches, and there is no active run to key one to). Do
# NOT swallow the result: echo the path ONLY if the worktree was ACTUALLY created. On failure
# (path collision, cwd not a git repo, any git error) surface the REAL git error to stderr and
# exit non-zero (1 — a provisioning ERROR, not the exit-2 policy DENY) so Claude Code reports the
# genuine failure instead of believing a bogus success path (the earlier `|| true` bug wedged
# creation by echoing a path even when `git worktree add` failed).
if ! _giterr="$(git -C "$CWD" worktree add --detach "$WT_PATH" 2>&1)"; then
  printf '/drive worktree gate: failed to provision the worktree at %s: %s. No worktree created.\n' "$WT_PATH" "$_giterr" >&2
  exit 1
fi
printf '%s\n' "$WT_PATH"
exit 0
