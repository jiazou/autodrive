"""AC22 — mission-control/bin/mc-bind.sh (subprocess into a temp HOME).

mc-bind.sh appends one event line to ~/mission-control/bindings.jsonl (append-only
log; harvest.load_bindings reads the latest per session). These tests drive the REAL
script via _helpers.run_script with HOME redirected to a per-test fake home, asserting
the appended JSON shape, the short-id resolution, and the missing-id exit behavior.

Re-read of main's mc-bind.sh (the +18 change): the short-id branch was reworked to
resolve a <=12-char prefix against ~/.claude/sessions/*.json (reading each file's
`sessionId` key), refusing ambiguous prefixes. It still does NOT `mkdir -p
~/mission-control` before appending (followup F2 stands), so every test seeds the dir
via _helpers.seed_mc_home first; one test also confirms the no-seed crash to pin F2.

Id-resolution order (mc-bind.sh:32-63): explicit arg wins; a <=12-char arg is a short
form resolved via the sessions dir; a longer arg is used verbatim; no arg falls back to
$CLAUDE_CODE_SESSION_ID and exits 1 when that is unset.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _helpers  # noqa: E402

SCRIPT = str(_helpers.REPO_ROOT / "mission-control" / "bin" / "mc-bind.sh")
FULL_UUID = "abcd1234-0000-0000-0000-0000deadbeef"  # 36 chars -> used verbatim


def _bindings_lines(home):
    """Return the parsed JSON records currently in ~/mission-control/bindings.jsonl."""
    p = Path(home) / "mission-control" / "bindings.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def _run(args, home, env=None):
    return _helpers.run_script([SCRIPT, *args], home=home, env=env)


# --------------------------------------------------------------------------- #
# --project: one well-formed bind line
# --------------------------------------------------------------------------- #
def test_project_appends_one_bind_line(fake_home):
    _helpers.seed_mc_home(fake_home)
    cp = _run([FULL_UUID, "--project", "Acme"], fake_home)

    assert cp.returncode == 0, cp.stderr
    recs = _bindings_lines(fake_home)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["event"] == "bind"
    assert rec["project"] == "Acme"
    assert rec["session_id"] == FULL_UUID
    assert isinstance(rec["ts"], int)


def test_project_with_task_records_task(fake_home):
    _helpers.seed_mc_home(fake_home)
    cp = _run([FULL_UUID, "--project", "Acme", "--task", "ship-it"], fake_home)

    assert cp.returncode == 0, cp.stderr
    (rec,) = _bindings_lines(fake_home)
    assert rec["event"] == "bind"
    assert rec["project"] == "Acme"
    assert rec["task"] == "ship-it"
    assert rec["session_id"] == FULL_UUID


def test_tab_flag_serializes_tab_name(fake_home):
    """--tab <name> sets the `tab` shell var (mc-bind.sh:26) which the python builder
    serializes as the `tab_name` JSON key (mc-bind.sh:73). Regresses if the flag is
    dropped or the key is renamed."""
    _helpers.seed_mc_home(fake_home)
    cp = _run([FULL_UUID, "--project", "Acme", "--tab", "left-pane"], fake_home)

    assert cp.returncode == 0, cp.stderr
    (rec,) = _bindings_lines(fake_home)
    assert rec["event"] == "bind"
    assert rec["session_id"] == FULL_UUID
    assert rec["tab_name"] == "left-pane", "the --tab value must serialize under tab_name"


# --------------------------------------------------------------------------- #
# --unbind: one unbind line
# --------------------------------------------------------------------------- #
def test_unbind_appends_unbind_line(fake_home):
    _helpers.seed_mc_home(fake_home)
    cp = _run(["--unbind", FULL_UUID], fake_home)

    assert cp.returncode == 0, cp.stderr
    (rec,) = _bindings_lines(fake_home)
    assert rec["event"] == "unbind"
    assert rec["session_id"] == FULL_UUID
    # unbind without --project emits no project key.
    assert "project" not in rec


# --------------------------------------------------------------------------- #
# session id from $CLAUDE_CODE_SESSION_ID when no arg given
# --------------------------------------------------------------------------- #
def test_session_id_from_env_when_no_arg(fake_home):
    _helpers.seed_mc_home(fake_home)
    cp = _run(["--project", "EnvProj"], fake_home,
              env={"CLAUDE_CODE_SESSION_ID": FULL_UUID})

    assert cp.returncode == 0, cp.stderr
    (rec,) = _bindings_lines(fake_home)
    assert rec["session_id"] == FULL_UUID
    assert rec["project"] == "EnvProj"


# --------------------------------------------------------------------------- #
# short-id resolution against a fake live session file
# --------------------------------------------------------------------------- #
def test_short_id_resolves_to_full_uuid(fake_home, claude_state):
    # claude_state.__init__ + add_session create ~/.claude/sessions/<uuid>.json with
    # the `sessionId` key the resolver reads; also seed ~/mission-control for the append.
    _helpers.seed_mc_home(fake_home)
    claude_state.add_session(FULL_UUID)

    short = FULL_UUID[:8]  # "abcd1234" -> <=12 chars -> short-form branch
    cp = _run([short, "--project", "Resolved"], fake_home)

    assert cp.returncode == 0, cp.stderr
    (rec,) = _bindings_lines(fake_home)
    assert rec["session_id"] == FULL_UUID, "short prefix must expand to the full id"
    assert rec["project"] == "Resolved"


def test_short_id_no_match_exits_nonzero_and_appends_nothing(fake_home):
    _helpers.seed_mc_home(fake_home)
    # No session files exist -> the short prefix matches nothing -> sid empty -> exit 1.
    cp = _run(["nomatch", "--project", "P"], fake_home)

    assert cp.returncode != 0
    assert _bindings_lines(fake_home) == []


def test_short_id_ambiguous_exits_nonzero_and_appends_nothing(fake_home, claude_state):
    _helpers.seed_mc_home(fake_home)
    # Two session files share the prefix -> resolver refuses -> non-zero, no line.
    # (The resolver matches on sessionId only; it does not filter on liveness/pid.)
    claude_state.add_session("dupe1234-0000-0000-0000-00000000aaaa")
    claude_state.add_session("dupe1234-0000-0000-0000-00000000bbbb")
    cp = _run(["dupe1234", "--project", "P"], fake_home)

    assert cp.returncode != 0
    assert _bindings_lines(fake_home) == []


# --------------------------------------------------------------------------- #
# missing id with unset CLAUDE_CODE_SESSION_ID -> non-zero, nothing written
# --------------------------------------------------------------------------- #
def test_missing_id_unset_env_exits_nonzero(fake_home):
    _helpers.seed_mc_home(fake_home)
    # run_script overlays os.environ; force the var empty so the unset-fallback fires.
    cp = _run(["--project", "P"], fake_home, env={"CLAUDE_CODE_SESSION_ID": ""})

    assert cp.returncode != 0
    assert _bindings_lines(fake_home) == [], "no malformed/partial line on the error path"


def test_unknown_flag_exits_nonzero(fake_home):
    _helpers.seed_mc_home(fake_home)
    cp = _run([FULL_UUID, "--bogus"], fake_home)

    assert cp.returncode != 0
    assert _bindings_lines(fake_home) == []


# --------------------------------------------------------------------------- #
# append-log semantics: each successful call adds exactly one line
# --------------------------------------------------------------------------- #
def test_each_call_appends_one_line(fake_home):
    _helpers.seed_mc_home(fake_home)
    assert _run([FULL_UUID, "--project", "A"], fake_home).returncode == 0
    assert _run([FULL_UUID, "--task", "t1"], fake_home).returncode == 0
    assert _run(["--unbind", FULL_UUID], fake_home).returncode == 0

    recs = _bindings_lines(fake_home)
    assert [r["event"] for r in recs] == ["bind", "bind", "unbind"]
    assert recs[0]["project"] == "A"
    assert recs[1]["task"] == "t1"


# --------------------------------------------------------------------------- #
# F2 pin: without ~/mission-control, the append-target dir is missing -> the
# `set -euo pipefail` script fails rather than silently creating the dir.
# --------------------------------------------------------------------------- #
def test_missing_mc_home_is_not_self_created(fake_home):
    # Deliberately do NOT seed_mc_home: confirm main's mc-bind.sh still does not
    # mkdir -p ~/mission-control (followup F2 stands as of main).
    cp = _run([FULL_UUID, "--project", "P"], fake_home)

    assert cp.returncode != 0, (
        "mc-bind.sh now self-creates ~/mission-control — update F2 if so"
    )
    # Pin F2 at the DIRECTORY level, not just the file: the append fails because the
    # parent dir is absent, and the script must leave it absent (no mkdir -p anywhere).
    # The bindings file being absent alone would still pass if mc-bind started doing
    # `mkdir -p ~/mission-control` and then died for an unrelated reason.
    assert not (Path(fake_home) / "mission-control").exists(), (
        "mc-bind.sh created the ~/mission-control directory — it must not self-create it (F2)"
    )
    assert not (Path(fake_home) / "mission-control" / "bindings.jsonl").exists()
    # The failure reason is the missing append target, surfaced by the python `open`.
    assert "No such file or directory" in cp.stderr, (
        f"expected a missing-path failure; stderr was:\n{cp.stderr}"
    )
