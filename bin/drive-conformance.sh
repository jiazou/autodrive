#!/usr/bin/env bash
# drive-conformance.sh — the keystone conformance checker for /drive enforcement.
#
# Pure function over git refs + SHA-bound review artifacts in RUN_DIR. NEVER reads
# state.json's `step`/`phaseReview` for the verdict (D1: git-truth, not state-trust).
#
# Usage:
#   drive-conformance.sh <RUN_DIR> --mode plan-gate | slice-merge:<id> | phase-merge:<P> | ship | audit
#
# Truth model:
#   runId        = basename(RUN_DIR)
#   featureBranch = drive/<runId>
#   A review "counts" iff the highest-N review-<scope>-N.md has `## Verdict: CONVERGED`
#   AND a `reviewed-sha: <40hex>` line equal to the git tip the mode checks, AND a
#   sibling codex-review-<scope>.md exists (its degradation marker, if present, must be
#   the anchored first-line token CODEX_UNAVAILABLE).
#
# Output (stdout JSON): {"clean":bool,"mode":"...","tip":"<sha>","violations":[...]}
# Exit: 0 clean · 1 violations · 2 usage/IO/git error.
# Fail-closed/open semantics for exit 2 live in the HOOKS, not here.
set -euo pipefail

# --- Ship-ledger allowlist: the EXACT two files SHIP commits AFTER the last review.
#     Kept in sync with drive-ship.md (NOT the whole .harness/ dir — D12 / round-3). ---
SHIP_LEDGER_ALLOWLIST=(".harness/decisions.md" ".harness/followups.md")

usage() {
  echo "usage: drive-conformance.sh <RUN_DIR> --mode plan-gate|slice-merge:<id>|phase-merge:<P>|ship|audit" >&2
}

# Emit the JSON result and exit. $1=clean(true|false) $2=mode $3=tip $4=violations-json-array
emit() {
  local clean="$1" mode="$2" tip="$3" viols="$4"
  printf '{"clean":%s,"mode":"%s","tip":"%s","violations":%s}\n' "$clean" "$mode" "$tip" "$viols"
  if [ "$clean" = "true" ]; then exit 0; else exit 1; fi
}

# Build one violation object. $1=scope $2=reason [$3=expected_sha $4=found_sha]
violation() {
  local scope="$1" reason="$2" exp="${3:-}" found="${4:-}"
  printf '{"scope":"%s","reason":"%s","expected_sha":"%s","found_sha":"%s"}' \
    "$scope" "$reason" "$exp" "$found"
}

# --- arg parse ---
[ $# -eq 3 ] || { usage; exit 2; }
RUN_DIR="$1"
[ "$2" = "--mode" ] || { usage; exit 2; }
MODE_ARG="$3"

[ -d "$RUN_DIR" ] || { echo "error: RUN_DIR not a directory: $RUN_DIR" >&2; exit 2; }
RUN_DIR="$(cd "$RUN_DIR" && pwd)"   # canonicalize
runId="$(basename "$RUN_DIR")"
featureBranch="drive/$runId"

# --- helpers over review artifacts (operate in $RUN_DIR) ---

# Echo the path of the highest-N review-<scope>-N.md, rc1 if none. $1=scope
highest_review_file() {
  local scope="$1" best="" bestn=-1 f n
  for f in "$RUN_DIR"/review-"$scope"-*.md; do
    [ -e "$f" ] || continue
    n="${f##*/review-"$scope"-}"; n="${n%.md}"
    case "$n" in (*[!0-9]*|'') continue;; esac   # only pure-integer N
    if [ "$n" -gt "$bestn" ]; then bestn="$n"; best="$f"; fi
  done
  [ -n "$best" ] || return 1
  printf '%s\n' "$best"
}

# Is the codex side satisfied for scope? codex-review-<scope>.md must exist; if its
# anchored first line is the bare token CODEX_UNAVAILABLE, that's allowed (codex down).
# rc0 satisfied, rc1 missing. $1=scope
codex_present() {
  local scope="$1"
  local f="$RUN_DIR/codex-review-$scope.md"
  [ -f "$f" ] || return 1
  return 0
}

# Read `reviewed-sha:` (first match) from a review file; echo sha or empty. $1=file
reviewed_sha_of() {
  local f="$1" line
  line="$(grep -m1 -E '^reviewed-sha:[[:space:]]*[0-9a-fA-F]{40}[[:space:]]*$' "$f" 2>/dev/null || true)"
  [ -n "$line" ] || return 1
  line="${line#reviewed-sha:}"
  # trim whitespace
  line="${line//[[:space:]]/}"
  printf '%s\n' "$line"
}

# Does the highest-N review for scope have CONVERGED verdict? rc0 yes. $1=file
verdict_converged() {
  grep -qE '^## Verdict:[[:space:]]*CONVERGED[[:space:]]*$' "$1" 2>/dev/null
}

# Evaluate whether scope <id> has a COUNTING review for tip <sha>.
# Echoes a violation object (or nothing) and returns rc0 if counts, rc1 if not.
# $1=scope-label (for violation) $2=review-scope $3=expected-tip-sha
check_scope_counts() {
  local label="$1" scope="$2" tip="$3" rf rsha
  if ! rf="$(highest_review_file "$scope")"; then
    violation "$label" "no-review" "$tip" ""
    return 1
  fi
  if ! verdict_converged "$rf"; then
    violation "$label" "verdict-not-converged" "$tip" ""
    return 1
  fi
  if ! rsha="$(reviewed_sha_of "$rf")"; then
    violation "$label" "sha-mismatch" "$tip" ""
    return 1
  fi
  if [ "$rsha" != "$tip" ]; then
    violation "$label" "sha-mismatch" "$tip" "$rsha"
    return 1
  fi
  if ! codex_present "$scope"; then
    violation "$label" "no-codex" "$tip" "$rsha"
    return 1
  fi
  return 0
}

# git rev-parse a ref; echo sha or rc1. $1=ref
rev() { git rev-parse --verify --quiet "$1^{commit}" 2>/dev/null; }

case "$MODE_ARG" in

  plan-gate)
    # Enforces the PLAN/design review. No git tip — design review audits design.md.
    # Clean iff highest-N review-design-N.md is CONVERGED AND codex-review-design.md exists.
    rf=""; viols=""
    if ! rf="$(highest_review_file design)"; then
      viols="$(violation "design" "no-review")"
    elif ! verdict_converged "$rf"; then
      viols="$(violation "design" "verdict-not-converged")"
    elif ! codex_present design; then
      viols="$(violation "design" "no-codex")"
    fi
    if [ -z "$viols" ]; then emit true "plan-gate" "" "[]"; else emit false "plan-gate" "" "[$viols]"; fi
    ;;

  slice-merge:*)
    id="${MODE_ARG#slice-merge:}"
    [ -n "$id" ] || { usage; exit 2; }
    ref="slice/$runId/$id"
    if ! tip="$(rev "$ref")"; then
      echo "error: cannot resolve ref $ref" >&2; exit 2
    fi
    if v="$(check_scope_counts "slice:$id" "$id" "$tip")"; then
      emit true "slice-merge:$id" "$tip" "[]"
    else
      emit false "slice-merge:$id" "$tip" "[$v]"
    fi
    ;;

  phase-merge:*)
    P="${MODE_ARG#phase-merge:}"
    [ -n "$P" ] || { usage; exit 2; }
    ref="phaseInt/$runId/$P"
    if ! tip="$(rev "$ref")"; then
      echo "error: cannot resolve ref $ref" >&2; exit 2
    fi
    if v="$(check_scope_counts "phase:$P" "phase$P" "$tip")"; then
      emit true "phase-merge:$P" "$tip" "[]"
    else
      emit false "phase-merge:$P" "$tip" "[$v]"
    fi
    ;;

  ship)
    # Existential R (D12): EXISTS a counting phase/integration review with
    # reviewed-sha R s.t. (a) R is ancestor of tip, (b) git diff R..tip ⊆ allowlist,
    # (c) R..tip is at most one commit. Do NOT pick highest-N (mis-selects across phases).
    if ! tip="$(rev "$featureBranch")"; then
      echo "error: cannot resolve featureBranch $featureBranch" >&2; exit 2
    fi

    # Gather all counting phase reviews: highest-N review-phase<P>-N.md that is CONVERGED,
    # has a reviewed-sha, and has codex-review-phase<P>.md. Collect their R shas.
    # (No associative arrays — macOS ships bash 3.2; dedup via a space-delimited string.)
    candidate_R=""
    seen_phase=" "
    for f in "$RUN_DIR"/review-phase*-*.md; do
      [ -e "$f" ] || continue
      base="${f##*/}"                       # review-phase<P>-<N>.md
      rest="${base#review-}"                # phase<P>-<N>.md
      scope="${rest%-*.md}"                 # phase<P>
      case "$seen_phase" in (*" $scope "*) continue;; esac
      seen_phase="$seen_phase$scope "
      rf="$(highest_review_file "$scope")" || continue
      verdict_converged "$rf" || continue
      rsha="$(reviewed_sha_of "$rf")" || continue
      codex_present "$scope" || continue
      candidate_R="$candidate_R$rsha "
    done

    # Test each candidate R against (a)(b)(c). Succeed on first that satisfies all.
    ship_clean=false
    for R in $candidate_R; do
      [ -n "$R" ] || continue
      # R must resolve in this repo
      git rev-parse --verify --quiet "$R^{commit}" >/dev/null 2>&1 || continue
      # (a) R ancestor of tip
      git merge-base --is-ancestor "$R" "$tip" 2>/dev/null || continue
      # (c) R..tip ≤ 1 commit
      ncommits="$(git rev-list --count "$R..$tip" 2>/dev/null || echo 999)"
      [ "$ncommits" -le 1 ] || continue
      # (b) changed files ⊆ allowlist
      subset=true
      while IFS= read -r path; do
        [ -n "$path" ] || continue
        allowed=false
        for a in "${SHIP_LEDGER_ALLOWLIST[@]}"; do
          [ "$path" = "$a" ] && { allowed=true; break; }
        done
        [ "$allowed" = true ] || { subset=false; break; }
      done < <(git diff --name-only "$R..$tip" 2>/dev/null)
      [ "$subset" = true ] || continue
      # all satisfied
      ship_clean=true
      break
    done

    if [ "$ship_clean" = true ]; then
      emit true "ship" "$tip" "[]"
    else
      emit false "ship" "$tip" "[$(violation "ship" "no-review" "$tip" "")]"
    fi
    ;;

  audit)
    # Scoped to the in-flight phase only. Report slices merged into the CURRENT LIVE
    # phaseInt/<runId>/<P> that lack a counting review. Completed phases are NOT
    # re-audited (guaranteed by phase-merge + ship gates). If no live phaseInt, clean.
    #
    # Find the highest live phaseInt/<runId>/<P>.
    live_P=""; live_ref=""
    while IFS= read -r ref; do
      [ -n "$ref" ] || continue
      p="${ref##*/}"
      case "$p" in (*[!0-9]*|'') continue;; esac
      if [ -z "$live_P" ] || [ "$p" -gt "$live_P" ]; then live_P="$p"; live_ref="$ref"; fi
    done < <(git for-each-ref --format='%(refname:short)' "refs/heads/phaseInt/$runId/" 2>/dev/null)

    if [ -z "$live_ref" ]; then
      emit true "audit" "" "[]"
    fi

    tip="$(rev "$live_ref" 2>/dev/null || echo "")"

    # Enumerate slice branches merged into live_ref. Slice refs: slice/<runId>/<id>.
    declare -a viol_arr=()
    while IFS= read -r sref; do
      [ -n "$sref" ] || continue
      id="${sref#slice/$runId/}"
      [ "$id" = "$sref" ] && continue
      # Is this slice's tip an ancestor of the live phaseInt tip (i.e. merged in)?
      stip="$(rev "$sref" 2>/dev/null || echo "")"
      [ -n "$stip" ] || continue
      git merge-base --is-ancestor "$stip" "$tip" 2>/dev/null || continue
      if ! v="$(check_scope_counts "slice:$id" "$id" "$stip")"; then
        viol_arr+=("$v")
      fi
    done < <(git for-each-ref --format='%(refname:short)' "refs/heads/slice/$runId/" 2>/dev/null)

    if [ "${#viol_arr[@]}" -eq 0 ]; then
      emit true "audit" "$tip" "[]"
    else
      joined="$(IFS=,; echo "${viol_arr[*]}")"
      emit false "audit" "$tip" "[$joined]"
    fi
    ;;

  *)
    usage; exit 2
    ;;
esac
