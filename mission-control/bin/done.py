#!/usr/bin/env python3
"""
Mission Control — done: mark a vault task complete by slug.

The ONE writer into task notes. Resolves a slug to its file (via the vault_tasks
glob — the reader doesn't expose paths), flips `status:` -> done in the frontmatter,
clears the `needs_review` flag, and appends a dated line to the `## Log` section.

Idempotent: marking an already-done task is a no-op (exit 0). Accepts a slug with or
without `.md`.

Usage:
  mc done <slug>                  # e.g. mc done 2026-06-02-pa-rental
  mc done <slug> --status doing   # set an arbitrary status
"""
import os
import re
import sys
import glob
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vault_tasks

FM_RE = re.compile(r"^(---\n)(.*?)(\n---\n?)", re.DOTALL)


def _resolve(slug):
    """slug (or basename with/without .md) -> {path, title, status}, or None.

    Resolves against the filesystem directly (the shared reader doesn't expose
    paths), so this stays the single writer without depending on reader internals.
    """
    slug = slug.strip()
    if slug.endswith(".md"):
        slug = slug[:-3]
    for path in glob.glob(vault_tasks.TASKS_GLOB):
        if os.path.splitext(os.path.basename(path))[0] != slug:
            continue
        text = open(path).read()
        fm = vault_tasks._parse_frontmatter(text)
        if fm.get("type") != "task":
            continue
        return {"path": path, "title": vault_tasks._title(text, slug),
                "status": fm.get("status", "todo")}
    return None


def _set_fm_field(fm_body, key, value):
    """Replace `key: ...` line inside the frontmatter body, or add it before the end."""
    pat = re.compile(rf"^(\s*){re.escape(key)}\s*:.*$", re.MULTILINE)
    if pat.search(fm_body):
        return pat.sub(rf"\g<1>{key}: {value}", fm_body, count=1)
    sep = "" if fm_body.endswith("\n") else "\n"
    return f"{fm_body}{sep}{key}: {value}"


def _append_log(text, line):
    """Append a dated bullet at the end of the `## Log` section (or add the section)."""
    bullet = f"- {date.today().isoformat()} — {line}"
    if re.search(r"^##\s+Log\s*$", text, re.MULTILINE):
        return f"{text.rstrip(chr(10))}\n{bullet}\n"
    sep = "" if text.endswith("\n") else "\n"
    return f"{text}{sep}\n## Log\n{bullet}\n"


def mark(slug, status="done"):
    t = _resolve(slug)
    if not t:
        print(f"done: no task matches slug '{slug}'", file=sys.stderr)
        return 2
    text = open(t["path"]).read()
    m = FM_RE.match(text)
    if not m:
        print(f"done: {t['path']} has no frontmatter — refusing to edit", file=sys.stderr)
        return 3
    if t["status"] == status:
        print(f"done: '{t['title']}' is already {status} — nothing to do")
        return 0
    fm = _set_fm_field(m.group(2), "status", status)
    fm = _set_fm_field(fm, "needs_review", "false")
    new = m.group(1) + fm + m.group(3) + text[m.end():]
    new = _append_log(new, f"status -> {status} (via mc done).")
    open(t["path"], "w").write(new)
    print(f"✓ {t['title']}  →  {status}")
    return 0


def main():
    args = list(sys.argv[1:])
    status = "done"
    if "--status" in args:
        i = args.index("--status")
        status = args[i + 1]
        del args[i:i + 2]
    if not args:
        print("usage: mc done <slug> [--status <status>]", file=sys.stderr)
        return 1
    return mark(args[0], status)


if __name__ == "__main__":
    sys.exit(main())
