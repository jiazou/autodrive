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
