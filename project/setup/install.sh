#!/bin/bash
# install.sh [CAPTURE_DIR] - install the capture service as a launchd agent (macOS).
# Default CAPTURE_DIR: the synced Nextcloud folder (see docs/decisions/0004).
set -eu

LABEL="com.nilsechterhoff.whiteboard-capture"
SETUP="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SETUP/../.." && pwd)"
WBC_DIR="${1:-$HOME/Library/CloudStorage/Nextcloud-cloud.echterhoff.dk-nilsechterhoff/Services/Whiteboard Capture}"
WBC_CAMERA="${WBC_CAMERA:-J1455}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/whiteboard-capture.log"

[ "$(uname)" = "Darwin" ] || { echo "macOS only." >&2; exit 1; }
command -v imagesnap >/dev/null || { echo "imagesnap missing: brew install imagesnap" >&2; exit 1; }

if ! imagesnap -l | grep -qF -- "$WBC_CAMERA"; then
  echo "Warning: camera '$WBC_CAMERA' not listed now (unplugged or not in PC Camera mode?)."
  echo "Cameras seen:"; imagesnap -l
  echo "Set another name with: WBC_CAMERA='<name>' project/setup/install.sh"
fi

# Escape & and | for sed; XML-escape & < > for the plist.
xml() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }
sedv() { printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'; }

mkdir -p "$WBC_DIR/latest" "$WBC_DIR/hourly" "$WBC_DIR/daily" "$(dirname "$PLIST")" "$(dirname "$LOG")"
chmod +x "$REPO/script/wbcapture.sh"

sed -e "s|__SCRIPT__|$(sedv "$(xml "$REPO/script/wbcapture.sh")")|" \
    -e "s|__WBC_DIR__|$(sedv "$(xml "$WBC_DIR")")|" \
    -e "s|__WBC_CAMERA__|$(sedv "$(xml "$WBC_CAMERA")")|" \
    -e "s|__LOG__|$(sedv "$(xml "$LOG")")|g" \
    "$SETUP/$LABEL.plist.template" > "$PLIST"
plutil -lint "$PLIST" >/dev/null

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "Installed. Capture folder: $WBC_DIR"
echo "Log: $LOG   Status: cat '$WBC_DIR/status.txt'"
echo "If macOS asks for camera access or for access to Nextcloud files, allow it once."
