#!/usr/bin/env bash
# The canonical FULL test suite for this repo — the single command every /drive stage
# ("run the full suite") and CI invoke, so "full suite" is unambiguous and identical
# everywhere. Runs BOTH acceptance harnesses:
#   1. python3 -m pytest tests/          (contract pins)
#   2. every test/*.test.sh              (the security-critical /drive gate bash suites)
# It runs ALL suites and reports EVERY failure (no early exit) — unlike a historical
# `|| exit 1` loop, which stopped at the first failing file and masked downstream fails
# (the regress-selfid-20260706 miss: drive-conformance + pytest green while
# drive-enforcement-e2e / drive-merge-gate / drive-stop-guard silently red). Exits
# nonzero iff any suite failed.
#
# Modes (so CI's two independent red/green jobs call this SAME runner):
#   (no arg)        run both harnesses
#   --pytest-only   run only python3 -m pytest tests/
#   --bash-only     run only the test/*.test.sh suites
#
# `python3` is deliberate: `python` is often absent locally (rc 127, not a failure).
# TMPDIR is left at the caller's default on purpose — the faithful env some tests depend
# on (macOS's trailing-slash $TMPDIR); do NOT unset/override it here.
set -u

mode="all"
case "${1:-}" in
  "")            mode="all" ;;
  --pytest-only) mode="pytest" ;;
  --bash-only)   mode="bash" ;;
  *) echo "usage: run-tests.sh [--pytest-only | --bash-only]" >&2; exit 2 ;;
esac

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root" || { echo "run-tests: cannot cd to repo root $repo_root" >&2; exit 2; }

fails=()

if [ "$mode" = "all" ] || [ "$mode" = "pytest" ]; then
  echo "== python3 -m pytest tests/ =="
  if python3 -m pytest tests/ -q; then
    echo "-- pytest OK"
  else
    fails+=("pytest")
  fi
fi

if [ "$mode" = "all" ] || [ "$mode" = "bash" ]; then
  for f in test/*.test.sh; do
    [ -e "$f" ] || continue          # no bash suites present → skip cleanly
    echo "== $f =="
    if bash "$f"; then
      echo "-- $f OK"
    else
      fails+=("$f")
    fi
  done
fi

echo ""
echo "===================================="
if [ "${#fails[@]}" -eq 0 ]; then
  echo "FULL SUITE ($mode): all green"
  exit 0
fi
echo "FULL SUITE ($mode): ${#fails[@]} suite(s) FAILED:"
printf '  - %s\n' "${fails[@]}"
exit 1
