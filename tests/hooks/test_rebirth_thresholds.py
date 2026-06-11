"""AC6 — single source of truth, no drift between bash and python.

Pins the python `rebirth_thresholds` resolver (the hook's classifier path) against:
  - the window-by-model resolution for display-name + model-id + default forms,
  - the hard/soft byte thresholds,
  - the canonical latest-assistant token sum on the over/under-water fixtures,
and the ANTI-DRIFT cross-checks that key the python numbers off the SAME upstream
sources bash uses:
  - the window for the bash display-name forms is whatever `bin/statusline.sh`'s own
    inline `case` resolves (read statusline.sh, run its case, assert equality);
  - the canonical token sum equals statusline.sh's own jq filter run over the fixture.
A drift between the json table and statusline reds the suite.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import _helpers  # noqa: E402  (tests/ on sys.path via conftest)

# bin/ on sys.path so `import rebirth_thresholds` resolves (bin/*.py are not a package).
BIN_DIR = _helpers.REPO_ROOT / "bin"
sys.path.insert(0, str(BIN_DIR))
import rebirth_thresholds as rt  # noqa: E402

THRESHOLDS_JSON = BIN_DIR / "rebirth-thresholds.json"
STATUSLINE = BIN_DIR / "statusline.sh"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
OVER = FIXTURES / "transcript-over-water.jsonl"
UNDER = FIXTURES / "transcript-under-water.jsonl"

# statusline's jq token-sum filter — VERBATIM the canonical filter the resolver mirrors.
JQ_TOKEN_FILTER = (
    'select(.type=="assistant" and .message.usage) | '
    '((.message.usage.input_tokens // 0) + '
    '(.message.usage.cache_creation_input_tokens // 0) + '
    '(.message.usage.cache_read_input_tokens // 0))'
)


@pytest.fixture(scope="module")
def thresholds():
    return rt.load_thresholds()


# --------------------------------------------------------------------------- #
# Window resolution: display-name, model-id, default
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("model", ["Opus 4.8", "Opus 4.7"])
def test_resolve_window_display_name(thresholds, model):
    assert rt.resolve_window(model, thresholds) == 1_000_000


@pytest.mark.parametrize("model", [
    "claude-opus-4-8", "claude-opus-4-7", "opus-4.8", "opus-4.7",
])
def test_resolve_window_model_id(thresholds, model):
    assert rt.resolve_window(model, thresholds) == 1_000_000


@pytest.mark.parametrize("model", ["claude-sonnet-4-5", "Sonnet 4.5", "", None])
def test_resolve_window_default(thresholds, model):
    assert rt.resolve_window(model, thresholds) == 200_000


# --------------------------------------------------------------------------- #
# Hard / soft byte thresholds
# --------------------------------------------------------------------------- #
def test_resolve_thresholds_opus(thresholds):
    window, hard, soft = rt.resolve_thresholds("claude-opus-4-8", thresholds)
    assert window == 1_000_000
    assert hard == 1_000_000 * thresholds["hardHighWaterFraction"]
    assert soft == 1_000_000 * thresholds["softThresholdFraction"]
    assert soft < hard < window  # soft below hard below the real window


def test_resolve_thresholds_default(thresholds):
    window, hard, soft = rt.resolve_thresholds("Sonnet 4.5", thresholds)
    assert (window, hard, soft) == (
        200_000,
        200_000 * thresholds["hardHighWaterFraction"],
        200_000 * thresholds["softThresholdFraction"],
    )


# --------------------------------------------------------------------------- #
# Canonical token sum on the fixtures + over/under-water classification
# --------------------------------------------------------------------------- #
def test_token_sum_over_water(thresholds):
    tokens = rt.latest_usage_tokens(str(OVER))
    assert tokens == 4200 + 15000 + 890000  # 909_200 — latest line, not the earlier one
    window, hard, _soft = rt.resolve_thresholds(rt.latest_model(str(OVER)), thresholds)
    assert window == 1_000_000
    assert tokens >= hard  # OVER the hard high-water


def test_token_sum_under_water(thresholds):
    tokens = rt.latest_usage_tokens(str(UNDER))
    assert tokens == 3000 + 12000 + 300000  # 315_000
    window, hard, _soft = rt.resolve_thresholds(rt.latest_model(str(UNDER)), thresholds)
    assert window == 1_000_000
    assert tokens < hard  # UNDER the hard high-water


def test_latest_model_from_transcript():
    assert rt.latest_model(str(OVER)) == "claude-opus-4-8"
    assert rt.latest_model(str(UNDER)) == "claude-opus-4-8"


def test_token_sum_none_when_no_usage(tmp_path):
    t = tmp_path / "no-usage.jsonl"
    t.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}) + "\n"
        + json.dumps({"type": "assistant", "message": {"model": "claude-opus-4-8"}}) + "\n",
        encoding="utf-8",
    )
    assert rt.latest_usage_tokens(str(t)) is None


# --------------------------------------------------------------------------- #
# AC6 anti-drift: the json numbers match what bin/statusline.sh uses
# --------------------------------------------------------------------------- #
def _statusline_case_window(model):
    """Resolve WINDOW for `model` via statusline.sh's OWN inline `case` block, read
    from the live script — so this asserts the json table against statusline's real
    resolution, not a copy of it. Reds if either side drifts."""
    src = STATUSLINE.read_text(encoding="utf-8")
    m = re.search(r'case "\$MODEL" in\n(.*?)\nesac', src, re.DOTALL)
    assert m, "statusline.sh window `case` block not found — refactor changed its shape"
    script = f'MODEL={json.dumps(model)}\ncase "$MODEL" in\n{m.group(1)}\nesac\necho "$WINDOW"'
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True)
    return int(out.stdout.strip())


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
@pytest.mark.parametrize("model", ["Opus 4.8", "Opus 4.7", "Sonnet 4.5", "Haiku"])
def test_json_window_matches_statusline_case(thresholds, model):
    """The python resolver (json table) and statusline.sh's inline case resolve the
    IDENTICAL window for the same display-name model — the AC6 no-drift pin."""
    assert rt.resolve_window(model, thresholds) == _statusline_case_window(model)


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq required")
@pytest.mark.parametrize("fixture", [OVER, UNDER])
def test_token_sum_matches_statusline_jq(fixture):
    """The python canonical token sum equals statusline.sh's own jq filter (run
    verbatim over the same fixture) — the AC6 token-sum no-drift pin."""
    out = subprocess.run(
        ["jq", "-r", JQ_TOKEN_FILTER, str(fixture)],
        capture_output=True, text=True, check=True,
    )
    bash_tokens = int(out.stdout.strip().splitlines()[-1])  # tail -1
    assert rt.latest_usage_tokens(str(fixture)) == bash_tokens


def test_mutating_json_changes_resolution(tmp_path):
    """Proves neither number is hardcoded: a window/fraction edit to the data file
    changes the resolver's output (it reads the file, not a constant)."""
    data = json.loads(THRESHOLDS_JSON.read_text(encoding="utf-8"))
    data["windows"][0]["window"] = 42
    data["defaultWindow"] = 7
    data["hardHighWaterFraction"] = 0.5
    mutated = tmp_path / "rebirth-thresholds.json"
    mutated.write_text(json.dumps(data), encoding="utf-8")
    t = rt.load_thresholds(str(mutated))
    assert rt.resolve_window("Opus 4.8", t) == 42
    assert rt.resolve_window("Sonnet 4.5", t) == 7
    _w, hard, _s = rt.resolve_thresholds("Opus 4.8", t)
    assert hard == 42 * 0.5
