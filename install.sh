#!/bin/bash
# install.sh [CAPTURE_DIR] - install the capture service as a launchd agent (macOS).
set -eu

LABEL="com.nilsechterhoff.whiteboard-capture"
REPO="$(cd "$(dirname "$0")" && pwd)"
WBC_DIR="${1:-$HOME/WhiteboardCapture}"
WBC_CAMERA="${WBC_CAMERA:-NOVATEK J1455}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/whiteboard-capture.log"

[ "$(uname)" = "Darwin" ] || { echo "macOS only." >&2; exit 1; }
command -v imagesnap >/dev/null || { echo "imagesnap missing: brew install imagesnap" >&2; exit 1; }

if ! imagesnap -l | grep -qF -- "$WBC_CAMERA"; then
  echo "Warning: camera '$WBC_CAMERA' not listed now (unplugged or not in PC Camera mode?)."
  echo "Cameras seen:"; imagesnap -l
  echo "Set another name with: WBC_CAMERA='<name>' ./install.sh"
fi

# Escape & and | for sed; XML-escape & < > for the plist.
xml() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }
sedv() { printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'; }

mkdir -p "$WBC_DIR" "$(dirname "$PLIST")" "$(dirname "$LOG")"
chmod +x "$REPO/src/wbcapture.sh"

sed -e "s|__SCRIPT__|$(sedv "$(xml "$REPO/src/wbcapture.sh")")|" \
    -e "s|__WBC_DIR__|$(sedv "$(xml "$WBC_DIR")")|" \
    -e "s|__WBC_CAMERA__|$(sedv "$(xml "$WBC_CAMERA")")|" \
    -e "s|__LOG__|$(sedv "$(xml "$LOG")")|g" \
    "$REPO/launchd/$LABEL.plist.template" > "$PLIST"
plutil -lint "$PLIST" >/dev/null

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "Installed. Capture folder: $WBC_DIR"
echo "Log: $LOG   Status: cat '$WBC_DIR/status.txt'"
echo "If macOS asks for camera access, allow it once."
