"""Slice 1.5 — session_summary pure helpers.

Tests mission-control/bin/session_summary.py:_text (flattening, pure), tail_text
(transcript parsing via the claude_state builder), and that summarize returns {} on
an empty/absent transcript. The real `claude -p` call is OUT OF SCOPE (design line
72-74 / out-of-scope) — only the pure path + the empty-case are exercised.
"""


# --------------------------------------------------------------------------- #
# _text — flatten message content (pure)
# --------------------------------------------------------------------------- #
def test_text_passes_through_string(mc_env):
    assert mc_env.session_summary._text("hello world") == "hello world"


def test_text_flattens_block_list_text_and_tool_use(mc_env):
    content = [
        {"type": "text", "text": "first"},
        {"type": "tool_use", "name": "Bash"},
        {"type": "text", "text": "second"},
    ]
    assert mc_env.session_summary._text(content) == "first [tool:Bash] second"


def test_text_ignores_unknown_blocks_and_non_dict(mc_env):
    content = [
        {"type": "thinking", "text": "ignored"},
        "not-a-dict",
        {"type": "text", "text": "kept"},
    ]
    assert mc_env.session_summary._text(content) == "kept"


def test_text_returns_empty_for_other_types(mc_env):
    assert mc_env.session_summary._text(None) == ""
    assert mc_env.session_summary._text(42) == ""


# --------------------------------------------------------------------------- #
# tail_text — parse a transcript's user/assistant turns
# --------------------------------------------------------------------------- #
def test_tail_text_empty_when_no_transcript(mc_env):
    assert mc_env.session_summary.tail_text("nope") == ""


def test_tail_text_parses_user_and_assistant_turns(mc_env, claude_state):
    sid = "sess-1"
    claude_state.add_transcript(sid, [
        {"type": "user", "message": {"content": "what's the plan"}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "do the thing"},
            {"type": "tool_use", "name": "Edit"},
        ]}},
        {"type": "summary", "message": {"content": "ignored non-turn"}},
    ])

    blob = mc_env.session_summary.tail_text(sid)

    assert "user: what's the plan" in blob
    assert "assistant: do the thing [tool:Edit]" in blob
    # non user/assistant events are skipped
    assert "ignored non-turn" not in blob


def test_tail_text_skips_bad_json_and_empty_turns(mc_env, claude_state):
    sid = "sess-2"
    # write a transcript then inject a malformed line + an empty-content turn
    path = claude_state.add_transcript(sid, [
        {"type": "user", "message": {"content": "real turn"}},
    ])
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{not valid json\n")
        fh.write('{"type": "assistant", "message": {"content": ""}}\n')

    blob = mc_env.session_summary.tail_text(sid)

    # the real turn survives; malformed line skipped (no crash); empty turn dropped
    assert blob == "user: real turn"


# --------------------------------------------------------------------------- #
# summarize — empty transcript -> {} (no claude -p call)
# --------------------------------------------------------------------------- #
def test_summarize_returns_empty_dict_on_empty_transcript(mc_env, monkeypatch):
    # no transcript on disk -> tail_text == "" -> summarize short-circuits to {}
    # BEFORE any subprocess to `claude` (session_summary.py:62-64).
    #
    # Guard the short-circuit STRUCTURALLY: replace the real call site
    # (session_summary.summarize -> subprocess.run, line 72) with a sentinel that
    # raises if invoked. summarize wraps the call in `try/except Exception: pass`, so
    # the sentinel must raise a BaseException (NOT an Exception) to propagate past that
    # handler and fail the test. If a regression removed the `if not blob: return {}`
    # guard, summarize would fall through to subprocess.run and this test would
    # HARD-FAIL instead of silently staying green on the swallowed-then-{} path.
    class _ClaudeWasCalled(BaseException):
        pass

    def _boom(*a, **k):
        raise _ClaudeWasCalled("claude -p must not be called on an empty transcript")

    monkeypatch.setattr(mc_env.session_summary.subprocess, "run", _boom)
    assert mc_env.session_summary.summarize("absent-sid") == {}
