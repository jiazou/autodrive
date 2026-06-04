"""AC24 — mission-control/bin/install_hooks.py.

Drives the REAL script via subprocess (HOME redirected to fake_home) and asserts
its actual behavior on main: it merges three passive-capture hook entries into
~/.claude/settings.json — Notification->waiting, UserPromptSubmit->active,
Stop->idle — each pointing at mc-hook.py. The schema written is
settings["hooks"][<event>] = [ {"hooks": [{"type":"command","command": cmd}]} ].

Verified properties:
- creates settings.json (and ~/.claude) from nothing, exit 0;
- idempotent: a 2nd run adds NOTHING — exactly one mc-hook entry per event;
- merge, not overwrite: pre-existing unrelated top-level keys AND a pre-existing
  non-mc hook on one of the events are preserved while the mc-hook entries appear.

The script reads HOME at call time (os.path.expanduser inside the body), so
run_script's HOME redirection is sufficient — no extra wiring needed. It takes an
optional argv[1] = MC root used only to build the mc-hook.py command path; we let
it default to the repo's own mission-control dir.
"""
import json

from _helpers import REPO_ROOT, run_script

SCRIPT = str(REPO_ROOT / "mission-control" / "bin" / "install_hooks.py")

# The three events the script wires, in main's wiring map.
EXPECTED_EVENTS = ("Notification", "UserPromptSubmit", "Stop")
EXPECTED_STATUS = {"Notification": "waiting", "UserPromptSubmit": "active", "Stop": "idle"}


def _run(home):
    return run_script(["python3", SCRIPT], home=home)


def _read_settings(home):
    path = home / ".claude" / "settings.json"
    assert path.exists(), f"settings.json not created at {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _mc_entries(hook_array):
    """Entries in a settings hooks[event] array that reference mc-hook.py."""
    return [e for e in hook_array if "mc-hook.py" in json.dumps(e)]


# --------------------------------------------------------------------------- #
# Fresh install
# --------------------------------------------------------------------------- #
def test_creates_settings_with_all_three_events(fake_home):
    """No pre-existing settings.json -> file created with one mc-hook entry per
    wired event, command pointing at mc-hook.py <status>. Exit 0."""
    assert not (fake_home / ".claude" / "settings.json").exists()

    proc = _run(fake_home)
    assert proc.returncode == 0, proc.stderr

    settings = _read_settings(fake_home)
    hooks = settings["hooks"]
    for event in EXPECTED_EVENTS:
        assert event in hooks, f"missing event {event} in {hooks}"
        entries = _mc_entries(hooks[event])
        assert len(entries) == 1, f"event {event}: expected 1 mc entry, got {hooks[event]}"
        cmd = entries[0]["hooks"][0]
        assert cmd["type"] == "command"
        # Pin the stable shape of the command string install_hooks writes:
        # f"{sys.executable} {MC}/bin/mc-hook.py {status}". We don't pin the
        # absolute python/MC prefix (varies by machine), but the contiguous
        # "/bin/mc-hook.py <status>" tail must match per event — so a malformed
        # command (wrong script path tail, dropped /bin/, or wrong status arg)
        # would fail here.
        assert cmd["command"].rstrip().endswith(
            f"/bin/mc-hook.py {EXPECTED_STATUS[event]}"
        ), cmd["command"]


# --------------------------------------------------------------------------- #
# Idempotency
# --------------------------------------------------------------------------- #
def test_second_run_adds_no_duplicates(fake_home):
    """Running twice yields exactly ONE mc-hook entry per event (no duplication);
    both runs exit 0 and the settings are byte-identical after the 2nd run."""
    assert _run(fake_home).returncode == 0
    first = (fake_home / ".claude" / "settings.json").read_text(encoding="utf-8")

    proc2 = _run(fake_home)
    assert proc2.returncode == 0, proc2.stderr
    assert "no change" in proc2.stdout.lower(), proc2.stdout

    second = (fake_home / ".claude" / "settings.json").read_text(encoding="utf-8")
    assert first == second, "2nd run mutated settings.json"

    settings = json.loads(second)
    for event in EXPECTED_EVENTS:
        assert len(_mc_entries(settings["hooks"][event])) == 1, settings["hooks"][event]


# --------------------------------------------------------------------------- #
# Merge / preserve
# --------------------------------------------------------------------------- #
def test_preserves_unrelated_settings_and_hooks(fake_home):
    """Pre-existing unrelated top-level keys and a non-mc hook on one event survive;
    the mc-hook entries are merged in (the install MERGES, never overwrites)."""
    claude_dir = fake_home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    foreign_hook = {"hooks": [{"type": "command", "command": "echo not-mc"}]}
    preexisting = {
        "model": "x",
        "someOther": 1,
        "hooks": {
            # A foreign hook already on an event the installer also targets.
            "Stop": [foreign_hook],
            # An event the installer does NOT touch — must remain untouched.
            "PreToolUse": [{"hooks": [{"type": "command", "command": "echo pre"}]}],
        },
    }
    settings_path = claude_dir / "settings.json"
    settings_path.write_text(json.dumps(preexisting), encoding="utf-8")

    proc = _run(fake_home)
    assert proc.returncode == 0, proc.stderr

    settings = _read_settings(fake_home)

    # Unrelated top-level keys preserved.
    assert settings["model"] == "x"
    assert settings["someOther"] == 1

    # Foreign event untouched.
    assert settings["hooks"]["PreToolUse"] == preexisting["hooks"]["PreToolUse"]

    # Foreign Stop hook preserved AND the mc-hook Stop entry added alongside it.
    stop = settings["hooks"]["Stop"]
    assert foreign_hook in stop, f"foreign Stop hook dropped: {stop}"
    assert len(_mc_entries(stop)) == 1, stop

    # The other two events got their mc-hook entries too.
    for event in ("Notification", "UserPromptSubmit"):
        assert len(_mc_entries(settings["hooks"][event])) == 1, settings["hooks"][event]


# --------------------------------------------------------------------------- #
# Migrate-on-rename (the rename-safety contract)
# --------------------------------------------------------------------------- #
def test_migrates_stale_path_on_rerun(fake_home):
    """A pre-existing mc-hook entry at an OLD path (e.g. left over from before a repo
    rename claude-harness -> autodrive) is MIGRATED to the current command on re-run:
    updated in place to the new path, NOT duplicated, and the stale dead path removed.
    Without this, a renamed install leaves a hook pointing at a deleted file."""
    claude_dir = fake_home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    stale_cmd = (
        "/usr/bin/python3 /Users/old/claude-harness/mission-control/bin/mc-hook.py idle"
    )
    foreign = {"hooks": [{"type": "command", "command": "echo keep-me"}]}
    preexisting = {
        "hooks": {
            # foreign hook + a STALE-path mc-hook entry on the same event
            "Stop": [foreign, {"hooks": [{"type": "command", "command": stale_cmd}]}],
        },
    }
    (claude_dir / "settings.json").write_text(json.dumps(preexisting), encoding="utf-8")

    proc = _run(fake_home)
    assert proc.returncode == 0, proc.stderr

    stop = _read_settings(fake_home)["hooks"]["Stop"]
    # exactly ONE mc-hook entry — migrated, not duplicated
    mc = _mc_entries(stop)
    assert len(mc) == 1, f"expected 1 mc entry after migration, got {stop}"
    # it points at the CURRENT repo's mc-hook.py, not the stale claude-harness path
    cmd = mc[0]["hooks"][0]["command"]
    assert "claude-harness" not in cmd, f"stale path not migrated: {cmd}"
    assert cmd.rstrip().endswith("/bin/mc-hook.py idle"), cmd
    # the stale dead-path entry is gone
    assert not any(stale_cmd in json.dumps(e) for e in stop), f"stale entry remained: {stop}"
    # the foreign hook on the same event is preserved
    assert foreign in stop, f"foreign hook dropped: {stop}"
