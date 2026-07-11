#!/usr/bin/env bash
# drive-portability-lint.sh — ADVISORY pre-push scan for commands the `macos-latest` CI runner lacks.
#
# The autodrive CI bash-suite runs on macos-latest (a CLEAN macOS runner). A test/script using a
# command that macOS does not ship (present locally only via homebrew) passes locally but is
# command-not-found on CI (empty output → spurious red). This lint flags that class BEFORE push so a
# reviewer catches it at Gate B, saving a push→CI→red→fix round-trip.
#
# ADVISORY BY DESIGN (both design voices): exit 0 ALWAYS — it never STOPs a ship (a grep heuristic
# lacks the authority to hard-block a shippable run). drive-ship surfaces its output at Gate B as a
# WARNING. The real gate is drive-ci-wait.sh (the empirical run on the actual macos-latest runner).
#
# Scope: only class-(i) — binaries ENTIRELY ABSENT on macos-latest, where a command-position match is
# a reliable signal. NOT class-(ii) (sed/awk/date/realpath — those EXIST on macOS and differ only in
# GNU-only flags, which a command-position grep cannot distinguish → would false-warn; that's
# drive-ci-wait's job on the real runner).
#
# Abstain-biased: skips a denylisted word when it is guarded (`command -v X` / `which X` / `type X`),
# a local function def (`X()`), a `VAR=` assignment, a `--flag`, or a comment — a portable construct
# must not warn.
#
# Usage:  drive-portability-lint.sh <file.sh> [file.sh ...]
#   (drive-ship passes the changed test/*.sh + bin/*.sh; caller computes the list.)
# Prints `file:line: <cmd> — not on macos-latest ...` per hit; exit 0 always. No files → exit 0.
#
# ADVISORY RESIDUALS (acceptable — exit 0, the CI-wait is the real gate): abstains are PER-LINE (a real
# hit sharing a line with a `command -v`/`--flag`/`VAR=` is suppressed), and heredoc PAYLOAD text can
# false-warn (no heredoc tracking in a line grep). Both are low-harm for an advisory warning.
set -uo pipefail

# class-(i) macOS-absent binaries (extend as new ones bite; keep to ENTIRELY-absent tools).
DENY="timeout gtimeout setsid sha256sum sha512sum sha1sum md5sum nproc tac \
gsed gawk gdate gtail ghead gstat gtr gcut greadlink grealpath gfind gxargs gwc gsort guniq gwatch"

hits=0
for f in "$@"; do
  [ -f "$f" ] || continue
  for cmd in $DENY; do
    # command-position occurrences: at line start, or after ; | & ( { ` $( , or after then/do/else.
    # (grep -nE gives file line numbers; the cmd must be followed by a word boundary.)
    while IFS=: read -r ln text; do
      [ -n "$ln" ] || continue
      # --- abstain filters (a portable/benign use must NOT warn) ---
      case "$text" in
        \#*) continue ;;                                   # comment-only line
        *"command -v $cmd"*|*"which $cmd"*|*"type $cmd"*|*"hash $cmd"*) continue ;;  # capability guard
        *"$cmd()"*|*"$cmd ()"*|*"function $cmd"*) continue ;;  # local shadowing function def
        *"--$cmd"*) continue ;;                            # part of a --flag
        *"$cmd="*) continue ;;                             # variable assignment (VAR=... not command)
      esac
      printf '%s:%s: %s — not on macos-latest (BSD/coreutils gap); use a portable alt or the tool'\''s own bound\n' "$f" "$ln" "$cmd"
      hits=$((hits + 1))
    done < <(grep -nE "(^|[;&|(\`{}]|\\\$\(|(^|[[:space:]])(then|do|else|if|while|until|xargs)[[:space:]])[[:space:]]*${cmd}([[:space:]]|\$|[;&|<>)])" "$f" 2>/dev/null)
  done
done

[ "$hits" -gt 0 ] && echo "drive-portability-lint: $hits advisory hit(s) — verify each is macOS-safe before merge (ADVISORY, not a block)." >&2
exit 0
