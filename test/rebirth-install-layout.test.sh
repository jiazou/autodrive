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
#   4. statusline.sh's THRESHOLDS_FILE resolution, HONEST about both modes: (4a) from the
#      SOURCE TREE (direct invocation) it resolves to the bin/ sibling json — reds on a later
#      override; (4b) from the INSTALL (a symlink) BASH_SOURCE[0] is the symlink's dir, so the
#      json is NOT a sibling and the inline `case` fallback carries it — asserted by running
#      statusline through a real symlink; (4c) AC6 anti-drift pins the inline window == json
#      window, so the install's fallback yields the same answer.
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

# --- 4. statusline.sh THRESHOLDS_FILE resolution — the HONEST two-mode reality -----
# statusline resolves THRESHOLDS_FILE = dirname(BASH_SOURCE[0])/rebirth-thresholds.json.
# In bash, BASH_SOURCE[0] is the INVOCATION path, NOT the symlink-resolved target — so the
# json sibling is reachable ONLY when statusline runs from the SOURCE TREE (a direct
# bin/statusline.sh invocation). The INSTALLER symlinks it to ~/.claude/statusline.sh and
# settings.json runs it via that symlink, so at runtime dirname(BASH_SOURCE) = ~/.claude,
# where rebirth-thresholds.json is NOT a sibling — the installed statusline therefore relies
# on the INLINE `case` fallback (AC6 anti-drift: same numbers as the json). This section
# asserts BOTH truths instead of pinning only the source-tree path (which masked the install).

# 4a. SOURCE-TREE resolution: with BASH_SOURCE pinned to the repo bin/ statusline (a direct,
#     non-symlinked invocation), THRESHOLDS_FILE IS the bin/ sibling json. Eval the script's
#     own THRESHOLDS_FILE= assignment(s) — last wins at runtime, so a later override to a
#     copied/absolute/non-sibling path reds here.
statusline_effective=$(
  THRESHOLDS_FILE=""
  _bs0='${BASH_SOURCE[0]}'; _bs='$BASH_SOURCE'
  while IFS= read -r _line; do
    _line="${_line//"$_bs0"/$STATUSLINE}"
    _line="${_line//"$_bs"/$STATUSLINE}"
    # Strip a leading export/readonly/declare[ -flags] keyword so the override lands
    # in THIS scope (a prefixed eval can scope/protect the var and hide the override).
    _line="$(printf '%s' "$_line" | sed -E 's/^[[:space:]]*(export|readonly|declare([[:space:]]+-[A-Za-z]+)*)[[:space:]]+//')"
    eval "$_line"
  done < <(grep -E '^[[:space:]]*((export|readonly|declare([[:space:]]+-[A-Za-z]+)*)[[:space:]]+)?THRESHOLDS_FILE=' "$STATUSLINE")
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
check "statusline source-tree THRESHOLDS_FILE is the bin/ sibling json (direct invocation)" "${statusline_effective:-no}" "yes"

# 4b. INSTALLED-SYMLINK reality: build the actual installed layout (a symlink in a separate
#     dir -> the repo bin/ statusline, with NO rebirth-thresholds.json sibling next to the
#     symlink) and run statusline THROUGH the symlink. Its dirname(BASH_SOURCE) is the
#     symlink's dir, so the json sibling does NOT resolve there — the installed statusline
#     CANNOT read the json and MUST fall to the inline case. Assert that honestly: the
#     would-be json path next to the symlink is absent, and the script still renders a window
#     (proving the inline fallback carries it). Opus 4.8 -> inline 1_000_000 -> PCT 90.
LINK_DIR="$(mktemp -d)"
ln -sfn "$STATUSLINE" "$LINK_DIR/statusline.sh"
sibling_at_symlink="$( [ -f "$LINK_DIR/rebirth-thresholds.json" ] && echo present || echo absent )"
check "installed symlink has NO rebirth-thresholds.json sibling (json unreachable from install)" "$sibling_at_symlink" "absent"
TRANS_IL="$(mktemp)"
printf '{"type":"assistant","message":{"usage":{"input_tokens":900000,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}}}\n' > "$TRANS_IL"
installed_pct="$(
  printf '%s' "{\"model\":{\"display_name\":\"Opus 4.8\"},\"workspace\":{\"current_dir\":\"$LINK_DIR\"},\"transcript_path\":\"$TRANS_IL\"}" \
    | bash "$LINK_DIR/statusline.sh" 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' | grep -oE '[0-9]+%' | tr -d '%'
)"
# 900000/1_000_000 = 90% iff the inline Opus window (1_000_000) carried it (the json was
# unreachable from the symlink dir); a fallback to the 200_000 default would render 450%.
check "installed (symlinked) statusline falls to the inline case -> Opus window (PCT 90)" "${installed_pct:-NONE}" "90"
rm -rf "$LINK_DIR" "$TRANS_IL"

# 4c. AC5/AC6 anti-drift: the inline `case` window numbers the install relies on MUST equal the
#     json's, so the fallback yields the SAME answer as a source-tree json read. The ordered
#     two-rule table lists the 1M families in windows[0] (which precedes windows[1]) and the
#     200k families in windows[1]; everything unlisted resolves to the 1M default. Pin all THREE
#     numbers, each anchored on its SPECIFIC arm so the two 1M-valued lines (the explicit 1M
#     arm and the `*)` default) can't mask a drift: the default arm (the `*)` line), the inline
#     1M arm (a 1M-arm token, `"Fable 5"`) == json windows[0].window, and the inline 200k arm
#     (a 200k-arm token, `"Sonnet 4.5"`) == the json's Sonnet 4.5 window.
inline_default_window="$(grep -E '^[[:space:]]*\*\)' "$STATUSLINE" | grep -oE 'WINDOW=[0-9]+' | head -1 | sed 's/WINDOW=//')"
json_default_window="$(jq -r '.defaultWindow' "$DATA")"
check "AC6 anti-drift: inline default arm (*)) window == json defaultWindow (1M, fallback matches)" "${inline_default_window:-X}" "${json_default_window:-Y}"
inline_1m_window="$(grep -E '"Fable 5"' "$STATUSLINE" | grep -oE 'WINDOW=[0-9]+' | head -1 | sed 's/WINDOW=//')"
json_1m_window="$(jq -r '.windows[0].window' "$DATA")"
check "AC5 anti-drift: inline 1M arm window == json windows[0].window (1M rule)" "${inline_1m_window:-X}" "${json_1m_window:-Y}"
inline_sonnet_window="$(grep -E '"Sonnet 4.5"' "$STATUSLINE" | grep -oE 'WINDOW=[0-9]+' | head -1 | sed 's/WINDOW=//')"
json_sonnet_window="$(jq -r '.windows[] | select(.match | index("Sonnet 4.5")) | .window' "$DATA")"
check "AC6 anti-drift: inline 200k arm window == json Sonnet 4.5 window (200k rule)" "${inline_sonnet_window:-X}" "${json_sonnet_window:-Y}"

# --- 5. The installers deploy the rebirth files by REFERENCE, not by copy --
# The installers register the hook in-place and symlink statusline; they must NOT
# copy the rebirth files (or bin/ wholesale) to a non-sibling location, which would
# fork a stale copy off bin/ and break the sibling resolution. Catch the BROAD class,
# not one literal: any copy-like op (cp / cp -R/-r / install / rsync / ditto / a python
# shutil.copy*/copyfile/copyfileobj) whose SOURCE OR TARGET is a rebirth/hook/statusline
# file or the repo bin/ dir — INCLUDING WHEN THE PATH IS HELD IN A VARIABLE the installer
# assigned (e.g. `STATUSLINE_SRC="$REPO_DIR/bin/statusline.sh"; cp "$STATUSLINE_SRC" /x`).
#
# Why a variable-tracking pass, not a single line-grep: a copy whose argument is `$HOOK_PY`
# is indirected — the rebirth path is one assignment away — so a literal-only filter stays
# green on exactly the copy that breaks the layout. We first taint every var assigned a
# value that references bin/ or a rebirth file, then flag a copy op referencing a rebirth
# literal OR a tainted var. Precision: only the REPO bin/ counts — system paths
# (/usr/bin, /usr/local/bin, /bin, /sbin) and the two legit backups (`cp "$GLOBAL" ...` →
# ~/CLAUDE.md, `cp -- "$SETTINGS" ...` → settings.json) reference neither a rebirth file
# nor a tainted var, so they do not trip. Comments are stripped before scanning.
# The guard is a Python pass (robust variable tracking); written to a temp file and
# invoked normally — a heredoc nested in $(...) trips bash 3.2's paren matcher on the
# unbalanced parens in the Python body.
COPY_GUARD_PY="$(mktemp -t rebirth-copy-guard.XXXXXX.py)"
trap 'rm -f "$COPY_GUARD_PY"' EXIT
cat > "$COPY_GUARD_PY" <<'PY'
import re, sys

# A path token that designates the REPO bin/ or a rebirth/hook/statusline file.
# Anchored so system bins do NOT match: a `bin` segment counts only when it is
# $BIN/${BIN}, or a `bin` whose left boundary is start, quote, space, or `$VAR/`
# / `${VAR}/` (i.e. `$REPO_DIR/bin`) — never `/usr/bin`, `/usr/local/bin`, `/bin`.
# The `bin` is matched as a path component at its right boundary (a following `/`
# OR a word boundary: quote, space, end-of-token), so a wholesale `cp -R "$REPO_DIR/bin"
# /dest` with NO trailing slash is caught the same as `$REPO_DIR/bin/`.
REBIRTH_FILE = r'(rebirth-thresholds\.json|rebirth_thresholds\.py|drive-stop-hook\.py|statusline\.sh)'
REPO_BIN = r'(\$\{?BIN\}?|(?:\$\{?[A-Za-z_][A-Za-z0-9_]*\}?/)bin(?:/|\b)|(?<![/\w])bin(?:/|\b))'
SYS_BIN = re.compile(r'(^|[\s"\'=(])/(usr/(local/)?)?s?bin/')   # /usr/bin, /usr/local/bin, /bin, /sbin

def references_repo_bin(text):
    # Strip out any system-bin token first so its `bin/` can't satisfy REPO_BIN.
    scrubbed = SYS_BIN.sub(' /SYSBIN/ ', text)
    return re.search(REBIRTH_FILE, scrubbed) or re.search(REPO_BIN, scrubbed)

# Copy-class op detector (shell verbs at command position + python copy calls).
COPY_OP = re.compile(
    r'(^|[\s;|&(])(cp|install|rsync|ditto)([\s]|$)'
    r'|shutil\.(copy[a-z0-9_]*|copyfile)|copyfileobj'
)
# Both shell (`VAR=value`) and python (`var = value`) assignment forms — the latter has
# spaces around `=`, so an indirected `shutil.copy2(statusline_src, ...)` whose source var
# was set to a rebirth path is caught too. A leading shell declaration keyword
# (export/local/readonly/declare[ -flags]) before `NAME=` is allowed and skipped, so
# `export SRC="$HOOK_PY"` / `local SRC=...` taints SRC too — mirrors the THRESHOLDS_FILE
# replay prefix handling. Python `var = ...` has no such prefix, so that path is unaffected.
ASSIGN = re.compile(
    r'^[\s]*(?:(?:export|local|readonly|declare(?:[\s]+-[A-Za-z]+)*)[\s]+)?'
    r'([A-Za-z_][A-Za-z0-9_]*)[\s]*=[\s]*(.*)$')

def strip_comment(line):
    # drop a full-line comment; strip a trailing ` # ...` (space-anchored so a `#`
    # inside a path/quote is not mistaken for a comment start).
    if re.match(r'^[\s]*#', line):
        return ''
    return re.sub(r'\s#.*$', '', line)

hits = 0
for path in sys.argv[1:]:
    try:
        lines = open(path, encoding='utf-8').read().splitlines()
    except OSError:
        continue
    tainted = set()
    code = [strip_comment(l) for l in lines]
    # Collect every assignment as (lhs, rhs) once, then taint to a FIXPOINT so taint
    # propagates through ALIASES, not just one hop: a var is tainted if its RHS
    # references the repo bin/ or a rebirth file OR references an already-tainted var
    # (`$T`/`${T}` shell, bare `T` python). Iterating to a fixpoint catches a chain
    # `HOOK_PY=.../bin/...; SRC="$HOOK_PY"; X="$SRC"` — every link becomes tainted.
    assigns = []
    for l in code:
        m = ASSIGN.match(l)
        if m:
            assigns.append((m.group(1), m.group(2)))

    def refs_tainted(text):
        if not tainted:
            return False
        alt = '|'.join(re.escape(v) for v in tainted)
        rx = re.compile(r'\$\{?(' + alt + r')\}?|(?<![A-Za-z0-9_.])(' + alt + r')(?![A-Za-z0-9_])')
        return bool(rx.search(text))

    while True:
        grew = False
        for lhs, rhs in assigns:
            if lhs in tainted:
                continue
            if references_repo_bin(rhs) or refs_tainted(rhs):
                tainted.add(lhs)
                grew = True
        if not grew:
            break
    # A tainted var is referenced as `$v`/`${v}` (shell) OR as a bare identifier `v`
    # (python), the latter word-bounded so it cannot match a substring of another name.
    alt = '|'.join(re.escape(v) for v in tainted)
    var_ref = re.compile(r'\$\{?(' + alt + r')\}?|(?<![A-Za-z0-9_.])(' + alt + r')(?![A-Za-z0-9_])') if tainted else None
    # Pass 2: a copy op trips if it names a rebirth/bin literal OR a tainted var.
    for l in code:
        if not COPY_OP.search(l):
            continue
        if references_repo_bin(l) or (var_ref and var_ref.search(l)):
            hits += 1
print(hits)
PY
copy_into_bin="$(python3 "$COPY_GUARD_PY" "$INSTALL_RULES" "$INSTALL_HOOKS")"
check "no installer copy-op (cp/install/rsync/ditto/shutil) targets bin/ or a rebirth file (incl. via a variable)" "$copy_into_bin" "0"

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

# statusline is SYMLINKED into ~/.claude (ln -sfn) — deploy-by-reference, not a copy. Run
# via the symlink, dirname(BASH_SOURCE) is the symlink's dir (~/.claude), NOT the repo bin/,
# so the json sibling does NOT resolve from the install and the inline case carries it
# (proven by section 4b). This check pins only that statusline is symlinked (by-reference).
statusline_symlinked=$(grep -c 'ln -sfn "\$STATUSLINE_SRC"' "$INSTALL_RULES")
check "statusline symlinked into ~/.claude (deploy-by-reference, not copied)" "$( [ "$statusline_symlinked" -ge 1 ] && echo yes || echo no )" "yes"

# --- Summary --------------------------------------------------------------
echo "----------------------------------------"
echo "PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -eq 0 ] || exit 1
