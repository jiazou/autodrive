"""AC26 — every /drive-* command referenced in .claude/commands/drive.md exists.

drive.md is the coordinator and names its stage runners as slash commands
(`/drive-plan`, `/drive-implement`, `/drive-review`, `/drive-harden`, `/drive-ship`).
Each such reference must have a backing `.claude/commands/<name>.md` file, or the
command is undiscoverable. This is data-driven: it DISCOVERS the referenced names
from drive.md (so a newly-referenced-but-missing command fails) rather than
hardcoding the set.
"""
import re

import pytest

from _helpers import REPO_ROOT

# Every `/drive` command file (the coordinator + its stage runners). Claude Code parses
# each file's YAML frontmatter to register the slash command; a missing or empty
# `description:` silently breaks discovery — so guard the structure of all of them.
_CMD_FILES = sorted((REPO_ROOT / ".claude" / "commands").glob("drive*.md"))
_CMD_IDS = [p.name for p in _CMD_FILES]


# A genuine `/drive-<word>` SLASH-COMMAND reference. The leading `/` must NOT be
# preceded by a word char or another path separator, so this matches real command
# tokens (`/drive-review phase ...`, `` `/drive-plan` ``) but NOT a `/drive-*`
# substring buried inside a file path such as `bin/drive-conformance.sh` (where the
# `/` is preceded by the word char `n`) — that is a bin script, not a slash command,
# and has no `.claude/commands/*.md` backing by design. `[a-z]+` (no `-`) stops at
# the first non-letter; bare `/drive` (no trailing `-word`) and the non-slash prose
# path `drive-stop-hook.py` are excluded too.
_DRIVE_REF = re.compile(r"(?<![\w/])/drive-[a-z]+")


def _referenced_drive_commands(text):
    """Sorted unique `drive-*` command names referenced as `/drive-*` in `text`."""
    return sorted({m.lstrip("/") for m in _DRIVE_REF.findall(text)})


def _load_referenced(repo_root):
    drive_md = repo_root / ".claude" / "commands" / "drive.md"
    assert drive_md.is_file(), f"drive.md missing at {drive_md}"
    return _referenced_drive_commands(drive_md.read_text(encoding="utf-8"))


def test_drive_md_references_the_stage_runners(repo_root):
    """Sanity: drive.md actually names a non-empty set of stage runners, including
    the six known ones — so the data-driven check below has real inputs.
    `drive-design` (the per-phase detailed-design step) is pinned here so a
    regression that drops it from the pipeline is caught."""
    names = _load_referenced(repo_root)
    assert names, "drive.md references no /drive-* commands — regex or file changed"
    for expected in (
        "drive-plan",
        "drive-design",
        "drive-implement",
        "drive-review",
        "drive-harden",
        "drive-ship",
    ):
        assert expected in names, (
            f"expected drive.md to reference /{expected}; found {names}"
        )


def test_each_referenced_drive_command_has_a_file(repo_root):
    """Every /drive-* referenced in drive.md has a backing command file in the repo."""
    names = _load_referenced(repo_root)
    cmds_dir = repo_root / ".claude" / "commands"
    missing = [n for n in names if not (cmds_dir / f"{n}.md").is_file()]
    assert not missing, (
        f"drive.md references {missing} but no {cmds_dir}/<name>.md exists for them"
    )


def test_drive_command_files_discovered():
    """Sanity: the glob found the command files — so the frontmatter check has inputs."""
    assert _CMD_FILES, "no .claude/commands/drive*.md files discovered"


@pytest.mark.parametrize("cmd_md", _CMD_FILES, ids=_CMD_IDS)
def test_drive_command_has_frontmatter_description(cmd_md):
    """Every /drive command file opens with a `---` YAML frontmatter block containing a
    non-empty `description:`. Claude Code parses this to register the slash command, so a
    malformed/empty block silently breaks discovery (e.g. a new stage runner like
    drive-design.md). A line-scan suffices — command frontmatter is plain `key: value`."""
    lines = cmd_md.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0].strip() == "---", (
        f"{cmd_md.name} must open with a `---` frontmatter fence"
    )
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    assert end is not None, f"{cmd_md.name} frontmatter block is not closed with `---`"
    desc = next((ln for ln in lines[1:end] if ln.startswith("description:")), None)
    assert desc is not None, f"{cmd_md.name} frontmatter has no `description:` key"
    assert desc[len("description:"):].strip(), f"{cmd_md.name} `description:` is empty"
