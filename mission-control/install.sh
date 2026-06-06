#!/usr/bin/env bash
# Mission Control — installer. DEPLOYS the code from this repo into the places
# macOS / Claude Code expect (real copies, not symlinks), so the live harness keeps
# working no matter which branch this repo is checked out on. Re-run after editing
# the repo to redeploy. Idempotent. Runtime data lives in ~/mission-control and is
# never touched by reinstalls.
set -euo pipefail
MC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # this repo's mission-control dir
DATA="$HOME/mission-control"                          # live deploy + runtime data (not in repo)
echo "Mission Control install — source: $MC  →  deploy: $DATA"

# 1. deploy code (real copies; leaves bindings.jsonl / status.jsonl / *.log in place)
mkdir -p "$DATA"
rm -rf "$DATA/bin" "$DATA/swiftbar-plugins"
cp -R "$MC/bin" "$DATA/bin"
cp -R "$MC/swiftbar-plugins" "$DATA/swiftbar-plugins"
rm -rf "$DATA/bin/__pycache__"

# 1b. persist the vault config so the launchd job + SwiftBar plugin — which run
# with a BARE environment and do NOT read your shell profile — resolve the same
# vault as your interactive shell. Captures whatever MC_VAULT/MC_VAULT_NAME are
# set in THIS shell now; re-run after you change them. (An env var still wins at
# runtime; this file is the fallback vault_tasks.py reads.)
CFG="$DATA/config"
if [ -n "${MC_VAULT:-}" ] || [ -n "${MC_VAULT_NAME:-}" ]; then
  # Carry forward a previously-persisted value when its env var is UNSET this run, so a
  # re-run with only one of the two vars set does not silently drop the other.
  old_vault="" old_vault_name=""
  if [ -f "$CFG" ]; then
    old_vault="$(sed -n 's/^MC_VAULT=//p' "$CFG" | head -n1)"
    old_vault_name="$(sed -n 's/^MC_VAULT_NAME=//p' "$CFG" | head -n1)"
  fi
  v="${MC_VAULT:-$old_vault}"; vn="${MC_VAULT_NAME:-$old_vault_name}"
  : > "$CFG"
  [ -n "$v" ]  && printf 'MC_VAULT=%s\n'      "$v"  >> "$CFG"
  [ -n "$vn" ] && printf 'MC_VAULT_NAME=%s\n' "$vn" >> "$CFG"
  echo "  wrote vault config → $CFG"
elif [ -f "$CFG" ]; then
  echo "  kept existing vault config → $CFG"
else
  echo "  no MC_VAULT set; using default ~/Documents/Vault (set MC_VAULT and re-run to change)"
fi

# 2. skills (real copies — every dir under skills/, so new skills deploy automatically)
mkdir -p "$HOME/.claude/skills"
for d in "$MC"/skills/*/; do
  s=$(basename "$d")
  rm -rf "$HOME/.claude/skills/$s"
  cp -R "$d" "$HOME/.claude/skills/$s"
done

# 3. CLI on PATH (point at the deploy, not the repo)
mkdir -p "$HOME/.local/bin"
ln -sfn "$DATA/bin/mc" "$HOME/.local/bin/mc"
ln -sfn "$DATA/bin/today.py" "$HOME/.local/bin/today"

# 4. 6:45am launchd job (render template → ~/Library/LaunchAgents, reload)
LA="$HOME/Library/LaunchAgents"; mkdir -p "$LA"
PLIST="$LA/com.autodrive.missioncontrol.morning.plist"
sed "s#__HOME__#$HOME#g" "$MC/launchd/com.autodrive.missioncontrol.morning.plist" > "$PLIST"
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || true

# 5. SwiftBar menu bar (point at the plugin dir + make sure it's actually running)
chmod +x "$DATA/swiftbar-plugins/"*.sh
defaults write com.ameba.SwiftBar PluginDirectory "$DATA/swiftbar-plugins" 2>/dev/null || true
if [ -d "/Applications/SwiftBar.app" ]; then
  open -a SwiftBar 2>/dev/null || true   # idempotent: launches if down, no-op if up
fi

# 6. passive-capture hooks (idempotent merge into settings.json)
python3 "$DATA/bin/install_hooks.py" "$DATA"

chmod +x "$DATA/bin/mc" "$DATA/bin/"*.sh "$DATA/bin/"*.py
echo "✓ deployed. Try:  mc today"
