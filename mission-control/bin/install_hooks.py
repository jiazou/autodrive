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

# Load existing settings. If the file is present but unparseable (hand-edited,
# comments, trailing comma), DON'T abort the whole install (this runs under
# `set -e`) — skip the hook wiring with a clear message and let the user add it.
settings = {}
if os.path.exists(settings_path):
    try:
        with open(settings_path, encoding="utf-8") as fh:
            settings = json.load(fh)
    except (ValueError, OSError) as e:
        print(f"  skipped: could not parse {settings_path} ({e}).", file=sys.stderr)
        print("  add the Mission Control hooks manually, or fix the JSON and re-run.",
              file=sys.stderr)
        sys.exit(0)

hooks = settings.setdefault("hooks", {})
wiring = {"Notification": "waiting", "UserPromptSubmit": "active", "Stop": "idle"}
changed = False
for event, status in wiring.items():
    cmd = f"{sys.executable} {MC}/bin/mc-hook.py {status}"
    arr = hooks.setdefault(event, [])
    desired = {"hooks": [{"type": "command", "command": cmd}]}
    # Canonicalize by IDENTITY (the mc-hook.py marker), not by exact command string:
    # strip any existing mc-hook entry for this event — including one whose path or
    # python interpreter changed (a moved MC dir, e.g. claude-harness -> autodrive) —
    # then append exactly one at the current command. Idempotent (no-op when already
    # canonical) AND migrates a stale path on re-run instead of leaving the dead entry
    # behind. Non-mc-hook entries for the event are preserved in order.
    existing_mc = [e for e in arr if "mc-hook.py" in json.dumps(e)]
    if existing_mc == [desired]:
        continue  # already exactly right — no change
    hooks[event] = [e for e in arr if "mc-hook.py" not in json.dumps(e)] + [desired]
    changed = True

if changed:
    # Atomic write (temp + os.replace) so a crash can't corrupt the user's
    # live Claude config — same discipline as done.py's vault writes.
    tmp = settings_path + ".tmp"
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, settings_path)
    print("  wired Mission Control hooks into settings.json")
else:
    print("  hooks already present — no change")
