#!/usr/bin/env bash
# drive-base-preflight.test.sh — behavioral tests for bin/drive-base-preflight.sh, the
# ship-stage BASE-DIVERGENCE detector.
#
# FAITHFULNESS (load-bearing): at ship PREFLIGHT time the run's ledger entries still live in
# $RUN_DIR and have NOT yet been appended to featureBranch — the promote step does that AFTER the
# preflight. So the `feat` fixtures here carry ONLY disjoint code (NO ledger append); the
# diverged-base ledger-conflict case is driven by the BASE touching the ledger (which the pending
# promotion append will conflict with), NOT by a pre-appended feat. A prior version of this test
# pre-committed the ledger append to feat — an UNFAITHFUL fixture that masked a real defect (the
# detector, run pre-append, saw the ledger as one-sided/clean). The RESUMED-ship path (feat DOES
# carry the ledger commit) is covered separately.
#
# bash 3.2-safe; hermetic ($TMPDIR git repos); read-only wrt the repo under test.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PF="$REPO_DIR/bin/drive-base-preflight.sh"

PASS=0; FAIL=0
check()    { if [ "$2" = "$3" ]; then echo "PASS: $1"; PASS=$((PASS+1)); else echo "FAIL: $1 (expected '$3', got '$2')"; FAIL=$((FAIL+1)); fi; }
contains() { case "$2" in *"$3"*) echo "PASS: $1"; PASS=$((PASS+1));; *) echo "FAIL: $1 (missing '$3' in '$2')"; FAIL=$((FAIL+1));; esac; }

[ -x "$PF" ] || { echo "FAIL: drive-base-preflight.sh not executable at $PF"; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "SKIP: jq not found"; exit 0; }

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# mk_state <repo> <baseSha-or-empty> [featureBranch=feat] : make a RUN_DIR + ship state.json.
mk_state() {
  local d; d="$(mktemp -d "$WORK/run.XXXXXX")"; local fb="${3:-feat}"
  if [ -n "$2" ]; then
    jq -nc --arg bs "$2" --arg rr "$1" --arg fb "$fb" '{baseRef:"main",baseSha:$bs,featureBranch:$fb,repoRoot:$rr,stage:"ship"}' > "$d/state.json"
  else
    jq -nc --arg rr "$1" --arg fb "$fb" '{baseRef:"main",featureBranch:$fb,repoRoot:$rr,stage:"ship"}' > "$d/state.json"
  fi
  echo "$d"
}
j() { "$PF" "$1" 2>/dev/null; }

# ============ primary fixture: feat = DISJOINT CODE ONLY (faithful pre-promotion state) ==========
FX="$WORK/repo"; mkdir -p "$FX"; cd "$FX"
git init -q -b main; git config user.email t@t; git config user.name t
mkdir -p .harness
printf 'base\n' > code.txt
printf 'a\nb\nc\n' > shared.txt
printf '# decisions\nD-old-1\n' > .harness/decisions.md
printf '# followups\n' > .harness/followups.md
git add -A; git commit -qm base; BASE="$(git rev-parse HEAD)"
git checkout -q -b feat
printf 'a\nB-feat\nc\n' > shared.txt   # disjoint code edit; NO ledger append (faithful)
git add -A; git commit -qm 'run code only (no ledger append yet)'
git checkout -q main

# (1) NOT diverged.
OUT="$(j "$(mk_state "$FX" "$BASE")")"
check "unmoved base ⇒ diverged=false"      "$(echo "$OUT" | jq -r '.diverged')"       "false"
check "unmoved base ⇒ recommendation=none" "$(echo "$OUT" | jq -r '.recommendation')" "none"

# (2) diverged, DISJOINT (main adds a new non-ledger file) ⇒ ship-as-is.
printf 'main code\n' > code2.txt; git add -A; git commit -qm 'main disjoint'
OUT="$(j "$(mk_state "$FX" "$BASE")")"
check "disjoint advance ⇒ diverged=true"               "$(echo "$OUT" | jq -r '.diverged')"              "true"
check "disjoint advance ⇒ mergeClean=true"             "$(echo "$OUT" | jq -r '.mergeClean')"            "true"
check "disjoint advance ⇒ pendingLedgerConflict=false" "$(echo "$OUT" | jq -r '.pendingLedgerConflict')" "false"
check "disjoint advance ⇒ recommendation=ship-as-is"   "$(echo "$OUT" | jq -r '.recommendation')"        "ship-as-is"

# (3) THE CORE CASE — base appends to a ledger, feat has NO ledger append yet (fresh ship):
#     merge-tree is CLEAN (one-sided) but the PENDING promotion append WILL conflict ⇒ auto-rebase.
#     A merge-tree-only detector would wrongly say ship-as-is here (the masked defect).
printf 'D-main-1\n' >> .harness/decisions.md; git add -A; git commit -qm 'main ledger append'
OUT="$(j "$(mk_state "$FX" "$BASE")")"
check "pending-ledger conflict ⇒ mergeClean=true (tree is one-sided)" "$(echo "$OUT" | jq -r '.mergeClean')"            "true"
check "pending-ledger conflict ⇒ pendingLedgerConflict=true"          "$(echo "$OUT" | jq -r '.pendingLedgerConflict')" "true"
check "pending-ledger conflict ⇒ codeConflict=false"                  "$(echo "$OUT" | jq -r '.codeConflict')"          "false"
check "pending-ledger conflict ⇒ recommendation=auto-rebase"          "$(echo "$OUT" | jq -r '.recommendation')"        "auto-rebase"

# (4) diverged, CODE conflict (main also edits shared.txt, which feat edited) ⇒ manual-merge.
printf 'a\nB-main\nc\n' > shared.txt; git add -A; git commit -qm 'main edits shared (code conflict)'
OUT="$(j "$(mk_state "$FX" "$BASE")")"
check "code conflict ⇒ codeConflict=true"           "$(echo "$OUT" | jq -r '.codeConflict')"   "true"
check "code conflict ⇒ rebaseSafe=false"            "$(echo "$OUT" | jq -r '.rebaseSafe')"     "false"
check "code conflict ⇒ recommendation=manual-merge" "$(echo "$OUT" | jq -r '.recommendation')" "manual-merge"
contains "code conflict ⇒ conflicts names shared.txt" "$(echo "$OUT" | jq -c '.conflicts')" "shared.txt"

# (5) RESUMED-ship path — feat ALREADY carries the ledger commit AND base appended to it:
#     merge-tree sees a ledger conflict on the current tree (codeConflict=false) ⇒ auto-rebase.
RS="$WORK/resumed"; mkdir -p "$RS"; cd "$RS"
git init -q -b main; git config user.email t@t; git config user.name t
mkdir -p .harness; printf '# d\nD-old\n' > .harness/decisions.md; printf 'x\n' > c.txt
git add -A; git commit -qm base; RSBASE="$(git rev-parse HEAD)"
git checkout -q -b feat; printf 'D-run\n' >> .harness/decisions.md; git add -A; git commit -qm 'feat WITH ledger commit'
git checkout -q main; printf 'D-main\n' >> .harness/decisions.md; git add -A; git commit -qm 'main ledger append'
OUT="$(j "$(mk_state "$RS" "$RSBASE")")"
check "resumed-ship ledger conflict ⇒ mergeClean=false"        "$(echo "$OUT" | jq -r '.mergeClean')"     "false"
check "resumed-ship ledger conflict ⇒ codeConflict=false"      "$(echo "$OUT" | jq -r '.codeConflict')"   "false"
check "resumed-ship ledger conflict ⇒ recommendation=auto-rebase" "$(echo "$OUT" | jq -r '.recommendation')" "auto-rebase"
cd "$FX"

# (6) modify/delete NON-ledger conflict — caught by the stage-entry parser (not the human msg grep).
MD="$WORK/md"; mkdir -p "$MD"; cd "$MD"
git init -q -b main; git config user.email t@t; git config user.name t
mkdir -p .harness; printf 'x\n' > shared.txt; printf '# d\n' > .harness/decisions.md
git add -A; git commit -qm base; MDBASE="$(git rev-parse HEAD)"
git checkout -q -b feat; git rm -q shared.txt; git commit -qm 'feat deletes shared'
git checkout -q main; printf 'x\nmain-mod\n' > shared.txt; git add -A; git commit -qm 'main modifies shared'
OUT="$(j "$(mk_state "$MD" "$MDBASE")")"
contains "modify/delete ⇒ conflicts names shared.txt (stage-entry parse)" "$(echo "$OUT" | jq -c '.conflicts')" "shared.txt"
check "modify/delete non-ledger ⇒ codeConflict=true"          "$(echo "$OUT" | jq -r '.codeConflict')"   "true"
check "modify/delete non-ledger ⇒ recommendation=manual-merge" "$(echo "$OUT" | jq -r '.recommendation')" "manual-merge"
cd "$FX"

# (7) SUBSTRING of a ledger path is NOT a ledger (exact equality): a conflict on
#     x/.harness/decisions.md.bak is a NON-ledger code conflict ⇒ manual-merge. Also assert fetchOk.
SS="$WORK/ss"; mkdir -p "$SS"; cd "$SS"
git init -q -b main; git config user.email t@t; git config user.name t
mkdir -p x/.harness .harness
printf 'a\n' > x/.harness/decisions.md.bak; printf '# d\n' > .harness/decisions.md
git add -A; git commit -qm base; SSBASE="$(git rev-parse HEAD)"
git checkout -q -b feat; printf 'a\nfeat\n' > x/.harness/decisions.md.bak; git add -A; git commit -qm feat
git checkout -q main; printf 'a\nmain\n' > x/.harness/decisions.md.bak; git add -A; git commit -qm main
OUT="$(j "$(mk_state "$SS" "$SSBASE")")"
check "substring ledger path ⇒ codeConflict=true (exact-equality)" "$(echo "$OUT" | jq -r '.codeConflict')"   "true"
check "substring ledger path ⇒ recommendation=manual-merge"        "$(echo "$OUT" | jq -r '.recommendation')" "manual-merge"
check "diverged output carries fetchOk (boolean)" "$(echo "$OUT" | jq -r 'has("fetchOk") and (.fetchOk|type=="boolean")')" "true"
cd "$FX"

# (8) TODO.md is a pending ledger ONLY when $RUN_DIR/finalize-todo.md is non-empty. Base touches
#     TODO.md; without finalize-todo.md ⇒ NOT a pending conflict (ship-as-is); WITH it ⇒ auto-rebase.
TD="$WORK/todo"; mkdir -p "$TD"; cd "$TD"
git init -q -b main; git config user.email t@t; git config user.name t
mkdir -p .harness; printf '# d\n' > .harness/decisions.md; printf '# todo\n' > TODO.md; printf 'x\n' > c.txt
git add -A; git commit -qm base; TDBASE="$(git rev-parse HEAD)"
git checkout -q -b feat; printf 'run\n' > r.txt; git add -A; git commit -qm 'feat code'
git checkout -q main; printf '%s\n' '- new todo' >> TODO.md; git add -A; git commit -qm 'main touches TODO'
D_NO="$(mk_state "$TD" "$TDBASE")"
check "base touches TODO.md, no finalize-todo ⇒ ship-as-is" "$(j "$D_NO" | jq -r '.recommendation')" "ship-as-is"
D_YES="$(mk_state "$TD" "$TDBASE")"; printf 'arch finding\n' > "$D_YES/finalize-todo.md"
check "base touches TODO.md WITH finalize-todo ⇒ auto-rebase" "$(j "$D_YES" | jq -r '.recommendation')" "auto-rebase"
cd "$FX"

# (9) legacy run — no baseSha ⇒ fail-OPEN, never a block.
OUT="$(j "$(mk_state "$FX" "")")"
check "no baseSha ⇒ diverged=false (fail-open)" "$(echo "$OUT" | jq -r '.diverged')"       "false"
check "no baseSha ⇒ recommendation=none"        "$(echo "$OUT" | jq -r '.recommendation')" "none"
contains "no baseSha ⇒ reason names baseSha"    "$(echo "$OUT" | jq -r '.reason')"          "baseSha"

# (10) CLI/precondition errors ⇒ exit 2.
"$PF" >/dev/null 2>&1;             check "no-arg ⇒ exit 2"    "$?" "2"
"$PF" "$WORK/nope" >/dev/null 2>&1; check "no-state ⇒ exit 2" "$?" "2"

# (11) SHIP_LEDGER_ALLOWLIST must not drift from bin/drive-conformance.sh. SITE-PRECISE
#      (D-28/D-41): each extraction reads ONLY its array's own declaration line — a
#      whole-file quoted-string sweep would also match the pendingLedgers conditional and
#      mask a one-array drift — and the expected 4-entry contents are pinned explicitly.
pf_al="$(sed -n 's/^LEDGER_ALLOWLIST=(\(.*\))$/\1/p' "$PF" | grep -oE '"[^"]+"' | tr -d '"' | LC_ALL=C sort -u | tr '\n' ' ')"
cf_al="$(sed -n 's/^SHIP_LEDGER_ALLOWLIST=(\(.*\))$/\1/p' "$REPO_DIR/bin/drive-conformance.sh" | grep -oE '"[^"]+"' | tr -d '"' | LC_ALL=C sort -u | tr '\n' ' ')"
check "ledger allowlist matches drive-conformance.sh" "$pf_al" "$cf_al"
check "ledger allowlist is the 4-entry set" "$cf_al" ".harness/codex-refutations.md .harness/decisions.md .harness/followups.md TODO.md "

# (12) .harness/codex-refutations.md is a pending ledger ONLY when
#      $RUN_DIR/codex-refutations-pending.md is non-empty (mirrors the (8)
#      finalize-todo/TODO.md conditional). Base appends to the refutation ledger; feat has
#      no ledger commit yet: without the pending file ⇒ NOT a pending conflict
#      (ship-as-is); WITH it non-empty ⇒ auto-rebase.
CR="$WORK/refut"; mkdir -p "$CR"; cd "$CR"
git init -q -b main; git config user.email t@t; git config user.name t
mkdir -p .harness
printf '# d\n' > .harness/decisions.md; printf '# cr\n' > .harness/codex-refutations.md; printf 'x\n' > c.txt
git add -A; git commit -qm base; CRBASE="$(git rev-parse HEAD)"
git checkout -q -b feat; printf 'run\n' > r.txt; git add -A; git commit -qm 'feat code'
git checkout -q main; printf '%s\n' '## CR-new — main appended' >> .harness/codex-refutations.md
git add -A; git commit -qm 'main touches codex-refutations'
D_NO="$(mk_state "$CR" "$CRBASE")"
check "base touches codex-refutations.md, no pending file ⇒ ship-as-is" "$(j "$D_NO" | jq -r '.recommendation')" "ship-as-is"
D_YES="$(mk_state "$CR" "$CRBASE")"; printf '## CR-pending entry\n' > "$D_YES/codex-refutations-pending.md"
check "base touches codex-refutations.md WITH pending ⇒ auto-rebase" "$(j "$D_YES" | jq -r '.recommendation')" "auto-rebase"
cd "$FX"

echo "----------------------------------------"
echo "PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -eq 0 ] || exit 1
