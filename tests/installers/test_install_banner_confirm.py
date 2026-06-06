"""Banner + TTY-gated confirm for both installers.

Covers the disclosure banner (always printed) and the confirm gate added to
bin/install-drive-hooks.sh and bin/install-operating-rules.sh:
  - the banner prints (to stderr) on every run;
  - non-interactive (no TTY) and DRIVE_INSTALL_ASSUME_YES=1 auto-proceed (no prompt);
  - install-drive-hooks skips the prompt when given an explicit $1 target path;
  - an interactive DECLINE (a real pty, 'n') exits 1 and changes nothing;
  - an interactive ACCEPT ('y') proceeds.

run_script is subprocess-with-pipes (no TTY) — perfect for the auto-skip paths. The
interactive paths need a pty, so those use pty.fork directly.
"""
import os
import pty

from _helpers import REPO_ROOT, run_script

DRIVE_HOOKS = str(REPO_ROOT / "bin" / "install-drive-hooks.sh")
OP_RULES = str(REPO_ROOT / "bin" / "install-operating-rules.sh")


def _run_pty(argv, env, reply):
    """Run argv under a pty (so `[ -t 0 ] && [ -t 1 ]` is true → the prompt fires).
    Feeds `reply` bytes to stdin. Returns (exit_code, combined_output)."""
    pid, fd = pty.fork()
    if pid == 0:  # child
        os.execvpe(argv[0], argv, env)
    os.write(fd, reply)
    out = b""
    try:
        while True:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            out += chunk
    except OSError:
        pass
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status), out.decode(errors="replace")


# --------------------------------------------------------------------------- #
# Banner is always printed
# --------------------------------------------------------------------------- #
def test_drive_hooks_banner_always_prints(fake_home):
    settings = fake_home / "settings.json"
    proc = run_script([DRIVE_HOOKS, str(settings)], home=fake_home)
    assert proc.returncode == 0
    blob = proc.stdout + proc.stderr
    assert "enforcement hooks" in blob and "SECURITY.md" in blob


def test_op_rules_banner_flags_machine_wide(fake_home):
    proc = run_script([OP_RULES], home=fake_home, env={"DRIVE_INSTALL_ASSUME_YES": "1"})
    assert proc.returncode == 0
    blob = proc.stdout + proc.stderr
    assert "machine-wide installer" in blob and "OVERWRITE ~/CLAUDE.md" in blob


# --------------------------------------------------------------------------- #
# Auto-skip the prompt (non-interactive / assume-yes / explicit arg)
# --------------------------------------------------------------------------- #
def test_drive_hooks_explicit_arg_skips_prompt(fake_home):
    # An explicit $1 target path means no prompt even though stdin is a pipe here.
    settings = fake_home / "settings.json"
    proc = run_script([DRIVE_HOOKS, str(settings)], home=fake_home)
    assert proc.returncode == 0
    assert "Proceed" not in (proc.stdout + proc.stderr)
    assert settings.exists()


def test_op_rules_assume_yes_proceeds(fake_home):
    proc = run_script([OP_RULES], home=fake_home, env={"DRIVE_INSTALL_ASSUME_YES": "1"})
    assert proc.returncode == 0
    assert (fake_home / "CLAUDE.md").exists()  # it wrote the global pointer


def test_op_rules_non_tty_proceeds(fake_home):
    # No TTY (pipe) and no assume-yes → prompt is skipped, install proceeds.
    proc = run_script([OP_RULES], home=fake_home)
    assert proc.returncode == 0
    assert "Proceed" not in (proc.stdout + proc.stderr)
    assert (fake_home / "CLAUDE.md").exists()


# --------------------------------------------------------------------------- #
# Interactive prompt (real pty): decline changes nothing; accept proceeds
# --------------------------------------------------------------------------- #
def test_drive_hooks_interactive_decline_changes_nothing(fake_home):
    settings = fake_home / "dh-decline.json"
    env = dict(os.environ, HOME=str(fake_home), DRIVE_HOOKS_SETTINGS=str(settings))
    env.pop("DRIVE_INSTALL_ASSUME_YES", None)
    # No $1 arg (target via env) so the prompt fires on the pty.
    rc, out = _run_pty(["bash", DRIVE_HOOKS], env, b"n\n")
    assert rc == 1, out
    assert "Aborted" in out
    assert not settings.exists(), "declined install must not create the settings file"


def test_drive_hooks_interactive_accept_proceeds(fake_home):
    settings = fake_home / "dh-accept.json"
    env = dict(os.environ, HOME=str(fake_home), DRIVE_HOOKS_SETTINGS=str(settings))
    env.pop("DRIVE_INSTALL_ASSUME_YES", None)
    rc, out = _run_pty(["bash", DRIVE_HOOKS], env, b"y\n")
    assert rc == 0, out
    assert "Proceed" in out
    assert settings.exists()


def test_op_rules_interactive_decline_changes_nothing(fake_home):
    env = dict(os.environ, HOME=str(fake_home))
    env.pop("DRIVE_INSTALL_ASSUME_YES", None)
    rc, out = _run_pty(["bash", OP_RULES], env, b"n\n")
    assert rc == 1, out
    assert "Aborted" in out
    assert not (fake_home / "CLAUDE.md").exists(), "declined install must not write ~/CLAUDE.md"
