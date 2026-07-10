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


def test_load_tasks_wikilink_project_coerced_to_scalar(mc_env, vault):
    """Regression: a `project: [[Autodrive]]` wikilink parses (via _parse_scalar) as a
    LIST, so `(fm.get('project') or '').strip('[]')` used to raise AttributeError and
    traceback every mc command + the 6:45am launchd job. load_tasks must coerce the
    list back to a scalar (the wikilink brackets stripped) instead of crashing."""
    vt = mc_env.vault_tasks
    vault.add_raw(
        "01 Projects/Autodrive/Tasks/wl-proj.md",
        "---\n"
        "type: task\n"
        "project: [[Autodrive]]\n"
        "status: [doing]\n"      # also a bracketed scalar -> list; must coerce too
        "priority: [p1]\n"
        "---\n"
        "# Wikilink project\n",
    )
    (task,) = vt.load_tasks()  # must NOT raise AttributeError
    assert task["project"] == "Autodrive"   # list->scalar, wikilink brackets stripped
    assert task["status"] == "doing"        # bracketed scalar coerced, not a list
    assert task["priority"] == "p1"
    assert isinstance(task["project"], str)


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


# =========================================================================== #
# Block-style YAML list parsing (Phase 1, AC 1-9)
# The `add_task` builder emits INLINE `[...]` lists, so every block-style fixture
# below uses `add_raw` to write the `key:` header + indented `  - item` lines.
# =========================================================================== #

# --------------------------------------------------------------------------- #
# AC 1 — block-style depends_on -> list
# --------------------------------------------------------------------------- #
def test_parse_frontmatter_block_depends_on_to_list(mc_env):
    vt = mc_env.vault_tasks
    text = (
        "---\n"
        "type: task\n"
        "depends_on:\n"
        "  - a\n"
        "  - b\n"
        "---\n"
        "# body\n"
    )
    fm = vt._parse_frontmatter(text)
    assert fm["depends_on"] == ["a", "b"]


def test_load_tasks_block_depends_on_to_list(mc_env, vault):
    vt = mc_env.vault_tasks
    vault.add_raw(
        "01 Projects/P1/Tasks/block-dep.md",
        "---\n"
        "type: task\n"
        "project: P1\n"
        "status: todo\n"
        "depends_on:\n"
        "  - a\n"
        "  - b\n"
        "---\n"
        "# Block dep\n",
    )
    (task,) = vt.load_tasks()
    assert task["depends_on"] == ["a", "b"]


# --------------------------------------------------------------------------- #
# AC 2 — block-style tags -> list
# --------------------------------------------------------------------------- #
def test_load_tasks_block_tags_to_list(mc_env, vault):
    vt = mc_env.vault_tasks
    vault.add_raw(
        "01 Projects/P1/Tasks/block-tags.md",
        "---\n"
        "type: task\n"
        "project: P1\n"
        "status: todo\n"
        "tags:\n"
        "  - x\n"
        "  - y\n"
        "---\n"
        "# Block tags\n",
    )
    (task,) = vt.load_tasks()
    assert task["tags"] == ["x", "y"]


# --------------------------------------------------------------------------- #
# AC 3 — an orphan `- item` line (no active list key) is skipped, no crash
# --------------------------------------------------------------------------- #
def test_parse_frontmatter_orphan_list_item_skipped_no_crash(mc_env):
    vt = mc_env.vault_tasks
    text = (
        "---\n"
        "type: task\n"
        "  - orphan\n"       # list marker with no active list key -> skipped
        "status: todo\n"
        "---\n"
    )
    fm = vt._parse_frontmatter(text)  # must NOT raise
    assert fm == {"type": "task", "status": "todo"}


# --------------------------------------------------------------------------- #
# AC 4 — a block item containing a colon is kept whole
# --------------------------------------------------------------------------- #
def test_parse_frontmatter_block_item_with_colon_kept_whole(mc_env):
    vt = mc_env.vault_tasks
    text = (
        "---\n"
        "type: task\n"
        "tags:\n"
        '  - "a:b"\n'
        "  - k:v\n"
        "---\n"
    )
    fm = vt._parse_frontmatter(text)
    assert fm["tags"] == ["a:b", "k:v"]


# --------------------------------------------------------------------------- #
# AC 5 — empty tags: -> [] AND empty depends_on: -> []
# --------------------------------------------------------------------------- #
def test_load_tasks_empty_block_headers_become_empty_lists(mc_env, vault):
    vt = mc_env.vault_tasks
    vault.add_raw(
        "01 Projects/P1/Tasks/empty-headers.md",
        "---\n"
        "type: task\n"
        "project: P1\n"
        "status: todo\n"
        "tags:\n"
        "depends_on:\n"
        "---\n"
        "# Empty headers\n",
    )
    (task,) = vt.load_tasks()
    assert task["tags"] == []
    assert task["depends_on"] == []


# --------------------------------------------------------------------------- #
# AC 6 — quoted block items match inline `[ "a", 'b' ]`
# --------------------------------------------------------------------------- #
def test_parse_frontmatter_block_quoted_items_match_inline(mc_env):
    vt = mc_env.vault_tasks
    block = vt._parse_frontmatter(
        "---\ntype: task\ntags:\n  - \"a\"\n  - 'b'\n---\n"
    )
    inline = vt._parse_frontmatter(
        "---\ntype: task\ntags: [ \"a\", 'b' ]\n---\n"
    )
    assert block["tags"] == ["a", "b"]
    assert block["tags"] == inline["tags"]


# --------------------------------------------------------------------------- #
# AC 7 — standup-level regression: block-`depends_on` with an open dep -> BLOCKED
#        (RED against pre-fix code, which drops the block list -> [] -> READY)
# --------------------------------------------------------------------------- #
def test_standup_classifies_block_depends_on_as_blocked(mc_env, vault):
    vt = mc_env.vault_tasks
    # An open dependency task (its slug is what the blocked task depends on).
    vault.add_task("dep-open", project="P1", status="todo")
    # The dependent task writes depends_on block-style (only add_raw can).
    vault.add_raw(
        "01 Projects/P1/Tasks/needs-dep.md",
        "---\n"
        "type: task\n"
        "project: P1\n"
        "status: todo\n"
        "depends_on:\n"
        "  - dep-open\n"
        "---\n"
        "# Needs dep\n",
    )
    ready, blocked = mc_env.standup.classify_ready(vt.load_tasks())
    blocked_slugs = {t["slug"] for t in blocked}
    ready_slugs = {t["slug"] for t in ready}
    assert "needs-dep" in blocked_slugs   # RED pre-fix: block list dropped -> ready
    assert "needs-dep" not in ready_slugs


# --------------------------------------------------------------------------- #
# AC 8 — scalar-key safety guard: a block list under a SCALAR key does not
#        corrupt the value and does not crash (RED against arm-on-any-key).
# --------------------------------------------------------------------------- #
def test_load_tasks_block_under_scalar_keys_no_corruption(mc_env, vault):
    vt = mc_env.vault_tasks
    vault.add_raw(
        "01 Projects/P1/Tasks/scalar-block.md",
        "---\n"
        "type: task\n"
        "project: P1\n"
        "status:\n"
        "  - done\n"          # arm-on-any-key would set status -> "done"
        "due:\n"
        "  - 2026-01-01\n"     # arm-on-any-key would make `due` a LIST -> bucket() crash
        "---\n"
        "# Scalar block\n",
    )
    tasks = vt.load_tasks()          # must NOT raise
    (task,) = tasks
    assert task["status"] == "todo"  # orphan `- done` skipped -> default, not "done"
    assert task["due"] == ""         # scalar, not a list
    assert not isinstance(task["due"], list)
    vt.bucket(tasks)                 # prio-sort over a scalar `due` -> no TypeError


def test_parse_frontmatter_block_under_scalar_key_disarms(mc_env):
    vt = mc_env.vault_tasks
    fm = vt._parse_frontmatter(
        "---\ntype: task\nstatus:\n  - done\n---\n"
    )
    # status is not a list key -> never armed -> `- done` orphaned -> status stays "".
    assert fm["status"] == ""
    assert not isinstance(fm["status"], list)


# =========================================================================== #
# Harden phase 1 — block-list edge cases (P1 regression + P2 coverage gaps)
# =========================================================================== #

# --------------------------------------------------------------------------- #
# [P1] A QUOTED-empty list value (`tags: ""` / `depends_on: ''`) parses to "" but
#      is NOT a bare header — it must NOT arm block accumulation, so a following
#      `- x` is DROPPED (matches base's strictly-additive contract, D9). Arming
#      keys off the RAW value, not `parsed`. RED against the pre-fix `parsed == ""`
#      arming, which absorbed the items into a block list.
# --------------------------------------------------------------------------- #
def test_parse_frontmatter_quoted_empty_list_value_does_not_arm(mc_env):
    vt = mc_env.vault_tasks
    text = (
        "---\n"
        "type: task\n"
        'tags: ""\n'          # quoted-empty scalar, NOT a bare header
        "  - x\n"             # dropped: accumulation is not armed
        "depends_on: ''\n"
        "  - a\n"             # dropped
        "---\n"
    )
    fm = vt._parse_frontmatter(text)
    assert fm["tags"] == ""          # pre-fix bug: ["x"]
    assert fm["depends_on"] == ""    # pre-fix bug: ["a"]
    # Contrast: a truly BARE `tags:` header DOES still arm (regression guard on the
    # correct-arm path — this fix must not disarm the legitimate bare header).
    bare = vt._parse_frontmatter("---\ntype: task\ntags:\n  - x\n---\n")
    assert bare["tags"] == ["x"]


def test_load_tasks_quoted_empty_list_value_becomes_empty_list(mc_env, vault):
    vt = mc_env.vault_tasks
    vault.add_raw(
        "01 Projects/P1/Tasks/quoted-empty.md",
        "---\n"
        "type: task\n"
        "project: P1\n"
        "status: todo\n"
        'tags: ""\n'
        "  - x\n"
        "depends_on: ''\n"
        "  - a\n"
        "---\n"
        "# Quoted empty\n",
    )
    (task,) = vt.load_tasks()
    assert task["tags"] == []        # "" -> [] (item x dropped; pre-fix: ["x"])
    assert task["depends_on"] == []  # "" -> [] (item a dropped; pre-fix: ["a"])


# --------------------------------------------------------------------------- #
# [P2] Empty-item skip (the `if item:` FALSE branch): a bare `- ` (nothing after
#      the marker) inside an ACTIVE list block is skipped (not appended as ""),
#      while a real following item still accumulates.
# --------------------------------------------------------------------------- #
def test_parse_frontmatter_empty_block_item_skipped(mc_env):
    vt = mc_env.vault_tasks
    text = (
        "---\n"
        "type: task\n"
        "depends_on:\n"
        "  - a\n"
        "  - \n"          # bare marker, nothing after -> skipped (not a "" entry)
        "  - b\n"
        "---\n"
    )
    fm = vt._parse_frontmatter(text)
    assert fm["depends_on"] == ["a", "b"]   # no stray "" between a and b


# --------------------------------------------------------------------------- #
# [P2] `active` disarm/rebind: two NON-EMPTY blocks in one note (depends_on THEN
#      tags) both land intact (the state transition from one list key holding
#      items to a second); and an INLINE list value (`tags: [a, b]`) DISARMS, so
#      a following `- c` is NOT absorbed.
# --------------------------------------------------------------------------- #
def test_parse_frontmatter_two_nonempty_blocks_rebind(mc_env):
    vt = mc_env.vault_tasks
    text = (
        "---\n"
        "type: task\n"
        "depends_on:\n"
        "  - a\n"
        "  - b\n"
        "tags:\n"
        "  - x\n"
        "  - y\n"
        "---\n"
    )
    fm = vt._parse_frontmatter(text)
    assert fm["depends_on"] == ["a", "b"]
    assert fm["tags"] == ["x", "y"]


def test_parse_frontmatter_inline_list_value_disarms(mc_env):
    vt = mc_env.vault_tasks
    text = (
        "---\n"
        "type: task\n"
        "tags: [a, b]\n"    # inline (non-blank) value -> disarms
        "  - c\n"           # orphan -> dropped, NOT absorbed into tags
        "---\n"
    )
    fm = vt._parse_frontmatter(text)
    assert fm["tags"] == ["a", "b"]   # `- c` not absorbed


# --------------------------------------------------------------------------- #
# [P2] CRLF inside a block list: depends_on/tags blocks written with `\r\n`
#      throughout parse to the correct lists (no stray `\r`).
# --------------------------------------------------------------------------- #
def test_parse_frontmatter_block_list_crlf(mc_env):
    vt = mc_env.vault_tasks
    text = (
        "---\r\n"
        "type: task\r\n"
        "depends_on:\r\n"
        "  - a\r\n"
        "  - b\r\n"
        "tags:\r\n"
        "  - x\r\n"
        "  - y\r\n"
        "---\r\n"
    )
    fm = vt._parse_frontmatter(text)
    assert fm["depends_on"] == ["a", "b"]
    assert fm["tags"] == ["x", "y"]   # no stray "\r"


# --------------------------------------------------------------------------- #
# [P2] Blank/comment interleaving inside an ACTIVE block does not disarm (D8 /
#      design edge case 8): blank and comment lines `continue` WITHOUT touching
#      `active`, so a block survives them and both items land -> ["a", "b"].
# --------------------------------------------------------------------------- #
def test_parse_frontmatter_blank_comment_inside_block_does_not_disarm(mc_env):
    vt = mc_env.vault_tasks
    text = (
        "---\n"
        "type: task\n"
        "depends_on:\n"
        "  - a\n"
        "\n"             # blank line inside the block -> does NOT disarm
        "  # note\n"     # comment line inside the block -> does NOT disarm
        "  - b\n"
        "---\n"
    )
    fm = vt._parse_frontmatter(text)
    assert fm["depends_on"] == ["a", "b"]   # block survives the interleaved blank/comment


# --------------------------------------------------------------------------- #
# [P2] A non-empty SCALAR value under a list key DISARMS (the `val.strip() != ""`
#      branch, distinct input shape from the inline-list disarm test): `tags:
#      somevalue` stays the scalar "somevalue" and a following `- c` is orphaned
#      (dropped), NOT absorbed. Complements test_parse_frontmatter_inline_list_
#      value_disarms (which uses the `tags: [a, b]` inline-list shape).
# --------------------------------------------------------------------------- #
def test_parse_frontmatter_scalar_value_under_list_key_disarms(mc_env):
    vt = mc_env.vault_tasks
    text = (
        "---\n"
        "type: task\n"
        "tags: somevalue\n"   # non-empty scalar value -> disarms
        "  - c\n"             # orphan -> dropped, NOT absorbed into tags
        "---\n"
    )
    fm = vt._parse_frontmatter(text)
    assert fm["tags"] == "somevalue"       # scalar preserved, `- c` not absorbed
    assert not isinstance(fm["tags"], list)
