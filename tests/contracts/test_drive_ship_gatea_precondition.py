"""RL-1 — drive-ship.md precondition #1 derives "Gate A passed" from the actor-independent
artifact chain when the droppable `lastGate` scalar is null, instead of hard-STOPping.

Guards guard-repoint D-9: the Gate-A atomic write can persist `stage`/`phaseList` but DROP
the `lastGate` field, leaving a legitimately-approved run false-blocked at ship. The
LOAD-BEARING derived signal is a NON-EMPTY `phaseList` at stage>=execute — the Gate-A
transition is its sole writer and runs only post-human-approval — NOT the converged design
alone. Each assertion below reds against the pre-RL-1 precondition (`lastGate == "A"` +
"Do NOT infer it from a review file existing"), so the pin is non-vacuous.

Sibling of the memory `drive-ship-lastgate-null-repair-from-artifacts`.
"""
import re

from _helpers import REPO_ROOT

SHIP_MD = REPO_ROOT / ".claude" / "commands" / "drive-ship.md"


def _preconditions_section():
    text = SHIP_MD.read_text(encoding="utf-8")
    m = re.search(r"^## Preconditions.*?(?=^## )", text, re.S | re.M)
    assert m, "drive-ship.md must have a '## Preconditions' section"
    return m.group(0)


def _precondition_1():
    """Item #1 (Gate A passed) — from its '1. **Gate A passed' opener up to item '2. **',
    section-bound so a match elsewhere can't make an assertion vacuous."""
    sec = _preconditions_section()
    m = re.search(r"^1\. \*\*Gate A passed.*?(?=^2\. \*\*)", sec, re.S | re.M)
    assert m, "precondition #1 (Gate A passed) not found in ## Preconditions"
    return m.group(0)


def test_gatea_fast_path_preserved():
    """The fast path stays: `lastGate == "A"` still satisfies precondition #1."""
    assert 'lastGate == "A"' in _precondition_1(), \
        'precondition #1 must keep the `lastGate == "A"` fast path'


def test_gatea_derives_from_phaselist_when_lastgate_null():
    """When lastGate is null/absent, Gate A is DERIVED — and the load-bearing signal is a
    NON-EMPTY phaseList at stage>=execute, not the converged design alone."""
    p1 = _precondition_1()
    low = p1.lower()
    # 1) the dropped/null lastGate case is HANDLED (not hard-required)
    assert re.search(r"\b(null|absent)\b", low), \
        "precondition #1 must cover the dropped/null `lastGate` case, not hard-require the scalar"
    # 2) the LOAD-BEARING derived signal: a non-empty phaseList ...
    assert "phaseList" in p1 and re.search(r"non-?empty", low), \
        "the derived Gate-A signal must be a NON-EMPTY phaseList (its sole writer is the Gate-A transition)"
    # 3) ... at stage >= execute (a pre-Execute stage means the transition never ran)
    assert "execute" in low, \
        "the derived signal must require stage>=execute"
    # 4) the phaseList's sole-writer / post-approval rationale is stated (why it is sound)
    assert re.search(r"sole writer", low), \
        "must state WHY phaseList is load-bearing: the Gate-A transition is its SOLE writer (post-approval)"


def test_gatea_design_corroborates_not_sufficient_alone():
    """A converged design must CORROBORATE only — never prove Gate A alone (preserves the
    original 'do not infer from a review file' spirit under the new derivation)."""
    p1 = _precondition_1()
    assert re.search(r"review\s+file\s+alone", p1, re.I), \
        "a converged design (review file) must NOT be sufficient ALONE to prove Gate A"


def test_gatea_derivation_repairs_logs_surfaces_or_stops():
    """A DERIVED pass repairs lastGate, logs the derivation (framed as recording a fact, not
    a forge), and surfaces at Gate B; neither fast-path nor sound derivation STOPs."""
    p1 = _precondition_1()
    low = p1.lower()
    assert "repair" in low and re.search(r'lastgate\s*=\s*"a"', low), \
        'a derived pass must REPAIR `state.lastGate = "A"` (single `=`, distinct from the `==` fast path)'
    assert "decisions.md" in p1, "the derivation must be LOGGED to $RUN_DIR/decisions.md"
    assert "gate b" in low, "the derivation must be SURFACED at Gate B"
    assert re.search(r"not a forge|not.*\bforge", low), \
        "the repair must be framed as recording an established fact, NOT a forge"
    assert "stop" in low, \
        "neither the fast path NOR a sound derivation must STOP (Gate A not provable)"
