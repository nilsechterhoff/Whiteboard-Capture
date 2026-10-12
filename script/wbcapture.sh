#!/bin/bash
# wbcapture.sh - whiteboard capture service (see docs/decisions/0002 and 0004).
#
# Loop: check camera -> take a frame every WBC_LIVE_INTERVAL s or on
# capture.request -> update latest/latest.jpg, hourly/, daily/ -> prune -> status.txt.
# Written for macOS bash 3.2; also runs on Linux (used by tests/).

set -u

# Default: the synced Nextcloud folder (path contains spaces; always quoted).
WBC_DIR="${WBC_DIR:-$HOME/Library/CloudStorage/Nextcloud-cloud.echterhoff.dk-nilsechterhoff/Services/Whiteboard Capture}"
WBC_CAMERA="${WBC_CAMERA:-J1455}"
WBC_LIVE_INTERVAL="${WBC_LIVE_INTERVAL:-30}"
WBC_POLL="${WBC_POLL:-1}"
WBC_CAMERA_RETRY="${WBC_CAMERA_RETRY:-5}"
WBC_KEEP_HOURLY="${WBC_KEEP_HOURLY:-12}"
WBC_KEEP_DAILY="${WBC_KEEP_DAILY:-7}"
WBC_WARMUP="${WBC_WARMUP:-1}"
IMAGESNAP="${IMAGESNAP:-imagesnap}"
# Test hook only: file holding a fake epoch time. Unset in production.
WBC_NOW_FILE="${WBC_NOW_FILE:-}"

STATUS="$WBC_DIR/status.txt"
LATEST="$WBC_DIR/latest/latest.jpg"
REQUEST="$WBC_DIR/capture.request"
# Trailing "~" keeps sync clients (Nextcloud excludes *~) away from temp files.
TMP_IMG="$WBC_DIR/.wbc-frame.jpg~"
TMP_STATUS="$WBC_DIR/.wbc-status.txt~"

log() { echo "$(fmt_epoch "$(now)" '+%Y-%m-%d %H:%M:%S') $*"; }

now() {
  if [ -n "$WBC_NOW_FILE" ] && [ -s "$WBC_NOW_FILE" ]; then cat "$WBC_NOW_FILE"; else date +%s; fi
}

# fmt_epoch EPOCH FORMAT - BSD date (macOS) first, GNU date as fallback.
fmt_epoch() {
  date -r "$1" "$2" 2>/dev/null || date -d "@$1" "$2"
}

write_status() {
  printf '%s %s\n' "$1" "$(fmt_epoch "$(now)" '+%Y-%m-%d %H:%M:%S')" > "$TMP_STATUS" &&
    mv -f "$TMP_STATUS" "$STATUS"
}

camera_present() {
  "$IMAGESNAP" -l 2>/dev/null | grep -qF -- "$WBC_CAMERA"
}

capture() {
  rm -f "$TMP_IMG"
  "$IMAGESNAP" -q -w "$WBC_WARMUP" -d "$WBC_CAMERA" "$TMP_IMG" >/dev/null 2>&1 &&
    [ -s "$TMP_IMG" ] &&
    mv -f "$TMP_IMG" "$LATEST"
}

# prune DIR KEEP - names sort by time, so delete all but the newest KEEP.
prune() {
  local dir="$1" keep="$2" total
  total=$(ls -1 "$dir" 2>/dev/null | grep -c '\.jpg$')
  [ "$total" -gt "$keep" ] || return 0
  ls -1 "$dir" | grep '\.jpg$' | sort | head -n $((total - keep)) |
    while IFS= read -r f; do rm -f "$dir/$f"; done
}

update_tiers() {
  local t hourly daily
  t=$(now)
  hourly="$WBC_DIR/hourly/$(fmt_epoch "$t" '+%Y-%m-%d_%H').jpg"
  daily="$WBC_DIR/daily/$(fmt_epoch "$t" '+%Y-%m-%d').jpg"
  [ -e "$hourly" ] || cp "$LATEST" "$hourly"
  [ -e "$daily" ] || cp "$LATEST" "$daily"
  prune "$WBC_DIR/hourly" "$WBC_KEEP_HOURLY"
  prune "$WBC_DIR/daily" "$WBC_KEEP_DAILY"
}

cleanup() { rm -f "$TMP_IMG" "$TMP_STATUS"; write_status "STOPPED"; log "stopped"; exit 0; }

main() {
  mkdir -p "$WBC_DIR/latest" "$WBC_DIR/hourly" "$WBC_DIR/daily" || exit 1
  trap cleanup TERM INT
  log "started: dir=$WBC_DIR camera='$WBC_CAMERA' interval=${WBC_LIVE_INTERVAL}s"

  local last=0 last_state="" t
  while :; do
    if ! camera_present; then
      if [ "$last_state" != "CAMERA_NOT_FOUND" ]; then log "camera not found"; fi
      write_status "CAMERA_NOT_FOUND"; last_state="CAMERA_NOT_FOUND"
      sleep "$WBC_CAMERA_RETRY"
      continue
    fi

    t=$(now)
    if [ -e "$REQUEST" ] || [ $((t - last)) -ge "$WBC_LIVE_INTERVAL" ]; then
      if capture; then
        update_tiers
        rm -f "$REQUEST"   # only on success; on failure status.txt explains
        write_status "OK"
        if [ "$last_state" != "OK" ]; then log "capturing"; fi
        last_state="OK"; last=$t
      else
        write_status "CAPTURE_FAILED"
        if [ "$last_state" != "CAPTURE_FAILED" ]; then log "capture failed"; fi
        last_state="CAPTURE_FAILED"
        sleep "$WBC_CAMERA_RETRY"
        continue
      fi
    fi
    sleep "$WBC_POLL"
  done
}

main "$@"
