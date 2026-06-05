#!/usr/bin/env bash
# drive-conformance.sh — the keystone conformance checker for /drive enforcement.
#
# Pure function over git refs + SHA-bound review artifacts in RUN_DIR. NEVER reads
# state.json's `step`/`phaseReview` for the verdict (D1: git-truth, not state-trust).
#
# Usage:
#   drive-conformance.sh <RUN_DIR> --mode plan-gate | slice-merge:<id> | phase-merge:<P> | impl-presence:<id> | ship | audit
#
# Truth model:
#   runId        = basename(RUN_DIR)
#   featureBranch = drive/<runId>
#   A review "counts" iff the highest-N review-<scope>-N.md has `## Verdict: CONVERGED`
#   AND a `reviewed-sha: <40hex>` line equal to the git tip the mode checks, AND a
#   sibling codex-review-<scope>.md exists and is non-empty (any non-empty content
#   satisfies — a real codex review OR a CODEX_UNAVAILABLE degradation note; the file's
#   content is NOT inspected).
#
# Output (stdout JSON): {"clean":bool,"mode":"...","tip":"<sha>","violations":[...]}
# Exit: 0 clean · 1 violations · 2 usage/IO/git error.
# Fail-closed/open semantics for exit 2 live in the HOOKS, not here.
set -euo pipefail

# --- Ship-ledger allowlist: the EXACT two files SHIP commits AFTER the last review.
#     Kept in sync with drive-ship.md (NOT the whole .harness/ dir — D12 / round-3). ---
SHIP_LEDGER_ALLOWLIST=(".harness/decisions.md" ".harness/followups.md")

usage() {
  echo "usage: drive-conformance.sh <RUN_DIR> --mode plan-gate|slice-merge:<id>|phase-merge:<P>|impl-presence:<id>|ship|audit" >&2
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

# Is the codex side satisfied for scope? codex-review-<scope>.md must exist AND be
# non-empty. ANY existing non-empty codex-review-<scope>.md satisfies — the content is
# NOT inspected: it may be a real codex review OR a CODEX_UNAVAILABLE degradation note
# (the codex-down case). Only an EMPTY file (a bare `touch`) or a missing file fails.
# rc0 satisfied, rc1 missing/empty. $1=scope
codex_present() {
  local scope="$1"
  local f="$RUN_DIR/codex-review-$scope.md"
  [ -f "$f" ] || return 1
  [ -s "$f" ] || return 1           # empty file does NOT satisfy
  # Any non-empty content satisfies (real review OR CODEX_UNAVAILABLE note); not inspected.
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

# Run a git command that MUST succeed; on any nonzero rc this is a genuine git/IO
# error (not a verdict) → surface as exit 2 (fail-closed/contract). Echoes stdout.
# Use ONLY for commands whose nonzero rc has no legitimate "this is the answer"
# meaning (e.g. `git diff`, `git rev-list --count`). Do NOT use for
# `merge-base --is-ancestor` (nonzero = "not an ancestor", a real verdict).
git_or_die() {
  local out
  if ! out="$(git "$@" 2>/dev/null)"; then
    echo "error: git $* failed (git/IO error)" >&2
    exit 2
  fi
  printf '%s' "$out"
}

# Does a changed path count as test evidence (a file a REAL repo test runner executes)?
# Anchored to the two runner roots (README ## Testing / pyproject testpaths), NOT a bare
# basename anywhere — `test_root.py`, `docs/x.test.md`, `scratch/x.test.json` do NOT count.
#   - test/*.test.sh                                  (bash suite runner root), OR
#   - tests/**/{test_*.py | *_test.py}                (pytest testpaths root),
#     EXCLUDING support files even under tests/: _helpers.py, conftest.py, any path with a
#     `fixtures/` segment, *.pyc, any `__pycache__/` segment.
# rc0 = counts as test evidence; rc1 = does not. $1=path
is_test_path() {
  local p="$1" b
  b="${p##*/}"   # basename

  # A DOTFILE basename is NEVER a runnable test: the real bash runner glob
  # (`for f in test/*.test.sh`) and CI's pytest collection both SKIP dotfiles (a leading
  # `.` is not matched by `*` without `dotglob`). So `test/.noop.test.sh` /
  # `tests/mc/.test_x.py` would pass the patterns below on bash 3.2's `case` (which DOES
  # match a leading dot) yet never actually run — reject them up front. (Applies to both
  # the test/*.test.sh and tests/** branches.)
  case "$b" in .*) return 1;; esac

  # --- bash suite: exactly test/<name>.test.sh (one segment under test/) ---
  case "$p" in
    test/*.test.sh)
      # reject nested (test/sub/x.test.sh): the runner globs only test/*.test.sh
      case "${p#test/}" in (*/*) ;; (*) return 0;; esac
      ;;
  esac

  # --- pytest: under tests/ with a runnable basename, minus support exclusions ---
  case "$p" in
    tests/*)
      # exclusions (apply even under tests/)
      case "$b" in (_helpers.py|conftest.py|*.pyc) return 1;; esac
      case "$p" in (*/fixtures/*|fixtures/*) return 1;; esac   # any fixtures/ segment
      case "$p" in (*/__pycache__/*|__pycache__/*) return 1;; esac
      case "$b" in
        (test_*.py|*_test.py) return 0;;
      esac
      ;;
  esac

  return 1
}

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

  impl-presence:*)
    # IMPLEMENT-stage test-presence invariant (Item C). A slice branch's diff against its
    # fork-point off drive/<runId> must add/modify a runnable test path, OR a commit in that
    # range must carry a real `Drive-Test-Waiver:` git TRAILER. Pure git-truth (no state.json).
    # base = merge-base(slice, drive/<runId>) via git_or_die so rc>=1 (unresolvable ref OR
    # genuinely-disjoint histories) → exit 2 (fail-closed at the HOOK; here it is just abnormal),
    # never a silent empty base feeding a malformed <empty>..tip diff.
    id="${MODE_ARG#impl-presence:}"
    [ -n "$id" ] || { usage; exit 2; }
    ref="slice/$runId/$id"
    if ! tip="$(rev "$ref")"; then
      echo "error: cannot resolve ref $ref" >&2; exit 2
    fi
    base="$(git_or_die merge-base "$ref" "$featureBranch")"   # rc>=1 → exit 2 (no silent empty)
    [ -n "$base" ] || { echo "error: empty merge-base for $ref..$featureBranch" >&2; exit 2; }

    # test? — ANY NON-DELETION change to a runnable test path in base..tip matches the
    # runner-anchored predicate. `--diff-filter=d` (lowercase d = EXCLUDE deletions) so a
    # DELETED test path (D) does NOT count as test evidence — deleting tests/test_auth.py
    # must NOT satisfy the invariant — while ADD (A), MODIFY (M), RENAME (R), COPY (C), and
    # TYPE-CHANGE (T) all DO count. Uppercase `AM` would over-block: git classes a renamed or
    # copied test as R/C (and a type-change as T), so `AM` false-DENIES a slice that adds
    # coverage by renaming/copying a file INTO a runnable test path. With `--name-only`, a
    # rename prints only the DESTINATION path, so a rename AWAY from a test path (test → docs)
    # prints the non-runnable dest and is correctly NOT counted (the test was removed); a
    # rename INTO a test path prints the runnable dest and IS counted.
    changed="$(git_or_die diff --diff-filter=d --name-only "$base..$tip")"
    has_test=false
    while IFS= read -r path; do
      [ -n "$path" ] || continue
      if is_test_path "$path"; then has_test=true; break; fi
    done <<EOF
$changed
EOF

    # waived? — ANY commit in base..tip has a REAL `Drive-Test-Waiver:` git trailer with a
    # NON-WHITESPACE value (real trailer parsing, NOT a %B body substring). The format emits
    # one (possibly blank) value per commit + NUL separators, so check for non-whitespace.
    waived=false
    if [ "$has_test" != true ]; then
      wvals="$(git_or_die log "$base..$tip" \
        --format='%(trailers:key=Drive-Test-Waiver,valueonly,separator=%x00)')"
      # Strip NULs and all whitespace; any leftover char = a real non-empty trailer value.
      stripped="$(printf '%s' "$wvals" | tr -d '\000[:space:]')"
      [ -n "$stripped" ] && waived=true
    fi

    if [ "$has_test" = true ] || [ "$waived" = true ]; then
      emit true "impl-presence:$id" "$tip" "[]"
    else
      emit false "impl-presence:$id" "$tip" "[$(violation "slice:$id" "no-test-evidence" "$tip" "")]"
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
    # git-error-vs-verdict: a candidate R is a sha read from a review ARTIFACT (not a
    # ref the tool constructed). A non-resolving R = a stale/typoed artifact that binds
    # to no real commit = a legitimate "this candidate doesn't count" VERDICT → skip,
    # so one bad phase review can't false-block a later valid existential R. By contrast
    # `git diff` / `rev-list --count` failures (with an R that DID resolve) are genuine
    # git/IO errors → exit 2 via git_or_die. `merge-base --is-ancestor` nonzero=1 is the
    # "not an ancestor" verdict (skip); only rc>1 is a true error → exit 2.
    ship_clean=false
    for R in $candidate_R; do
      [ -n "$R" ] || continue
      # R must resolve as a commit. A non-resolving artifact sha is a verdict (skip),
      # NOT a git/IO error — it just means this review doesn't bind to a real commit.
      git rev-parse --verify --quiet "$R^{commit}" >/dev/null 2>&1 || continue
      # (a) R ancestor of tip. Nonzero = legitimate "not an ancestor" verdict → skip.
      # We distinguish that from a true error: --is-ancestor returns 0 (ancestor),
      # 1 (not ancestor), or >1 (error). Capture rc and only exit 2 on rc>1.
      anc_rc=0
      git merge-base --is-ancestor "$R" "$tip" 2>/dev/null || anc_rc=$?
      if [ "$anc_rc" -gt 1 ]; then
        echo "error: git merge-base --is-ancestor failed (rc=$anc_rc)" >&2
        exit 2
      fi
      [ "$anc_rc" -eq 0 ] || continue   # not an ancestor → this candidate doesn't apply
      # (c) R..tip ≤ 1 commit. A rev-list failure is a real git error → exit 2.
      ncommits="$(git_or_die rev-list --count "$R..$tip")"
      [ "$ncommits" -le 1 ] || continue
      # (b) changed files ⊆ allowlist. Capture diff output FIRST with an explicit
      # failure check — process-substitution does NOT propagate producer failure in
      # bash, so a swallowed `git diff` error would leave subset=true (false-clean).
      files="$(git_or_die diff --name-only "$R..$tip")"
      subset=true
      while IFS= read -r path; do
        [ -n "$path" ] || continue
        allowed=false
        for a in "${SHIP_LEDGER_ALLOWLIST[@]}"; do
          [ "$path" = "$a" ] && { allowed=true; break; }
        done
        [ "$allowed" = true ] || { subset=false; break; }
      done <<EOF
$files
EOF
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
    # git-error-vs-verdict: `for-each-ref` enumerating refs and `git diff`-style ref
    # resolution are genuine git ops — a failure is exit 2, NOT exit 0 clean (which
    # would swallow a broken repo into a false "nothing to audit"). `merge-base
    # --is-ancestor` nonzero=1 stays a legitimate "not merged in" verdict (skip);
    # only rc>1 is a true error → exit 2.
    #
    # Find the highest live phaseInt/<runId>/<P>.
    live_P=""; live_ref=""
    phase_refs="$(git_or_die for-each-ref --format='%(refname:short)' "refs/heads/phaseInt/$runId/")"
    while IFS= read -r ref; do
      [ -n "$ref" ] || continue
      p="${ref##*/}"
      case "$p" in (*[!0-9]*|'') continue;; esac
      if [ -z "$live_P" ] || [ "$p" -gt "$live_P" ]; then live_P="$p"; live_ref="$ref"; fi
    done <<EOF
$phase_refs
EOF

    if [ -z "$live_ref" ]; then
      emit true "audit" "" "[]"
    fi

    # The live ref came from for-each-ref, so it MUST resolve; a non-resolving ref here
    # is a genuine git error → exit 2 (not an empty-tip false verdict).
    if ! tip="$(rev "$live_ref")"; then
      echo "error: cannot resolve live phaseInt ref $live_ref" >&2; exit 2
    fi

    # Enumerate slice branches merged into live_ref. Slice refs: slice/<runId>/<id>.
    viol_arr=()
    slice_refs="$(git_or_die for-each-ref --format='%(refname:short)' "refs/heads/slice/$runId/")"
    while IFS= read -r sref; do
      [ -n "$sref" ] || continue
      id="${sref#slice/$runId/}"
      [ "$id" = "$sref" ] && continue
      # This slice ref came from for-each-ref, so it MUST resolve → non-resolve = error.
      if ! stip="$(rev "$sref")"; then
        echo "error: cannot resolve slice ref $sref" >&2; exit 2
      fi
      # Is this slice's tip an ancestor of the live phaseInt tip (i.e. merged in)?
      # Nonzero rc=1 = not merged in (verdict, skip); rc>1 = real error → exit 2.
      anc_rc=0
      git merge-base --is-ancestor "$stip" "$tip" 2>/dev/null || anc_rc=$?
      if [ "$anc_rc" -gt 1 ]; then
        echo "error: git merge-base --is-ancestor failed (rc=$anc_rc)" >&2; exit 2
      fi
      [ "$anc_rc" -eq 0 ] || continue   # not merged into the live phase → skip
      if ! v="$(check_scope_counts "slice:$id" "$id" "$stip")"; then
        viol_arr+=("$v")
      fi
    done <<EOF
$slice_refs
EOF

    if [ "${#viol_arr[@]:-0}" -eq 0 ]; then
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
