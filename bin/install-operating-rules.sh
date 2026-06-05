#!/usr/bin/env bash
# Turnkey: point this machine's global ~/CLAUDE.md at this repo's canonical
# OPERATING.md, so every Claude session on this machine uses the same rules.
# The path is computed from where THIS repo lives — no manual editing needed.
# Also registers the /drive pipeline commands globally (symlinked into
# ~/.claude/commands/) so /drive — and its stage runners — are discoverable from
# any directory, not only inside this repo. Symlinks the global status line too,
# so usage/limits render in every session.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPERATING="$REPO_DIR/OPERATING.md"
GLOBAL="$HOME/CLAUDE.md"

[ -f "$OPERATING" ] || { echo "error: OPERATING.md not found at $OPERATING" >&2; exit 1; }

if [ -f "$GLOBAL" ]; then
  BACKUP="$GLOBAL.bak.$(date +%Y%m%d-%H%M%S)"
  cp "$GLOBAL" "$BACKUP"
  echo "Backed up existing ~/CLAUDE.md -> $BACKUP"
fi

cat > "$GLOBAL" <<EOF
# CLAUDE.md (global) — machine-local pointer

My Claude operating rules are canonical in the autodrive repo's OPERATING.md.
This file imports them so they apply in every session on this machine.
Edit rules in the repo's OPERATING.md, not here. Re-run bin/install-operating-rules.sh
if you move the clone.

@$OPERATING
EOF

echo "Wrote ~/CLAUDE.md -> @$OPERATING"

# Install bundled skills (e.g. /decant, referenced by OPERATING.md) into
# ~/.claude/skills/ via symlink, so those references resolve on a fresh checkout.
SKILLS_SRC="$REPO_DIR/skills"
SKILLS_DST="$HOME/.claude/skills"
if [ -d "$SKILLS_SRC" ]; then
  mkdir -p "$SKILLS_DST"
  BK="$HOME/.claude/skill-backups"   # OUTSIDE skills/, so a backup is never re-registered as a skill
  for s in "$SKILLS_SRC"/*/; do
    s="${s%/}"; name="$(basename "$s")"; target="$SKILLS_DST/$name"
    if [ -e "$target" ] && [ ! -L "$target" ]; then
      mkdir -p "$BK"; mv "$target" "$BK/$name.$(date +%Y%m%d-%H%M%S)"
      echo "Backed up existing skill: $name -> $BK"
    fi
    ln -sfn "$s" "$target"
    echo "Linked skill: $name -> repo"
  done
fi

# Register the /drive pipeline commands globally (symlink into ~/.claude/commands/)
# so /drive and its stage runners (/drive-plan /drive-implement /drive-review
# /drive-harden /drive-ship) are discoverable
# from any directory. Claude Code finds project commands only by walking UP from the
# launch dir to the repo root — never down into a subdirectory — so without this the
# commands are invisible unless you launch claude inside this repo.
CMDS_SRC="$REPO_DIR/.claude/commands"
CMDS_DST="$HOME/.claude/commands"
if [ -d "$CMDS_SRC" ]; then
  mkdir -p "$CMDS_DST"
  BKC="$HOME/.claude/command-backups"   # OUTSIDE commands/, so a backup is never re-registered
  for c in "$CMDS_SRC"/*.md; do
    [ -e "$c" ] || continue
    name="$(basename "$c")"; target="$CMDS_DST/$name"
    if [ -e "$target" ] && [ ! -L "$target" ]; then
      mkdir -p "$BKC"; mv "$target" "$BKC/$name.$(date +%Y%m%d-%H%M%S)"
      echo "Backed up existing command: $name -> $BKC"
    fi
    ln -sfn "$c" "$target"
    echo "Linked command: /${name%.md} -> repo"
  done
fi

# Symlink the global status line into ~/.claude (shows dir/git/model/context% +
# $/day·$/hr + block%/week% toward plan limits). settings.json keeps its own
# statusLine entry; we only point it at the symlink, hinting if it's not set yet.
STATUSLINE_SRC="$REPO_DIR/bin/statusline.sh"
STATUSLINE_DST="$HOME/.claude/statusline.sh"
if [ -f "$STATUSLINE_SRC" ]; then
  mkdir -p "$HOME/.claude"
  if [ -e "$STATUSLINE_DST" ] && [ ! -L "$STATUSLINE_DST" ]; then
    BKS="$HOME/.claude/statusline-backups"
    mkdir -p "$BKS"; mv "$STATUSLINE_DST" "$BKS/statusline.sh.$(date +%Y%m%d-%H%M%S)"
    echo "Backed up existing statusline.sh -> $BKS"
  fi
  ln -sfn "$STATUSLINE_SRC" "$STATUSLINE_DST"
  echo "Linked status line -> repo"
  if ! grep -q '"statusLine"' "$HOME/.claude/settings.json" 2>/dev/null; then
    echo "  to enable it, add to ~/.claude/settings.json:"
    echo "    \"statusLine\": { \"type\": \"command\", \"command\": \"$STATUSLINE_DST\" }"
  fi
fi

# Register the /drive autonomous-continuation Stop hook in ~/.claude/settings.json.
# It only ever acts during an active /drive run owned by the firing session, fails
# open on every error, and self-disarms at stage=done — safe for all other sessions.
# Idempotent + atomic; never aborts the install if settings.json is unparseable.
HOOK_PY="$REPO_DIR/bin/drive-stop-hook.py"
if [ -f "$HOOK_PY" ]; then
  python3 - "$HOOK_PY" <<'PY' || true
import json, os, sys
hook_py = sys.argv[1]
cmd = f'python3 "{hook_py}"'
path = os.path.expanduser("~/.claude/settings.json")
settings = {}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as fh:
            settings = json.load(fh)
    except (ValueError, OSError) as e:
        print(f"  drive Stop hook: could not parse {path} ({e}); add it manually.")
        sys.exit(0)
arr = settings.setdefault("hooks", {}).setdefault("Stop", [])
if any("drive-stop-hook.py" in json.dumps(e) for e in arr):
    print("  drive Stop hook already registered — no change")
    sys.exit(0)
arr.append({"hooks": [{"type": "command", "command": cmd}]})
tmp = path + ".tmp"
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(settings, fh, indent=2)
    fh.write("\n")
    fh.flush(); os.fsync(fh.fileno())
os.replace(tmp, path)
print("  registered /drive Stop hook in settings.json")
PY
fi

echo
echo "Operating rules + bundled skills + /drive commands + status line are active machine-wide."
echo "The /drive autonomous-continuation Stop hook is registered (no-op outside an"
echo "active /drive run). Disable per-run: set autoContinue:false in the run's"
echo "state.json. Remove globally: delete the drive-stop-hook.py entry from"
echo "~/.claude/settings.json hooks.Stop."
echo "To run the /drive pipeline you also need gstack + codex — see README 'Installation'."
