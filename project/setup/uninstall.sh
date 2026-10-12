#!/bin/bash
# uninstall.sh - stop and remove the launchd agent. Captured images are kept.
set -eu
LABEL="com.nilsechterhoff.whiteboard-capture"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST"
echo "Removed $LABEL. Capture folder left untouched."
