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

# A parseable file may still not be a JSON object (e.g. a top-level array). Don't crash
# (this runs under `set -e`) and don't clobber whatever the user has — skip like the
# unparseable case above.
if not isinstance(settings, dict):
    print(f"  skipped: {settings_path} is not a JSON object.", file=sys.stderr)
    print("  add the Mission Control hooks manually, or fix the file and re-run.",
          file=sys.stderr)
    sys.exit(0)

# Normalize the hooks container: a parseable settings file may legally hold a non-dict
# "hooks" (e.g. null) — replace any non-dict with {} so the wiring below cannot crash.
hooks = settings.get("hooks")
if not isinstance(hooks, dict):
    hooks = {}
    settings["hooks"] = hooks
wiring = {"Notification": "waiting", "UserPromptSubmit": "active", "Stop": "idle"}
changed = False
def _strip_mc(arr):
    """Remove mc-hook.py at the individual HOOK level (mirrors install-drive-hooks.sh's
    strip_managed): for each entry, drop only the hooks whose command references
    mc-hook.py, keep all other hooks, and drop an entry only if it is left empty. This
    preserves a FOREIGN hook that happens to share an entry-group with the mc-hook
    (filtering whole entries by a json.dumps substring would silently delete it)."""
    out = []
    for e in arr:
        inner = e.get("hooks") if isinstance(e, dict) else None
        if isinstance(inner, list):
            kept = [h for h in inner if "mc-hook.py" not in json.dumps(h)]
            if kept:
                ne = dict(e)
                ne["hooks"] = kept
                out.append(ne)
            # else: the entry held only mc-hook hook(s) -> drop the now-empty entry
        elif "mc-hook.py" not in json.dumps(e):
            out.append(e)  # odd-shaped entry with no hooks list: keep unless it is mc's
    return out


for event, status in wiring.items():
    cmd = f"{sys.executable} {MC}/bin/mc-hook.py {status}"
    # A parseable file may hold a non-list event value. Normalize so _strip_mc never
    # iterates a non-list, WITHOUT discarding recoverable hooks: a lone group object
    # (a dict placed where the array wrapper was forgotten) is wrapped into a one-item
    # list so any foreign hook inside it survives; a scalar (null / 42) holds nothing
    # recoverable and becomes [].
    arr = hooks.get(event)
    if isinstance(arr, dict):
        arr = [arr]
    elif not isinstance(arr, list):
        arr = []
    desired = {"hooks": [{"type": "command", "command": cmd}]}
    # Canonicalize by IDENTITY (the mc-hook.py marker), not by exact command string:
    # strip the existing mc-hook hook(s) for this event — including one whose path or
    # python interpreter changed (a moved MC dir, e.g. claude-harness -> autodrive) —
    # then append exactly one at the current command. Idempotent (no-op when already
    # canonical) AND migrates a stale path on re-run instead of leaving a dead entry.
    new_arr = _strip_mc(arr) + [desired]
    if new_arr == arr:
        continue  # already exactly right — no change
    hooks[event] = new_arr
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
