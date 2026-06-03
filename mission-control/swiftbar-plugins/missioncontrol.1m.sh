#!/bin/bash
# Mission Control — today's tasks + live agent sessions in the menu bar.
# <bitbar.title>Mission Control</bitbar.title>
# <bitbar.desc>Today's vault tasks + Claude session status</bitbar.desc>
# NOTE: refreshOnOpen intentionally OFF — it made every click re-run the script
# synchronously. The menu opens instantly from the last background run (1-min
# interval, set by the .1m. filename); click "Refresh" for an on-demand update.
# SwiftBar runs plugins with a bare PATH, so add the usual Python locations before
# resolving python3 (Homebrew on Apple Silicon / Intel, then system).
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
PY="$(command -v python3 || echo /usr/bin/python3)"
exec "$PY" "$HOME/mission-control/bin/today.py" --swiftbar
