"""AC21 — mission-control/install.sh: deploy, idempotency, runtime-data safety.

Drives the REAL installer as a subprocess (via _helpers.run_script) into a fresh
fake HOME and asserts the script's ACTUAL behavior, read off mission-control/install.sh:

  - bin/ and swiftbar-plugins/ are deployed to ~/mission-control as REAL COPIES
    (rm -rf + cp -R), not symlinks.
  - mc + today are symlinked onto ~/.local/bin pointing at the deploy
    (~/mission-control/bin/mc and .../bin/today.py).
  - re-running is idempotent: exit 0, no duplicated entries, stable symlink targets.
  - runtime data (~/mission-control/bindings.jsonl, status.jsonl) is NEVER clobbered
    — the script only `rm -rf`s $DATA/bin and $DATA/swiftbar-plugins, never the
    ledger files that sit directly in $DATA.

launchctl / `defaults write` / `open -a SwiftBar` are guarded (`2>/dev/null || true`)
so they no-op in the sandbox; per design F3 we assert only that the script reaches
exit 0, NOT any launchd / SwiftBar GUI effect. cwd is the worktree root so the script
resolves its own dir ($MC) relative to BASH_SOURCE.

The script reads MC_VAULT / MC_VAULT_NAME from the calling shell (step 1b); we clear
them in the child env so the run is deterministic regardless of the test machine's env.
"""
import os
from pathlib import Path

import pytest

import _helpers

INSTALL_SH = _helpers.REPO_ROOT / "mission-control" / "install.sh"
# Source-of-truth files the script copies from (mission-control/{bin,swiftbar-plugins}).
SRC_BIN = _helpers.REPO_ROOT / "mission-control" / "bin"
SRC_PLUGINS = _helpers.REPO_ROOT / "mission-control" / "swiftbar-plugins"
# Step 2 deploys every dir under mission-control/skills/ to ~/.claude/skills/<name>.
SRC_SKILLS = _helpers.REPO_ROOT / "mission-control" / "skills"

# Env that makes the run deterministic: blank the vault vars step 1b consumes so the
# child neither reads nor writes a $DATA/config from the test machine's shell.
_DETERMINISTIC_ENV = {"MC_VAULT": "", "MC_VAULT_NAME": ""}


def _run_install(home, env=None):
    """Run install.sh once with HOME=home, cwd=repo root (so BASH_SOURCE resolves $MC).

    `env` defaults to the deterministic blanked-vault env; pass an explicit mapping to
    exercise step 1b's MC_VAULT branch (the values override the blanked defaults)."""
    child_env = dict(_DETERMINISTIC_ENV)
    if env:
        child_env.update(env)
    return _helpers.run_script(
        ["bash", str(INSTALL_SH)],
        home=home,
        cwd=_helpers.REPO_ROOT,
        env=child_env,
    )


def _src_skill_names():
    """Names of every dir under mission-control/skills/ (the deploy loop's $MC/skills/*/)."""
    return sorted(p.name for p in SRC_SKILLS.iterdir() if p.is_dir())


def _src_relfiles(src_dir):
    """Relative paths of every regular file under src_dir, excluding __pycache__
    (install.sh rm -rf's $DATA/bin/__pycache__ after copying)."""
    out = set()
    for p in src_dir.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            out.add(p.relative_to(src_dir))
    return out


@pytest.fixture
def installed_home(fake_home):
    """A fake HOME with install.sh run once. Asserts a clean exit so every test
    that builds on it starts from a known-good deploy."""
    r = _run_install(fake_home)
    assert r.returncode == 0, f"install.sh exit {r.returncode}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
    return fake_home


# --------------------------------------------------------------------------- #
# Deploy: copies, not symlinks; CLI symlinks on ~/.local/bin
# --------------------------------------------------------------------------- #
def test_exit_zero(fake_home):
    """Guarded launchctl/defaults/open let the whole script reach exit 0 (F3)."""
    r = _run_install(fake_home)
    assert r.returncode == 0, f"STDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"


def test_bin_deployed_as_real_copies(installed_home):
    """~/mission-control/bin mirrors the repo bin/ as REAL files (cp -R), not symlinks,
    and carries no __pycache__ (script rm -rf's it after the copy)."""
    dest_bin = installed_home / "mission-control" / "bin"
    assert dest_bin.is_dir()

    deployed = _src_relfiles(dest_bin)
    expected = _src_relfiles(SRC_BIN)
    assert deployed == expected, f"deployed bin files != source bin files\nmissing={expected-deployed}\nextra={deployed-expected}"

    for rel in expected:
        f = dest_bin / rel
        assert f.is_file(), f"{rel} not deployed as a file"
        assert not f.is_symlink(), f"{rel} should be a real copy, not a symlink"

    assert not (dest_bin / "__pycache__").exists(), "deployed bin must not carry __pycache__"


def test_swiftbar_plugins_deployed_as_real_copies(installed_home):
    """~/mission-control/swiftbar-plugins is a real copy of the repo plugin dir."""
    dest_plugins = installed_home / "mission-control" / "swiftbar-plugins"
    assert dest_plugins.is_dir()

    deployed = _src_relfiles(dest_plugins)
    expected = _src_relfiles(SRC_PLUGINS)
    assert deployed == expected, f"plugins mismatch missing={expected-deployed} extra={deployed-expected}"

    for rel in expected:
        f = dest_plugins / rel
        assert f.is_file() and not f.is_symlink(), f"{rel} should be a real copied file"


def test_cli_symlinks_point_at_deploy(installed_home):
    """mc + today are symlinked onto ~/.local/bin and point at the DEPLOY
    (~/mission-control/bin/...), not the repo (install.sh lines 46-47)."""
    local_bin = installed_home / ".local" / "bin"
    data_bin = installed_home / "mission-control" / "bin"

    mc_link = local_bin / "mc"
    today_link = local_bin / "today"

    assert mc_link.is_symlink(), "~/.local/bin/mc should be a symlink"
    assert today_link.is_symlink(), "~/.local/bin/today should be a symlink"

    assert os.readlink(mc_link) == str(data_bin / "mc")
    assert os.readlink(today_link) == str(data_bin / "today.py")
    # Targets resolve to existing deployed files.
    assert mc_link.resolve() == (data_bin / "mc").resolve()
    assert today_link.resolve() == (data_bin / "today.py").resolve()


# --------------------------------------------------------------------------- #
# Idempotency: second run is clean, no duplication, stable targets
# --------------------------------------------------------------------------- #
def test_second_run_idempotent(installed_home):
    """A second install.sh exits 0, leaves identical deployed-file sets, and keeps
    the SAME symlink targets (no nested/duplicated links)."""
    data_bin = installed_home / "mission-control" / "bin"
    local_bin = installed_home / ".local" / "bin"

    bin_before = _src_relfiles(data_bin)
    mc_target_before = os.readlink(local_bin / "mc")
    today_target_before = os.readlink(local_bin / "today")

    r2 = _run_install(installed_home)
    assert r2.returncode == 0, f"2nd run exit {r2.returncode}\nSTDERR:\n{r2.stderr}"

    # Same file set, still real copies, still no pycache.
    assert _src_relfiles(data_bin) == bin_before
    assert not (data_bin / "__pycache__").exists()

    # Symlinks unchanged: still exactly one each, same target, not a link-to-a-link.
    assert os.readlink(local_bin / "mc") == mc_target_before
    assert os.readlink(local_bin / "today") == today_target_before
    assert (local_bin / "mc").resolve() == (data_bin / "mc").resolve()
    assert (local_bin / "today").resolve() == (data_bin / "today.py").resolve()
    # No accidental extra CLI entries beyond mc + today.
    assert sorted(p.name for p in local_bin.iterdir()) == ["mc", "today"]


# --------------------------------------------------------------------------- #
# Runtime-data safety: ledgers in ~/mission-control are never clobbered
# --------------------------------------------------------------------------- #
def test_runtime_ledgers_preserved(fake_home):
    """bindings.jsonl + status.jsonl (live runtime data in $DATA) survive install
    BYTE-FOR-BYTE — the script only rm -rf's $DATA/bin + $DATA/swiftbar-plugins."""
    data = fake_home / "mission-control"
    data.mkdir(parents=True)
    bindings = data / "bindings.jsonl"
    status = data / "status.jsonl"
    sentinel_b = '{"event":"bind","session_id":"keepme"}\n'
    sentinel_s = '{"session_id":"keepme","status":"active"}\n'
    bindings.write_text(sentinel_b, encoding="utf-8")
    status.write_text(sentinel_s, encoding="utf-8")

    r = _run_install(fake_home)
    assert r.returncode == 0, f"STDERR:\n{r.stderr}"

    assert bindings.read_text(encoding="utf-8") == sentinel_b, "bindings.jsonl was clobbered"
    assert status.read_text(encoding="utf-8") == sentinel_s, "status.jsonl was clobbered"


def test_runtime_ledgers_preserved_across_reinstall(fake_home):
    """Ledgers survive a SECOND install too (idempotent reinstall path)."""
    data = fake_home / "mission-control"
    data.mkdir(parents=True)
    bindings = data / "bindings.jsonl"
    sentinel = '{"event":"bind","session_id":"survivor","ts":1}\n'
    bindings.write_text(sentinel, encoding="utf-8")

    assert _run_install(fake_home).returncode == 0
    assert _run_install(fake_home).returncode == 0
    assert bindings.read_text(encoding="utf-8") == sentinel


# --------------------------------------------------------------------------- #
# Step 2: skills deployed to ~/.claude/skills/<name> as REAL copies (install.sh:36-42)
# --------------------------------------------------------------------------- #
def test_skills_deployed_as_real_copies(installed_home):
    """install.sh:38-41 loops every $MC/skills/*/ dir and `cp -R`s it to
    ~/.claude/skills/<name> — a REAL copy (not a symlink) mirroring the source file
    set. Regresses if the loop is dropped, uses a symlink, or copies to the wrong dest."""
    skills_dst = installed_home / ".claude" / "skills"
    names = _src_skill_names()
    assert names, "expected at least one skill under mission-control/skills/"

    for name in names:
        dest = skills_dst / name
        assert dest.is_dir(), f"skill {name} not deployed to {dest}"
        assert not dest.is_symlink(), f"skill {name} should be a real copy, not a symlink"

        deployed = _src_relfiles(dest)
        expected = _src_relfiles(SRC_SKILLS / name)
        assert deployed == expected, (
            f"skill {name} file set mismatch missing={expected-deployed} extra={deployed-expected}"
        )
        for rel in expected:
            f = dest / rel
            assert f.is_file() and not f.is_symlink(), f"{name}/{rel} should be a real copied file"


def test_skills_redeploy_refreshes_stale_content(installed_home):
    """install.sh `rm -rf`s ~/.claude/skills/<name> before each `cp -R`, so a reinstall
    REPLACES the deploy: stale files vanish and tampered files are restored byte-for-byte.
    Regresses if the rm-rf is dropped (stale file would survive) or the copy is skipped."""
    skills_dst = installed_home / ".claude" / "skills"
    name = _src_skill_names()[0]
    dest = skills_dst / name

    # 1) Drop a stale file the source does NOT have, and tamper an existing one.
    stale = dest / "STALE_DELETE_ME.txt"
    stale.write_text("orphan from a previous deploy\n", encoding="utf-8")
    canonical = next(iter(_src_relfiles(SRC_SKILLS / name)))
    (dest / canonical).write_text("TAMPERED — should be overwritten\n", encoding="utf-8")

    r2 = _run_install(installed_home)
    assert r2.returncode == 0, f"reinstall exit {r2.returncode}\nSTDERR:\n{r2.stderr}"

    # Stale file gone (rm -rf), file set back to source, tampered file restored.
    assert not stale.exists(), "rm -rf must drop stale files on reinstall"
    assert _src_relfiles(dest) == _src_relfiles(SRC_SKILLS / name)
    assert (dest / canonical).read_text(encoding="utf-8") == \
        (SRC_SKILLS / name / canonical).read_text(encoding="utf-8"), \
        "tampered skill file must be restored from source"


# --------------------------------------------------------------------------- #
# Step 1b: ~/mission-control/config written from MC_VAULT / kept when present
# --------------------------------------------------------------------------- #
def test_config_written_from_mc_vault(fake_home):
    """With MC_VAULT (and MC_VAULT_NAME) set, step 1b writes ~/mission-control/config
    with the captured values (install.sh:25-29). Regresses if the write branch is lost."""
    r = _run_install(
        fake_home,
        env={"MC_VAULT": "/some/Vault", "MC_VAULT_NAME": "MyVault"},
    )
    assert r.returncode == 0, f"STDERR:\n{r.stderr}"

    cfg = fake_home / "mission-control" / "config"
    assert cfg.is_file(), "config should be written when MC_VAULT is set"
    text = cfg.read_text(encoding="utf-8")
    assert "MC_VAULT=/some/Vault" in text
    assert "MC_VAULT_NAME=MyVault" in text


def test_existing_config_kept_when_vault_unset(fake_home):
    """With MC_VAULT/MC_VAULT_NAME unset, an EXISTING ~/mission-control/config is kept
    byte-for-byte, not overwritten (install.sh:30-31, the `elif [ -f "$CFG" ]` branch)."""
    data = fake_home / "mission-control"
    data.mkdir(parents=True)
    cfg = data / "config"
    sentinel = "MC_VAULT=/preexisting/Vault\nMC_VAULT_NAME=Kept\n"
    cfg.write_text(sentinel, encoding="utf-8")

    # _DETERMINISTIC_ENV blanks both vault vars -> the keep-existing branch.
    r = _run_install(fake_home)
    assert r.returncode == 0, f"STDERR:\n{r.stderr}"

    assert cfg.read_text(encoding="utf-8") == sentinel, "existing config must not be overwritten"
