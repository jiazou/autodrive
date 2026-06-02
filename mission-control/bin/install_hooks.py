#!/usr/bin/env python3
"""
Idempotently wire Mission Control's passive-capture hooks into ~/.claude/settings.json.
Adds Notification->waiting, UserPromptSubmit->active, Stop->idle entries pointing at
mc-hook.py, unless an mc-hook entry already exists for that event. Called by install.sh.
"""
import json
import os
import sys

MC = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
settings_path = os.path.expanduser("~/.claude/settings.json")
settings = json.load(open(settings_path)) if os.path.exists(settings_path) else {}

hooks = settings.setdefault("hooks", {})
wiring = {"Notification": "waiting", "UserPromptSubmit": "active", "Stop": "idle"}
changed = False
for event, status in wiring.items():
    cmd = f"{sys.executable} {MC}/bin/mc-hook.py {status}"
    arr = hooks.setdefault(event, [])
    if any("mc-hook.py" in json.dumps(e) for e in arr):
        continue
    arr.append({"hooks": [{"type": "command", "command": cmd}]})
    changed = True

if changed:
    json.dump(settings, open(settings_path, "w"), indent=2)
    print("  wired Mission Control hooks into settings.json")
else:
    print("  hooks already present — no change")
