"""Slice 1.3 — harvest render + helpers (AC 9/edge #3 render path, render formatting).

Asserts the REAL output of harvest.render plus the home_rel / short helpers. The
empty-live render ("No live Claude sessions found.") is the render half of edge case
#3; the rest covers row formatting, bound vs unbound sections, and the self marker
(SELF_ID set via monkeypatch.setattr on the reloaded harvest module).

mc/conftest autouse stubs iterm_tab_names -> {}; render takes already-built dicts so
it does not touch iTerm anyway.
"""


def _row(*, status="idle", goal="A goal", cwd="/work/repo", color=None, name=None):
    return {"pid": 123, "cwd": cwd, "status": status,
            "color": color, "name": name, "goal": goal}


# --------------------------------------------------------------------------- #
# Edge case #3 — no live sessions
# --------------------------------------------------------------------------- #
def test_render_no_live_sessions(mc_env):
    out = mc_env.harvest.render({}, {}, "2026-06-03 09:00")
    assert "No live Claude sessions found." in out
    # header still present; no session rows
    assert "MISSION CONTROL" in out
    assert "live session(s)" not in out


# --------------------------------------------------------------------------- #
# render — counts header + row formatting
# --------------------------------------------------------------------------- #
def test_render_counts_header(mc_env):
    live = {
        "sid-a": _row(status="idle", goal="Goal A"),
        "sid-b": _row(status="busy", goal="Goal B"),
    }
    binds = {"sid-a": {"event": "bind", "session_id": "sid-a", "project": "Proj"}}
    out = mc_env.harvest.render(live, binds, "2026-06-03 09:00")
    assert "2 live session(s)" in out
    assert "1 bound" in out
    assert "1 unbound" in out
    assert "0 waiting on you" in out


def test_render_row_shows_goal_status_and_meta(mc_env):
    live = {"sid-a": _row(status="busy", goal="Ship it", cwd="/work/repo",
                          color="cyan")}
    out = mc_env.harvest.render(live, {}, "now")
    assert "● Ship it" in out
    assert "▶ working" in out          # STATUS_GLYPH[busy]
    assert "🎨cyan" in out
    # short("sid-a") = "sid", rendered inside the " · "-joined meta line
    assert " · sid · " in out


def test_render_untitled_when_no_goal(mc_env):
    live = {"sid-a": _row(goal=None)}
    out = mc_env.harvest.render(live, {}, "now")
    assert "(untitled session)" in out


def test_render_waiting_glyph_and_count(mc_env):
    live = {"sid-a": _row(status="waiting", goal="Needs you")}
    out = mc_env.harvest.render(live, {}, "now")
    assert "⏸ WAITING ON YOU" in out
    assert "1 waiting on you" in out


# --------------------------------------------------------------------------- #
# render — bound vs unbound sections
# --------------------------------------------------------------------------- #
def test_render_bound_session_shows_project_arrow(mc_env):
    live = {"sid-a": _row(goal="Bound one")}
    binds = {"sid-a": {"event": "bind", "session_id": "sid-a", "project": "MyProj"}}
    out = mc_env.harvest.render(live, binds, "now")
    assert "→ MyProj" in out


def test_render_unbound_session_listed_with_bind_hint(mc_env):
    """An unbound, non-self session appears in the 'Unbound sessions' hint block."""
    live = {"abcd-1234": _row(goal="Unbound one")}
    out = mc_env.harvest.render(live, {}, "now")
    assert "Unbound sessions" in out
    assert "mc bind abcd " in out      # short("abcd-1234") = "abcd"


def test_render_no_unbound_block_when_all_bound(mc_env):
    live = {"sid-a": _row(goal="Bound")}
    binds = {"sid-a": {"event": "bind", "session_id": "sid-a", "project": "P"}}
    out = mc_env.harvest.render(live, binds, "now")
    assert "Unbound sessions" not in out


# --------------------------------------------------------------------------- #
# render — self marker (SELF_ID via monkeypatch.setattr on reloaded harvest)
# --------------------------------------------------------------------------- #
def test_render_self_marker(mc_env, monkeypatch):
    monkeypatch.setattr(mc_env.harvest, "SELF_ID", "self-sid")
    live = {
        "self-sid": _row(goal="My own session"),
        "other-sid": _row(goal="Another session"),
    }
    out = mc_env.harvest.render(live, {}, "now")
    assert "⟵ this session" in out
    # the marker attaches to the self row's goal line
    assert "● My own session  ⟵ this session" in out


def test_render_self_session_excluded_from_unbound_hint(mc_env, monkeypatch):
    """An unbound self session is NOT listed in the 'bind me' hint block."""
    monkeypatch.setattr(mc_env.harvest, "SELF_ID", "self-sid")
    live = {"self-sid": _row(goal="My own session")}
    out = mc_env.harvest.render(live, {}, "now")
    assert "Unbound sessions" not in out


# --------------------------------------------------------------------------- #
# render — optional summaries block
# --------------------------------------------------------------------------- #
def test_render_summaries_block(mc_env):
    live = {"sid-a": _row(goal="With summary")}
    summaries = {"sid-a": {"progress": "did X", "next": "do Y"}}
    out = mc_env.harvest.render(live, {}, "now", summaries)
    assert "progress: did X" in out
    assert "next:     do Y" in out


# --------------------------------------------------------------------------- #
# helpers — home_rel / short
# --------------------------------------------------------------------------- #
def test_home_rel_replaces_home_prefix(mc_env):
    home = str(mc_env.home)
    assert mc_env.harvest.home_rel(home + "/work") == "~/work"


def test_home_rel_none(mc_env):
    assert mc_env.harvest.home_rel(None) == "?"


def test_short_takes_first_uuid_segment(mc_env):
    assert mc_env.harvest.short("abcd1234-ef56-7890") == "abcd1234"


def test_short_falsy(mc_env):
    assert mc_env.harvest.short("") == "?"
