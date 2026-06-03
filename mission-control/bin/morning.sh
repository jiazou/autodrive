#!/bin/bash
# Mission Control — pre-wake morning run (driven by the launchd agent ~6:45am).
# Writes today's single surface so you wake to a plan already written, plus a
# per-session harvest enriched with Goal / Progress / Next (Progress+Next are
# summarized from each session's transcript via headless claude).
# claude must be on PATH for --summarize; it degrades to Goal+status if absent.
# /opt/homebrew/bin is included so Homebrew Python is found under launchd's bare PATH.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
PY="$(command -v python3 || echo /usr/bin/python3)"
MC="$HOME/mission-control/bin"
LOG="$HOME/mission-control/morning.log"

echo "=== morning run $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG"
"$PY" "$MC/standup.py" --draft              >> "$LOG" 2>&1   # Today's Focus + Parallel Plan
"$PY" "$MC/harvest.py" --log --summarize    >> "$LOG" 2>&1   # per-session Goal/Progress/Next digest
echo "--- done ---" >> "$LOG"
