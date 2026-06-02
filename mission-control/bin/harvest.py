#!/usr/bin/env python3
"""
Mission Control — harvest: summarize the status of all current Claude sessions.

Ground truth for "what is running" = Claude Code's own ~/.claude/sessions/*.json
(one file per session, keyed by pid, carrying the stable sessionId UUID, cwd, status).
Mission Control adds an enrichment overlay — ~/mission-control/bindings.jsonl, an
append-only log binding a session to a task/project. Color and name are auto-resolved
from the session transcript, not stored in the binding.

harvest = live sessions  LEFT JOIN  latest binding per session  ->  rendered digest.

Read-only unless --log is passed (which appends the digest to today's daily note).
"""
import json
import os
import sys
import glob
from datetime import datetime

HOME = os.path.expanduser("~")
SESSIONS_DIR = os.path.join(HOME, ".claude", "sessions")
PROJECTS_DIR = os.path.join(HOME, ".claude", "projects")
BINDINGS = os.path.join(HOME, "mission-control", "bindings.jsonl")
STATUS_LEDGER = os.path.join(HOME, "mission-control", "status.jsonl")
SELF_ID = os.environ.get("CLAUDE_CODE_SESSION_ID", "")


def load_status_overlay():
    """Latest hook-reported status per session (from mc-hook via Claude Code hooks).
    Used to surface 'waiting on YOU' precisely — more reliable than idle/busy."""
    latest = {}
    if not os.path.exists(STATUS_LEDGER):
        return latest
    for line in open(STATUS_LEDGER):
        try:
            e = json.loads(line)
        except Exception:
            continue
        sid = e.get("session_id")
        if sid:
            latest[sid] = e.get("status")  # later lines win
    return latest

VAULT = os.path.join(HOME, "Documents", "Jia's Personal Vault")
VAULT_DAILY = os.path.join(VAULT, "Daily")
DAILY_TEMPLATE = os.path.join(VAULT, "03 Resources", "Templates", "daily-note-template.md")


def ensure_daily_note(date_str):
    """Return the path to Daily/<date_str>.md, creating it from the template
    (or a minimal frontmatter) if absent. Single source of the date — callers
    pass the date string so there's no second clock to race across midnight."""
    path = os.path.join(VAULT_DAILY, date_str + ".md")
    created = False
    if not os.path.exists(path):
        os.makedirs(VAULT_DAILY, exist_ok=True)
        if os.path.exists(DAILY_TEMPLATE):
            body = open(DAILY_TEMPLATE).read().replace("{{date}}", date_str)
        else:
            body = (f"---\ndate: {date_str}\ntype: daily-note\narea: operations\n"
                    f"tags: [daily]\nstatus: active\n---\n\n# {date_str} — Daily\n")
        open(path, "w").write(body)
        created = True
    return path, created


def log_to_vault(digest, now):
    """Append this harvest to the day's cockpit note as a timestamped
    '## 🛰 Harvest HH:MM' section. Never clobbers existing content."""
    path, created = ensure_daily_note(now.strftime("%Y-%m-%d"))
    section = f"\n## 🛰 Harvest {now.strftime('%H:%M')}\n\n```text\n{digest}\n```\n"
    with open(path, "a") as fh:
        fh.write(section)
    return path, created


def session_meta(sid):
    """Read the session's TUI color (/color) and name (/rename) straight from its
    transcript at ~/.claude/projects/<slug>/<sid>.jsonl. Latest event wins.
    These match exactly what the user sees in the TUI — no manual entry needed."""
    color = name = None
    for f in glob.glob(os.path.join(PROJECTS_DIR, "*", sid + ".jsonl")):
        try:
            for line in open(f):
                if "agent-color" not in line and "agent-name" not in line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if e.get("sessionId") != sid:
                    continue
                if e.get("type") == "agent-color":
                    color = e.get("agentColor")
                elif e.get("type") == "agent-name":
                    name = e.get("agentName")
        except Exception:
            continue
    return color, name


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def load_live_sessions():
    """Return {sessionId: {...}} for every Claude session whose pid is still alive."""
    out = {}
    overlay = load_status_overlay()
    for f in glob.glob(os.path.join(SESSIONS_DIR, "*.json")):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        pid = d.get("pid")
        if pid is None or not pid_alive(pid):
            continue
        sid = d.get("sessionId")
        if not sid:
            continue
        color, name = session_meta(sid)
        status = d.get("status", "?")
        # a hook-reported "waiting" overrides idle/busy — it means Claude pinged YOU
        if overlay.get(sid) == "waiting":
            status = "waiting"
        out[sid] = {
            "pid": pid,
            "cwd": d.get("cwd", "?"),
            "status": status,
            "color": color,   # from /color, auto-resolved
            "name": name,     # from /rename, auto-resolved
        }
    return out


def load_bindings():
    """Reduce the append-only event log to the latest live binding per session_id."""
    latest = {}
    if not os.path.exists(BINDINGS):
        return latest
    for line in open(BINDINGS):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        sid = e.get("session_id")
        if not sid:
            continue
        latest[sid] = e  # later lines win (append-only -> chronological)
    # drop sessions whose last event was an explicit unbind
    return {s: e for s, e in latest.items() if e.get("event") != "unbind"}


def short(sid):
    return sid.split("-")[0] if sid else "?"


def home_rel(path):
    return path.replace(HOME, "~") if path else "?"


# status -> a glyph that reads at a glance; "waiting on me" is what matters most
STATUS_GLYPH = {
    "busy": "▶ working",
    "idle": "● idle",
    "shell": "○ shell",
    "waiting": "⏸ WAITING ON YOU",
}


def render(live, binds, now_str):
    lines = []
    lines.append(f"🛰️  MISSION CONTROL — Session Harvest · {now_str}")
    lines.append("")

    if not live:
        lines.append("No live Claude sessions found.")
        return "\n".join(lines)

    # sort: waiting-on-you first, then working, then idle/shell; this session last
    order = {"waiting": 0, "busy": 1, "shell": 2, "idle": 3}
    rows = []
    for sid, s in live.items():
        b = binds.get(sid, {})
        rows.append((sid, s, b))
    rows.sort(key=lambda r: (r[0] == SELF_ID, order.get(r[1]["status"], 4)))

    waiting = [r for r in rows if r[1]["status"] == "waiting"]
    bound = [r for r in rows if r[2]]
    unbound = [r for r in rows if not r[2] and r[0] != SELF_ID]

    lines.append(f"{len(live)} live session(s) · {len(bound)} bound · "
                 f"{len(unbound)} unbound · {len(waiting)} waiting on you")
    lines.append("")

    for sid, s, b in rows:
        glyph = STATUS_GLYPH.get(s["status"], s["status"])
        tag = "  ⟵ this session" if sid == SELF_ID else ""
        proj = b.get("project")
        task = b.get("task")
        color = s.get("color")   # auto-resolved from /color
        name = s.get("name")     # auto-resolved from /rename
        tab = b.get("tab_name")
        bits = []
        if color:
            bits.append(f"🎨{color}")
        if name:
            bits.append(f"“{name}”")
        if proj:
            bits.append(proj)
        if task:
            bits.append(f"task:{task}")
        if tab:
            bits.append(f"⧉{tab}")
        bind_str = "  —  " + " · ".join(bits) if bits else "  —  (unbound)"
        lines.append(f"  {short(sid):<9} {glyph:<18} {home_rel(s['cwd']):<30}{bind_str}{tag}")

    if unbound:
        lines.append("")
        lines.append("Unbound sessions — tag them to a project/task (color & name are auto):")
        for sid, s, _ in unbound:
            lines.append(f"  mc bind {short(sid)} --project \"<Project>\" [--task <slug>]")

    return "\n".join(lines)


def main():
    now = datetime.now()
    live = load_live_sessions()
    binds = load_bindings()
    out = render(live, binds, now.strftime("%Y-%m-%d %H:%M"))
    print(out)
    if "--log" in sys.argv:
        path, created = log_to_vault(out, now)
        print(f"\n📝 logged to {path.replace(HOME, '~')}"
              + ("  (created)" if created else "  (appended)"))


if __name__ == "__main__":
    main()
