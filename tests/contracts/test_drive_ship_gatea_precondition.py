"""RL-1 — drive-ship.md precondition #1 derives "Gate A passed" from the actor-independent
artifact chain when the droppable `lastGate` scalar is null, instead of hard-STOPping.

Guards guard-repoint D-9: a Gate-A write can leave `lastGate` null while `stage`/`phaseList`
persist, false-blocking a legitimately-approved run at ship. The LOAD-BEARING derived signal
is `phaseList` NON-EMPTY **AND** `stage` ∈ {execute,finalize,verify,ship} — a CONJUNCTION whose
sole writer is the post-human-approval Gate-A transition.

Pin history / why the conjunction + exact-set assertions exist: an earlier version searched
for the words `phaseList`, `non-empty`, `execute` SEPARATELY, and codex proved an `AND→OR`
mutation stayed green — a real bypass letting `{lastGate:null, phaseList:[], stage:execute}`
(a not-approved / malformed state) derive Gate-A-passed. That vacuity is closed here and
mutation-verified (test/drive-ship-gatea-mutation.test.sh drives the AND→OR and stage-set
mutations and asserts these tests RED).

Imprecision budget (STATED): these are PROSE pins over a coordinator-followed spec — best-effort
by nature. They catch the load-bearing WHOLE-CLAUSE regressions (AND→OR, an altered stage set, a
dropped negative case, a dropped corroborator) but cannot prove the coordinator EXECUTES the
prose. The robust follow-up is to move the derivation into an executable check with table-tested
inputs→outputs (RL-1b, .harness/followups.md). The runtime guards that stay load-bearing
regardless: the resume matrix fails closed on BOTH malformed {phaseList × stage} corners
(drive.md § Run setup & resume), and every ship goes through a dual-voice review + Gate B.

Sibling of the memory `drive-ship-lastgate-null-repair-from-artifacts`.
"""
import os
import re
from pathlib import Path

from _helpers import REPO_ROOT

# The mutation-verify bash test (test/drive-ship-gatea-mutation.test.sh) points this at a
# MUTATED copy of drive-ship.md to prove these pins RED on the AND→OR / stage-set bypasses.
SHIP_MD = Path(os.environ.get(
    "DRIVE_SHIP_MD_OVERRIDE", str(REPO_ROOT / ".claude" / "commands" / "drive-ship.md")))


def _preconditions_section():
    text = SHIP_MD.read_text(encoding="utf-8")
    m = re.search(r"^## Preconditions.*?(?=^## )", text, re.S | re.M)
    assert m, "drive-ship.md must have a '## Preconditions' section"
    return m.group(0)


def _precondition_1():
    """Item #1 (Gate A passed) — section-bound from its '1. **Gate A passed' opener to '2. **'."""
    sec = _preconditions_section()
    m = re.search(r"^1\. \*\*Gate A passed.*?(?=^2\. \*\*)", sec, re.S | re.M)
    assert m, "precondition #1 (Gate A passed) not found in ## Preconditions"
    return m.group(0)


def _clause_a():
    """The load-bearing bullet (a) — from its `[load-bearing]` marker to the `(b)` clause."""
    m = re.search(r"\[load-bearing\].*?(?=\(b\))", _precondition_1(), re.S)
    assert m, "precondition #1 must have a `[load-bearing]` clause (a) before clause (b)"
    return m.group(0)


def test_gatea_fast_path_preserved():
    """The fast path stays: `lastGate == "A"` still satisfies precondition #1 (backward-compat)."""
    assert 'lastGate == "A"' in _precondition_1(), \
        'precondition #1 must keep the `lastGate == "A"` fast path'


def test_gatea_handles_null_lastgate():
    """precondition #1 handles the dropped/null lastGate case (does not hard-require the scalar)."""
    low = _precondition_1().lower()
    assert re.search(r"\b(null|absent)\b", low), \
        "precondition #1 must cover the dropped/null `lastGate` case, not hard-require the scalar"


def test_gatea_load_bearing_is_phaselist_stage_conjunction():
    """The load-bearing derived signal is `phaseList` NON-EMPTY **AND** `stage` in the allowed
    set — a CONJUNCTION. Pins against the AND→OR bypass: with OR, {phaseList:[], stage:execute}
    would derive Gate-A-passed for a not-approved/malformed state."""
    low = _clause_a().lower()
    assert "phaselist" in low and re.search(r"non-?empty", low), \
        "clause (a) must require a NON-EMPTY phaseList"
    seg = re.search(r"non-?empty(.{0,50}?)stage", low)
    assert seg, "clause (a) must relate the non-empty phaseList to the stage"
    link = seg.group(1)
    assert re.search(r"\band\b", link) and not re.search(r"\bor\b", link), \
        "clause (a) must CONJOIN (AND) a non-empty phaseList with stage — NEVER OR " \
        "(OR lets {phaseList:[], stage:execute} bypass Gate A)"


def test_gatea_exact_allowed_stage_set():
    """The allowed stage set is EXACTLY {execute, finalize, verify, ship} — pins against widening
    it (e.g. adding `plan`/`premises`, which would accept a pre-approval run)."""
    m = re.search(r"stage[^{]*\{([^}]*)\}", _clause_a())
    assert m, "clause (a) must name the allowed stage set in braces"
    allowed = {s.strip().strip("`").lower() for s in m.group(1).split(",") if s.strip()}
    assert allowed == {"execute", "finalize", "verify", "ship"}, \
        f"allowed stage set must be EXACTLY execute/finalize/verify/ship (guards plan/premises " \
        f"being added as accepted); got {allowed}"


def test_gatea_both_negative_cases_stop():
    """Both pre-approval corners must be named as NOT passing — an empty phaseList AND a
    pre-Execute stage — and a terminal STOP must exist."""
    low = _precondition_1().lower()
    assert re.search(r"empty\s+`?phaselist", low), "must state an EMPTY phaseList does NOT pass"
    assert re.search(r"pre-execute\s+`?stage", low), "must state a pre-Execute stage does NOT pass"
    assert "stop" in low, \
        "precondition #1 must STOP when neither the fast path nor a sound derivation holds"


def test_gatea_corroboration_requires_all_of_abc():
    """(b)/(c) corroborate — the derivation requires the CONVERGED high-level design + its
    codex sibling AND precondition #2 (hardened); a review file is never sufficient ALONE.
    Crucially the clauses AGGREGATE with ALL, never ANY: under ANY, clause (b) alone — a
    converged design, which legitimately exists PRE-approval — would derive Gate-A-passed."""
    low = _precondition_1().lower()
    assert "converged" in low and "codex-review-design" in low, \
        "(b) must require the CONVERGED high-level design + its non-empty codex sibling"
    assert "hardened" in low, "(c) must require precondition #2 (every phase hardened)"
    assert re.search(r"review\s+file\s+alone", low), \
        "a converged design (review file) must NOT be sufficient ALONE to prove Gate A"
    # AGGREGATION connective: require ALL of (a)/(b)/(c), never ANY (pins the ALL→ANY bypass)
    assert re.search(r"requiring\s+all\s+of", low) and not re.search(r"requiring\s+any\s+of", low), \
        "the derivation must require ALL of (a)/(b)/(c) — never ANY (clause (b) alone can exist pre-approval)"


def test_gatea_derivation_repairs_logs_surfaces():
    """A DERIVED pass repairs lastGate, logs the derivation (recording a fact, not a forge),
    and surfaces at Gate B."""
    p1 = _precondition_1()
    low = p1.lower()
    assert "repair" in low and re.search(r'lastgate\s*=\s*"a"', low), \
        'a derived pass must REPAIR `state.lastGate = "A"` (single `=`, distinct from the `==` fast path)'
    assert "decisions.md" in p1, "the derivation must be LOGGED to $RUN_DIR/decisions.md"
    assert "gate b" in low, "the derivation must be SURFACED at Gate B"
    assert re.search(r"not a forge|not.*\bforge", low), \
        "the repair must be framed as recording an established fact, NOT a forge"
