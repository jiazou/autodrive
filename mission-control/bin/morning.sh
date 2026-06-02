#!/bin/bash
# Mission Control — pre-wake morning run (driven by the launchd agent ~6:45am).
# Deterministic: writes today's single surface so Jia wakes to a plan already written.
# The intelligent two-lane refinement happens later when Jia runs the `standup` skill.
export PATH="/opt/homebrew/bin:/usr/bin:/bin:$PATH"
PY=/opt/homebrew/bin/python3
MC="$HOME/mission-control/bin"
LOG="$HOME/mission-control/morning.log"

echo "=== morning run $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG"
"$PY" "$MC/standup.py" --draft  >> "$LOG" 2>&1   # Today's Focus + Parallel Plan into Daily/<date>.md
"$PY" "$MC/harvest.py" --log    >> "$LOG" 2>&1   # session digest appended to the same note
echo "--- done ---" >> "$LOG"
