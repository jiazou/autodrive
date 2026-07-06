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
# chmod -R before rm so a deliberately 000'd dir (blind-root test) is still removable.
trap 'chmod -R u+rwx "$HOME" "$WORK" 2>/dev/null; rm -rf "$HOME" "$WORK"' EXIT

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
for b in cat git dirname find sort; do ln -sf "$(command -v "$b")" "$STUB/$b"; done   # deliberately NO jq
ERR2="$WORK/a2.err"
out="$(payload_for "$REPO" wt-nojq | PATH="$STUB" /bin/bash "$GATE" 2>"$ERR2")"; rc=$?
check "AC-8(a2) jq absent → exit 2 (fail-closed DENY, even with no active run)" "$rc" "2"
check "AC-8(a2) jq absent → NO stdout path" "$out" ""
contains "AC-8(a2) jq-absent stderr names the missing tool" "$(cat "$ERR2")" "not found in PATH: jq"

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
# REVIEW-FIX (round 1) — codex adversarial fail-open/wedge repros, now regression-guarded.
# =====================================================================================

# Fix 1 (BLOCKING fail-open): drive_scan_active_runs suppresses its find/sort/dirname/jq pipeline
# errors, so a MISSING scan binary yielded an EMPTY scan → the gate concluded "no active run" and
# PROVISIONED even while a run WAS active. The required-tool pre-check now FAILS CLOSED (exit 2)
# when any of jq/find/sort/dirname/git is absent. Drive it with an active run + a PATH that omits
# each required tool in turn → must DENY (exit 2) and create NO worktree.
rm -rf "$RUNS"/*
FIXREPO="$WORK/fix-repo"; mk_repo "$FIXREPO"
mk_run run-fix "$FIXREPO"
FULLBIN="$WORK/fullbin"; mkdir -p "$FULLBIN"
for b in bash cat jq git dirname sed basename sort find; do ln -sf "$(command -v "$b")" "$FULLBIN/$b"; done
for miss in find sort dirname jq git; do
  STUBM="$WORK/stub-no-$miss"; mkdir -p "$STUBM"
  for b in bash cat jq git dirname sed basename sort find; do [ "$b" = "$miss" ] || ln -sf "$(command -v "$b")" "$STUBM/$b"; done
  out="$(payload_for "$FIXREPO" "slip-$miss" | PATH="$STUBM" HOME="$HOME" /bin/bash "$GATE" 2>/dev/null)"; rc=$?
  check "Fix1 active run + '$miss' absent → exit 2 (fail-closed DENY, no fail-open)" "$rc" "2"
  check "Fix1 active run + '$miss' absent → NO stdout path" "$out" ""
  check "Fix1 active run + '$miss' absent → NO worktree created" "$(git -C "$FIXREPO" worktree list | grep -c "slip-$miss")" "0"
done
# control: with the FULL toolset + active run → still denies (exit 2), proving the tests above
# aren't passing merely because the payload was malformed.
out="$(payload_for "$FIXREPO" "slip-full" | PATH="$FULLBIN" HOME="$HOME" /bin/bash "$GATE" 2>/dev/null)"; rc=$?
check "Fix1 control: full toolset + active run → still exit 2 DENY" "$rc" "2"

# Fix 1b (r2 BLOCKING blind-root fail-open): if RUNS_ROOT EXISTS but is unreadable/unsearchable
# (`chmod 000`), `find "$RUNS_ROOT"` enumerates NOTHING → an EMPTY scan → the gate would conclude
# "no active run" and provision even with a run active (codex repro). The blind-root pre-check
# now FAILS CLOSED (exit 2). Active run present + RUNS_ROOT chmod 000 → DENY, no worktree.
chmod 000 "$RUNS"
brerr="$WORK/blindroot.err"
out="$(payload_for "$FIXREPO" "blindslip" | HOME="$HOME" /bin/bash "$GATE" 2>"$brerr")"; rc=$?
chmod 755 "$RUNS"   # restore immediately so the rest of the suite + trap can read it
check "Fix1b active run + RUNS_ROOT chmod 000 (blind scan) → exit 2 (fail-closed, no fail-open)" "$rc" "2"
check "Fix1b blind-root → NO stdout path" "$out" ""
check "Fix1b blind-root → NO worktree created" "$(git -C "$FIXREPO" worktree list | grep -c blindslip)" "0"
contains "Fix1b blind-root stderr names the blind scan" "$(cat "$brerr")" "not readable+searchable"
# surgical: a single unreadable SUBDIR must NOT deny (find still enumerates the rest of the root).
# Idle (no active run) + an unreadable subdir alongside → still provisions.
rm -rf "$RUNS"/*
mkdir -p "$RUNS/hidden"; chmod 000 "$RUNS/hidden"
SUBREPO="$WORK/sub-repo"; mk_repo "$SUBREPO"
out="$(payload_for "$SUBREPO" "subdir-ok" | HOME="$HOME" /bin/bash "$GATE" 2>/dev/null)"; rc=$?
chmod 755 "$RUNS/hidden"
check "Fix1b surgical: unreadable SUBDIR (idle) does NOT deny (root still scannable)" "$rc" "0"
check "Fix1b surgical: idle path still provisions a real worktree past the unreadable subdir" "$( [ -n "$out" ] && git -C "$out" rev-parse --is-inside-work-tree 2>/dev/null || echo no )" "true"
[ -n "$out" ] && { git -C "$SUBREPO" worktree remove --force "$out" 2>/dev/null; git -C "$SUBREPO" worktree prune 2>/dev/null; }
# ABSENT root is NOT a blind scan → allow/provision (genuinely no runs on this machine).
ABSHOME="$WORK/abs-home"; mkdir -p "$ABSHOME/.claude"   # deliberately NO harness-runs
ABSREPO="$WORK/abs-repo"; mk_repo "$ABSREPO"
out="$(payload_for "$ABSREPO" "absent-ok" | HOME="$ABSHOME" /bin/bash "$GATE" 2>/dev/null)"; rc=$?
check "Fix1b absent RUNS_ROOT (no runs dir) → allow/provision (exit 0), NOT a blind deny" "$rc" "0"
check "Fix1b absent-root path IS a real worktree" "$( [ -n "$out" ] && git -C "$out" rev-parse --is-inside-work-tree 2>/dev/null || echo no )" "true"

# Fix 2 (MAJOR wedge): the idle allow path used `|| true`, echoing a BOGUS success path even when
# `git worktree add` FAILED (collision / bad cwd) → Claude Code believed a worktree existed where
# none did = wedge. Now: never echo a path unless the worktree was ACTUALLY created; validate the
# name; fail non-zero (non-2) on a genuine provisioning error.
rm -rf "$RUNS"/*   # idle (no active run)
COLREPO="$WORK/col-repo"; mk_repo "$COLREPO"
# (a) collide with a NON-EMPTY existing dir at the derived path → git worktree add fails
mkdir -p "$WORK/collide-dir"; printf 'x' > "$WORK/collide-dir/f"
ce="$WORK/col-a.err"
out="$(payload_for "$COLREPO" "collide-dir" | bash "$GATE" 2>"$ce")"; rc=$?
check "Fix2 idle + non-empty-dir collision → non-zero (not exit 0)" "$( [ "$rc" -ne 0 ] && echo nonzero || echo zero )" "nonzero"
check "Fix2 idle + non-empty-dir collision → NOT the exit-2 policy DENY (a provisioning error)" "$rc" "1"
check "Fix2 idle + non-empty-dir collision → NO bogus success path echoed" "$out" ""
contains "Fix2 collision stderr carries the real git failure" "$(cat "$ce")" "failed to provision"
# and the colliding path is NOT a git worktree (nothing was actually created)
check "Fix2 collision: derived path is NOT a worktree" "$(git -C "$WORK/collide-dir" rev-parse --is-inside-work-tree 2>/dev/null || echo no)" "no"
# (b) collide with an existing FILE at the derived path
printf 'file' > "$WORK/collide-file"
out="$(payload_for "$COLREPO" "collide-file" | bash "$GATE" 2>/dev/null)"; rc=$?
check "Fix2 idle + file collision → non-zero" "$( [ "$rc" -ne 0 ] && echo nonzero || echo zero )" "nonzero"
check "Fix2 idle + file collision → NO path echoed" "$out" ""
# (c) unsafe names → refused (exit 1, no path), never a bogus success
for badname in "../../evil" "a/b" "-rf" "with space" 'na$me' ".."; do
  out="$(payload_for "$COLREPO" "$badname" | bash "$GATE" 2>/dev/null)"; rc=$?
  check "Fix2 unsafe name [$badname] → exit 1" "$rc" "1"
  check "Fix2 unsafe name [$badname] → NO path echoed" "$out" ""
done
# (d) cwd missing / not a directory → refuse (exit 1), no bogus path
out="$(printf '{"hook_event_name":"WorktreeCreate","name":"nocwd"}' | bash "$GATE" 2>/dev/null)"; rc=$?
check "Fix2 idle + missing cwd → exit 1 (no bogus path)" "$rc" "1"
check "Fix2 idle + missing cwd → NO path echoed" "$out" ""
# (e) control: idle + valid name + real repo cwd → provisions a REAL worktree (exit 0, path)
out="$(payload_for "$COLREPO" "good-wt" | bash "$GATE" 2>/dev/null)"; rc=$?
check "Fix2 control: idle + valid name → exit 0 + real worktree (not wedged)" "$rc" "0"
check "Fix2 control: the echoed path IS an actual worktree" "$( [ -n "$out" ] && git -C "$out" rev-parse --is-inside-work-tree 2>/dev/null || echo no )" "true"
git -C "$COLREPO" worktree remove --force "$out" 2>/dev/null; git -C "$COLREPO" worktree prune 2>/dev/null

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
