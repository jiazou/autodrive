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
import vault_tasks

# Vault name for obsidian:// links — configurable via MC_VAULT_NAME (see vault_tasks.py).
VAULT_NAME = vault_tasks.VAULT_NAME
_BIN = os.path.dirname(os.path.abspath(__file__))
DONE_PY = os.path.join(_BIN, "done.py")

# A colored emoji dot carries the session's Claude /color while the name stays in
# default-readable text (SwiftBar's color= would tint the whole line). Keyed by the
# /color name. No cyan circle emoji exists, so cyan→🔵 (approx).
_CLAUDE_DOT = {
    "red": "🔴", "orange": "🟠", "yellow": "🟡", "green": "🟢",
    "blue": "🔵", "cyan": "🔵", "violet": "🟣", "purple": "🟣", "magenta": "🟣",
}


def _obsidian_href(slug):
    # Obsidian's URI handler does NOT decode "+" as a space, so urlencode's default
    # quote_plus breaks the vault name. Force %20 via quote_via=quote.
    q = urllib.parse.urlencode({"vault": VAULT_NAME, "file": slug},
                               quote_via=urllib.parse.quote)
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
        # submenu: mark done in place (calls done.py via this interpreter — SwiftBar's
        # PATH is minimal), then refresh; plus a direct open. The slug is percent-encoded
        # so a space / '|' can't split the param line or inject extra SwiftBar attributes
        # (done.py unquotes it). SwiftBar's shell= execs the binary directly — no shell —
        # so this is argument-safety, not RCE.
        L.append(f"--✓ Mark done | shell={sys.executable} param1={DONE_PY} "
                 f"param2={urllib.parse.quote(slug)} terminal=false refresh=true")
        L.append(f"--↗ Open in Obsidian | href={_obsidian_href(slug)}")
    L.append("---")
    L.append("Sessions | size=11 color=gray")
    for s in d["sessions"]:
        glyph = {"waiting": "⏸", "busy": "▶", "idle": "●", "shell": "○"}.get(s["status"], "·")
        # lead with the goal (iTerm tab name); fall back to id when untitled
        label = (s.get("goal") or s.get("name") or s["id"]).replace("|", "/")
        dot = _CLAUDE_DOT.get(s["color"], "")
        dot = f"{dot} " if dot else ""
        proj = f"  → {s['project']}" if s["project"] else ""
        # emoji dot carries the color; size=12 trims it; #000000 = pure black.
        # refresh=true makes the line ACTIONABLE → macOS renders it enabled (full
        # opacity); without an action it's a disabled item drawn dimmed, which washed
        # every color out (orange→yellow, black→grey). Click just refreshes the menu.
        L.append(f"{glyph} {dot}{label}{proj} | size=12 color=#000000 refresh=true")
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
