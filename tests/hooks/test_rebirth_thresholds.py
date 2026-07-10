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


# The 200k rule (windows[1]) lists the genuinely-200k families explicitly; everything
# unlisted — including an unknown/future model and an absent model field — resolves to the
# 1M default (defaultWindow). `Sonnet 4`/`claude-sonnet-4-20250514` (the reported bug) and
# bare-`Haiku` forms (D3) are pinned here.
@pytest.mark.parametrize("model", [
    "claude-sonnet-4-5", "Sonnet 4.5", "claude-haiku-4-5", "Haiku 4",
    "claude-opus-4-1", "Opus 4.5",
    "Sonnet 4", "claude-sonnet-4-20250514",           # the reported bug: real Sonnet-4 -> 200k
    "Haiku 3.5", "claude-3-5-haiku-20241022",         # bare Haiku (D3) catches Haiku 3.5
])
def test_resolve_window_known_200k(thresholds, model):
    assert rt.resolve_window(model, thresholds) == 200_000


# C2 regression pin: current-gen 1M-context models must NOT be clamped to 200k. A bare
# "Sonnet" substring once silently matched Sonnet 5 / 4.6, and Opus 4.6 was explicitly
# (wrongly) listed in the 200k rule — both steered rebirth at ~17% of real usage. The
# ordered two-rule table now lists these families in the 1M rule (windows[0]), which precedes
# the 200k rule (windows[1]); first-match wins, so they resolve to 1M — including the
# collision id `claude-sonnet-4-6` (contains the 200k substring `sonnet-4`, but the 1M rule
# fires first). Without this pin the bug is invisible (the suite tested only Sonnet 4.5).
# Guards bin/rebirth-thresholds.json + statusline.sh.
@pytest.mark.parametrize("model", [
    "Sonnet 5", "claude-sonnet-5", "Sonnet 4.6", "claude-sonnet-4-6",
    "Opus 4.6", "claude-opus-4-6",
])
def test_resolve_window_1m_current_gen(thresholds, model):
    assert rt.resolve_window(model, thresholds) == 1_000_000


# Bare `Sonnet` (no version) is 1M via the default (it matches no rule token). Bare `Haiku`
# is deliberately NOT here — it IS a 200k rule token (D3), so it resolves 200k, not 1M.
@pytest.mark.parametrize("model", ["Some Future Model", "claude-opus-9", "Sonnet", "", None])
def test_resolve_window_default_is_1m(thresholds, model):
    assert rt.resolve_window(model, thresholds) == 1_000_000


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
    model, tokens = rt.latest_usage_model_and_tokens(str(OVER))
    assert tokens == 4200 + 15000 + 890000  # 909_200 — latest line, not the earlier one
    window, hard, _soft = rt.resolve_thresholds(model, thresholds)
    assert window == 1_000_000
    assert tokens >= hard  # OVER the hard high-water


def test_token_sum_under_water(thresholds):
    model, tokens = rt.latest_usage_model_and_tokens(str(UNDER))
    assert tokens == 3000 + 12000 + 300000  # 315_000
    window, hard, _soft = rt.resolve_thresholds(model, thresholds)
    assert window == 1_000_000
    assert tokens < hard  # UNDER the hard high-water


def test_latest_usage_model_and_tokens_bound_to_same_line(tmp_path):
    """P1-1: the window model and the token sum must come from the SAME usage-bearing
    line. A usage-bearing opus line followed by a LATER usage-less line with a different
    model must yield the opus line's model AND tokens together — NOT the later line's
    model paired with the opus tokens (the mismatch that splits window from the token
    source)."""
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
def _statusline_case_window(model, model_id=""):
    """Resolve WINDOW for (`model`, `model_id`) via statusline.sh's OWN inline `case` block,
    read from the live script — running `case "$MODEL $MODEL_ID"` (NOT display-only) so
    id-forms are exercised on the statusline surface. Asserts the json table against
    statusline's real resolution, not a copy of it. Reds if either side drifts."""
    src = STATUSLINE.read_text(encoding="utf-8")
    m = re.search(r'case "\$MODEL \$MODEL_ID" in\n(.*?)\nesac', src, re.DOTALL)
    assert m, "statusline.sh window `case` block not found — refactor changed its shape"
    script = (f'MODEL={json.dumps(model)}\nMODEL_ID={json.dumps(model_id)}\n'
              f'case "$MODEL $MODEL_ID" in\n{m.group(1)}\nesac\necho "$WINDOW"')
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True)
    return int(out.stdout.strip())


def _statusline_case_arms():
    """Parse statusline.sh's inline window `case` into {window_int: set(match_tokens)} for
    the two non-default arms (the `*)` default arm carries no *"tok"* globs). Reads the live
    script so a token change on the statusline surface is reflected here."""
    src = STATUSLINE.read_text(encoding="utf-8")
    m = re.search(r'case "\$MODEL \$MODEL_ID" in\n(.*?)\nesac', src, re.DOTALL)
    assert m, "statusline.sh window `case` block not found — refactor changed its shape"
    arms = {}
    for line in m.group(1).splitlines():
        wm = re.search(r'WINDOW=(\d+)', line)
        if not wm:
            continue
        toks = set(re.findall(r'\*"([^"]+)"\*', line))
        if not toks:  # the `*)` default arm has no *"tok"* globs
            continue
        arms.setdefault(int(wm.group(1)), set()).update(toks)
    return arms


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
@pytest.mark.parametrize("model", [
    "Opus 4.8", "Opus 4.7", "Sonnet 5", "Sonnet 4.6", "Sonnet 4.5", "Sonnet 4", "Haiku",
])
def test_json_window_matches_statusline_case(thresholds, model):
    """The python resolver (json table) and statusline.sh's inline case resolve the
    IDENTICAL window for the same display-name model — a behavioral spot-check of the two
    surfaces. Includes Sonnet 5 / Sonnet 4.6 (1M, NOT clamped — C2 / the collision) and
    Sonnet 4 (200k, the reported bug)."""
    assert rt.resolve_window(model, thresholds) == _statusline_case_window(model)


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
@pytest.mark.parametrize("model,model_id,expected", [
    # AC4 statusline half — id-forms are LOAD-BEARING on the `case "$MODEL $MODEL_ID"` surface.
    # The only shape that reds on deleting a 1M id-form is one where the id must win over a
    # *200k* display: `Sonnet 4` (200k display) + `claude-sonnet-4-6` (1M id). The 1M arm's
    # *"sonnet-4-6"* must beat the 200k arm's *"Sonnet 4"* — drop `sonnet-4-6` from the 1M arm
    # and it falls to 200k -> this REDS.
    ("Sonnet 4", "claude-sonnet-4-6", 1_000_000),
    # Generic display + real 200k id -> 200k (id load-bearing in the 200k arm).
    ("Brand X", "claude-sonnet-4-20250514", 200_000),
])
def test_statusline_case_id_forms_load_bearing(model, model_id, expected):
    """AC4 statusline surface: exercising `case "$MODEL $MODEL_ID"`, an id-form resolves the
    window even against a colliding/generic display name."""
    assert _statusline_case_window(model, model_id) == expected


# AC12 — every REAL 200k model id-form is behaviorally pinned on BOTH surfaces. A 200k
# id-form is LOAD-BEARING in a way a 1M id-form is NOT: a coordinated deletion of a 200k
# token from BOTH json and the inline `case` drops its model to the 1M `defaultWindow` — a
# REAL regression (the exact class this run targets) — whereas a 1M id-form is inert (resolves
# 1M via the default whether present or absent). Each id is paired with a GENERIC display
# ("Brand X", matching no rule token) so ONLY the id-form can carry the 200k window; the pin
# reds on a coordinated both-surface deletion of that token. Imprecision budget (D-p1-5): 1M
# id-forms (`fable-5`, `sonnet-5`, `sonnet-4-6`, `opus-4-8/4-7/4-6`) are intentionally NOT
# pinned against coordinated deletion (inert; the colliding `sonnet-4-6` is separately pinned
# by AC4's id-beats-display test); future/unknown ids are out of scope (fail-safe direction).
KNOWN_200K_IDS = [
    "claude-sonnet-4-20250514",   # sonnet-4  (the reported bug)
    "claude-sonnet-4-5",          # sonnet-4-5
    "claude-opus-4-5",            # opus-4-5
    "claude-opus-4-1",            # opus-4-1
    "claude-3-5-haiku-20241022",  # bare haiku
    "claude-haiku-4",             # bare haiku
    "claude-haiku-4-5",           # bare haiku
]


@pytest.mark.parametrize("model_id", KNOWN_200K_IDS)
def test_resolver_200k_id_forms_pinned(thresholds, model_id):
    """AC12 (resolver half): every real 200k model id resolves to 200k via `resolve_window`.
    Reds if its token is deleted from the json 200k rule (drops to the 1M default)."""
    assert rt.resolve_window(model_id, thresholds) == 200_000


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
@pytest.mark.parametrize("model_id", KNOWN_200K_IDS)
def test_statusline_200k_id_forms_pinned(model_id):
    """AC12 (statusline half): every real 200k model id resolves to 200k via statusline.sh's
    inline `case "$MODEL $MODEL_ID"` — id-only (generic display "Brand X"), so ONLY the id-form
    carries the window. Reds if its token is deleted from the 200k `case` arm (drops to the 1M
    default `*)` arm). Together with the resolver half, a coordinated both-surface token
    deletion reds on at least one surface."""
    assert _statusline_case_window("Brand X", model_id) == 200_000


def test_json_case_token_sets_identical(thresholds):
    """AC5 — STRUCTURAL cross-surface parity: each json rule's FULL match-token set equals the
    corresponding inline `case` arm's FULL *"tok"* glob set, keyed by the SAME window. Reds on
    any token that changes on ONE surface but not the other (the realistic
    edit-one-file-forget-its-twin drift). HONEST bound (no overclaim): it does NOT red on a
    *coordinated* deletion of the SAME token from BOTH surfaces (the sets stay equal) — such a
    loss is a real regression only for a COLLIDING 1M id-form (`sonnet-4-6` ⊃ 200k `sonnet-4`),
    which AC4 pins functionally (drop -> falls to 200k -> reds), and is functionally INERT for a
    NON-colliding 1M id-form (`fable-5`, `opus-4-8`, …, resolve 1M via the default whether
    present or absent), intentionally not pinned (edge case #6 / D-p1-4). Scope: the two
    EXECUTABLE surfaces only (docstring human-maintained, AC9 verify-only)."""
    json_sets = {rule["window"]: set(rule["match"]) for rule in thresholds["windows"]}
    case_sets = _statusline_case_arms()
    assert json_sets == case_sets


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
    """AC6 — proves neither number is hardcoded AND per-rule indexing (windows[0]=the 1M
    rule, windows[1]=the 200k rule): edits each rule's window independently plus the default
    and a fraction, then asserts a 1M-rule model tracks windows[0], a 200k-rule model tracks
    windows[1], and an unmatched model tracks defaultWindow — all read from the file, not a
    constant."""
    data = json.loads(THRESHOLDS_JSON.read_text(encoding="utf-8"))
    data["windows"][0]["window"] = 42   # the 1M rule (Fable 5 / Sonnet 4.6 / Opus 4.8 …)
    data["windows"][1]["window"] = 99   # the 200k rule (Sonnet 4.5 / Sonnet 4 / Haiku …)
    data["defaultWindow"] = 7
    data["hardHighWaterFraction"] = 0.5
    mutated = tmp_path / "rebirth-thresholds.json"
    mutated.write_text(json.dumps(data), encoding="utf-8")
    t = rt.load_thresholds(str(mutated))
    assert rt.resolve_window("Fable 5", t) == 42            # 1M rule -> windows[0]
    assert rt.resolve_window("Sonnet 4.5", t) == 99         # 200k rule -> windows[1]
    assert rt.resolve_window("Some Future Model", t) == 7   # unmatched -> defaultWindow
    _w, hard, _s = rt.resolve_thresholds("Sonnet 4.5", t)
    assert hard == 99 * 0.5
