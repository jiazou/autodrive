"""Slice 1.4 — today render layer (AC 16).

Asserts the REAL behavior of today.render_swiftbar / today._obsidian_href /
today._title_count:
  - obsidian links percent-encode spaces as %20 (NOT +)
  - `|` in titles/labels is SANITIZED by REPLACING with `/` (today.py does
    `.replace("|","/")`) — it does NOT emit an escaped pipe, so we assert the `/`
    replacement, never escaping.
  - _title_count counts overdue+due_today and waiting sessions.
"""
from datetime import date, timedelta


def _iso(days):
    return (date.today() + timedelta(days=days)).isoformat()


# --------------------------------------------------------------------------- #
# AC 16 — _obsidian_href encodes %20, not +
# --------------------------------------------------------------------------- #
def test_obsidian_href_encodes_space_as_percent20(mc_env):
    # VAULT_NAME is "TestVault" (no space); use a slug WITH a space to exercise
    # the quote_via=quote path that forces %20.
    href = mc_env.today._obsidian_href("a b c")

    assert "%20" in href
    assert "+" not in href
    assert href.startswith("obsidian://open?")
    # vault name flows through, encoded the same way
    assert "vault=TestVault" in href


def test_render_swiftbar_uses_percent20_for_links(mc_env, vault, claude_state):
    vault.add_task("space slug", due=_iso(0), title="Space Slug")

    d = mc_env.standup.gather()
    out = mc_env.today.render_swiftbar(d)

    # the obsidian href line for the due-today task uses %20, never +
    href_lines = [ln for ln in out.splitlines() if "href=obsidian://" in ln]
    assert href_lines
    assert any("%20" in ln for ln in href_lines)
    assert not any("+" in ln for ln in href_lines)


# --------------------------------------------------------------------------- #
# AC 16 — `|` sanitized by REPLACE with `/`, not escaped
# --------------------------------------------------------------------------- #
def test_render_swiftbar_replaces_pipe_in_title_with_slash(mc_env, vault, claude_state):
    # a task title containing a pipe -> must render as `/` (not escaped, not literal |)
    vault.add_task("piped", due=_iso(0), title="alpha|beta")

    d = mc_env.standup.gather()
    out = mc_env.today.render_swiftbar(d)

    # the rendered task line replaces | with /
    task_lines = [ln for ln in out.splitlines() if "alpha" in ln]
    assert task_lines
    line = task_lines[0]
    assert "alpha/beta" in line
    # the literal title pipe was removed; the only `|` on the line is SwiftBar's
    # own attribute separator (` | href=...`), never the title's pipe.
    title_part = line.split(" | ")[0]
    assert "|" not in title_part


def test_render_swiftbar_replaces_pipe_in_session_label(mc_env, vault, claude_state):
    # a session goal containing a pipe -> sanitized to `/` in the Sessions block
    sid = "eeeeeeee-1111-2222-3333-444444444444"
    claude_state.add_session(sid, status="idle")
    claude_state.add_transcript(sid, [
        {"type": "ai-title", "sessionId": sid, "aiTitle": "left|right"},
    ])

    d = mc_env.standup.gather()
    out = mc_env.today.render_swiftbar(d)

    label_lines = [ln for ln in out.splitlines() if "left" in ln]
    assert label_lines
    line = label_lines[0]
    assert "left/right" in line
    title_part = line.split(" | ")[0]
    assert "|" not in title_part


# --------------------------------------------------------------------------- #
# AC 16 — _title_count counts overdue+due_today and waiting
# --------------------------------------------------------------------------- #
def test_title_count_counts_overdue_due_today_and_waiting(mc_env, vault, claude_state):
    vault.add_task("od1", due=_iso(-1))
    vault.add_task("od2", due=_iso(-2))
    vault.add_task("dt1", due=_iso(0))
    # a waiting session (status overlay upgrades idle -> waiting)
    sid = "ffffffff-1111-2222-3333-444444444444"
    claude_state.add_session(sid, status="idle")
    claude_state.add_status(sid, "waiting")

    d = mc_env.standup.gather()
    title = mc_env.today._title_count(d)

    # 2 overdue + 1 due-today = 3
    assert "☀3" in title
    # one waiting session
    assert "⏸1" in title


def test_title_count_no_due_no_waiting(mc_env):
    # nothing overdue/due-today and no waiting sessions -> bare sun, no counts
    d = mc_env.standup.gather()
    title = mc_env.today._title_count(d)

    assert title == "☀"


# --------------------------------------------------------------------------- #
# AC 16 — render_terminal: the human terminal surface (rows + waiting + idle)
# --------------------------------------------------------------------------- #
def test_render_terminal_lists_focus_rows_waiting_and_idle(mc_env, vault, claude_state):
    """AC 16 render_terminal: the compact iTerm view. Header carries the title-count
    + timestamp; each focused task is a `• <title>` row; a waiting agent is listed
    under the waiting block (label = goal/name/id + cwd); idle sessions surface the
    spare-capacity line. Asserts the real rendered rows, not just that it returns a
    string — a dropped focus row / waiting block / idle line would FAIL."""
    vault.add_task("od1", due=_iso(-1), title="Overdue One")
    vault.add_task("dt1", due=_iso(0), title="Due Today One")
    # a waiting session (idle in the session file, upgraded to waiting via overlay)
    wsid = "ffffffff-1111-2222-3333-444444444444"
    claude_state.add_session(wsid, status="idle", cwd="/work/proj")
    claude_state.add_status(wsid, "waiting")
    claude_state.add_transcript(wsid, [
        {"type": "ai-title", "sessionId": wsid, "aiTitle": "fixing the parser"},
    ])
    # an idle + unbound + not-self session -> spare capacity
    claude_state.add_session("bbbbbbbb-1111-2222-3333-444444444444", status="idle")

    d = mc_env.standup.gather()
    out = mc_env.today.render_terminal(d)
    lines = out.splitlines()

    # header: title-count (2 overdue/due-today total -> ☀2, 1 waiting -> ⏸1) + timestamp
    assert lines[0].startswith("☀2⏸1")
    assert d["generated_at"] in lines[0]

    # both focused tasks rendered as `• <title>` rows
    assert "  • Overdue One" in lines
    assert "  • Due Today One" in lines

    # waiting block present with the agent's goal label + its cwd
    assert "  ⏸ agents waiting on you:" in lines
    assert any("fixing the parser" in ln and "/work/proj" in ln for ln in lines)

    # idle spare-capacity line (one idle unbound session)
    assert any("idle session(s)" in ln for ln in lines)
    assert any(ln.strip().startswith("🟢 1 idle session(s)") for ln in lines)


def test_render_terminal_empty_focus_shows_pull_from_backlog(mc_env):
    """AC 16 render_terminal empty path: no overdue/due-today tasks -> the explicit
    'no overdue or due-today tasks' hint row (focus_slugs empty branch), and NO
    spurious waiting/idle blocks when there are no sessions."""
    d = mc_env.standup.gather()
    out = mc_env.today.render_terminal(d)

    assert "no overdue or due-today tasks — pull from backlog" in out
    assert "agents waiting on you" not in out
    assert "idle session(s)" not in out
