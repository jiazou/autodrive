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
LAST such value (statusline's `tail -1`). A JSON *parse* error halts the whole stream
(jq stops reading input), so the scan stops there and keeps the prior value; a per-line
*runtime* error (a truthy non-object `usage`, or a non-object `message` indexed in the
`select`) drops only that one line and the scan CONTINUES. None when no usage line exists.
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

    Byte-for-behavior with statusline.sh's `jq ... | tail -1`:
      - jq's `select(... and .message.usage)` keeps a line whose `.message.usage` is
        jq-truthy — an empty `{}` usage is PRESENT and sums to 0; an absent, `null`, or
        `false` usage is jq-falsy and dropped. So `{}` counts as a 0-total line; the
        falsy forms do not.
      - A JSON PARSE error ENDS the stream (jq stops reading input); `tail -1` then takes
        the last value emitted before it — so the scan stops and keeps the prior value.
      - A per-line RUNTIME error (a truthy non-object `usage` like `5`/`"x"`, indexed by
        `.input_tokens`; or a non-object `message` indexed by `.usage` inside `select`)
        makes jq emit nothing for THAT line but keep going — so it drops only that line
        and the scan CONTINUES. Distinct from the parse error, which halts.
    (Blank lines are not jq inputs and are skipped on both sides.)"""
    tokens = None
    with open(transcript_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                break  # jq halts at the first parse error; tail -1 keeps the prior value
            if obj.get("type") != "assistant":
                continue
            message = obj.get("message")
            if not isinstance(message, dict):
                continue  # jq: `.message.usage` on a non-object errors → that line drops, scan continues
            usage = message.get("usage")
            if not isinstance(usage, dict):
                # jq-falsy usage (null/absent/false) is dropped by select; a truthy
                # non-object usage passes select but errors when indexed → that line
                # drops. Either way the line contributes nothing and the scan continues.
                continue
            tokens = ((usage.get("input_tokens") or 0)
                      + (usage.get("cache_creation_input_tokens") or 0)
                      + (usage.get("cache_read_input_tokens") or 0))
    return tokens


def latest_model(transcript_path):
    """The LAST assistant line's `.message.model` VERBATIM (a model id, e.g.
    `claude-opus-4-8`), or None — fed to resolve_window, which maps None to the default
    window. Takes the latest assistant line's model as-is: if that line omits model it
    yields None (NOT an older line's value), so an unmodeled latest line falls back to
    the default window. Halts at the first parse-malformed line, matching the token scan;
    a non-object `message` drops only that line (no crash), like the token scan's runtime
    skip."""
    model = None
    with open(transcript_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                break
            if obj.get("type") != "assistant":
                continue
            message = obj.get("message")
            if not isinstance(message, dict):
                continue  # non-object message has no .model → skip this line, keep prior
            model = message.get("model")
    return model
