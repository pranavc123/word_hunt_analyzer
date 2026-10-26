#!/bin/zsh
# Install / reload the Word Hunt server + worker as launchd agents (user-level, start at login).
# Reads WH_DATA, WH_DICT, WH_TOKEN from your environment (~/.zshrc). Run from anywhere:
#   zsh tools/launchd/install.sh
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
UV="$(command -v uv)"
: "${WH_DATA:?set WH_DATA in ~/.zshrc}"
: "${WH_TOKEN:?set WH_TOKEN in ~/.zshrc}"
WH_DICT="${WH_DICT:-$REPO/dictionaries/yawl.txt}"
AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$AGENTS" "$WH_DATA/logs"
(cd "$REPO" && "$UV" sync -q && "$UV" run alembic -c server/alembic.ini upgrade head)
for name in server worker; do
  label="com.wordhunt.$name"
  dest="$AGENTS/$label.plist"
  sed -e "s|__REPO__|$REPO|g" -e "s|__UV__|$UV|g" -e "s|__WH_DATA__|$WH_DATA|g" \
      -e "s|__WH_DICT__|$WH_DICT|g" -e "s|__WH_TOKEN__|$WH_TOKEN|g" \
      "$REPO/tools/launchd/$label.plist" > "$dest"
  chmod 600 "$dest"  # contains the token
  plutil -lint -s "$dest"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$dest"
  echo "loaded $label"
done
echo "logs: $WH_DATA/logs/{server,worker}.log"
