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
  local suffix="${1%.json}"
  check "AC-3 $1 → deny" "$(is_deny "$out")" "yes"
  contains "AC-3 $1 names the run" "$out" "run run-primary is active"
  contains "AC-3 $1 retry path verbatim" "$out" "$2"
  # Pin the DISTINCT per-tool reason so a within-pair branch swap in mcp_deny_reason is
  # caught even where two tools share a retry-path substring (create_or_update_file/delete_file
  # both 'git merge slice/…'; push_files/update_pull_request_branch both 'git push';
  # merge_pull_request/update_pull_request both 'human-owned at Gate B'). Each reason names its
  # own tool verbatim as 'MCP tool <suffix>' — unique within every pair.
  contains "AC-3 $1 reason names its own tool (distinct within same-retry pair)" "$out" "MCP tool $suffix"
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
  case "$wf" in agent-worktree.json) wtn=Agent ;; enter-worktree.json) wtn=EnterWorktree ;; esac
  check "AC-3 $wf → deny" "$(is_deny "$out")" "yes"
  contains "AC-3 $wf names the run" "$out" "run run-primary is active"
  contains "AC-3 $wf retry = gated worktree add" "$out" 'git worktree add $RUN_DIR/wt/<id> -b slice/<runId>/<id>'
  # both worktree fixtures share the SAME retry path; pin the distinct tool name so a swap
  # of the tool token in worktree_deny_reason is caught.
  contains "AC-3 $wf reason names its own tool ($wtn)" "$out" "native worktree tool $wtn"
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

# AC-5 (liveness OR-branch): the find is `\( -name state.json -o -name event-log.jsonl \)`.
# The state.json side is exercised above; this isolates the event-log.jsonl side. A run whose
# state.json is STALE but whose event-log.jsonl is FRESH must STILL be ACTIVE → deny. This is
# the LOAD-BEARING branch mid-run: a live /drive run appends to event-log.jsonl constantly but
# rewrites state.json far less often, so event-log freshness is what keeps the gate armed.
# MUTATION-VERIFY: dropping `-o -name event-log.jsonl` from the find REDs this (the dir would
# not be a candidate → no active run → silent pass).
rm -rf "$RUNS"/*
mk_run run-evlog "$LREPO"
touch -t 200001010000 "$RUNS/run-evlog/state.json"   # state.json STALE (year 2000)
touch "$RUNS/run-evlog/event-log.jsonl"              # event-log.jsonl FRESH (now)
out="$(run_gate "$LIVE_JSON")"
check "AC-5 stale state.json + FRESH event-log.jsonl → active → deny (OR-branch)" "$(is_deny "$out")" "yes"
# control: BOTH stale → dormant → silent (proves the deny above came from the event-log side)
touch -t 200001010000 "$RUNS/run-evlog/event-log.jsonl"
out="$(run_gate "$LIVE_JSON")"
check "AC-5 both files stale → silent (OR-branch control)" "$out" ""

# AC-5 (DRIVE_TOOL_GATE_LIVE_HOURS knob): the liveness window is env-tunable, with an
# invalid-value / zero fallback to 24 (bin/drive-tool-gate.sh:154-156). Every other test uses
# the DEFAULT 24h, so a hardcoded-24 regression OR a broken fallback would pass unnoticed. Prove
# the knob MOVES the window boundary + the fallback guards hold. (run_gate can't set env, so
# these pipe the payload with the env var inline.)
rm -rf "$RUNS"/*
mk_run run-knob "$LREPO"
touch -t 200001010000 "$RUNS/run-knob/state.json" "$RUNS/run-knob/event-log.jsonl"  # ~26y old
# default 24h → the old run is stale → silent (baseline)
out="$(run_gate "$LIVE_JSON")"
check "knob default 24h: 2000-dated run is stale → silent" "$out" ""
# a HUGE window keeps the SAME old run ACTIVE → deny (proves the knob WIDENS the window)
out="$(printf '%s' "$LIVE_JSON" | DRIVE_TOOL_GATE_LIVE_HOURS=9999999 bash "$GATE" 2>/dev/null)"
check "knob=9999999 widens window: 2000-dated run active → deny" "$(is_deny "$out")" "yes"
# invalid value → falls back to 24 (NOT infinite): the old run stays stale → silent
out="$(printf '%s' "$LIVE_JSON" | DRIVE_TOOL_GATE_LIVE_HOURS=abc bash "$GATE" 2>/dev/null)"
check "knob=abc invalid → fallback 24h: old run still stale → silent" "$out" ""
# fallback still ARMS on a FRESH run (proves fallback = 24, gate NOT disabled)
touch "$RUNS/run-knob/state.json"
out="$(printf '%s' "$LIVE_JSON" | DRIVE_TOOL_GATE_LIVE_HOURS=abc bash "$GATE" 2>/dev/null)"
check "knob=abc invalid → fallback 24h: fresh run denies" "$(is_deny "$out")" "yes"
# zero → the `-gt 0` guard falls back to 24 (does NOT disable the gate): fresh run denies
out="$(printf '%s' "$LIVE_JSON" | DRIVE_TOOL_GATE_LIVE_HOURS=0 bash "$GATE" 2>/dev/null)"
check "knob=0 → -gt 0 guard falls back to 24: fresh run denies" "$(is_deny "$out")" "yes"

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

# (h) UPPERCASE `.GIT`/`.Git` suffix canonicalization (MAJOR bypass fix): a run whose origin
#     ends `.GIT`/`.Git` MUST key IDENTICALLY to a `.git` (lowercase) clone — so a same-repo
#     MCP write AND a second-clone worktree using the `.git` form BOTH DENY. MUTATION-VERIFY:
#     reverting the parse_origin reorder (strip `.git` case-sensitively BEFORE lowercasing)
#     leaves `.GIT` → `repo.git` ≠ `repo` → these RED.
rm -rf "$RUNS"/*
UPREPO="$WORK/up-run"; mk_repo "$UPREPO" "https://github.com/Owner/Repo.GIT"
mk_run run-upper "$UPREPO"
#   MCP write using the plain lowercase, no-suffix owner/repo form → deny
out="$(run_gate '{"tool_name":"mcp__github__push_files","tool_input":{"owner":"owner","repo":"repo"},"cwd":"/x"}')"
check "AC-7 .GIT-suffix run vs .git-form MCP write → deny (case-insensitive .git strip)" "$(is_deny "$out")" "yes"
#   second INDEPENDENT clone at the lowercase `.git` form → worktree-class origin-identity deny
GITLC="$WORK/gitlc"; mk_repo "$GITLC" "git@github.com:owner/repo.git"
out="$(run_gate "$FX/enter-worktree.json" "$GITLC")"
check "AC-7 .GIT-suffix run vs .git second clone (worktree) → deny (origin identity)" "$(is_deny "$out")" "yes"
#   mixed-case `.Git` suffix keys the same too
rm -rf "$RUNS"/*
MIXREPO="$WORK/mix-run"; mk_repo "$MIXREPO" "https://github.com/owner/repo.Git"
mk_run run-mix "$MIXREPO"
out="$(run_gate '{"tool_name":"mcp__github__push_files","tool_input":{"owner":"owner","repo":"repo"},"cwd":"/x"}')"
check "AC-7 .Git-suffix run vs .git-form MCP write → deny" "$(is_deny "$out")" "yes"

# (i) WHITESPACE-padded identifiers must NOT slip (MINOR fail-closed): a padded owner / repo /
#     cwd is semantically the SAME repo → trim → match → deny (never a silent-pass bypass).
rm -rf "$RUNS"/*
WSREPO="$WORK/ws-run"; mk_repo "$WSREPO" "https://github.com/wsowner/wsrepo.git"
mk_run run-ws "$WSREPO"
#   MCP owner with a TRAILING space to the active repo → deny (trimmed match)
out="$(run_gate '{"tool_name":"mcp__github__push_files","tool_input":{"owner":"wsowner ","repo":"wsrepo"},"cwd":"/x"}')"
check "AC-7 MCP owner trailing-space → deny (trimmed match)" "$(is_deny "$out")" "yes"
#   MCP repo with a LEADING space → deny (trimmed match)
out="$(run_gate '{"tool_name":"mcp__github__push_files","tool_input":{"owner":"wsowner","repo":" wsrepo"},"cwd":"/x"}')"
check "AC-7 MCP repo leading-space → deny (trimmed match)" "$(is_deny "$out")" "yes"
#   worktree cwd with a TRAILING space resolving to the run repo → deny (trimmed → resolves)
WSWT="$WORK/ws-wt"; git -C "$WSREPO" worktree add -q "$WSWT" -b wswt 2>/dev/null
out="$(run_gate "$FX/enter-worktree.json" "$WSWT ")"
check "AC-7 worktree cwd trailing-space → deny (trimmed → common-dir match)" "$(is_deny "$out")" "yes"
#   control: a padded but genuinely DIFFERENT owner still silent-passes (trim doesn't over-match)
out="$(run_gate '{"tool_name":"mcp__github__push_files","tool_input":{"owner":"someone ","repo":"else"},"cwd":"/x"}')"
check "AC-7 padded DIFFERENT owner/repo → silent (no over-deny)" "$out" ""

# (j) THOROUGH origin-form combinatorial sweep (the 2nd origin-norm finding: a single-slash
#     strip let `owner/repo.git//` keep an unstrippable `.git` → repo derived empty → same-repo
#     silent fail-OPEN; the restructure closes the WHOLE space at once). Sweep the SAME repo over
#       {scp, https, ssh://} × {no-suffix, .git, .Git, .GIT} × {0, 1, 2 trailing slashes} = 36
#     forms, using MIXED-CASE Owner/Repo so case-insensitivity is folded into EVERY cell:
#       - worktree class: a SECOND clone whose origin is ANY of the 36 forms → origin-identity
#         DENY against a fixed canonical run (form-independence on the cwd side).
#       - MCP class: an active run whose origin is ANY of the 36 forms → a plain lowercase
#         owner/repo write DENIES (form-independence on the run side — the run-side parse).
#     Explicitly includes the codex-reproduced `Repo.git//` double-slash cases. MUTATION-VERIFY
#     (manual, per implement notes): reverting parse_origin to a single-slash strip REDs every
#     `//` cell here — confirmed RED, then restored.
FORM_TRANSPORTS="git@github.com: https://github.com/ ssh://git@github.com/"

# -- worktree-class form-independence: fixed canonical run, second clone in each of 36 forms --
rm -rf "$RUNS"/*
FM_RUN="$WORK/fm-run"; mk_repo "$FM_RUN" "https://github.com/owner/repo.git"
mk_run run-fm "$FM_RUN"
fm_i=0; fm_deny_all=yes
for t in $FORM_TRANSPORTS; do
  for suf in "" .git .Git .GIT; do
    for sl in "" / //; do
      url="$t"Owner/Repo"$suf""$sl"
      fm_i=$((fm_i+1))
      clone="$WORK/fm-wt-$fm_i"; mk_repo "$clone" "$url"
      out="$(run_gate "$FX/enter-worktree.json" "$clone")"
      if [ "$(is_deny "$out")" != yes ]; then
        echo "  form-independence WORKTREE MISS: origin='$url' did NOT deny"; fm_deny_all=no
      fi
    done
  done
done
check "AC-7(j) worktree origin-form sweep (36 forms of same repo) → ALL deny" "$fm_deny_all" "yes"
check "AC-7(j) worktree sweep covered 36 forms" "$fm_i" "36"

# -- explicit codex-reproduced double-slash cases (named so a regression is unmissable) --
dbl_n=0
for u in "https://github.com/Owner/Repo.git//" "git@github.com:Owner/Repo.git//"; do
  dbl_n=$((dbl_n+1)); clone="$WORK/fm-dbl-$dbl_n"; mk_repo "$clone" "$u"
  out="$(run_gate "$FX/enter-worktree.json" "$clone")"
  check "AC-7(j) reproduced double-slash origin '$u' → deny" "$(is_deny "$out")" "yes"
done

# -- MCP-class form-independence: run origin in each of 36 forms, plain owner/repo write --
FM_MCP='{"tool_name":"mcp__github__push_files","tool_input":{"owner":"owner","repo":"repo"},"cwd":"/x"}'
fm_j=0; fm_mcp_all=yes
for t in $FORM_TRANSPORTS; do
  for suf in "" .git .Git .GIT; do
    for sl in "" / //; do
      url="$t"Owner/Repo"$suf""$sl"
      fm_j=$((fm_j+1))
      rm -rf "$RUNS"/*
      rr="$WORK/fm-run-$fm_j"; mk_repo "$rr" "$url"; mk_run "run-fm-$fm_j" "$rr"
      out="$(run_gate "$FM_MCP")"
      if [ "$(is_deny "$out")" != yes ]; then
        echo "  form-independence MCP MISS: run origin='$url' did NOT deny owner/repo write"; fm_mcp_all=no
      fi
    done
  done
done
check "AC-7(j) MCP origin-form sweep (run origin in 36 forms) → ALL deny owner/repo write" "$fm_mcp_all" "yes"
check "AC-7(j) MCP sweep covered 36 forms" "$fm_j" "36"

# -- DIFFERENT-repo control across the axes: a genuinely different repo → silent (no over-deny) --
rm -rf "$RUNS"/*
mk_repo "$WORK/fm-diffrun" "https://github.com/owner/repo.git"; mk_run run-fmdiff "$WORK/fm-diffrun"
fm_diff_silent=yes; dc_n=0
for du in "git@github.com:owner/different.git//" "https://github.com/owner/different.git/" \
          "ssh://git@github.com/other/repo.GIT" "https://github.com/owner/repo-x.git//" \
          "git@github.com:owner/repo2//"; do
  dc_n=$((dc_n+1)); dc="$WORK/fm-diff-$dc_n"; mk_repo "$dc" "$du"
  out="$(run_gate "$FX/enter-worktree.json" "$dc")"
  [ -z "$out" ] || { echo "  DIFFERENT-repo OVER-DENY: origin='$du' denied"; fm_diff_silent=no; }
done
check "AC-7(j) different-repo forms across the axes → silent (no over-deny)" "$fm_diff_silent" "yes"

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

# --- Fix #1 (round-2 NARROWED): native-worktree fail-closed ONLY on a missing/non-string/
#     empty cwd FIELD. A PRESENT non-empty cwd string that resolves to no active run silent-
#     passes (Edge-case-9) — including a valid EXISTING NON-git-repo directory. Round-1
#     over-denied that non-git-repo case; this restores its pass while keeping the
#     malformed-payload cases fail-closed.
rm -rf "$RUNS"/*
WCREPO="$WORK/wc-repo"; mk_repo "$WCREPO" "https://github.com/wc/wc.git"
mk_run run-wc "$WCREPO"
NONGIT="$WORK/wc-nongit"; mkdir -p "$NONGIT"   # an EXISTING, NON-git-repo directory
# (a) EnterWorktree with the cwd FIELD MISSING (run live) → deny (fail-closed, not silent-pass)
out="$(run_gate '{"tool_name":"EnterWorktree","tool_input":{"name":"x"}}')"
check "Fix1 EnterWorktree missing cwd (run live) → deny" "$(is_deny "$out")" "yes"
contains "Fix1 missing-cwd deny is fail-closed" "$out" "WITHOUT a usable cwd"
# (a2) NON-STRING cwd field (object) → PAYLOAD_CWD extracts to "" (unusable) → deny (fail-closed)
out="$(run_gate '{"tool_name":"Agent","tool_input":{"isolation":"worktree","description":"d","prompt":"p"},"cwd":{}}')"
check "Fix1 non-string cwd field (object) → deny (fail-closed)" "$(is_deny "$out")" "yes"
# (b) NEW (round-2, the codex-reproduced over-deny): legit Agent isolation:"worktree" with cwd
#     = an EXISTING NON-git-repo dir during an active same-repo run → SILENT PASS (Edge-9).
#     MUTATION-VERIFY: reverting the fix (fail-close when the cwd resolves to no git repo) REDs
#     this — a non-git dir yields NO origin key AND NO common dir, so the round-1 code denied it.
out="$(run_gate '{"tool_name":"Agent","tool_input":{"isolation":"worktree","description":"d","prompt":"p"}}' "$NONGIT")"
check "Fix1 (round-2) Agent isolation:worktree + existing NON-git-repo cwd → silent (Edge-9)" "$out" ""
# (b2) NEW (round-2): same restoration for EnterWorktree + existing NON-git-repo cwd → SILENT PASS
out="$(run_gate '{"tool_name":"EnterWorktree","tool_input":{"name":"x"}}' "$NONGIT")"
check "Fix1 (round-2) EnterWorktree + existing NON-git-repo cwd → silent (Edge-9)" "$out" ""
# (c) Agent NON-STRING isolation (object) is MALFORMED → worktree class; cwd that IS the run
#     repo → deny (worktree-class match; pre-fix a tostring compare took the hot path silently)
out="$(run_gate '{"tool_name":"Agent","tool_input":{"isolation":{},"description":"d","prompt":"p"}}' "$WCREPO")"
check "Fix1 non-string isolation (object) + run-repo cwd → deny (worktree-class routing)" "$(is_deny "$out")" "yes"
# (d) non-string isolation (array) + a cwd that IS the run repo → deny (worktree-class match)
out="$(run_gate '{"tool_name":"Agent","tool_input":{"isolation":[],"description":"d","prompt":"p"}}' "$WCREPO")"
check "Fix1 non-string isolation (array) + run-repo cwd → deny" "$(is_deny "$out")" "yes"
# (e) non-string isolation with a RESOLVABLE UNRELATED-git-repo cwd → silent (identifiable, differs)
WCOTHER="$WORK/wc-other"; mk_repo "$WCOTHER" "https://github.com/other/other.git"
out="$(run_gate '{"tool_name":"Agent","tool_input":{"isolation":true,"description":"d","prompt":"p"}}' "$WCOTHER")"
check "Fix1 non-string isolation + unrelated-git-repo cwd → silent (legit Edge-case-9)" "$out" ""
# (f) a CLEAN non-"worktree" isolation string → hot path (NOT worktree class), even in-repo
out="$(run_gate '{"tool_name":"Agent","tool_input":{"isolation":"none","description":"d","prompt":"p"}}' "$WCREPO")"
check "Fix1 clean non-worktree isolation string ('none') → hot path silent" "$out" ""
# (g) trailing-whitespace 'worktree ' string → trimmed → worktree class → deny (run-repo cwd)
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

# --- Fix (harden): a NON-STRING tool_name is MALFORMED input → fail-CLOSED (same class as the
#     owner/repo/cwd/isolation malformed-input fixes). Pre-fix `{"tool_name":{}}` tostring'd to
#     "{}", matched NO class, and SILENT fail-OPENed while a run was live; now tool_name is a
#     STRING SCALAR (`s`) → a non-string yields "" → the empty/non-string tool_name deny.
#     Defense-in-depth (the settings matcher regex-matches the tool_name STRING, so a non-string
#     tool_name is also unreachable via the real platform), uniform with D-p2-5. run-malf (m/m)
#     is still live here. MUTATION-VERIFY: reverting tool_name to the tostring extraction REDs
#     these (they silent-pass).
for bad in '{}' '[]' 'true' '123'; do
  out="$(run_gate "{\"tool_name\":$bad,\"tool_input\":{\"owner\":\"m\",\"repo\":\"m\"},\"cwd\":\"/x\"}")"
  check "FixTN non-string tool_name ($bad, run live) → deny (fail-closed)" "$(is_deny "$out")" "yes"
  contains "FixTN non-string tool_name ($bad) is the unparseable branch" "$out" "empty or non-string tool_name"
done
# control: a well-formed STRING but non-write / mis-registered tool → silent pass (no over-deny)
out="$(run_gate '{"tool_name":"Task","tool_input":{},"cwd":"/x"}')"
check "FixTN well-formed non-write string tool (Task) → silent (no over-deny)" "$out" ""

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
