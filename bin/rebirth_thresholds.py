#!/usr/bin/env python3
"""Shared window/threshold resolver for the rebirth context-pressure detection.

The SINGLE python place for the rebirth number logic (design phase 2, I1/D24). Both
`bin/drive-stop-hook.py` (the Stop-hook hard high-water steer) import this module and
read the same `bin/rebirth-thresholds.json` sibling data file — no window or fraction
is hardcoded in a consumer. `bin/statusline.sh` (bash) reads the SAME json via jq; AC6
pins both classifiers to identical numbers for the same model + the same file.

Resolution contract (mirrors statusline's bash, restated in python — D24/D25/D26):
  window(M) = first windows[i].window whose any match[j] is a substring of M, else
              defaultWindow. Matching is case-sensitive substring (statusline's
              `case "$MODEL" in *"Opus 4.8"*` semantics), and the match list carries
              BOTH the display-name form (`Opus 4.8`, what statusline feeds) and the
              model-id form (`opus-4-8`, what the hook reads from the transcript).
              Rule order is load-bearing: 1M rules precede the 200k substrings they
              prefix-collide with (`Sonnet 4.6` contains `Sonnet 4`); first match wins.
  hard = window * hardHighWaterFraction ; soft = window * softThresholdFraction
  Comparisons are on the raw token count vs the fractional byte threshold
  (tokens >= window * fraction) to avoid integer-pct rounding at the boundary.

Token sum (canonical, VERBATIM from statusline.sh L24 — D26): over the transcript
JSONL, for each `assistant` line whose `.message.usage` is jq-truthy (an empty `{}`
counts and sums to 0; `null`/absent/`false` is dropped), sum input_tokens +
cache_creation_input_tokens + cache_read_input_tokens under jq's `(.field // 0)`
arithmetic — `null`/absent/`false` field => 0, a JSON number is used, any other type
(`""`, `true`, list, dict) is a runtime error that DROPS the line; take the LAST such
value (statusline's `tail -1`). See `_jq_token`.

jq's error model over `jq -r '<filter>' file | tail -1` has exactly two relevant modes;
the resolver replicates BOTH uniformly (one guard per mode, no per-shape special-casing):
  Mode 1 — a JSON *parse* error halts the whole stream (jq stops reading input), so the
    scan stops there and keeps the prior value. => `json.loads` failure BREAKs.
  Mode 2 — a per-line *runtime* error on a successfully-parsed line (indexing a non-object
    top-level scalar/array, a non-object `message`/`usage`, string-vs-number arithmetic on a
    token field, …) makes jq emit nothing for THAT line yet keep going. => any exception
    while extracting/summing the line DROPS it and CONTINUEs.
(jq-falsy/absent usage — `null`/missing/`false`/a `null` top-level line — is dropped via
`select`; in Python that is either a falsy `.get` or an AttributeError, both of which the
mode-2 guard turns into a continue, matching jq.) None when no usage line ever sums.
"""
import json
import os


THRESHOLDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "rebirth-thresholds.json")


def load_thresholds(path=None):
    """Parse the thresholds data file. Raises on missing/malformed json — the caller
    (a fail-open consumer) decides how to degrade; this stays a pure reader."""
    with open(path or THRESHOLDS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def resolve_window(model, thresholds):
    """The window for `model` per the I1 substring rule, else defaultWindow.

    `model` None/empty (model field absent) falls through to defaultWindow."""
    if model:
        for rule in thresholds.get("windows", []):
            for sub in rule.get("match", []):
                if sub in model:
                    return rule["window"]
    return thresholds["defaultWindow"]


def resolve_thresholds(model, thresholds):
    """(window, hard_bytes, soft_bytes) for `model` — the fractional byte thresholds
    the consumers compare the raw token sum against (no integer-pct rounding).

    `soft_bytes` (and the `softThresholdFraction` it derives from) is LEGACY/UNUSED: it
    backed the coordinator soft-check, the secondary detection surface removed for
    over-triggering false handoffs. The only live detector — the Stop hook — uses `hard`
    alone. `soft` is retained here (and in the data file) for backward compatibility; do
    NOT reintroduce an eyeballed soft-threshold detector."""
    window = resolve_window(model, thresholds)
    hard = window * thresholds["hardHighWaterFraction"]
    soft = window * thresholds["softThresholdFraction"]  # legacy/unused (see docstring)
    return window, hard, soft


def _jq_token(usage, field):
    """One token field under jq's `(.field // 0)` arithmetic semantics (D26):
      - absent / `null` / `false`  → 0      (jq `//` defaults on null AND false)
      - a JSON number (int or float, incl. negative) → the number
      - anything else (`""`, `true`, list, dict) → RAISE, so the per-line mode-2
        guard DROPS the line (jq's arithmetic runtime-errors on a non-number, which
        emits nothing for that line while the stream keeps going).
    Python `bool` is an `int` subclass but jq treats `true`/`false` as non-numbers:
    `false` is handled by the `// 0` default above; `true` must raise (drop the line)."""
    value = usage.get(field)
    if value is None or value is False:
        return 0
    if isinstance(value, bool):  # True — jq-non-number, not defaulted by `//`
        raise TypeError("bool token field is a jq runtime error")
    if isinstance(value, (int, float)):
        return value
    raise TypeError("non-number token field is a jq runtime error")


def latest_usage_tokens(transcript_path):
    """The canonical token sum (the LAST usage-bearing assistant line's input +
    cache_creation + cache_read), or None when no usage line exists — a token-only view
    of `latest_usage_model_and_tokens` (the single scanner). Kept as the surface the AC6
    anti-drift suite pins against statusline.sh's jq token pipeline."""
    return latest_usage_model_and_tokens(transcript_path)[1]


def latest_usage_model_and_tokens(transcript_path):
    """`(model, tokens)` from the SAME latest usage-bearing assistant line, or
    `(None, None)` when no usage line exists.

    The window lookup and the token sum MUST come from one line: the model selects the
    window the tokens are measured against, so reading the model from a *different* line
    than the tokens (e.g. a usage-less/synthetic line emitted after the last usage line,
    with a different or absent model) yields a window that does not match the token
    source. This binds both to the last line that sums a usage — the same line `tail -1`
    on the canonical token jq selects — so the hook's `pct = tokens / window` is always
    self-consistent. Same two-mode guard as the token scan (parse error BREAKs; per-line
    runtime error DROPS the line and CONTINUEs)."""
    model = None
    tokens = None
    with open(transcript_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                break  # mode 1: parse error halts the stream; keep the prior pair
            try:
                # mode 2: any indexing/arithmetic error here mirrors jq emitting nothing
                # for this line while the stream keeps going → drop the line, continue.
                usage = obj["message"]["usage"]  # raises on non-object obj/message
                if obj.get("type") != "assistant" or usage is None or usage is False:
                    continue
                line_tokens = (_jq_token(usage, "input_tokens")
                               + _jq_token(usage, "cache_creation_input_tokens")
                               + _jq_token(usage, "cache_read_input_tokens"))
            except Exception:
                continue
            # This line sums a usage → it is the canonical token source; bind the model
            # to THIS same line (`.message.model`, None if absent) so both advance together.
            tokens = line_tokens
            model = obj["message"].get("model")
    return model, tokens
