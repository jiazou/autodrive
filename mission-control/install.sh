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

# 2. skills (real copies)
mkdir -p "$HOME/.claude/skills"
for s in harvest standup weekly; do
  rm -rf "$HOME/.claude/skills/$s"
  cp -R "$MC/skills/$s" "$HOME/.claude/skills/$s"
done

# 3. CLI on PATH (point at the deploy, not the repo)
mkdir -p "$HOME/.local/bin"
ln -sfn "$DATA/bin/mc" "$HOME/.local/bin/mc"
ln -sfn "$DATA/bin/today.py" "$HOME/.local/bin/today"

# 4. 6:45am launchd job (render template → ~/Library/LaunchAgents, reload)
LA="$HOME/Library/LaunchAgents"; mkdir -p "$LA"
PLIST="$LA/com.jiazou.missioncontrol.morning.plist"
sed "s#__HOME__#$HOME#g" "$MC/launchd/com.jiazou.missioncontrol.morning.plist" > "$PLIST"
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
