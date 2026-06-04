"""AC23 — mission-control/bin/mc-hook.py contract (slice 3.1).

mc-hook.py is a Claude Code hook: it reads a JSON payload on STDIN, takes a
`status` argv, and appends ONE {ts, session_id, status} line to
~/mission-control/status.jsonl keyed by the payload's session_id (falling back
to the CLAUDE_CODE_SESSION_ID env var). It prints NOTHING to stdout and exits 0
unconditionally — even on malformed stdin or an unwritable ledger path
(followup F2: it wraps the append in try/except and never mkdir's the dir, so a
missing ~/mission-control is a silent no-op).

These run the REAL script via subprocess (piping JSON to stdin) into a fake HOME.
seed_mc_home(home) is called FIRST in the happy-path tests so ~/mission-control
exists and the appended line is observable; the silent-failure test deliberately
SKIPS seeding to pin the "exit 0 even when it can't write" contract.

run_script (tests/_helpers.py) can't pipe stdin, so we call subprocess.run
directly here with HOME forced to the fake home and cwd at the repo root — same
child-env shape as run_script, plus `input=`.
"""
import json
import os
import subprocess
import sys

import pytest

# tests/ is on sys.path (conftest); _helpers gives REPO_ROOT + seed_mc_home.
import _helpers  # noqa: E402

MC_HOOK = _helpers.REPO_ROOT / "mission-control" / "bin" / "mc-hook.py"


def run_hook(status, payload_str, *, home, extra_env=None):
    """Invoke mc-hook.py <status> with `payload_str` on stdin, HOME=home.

    Mirrors _helpers.run_script's child-env (os.environ overlaid with extra_env,
    HOME forced last) but adds stdin piping, which run_script doesn't support.
    Returns the CompletedProcess.
    """
    child_env = dict(os.environ)
    if extra_env:
        child_env.update(extra_env)
    child_env["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(MC_HOOK), status],
        input=payload_str,
        env=child_env,
        cwd=str(_helpers.REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )


def read_ledger_lines(home):
    """Parsed JSON records from ~/mission-control/status.jsonl (empty if absent)."""
    path = home / "mission-control" / "status.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def test_valid_payload_appends_one_record(fake_home):
    """A valid payload with session_id appends exactly one {ts, session_id, status}
    line; exit 0; stdout silent."""
    _helpers.seed_mc_home(fake_home)
    cp = run_hook("waiting", json.dumps({"session_id": "sess-abc"}), home=fake_home)

    assert cp.returncode == 0
    assert cp.stdout == ""  # hook contract: NOTHING to stdout

    recs = read_ledger_lines(fake_home)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["session_id"] == "sess-abc"
    assert rec["status"] == "waiting"
    assert isinstance(rec["ts"], int)
    # Exactly these keys, nothing extra.
    assert set(rec) == {"ts", "session_id", "status"}


def test_status_comes_from_argv(fake_home):
    """The status field is the argv value, not anything in the payload."""
    _helpers.seed_mc_home(fake_home)
    # Put a decoy 'status' in the payload to prove argv wins.
    cp = run_hook("idle", json.dumps({"session_id": "s1", "status": "DECOY"}),
                  home=fake_home)
    assert cp.returncode == 0
    recs = read_ledger_lines(fake_home)
    assert len(recs) == 1
    assert recs[0]["status"] == "idle"
    assert recs[0]["session_id"] == "s1"


def test_session_id_env_fallback(fake_home):
    """Payload WITHOUT session_id but CLAUDE_CODE_SESSION_ID set -> the appended
    line uses the env session_id."""
    _helpers.seed_mc_home(fake_home)
    cp = run_hook("active", json.dumps({"no_session": True}), home=fake_home,
                  extra_env={"CLAUDE_CODE_SESSION_ID": "env-sid-42"})
    assert cp.returncode == 0
    recs = read_ledger_lines(fake_home)
    assert len(recs) == 1
    assert recs[0]["session_id"] == "env-sid-42"
    assert recs[0]["status"] == "active"


def test_payload_session_id_wins_over_env(fake_home):
    """When both are present, the payload session_id takes precedence over env
    (sid = payload.get(...) or env)."""
    _helpers.seed_mc_home(fake_home)
    cp = run_hook("waiting", json.dumps({"session_id": "from-payload"}),
                  home=fake_home,
                  extra_env={"CLAUDE_CODE_SESSION_ID": "from-env"})
    assert cp.returncode == 0
    recs = read_ledger_lines(fake_home)
    assert len(recs) == 1
    assert recs[0]["session_id"] == "from-payload"


def test_no_session_id_anywhere_writes_nothing(fake_home):
    """No payload session_id AND no env var -> sid is "" (falsy) -> NO line written,
    but still exit 0 (graceful no-op)."""
    _helpers.seed_mc_home(fake_home)
    # Ensure the env var is empty in the child (conftest's fake_home doesn't set it;
    # pass it explicitly empty to be robust against an inherited value).
    cp = run_hook("active", json.dumps({"foo": "bar"}), home=fake_home,
                  extra_env={"CLAUDE_CODE_SESSION_ID": ""})
    assert cp.returncode == 0
    assert cp.stdout == ""
    assert read_ledger_lines(fake_home) == []


def test_malformed_stdin_exits_zero_no_crash(fake_home):
    """Non-JSON stdin -> payload={} (exception swallowed). With no env session_id
    there is no sid, so nothing is written, but the script must NOT crash and must
    exit 0 (stderr empty — no traceback)."""
    _helpers.seed_mc_home(fake_home)
    cp = run_hook("active", "this is not json {{{", home=fake_home,
                  extra_env={"CLAUDE_CODE_SESSION_ID": ""})
    assert cp.returncode == 0
    assert cp.stdout == ""
    assert cp.stderr == ""  # no traceback
    assert read_ledger_lines(fake_home) == []


def test_malformed_stdin_with_env_sid_still_writes(fake_home):
    """Malformed stdin -> payload={}, but the env session_id fallback still applies,
    so a graceful line IS written. Pins that the malformed-stdin guard only zeroes
    the payload, not the env fallback."""
    _helpers.seed_mc_home(fake_home)
    cp = run_hook("idle", "<<<garbage>>>", home=fake_home,
                  extra_env={"CLAUDE_CODE_SESSION_ID": "fallback-sid"})
    assert cp.returncode == 0
    recs = read_ledger_lines(fake_home)
    assert len(recs) == 1
    assert recs[0]["session_id"] == "fallback-sid"
    assert recs[0]["status"] == "idle"


def test_absent_dir_silent_no_op_without_seed(fake_home):
    """WITHOUT seed_mc_home: ~/mission-control does not exist. The script never
    mkdir's it and wraps the append in try/except, so it exits 0 silently and
    writes NOTHING even though a valid sid was supplied (followup F2's
    silent-failure contract)."""
    # Deliberately NOT calling seed_mc_home(fake_home).
    assert not (fake_home / "mission-control").exists()

    cp = run_hook("waiting", json.dumps({"session_id": "s-x"}), home=fake_home)

    assert cp.returncode == 0
    assert cp.stdout == ""
    assert cp.stderr == ""  # the OSError is swallowed, no traceback
    # No dir was created and no line was written. Pin the DIRECTORY absent too:
    # mc-hook never mkdir's its dir (it opens the ledger path directly and
    # swallows the OSError), so a regression that started mkdir-p'ing would
    # leave ~/mission-control behind and trip this.
    assert not (fake_home / "mission-control").exists()
    assert not (fake_home / "mission-control" / "status.jsonl").exists()
    assert read_ledger_lines(fake_home) == []


def test_multiple_invocations_append(fake_home):
    """Each invocation appends another line (it's an append-only log)."""
    _helpers.seed_mc_home(fake_home)
    run_hook("waiting", json.dumps({"session_id": "s1"}), home=fake_home)
    run_hook("active", json.dumps({"session_id": "s1"}), home=fake_home)
    run_hook("idle", json.dumps({"session_id": "s2"}), home=fake_home)

    recs = read_ledger_lines(fake_home)
    assert len(recs) == 3
    assert [r["status"] for r in recs] == ["waiting", "active", "idle"]
    assert [r["session_id"] for r in recs] == ["s1", "s1", "s2"]


def test_default_status_when_argv_missing(fake_home):
    """No status argv -> the script defaults status to "active"
    (status = sys.argv[1] if len(sys.argv) > 1 else "active")."""
    _helpers.seed_mc_home(fake_home)
    child_env = dict(os.environ)
    child_env["HOME"] = str(fake_home)
    cp = subprocess.run(
        [sys.executable, str(MC_HOOK)],  # no status arg
        input=json.dumps({"session_id": "s-default"}),
        env=child_env,
        cwd=str(_helpers.REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert cp.returncode == 0
    recs = read_ledger_lines(fake_home)
    assert len(recs) == 1
    assert recs[0]["status"] == "active"
    assert recs[0]["session_id"] == "s-default"
