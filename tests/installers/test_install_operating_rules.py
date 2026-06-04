"""AC20 — bin/install-operating-rules.sh.

Subprocess tests (via _helpers.run_script) into a per-test fake HOME. The script
computes its own REPO_DIR from BASH_SOURCE (dirname/..), so it must be invoked by
its real path; run_script's cwd defaults to the repo root, which is fine. We assert
the script's ACTUAL behavior (read from main's bin/install-operating-rules.sh):

  - writes ~/CLAUDE.md containing `@<abs>/OPERATING.md` (REPO_ROOT/OPERATING.md);
  - symlinks every skills/*/ dir -> ~/.claude/skills/<name>;
  - symlinks every .claude/commands/*.md -> ~/.claude/commands/<name>;
  - is idempotent (2nd run leaves valid, non-nested symlinks, exit 0);
  - backs up a pre-existing REAL ~/CLAUDE.md to ~/CLAUDE.md.bak.<ts> exactly once;
  - backs up a pre-existing REAL command target to ~/.claude/command-backups/.

The script also registers a Stop hook in ~/.claude/settings.json; it fails open and
is not part of AC20, so we only require exit 0 (a temp HOME has no settings.json).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _helpers  # noqa: E402

REPO_ROOT = _helpers.REPO_ROOT
SCRIPT = REPO_ROOT / "bin" / "install-operating-rules.sh"
OPERATING = REPO_ROOT / "OPERATING.md"


def _run(home):
    """Invoke the installer by absolute path with HOME = fake_home."""
    return _helpers.run_script([str(SCRIPT)], home=home)


def _skill_names():
    return sorted(p.name for p in (REPO_ROOT / "skills").iterdir() if p.is_dir())


def _command_names():
    return sorted(p.name for p in (REPO_ROOT / ".claude" / "commands").glob("*.md"))


def test_script_exists_and_executable():
    assert SCRIPT.is_file(), f"installer missing at {SCRIPT}"
    assert OPERATING.is_file(), f"OPERATING.md missing at {OPERATING}"


def test_writes_global_claude_md_with_absolute_import(fake_home):
    res = _run(fake_home)
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"

    global_md = fake_home / "CLAUDE.md"
    assert global_md.is_file()
    text = global_md.read_text()
    # The script emits literally `@$OPERATING` where OPERATING is the absolute path.
    expected_import = f"@{OPERATING}"
    assert expected_import in text, f"missing import line {expected_import!r}\n{text}"
    # The import token the script WROTE must be an absolute path (starts with /), not
    # just the test-local constant — parse the `@...` line out of the emitted file.
    import_line = next(ln for ln in text.splitlines() if ln.startswith("@"))
    assert import_line[1:].startswith("/"), f"import path not absolute: {import_line!r}"


def test_symlinks_skills_and_commands(fake_home):
    res = _run(fake_home)
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"

    skills_dst = fake_home / ".claude" / "skills"
    names = _skill_names()
    assert names, "expected at least one skill in repo skills/"
    for name in names:
        link = skills_dst / name
        assert link.is_symlink(), f"{link} should be a symlink"
        assert link.resolve() == (REPO_ROOT / "skills" / name).resolve()

    cmds_dst = fake_home / ".claude" / "commands"
    cnames = _command_names()
    assert cnames, "expected at least one command in repo .claude/commands/"
    for name in cnames:
        link = cmds_dst / name
        assert link.is_symlink(), f"{link} should be a symlink"
        assert link.resolve() == (REPO_ROOT / ".claude" / "commands" / name).resolve()


def test_idempotent_second_run(fake_home):
    first = _run(fake_home)
    assert first.returncode == 0, f"stdout={first.stdout}\nstderr={first.stderr}"
    second = _run(fake_home)
    assert second.returncode == 0, f"stdout={second.stdout}\nstderr={second.stderr}"

    skills_dst = fake_home / ".claude" / "skills"
    for name in _skill_names():
        link = skills_dst / name
        # Still a symlink pointing at the repo dir — NOT a real dir, and the repo
        # dir must NOT have a nested copy created inside it (the `ln -sfn` guard).
        assert link.is_symlink()
        assert link.resolve() == (REPO_ROOT / "skills" / name).resolve()
        nested = REPO_ROOT / "skills" / name / name
        assert not nested.exists(), f"nested dir created inside symlink target: {nested}"

    cmds_dst = fake_home / ".claude" / "commands"
    for name in _command_names():
        link = cmds_dst / name
        assert link.is_symlink()
        assert link.resolve() == (REPO_ROOT / ".claude" / "commands" / name).resolve()

    # No duplicate global file appended; exactly one import line.
    text = (fake_home / "CLAUDE.md").read_text()
    assert text.count(f"@{OPERATING}") == 1

    # Second run found a pre-existing REAL ~/CLAUDE.md (written by run 1) and backs
    # it up. The point of idempotency here: it's still a single valid global file.
    assert (fake_home / "CLAUDE.md").is_file()


def test_backs_up_preexisting_real_global_claude_md(fake_home):
    # Pre-create a REAL ~/CLAUDE.md before the installer runs.
    global_md = fake_home / "CLAUDE.md"
    sentinel = "# pre-existing real CLAUDE.md\nkeep me in a backup\n"
    global_md.write_text(sentinel)

    res = _run(fake_home)
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"

    # Backup naming from the script: "$GLOBAL.bak.$(date +%Y%m%d-%H%M%S)".
    backups = sorted(fake_home.glob("CLAUDE.md.bak.*"))
    assert len(backups) == 1, f"expected exactly one backup, got {backups}"
    assert backups[0].read_text() == sentinel, "backup must preserve original bytes"

    # The live global file was rewritten to the pointer (not the sentinel).
    new_text = global_md.read_text()
    assert new_text != sentinel
    assert f"@{OPERATING}" in new_text


def test_backs_up_preexisting_real_command_target(fake_home):
    # Pre-create a REAL file where a command symlink would go.
    cmds_dst = fake_home / ".claude" / "commands"
    cmds_dst.mkdir(parents=True)
    cnames = _command_names()
    assert cnames
    victim_name = cnames[0]
    victim = cmds_dst / victim_name
    sentinel = "real command file, not a symlink\n"
    victim.write_text(sentinel)

    res = _run(fake_home)
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"

    # The real file is replaced by a symlink to the repo command.
    assert victim.is_symlink()
    assert victim.resolve() == (REPO_ROOT / ".claude" / "commands" / victim_name).resolve()

    # The original real file was moved to ~/.claude/command-backups/ exactly once.
    bk_dir = fake_home / ".claude" / "command-backups"
    backups = sorted(bk_dir.glob(f"{victim_name}.*"))
    assert len(backups) == 1, f"expected one command backup, got {backups}"
    assert backups[0].read_text() == sentinel


def test_backs_up_preexisting_real_skill_target(fake_home):
    # Pre-create a REAL dir (not a symlink) where a skill symlink would go.
    # install-operating-rules.sh:44-47 backs it up to ~/.claude/skill-backups/<name>.<ts>
    # before replacing it with the symlink — analogous to the command-backup branch.
    skills_dst = fake_home / ".claude" / "skills"
    skills_dst.mkdir(parents=True)
    snames = _skill_names()
    assert snames
    victim_name = snames[0]
    victim = skills_dst / victim_name
    victim.mkdir()
    sentinel = "real skill content, not a symlink\n"
    (victim / "SKILL.md").write_text(sentinel)

    res = _run(fake_home)
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"

    # The real dir is replaced by a symlink to the repo skill.
    assert victim.is_symlink()
    assert victim.resolve() == (REPO_ROOT / "skills" / victim_name).resolve()

    # The original real dir was moved to ~/.claude/skill-backups/ exactly once.
    bk_dir = fake_home / ".claude" / "skill-backups"
    backups = sorted(bk_dir.glob(f"{victim_name}.*"))
    assert len(backups) == 1, f"expected one skill backup, got {backups}"
    assert (backups[0] / "SKILL.md").read_text() == sentinel
