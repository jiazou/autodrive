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

# Commit a file. The message $4 is passed verbatim to `commit -m`, so a multi-line message
# (a real `Drive-Test-Waiver:` trailer block or body prose) is preserved exactly.
# $1=repo $2=path $3=content $4=msg ; echoes resulting tip sha
_commit() {
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

# Write a degradation codex file: first-line CODEX_UNAVAILABLE marker (convention).
# Non-empty, so it satisfies codex_present(). $1=rd $2=scope
_write_codex_unavailable() {
  local rd="$1" scope="$2"
  mkdir -p "$rd"
  { echo "CODEX_UNAVAILABLE"; echo "codex CLI not installed"; } > "$rd/codex-review-$scope.md"
}

# Write a real codex review that merely mentions the word in its body. Non-empty, so it
# satisfies codex_present() exactly like any review (the gate does not parse the marker).
# $1=rd $2=scope
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

# Write a harden audit file (drive-harden.md template shape). $1=rd $2=P $3=N $4=yes|no
_write_harden() {
  local rd="$1" P="$2" n="$3" applied="$4"
  mkdir -p "$rd"
  {
    echo "# Harden phase $P $n"
    echo "## Verdict: HARDENED"
    echo "## AppliedEdits: $applied"
  } > "$rd/harden-$P-$n.md"
}

# Write a redesign epoch marker (I1 — the file NAME is the load-bearing data). $1=rd $2=P $3=R
_write_redesign_marker() {
  local rd="$1" P="$2" R="$3"
  mkdir -p "$rd"
  printf '{"phase":"%s","epoch":%s}\n' "$P" "$R" > "$rd/redesign-$P-r$R.marker"
}

# Write a DANGLING redesign epoch marker (a broken symlink). The dirent NAME still encodes
# the epoch, so highest_epoch()/the checkpoint marker scan must COUNT it (forcing the higher
# epoch) — the `-e` glob test follows the link and fails, so an `-e`-only guard would skip it
# and fall back to a LOWER epoch (fail-OPEN). $1=rd $2=P $3=R
_write_redesign_marker_dangling() {
  local rd="$1" P="$2" R="$3"
  mkdir -p "$rd"
  ln -s /nonexistent/redesign-target "$rd/redesign-$P-r$R.marker"
}

# Write a DANGLING artifact symlink (a broken symlink) at $rd/$2. The dirent NAME still
# parses (round N / scope), so the dirent loops must COUNT it as present-but-unparseable
# and fail closed — the `-e` glob test follows the link and fails, so an `-e`-only guard
# would skip it (fail-OPEN: a dropped highest-N round / undercounted counter). $1=rd $2=name
_write_dangling_dirent() {
  local rd="$1" name="$2"
  mkdir -p "$rd"
  ln -s /nonexistent/artifact-target "$rd/$name"
}

# Write an open in-flight dispatch marker (I2). $1=rd $2=kind-scope (e.g. review-phase1)
_write_inflight() {
  local rd="$1" ks="$2"
  mkdir -p "$rd"
  printf '{"kind":"x","scope":"x","runId":"x","sessionId":null,"startedAt":"now"}\n' \
    > "$rd/inflight-$ks.marker"
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

# slice with a FINDINGS (NOT converged) review whose reviewed-sha MATCHES the tip + codex
# present: must return verdict-not-converged, never pass on the sha match alone.
mk_slice_findings() {
  local name="${1:-slice-findings}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" checkout -q -b "slice/$name/4a"
  local tip; tip="$(_commit "$repo" "feature.sh" "echo hi" "slice 4a work")"
  _write_review_findings "$rd" "4a" 1 "$tip"
  _write_codex "$rd" "4a"
  echo "$repo $rd"
}

# plan-gate fixtures. RUN_DIR holds review-design-N.md + codex-review-design.md.
# variant: clean | findings | nodesign | nocodex | codex_unavailable | codex_buried |
#          codex_empty | dangling_highest
#   dangling_highest -- a CONVERGED review-design-1.md + a DANGLING review-design-2.md
#                       symlink (broken) + codex. highest_review_file's `-e`-only guard
#                       skips the broken higher-N link and drops to the N=1 CONVERGED
#                       round -> plan-gate PASSES (fail-OPEN). `-e || -L` counts N=2 as
#                       `best`; it is unreadable so verdict_converged() fails -> block.
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
    dangling_highest)
      # N=1 CONVERGED + a DANGLING higher-N (N=2) review symlink + codex. The dangling
      # N=2 is the real highest round; an -e-only highest_review_file drops to N=1 and
      # PASSES. -e||-L counts N=2 (unreadable -> verdict-not-converged) -> block.
      _write_review "$rd" design 1 "$(printf '0%.0s' {1..40})"
      _write_dangling_dirent "$rd" "review-design-2.md"
      _write_codex "$rd" design ;;
  esac
  echo "$repo $rd"
}

# Per-phase design-gate fixtures (Tier 2). RUN_DIR holds review-phasedesign<P>-N.md +
# codex-review-phasedesign<P>.md. Mirrors mk_plan, scoped to phasedesign<P>. Like plan-gate,
# no git tip (it audits a design DOC). Epoch variants exercise the redesign-epoch scope
# token (phasedesign<P>-r<R>, R = highest redesign-<P>-r*.marker):
#   epoch1_clean    -- r1 marker + CONVERGED review-phasedesign<P>-r1-1.md + codex sibling
#   epoch1_stale    -- r1 marker + ONLY a stale epoch-0 CONVERGED pair (must NOT satisfy)
#   epoch1_unmarked -- r1 CONVERGED review + codex sibling but the redesign-<P>-r1.marker
#                      is MISSING (corruption / deleted marker). highest_epoch() would
#                      fall back to bare phasedesign<P> and PASS on the stale epoch-0 pair;
#                      the gate must instead fail closed with epoch-unmarked. An epoch-0
#                      CONVERGED pair is seeded too, so a marker-only check would PASS.
#   epoch1_marker_dangling -- a DANGLING redesign-<P>-r1.marker symlink + ONLY a stale
#                      epoch-0 CONVERGED pair (no r1 review/codex). An `-e`-only highest_epoch()
#                      skips the broken symlink, resolves epoch 0, and PASSES on the stale
#                      pair (fail-OPEN); `-e || -L` counts the dangling marker -> epoch 1 ->
#                      scope phasedesign<P>-r1 has no review -> fail closed (no-review).
# $1=variant (clean|nodesign|nocodex|findings|epoch1_clean|epoch1_stale|epoch1_unmarked|epoch1_marker_dangling) $2=P.
mk_phasedesign() {
  local variant="$1"
  local P="${2:-1}"
  local name="phasedesign-$variant-$P"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  local scope="phasedesign$P"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  mkdir -p "$rd"
  case "$variant" in
    clean)
      _write_review "$rd" "$scope" 1 "$(printf '0%.0s' {1..40})"
      _write_codex "$rd" "$scope" ;;
    findings)
      _write_review "$rd" "$scope" 1 "$(printf '0%.0s' {1..40})"
      _write_review_findings "$rd" "$scope" 2 "$(printf '0%.0s' {1..40})"  # highest-N FINDINGS
      _write_codex "$rd" "$scope" ;;
    nodesign)
      _write_codex "$rd" "$scope" ;;
    nocodex)
      _write_review "$rd" "$scope" 1 "$(printf '0%.0s' {1..40})" ;;
    epoch1_clean)
      _write_redesign_marker "$rd" "$P" 1
      _write_review "$rd" "$scope-r1" 1 "$(printf '0%.0s' {1..40})"
      _write_codex "$rd" "$scope-r1" ;;
    epoch1_stale)
      _write_redesign_marker "$rd" "$P" 1
      _write_review "$rd" "$scope" 1 "$(printf '0%.0s' {1..40})"   # stale epoch-0 pair
      _write_codex "$rd" "$scope" ;;
    epoch1_unmarked)
      # r1 artifacts present, marker MISSING — plus a CONVERGED epoch-0 pair so a
      # marker-only gate would resolve epoch 0 and PASS. Must fail closed (epoch-unmarked).
      _write_review "$rd" "$scope" 1 "$(printf '0%.0s' {1..40})"   # stale epoch-0 pair
      _write_codex "$rd" "$scope"
      _write_review "$rd" "$scope-r1" 1 "$(printf '0%.0s' {1..40})"
      _write_codex "$rd" "$scope-r1" ;;
    epoch1_marker_dangling)
      # dangling r1 marker (broken symlink) + ONLY a stale epoch-0 CONVERGED pair. An
      # -e-only highest_epoch() skips the broken link, resolves epoch 0, and PASSES on the
      # stale pair; -e||-L counts the marker -> epoch 1 -> phasedesign<P>-r1 has no review.
      _write_redesign_marker_dangling "$rd" "$P" 1
      _write_review "$rd" "$scope" 1 "$(printf '0%.0s' {1..40})"   # stale epoch-0 pair
      _write_codex "$rd" "$scope" ;;
  esac
  echo "$repo $rd"
}

# Ship fixtures. featureBranch = drive/<runId>. A phase review with reviewed-sha=R, then
# W1 regression fixture: featureBranch at tip R, but the RUN_DIR holds ONLY a per-phase
# DESIGN review (review-phasedesign1-1.md) carrying a reviewed-sha + its codex sibling, and
# NO phase-INTEGRATION review (review-phase1-N.md). Pre-fix the ship glob `review-phase*-*.md`
# matched the phasedesign file and trusted its reviewed-sha → clean ship with zero integration
# review. Post-fix the ship loop excludes phasedesign* → exit 1 (no counting review).
mk_ship_phasedesign_only() {
  local name="${1:-ship-phasedesignonly}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" checkout -q -b "drive/$name"
  local R; R="$(_commit "$repo" "feature.sh" "echo phase1" "phase 1 code")"
  _write_review "$rd" phasedesign1 1 "$R"   # design review (against convention) carrying a sha
  _write_codex "$rd" phasedesign1
  # Deliberately NO review-phase1-*.md integration review.
  echo "$repo $rd"
}

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

# mk_ship_findings_only REMOVED (Phase-3 harden): it backed the deleted AC-ship-skip case, which
# tested "ship skips a FINDINGS phase review as a candidate R". After the finalize wiring (D17)
# phase reviews are no longer candidate Rs (the finalize artifact is the (a)(b)(c) candidate; a
# phase review only feeds the b-i precondition). The live "FINDINGS phase review doesn't count
# toward b-i -> no-phase-review" behavior is covered non-vacuously by AC34 in the test runner.

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
    findings)
      _write_review_findings "$rd" "phase$P" 1 "$post" ;;  # sha matches tip but FINDINGS -> not converged
  esac
  echo "$repo $rd"
}

# Audit fixture: a live phaseInt/<runId>/<P> with one slice merged in. drive/<runId>
# sits at the base, so the phaseInt tip descends from it (live, per the ancestry rule).
# variant: reviewed (slice has a counting review) | unreviewed (slice merged, no review)
mk_audit() {
  local variant="$1" name="${2:-audit-$1}" P=1
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" branch "drive/$name"
  # slice branch with work
  _gitc "$repo" checkout -q -b "slice/$name/4a"
  local stip; stip="$(_commit "$repo" "feature.sh" "echo hi" "slice 4a")"
  # live phaseInt that has merged the slice (fast-forward so slice tip is ancestor)
  _gitc "$repo" checkout -q -b "phaseInt/$name/$P"
  _write_codex "$rd" "4a"
  case "$variant" in
    reviewed)   _write_review "$rd" "4a" 1 "$stip" ;;
    unreviewed) : ;;   # no review-4a-*.md -> audit must flag it
    findings)   _write_review_findings "$rd" "4a" 1 "$stip" ;;   # merged slice, FINDINGS review -> flag
    not_merged)
      # 4a is reviewed+merged (won't flag); add an unreviewed slice/4b cut from base that is
      # NOT an ancestor of phaseInt -> audit must SKIP it (only flags merged-but-unreviewed).
      _write_review "$rd" "4a" 1 "$stip"
      _gitc "$repo" checkout -q -b "slice/$name/4b" main
      _commit "$repo" "f4b.sh" "echo 4b" "slice 4b unreviewed, NOT merged into phaseInt" >/dev/null
      _gitc "$repo" checkout -q "phaseInt/$name/$P" ;;
  esac
  echo "$repo $rd"
}

# Audit ancestry fixture (criterion 11): the ONLY live ref is the NON-NUMERIC
# phaseInt/<runId>/4a (tip descends from drive/<runId>) with a merged-but-UNREVIEWED
# slice — audit must flag it. Pre-retrofit the numeric filter skipped `4a` entirely
# (false clean). Echoes "REPO RUN_DIR".
mk_audit_4a() {
  local name="${1:-audit-4a}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" branch "drive/$name"
  _gitc "$repo" checkout -q -b "slice/$name/s1"
  _commit "$repo" "feature.sh" "echo hi" "slice s1" >/dev/null
  _gitc "$repo" checkout -q -b "phaseInt/$name/4a"   # at slice tip -> merged, live
  mkdir -p "$rd"   # no review-s1-*.md -> audit must flag
  echo "$repo $rd"
}

# Audit ancestry fixture (criterion 11): a COMPLETED phaseInt (tip is a STRICT ancestor
# of drive/<runId> — the step-6 advance moved drive to it and later work moved drive
# past it) containing a merged unreviewed slice must be SKIPPED (clean). Pre-retrofit
# the numeric pick audited it (false flag).
mk_audit_completed() {
  local name="${1:-audit-completed}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" branch "drive/$name"
  _gitc "$repo" checkout -q -b "slice/$name/s1"
  _commit "$repo" "feature.sh" "echo hi" "slice s1" >/dev/null
  _gitc "$repo" checkout -q -b "phaseInt/$name/1"
  _gitc "$repo" branch -f "drive/$name" "phaseInt/$name/1"   # the advance
  _gitc "$repo" checkout -q "drive/$name"
  _commit "$repo" "next.sh" "echo next" "post-advance work moves drive past" >/dev/null
  mkdir -p "$rd"   # no review for s1 — flagged only if the completed ref were audited
  echo "$repo $rd"
}

# Audit ancestry fixture: drive/<runId> EQUAL to the phaseInt tip (advance done, drive
# not yet moved past). Equality classifies LIVE — the merged unreviewed slice is flagged.
mk_audit_equal_tip() {
  local name="${1:-audit-equal}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" branch "drive/$name"
  _gitc "$repo" checkout -q -b "slice/$name/s1"
  _commit "$repo" "feature.sh" "echo hi" "slice s1" >/dev/null
  _gitc "$repo" checkout -q -b "phaseInt/$name/1"
  _gitc "$repo" branch -f "drive/$name" "phaseInt/$name/1"   # equal tips
  mkdir -p "$rd"
  echo "$repo $rd"
}

# Audit dedup fixture: ONE unreviewed slice s1 merged into TWO live phaseInt refs — an
# equal-tip just-advanced phaseInt/<runId>/1 (live per D20) AND a later live
# phaseInt/<runId>/2 descending from drive. The slice must be flagged ONCE, not twice
# (the raw violations JSON is the human-facing STOP evidence). Pre-dedup emits two
# identical slice:s1 objects. Echoes "REPO RUN_DIR".
mk_audit_multi_live() {
  local name="${1:-audit-multi-live}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" branch "drive/$name"
  _gitc "$repo" checkout -q -b "slice/$name/s1"
  _commit "$repo" "feature.sh" "echo hi" "slice s1" >/dev/null
  _gitc "$repo" checkout -q -b "phaseInt/$name/1"
  _gitc "$repo" branch -f "drive/$name" "phaseInt/$name/1"   # equal tip -> live
  _gitc "$repo" checkout -q -b "phaseInt/$name/2"
  _commit "$repo" "more.sh" "echo more" "phase 2 extra" >/dev/null   # descends drive -> live
  mkdir -p "$rd"   # no review for s1 -> flagged (once)
  echo "$repo $rd"
}

# ---------------------------------------------------------------------------------
# --mode checkpoint fixtures (I4). All have a real drive/<runId> branch; artifacts per
# variant. Echoes "REPO RUN_DIR".
#
# variant:
#   clean             -- quiescent well-formed run: live phaseInt, no inflight markers,
#                        counter artifacts covering all five I3 rules; state.json is
#                        CORRUPT garbage (proves the mode never reads it).
#                        Expected counters: reviewCount {"1.1":2} (review-1.1-final.md
#                        is not a round file), phaseReviewRound {"1":2} (3 review-phase1
#                        files MINUS 1 AppliedEdits:yes regress marker), hardenRound
#                        {"1":1} (one yes + one no), phaseDesignRound {"1":1} (epoch 0),
#                        redesigns {}.
#   inflight          -- clean-shaped + one open inflight-*.marker        -> inflight-open
#   unparseable_review-- a round file with NO '## Verdict:' line          -> unparseable-review
#   unparseable_harden-- a harden file with NO 'AppliedEdits:' line       -> unparseable-harden
#   epoch_gap         -- markers r1+r3 (r2 missing) + a VALID state.json claiming
#                        redesigns:2 -> counters.redesigns {"1":3} (highest-R; state
#                        never read) + epoch-gap violation
#   regress_mismatch  -- 1 review-phase1 file but 2 AppliedEdits:yes harden files
#                        -> regress-mismatch, phaseReviewRound {"1":0}
#   divergent         -- phaseInt cut from main with its own commit while drive moved on
#                        -> related in NEITHER direction -> phaseInt-divergent
#   fourA             -- only ref is the non-numeric phaseInt/<runId>/4a descending from
#                        drive -> accepted by the ancestry rule (clean)
#   epoch_files       -- r1 marker + 1 epoch-0 round file + 2 epoch-r1 round files
#                        -> phaseDesignRound {"1":2} (current epoch only), redesigns {"1":1}
#   epoch_unmarked    -- epoch-r1 review + codex sibling but NO redesign-1-r1.marker
#                        (corruption / deleted marker) -> epoch-unmarked, exit 1. Without
#                        the check highest_epoch() falls back to 0 and the run reads clean.
#   inflight_symlink  -- clean-shaped + a DANGLING symlink named inflight-*.marker: the
#                        `-e` glob guard follows the link and fails, so a marker-only
#                        glob would read clean; `-L` must fail it closed -> inflight-open.
#   epoch_marker_dangling -- a DANGLING redesign-1-r1.marker symlink (broken) + a stale,
#                        well-formed epoch-0 phasedesign review; otherwise quiescent. An
#                        `-e`-only marker scan skips the broken link, sees no redesign, and
#                        reads clean (fail-OPEN); `-e || -L` counts it -> highest_epoch=1 and
#                        the r1 marker fails the `-e` existence probe in the gapless check
#                        -> epoch-gap, exit 1.
#   dangling_review   -- a DANGLING review-1.1-2.md symlink (broken), otherwise quiescent.
#                        The `-e`-only review-* scan skips it (undercounting reviewCount and
#                        reading clean on corruption); `-e || -L` counts it present-but-
#                        unparseable (grep '## Verdict:' fails) -> unparseable-review, exit 1.
#   dangling_harden   -- a DANGLING harden-1-2.md symlink (broken), otherwise quiescent. The
#                        `-e`-only harden-* scan skips it (erasing a fix round / suppressing
#                        a regress-mismatch); `-e || -L` counts it (grep 'AppliedEdits:' fails)
#                        -> unparseable-harden, exit 1.
#   epoch_phaseid_dash_r_round -- a `-r`-containing phase id (`4-r1`) at epoch 0 with 2 round
#                        files -> phaseDesignRound {"4-r1":2} (marker-anchored counter). exit 1
#                        from the epoch-unmarked detector's by-design residual on a terminal-`-r`
#                        id; the assertion is on the counter VALUE, not cleanliness.
#   finalize_round    -- quiescent clean-shaped base (live phaseInt/<name>/1) + a CONVERGED
#                        review-finalize-1.md carrying `## Verdict:` + `## AppliedEdits: yes`
#                        + a codex-review-finalize.md sibling, and NO slice/<name>/finalize
#                        branch. Asserts the POSITIVE: counters.finalizeRound==1 AND
#                        counters.reviewCount has NO `finalize` key (the `(finalize)` arm
#                        diverted it to finalize_yes_count, not the slice default) -> clean.
#   finalize_unparseable -- same base, but review-finalize-1.md keeps `## Verdict: CONVERGED`
#                        (so it passes the unparseable-review Verdict grep) and OMITS the
#                        `AppliedEdits:` line entirely -> the (finalize) arm fails its
#                        AppliedEdits grep -> unparseable-finalize, exit 1. Codex sibling present.
mk_checkpoint() {
  local variant="$1" name="${2:-ckpt-$1}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  local zeros; zeros="$(printf '0%.0s' {1..40})"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" checkout -q -b "drive/$name"
  _commit "$repo" "drive.sh" "echo drive" "drive work" >/dev/null
  mkdir -p "$rd"
  case "$variant" in
    clean)
      _gitc "$repo" checkout -q -b "phaseInt/$name/1"
      _commit "$repo" "phase.sh" "echo p1" "phase 1 integration" >/dev/null
      _write_review "$rd" design 1 "$zeros"
      _write_review "$rd" "1.1" 1 "$zeros"
      _write_review "$rd" "1.1" 2 "$zeros"
      printf 'notes, not a round file\n' > "$rd/review-1.1-final.md"  # non-integer N
      _write_review "$rd" phase1 1 "$zeros"
      _write_review "$rd" phase1 2 "$zeros"
      _write_review "$rd" phase1 3 "$zeros"
      _write_harden "$rd" 1 1 yes
      _write_harden "$rd" 1 2 no
      _write_review "$rd" phasedesign1 1 "$zeros"
      printf 'CORRUPT-NOT-JSON{{{\n' > "$rd/state.json"   # never a proof input
      ;;
    inflight)
      _write_review "$rd" phase1 1 "$zeros"
      _write_inflight "$rd" "review-phase1"
      ;;
    unparseable_review)
      { echo "# half-written review"; echo "no verdict line here"; } > "$rd/review-2.2-1.md"
      ;;
    unparseable_harden)
      { echo "# Harden phase 1 1"; echo "## Verdict: HARDENED"; } > "$rd/harden-1-1.md"
      ;;
    epoch_gap)
      _write_redesign_marker "$rd" 1 1
      _write_redesign_marker "$rd" 1 3   # r2 lost
      printf '{"phaseDesign":{"1":{"redesigns":2,"round":0}}}\n' > "$rd/state.json"
      ;;
    regress_mismatch)
      _write_review "$rd" phase1 1 "$zeros"
      _write_harden "$rd" 1 1 yes
      _write_harden "$rd" 1 2 yes
      ;;
    divergent)
      _gitc "$repo" checkout -q main
      _gitc "$repo" checkout -q -b "phaseInt/$name/1"
      _commit "$repo" "px.sh" "echo px" "divergent phase work" >/dev/null
      ;;
    fourA)
      _gitc "$repo" checkout -q -b "phaseInt/$name/4a"
      _commit "$repo" "p4a.sh" "echo 4a" "phase 4a integration" >/dev/null
      ;;
    epoch_files)
      _write_redesign_marker "$rd" 1 1
      _write_review "$rd" phasedesign1 1 "$zeros"        # epoch 0: must NOT count
      _write_review "$rd" "phasedesign1-r1" 1 "$zeros"
      _write_review "$rd" "phasedesign1-r1" 2 "$zeros"
      ;;
    epoch_unmarked)
      # r1 review + codex artifacts, marker MISSING. A marker-only check falls back to
      # epoch 0 and reads clean; must fail closed with epoch-unmarked.
      _write_review "$rd" phasedesign1 1 "$zeros"        # epoch-0 pair (looks complete)
      _write_review "$rd" "phasedesign1-r1" 1 "$zeros"
      _write_codex "$rd" "phasedesign1-r1"
      ;;
    inflight_symlink)
      _gitc "$repo" checkout -q -b "phaseInt/$name/1"
      _commit "$repo" "phase.sh" "echo p1" "phase 1 integration" >/dev/null
      _write_review "$rd" phase1 1 "$zeros"
      ln -s /nonexistent/target "$rd/inflight-review-phase1.marker"   # dangling symlink
      ;;
    epoch_marker_dangling)
      # dangling r1 marker + stale well-formed epoch-0 review; otherwise quiescent. An
      # -e-only marker scan skips the broken link and reads clean; -e||-L counts it ->
      # highest_epoch=1 and the gapless check's `-e` probe of the broken r1 marker fails
      # -> epoch-gap.
      _write_redesign_marker_dangling "$rd" 1 1
      _write_review "$rd" phasedesign1 1 "$zeros"   # stale epoch-0 review (well-formed)
      ;;
    dangling_review)
      # a DANGLING review-1.1-2.md symlink, otherwise quiescent. The -e-only review-* scan
      # skips it (undercount + clean-on-corruption); -e||-L counts it present-but-unparseable
      # (grep '## Verdict:' fails on the broken link) -> unparseable-review.
      _write_dangling_dirent "$rd" "review-1.1-2.md"
      ;;
    dangling_harden)
      # a DANGLING harden-1-2.md symlink, otherwise quiescent. The -e-only harden-* scan skips
      # it (erasing a fix round); -e||-L counts it (grep 'AppliedEdits:' fails) -> unparseable-harden.
      _write_dangling_dirent "$rd" "harden-1-2.md"
      ;;
    epoch_unmarked_phaseid_dash_r)
      # a phase id that itself contains `-r` (`4-r1`). A markerless epoch artifact for this
      # phase (review+codex for epoch r1 of phase `4-r1`, NO redesign-4-r1-r1.marker) must be
      # flagged epoch-unmarked under the CORRECT scope `phasedesign4-r1` — the anchored-suffix
      # phase-id parse keeps the full `4-r1` (not a `4` truncation).
      _gitc "$repo" checkout -q -b "phaseInt/$name/4-r1"
      _commit "$repo" "p.sh" "echo p" "phase 4-r1 integration" >/dev/null
      _write_review "$rd" "phasedesign4-r1-r1" 1 "$zeros"
      _write_codex "$rd" "phasedesign4-r1-r1"
      ;;
    epoch_phaseid_dash_r_round)
      # phaseDesignRound counter: a phase id that itself contains `-r` (`4-r1`) at EPOCH 0
      # (no redesign markers). Its round files are review-phasedesign4-r1-N.md, so the pd_key
      # is `4-r1`. The pre-fix `${t##*-r}` split mis-keys the counter to phase `4` (count 0);
      # the marker-anchored phase_of_pd_key keeps `4-r1` (count 2). The epoch-unmarked detector
      # still fires on `phasedesign4` (its by-design fail-closed residual on a terminal-`-r`
      # phase id) so the run is exit 1 — the assertion is on the COUNTER value, not cleanliness.
      _gitc "$repo" checkout -q -b "phaseInt/$name/4-r1"
      _commit "$repo" "p.sh" "echo p" "phase 4-r1 integration" >/dev/null
      _write_review "$rd" "phasedesign4-r1" 1 "$zeros"
      _write_review "$rd" "phasedesign4-r1" 2 "$zeros"
      ;;
    epoch_unmarked_codex_only)
      # FIX 2: ONLY the codex sibling of an epoch artifact (codex-review-phasedesign1-r1.md),
      # NO review file and NO redesign-1-r1.marker. Exercises the codex-half of the
      # epoch-unmarked scan independently — a regression dropping the codex glob from
      # unmarked_epochs()/the phase-derivation loop would otherwise stay green (every other
      # epoch-unmarked fixture also seeds a review file). Must fail closed: epoch-unmarked.
      _write_codex "$rd" "phasedesign1-r1"
      ;;
    finalize_round)
      # Quiescent clean-shaped base (a live phaseInt so the run is well-formed), then a single
      # CONVERGED review-finalize-1.md with `## AppliedEdits: yes` + a codex sibling. NO
      # slice/<name>/finalize branch is ever created (proves finalize is NOT a slice). Keep
      # the run otherwise-CLEAN: no other review-*/harden-* files that would add counter noise,
      # so the ONLY observables are finalizeRound==1 and an EMPTY reviewCount (no `finalize` key).
      # The `## Verdict:` line is required — else the unparseable-review grep trips BEFORE the
      # (finalize) arm runs. Regression validity: pre-Phase-2 there was no (finalize) arm, so the
      # finalize review would land in slice_keys -> reviewCount {"finalize":1} + finalizeRound 0.
      _gitc "$repo" checkout -q -b "phaseInt/$name/1"
      local fr_tip; fr_tip="$(_commit "$repo" "phase.sh" "echo p1" "phase 1 integration")"
      {
        echo "# Review finalize round 1"
        echo
        echo "## Verdict: CONVERGED"
        echo "## AppliedEdits: yes"
        echo
        echo "reviewed-sha: $fr_tip"
      } > "$rd/review-finalize-1.md"
      { echo "codex review for finalize"; echo "looks fine"; } > "$rd/codex-review-finalize.md"
      ;;
    finalize_unparseable)
      # Same quiescent base, but review-finalize-1.md keeps `## Verdict: CONVERGED` (so the
      # unparseable-review Verdict grep passes) and OMITS the `AppliedEdits:` line entirely.
      # The (finalize) arm's AppliedEdits grep then fails -> unparseable-finalize, exit 1.
      # Regression validity: pre-Phase-2 there was no (finalize) arm, so the missing
      # AppliedEdits line is irrelevant (the finalize review counts as a slice) -> no
      # unparseable-finalize; the assertion below flips with the Phase-2 fix.
      _gitc "$repo" checkout -q -b "phaseInt/$name/1"
      local fu_tip; fu_tip="$(_commit "$repo" "phase.sh" "echo p1" "phase 1 integration")"
      {
        echo "# Review finalize round 1"
        echo
        echo "## Verdict: CONVERGED"
        echo
        echo "reviewed-sha: $fu_tip"
      } > "$rd/review-finalize-1.md"
      { echo "codex review for finalize"; echo "looks fine"; } > "$rd/codex-review-finalize.md"
      ;;
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
  _gitc "$repo" branch "drive/$name"
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
#                      (a deleted test is not test EVIDENCE: `--diff-filter=d` excludes D)
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
    # (--diff-filter=d excludes D), so with no other test + no waiver -> violation (exit 1).
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
      _commit "$repo" "doc.md" "docs" \
        "$(printf 'doc slice work\n\nDrive-Test-Waiver: pure documentation slice, no testable surface')" >/dev/null ;;
    waiver_prose)
      _commit "$repo" "src.sh" "echo hi" "slice 3a code only" >/dev/null
      # waiver string MID-BODY with non-Key:val prose AFTER it -> NOT a trailer block
      _commit "$repo" "doc.md" "docs" \
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

# ---------------------------------------------------------------------------------
# --mode state-lint fixtures (D40). state-lint is the ONLY mode that reads state.json; it
# validates the routing fields resume keys on. Each fixture builds a real drive/<runId>
# branch (so `rev featureBranch` resolves and `tip` is recorded) + a state.json per variant.
# Echoes "REPO RUN_DIR".
#
# variant:
#   clean             -- well-formed executing state.json: non-empty phaseList, slices with
#                        valid step/owns/deps, well-formed verify/ship                -> exit 0
#   early_clean       -- stage=premises with EMPTY phaseList + empty slices (well-formed-
#                        empty early run) — must PASS (stage-aware)                    -> exit 0
#   unparseable       -- state.json is corrupt non-JSON -> unparseable-state           -> exit 1
#   phaselist_empty_executing -- stage=execute but phaseList:[] (unroutable)
#                        -> phaselist-malformed                                         -> exit 1
#   step_bogus        -- a slice with step:"bogus" (out of enum) -> slice-routing-malformed
#   owns_empty        -- a slice with owns:[] (empty) -> slice-routing-malformed       -> exit 1
#   slice_scalar      -- a slice VALUE is a non-object scalar (string) -> must emit a named
#                        slice-routing-malformed (exit 1), NOT crash jq                  -> exit 1
#   slices_array      -- the .slices CONTAINER is an array (non-object) while executing —
#                        unroutable -> slices-malformed (must NOT false-clean)           -> exit 1
#   slices_empty_executing -- stage=execute with slices:{} (empty object, mid-design):
#                        legitimate pre-design -> must PASS (empty {} is always OK)      -> exit 0
#   verify_bad        -- verify is not an object-with-attempts-array -> verify-malformed
#   ship_bad          -- ship missing the prUrl key -> ship-malformed                  -> exit 1
#   multi_bad_slice   -- TWO malformed slices -> TWO slice-routing-malformed objects
#                        (cardinality: one per malformed slice, D44)                   -> exit 1
#   slice_key_metachar -- a slice-id KEY with a JSON metachar (`"`) -> envelope stays VALID
#                        JSON (violation() escapes the scope) + violation fires           -> exit 1
#   deps_nonstring    -- a deps element that isn't a string (42) -> slice-routing-malformed
#   deps_badref       -- a deps element not matching slice-id grammar ("1 bad") -> same   -> exit 1
#   deps_clean        -- valid deps ("1.1") still pass (no over-rejection)              -> exit 0
#   slice_key_empty   -- an EMPTY-STRING slice-id KEY ("") -> slice-routing-malformed, must
#                        NOT be skipped (false-clean) by the key loop                   -> exit 1
#   slice_key_newline -- a slice-id KEY containing a newline ("1\n2") -> one
#                        slice-routing-malformed, consumed losslessly (no shredding)    -> exit 1
#   stage_finalize_clean -- a clone of `clean` with "stage":"finalize" (Stage 4c). The
#                        state-lint stage enum accepts `finalize`, so all other routing
#                        fields being well-formed -> clean (no stage-malformed)        -> exit 0
#   no_state          -- a real drive/<runId> branch but NO state.json file -> exit 2 (IO)
mk_state_lint() {
  local variant="$1" name="${2:-statelint-$1}"
  local repo="$FIXROOT/$name-repo" rd="$FIXROOT/$name"
  _init_repo "$repo"
  _commit "$repo" "README" "base" "base" >/dev/null
  _gitc "$repo" checkout -q -b "drive/$name"
  _commit "$repo" "drive.sh" "echo drive" "drive work" >/dev/null
  mkdir -p "$rd"
  local sj="$rd/state.json"
  case "$variant" in
    clean)
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1", "2"],
  "slices": {
    "1.1": {"step": "converged", "owns": ["bin/x.sh"], "deps": []},
    "1.2": {"step": "implementing", "owns": ["bin/y.sh", "test/y.test.sh"], "deps": ["1.1"]}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    early_clean)
      cat > "$sj" <<'JSON'
{
  "stage": "premises",
  "phaseList": [],
  "slices": {},
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    unparseable)
      printf 'CORRUPT-NOT-JSON{{{\n' > "$sj"
      ;;
    phaselist_empty_executing)
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": [],
  "slices": {},
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    step_bogus)
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "1.1": {"step": "bogus", "owns": ["bin/x.sh"], "deps": []}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    owns_empty)
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "1.1": {"step": "converged", "owns": [], "deps": []}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    slice_scalar)
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "1.1": "notanobject"
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    slices_array)
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": [],
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    slices_empty_executing)
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {},
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    verify_bad)
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "1.1": {"step": "converged", "owns": ["bin/x.sh"], "deps": []}
  },
  "verify": "not-an-object",
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    ship_bad)
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "1.1": {"step": "converged", "owns": ["bin/x.sh"], "deps": []}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null}
}
JSON
      ;;
    multi_bad_slice)
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "1.1": {"step": "bogus", "owns": ["bin/x.sh"], "deps": []},
    "1.2": {"step": "converged", "owns": [], "deps": []}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    toplevel_array)
      # A parseable-but-non-object ROOT (valid JSON array) must NOT crash jq (exit 5) —
      # it is unparseable-state (exit 1), like a scalar root.
      printf '[1,2,3]\n' > "$sj"
      ;;
    toplevel_scalar)
      # A parseable scalar ROOT — same fail-closed verdict, never a crash.
      printf '42\n' > "$sj"
      ;;
    stage_bogus)
      # An out-of-enum stage is an unroutable hint -> stage-malformed.
      cat > "$sj" <<'JSON'
{
  "stage": "bogus",
  "phaseList": ["1"],
  "slices": {
    "1.1": {"step": "converged", "owns": ["bin/x.sh"], "deps": []}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    stage_done_clean)
      # `done` is a real stage -> must still pass.
      cat > "$sj" <<'JSON'
{
  "stage": "done",
  "phaseList": ["1"],
  "slices": {
    "1.1": {"step": "converged", "owns": ["bin/x.sh"], "deps": []}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    phaselist_badref)
      # A phaseList element that isn't ref-safe (spaces) forms an invalid
      # phaseInt/<runId>/<P> ref -> phaselist-malformed.
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["bad ref name"],
  "slices": {
    "1.1": {"step": "converged", "owns": ["bin/x.sh"], "deps": []}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    phaselist_epoch_clean)
      # A `4a` epoch phase id is ref-safe -> must pass (with its matching `4a.1` slice).
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1", "4a"],
  "slices": {
    "4a.1": {"step": "converged", "owns": ["bin/x.sh"], "deps": []}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    slice_key_badref)
      # A slice-id KEY that isn't ref-safe (spaces) forms an invalid slice/<runId>/<id>
      # ref -> slice-routing-malformed, scoped to the offending key.
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "1 bad": {"step": "converged", "owns": ["bin/x.sh"], "deps": []}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    slice_key_metachar)
      # A slice-id KEY carrying a JSON metacharacter (`"`) — corruption-controlled and flows
      # into the violation `scope`. The envelope must stay VALID JSON (violation() escapes it).
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "1.2\"x": {"step": "converged", "owns": ["bin/x.sh"], "deps": []}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    deps_nonstring)
      # A deps element that isn't a string (42) is unroutable -> slice-routing-malformed.
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "1.1": {"step": "converged", "owns": ["bin/x.sh"], "deps": [42]}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    deps_badref)
      # A deps element that's a string but not slice-id grammar ("1 bad") is unroutable
      # -> slice-routing-malformed.
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "1.1": {"step": "converged", "owns": ["bin/x.sh"], "deps": ["1 bad"]}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    deps_clean)
      # A valid deps element ("1.1") still passes — the grammar check must not over-reject.
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "1.1": {"step": "converged", "owns": ["bin/x.sh"], "deps": []},
    "1.2": {"step": "implementing", "owns": ["bin/y.sh"], "deps": ["1.1"]}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    slice_key_empty)
      # An EMPTY-STRING slice-id KEY ("": {...}) fails the slice-id grammar and is
      # unroutable. A newline-split loop would emit an empty line for it and skip it
      # (false-clean); the NUL-delimited loop must still fire slice-routing-malformed.
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "": {"step": "converged", "owns": ["bin/x.sh"], "deps": []}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    slice_key_newline)
      # A slice-id KEY containing a newline ("1\n2") fails the grammar and is unroutable.
      # A newline-split loop would shred it into fragments; the NUL-delimited loop must
      # consume it losslessly and fire exactly one slice-routing-malformed.
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "1\n2": {"step": "converged", "owns": ["bin/x.sh"], "deps": []}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
    waiting_bad_type)
      # A non-null-non-string `waiting` (here a number) is unroutable: resume + the stop
      # hook both BRANCH on this field -> waiting-malformed.
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "1.1": {"step": "converged", "owns": ["bin/x.sh"], "deps": []}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null},
  "waiting": 42
}
JSON
      ;;
    waiting_bad_string)
      # A STRING `waiting` outside the canonical grammar ("frobnicate") would mis-branch the
      # resume/stop-hook consumers (it is neither null, a bare gateA|gateB|rebirth, nor a
      # stop:/ask: prefixed reason) -> waiting-malformed.
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "1.1": {"step": "converged", "owns": ["bin/x.sh"], "deps": []}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null},
  "waiting": "frobnicate"
}
JSON
      ;;
    waiting_rebirth_clean)
      # `rebirth` is the lone CONTINUE waiting value (the resume-as-continue this feature is
      # about) — it is a valid bare reason and must pass.
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "1.1": {"step": "converged", "owns": ["bin/x.sh"], "deps": []}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null},
  "waiting": "rebirth"
}
JSON
      ;;
    waiting_stop_clean)
      # A prefixed human-pause reason ("stop:checkpoint-unprovable") is valid -> must pass.
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "1.1": {"step": "converged", "owns": ["bin/x.sh"], "deps": []}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null},
  "waiting": "stop:checkpoint-unprovable"
}
JSON
      ;;
    waiting_null_clean)
      # An EXPLICIT null `waiting` (the autonomous, not-paused state) is valid -> must pass.
      # (The base `clean` fixture omits the key entirely; absent ≡ null. This pins the
      # explicit-null form too.)
      cat > "$sj" <<'JSON'
{
  "stage": "execute",
  "phaseList": ["1"],
  "slices": {
    "1.1": {"step": "converged", "owns": ["bin/x.sh"], "deps": []}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null},
  "waiting": null
}
JSON
      ;;
    stage_finalize_clean)
      # A clone of `clean` with stage=finalize (Stage 4c). The stage enum accepts `finalize`,
      # so with all other routing fields well-formed the run is clean (no stage-malformed).
      # Regression validity: pre-Phase-2 the enum lacked `finalize`, so this would have hit
      # stage-malformed (exit 1); the clean assertion flips with the enum add.
      cat > "$sj" <<'JSON'
{
  "stage": "finalize",
  "phaseList": ["1", "2"],
  "slices": {
    "1.1": {"step": "converged", "owns": ["bin/x.sh"], "deps": []},
    "1.2": {"step": "converged", "owns": ["bin/y.sh", "test/y.test.sh"], "deps": ["1.1"]}
  },
  "verify": {"attempts": []},
  "ship": {"suite": null, "conformance": null, "prUrl": null}
}
JSON
      ;;
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
  _gitc "$repo" branch "drive/$r1"
  _gitc "$repo" branch "drive/$r2"
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
