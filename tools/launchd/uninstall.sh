#!/bin/zsh
# Stop and remove the Word Hunt launchd agents.
for name in server worker; do
  label="com.wordhunt.$name"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null && echo "stopped $label"
  rm -f "$HOME/Library/LaunchAgents/$label.plist"
done
