"""Slice 1.5 — done writer (AC 18, 19; edge cases #2, #7).

Asserts the REAL behavior of mission-control/bin/done.py:mark, against fixtures
built with the `vault` builder and read back off disk. Exit codes follow design D9 /
followup F1 (frontmatter-less file -> exit 2, NOT the unreachable exit-3 branch).
"""
from datetime import date


# --------------------------------------------------------------------------- #
# AC 18 — done.mark rewrites the note
# --------------------------------------------------------------------------- #
def test_mark_flips_status_clears_review_appends_log_preserves_other_fm(mc_env, vault):
    path = vault.add_task(
        "2026-06-02-pa-rental",
        project="P",
        status="doing",
        priority="p1",
        needs_review=True,
        tags=["home", "errand"],
        title="Sign the rental",
        extra_frontmatter="custom_field: keep-me",
    )

    before = path.read_text(encoding="utf-8")
    rc = mc_env.done.mark("2026-06-02-pa-rental")
    assert rc == 0

    text = path.read_text(encoding="utf-8")

    # top-level status flipped to done, needs_review cleared
    assert "status: done" in text
    assert "status: doing" not in text
    assert "needs_review: false" in text
    assert "needs_review: true" not in text

    # other frontmatter preserved
    assert "priority: p1" in text
    assert "tags: [home, errand]" in text
    assert "custom_field: keep-me" in text
    assert "type: task" in text

    # AC18 — UNRELATED frontmatter lines must survive BYTE-FOR-BYTE. Only the two
    # edited keys (status, needs_review) may differ; every other frontmatter line is
    # asserted byte-identical against the pre-write file. A reorder/round-trip/rewrite
    # regression that re-serialized the frontmatter would change these and FAIL here.
    def _fm_lines(s):
        # frontmatter body between the first two '---' fences
        body = s.split("---\n", 2)[1]
        return body.splitlines()

    before_fm = _fm_lines(before)
    after_fm = _fm_lines(text)
    edited_keys = ("status:", "needs_review:")
    unrelated_before = [ln for ln in before_fm if not ln.startswith(edited_keys)]
    unrelated_after = [ln for ln in after_fm if not ln.startswith(edited_keys)]
    assert unrelated_before == unrelated_after  # byte-identical, same order
    # and concretely the load-bearing ones survive verbatim
    for line in ("type: task", "project: P", "priority: p1",
                 "tags: [home, errand]", "custom_field: keep-me"):
        assert line in unrelated_after

    # dated ## Log bullet appended
    assert "## Log" in text
    new_bullet = f"- {date.today().isoformat()} —"
    assert new_bullet in text
    assert "status -> done" in text
    assert "cleared needs_review" in text

    # AC18 — the Log section was CREATED (none existed) and the dated bullet is the
    # LAST non-empty line of that section (appended at the END, not prepended).
    log_body = text.split("## Log\n", 1)[1]
    log_bullets = [ln for ln in log_body.splitlines() if ln.strip()]
    assert log_bullets[-1].startswith(new_bullet)

    # AC18 — atomic write left NO .tmp/dotfile residue in the Tasks dir; the only
    # file present is the rewritten task note with the rewritten content on disk.
    residue = [p.name for p in path.parent.iterdir() if p.name != path.name]
    assert residue == []
    assert path.read_text(encoding="utf-8") == text


def test_mark_atomic_no_temp_left_behind(mc_env, vault):
    path = vault.add_task("solo-task", status="todo", needs_review=False)
    rc = mc_env.done.mark("solo-task")
    assert rc == 0
    # _atomic_write uses os.replace; the .<name>.tmp must not survive
    tmp = path.parent / f".{path.name}.tmp"
    assert not tmp.exists()
    assert "status: done" in path.read_text(encoding="utf-8")


def test_mark_appends_to_existing_log_section(mc_env, vault):
    path = vault.add_task(
        "with-log", status="todo", needs_review=False,
        body="## Log\n- 2026-01-01 — created\n- 2026-01-02 — touched\n",
    )
    rc = mc_env.done.mark("with-log")
    assert rc == 0
    text = path.read_text(encoding="utf-8")
    # existing bullets preserved, in their original order
    assert "- 2026-01-01 — created" in text
    assert "- 2026-01-02 — touched" in text
    assert text.count("## Log") == 1

    # AC18 — the new dated bullet is APPENDED at the END of the existing Log section:
    # it is the LAST bullet, and the two pre-existing bullets keep their relative
    # order (not prepended/reordered). A prepend regression would put the new bullet
    # first and FAIL the `[-1]` assertion below.
    new_bullet = f"- {date.today().isoformat()} —"
    log_body = text.split("## Log\n", 1)[1]
    bullets = [ln for ln in log_body.splitlines() if ln.strip().startswith("- ")]
    assert bullets[0] == "- 2026-01-01 — created"
    assert bullets[1] == "- 2026-01-02 — touched"
    assert bullets[-1].startswith(new_bullet)

    # atomic write: no .tmp/dotfile residue left behind in the Tasks dir
    residue = [p.name for p in path.parent.iterdir() if p.name != path.name]
    assert residue == []


# --------------------------------------------------------------------------- #
# AC 19 — exit codes (design D9, followup F1)
# --------------------------------------------------------------------------- #
def test_mark_idempotent_already_done_no_write(mc_env, vault):
    """Already done + needs_review clear -> exit 0, NO write (mtime unchanged)."""
    path = vault.add_task("done-already", status="done", needs_review=False)
    before = path.read_text(encoding="utf-8")
    mtime_before = path.stat().st_mtime_ns

    rc = mc_env.done.mark("done-already")

    assert rc == 0
    assert path.read_text(encoding="utf-8") == before
    # no-op path returns before any _atomic_write, so the file is untouched
    assert path.stat().st_mtime_ns == mtime_before
    assert "## Log" not in before  # and none was added


def test_mark_no_match_returns_2(mc_env, vault):
    vault.add_task("real-task")
    assert mc_env.done.mark("does-not-exist") == 2


def test_mark_ambiguous_returns_2_and_writes_nothing(mc_env, vault):
    """Same slug in two projects -> ambiguous -> exit 2, neither file rewritten."""
    p1 = vault.add_task("dup-slug", project="ProjA", status="todo", needs_review=True)
    p2 = vault.add_task("dup-slug", project="ProjB", status="todo", needs_review=True)
    before1, before2 = p1.read_text(encoding="utf-8"), p2.read_text(encoding="utf-8")

    rc = mc_env.done.mark("dup-slug")

    assert rc == 2
    assert p1.read_text(encoding="utf-8") == before1
    assert p2.read_text(encoding="utf-8") == before2


def test_mark_frontmatterless_file_returns_2_not_3(mc_env, vault):
    """A note with NO frontmatter is filtered by _resolve (no type:task) -> it is a
    no-match -> exit 2 (edge case #2). It never reaches mark's fence re-check."""
    vault.add_raw(
        "01 Projects/P/Tasks/no-fm.md",
        "# No Frontmatter Here\n\nJust a body, no --- fence.\n",
    )
    assert mc_env.done.mark("no-fm") == 2


def test_mark_returns_3_when_frontmatter_vanishes_between_resolve_and_write(mc_env, vault):
    """TOCTOU guard: _resolve validates the fence on one read; mark re-reads. If the
    frontmatter is stripped in that window, mark must return 3 (refuse) — NOT crash on
    m.group(). Simulate the race by pointing _resolve at a now-frontmatter-less file."""
    raw = vault.add_raw(
        "01 Projects/P/Tasks/raced.md",
        "# Raced\n\nframtter got stripped underfoot — no --- fence now.\n",
    )
    done = mc_env.done
    hit = {"path": str(raw), "title": "Raced", "status": "todo", "needs_review": False}
    orig_resolve = done._resolve
    done._resolve = lambda slug: [hit]
    try:
        assert done.mark("raced") == 3  # guarded, no AttributeError
    finally:
        done._resolve = orig_resolve


def test_mark_strips_md_suffix(mc_env, vault):
    """slug accepted with or without .md (done._resolve — .md suffix strip)."""
    path = vault.add_task("trailing-md", status="todo", needs_review=False)
    rc = mc_env.done.mark("trailing-md.md")
    assert rc == 0
    assert "status: done" in path.read_text(encoding="utf-8")
