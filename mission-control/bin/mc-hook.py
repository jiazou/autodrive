#!/usr/bin/env python3
"""
Mission Control — Claude Code hook for passive session-status capture.

Wired in ~/.claude/settings.json to fire on Notification / UserPromptSubmit / Stop.
Records a status transition for the firing session into ~/mission-control/status.jsonl,
which harvest/standup read to surface "waiting on YOU" precisely (more precise than the
idle/busy state in ~/.claude/sessions/*.json).

  Notification     -> "waiting"  (Claude pinged you: needs input/permission)
  UserPromptSubmit -> "active"   (you replied — clears waiting)
  Stop             -> "idle"     (turn finished)

CONTRACT: a hook must never block and must print NOTHING to stdout (UserPromptSubmit
stdout would be injected into the session context). Write to the ledger, exit 0.
"""
import sys
import os
import json
import time

status = sys.argv[1] if len(sys.argv) > 1 else "active"
try:
    payload = json.load(sys.stdin)
except Exception:
    payload = {}

sid = payload.get("session_id") or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
if sid:
    rec = {"ts": int(time.time()), "session_id": sid, "status": status}
    path = os.path.join(os.path.expanduser("~"), "mission-control", "status.jsonl")
    try:
        with open(path, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        pass

sys.exit(0)
