#!/usr/bin/env python3
"""
Mission Control — weekly review agenda.

Gathers what the weekly review needs in one place: the Needs-Review queue, open
tasks grouped by project, the overdue pile, and the stale backlog. The `weekly`
skill drives the actual review (accept/close/re-prioritize) over this agenda.

Read-only.
"""
import os
import sys
import json
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vault_tasks


def gather():
    tasks = vault_tasks.load_tasks()
    open_t = [t for t in tasks if t["status"] in vault_tasks.OPEN_STATUSES]
    b = vault_tasks.bucket(tasks)
    by_project = defaultdict(list)
    for t in open_t:
        by_project[t["project"] or "(no project)"].append(t)
    needs_review = [t for t in tasks if t["needs_review"]]
    return {
        "open_count": len(open_t),
        "needs_review": needs_review,
        "by_project": by_project,
        "overdue": b["overdue"],
        "waiting": b["waiting"],
        "backlog": b["backlog"],
    }


def main():
    d = gather()
    if "--json" in sys.argv:
        print(json.dumps({
            "open_count": d["open_count"],
            "needs_review": [t["slug"] for t in d["needs_review"]],
            "overdue": [t["slug"] for t in d["overdue"]],
            "waiting": [t["slug"] for t in d["waiting"]],
            "backlog": [t["slug"] for t in d["backlog"]],
            "by_project": {p: [t["slug"] for t in ts] for p, ts in d["by_project"].items()},
        }, indent=2))
        return

    print(f"🗓  WEEKLY REVIEW · {d['open_count']} open tasks · "
          f"{len(d['needs_review'])} need review · {len(d['overdue'])} overdue\n")

    if d["needs_review"]:
        print(f"① NEEDS REVIEW — {len(d['needs_review'])} Claude-written tasks awaiting your sign-off:")
        for t in d["needs_review"]:
            print(f"   ☐ {t['priority']} {t['title']}  ({t['project']})")
        print()

    print("② BY PROJECT — sweep each: close done · drop stale · re-prioritize:")
    for proj, ts in sorted(d["by_project"].items()):
        print(f"   ▸ {proj}  ({len(ts)} open)")
        for t in sorted(ts, key=lambda x: (x["priority"], x["due"] or "9999")):
            due = f" due {t['due']}" if t["due"] else ""
            print(f"       {t['priority']} {t['title']}{due}")
    print()

    if d["overdue"]:
        print("③ OVERDUE — reset the due date or do it this week:")
        for t in d["overdue"]:
            print(f"   ⚠ {t['priority']} {t['title']} (was due {t['due']})")
        print()

    if d["backlog"]:
        print(f"④ BACKLOG — {len(d['backlog'])} someday/maybe. Promote 1-2 with room:")
        for t in d["backlog"][:8]:
            print(f"   · {t['priority']} {t['title']}")


if __name__ == "__main__":
    main()
