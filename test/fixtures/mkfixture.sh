#!/usr/bin/env bash
# mkfixture.sh — build self-contained, hermetic throwaway git repos + RUN_DIRs for the
# drive-conformance.sh test suite. Each fixture is a real git repo (real commits so
# rev-parse / merge-base / diff resolve) paired with a RUN_DIR of review artifacts.
#
# Usage:  source mkfixture.sh   (provides the mk_* functions + FIXROOT)
# All fixtures are built under a single mktemp dir exported as FIXROOT; the caller is
# responsible for trashing it (the test runner does so on exit).
set -euo pipefail

FIXROOT="$(mktemp -d "${TMPDIR:-/tmp}/drive-conf-fix.XXXXXX")"
export FIXROOT

# git with deterministic identity + no signing, scoped to the fixture repo via -C.
_gitc() { git -C "$1" -c user.name=t -c user.email=t@t -c commit.gpgsign=false "${@:2}"; }

# Initialize a fresh repo at $1. Echoes nothing.
_init_repo() {
  local r="$1"
  mkdir -p "$r"
  git -C "$r" init -q -b main
  _gitc "$r" config user.name t
  _gitc "$r" config user.email t@t
}

# Commit a file. $1=repo $2=path $3=content $4=msg ; echoes resulting tip sha
_commit() {
  local r="$1" p="$2" c="$3" m="$4"
  mkdir -p "$r/$(dirname "$p")"
  printf '%s\n' "$c" > "$r/$p"
  _gitc "$r" add -A
  _gitc "$r" commit -q -m "$m"
  _gitc "$r" rev-parse HEAD
}

# Commit a file with an EXPLICIT multi-line message (for trailer fixtures). The message
# is passed verbatim so a real `Drive-Test-Waiver:` trailer block (or body prose) is
# preserved exactly. $1=repo $2=path $3=content $4=msg ; echoes resulting tip sha
_commit_msg() {
  local r="$1" p="$2" c="$3" m="$4"
  mkdir -p "$r/$(dirname "$p")"
  printf '%s\n' "$c" > "$r/$p"
  _gitc "$r" add -A
  _gitc "$r" commit -q -m "$m"
  _gitc "$r" rev-parse HEAD
}

# Write a CONVERGED review artifact. $1=run_dir $2=scope $3=N $4=reviewed-sha
_write_review() {
  local rd="$1" scope="$2" n="$3" sha="$4"
  mkdir -p "$rd"
  {
    echo "# Review $scope round $n"
    echo
    echo "## Verdict: CONVERGED"
    echo
    echo "reviewed-sha: $sha"
  } > "$rd/review-$scope-$n.md"
}

# Write a FINDINGS review artifact. $1=run_dir $2=scope $3=N $4=reviewed-sha
_write_review_findings() {
  local rd="$1" scope="$2" n="$3" sha="$4"
  mkdir -p "$rd"
  {
    echo "# Review $scope round $n"
    echo
    echo "## Verdict: FINDINGS"
    echo
    echo "reviewed-sha: $sha"
  } > "$rd/review-$scope-$n.md"
}

# Write a normal codex review file. $1=run_dir $2=scope
_write_codex() {
  local rd="$1" scope="$2"
  mkdir -p "$rd"
  { echo "codex review for $scope"; echo "looks fine"; } > "$rd/codex-review-$scope.md"
}

# Write a codex file with the anchored first-line CODEX_UNAVAILABLE token. $1=rd $2=scope
_write_codex_unavailable() {
  local rd="$1" scope="$2"
  mkdir -p "$rd"
  { echo "CODEX_UNAVAILABLE"; echo "codex CLI not installed"; } > "$rd/codex-review-$scope.md"
}

# Write a codex file that merely MENTIONS the word elsewhere (not anchored). $1=rd $2=scope
_write_codex_word_buried() {
  local rd="$1" scope="$2"
  mkdir -p "$rd"
  { echo "codex review for $scope"; echo "note: CODEX_UNAVAILABLE was not the case"; } > "$rd/codex-review-$scope.md"
}

# Write an EMPTY codex file (bare `touch`). Must NOT satisfy the codex side. $1=rd $2=scope
_write_codex_empty() {
  local rd="$1" scope="$2"
  mkdir -p "$rd"
  : > "$rd/codex-review-$scope.md"
}

# ---------------------------------------------------------------------------------
# Fixture builders. Each echoes "REPO_DIR RUN_DIR" on one line (space-separated).
# runId is the basename of RUN_DIR; featureBranch is drive/<runId>.
# ---------------------------------------------------------------------------------

# clean slice-merge: slice/<runId>/4a exists, review matches its tip + codex present.
mk_slice_clean() {
  local name="${1:-slice-clean}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" checkout -q -b "slice/$name/4a"
  local tip; tip="$(_commit "$repo" "feature.sh" "echo hi" "slice 4a work")"
  _write_review "$rd" "4a" 1 "$tip"
  _write_codex "$rd" "4a"
  echo "$repo $rd"
}

# sha-mismatch: review's reviewed-sha points at an OLD commit, slice tip moved on.
mk_slice_sha_mismatch() {
  local name="${1:-slice-sha-mismatch}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" checkout -q -b "slice/$name/4a"
  local oldtip; oldtip="$(_commit "$repo" "feature.sh" "echo hi" "slice 4a v1")"
  _commit "$repo" "feature.sh" "echo hi2" "slice 4a v2 (unreviewed)" >/dev/null
  _write_review "$rd" "4a" 1 "$oldtip"   # bound to the stale tip
  _write_codex "$rd" "4a"
  echo "$repo $rd"
}

# missing-review: slice exists, codex exists, but NO review-4a-*.md file.
mk_slice_missing_review() {
  local name="${1:-slice-missing-review}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" checkout -q -b "slice/$name/4a"
  _commit "$repo" "feature.sh" "echo hi" "slice 4a work" >/dev/null
  mkdir -p "$rd"
  _write_codex "$rd" "4a"
  echo "$repo $rd"
}

# slice clean but codex file ABSENT (no-codex violation).
mk_slice_no_codex() {
  local name="${1:-slice-no-codex}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" checkout -q -b "slice/$name/4a"
  local tip; tip="$(_commit "$repo" "feature.sh" "echo hi" "slice 4a work")"
  _write_review "$rd" "4a" 1 "$tip"
  echo "$repo $rd"
}

# plan-gate fixtures. RUN_DIR holds review-design-N.md + codex-review-design.md.
# variant: clean | findings | nodesign | nocodex | codex_unavailable | codex_buried | codex_empty
mk_plan() {
  local variant="$1" name="${2:-plan-$1}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  mkdir -p "$rd"
  case "$variant" in
    clean)
      _write_review "$rd" design 1 "$(printf '0%.0s' {1..40})"
      _write_codex "$rd" design ;;
    findings)
      _write_review "$rd" design 1 "$(printf '0%.0s' {1..40})"
      _write_review_findings "$rd" design 2 "$(printf '0%.0s' {1..40})"  # highest-N is FINDINGS
      _write_codex "$rd" design ;;
    nodesign)
      _write_codex "$rd" design ;;
    nocodex)
      _write_review "$rd" design 1 "$(printf '0%.0s' {1..40})" ;;
    codex_unavailable)
      _write_review "$rd" design 1 "$(printf '0%.0s' {1..40})"
      _write_codex_unavailable "$rd" design ;;
    codex_buried)
      # for AC3: a normal-review codex whose body buries the word — still counts as a
      # present, non-empty review file (it is not falsely treated as a degraded marker,
      # but it satisfies on the strength of being a real review). plan-gate clean here.
      _write_review "$rd" design 1 "$(printf '0%.0s' {1..40})"
      _write_codex_word_buried "$rd" design ;;
    codex_empty)
      # for AC3 negative: an EMPTY codex file (bare `touch`) does NOT satisfy.
      _write_review "$rd" design 1 "$(printf '0%.0s' {1..40})"
      _write_codex_empty "$rd" design ;;
  esac
  echo "$repo $rd"
}

# Ship fixtures. featureBranch = drive/<runId>. A phase review with reviewed-sha=R, then
# one ledger-only commit advances tip.
# variant: clean | code_past_r | other_harness_past_r | two_ledger_commits
mk_ship() {
  local variant="$1" name="${2:-ship-$1}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" checkout -q -b "drive/$name"
  local R; R="$(_commit "$repo" "feature.sh" "echo phase1" "phase 1 code")"
  _write_review "$rd" phase1 1 "$R"
  _write_codex "$rd" phase1
  case "$variant" in
    clean)
      # one ledger-only commit (both allowlisted files) past R
      mkdir -p "$repo/.harness"
      printf 'd\n' > "$repo/.harness/decisions.md"
      printf 'f\n' > "$repo/.harness/followups.md"
      _gitc "$repo" add -A; _gitc "$repo" commit -q -m "ledger" ;;
    code_past_r)
      _commit "$repo" "extra.sh" "echo unreviewed" "unreviewed code past R" >/dev/null ;;
    other_harness_past_r)
      mkdir -p "$repo/.harness"
      printf 'x\n' > "$repo/.harness/foo.md"   # NOT in allowlist
      _gitc "$repo" add -A; _gitc "$repo" commit -q -m "other harness file" ;;
    two_ledger_commits)
      mkdir -p "$repo/.harness"
      printf 'd\n' > "$repo/.harness/decisions.md"
      _gitc "$repo" add -A; _gitc "$repo" commit -q -m "ledger 1"
      printf 'f\n' > "$repo/.harness/followups.md"
      _gitc "$repo" add -A; _gitc "$repo" commit -q -m "ledger 2" ;;
  esac
  echo "$repo $rd"
}

# Multi-phase existential R (AC4b): phase1 converged in MORE rounds than phase2 (so the
# global max review-N is phase1's). Linear history: base -> p1code(R1) -> p2code(R2) ->
# ledger. The existential must pick phase2's review (R2), whose R2..tip is ledger-only.
mk_ship_multiphase() {
  local name="${1:-ship-multiphase}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" checkout -q -b "drive/$name"
  local R1; R1="$(_commit "$repo" "p1.sh" "echo p1" "phase 1 code")"
  local R2; R2="$(_commit "$repo" "p2.sh" "echo p2" "phase 2 code")"
  # phase1 took 3 rounds (highest N = 3), phase2 took 1 round (N=1) — max-N selects p1.
  _write_review "$rd" phase1 1 "$(printf '1%.0s' {1..40})"
  _write_review "$rd" phase1 2 "$(printf '1%.0s' {1..40})"
  _write_review "$rd" phase1 3 "$R1"
  _write_codex "$rd" phase1
  _write_review "$rd" phase2 1 "$R2"
  _write_codex "$rd" phase2
  # ledger-only commit advances tip
  mkdir -p "$repo/.harness"
  printf 'd\n' > "$repo/.harness/decisions.md"
  printf 'f\n' > "$repo/.harness/followups.md"
  _gitc "$repo" add -A; _gitc "$repo" commit -q -m "ledger"
  echo "$repo $rd"
}

# HARDEN->advance (AC4c). phaseInt/<runId>/<P> advanced by a harden commit AFTER the
# integration review. The post-harden review-phase<P> (higher N) is bound to the
# post-harden tip; the pre-harden one is stale.
# variant: post_harden_ok | stale_only
mk_phase_harden() {
  local variant="$1" P="${2:-1}" name="${3:-phase-harden-$1}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" checkout -q -b "phaseInt/$name/$P"
  local pre; pre="$(_commit "$repo" "phase.sh" "echo phase" "phase $P integration")"
  local post; post="$(_commit "$repo" "phase.sh" "echo phase hardened" "phase $P harden fix")"
  _write_codex "$rd" "phase$P"
  case "$variant" in
    post_harden_ok)
      _write_review "$rd" "phase$P" 1 "$pre"    # stale integration review
      _write_review "$rd" "phase$P" 2 "$post" ;; # post-harden regress review (highest-N, matches tip)
    stale_only)
      _write_review "$rd" "phase$P" 1 "$pre" ;;  # only the stale review; tip is post
  esac
  echo "$repo $rd"
}

# Audit fixture: a live phaseInt/<runId>/<P> with one slice merged in.
# variant: reviewed (slice has a counting review) | unreviewed (slice merged, no review)
mk_audit() {
  local variant="$1" name="${2:-audit-$1}" P=1
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  # slice branch with work
  _gitc "$repo" checkout -q -b "slice/$name/4a"
  local stip; stip="$(_commit "$repo" "feature.sh" "echo hi" "slice 4a")"
  # live phaseInt that has merged the slice (fast-forward so slice tip is ancestor)
  _gitc "$repo" checkout -q -b "phaseInt/$name/$P"
  _write_codex "$rd" "4a"
  case "$variant" in
    reviewed)   _write_review "$rd" "4a" 1 "$stip" ;;
    unreviewed) : ;;   # no review-4a-*.md -> audit must flag it
  esac
  echo "$repo $rd"
}

# Delete the loose git object for sha $2 in repo $1 (hermetic object-store corruption).
_corrupt_object() {
  local repo="$1" sha="$2"
  local obj="$repo/.git/objects/${sha:0:2}/${sha:2}"
  if [ -f "$obj" ]; then
    chmod -R u+w "$repo/.git/objects/${sha:0:2}"
    rm -f "$obj"
  else
    # Object is packed — truncate any pack so reads of its objects fail.
    local p
    for p in "$repo"/.git/objects/pack/*.pack; do
      [ -f "$p" ] || continue
      chmod u+w "$p"; : > "$p"
    done
  fi
}

# SHIP git-error fixture: a counting phase review binds to a real, resolvable, ancestor
# R; the featureBranch tip commit object is INTACT (so `rev featureBranch` and
# `rev-list R..tip` succeed) but the tip's TREE object is DELETED, so `git diff
# --name-only R..tip` (the allowlist check) ERRORS. That git/IO error MUST surface as
# exit 2 (fail-closed) — process-substitution would have swallowed it into a false
# clean. This is exactly the BLOCKING finding. Echoes "REPO RUN_DIR".
# (Distinct from a non-resolving artifact sha, which is a verdict → skip, not exit 2.)
mk_ship_git_error() {
  local name="${1:-ship-git-error}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" checkout -q -b "drive/$name"
  local R; R="$(_commit "$repo" "feature.sh" "echo phase1" "phase 1 code")"
  # one ledger-only commit past R (so R..tip = 1 commit, R is ancestor)
  mkdir -p "$repo/.harness"
  printf 'd\n' > "$repo/.harness/decisions.md"
  printf 'f\n' > "$repo/.harness/followups.md"
  _gitc "$repo" add -A; _gitc "$repo" commit -q -m "ledger"
  _write_review "$rd" phase1 1 "$R"
  _write_codex "$rd" phase1
  # Corrupt the tip's TREE (not the commit) → diff errors, commit/rev-list still work.
  local tip tree
  tip="$(_gitc "$repo" rev-parse HEAD)"
  tree="$(_gitc "$repo" rev-parse "$tip^{tree}")"
  _corrupt_object "$repo" "$tree"
  echo "$repo $rd"
}

# AUDIT git-error fixture: a live phaseInt/<runId>/1 ref exists and enumerates via
# for-each-ref, but its tip commit object is DELETED so resolving the enumerated ref
# errors mid-check (a ref that for-each-ref found but can't be peeled = real repo
# corruption, distinct from an absent ref). audit must surface exit 2 (NOT exit 0
# clean, which would swallow a broken repo). Echoes "REPO RUN_DIR".
mk_audit_git_error() {
  local name="${1:-audit-git-error}" P=1
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" checkout -q -b "phaseInt/$name/$P"
  local tip; tip="$(_commit "$repo" "phase.sh" "echo phase" "phase $P integration")"
  mkdir -p "$rd"
  _write_codex "$rd" "phase$P"
  # Corrupt the live phaseInt tip so for-each-ref lists it but rev-parse errors.
  _corrupt_object "$repo" "$tip"
  echo "$repo $rd"
}

# ---------------------------------------------------------------------------------
# impl-presence fixtures (Item C). Build a repo with a REAL drive/<runId> base branch
# and a slice/<runId>/<id> branch cut FROM it (so merge-base(slice, drive) resolves to
# the fork point), then add slice commits per variant. The mode derives base =
# merge-base(slice, drive/<runId>), diffs base..tip, checks the test-path predicate and
# the Drive-Test-Waiver trailer. runId = basename(RUN_DIR) = $name, so featureBranch =
# drive/$name. Echoes "REPO RUN_DIR".
#
# variant:
#   test            -- slice adds tests/foo/test_x.py (a runnable pytest path)   -> clean
#   test_suffix     -- slice adds tests/foo/x_test.py (the *_test.py suffix form) -> clean
#   test_sh         -- slice adds test/foo.test.sh (a runnable bash path)        -> clean
#   test_sh_nested  -- slice adds test/sub/x.test.sh (NESTED; the runner globs only
#                      test/*.test.sh, so a nested path is NOT a runnable test)   -> violation
#   notest          -- slice adds only src.sh (no test, no waiver)               -> violation
#   waiver          -- slice adds only src.sh but a real Drive-Test-Waiver: TRAILER -> clean
#   waiver_prose    -- slice adds only src.sh; the waiver string sits MID-BODY as
#                      prose (non-Key:val text after it) so git does NOT parse it as a
#                      trailer                                                    -> violation
#   pred_helpers    -- slice only touches tests/_helpers.py (excluded)           -> violation
#   pred_conftest   -- slice only touches tests/conftest.py (excluded)           -> violation
#   pred_fixtures   -- slice only touches tests/fixtures/data.py (excluded)      -> violation
#   pred_pyc        -- slice only touches tests/foo/test_x.pyc (excluded)        -> violation
#   pred_root       -- slice only touches root-level test_root.py (not under tests/) -> violation
#   pred_docs       -- slice only touches docs/guide.test.md (no runner)         -> violation
#   del_test        -- slice's ONLY test-path change is DELETING a runnable test  -> violation
#                      (a deleted test is not test EVIDENCE: `--diff-filter=AM`)
#   dot_test_sh     -- slice only adds test/.noop.test.sh (dotfile basename; the
#                      real bash runner glob skips dotfiles)                       -> violation
#   dot_test_py     -- slice only adds tests/mc/.foo_test.py (dotfile basename that DOES
#                      match `*_test.py`; CI pytest collection skips dotfiles)      -> violation
#   no_drive        -- slice exists but NO drive/<runId> branch (merge-base fails) -> exit 2
mk_impl_presence() {
  local variant="$1" name="${2:-impl-$1}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  mkdir -p "$rd"   # runId = basename(rd); needed even though no review artifacts here

  if [ "$variant" = "del_test" ]; then
    # A runnable test EXISTS on drive/<runId> base; the slice's only test-path change is to
    # DELETE it (plus an unrelated code edit). The deletion must NOT count as test evidence
    # (--diff-filter=AM excludes D), so with no other test + no waiver -> violation (exit 1).
    _gitc "$repo" checkout -q -b "drive/$name"
    _commit "$repo" "tests/foo/test_existing.py" "def test_e(): pass" "drive base: seed a test" >/dev/null
    _gitc "$repo" checkout -q -b "slice/$name/3a"
    _gitc "$repo" rm -q "tests/foo/test_existing.py"
    printf 'echo changed\n' > "$repo/src.sh"
    _gitc "$repo" add -A
    _gitc "$repo" commit -q -m "slice 3a: delete the test + edit code"
    echo "$repo $rd"
    return 0
  fi

  if [ "$variant" = "rename_test" ]; then
    # A runnable bash test EXISTS on the drive/<runId> base; the slice RENAMES it to ANOTHER
    # runnable test path (test/foo.test.sh -> test/bar.test.sh) WITH a real content edit (so git
    # classes it R, not A+D) PLUS an unrelated code edit. The renamed test still EXISTS at a
    # runnable path, so this must be CLEAN (exit 0). NON-VACUOUS: under the old --diff-filter=AM
    # filter the R-classified rename is EXCLUDED and only the code file shows -> false violation;
    # --diff-filter=d (exclude-deletions) keeps the rename DESTINATION -> clean.
    # Seed a multi-line file so a one-line append stays >50% similar and git detects a rename.
    _gitc "$repo" checkout -q -b "drive/$name"
    mkdir -p "$repo/test"
    for _i in 1 2 3 4 5 6 7 8 9 10; do printf 'echo line%d\n' "$_i"; done > "$repo/test/foo.test.sh"
    _gitc "$repo" add -A
    _gitc "$repo" commit -q -m "drive base: seed a runnable bash test"
    _gitc "$repo" checkout -q -b "slice/$name/3a"
    _gitc "$repo" mv "test/foo.test.sh" "test/bar.test.sh"
    printf 'echo line11\n' >> "$repo/test/bar.test.sh"   # small edit -> high similarity -> R
    printf 'echo changed\n' > "$repo/src.sh"             # unrelated code change
    _gitc "$repo" add -A
    _gitc "$repo" commit -q -m "slice 3a: rename+edit the bash test + edit code"
    echo "$repo $rd"
    return 0
  fi

  if [ "$variant" = "no_drive" ]; then
    # slice branch off main, but NEVER create drive/<runId> -> merge-base unresolvable -> exit 2
    _gitc "$repo" checkout -q -b "slice/$name/3a"
    _commit "$repo" "src.sh" "echo hi" "slice work no drive base" >/dev/null
    echo "$repo $rd"
    return 0
  fi

  # Real drive/<runId> base branch, then cut the slice FROM it.
  _gitc "$repo" checkout -q -b "drive/$name"
  _commit "$repo" "featureBase" "fb" "drive base advance" >/dev/null
  _gitc "$repo" checkout -q -b "slice/$name/3a"

  case "$variant" in
    test)
      _commit "$repo" "tests/foo/test_x.py" "def test_x(): pass" "slice 3a + test" >/dev/null ;;
    test_suffix)
      _commit "$repo" "tests/foo/x_test.py" "def test_x(): pass" "slice 3a + *_test.py" >/dev/null ;;
    test_sh)
      _commit "$repo" "test/foo.test.sh" "echo ok" "slice 3a + bash test" >/dev/null ;;
    test_sh_nested)
      _commit "$repo" "test/sub/x.test.sh" "echo ok" "slice 3a + nested bash test" >/dev/null ;;
    notest)
      _commit "$repo" "src.sh" "echo hi" "slice 3a code only" >/dev/null ;;
    waiver)
      _commit "$repo" "src.sh" "echo hi" "slice 3a code only" >/dev/null
      # real trailing trailer block: blank line then Key: val at end of message
      _commit_msg "$repo" "doc.md" "docs" \
        "$(printf 'doc slice work\n\nDrive-Test-Waiver: pure documentation slice, no testable surface')" >/dev/null ;;
    waiver_prose)
      _commit "$repo" "src.sh" "echo hi" "slice 3a code only" >/dev/null
      # waiver string MID-BODY with non-Key:val prose AFTER it -> NOT a trailer block
      _commit_msg "$repo" "doc.md" "docs" \
        "$(printf 'explain the policy\n\nWe reference Drive-Test-Waiver: here as an example.\nMore prose follows so this is body text, not a trailer.')" >/dev/null ;;
    pred_helpers)
      _commit "$repo" "tests/_helpers.py" "X = 1" "slice 3a touches helpers only" >/dev/null ;;
    pred_conftest)
      _commit "$repo" "tests/conftest.py" "X = 1" "slice 3a touches conftest only" >/dev/null ;;
    pred_fixtures)
      _commit "$repo" "tests/fixtures/data.py" "X = 1" "slice 3a touches fixtures only" >/dev/null ;;
    pred_pyc)
      _commit "$repo" "tests/foo/test_x.pyc" "bin" "slice 3a touches pyc only" >/dev/null ;;
    pred_root)
      _commit "$repo" "test_root.py" "def test_root(): pass" "slice 3a root test only" >/dev/null ;;
    pred_docs)
      _commit "$repo" "docs/guide.test.md" "# guide" "slice 3a docs only" >/dev/null ;;
    dot_test_sh)
      # dotfile basename under test/: the bash runner globs test/*.test.sh which SKIPS
      # dotfiles, so this is not a runnable test -> violation.
      _commit "$repo" "test/.noop.test.sh" "echo ok" "slice 3a dotfile bash test only" >/dev/null ;;
    dot_test_py)
      # dotfile basename under tests/ whose name WOULD match the `*_test.py` pytest pattern
      # (the leading-`.` is absorbed by the `*`), but pytest collection SKIPS dotfiles, so it
      # is not runnable -> violation. NON-VACUOUS: `.foo_test.py` matches `*_test.py` on
      # bash 3.2, so only the dotfile-basename guard rejects it.
      _commit "$repo" "tests/mc/.foo_test.py" "def test_x(): pass" "slice 3a dotfile pytest only" >/dev/null ;;
  esac
  echo "$repo $rd"
}

# Two concurrent runs in ONE repo (AC10): run-keyed phaseInt/R1/1 and phaseInt/R2/1.
# Echoes "REPO R1_RUN_DIR R2_RUN_DIR".
mk_two_concurrent() {
  local name="${1:-concurrent}"
  local repo="$FIXROOT/$name-repo"
  local r1="$name-R1" r2="$name-R2"
  local rd1="$FIXROOT/$r1" rd2="$FIXROOT/$r2"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  # R1 phase1: reviewed & clean
  _gitc "$repo" checkout -q -b "phaseInt/$r1/1"
  local t1; t1="$(_commit "$repo" "r1.sh" "echo r1" "R1 phase1")"
  _write_review "$rd1" phase1 1 "$t1"
  _write_codex "$rd1" phase1
  # R2 phase1: UNREVIEWED (sha mismatch — review bound to wrong sha)
  _gitc "$repo" checkout -q main
  _gitc "$repo" checkout -q -b "phaseInt/$r2/1"
  _commit "$repo" "r2.sh" "echo r2" "R2 phase1" >/dev/null
  _write_review "$rd2" phase1 1 "$(printf '2%.0s' {1..40})"  # wrong sha
  _write_codex "$rd2" phase1
  echo "$repo $rd1 $rd2"
}
