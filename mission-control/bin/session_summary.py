#!/usr/bin/env python3
"""
Mission Control — session_summary: summarize one Claude session's recent transcript
into {progress, next} via headless `claude -p`.

Used by the 6:45am morning job to enrich the harvest with per-session progress and
next-steps. The interactive `harvest` skill does this with in-context subagents
instead (higher quality); this is the unattended path.

Reads the tail of the transcript only (recent activity = where we are + what's next),
never the whole file. Prints a JSON object {"progress": "...", "next": "..."} to stdout.
On any failure prints {} so the caller degrades to goal+status. Read-only.
"""
import json
import os
import sys
import glob
import subprocess

HOME = os.path.expanduser("~")
PROJECTS_DIR = os.path.join(HOME, ".claude", "projects")
TAIL_MESSAGES = 60      # recent user/assistant turns to consider
MAX_CHARS = 6000        # cap the prompt payload


def _text(content):
    """Flatten a user/assistant message 'content' (str or block list) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    out.append(b.get("text", ""))
                elif b.get("type") == "tool_use":
                    out.append(f"[tool:{b.get('name', '')}]")
        return " ".join(out)
    return ""


def tail_text(sid):
    hits = glob.glob(os.path.join(PROJECTS_DIR, "*", sid + ".jsonl"))
    if not hits:
        return ""
    turns = []
    with open(hits[0]) as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("type") in ("user", "assistant"):
                t = _text(e.get("message", {}).get("content"))
                t = " ".join(t.split())
                if t:
                    turns.append(f"{e['type']}: {t[:600]}")
    blob = "\n".join(turns[-TAIL_MESSAGES:])
    return blob[-MAX_CHARS:]


def summarize(sid, goal=""):
    blob = tail_text(sid)
    if not blob:
        return {}
    prompt = (
        "Below is the recent tail of a Claude Code session transcript"
        + (f' whose goal is: "{goal}".' if goal else ".")
        + " In under 40 words summarize the PROGRESS so far, and in under 25 words"
        " state what should be done NEXT. Reply with ONLY a JSON object, no prose:"
        ' {"progress": "...", "next": "..."}\n\nTRANSCRIPT TAIL:\n' + blob)
    try:
        r = subprocess.run(["claude", "-p", prompt], capture_output=True,
                           text=True, timeout=120)
        txt = r.stdout.strip()
        start, end = txt.find("{"), txt.rfind("}")
        if start >= 0 and end > start:
            obj = json.loads(txt[start:end + 1])
            return {"progress": obj.get("progress", ""), "next": obj.get("next", "")}
    except Exception:
        pass
    return {}


def main():
    if len(sys.argv) < 2:
        print("{}")
        return
    sid = sys.argv[1]
    goal = sys.argv[2] if len(sys.argv) > 2 else ""
    print(json.dumps(summarize(sid, goal)))


if __name__ == "__main__":
    main()
