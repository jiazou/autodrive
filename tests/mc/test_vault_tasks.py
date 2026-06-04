"""Slice 1.2 — vault_tasks parsing (AC 1, 2, 3, 4) + edge case #2.

Asserts the REAL behavior of mission-control/bin/vault_tasks.py:
- _parse_frontmatter / _parse_scalar (pure string -> dict/list)
- load_tasks (vault glob -> task dicts; type:task filter; slug; depends_on
  string->list coercion; _dod checkbox parse; [] on missing vault)
- _as_date (None for empty/garbage; a date for YYYY-MM-DD)

Builders come from tests/conftest.py: `vault` (add_task / add_raw) writes fixtures
the regex frontmatter parser accepts; `mc_env.vault_tasks` is the module reloaded
against the per-test fake HOME/MC_VAULT.
"""
import datetime

import pytest


# --------------------------------------------------------------------------- #
# AC 1 — _parse_frontmatter
# --------------------------------------------------------------------------- #
def test_parse_frontmatter_scalars_quotes_and_lists(mc_env):
    vt = mc_env.vault_tasks
    text = (
        "---\n"
        "type: task\n"
        'title: "A quoted title"\n'
        "single: 'sq'\n"
        "tags: [a, b, c]\n"
        "---\n"
        "# body\n"
    )
    fm = vt._parse_frontmatter(text)
    assert fm["type"] == "task"
    assert fm["title"] == "A quoted title"   # double quotes stripped
    assert fm["single"] == "sq"               # single quotes stripped
    assert fm["tags"] == ["a", "b", "c"]      # [a, b] -> list


def test_parse_frontmatter_skips_blank_comment_and_colonless_lines(mc_env):
    vt = mc_env.vault_tasks
    text = (
        "---\n"
        "type: task\n"
        "\n"                 # blank -> skipped
        "# a comment\n"      # comment -> skipped
        "  # indented comment\n"  # lstrip then '#' -> skipped
        "this line has no colon\n"  # colon-less -> skipped
        "status: doing\n"
        "---\n"
    )
    fm = vt._parse_frontmatter(text)
    assert fm == {"type": "task", "status": "doing"}


def test_parse_frontmatter_no_fence_returns_empty(mc_env):
    vt = mc_env.vault_tasks
    # No leading `---\n...\n---` fence -> {} (the regex .match fails).
    assert vt._parse_frontmatter("type: task\nstatus: todo\n") == {}
    assert vt._parse_frontmatter("# just a heading\n\nsome body\n") == {}


def test_parse_frontmatter_tolerates_bom_and_crlf(mc_env):
    """AC 1 BOM/CRLF: FRONTMATTER_RE is `^\\ufeff?---\\r?\\n(.*?)\\r?\\n---` — it
    strips an optional leading UTF-8 BOM and tolerates CRLF line endings, so notes
    saved by non-Obsidian editors still parse. A note with BOTH a BOM and CRLF must
    still yield the frontmatter dict. Drop the `\\ufeff?` or `\\r?` and this FAILS
    (the regex .match would miss the fence)."""
    vt = mc_env.vault_tasks
    text = (
        "﻿"            # leading UTF-8 BOM
        "---\r\n"            # CRLF line endings throughout
        "type: task\r\n"
        "status: doing\r\n"
        "priority: p1\r\n"
        "---\r\n"
        "# A BOM+CRLF note\r\n"
    )
    fm = vt._parse_frontmatter(text)
    assert fm == {"type": "task", "status": "doing", "priority": "p1"}


def test_load_tasks_includes_bom_crlf_note(mc_env, vault):
    """AC 3 BOM/CRLF end-to-end: a real .md file written with a UTF-8 BOM + CRLF must
    flow through load_tasks (glob -> open().read() -> _parse_frontmatter) and appear
    as a parsed task. add_raw writes the BOM as a genuine 3-byte UTF-8 BOM (write_text
    encodes the leading \\ufeff). If the BOM/CRLF tolerance regressed, this note would
    be silently invisible and the assertion FAILS."""
    vt = mc_env.vault_tasks
    vault.add_raw(
        "01 Projects/P1/Tasks/bom-crlf.md",
        "﻿"
        "---\r\n"
        "type: task\r\n"
        "project: P1\r\n"
        "status: todo\r\n"
        "priority: p1\r\n"
        "---\r\n"
        "# BOM CRLF Task\r\n",
    )
    tasks = vt.load_tasks()
    by_slug = {t["slug"]: t for t in tasks}
    assert "bom-crlf" in by_slug, "BOM/CRLF note dropped by load_tasks"
    t = by_slug["bom-crlf"]
    assert t["status"] == "todo"
    assert t["priority"] == "p1"
    assert t["title"] == "BOM CRLF Task"


# --------------------------------------------------------------------------- #
# AC 2 — _parse_scalar
# --------------------------------------------------------------------------- #
def test_parse_scalar_strips_quotes(mc_env):
    vt = mc_env.vault_tasks
    assert vt._parse_scalar('  "hello"  ') == "hello"
    assert vt._parse_scalar("'world'") == "world"
    assert vt._parse_scalar("bare") == "bare"


def test_parse_scalar_inline_list_and_empty_list(mc_env):
    vt = mc_env.vault_tasks
    assert vt._parse_scalar("[x, y]") == ["x", "y"]
    assert vt._parse_scalar('["q", \'r\']') == ["q", "r"]  # per-item quote strip
    assert vt._parse_scalar("[]") == []                    # empty list
    assert vt._parse_scalar("[  ]") == []                  # whitespace-only -> []


# --------------------------------------------------------------------------- #
# AC 3 — load_tasks
# --------------------------------------------------------------------------- #
def test_load_tasks_includes_only_type_task(mc_env, vault):
    vt = mc_env.vault_tasks
    vault.add_task("real-task", project="P1")
    # A non-task note under Tasks/ (type: note) must be excluded.
    vault.add_raw(
        "01 Projects/P1/Tasks/note.md",
        "---\ntype: note\nstatus: todo\n---\n# Not a task\n",
    )
    slugs = {t["slug"] for t in vt.load_tasks()}
    assert slugs == {"real-task"}


def test_load_tasks_slug_from_filename_and_title(mc_env, vault):
    vt = mc_env.vault_tasks
    vault.add_task("my-slug", project="P1", title="Human Title")
    (task,) = vt.load_tasks()
    assert task["slug"] == "my-slug"       # from filename, not frontmatter
    assert task["title"] == "Human Title"  # from the `# ` H1 via _title


def test_load_tasks_depends_on_string_coerced_to_list(mc_env, vault):
    vt = mc_env.vault_tasks
    # The builder emits depends_on as a list; to exercise the string->list
    # coercion in load_tasks we write the frontmatter raw with a scalar value.
    vault.add_raw(
        "01 Projects/P1/Tasks/dep-scalar.md",
        "---\n"
        "type: task\n"
        "project: P1\n"
        "status: todo\n"
        "depends_on: other-slug\n"
        "---\n"
        "# Dep scalar\n",
    )
    (task,) = vt.load_tasks()
    assert task["depends_on"] == ["other-slug"]


def test_load_tasks_depends_on_empty_string_becomes_empty_list(mc_env, vault):
    vt = mc_env.vault_tasks
    vault.add_raw(
        "01 Projects/P1/Tasks/dep-empty.md",
        "---\ntype: task\nproject: P1\nstatus: todo\ndepends_on: \n---\n# Empty dep\n",
    )
    (task,) = vt.load_tasks()
    # `depends_on:` with empty value -> _parse_scalar "" -> falsy -> [] (not [""])
    assert task["depends_on"] == []


def test_load_tasks_depends_on_list_preserved(mc_env, vault):
    vt = mc_env.vault_tasks
    vault.add_task("dep-list", project="P1", depends_on=["a", "b"])
    (task,) = vt.load_tasks()
    assert task["depends_on"] == ["a", "b"]


def test_load_tasks_parses_definition_of_done_checkboxes(mc_env, vault):
    vt = mc_env.vault_tasks
    path = vault.add_task("with-dod", project="P1", dod=["step one", "step two"])
    # Builder writes all `- [ ]` (unchecked). Flip one to checked at the source
    # so we assert the real done/text parse, not a fixture-only value.
    text = path.read_text().replace("- [ ] step one", "- [x] step one")
    path.write_text(text)
    (task,) = vt.load_tasks()
    assert task["dod"] == [
        {"done": True, "text": "step one"},
        {"done": False, "text": "step two"},
    ]


def test_load_tasks_needs_review_and_tags(mc_env, vault):
    vt = mc_env.vault_tasks
    vault.add_task("flagged", project="P1", needs_review=True, tags=["urgent", "x"])
    (task,) = vt.load_tasks()
    assert task["needs_review"] is True
    assert task["tags"] == ["urgent", "x"]


# --------------------------------------------------------------------------- #
# AC 4 — load_tasks returns [] on a missing vault dir (edge case #1)
# --------------------------------------------------------------------------- #
def test_load_tasks_missing_vault_returns_empty(mc_env):
    vt = mc_env.vault_tasks
    # No vault fixtures written this test; MC_VAULT points at a non-existent dir.
    assert not mc_env.vault.exists()
    assert vt.load_tasks() == []   # glob -> [] -> no crash


# --------------------------------------------------------------------------- #
# AC 4 — _as_date (date coercion used by bucket; AC 6 is the import-smoke in
#         test_smoke_imports.py — not this section)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", ["", None, "not-a-date", "2026/06/03", "2026-13-40"])
def test_as_date_none_for_empty_or_garbage(mc_env, bad):
    assert mc_env.vault_tasks._as_date(bad) is None


def test_as_date_parses_iso(mc_env):
    assert mc_env.vault_tasks._as_date("2026-06-03") == datetime.date(2026, 6, 3)


# --------------------------------------------------------------------------- #
# Edge case #2 — malformed frontmatter
# --------------------------------------------------------------------------- #
def test_malformed_frontmatter_skips_bad_lines_keeps_good(mc_env):
    vt = mc_env.vault_tasks
    text = (
        "---\n"
        "type: task\n"
        "garbage line with no colon\n"
        "# comment\n"
        "\n"
        "   indented: kept\n"   # leading whitespace stripped off key
        "---\n"
    )
    fm = vt._parse_frontmatter(text)
    assert fm == {"type": "task", "indented": "kept"}


def test_load_tasks_excludes_note_with_no_frontmatter(mc_env, vault):
    vt = mc_env.vault_tasks
    vault.add_task("good", project="P1")
    # No fence at all -> _parse_frontmatter {} -> fm.get("type") != "task" -> excluded.
    vault.add_raw(
        "01 Projects/P1/Tasks/no-fence.md",
        "type: task\nstatus: todo\n\n# Looks like a task but has no fence\n",
    )
    slugs = {t["slug"] for t in vt.load_tasks()}
    assert slugs == {"good"}
