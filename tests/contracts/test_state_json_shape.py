"""AC28 — state.json soft contract.

Two artifacts describe the run-model `state.json`:
  - .claude/commands/drive.md ships an example as a ```json fenced block.
  - CLAUDE.md ("Run state & shared memory") describes it in prose, enumerating
    the top-level run-model keys.

This is a SOFT contract (decisions D9/D11): we do NOT require the example to be a
strict subset of the prose (or vice versa) — drive.md carries extra operational
keys (task, stage, designReview, sessionId, ...) and CLAUDE.md names only the
load-bearing run-model fields. We assert:
  (a) the drive.md example parses as valid JSON, and
  (b) the verified CORE key set is present in BOTH the drive.md JSON top-level keys
      AND the CLAUDE.md description — a drop of ANY core key from EITHER fails.

CORE_KEYS is the FULL verified intersection, computed from main's actual files in
THIS worktree (re-verified after the quality pass added `stage` to CLAUDE.md):
  - drive.md JSON top-level keys: runId, task, stage, baseRef, featureBranch,
    phase, phaseBaseSha, concurrencyCap, designReview, budget, slices,
    phaseReview, lastGate, sessionId, autoContinue, waiting, designPath.
  - CLAUDE.md enumerates (top-level): runId, baseRef, featureBranch, stage, phase,
    phaseBaseSha, concurrencyCap, budget, phaseReview.
    (It writes "per-slice {...}" — the prose word, NOT the JSON key `slices` — so
    `slices` is in drive.md ONLY and is deliberately NOT a core key.)
  - Intersection = the 9 keys below. `stage` is now a documented top-level run-model
    key in BOTH artifacts, so it joins CORE (asserted explicitly below).
"""
import json
import re

from _helpers import REPO_ROOT

CORE_KEYS = {
    "runId",
    "baseRef",
    "featureBranch",
    "stage",
    "phase",
    "phaseBaseSha",
    "concurrencyCap",
    "budget",
    "phaseReview",
}

_JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def _drive_md_json():
    """Parse the first ```json fenced block from drive.md and return (raw, obj)."""
    text = (REPO_ROOT / ".claude" / "commands" / "drive.md").read_text(encoding="utf-8")
    m = _JSON_FENCE_RE.search(text)
    assert m, "no ```json fenced block found in .claude/commands/drive.md"
    raw = m.group(1)
    return raw, json.loads(raw)


def _claude_md_state_keys():
    """Extract the candidate top-level key names CLAUDE.md's state.json description
    enumerates.

    The description begins on the `state.json -- run model: ...` line and continues
    on the indented continuation lines until the next ledger entry (`event-log.jsonl
    ...`). We scan that span for whole-word identifiers. We collect a candidate name
    set and intersect with CORE_KEYS, so unrelated words (run, model, per, slice,
    status) never produce false positives.
    """
    text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if ln.lstrip().startswith("state.json")), None)
    assert start is not None, "CLAUDE.md has no `state.json` description line"
    span = [lines[start]]
    for ln in lines[start + 1:]:
        # Continuation lines are indented; the next ledger entry starts at column 0.
        if ln[:1].strip() and not ln.startswith(" "):
            break
        span.append(ln)
    blob = "\n".join(span)
    return set(re.findall(r"[A-Za-z][A-Za-z0-9]*", blob))


def test_drive_md_example_is_valid_json():
    _, obj = _drive_md_json()
    assert isinstance(obj, dict), "drive.md example state.json is not a JSON object"


def test_core_keys_present_in_drive_md():
    _, obj = _drive_md_json()
    missing = CORE_KEYS - set(obj.keys())
    assert not missing, f"drive.md example state.json missing core keys: {missing}"


def test_core_keys_present_in_claude_md_description():
    names = _claude_md_state_keys()
    missing = CORE_KEYS - names
    assert not missing, (
        f"CLAUDE.md state.json description does not enumerate core keys: {missing}"
    )


def test_stage_documented_in_both():
    """`stage` is a real top-level run-model key and is now documented in BOTH
    artifacts. Guard that it stays so: it must appear in drive.md's JSON, in
    CLAUDE.md's state.json key set, AND in CORE_KEYS. This FAILS (not a tautology)
    if a future edit drops `stage` from EITHER doc — exactly the regression the
    CORE machinery should catch for a load-bearing key."""
    _, obj = _drive_md_json()
    claude_names = _claude_md_state_keys()
    assert "stage" in obj, "expected drive.md example to carry a top-level `stage`"
    assert "stage" in claude_names, (
        "CLAUDE.md no longer documents `stage` in its state.json description — "
        "it is a real top-level run-model key and must be documented in both"
    )
    assert "stage" in CORE_KEYS
