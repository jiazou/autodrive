#!/usr/bin/env bash
# drive-tool-gate.test.sh — the sibling PreToolUse hook suite (bin/drive-tool-gate.sh).
# Covers AC-1..AC-8 + AC-15: deny-JSON shape / silent clean paths, the hot path, live
# repo-scoped denies (8 MCP write tools + Agent-worktree + EnterWorktree), the settings
# matcher selection + drift table defense, liveness (stale/done/refresh), corrupt-skip,
# the repo-scope + origin-form matrix (scp/URL/case/trailing-slash/port+userinfo,
# linked-worktree common-dir, second clone, no-origin fallback, unextractable owner/repo),
# jq-absent + empty-stdin fail-closed, and the fixture provenance corpus.
#
# HOME is a dedicated temp dir so the gate's $HOME/.claude/harness-runs scan is isolated
# and the real one is never touched. bash 3.2-safe.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$HERE/.." && pwd)"
GATE="$REPO_DIR/bin/drive-tool-gate.sh"
INSTALLER="$REPO_DIR/bin/install-drive-hooks.sh"
FX="$HERE/fixtures/github-mcp"

# Dedicated HOME (scan root = $HOME/.claude/harness-runs).
HOME="$(mktemp -d "${TMPDIR:-/tmp}/tool-gate-home.XXXXXX")"; export HOME
RUNS="$HOME/.claude/harness-runs"; mkdir -p "$RUNS"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/tool-gate-work.XXXXXX")"
trap 'rm -rf "$HOME" "$WORK"' EXIT

PASS=0; FAIL=0
check() { if [ "$2" = "$3" ]; then echo "PASS: $1"; PASS=$((PASS+1)); else echo "FAIL: $1 (expected '$3', got '$2')"; FAIL=$((FAIL+1)); fi; }
# contains <desc> <haystack> <needle-literal>
contains() { case "$2" in *"$3"*) echo "PASS: $1"; PASS=$((PASS+1));; *) echo "FAIL: $1 (missing literal '$3')"; FAIL=$((FAIL+1));; esac; }

_gitc() { git -C "$1" -c user.name=t -c user.email=t@t -c commit.gpgsign=false "${@:2}"; }
mk_repo() { # mk_repo <dir> [origin-url]  — an initialized repo with one commit
  local d="$1"; mkdir -p "$d"; git -C "$d" init -q -b main
  [ -n "${2:-}" ] && git -C "$d" remote add origin "$2"
  _gitc "$d" commit -q --allow-empty -m init
}
mk_run() { # mk_run <runId> <repoRoot> [stage]  — a fresh-mtime active run dir
  local rd="$RUNS/$1"; mkdir -p "$rd"
  printf '{"stage":"%s","repoRoot":"%s"}\n' "${3:-execute}" "$2" > "$rd/state.json"
  printf '' > "$rd/event-log.jsonl"
}
# run_gate <fixture|json> [cwd_override] → stdout (deny JSON or empty). rc in $GATE_RC.
GATE_RC=0
run_gate() {
  local payload
  if [ -f "$1" ]; then payload="$(cat "$1")"; else payload="$1"; fi
  if [ -n "${2:-}" ]; then payload="$(printf '%s' "$payload" | jq -c --arg c "$2" '.cwd=$c')"; fi
  local out; out="$(printf '%s' "$payload" | bash "$GATE" 2>/dev/null)"; GATE_RC=$?
  printf '%s' "$out"
}
is_deny() { case "$1" in *'"permissionDecision":"deny"'*) echo yes;; *) echo no;; esac; }

# =====================================================================================
# AC-1 — hook exists, executable; deny is the exact JSON shape + exit 0; clean = silent.
# =====================================================================================
check "AC-1 hook exists"      "$( [ -f "$GATE" ] && echo yes || echo no )" yes
check "AC-1 hook executable"  "$( [ -x "$GATE" ] && echo yes || echo no )" yes

RUNREPO="$WORK/runrepo"; mk_repo "$RUNREPO" "https://github.com/octo-org/drive-fixture-repo.git"
mk_run run-primary "$RUNREPO"

out="$(run_gate "$FX/push_files.json")"
check "AC-1 matched write emits deny (exit 0)" "$GATE_RC" "0"
check "AC-1 deny carries permissionDecision:deny" "$(is_deny "$out")" "yes"
check "AC-1 deny is valid single-line JSON" "$(printf '%s' "$out" | jq -e '.hookSpecificOutput.hookEventName' >/dev/null 2>&1 && echo yes || echo no)" "yes"
check "AC-1 deny hookEventName == PreToolUse" "$(printf '%s' "$out" | jq -r '.hookSpecificOutput.hookEventName')" "PreToolUse"
check "AC-1 deny is exactly ONE line" "$(printf '%s' "$out" | wc -l | tr -d ' ')" "0"  # printf w/o trailing NL from jq -> single line, 0 newlines in capture
# clean path: read tool to unrelated repo owner (matcher would not select it, but pipe direct)
out="$(run_gate "$FX/create_pull_request.json")"
# create_pull_request to the matching run → deny; but a clean MCP write to another repo → silent:
CLEAN="$(printf '{"tool_name":"mcp__github__push_files","tool_input":{"owner":"nobody","repo":"elsewhere"},"cwd":"/x"}' | bash "$GATE" 2>/dev/null)"; crc=$?
check "AC-1 clean/non-matching path emits NO stdout" "$CLEAN" ""
check "AC-1 clean path exits 0" "$crc" "0"

# =====================================================================================
# AC-2 — hot path: agent-plain → exit 0, NO stdout, and NO run scan (proven by pointing
#         harness-runs at a regular FILE — a scan would choke; the hot path never scans).
# =====================================================================================
HOT_HOME="$WORK/hot-home"; mkdir -p "$HOT_HOME/.claude"; printf 'NOT A DIR\n' > "$HOT_HOME/.claude/harness-runs"
out="$(printf '%s' "$(cat "$FX/agent-plain.json")" | HOME="$HOT_HOME" bash "$GATE" 2>/dev/null)"; hrc=$?
check "AC-2 hot path (plain Agent) emits NO stdout" "$out" ""
check "AC-2 hot path exits 0 even with harness-runs as a regular file" "$hrc" "0"

# AC-2 (DISCRIMINATING): a plain Agent dispatched DURING an active /drive run in the SAME
# repo (the real hot path, hit on every fan-out) must STILL take the hot path — exit 0
# BEFORE the run scan. The load-bearing proof is a CORRUPT run dir placed alongside the
# fresh active run: the hot path never scans, so NO stderr warning is emitted. If the
# hot-path early exit regressed, the scan WOULD run and warn about the corrupt dir on stderr
# (the CLASS guard keeps stdout silent, but the stderr side-effect leaks), so we assert
# stderr is ALSO empty. This RE-verifies the mechanism the file-not-a-dir case cannot: it
# reds under the line-97 (ISO_TYPE null → exit) mutation even WITH the CLASS defense-in-depth.
D2HOME="$WORK/ac2-home"; mkdir -p "$D2HOME/.claude/harness-runs"
D2REPO="$WORK/ac2-repo"; mk_repo "$D2REPO" "https://github.com/ac2org/ac2repo.git"
mkdir -p "$D2HOME/.claude/harness-runs/run-ac2"
printf '{"stage":"execute","repoRoot":"%s"}\n' "$D2REPO" > "$D2HOME/.claude/harness-runs/run-ac2/state.json"
printf '' > "$D2HOME/.claude/harness-runs/run-ac2/event-log.jsonl"
mkdir -p "$D2HOME/.claude/harness-runs/run-ac2-corrupt"
printf 'GARBAGE {{{ not json' > "$D2HOME/.claude/harness-runs/run-ac2-corrupt/state.json"
printf '' > "$D2HOME/.claude/harness-runs/run-ac2-corrupt/event-log.jsonl"
D2ERR="$WORK/ac2.err"
D2PAYLOAD="$(jq -c --arg c "$D2REPO" '.cwd=$c' "$FX/agent-plain.json")"
out="$(printf '%s' "$D2PAYLOAD" | HOME="$D2HOME" bash "$GATE" 2>"$D2ERR")"; d2rc=$?
check "AC-2 (discriminating) plain Agent in active same-repo run → NO stdout" "$out" ""
check "AC-2 (discriminating) exits 0" "$d2rc" "0"
check "AC-2 (discriminating) hot path took NO run scan (stderr empty; corrupt dir unscanned)" "$(cat "$D2ERR")" ""

# =====================================================================================
# AC-3 — live matching run: 8 MCP writes + agent-worktree + enter-worktree → deny;
#         each reason carries its verbatim retry path + the runId.
# =====================================================================================
# Linked worktree of the run repo for the worktree-class fixtures (repo-scoped by cwd).
LINKED="$WORK/linked-wt"; git -C "$RUNREPO" worktree add -q "$LINKED" -b wtbranch 2>/dev/null

ac3_mcp() { # ac3_mcp <fixture> <retry-literal>
  local out; out="$(run_gate "$FX/$1")"
  check "AC-3 $1 → deny" "$(is_deny "$out")" "yes"
  contains "AC-3 $1 names the run" "$out" "run run-primary is active"
  contains "AC-3 $1 retry path verbatim" "$out" "$2"
}
ac3_mcp create_or_update_file.json      "git merge slice/<runId>/<id>"
ac3_mcp delete_file.json                "git merge slice/<runId>/<id>"
ac3_mcp push_files.json                 "git push"
ac3_mcp create_branch.json              'git worktree add $RUN_DIR/wt/<id> -b slice/<runId>/<id>'
ac3_mcp create_pull_request.json        "gh pr create"
ac3_mcp merge_pull_request.json         "human-owned at Gate B"
ac3_mcp update_pull_request.json        "human-owned at Gate B"
ac3_mcp update_pull_request_branch.json "git push"

for wf in agent-worktree.json enter-worktree.json; do
  out="$(run_gate "$FX/$wf" "$LINKED")"
  check "AC-3 $wf → deny" "$(is_deny "$out")" "yes"
  contains "AC-3 $wf names the run" "$out" "run run-primary is active"
  contains "AC-3 $wf retry = gated worktree add" "$out" 'git worktree add $RUN_DIR/wt/<id> -b slice/<runId>/<id>'
done

# =====================================================================================
# AC-4 — settings matcher selects the 8 writes, rejects the reads/other-server; and the
#         hook's OWN table fail-closes on a force-piped read (settings/hook drift defense).
# =====================================================================================
MSET="$WORK/matcher-settings.json"
bash "$INSTALLER" "$MSET" >/dev/null 2>&1
MATCHER="$(jq -r '.hooks.PreToolUse[] | select((.hooks[]?.command // "")|endswith("/drive-tool-gate.sh")) | .matcher' "$MSET" | grep 'mcp__' | head -1)"
check "AC-4 mcp matcher present in installed settings" "$( [ -n "$MATCHER" ] && echo yes || echo no )" "yes"
sel() { printf '%s' "$1" | grep -Eq "$MATCHER" && echo yes || echo no; }
for t in create_or_update_file delete_file push_files create_branch create_pull_request merge_pull_request update_pull_request update_pull_request_branch; do
  check "AC-4 matcher SELECTS mcp__github__$t" "$(sel "mcp__github__$t")" "yes"
  check "AC-4 matcher SELECTS server-wildcard mcp__gh__$t" "$(sel "mcp__gh__$t")" "yes"
done
check "AC-4 matcher REJECTS list_pull_requests" "$(sel "mcp__github__list_pull_requests")" "no"
check "AC-4 matcher REJECTS get_file_contents"  "$(sel "mcp__github__get_file_contents")"  "no"
check "AC-4 matcher REJECTS other-server create_issue" "$(sel "mcp__linear__create_issue")" "no"
# longest-first: update_pull_request must not shadow update_pull_request_branch
check "AC-4 matcher SELECTS update_pull_request_branch (no shadow)" "$(sel "mcp__github__update_pull_request_branch")" "yes"
# Drift defense: force-pipe a read fixture straight into the hook → drift fail-closed deny.
out="$(run_gate "$FX/list_pull_requests.json")"
check "AC-4 force-piped read → drift deny" "$(is_deny "$out")" "yes"
contains "AC-4 drift deny names table drift" "$out" "absent from the hook's own tool table"

# =====================================================================================
# AC-5 — stage done / stale mtime → silent; refreshing state.json's mtime → deny.
# =====================================================================================
mk_run run-done "$RUNREPO" done
# (run-done is stage=done; run-primary is still active so a write would still deny —
#  isolate by using a SEPARATE repo/owner for the liveness runs.)
LREPO="$WORK/lrepo"; mk_repo "$LREPO" "https://github.com/live-owner/live-repo.git"
# remove run-primary temporarily is overkill; instead scope the liveness fixture to LREPO's owner
LIVE_JSON='{"tool_name":"mcp__github__push_files","tool_input":{"owner":"live-owner","repo":"live-repo"},"cwd":"/x"}'
rm -rf "$RUNS"/*   # clear all runs; test liveness in isolation
mk_run run-live "$LREPO"
touch -t 200001010000 "$RUNS/run-live/state.json" "$RUNS/run-live/event-log.jsonl"
out="$(run_gate "$LIVE_JSON")"
check "AC-5 stale mtime → silent" "$out" ""
touch "$RUNS/run-live/state.json"
out="$(run_gate "$LIVE_JSON")"
check "AC-5 refreshed mtime → deny" "$(is_deny "$out")" "yes"
# stage=done → silent even when fresh
printf '{"stage":"done","repoRoot":"%s"}\n' "$LREPO" > "$RUNS/run-live/state.json"
out="$(run_gate "$LIVE_JSON")"
check "AC-5 stage=done → silent" "$out" ""

# =====================================================================================
# AC-6 — one corrupt state.json → stderr warning + skip; a second live run still denies.
# =====================================================================================
rm -rf "$RUNS"/*
mk_run run-corrupt "$LREPO"; printf 'GARBAGE {{{ not json' > "$RUNS/run-corrupt/state.json"
mk_run run-healthy "$LREPO"
ERR="$WORK/ac6.err"
out="$(printf '%s' "$LIVE_JSON" | bash "$GATE" 2>"$ERR")"
check "AC-6 healthy run still denies past the corrupt one" "$(is_deny "$out")" "yes"
contains "AC-6 healthy deny names run-healthy" "$out" "run run-healthy is active"
contains "AC-6 stderr warns about the corrupt dir" "$(cat "$ERR")" "skipping unreadable/corrupt state.json"
contains "AC-6 stderr names the corrupt run dir" "$(cat "$ERR")" "run-corrupt"

# =====================================================================================
# AC-7 — repo scoping + origin-form matrix.
# =====================================================================================
rm -rf "$RUNS"/*
SRC="$WORK/scope-run"; mk_repo "$SRC" "https://github.com/owner/repo.git"
mk_run run-scope "$SRC"
MCP_OR='{"tool_name":"mcp__github__push_files","tool_input":{"owner":"owner","repo":"repo"},"cwd":"/x"}'

# (a) MCP owner/repo mismatch → silent
out="$(run_gate '{"tool_name":"mcp__github__push_files","tool_input":{"owner":"someone","repo":"else"},"cwd":"/x"}')"
check "AC-7 MCP owner/repo mismatch → silent" "$out" ""
# (b) MCP same owner/repo (case-diff) → deny
out="$(run_gate '{"tool_name":"mcp__github__push_files","tool_input":{"owner":"Owner","repo":"Repo"},"cwd":"/x"}')"
check "AC-7 MCP same owner/repo (case-insensitive) → deny" "$(is_deny "$out")" "yes"
# (c) worktree cwd in an UNRELATED repo → silent
UNREL="$WORK/unrel"; mk_repo "$UNREL" "https://github.com/x/y.git"
out="$(run_gate "$FX/agent-worktree.json" "$UNREL")"
check "AC-7 worktree cwd unrelated repo → silent" "$out" ""
# (d) linked worktree of the run repo → deny (common-dir fast-match; run side via --git-common-dir)
WT7="$WORK/wt7"; git -C "$SRC" worktree add -q "$WT7" -b wt7 2>/dev/null
out="$(run_gate "$FX/agent-worktree.json" "$WT7")"
check "AC-7 linked worktree of run repo → deny (common-dir)" "$(is_deny "$out")" "yes"
# (d2) run launched FROM a linked worktree (repoRoot is itself a worktree) → still deny
#      (comparator must be --git-common-dir, not realpath(repoRoot/.git)).
mk_run run-wtroot "$WT7"; rm -rf "$RUNS/run-scope"
out="$(run_gate "$FX/agent-worktree.json" "$SRC")"   # cwd = main clone; run repoRoot = worktree
check "AC-7 repoRoot=linked-worktree, cwd=main clone → deny (symmetric common-dir)" "$(is_deny "$out")" "yes"
rm -rf "$RUNS"/*; mk_run run-scope "$SRC"
# (e) second INDEPENDENT clone of the same GitHub repo, different transport forms → deny
#     scp-form clone
SCPC="$WORK/scpc"; mk_repo "$SCPC" "git@github.com:Owner/Repo.git"
out="$(run_gate "$FX/enter-worktree.json" "$SCPC")"
check "AC-7 scp-form clone of same repo → deny (origin identity)" "$(is_deny "$out")" "yes"
#     trailing-slash URL
TSC="$WORK/tsc"; mk_repo "$TSC" "https://github.com/owner/repo/"
out="$(run_gate "$FX/enter-worktree.json" "$TSC")"
check "AC-7 trailing-slash origin clone → deny" "$(is_deny "$out")" "yes"
#     port+userinfo URL form (locks the :port + userinfo strip)
PUC="$WORK/puc"; mk_repo "$PUC" "ssh://git@github.com:22/owner/repo"
out="$(run_gate "$FX/enter-worktree.json" "$PUC")"
check "AC-7 port+userinfo URL clone → deny (:port strip)" "$(is_deny "$out")" "yes"
#     genuinely DIFFERENT repo → pass
DIFF="$WORK/diff"; mk_repo "$DIFF" "https://github.com/owner/OTHER.git"
out="$(run_gate "$FX/enter-worktree.json" "$DIFF")"
check "AC-7 genuinely different repo → silent" "$out" ""
#     clone whose origin was REMOVED → silent (forgery-class residual)
NOORIG="$WORK/noorig"; mk_repo "$NOORIG"
out="$(run_gate "$FX/enter-worktree.json" "$NOORIG")"
check "AC-7 clone with no origin (worktree class) → silent (forgery-class residual)" "$out" ""
# (f) matched MCP write with UNEXTRACTABLE owner/repo while a run is live → deny (over-deny)
out="$(run_gate '{"tool_name":"mcp__github__push_files","tool_input":{"branch":"main"},"cwd":"/x"}')"
check "AC-7 MCP unextractable owner/repo (run live) → deny" "$(is_deny "$out")" "yes"
contains "AC-7 unextractable deny names the run + over-deny" "$out" "no extractable owner/repo"

# (g) NO-ORIGIN fallback: origin-less run whose repoRoot is a LINKED worktree; MCP repo ==
#     common-dir repo name (basename of RUN_COMMONDIR sans /.git), NOT basename(repoRoot).
rm -rf "$RUNS"/*
NOFO_MAIN="$WORK/nofo-main"; mk_repo "$NOFO_MAIN"   # no origin; clone dir name = nofo-main
NOFO_WT="$WORK/nofo-worktree"; git -C "$NOFO_MAIN" worktree add -q "$NOFO_WT" -b nofowt 2>/dev/null
mk_run run-nofo "$NOFO_WT"   # repoRoot = the worktree folder (basename nofo-worktree)
out="$(run_gate '{"tool_name":"mcp__github__push_files","tool_input":{"owner":"anyone","repo":"nofo-main"},"cwd":"/x"}')"
check "AC-7 no-origin fallback: repo==common-dir name → deny" "$(is_deny "$out")" "yes"
out="$(run_gate '{"tool_name":"mcp__github__push_files","tool_input":{"owner":"anyone","repo":"nofo-worktree"},"cwd":"/x"}')"
check "AC-7 no-origin fallback keys off RUN_COMMONDIR, NOT basename(repoRoot)" "$out" ""

# =====================================================================================
# AC-8 — jq-absent (restricted PATH) → static deny; empty stdin → deny.
# =====================================================================================
STUB="$WORK/stub-bin"; mkdir -p "$STUB"; ln -s "$(command -v cat)" "$STUB/cat"
out="$(printf '%s' "$(cat "$FX/push_files.json")" | PATH="$STUB" /bin/bash "$GATE" 2>/dev/null)"; jrc=$?
check "AC-8 jq-absent → deny" "$(is_deny "$out")" "yes"
check "AC-8 jq-absent → exit 0" "$jrc" "0"
contains "AC-8 jq-absent deny mentions jq" "$out" "jq is required"
out="$(printf '' | bash "$GATE" 2>/dev/null)"; erc=$?
check "AC-8 empty stdin → deny" "$(is_deny "$out")" "yes"
check "AC-8 empty stdin → exit 0" "$erc" "0"

# =====================================================================================
# REVIEW-FIX HARDENING — malformed-input fail-closed (codex BLOCKING/MAJOR + Claude P2s).
# =====================================================================================

# --- Fix #1: native-worktree fail-closed on malformed/missing cwd + non-string isolation.
rm -rf "$RUNS"/*
WCREPO="$WORK/wc-repo"; mk_repo "$WCREPO" "https://github.com/wc/wc.git"
mk_run run-wc "$WCREPO"
# (a) EnterWorktree with MISSING cwd (run live) → deny (fail-closed, not silent-pass)
out="$(run_gate '{"tool_name":"EnterWorktree","tool_input":{"name":"x"}}')"
check "Fix1 EnterWorktree missing cwd (run live) → deny" "$(is_deny "$out")" "yes"
contains "Fix1 missing-cwd deny is fail-closed" "$out" "cannot be resolved to a git repository"
# (b) Agent with a NON-STRING isolation (object) is MALFORMED → worktree class; an
#     unresolvable cwd then fail-closes → deny (pre-fix this took the hot path silently).
out="$(run_gate '{"tool_name":"Agent","tool_input":{"isolation":{},"description":"d","prompt":"p"},"cwd":"/no/such/git/dir"}')"
check "Fix1 Agent non-string isolation (object) + unresolvable cwd → deny" "$(is_deny "$out")" "yes"
# (c) non-string isolation but a cwd that IS the run repo → deny (worktree-class match)
out="$(run_gate '{"tool_name":"Agent","tool_input":{"isolation":[],"description":"d","prompt":"p"}}' "$WCREPO")"
check "Fix1 non-string isolation (array) + run-repo cwd → deny" "$(is_deny "$out")" "yes"
# (d) non-string isolation with a RESOLVABLE non-run-repo cwd → silent (identifiable, differs)
WCOTHER="$WORK/wc-other"; mk_repo "$WCOTHER" "https://github.com/other/other.git"
out="$(run_gate '{"tool_name":"Agent","tool_input":{"isolation":true,"description":"d","prompt":"p"}}' "$WCOTHER")"
check "Fix1 non-string isolation + resolvable non-run-repo cwd → silent (legit Edge-case-9)" "$out" ""
# (e) a CLEAN non-"worktree" isolation string → hot path (NOT worktree class), even in-repo
out="$(run_gate '{"tool_name":"Agent","tool_input":{"isolation":"none","description":"d","prompt":"p"}}' "$WCREPO")"
check "Fix1 clean non-worktree isolation string ('none') → hot path silent" "$out" ""
# (f) trailing-whitespace 'worktree ' string → trimmed → worktree class → deny (run-repo cwd)
out="$(run_gate '{"tool_name":"Agent","tool_input":{"isolation":"worktree ","description":"d","prompt":"p"}}' "$WCREPO")"
check "Fix1 isolation 'worktree ' (trailing ws) trimmed → deny (run-repo cwd)" "$(is_deny "$out")" "yes"

# --- Fix #2: MCP fail-closed catches MALFORMED (non-string) owner/repo, not just EMPTY.
rm -rf "$RUNS"/*
MREPO="$WORK/m-repo"; mk_repo "$MREPO" "https://github.com/m/m.git"
mk_run run-malf "$MREPO"
for bad in '{}' '[]' 'true' 'null' '123'; do
  out="$(run_gate "{\"tool_name\":\"mcp__github__push_files\",\"tool_input\":{\"owner\":$bad,\"repo\":$bad},\"cwd\":\"/x\"}")"
  check "Fix2 non-string owner/repo ($bad) → deny (unextractable)" "$(is_deny "$out")" "yes"
done
out="$(run_gate '{"tool_name":"mcp__github__push_files","tool_input":{"owner":{},"repo":"m"},"cwd":"/x"}')"
check "Fix2 object owner + valid repo → deny" "$(is_deny "$out")" "yes"
contains "Fix2 malformed-owner deny is the unextractable branch" "$out" "no extractable owner/repo"
out="$(run_gate '{"tool_name":"mcp__github__push_files","tool_input":{"owner":"m","repo":[]},"cwd":"/x"}')"
check "Fix2 valid owner + array repo → deny" "$(is_deny "$out")" "yes"
# control: a genuinely different (well-formed) owner/repo still silent-passes (no over-deny)
out="$(run_gate '{"tool_name":"mcp__github__push_files","tool_input":{"owner":"someone","repo":"else"},"cwd":"/x"}')"
check "Fix2 well-formed non-matching owner/repo → silent (no over-deny)" "$out" ""

# --- Fix #5: active run with stage!=done but EMPTY/absent repoRoot → skip-with-warning;
#            never `git -C ""` mis-attribution to the hook's own cwd.
rm -rf "$RUNS"/*
mkdir -p "$RUNS/run-noroot"; printf '{"stage":"execute"}\n' > "$RUNS/run-noroot/state.json"; printf '' > "$RUNS/run-noroot/event-log.jsonl"
MISREPO="$WORK/mis-repo"; mk_repo "$MISREPO" "https://github.com/attacker/target.git"
NRERR="$WORK/noroot.err"
# Run the gate FROM INSIDE mis-repo (hook cwd = attacker/target) + an MCP write to
# attacker/target. Pre-fix `git -C ""` resolved to the hook cwd → mis-attributed match → deny.
out="$(cd "$MISREPO" && printf '%s' '{"tool_name":"mcp__github__push_files","tool_input":{"owner":"attacker","repo":"target"},"cwd":"/x"}' | HOME="$HOME" bash "$GATE" 2>"$NRERR")"
check "Fix5 no-repoRoot run does NOT mis-attribute to hook cwd (no over-deny)" "$out" ""
contains "Fix5 no-repoRoot run skipped-with-warning naming it" "$(cat "$NRERR")" "run-noroot"
contains "Fix5 warning is the no-repoRoot branch" "$(cat "$NRERR")" "no repoRoot"
# a HEALTHY run alongside the no-repoRoot one still denies (skip is per-dir, not machine-wide)
mk_run run-healthy3 "$MISREPO"
out="$(run_gate '{"tool_name":"mcp__github__push_files","tool_input":{"owner":"attacker","repo":"target"},"cwd":"/x"}')"
check "Fix5 healthy run past the no-repoRoot one still denies" "$(is_deny "$out")" "yes"

# --- Fix #6: git absent from PATH (jq present) + matched write + active run → fail-closed.
rm -rf "$RUNS"/*
GABSREPO="$WORK/gabs-repo"; mk_repo "$GABSREPO" "https://github.com/g/g.git"
mk_run run-gabs "$GABSREPO"
GSTUB="$WORK/git-absent-bin"; mkdir -p "$GSTUB"
for b in cat jq find dirname sort basename tr; do ln -sf "$(command -v "$b")" "$GSTUB/$b"; done
out="$(printf '%s' "$(cat "$FX/push_files.json")" | PATH="$GSTUB" HOME="$HOME" /bin/bash "$GATE" 2>/dev/null)"; grc=$?
check "Fix6 git-absent + matched write + active run → deny (fail-closed)" "$(is_deny "$out")" "yes"
check "Fix6 git-absent → exit 0" "$grc" "0"
contains "Fix6 git-absent deny mentions git not found" "$out" "git was not found"

# =====================================================================================
# AC-15 — every fixture carries _provenance (source + url + retrieved); README records D9.
# =====================================================================================
prov_bad=0
for f in "$FX"/*.json; do
  jq -e '._provenance.source and ._provenance.url and ._provenance.retrieved' "$f" >/dev/null 2>&1 || prov_bad=1
done
check "AC-15 every fixture carries _provenance{source,url,retrieved}" "$prov_bad" "0"
check "AC-15 fixtures README exists" "$( [ -f "$FX/README.md" ] && echo yes || echo no )" "yes"
contains "AC-15 README records the D9 schema-derived rule" "$(cat "$FX/README.md")" "Schema-derived, NOT live-captured"

# --- Summary -------------------------------------------------------------------------
echo "----------------------------------------"
echo "PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -eq 0 ] || exit 1
