"""harvest.iterm_tab_names() output parsing + build_summaries() fan-out.

The mc/conftest autouse fixture stubs harvest.iterm_tab_names -> {} so no real osascript
fires; to test the REAL parser we importlib.reload(harvest) (restoring the real function)
and stub its subprocess.run with canned osascript stdout.
"""
import importlib


class _FakeProc:
    """Stand-in for CompletedProcess: the parsers read only `.stdout`."""
    def __init__(self, stdout):
        self.stdout = stdout


# --- iterm_tab_names parsing (#18) -------------------------------------------------
def test_iterm_tab_names_override_wins_name_fallback_short_row_skipped(mc_env, monkeypatch):
    h = importlib.reload(mc_env.harvest)  # restore the real iterm_tab_names (autouse stubbed it)
    canned = (
        "ttys001\tHarness\tlong auto-generated title\n"   # override "Harness" wins over name
        "ttys002\t\tfallback-name\n"                        # no override -> name fallback
        "ttys003\tonly-two-fields\n"                        # <3 tab fields -> skipped
        "\n"                                                # blank line -> skipped
    )
    monkeypatch.setattr(h.subprocess, "run", lambda *a, **k: _FakeProc(canned))
    assert h.iterm_tab_names() == {"ttys001": "Harness", "ttys002": "fallback-name"}


def test_iterm_tab_names_subprocess_failure_is_empty(mc_env, monkeypatch):
    h = importlib.reload(mc_env.harvest)

    def boom(*a, **k):
        raise OSError("osascript not available")

    monkeypatch.setattr(h.subprocess, "run", boom)
    assert h.iterm_tab_names() == {}


# --- build_summaries fan-out (#15) -------------------------------------------------
def test_build_summaries_drops_empty_and_passes_goal(mc_env, monkeypatch):
    """build_summaries maps session_summary.summarize over live sessions, passes each
    session's goal (missing -> ""), and DROPS sessions whose summary is empty."""
    seen = {}

    def fake_summarize(sid, goal):
        seen[sid] = goal
        return {} if sid == "empty" else {"progress": f"p-{sid}", "next": "n"}

    monkeypatch.setattr(mc_env.session_summary, "summarize", fake_summarize)
    live = {"a": {"goal": "ga"}, "empty": {"goal": "ge"}, "b": {}}  # "b" has no goal
    out = mc_env.harvest.build_summaries(live)

    assert set(out) == {"a", "b"}, "the empty-summary session must be dropped"
    assert out["a"] == {"progress": "p-a", "next": "n"}
    assert seen == {"a": "ga", "empty": "ge", "b": ""}, "goal passed through; missing -> ''"


def test_build_summaries_empty_input(mc_env, monkeypatch):
    monkeypatch.setattr(mc_env.session_summary, "summarize",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("called for empty input")))
    assert mc_env.harvest.build_summaries({}) == {}
