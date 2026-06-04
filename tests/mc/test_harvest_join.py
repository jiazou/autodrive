"""Slice 1.3 — harvest join + sessions (AC 7, 8, 9, 10, 11).

Asserts the REAL behavior of harvest.{load_status_overlay, load_bindings,
load_live_sessions, session_meta, clean_goal} against fixtures the readers accept.

mc/conftest autouse stubs harvest.iterm_tab_names -> {} so no osascript fires and
liveness uses real os.getpid(); goal therefore falls back to the transcript ai-title.
"""
import json

import pytest


# --------------------------------------------------------------------------- #
# AC 7 — load_status_overlay (edge case #5)
# --------------------------------------------------------------------------- #
def test_status_overlay_empty_when_absent(mc_env):
    """No status.jsonl on disk -> {} (no crash)."""
    assert not mc_env.status_ledger.exists()
    assert mc_env.harvest.load_status_overlay() == {}


def test_status_overlay_last_wins_per_session(claude_state, mc_env):
    """Later status line for the same session_id wins."""
    claude_state.add_status("sid-a", "active", ts=1)
    claude_state.add_status("sid-a", "waiting", ts=2)
    overlay = mc_env.harvest.load_status_overlay()
    assert overlay == {"sid-a": "waiting"}


def test_status_overlay_skips_malformed_lines(claude_state, mc_env):
    """A non-JSON line is skipped; surrounding valid lines still load."""
    claude_state.add_status("sid-a", "active", ts=1)
    with open(mc_env.status_ledger, "a", encoding="utf-8") as fh:
        fh.write("not json at all\n")
    claude_state.add_status("sid-b", "waiting", ts=2)
    overlay = mc_env.harvest.load_status_overlay()
    assert overlay == {"sid-a": "active", "sid-b": "waiting"}


# --------------------------------------------------------------------------- #
# AC 8 — load_bindings (edge case #4)
# --------------------------------------------------------------------------- #
def test_bindings_empty_when_absent(mc_env):
    """No bindings.jsonl -> {}."""
    assert not mc_env.bindings.exists()
    assert mc_env.harvest.load_bindings() == {}


def test_bindings_last_wins_per_sid(claude_state, mc_env):
    """Latest bind event per session_id wins (later line overrides earlier)."""
    claude_state.add_binding("sid-a", event="bind", project="Old", ts=1)
    claude_state.add_binding("sid-a", event="bind", project="New", task="t1", ts=2)
    binds = mc_env.harvest.load_bindings()
    assert set(binds) == {"sid-a"}
    assert binds["sid-a"]["project"] == "New"
    assert binds["sid-a"]["task"] == "t1"


def test_bindings_drops_sid_whose_last_event_is_unbind(claude_state, mc_env):
    """A sid whose final event is `unbind` is dropped from the result."""
    claude_state.add_binding("sid-a", event="bind", project="P", ts=1)
    claude_state.add_binding("sid-a", event="unbind", ts=2)
    claude_state.add_binding("sid-b", event="bind", project="Q", ts=3)
    binds = mc_env.harvest.load_bindings()
    assert "sid-a" not in binds
    assert binds["sid-b"]["project"] == "Q"


def test_bindings_rebind_after_unbind_is_kept(claude_state, mc_env):
    """unbind then bind again -> the sid is bound (last event is bind, not unbind)."""
    claude_state.add_binding("sid-a", event="bind", project="P", ts=1)
    claude_state.add_binding("sid-a", event="unbind", ts=2)
    claude_state.add_binding("sid-a", event="bind", project="R", ts=3)
    binds = mc_env.harvest.load_bindings()
    assert "sid-a" in binds
    assert binds["sid-a"]["project"] == "R"


# --------------------------------------------------------------------------- #
# AC 9 — load_live_sessions (edge case #9)
# --------------------------------------------------------------------------- #
def test_live_sessions_keeps_only_live_pid(claude_state, mc_env):
    """A session with a live pid is kept; one with a dead pid is excluded."""
    claude_state.add_session("live-sid")  # default pid = os.getpid() (alive)
    claude_state.add_session("dead-sid", pid=claude_state.dead_pid())
    live = mc_env.harvest.load_live_sessions()
    assert "live-sid" in live
    assert "dead-sid" not in live


def test_live_sessions_applies_waiting_overlay(claude_state, mc_env):
    """A `waiting` status line upgrades the session's idle/busy status to waiting."""
    claude_state.add_session("sid-a", status="idle")
    claude_state.add_status("sid-a", "waiting")
    live = mc_env.harvest.load_live_sessions()
    assert live["sid-a"]["status"] == "waiting"


def test_live_sessions_non_waiting_overlay_does_not_override(claude_state, mc_env):
    """Only `waiting` overrides; an `active` overlay leaves the session status alone."""
    claude_state.add_session("sid-a", status="busy")
    claude_state.add_status("sid-a", "active")
    live = mc_env.harvest.load_live_sessions()
    assert live["sid-a"]["status"] == "busy"


def test_live_sessions_goal_falls_back_to_ai_title(claude_state, mc_env):
    """With iTerm stubbed to {}, goal resolves to the transcript ai-title."""
    claude_state.add_session("sid-a")
    claude_state.add_transcript("sid-a", [
        {"type": "ai-title", "sessionId": "sid-a", "aiTitle": "Fix the parser"},
    ])
    live = mc_env.harvest.load_live_sessions()
    assert live["sid-a"]["goal"] == "Fix the parser"


def test_live_sessions_goal_iterm_name_overrides_ai_title(claude_state, mc_env, monkeypatch):
    """A live iTerm tab name OVERRIDES the transcript ai-title, run through clean_goal.

    load_live_sessions resolves goal as `clean_goal(tabs.get(tty)) or ai_title`,
    where tabs is keyed by the session pid's controlling tty (pid_tty(pid)). The
    autouse `_no_iterm_autouse` stub forces iterm_tab_names -> {}, so every other
    mc/ test only ever exercises the ai-title fallback. Here we override BOTH that
    stub (after it ran) and pid_tty so the live iTerm side of the `or` is taken:
    the cleaned tab name ("Real Tab" — glyph + process badge stripped) must win
    over the ai-title. Reverse the precedence in harvest and this goes red.
    """
    tty = "/dev/ttys042"
    claude_state.add_session("sid-a")
    claude_state.add_transcript("sid-a", [
        {"type": "ai-title", "sessionId": "sid-a", "aiTitle": "AI fallback title"},
    ])
    # override the autouse {} stub and pin the tab to this session's tty
    monkeypatch.setattr(mc_env.harvest, "iterm_tab_names",
                        lambda: {tty: "✳ Real Tab (node)"})
    monkeypatch.setattr(mc_env.harvest, "pid_tty", lambda pid: tty)

    live = mc_env.harvest.load_live_sessions()
    assert live["sid-a"]["goal"] == "Real Tab"


def test_live_sessions_carries_cwd_color_name(claude_state, mc_env):
    """The row carries cwd from the session file and color/name from the transcript."""
    claude_state.add_session("sid-a", cwd="/work/repo")
    claude_state.add_transcript("sid-a", [
        {"type": "agent-color", "sessionId": "sid-a", "agentColor": "cyan"},
        {"type": "agent-name", "sessionId": "sid-a", "agentName": "Scout"},
    ])
    live = mc_env.harvest.load_live_sessions()
    row = live["sid-a"]
    assert row["cwd"] == "/work/repo"
    assert row["color"] == "cyan"
    assert row["name"] == "Scout"


def test_live_sessions_empty_when_no_sessions(claude_state, mc_env):
    """No session files -> {} (edge case #3, no-live-sessions)."""
    # claude_state created the sessions dir but wrote no session files.
    assert list(mc_env.sessions_dir.glob("*.json")) == []
    assert mc_env.harvest.load_live_sessions() == {}


def test_live_sessions_skips_pidless_session(claude_state, mc_env):
    """A session file with no pid is skipped (pid is None -> not live)."""
    # claude_state in the signature already created the sessions dir.
    path = mc_env.sessions_dir / "nopid.json"
    path.write_text(json.dumps({"sessionId": "nopid", "cwd": "/x"}),
                    encoding="utf-8")
    assert mc_env.harvest.load_live_sessions() == {}


# --------------------------------------------------------------------------- #
# AC 10 — session_meta
# --------------------------------------------------------------------------- #
def test_session_meta_returns_latest_color_name_title(claude_state, mc_env):
    """Latest event of each type wins; returns (color, name, ai_title)."""
    claude_state.add_transcript("sid-a", [
        {"type": "agent-color", "sessionId": "sid-a", "agentColor": "red"},
        {"type": "agent-name", "sessionId": "sid-a", "agentName": "First"},
        {"type": "ai-title", "sessionId": "sid-a", "aiTitle": "Old goal"},
        {"type": "agent-color", "sessionId": "sid-a", "agentColor": "green"},
        {"type": "agent-name", "sessionId": "sid-a", "agentName": "Second"},
        {"type": "ai-title", "sessionId": "sid-a", "aiTitle": "New goal"},
    ])
    color, name, ai_title = mc_env.harvest.session_meta("sid-a")
    assert color == "green"
    assert name == "Second"
    assert ai_title == "New goal"


def test_session_meta_none_when_no_transcript(mc_env):
    """No transcript for the sid -> (None, None, None)."""
    assert mc_env.harvest.session_meta("ghost") == (None, None, None)


def test_session_meta_ignores_events_for_other_sessions(claude_state, mc_env):
    """An event whose sessionId != sid is ignored even if the file is globbed."""
    claude_state.add_transcript("sid-a", [
        {"type": "agent-color", "sessionId": "sid-other", "agentColor": "blue"},
    ])
    assert mc_env.harvest.session_meta("sid-a") == (None, None, None)


# --------------------------------------------------------------------------- #
# AC 11 — clean_goal
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("raw,expected", [
    ("✳ Build the harness", "Build the harness"),
    ("⠐ Working on tests", "Working on tests"),
    ("Build the harness (caffeinate)", "Build the harness"),
    ("✳ Build the harness (node)", "Build the harness"),
    ("Plain title", "Plain title"),
])
def test_clean_goal_strips_glyphs_and_process_badge(mc_env, raw, expected):
    assert mc_env.harvest.clean_goal(raw) == expected


def test_clean_goal_passthrough_falsy(mc_env):
    """Empty/None returns as-is (the early guard)."""
    assert mc_env.harvest.clean_goal("") == ""
    assert mc_env.harvest.clean_goal(None) is None


# --------------------------------------------------------------------------- #
# pid_tty — `ps -o tty=` parsing, incl. the "no controlling tty" branch
# --------------------------------------------------------------------------- #
class _FakeProc:
    """Stand-in for CompletedProcess: pid_tty reads only `.stdout`."""
    def __init__(self, stdout):
        self.stdout = stdout


def _stub_ps(monkeypatch, mc_env, stdout):
    """Make harvest.subprocess.run (the `ps` call in pid_tty) return `stdout`. Also
    asserts the real `ps` is not invoked — we feed canned tty output."""
    monkeypatch.setattr(mc_env.harvest.subprocess, "run",
                        lambda *a, **k: _FakeProc(stdout))


def test_pid_tty_normal_tty(mc_env, monkeypatch):
    """A real tty like 'ttys003' (with surrounding whitespace from ps) -> '/dev/ttys003'."""
    _stub_ps(monkeypatch, mc_env, "ttys003\n")
    assert mc_env.harvest.pid_tty(1234) == "/dev/ttys003"


def test_pid_tty_double_question_is_none(mc_env, monkeypatch):
    """A process with NO controlling tty: ps prints '??' -> pid_tty returns None
    (the `t and t != "??"` guard), NOT the literal '/dev/??'. This is the branch
    that previously had no coverage."""
    _stub_ps(monkeypatch, mc_env, "??\n")
    assert mc_env.harvest.pid_tty(1234) is None


def test_pid_tty_empty_output_is_none(mc_env, monkeypatch):
    """ps prints nothing (dead/unknown pid) -> stripped t is '' (falsy) -> None,
    never '/dev/'."""
    _stub_ps(monkeypatch, mc_env, "\n")
    assert mc_env.harvest.pid_tty(1234) is None


def test_pid_tty_subprocess_failure_is_none(mc_env, monkeypatch):
    """If `ps` itself raises (timeout / not found) -> the except returns None,
    not a crash."""
    def _boom(*a, **k):
        raise OSError("ps unavailable")
    monkeypatch.setattr(mc_env.harvest.subprocess, "run", _boom)
    assert mc_env.harvest.pid_tty(1234) is None
