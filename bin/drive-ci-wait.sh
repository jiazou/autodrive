#!/usr/bin/env bash
# drive-ci-wait.sh — post-push CI gate for /drive-ship. Polls a GitHub PR's checks until they
# conclude, so a /drive run cannot reach stage=done with red CI (the human no longer has to notice).
#
# Read-only: NEVER writes state.json (drive-ship maps the exit code to the ship outcome). GitHub-only:
# the ship path opened the PR via `gh pr create`, so `gh` is provably present here; a glab/GitLab run
# is an explicit out-of-scope residual (drive-ship does not invoke this ⇒ the pre-existing gap).
#
# Usage:
#   drive-ci-wait.sh --pr <number|url> [--repo-root <path>] \
#       [--max-secs N] [--grace-secs N] [--poll-secs N]
#
# The CORE correctness rule (both design voices, P1): NEVER return pass from an empty or single
# snapshot. A 0-checks reading right after a push is INDISTINGUISHABLE from "no CI" by one sample —
# GitHub takes seconds to register check runs. So: pass (0) requires CI to have STARTED (≥1 check on
# the PR head) AND every check concluded non-failing. Persistent 0-checks is disambiguated by whether
# the repo has `.github/workflows/*` — workflows present + 0 checks ⇒ keep waiting (never proceed);
# no workflows + 0 checks ⇒ genuinely no CI ⇒ proceed. Per-check state is parsed from `--json`
# (NEVER `gh pr checks`'s exit code, which is nonzero for BOTH pending AND fail).
#
# Exit codes (drive-ship maps these):
#   0  GREEN         — CI started; every check concluded; none failed. Ship proceeds to done.
#   1  RED           — ≥1 check FAILED (failure/timed_out/action_required/error/startup_failure).
#                      Failing check names+links printed to stdout. drive-ship STOPs (stop:ci-red).
#   2  NO-CI         — no `.github/workflows/*` AND 0 checks after the grace window (genuine no-CI),
#                      OR `gh`/API unavailable. Best-effort PROCEED (never block a run for absent CI).
#   3  PENDING       — max wait elapsed with checks still pending, OR workflows-present-but-0-checks
#                      at max (CI expected but never registered). drive-ship surfaces a human pause.
#   2  usage/arg error also maps here (proceed best-effort; a broken invocation must not wedge ship).
#
# Env overrides (defaults tuned for real CI; tests pass small values):
#   DRIVE_CI_WAIT_MAX_SECS   (default 1800)  total wait bound
#   DRIVE_CI_WAIT_GRACE_SECS (default 120)   registration grace: 0-checks within this is "not yet"
#   DRIVE_CI_WAIT_POLL_SECS  (default 15)    inter-poll sleep
#   DRIVE_CI_WAIT_GH         (default `gh`)  the gh binary — the dep-independent TEST SEAM.
set -uo pipefail

PR=""; REPO_ROOT="."
while [ $# -gt 0 ]; do
  case "$1" in
    --pr)        PR="${2:-}"; shift 2 || shift ;;
    --repo-root) REPO_ROOT="${2:-.}"; shift 2 || shift ;;
    --max-secs)  DRIVE_CI_WAIT_MAX_SECS="${2:-}"; shift 2 || shift ;;
    --grace-secs) DRIVE_CI_WAIT_GRACE_SECS="${2:-}"; shift 2 || shift ;;
    --poll-secs) DRIVE_CI_WAIT_POLL_SECS="${2:-}"; shift 2 || shift ;;
    *)           shift ;;
  esac
done

GH="${DRIVE_CI_WAIT_GH:-gh}"
MAX="${DRIVE_CI_WAIT_MAX_SECS:-1800}"
GRACE="${DRIVE_CI_WAIT_GRACE_SECS:-120}"
POLL="${DRIVE_CI_WAIT_POLL_SECS:-15}"

# integer guards. MAX must be positive (a zero/garbage bound would proceed instantly / never wedge);
# GRACE/POLL are NON-negative (0 = no registration grace / no inter-poll sleep — valid, tests use it).
_posint()  { case "$1" in ''|*[!0-9]*) return 1;; *) [ "$1" -gt 0 ];; esac; }
_nonneg()  { case "$1" in ''|*[!0-9]*) return 1;; *) return 0;; esac; }
_posint "$MAX" || { echo "drive-ci-wait: bad --max-secs '$MAX'" >&2; exit 2; }
_nonneg "$GRACE" || GRACE=120
_nonneg "$POLL" || POLL=15
[ -n "$PR" ] || { echo "drive-ci-wait: --pr required" >&2; exit 2; }
command -v "$GH" >/dev/null 2>&1 || { echo "drive-ci-wait: gh unavailable ('$GH') — best-effort proceed" >&2; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "drive-ci-wait: jq unavailable — best-effort proceed" >&2; exit 2; }

# Does the repo declare CI? (used ONLY to disambiguate a persistent 0-checks reading)
_has_workflows() {
  local d="$REPO_ROOT/.github/workflows" f
  [ -d "$d" ] || return 1
  for f in "$d"/*.yml "$d"/*.yaml; do [ -e "$f" ] && return 0; done
  return 1
}

# elapsed seconds since $START
START="$(date +%s)"
_elapsed() { echo $(( $(date +%s) - START )); }

# One CI snapshot. Prints the JSON array (or "" on no-checks/error) to stdout.
_snapshot() { "$GH" pr checks "$PR" --json name,bucket,state,link 2>/dev/null; }

while :; do
  json="$(_snapshot)"
  el="$(_elapsed)"

  if [ -z "$json" ] || [ "$json" = "[]" ]; then
    # 0 checks. Within grace → checks may still be registering → keep polling.
    if [ "$el" -lt "$GRACE" ]; then
      [ "$el" -ge "$MAX" ] && { echo "drive-ci-wait: max<grace misconfig; timing out"; exit 3; }
      sleep "$POLL"; continue
    fi
    # Past grace with 0 checks: disambiguate no-CI vs never-registered.
    if _has_workflows; then
      # CI is expected but nothing registered — keep waiting to MAX, then PENDING (never PROCEED).
      if [ "$el" -ge "$MAX" ]; then
        echo "drive-ci-wait: .github/workflows present but 0 checks after ${el}s (CI never registered)"; exit 3
      fi
      sleep "$POLL"; continue
    fi
    echo "drive-ci-wait: no .github/workflows and 0 checks — no CI configured (proceed)"; exit 2
  fi

  # CI has STARTED (≥1 check). Classify buckets (gh: pass|fail|pending|skipping|cancel).
  fails="$(printf '%s' "$json" | jq -r '[.[]|select(.bucket=="fail")]' 2>/dev/null)"
  n_fail="$(printf '%s' "$json" | jq '[.[]|select(.bucket=="fail")]|length' 2>/dev/null || echo 0)"
  n_pend="$(printf '%s' "$json" | jq '[.[]|select(.bucket=="pending")]|length' 2>/dev/null || echo 0)"

  if [ "${n_fail:-0}" -gt 0 ]; then
    echo "CI RED — failing checks:"
    printf '%s' "$json" | jq -r '.[]|select(.bucket=="fail")|"  \(.name): \(.state) \(.link // "")"' 2>/dev/null
    exit 1
  fi
  if [ "${n_pend:-0}" -gt 0 ]; then
    if [ "$el" -ge "$MAX" ]; then
      echo "drive-ci-wait: still pending after ${el}s:"
      printf '%s' "$json" | jq -r '.[]|select(.bucket=="pending")|"  \(.name): \(.state)"' 2>/dev/null
      exit 3
    fi
    sleep "$POLL"; continue
  fi
  # ≥1 check, none failing, none pending (all pass/skipping/cancel) → GREEN.
  echo "CI GREEN — all checks concluded non-failing"
  exit 0
done
