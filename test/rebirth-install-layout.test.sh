#!/usr/bin/env bash
# AC12: the rebirth machinery needs NO new installer wiring — it ships with the
# repo's bin/ that the installers already symlink (statusline) / register-in-place
# (drive-stop-hook.py). This test pins the SIBLING LAYOUT that makes that true: the
# rebirth data file + resolver live next to the hook + statusline in bin/, reachable
# by the relative-path expressions those consumers use. If a future move breaks the
# sibling relationship the relative-path resolution silently breaks at runtime —
# this guard fails loudly there instead.
#
# What it asserts (each a real layout invariant, not a tautology):
#   1. bin/rebirth-thresholds.json + bin/rebirth_thresholds.py exist as siblings of
#      bin/drive-stop-hook.py + bin/statusline.sh (all four in the SAME dir).
#   2. drive-stop-hook.py imports rebirth_thresholds via sys.path.insert(dirname(__file__))
#      — i.e. it expects the resolver as a bin/ sibling, not an installed copy.
#   3. rebirth_thresholds.py's EFFECTIVE THRESHOLDS_PATH (imported and read at runtime)
#      resolves to the bin/ sibling json — reds on any later override to a copied/
#      absolute/non-sibling path, not just on the textual expression disappearing.
#   4. statusline.sh's EFFECTIVE THRESHOLDS_FILE (its last winning assignment, evaled
#      with BASH_SOURCE pinned) resolves to the bin/ sibling json — same effective-path
#      assertion, reds on a later override.
#   5. The installers do NOT copy the rebirth files (or bin/ wholesale) to a non-sibling
#      location: NO copy-like op (cp / cp -R/-r / install / rsync / ditto / python
#      shutil.copy*) references bin/ or a rebirth file. The stop hook is registered as an
#      in-place `python3 "<repo>/bin/drive-stop-hook.py"` command and statusline is
#      symlinked — bin/ is canonical-by-reference and the siblings resolve with no copy.
#
# bash 3.2-safe; read-only (touches no settings.json, runs no installer).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BIN="$REPO_DIR/bin"

HOOK="$BIN/drive-stop-hook.py"
STATUSLINE="$BIN/statusline.sh"
RESOLVER="$BIN/rebirth_thresholds.py"
DATA="$BIN/rebirth-thresholds.json"
INSTALL_RULES="$BIN/install-operating-rules.sh"
INSTALL_HOOKS="$BIN/install-drive-hooks.sh"

PASS=0
FAIL=0
check() { # check <desc> <actual> <expected>
  if [ "$2" = "$3" ]; then
    echo "PASS: $1"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $1 (expected '$3', got '$2')"
    FAIL=$((FAIL + 1))
  fi
}

# --- 1. The four files are siblings in bin/ -------------------------------
check "rebirth data file exists in bin/"      "$( [ -f "$DATA" ]       && echo yes || echo no )" "yes"
check "rebirth resolver exists in bin/"       "$( [ -f "$RESOLVER" ]   && echo yes || echo no )" "yes"
check "drive-stop-hook.py exists in bin/"     "$( [ -f "$HOOK" ]       && echo yes || echo no )" "yes"
check "statusline.sh exists in bin/"          "$( [ -f "$STATUSLINE" ] && echo yes || echo no )" "yes"

# All four share the SAME parent directory (the sibling invariant). Comparing
# resolved dirnames catches a future move of any one file out of bin/.
dir_of() { ( cd "$(dirname "$1")" && pwd ); }
DATA_DIR="$(dir_of "$DATA")"
RESOLVER_DIR="$(dir_of "$RESOLVER")"
HOOK_DIR="$(dir_of "$HOOK")"
STATUSLINE_DIR="$(dir_of "$STATUSLINE")"
check "rebirth data file is a sibling of drive-stop-hook.py" "$DATA_DIR"      "$HOOK_DIR"
check "rebirth resolver is a sibling of drive-stop-hook.py"  "$RESOLVER_DIR"  "$HOOK_DIR"
check "statusline.sh is a sibling of drive-stop-hook.py"     "$STATUSLINE_DIR" "$HOOK_DIR"
check "all rebirth siblings live in bin/"                    "$DATA_DIR"      "$BIN"

# --- 2. drive-stop-hook.py expects the resolver as a bin/ sibling ---------
# It inserts its OWN dir onto sys.path before importing rebirth_thresholds.
sys_path_sibling=$(grep -c 'sys\.path\.insert(0, os\.path\.dirname(os\.path\.abspath(__file__)))' "$HOOK")
check "stop-hook puts its own dir on sys.path (sibling import)" "$( [ "$sys_path_sibling" -ge 1 ] && echo yes || echo no )" "yes"
imports_resolver=$(grep -c 'import rebirth_thresholds' "$HOOK")
check "stop-hook imports rebirth_thresholds (sibling module)" "$( [ "$imports_resolver" -ge 1 ] && echo yes || echo no )" "yes"

# --- 3. rebirth_thresholds.py resolves the json to its bin/ sibling --------
# Assert the EFFECTIVE runtime path, not just that a sibling-style expression
# appears: import the resolver and read the THRESHOLDS_PATH it actually computes.
# A later reassignment to a copied/absolute/non-sibling path reds here (the appears-
# somewhere grep would stay green). Resolved through dirname so a symlinked bin/
# compares equal to its physical location.
resolver_effective=$(python3 - "$RESOLVER" "$BIN" <<'PY' 2>/dev/null
import importlib.util, os, sys
resolver, want_dir = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("rebirth_thresholds", resolver)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
p = mod.THRESHOLDS_PATH
got_dir = os.path.realpath(os.path.dirname(p))
print("yes" if (got_dir == os.path.realpath(want_dir)
                and os.path.basename(p) == "rebirth-thresholds.json") else "no")
PY
)
check "resolver's effective THRESHOLDS_PATH is the bin/ sibling json" "${resolver_effective:-no}" "yes"

# --- 4. statusline.sh resolves the json to its bin/ sibling ----------------
# Assert the EFFECTIVE runtime path the script computes for THRESHOLDS_FILE, not
# just that a dirname(BASH_SOURCE) expression appears. Eval the script's own
# assignment(s) for THRESHOLDS_FILE with BASH_SOURCE pinned to the real statusline,
# taking the LAST assignment that wins at runtime — so a later override to a
# copied/absolute/non-sibling path reds here. Then resolve through dirname.
statusline_effective=$(
  THRESHOLDS_FILE=""
  # Replay every THRESHOLDS_FILE= assignment in source order; the last one wins,
  # exactly as it would at runtime. ${BASH_SOURCE[0]} / $BASH_SOURCE are textually
  # substituted with the real statusline path (the interpreter does not let a caller
  # override the BASH_SOURCE call-stack array inside eval), so dirname(BASH_SOURCE)
  # resolves to bin/ just as it does when the script runs.
  _bs0='${BASH_SOURCE[0]}'; _bs='$BASH_SOURCE'
  while IFS= read -r _line; do
    _line="${_line//"$_bs0"/$STATUSLINE}"
    _line="${_line//"$_bs"/$STATUSLINE}"
    eval "$_line"
  done < <(grep -E '^[[:space:]]*THRESHOLDS_FILE=' "$STATUSLINE")
  if [ -n "$THRESHOLDS_FILE" ]; then
    got_dir="$( cd "$(dirname "$THRESHOLDS_FILE")" 2>/dev/null && pwd -P )"
    if [ "$got_dir" = "$( cd "$BIN" && pwd -P )" ] \
       && [ "$(basename "$THRESHOLDS_FILE")" = "rebirth-thresholds.json" ]; then
      echo yes
    else
      echo no
    fi
  else
    echo no
  fi
)
check "statusline's effective THRESHOLDS_FILE is the bin/ sibling json" "${statusline_effective:-no}" "yes"

# --- 5. The installers deploy the rebirth files by REFERENCE, not by copy --
# The installers register the hook in-place and symlink statusline; they must NOT
# copy the rebirth files (or bin/ wholesale) to a non-sibling location, which would
# fork a stale copy off bin/ and break the sibling resolution. Catch the BROAD class,
# not one literal: any copy-like operation (cp / cp -R/-r / install / rsync / ditto /
# a python shutil.copy*/copyfile) whose line references bin/ or a rebirth file. The
# two legit backup copies (`cp "$GLOBAL" ...`, `cp -- "$SETTINGS" ...`) name ~/CLAUDE.md
# and settings.json — neither touches bin/ or a rebirth file, so they do not match;
# the symlink (`ln -sfn`) and backup `mv` lines are not copy verbs at all.
#
# Two-stage match per line: (a) it invokes a copy verb, AND (b) it references bin/ or a
# rebirth file. Comments are stripped first (leading-# lines and trailing ` #...`) so a
# narrating comment that merely mentions `cp ... bin` is not a false positive.
copy_into_bin=$(
  for f in "$INSTALL_RULES" "$INSTALL_HOOKS"; do
    [ -f "$f" ] || continue
    # drop full-line comments, then strip trailing comments, then scan code only.
    grep -vE '^[[:space:]]*#' "$f" \
      | sed -E 's/[[:space:]]#.*$//' \
      | grep -E '(^|[[:space:];|&(])(cp|install|rsync|ditto)([[:space:]]|$)|shutil\.(copy[a-z]*|copyfile)|copyfileobj' \
      | grep -E '/bin([/"'"'"' ]|$)|(^|[^[:alnum:]_])bin/|rebirth-thresholds\.json|rebirth_thresholds\.py|drive-stop-hook\.py|statusline\.sh|\$\{?BIN\}?'
  done | wc -l | tr -d ' '
)
check "no installer copy-op (cp/install/rsync/ditto/shutil) targets bin/ or a rebirth file" "$copy_into_bin" "0"

# Positive evidence the deployment is by-reference: the hook is registered as an in-place
# `python3 "<repo>/bin/drive-stop-hook.py"` command and statusline is symlinked (ln -sfn).
data_copied=$( { grep -E 'cp .*rebirth-thresholds\.json' "$INSTALL_RULES" "$INSTALL_HOOKS"; } 2>/dev/null | wc -l | tr -d ' ')
check "no installer copies rebirth-thresholds.json (canonical-by-reference)" "$data_copied" "0"
resolver_copied=$( { grep -E 'cp .*rebirth_thresholds\.py' "$INSTALL_RULES" "$INSTALL_HOOKS"; } 2>/dev/null | wc -l | tr -d ' ')
check "no installer copies rebirth_thresholds.py (canonical-by-reference)" "$resolver_copied" "0"

# The Stop hook is registered as an in-place reference to the repo's bin/ script
# (python3 "<repo>/bin/drive-stop-hook.py"), so its dirname(__file__) sibling
# resolution lands on the same bin/ that holds the rebirth files — no copy.
hook_registered_inplace=$(grep -c 'cmd = f.python3 "{hook_py}"' "$INSTALL_RULES")
check "stop hook registered as in-place bin/ reference (not copied)" "$( [ "$hook_registered_inplace" -ge 1 ] && echo yes || echo no )" "yes"

# statusline is SYMLINKED into ~/.claude (ln -sfn), so dirname(BASH_SOURCE) of the
# symlink target is the repo bin/ — the rebirth-thresholds.json sibling resolves.
statusline_symlinked=$(grep -c 'ln -sfn "\$STATUSLINE_SRC"' "$INSTALL_RULES")
check "statusline symlinked into ~/.claude (sibling json resolves)" "$( [ "$statusline_symlinked" -ge 1 ] && echo yes || echo no )" "yes"

# --- Summary --------------------------------------------------------------
echo "----------------------------------------"
echo "PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -eq 0 ] || exit 1
