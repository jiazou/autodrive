#!/usr/bin/env bash
# drive-worktree-gate.test.sh — the authoritative WorktreeCreate gate (bin/drive-worktree-gate.sh).
# Covers AC-8 (exit codes + allow-path provisioning) and AC-9 (installer wires WorktreeCreate).
#
#   AC-8(a)  run active            -> exit 2 + stderr routing reason, NO stdout path, NO worktree
#   AC-8(a2) jq absent             -> exit 2 (fail-closed DENY), matching drive-tool-gate.sh
#   AC-8(b)  no run active         -> exit 0, a worktree path on stdout, AND the worktree is
#                                     ACTUALLY created (I-a: the hook `git worktree add`s it) —
#                                     the unit-level closure of the live AC-8b spike
#                                     (worktree-proof/RESULT-allow.md: --worktree AND
#                                     isolation:"worktree" both create; a bare exit 0 would wedge).
#
# HOME is a dedicated temp dir so the gate's $HOME/.claude/harness-runs scan is isolated (empty
# = no active run). bash 3.2-safe.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$HERE/.." && pwd)"
GATE="$REPO_DIR/bin/drive-worktree-gate.sh"
INSTALLER="$REPO_DIR/bin/install-drive-hooks.sh"
WTFX="$HERE/fixtures/worktree/worktree-create.json"

HOME="$(mktemp -d "${TMPDIR:-/tmp}/wt-gate-home.XXXXXX")"; export HOME
RUNS="$HOME/.claude/harness-runs"; mkdir -p "$RUNS"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/wt-gate-work.XXXXXX")"
trap 'rm -rf "$HOME" "$WORK"' EXIT

PASS=0; FAIL=0
check() { if [ "$2" = "$3" ]; then echo "PASS: $1"; PASS=$((PASS+1)); else echo "FAIL: $1 (expected '$3', got '$2')"; FAIL=$((FAIL+1)); fi; }
contains() { case "$2" in *"$3"*) echo "PASS: $1"; PASS=$((PASS+1));; *) echo "FAIL: $1 (missing literal '$3')"; FAIL=$((FAIL+1));; esac; }

mk_repo() { local d="$1"; mkdir -p "$d"; git -C "$d" init -q -b main; git -C "$d" -c user.name=t -c user.email=t@t commit -q --allow-empty -m init; }
mk_run() { local rd="$RUNS/$1"; mkdir -p "$rd"; printf '{"stage":"%s","repoRoot":"%s"}\n' "${3:-execute}" "$2" > "$rd/state.json"; printf '' > "$rd/event-log.jsonl"; }

# payload_for <cwd> <name> — the WorktreeCreate fixture with cwd/name overridden.
payload_for() { jq -c --arg c "$1" --arg n "$2" '.cwd=$c | .name=$n' "$WTFX"; }

check "hook exists"     "$( [ -f "$GATE" ] && echo yes || echo no )" yes
check "hook executable" "$( [ -x "$GATE" ] && echo yes || echo no )" yes

# =====================================================================================
# AC-8(a) — a run active → DENY (exit 2), NO stdout path, stderr routing reason.
# =====================================================================================
REPO="$WORK/repo"; mk_repo "$REPO"
mk_run run-primary "$REPO"
ERR="$WORK/a.err"
out="$(payload_for "$REPO" wt-probe | bash "$GATE" 2>"$ERR")"; rc=$?
check "AC-8(a) run active → exit 2" "$rc" "2"
check "AC-8(a) run active → NO stdout path" "$out" ""
contains "AC-8(a) stderr names the active run" "$(cat "$ERR")" "run run-primary is active"
contains "AC-8(a) stderr routes to gated Bash git worktree add" "$(cat "$ERR")" "git worktree add"
check "AC-8(a) run active → no worktree created" "$(git -C "$REPO" worktree list | wc -l | tr -d ' ')" "1"

# a SECOND unrelated repo is ALSO blocked while any run is active (D-w1: not repo-scoped)
REPO2="$WORK/repo2"; mk_repo "$REPO2"
out="$(payload_for "$REPO2" wt-probe2 | bash "$GATE" 2>/dev/null)"; rc=$?
check "AC-8(a) D-w1 machine-wide: unrelated repo also blocked while a run is active" "$rc" "2"

# a run whose state.json has NO repoRoot does NOT force a deny (inherited predicate skip)
rm -rf "$RUNS"/*
mkdir -p "$RUNS/run-noroot"; printf '{"stage":"execute"}\n' > "$RUNS/run-noroot/state.json"; printf '' > "$RUNS/run-noroot/event-log.jsonl"
out="$(payload_for "$REPO" wt-noroot | bash "$GATE" 2>/dev/null)"; rc=$?
check "AC-8 no-repoRoot run does NOT force deny (inherited skip) → provisions" "$rc" "0"
git -C "$REPO" worktree remove --force "$WORK/wt-noroot" 2>/dev/null; git -C "$REPO" worktree prune 2>/dev/null

# =====================================================================================
# AC-8(a2) — jq absent → FAIL-CLOSED DENY (exit 2), matching drive-tool-gate.sh.
# =====================================================================================
rm -rf "$RUNS"/*   # NOTE: even with NO active run, jq-absent must still DENY (not provision)
STUB="$WORK/stub-bin"; mkdir -p "$STUB"
for b in cat git dirname; do ln -sf "$(command -v "$b")" "$STUB/$b"; done   # deliberately NO jq
ERR2="$WORK/a2.err"
out="$(payload_for "$REPO" wt-nojq | PATH="$STUB" /bin/bash "$GATE" 2>"$ERR2")"; rc=$?
check "AC-8(a2) jq absent → exit 2 (fail-closed DENY, even with no active run)" "$rc" "2"
check "AC-8(a2) jq absent → NO stdout path" "$out" ""
contains "AC-8(a2) jq-absent stderr mentions jq" "$(cat "$ERR2")" "jq is required"

# =====================================================================================
# AC-8(b) — no run active → PROVISION: exit 0, a worktree path on stdout, AND the worktree is
#           ACTUALLY created (I-a). A bare exit 0 with no path is a design violation.
# =====================================================================================
rm -rf "$RUNS"/*
PROVREPO="$WORK/provrepo"; mk_repo "$PROVREPO"
ERR3="$WORK/b.err"
out="$(payload_for "$PROVREPO" wtc-allow | bash "$GATE" 2>"$ERR3")"; rc=$?
check "AC-8(b) no run active → exit 0" "$rc" "0"
check "AC-8(b) allow path returns a NON-empty worktree path (never a bare exit 0)" "$( [ -n "$out" ] && echo nonempty || echo empty )" "nonempty"
check "AC-8(b) returned path is the derived sibling ($WORK/wtc-allow)" "$out" "$WORK/wtc-allow"
check "AC-8(b) I-a: the worktree is ACTUALLY created at the returned path" "$( [ -d "$out" ] && git -C "$out" rev-parse --is-inside-work-tree 2>/dev/null || echo no )" "true"
check "AC-8(b) it appears in the repo's worktree list" "$(git -C "$PROVREPO" worktree list | grep -c wtc-allow)" "1"
# clean up the created worktree
git -C "$PROVREPO" worktree remove --force "$out" 2>/dev/null; git -C "$PROVREPO" worktree prune 2>/dev/null

# AC-8(b) missing/non-string name → falls back to a non-empty derived path (still provisions)
out="$(jq -c --arg c "$PROVREPO" 'del(.name) | .cwd=$c' "$WTFX" | bash "$GATE" 2>/dev/null)"; rc=$?
check "AC-8(b) missing name → still exit 0 + a path (fallback name)" "$rc" "0"
check "AC-8(b) missing name → non-empty path" "$( [ -n "$out" ] && echo nonempty || echo empty )" "nonempty"
git -C "$PROVREPO" worktree remove --force "$out" 2>/dev/null; git -C "$PROVREPO" worktree prune 2>/dev/null

# =====================================================================================
# AC-9 — the installer wires WorktreeCreate → drive-worktree-gate.sh (matcher-less).
#        (Deeper idempotency/migration coverage lives in install-drive-hooks.test.sh.)
# =====================================================================================
WSET="$WORK/wt-settings.json"
bash "$INSTALLER" "$WSET" >/dev/null 2>&1
wired=$(jq --arg p "$GATE" '[.hooks.WorktreeCreate[]?.hooks[]? | select((.command//"")==$p)] | length' "$WSET")
check "AC-9 installer wires WorktreeCreate → drive-worktree-gate.sh" "$wired" "1"
matcherless=$(jq '[.hooks.WorktreeCreate[] | select(has("matcher")|not)] | length' "$WSET")
check "AC-9 WorktreeCreate entry is matcher-less" "$matcherless" "1"

# --- Summary -------------------------------------------------------------------------
echo "----------------------------------------"
echo "PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -eq 0 ] || exit 1
