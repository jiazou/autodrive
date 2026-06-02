#!/usr/bin/env python3
"""
Mission Control — today: the glanceable single-surface view.

Powers two ambient layers off the same data:
  - terminal:  `today`            -> compact today list for iTerm
  - menu bar:  `today --swiftbar` -> SwiftBar menu-bar format

Reads the vault tasks + live sessions (via standup.gather). Read-only.
"""
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import standup

VAULT_NAME = "Jia's Personal Vault"


def _obsidian_href(slug):
    q = urllib.parse.urlencode({"vault": VAULT_NAME, "file": slug})
    return "obsidian://open?" + q


def _title_count(d):
    """Menu-bar title: overdue+due-today count + waiting-session count."""
    b = d["buckets"]
    due = len(b["overdue"]) + len(b["due_today"])
    waiting = sum(1 for s in d["sessions"] if s["status"] == "waiting")
    # keep this as narrow as possible — notched menu bars have little room
    title = f"☀{due}" if due else "☀"
    if waiting:
        title += f"⏸{waiting}"
    return title


def render_terminal(d):
    L = [_title_count(d) + f"   ({d['generated_at']})", ""]
    picks = standup.focus_slugs(d)
    if not picks:
        L.append("  no overdue or due-today tasks — pull from backlog")
    for slug in picks:
        L.append(f"  • {standup.title_of(d, slug)}")
    waiting = [s for s in d["sessions"] if s["status"] == "waiting"]
    if waiting:
        L.append("")
        L.append("  ⏸ agents waiting on you:")
        for s in waiting:
            label = s.get("goal") or s.get("name") or s["id"]
            L.append(f"     {label}  ({s['cwd']})")
    idle = d["spare_capacity"]
    if idle:
        L.append("")
        L.append(f"  🟢 {idle} idle session(s) — spare capacity to fan work out")
    return "\n".join(L)


def render_swiftbar(d):
    L = [_title_count(d), "---"]
    L.append(f"Today · {d['generated_at']} | size=11 color=gray")
    picks = standup.focus_slugs(d)
    if not picks:
        L.append("No overdue / due-today tasks | color=gray")
    for slug in picks:
        title = standup.title_of(d, slug).replace("|", "/")
        L.append(f"{title} | href={_obsidian_href(slug)}")
    L.append("---")
    L.append("Sessions | size=11 color=gray")
    for s in d["sessions"]:
        glyph = {"waiting": "⏸", "busy": "▶", "idle": "●", "shell": "○"}.get(s["status"], "·")
        col = s["color"] or "white"
        # lead with the goal (iTerm tab name); fall back to id when untitled
        label = (s.get("goal") or s.get("name") or s["id"]).replace("|", "/")
        proj = f"  → {s['project']}" if s["project"] else ""
        L.append(f"{glyph} {label}{proj} | color={col}")
    L.append("---")
    L.append("Refresh | refresh=true")
    L.append("Open today's note | href=" + _obsidian_href(d["generated_at"].split(" ")[0]))
    return "\n".join(L)


def main():
    d = standup.gather()
    if "--swiftbar" in sys.argv:
        print(render_swiftbar(d))
    else:
        print(render_terminal(d))


if __name__ == "__main__":
    main()
