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

def _statusline_token_filter():
    """The LIVE jq token-sum filter, extracted from the `TOKENS=$(jq -r '...')` line in
    bin/statusline.sh — so the anti-drift tests run statusline's REAL filter, not a copy.
    A change to statusline's token jq pipeline therefore reds the anti-drift tests (the
    same way the window test extracts statusline's live `case` block)."""
    src = STATUSLINE.read_text(encoding="utf-8")
    m = re.search(r"""TOKENS=\$\(jq -r '(.*?)' "\$TRANSCRIPT""", src, re.DOTALL)
    assert m, "statusline.sh token `jq` filter not found — refactor changed its shape"
    return m.group(1)


# statusline's LIVE jq token-sum filter (extracted, not copied) — the resolver mirrors it.
JQ_TOKEN_FILTER = _statusline_token_filter()


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


def test_latest_usage_model_and_tokens_bound_to_same_line(tmp_path):
    """P1-1: the window model and the token sum must come from the SAME usage-bearing
    line. A usage-bearing opus line followed by a LATER usage-less line with a different
    model must yield the opus line's model AND tokens together — NOT the later line's
    model paired with the opus tokens (the mismatch that splits window from the token
    source). Contrast with `latest_model`, which by design returns the latest line's
    model (haiku) regardless of usage."""
    t = tmp_path / "usage-then-usageless.jsonl"
    t.write_text(
        json.dumps({"type": "assistant",
                    "message": {"model": "claude-opus-4-8",
                                "usage": {"input_tokens": 500000}}}) + "\n"
        + json.dumps({"type": "assistant",
                      "message": {"model": "claude-haiku-4"}}) + "\n",  # usage-less, later
        encoding="utf-8",
    )
    model, tokens = rt.latest_usage_model_and_tokens(str(t))
    assert (model, tokens) == ("claude-opus-4-8", 500000)
    # latest_model still tracks the latest LINE (the divergence this fix routes around).
    assert rt.latest_model(str(t)) == "claude-haiku-4"


def test_latest_usage_model_and_tokens_none_when_no_usage(tmp_path):
    """No usage-bearing line -> (None, None), the skip signal the hook needs."""
    t = tmp_path / "no-usage.jsonl"
    t.write_text(
        json.dumps({"type": "assistant", "message": {"model": "claude-opus-4-8"}}) + "\n",
        encoding="utf-8",
    )
    assert rt.latest_usage_model_and_tokens(str(t)) == (None, None)


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
    """The python canonical token sum equals statusline.sh's own jq filter — the LIVE
    filter extracted from the script (not a copy) — run over the same fixture: the AC6
    token-sum no-drift pin. Mutating statusline's token jq pipeline reds this."""
    out = subprocess.run(
        ["jq", "-r", JQ_TOKEN_FILTER, str(fixture)],
        capture_output=True, text=True, check=True,
    )
    bash_tokens = int(out.stdout.strip().splitlines()[-1])  # tail -1
    assert rt.latest_usage_tokens(str(fixture)) == bash_tokens


# --------------------------------------------------------------------------- #
# AC6 anti-drift — EDGE CASES the clean fixtures never exercise. Each runs the
# REAL statusline jq token pipeline (L24, verbatim filter `| tail -1`) and the
# python resolver on the SAME transcript and asserts they AGREE. The clean
# over/under fixtures masked these three drift bugs (codex-review-2.1.md).
# --------------------------------------------------------------------------- #
def _statusline_token_sum(transcript_path):
    """statusline.sh's REAL token pipeline (script L24): the verbatim jq filter piped to
    `tail -1`, run through bash so jq's halt-at-first-error + tail semantics are exact.
    Returns the int, or None when the pipeline emits nothing (statusline's empty TOKENS)."""
    script = (
        f'jq -r {json.dumps(JQ_TOKEN_FILTER)} {json.dumps(str(transcript_path))} '
        f'2>/dev/null | tail -1'
    )
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True)
    raw = out.stdout.strip()
    if not raw:
        return None
    f = float(raw)
    return int(f) if f.is_integer() else f  # jq may emit a float (e.g. 3.5)


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq required")
def test_drift_empty_usage_counts_as_present_zero(tmp_path):
    """P1-1: an empty `{}` usage on the latest line is PRESENT-0 in jq (select passes,
    fields default to 0), not skipped. Resolver must return 0 here, not the earlier
    line's 100 — matching statusline. (Pre-fix `if not usage: continue` returned 100.)"""
    t = tmp_path / "empty-usage.jsonl"
    t.write_text(
        json.dumps({"type": "assistant",
                    "message": {"model": "claude-opus-4-8",
                                "usage": {"input_tokens": 100}}}) + "\n"
        + json.dumps({"type": "assistant",
                      "message": {"model": "claude-opus-4-8", "usage": {}}}) + "\n",
        encoding="utf-8",
    )
    bash = _statusline_token_sum(t)
    assert bash == 0  # jq: {} usage present, sums to 0
    assert rt.latest_usage_tokens(str(t)) == bash


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq required")
def test_drift_malformed_line_halts_scan(tmp_path):
    """P1-2: jq stops at the first malformed line; `tail -1` then yields the last value
    BEFORE it (100), never a later valid line's value (999). Resolver must halt there
    too. (Pre-fix skip-and-continue returned 999.)"""
    t = tmp_path / "malformed.jsonl"
    t.write_text(
        json.dumps({"type": "assistant",
                    "message": {"usage": {"input_tokens": 100}}}) + "\n"
        + "THIS IS NOT JSON\n"
        + json.dumps({"type": "assistant",
                      "message": {"usage": {"input_tokens": 999}}}) + "\n",
        encoding="utf-8",
    )
    bash = _statusline_token_sum(t)
    assert bash == 100  # value before the parse error, via tail -1
    assert rt.latest_usage_tokens(str(t)) == bash


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq required")
def test_drift_usage_false_dropped_keeps_prior(tmp_path):
    """P1(r2): a `usage:false` latest line is jq-falsy → dropped by `select`, so `tail -1`
    keeps the prior line's 100 (not a crash). Resolver must match. (Pre-fix `usage.get`
    raised AttributeError on the bool.)"""
    t = tmp_path / "usage-false.jsonl"
    t.write_text(
        json.dumps({"type": "assistant",
                    "message": {"usage": {"input_tokens": 100}}}) + "\n"
        + json.dumps({"type": "assistant", "message": {"usage": False}}) + "\n",
        encoding="utf-8",
    )
    bash = _statusline_token_sum(t)
    assert bash == 100  # jq: false usage dropped by select, tail -1 keeps prior
    assert rt.latest_usage_tokens(str(t)) == bash


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq required")
def test_drift_usage_nonobject_truthy_line_dropped_scan_continues(tmp_path):
    """P1(r2): a truthy non-object `usage` (e.g. `"x"`) PASSES `select` but errors when
    indexed by `.input_tokens` — jq emits nothing for THAT line yet KEEPS GOING (a runtime
    error, unlike a parse error). So a later valid 999 line still wins. Resolver must drop
    the bad line and continue. (Pre-fix `"x".get(...)` raised AttributeError.)"""
    t = tmp_path / "usage-nonobject.jsonl"
    t.write_text(
        json.dumps({"type": "assistant",
                    "message": {"usage": {"input_tokens": 100}}}) + "\n"
        + json.dumps({"type": "assistant", "message": {"usage": "x"}}) + "\n"
        + json.dumps({"type": "assistant",
                      "message": {"usage": {"input_tokens": 999}}}) + "\n",
        encoding="utf-8",
    )
    bash = _statusline_token_sum(t)
    assert bash == 999  # runtime error on the bad line, scan continues to 999
    assert rt.latest_usage_tokens(str(t)) == bash


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq required")
def test_drift_message_nonobject_line_dropped_scan_continues(tmp_path):
    """P1(r2): a non-object `message` (e.g. `false`) makes `.message.usage` error inside
    `select` — jq drops THAT line and CONTINUES (runtime, not parse, error). A later valid
    999 line still wins. Resolver must drop and continue. (Pre-fix `.get("message",{}).get`
    raised AttributeError on the bool message.)"""
    t = tmp_path / "message-nonobject.jsonl"
    t.write_text(
        json.dumps({"type": "assistant",
                    "message": {"usage": {"input_tokens": 100}}}) + "\n"
        + json.dumps({"type": "assistant", "message": False}) + "\n"
        + json.dumps({"type": "assistant",
                      "message": {"usage": {"input_tokens": 999}}}) + "\n",
        encoding="utf-8",
    )
    bash = _statusline_token_sum(t)
    assert bash == 999  # runtime error on the bad-message line, scan continues to 999
    assert rt.latest_usage_tokens(str(t)) == bash


def test_drift_latest_model_nonobject_message_keeps_prior(tmp_path):
    """P1(r2): latest_model on a non-object `message` (`false`) drops that line and keeps
    the prior line's model (no crash), matching the token scan's runtime-skip. (Pre-fix
    `.get("message",{}).get("model")` raised AttributeError on the bool.)"""
    t = tmp_path / "model-nonobject.jsonl"
    t.write_text(
        json.dumps({"type": "assistant",
                    "message": {"model": "claude-opus-4-8"}}) + "\n"
        + json.dumps({"type": "assistant", "message": False}) + "\n",
        encoding="utf-8",
    )
    assert rt.latest_model(str(t)) == "claude-opus-4-8"  # prior kept, no crash


def test_drift_latest_model_none_when_latest_line_omits_it(tmp_path):
    """P1-3: latest_model takes the LATEST assistant line's model verbatim — if that line
    omits model it is None (NOT an older line's `claude-opus-4-8`), so resolve_window
    falls back to the DEFAULT window. (Pre-fix kept-last-truthy returned the older opus
    id → wrong 1M window.) Drift here would split the hook's window from the default."""
    t = tmp_path / "unmodeled-latest.jsonl"
    t.write_text(
        json.dumps({"type": "assistant",
                    "message": {"model": "claude-opus-4-8",
                                "usage": {"input_tokens": 10}}}) + "\n"
        + json.dumps({"type": "assistant",
                      "message": {"usage": {"input_tokens": 20}}}) + "\n",  # no model
        encoding="utf-8",
    )
    assert rt.latest_model(str(t)) is None
    th = rt.load_thresholds()
    assert rt.resolve_window(rt.latest_model(str(t)), th) == th["defaultWindow"]


# --------------------------------------------------------------------------- #
# STRUCTURAL close of the malformed-shape drift class (slice 2.1 r3). Instead of
# one bespoke test per exotic shape (rounds 1-2 whack-a-mole), one PARAMETRIZED
# sweep proves the resolver replicates jq's two-mode error model UNIFORMLY: a parse
# error HALTS (prior value wins), a per-line runtime error DROPS that line and the
# scan CONTINUES. Each case runs the REAL statusline jq pipeline and the resolver on
# the SAME transcript and asserts agreement — closing the class, not a shape.
# --------------------------------------------------------------------------- #
_A = '{"type":"assistant","message":{"usage":{"input_tokens":100}}}'      # prior valid: 100
_B = '{"type":"assistant","message":{"usage":{"input_tokens":999}}}'      # later valid: 999

_DRIFT_SHAPES = {
    # name: (jsonl body, expected jq|resolver sum)
    # --- mode 2: per-line RUNTIME error → drop bad line, scan CONTINUES to 999 ---
    "toplevel_scalar_false":   (f"{_A}\nfalse\n{_B}", 999),
    "toplevel_scalar_number":  (f"{_A}\n42\n{_B}", 999),
    "toplevel_scalar_string":  (f'{_A}\n"hi"\n{_B}', 999),
    "toplevel_array":          (f"{_A}\n[1,2,3]\n{_B}", 999),
    "message_nonobject":       (f'{_A}\n{{"type":"assistant","message":false}}\n{_B}', 999),
    "usage_nonobject_string":  (f'{_A}\n{{"type":"assistant","message":{{"usage":"x"}}}}\n{_B}', 999),
    "string_input_tokens":     (f'{_A}\n{{"type":"assistant","message":{{"usage":{{"input_tokens":"7"}}}}}}\n{_B}', 999),
    "string_cache_field":      (f'{_A}\n{{"type":"assistant","message":{{"usage":{{"cache_read_input_tokens":"x"}}}}}}\n{_B}', 999),
    # --- token-field VALUE TYPES vs jq `(.field // 0)` (r4): a non-number that is
    # neither null nor false is a jq arithmetic runtime error → drop the line (→ 999).
    # `null`/`false` are `// 0` defaults; a real number is summed. Sweeps both an
    # input_tokens and a cache field so the helper is consistent across all three. ---
    # empty-string token field is the r4 FLIP: pre-fix `or 0` collapsed `""` to 0,
    # but jq drops the line (string arithmetic error) so the prior 100 wins:
    "tok_emptystr_input_latest": (f'{_A}\n{{"type":"assistant","message":{{"usage":{{"input_tokens":""}}}}}}', 100),
    "tok_emptystr_cache_latest": (f'{_A}\n{{"type":"assistant","message":{{"usage":{{"input_tokens":5,"cache_read_input_tokens":""}}}}}}', 100),
    "tok_emptystr_input_mid":    (f'{_A}\n{{"type":"assistant","message":{{"usage":{{"input_tokens":""}}}}}}\n{_B}', 999),
    "tok_true_input":          (f'{_A}\n{{"type":"assistant","message":{{"usage":{{"input_tokens":true}}}}}}\n{_B}', 999),
    "tok_true_cache":          (f'{_A}\n{{"type":"assistant","message":{{"usage":{{"cache_creation_input_tokens":true}}}}}}\n{_B}', 999),
    "tok_emptyarr_input":      (f'{_A}\n{{"type":"assistant","message":{{"usage":{{"input_tokens":[]}}}}}}\n{_B}', 999),
    "tok_emptyobj_input":      (f'{_A}\n{{"type":"assistant","message":{{"usage":{{"input_tokens":{{}}}}}}}}\n{_B}', 999),
    # null/false token field → `// 0` default (NOT a drop); latest line so it wins:
    "tok_false_input_latest":  (f'{_A}\n{{"type":"assistant","message":{{"usage":{{"input_tokens":false}}}}}}', 0),
    "tok_null_input_latest":   (f'{_A}\n{{"type":"assistant","message":{{"usage":{{"input_tokens":null}}}}}}', 0),
    "tok_false_cache_latest":  (f'{_A}\n{{"type":"assistant","message":{{"usage":{{"input_tokens":4,"cache_creation_input_tokens":false}}}}}}', 4),
    # a real number (int / float, incl. absent-other-fields → 0) is summed:
    "tok_int_input_latest":    (f'{_A}\n{{"type":"assistant","message":{{"usage":{{"input_tokens":5}}}}}}', 5),
    "tok_float_input_latest":  (f'{_A}\n{{"type":"assistant","message":{{"usage":{{"input_tokens":1.5,"cache_read_input_tokens":2}}}}}}', 3.5),
    "tok_absent_input_latest": (f'{_A}\n{{"type":"assistant","message":{{"usage":{{"cache_read_input_tokens":7}}}}}}', 7),
    # --- jq-falsy/absent usage → dropped by `select`, scan continues (no crash) ---
    "usage_false_latest":      (f'{_A}\n{{"type":"assistant","message":{{"usage":false}}}}', 100),
    "usage_null_latest":       (f'{_A}\n{{"type":"assistant","message":{{"usage":null}}}}', 100),
    "toplevel_null":           (f"{_A}\nnull\n{_B}", 999),
    # --- jq-truthy `{}` usage → PRESENT, sums to 0 (not skipped) ---
    "empty_usage_latest":      (f'{_A}\n{{"type":"assistant","message":{{"usage":{{}}}}}}', 0),
    # --- mode 1: PARSE error → HALT, tail -1 keeps the prior 100 (never the later 999) ---
    "unparseable_line":        (f"{_A}\n{{not json\n{_B}", 100),
}


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq required")
@pytest.mark.parametrize("name", sorted(_DRIFT_SHAPES))
def test_drift_class_resolver_agrees_with_jq(tmp_path, name):
    """The whole malformed-shape class, closed structurally: the resolver AGREES with
    statusline.sh's live jq pipeline on every exotic shape, because both modes (parse=halt,
    runtime=drop+continue) are replicated uniformly. Pre-fix HEAD crashed or diverged on
    the top-level-scalar / string-token / non-object shapes; this pins them shut."""
    body, expected = _DRIFT_SHAPES[name]
    t = tmp_path / f"{name}.jsonl"
    t.write_text(body + "\n", encoding="utf-8")
    bash = _statusline_token_sum(t)
    assert bash == expected, f"{name}: jq gave {bash}, expected {expected}"
    assert rt.latest_usage_tokens(str(t)) == bash, f"{name}: resolver drifts from jq"


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
