"""Behavioral tests for bin/drive-stop-hook.py — the /drive Stop hook.

The hook reads a JSON payload on STDIN and decides whether to BLOCK the turn from
ending (so the pipeline keeps driving) or ALLOW the stop. It is biased HARD toward
allowing: it blocks ONLY on positive evidence that THIS session owns a not-done run
that is not waiting and not disabled. Every other path allows.

Contract (from the script + drive.md):
  - BLOCK  -> prints `{"decision": "block", "reason": ...}` to stdout, exit 0.
  - ALLOW  -> prints NOTHING, exit 0.
The ONLY observable difference between block and allow is the stdout JSON, so each
test asserts on that (plus exit 0 everywhere — the hook never exits non-zero).

We drive the REAL script via subprocess (same child-env shape as run_hook in
test_mc_hook.py) with HOME pointed at a per-test fake home, and we materialize the
run state at ~/.claude/harness-runs/<run>/state.json so the hook's glob finds it.
"""
import json
import os
import subprocess
import sys

import pytest

import _helpers  # noqa: E402  (tests/ on sys.path via conftest)

STOP_HOOK = _helpers.REPO_ROOT / "bin" / "drive-stop-hook.py"
FIXTURES = _helpers.REPO_ROOT / "tests" / "hooks" / "fixtures"
OVER_WATER = FIXTURES / "transcript-over-water.jsonl"    # Opus-4.8, sum 909200 (>= 850000)
UNDER_WATER = FIXTURES / "transcript-under-water.jsonl"  # Opus-4.8, sum 315000 (< 850000)

# The pre-flag set-flag steer's stable anchor (the exact sentence the hook appends, I2).
CONTEXT_PRESSURE_ANCHOR = "CONTEXT-PRESSURE: this run has crossed the rebirth high-water mark"
# The post-flag ESCALATION steer's stable anchor (I7: flag already set, steer the handoff).
ESCALATION_ANCHOR = (
    "this run is over the rebirth high-water mark and state.rebirth_pending is already set"
)
# Words the signal-only set-flag wording must NEVER use (it sets a flag, never enacts now).
FORBIDDEN_HANDOFF_WORDS = ("hand off now", "checkpoint now", "pause here now")


def run_hook(payload, *, home, env=None):
    """Invoke drive-stop-hook.py with `payload` (dict or str) on stdin, HOME=home.

    Mirrors test_mc_hook.run_hook's child-env (os.environ overlaid, HOME forced
    last) and pipes stdin. `env`, if given, is overlaid onto the child env (used to
    pin DRIVE_STOP_HOOK_PATHS — the hook's test-only scan-order seam). Returns the
    CompletedProcess.
    """
    payload_str = payload if isinstance(payload, str) else json.dumps(payload)
    child_env = dict(os.environ)
    if env:
        child_env.update(env)
    child_env["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(STOP_HOOK)],
        input=payload_str,
        env=child_env,
        cwd=str(_helpers.REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )


def write_run(home, run_id, state):
    """Materialize ~/.claude/harness-runs/<run_id>/state.json with `state`.
    Returns the Path. The hook globs harness-runs/*/state.json under HOME."""
    path = home / ".claude" / "harness-runs" / run_id / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def decision(cp):
    """The parsed stdout decision dict, or None when the hook produced no output
    (the ALLOW contract is: print nothing)."""
    out = cp.stdout.strip()
    if not out:
        return None
    return json.loads(out)


SID = "sess-owner-1"


def _block_state(**overrides):
    """A run state that SHOULD trigger a block: owned by SID, mid-pipeline,
    autoContinue not false, not waiting. Overrides mutate it per test."""
    st = {
        "runId": "run-42",
        "sessionId": SID,
        "stage": "implement",
        "phase": 1,
        "autoContinue": True,
    }
    st.update(overrides)
    return st


# --------------------------------------------------------------------------- #
# The positive BLOCK path (the keep-driving decision)
# --------------------------------------------------------------------------- #
def test_owned_not_done_run_blocks(fake_home):
    """A run owned by this session, mid-stage, not waiting, autoContinue truthy ->
    BLOCK with a steer reason. This is the one path that should ever block."""
    write_run(fake_home, "run-42", _block_state())
    cp = run_hook({"session_id": SID}, home=fake_home)

    assert cp.returncode == 0
    d = decision(cp)
    assert d is not None, "expected a block decision on stdout, got nothing (allowed)"
    assert d["decision"] == "block"
    # The reason must steer the agent and reference the run, so the next turn has
    # context (and defers to gates/STOPs).
    assert "run-42" in d["reason"]
    assert "implement" in d["reason"]  # stage echoed
    assert "Gate" in d["reason"]       # defers to the human gates


# --------------------------------------------------------------------------- #
# Fail-open / allow branches — each must produce NO output (allow).
# --------------------------------------------------------------------------- #
def test_stop_hook_active_loop_guard_allows(fake_home):
    """stop_hook_active set -> this stop is a continuation we already forced; allow
    it even though an otherwise-blockable run exists (the loop guard)."""
    write_run(fake_home, "run-42", _block_state())
    cp = run_hook({"session_id": SID, "stop_hook_active": True}, home=fake_home)
    assert cp.returncode == 0
    assert decision(cp) is None  # allowed: no block emitted


def test_no_session_id_allows(fake_home):
    """No session_id in the payload -> can't attribute a run -> allow, even with a
    blockable run present."""
    write_run(fake_home, "run-42", _block_state())
    cp = run_hook({"no_session": True}, home=fake_home)
    assert cp.returncode == 0
    assert decision(cp) is None


def test_no_matching_run_allows(fake_home):
    """A run exists but is owned by a DIFFERENT session -> not a /drive session for
    this sid -> allow."""
    write_run(fake_home, "run-42", _block_state(sessionId="someone-else"))
    cp = run_hook({"session_id": SID}, home=fake_home)
    assert cp.returncode == 0
    assert decision(cp) is None


def test_done_stage_allows(fake_home):
    """The owned run is at stage=done (PR open) -> the run is finished -> allow."""
    write_run(fake_home, "run-42", _block_state(stage="done"))
    cp = run_hook({"session_id": SID}, home=fake_home)
    assert cp.returncode == 0
    assert decision(cp) is None


def test_kill_switch_autocontinue_false_allows(fake_home):
    """autoContinue is exactly False -> the per-run kill-switch disables the hook
    -> allow even though the run is otherwise blockable."""
    write_run(fake_home, "run-42", _block_state(autoContinue=False))
    cp = run_hook({"session_id": SID}, home=fake_home)
    assert cp.returncode == 0
    assert decision(cp) is None


def test_waiting_state_allows(fake_home):
    """waiting is truthy -> the run is paused for the human (gate/STOP/question) ->
    allow the pause."""
    write_run(fake_home, "run-42", _block_state(waiting=True))
    cp = run_hook({"session_id": SID}, home=fake_home)
    assert cp.returncode == 0
    assert decision(cp) is None


def test_malformed_stdin_allows(fake_home):
    """Unparseable stdin -> can't read the hook input -> allow, no crash, no
    traceback (fail-open)."""
    write_run(fake_home, "run-42", _block_state())
    cp = run_hook("not json {{{", home=fake_home)
    assert cp.returncode == 0
    assert cp.stderr == ""  # fail-open, no traceback
    assert decision(cp) is None


def test_nondict_stdin_payload_hits_outer_failopen_backstop(fake_home):
    """STDIN is VALID JSON but not a dict (e.g. `[]`), so json.load succeeds (past the
    inner stdin try/except) and the very first `payload.get(...)` in main() raises
    AttributeError. That escapes to the OUTER `except Exception: sys.exit(0)` backstop
    in __main__ -> the hook must still exit 0, emit no stderr/traceback, and ALLOW.

    This directly exercises the outer fail-open backstop on a path the inner handlers
    do NOT catch (unlike test_malformed_stdin_allows, which is caught by the inner
    json.load except). Removing the outer `except Exception: sys.exit(0)` wrapper makes
    this AttributeError propagate -> non-zero rc + traceback on stderr (proven red)."""
    write_run(fake_home, "run-42", _block_state())  # a blockable run exists; never reached
    cp = run_hook("[]", home=fake_home)
    assert cp.returncode == 0          # outer backstop swallowed the AttributeError
    assert cp.stderr == ""             # no traceback leaked
    assert decision(cp) is None        # allow == no block emitted


def test_no_runs_directory_allows(fake_home):
    """No harness-runs dir at all -> glob finds nothing -> allow (this is the
    common case for a non-/drive session)."""
    assert not (fake_home / ".claude" / "harness-runs").exists()
    cp = run_hook({"session_id": SID}, home=fake_home)
    assert cp.returncode == 0
    assert decision(cp) is None


def test_unreadable_run_file_is_skipped_and_allows(fake_home):
    """A partial/corrupt state.json is skipped (not a crash); with no other matching
    run the hook allows."""
    path = fake_home / ".claude" / "harness-runs" / "run-bad" / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is : not json", encoding="utf-8")
    cp = run_hook({"session_id": SID}, home=fake_home)
    assert cp.returncode == 0
    assert cp.stderr == ""  # the per-file exception is swallowed
    assert decision(cp) is None


def test_nondict_run_file_allows_when_no_owned_run(fake_home):
    """A state.json that is VALID JSON but not an object (e.g. a list) is skipped like
    any other bad file; with no owned, not-done run present the hook allows with no
    traceback. Pins the allow contract for the non-dict-only scan."""
    path = fake_home / ".claude" / "harness-runs" / "run-nondict" / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1, 2, 3]", encoding="utf-8")  # valid JSON, not a dict
    cp = run_hook({"session_id": SID}, home=fake_home)
    assert cp.returncode == 0          # clean exit (allow)
    assert cp.stderr == ""             # no traceback leaked
    assert decision(cp) is None        # allow == no block emitted


def test_nondict_foreign_file_before_owned_run_still_blocks(fake_home):
    """A foreign run-dir whose state.json is VALID JSON but not an object (e.g. [1,2,3])
    is scanned BEFORE an owned, not-done run that should block. The non-dict file must be
    skipped like any other bad file so the scan CONTINUES to the owned run and BLOCKS.

    Regression guard for the fail-open bug: before the fix, the non-dict file parsed past
    the per-file `json.load` try, then `st.get(...)` raised AttributeError outside that
    try, aborting the WHOLE scan into the outer fail-open backstop -> the hook ALLOWED
    instead of blocking the owned not-done run.

    Order is pinned deterministically via DRIVE_STOP_HOOK_PATHS (the hook's test-only
    scan-order seam) rather than dir-name sort, so the non-dict file is provably reached
    FIRST regardless of filesystem glob order OR whether production happens to sort."""
    nondict = fake_home / ".claude" / "harness-runs" / "run-nondict" / "state.json"
    nondict.parent.mkdir(parents=True, exist_ok=True)
    nondict.write_text("[1, 2, 3]", encoding="utf-8")  # valid JSON, not a dict
    owned = write_run(fake_home, "run-mine", _block_state(runId="run-mine"))

    cp = run_hook(
        {"session_id": SID},
        home=fake_home,
        env={"DRIVE_STOP_HOOK_PATHS": json.dumps([str(nondict), str(owned)])},
    )
    assert cp.returncode == 0
    d = decision(cp)
    assert d is not None and d["decision"] == "block", \
        "scan must continue past the non-dict foreign file and block the owned run"
    assert "run-mine" in d["reason"]


def test_owned_run_among_unreadable_and_foreign_still_blocks(fake_home):
    """With a corrupt run AND a foreign-session run present, the hook still finds the
    one owned, not-done, not-waiting run and BLOCKS — proving the loop doesn't bail
    on the first skip and the match is session-scoped."""
    bad = fake_home / ".claude" / "harness-runs" / "run-bad" / "state.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{corrupt", encoding="utf-8")
    write_run(fake_home, "run-foreign", _block_state(sessionId="other", runId="run-foreign"))
    write_run(fake_home, "run-mine", _block_state(runId="run-mine"))

    cp = run_hook({"session_id": SID}, home=fake_home)
    assert cp.returncode == 0
    d = decision(cp)
    assert d is not None and d["decision"] == "block"
    assert "run-mine" in d["reason"]


def test_nonblockable_owned_run_before_active_owned_run_still_blocks(fake_home):
    """TWO not-done runs owned by THIS session: a NON-blockable one (waiting set)
    scanned FIRST, and a blockable one (not-done, not-waiting, autoContinue truthy)
    scanned LATER. The hook must scan PAST the waiting run and BLOCK on the active one.

    Regression guard for the same-session multi-run masking fail-open: before the fix,
    the loop broke on the FIRST owned not-done run and only THEN checked
    autoContinue/waiting — so the waiting run enumerated first masked the active run
    behind it and the hook ALLOWED instead of blocking real autonomous work.

    Order is pinned via DRIVE_STOP_HOOK_PATHS (the test-only scan-order seam) so the
    non-blockable run is provably reached first, independent of FS order."""
    waiting = write_run(
        fake_home, "run-waiting", _block_state(runId="run-waiting", waiting=True)
    )
    active = write_run(fake_home, "run-active", _block_state(runId="run-active"))

    cp = run_hook(
        {"session_id": SID},
        home=fake_home,
        env={"DRIVE_STOP_HOOK_PATHS": json.dumps([str(waiting), str(active)])},
    )
    assert cp.returncode == 0
    d = decision(cp)
    assert d is not None and d["decision"] == "block", \
        "scan must continue past the waiting owned run and block the active owned run"
    assert "run-active" in d["reason"]


def test_disabled_owned_run_before_active_owned_run_still_blocks(fake_home):
    """Sibling of the waiting-first masking test for the OTHER non-blockable owned
    state: a kill-switched run (autoContinue: False) owned by THIS session scanned
    FIRST, and a blockable owned run (not-done, not-waiting, autoContinue truthy)
    scanned LATER. The hook must scan PAST the disabled run and BLOCK on the active one.

    Regression guard for the same-session multi-run masking fail-open via the
    autoContinue:False branch: a kill-switched run enumerated ahead of an active one
    must not mask it. Order is pinned via DRIVE_STOP_HOOK_PATHS (the test-only
    scan-order seam) so the disabled run is provably reached first, independent of FS
    order."""
    disabled = write_run(
        fake_home, "run-disabled", _block_state(runId="run-disabled", autoContinue=False)
    )
    active = write_run(fake_home, "run-active", _block_state(runId="run-active"))

    cp = run_hook(
        {"session_id": SID},
        home=fake_home,
        env={"DRIVE_STOP_HOOK_PATHS": json.dumps([str(disabled), str(active)])},
    )
    assert cp.returncode == 0
    d = decision(cp)
    assert d is not None and d["decision"] == "block", \
        "scan must continue past the disabled owned run and block the active owned run"
    assert "run-active" in d["reason"]


# --------------------------------------------------------------------------- #
# Context-pressure detection (signal-only): AC1/AC2/AC3/AC4/AC7.
#
# The hook computes context% from the OWNED run's transcript (payload.transcript_path)
# and, when it crosses the hard high-water mark, APPENDS a signal-only steer to its
# block reason instructing the coordinator to set state.rebirth_pending=true. It never
# writes state.json (AC4), is idempotent (AC2/AC3), and fails open (AC7).
#
# `payload(transcript=...)` adds transcript_path; the block decision is otherwise the
# same keep-driving path the tests above exercise.
# --------------------------------------------------------------------------- #
def _payload(transcript=None, **extra):
    p = {"session_id": SID}
    if transcript is not None:
        p["transcript_path"] = str(transcript)
    p.update(extra)
    return p


def _read_state_bytes(path):
    return path.read_bytes()


# --- AC1: hard-water crossing appends the signal-only steer ---------------- #
def test_over_water_appends_rebirth_steer(fake_home):
    """An owned, not-done, not-waiting run with rebirth_pending != true and a transcript
    whose latest assistant usage sum >= window*0.85 -> the block reason CONTAINS the
    CONTEXT-PRESSURE sentence instructing state.rebirth_pending=true (AC1)."""
    write_run(fake_home, "run-42", _block_state())
    cp = run_hook(_payload(transcript=OVER_WATER), home=fake_home)

    assert cp.returncode == 0
    d = decision(cp)
    assert d is not None and d["decision"] == "block"
    assert CONTEXT_PRESSURE_ANCHOR in d["reason"], "expected the hard-water steer appended"
    assert "state.rebirth_pending=true" in d["reason"]
    # The pre-flag case emits the SET-FLAG steer, NOT the post-flag escalation (AC6).
    assert ESCALATION_ANCHOR not in d["reason"], "pre-flag must not emit the escalation steer"
    # The original continue steer is PRESERVED (still drives the pipeline).
    assert "Continue the pipeline" in d["reason"]
    assert "run-42" in d["reason"]
    # Signal-only wording: it says set the flag, NOT "hand off / checkpoint / pause" now.
    low = d["reason"].lower()
    for forbidden in FORBIDDEN_HANDOFF_WORDS:
        assert forbidden not in low, f"signal-only wording leaked an enact verb: {forbidden!r}"
    # It tells the coordinator explicitly NOT to hand off / checkpoint / pause here.
    assert "do NOT hand off" in d["reason"]
    assert "do NOT checkpoint" in d["reason"]
    assert "do NOT pause here" in d["reason"]


# --- AC2: below-water -> no steer ------------------------------------------ #
def test_under_water_no_rebirth_steer(fake_home):
    """Same run, transcript sum < window*0.85 -> the block reason does NOT contain the
    CONTEXT-PRESSURE sentence; the original continue steer is present & unchanged, and
    the hook still blocks-to-continue exactly as today (AC2)."""
    write_run(fake_home, "run-42", _block_state())
    cp = run_hook(_payload(transcript=UNDER_WATER), home=fake_home)

    assert cp.returncode == 0
    d = decision(cp)
    assert d is not None and d["decision"] == "block"
    assert CONTEXT_PRESSURE_ANCHOR not in d["reason"], "no steer expected below water"
    assert ESCALATION_ANCHOR not in d["reason"], "no escalation steer expected below water"
    assert "Continue the pipeline" in d["reason"]
    assert "run-42" in d["reason"]


# --- AC1/AC2 boundary: tokens EXACTLY at window*0.85 steers (>=, not >) ----- #
@pytest.mark.parametrize(
    "tokens, steers",
    [(850_000, True), (849_999, False)],
    ids=["exactly-at-hard", "one-below-hard"],
)
def test_hard_water_boundary_is_inclusive(fake_home, tokens, steers):
    """The hard-water comparison is `tokens >= window * fraction` (D27: compared on the
    raw token count vs the fractional byte threshold, no integer-pct rounding). For the
    default Opus window 1_000_000 * 0.85 = 850_000, a sum of EXACTLY 850_000 must steer
    and 849_999 must not — pins the inclusive boundary the whole detection pivots on."""
    trans = fake_home / f"boundary-{tokens}.jsonl"
    trans.write_text(
        '{"type": "assistant", "message": {"model": "claude-opus-4-8", '
        f'"usage": {{"input_tokens": {tokens}, "cache_creation_input_tokens": 0, '
        '"cache_read_input_tokens": 0}}}\n',
        encoding="utf-8",
    )
    write_run(fake_home, "run-42", _block_state())
    cp = run_hook(_payload(transcript=trans), home=fake_home)

    assert cp.returncode == 0
    d = decision(cp)
    assert d is not None and d["decision"] == "block"
    assert (CONTEXT_PRESSURE_ANCHOR in d["reason"]) is steers


# --- P1-1: model + tokens come from the SAME usage-bearing line ------------ #
def test_window_uses_model_of_latest_usage_line_not_a_later_usageless_line(fake_home):
    """Regression for the model/token line mismatch: the window must be resolved from the
    model on the SAME line the token sum came from (the last usage-bearing assistant
    line), NOT from a later usage-less/synthetic line whose model differs or is absent.

    Transcript: a usage-bearing Opus-4.8 line at 909_200 tokens (>= 1M*0.85 -> over its
    1M window), then a LATER usage-less assistant line with a DIFFERENT model
    (`claude-haiku-4`, no usage). Pre-fix the hook read the model from the latest line
    (haiku -> the 200k rule's bare `haiku`/`Haiku` token) while the tokens came from the
    opus line, so the %/window in the steer described the wrong window. Post-fix both come
    from the opus line: the steer fires (909_200 >= 850_000) and reports the
    1_000_000-token window."""
    # PREMISE PIN: this test discriminates only while the trailing model's window
    # differs from the usage-line model's. If a future table change gave claude-haiku-4
    # the same window as claude-opus-4-8, the assertions below would pass even with the
    # line-binding bug reintroduced — red loudly instead of losing power silently.
    sys.path.insert(0, str(_helpers.REPO_ROOT / "bin"))
    import rebirth_thresholds as rt
    th = rt.load_thresholds()
    assert rt.resolve_window("claude-haiku-4", th) == 200_000 \
        != rt.resolve_window("claude-opus-4-8", th), (
        "premise lost: the trailing model claude-haiku-4 must resolve a window "
        "different from the opus usage line's 1M for this line-binding test to "
        "discriminate — re-anchor the trailing model to a retained 200k family")
    trans = fake_home / "model-token-mismatch.jsonl"
    trans.write_text(
        '{"type": "assistant", "message": {"model": "claude-opus-4-8", '
        '"usage": {"input_tokens": 909200, "cache_creation_input_tokens": 0, '
        '"cache_read_input_tokens": 0}}}\n'
        # a later usage-less assistant line with a DIFFERENT model -> must be ignored
        '{"type": "assistant", "message": {"model": "claude-haiku-4"}}\n',
        encoding="utf-8",
    )
    write_run(fake_home, "run-42", _block_state())
    cp = run_hook(_payload(transcript=trans), home=fake_home)

    assert cp.returncode == 0
    d = decision(cp)
    assert d is not None and d["decision"] == "block"
    assert CONTEXT_PRESSURE_ANCHOR in d["reason"], \
        "must steer: tokens 909200 >= 1M*0.85 using the opus line's own window"
    # The window in the steer is the opus line's 1M, NOT the later haiku line's default.
    assert "1000000-token window" in d["reason"]
    assert "200000-token window" not in d["reason"]


# --- Sonnet-4 id-collision END-TO-END: the hook path this whole run fixes ---- #
@pytest.mark.parametrize(
    "model, steers",
    [("claude-sonnet-4-20250514", True), ("claude-sonnet-4-6", False)],
    ids=["sonnet-4-200k-steers", "sonnet-4-6-1M-no-steer"],
)
def test_sonnet4_id_collision_steers_at_200k_window(fake_home, model, steers):
    """The id-level collision the entire run guards, exercised on the REAL consumer path
    (the rebirth Stop-hook), not just the resolver: the same 300_000-token transcript
    steers for a real Sonnet-4 session (`claude-sonnet-4-20250514`, a 200_000 window —
    200_000*0.85 = 170_000 <= 300_000) but does NOT steer for Sonnet 4.6
    (`claude-sonnet-4-6`, a 1M window — 1_000_000*0.85 = 850_000 > 300_000). The two ids
    collide on the `sonnet-4` substring yet must resolve to OPPOSITE steer decisions at the
    same token count; pre-fix, `claude-sonnet-4-20250514` fell to the 1M default and never
    steered. Built inline like test_hard_water_boundary_is_inclusive (no fixture file)."""
    trans = fake_home / f"sonnet4-{model}.jsonl"
    trans.write_text(
        '{"type": "assistant", "message": {"model": "' + model + '", '
        '"usage": {"input_tokens": 300000, "cache_creation_input_tokens": 0, '
        '"cache_read_input_tokens": 0}}}\n',
        encoding="utf-8",
    )
    write_run(fake_home, "run-42", _block_state())
    cp = run_hook(_payload(transcript=trans), home=fake_home)

    assert cp.returncode == 0
    d = decision(cp)
    assert d is not None and d["decision"] == "block"
    assert (CONTEXT_PRESSURE_ANCHOR in d["reason"]) is steers


# --- AC5: post-flag over-water -> ESCALATION steer (not the set-flag steer) -- #
def test_already_pending_over_water_emits_escalation_steer(fake_home):
    """A run with rebirth_pending == true and a transcript OVER water -> the block reason
    contains the ESCALATION sentence (checkpoint + set waiting="rebirth" at the next safe
    boundary) and NOT the phase-2 set-flag sentence (don't re-emit "set the flag"; the
    coordinator already set it). The base continue steer is still emitted (AC5).

    Replaces the phase-2 idempotency test: that pre-change behavior (return "" when the
    flag was set) is now the two-branch split — the post-flag branch emits the escalation
    instead of nothing."""
    write_run(fake_home, "run-42", _block_state(rebirth_pending=True))
    cp = run_hook(_payload(transcript=OVER_WATER), home=fake_home)

    assert cp.returncode == 0
    d = decision(cp)
    assert d is not None and d["decision"] == "block"
    # Escalation steer IS present; the set-flag steer is ABSENT (the split, AC5).
    assert ESCALATION_ANCHOR in d["reason"], "expected the post-flag escalation steer"
    assert CONTEXT_PRESSURE_ANCHOR not in d["reason"], \
        "must not re-emit the set-flag steer once the flag is already set"
    # The escalation names the handoff sequence it defers to the coordinator's boundary.
    assert "next safe boundary" in d["reason"].lower()
    assert 'state.waiting="rebirth"' in d["reason"]
    # The proof it names is the BOTH-modes contract (per drive.md § I1), NOT checkpoint-only.
    assert "I1 routine" in d["reason"], "escalation must defer to the drive.md § I1 routine"
    assert "--mode checkpoint AND --mode state-lint" in d["reason"], (
        "escalation must name BOTH proof modes, never a checkpoint-only proof surface"
    )
    # The base keep-driving steer is preserved.
    assert "Continue the pipeline" in d["reason"]
    assert "run-42" in d["reason"]


# --- AC7: post-flag BELOW water -> neither steer ---------------------------- #
def test_already_pending_below_water_no_steer(fake_home):
    """A run with rebirth_pending == true but a transcript UNDER water -> neither the
    set-flag NOR the escalation steer (escalation is hard-water gated, AC7). The base
    continue steer is present + unchanged."""
    write_run(fake_home, "run-42", _block_state(rebirth_pending=True))
    cp = run_hook(_payload(transcript=UNDER_WATER), home=fake_home)

    assert cp.returncode == 0
    d = decision(cp)
    assert d is not None and d["decision"] == "block"
    assert ESCALATION_ANCHOR not in d["reason"], "escalation is hard-water gated"
    assert CONTEXT_PRESSURE_ANCHOR not in d["reason"]
    assert "Continue the pipeline" in d["reason"]


# --- AC8: signal-only — the hook NEVER writes state.json or pauses --------- #
@pytest.mark.parametrize(
    "transcript, pending",
    [(OVER_WATER, False), (UNDER_WATER, False), (OVER_WATER, True)],
    ids=["set-flag", "under-water", "escalation"],
)
def test_hook_leaves_state_byte_unchanged(fake_home, transcript, pending):
    """Across the set-flag / no-steer / ESCALATION cases (AC5-8), the hook prints ONLY a
    block decision, exits 0, and leaves state.json BYTE-UNCHANGED — detection is signal
    only; ONLY the coordinator writes rebirth_pending/waiting. No waiting/checkpoint/handoff
    is performed by the hook, including on the escalation (rebirth_pending=true) path
    (AC8)."""
    state = _block_state(**({"rebirth_pending": True} if pending else {}))
    path = write_run(fake_home, "run-42", state)
    before = _read_state_bytes(path)

    cp = run_hook(_payload(transcript=transcript), home=fake_home)

    assert cp.returncode == 0
    d = decision(cp)
    assert d is not None and set(d.keys()) == {"decision", "reason"}, \
        "the hook must print ONLY {decision, reason} — no waiting/marker field"
    assert d["decision"] == "block"
    assert _read_state_bytes(path) == before, "the hook must NOT mutate state.json"


# --- AC7: fail-open everywhere — detection error -> pre-change behavior ----- #
# The fail-open CONTRACT is byte-strict: on ANY detection error the steer helper must
# return "" so the hook's reason is the EXACT string it would emit with the extension
# absent (the original continue-only reason). Asserting merely "the anchor is absent"
# is too weak — a partial/garbled steer fragment could also lack the anchor. So every
# error path below asserts d["reason"] == the pre-change baseline, byte for byte.

# The ORIGINAL continue-only reason for run "run-42" — captured by running the hook
# with NO transcript_path (the no-transcript guard returns "" first, so this IS the
# pre-extension reason). Every error-path test below pins reason to THIS exact string.
def _baseline_reason(fake_home):
    """The hook's original continue-only block reason for run-42 (no steer appended).
    The byte-exact string a fully fail-open detection must degrade back to."""
    path = write_run(fake_home, "run-42", _block_state())
    cp = run_hook({"session_id": SID}, home=fake_home)  # no transcript_path -> no steer
    d = decision(cp)
    assert d is not None and d["decision"] == "block"
    assert CONTEXT_PRESSURE_ANCHOR not in d["reason"]
    path.unlink()  # clear so each caller re-materializes its own run-42 state
    return d["reason"]


def _assert_failopen(cp, baseline):
    """A fail-open error path: exit 0, no traceback, and reason BYTE-IDENTICAL to the
    pre-change baseline (steer helper returned "")."""
    assert cp.returncode == 0
    assert cp.stderr == ""
    d = decision(cp)
    assert d is not None and d["decision"] == "block"
    assert CONTEXT_PRESSURE_ANCHOR not in d["reason"]
    assert d["reason"] == baseline, "fail-open must restore the byte-exact pre-change reason"


def test_failopen_missing_transcript_path(fake_home):
    """No transcript_path in the payload -> token sum unavailable -> rebirth check
    SKIPPED, the hook emits its byte-exact original continue reason, exit 0 (AC7)."""
    baseline = _baseline_reason(fake_home)
    write_run(fake_home, "run-42", _block_state())
    cp = run_hook({"session_id": SID}, home=fake_home)  # no transcript_path
    _assert_failopen(cp, baseline)


def test_failopen_escalation_path_missing_transcript(fake_home):
    """AC8 fail-open on the ESCALATION (rebirth_pending=true) branch: a missing
    transcript_path with the flag already set degrades to the byte-exact original
    continue-only reason (NO escalation sentence) — the escalation branch is fail-open
    just like the set-flag branch."""
    baseline = _baseline_reason(fake_home)
    write_run(fake_home, "run-42", _block_state(rebirth_pending=True))
    cp = run_hook({"session_id": SID}, home=fake_home)  # no transcript_path, flag set
    assert ESCALATION_ANCHOR not in baseline  # sanity: baseline carries no steer
    _assert_failopen(cp, baseline)


def test_failopen_nonexistent_transcript_file(fake_home):
    """transcript_path points at a file that does not exist -> rebirth check skipped,
    byte-exact original reason, exit 0, no traceback (AC7)."""
    baseline = _baseline_reason(fake_home)
    write_run(fake_home, "run-42", _block_state())
    cp = run_hook(_payload(transcript=fake_home / "nope.jsonl"), home=fake_home)
    _assert_failopen(cp, baseline)


def test_failopen_no_usage_transcript(fake_home):
    """A transcript with no completed assistant usage line -> token sum unavailable ->
    SKIP the rebirth check (a fresh transcript is exactly this case -> no false steer);
    byte-exact original reason (AC7)."""
    baseline = _baseline_reason(fake_home)
    trans = fake_home / "fresh.jsonl"
    trans.write_text(
        '{"type": "user", "message": {"role": "user", "content": "hi"}}\n',
        encoding="utf-8",
    )
    write_run(fake_home, "run-42", _block_state())
    cp = run_hook(_payload(transcript=trans), home=fake_home)
    _assert_failopen(cp, baseline)


def test_failopen_unknown_model_below_default_byte_exact(fake_home):
    """An unknown model resolving to the default window whose sum is BELOW water -> no
    steer -> reason is byte-identical to the pre-change baseline (not merely
    anchor-absent). Pins the under-water unknown-model path to the strict contract."""
    baseline = _baseline_reason(fake_home)
    trans = fake_home / "unknown-under.jsonl"
    # sum 100000 < 1000000*0.85=850000 -> under water on the default (1M) window.
    trans.write_text(
        '{"type": "assistant", "message": {"model": "mystery-model-9", '
        '"usage": {"input_tokens": 100000, "cache_creation_input_tokens": 0, '
        '"cache_read_input_tokens": 0}}}\n',
        encoding="utf-8",
    )
    write_run(fake_home, "run-42", _block_state())
    cp = run_hook(_payload(transcript=trans), home=fake_home)
    _assert_failopen(cp, baseline)


def test_failopen_resolver_import_failure(fake_home):
    """`import rebirth_thresholds` inside the steer's try FAILS (the sibling module is
    absent from the bin/ the hook imports from) -> ImportError is swallowed -> byte-exact
    original reason, exit 0, no traceback (AC7). Run a COPY of bin/ WITHOUT the resolver
    module so the real `import rebirth_thresholds` raises on the live import path."""
    import shutil
    baseline = _baseline_reason(fake_home)
    bindir = fake_home / "bin-no-resolver"
    shutil.copytree(_helpers.REPO_ROOT / "bin", bindir)
    (bindir / "rebirth_thresholds.py").unlink()  # remove the sibling resolver

    write_run(fake_home, "run-42", _block_state())
    cp = subprocess.run(
        [sys.executable, str(bindir / "drive-stop-hook.py")],
        input=json.dumps(_payload(transcript=OVER_WATER)),
        env={**os.environ, "HOME": str(fake_home)},
        capture_output=True, text=True, timeout=30,
    )
    _assert_failopen(cp, baseline)


def test_failopen_steer_helper_unexpected_exception(fake_home, monkeypatch):
    """ANY unexpected exception inside the steer helper degrades to no steer (the
    catch-all `except Exception: return ""`). Force it by making the resolver's
    latest_usage_model_and_tokens raise a generic RuntimeError mid-detection (a path none
    of the typed guards cover) -> byte-exact original reason, exit 0, no traceback (AC7).

    Run a COPY of bin/ whose rebirth_thresholds.py raises in latest_usage_model_and_tokens
    (the function the steer helper calls), so the real steer hits its catch-all."""
    import shutil
    baseline = _baseline_reason(fake_home)
    bindir = fake_home / "bin-raising-resolver"
    shutil.copytree(_helpers.REPO_ROOT / "bin", bindir)
    resolver = bindir / "rebirth_thresholds.py"
    src = resolver.read_text(encoding="utf-8")
    # Make the resolver call the hook uses raise a generic (non-IO, non-Import) error.
    src += (
        "\n\ndef latest_usage_model_and_tokens(*_a, **_k):\n"
        "    raise RuntimeError('boom: unexpected steer-helper failure')\n"
    )
    resolver.write_text(src, encoding="utf-8")

    write_run(fake_home, "run-42", _block_state())
    cp = subprocess.run(
        [sys.executable, str(bindir / "drive-stop-hook.py")],
        input=json.dumps(_payload(transcript=OVER_WATER)),
        env={**os.environ, "HOME": str(fake_home)},
        capture_output=True, text=True, timeout=30,
    )
    _assert_failopen(cp, baseline)


def test_failopen_unknown_model_over_default_window_steers(fake_home):
    """Sibling of the above: an unknown model resolving to the default 1_000_000 window
    whose sum EXCEEDS 1_000_000*0.85=850_000 DOES steer — proving the default-window
    branch is live (not a silent skip). Unknown models default to 1M (the ordered two-rule
    table lists the 1M families in windows[0] and the 200k families in windows[1], and the
    `[1m]` marker covers an active beta); a genuinely unknown 200k-window model firing late
    is the accepted residual of the default-1M policy."""
    trans = fake_home / "unknown-model-hi.jsonl"
    trans.write_text(
        '{"type": "assistant", "message": {"model": "mystery-model-9", '
        '"usage": {"input_tokens": 900000, "cache_creation_input_tokens": 0, '
        '"cache_read_input_tokens": 0}}}\n',
        encoding="utf-8",
    )
    write_run(fake_home, "run-42", _block_state())
    cp = run_hook(_payload(transcript=trans), home=fake_home)

    assert cp.returncode == 0
    d = decision(cp)
    assert d is not None and CONTEXT_PRESSURE_ANCHOR in d["reason"]
    # PCT reported against the default window: 900000*100//1000000 = 90.
    assert "1000000-token window" in d["reason"]


def test_failopen_malformed_thresholds_file(fake_home, tmp_path):
    """A malformed bin/rebirth-thresholds.json -> the resolver's load raises -> the
    rebirth check is swallowed and the hook emits its original continue reason, exit 0,
    no crash (AC7). Exercised by running a COPY of bin/ whose data file is corrupt, so
    the real owned data file is untouched."""
    import shutil
    baseline = _baseline_reason(fake_home)
    bindir = tmp_path / "bin"
    shutil.copytree(_helpers.REPO_ROOT / "bin", bindir)
    (bindir / "rebirth-thresholds.json").write_text("not json {{{", encoding="utf-8")

    write_run(fake_home, "run-42", _block_state())
    cp = subprocess.run(
        [sys.executable, str(bindir / "drive-stop-hook.py")],
        input=json.dumps(_payload(transcript=OVER_WATER)),
        env={**os.environ, "HOME": str(fake_home)},
        capture_output=True, text=True, timeout=30,
    )
    _assert_failopen(cp, baseline)


# --------------------------------------------------------------------------- #
# AC11: the hook's module docstring `waiting` contract enumerates `rebirth`
# with its dual nature (I6/D37). The hook BEHAVIOUR is unchanged (truthiness
# only); this pins the documentation-contract amendment by reading the module's
# own __doc__ so it no longer reads as "human-pause only".
# --------------------------------------------------------------------------- #
def _hook_doc():
    """Load bin/drive-stop-hook.py's module __doc__ without executing main().
    The module only runs main() under `if __name__ == "__main__"`, so importing
    it by spec is side-effect free."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_drive_stop_hook_doc", str(STOP_HOOK))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.__doc__ or ""


def test_docstring_waiting_contract_enumerates_rebirth_dual_nature():
    """The hook docstring's `waiting` contract enumerates `rebirth` AND states its dual
    nature (set-to-pause in the outgoing session; auto-cleared-as-continue on resume),
    consistent with drive.md's canonical definition (AC11, I6/D37). A docstring that adds
    `rebirth` to the set but omits the continue/auto-clear semantics — or omits it — flips
    this test."""
    doc = _hook_doc()
    low = doc.lower()
    assert "rebirth" in low, "the docstring `waiting` contract must enumerate rebirth"
    # Dual nature: it is a CONTINUE on resume (auto-cleared), not a human pause.
    assert "continue-on-resume" in low or "auto-clear" in low or "auto-clears" in low, \
        "the docstring must state rebirth's continue/auto-clear-on-resume semantics"
    # And that the outgoing session SETS it to hand off (the set-to-pause half).
    assert "outgoing session sets" in low or "outgoing session" in low, \
        "the docstring must state the outgoing session sets waiting=rebirth to hand off"
    # The hook acts on truthiness only (it does not distinguish the value).
    assert "truthiness" in low


# --------------------------------------------------------------------------- #
# The DRIVE_STOP_HOOK_PATHS scan-order seam is honored ONLY under pytest.
# --------------------------------------------------------------------------- #
def _two_blockable_runs(home):
    """Two owned, blockable runs whose SORTED-glob order is a-first then z-second.
    Returns (a_path, z_path). The hook blocks on the FIRST blockable run in scan order,
    naming its runId in the reason — so which runId appears reveals the scan order used."""
    a = write_run(home, "run-a-first", _block_state(runId="run-a-first"))
    z = write_run(home, "run-z-second", _block_state(runId="run-z-second"))
    return a, z


def test_path_seam_honored_under_pytest(fake_home):
    """Sanity anchor: under pytest, the override order IS honored — feeding [z, a] makes
    z scanned first, so the block names run-z-second (not the production-sorted a-first)."""
    a, z = _two_blockable_runs(fake_home)
    cp = run_hook(
        {"session_id": SID},
        home=fake_home,
        env={"DRIVE_STOP_HOOK_PATHS": json.dumps([str(z), str(a)])},
    )
    d = decision(cp)
    assert d is not None and d["decision"] == "block"
    assert "run-z-second" in d["reason"], "override order should win under pytest"


def test_path_seam_is_noop_outside_pytest(fake_home):
    """Outside pytest the seam is a COMPLETE no-op: even with DRIVE_STOP_HOOK_PATHS=[z, a],
    production falls back to sorted(glob) -> a-first scanned first -> block names run-a-first.
    PYTEST_CURRENT_TEST="" is falsy, so the hook ignores the override (production behavior),
    proving a foreign parent-env value can never alter the real scan order."""
    a, z = _two_blockable_runs(fake_home)
    cp = run_hook(
        {"session_id": SID},
        home=fake_home,
        env={"DRIVE_STOP_HOOK_PATHS": json.dumps([str(z), str(a)]), "PYTEST_CURRENT_TEST": ""},
    )
    d = decision(cp)
    assert d is not None and d["decision"] == "block"
    assert "run-a-first" in d["reason"], "outside pytest the override must be ignored (sorted glob wins)"
    assert "run-z-second" not in d["reason"]
