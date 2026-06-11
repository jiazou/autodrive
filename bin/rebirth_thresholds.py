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
JSONL, for each `assistant` line carrying `.message.usage`, sum input_tokens +
cache_creation_input_tokens + cache_read_input_tokens (each missing => 0); take the
LAST such value (statusline's `tail -1`). None when no usage line exists.
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

    Mirrors statusline.sh's `jq ... | tail -1`: a malformed line is skipped (jq's
    per-line model), a line without `.message.usage` does not count."""
    tokens = None
    with open(transcript_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") != "assistant":
                continue
            usage = obj.get("message", {}).get("usage")
            if not usage:
                continue
            tokens = ((usage.get("input_tokens") or 0)
                      + (usage.get("cache_creation_input_tokens") or 0)
                      + (usage.get("cache_read_input_tokens") or 0))
    return tokens


def latest_model(transcript_path):
    """The LAST assistant line's `.message.model` (a model id, e.g. `claude-opus-4-8`),
    or None when no assistant line carries one — fed to resolve_window."""
    model = None
    with open(transcript_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") != "assistant":
                continue
            m = obj.get("message", {}).get("model")
            if m:
                model = m
    return model
