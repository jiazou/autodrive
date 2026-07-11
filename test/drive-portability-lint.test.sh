#!/usr/bin/env bash
# Plain-bash test suite for bin/drive-portability-lint.sh — the ADVISORY macOS-absent-command scan.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SUT="$ROOT/bin/drive-portability-lint.sh"
PASS=0; FAIL=0
WORK="$(mktemp -d "${TMPDIR:-/tmp}/drive-plint-test.XXXXXX")"
trap 'rm -rf "$WORK" 2>/dev/null' EXIT
pass() { PASS=$((PASS+1)); printf 'PASS: %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf 'FAIL: %s\n' "$1"; }
has()  { case "$2" in *"$3"*) pass "$1";; *) fail "$1 (missing [$3] in [$2])";; esac; }
hasnt(){ case "$2" in *"$3"*) fail "$1 (unexpected [$3] in [$2])";; *) pass "$1";; esac; }

mkf() { local p="$WORK/$1"; shift; printf '%s\n' "$@" > "$p"; printf '%s' "$p"; }

# --- FLAG cases (command-position, unguarded) ---
F="$(mkf flag.sh 'timeout 30 mycmd' 'gsed -i s/a/b/ f' 'x=$(nproc)' 'foo | tac' 'setsid daemon')"
OUT="$("$SUT" "$F" 2>&1)"; RC=$?
has  "flags timeout"   "$OUT" "timeout"
has  "flags gsed"      "$OUT" "gsed"
has  "flags nproc (in \$())" "$OUT" "nproc"
has  "flags tac (after pipe)" "$OUT" "tac"
has  "flags setsid"    "$OUT" "setsid"
if [ "$RC" = 0 ]; then pass "ADVISORY: exit 0 even with hits"; else fail "exit $RC not 0 (must be advisory)"; fi

# --- ABSTAIN cases (portable/benign — must NOT flag) ---
A="$(mkf abstain.sh \
  '# timeout in a comment' \
  'if command -v timeout >/dev/null; then timeout 5 x; fi' \
  'mytimeout=timeout' \
  'run --timeout 5 cmd' \
  'timeout() { echo shadow; }' \
  'which gsed >/dev/null && gsed x')"
OUT="$("$SUT" "$A" 2>&1)"
hasnt "abstains comment"                 "$OUT" "abstain.sh:1"
hasnt "abstains command -v guard"        "$OUT" "abstain.sh:2"
hasnt "abstains VAR=timeout assignment"  "$OUT" "abstain.sh:3"
hasnt "abstains --timeout flag"          "$OUT" "abstain.sh:4"
hasnt "abstains local function def"      "$OUT" "abstain.sh:5"
hasnt "abstains which-guarded gsed"      "$OUT" "abstain.sh:6"

# --- clean file / no shell files / missing file ---
C="$(mkf clean.sh 'set -e' 'sed -i.bak s/a/b/ f' 'awk "{print}" f' 'echo hi')"
OUT="$("$SUT" "$C" 2>&1)"; hasnt "clean file (bare sed/awk exist on macOS) ⇒ no hit" "$OUT" "clean.sh:"
OUT="$("$SUT" "$WORK/does-not-exist.sh" 2>&1)"; RC=$?
if [ "$RC" = 0 ] && [ -z "$OUT" ]; then pass "missing file ⇒ skip, exit 0, no output"; else fail "missing file mishandled (rc=$RC out=$OUT)"; fi
OUT="$("$SUT" 2>&1)"; RC=$?
if [ "$RC" = 0 ]; then pass "no args ⇒ exit 0"; else fail "no args exit $RC"; fi

# --- class-(ii) NOT flagged (sed/awk/date/realpath exist on macOS; GNU-flags are (b)'s job) ---
D="$(mkf classii.sh 'sed -i s/a/b/ f' 'date -d yesterday' 'realpath ./x' 'awk BEGIN{}')"
OUT="$("$SUT" "$D" 2>&1)"
hasnt "does NOT flag bare sed (class-ii)" "$OUT" "classii.sh"

echo ""
echo "===================================================================="
printf 'drive-portability-lint.test.sh: %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
