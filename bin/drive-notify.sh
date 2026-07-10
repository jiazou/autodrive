#!/usr/bin/env bash
# drive-notify.sh — R3 fail-open push-notify transport for /drive decision-bearing parks.
#
# Config-driven, content-agnostic transport. The coordinator (drive.md § Present human
# pause step 3) fires this AFTER `waiting` is durably set, ONLY for a decision-bearing park
# (`waiting` ∈ gateA/gateB/stop:/ask: — NEVER rebirth). It is a pure SIDE-EFFECT:
#   * ALWAYS exits 0 — every path, incl. bad args / missing RUN_DIR / dedup-hit / a
#     transport that errors or times out. It never gates, blocks, or fails a run.
#   * NEVER writes state.json — the ONLY file it writes is $RUN_DIR/notified-*.marker.
#   * Backgrounds + timeout-bounds the send so neither the pause turn nor the Stop hook's
#     allow-stop-when-waiting path can be wedged (R3 constraint 1).
#
# Usage:
#   drive-notify.sh --waiting <waiting> --tip <tipSha> --message <text> \
#                   [--run-dir <RUN_DIR>] [--title <text>]
#
# Transport (config, the operator's own trusted command):
#   $DRIVE_NOTIFY_CMD      shell command that RECEIVES THE MESSAGE ON STDIN. UNSET/empty →
#                          NO-OP, exit 0 (the inert fail-open default; ships inert).
#   $DRIVE_NOTIFY_TIMEOUT  send timeout seconds (default 5).
# The message is delivered on STDIN, NEVER shell-interpolated (injection-safe); the command
# is the operator's config. Per-send context is exported as DRIVE_NOTIFY_{WAITING,TIP,TITLE,RUNID}.

WAITING=""; TIP=""; MESSAGE=""; RUN_DIR_ARG=""; TITLE=""
# `shift 2 || shift` guards a dangling final flag (`--waiting` with no value): `shift 2` fails
# when fewer than 2 args remain, so `|| shift` drops the flag and the loop still makes progress
# (never an infinite loop, never a usage exit).
while [ $# -gt 0 ]; do
  case "$1" in
    --waiting)  WAITING="${2:-}"; shift 2 || shift ;;
    --tip)      TIP="${2:-}"; shift 2 || shift ;;
    --message)  MESSAGE="${2:-}"; shift 2 || shift ;;
    --run-dir)  RUN_DIR_ARG="${2:-}"; shift 2 || shift ;;
    --title)    TITLE="${2:-}"; shift 2 || shift ;;
    *)          shift ;;   # unknown arg — ignore (fail-open, never a usage error)
  esac
done

# 1. RUN_DIR = --run-dir else $RUN_DIR. Not a dir → no-op, exit 0 (no place for the dedup marker).
RUN_DIR="${RUN_DIR_ARG:-${RUN_DIR:-}}"
[ -n "$RUN_DIR" ] && [ -d "$RUN_DIR" ] || exit 0

# 2. Transport unset/empty → pure no-op (never even builds the marker).
[ -n "${DRIVE_NOTIFY_CMD:-}" ] || exit 0

# 3. Dedup marker: notified-<slug>-<tipSha>.marker.
#      slug = <sanitized+truncated raw waiting>-<sha256[:12] of the RAW waiting>
#    The hash is over the RAW waiting so two distinct strings that SANITIZE to the same
#    value (e.g. `stop:a b` vs `stop:a/b`) get DISTINCT markers. shasum absent → no reliable
#    dedup key → BIAS-TO-SEND (skip the dedup gate; a duplicate ping is benign, a miss is worse).
sane="$(printf '%s' "$WAITING" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-40)"
hash=""
if command -v shasum >/dev/null 2>&1; then
  hash="$(printf '%s' "$WAITING" | shasum -a 256 2>/dev/null | cut -c1-12)"
fi
if [ -n "$hash" ]; then
  MARKER="$RUN_DIR/notified-${sane}-${hash}-${TIP}.marker"
  # Already notified this (waiting,tip) → exit 0, NO send.
  [ -e "$MARKER" ] && exit 0
  # Create the marker (tmp + mv) BEFORE the send, so a concurrent re-fire dedups.
  tmp="$MARKER.tmp.$$"
  { : > "$tmp" && mv -f "$tmp" "$MARKER"; } 2>/dev/null || rm -f "$tmp" 2>/dev/null || true
fi

# 4. Send: BACKGROUNDED, timeout-bounded, output discarded. Message on STDIN (never interpolated).
export DRIVE_NOTIFY_WAITING="$WAITING"
export DRIVE_NOTIFY_TIP="$TIP"
export DRIVE_NOTIFY_TITLE="$TITLE"
export DRIVE_NOTIFY_RUNID="$(basename "$RUN_DIR")"
TIMEOUT="${DRIVE_NOTIFY_TIMEOUT:-5}"
if command -v timeout >/dev/null 2>&1; then
  printf '%s' "$MESSAGE" | timeout "$TIMEOUT" sh -c "$DRIVE_NOTIFY_CMD" >/dev/null 2>&1 &
else
  printf '%s' "$MESSAGE" | sh -c "$DRIVE_NOTIFY_CMD" >/dev/null 2>&1 &
fi

# 5. Always exit 0 — the send is detached; its exit code never reaches the coordinator.
exit 0
