#!/usr/bin/env bash
# drive-base-preflight.sh — ship-stage BASE-DIVERGENCE detector for /drive.
#
# Closes the "diverged-base append-only-ledger" trap: a /drive run branches from `baseRef`
# at a frozen `baseSha`; if `baseRef` advances while the run is in flight (common in a shared
# clone) AND both sides append to the same append-only `.harness` ledgers, the ship's ledger
# promotion lands on the STALE base copy and the resulting PR CONFLICTS at merge — silently,
# unless someone remembers to check. This detector makes the check EXECUTABLE (not a memory):
# drive-ship.md runs it BEFORE the ledger promotion and acts on `recommendation`.
#
# It ONLY reads git + state.json and PREDICTS the merge via `git merge-tree`. It performs NO
# mutation (no fetch of writes, no rebase, no push) beyond a best-effort read-only `git fetch`
# of the base branch. It is a REPORT, never a gate: it ALWAYS exits 0 with a JSON verdict on
# stdout (the ONLY non-zero exits are 2 for a CLI/precondition error — missing arg, jq, or
# state.json — surfaced BEFORE any git work). Fail-OPEN by construction: any condition it
# cannot reason about (legacy run without `baseSha`, unresolvable ref, invalid repoRoot) emits
# `{"diverged":false,...}` so a run ships exactly as today — the detector never invents a block.
#
# Output JSON fields:
#   diverged              base moved past baseSha (currentBase != baseSha)
#   baseRef/baseSha       from state.json
#   currentBase/currentBaseRef   the resolved current base tip (origin/<baseRef> preferred)
#   movedCommits          count of baseSha..currentBase
#   mergeClean            git merge-tree of currentBase + featureBranch has NO conflict
#   conflicts             array of conflicted paths (empty when mergeClean)
#   conflictInLedgersOnly every conflicted path ∈ the ship ledger allowlist (append-only)
#   rebaseSafe            mergeClean OR conflictInLedgersOnly ⇒ the run's code is disjoint from
#                         the base's changes ⇒ rebasing the run's commits onto currentBase is
#                         content-preserving (drive-ship.md may auto-rebase + re-bind finalize)
#   recommendation        none | ship-as-is | auto-rebase | manual-merge
#
# Usage: drive-base-preflight.sh <RUN_DIR>
#
# Best-effort isolation: NOT `set -euo pipefail`; `set -u` only. A git hiccup folds to a
# fail-open verdict, never a crash.
set -u

# SHIP_LEDGER_ALLOWLIST — MUST stay byte-identical to bin/drive-conformance.sh's
# SHIP_LEDGER_ALLOWLIST (the append-only ledger files the single ship commit may touch). A
# drift test (test/drive-base-preflight.test.sh) asserts the two lists match.
LEDGER_ALLOWLIST=(".harness/decisions.md" ".harness/followups.md" "TODO.md" ".harness/codex-refutations.md")

RUN_DIR="${1:-}"
[ -n "$RUN_DIR" ] || { echo "usage: drive-base-preflight.sh <RUN_DIR>" >&2; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "drive-base-preflight: jq not found" >&2; exit 2; }
STATE="$RUN_DIR/state.json"
[ -f "$STATE" ] || { echo "drive-base-preflight: no state.json at $STATE" >&2; exit 2; }
jq -e . "$STATE" >/dev/null 2>&1 || { echo "drive-base-preflight: unparseable state.json" >&2; exit 2; }

# emit a fail-open non-diverged verdict with a reason, then exit 0.
emit_open() { jq -nc --arg r "$1" '{diverged:false,recommendation:"none",reason:$r}'; exit 0; }

baseRef=$(jq -r '.baseRef // empty' "$STATE")
baseSha=$(jq -r '.baseSha // empty' "$STATE")
featureBranch=$(jq -r '.featureBranch // empty' "$STATE")
repoRoot=$(jq -r '.repoRoot // empty' "$STATE")

# baseSha is an OPTIONAL state field (legacy runs predate it) — without it divergence is
# undetectable → fail-open (ship as today).
[ -n "$baseSha" ] || emit_open "no-baseSha (legacy run; divergence undetectable, ship-as-is)"
[ -n "$baseRef" ] && [ -n "$featureBranch" ] || emit_open "incomplete-state (baseRef/featureBranch missing)"
{ [ -n "$repoRoot" ] && [ -d "$repoRoot" ]; } || emit_open "repoRoot-invalid"
cd "$repoRoot" 2>/dev/null || emit_open "cd-repoRoot-failed"

# Resolve the CURRENT base tip. The PR merges into the REMOTE baseRef, so prefer
# origin/<baseRef> after a best-effort NON-INTERACTIVE fetch; fall back to the local branch.
# CAPTURE whether the fetch SUCCEEDED: on a FAILED fetch, `origin/<baseRef>` is a possibly-STALE
# remote-tracking ref — comparing against it can miss a real remote divergence (a silent bypass).
# We still emit a best-effort verdict, but tag it `fetchOk:false` so drive-ship.md surfaces the
# degraded check at Gate B rather than trusting a clean/none result computed against a stale ref.
fetchOk=false
GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -oBatchMode=yes' git fetch --quiet origin "$baseRef" 2>/dev/null && fetchOk=true
if currentBase=$(git rev-parse --verify -q "origin/$baseRef^{commit}" 2>/dev/null); then
  currentBaseRef="origin/$baseRef"
elif currentBase=$(git rev-parse --verify -q "refs/heads/$baseRef^{commit}" 2>/dev/null); then
  currentBaseRef="$baseRef"
else
  emit_open "baseRef-unresolvable: $baseRef"
fi

fbTip=$(git rev-parse --verify -q "$featureBranch^{commit}" 2>/dev/null) \
  || emit_open "featureBranch-unresolvable: $featureBranch"

# Not moved → not diverged. (Still tag fetchOk: a FALSE here computed against a stale
# origin/<baseRef> is exactly the failed-fetch bypass — drive-ship.md surfaces it.)
if [ "$currentBase" = "$baseSha" ]; then
  jq -nc --arg cb "$currentBase" --arg cr "$currentBaseRef" --argjson fo "$fetchOk" \
    '{diverged:false,currentBase:$cb,currentBaseRef:$cr,movedCommits:0,fetchOk:$fo,recommendation:"none"}'
  exit 0
fi

# baseSha must be an ANCESTOR of currentBase (a normal fast-forward advance of the base). If it
# is NOT (the base's history was rewritten/force-pushed under the run), a clean rebase cannot be
# reasoned about → surface as manual, never auto-rebase.
if ! git merge-base --is-ancestor "$baseSha" "$currentBase" 2>/dev/null; then
  jq -nc --arg cb "$currentBase" --arg cr "$currentBaseRef" --arg bs "$baseSha" --argjson fo "$fetchOk" \
    '{diverged:true,baseSha:$bs,currentBase:$cb,currentBaseRef:$cr,baseRewritten:true,mergeClean:false,rebaseSafe:false,fetchOk:$fo,recommendation:"manual-merge",reason:"baseSha is not an ancestor of currentBase (base history rewritten)"}'
  exit 0
fi

movedCommits=$(git rev-list --count "$baseSha..$currentBase" 2>/dev/null || echo 0)

# PREDICT the merge: merge-tree the currentBase and the featureBranch tip. On a CLEAN merge the
# output is a single tree-OID line; on a conflict, the tree-OID line is followed by the machine-
# readable "Conflicted file info" section — one entry per conflicted path+stage,
# `<mode> <object> <stage>\t<path>` — then a blank line, then human messages. Parse the STAGE
# ENTRIES (the path after the tab, up to the first blank line), NOT the human "Merge conflict in"
# messages: those only cover CONTENT conflicts and omit modify/delete, add/add, and rename
# phrasings — grepping them would MISS a real non-ledger conflict and wrongly green-light an
# auto-rebase. (git >= 2.38 --write-tree format.)
# NOTE (safe by construction): a path with a tab/newline/special char is C-quoted by git in the
# stage entry (`"dir/has\tTab.txt"`); we keep the raw form. This never MISclassifies: the ledger
# allowlist entries are plain strings with no special chars, so a C-quoted path can never EXACTLY
# equal a ledger entry → it always classifies NON-ledger (`manual-merge`), the SAFE direction
# (never a wrongful auto-rebase). Only the human-facing `.conflicts` string is quoted for such names.
# merge-tree --write-tree exits 0=clean, 1=conflict, >1=ERROR (incl. git <2.38 lacking
# --write-tree). A valid run's stdout line 1 is a 40-hex tree OID; anything else ⇒ merge-tree
# FAILED → fail-OPEN to a NON-confident verdict (recommendation "none" + a reason drive-ship.md
# surfaces at Gate B), NOT a confident clean (which would hide a real conflict). Degrading to
# "no check" == the pre-detector behaviour (a human catches the conflict at merge).
mt_out=$(git merge-tree --write-tree "$currentBase" "$fbTip" 2>/dev/null); mt_rc=$?
first_line=$(printf '%s\n' "$mt_out" | head -1)
# valid tree OID = 40-hex (SHA-1) OR 64-hex (SHA-256 repos) — accept both.
if { [ "$mt_rc" -ne 0 ] && [ "$mt_rc" -ne 1 ]; } || ! printf '%s' "$first_line" | grep -qiE '^[0-9a-f]{40}$|^[0-9a-f]{64}$'; then
  emit_open "merge-tree-failed (git too old for --write-tree, or an error) — merge unpredictable"
fi
raw_paths=()
while IFS= read -r line; do
  [ -z "$line" ] && break                      # blank line ends the conflicted-file-info section
  case "$line" in
    *$'\t'*) raw_paths+=("${line#*$'\t'}") ;;   # stage entry → path after the tab
  esac
done < <(printf '%s\n' "$mt_out" | tail -n +2)  # skip the leading tree-OID line
conflicts=()
if [ "${#raw_paths[@]}" -gt 0 ]; then
  while IFS= read -r p; do [ -n "$p" ] && conflicts+=("$p"); done \
    < <(printf '%s\n' "${raw_paths[@]}" | sort -u)
fi
mergeClean=true; [ "${#conflicts[@]}" -gt 0 ] && mergeClean=false

# Classify the CURRENT-tree conflicts: a NON-ledger conflicted path is a real CODE/semantic
# conflict (never auto-resolve those). (Ledger conflicts on the current tree only occur on a
# RESUMED post-promotion ship, where featureBranch already carries the ledger commit.)
codeConflict=false
for c in "${conflicts[@]:-}"; do
  [ -n "$c" ] || continue
  isLedger=false
  for a in "${LEDGER_ALLOWLIST[@]}"; do [ "$c" = "$a" ] && { isLedger=true; break; }; done
  $isLedger || { codeConflict=true; break; }
done

# PENDING ledger-append conflict — the CORE diverged-base case. The ship's promote step ALWAYS
# appends the run's entries to .harness/decisions.md + .harness/followups.md (and to TODO.md IFF
# $RUN_DIR/finalize-todo.md is non-empty). At preflight time (a FRESH ship) featureBranch has NOT
# yet appended, so merge-tree on the pre-append tree sees the ledger as ONE-SIDED → clean — it
# STRUCTURALLY cannot observe the conflict the promotion will create. So predict it DIRECTLY: if
# the advancing base MODIFIED any ledger the run WILL append to, both sides append at EOF relative
# to the shared base ⇒ the promotion conflicts. This is the case merge-tree alone would miss.
# CONSERVATIVE BIAS (deliberate): this fires on ANY base-side change to a pending ledger, even a
# NON-tail edit (main edits line 1, or a mode-only change) that the run's EOF append would actually
# merge cleanly. The cost of a false positive is a possibly-unnecessary but ALWAYS-SAFE
# (content-preserving) auto-rebase; the safe direction. Predicting tail-only conflict precisely
# would require simulating the append (a temp commit + merge-tree) — not worth it for append-only
# ledgers, where the base almost always appends (a real conflict) rather than edits mid-file.
pendingLedgers=(".harness/decisions.md" ".harness/followups.md")
[ -s "$RUN_DIR/finalize-todo.md" ] && pendingLedgers+=("TODO.md")
[ -s "$RUN_DIR/codex-refutations-pending.md" ] && pendingLedgers+=(".harness/codex-refutations.md")
baseChanged=$(git diff --name-only "$baseSha".."$currentBase" 2>/dev/null || true)
pendingLedgerConflict=false
for pl in "${pendingLedgers[@]}"; do
  printf '%s\n' "$baseChanged" | grep -qxF -- "$pl" && { pendingLedgerConflict=true; break; }
done

# Recommendation: a NON-ledger conflict ⇒ manual-merge (a genuine semantic overlap — never
# auto-rewrite). Else, if a ledger conflicts (already on the tree OR the pending append) ⇒
# auto-rebase (the run's code is disjoint ⇒ rebasing onto currentBase is content-preserving).
# Else the base moved but nothing the run touches conflicts ⇒ ship-as-is.
if $codeConflict; then rec="manual-merge"
elif [ "$mergeClean" = false ] || $pendingLedgerConflict; then rec="auto-rebase"
else rec="ship-as-is"; fi
rebaseSafe=true; $codeConflict && rebaseSafe=false

if [ "${#conflicts[@]}" -gt 0 ]; then
  conflicts_json=$(printf '%s\n' "${conflicts[@]}" | jq -R . | jq -sc .)
else
  conflicts_json="[]"
fi

jq -nc \
  --arg br "$baseRef" --arg bs "$baseSha" --arg cb "$currentBase" --arg cr "$currentBaseRef" \
  --arg fb "$fbTip" --argjson mv "$movedCommits" \
  --argjson mc "$mergeClean" --argjson cc "$codeConflict" --argjson pl "$pendingLedgerConflict" \
  --argjson rs "$rebaseSafe" --argjson conf "$conflicts_json" --argjson fo "$fetchOk" --arg rec "$rec" \
  '{diverged:true,baseRef:$br,baseSha:$bs,currentBase:$cb,currentBaseRef:$cr,featureTip:$fb,movedCommits:$mv,mergeClean:$mc,conflicts:$conf,codeConflict:$cc,pendingLedgerConflict:$pl,rebaseSafe:$rs,fetchOk:$fo,recommendation:$rec}'
exit 0
