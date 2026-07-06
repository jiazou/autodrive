"""C6 contract pins — drive-ship.md's Gate-B commit-trailer directive.

The C6 bug: a model-rename sweep hardcoded `Co-Authored-By: Claude Opus 4.8 <...>`
into drive-ship.md, so every subsequent run's ship commits misattributed their model.
The fix made the trailer a `<model>` substitution directive with an explicit `Claude`
fallback. Nothing else pinned that section (the AC8/AC43 pins cover other drive-ship.md
sections), so a re-hardcode would ship green — these pins close that gap, SECTION-BOUND
to the Gate-B section:

  (a) the literal `Co-Authored-By: <model> <noreply@anthropic.com>` directive line,
  (b) the explicit `Claude` fallback clause (`<model>` unavailable => `Claude`),
  (c) the model-agnostic re-hardcode guard: no command file carries a concrete model
      name on a `Co-Authored-By` LINE. Line-scoped, not a bare repo-wide grep, because
      legitimate prose exists: drive-ship.md's directive itself gives `Claude Fable 5`
      as the e.g. substitution example — a bare `grep -rE "Claude (Opus|Sonnet|Haiku|
      Fable) [0-9]" .claude/commands/` false-positives on it (verified 2026-07-04).

MUTATION-VERIFIED (2026-07-04, phase-1 harden): re-hardcoding the trailer line to
`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` reds (a) AND (c); deleting
the `; if unavailable, use\n`Claude`:` fallback clause reds (b). Restored, all green.
"""
import re

from _helpers import REPO_ROOT

CMDS = REPO_ROOT / ".claude" / "commands"
SHIP_MD = CMDS / "drive-ship.md"

# A concrete Claude model name (family + version number) — the shape a model-rename
# sweep re-hardcodes. Extend the family alternation if a new family name ships.
CONCRETE_MODEL_RE = re.compile(r"Claude (Opus|Sonnet|Haiku|Fable) [0-9]")


def _gate_b_section():
    """drive-ship.md's Gate-B section (from the `## Gate B` header up to the next
    `## ` header). Asserts the header exists so a rename/removal reds loudly."""
    text = SHIP_MD.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("## Gate B")), None)
    assert start is not None, "drive-ship.md `## Gate B` section header not found"
    end = next(
        (j for j in range(start + 1, len(lines)) if lines[j].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def test_gate_b_trailer_is_model_substituted():
    """(a) The commit-trailer directive is the `<model>` placeholder form — the literal
    directive line `Co-Authored-By: <model> <noreply@anthropic.com>` sits in the Gate-B
    section. A sweep that re-hardcodes a concrete model name removes this line and reds."""
    span = _gate_b_section()
    assert "Co-Authored-By: <model> <noreply@anthropic.com>" in span, (
        "drive-ship.md Gate-B commit trailer must be the `<model>` substitution form "
        "(C6: never a hardcoded concrete model name)"
    )


def test_gate_b_trailer_has_claude_fallback():
    """(b) The directive binds `<model>` and states its error path (SKILL.md rule:
    every variable bound, every failure handled): substitute the session's own model
    name; if unavailable, fall back to the literal `Claude`."""
    span = _gate_b_section()
    assert re.search(r"substituting <model>", span), (
        "Gate-B trailer directive must bind <model> (substituting <model> = ...)"
    )
    assert re.search(r"if unavailable, use\s+`Claude`", span), (
        "Gate-B trailer directive must state the explicit `Claude` fallback for an "
        "unknown model identity"
    )


def test_no_hardcoded_model_on_coauthored_by_lines():
    """(c) The model-agnostic re-hardcode guard: NO command file carries a concrete
    model name in a Co-Authored-By context — i.e. on the same line as `Co-Authored-By`.
    This is the exact mechanism that produced C6 (a rename sweep writing the
    then-current model into the trailer); scoped per-line so the directive's own
    legitimate `Claude Fable 5` e.g. prose (a different line) cannot false-positive."""
    offenders = []
    for md in sorted(CMDS.glob("*.md")):
        for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            if "Co-Authored-By" in line and CONCRETE_MODEL_RE.search(line):
                offenders.append(f"{md.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "concrete model name hardcoded in a Co-Authored-By context (C6 regression):\n"
        + "\n".join(offenders)
    )
