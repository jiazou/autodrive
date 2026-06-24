#!/usr/bin/env bash
# drive-conformance.sh — the keystone conformance checker for /drive enforcement.
#
# Pure function over git refs + SHA-bound review artifacts in RUN_DIR. NEVER reads
# state.json's `step`/`phaseReview` for the verdict (D1: git-truth, not state-trust).
#
# Usage:
#   drive-conformance.sh <RUN_DIR> --mode plan-gate | phasedesign-gate:<P> | slice-merge:<id> | phase-merge:<P> | impl-presence:<id> | ship | audit | checkpoint | state-lint
#
# Mode `state-lint` is the ONLY mode that reads state.json: it validates the routing
# fields resume keys on (D40). All other modes derive the verdict from git refs +
# review artifacts and NEVER read state.json (D1/D8).
#
# Stage 4c FINALIZE wiring (scope token `finalize`): `--mode ship`'s tip-binding
# candidate-R is the `review-finalize-N.md` artifact (the phase-integration review is
# demoted to a `no-phase-review` precondition — D17); `--mode checkpoint`'s `counters`
# carries a 6th key `finalizeRound` (bare int = `## AppliedEdits: yes` count over the
# review-finalize-*.md family; finalize is run-singleton, so not a per-phase map — D16);
# `--mode state-lint`'s stage enum includes `finalize` (D18).
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

# --- Ship-ledger allowlist: the EXACT files SHIP commits AFTER the last review.
#     Kept in sync with drive-ship.md (NOT the whole .harness/ dir — D12). Repo-root
#     TODO.md is promoted from finalize-todo.md in the same single ledger commit (D10). ---
SHIP_LEDGER_ALLOWLIST=(".harness/decisions.md" ".harness/followups.md" "TODO.md")

usage() {
  echo "usage: drive-conformance.sh <RUN_DIR> --mode plan-gate|phasedesign-gate:<P>|slice-merge:<id>|phase-merge:<P>|impl-presence:<id>|ship|audit|checkpoint|state-lint" >&2
}

# Emit the JSON result and exit. $1=clean(true|false) $2=mode $3=tip $4=violations-json-array
emit() {
  local clean="$1" mode="$2" tip="$3" viols="$4"
  printf '{"clean":%s,"mode":"%s","tip":"%s","violations":%s}\n' "$clean" "$mode" "$tip" "$viols"
  if [ "$clean" = "true" ]; then exit 0; else exit 1; fi
}

# Build one violation object. $1=scope $2=reason [$3=expected_sha $4=found_sha]
# jq (not printf) so a state.json-derived field (e.g. a corrupt slice-id KEY carrying a
# `"`, `\`, or control char) is JSON-escaped — the envelope stays valid at the corrupt-state
# path state-lint defends. Output is byte-identical to the old printf for metachar-free input.
violation() {
  local scope="$1" reason="$2" exp="${3:-}" found="${4:-}"
  jq -cn --arg scope "$scope" --arg reason "$reason" --arg exp "$exp" --arg found "$found" \
    '{scope:$scope,reason:$reason,expected_sha:$exp,found_sha:$found}'
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
    # -e || -L: a DANGLING higher-N review symlink (the `-e` test follows the link and
    # fails) must still COUNT as the highest round — skipping it would resolve a LOWER-N
    # file as `best`, and that lower round may be CONVERGED (a harden-regress round, or
    # any non-highest round whose verdict is not guaranteed FINDINGS) → a gate that should
    # block on the real (dangling/corrupt) highest round passes (fail-OPEN). Counting the
    # dangling file as `best` is fail-CLOSED: it is unreadable, so verdict_converged() and
    # reviewed_sha_of() both fail on it → the scope does NOT count → block.
    [ -e "$f" ] || [ -L "$f" ] || continue
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
  # Must exist and be non-empty; content is not inspected (real review OR a CODEX_UNAVAILABLE
  # note both satisfy). `-s` already implies existence, so no separate `-f` test is needed.
  [ -s "$f" ] || return 1
  return 0
}

# Highest redesign epoch R for phase $1, from $RUN_DIR/redesign-<P>-r*.marker names
# (the load-bearing data is the file NAME — I1). Echoes 0 when no marker exists.
highest_epoch() {
  local P="$1" best=0 f r
  for f in "$RUN_DIR"/redesign-"$P"-r*.marker; do
    # -e || -L: a DANGLING marker symlink (the `-e` test follows the link and fails)
    # must still COUNT its epoch — skipping it would resolve a LOWER epoch (fail-OPEN).
    [ -e "$f" ] || [ -L "$f" ] || continue
    r="${f##*-r}"; r="${r%.marker}"
    case "$r" in (*[!0-9]*|'') continue;; esac
    if [ "$r" -gt "$best" ]; then best="$r"; fi
  done
  printf '%s\n' "$best"
}

# Epoch numbers R that have a phasedesign<P>-r<R> ARTIFACT (review-phasedesign<P>-r<R>-N.md
# or codex-review-phasedesign<P>-r<R>.md) but NO matching redesign-<P>-r<R>.marker. A
# markerless epoch artifact is corruption / partial sweep / deleted marker — trusting only
# the marker would let highest_epoch() fall back to a LOWER epoch and pass the gate /
# count epoch 0 on stale artifacts (fail-OPEN in the exact mechanism this phase makes
# fail-closed). Echoes the sorted-unique unmarked R values, one per line (empty if none).
# $1=P
unmarked_epochs() {
  local P="$1" f core r out=""
  for f in "$RUN_DIR"/review-phasedesign"$P"-r*-*.md "$RUN_DIR"/codex-review-phasedesign"$P"-r*.md; do
    # -e || -L: a DANGLING epoch-suffixed dirent (broken symlink) is still corruption to
    # flag — skipping it would hide the markerless epoch and fail OPEN.
    [ -e "$f" ] || [ -L "$f" ] || continue
    core="${f##*/}"
    # strip the leading prefix down to "r<R>..."; both families share the -r<R> token.
    core="${core#review-phasedesign"$P"-r}"
    core="${core#codex-review-phasedesign"$P"-r}"
    r="${core%%-*}"          # codex sibling has no -N; review has -N — both leave R here
    r="${r%.md}"             # codex sibling: r<R>.md -> R
    case "$r" in (*[!0-9]*|'') continue;; esac
    [ -e "$RUN_DIR/redesign-$P-r$r.marker" ] && continue
    out="$out$r"$'\n'
  done
  printf '%s' "$out" | sort -un
}

# Extract the phase id <P> from a phasedesign epoch-artifact BASENAME — i.e. strip ONLY a
# trailing epoch/round suffix, anchored from the RIGHT, so a phase id that itself contains
# `-r<digits>` (e.g. `4-r1`) survives (a `%%-r*` split would mis-truncate it to `4`).
# Accepts either family AFTER the `review-phasedesign` / `codex-review-phasedesign` prefix
# is stripped (caller strips it):
#   review sibling:  <P>-r<R>-<N>   -> strip trailing -<N> (digits) then trailing -r<R>
#   codex sibling:   <P>-r<R>       -> strip trailing -r<R>
# Echoes <P> (empty if the suffix shape is absent — caller skips such names).
phase_of_pd_core() {
  local core="$1" tail
  # 1) review-family trailing round -<N> (all digits): peel it so step 2 sees -r<R> last.
  tail="${core##*-}"
  case "$tail" in (''|*[!0-9]*) ;; (*) core="${core%-*}";; esac
  # 2) the epoch token must now be the rightmost segment: -r<R> (R all digits).
  tail="${core##*-r}"
  case "$tail" in (''|*[!0-9]*) printf '%s' ""; return;; esac
  case "$core" in (*-r"$tail") printf '%s' "${core%-r$tail}";; (*) printf '%s' "";; esac
}

# Resolve the phase id <P> from a pd_key (= the round-file scope minus the `phasedesign`
# prefix, so `<P>` for epoch 0 or `<P>-r<R>` for epoch R) — MARKER-anchored, for the
# COUNTING path. A trailing `-r<R>` is the epoch suffix ONLY when redesign-<base>-r<R>.marker
# confirms the phase actually reached epoch R; otherwise the `-r<R>` belongs to the phase id
# itself (a literal epoch-0 phase like `4-r1`) and the key is returned unchanged. This is the
# opposite policy to the epoch-unmarked detector, which deliberately treats any trailing
# `-r<R>` as an epoch CLAIM and fails closed on a missing marker — so a deleted-marker
# corruption can't be reclassified into a benign phase id here. $1=pd_key
phase_of_pd_key() {
  local t="$1" r base
  r="${t##*-r}"
  # No trailing `-r…`, or the suffix isn't all-digits → t is the phase id as-is.
  [ "$r" = "$t" ] && { printf '%s' "$t"; return; }
  case "$r" in (*[!0-9]*|'') printf '%s' "$t"; return;; esac
  base="${t%-r$r}"
  [ -n "$base" ] || { printf '%s' "$t"; return; }
  # Epoch only if the marker backs it; else the `-r<R>` is part of the phase id.
  if [ -e "$RUN_DIR/redesign-$base-r$r.marker" ] || [ -L "$RUN_DIR/redesign-$base-r$r.marker" ]; then
    printf '%s' "$base"
  else
    printf '%s' "$t"
  fi
}

# Count exact-match lines of key $2 in newline-list $1. Echoes the count (0 if none).
count_in_list() {
  local c
  c="$(printf '%s' "$1" | grep -cxF -- "$2")" || true
  printf '%s' "$c"
}

# Build a JSON object from "key value" lines on stdin. Keys are scope tokens /
# phase ids / slice ids (no quotes or backslashes to escape).
json_from_pairs() {
  local out="" k v
  while read -r k v; do
    [ -n "$k" ] || continue
    out="$out${out:+,}\"$k\":$v"
  done
  printf '{%s}' "$out"
}

# Read `reviewed-sha:` (first match) from a review file; echo sha or empty. $1=file
reviewed_sha_of() {
  local f="$1" line
  line="$(grep -m1 -E '^reviewed-sha:[[:space:]]*[0-9a-fA-F]{40}[[:space:]]*$' "$f" 2>/dev/null || true)"
  [ -n "$line" ] || return 1
  line="${line#reviewed-sha:}"
  # trim whitespace
  line="${line//[[:space:]]/}"
  # Lowercase: the regex tolerates uppercase hex but git tips are always lowercase, so an
  # otherwise-correct review written with an uppercase sha would spuriously sha-mismatch.
  line="$(printf '%s' "$line" | tr 'A-F' 'a-f')"
  printf '%s\n' "$line"
}

# Does the highest-N review for scope have CONVERGED verdict? rc0 yes. $1=file
# Decide on the FIRST `## Verdict:` line ONLY — the schema puts the real verdict first
# (drive-review.md). A later standalone `## Verdict: CONVERGED` heading elsewhere in a
# FINDINGS file (e.g. quoting a prior round) must NOT flip the verdict to converged.
verdict_converged() {
  local line
  line="$(grep -m1 -E '^## Verdict:' "$1" 2>/dev/null || true)"
  [ -n "$line" ] || return 1
  printf '%s\n' "$line" | grep -qE '^## Verdict:[[:space:]]*CONVERGED[[:space:]]*$'
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

  phasedesign-gate:*)
    # Enforces the per-phase DESIGN review (Tier 2). Like plan-gate, no git tip — it audits
    # the design DOC design-phase<P>.md. Epoch-aware (I5/D9): the redesign epoch rides the
    # SCOPE TOKEN — phasedesign<P> for epoch 0, phasedesign<P>-r<R> for the current epoch
    # R = highest redesign-<P>-r*.marker — so a stale prior-epoch CONVERGED pair cannot
    # satisfy the gate after a redesign. Clean iff the current epoch's highest-N
    # review-<scope>-N.md is CONVERGED AND its codex-review-<scope>.md sibling exists.
    P="${MODE_ARG#phasedesign-gate:}"
    [ -n "$P" ] || { usage; exit 2; }
    R="$(highest_epoch "$P")"
    scope="phasedesign$P"
    if [ "$R" -gt 0 ]; then scope="phasedesign$P-r$R"; fi
    rf=""; viols=""
    # Fail closed on a markerless epoch artifact (corruption / deleted marker): an
    # epoch-suffixed review/codex file with no redesign-<P>-r<R>.marker would otherwise
    # let highest_epoch() resolve a LOWER epoch and pass on stale artifacts. Take
    # precedence over the per-scope checks — the resolved scope itself is untrustworthy.
    unmarked="$(unmarked_epochs "$P")"
    if [ -n "$unmarked" ]; then
      viols="$(violation "phasedesign$P" "epoch-unmarked")"
    elif ! rf="$(highest_review_file "$scope")"; then
      viols="$(violation "$scope" "no-review")"
    elif ! verdict_converged "$rf"; then
      viols="$(violation "$scope" "verdict-not-converged")"
    elif ! codex_present "$scope"; then
      viols="$(violation "$scope" "no-codex")"
    fi
    if [ -z "$viols" ]; then emit true "phasedesign-gate:$P" "" "[]"; else emit false "phasedesign-gate:$P" "" "[$viols]"; fi
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

    # test? — ANY NON-DELETION change to a runnable test path in base..tip. `--diff-filter=d`
    # (lowercase = EXCLUDE deletions) so a DELETED test path does NOT count (deleting
    # tests/test_auth.py must not satisfy the invariant), while A/M/R/C/T all do. Uppercase `AM`
    # would over-block: git classes a renamed/copied test as R/C, so it would false-DENY a slice
    # that adds coverage by renaming a file INTO a test path. With `--name-only` a rename prints
    # only the DESTINATION, so a rename AWAY from a test path is not counted, a rename INTO one is.
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
    # Two-stage ship gate (mirrors docs/drive-enforcement.md:63-74):
    # (b-i) PRECONDITION: ≥1 COUNTING phase-integration review must exist — a converged,
    #   SHA-bound, codex-backed review-phase* (else "no-phase-review"); a run that never
    #   produced one never legitimately reached finalize.
    # (b-ii) TERMINAL candidate-R: the CONVERGED finalize artifact (highest-N
    #   review-finalize-N.md, CONVERGED, with codex-review-finalize.md), whose reviewed-sha
    #   R must satisfy (a) R is ancestor of tip, (b) git diff R..tip ⊆ the ship-ledger
    #   allowlist, (c) R..tip is at most one commit. No converged finalize → candidate_R=""
    #   → ship blocks (no-review).
    if ! tip="$(rev "$featureBranch")"; then
      echo "error: cannot resolve featureBranch $featureBranch" >&2; exit 2
    fi

    # Gather all counting phase reviews: highest-N review-phase<P>-N.md that is CONVERGED,
    # has a reviewed-sha, and has codex-review-phase<P>.md. Collect their R shas.
    # (No associative arrays — macOS ships bash 3.2; dedup via a space-delimited string.)
    candidate_R=""
    seen_phase=" "
    for f in "$RUN_DIR"/review-phase*-*.md; do
      # This scan only discovers WHICH phase scopes exist; the counting verdict for each is
      # re-derived via highest_review_file. A DANGLING dirent here is safe to skip
      # (fail-CLOSED): ship requires a POSITIVE existential R, so dropping a candidate
      # can only WITHHOLD a candidate → ship blocks, never passes. Skipping strictly tightens.
      [ -e "$f" ] || continue
      base="${f##*/}"                       # review-phase<P>-<N>.md
      rest="${base#review-}"                # phase<P>-<N>.md
      scope="${rest%-*.md}"                 # phase<P>
      # The `review-phase*-*.md` glob ALSO matches `review-phasedesign<P>-N.md` (a per-phase
      # DESIGN-DOC review). A design review must NEVER count as the phase-INTEGRATION code
      # review at ship — exclude it explicitly so the ship gate does not silently depend on
      # the convention that phasedesign reviews omit `reviewed-sha`.
      case "$scope" in phasedesign*) continue;; esac
      case "$seen_phase" in (*" $scope "*) continue;; esac
      seen_phase="$seen_phase$scope "
      rf="$(highest_review_file "$scope")" || continue
      verdict_converged "$rf" || continue
      rsha="$(reviewed_sha_of "$rf")" || continue
      codex_present "$scope" || continue
      candidate_R="$candidate_R$rsha "
    done

    # (b-i) Precondition: ≥1 COUNTING phase-integration review must exist (D17). Key off the
    # COUNTING set (candidate_R: post verdict_converged/reviewed_sha_of/codex_present), NOT
    # seen_phase — seen_phase is set BEFORE those checks, so it proves only a review-phase*
    # PATHNAME exists, which a stale/FINDINGS/missing-codex artifact would forge. A run that
    # never produced a counting phase review never legitimately reached finalize.
    # candidate_R still holds the COUNTING phase Rs here — b-ii overwrites it below.
    if [ -z "$candidate_R" ]; then
      emit false "ship" "$tip" "[$(violation "ship" "no-phase-review" "$tip" "")]"
    fi

    # (b-ii) The TERMINAL tip-binding candidate-R is the finalize artifact (D17): finalize's
    # reviewed-sha == post-finalize tip, so it REPLACES the phase Rs as the candidate set the
    # (a)(b)(c) test runs on. The phase Rs are consumed only by the b-i precondition above.
    # No converged finalize artifact → candidate_R="" → ship blocks below (no-review).
    fin_rf="$(highest_review_file finalize)" || true
    if [ -n "$fin_rf" ] && verdict_converged "$fin_rf" \
         && fin_rsha="$(reviewed_sha_of "$fin_rf")" && codex_present finalize; then
      candidate_R="$fin_rsha "
    else
      candidate_R=""
    fi

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

  checkpoint)
    # The checkpoint_complete safe-boundary proof (I4): a pure function over git refs +
    # durable RUN_DIR artifacts — state.json is NEVER a proof input. Envelope gains a
    # "counters" key (this mode only): the artifact-derived I3 values that resume-repair
    # and the rebirth handoff read (single computation point).
    if ! tip="$(rev "$featureBranch")"; then
      echo "error: cannot resolve featureBranch $featureBranch" >&2; exit 2
    fi
    viol_arr=()

    # (a) No open in-flight marker. An open marker is "not safe", full stop — the proof
    # never probes liveness and never waits. `-e || -L` so a DANGLING symlink dirent
    # (the `-e` test follows the link and fails) still reads as an open marker, not clean:
    # the `-L` keeps the literal-glob guard while failing closed on any actual dirent.
    for f in "$RUN_DIR"/inflight-*.marker; do
      [ -e "$f" ] || [ -L "$f" ] || continue
      viol_arr+=("$(violation "${f##*/}" "inflight-open")")
    done

    # (b) Run refs resolve & relate. Non-resolve of an enumerated ref = exit 2 (same
    # convention as audit). Every phaseInt ref must relate to drive/<runId> by ancestry
    # in ONE direction — tip ancestor of drive (completed/advanced) OR drive ancestor of
    # tip (live) — else phaseInt-divergent. NO numeric phase-id ordering: ids come from
    # design.md ## Phases and may be non-numeric (e.g. 4a); the ancestry test needs none.
    # merge-base --is-ancestor rc 1 = verdict; rc > 1 = real git error → exit 2.
    slice_refs="$(git_or_die for-each-ref --format='%(refname:short)' "refs/heads/slice/$runId/")"
    while IFS= read -r sref; do
      [ -n "$sref" ] || continue
      if ! rev "$sref" >/dev/null; then
        echo "error: cannot resolve slice ref $sref" >&2; exit 2
      fi
    done <<EOF
$slice_refs
EOF
    phase_refs="$(git_or_die for-each-ref --format='%(refname:short)' "refs/heads/phaseInt/$runId/")"
    while IFS= read -r pref; do
      [ -n "$pref" ] || continue
      if ! ptip="$(rev "$pref")"; then
        echo "error: cannot resolve phaseInt ref $pref" >&2; exit 2
      fi
      anc_rc=0
      git merge-base --is-ancestor "$ptip" "$tip" 2>/dev/null || anc_rc=$?
      if [ "$anc_rc" -gt 1 ]; then
        echo "error: git merge-base --is-ancestor failed (rc=$anc_rc)" >&2; exit 2
      fi
      [ "$anc_rc" -ne 0 ] || continue   # completed/advanced phase
      anc_rc=0
      git merge-base --is-ancestor "$tip" "$ptip" 2>/dev/null || anc_rc=$?
      if [ "$anc_rc" -gt 1 ]; then
        echo "error: git merge-base --is-ancestor failed (rc=$anc_rc)" >&2; exit 2
      fi
      if [ "$anc_rc" -ne 0 ]; then
        viol_arr+=("$(violation "$pref" "phaseInt-divergent" "$tip" "$ptip")")
      fi
    done <<EOF
$phase_refs
EOF

    # (c) Counter artifacts well-formed + per-counter reconstruction (the I3 rules,
    # artifact side only — no max(state,…) here). Violations here: unparseable-review,
    # unparseable-harden, epoch-gap, regress-mismatch, and epoch-unmarked (an
    # epoch-suffixed phasedesign artifact with no redesign-<P>-r<R>.marker — fail closed).
    # Round files are review-<scope>-N.md with pure-integer N; classify the scope:
    # design (not a counter) | phasedesign<P>[-r<R>] | phase<P> | else a slice id.
    slice_keys=""; phase_keys=""; pd_keys=""; finalize_yes_count=0
    for f in "$RUN_DIR"/review-*.md; do
      # -e || -L: a DANGLING review dirent is corruption, not absence — skipping it would
      # UNDERCOUNT reviewCount/phaseReviewRound (the counters the resume path consumes) and
      # let the checkpoint read CLEAN on a corrupt artifact. Counting it is fail-CLOSED: the
      # `grep '^## Verdict:'` below fails on the unreadable file → unparseable-review violation.
      [ -e "$f" ] || [ -L "$f" ] || continue
      base="${f##*/}"; core="${base#review-}"; core="${core%.md}"
      n="${core##*-}"
      case "$n" in (*[!0-9]*|'') continue;; esac   # not a round file
      scope="${core%-*}"
      [ -n "$scope" ] || continue
      if ! grep -qE '^## Verdict:' "$f"; then
        viol_arr+=("$(violation "$base" "unparseable-review")")
      fi
      case "$scope" in
        (design) ;;
        (phasedesign?*) pd_keys="$pd_keys${scope#phasedesign}"$'\n' ;;
        (phase?*)       phase_keys="$phase_keys${scope#phase}"$'\n' ;;
        (finalize)
          # finalize is run-singleton — NOT a slice (no phantom slice/<runId>/finalize branch).
          # Count its `AppliedEdits: yes` fix rounds for finalizeRound (B5); FAIL CLOSED on a
          # missing AppliedEdits: line, mirroring the harden unparseable-harden path exactly
          # (a finalize fix-round artifact MUST carry the marker; a missing one would silently
          # undercount the cap/re-dispatch guard). A `pending`/`no` line is present-but-not-yes
          # → not a violation, just not counted.
          if ! grep -qE '^(##[[:space:]]*)?AppliedEdits:' "$f"; then
            viol_arr+=("$(violation "$base" "unparseable-finalize")")
          elif grep -qE '^(##[[:space:]]*)?AppliedEdits:[[:space:]]*yes[[:space:]]*$' "$f"; then
            finalize_yes_count=$((finalize_yes_count + 1))
          fi ;;
        (*)             slice_keys="$slice_keys$scope"$'\n' ;;
      esac
    done

    # harden-<P>-N.md: must carry an AppliedEdits: line; only `yes` counts a fix round
    # (a confirming clean audit writes `no` and is free — cap-3 is on fix rounds).
    harden_all=""; harden_yes=""
    for f in "$RUN_DIR"/harden-*.md; do
      # -e || -L: a DANGLING harden dirent is corruption — skipping it would erase a fix
      # round (undercounting hardenRound) AND drop its yes-count from the regress-mismatch
      # check below (suppressing a real mismatch), letting the checkpoint read CLEAN on a
      # corrupt artifact. Counting it is fail-CLOSED: the `grep 'AppliedEdits:'` fails on
      # the unreadable file → unparseable-harden violation.
      [ -e "$f" ] || [ -L "$f" ] || continue
      base="${f##*/}"; core="${base#harden-}"; core="${core%.md}"
      n="${core##*-}"
      case "$n" in (*[!0-9]*|'') continue;; esac
      P="${core%-*}"
      [ -n "$P" ] || continue
      harden_all="$harden_all$P"$'\n'
      if ! grep -qE '^(##[[:space:]]*)?AppliedEdits:' "$f"; then
        viol_arr+=("$(violation "$base" "unparseable-harden")")
      elif grep -qE '^(##[[:space:]]*)?AppliedEdits:[[:space:]]*yes[[:space:]]*$' "$f"; then
        harden_yes="$harden_yes$P"$'\n'
      fi
    done

    # redesigns = HIGHEST epoch R per phase (not file count — epochs are sequential, so
    # marker rN proves N redesigns even if an intermediate marker was lost; the proof
    # flags the gap). Gapless r1..rR required, else epoch-gap.
    rd_phases=""
    for f in "$RUN_DIR"/redesign-*-r*.marker; do
      # -e || -L: a DANGLING marker still proves its epoch (highest_epoch/epoch-gap below).
      [ -e "$f" ] || [ -L "$f" ] || continue
      core="${f##*/}"; core="${core#redesign-}"; core="${core%.marker}"
      r="${core##*-r}"
      case "$r" in (*[!0-9]*|'') continue;; esac
      P="${core%-r$r}"
      [ -n "$P" ] || continue
      rd_phases="$rd_phases$P"$'\n'
    done
    rd_pairs=""
    for P in $(printf '%s' "$rd_phases" | sort -u); do
      R="$(highest_epoch "$P")"
      k=1
      while [ "$k" -le "$R" ]; do
        if [ ! -e "$RUN_DIR/redesign-$P-r$k.marker" ]; then
          viol_arr+=("$(violation "redesign-$P" "epoch-gap")")
          break
        fi
        k=$((k+1))
      done
      rd_pairs="$rd_pairs$P $R"$'\n'
    done
    rdj="$(printf '%s' "$rd_pairs" | json_from_pairs)"

    # hardenRound[<P>] = count of AppliedEdits: yes files (I3 rule 3).
    hr_pairs=""
    for P in $(printf '%s' "$harden_all" | sort -u); do
      hr_pairs="$hr_pairs$P $(count_in_list "$harden_yes" "$P")"$'\n'
    done
    hrj="$(printf '%s' "$hr_pairs" | json_from_pairs)"

    # phaseReviewRound[<P>] = R_conf = review-phase<P> file count MINUS AppliedEdits: yes
    # harden files (I3 rule 2 — harden-regress writes into the same review-phase<P>-N.md
    # family without incrementing the round; each fix round's `yes` audit is its durable
    # 1:1 marker). yes-count > review-file count is malformed → regress-mismatch, value 0.
    prr_pairs=""
    for P in $(printf '%s\n%s' "$phase_keys" "$harden_all" | sort -u); do
      prc="$(count_in_list "$phase_keys" "$P")"
      yc="$(count_in_list "$harden_yes" "$P")"
      if [ "$yc" -gt "$prc" ]; then
        viol_arr+=("$(violation "phase$P" "regress-mismatch")")
        prr_pairs="$prr_pairs$P 0"$'\n'
      else
        prr_pairs="$prr_pairs$P $((prc - yc))"$'\n'
      fi
    done
    prrj="$(printf '%s' "$prr_pairs" | json_from_pairs)"

    # epoch-unmarked: an epoch-suffixed phasedesign artifact (review or codex sibling)
    # with NO matching redesign-<P>-r<R>.marker (corruption / partial sweep / deleted
    # marker). Without this, highest_epoch() would fall back to a LOWER epoch and the
    # round counts would run on stale artifacts (a fail-OPEN). Derive the phase set from
    # BOTH artifact families (a markerless codex-only sibling is still corruption to flag).
    pdr_phases=""
    for f in "$RUN_DIR"/review-phasedesign*-r*-*.md "$RUN_DIR"/codex-review-phasedesign*-r*.md; do
      # -e || -L: a DANGLING epoch-suffixed dirent still belongs to a phase whose markerless
      # epoch unmarked_epochs() must flag — skipping it would fail OPEN.
      [ -e "$f" ] || [ -L "$f" ] || continue
      core="${f##*/}"
      core="${core#review-phasedesign}"
      core="${core#codex-review-phasedesign}"
      core="${core%.md}"
      # phase_of_pd_core strips ONLY the trailing -r<R>[ -<N>] suffix (anchored right) so a
      # phase id containing `-r` (e.g. `4-r1`) is not mis-truncated by a `%%-r*` split.
      P="$(phase_of_pd_core "$core")"
      [ -n "$P" ] && pdr_phases="$pdr_phases$P"$'\n'
    done
    for P in $(printf '%s' "$pdr_phases" | sort -u); do
      if [ -n "$(unmarked_epochs "$P")" ]; then
        viol_arr+=("$(violation "phasedesign$P" "epoch-unmarked")")
      fi
    done

    # phaseDesignRound[<P>] = round files of the CURRENT epoch only (I3 rule 5): scope
    # phasedesign<P> when redesigns == 0, else phasedesign<P>-r<R> for the highest R —
    # a redesign legitimately resets the round to 0 with a fresh cap-8.
    # Resolve each pd_key to its phase id MARKER-anchored (phase_of_pd_key): a trailing
    # `-r<R>` is the epoch suffix only when redesign-<P>-r<R>.marker exists, else the key is a
    # literal epoch-0 phase id (e.g. `4-r1`) and survives intact — so `4-r1` is counted under
    # `4-r1`, not mis-keyed to `4`.
    pd_phases=""
    for t in $(printf '%s' "$pd_keys" | sort -u); do
      pd_phases="$pd_phases$(phase_of_pd_key "$t")"$'\n'
    done
    pdr_pairs=""
    for P in $(printf '%s\n%s' "$pd_phases" "$rd_phases" | sort -u); do
      R="$(highest_epoch "$P")"
      tok="$P"
      if [ "$R" -gt 0 ]; then tok="$P-r$R"; fi
      pdr_pairs="$pdr_pairs$P $(count_in_list "$pd_keys" "$tok")"$'\n'
    done
    pdrj="$(printf '%s' "$pdr_pairs" | json_from_pairs)"

    # reviewCount[<id>] = count of review-<id>-N.md, pure-integer N (I3 rule 1).
    rcj="$(printf '%s' "$slice_keys" | sort | uniq -c | awk '{print $2, $1}' | json_from_pairs)"

    # finalizeRound = count of review-finalize-*.md with `AppliedEdits: yes` (B5). A bare
    # integer (finalize is run-singleton), not a per-phase map — matches state.finalizeRound.
    frj="$finalize_yes_count"
    counters="{\"redesigns\":$rdj,\"phaseDesignRound\":$pdrj,\"phaseReviewRound\":$prrj,\"hardenRound\":$hrj,\"reviewCount\":$rcj,\"finalizeRound\":$frj}"
    if [ "${#viol_arr[@]:-0}" -eq 0 ]; then
      printf '{"clean":true,"mode":"checkpoint","tip":"%s","violations":[],"counters":%s}\n' "$tip" "$counters"
      exit 0
    else
      joined="$(IFS=,; echo "${viol_arr[*]}")"
      printf '{"clean":false,"mode":"checkpoint","tip":"%s","violations":[%s],"counters":%s}\n' "$tip" "$joined" "$counters"
      exit 1
    fi
    ;;

  audit)
    # Scoped to LIVE phaseInt refs only. Live = drive/<runId> is an ancestor of the ref
    # tip (the phase is built on the current base; EQUAL tips audit as live — re-auditing
    # a just-advanced phase is harmless since its reviews are gate-guaranteed); a ref
    # whose tip is a STRICT ancestor of drive/<runId> is a completed phase → skipped
    # (guaranteed by phase-merge + ship gates). Selection is the D18 ancestry rule — NO
    # numeric phase-id ordering (ids come from design.md ## Phases and may be
    # non-numeric, e.g. 4a). A ref related in NEITHER direction is divergent → not
    # audited here (--mode checkpoint flags it as phaseInt-divergent). Report slices
    # merged into each live ref that lack a counting review. If no live phaseInt, clean.
    #
    # git-error-vs-verdict: `for-each-ref` enumerating refs and resolving an enumerated
    # ref are genuine git ops — a failure is exit 2, NOT exit 0 clean (which would
    # swallow a broken repo into a false "nothing to audit"). `merge-base --is-ancestor`
    # nonzero=1 stays a legitimate verdict (skip); only rc>1 is a true error → exit 2.
    phase_refs="$(git_or_die for-each-ref --format='%(refname:short)' "refs/heads/phaseInt/$runId/")"
    drive_tip=""
    if [ -n "$phase_refs" ]; then
      # Needed only to CLASSIFY refs; phaseInt refs with no resolvable drive/<runId>
      # is a broken run → exit 2.
      if ! drive_tip="$(rev "$featureBranch")"; then
        echo "error: cannot resolve featureBranch $featureBranch" >&2; exit 2
      fi
    fi

    viol_arr=()
    audit_tip=""
    # Dedup audited slice ids ACROSS the live-ref loop: a just-advanced phase (equal tip
    # = live per D20) plus the next live phase can share a merged slice, which would
    # otherwise emit duplicate violation objects (the raw JSON is the human-facing
    # evidence at a STOP). Same space-delimited-string dedup as ship mode's seen_phase.
    seen_slice=" "
    slice_refs="$(git_or_die for-each-ref --format='%(refname:short)' "refs/heads/slice/$runId/")"
    while IFS= read -r pref; do
      [ -n "$pref" ] || continue
      # An enumerated ref MUST resolve; a non-resolving ref here is a genuine git
      # error → exit 2 (not an empty-tip false verdict).
      if ! ptip="$(rev "$pref")"; then
        echo "error: cannot resolve phaseInt ref $pref" >&2; exit 2
      fi
      # live first, so EQUAL tips classify live (not completed): completed = strict.
      anc_rc=0
      git merge-base --is-ancestor "$drive_tip" "$ptip" 2>/dev/null || anc_rc=$?
      if [ "$anc_rc" -gt 1 ]; then
        echo "error: git merge-base --is-ancestor failed (rc=$anc_rc)" >&2; exit 2
      fi
      [ "$anc_rc" -eq 0 ] || continue   # completed (strict ancestor) or divergent → skip
      [ -n "$audit_tip" ] || audit_tip="$ptip"
      # Enumerate slice branches merged into THIS live ref. Slice refs: slice/<runId>/<id>.
      while IFS= read -r sref; do
        [ -n "$sref" ] || continue
        id="${sref#slice/$runId/}"
        [ "$id" = "$sref" ] && continue
        if ! stip="$(rev "$sref")"; then
          echo "error: cannot resolve slice ref $sref" >&2; exit 2
        fi
        # Merged in = slice tip is an ancestor of the live phaseInt tip.
        anc_rc=0
        git merge-base --is-ancestor "$stip" "$ptip" 2>/dev/null || anc_rc=$?
        if [ "$anc_rc" -gt 1 ]; then
          echo "error: git merge-base --is-ancestor failed (rc=$anc_rc)" >&2; exit 2
        fi
        [ "$anc_rc" -eq 0 ] || continue   # not merged into this live phase → skip
        # already audited via another live ref? slice ids are unique → audit once.
        case "$seen_slice" in (*" $id "*) continue;; esac
        seen_slice="$seen_slice$id "
        if ! v="$(check_scope_counts "slice:$id" "$id" "$stip")"; then
          viol_arr+=("$v")
        fi
      done <<EOF_SLICES
$slice_refs
EOF_SLICES
    done <<EOF_PHASES
$phase_refs
EOF_PHASES

    if [ -z "$audit_tip" ]; then
      emit true "audit" "" "[]"
    fi
    if [ "${#viol_arr[@]:-0}" -eq 0 ]; then
      emit true "audit" "$audit_tip" "[]"
    else
      joined="$(IFS=,; echo "${viol_arr[*]}")"
      emit false "audit" "$audit_tip" "[$joined]"
    fi
    ;;

  state-lint)
    # The ONLY mode that reads state.json (D40): validate the load-bearing routing fields
    # resume keys on are PRESENT + MEANINGFULLY ROUTABLE (not bare type checks). state.json
    # is a resume HINT, never a proof input — but a corrupt/unroutable hint must fail closed
    # at the rebirth handoff/resume, so violations exit 1 (a verdict), and only true
    # usage/IO/git error is exit 2. `tip` = current drive/<runId> rev for record (a
    # non-resolving featureBranch is a git/IO error -> exit 2).
    if ! tip="$(rev "$featureBranch")"; then
      echo "error: cannot resolve featureBranch $featureBranch" >&2; exit 2
    fi
    SJ="$RUN_DIR/state.json"
    [ -f "$SJ" ] || { echo "error: state.json not found: $SJ" >&2; exit 2; }
    viol_arr=()

    # (1) state.json parses as JSON AND its root is an OBJECT. The gate requires
    # `type == "object"`, not bare `jq -e .` — a parseable-but-non-object root (a JSON
    # array `[…]` or scalar `42`) is valid JSON yet every later `.<field>` index crashes
    # jq (exit 5, no envelope). A corrupt/non-object file is a VERDICT the handoff fails
    # closed on (exit 1 unparseable-state), NOT a usage error (exit 2) and NEVER a crash.
    if ! jq -e 'type == "object"' "$SJ" >/dev/null 2>&1; then
      printf '{"clean":false,"mode":"state-lint","tip":"%s","violations":[%s]}\n' \
        "$tip" "$(violation "state.json" "unparseable-state")"
      exit 1
    fi

    # (2) Routing fields present + meaningfully routable. stage drives the phaseList check:
    # an empty phaseList is well-formed-empty at premises/plan but UNROUTABLE once executing.
    stage="$(jq -r '.stage // ""' "$SJ")"

    # stage must be one of the real pipeline stages — an out-of-enum stage is an
    # unroutable hint (a resume can't place the run). The enum is the state.json
    # template's stage values: premises, plan, execute, finalize, verify, ship, done
    # (finalize = Stage 4c, the cross-slice contract with drive.md — B4/D18).
    case "$stage" in
      premises|plan|execute|finalize|verify|ship|done) ;;
      *) viol_arr+=("$(violation "stage" "stage-malformed")") ;;
    esac

    # phaseList: a non-empty array of REF-SAFE phase-id strings — but an empty/absent
    # phaseList is allowed ONLY while stage ∈ {premises, plan}. Anything else (execute,
    # verify, ship, done, or an unknown stage) with no routable phases is malformed.
    # Each element must match the phase-id grammar `^[0-9]+[a-z]?$` (e.g. `1`, `2`, `4a`):
    # a digit run with an optional lowercase-letter epoch suffix. A non-empty-but-unsafe
    # value (`"bad ref name"` with spaces, slashes, etc.) is NOT routable — it forms an
    # invalid `phaseInt/<runId>/<P>` git ref and breaks conformance scope-token parsing.
    pl_ok="$(jq -r '
      if (.phaseList | type) != "array" then "notarray"
      elif (.phaseList | length) == 0 then "empty"
      elif ([.phaseList[] | select((type != "string") or (test("^[0-9]+[a-z]?$") | not))] | length) > 0 then "badelem"
      else "ok" end' "$SJ")"
    case "$pl_ok" in
      ok) ;;
      empty)
        case "$stage" in
          premises|plan) ;;   # well-formed-empty early run
          *) viol_arr+=("$(violation "phaseList" "phaselist-malformed")") ;;
        esac ;;
      *) viol_arr+=("$(violation "phaseList" "phaselist-malformed")") ;;
    esac

    # slices: the routing CONTAINER must be an object; each value must be meaningfully
    # routable —
    #   step  ∈ {queued, implementing, awaiting_review, needs_fix, converged, blocked}
    #   owns  = a NON-EMPTY array of strings
    #   deps  = an array (possibly empty) of slice-id strings — each element must match the
    #           same `^[0-9]+[a-z]?\.[0-9]+$` grammar as a slice-id KEY, since /drive
    #           dispatches on CONVERGED deps to look up sibling slices.
    # The slice-id KEY must also be ref-safe: it forms `slice/<runId>/<id>` and a
    # conformance scope token, so it must match `^[0-9]+[a-z]?\.[0-9]+$` (phase-id `.`
    # slice number, e.g. `1.2`, `4.3`). A key with a space/slash/special char (`"1 bad"`)
    # is unroutable. A non-object slice value (scalar/array/bool/null) is unroutable too.
    # Either condition -> one `slice-routing-malformed` PER malformed slice, scoped to the
    # slice id (D44).
    # The container itself: an empty `{}` is always legitimate (a run may not have
    # designed slices yet); a non-object container (null/array/scalar/missing) is a
    # `slices-malformed` violation once the run is past plan (stage ∉ {premises, plan}) —
    # at premises/plan it is well-formed-absent like an empty phaseList.
    sl_type="$(jq -r '.slices | type' "$SJ")"
    if [ "$sl_type" = "object" ]; then
      # NUL-delimit each malformed key: an empty-string key (`"": {...}`) or a
      # newline-containing key is itself unroutable (fails the slice-id grammar) and must
      # NOT be skipped — a newline-split loop would drop an empty key (false-clean) or split
      # a newline key into fragments. NUL round-trips both losslessly.
      while IFS= read -r -d '' sid; do
        viol_arr+=("$(violation "$sid" "slice-routing-malformed")")
      done < <(jq -j '
        ["queued","implementing","awaiting_review","needs_fix","converged","blocked"] as $steps
        | .slices | to_entries[] | . as $e
        | select(
            (($e.key | test("^[0-9]+[a-z]?\\.[0-9]+$") | not))
            or (($e.value | type) != "object")
            or (($e.value.step | type) != "string")
            or (($e.value.step) as $s | $steps | index($s) | not)
            or (($e.value.owns | type) != "array")
            or (($e.value.owns | length) == 0)
            or ([$e.value.owns[] | select(type != "string")] | length > 0)
            or (($e.value.deps | type) != "array")
            or ([$e.value.deps[] | select((type != "string") or (test("^[0-9]+[a-z]?\\.[0-9]+$") | not))] | length > 0)
          )
        | $e.key, "\u0000"' "$SJ")
    else
      case "$stage" in
        premises|plan) ;;   # well-formed-absent before slices are designed
        *) viol_arr+=("$(violation "slices" "slices-malformed")") ;;
      esac
    fi

    # verify: an object with an `attempts` array.
    if [ "$(jq -r '((.verify | type) == "object") and ((.verify.attempts | type) == "array")' "$SJ")" != "true" ]; then
      viol_arr+=("$(violation "verify" "verify-malformed")")
    fi

    # ship: an object with the suite/conformance/prUrl KEYS present (any value incl. null —
    # a not-yet-shipped run has suite:null; the KEYS must exist).
    if [ "$(jq -r '((.ship | type) == "object") and (.ship | has("suite") and has("conformance") and has("prUrl"))' "$SJ")" != "true" ]; then
      viol_arr+=("$(violation "ship" "ship-malformed")")
    fi

    # waiting: BOTH resume (§ Run setup & resume) and the stop hook BRANCH on this field —
    # `waiting=="rebirth"` is the re-proven CONTINUE; any other truthy value is a human
    # pause; null/absent means autonomous. A malformed `waiting` misroutes both consumers,
    # so it must fail closed here. The canonical shape (drive.md I1 / pause routine): null,
    # OR one of the bare reasons `gateA`/`gateB`/`rebirth`, OR a prefixed reason
    # `stop:<short>` / `ask:<header>`. A non-null-non-string value, or a string outside this
    # grammar, is `waiting-malformed`. (Absent ≡ null via `.waiting`.)
    if [ "$(jq -r '
      (.waiting) as $w
      | if $w == null then "ok"
        elif ($w | type) != "string" then "bad"
        elif ($w | test("^(gateA|gateB|rebirth|stop:.+|ask:.+)$")) then "ok"
        else "bad" end' "$SJ")" != "ok" ]; then
      viol_arr+=("$(violation "waiting" "waiting-malformed")")
    fi

    if [ "${#viol_arr[@]:-0}" -eq 0 ]; then
      printf '{"clean":true,"mode":"state-lint","tip":"%s","violations":[]}\n' "$tip"
      exit 0
    else
      joined="$(IFS=,; echo "${viol_arr[*]}")"
      printf '{"clean":false,"mode":"state-lint","tip":"%s","violations":[%s]}\n' "$tip" "$joined"
      exit 1
    fi
    ;;

  *)
    usage; exit 2
    ;;
esac
