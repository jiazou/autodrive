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
import urllib.parse
from datetime import date, datetime

HOME = os.path.expanduser("~")


def _config_value(key):
    """Read KEY=VALUE from ~/mission-control/config (written by install.sh).
    This is how the 6:45am launchd job and the SwiftBar plugin — which run with a
    bare environment and do NOT inherit your shell profile — learn MC_VAULT /
    MC_VAULT_NAME. An explicit environment variable always takes precedence."""
    cfg = os.path.join(HOME, "mission-control", "config")
    try:
        with open(cfg, encoding="utf-8") as fh:
            for line in fh:
                k, sep, val = line.partition("=")
                if sep and k.strip() == key:
                    return val.strip() or None
    except OSError:
        return None
    return None


# Vault location, resolved in priority order so it works in EVERY launch context:
#   1. MC_VAULT env var          (interactive shells)
#   2. ~/mission-control/config  (launchd / SwiftBar — no shell env; see install.sh)
#   3. ~/Documents/Vault         (default)
VAULT = (os.environ.get("MC_VAULT") or _config_value("MC_VAULT")
         or os.path.join(HOME, "Documents", "Vault"))
VAULT_NAME = (os.environ.get("MC_VAULT_NAME") or _config_value("MC_VAULT_NAME")
              or os.path.basename(VAULT.rstrip("/")))
TASKS_GLOB = os.path.join(VAULT, "01 Projects", "*", "Tasks", "*.md")


def atomic_write(path, data):
    """Write `data` to `path` atomically: temp file in the same dir, fsync, os.replace.
    A crash mid-write can never leave a half-written note — the readers either see the
    old file or the new one. Shared by every writer (done/standup/harvest)."""
    d = os.path.dirname(path) or "."
    tmp = os.path.join(d, f".{os.path.basename(path)}.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def obsidian_href(slug):
    """Build an obsidian:// deep link to a note. Obsidian's URI handler does NOT
    decode '+' as a space, so force %20 via quote_via=quote (urlencode's default
    quote_plus would break the vault name). Shared by today.py and standup.py."""
    q = urllib.parse.urlencode({"vault": VAULT_NAME, "file": slug},
                               quote_via=urllib.parse.quote)
    return "obsidian://open?" + q


OPEN_STATUSES = {"todo", "doing", "waiting"}
# The only frontmatter keys that are list-valued; block-style `- item` accumulation
# arms ONLY for these. A `- ` line under any scalar key stays a skipped colon-less line,
# so a malformed `status:` / `due:` block can never corrupt a scalar value or crash bucket().
_LIST_KEYS = frozenset(("depends_on", "tags"))
# Tolerate an optional UTF-8 BOM and CRLF line endings so notes saved by editors
# other than Obsidian still parse (otherwise the task is silently invisible).
FRONTMATTER_RE = re.compile(r"^\ufeff?---\r?\n(.*?)\r?\n---", re.DOTALL)


def _parse_scalar(v):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [x.strip().strip('"').strip("'") for x in inner.split(",")]
    return v.strip('"').strip("'")


def _scalar(v, default=""):
    """Coerce a frontmatter value that may have parsed as a LIST back to a scalar.
    `_parse_scalar` turns any bracketed value into a list, so a wikilink like
    `project: [[Autodrive]]` (or `status: [doing]`) arrives here as a one-element
    list; the standup/harvest readers want a single string. Mirrors the depends_on
    str->list guard in the opposite direction. Empty/absent -> default."""
    if isinstance(v, list):
        v = v[0] if v else ""
    return v if v else default


def _parse_frontmatter(text):
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fm = {}
    active = None  # a depends_on/tags key currently absorbing block-list `- item` lines
    for line in m.group(1).splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            # Block-list continuation item. This branch MUST precede the ":" branch
            # so an item that itself contains a colon (`- "a:b"`, `- k:v`) is kept
            # whole. It appends ONLY when `active` is a list key (depends_on/tags);
            # an orphan `- ` (active is None) is skipped, like a colon-less line.
            if active is not None:
                item = stripped[2:].strip().strip('"').strip("'")
                if item:
                    if not isinstance(fm.get(active), list):
                        fm[active] = []
                    fm[active].append(item)
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        parsed = _parse_scalar(val)
        fm[key] = parsed
        # Arm block accumulation ONLY for an empty-valued LIST key; anything else disarms.
        active = key if (parsed == "" and key in _LIST_KEYS) else None
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
            with open(path) as fh:
                text = fh.read()
        except Exception:
            continue
        fm = _parse_frontmatter(text)
        if fm.get("type") != "task":
            continue
        slug = os.path.splitext(os.path.basename(path))[0]
        project = _scalar(fm.get("project")).strip("[]")
        due = fm.get("due") or ""
        sched = fm.get("scheduled") or ""
        deps = fm.get("depends_on") or []
        if isinstance(deps, str):
            deps = [deps] if deps else []
        tasks.append({
            "slug": slug,
            "title": _title(text, slug),
            "project": project,
            "area": _scalar(fm.get("area")),
            "status": _scalar(fm.get("status"), "todo"),
            "priority": _scalar(fm.get("priority"), "p3"),
            "due": due,
            "scheduled": sched,
            "needs_review": str(fm.get("needs_review", "")).lower() == "true",
            "tags": fm.get("tags") or [],
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
        else:
            # Everything else open (due >7d out, or scheduled-with-no-due, or
            # truly unscheduled) lands in backlog so no open task silently
            # vanishes from the weekly sweep. open_count == sum of all buckets.
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
