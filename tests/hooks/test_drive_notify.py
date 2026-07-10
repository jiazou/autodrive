"""AC6/AC8 — bin/drive-notify.sh fail-open transport + dedup slug.

AC6 (fail-open): the script ALWAYS exits 0 on EVERY path — unset `$DRIVE_NOTIFY_CMD`, bad/dangling
args, a missing RUN_DIR, a dedup-hit, and a transport that errors or times out — and NEVER writes
state.json (the ONLY file it writes is `$RUN_DIR/notified-*.marker`).
AC8 (dedup slug): a filesystem-safe marker for a hostile `waiting` (`stop:merge conflict at a/b`);
two distinct strings that SANITIZE to the same value get DISTINCT markers (the hash is over the RAW
waiting); and a repeat (waiting, tip) is deduped (no second send).
"""
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NOTIFY = REPO_ROOT / "bin" / "drive-notify.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or not NOTIFY.is_file(),
    reason="needs bash + bin/drive-notify.sh",
)


def run_notify(args, *, env_extra=None):
    """Invoke bin/drive-notify.sh from a CLEAN env (DRIVE_NOTIFY_CMD + RUN_DIR popped so the
    inert default and RUN_DIR resolution are deterministic). Returns the CompletedProcess."""
    env = {**os.environ}
    env.pop("DRIVE_NOTIFY_CMD", None)
    env.pop("RUN_DIR", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(["bash", str(NOTIFY), *args],
                          env=env, capture_output=True, text=True, timeout=30)


def _markers(rd):
    return sorted(p.name for p in Path(rd).glob("notified-*.marker"))


def _wait_for(path, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if Path(path).exists():
            return True
        time.sleep(0.03)
    return False


# --------------------------------------------------------------------------- #
# AC6 — every path exits 0; never writes state.json
# --------------------------------------------------------------------------- #
def test_unset_cmd_is_noop_no_marker(tmp_path):
    rd = tmp_path / "rd"; rd.mkdir()
    cp = run_notify(["--run-dir", str(rd), "--waiting", "gateB", "--tip", "abc", "--message", "hi"])
    assert cp.returncode == 0
    assert _markers(rd) == [], "an unset transport builds NO marker (pure no-op)"
    assert not (rd / "state.json").exists(), "drive-notify.sh must NEVER write state.json"


def test_missing_run_dir_is_noop(tmp_path):
    cp = run_notify(["--run-dir", str(tmp_path / "nope"), "--waiting", "gateB",
                     "--tip", "abc", "--message", "hi"],
                    env_extra={"DRIVE_NOTIFY_CMD": "cat"})
    assert cp.returncode == 0


def test_bad_and_dangling_args_exit_zero():
    assert run_notify(["--bogus", "x", "--waiting"]).returncode == 0  # dangling final flag
    assert run_notify([]).returncode == 0                             # no args at all


def test_real_send_delivers_message_on_stdin_and_writes_only_marker(tmp_path):
    rd = tmp_path / "rd"; rd.mkdir()
    out = tmp_path / "delivered.txt"
    cp = run_notify(["--run-dir", str(rd), "--waiting", "stop:merge conflict at a/b",
                     "--tip", "deadbeef", "--message", "the message body"],
                    env_extra={"DRIVE_NOTIFY_CMD": f"cat > {out}"})
    assert cp.returncode == 0
    assert _wait_for(out), "the backgrounded transport must receive the message on STDIN"
    assert out.read_text(encoding="utf-8") == "the message body"
    # exactly one filesystem-safe marker, and NO state.json.
    marks = _markers(rd)
    assert len(marks) == 1
    assert marks[0].startswith("notified-stop_merge_conflict_at_a_b-")  # sanitized + hash + tip
    assert not (rd / "state.json").exists()


def test_transport_nonzero_still_exits_zero(tmp_path):
    rd = tmp_path / "rd"; rd.mkdir()
    cp = run_notify(["--run-dir", str(rd), "--waiting", "gateA", "--tip", "t1", "--message", "m"],
                    env_extra={"DRIVE_NOTIFY_CMD": "exit 7"})  # transport errors
    assert cp.returncode == 0, "a non-zero transport must NOT make drive-notify.sh non-zero"


def test_past_timeout_transport_still_exits_zero(tmp_path):
    rd = tmp_path / "rd"; rd.mkdir()
    # A transport that sleeps well past a 1s timeout — the backgrounded+timeout-bounded send
    # cannot wedge the caller; the script returns 0 immediately.
    start = time.time()
    cp = run_notify(["--run-dir", str(rd), "--waiting", "gateB", "--tip", "t2", "--message", "m"],
                    env_extra={"DRIVE_NOTIFY_CMD": "sleep 30", "DRIVE_NOTIFY_TIMEOUT": "1"})
    assert cp.returncode == 0
    assert time.time() - start < 10, "the send must be backgrounded (no blocking on the transport)"


# --------------------------------------------------------------------------- #
# AC8 — dedup slug: filesystem-safe, collision-resistant, deduped repeat
# --------------------------------------------------------------------------- #
def test_dedup_repeat_waiting_tip_no_second_send(tmp_path):
    rd = tmp_path / "rd"; rd.mkdir()
    out = tmp_path / "n.txt"
    args = ["--run-dir", str(rd), "--waiting", "stop:x", "--tip", "abc123", "--message", "first"]
    cp1 = run_notify(args, env_extra={"DRIVE_NOTIFY_CMD": f"cat >> {out}"})
    assert cp1.returncode == 0 and _wait_for(out)
    first = out.read_text(encoding="utf-8")
    # Repeat the SAME (waiting, tip): dedup-hit -> exit 0, NO second send.
    cp2 = run_notify(["--run-dir", str(rd), "--waiting", "stop:x", "--tip", "abc123",
                      "--message", "second"],
                     env_extra={"DRIVE_NOTIFY_CMD": f"cat >> {out}"})
    assert cp2.returncode == 0
    time.sleep(0.3)
    assert out.read_text(encoding="utf-8") == first, "a repeated (waiting,tip) must NOT re-send"
    assert len(_markers(rd)) == 1, "the dedup marker is single per (waiting,tip)"


def test_sanitize_colliding_distinct_waitings_get_distinct_markers(tmp_path):
    rd = tmp_path / "rd"; rd.mkdir()
    # `stop:a b` and `stop:a/b` both SANITIZE to `stop_a_b` but the sha256 of the RAW waiting
    # differs, so they get DISTINCT markers (the hash prevents a false-dedup collision).
    for w in ("stop:a b", "stop:a/b"):
        cp = run_notify(["--run-dir", str(rd), "--waiting", w, "--tip", "T", "--message", "m"],
                        env_extra={"DRIVE_NOTIFY_CMD": "cat >/dev/null"})
        assert cp.returncode == 0
    marks = _markers(rd)
    assert len(marks) == 2, f"sanitize-colliding distinct strings must get DISTINCT markers; got {marks}"


def test_hostile_waiting_marker_is_filesystem_safe(tmp_path):
    rd = tmp_path / "rd"; rd.mkdir()
    cp = run_notify(["--run-dir", str(rd), "--waiting", "stop:merge conflict at a/b (x)!",
                     "--tip", "beef", "--message", "m"],
                    env_extra={"DRIVE_NOTIFY_CMD": "cat >/dev/null"})
    assert cp.returncode == 0
    marks = _markers(rd)
    assert len(marks) == 1
    name = marks[0]
    # no path separators or spaces leak into the filename (sanitized to `_`).
    assert "/" not in name and " " not in name and "!" not in name
    assert name.endswith("-beef.marker")
