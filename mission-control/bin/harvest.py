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
import re
import sys
import glob
import subprocess
from datetime import datetime

HOME = os.path.expanduser("~")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vault_tasks  # single source of the configurable vault path (MC_VAULT)
SESSIONS_DIR = os.path.join(HOME, ".claude", "sessions")
PROJECTS_DIR = os.path.join(HOME, ".claude", "projects")
# /drive run state lives here (sibling of SESSIONS_DIR); the harvest bridge reads it
# READ-ONLY to surface runs parked on a human decision (mc tests monkeypatch this).
HARNESS_RUNS_DIR = os.path.join(HOME, ".claude", "harness-runs")
BINDINGS = os.path.join(HOME, "mission-control", "bindings.jsonl")
STATUS_LEDGER = os.path.join(HOME, "mission-control", "status.jsonl")
SELF_ID = os.environ.get("CLAUDE_CODE_SESSION_ID", "")


def load_status_overlay():
    """Latest hook-reported status per session (from mc-hook via Claude Code hooks).
    Used to surface 'waiting on YOU' precisely — more reliable than idle/busy."""
    latest = {}
    if not os.path.exists(STATUS_LEDGER):
        return latest
    with open(STATUS_LEDGER) as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except Exception:
                continue
            sid = e.get("session_id")
            if sid:
                latest[sid] = e.get("status")  # later lines win
    return latest

# Configurable vault path — resolved once in vault_tasks (MC_VAULT env, then
# ~/mission-control/config, then default) so the launchd job agrees with the CLI.
VAULT = vault_tasks.VAULT
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
            with open(DAILY_TEMPLATE) as fh:
                body = fh.read().replace("{{date}}", date_str)
        else:
            body = (f"---\ndate: {date_str}\ntype: daily-note\narea: operations\n"
                    f"tags: [daily]\nstatus: active\n---\n\n# {date_str} — Daily\n")
        vault_tasks.atomic_write(path, body)
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
    """Read the session's TUI color (/color), name (/rename), and ai-title (the
    auto-generated goal) straight from its transcript. Latest event of each wins.
    These match what the user sees in the TUI — no manual entry needed."""
    color = name = ai_title = None
    for f in glob.glob(os.path.join(PROJECTS_DIR, "*", sid + ".jsonl")):
        try:
            with open(f) as fh:
                for line in fh:
                    if ("agent-color" not in line and "agent-name" not in line
                            and "ai-title" not in line):
                        continue
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue
                    if e.get("sessionId") != sid:
                        continue
                    t = e.get("type")
                    if t == "agent-color":
                        color = e.get("agentColor")
                    elif t == "agent-name":
                        name = e.get("agentName")
                    elif t == "ai-title":
                        ai_title = e.get("aiTitle")
        except Exception:
            continue
    return color, name, ai_title


def iterm_tab_names():
    """Map controlling-tty -> live iTerm tab name via one osascript call. Prefers the
    user's manual short tab name (the tab *title override*, e.g. "Harness") over the
    long auto-generated title — that short name is what you read as the session goal.
    Empty dict if iTerm isn't running or automation is denied (caller falls back to
    ai-title). One call per harvest, not per session."""
    script = (
        'tell application "iTerm2"\n'
        '  set out to ""\n'
        '  repeat with w in windows\n'
        '    repeat with t in tabs of w\n'
        '      repeat with s in sessions of t\n'
        '        set ov to ""\n'
        '        try\n'
        '          set ov to (variable s named "tab.titleOverride")\n'
        '        end try\n'
        '        set out to out & (tty of s) & "\t" & ov & "\t" & (name of s) & linefeed\n'
        '      end repeat\n'
        '    end repeat\n'
        '  end repeat\n'
        '  return out\n'
        'end tell')
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True,
                           text=True, timeout=5)
    except Exception:
        return {}
    out = {}
    for ln in r.stdout.splitlines():
        parts = ln.split("\t")
        if len(parts) < 3:
            continue
        tty, override, name = parts[0], parts[1], parts[2]
        out[tty.strip()] = override.strip() or name.strip()   # short manual name wins
    return out


def clean_goal(name):
    """Strip iTerm's own decorations from a tab name: a leading activity glyph
    (✳ ⠐ ⠂ …) and the trailing foreground-process badge like ' (caffeinate)'."""
    if not name:
        return name
    name = re.sub(r"^[^\w一-鿿]+", "", name)          # leading symbols/space
    name = re.sub(r"\s*\([^)\s]+\)\s*$", "", name)            # trailing (process)
    return name.strip()


def pid_tty(pid):
    try:
        r = subprocess.run(["ps", "-o", "tty=", "-p", str(pid)],
                           capture_output=True, text=True, timeout=3)
        t = r.stdout.strip()
        return "/dev/" + t if t and t != "??" else None
    except Exception:
        return None


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
    tabs = iterm_tab_names()   # one osascript call, shared across sessions
    for f in glob.glob(os.path.join(SESSIONS_DIR, "*.json")):
        try:
            with open(f) as fh:
                d = json.load(fh)
        except Exception:
            continue
        pid = d.get("pid")
        if pid is None or not pid_alive(pid):
            continue
        sid = d.get("sessionId")
        if not sid:
            continue
        color, name, ai_title = session_meta(sid)
        status = d.get("status", "?")
        # a hook-reported "waiting" overrides idle/busy — it means Claude pinged YOU
        if overlay.get(sid) == "waiting":
            status = "waiting"
        # goal = the iTerm tab name the user sees; fall back to the ai-title
        tty = pid_tty(pid)
        goal = clean_goal(tabs.get(tty) if tty else None) or ai_title
        out[sid] = {
            "pid": pid,
            "cwd": d.get("cwd", "?"),
            "status": status,
            "color": color,    # from /color, auto-resolved
            "name": name,      # from /rename, auto-resolved
            "goal": goal,      # iTerm tab name (or ai-title fallback)
        }
    return out


def load_bindings():
    """Reduce the append-only event log to the latest live binding per session_id."""
    latest = {}
    if not os.path.exists(BINDINGS):
        return latest
    with open(BINDINGS) as fh:
        for line in fh:
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


# The authoritative decision-bearing `waiting` grammar (drive-conformance.sh:1164 /
# drive.md R3 notify filter), ANCHORED so `gateAfoo` cannot false-match and `rebirth`
# (which auto-resumes — never a human decision) is EXCLUDED.
_DRIVE_WAITING_RE = re.compile(r"^(gateA|gateB|stop:.+|ask:.+)$")


def drive_waiting_runs():
    """Read-only scan of `~/.claude/harness-runs/*/state.json` for /drive runs PARKED on a
    human decision. Fail-open PER FILE (an unreadable/corrupt state.json is skipped, never
    fatal). A run qualifies iff `state.waiting` is a STRING matching the anchored
    decision-bearing grammar `^(gateA|gateB|stop:.+|ask:.+)$` — the `isinstance` guard skips a
    non-str/malformed `waiting`, and the anchors exclude `rebirth` (auto-resumes) and a
    `gateAfoo` false-match. Returns a list of `{runId, waiting, repoRoot}`."""
    out = []
    for sj in sorted(glob.glob(os.path.join(HARNESS_RUNS_DIR, "*", "state.json"))):
        try:
            with open(sj) as fh:
                st = json.load(fh)
        except Exception:
            continue  # fail-open per file — an unreadable/corrupt run never breaks harvest
        if not isinstance(st, dict):
            continue  # a PARSEABLE but non-object state.json (`[]`/`42`/`"x"`) — skip, never crash
        w = st.get("waiting")
        if not isinstance(w, str) or not _DRIVE_WAITING_RE.match(w):
            continue
        out.append({
            "runId": st.get("runId") or os.path.basename(os.path.dirname(sj)),
            "waiting": w,
            "repoRoot": st.get("repoRoot") or "?",
        })
    return out


def short(sid):
    return sid.split("-")[0] if sid else "?"


def home_rel(path):
    if not path:
        return "?"
    # Replace ONLY a leading $HOME prefix (str.replace would mangle a path that contains
    # $HOME more than once, e.g. a worktree path nested under another home-rooted dir).
    if path == HOME:
        return "~"
    if path.startswith(HOME + "/"):
        return "~/" + path[len(HOME) + 1:]
    return path


# status -> a glyph that reads at a glance; "waiting on me" is what matters most
STATUS_GLYPH = {
    "busy": "▶ working",
    "idle": "● idle",
    "shell": "○ shell",
    "waiting": "⏸ WAITING ON YOU",
}


def _append_drive_waits(lines, drive_waits):
    """Append the `/drive runs waiting on you:` section when non-empty (else nothing) —
    one `⏸ <runId> — <waiting> · <repoRoot>` line per parked run. Shared by both the
    no-live and the normal render paths so a parked /drive run surfaces even when its
    Claude session has already exited."""
    if not drive_waits:
        return
    lines.append("")
    lines.append("/drive runs waiting on you:")
    for w in drive_waits:
        lines.append(f"  ⏸ {w['runId']} — {w['waiting']} · {w['repoRoot']}")


def render(live, binds, now_str, summaries=None, drive_waits=None):
    lines = []
    lines.append(f"🛰️  MISSION CONTROL — Session Harvest · {now_str}")
    lines.append("")

    if not live:
        lines.append("No live Claude sessions found.")
        _append_drive_waits(lines, drive_waits)
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
        goal = s.get("goal") or "(untitled session)"
        color = s.get("color")
        proj = b.get("project")
        meta = []
        if color:
            meta.append(f"🎨{color}")
        meta.append(short(sid))
        meta.append(home_rel(s["cwd"]))
        if proj:
            meta.append(f"→ {proj}")
        # header line = the goal (iTerm tab name); detail line = status + meta
        lines.append("")
        lines.append(f"● {goal}{tag}")
        lines.append(f"    {glyph} · " + " · ".join(meta))
        summ = (summaries or {}).get(sid)
        if summ:
            if summ.get("progress"):
                lines.append(f"    progress: {summ['progress']}")
            if summ.get("next"):
                lines.append(f"    next:     {summ['next']}")

    if unbound:
        lines.append("")
        lines.append("Unbound sessions — tag them to a project/task (color & name are auto):")
        for sid, s, _ in unbound:
            lines.append(f"  mc bind {short(sid)} --project \"<Project>\" [--task <slug>]")

    _append_drive_waits(lines, drive_waits)
    return "\n".join(lines)


def build_summaries(live):
    """Per-session {progress, next} via headless claude, run in PARALLEL (each is an
    independent claude call, so N sessions take ~1 call's time, not N). Used by
    --summarize. Failures degrade to {} for that session."""
    import session_summary
    from concurrent.futures import ThreadPoolExecutor
    items = list(live.items())
    with ThreadPoolExecutor(max_workers=min(8, len(items) or 1)) as ex:
        results = ex.map(lambda kv: (kv[0], session_summary.summarize(
            kv[0], kv[1].get("goal") or "")), items)
    return {sid: summ for sid, summ in results if summ}


def main():
    now = datetime.now()
    live = load_live_sessions()
    binds = load_bindings()
    summaries = build_summaries(live) if "--summarize" in sys.argv else None
    out = render(live, binds, now.strftime("%Y-%m-%d %H:%M"), summaries,
                 drive_waits=drive_waiting_runs())
    print(out)
    if "--log" in sys.argv:
        path, created = log_to_vault(out, now)
        print(f"\n📝 logged to {path.replace(HOME, '~')}"
              + ("  (created)" if created else "  (appended)"))


if __name__ == "__main__":
    main()
