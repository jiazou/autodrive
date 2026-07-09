#!/usr/bin/env python3
"""
Mission Control — done: mark a vault task complete by slug.

The ONE writer into task notes. Resolves a slug to its file (via the vault_tasks
glob — the reader doesn't expose paths), flips the TOP-LEVEL `status:` -> done in
the frontmatter, clears the `needs_review` flag, and appends a dated line inside
the `## Log` section.

Safety properties (this is the sole writer for source-of-truth task files):
- Atomic write (temp file + os.replace) — a crash can never leave a half-written note.
- Top-level-only frontmatter edits (column 0) — never rewrites a nested/indented or
  commented `status:`/`needs_review:`. Line-wise, so the rest of the user's
  hand-written frontmatter is preserved byte-for-byte (no YAML round-trip churn).
- UTF-8 throughout (vault notes contain emoji / em dashes).

Idempotent: if the task is already at the target status AND needs_review is clear,
it's a no-op (exit 0). Accepts a slug with or without `.md`.

Usage:
  mc done <slug>                  # e.g. mc done 2026-06-02-pa-rental
  mc done <slug> --status doing   # set an arbitrary status
"""
import os
import re
import sys
import glob
import urllib.parse
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vault_tasks

# Tolerates an optional UTF-8 BOM and CRLF line endings (the `\r?\n` alternation
# matches both LF and CRLF) so a note saved by a non-Obsidian editor isn't refused
# as "no frontmatter".
FM_RE = re.compile(r"^(\ufeff?---\r?\n)(.*?)(\r?\n---\r?\n?)", re.DOTALL)
# Bounded '## Log' section: heading line + body up to the next '## ' heading or EOF.
# The heading requires a LINE BOUNDARY after `Log` (a newline or EOF, allowing only
# horizontal whitespace before it) so it can't prefix-match a longer heading like
# `## Logistics` / `## Logs` / `## Logbook` and corrupt those notes. The boundary is
# `(?:\r?\n|\Z)` — matching a `## Log` heading on the file's FINAL line with no
# trailing newline (common for editor-saved notes) as well as CRLF/LF-terminated ones.
LOG_SECTION_RE = re.compile(r"(^##[ \t]+Log[ \t]*(?:\r?\n|\Z))(.*?)(?=^##\s|\Z)", re.DOTALL | re.MULTILINE)


def _resolve(slug):
    """slug (or basename, with/without .md) -> list of {path,title,status,needs_review}
    for every type:task note whose filename matches. Resolves against the filesystem
    directly (the shared reader doesn't expose paths). Returns [] if none match; the
    caller refuses to act on an ambiguous (>1) match rather than guess."""
    slug = slug.strip()
    if slug.endswith(".md"):
        slug = slug[:-3]
    hits = []
    for path in glob.glob(vault_tasks.TASKS_GLOB):
        if os.path.splitext(os.path.basename(path))[0] != slug:
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        fm = vault_tasks._parse_frontmatter(text)
        if fm.get("type") != "task":
            continue
        hits.append({
            "path": path,
            "title": vault_tasks._title(text, slug),
            "status": fm.get("status", "todo"),
            "needs_review": str(fm.get("needs_review", "")).lower() == "true",
        })
    return hits


def _set_top_level_field(fm_body, key, value):
    """Replace a TOP-LEVEL `key: ...` line (column 0 only) in the frontmatter body, or
    append it. Never matches a nested/indented or commented occurrence, and edits
    line-wise so the rest of the frontmatter is untouched."""
    pat = re.compile(rf"^{re.escape(key)}[ \t]*:.*$", re.MULTILINE)
    if pat.search(fm_body):
        # function replacement avoids backreference/escape surprises in `value`
        return pat.sub(lambda _m: f"{key}: {value}", fm_body, count=1)
    sep = "" if (not fm_body or fm_body.endswith("\n")) else "\n"
    return f"{fm_body}{sep}{key}: {value}"


def _append_log(text, line):
    """Append a dated bullet at the END of the `## Log` section (bounded by the next
    heading), or create the section at EOF if absent."""
    bullet = f"- {date.today().isoformat()} — {line}"
    m = LOG_SECTION_RE.search(text)
    if m:
        # Normalize the heading to end with a newline: when `## Log` was the file's final
        # line with no trailing newline, group(1) has none, and concatenating the bullet
        # would yield `## Log- …` on one line.
        head = m.group(1) if m.group(1).endswith("\n") else m.group(1) + "\n"
        body = m.group(2).rstrip("\n")
        new_section = head + (body + "\n" if body else "") + bullet + "\n"
        return text[:m.start()] + new_section + text[m.end():]
    sep = "" if text.endswith("\n") else "\n"
    return f"{text}{sep}\n## Log\n{bullet}\n"


def mark(slug, status="done"):
    hits = _resolve(slug)
    if not hits:
        print(f"done: no task matches slug '{slug}'", file=sys.stderr)
        return 2
    if len(hits) > 1:
        print(f"done: '{slug}' is ambiguous — {len(hits)} tasks match:", file=sys.stderr)
        for h in hits:
            print(f"  {h['path']}", file=sys.stderr)
        print("refusing to edit; the slug collides across projects.", file=sys.stderr)
        return 2
    t = hits[0]
    with open(t["path"], encoding="utf-8") as fh:
        text = fh.read()
    # _resolve() validated the fence on a SEPARATE read; this is a second read, so the
    # file could have changed in between (TOCTOU) — e.g. its frontmatter stripped. Guard
    # against that race rather than crashing on m.group(): refuse to edit and exit 3.
    m = FM_RE.match(text)
    if not m:
        print(f"done: {t['path']} frontmatter changed underfoot — refusing to edit",
              file=sys.stderr)
        return 3

    need_status = t["status"] != status
    need_clear = t["needs_review"]
    if not need_status and not need_clear:
        print(f"done: '{t['title']}' is already {status} — nothing to do")
        return 0

    fm = m.group(2)
    changes = []
    if need_status:
        fm = _set_top_level_field(fm, "status", status)
        changes.append(f"status -> {status}")
    if need_clear:
        fm = _set_top_level_field(fm, "needs_review", "false")
        changes.append("cleared needs_review")
    new = m.group(1) + fm + m.group(3) + text[m.end():]
    new = _append_log(new, ", ".join(changes) + " (via mc done).")
    vault_tasks.atomic_write(t["path"], new)
    print(f"✓ {t['title']}  →  {status}")
    return 0


def main():
    args = list(sys.argv[1:])
    status = "done"
    if "--status" in args:
        i = args.index("--status")
        if i + 1 >= len(args):
            print("usage: mc done <slug> [--status <status>]", file=sys.stderr)
            return 1
        status = args[i + 1]
        del args[i:i + 2]
    if not args:
        print("usage: mc done <slug> [--status <status>]", file=sys.stderr)
        return 1
    if not status or "\n" in status or "\r" in status:
        print("done: --status must be a single line with no newlines", file=sys.stderr)
        return 1
    # The SwiftBar menu passes the slug percent-encoded (so spaces / '|' can't break
    # the param line); unquote is a no-op for normal date-prefixed slugs.
    slug = urllib.parse.unquote(args[0])
    return mark(slug, status)


if __name__ == "__main__":
    sys.exit(main())
