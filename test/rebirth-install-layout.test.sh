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
#   3. rebirth_thresholds.py resolves rebirth-thresholds.json relative to its OWN
#      dirname (dirname(__file__)/rebirth-thresholds.json) — sibling, not cwd/abspath.
#   4. statusline.sh resolves rebirth-thresholds.json relative to its OWN dirname
#      (dirname(BASH_SOURCE)/rebirth-thresholds.json) — sibling, not a copied path.
#   5. The installers do NOT copy these files (no install step deploys them): the
#      stop hook is registered as an in-place `python3 "<repo>/bin/drive-stop-hook.py"`
#      command and statusline is symlinked — so bin/ is canonical-by-reference and the
#      siblings resolve with no install action.
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

# --- 3. rebirth_thresholds.py resolves the json relative to its own dir ----
# THRESHOLDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rebirth-thresholds.json")
resolver_sibling=$(grep -A1 'THRESHOLDS_PATH' "$RESOLVER" | grep -c 'os\.path\.dirname(os\.path\.abspath(__file__))')
check "resolver builds json path from dirname(__file__)" "$( [ "$resolver_sibling" -ge 1 ] && echo yes || echo no )" "yes"
resolver_names_json=$(grep -c '"rebirth-thresholds\.json"' "$RESOLVER")
check "resolver names rebirth-thresholds.json as the sibling file" "$( [ "$resolver_names_json" -ge 1 ] && echo yes || echo no )" "yes"

# --- 4. statusline.sh resolves the json relative to its own dir -----------
# THRESHOLDS_FILE="$(dirname "${BASH_SOURCE[0]}")/rebirth-thresholds.json"
statusline_sibling=$(grep -c 'dirname "\${BASH_SOURCE\[0\]}")/rebirth-thresholds\.json' "$STATUSLINE")
check "statusline resolves json from dirname(BASH_SOURCE) (sibling)" "$( [ "$statusline_sibling" -ge 1 ] && echo yes || echo no )" "yes"

# --- 5. The installers deploy the rebirth files by REFERENCE, not by copy --
# No installer copies the rebirth data file or resolver anywhere; the hook is
# registered as an in-place command and statusline is symlinked. So a `cp` of
# either rebirth file would be a regression (it would fork a stale copy off bin/).
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
