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
  hard = window * hardHighWaterFraction ; soft = window * softThresholdFraction
  Comparisons are on the raw token count vs the fractional byte threshold
  (tokens >= window * fraction) to avoid integer-pct rounding at the boundary.

Token sum (canonical, VERBATIM from statusline.sh L24 — D26): over the transcript
JSONL, for each `assistant` line whose `.message.usage` is jq-truthy (an empty `{}`
counts and sums to 0; `null`/absent/`false` is dropped), sum input_tokens +
cache_creation_input_tokens + cache_read_input_tokens (each missing => 0); take the
LAST such value (statusline's `tail -1`).

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
    the consumers compare the raw token sum against (no integer-pct rounding)."""
    window = resolve_window(model, thresholds)
    hard = window * thresholds["hardHighWaterFraction"]
    soft = window * thresholds["softThresholdFraction"]
    return window, hard, soft


def latest_usage_tokens(transcript_path):
    """The canonical token sum: the LAST assistant line's input + cache_creation +
    cache_read usage in the transcript JSONL, or None when no usage line exists.

    Byte-for-behavior with statusline.sh's `jq ... | tail -1` via the two-mode guard
    (see the module docstring): `json.loads` failure BREAKs (parse error halts the
    stream); any exception in the per-line extract/sum DROPS the line and CONTINUEs
    (runtime error). `{}` usage sums to 0 (present); `null`/absent/`false` usage and a
    `null`/scalar top-level line contribute nothing. Blank lines are skipped on both
    sides (not jq inputs)."""
    tokens = None
    with open(transcript_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                break  # mode 1: parse error halts the stream; tail -1 keeps the prior value
            try:
                # mode 2: any indexing/arithmetic error here mirrors jq emitting nothing
                # for this line while the stream keeps going → drop the line, continue.
                usage = obj["message"]["usage"]  # raises on non-object obj/message
                # jq's `select(.message.usage)` truthiness: only null/false (and absent,
                # already a KeyError above) are falsy — `{}` is jq-truthy and sums to 0.
                if obj.get("type") != "assistant" or usage is None or usage is False:
                    continue
                tokens = ((usage.get("input_tokens") or 0)
                          + (usage.get("cache_creation_input_tokens") or 0)
                          + (usage.get("cache_read_input_tokens") or 0))
            except Exception:
                continue
    return tokens


def latest_model(transcript_path):
    """The LAST assistant line's `.message.model` VERBATIM (a model id, e.g.
    `claude-opus-4-8`), or None — fed to resolve_window, which maps None to the default
    window. Takes the latest assistant line's model as-is: if that line omits model it
    yields None (NOT an older line's value), so an unmodeled latest line falls back to
    the default window. Same two-mode guard as the token scan: a parse error BREAKs
    (halts); any runtime error (non-object top-level line or `message`) DROPS that line
    and CONTINUEs."""
    model = None
    with open(transcript_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                break  # mode 1: parse error halts the stream
            try:
                if obj.get("type") != "assistant":
                    continue
                # jq `.message.model`: a missing `model` key yields null (sets None on
                # THIS line), but indexing a non-object `message` is a runtime error.
                model = obj["message"].get("model")
            except Exception:
                continue  # mode 2: runtime error drops this line, scan continues (keeps prior)
    return model
