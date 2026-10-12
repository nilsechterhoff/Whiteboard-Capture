#!/bin/bash
# wbcapture.sh - whiteboard capture service (see docs/decisions/0002, 0004, 0005).
#
# Loop: when a frame is due (every WBC_LIVE_INTERVAL s or on capture.request):
# check camera -> take a frame (with time limit) -> update latest/latest.jpg,
# hourly/, daily/ -> prune -> status.txt. On failure the real imagesnap error
# is logged and the next attempt waits WBC_FAIL_RETRY s.
# Only one instance runs at a time (lock in WBC_TMP).
# Written for macOS bash 3.2; also runs on Linux (used by tests/).

set -u

# Default: the synced Nextcloud folder (path contains spaces; always quoted).
WBC_DIR="${WBC_DIR:-$HOME/Library/CloudStorage/Nextcloud-cloud.echterhoff.dk-nilsechterhoff/Services/Whiteboard Capture}"
WBC_CAMERA="${WBC_CAMERA:-J1455}"
WBC_LIVE_INTERVAL="${WBC_LIVE_INTERVAL:-20}"
WBC_POLL="${WBC_POLL:-1}"
WBC_CAMERA_RETRY="${WBC_CAMERA_RETRY:-5}"
WBC_FAIL_RETRY="${WBC_FAIL_RETRY:-30}"
WBC_CAPTURE_TIMEOUT="${WBC_CAPTURE_TIMEOUT:-20}"
WBC_LOCK_WAIT="${WBC_LOCK_WAIT:-30}"
WBC_KEEP_HOURLY="${WBC_KEEP_HOURLY:-12}"
WBC_KEEP_DAILY="${WBC_KEEP_DAILY:-7}"
WBC_WARMUP="${WBC_WARMUP:-1}"
# Local scratch space (fixed /tmp so manual runs and the service share one lock).
WBC_TMP="${WBC_TMP:-/tmp}"
IMAGESNAP="${IMAGESNAP:-imagesnap}"
# Test hook only: file holding a fake epoch time. Unset in production.
WBC_NOW_FILE="${WBC_NOW_FILE:-}"

STATUS="$WBC_DIR/status.txt"
LATEST="$WBC_DIR/latest/latest.jpg"
LATEST_TMP="$WBC_DIR/latest/.latest.jpg~"   # same folder -> atomic rename
REQUEST="$WBC_DIR/capture.request"
TMP_STATUS="$WBC_DIR/.wbc-status.txt~"
# imagesnap writes outside the synced folder, with a real .jpg extension.
TMP_IMG="$WBC_TMP/wbcapture-frame.jpg"
TMP_ERR="$WBC_TMP/wbcapture-imagesnap.err"
LOCK="$WBC_TMP/wbcapture.lock"

CHILD=""       # pid of the running child (imagesnap or sleep), for cleanup
LAST_ERR=""    # error text of the last failed capture
HAVE_LOCK=0

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

# nap SECONDS - sleep that a stop signal can interrupt.
nap() {
  sleep "$1" &
  CHILD=$!
  wait "$CHILD" 2>/dev/null
  CHILD=""
}

# run_limited SECONDS CMD... - run CMD, kill it after SECONDS. Returns 124 on timeout.
# (macOS has no `timeout` command.)
run_limited() {
  local secs="$1" i=0 rc
  shift
  "$@" &
  CHILD=$!
  while kill -0 "$CHILD" 2>/dev/null; do
    if [ "$i" -ge $((secs * 10)) ]; then
      kill "$CHILD" 2>/dev/null; sleep 0.5; kill -9 "$CHILD" 2>/dev/null
      wait "$CHILD" 2>/dev/null
      CHILD=""
      return 124
    fi
    sleep 0.1
    i=$((i + 1))
  done
  wait "$CHILD"; rc=$?
  CHILD=""
  return "$rc"
}

# acquire_lock - only one instance; a lock left by a dead process is taken over.
acquire_lock() {
  local p
  if mkdir "$LOCK" 2>/dev/null; then echo $$ > "$LOCK/pid"; HAVE_LOCK=1; return 0; fi
  p=$(cat "$LOCK/pid" 2>/dev/null)
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
    log "already running (pid $p); not starting a second instance"
    return 1
  fi
  rm -rf "$LOCK"
  mkdir "$LOCK" 2>/dev/null && echo $$ > "$LOCK/pid" && HAVE_LOCK=1
}

camera_present() {
  run_limited 10 "$IMAGESNAP" -l > "$TMP_ERR" 2>&1 && grep -qF -- "$WBC_CAMERA" "$TMP_ERR"
}

capture() {
  local rc
  rm -f "$TMP_IMG" "$TMP_ERR"
  run_limited "$WBC_CAPTURE_TIMEOUT" "$IMAGESNAP" -q -w "$WBC_WARMUP" -d "$WBC_CAMERA" "$TMP_IMG" > "$TMP_ERR" 2>&1
  rc=$?
  if [ "$rc" -ne 0 ] || [ ! -s "$TMP_IMG" ]; then
    # Keep imagesnap's real message; drop its known harmless objc warning.
    LAST_ERR="exit=$rc: $(grep -v 'not linked into application' "$TMP_ERR" 2>/dev/null | tr '\n' ' ')"
    [ "$rc" -eq 124 ] && LAST_ERR="no result after ${WBC_CAPTURE_TIMEOUT}s, killed; $LAST_ERR"
    return 1
  fi
  cp "$TMP_IMG" "$LATEST_TMP" && mv -f "$LATEST_TMP" "$LATEST"
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

cleanup() {
  [ -n "$CHILD" ] && kill "$CHILD" 2>/dev/null
  rm -f "$TMP_IMG" "$TMP_ERR" "$TMP_STATUS" "$LATEST_TMP"
  if [ "$HAVE_LOCK" -eq 1 ]; then
    rm -rf "$LOCK"
    write_status "STOPPED"
  fi
  log "stopped"
  exit 0
}

main() {
  trap cleanup TERM INT
  mkdir -p "$WBC_TMP" || exit 1
  if ! acquire_lock; then
    nap "$WBC_LOCK_WAIT"   # under launchd: avoid a fast restart loop while another copy runs
    exit 0
  fi
  mkdir -p "$WBC_DIR/latest" "$WBC_DIR/hourly" "$WBC_DIR/daily" || exit 1
  log "started: dir=$WBC_DIR camera='$WBC_CAMERA' interval=${WBC_LIVE_INTERVAL}s"

  local last=0 last_state="" t
  while :; do
    t=$(now)
    # The camera is only touched when a frame is due.
    if [ -e "$REQUEST" ] || [ $((t - last)) -ge "$WBC_LIVE_INTERVAL" ]; then
      if ! camera_present; then
        if [ "$last_state" != "CAMERA_NOT_FOUND" ]; then log "camera '$WBC_CAMERA' not found"; fi
        write_status "CAMERA_NOT_FOUND"; last_state="CAMERA_NOT_FOUND"
        nap "$WBC_CAMERA_RETRY"
        continue
      fi
      if capture; then
        update_tiers
        write_status "OK"
        rm -f "$REQUEST"   # after the status, so a reader sees OK once the request is gone
        if [ "$last_state" != "OK" ]; then log "capturing"; fi
        last_state="OK"; last=$t
      else
        write_status "CAPTURE_FAILED"
        log "capture failed: $LAST_ERR"
        last_state="CAPTURE_FAILED"
        nap "$WBC_FAIL_RETRY"
        continue
      fi
    fi
    nap "$WBC_POLL"
  done
}

main "$@"
