#!/usr/bin/env bash
# AC8: pin the coordinator soft-check prose in .claude/commands/drive.md.
#
# The soft-check is the SECONDARY context-pressure detection surface: at each safe
# boundary the coordinator reads its own latest transcript line and self-signals
# `rebirth_pending` when the SOFT threshold is crossed — signal-only, idempotent,
# continues. This test pins the load-bearing contract so a drift that removes or
# weakens any clause reds the suite (whitespace-normalized substring guards, mirroring
# the phase-1 checkpoint-contract doc pins).
#
# bash 3.2-safe; read-only on the shipped prose (never edits drive.md).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DRIVE_MD="$REPO_DIR/.claude/commands/drive.md"

PASS=0
FAIL=0

# Whitespace-normalized prose (collapse all runs of whitespace to one space) so a
# clause that wraps across lines still matches as a contiguous phrase.
PROSE="$(tr '\n' ' ' < "$DRIVE_MD" | tr -s '[:space:]' ' ')"

# pin <desc> <substring> : FAIL unless <substring> occurs in the normalized prose.
pin() {
  case "$PROSE" in
    *"$2"*) echo "PASS: $1"; PASS=$((PASS + 1)) ;;
    *)      echo "FAIL: $1 (missing: '$2')"; FAIL=$((FAIL + 1)) ;;
  esac
}

# --- The soft-check section exists, named as the secondary surface ----------
pin "section header present" \
  "## Coordinator soft-check"
pin "secondary surface / Stop hook primary" \
  "SECONDARY context-pressure detection surface (the Stop hook is primary)"

# --- Fires at the enumerated safe boundaries --------------------------------
pin "fires at safe boundaries" \
  "At each **safe boundary** in the Execute loop"
pin "per-slice review verdict boundary" \
  "after each per-slice review verdict is recorded"
pin "phase-integration review verdict boundary" \
  "after the phase-integration review verdict"
pin "HARDEN round verdict boundary" \
  "after each HARDEN round verdict"
pin "phase advance boundary" \
  "after the phase advance"

# --- Reads the shared data-file threshold (no hardcoded number) -------------
pin "reads the data file" \
  "bin/rebirth-thresholds.json"
pin "uses the soft fraction from the data file" \
  "window * softThresholdFraction"

# --- Self-signals rebirth_pending -------------------------------------------
pin "sets rebirth_pending itself" \
  "set \`state.rebirth_pending = true\`"

# --- Writes the event-log line on the soft signal (AC8 / drive.md step 3) ----
# The design REQUIRES the coordinator to append a rebirth_pending event-log line when it
# self-signals at a soft boundary; pin that contract (the via/pct shape) so a drift that
# drops the event-log write reds the suite.
pin "appends the rebirth_pending event-log line" \
  "append one event-log"
pin "event-log line shape (via=coordinator-soft)" \
  '{"event":"rebirth_pending","via":"coordinator-soft","pct":<tokens*100/window>}'

# --- Idempotent -------------------------------------------------------------
pin "guarded on not-already-true (idempotent condition)" \
  "\`state.rebirth_pending\` is not already"
pin "idempotency clause stated" \
  "never re-set an already-\`true\` flag and never log a duplicate"

# --- Signal-only: does NOT checkpoint / hand off / pause --------------------
pin "signal-only wording" \
  "SIGNAL-ONLY:"
pin "does not checkpoint/hand off/pause" \
  "does NOT checkpoint, hand off, or pause"

# --- Continues autonomous work after signalling -----------------------------
pin "continues after signalling" \
  "coordinator CONTINUES autonomous work normally"

# --- Handoff deferred to Phase 3 (not here) ---------------------------------
pin "Phase 3 consumes the flag" \
  "Phase 3's safe-boundary handler consumes \`rebirth_pending\`"

# --- Honest-coverage residuals acknowledged ---------------------------------
pin "single-catastrophic-turn residual" \
  "single catastrophic turn can overshoot"
pin "absent-hook degrades to this self-check residual" \
  "when the Stop hook is ABSENT this self-check is the ONLY"

# --- Execute loop invokes the soft-check at safe boundaries -----------------
pin "Execute loop points at the soft-check" \
  "run the **Coordinator soft-check**"

# --- Summary ----------------------------------------------------------------
echo "----------------------------------------"
echo "PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -eq 0 ] || exit 1
