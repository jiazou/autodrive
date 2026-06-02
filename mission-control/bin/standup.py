#!/usr/bin/env python3
"""
Mission Control — standup: the data layer for the daily standup.

Joins the live Claude sessions (harvest) with the vault's open tasks
(vault_tasks) and classifies each open task as READY or BLOCKED using the
optional `depends_on` frontmatter. Emits structured JSON for the planning
skill to reason over, plus a human-readable summary.

Deterministic data only. The *parallel plan* itself is the skill's job —
this gives it clean inputs (sessions, buckets, ready/blocked, capacity).

Read-only.
"""
import os
import re
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harvest          # load_live_sessions, load_bindings, ensure_daily_note
import vault_tasks      # load_tasks, bucket, OPEN_STATUSES


def classify_ready(tasks):
    """A task is BLOCKED if any slug in its depends_on is still open; else READY."""
    open_slugs = {t["slug"] for t in tasks if t["status"] in vault_tasks.OPEN_STATUSES}
    ready, blocked = [], []
    for t in tasks:
        if t["status"] not in vault_tasks.OPEN_STATUSES:
            continue
        unmet = [d for d in t.get("depends_on", []) if d in open_slugs]
        if unmet:
            blocked.append({**t, "_unmet": unmet})
        else:
            ready.append(t)
    return ready, blocked


def focus_slugs(d):
    """Today's focus = overdue + due-today, capped at 5. Shared by the daily-note
    draft and the `today` glance views so the rule lives in one place."""
    return (d["buckets"]["overdue"] + d["buckets"]["due_today"])[:5]


def title_of(d, slug):
    return d["tasks_detail"].get(slug, {}).get("title", slug)


def gather():
    live = harvest.load_live_sessions()
    binds = harvest.load_bindings()
    tasks = vault_tasks.load_tasks()
    b = vault_tasks.bucket(tasks)
    ready, blocked = classify_ready(tasks)

    sessions = []
    for sid, s in live.items():
        bd = binds.get(sid, {})
        sessions.append({
            "id": sid[:8],
            "status": s["status"],
            "cwd": s["cwd"].replace(harvest.HOME, "~"),
            "color": s.get("color"),
            "name": s.get("name"),
            "goal": s.get("goal"),   # iTerm tab name
            "project": bd.get("project"),
            "task": bd.get("task"),
            "is_self": sid == harvest.SELF_ID,
        })
    # idle sessions = spare agent capacity to fan work out to
    spare = [s for s in sessions if s["status"] in ("idle", "shell")
             and not s["project"] and not s["is_self"]]
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sessions": sessions,
        "spare_capacity": len(spare),
        "buckets": {k: (v if isinstance(v, int) else [t["slug"] for t in v])
                    for k, v in b.items()},
        "ready": [{"slug": t["slug"], "title": t["title"], "project": t["project"],
                   "priority": t["priority"], "due": t["due"], "area": t["area"]}
                  for t in sorted(ready, key=lambda t: (t["priority"], t["due"] or "9999"))],
        "blocked": [{"slug": t["slug"], "title": t["title"], "blocked_on": t["_unmet"]}
                    for t in blocked],
        "tasks_detail": {t["slug"]: {
            "title": t["title"], "priority": t["priority"], "due": t["due"],
            "project": t["project"], "area": t["area"], "dod": t.get("dod", []),
        } for t in tasks},
    }


def human(d):
    L = [f"🗓  DAILY STANDUP · {d['generated_at']}", ""]
    b = d["buckets"]
    L.append(f"Tasks: {b['open_count']} open · {len(b['overdue'])} overdue · "
             f"{len(b['due_today'])} due today · {len(b['due_week'])} due ≤7d · "
             f"{len(b['waiting'])} waiting · {b['needs_review_count']} need review")
    L.append(f"Sessions: {len(d['sessions'])} live · {d['spare_capacity']} idle (spare capacity)")
    L.append("")
    L.append("Sessions:")
    for s in d["sessions"]:
        tag = " ⟵ this" if s["is_self"] else ""
        bind = f" → {s['project']}" if s["project"] else " (unbound)"
        col = f"🎨{s['color']}" if s["color"] else ""
        L.append(f"  {s['id']} {s['status']:<6} {col:<10} {s['cwd']}{bind}{tag}")
    if d["blocked"]:
        L.append("")
        L.append("Blocked (cannot start — waiting on a dependency):")
        for t in d["blocked"]:
            on = ", ".join(title_of(d, x) for x in t["blocked_on"])
            L.append(f"  ✗ {t['title']}  ← {on}")
    return "\n".join(L)


def SECTION_RE(h):
    return re.compile(r"(^##\s+" + re.escape(h) + r"\s*\n)(.*?)(?=^##\s|\Z)",
                      re.DOTALL | re.MULTILINE)


def _replace_or_append_section(text, heading, body):
    """Replace the body of '## <heading>' in-place, or append the section if absent."""
    pat = SECTION_RE(heading)
    repl = lambda m: m.group(1) + body
    if pat.search(text):
        return pat.sub(repl, text)
    sep = "" if text.endswith("\n") else "\n"
    return f"{text}{sep}\n## {heading}\n{body}"


def _focus_md(d):
    """Today's Focus = overdue + due-today, priority-sorted, capped at 5 — rendered
    SELF-CONTAINED: title, priority, due, project, and the task's Definition-of-Done
    steps inline, so the daily note is the one place; no clicking into task files."""
    detail = d["tasks_detail"]
    picks = focus_slugs(d)
    if not picks:
        return "_No overdue or due-today tasks. Pull from the backlog or due-this-week below._\n"
    lines = []
    for slug in picks:
        t = detail.get(slug, {})
        due = f" · due {t['due']}" if t.get("due") else ""
        proj = f" · _{t['project']}_" if t.get("project") else ""
        lines.append(f"- [ ] **{t.get('priority','').upper()}** {t.get('title', slug)}{due}{proj}  "
                     f"·  [open ↗](obsidian://open?file={slug})")
        for step in t.get("dod", []):
            box = "x" if step["done"] else " "
            lines.append(f"    - [{box}] {step['text']}")
    return "\n".join(lines) + "\n"


def _plan_md(d):
    stamp = d["generated_at"].split(" ")[1]
    L = [f"_Auto-drafted by Mission Control standup at {stamp} — review & adjust._\n"]
    L.append(f"**Capacity:** {len(d['sessions'])} live sessions, "
             f"**{d['spare_capacity']} idle** (spare agents to fan work out to).\n")
    ready = d["ready"]
    if ready:
        L.append("**Ready to start now** (no blocking dependency), priority order:")
        for t in ready[:8]:
            due = f" · due {t['due']}" if t["due"] else ""
            L.append(f"- {t['priority']} **{t['title']}** ({t['project']}{due})")
        L.append("")
    if d["blocked"]:
        L.append("**Blocked** (don't start — waiting on a dependency):")
        for t in d["blocked"]:
            on = ", ".join(title_of(d, x) for x in t["blocked_on"])
            L.append(f"- ✗ {t['title']} ← {on}")
        L.append("")
    waiting_sessions = [s for s in d["sessions"] if s["status"] == "waiting"]
    if waiting_sessions:
        L.append("**⏸ Agent sessions waiting on YOU** (unblock these first):")
        for s in waiting_sessions:
            L.append(f"- {s['id']} {('🎨'+s['color']) if s['color'] else ''} "
                     f"{s['cwd']}{(' → '+s['project']) if s['project'] else ''}")
        L.append("")
    return "\n".join(L)


def draft(d):
    """Write Today's Focus + Parallel Plan into the day's note (in-place, non-destructive
    to other sections). Creates the note from template if absent. Returns the path."""
    date_str = d["generated_at"].split(" ")[0]
    path, _ = harvest.ensure_daily_note(date_str)
    text = open(path).read()
    text = _replace_or_append_section(text, "Today's Focus", _focus_md(d))
    text = _replace_or_append_section(text, "Parallel Plan", _plan_md(d))
    open(path, "w").write(text)
    return path


def main():
    d = gather()
    if "--json" in sys.argv:
        print(json.dumps(d, indent=2))
        return
    print(human(d))
    if "--draft" in sys.argv:
        path = draft(d)
        print(f"\n📝 drafted Today's Focus + Parallel Plan → {path.replace(harvest.HOME, '~')}")


if __name__ == "__main__":
    main()
