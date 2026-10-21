#!/bin/bash
# install.sh [CAPTURE_DIR] - install the capture service as a launchd agent (macOS).
# Default CAPTURE_DIR: the synced Nextcloud folder (see docs/decisions/0004).
set -eu

LABEL="com.nilsechterhoff.whiteboard-capture"
SETUP="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SETUP/../.." && pwd)"
WBC_DIR="${1:-$HOME/Library/CloudStorage/Nextcloud-cloud.echterhoff.dk-nilsechterhoff/Services/Whiteboard Capture}"
WBC_CAMERA_SERIAL="${WBC_CAMERA_SERIAL:-7B5E845E}"   # Logitech C930e (see docs/decisions/0006)
WBC_FFMPEG="${WBC_FFMPEG:-$(command -v ffmpeg 2>/dev/null || true)}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/whiteboard-capture.log"

[ "$(uname)" = "Darwin" ] || { echo "macOS only." >&2; exit 1; }
[ -n "$WBC_FFMPEG" ] && [ -x "$WBC_FFMPEG" ] || { echo "ffmpeg missing: brew install ffmpeg, or set WBC_FFMPEG=/path/to/ffmpeg" >&2; exit 1; }

if ! "$WBC_FFMPEG" -hide_banner -f avfoundation -list_devices true -i "" 2>&1 | grep -qF -- "serial:$WBC_CAMERA_SERIAL"; then
  echo "Warning: camera serial '$WBC_CAMERA_SERIAL' not listed now (unplugged?)."
  echo "Set another serial with: WBC_CAMERA_SERIAL='<serial>' project/setup/install.sh"
fi

# Escape & and | for sed; XML-escape & < > for the plist.
xml() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }
sedv() { printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'; }

mkdir -p "$WBC_DIR/latest" "$WBC_DIR/hourly" "$WBC_DIR/daily" "$(dirname "$PLIST")" "$(dirname "$LOG")"
chmod +x "$REPO/script/wbcapture.sh"

sed -e "s|__SCRIPT__|$(sedv "$(xml "$REPO/script/wbcapture.sh")")|" \
    -e "s|__WBC_DIR__|$(sedv "$(xml "$WBC_DIR")")|" \
    -e "s|__WBC_CAMERA_SERIAL__|$(sedv "$(xml "$WBC_CAMERA_SERIAL")")|" \
    -e "s|__WBC_FFMPEG__|$(sedv "$(xml "$WBC_FFMPEG")")|" \
    -e "s|__LOG__|$(sedv "$(xml "$LOG")")|g" \
    "$SETUP/$LABEL.plist.template" > "$PLIST"
plutil -lint "$PLIST" >/dev/null

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "Installed. Capture folder: $WBC_DIR"
echo "Log: $LOG   Status: cat '$WBC_DIR/status.txt'"
echo "If macOS asks for camera access (for ffmpeg) or for access to Nextcloud files, allow it once."
