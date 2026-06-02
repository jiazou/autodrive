#!/bin/bash
# Mission Control — today's tasks + live agent sessions in the menu bar.
# <bitbar.title>Mission Control</bitbar.title>
# <bitbar.desc>Today's vault tasks + Claude session status</bitbar.desc>
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
exec /opt/homebrew/bin/python3 "/Users/jiazou/mission-control/bin/today.py" --swiftbar
