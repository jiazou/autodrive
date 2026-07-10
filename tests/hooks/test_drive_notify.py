"""AC6/AC8 — bin/drive-notify.sh fail-open transport + dedup slug.

AC6 (fail-open): the script ALWAYS exits 0 on EVERY path — unset `$DRIVE_NOTIFY_CMD`, bad/dangling
args, a missing RUN_DIR, a dedup-hit, and a transport that errors or times out — and NEVER writes
state.json (the ONLY file it writes is `$RUN_DIR/notified-*.marker`).
AC8 (dedup slug): a filesystem-safe marker for a hostile `waiting` (`stop:merge conflict at a/b`);
two distinct strings that SANITIZE to the same value get DISTINCT markers (the hash is over the RAW
waiting); and a repeat (waiting, tip) is deduped (no second send).
"""
import hashlib
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


def test_shasum_absent_still_sends_bias_to_send(tmp_path):
    """AC6 fail-open (finalize): when `shasum` is ABSENT there is no reliable dedup key, so the
    script SKIPS the dedup gate and STILL sends (bias-to-send: a duplicate ping is benign, a
    miss is worse) — exiting 0 and writing NO `notified-*` marker. Shadowing shasum out of PATH
    (a shim dir with the needed tools but no shasum) drives the shipped fallback deterministically,
    independent of whether the host has shasum installed."""
    rd = tmp_path / "rd"; rd.mkdir()
    out = tmp_path / "delivered.txt"
    # Build a shim PATH with the tools the script needs (tr/cut/basename/sh/cat) but WITHOUT shasum,
    # so `command -v shasum` fails and the fail-open (empty-key) branch is taken deterministically.
    shim = tmp_path / "shim"; shim.mkdir()
    for tool in ("tr", "cut", "basename", "cat", "sh", "env", "timeout"):
        p = shutil.which(tool)
        if p:
            os.symlink(p, shim / tool)
    assert shutil.which("shasum", path=str(shim)) is None, "the shim PATH must NOT contain shasum"
    bash = shutil.which("bash")
    env = {"PATH": str(shim), "DRIVE_NOTIFY_CMD": f"cat > {out}"}
    cp = subprocess.run([bash, str(NOTIFY), "--run-dir", str(rd), "--waiting", "gateB",
                         "--tip", "abc", "--message", "hi"],
                        env=env, capture_output=True, text=True, timeout=30)
    assert cp.returncode == 0, "shasum absent must still exit 0 (fail-open)"
    assert _wait_for(out), "shasum absent must NOT suppress the send (bias-to-send)"
    assert out.read_text(encoding="utf-8") == "hi"
    assert _markers(rd) == [], "the shasum-absent bias-to-send path builds NO dedup marker"
    assert not (rd / "state.json").exists(), "drive-notify.sh must NEVER write state.json"


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


def _race(tmp_path, script, *, n=40):
    """Fire N racers for one (waiting,tip) at `script` behind a start-barrier and return
    (deliveries, markers). Deliveries are counted race-free by a per-send unique file
    (`$$` = the transport sh's PID) — the pre-fix `mv -f` overwrites the SINGLE marker path,
    so markers can't be counted; sends must."""
    tag = script.stem
    rd = tmp_path / f"rd-{tag}"; rd.mkdir()
    deliv = tmp_path / f"deliv-{tag}"; deliv.mkdir()
    barrier = tmp_path / f"go-{tag}"
    env = {**os.environ}
    env.pop("RUN_DIR", None)
    env["DRIVE_NOTIFY_CMD"] = f"cat > {deliv}/d.$$"   # $$ expanded by the transport sh -> unique
    env["DRIVE_NOTIFY_TIMEOUT"] = "20"
    args = ["--run-dir", str(rd), "--waiting", "gateB", "--tip", "deadbeef", "--message", "m"]
    # Each racer spins on the barrier file then execs the script — releasing all N together.
    wrapper = f'while [ ! -e "{barrier}" ]; do :; done; exec bash "{script}" "$@"'
    procs = [subprocess.Popen(["bash", "-c", wrapper, "notify", *args], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
             for _ in range(n)]
    time.sleep(0.4)      # let all N reach the spin-wait
    barrier.touch()      # release the herd
    for p in procs:
        p.wait(timeout=30)
    # Wait for the (backgrounded) send(s) to land, then let any stragglers settle.
    end = time.time() + 5
    while time.time() < end and not any(deliv.iterdir()):
        time.sleep(0.03)
    time.sleep(1.0)
    return len(list(deliv.iterdir())), len(_markers(rd))


def test_concurrent_same_waiting_tip_exactly_one_send(tmp_path):
    """AC8 CONCURRENCY: N racers for one (waiting,tip) must yield EXACTLY ONE delivery — the
    ATOMIC O_EXCL marker claim admits a single sender; every other racer loses the claim and
    exits 0 WITHOUT sending.

    Mutation guard (DETERMINISTIC): a RACY variant that restores the old check-then-create dedup
    WITH a widened window double-sends under the SAME harness — proving (a) the harness DETECTS a
    double-send (so the exactly-ONE assertion is not vacuous) and (b) the atomic claim is the
    load-bearing difference. The shipped narrow-window TOCTOU is timing-dependent to hit black-box,
    so the variant makes the window observable — exactly how the audit reproduced it (injected
    sleep). The `sleep 0.3` presence check reds if the atomic-claim anchor is ever reverted."""
    # Real (atomic) script: exactly ONE delivery, one marker.
    sends, marks = _race(tmp_path, NOTIFY)
    assert sends == 1, f"the atomic claim must admit exactly ONE sender; got {sends}"
    assert marks == 1, "a single dedup marker for the (waiting,tip)"

    # Racy variant: check-then-create with a WIDENED window -> the TOCTOU manifests -> many sends.
    racy_src = NOTIFY.read_text(encoding="utf-8").replace(
        '( set -o noclobber; : > "$MARKER" ) 2>/dev/null || exit 0',
        '[ -e "$MARKER" ] && exit 0\n  sleep 0.3\n  : > "$MARKER"')
    assert "sleep 0.3" in racy_src, \
        "the atomic-claim anchor must be present to build the racy variant (fix reverted?)"
    racy = tmp_path / "drive-notify-racy.sh"
    racy.write_text(racy_src, encoding="utf-8")
    racy_sends, _ = _race(tmp_path, racy)
    assert racy_sends > 1, \
        f"the racy check-then-create pattern MUST double-send under concurrency; got {racy_sends}"


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


# --------------------------------------------------------------------------- #
# P1 (BLOCKING, codex-review-1.1) — a hostile --tip must NOT escape $RUN_DIR via the marker path
# (path-traversal). --tip is sanitized the same way as the slug ([^A-Za-z0-9._-] → '_'), so the
# marker ALWAYS stays directly inside $RUN_DIR.
# --------------------------------------------------------------------------- #
def test_hostile_tip_traversal_repro_no_escape(tmp_path):
    """FAITHFUL repro of the codex BLOCKING: `--tip 'a/../../escaped'` WITH the intermediate dir
    pre-created (the repro condition that made the unsanitized `mv` land OUTSIDE $RUN_DIR) must NOT
    write `escaped.marker` in $RUN_DIR's parent. Reds against the pre-fix (unsanitized) script."""
    parent = tmp_path / "run"
    rd = parent / "rd"
    rd.mkdir(parents=True)
    waiting = "gateB"
    h = hashlib.sha256(waiting.encode()).hexdigest()[:12]
    # the intermediate path component the traversal would write THROUGH (the repro precondition).
    (rd / f"notified-{waiting}-{h}-a").mkdir()
    before_parent = {p.name for p in parent.iterdir()}
    cp = run_notify(["--run-dir", str(rd), "--waiting", waiting, "--tip", "a/../../escaped",
                     "--message", "m"], env_extra={"DRIVE_NOTIFY_CMD": "cat >/dev/null"})
    assert cp.returncode == 0
    assert not (parent / "escaped.marker").exists(), \
        "a hostile --tip ESCAPED $RUN_DIR (path traversal) — the marker must stay inside $RUN_DIR"
    assert {p.name for p in parent.iterdir()} == before_parent, \
        "nothing new may appear in $RUN_DIR's parent"


@pytest.mark.parametrize("hostile_tip", ["a/../../escaped", "x/y", "..", "/etc/passwd", "../../.."])
def test_hostile_tip_marker_stays_inside_run_dir(tmp_path, hostile_tip):
    """For ANY hostile --tip: exit 0, NO file created outside $RUN_DIR, and every marker written
    stays DIRECTLY inside $RUN_DIR (sanitized name, no path separator, no subdir)."""
    parent = tmp_path / "run"
    rd = parent / "rd"
    rd.mkdir(parents=True)
    cp = run_notify(["--run-dir", str(rd), "--waiting", "gateB", "--tip", hostile_tip, "--message", "m"],
                    env_extra={"DRIVE_NOTIFY_CMD": "cat >/dev/null"})
    assert cp.returncode == 0
    assert {p.name for p in parent.iterdir()} == {"rd"}, \
        f"a hostile --tip must not create files outside $RUN_DIR; parent={list(parent.iterdir())}"
    for p in rd.iterdir():
        if p.name.endswith(".marker"):
            assert p.parent == rd and "/" not in p.name, f"marker escaped $RUN_DIR: {p}"
