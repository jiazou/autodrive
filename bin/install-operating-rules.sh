#!/usr/bin/env bash
# Turnkey: point this machine's global ~/CLAUDE.md at this repo's canonical
# OPERATING.md, so every Claude session on this machine uses the same rules.
# The path is computed from where THIS repo lives — no manual editing needed.
# (The /drive pipeline is NOT imported globally; it stays opt-in, active only
#  when you work inside this repo.)
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
echo
echo "Operating rules are now active machine-wide."
echo "To run the /drive pipeline you also need gstack + codex — see README 'Setup'."
