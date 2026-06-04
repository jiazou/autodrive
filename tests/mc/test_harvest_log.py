"""harvest --log / log_to_vault — append the digest to today's daily note.

`harvest.log_to_vault(digest, now)` calls ensure_daily_note(date) then APPENDS a
timestamped '## 🛰 Harvest HH:MM' section to that note in "a" mode — it must never
clobber pre-existing content (mirror of test_standup.test_draft_is_non_destructive).
It returns (path, created): created=True when the note was freshly made, False when
it appended to one that already existed.

These exercise the real reader/writer via mc_env (the modules are reloaded against
the fake vault), with the daily dir at mc_env.daily_dir. No subprocess / no clock
race — we pass an explicit `now`.
"""
import datetime


def _now(date="2026-06-03", hm="09:30"):
    """A fixed datetime so the section header (HH:MM) and the note name (date) are
    deterministic."""
    h, m = (int(x) for x in hm.split(":"))
    y, mo, d = (int(x) for x in date.split("-"))
    return datetime.datetime(y, mo, d, h, m)


def test_log_to_vault_creates_note_when_absent(mc_env):
    """No daily note yet -> log_to_vault creates it (created=True) and writes the
    harvest section into it."""
    now = _now()
    daily = mc_env.daily_dir / "2026-06-03.md"
    assert not daily.exists()  # nothing pre-existing

    path, created = mc_env.harvest.log_to_vault("DIGEST-BODY-line", now)

    assert created is True
    out = open(path, encoding="utf-8").read()
    # minimal-frontmatter fallback note got created (no template in this fixture)...
    assert "2026-06-03" in out
    # ...and the harvest section + digest body are present.
    assert "## 🛰 Harvest 09:30" in out
    assert "DIGEST-BODY-line" in out


def test_log_to_vault_appends_without_clobbering(mc_env):
    """A pre-existing daily note with a sibling section -> log_to_vault APPENDS the
    harvest section and returns created=False; the sibling content survives verbatim
    (the non-destructive contract)."""
    now = _now(hm="14:05")
    daily = mc_env.daily_dir / "2026-06-03.md"
    daily.parent.mkdir(parents=True, exist_ok=True)
    daily.write_text(
        "# 2026-06-03 — Daily\n\n## Journal\nmy private journal entry\n",
        encoding="utf-8",
    )

    path, created = mc_env.harvest.log_to_vault("the harvest digest", now)

    assert created is False
    out = open(path, encoding="utf-8").read()
    # pre-existing sibling survives untouched...
    assert "## Journal\nmy private journal entry" in out
    # ...and the new harvest section is appended after it.
    assert "## 🛰 Harvest 14:05" in out
    assert "the harvest digest" in out
    assert out.index("## Journal") < out.index("## 🛰 Harvest 14:05")


def test_log_to_vault_appends_each_call(mc_env):
    """Two calls -> two distinct harvest sections in the same note; the second is
    created=False (the note already existed after the first call)."""
    p1, c1 = mc_env.harvest.log_to_vault("first run", _now(hm="08:00"))
    p2, c2 = mc_env.harvest.log_to_vault("second run", _now(hm="08:45"))

    assert c1 is True and c2 is False
    assert p1 == p2  # same daily note
    out = open(p2, encoding="utf-8").read()
    assert "## 🛰 Harvest 08:00" in out
    assert "## 🛰 Harvest 08:45" in out
    assert "first run" in out and "second run" in out
