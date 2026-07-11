#!/usr/bin/env bash
# drive-codex.sh — the supervised codex-dispatch helper for /drive's dual-voice review leg.
#
# It runs the codex CLI over a review/harden/finalize scope, watchdogs a byte-silent call,
# and reports the outcome as a CLOSED token on STDOUT so the coordinator can render an honest
# degradation tier without ever parsing the codex output. It is deliberately named `drive-*`
# so its own diffs self-classify as security-sensitive (full-effort codex review every round).
#
# Usage:
#   drive-codex.sh --mode probe   --scope <tok> --attempt-log <path>
#   drive-codex.sh --mode dispatch --scope <tok> --attempt-log <path> \
#       --scope-class <design|slice|phase|finalize> \
#       --raw-log <path> --marker <path> --prompt-file <path> \
#       [--security-diff] [--confirmation-class] [--prior-codex <path>] \
#       [--stall-secs <N>] [--backstop-secs <N>] [--poll-secs <N>] \
#       [--probe-timeout-secs <N>] [--sandbox <rung>] [--no-watchdog] [--no-tiering] \
#       [--max-attempts <N>]
#
# Modes (closed set):
#   probe     — health query only (`<cmd> doctor --json`, bounded); prints OK|CODEX_UNAVAILABLE;
#               writes NO marker (pure query).
#   dispatch  — one supervised codex call (probes internally); prints exactly one closed token.
#
# Closed outcome-token set — the LAST line of STDOUT, and STDOUT carries NOTHING ELSE (channel
# separation, not convention): all diagnostics + watchdog logging go to STDERR + the attempt
# log. So stderr emitted at any time (incl. after the token) can never corrupt the token file.
#   OK | CODEX_KILLED_TIMEOUT | CODEX_UNAVAILABLE | HELPER_ERROR
# The two degraded tokens are BYTE-IDENTICAL to the first-line marker strings the helper writes.
#
# Exit codes (mirror drive-conformance.sh 0/1/2):
#   0  OK                    — codex completed; the real review is in the raw log; NO marker
#                             (the coordinator's post-process writes the real review to --marker).
#   1  CODEX_KILLED_TIMEOUT  — watchdog kill (stall-after-retry, or backstop); marker written.
#   1  CODEX_UNAVAILABLE     — cli absent OR confirmed probed outage OR exec-failed; marker written.
#   2  HELPER_ERROR          — the helper's OWN PRE-LAUNCH usage/config error (bad flags,
#                             charset-invalid --scope, missing/empty prompt or marker, unwritable
#                             --marker parent, rung/effort resolution). NO marker → the coordinator
#                             STOPs (broken helper). HELPER_ERROR is a PRE-LAUNCH-ONLY outcome:
#                             from codex-spawn on, NO path emits it (post-launch faults map to
#                             CODEX_UNAVAILABLE cause=internal, the stall/backstop path, or the
#                             marker-write fail-closed path).
# A marker-WRITE failure (writable parent but the tmp/mv itself fails — a --marker path that is a
# directory, ENOSPC, a marker made read-only after the pre-check) is FAIL-CLOSED: NO fake marker,
# a stderr diagnostic, exit 1 with the degraded token still on STDOUT (no 5th token) — the
# coordinator honors a degraded token ONLY when the marker is present, so an absent marker fails
# the scope's gate by construction.
#
# Env-var escape hatches (precedence: explicit --flag > env var > default):
#   DRIVE_CODEX_STALL_MINS     stall_secs = mins*60      (default stall 900s = 15 min)
#   DRIVE_CODEX_BACKSTOP_HOURS backstop_secs = hours*3600 (default backstop 10800s = 3h per attempt)
#   DRIVE_CODEX_WATCHDOG=off   disable the STALL detector ONLY (the per-attempt backstop stays)
#   DRIVE_CODEX_SANDBOX=<rung|off>  override the scope-class sandbox rung, or `off` = pass no flag
#   DRIVE_CODEX_EFFORT_TIER=off     never down-tier codex effort (always full)
#   DRIVE_CODEX_CMD            the codex binary (default `codex`) — the dep-independent TEST SEAM
#                             (tests inject a simulated log-writer, cf. RETENTION_TRASH_CMD).
#   DRIVE_CODEX_INJECT_INTERNAL_FAULT=1  TEST knob: force a POST-launch internal fault (proves it
#                             maps to CODEX_UNAVAILABLE cause=internal, never HELPER_ERROR).
#
# Sandbox rungs (RESOLVED from sandbox-spike-evidence.md fail-branch, §D):
#   design/phasedesign scope → read-only ;  slice/phase/finalize scope → workspace-write.
#
# Untrusted-input validation (CLASS AUDIT — EVERY `--flag value` + EVERY DRIVE_CODEX_* env is either
# validated before use OR only ever reaches a quoted / array context; NONE reaches an awk/eval/sh -c
# program by source-interpolation):
#   VALIDATED pre-launch (a bad value ⇒ HELPER_ERROR exit 2, codex un-spawned):
#     --mode {probe,dispatch} · --scope ^[A-Za-z0-9._-]+$ · --scope-class {design,slice,phase,finalize}
#     · --attempt-log (regular writable file, not FIFO/socket) · --marker parent (writable)
#     · --raw-log (regular writable-or-creatable file, not dir/FIFO/socket/device, AND its PARENT DIR
#       writable — the exec `> "$RAW_LOG"` redirect, the probe sibling `${raw%.log}.probe.log`, and the
#       killed-log renames must not fail into a false CODEX_UNAVAILABLE degrade — round-4/5 FIX A)
#     · --prompt-file (exists, non-empty, AND READABLE with non-empty content — read pre-launch, FIX B)
#     · --stall-secs/--backstop-secs/--poll-secs/--probe-timeout-secs
#     (strictly-positive number; AND --poll-secs strictly < min(stall_secs,backstop_secs) — a poll
#     coarser than the deadline it guards sleeps past it before checking ⇒ the kill never fires)
#     · --max-attempts (positive integer) · --sandbox AND DRIVE_CODEX_SANDBOX
#     (rung ∈ {read-only,workspace-write,danger-full-access,off}) · DRIVE_CODEX_STALL_MINS /
#     DRIVE_CODEX_BACKSTOP_HOURS (strictly-positive number, THEN `awk -v`, NEVER interpolated — the
#     former command-injection hole).
#   Numeric values reach awk ONLY via `awk -v var=value` (parameterized), never program interpolation.
#   Trusted-by-contract, NOT eval'd by the helper: --raw-log/--marker (quoted paths), the prompt
#     CONTENT (a quoted argv handed to codex), DRIVE_CODEX_CMD (the binary to exec — a test seam).
#     Boolean env compared literally (`= off` / `= 1`): DRIVE_CODEX_WATCHDOG, DRIVE_CODEX_EFFORT_TIER,
#     DRIVE_CODEX_INJECT_INTERNAL_FAULT.
#   REQUIRED-FILE READS fail CLOSED on a read error (not just an existence/`-s` check): --prompt-file
#     ⇒ HELPER_ERROR (required); --prior-codex is optional/best-effort so an unreadable OR
#     empty/whitespace-only prior fails toward FULL codex effort (never silently down-tiers — round-6).
#   JSON OUTPUT ENCODING: `_jstr` escapes \, ", and ALL C0 control chars (\n/\r/\t + \uXXXX) so the
#     attempt-log JSONL is valid for ANY field value (round-5); and `_awk` fixes the numeric locale to
#     C so emitted numbers use `.` (a comma-locale would otherwise emit `0,2` — invalid JSON — round-6).
#   PROCESS SUPERVISION (no SAME-PROCESS-GROUP descendant survives helper return on ANY terminal
#     path): every spawned child is group-supervised under monitor mode — the `codex exec` group is
#     reaped via a post-`wait` `-<pgid>`-liveness check on EVERY path incl. clean OK (round-3 FIX A,
#     `_reap_pgid`); the `doctor` probe group is group-killed after the probe; the probe
#     timeout-watcher is group-killed (its `sleep` child never orphaned); and one installed reaper trap
#     group-reaps all of them on TERM/INT/HUP/EXIT.
#     ACCEPTED RESIDUAL (round-4 honesty narrowing): supervision is PGID-based, so a child that
#     DETACHES via `setsid()` / a new session ESCAPES the group and can survive helper return (or
#     append to raw.log after OK). This is OUT OF SCOPE — full descendant-tree reaping is non-portable
#     over-engineering, and the REAL codex CLI never setsid-detaches children to outlive itself
#     (refuted-at-integration); a hostile/misbehaving codex that detaches is beyond this PGID
#     supervisor. The contract is therefore "no SAME-PGID descendant survives", NOT "no child survives".
#
# Best-effort supervisor: deliberately NOT `set -euo pipefail`. rc is managed explicitly. No
# `set -u` (also sidesteps the same-line `local a=$1 b=$a` expansion gotcha).

# ----------------------------------------------------------------------------- #
# Helper-internal constants (§A/§D/§F)
# ----------------------------------------------------------------------------- #
SANDBOX_RUNG_DESIGN="read-only"        # design/phasedesign scope   (spike fail-branch, §D)
SANDBOX_RUNG_CODE="workspace-write"    # slice/phase/finalize scope (spike fail-branch, §D)
EFFORT_TIER_LOW="medium"               # -c model_reasoning_effort=<low> on a clean confirmation (§F)
PROBE_TIMEOUT_SECS_DEFAULT=10          # bounded health probe — the ONE un-watchdogged codex call
POLL_SECS_DEFAULT=15                   # watchdog poll granularity (prod)
GRACE_SECS=2                           # TERM→KILL grace on a group kill

# ----------------------------------------------------------------------------- #
# CLI parse — `--flag value` with a need_value guard + exit-2 usage (mirrors drive-retention.sh).
# Every exit-2 path prints the HELPER_ERROR token to STDOUT (the token channel) + a diagnostic to
# STDERR, so the coordinator's broken-helper STOP fires on the token.
# ----------------------------------------------------------------------------- #
DRIVE_CODEX_CMD="${DRIVE_CODEX_CMD:-codex}"

usage() {
  cat >&2 <<'EOF'
usage: drive-codex.sh --mode probe|dispatch --scope <tok> --attempt-log <path>
       [dispatch] --scope-class <design|slice|phase|finalize> --raw-log <path> \
                  --marker <path> --prompt-file <path>
       [--security-diff] [--confirmation-class] [--prior-codex <path>]
       [--stall-secs <N>] [--backstop-secs <N>] [--poll-secs <N>]
       [--probe-timeout-secs <N>] [--sandbox <rung>] [--no-watchdog] [--no-tiering]
       [--max-attempts <N>]
EOF
}

# HELPER_ERROR — a PRE-LAUNCH-ONLY fault. Diagnostic → STDERR; token → STDOUT; exit 2. The
# coordinator (never the helper) appends the attempt-log `helper_error` op (the helper never
# completed), so the JSONL op enum stays closed. NO marker is written on this lane.
helper_error() {
  echo "drive-codex.sh: HELPER_ERROR ($1)" >&2
  printf '%s\n' "HELPER_ERROR"
  exit 2
}

# need_value <flag> <remaining-argc> <next>: exit 2 (HELPER_ERROR) on a missing OR flag-shaped
# value (mirrors drive-retention.sh — a trailing valued flag would otherwise spin/mis-scan).
need_value() {
  local flag="$1" argc="$2" next="$3"
  [ "$argc" -ge 2 ] || { usage; helper_error "$flag needs a value"; }
  case "$next" in
    -*) usage; helper_error "$flag needs a value (got flag-shaped: $next)" ;;
  esac
}

MODE=""; SCOPE=""; ATTEMPT_LOG=""
SCOPE_CLASS=""; RAW_LOG=""; MARKER=""; PROMPT_FILE=""; PROMPT_TEXT=""
SECURITY_DIFF=0; CONFIRMATION_CLASS=0; PRIOR_CODEX=""
STALL_SECS=""; BACKSTOP_SECS=""; POLL_SECS=""; PROBE_TIMEOUT_SECS=""
SANDBOX_OVERRIDE=""; SANDBOX_OVERRIDE_SET=0
NO_WATCHDOG=0; NO_TIERING=0; MAX_ATTEMPTS=""

while [ $# -gt 0 ]; do
  case "$1" in
    --mode)               need_value --mode "$#" "$2"; MODE="$2"; shift 2 ;;
    --scope)              need_value --scope "$#" "$2"; SCOPE="$2"; shift 2 ;;
    --attempt-log)        need_value --attempt-log "$#" "$2"; ATTEMPT_LOG="$2"; shift 2 ;;
    --scope-class)        need_value --scope-class "$#" "$2"; SCOPE_CLASS="$2"; shift 2 ;;
    --raw-log)            need_value --raw-log "$#" "$2"; RAW_LOG="$2"; shift 2 ;;
    --marker)             need_value --marker "$#" "$2"; MARKER="$2"; shift 2 ;;
    --prompt-file)        need_value --prompt-file "$#" "$2"; PROMPT_FILE="$2"; shift 2 ;;
    --prior-codex)        need_value --prior-codex "$#" "$2"; PRIOR_CODEX="$2"; shift 2 ;;
    --stall-secs)         need_value --stall-secs "$#" "$2"; STALL_SECS="$2"; shift 2 ;;
    --backstop-secs)      need_value --backstop-secs "$#" "$2"; BACKSTOP_SECS="$2"; shift 2 ;;
    --poll-secs)          need_value --poll-secs "$#" "$2"; POLL_SECS="$2"; shift 2 ;;
    --probe-timeout-secs) need_value --probe-timeout-secs "$#" "$2"; PROBE_TIMEOUT_SECS="$2"; shift 2 ;;
    --sandbox)            need_value --sandbox "$#" "$2"; SANDBOX_OVERRIDE="$2"; SANDBOX_OVERRIDE_SET=1; shift 2 ;;
    --max-attempts)       need_value --max-attempts "$#" "$2"; MAX_ATTEMPTS="$2"; shift 2 ;;
    --security-diff)      SECURITY_DIFF=1; shift ;;
    --confirmation-class) CONFIRMATION_CLASS=1; shift ;;
    --no-watchdog)        NO_WATCHDOG=1; shift ;;
    --no-tiering)         NO_TIERING=1; shift ;;
    *) usage; helper_error "unknown flag: $1" ;;
  esac
done

# ---- required-flag validation (PRE-LAUNCH; all HELPER_ERROR) ----
case "$MODE" in
  probe|dispatch) ;;
  *) usage; helper_error "invalid --mode (want probe|dispatch): '$MODE'" ;;
esac
[ -n "$SCOPE" ] || { usage; helper_error "--scope required"; }
[ -n "$ATTEMPT_LOG" ] || { usage; helper_error "--attempt-log required"; }

# --scope charset validation — done IMMEDIATELY, before the helper composes any <scope>-derived
# path (killed-log stems, marker tmp names, the attempt-log scope field). This guards the
# HELPER's OWN path composition; the coordinator's <scope> is already a trusted validated id.
case "$SCOPE" in
  *[!A-Za-z0-9._-]*) helper_error "invalid --scope charset (want ^[A-Za-z0-9._-]+$): '$SCOPE'" ;;
esac

# awk under a FIXED C numeric locale so number FORMATTING (`print`) AND PARSING (`+0`) always use `.`
# as the decimal separator (round-6 FIX B). A comma-locale (e.g. LC_NUMERIC=de_DE) would otherwise make
# awk emit `0,2` — invalid JSON for max_gap_secs/stall_secs/backstop_secs — AND mis-parse a dot-decimal
# knob like `0.05` as 0 in the comparisons/validator. Scoped to awk ONLY (a command-local assignment,
# NOT exported) so the `codex exec` child keeps the inherited locale (its UTF-8 output is unaffected).
_awk() { LC_ALL=C awk "$@"; }

# rc0 iff $1 is a STRICTLY-POSITIVE decimal number (e.g. 15, 900, 0.05). Rejects empty, negatives,
# `0`, and non-numeric garbage (any char outside [0-9.], or >1 dot). Defined HERE (before the env
# resolution below) because the numeric-env conversion MUST validate the RAW env value BEFORE it can
# reach awk — an unvalidated env interpolated into an awk PROGRAM is a command-injection surface (a
# value like `1; system("…"); 1` would execute). The `case` guard rejects every char outside [0-9.]
# FIRST, so awk only ever sees digits+one dot; the awk test is ALSO parameterized via `-v` (never
# program interpolation) for belt-and-suspenders. $1 = value.
_is_positive_number() {
  case "$1" in
    ''|*[!0-9.]*) return 1 ;;   # empty, or any char outside [0-9.] (rejects -, e, letters, ;, space, "(")
    *.*.*) return 1 ;;          # more than one dot
  esac
  _awk -v n="$1" 'BEGIN{exit !((n+0)>0)}' 2>/dev/null   # strictly > 0 (rejects 0, 0.0); n via -v, NOT interpolated
}

# ----------------------------------------------------------------------------- #
# Resolve numeric knobs from env (precedence flag > env > default). SECURITY: every numeric env is
# VALIDATED as a strictly-positive number BEFORE use and multiplied via `awk -v` (parameterized) —
# NEVER source-interpolated into an awk program (that was the command-injection hole). A bad numeric
# env is a pre-launch config-resolution failure ⇒ HELPER_ERROR (same lane as a bad numeric --flag).
# ----------------------------------------------------------------------------- #
if [ -z "$STALL_SECS" ]; then
  if [ -n "$DRIVE_CODEX_STALL_MINS" ]; then
    _is_positive_number "$DRIVE_CODEX_STALL_MINS" || helper_error "DRIVE_CODEX_STALL_MINS must be a positive number: '$DRIVE_CODEX_STALL_MINS'"
    STALL_SECS="$(_awk -v m="$DRIVE_CODEX_STALL_MINS" 'BEGIN{print m*60}')"
  else STALL_SECS=900; fi
fi
if [ -z "$BACKSTOP_SECS" ]; then
  if [ -n "$DRIVE_CODEX_BACKSTOP_HOURS" ]; then
    _is_positive_number "$DRIVE_CODEX_BACKSTOP_HOURS" || helper_error "DRIVE_CODEX_BACKSTOP_HOURS must be a positive number: '$DRIVE_CODEX_BACKSTOP_HOURS'"
    BACKSTOP_SECS="$(_awk -v h="$DRIVE_CODEX_BACKSTOP_HOURS" 'BEGIN{print h*3600}')"
  else BACKSTOP_SECS=10800; fi
fi
[ -n "$POLL_SECS" ] || POLL_SECS="$POLL_SECS_DEFAULT"
[ -n "$PROBE_TIMEOUT_SECS" ] || PROBE_TIMEOUT_SECS="$PROBE_TIMEOUT_SECS_DEFAULT"
[ -n "$MAX_ATTEMPTS" ] || MAX_ATTEMPTS=2

WATCHDOG_ON=1
[ "$NO_WATCHDOG" = 1 ] && WATCHDOG_ON=0
[ "${DRIVE_CODEX_WATCHDOG:-}" = off ] && WATCHDOG_ON=0

TIERING_ON=1
[ "$NO_TIERING" = 1 ] && TIERING_ON=0
[ "${DRIVE_CODEX_EFFORT_TIER:-}" = off ] && TIERING_ON=0

# ----------------------------------------------------------------------------- #
# Small portable primitives.
# ----------------------------------------------------------------------------- #

# fstat-on-fd size (follows the inode across an mv-aside — a prior orphan appending to a
# since-renamed log cannot fool the poll). BSD `stat -f %z` first, GNU `stat -c %s` fallback
# (the proven drive-retention.sh idiom). $1 = fd number.
_fd_size() {
  local p
  if [ -d /proc/self/fd ]; then p="/proc/self/fd/$1"; else p="/dev/fd/$1"; fi
  stat -f %z "$p" 2>/dev/null || stat -c %s "$p" 2>/dev/null
}

# rc0 iff the file exists and has non-whitespace content. $1 = path.
_log_nonempty() {
  [ -s "$1" ] || return 1
  grep -q '[^[:space:]]' "$1" 2>/dev/null
}

# rc0 (true) iff the raw log is DEGENERATE — it carries NO real review content: it is the codex
# stdin banner "Reading additional input from stdin..." alone (the inherited-open-stdin
# degeneration, ~39 bytes, rc0 but no review), OR blank, OR the banner plus only hidden/stray
# bytes. codex prints this banner whenever stdin is a non-TTY (verified codex v0.142.5, EVEN with
# `< /dev/null`), so a HEALTHY log is "banner + real review" and must NOT match; only a
# no-real-content log matches, so the OK gate fails it closed. Full-LINE anchored (grep -vx), NOT a
# substring strip, so a real review line that QUOTES the banner (e.g.
# `MINOR: prints "Reading additional input from stdin..."`) is NOT dropped and stays a real review.
# Banner literal pinned to codex v0.142.5 (live-captured); a future codex reword silently retires
# this net but FIX-1 (< /dev/null) still prevents the bug. Defense-in-depth only.
# IMPRECISION BUDGET (safe direction): a review that is ENTIRELY non-ASCII (no ASCII graph byte
# survives normalization) classifies as degenerate → CODEX_UNAVAILABLE, never a false OK — codex
# reviews always carry ASCII severity tags, so this cannot mis-drop a real review. The whole
# escape-embedded-text class is closed (valid + malformed CSI/OSC/DCS/Fe); this is NOT a general
# adversarial-input sanitizer, and need not be — real codex writes to a NON-TTY file and emits no
# escapes, so its degenerate output is the plain banner.
# ACCEPTED RESIDUAL (overrule-with-evidence, codex r3): `banner + any VISIBLE printable residue`
# (`banner...X`, or `banner\n.\n`) classifies as a REAL review (→ OK), NOT degenerate. This is by
# design, not a bypass: (a) after FIX-1 the HEALTHY log IS `banner\n<review>`, so the matcher MUST
# pass `banner + substantive content`; `banner + X` (tiny junk) is byte-INDISTINGUISHABLE from
# `banner + a terse real review`, and NO content threshold converges (an adversary crafts N+1 chars;
# N also reds legitimately-terse real reviews). (b) The real producer cannot emit it — codex's banner
# is its own complete newline-terminated line, so `banner...X` on that line is unreachable, and a
# lone-`.` review body is not codex's degenerate output (which is the plain banner, caught here).
# FIX-1 (< /dev/null) is the load-bearing guarantee; this net catches the exact observed degenerate
# shape + escape/control-byte drift. $1 = path.
_log_banner_only() {
  [ -s "$1" ] || return 1
  # Normalize so a banner line carrying stray/hidden bytes STILL matches the full-line banner
  # pattern and is dropped. WITHOUT this the matcher is fail-OPEN — a degenerate rc0 log of
  # "banner + junk" fails the full-line match, its banner TEXT reads as real content, and a false OK
  # slips past the gate (codex adversarial finding). Two normalization passes:
  #   (a) strip ECMA-48 escape sequences — the FULL class that can embed printable residue: OSC
  #       (ESC ] … BEL|ST) and DCS/SOS/PM/APC (ESC P/X/^/_ … ST) carry ARBITRARY text and MUST be
  #       removed whole (their body would otherwise leak as content); CSI (ESC [ … final) and the
  #       Fe two-char (ESC <byte>) are also stripped. Stripping the whole escape-embedded-text class
  #       (not one shape) is the class-level fix — a per-escape-shape patch is a treadmill.
  #   (b) LC_ALL=C tr: keep ONLY newline + printable-ASCII (drops CR, NUL, BEL, DEL, TAB, any bare
  #       ESC left after (a), and any non-ASCII byte e.g. zero-width U+200B).
  # Then drop full-line banner matches (only space/newline remain as whitespace); if any VISIBLE
  # (`[[:graph:]]`) content remains it is a real review → return 1; else degenerate → 0. Full-LINE
  # anchored (grep -vx) so a real review line that QUOTES the banner is NOT dropped.
  # sed rules (per line — sed's line-orientation bounds each strip to its own line, so an
  # unterminated escape can never eat a following review line): OSC (ESC ] … BEL|ST), DCS/SOS/PM/APC
  # (ESC P/X/^/_ … ST), CSI (ESC [ params intermediates final), Fe two-char (ESC <byte>). The OSC/DCS
  # terminators AND the CSI final are OPTIONAL (`?`) so a MALFORMED/unterminated escape is stripped to
  # end-of-line too (else its param/title residue would leak as content). Only ACTUAL ESC bytes
  # trigger a strip, so real-review text (brackets, digits, `;`, even a literal "\033[0m" string) is
  # never touched.
  if LC_ALL=C sed -E $'s/\033\\][^\a\033]*(\a|\033\\\\)?//g; s/\033[PX^_][^\033]*(\033\\\\)?//g; s/\033\\[[0-9;?]*[ -\\/]*[@-~]?//g; s/\033[@-Z\\\\-_]//g' "$1" \
       | LC_ALL=C tr -cd '\012\040-\176' \
       | grep -vx ' *Reading additional input from stdin\.\.\. *' \
       | grep -q '[[:graph:]]'; then
    return 1
  fi
  return 0
}

# (`_is_positive_number` is defined ABOVE, before the numeric-env resolution it guards.)

# TERM the group leader was sent; give a brief grace, then KILL the whole group. $1 = pgid.
_grace_then_kill() {
  local pgid="$1" i=0
  while [ "$i" -lt 20 ] && kill -0 "$pgid" 2>/dev/null; do sleep 0.05; i=$((i + 1)); done
  kill -KILL -"$pgid" 2>/dev/null
}

# Reap a whole process GROUP if ANY member is still alive (keyed on GROUP liveness `kill -0 -pgid`,
# NOT the leader): TERM, brief grace, KILL. This is what supervises a codex that FORKS a background
# child in the SAME PGID and then self-exits — the leader `wait` reaps only the leader, leaving the
# child alive in the PGID. Called on EVERY terminal path (incl. clean OK) so no SAME-PGID descendant
# survives helper return (and none can append to raw.log after OK). A child that `setsid()`-detaches
# into a NEW session escapes this PGID reap — an ACCEPTED, out-of-scope residual (see the header
# CLASS-AUDIT note; the real codex CLI does not detach). No-op (returns fast) when the group is already
# empty, so it is idempotent with the watchdog kill paths that already group-killed. $1 = pgid.
_reap_pgid() {
  local pgid="$1" i=0
  kill -0 -"$pgid" 2>/dev/null || return 0     # group already empty — nothing to reap
  kill -TERM -"$pgid" 2>/dev/null
  while [ "$i" -lt 20 ] && kill -0 -"$pgid" 2>/dev/null; do sleep 0.05; i=$((i + 1)); done
  kill -KILL -"$pgid" 2>/dev/null
}

# A small jitter/backoff sleep, tied to the poll granularity (tiny under the test poll knob;
# ~15s in prod). Used for the probe retry backoff and the stall-retry jitter.
_jitter_sleep() { sleep "$POLL_SECS" 2>/dev/null; }

# ---- reaper (FIX C / round-6 MAJOR — AC-H21/H23 extended to the PROBE window) — a helper that is
#      itself killed or exits REAPS every codex process group it launched: the probe's `doctor`
#      group (PROBE_PGID) AND the dispatch's `codex exec` group (WATCH_PGID), plus the probe's
#      timeout-watcher. ONE trap is installed once (do_dispatch / do_probe, right after monitor
#      mode) and covers BOTH windows — so an external TERM DURING the doctor probe no longer leaks a
#      forking-doctor child (the pre-fix hole). The handler reaps whatever groups are currently
#      tracked, then (on TERM/INT/HUP) exits 128+signal so the supervisor dies cleanly. An
#      uncatchable SIGKILL is the accepted §A.4-2 residual — the trap cannot run. ----
PROBE_PGID=""; PROBE_WATCHER_PID=""; WATCH_PGID=""
_reap_groups() {
  # GROUP-kill each tracked group (the `-<pgid>` form) so a watcher's `sleep` child is reaped too,
  # never orphaned holding a pipe.
  [ -n "$PROBE_WATCHER_PID" ] && kill -KILL -"$PROBE_WATCHER_PID" 2>/dev/null
  [ -n "$PROBE_PGID" ] && { kill -TERM -"$PROBE_PGID" 2>/dev/null; kill -KILL -"$PROBE_PGID" 2>/dev/null; }
  [ -n "$WATCH_PGID" ] && { kill -TERM -"$WATCH_PGID" 2>/dev/null; kill -KILL -"$WATCH_PGID" 2>/dev/null; }
}
_install_reaper() {
  trap '_reap_groups' EXIT
  trap '_reap_groups; exit 130' INT
  trap '_reap_groups; exit 143' TERM
  trap '_reap_groups; exit 129' HUP
}

# ---- attempt log (§A.10) — one JSON line per op; CLOSED op enum probe|dispatch|kill|retry|degrade
#      (helper_error is coordinator-appended). Best-effort; never fatal. ----
_runid_from_attempt_log() {
  local b; b="$(basename "$ATTEMPT_LOG")"
  case "$b" in
    codex-attempts-*.jsonl) b="${b%.jsonl}"; printf '%s' "${b#codex-attempts-}" ;;
    *) printf '' ;;
  esac
}
_jstr() {   # JSON string (valid for ANY input), or `null` for empty. Escapes \ and " then ALL C0
            # control chars (\n/\r/\t readably, other 0x01-0x1F as \uXXXX) so every attempt-log field
            # is valid JSON regardless of input — a control char in a basename-derived runId or a
            # killed-log path would otherwise emit INVALID JSONL (round-5 MINOR). $1 = value.
  if [ -z "$1" ]; then printf 'null'; return; fi
  local s="$1"
  s="${s//\\/\\\\}"        # backslash FIRST (so the escapes we add below are not re-escaped)
  s="${s//\"/\\\"}"        # quote
  s="${s//$'\n'/\\n}"      # newline
  s="${s//$'\r'/\\r}"      # carriage return
  s="${s//$'\t'/\\t}"      # tab
  local i ch hex           # remaining C0 controls 0x01-0x1F (except \t \n \r) → \uXXXX (NUL can't be in a var)
  for i in {1..31}; do
    case $i in 9|10|13) continue ;; esac
    printf -v ch '%b' "\\$(printf '%03o' "$i")"
    printf -v hex '\\u%04x' "$i"
    s="${s//"$ch"/$hex}"
  done
  printf '"%s"' "$s"
}
_jnum() {   # JSON number, or `null` for empty. $1 = value.
  if [ -z "$1" ]; then printf 'null'; else printf '%s' "$1"; fi
}
# log_attempt op attempt outcome cause effort sandbox max_gap killed_log probe_rc rc
log_attempt() {
  [ -n "$ATTEMPT_LOG" ] || return 0
  local ts rid
  ts="$(date +%s 2>/dev/null)"
  rid="$(_runid_from_attempt_log)"
  {
    printf '{"ts":%s,"runId":%s,"scope":%s,"op":%s,"attempt":%s,"outcome":%s,"cause":%s,"effort":%s,"sandbox":%s,"max_gap_secs":%s,"stall_secs":%s,"backstop_secs":%s,"killed_log":%s,"probe_rc":%s,"rc":%s}\n' \
      "$(_jnum "$ts")" "$(_jstr "$rid")" "$(_jstr "$SCOPE")" "$(_jstr "$1")" "$(_jnum "$2")" \
      "$(_jstr "$3")" "$(_jstr "$4")" "$(_jstr "$5")" "$(_jstr "$6")" "$(_jnum "$7")" \
      "$(_jnum "$STALL_SECS")" "$(_jnum "$BACKSTOP_SECS")" "$(_jstr "$8")" "$(_jnum "$9")" "$(_jnum "${10}")"
  } >> "$ATTEMPT_LOG" 2>/dev/null
  return 0
}

# ---- marker writes (§A.9) — tmp+mv atomic; first line = the outcome token (byte-identical to
#      stdout); line 2 = the mandated warning. rc0 written, rc1 write FAILED (fail-closed). ----
write_marker() {   # $1=token $2=warning-line
  local tmp="$MARKER.tmp.$$"
  # A --marker path that is already a directory can never hold a regular file — fail closed
  # WITHOUT polluting it (an `mv file dir` would move the tmp INSIDE the dir, not replace it).
  [ -d "$MARKER" ] && return 1
  printf '%s\n%s\n' "$1" "$2" > "$tmp" 2>/dev/null || { rm -f "$tmp" 2>/dev/null; return 1; }
  # On a runtime mv failure (writable parent but ENOSPC / a marker made read-only after the
  # pre-check) UNLINK the orphan tmp before failing closed — no lingering `.tmp.<pid>` on the
  # STOP path (it could never false-satisfy codex_present, whose exact name differs, but is tidy).
  mv "$tmp" "$MARKER" 2>/dev/null || { rm -f "$tmp" 2>/dev/null; return 1; }
  [ -f "$MARKER" ] && [ -s "$MARKER" ]
}

# Emit a degraded outcome: write the marker, print the token, exit 1. On a marker-WRITE FAILURE
# (§A.9 fail-closed) print the SAME token + a stderr diagnostic + exit 1 with NO marker — the
# coordinator honors a degraded token ONLY with a present marker, so this fails the scope closed.
emit_degraded() {   # $1=token $2=warning-line
  if write_marker "$1" "$2"; then
    printf '%s\n' "$1"; exit 1
  fi
  echo "drive-codex.sh: marker write FAILED at $MARKER — fail-closed (NO marker written)" >&2
  printf '%s\n' "$1"; exit 1
}

emit_ok() { printf '%s\n' "OK"; exit 0; }

# ---- health probe (§A.4-1 / §A.5): bg `<cmd> doctor --json` in its OWN process group under
#      monitor mode, bounded by PROBE_TIMEOUT_SECS with a timed GROUP kill (never a bare PID —
#      a forking doctor shim must not leak a child). stdout is CAPTURED (never on the helper's
#      fd 1). Sets PROBE_RC. rc0 = probe OK. ----
PROBE_OUT=""
run_probe() {
  if [ -z "$PROBE_OUT" ]; then
    if [ -n "$RAW_LOG" ]; then PROBE_OUT="${RAW_LOG%.log}.probe.log"; else PROBE_OUT="$(dirname "$ATTEMPT_LOG")/codex-probe-$SCOPE.log"; fi
  fi
  # `< /dev/null`: never let doctor BLOCK reading an inherited open stdin (helper dispatched
  # from a backgrounded Bash whose fd 0 is a live-open fd). doctor is non-interactive.
  "$DRIVE_CODEX_CMD" doctor --json > "$PROBE_OUT" 2>&1 < /dev/null &
  local dpid=$! dpgid; dpgid=$dpid
  PROBE_PGID="$dpgid"   # FIX C: track the doctor group so the reaper trap covers the PROBE window —
                        # an external TERM during the probe must reap a forking doctor's child.
  ( sleep "$PROBE_TIMEOUT_SECS"
    kill -0 "$dpid" 2>/dev/null && { kill -TERM -"$dpgid" 2>/dev/null; sleep "$GRACE_SECS"; kill -KILL -"$dpgid" 2>/dev/null; }
  ) &
  PROBE_WATCHER_PID=$!   # its OWN pgid under monitor mode (== its pid)
  wait "$dpid" 2>/dev/null; PROBE_RC=$?
  # GROUP-kill the watcher (not a bare PID): a bare `kill $watcher` reaps only the subshell and
  # ORPHANS its `sleep $PROBE_TIMEOUT_SECS` child, which — having inherited the caller's stdout —
  # holds a command-substitution pipe open for the FULL timeout (a ~10s stall on every probe, and a
  # surviving probe child). Killing the group reaps the sleep too.
  kill -KILL -"$PROBE_WATCHER_PID" 2>/dev/null; wait "$PROBE_WATCHER_PID" 2>/dev/null
  kill -KILL -"$dpgid" 2>/dev/null   # reap any forked straggler in the probe's group
  PROBE_PGID=""; PROBE_WATCHER_PID=""   # FIX C: probe group fully reaped — clear so the reaper is a no-op
  [ "$PROBE_RC" = 0 ]
}

# run_probe once, then retry-once-with-backoff. rc0 = probe OK; rc1 = confirmed outage.
probe_with_retry() {
  run_probe && return 0
  _jitter_sleep
  run_probe && return 0
  return 1
}

# ----------------------------------------------------------------------------- #
# ONE supervised attempt (§A.4 steps 2-6). Launches codex in its OWN process group, watchdogs
# byte growth, classifies via `kill_confirmed`. Sets ATTEMPT_RESULT ∈
#   ok | exec-failed | killed-exec-failed | stall-kill | backstop-kill | internal-fault
# plus CODEX_RC, THIS_KILLED; grows the global round_was_killed / MAX_GAP / KILLED_LOGS.
# $1 = attempt index.
# ----------------------------------------------------------------------------- #
run_attempt() {
  local attempt="$1"
  local -a cmd=("$DRIVE_CODEX_CMD" exec)
  [ "$SANDBOX_FLAG_ON" = 1 ] && cmd+=(--sandbox "$RUNG")
  [ "$EFFORT_LOW" = 1 ] && cmd+=(-c "model_reasoning_effort=$EFFORT_TIER_LOW")
  # $PROMPT_TEXT was read + validated PRE-LAUNCH (FIX B) — reuse it, never a second cat that could
  # read-fail to "" and slip a degenerate empty prompt past the pre-launch guard.
  # `< /dev/null`: the prompt is passed as ARGV, so codex needs no stdin. Without this, a helper
  # dispatched from a backgrounded Bash whose fd 0 is an inherited live-open fd makes codex print
  # "Reading additional input from stdin..." and BLOCK/degenerate — it exits rc0 having written
  # only that ~39-byte banner and NO review (a silent false OK). /dev/null gives immediate EOF so
  # codex consumes only its argv prompt and produces the real review. (Fixes .harness/followups.md F5.)
  "${cmd[@]}" "$PROMPT_TEXT" > "$RAW_LOG" 2>&1 < /dev/null &
  local child=$! pgid; pgid=$child          # under monitor mode the job leader pid == its pgid
  # FIX C / round-6 MAJOR: track the codex group for the ONE installed reaper trap (do_dispatch),
  # so a helper that is itself killed/exits REAPS its codex child group instead of orphaning it.
  # (An uncatchable SIGKILL is the accepted §A.4-2 residual.)
  WATCH_PGID="$pgid"

  # TEST knob: a post-launch internal fault maps to CODEX_UNAVAILABLE(internal), never HELPER_ERROR.
  if [ "${DRIVE_CODEX_INJECT_INTERNAL_FAULT:-}" = 1 ]; then
    kill -TERM -"$pgid" 2>/dev/null; _grace_then_kill "$pgid"; wait "$child" 2>/dev/null
    _reap_pgid "$pgid"   # FIX A: reap any forked descendant on this terminal path too (uniform)
    WATCH_PGID=""
    ATTEMPT_RESULT=internal-fault; return
  fi

  # Open ONE read fd on the raw log (retry briefly until the child's `>` redirect created it).
  local opened=0 tries=0
  while [ "$tries" -lt 100 ]; do
    # Group-redirect so a FAILED `9<` (the child's `>` redirect not yet created the file) reports
    # to the already-suppressed fd 2, not the real stderr (a bare `exec 9<f 2>/dev/null` applies the
    # `2>` AFTER the failing `9<`, leaking the "No such file" to stderr and corrupting .err).
    if { exec 9<"$RAW_LOG"; } 2>/dev/null; then opened=1; break; fi
    tries=$((tries + 1)); sleep 0.02
  done

  local last=0 size zero_polls=0 total_polls=0 gap elapsed
  local watchdog_initiated=0 kill_reason="" target_alive=0
  while kill -0 "$child" 2>/dev/null; do
    sleep "$POLL_SECS"
    if [ "$opened" = 1 ]; then size="$(_fd_size 9)"; else size="$(stat -f %z "$RAW_LOG" 2>/dev/null || stat -c %s "$RAW_LOG" 2>/dev/null)"; fi
    total_polls=$((total_polls + 1))
    # awk float math — ALL values passed via `-v` (parameterized), never source-interpolated into the
    # program string (zero_polls/total_polls are internal integers; POLL/STALL/BACKSTOP_SECS are
    # pre-validated positive numbers — parameterizing is defense-in-depth so a future edit can't
    # reintroduce the env→awk injection class).
    if [ -z "$size" ]; then
      :   # poll ambiguity (fstat/stat error) → NO stall evidence; do not count, do not kill
    elif [ "$size" -gt "$last" ]; then
      gap="$(_awk -v z="$zero_polls" -v p="$POLL_SECS" 'BEGIN{print z*p}')"
      _awk -v g="$gap" -v mx="$MAX_GAP" 'BEGIN{exit !((g+0)>(mx+0))}' && MAX_GAP="$gap"
      zero_polls=0; last="$size"
    else
      zero_polls=$((zero_polls + 1))
    fi
    if [ "$WATCHDOG_ON" = 1 ]; then
      gap="$(_awk -v z="$zero_polls" -v p="$POLL_SECS" 'BEGIN{print z*p}')"
      if _awk -v g="$gap" -v s="$STALL_SECS" 'BEGIN{exit !((g+0)>=(s+0))}'; then watchdog_initiated=1; kill_reason=stall; break; fi
    fi
    elapsed="$(_awk -v t="$total_polls" -v p="$POLL_SECS" 'BEGIN{print t*p}')"
    if _awk -v e="$elapsed" -v b="$BACKSTOP_SECS" 'BEGIN{exit !((e+0)>=(b+0))}'; then watchdog_initiated=1; kill_reason=backstop; break; fi
  done
  [ "$opened" = 1 ] && exec 9<&-

  local kill_confirmed=0 wstatus
  if [ "$watchdog_initiated" = 1 ]; then
    kill -0 "$child" 2>/dev/null && target_alive=1   # was the target still alive at signal time?
    kill -TERM -"$pgid" 2>/dev/null
    _grace_then_kill "$pgid"
    wait "$child" 2>/dev/null; wstatus=$?
    # kill_confirmed = the signal hit a STILL-ALIVE target AND the wait-status is death-by-OUR-signal
    # (143=128+TERM, 137=128+KILL). A codex that self-exits in the kill window leaves kill_confirmed=0
    # and is classified by step 4 (its own rc/log), never mislabeled a stall (round-8 codex MAJOR).
    { [ "$target_alive" = 1 ] && { [ "$wstatus" = 143 ] || [ "$wstatus" = 137 ]; }; } && kill_confirmed=1
  else
    wait "$child" 2>/dev/null; wstatus=$?
  fi
  # FIX A (round-3, BLOCKING): supervise the whole PROCESS GROUP, not just the leader. A codex that
  # forks a background child in the SAME PGID then self-exits leaves that child alive — the
  # `wait`/watchdog track the LEADER only. Reap any surviving group member on EVERY terminal path
  # (incl. clean OK) BEFORE clearing WATCH_PGID / classifying, so no SAME-PGID descendant survives
  # helper return and none can append to raw.log after OK (which would corrupt the post-process read;
  # a `setsid()`-detached child escapes — accepted residual, header CLASS-AUDIT). Idempotent with the kill
  # paths (already group-killed ⇒ this no-ops).
  _reap_pgid "$pgid"
  WATCH_PGID=""   # codex + any descendant reaped — clear so the reaper trap is a no-op on exit
  CODEX_RC="$wstatus"

  if [ "$kill_confirmed" = 1 ]; then
    local killed="${RAW_LOG%.log}.killed-$attempt.log"
    mv "$RAW_LOG" "$killed" 2>/dev/null
    THIS_KILLED="$killed"
    KILLED_LOGS="${KILLED_LOGS:+$KILLED_LOGS,}$killed"
    round_was_killed=1
    if [ "$kill_reason" = stall ]; then ATTEMPT_RESULT=stall-kill; else ATTEMPT_RESULT=backstop-kill; fi
    return
  fi

  # kill_confirmed==0 → codex self-exited (step 4): OK iff rc==0 AND the log is non-empty AND it is
  # NOT a DEGENERATE banner-only log (the inherited-open-stdin residual — rc0 but no real review;
  # defense-in-depth for FIX-1, which prevents the banner-only degeneration at the source).
  if [ "$wstatus" = 0 ] && _log_nonempty "$RAW_LOG" && ! _log_banner_only "$RAW_LOG"; then ATTEMPT_RESULT=ok; return; fi
  # rc0 but banner-only ⇒ degenerate, NOT an exec failure — fail closed with an HONEST cause (rc was
  # 0, so `exec-failed` would mislead debugging toward spawn/absence). Gated on round_was_killed==0 so
  # a rc0-degenerate retry AFTER an earlier stall-kill keeps the killed-latch (falls through to
  # killed-exec-failed → CODEX_KILLED_TIMEOUT below), preserving that authority.
  if [ "$wstatus" = 0 ] && [ "$round_was_killed" = 0 ] && _log_banner_only "$RAW_LOG"; then ATTEMPT_RESULT=degenerate-log; return; fi
  # Availability failure (nonzero rc OR empty log). The killed-latch is authoritative here too:
  # a RETRY after an earlier stall-kill that exec-fails is terminal CODEX_KILLED_TIMEOUT, never
  # CODEX_UNAVAILABLE (round-3 Claude MAJOR — closes the step-4 escape).
  if [ "$round_was_killed" = 1 ]; then ATTEMPT_RESULT=killed-exec-failed; else ATTEMPT_RESULT=exec-failed; fi
}

# ----------------------------------------------------------------------------- #
# --mode dispatch (§A.4).
# ----------------------------------------------------------------------------- #
do_dispatch() {
  # ---- dispatch-required flags (PRE-LAUNCH; all HELPER_ERROR) ----
  case "$SCOPE_CLASS" in
    design|slice|phase|finalize) ;;
    *) helper_error "invalid --scope-class (want design|slice|phase|finalize): '$SCOPE_CLASS'" ;;
  esac
  [ -n "$RAW_LOG" ] || helper_error "--raw-log required for dispatch"
  [ -n "$MARKER" ] || helper_error "--marker required for dispatch"
  [ -n "$PROMPT_FILE" ] || helper_error "--prompt-file required for dispatch"
  # --prompt-file must name an EXISTING NON-EMPTY file (else a degenerate `codex exec ""`).
  [ -s "$PROMPT_FILE" ] || helper_error "--prompt-file missing or empty: '$PROMPT_FILE'"
  # FIX B (round-3, MAJOR): READ the prompt in the PRE-LAUNCH zone and FAIL CLOSED on a read error —
  # a non-empty but UNREADABLE file (chmod 000) passes `-s` but `cat`s to "" ⇒ a degenerate
  # empty-prompt exec ⇒ a false OK, defeating AC-H20. Require non-empty CONTENT after the read. Read
  # ONCE here; run_attempt reuses $PROMPT_TEXT (no second cat that could read-fail differently).
  PROMPT_TEXT="$(cat "$PROMPT_FILE" 2>/dev/null)" || helper_error "--prompt-file unreadable: '$PROMPT_FILE'"
  [ -n "$PROMPT_TEXT" ] || helper_error "--prompt-file has no readable content: '$PROMPT_FILE'"
  # --marker PARENT must be writable (early OK-path guard — a structurally-unwritable parent would
  # otherwise doom the eventual marker/post-process write and silently drop the codex voice). This
  # does NOT subsume the post-launch marker-WRITE fail-closed path (§A.9), which stays the authority
  # for a writable parent whose write still fails.
  local mparent; mparent="$(dirname "$MARKER")"
  [ -w "$mparent" ] || helper_error "--marker parent dir not writable: '$mparent'"

  # ---- policy resolution (§A.6): the coordinator passes FACTS; the helper applies policies ----
  # Sandbox rung resolution + PRE-LAUNCH validation. Precedence (§A.3): explicit --sandbox > env
  # DRIVE_CODEX_SANDBOX > scope-class default. The literal rung `off` (from EITHER the flag or the
  # env) is the kill switch ⇒ pass NO --sandbox flag. Any other resolved rung MUST be a member of
  # the closed set; a garbage rung (flag OR env) is a pre-launch config-resolution failure ⇒
  # HELPER_ERROR, codex un-spawned. (FIX B: explicit --sandbox beats env-off — resolve the override
  # FIRST. FIX D: validate the resolved rung, never pass garbage to codex.)
  local rung=""
  if [ "$SANDBOX_OVERRIDE_SET" = 1 ]; then
    rung="$SANDBOX_OVERRIDE"                       # explicit --sandbox wins over env (incl. env=off)
  elif [ -n "${DRIVE_CODEX_SANDBOX:-}" ]; then
    rung="$DRIVE_CODEX_SANDBOX"                     # env override (a rung, or `off`)
  else
    case "$SCOPE_CLASS" in
      design) rung="$SANDBOX_RUNG_DESIGN" ;;
      slice|phase|finalize) rung="$SANDBOX_RUNG_CODE" ;;
    esac
  fi
  case "$rung" in
    read-only|workspace-write|danger-full-access|off) ;;
    *) helper_error "invalid sandbox rung (want read-only|workspace-write|danger-full-access|off): '$rung'" ;;
  esac
  SANDBOX_FLAG_ON=1; RUNG=""
  if [ "$rung" = off ]; then SANDBOX_FLAG_ON=0; else RUNG="$rung"; fi

  local gate_enforced=0
  [ "$SECURITY_DIFF" = 1 ] && gate_enforced=1
  case "$SCOPE_CLASS" in phase|finalize) gate_enforced=1 ;; esac

  # effort carve-out (§F): down-tier IFF confirmation-class AND NOT security-diff AND the
  # --prior-codex scan is clean (non-degraded first line AND zero severity tags) AND tiering on.
  # REQUIRED-FILE-READ class (round-3): the `-r` guard makes an UNREADABLE --prior-codex fail toward
  # FULL effort (the conservative/closed direction — we can't confirm the prior is clean, so don't
  # down-tier), rather than the pre-fix behavior where an unreadable prior's failed `grep` fell
  # through to `|| EFFORT_LOW=1` and WRONGLY down-tiered. --prior-codex is optional/best-effort (not a
  # required input), so a read failure is NOT HELPER_ERROR — it just declines the down-tier.
  # round-6 FIX A: `_log_nonempty` also requires the prior be NON-EMPTY / non-whitespace — an EMPTY or
  # whitespace-only prior is NOT a real completed clean review, so it must fail toward FULL effort
  # (D-16 conservative direction), NOT fall through the clean-first-line/zero-tag scan into a down-tier.
  # FIX 3 (both design voices): a banner-only prior (rc0 degenerate) passes `_log_nonempty` + has
  # zero severity tags → would wrongly set EFFORT_LOW=1 (down-tier on a degenerate "clean" prior —
  # the WRONG direction). `! _log_banner_only` makes a degenerate prior fail toward FULL effort
  # (conservative). Low-stakes post-FIX-1 (priors are never banner-only once FIX-1 ships) but a cheap,
  # in-blast-radius belt-and-suspenders at the OTHER gate that consumes codex review output.
  EFFORT_LOW=0
  if [ "$TIERING_ON" = 1 ] && [ "$CONFIRMATION_CLASS" = 1 ] && [ "$SECURITY_DIFF" != 1 ] && [ -n "$PRIOR_CODEX" ] && [ -f "$PRIOR_CODEX" ] && [ -r "$PRIOR_CODEX" ] && _log_nonempty "$PRIOR_CODEX" && ! _log_banner_only "$PRIOR_CODEX"; then
    local fl; fl="$(head -n1 "$PRIOR_CODEX" 2>/dev/null)"
    case "$fl" in
      CODEX_UNAVAILABLE*|CODEX_KILLED_TIMEOUT*) : ;;   # degraded prior → full effort
      *) grep -Ewq 'BLOCKING|MAJOR|MINOR|NIT|P[123]' "$PRIOR_CODEX" 2>/dev/null || EFFORT_LOW=1 ;;
    esac
  fi
  local effort_desc="full" sandbox_desc="off"
  [ "$EFFORT_LOW" = 1 ] && effort_desc="$EFFORT_TIER_LOW"
  [ "$SANDBOX_FLAG_ON" = 1 ] && sandbox_desc="$RUNG"

  # FIX A (round-4, MAJOR): preflight --raw-log PRE-LAUNCH exactly like --marker/--attempt-log. A
  # directory / FIFO / socket / device --raw-log fails the exec-path `> "$RAW_LOG"` redirect at launch
  # (codex never starts) yet would be mis-classified `exec-failed` ⇒ CODEX_UNAVAILABLE + a non-empty
  # degraded marker `codex_present` accepts — silently dropping the codex voice as ordinary degradation
  # instead of the broken-helper STOP lane. The `-f` test rejects a dir/FIFO/socket/device and `-w`
  # rejects a read-only / read-only-FS regular file, so the exec-path redirect cannot fail into a false
  # degrade. (Deliberately do NOT pre-`:>`-truncate here — run_attempt's own `> "$RAW_LOG"` creates it,
  # and a pre-truncated inode perturbs the AC-H10 mv-aside fd-poll timing.)
  # round-5 MAJOR: ALSO require the raw-log's PARENT DIR writable — the probe writes a sibling
  # `${raw%.log}.probe.log` and killed-log renames (`${raw%.log}.killed-N.log`) land in that SAME dir,
  # so a writable raw.log inside a READ-ONLY dir would fail those POST-launch ⇒ the same false
  # CODEX_UNAVAILABLE degrade. Check the parent PRE-LAUNCH (mirrors the --marker parent guard) for BOTH
  # an existing and a to-be-created raw.log. Any failure ⇒ HELPER_ERROR, codex un-spawned.
  local rlparent; rlparent="$(dirname "$RAW_LOG")"
  [ -w "$rlparent" ] || helper_error "--raw-log parent dir not writable (probe sibling + killed-log renames need it): '$rlparent'"
  if [ -e "$RAW_LOG" ]; then
    { [ -f "$RAW_LOG" ] && [ -w "$RAW_LOG" ]; } || helper_error "--raw-log must be a writable regular file (not a dir/FIFO/socket/device): '$RAW_LOG'"
  fi

  set -m   # monitor mode: backgrounded jobs (probe + codex) get their OWN process group.
  _install_reaper   # FIX C: ONE trap for the whole dispatch — reaps the probe's doctor group AND the
                    # codex group on an external TERM/INT/HUP (or any exit), covering the PROBE window.

  round_was_killed=0; MAX_GAP=0; KILLED_LOGS=""; PROBE_RC=""

  # ---- Step 1: internal health probe (round_was_killed==0 — probe-as-outcome-writer) ----
  if ! command -v "$DRIVE_CODEX_CMD" >/dev/null 2>&1; then
    log_attempt probe 0 CODEX_UNAVAILABLE cli-absent "$effort_desc" "$sandbox_desc" "" "" "" ""
    emit_degraded CODEX_UNAVAILABLE "Codex unavailable (cli-absent): probe_rc=n/a live_attempt=skipped attempt_log=$ATTEMPT_LOG"
  fi
  local max_attempts="$MAX_ATTEMPTS"
  if probe_with_retry; then
    log_attempt probe 0 OK "" "$effort_desc" "$sandbox_desc" "" "" "$PROBE_RC" ""
  else
    log_attempt probe 0 outage probed-outage "$effort_desc" "$sandbox_desc" "" "" "$PROBE_RC" ""
    if [ "$gate_enforced" = 0 ]; then
      # non-gate-enforced (design/phasedesign, non-sensitive slice) → immediate CODEX_UNAVAILABLE
      log_attempt degrade 0 CODEX_UNAVAILABLE probed-outage "$effort_desc" "$sandbox_desc" "" "" "$PROBE_RC" ""
      emit_degraded CODEX_UNAVAILABLE "Codex unavailable (probed-outage): probe_rc=$PROBE_RC live_attempt=skipped attempt_log=$ATTEMPT_LOG"
    fi
    # gate-enforced (phase/finalize, sensitive slice) → ONE watchdog-bounded attempt (no stall-retry)
    max_attempts=1
  fi

  # ---- Steps 2-6: the supervised attempt loop ----
  local attempt=1
  while :; do
    run_attempt "$attempt"
    case "$ATTEMPT_RESULT" in
      ok)
        log_attempt dispatch "$attempt" OK "" "$effort_desc" "$sandbox_desc" "$MAX_GAP" "" "$PROBE_RC" "$CODEX_RC"
        emit_ok ;;
      internal-fault)
        log_attempt degrade "$attempt" CODEX_UNAVAILABLE internal "$effort_desc" "$sandbox_desc" "$MAX_GAP" "" "$PROBE_RC" "$CODEX_RC"
        emit_degraded CODEX_UNAVAILABLE "Codex unavailable (internal): probe_rc=$PROBE_RC live_attempt=failed attempt_log=$ATTEMPT_LOG" ;;
      degenerate-log)
        # rc0 but the raw log is only the codex stdin banner (no real review) — fail closed as an
        # HONEST degradation (CODEX_UNAVAILABLE token family, marker written), NOT a false OK.
        log_attempt degrade "$attempt" CODEX_UNAVAILABLE degenerate-log "$effort_desc" "$sandbox_desc" "$MAX_GAP" "" "$PROBE_RC" "$CODEX_RC"
        emit_degraded CODEX_UNAVAILABLE "Codex unavailable (degenerate-log: rc0 non-empty raw log with no real review content — banner-only, banner+junk/escapes, or whitespace-only; a zero-byte log is exec-failed): probe_rc=$PROBE_RC live_attempt=degenerate attempt_log=$ATTEMPT_LOG" ;;
      exec-failed)
        log_attempt degrade "$attempt" CODEX_UNAVAILABLE exec-failed "$effort_desc" "$sandbox_desc" "$MAX_GAP" "" "$PROBE_RC" "$CODEX_RC"
        emit_degraded CODEX_UNAVAILABLE "Codex unavailable (exec-failed): probe_rc=$PROBE_RC live_attempt=failed attempt_log=$ATTEMPT_LOG" ;;
      killed-exec-failed)
        # a RETRY after an earlier stall-kill that exec-failed → terminal CODEX_KILLED_TIMEOUT
        log_attempt degrade "$attempt" CODEX_KILLED_TIMEOUT stall "$effort_desc" "$sandbox_desc" "$MAX_GAP" "$KILLED_LOGS" "$PROBE_RC" "$CODEX_RC"
        emit_degraded CODEX_KILLED_TIMEOUT "Codex killed (stall): threshold=${STALL_SECS}s attempts=$attempt max_gap=${MAX_GAP}s killed_logs=$KILLED_LOGS attempt_log=$ATTEMPT_LOG" ;;
      backstop-kill)
        log_attempt kill "$attempt" CODEX_KILLED_TIMEOUT backstop "$effort_desc" "$sandbox_desc" "$MAX_GAP" "$THIS_KILLED" "$PROBE_RC" "$CODEX_RC"
        log_attempt degrade "$attempt" CODEX_KILLED_TIMEOUT backstop "$effort_desc" "$sandbox_desc" "$MAX_GAP" "$KILLED_LOGS" "$PROBE_RC" "$CODEX_RC"
        emit_degraded CODEX_KILLED_TIMEOUT "Codex killed (backstop): threshold=${BACKSTOP_SECS}s attempts=$attempt max_gap=${MAX_GAP}s killed_logs=$KILLED_LOGS attempt_log=$ATTEMPT_LOG" ;;
      stall-kill)
        log_attempt kill "$attempt" CODEX_KILLED_TIMEOUT stall "$effort_desc" "$sandbox_desc" "$MAX_GAP" "$THIS_KILLED" "$PROBE_RC" "$CODEX_RC"
        if [ "$attempt" -lt "$max_attempts" ]; then
          # probe-before-retry as a LAUNCH-GATE ONLY: it may SUPPRESS the next attempt on outage
          # but writes NO marker and NEVER switches the outcome family (round_was_killed stays 1).
          # Use the RETRYING `probe_with_retry` (NOT single-shot `run_probe`) so a transient probe blip
          # in the retry window does not falsely kill a recoverable round — §A.4-1 "the probe retries
          # once with backoff before an outage is confirmed" (round-7 FIX A). Log the launch-gate probe
          # outcome as an op=probe line, exactly like the initial probe path.
          if probe_with_retry; then
            log_attempt probe "$((attempt + 1))" OK "" "$effort_desc" "$sandbox_desc" "" "" "$PROBE_RC" ""
            log_attempt retry "$((attempt + 1))" "" stall "$effort_desc" "$sandbox_desc" "$MAX_GAP" "" "$PROBE_RC" ""
            _jitter_sleep
            attempt=$((attempt + 1)); continue
          fi
          log_attempt probe "$((attempt + 1))" outage probed-outage "$effort_desc" "$sandbox_desc" "" "" "$PROBE_RC" ""
        fi
        # retry suppressed by the launch-gate, exhausted, or unavailable → terminal KILLED
        log_attempt degrade "$attempt" CODEX_KILLED_TIMEOUT stall "$effort_desc" "$sandbox_desc" "$MAX_GAP" "$KILLED_LOGS" "$PROBE_RC" "$CODEX_RC"
        emit_degraded CODEX_KILLED_TIMEOUT "Codex killed (stall): threshold=${STALL_SECS}s attempts=$attempt max_gap=${MAX_GAP}s killed_logs=$KILLED_LOGS attempt_log=$ATTEMPT_LOG" ;;
      *)
        # unreachable by construction; fail closed as an availability failure
        emit_degraded CODEX_UNAVAILABLE "Codex unavailable (internal): probe_rc=$PROBE_RC live_attempt=failed attempt_log=$ATTEMPT_LOG" ;;
    esac
  done
}

# ----------------------------------------------------------------------------- #
# --mode probe (§A.5): health query only; writes NO marker.
# ----------------------------------------------------------------------------- #
do_probe() {
  set -m
  _install_reaper   # FIX C: reap the probe's doctor group on an external TERM during the probe window
  if ! command -v "$DRIVE_CODEX_CMD" >/dev/null 2>&1; then
    log_attempt probe 0 CODEX_UNAVAILABLE cli-absent full off "" "" "" ""
    printf '%s\n' "CODEX_UNAVAILABLE"; exit 1
  fi
  if probe_with_retry; then
    log_attempt probe 0 OK "" full off "" "" "$PROBE_RC" ""
    printf '%s\n' "OK"; exit 0
  fi
  log_attempt probe 0 CODEX_UNAVAILABLE probed-outage full off "" "" "$PROBE_RC" ""
  printf '%s\n' "CODEX_UNAVAILABLE"; exit 1
}

# ----------------------------------------------------------------------------- #
# PRE-LAUNCH validation of the resolved knobs (HELPER_ERROR-eligible zone — before probe/launch,
# before `set -m`; a failure exits 2 with NO marker and codex un-spawned).
# ----------------------------------------------------------------------------- #
# Every timing knob MUST be a strictly-positive number: `--poll-secs 0` (or a non-numeric value)
# would make `gap = zero_polls*POLL_SECS` and `elapsed = total_polls*POLL_SECS` stay 0 forever,
# disabling BOTH the stall kill AND the per-attempt backstop (a bounded-run bypass) and spinning
# `sleep 0`. Reject non-positive/non-numeric pre-launch.
_is_positive_number "$POLL_SECS"          || helper_error "--poll-secs must be a positive number: '$POLL_SECS'"
_is_positive_number "$STALL_SECS"         || helper_error "--stall-secs must be a positive number: '$STALL_SECS'"
_is_positive_number "$BACKSTOP_SECS"      || helper_error "--backstop-secs must be a positive number: '$BACKSTOP_SECS'"
_is_positive_number "$PROBE_TIMEOUT_SECS" || helper_error "--probe-timeout-secs must be a positive number: '$PROBE_TIMEOUT_SECS'"
case "$MAX_ATTEMPTS" in ''|*[!0-9]*) helper_error "--max-attempts must be a positive integer: '$MAX_ATTEMPTS'" ;; esac
[ "$MAX_ATTEMPTS" -ge 1 ] || helper_error "--max-attempts must be >= 1: '$MAX_ATTEMPTS'"

# --poll-secs must be strictly LESS than BOTH the stall AND the backstop threshold it guards. The
# watchdog SLEEPS `POLL_SECS` before each deadline check, so a poll >= a threshold sleeps PAST that
# deadline before ever testing it — the stall/backstop kill can never fire (a per-attempt-backstop
# bypass). All three are already validated strictly-positive numbers above, so `awk -v` (parameterized,
# never program interpolation) is safe. A mis-scaled poll is a config error ⇒ HELPER_ERROR pre-launch
# (codex un-spawned), same lane as a non-positive knob.
_awk -v p="$POLL_SECS" -v s="$STALL_SECS" -v b="$BACKSTOP_SECS" 'BEGIN{exit !((p+0)<(s+0) && (p+0)<(b+0))}' \
  || helper_error "--poll-secs ($POLL_SECS) must be strictly less than both --stall-secs ($STALL_SECS) and --backstop-secs ($BACKSTOP_SECS)"

# --attempt-log must be a REGULAR writable file (or creatable as one). A FIFO/socket/device would
# block the best-effort `>> "$ATTEMPT_LOG"` with no reader and WEDGE the helper before it emits any
# closed token. This pre-launch guard preserves the "best-effort, never fatal" contract for a
# regular file that later fails mid-run (that write still just no-ops).
if [ -e "$ATTEMPT_LOG" ]; then
  { [ -f "$ATTEMPT_LOG" ] && [ -w "$ATTEMPT_LOG" ]; } || helper_error "--attempt-log must be a writable regular file (not a FIFO/socket/device): '$ATTEMPT_LOG'"
else
  [ -w "$(dirname "$ATTEMPT_LOG")" ] || helper_error "--attempt-log parent dir not writable: '$ATTEMPT_LOG'"
fi

# --mode probe writes a sibling `codex-probe-<scope>.log` in the --attempt-log's dir (dispatch mode
# instead uses the R5-A-preflighted raw-log sibling). A writable --attempt-log FILE inside a
# READ-ONLY dir passes the check above, but the sibling create then fails at probe launch and a
# LOCAL fs fault would misclassify as a remote CODEX_UNAVAILABLE. Require the probe-log dir writable
# PRE-LAUNCH ⇒ HELPER_ERROR (broken-helper STOP lane) — the SAME class R5-A closed for dispatch's
# raw-log, now uniform across modes (dispatch always has a raw-log; only probe-mode falls back here).
if [ "$MODE" = probe ]; then
  if [ -n "$RAW_LOG" ]; then probe_log_dir="$(dirname "$RAW_LOG")"; else probe_log_dir="$(dirname "$ATTEMPT_LOG")"; fi
  [ -w "$probe_log_dir" ] || helper_error "--mode probe needs a writable dir for codex-probe-<scope>.log: '$probe_log_dir'"
fi

case "$MODE" in
  probe)    do_probe ;;
  dispatch) do_dispatch ;;
esac
