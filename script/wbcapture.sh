#!/bin/bash
# wbcapture.sh - whiteboard capture service (see docs/decisions/0005, 0006).
#
# Supervisor loop. One long-running ffmpeg process keeps the camera open and
# writes its newest frame (1 per second) to a scratch file. Every
# WBC_LIVE_INTERVAL s, or at once on capture.request, that frame goes to
# latest/latest.jpg, hourly/, daily/ -> prune -> status.txt.
# ffmpeg is restarted when it exits or when no new frame arrives for
# WBC_STALL_LIMIT s. The camera is found by serial number (two C930e are
# connected). Only one instance runs at a time (lock in WBC_TMP).
# Written for macOS bash 3.2; also runs on Linux (used by tests/).

set -u

# Default: the synced Nextcloud folder (path contains spaces; always quoted).
WBC_DIR="${WBC_DIR:-$HOME/Library/CloudStorage/Nextcloud-cloud.echterhoff.dk-nilsechterhoff/Services/Whiteboard Capture}"
# Logitech C930e serial, as listed by: ffmpeg -hide_banner -f avfoundation -list_devices true -i ""
WBC_CAMERA_SERIAL="${WBC_CAMERA_SERIAL:-7B5E845E}"
WBC_FFMPEG="${WBC_FFMPEG:-ffmpeg}"
WBC_LIVE_INTERVAL="${WBC_LIVE_INTERVAL:-20}"
WBC_POLL="${WBC_POLL:-1}"
WBC_CAMERA_RETRY="${WBC_CAMERA_RETRY:-5}"
WBC_FAIL_RETRY="${WBC_FAIL_RETRY:-30}"
WBC_STALL_LIMIT="${WBC_STALL_LIMIT:-60}"
WBC_STOP_GRACE="${WBC_STOP_GRACE:-5}"
WBC_LOCK_WAIT="${WBC_LOCK_WAIT:-30}"
WBC_KEEP_HOURLY="${WBC_KEEP_HOURLY:-12}"
WBC_KEEP_DAILY="${WBC_KEEP_DAILY:-7}"
# Local scratch space (fixed /tmp so manual runs and the service share one lock).
WBC_TMP="${WBC_TMP:-/tmp}"
# Test hook only: file holding a fake epoch time. Unset in production.
WBC_NOW_FILE="${WBC_NOW_FILE:-}"

STATUS="$WBC_DIR/status.txt"
LATEST="$WBC_DIR/latest/latest.jpg"
LATEST_TMP="$WBC_DIR/latest/.latest.jpg~"   # same folder -> atomic rename
REQUEST="$WBC_DIR/capture.request"
TMP_STATUS="$WBC_DIR/.wbc-status.txt~"
# ffmpeg writes the newest frame here (atomically, see start_capture).
TMP_IMG="$WBC_TMP/wbcapture-frame.jpg"
TMP_ERR="$WBC_TMP/wbcapture-ffmpeg.err"
TMP_LIST="$WBC_TMP/wbcapture-devices.txt"
LOCK="$WBC_TMP/wbcapture.lock"

CHILD=""       # pid of the running sleep, for cleanup
CAP_PID=""     # pid of the running ffmpeg stream
HAVE_LOCK=0

log() { echo "$(fmt_epoch "$(now)" '+%Y-%m-%d %H:%M:%S') $*"; }

now() {
  if [ -n "$WBC_NOW_FILE" ] && [ -s "$WBC_NOW_FILE" ]; then cat "$WBC_NOW_FILE"; else date +%s; fi
}

# real_now - wall clock, used for stall detection (never faked).
real_now() { date +%s; }

# fmt_epoch EPOCH FORMAT - BSD date (macOS) first, GNU date as fallback.
fmt_epoch() {
  date -r "$1" "$2" 2>/dev/null || date -d "@$1" "$2"
}

# file_mtime FILE - modification time in epoch seconds; empty if no file.
file_mtime() {
  stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null
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

# camera_index - ffmpeg device index of the camera with WBC_CAMERA_SERIAL.
# Empty if it is not connected. Only lists devices; does not open the camera.
camera_index() {
  "$WBC_FFMPEG" -hide_banner -f avfoundation -list_devices true -i "" > "$TMP_LIST" 2>&1
  sed -n "s/.*\[\([0-9][0-9]*\)\] .*serial:$WBC_CAMERA_SERIAL.*/\1/p" "$TMP_LIST" | head -n 1
}

# start_capture - start the stream in the background. Returns 1 if the camera is absent.
# ffmpeg writes one frame per second over TMP_IMG; -atomic_writing means a reader
# never sees a half-written file.
start_capture() {
  local idx
  idx=$(camera_index)
  [ -n "$idx" ] || return 1
  rm -f "$TMP_IMG" "$TMP_ERR"
  "$WBC_FFMPEG" -hide_banner -loglevel error -f avfoundation -framerate 30 -video_size 1920x1080 \
    -i "$idx:none" -vf fps=1 -update 1 -atomic_writing 1 -y "$TMP_IMG" > "$TMP_ERR" 2>&1 &
  CAP_PID=$!
  return 0
}

# stop_capture - ask ffmpeg to stop; SIGKILL only after WBC_STOP_GRACE s (logged).
stop_capture() {
  local i=0
  [ -n "$CAP_PID" ] || return 0
  kill "$CAP_PID" 2>/dev/null
  while kill -0 "$CAP_PID" 2>/dev/null && [ "$i" -lt $((WBC_STOP_GRACE * 10)) ]; do
    sleep 0.1; i=$((i + 1))
  done
  if kill -0 "$CAP_PID" 2>/dev/null; then
    log "stream did not stop within ${WBC_STOP_GRACE}s; killing"
    kill -9 "$CAP_PID" 2>/dev/null
  fi
  wait "$CAP_PID" 2>/dev/null
  CAP_PID=""
}

# tail_err - ffmpeg's last output on one line, for the log.
tail_err() { tr '\n' ' ' < "$TMP_ERR" 2>/dev/null | tail -c 300; }

# fail_capture REASON - status CAPTURE_FAILED, log, wait before the next start.
fail_capture() {
  write_status "CAPTURE_FAILED"
  log "capture failed: $1: $(tail_err)"
  last_state="CAPTURE_FAILED"
  nap "$WBC_FAIL_RETRY"
}

# publish - copy the newest frame into latest/ atomically.
publish() {
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

cleanup() {
  [ -n "$CHILD" ] && kill "$CHILD" 2>/dev/null
  stop_capture
  rm -f "$TMP_IMG" "$TMP_ERR" "$TMP_LIST" "$TMP_STATUS" "$LATEST_TMP"
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
  if ! command -v "$WBC_FFMPEG" >/dev/null 2>&1; then
    log "ffmpeg not found: '$WBC_FFMPEG' (set WBC_FFMPEG)"; rm -rf "$LOCK"; exit 1
  fi
  mkdir -p "$WBC_DIR/latest" "$WBC_DIR/hourly" "$WBC_DIR/daily" || exit 1
  log "started: dir=$WBC_DIR serial=$WBC_CAMERA_SERIAL interval=${WBC_LIVE_INTERVAL}s"

  local last=0 last_state="" t m frame_mtime="" frame_seen=0
  while :; do
    t=$(now)

    # The stream process ended on its own (camera unplugged, device error).
    if [ -n "$CAP_PID" ] && ! kill -0 "$CAP_PID" 2>/dev/null; then
      wait "$CAP_PID" 2>/dev/null; CAP_PID=""
      fail_capture "process exited"; continue
    fi

    # Not streaming: start the stream if the camera is connected.
    if [ -z "$CAP_PID" ]; then
      if ! start_capture; then
        if [ "$last_state" != "CAMERA_NOT_FOUND" ]; then log "camera serial $WBC_CAMERA_SERIAL not found"; fi
        write_status "CAMERA_NOT_FOUND"; last_state="CAMERA_NOT_FOUND"
        nap "$WBC_CAMERA_RETRY"; continue
      fi
      frame_mtime=""; frame_seen=$(real_now)
      last=0   # the first frame of a new stream is published at once
    fi

    # New frame? Remember when it arrived.
    m=$(file_mtime "$TMP_IMG")
    if [ -n "$m" ] && [ "$m" != "$frame_mtime" ]; then frame_mtime=$m; frame_seen=$(real_now); fi

    # Stream alive but silent: restart it.
    if [ $(( $(real_now) - frame_seen )) -ge "$WBC_STALL_LIMIT" ]; then
      stop_capture
      fail_capture "no new frame for ${WBC_STALL_LIMIT}s, restarting"; continue
    fi

    # Frame due (interval, or trigger file): publish it.
    if [ -n "$m" ] && { [ -e "$REQUEST" ] || [ $((t - last)) -ge "$WBC_LIVE_INTERVAL" ]; }; then
      if publish; then
        update_tiers
        write_status "OK"
        rm -f "$REQUEST"   # after the status, so a reader sees OK once the request is gone
        if [ "$last_state" != "OK" ]; then log "capturing"; fi
        last_state="OK"; last=$t
      fi
    fi
    nap "$WBC_POLL"
  done
}

main "$@"
