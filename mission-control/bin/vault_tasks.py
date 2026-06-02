#!/usr/bin/env python3
"""
Mission Control — vault task reader.

Parses one-task-per-file notes under the Obsidian vault's
`01 Projects/<Project>/Tasks/*.md` into structured task dicts. Importable
(used by standup.py / harvest.py) and runnable as a CLI (`mc tasks`).

Read-only. The vault is the source of truth; this never writes.
"""
import os
import re
import glob
from datetime import date, datetime

HOME = os.path.expanduser("~")
VAULT = os.path.join(HOME, "Documents", "Jia's Personal Vault")
TASKS_GLOB = os.path.join(VAULT, "01 Projects", "*", "Tasks", "*.md")

OPEN_STATUSES = {"todo", "doing", "waiting"}
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def _parse_scalar(v):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [x.strip().strip('"').strip("'") for x in inner.split(",")]
    return v.strip('"').strip("'")


def _parse_frontmatter(text):
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        fm[key.strip()] = _parse_scalar(val)
    return fm


def _title(text, fallback):
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _dod(text):
    """Extract the checkbox items under '## Definition of done' (the task's steps)."""
    items = []
    in_section = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_section = line.strip().lower().startswith("## definition of done")
            continue
        if in_section:
            m = re.match(r"\s*-\s*\[( |x|X)\]\s*(.+)", line)
            if m:
                items.append({"done": m.group(1).lower() == "x", "text": m.group(2).strip()})
    return items


def _as_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def load_tasks():
    """Return a list of task dicts parsed from the vault."""
    tasks = []
    for path in glob.glob(TASKS_GLOB):
        try:
            text = open(path).read()
        except Exception:
            continue
        fm = _parse_frontmatter(text)
        if fm.get("type") != "task":
            continue
        slug = os.path.splitext(os.path.basename(path))[0]
        project = (fm.get("project") or "").strip("[]")
        due = fm.get("due") or ""
        sched = fm.get("scheduled") or ""
        deps = fm.get("depends_on") or []
        if isinstance(deps, str):
            deps = [deps] if deps else []
        tasks.append({
            "slug": slug,
            "title": _title(text, slug),
            "project": project,
            "area": fm.get("area", ""),
            "status": fm.get("status", "todo"),
            "priority": fm.get("priority", "p3"),
            "due": due,
            "scheduled": sched,
            "needs_review": str(fm.get("needs_review", "")).lower() == "true",
            "tags": fm.get("tags", []),
            "depends_on": deps,
            "dod": _dod(text),
        })
    return tasks


def bucket(tasks):
    """Group open tasks into the buckets a daily standup needs."""
    today = date.today()
    open_tasks = [t for t in tasks if t["status"] in OPEN_STATUSES]
    overdue, due_today, due_week, waiting, backlog = [], [], [], [], []
    for t in open_tasks:
        d = _as_date(t["due"])
        if t["status"] == "waiting":
            waiting.append(t)
            continue
        if d and d < today:
            overdue.append(t)
        elif d and d == today:
            due_today.append(t)
        elif d and (d - today).days <= 7:
            due_week.append(t)
        elif not d and not t["scheduled"]:
            backlog.append(t)
    prio = lambda t: (t["priority"], t["due"] or "9999")
    return {
        "overdue": sorted(overdue, key=prio),
        "due_today": sorted(due_today, key=prio),
        "due_week": sorted(due_week, key=prio),
        "waiting": waiting,
        "backlog": sorted(backlog, key=prio),
        "open_count": len(open_tasks),
        "needs_review_count": sum(1 for t in tasks if t["needs_review"]),
    }


def main():
    tasks = load_tasks()
    b = bucket(tasks)
    print(f"{b['open_count']} open tasks · {len(b['overdue'])} overdue · "
          f"{len(b['due_today'])} due today · {len(b['due_week'])} due ≤7d · "
          f"{len(b['waiting'])} waiting · {b['needs_review_count']} need review")
    for label in ("overdue", "due_today", "due_week"):
        rows = b[label]
        if rows:
            print(f"\n[{label}]")
            for t in rows:
                print(f"  {t['priority']} {t['due'] or '—':<10} {t['title']}  ({t['project']})")


if __name__ == "__main__":
    main()
