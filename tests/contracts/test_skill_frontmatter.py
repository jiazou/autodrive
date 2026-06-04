"""AC27 — skill SKILL.md frontmatter contract.

Every `SKILL.md` in the repo (under `skills/<dir>/` AND
`mission-control/skills/<dir>/`) must open with a `---`-fenced YAML frontmatter
block that PARSES AS REAL YAML, carries the required keys (`name`,
`description`), and whose `name` equals the containing directory name.

We parse the frontmatter with PyYAML (`yaml.safe_load`) — the same real parser
Claude Code uses to read skill frontmatter. This is load-bearing for two reasons:
  (a) a malformed block raises -> the test fails (true validation, not a scrape);
  (b) `description: |` block scalars are resolved to their real body text, so the
      non-empty check sees the actual prose, not the literal "|".
A negative test feeds a deliberately MALFORMED block to the SAME validator and
asserts it is rejected — proving the guard actually bites.
"""
import pytest

# PyYAML is a hard dependency of this contract (it IS installed). importorskip
# turns a missing-yaml environment into a clean SKIP rather than a collection error.
yaml = pytest.importorskip("yaml")

from _helpers import REPO_ROOT


def _skill_md_files():
    """Discover EVERY SKILL.md shipped in the repo, regardless of location, so a
    future move of skills can't silently shrink coverage. We rglob the whole repo
    (excluding .git) — this captures both `skills/<dir>/SKILL.md` and
    `mission-control/skills/<dir>/SKILL.md`."""
    return sorted(
        p
        for p in REPO_ROOT.rglob("SKILL.md")
        if ".git" not in p.parts
    )


def _extract_frontmatter(text):
    """Return the text inside the leading `---`-fenced block, or None if the file
    does not open with a frontmatter fence. The opening `---` must be the first
    non-empty line; the block ends at the next line that is exactly `---`."""
    lines = text.splitlines()
    # Find the opening fence (first non-blank line must be the fence).
    idx = 0
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx >= len(lines) or lines[idx].strip() != "---":
        return None
    start = idx + 1
    for end in range(start, len(lines)):
        if lines[end].strip() == "---":
            return "\n".join(lines[start:end])
    return None  # no closing fence


def _parse_frontmatter(block):
    """Parse a frontmatter block as YAML and return the mapping. Raises
    yaml.YAMLError on a malformed block; asserts the top level is a mapping."""
    data = yaml.safe_load(block)
    assert isinstance(data, dict), (
        f"frontmatter did not parse to a mapping (got {type(data).__name__})"
    )
    return data


SKILL_FILES = _skill_md_files()

# Stable, unique parametrize ids: <location>/<skill-dir> relative to the repo root,
# so two skills sharing a dir name across locations never collide.
SKILL_IDS = [str(p.parent.relative_to(REPO_ROOT)) for p in SKILL_FILES]


def test_repo_has_skill_files():
    """Non-vacuous guard: the repo must ship multiple SKILL.md files AND both
    discovery locations (`skills/` and `mission-control/skills/`) must be
    represented — so a future move can't silently shrink coverage to zero or to a
    single location (which would let real skills go unvalidated)."""
    assert len(SKILL_FILES) >= 2, (
        f"expected >=2 SKILL.md across the repo, found {len(SKILL_FILES)}: "
        f"{[str(p) for p in SKILL_FILES]}"
    )
    rels = [str(p.relative_to(REPO_ROOT)) for p in SKILL_FILES]
    from_skills = [r for r in rels if r.startswith("skills/")]
    from_mc = [r for r in rels if r.startswith("mission-control/skills/")]
    assert from_skills, f"no SKILL.md under skills/ (found: {rels})"
    assert from_mc, f"no SKILL.md under mission-control/skills/ (found: {rels})"


def test_skill_md_discovery_count():
    """Pin the discovered count so a regression that drops a skill (or a glob that
    over-matches) is caught explicitly. The repo currently ships 5 SKILL.md:
    skills/decant + mission-control/skills/{harvest,mc,standup,weekly}."""
    assert len(SKILL_FILES) == 5, (
        f"expected 5 SKILL.md, discovered {len(SKILL_FILES)}: "
        f"{[str(p.relative_to(REPO_ROOT)) for p in SKILL_FILES]}"
    )


@pytest.mark.parametrize(
    "skill_md", SKILL_FILES, ids=SKILL_IDS
)
def test_skill_frontmatter_parses(skill_md):
    """The block is present AND valid YAML (a malformed block raises here)."""
    text = skill_md.read_text(encoding="utf-8")
    block = _extract_frontmatter(text)
    assert block is not None, f"{skill_md} has no ---fenced frontmatter block"
    _parse_frontmatter(block)  # raises -> test fails on malformed YAML


@pytest.mark.parametrize(
    "skill_md", SKILL_FILES, ids=SKILL_IDS
)
def test_skill_frontmatter_required_keys(skill_md):
    block = _extract_frontmatter(skill_md.read_text(encoding="utf-8"))
    data = _parse_frontmatter(block)
    for required in ("name", "description"):
        assert required in data, f"{skill_md} frontmatter missing `{required}`"
    # `description: |` block scalars resolve to their real body text here, so this
    # asserts genuine non-empty prose — not the literal "|".
    description = data["description"]
    assert isinstance(description, str) and description.strip(), (
        f"{skill_md} `description` is empty (resolved value: {description!r})"
    )


@pytest.mark.parametrize(
    "skill_md", SKILL_FILES, ids=SKILL_IDS
)
def test_skill_name_matches_dir(skill_md):
    data = _parse_frontmatter(_extract_frontmatter(skill_md.read_text(encoding="utf-8")))
    dir_name = skill_md.parent.name
    assert data.get("name") == dir_name, (
        f"{skill_md} frontmatter name={data.get('name')!r} "
        f"does not match dir {dir_name!r}"
    )


def test_malformed_frontmatter_is_rejected():
    """Negative guard: a deliberately broken frontmatter block must FAIL the same
    validator the real skills pass — proving the YAML check actually bites (not a
    line scrape that would silently accept garbage)."""
    bad = "name: x\ndescription: [unterminated\n  : : :\n"
    with pytest.raises(yaml.YAMLError):
        _parse_frontmatter(bad)


def test_block_scalar_description_resolves_to_body(tmp_path):
    """A `description: |` block scalar must resolve to its real body text, never the
    literal '|'. This is exactly the shape decant/SKILL.md ships, written here via
    tmp_path so the guard holds independent of which skills exist on disk."""
    skill = tmp_path / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\n"
        "name: demo\n"
        "description: |\n"
        "  Real multi-line body text.\n"
        "  Second line.\n"
        "---\n"
        "# body\n",
        encoding="utf-8",
    )
    data = _parse_frontmatter(_extract_frontmatter(skill.read_text(encoding="utf-8")))
    assert data["description"].strip() != "|"
    assert "Real multi-line body text." in data["description"]
