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
# tail_text — DEGRADE (docstring's "on any failure prints {}" contract)
# --------------------------------------------------------------------------- #
def test_tail_text_nondict_message_dropped_not_raised(mc_env, claude_state):
    """A transcript entry whose `message` is NOT a dict (e.g. a bare string, or a null)
    must be DROPPED, not raise AttributeError from `.get("content")`. Regression: the old
    `e.get("message", {}).get("content")` crashed on such a note."""
    sid = "sess-nondict"
    claude_state.add_transcript(sid, [
        {"type": "user", "message": {"content": "real turn"}},
        {"type": "assistant", "message": "oops-not-a-dict"},   # non-dict message → drop, not crash
        {"type": "user", "message": None},                     # null message → drop, not crash
    ])
    blob = mc_env.session_summary.tail_text(sid)   # must NOT raise
    assert blob == "user: real turn"               # the valid turn survives; bad ones dropped


def test_tail_text_unreadable_transcript_returns_empty(mc_env, claude_state, monkeypatch):
    """A transcript that exists at glob time but fails to open (removed in the race, a
    permission error) must return "" — NOT raise through harvest.build_summaries' ex.map
    and crash the whole unattended harvest. Regression: the old `open(hits[0])` was
    unguarded and `summarize` called `tail_text` OUTSIDE its try."""
    sid = "sess-unreadable"
    claude_state.add_transcript(sid, [{"type": "user", "message": {"content": "hi"}}])
    real_open = open

    def _boom_open(path, *a, **k):
        if isinstance(path, str) and path.endswith(sid + ".jsonl"):
            raise OSError("transcript vanished mid-read")
        return real_open(path, *a, **k)

    monkeypatch.setattr("builtins.open", _boom_open)
    assert mc_env.session_summary.tail_text(sid) == ""     # degrades, does not raise


def test_summarize_degrades_to_empty_on_unreadable_transcript(mc_env, claude_state, monkeypatch):
    """End-to-end degrade: an unreadable transcript makes summarize return {} (goal+status
    fallback), never propagating an exception to the caller's ex.map."""
    sid = "sess-summ-degrade"
    claude_state.add_transcript(sid, [{"type": "user", "message": {"content": "hi"}}])
    real_open = open

    def _boom_open(path, *a, **k):
        if isinstance(path, str) and path.endswith(sid + ".jsonl"):
            raise OSError("gone")
        return real_open(path, *a, **k)

    monkeypatch.setattr("builtins.open", _boom_open)
    assert mc_env.session_summary.summarize(sid) == {}     # degrade contract, no crash


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


# --------------------------------------------------------------------------- #
# summarize — JSON extraction from a prose-wrapped `claude -p` reply
# --------------------------------------------------------------------------- #
class _FakeProc:
    """Stand-in for subprocess.CompletedProcess: only .stdout is read by summarize."""
    def __init__(self, stdout):
        self.stdout = stdout


def _stub_claude(monkeypatch, mc_env, stdout):
    """Replace session_summary.subprocess.run with one returning `stdout`. Asserts
    the real `claude` binary is NEVER invoked (we feed canned output)."""
    monkeypatch.setattr(mc_env.session_summary.subprocess, "run",
                        lambda *a, **k: _FakeProc(stdout))


def _seed_transcript(claude_state, sid="sess-sum"):
    """A non-empty transcript so tail_text != "" and summarize reaches the call site
    (the path under test); without this it short-circuits before subprocess.run."""
    claude_state.add_transcript(sid, [
        {"type": "user", "message": {"content": "what next"}},
        {"type": "assistant", "message": {"content": "working on it"}},
    ])
    return sid


def test_summarize_extracts_json_wrapped_in_prose(mc_env, claude_state, monkeypatch):
    """`claude -p` often replies with prose before/after the JSON object. summarize
    must find the FIRST '{' .. LAST '}' span and parse it (session_summary.py:76-79).
    Pin both fields are extracted from the embedded object."""
    sid = _seed_transcript(claude_state)
    _stub_claude(monkeypatch, mc_env,
                 'Sure! Here is the summary you asked for:\n'
                 '{"progress": "wired the parser", "next": "add tests"}\n'
                 'Let me know if you need more.')

    out = mc_env.session_summary.summarize(sid, goal="ship it")

    assert out == {"progress": "wired the parser", "next": "add tests"}


def test_summarize_picks_outermost_braces_with_nested_json(mc_env, claude_state, monkeypatch):
    """find('{')..rfind('}') spans the OUTERMOST object even when the values contain
    nested braces — proves the extraction isn't a naive first-pair match."""
    sid = _seed_transcript(claude_state)
    _stub_claude(monkeypatch, mc_env,
                 'prose... {"progress": "did {x} and {y}", "next": "do {z}"} ...more prose')

    out = mc_env.session_summary.summarize(sid)

    assert out == {"progress": "did {x} and {y}", "next": "do {z}"}


def test_summarize_malformed_braces_returns_empty_dict(mc_env, claude_state, monkeypatch):
    """A reply with brace characters but invalid JSON between them -> json.loads
    raises -> the bare-except path returns {} (session_summary.py:80-82). Without a
    transcript this would short-circuit BEFORE the parse, so we seed one to force the
    real except path under test."""
    sid = _seed_transcript(claude_state)
    _stub_claude(monkeypatch, mc_env,
                 'here you go: { progress: not-valid-json, next: nope } done')

    assert mc_env.session_summary.summarize(sid) == {}


def test_summarize_no_braces_returns_empty_dict(mc_env, claude_state, monkeypatch):
    """A reply with NO JSON object at all -> start/end indices fail the
    `start >= 0 and end > start` guard -> {} (no parse attempted)."""
    sid = _seed_transcript(claude_state)
    _stub_claude(monkeypatch, mc_env, "I could not produce a summary, sorry.")

    assert mc_env.session_summary.summarize(sid) == {}


def test_summarize_defaults_missing_fields_to_empty_string(mc_env, claude_state, monkeypatch):
    """A valid JSON object missing one field -> summarize fills it with "" via
    obj.get(field, "") rather than raising (session_summary.py:79)."""
    sid = _seed_transcript(claude_state)
    _stub_claude(monkeypatch, mc_env, '{"progress": "only progress here"}')

    out = mc_env.session_summary.summarize(sid)

    assert out == {"progress": "only progress here", "next": ""}
