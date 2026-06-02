#!/usr/bin/env bash
# Turnkey: point this machine's global ~/CLAUDE.md at this repo's canonical
# OPERATING.md, so every Claude session on this machine uses the same rules.
# The path is computed from where THIS repo lives — no manual editing needed.
# Also registers the /drive pipeline commands globally (symlinked into
# ~/.claude/commands/) so /drive — and its stage runners — are discoverable from
# any directory, not only inside this repo.
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

My Claude operating rules are canonical in the claude-harness repo's OPERATING.md.
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
# so /drive and its stage runners (/plan /implement /review /ship) are discoverable
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

echo
echo "Operating rules + bundled skills + /drive commands are active machine-wide."
echo "To run the /drive pipeline you also need gstack + codex — see README 'Setup'."
