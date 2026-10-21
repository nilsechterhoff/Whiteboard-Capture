#!/bin/bash
# test_wbcapture.sh - runs script/wbcapture.sh against a stubbed ffmpeg and a
# fake clock. No camera needed; runs on Linux and macOS. ~60 s.
set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"
trap 'kill $PID 2>/dev/null; rm -rf "$T"' EXIT
pass=0; fail=0
check() { if eval "$2"; then echo "  PASS  $1"; pass=$((pass+1)); else echo "  FAIL  $1"; fail=$((fail+1)); fi; }
wait_for() { local i=0; while [ $i -lt 100 ]; do eval "$1" && return 0; sleep 0.1; i=$((i+1)); done; return 1; }

# Stub ffmpeg. Device listing ("-list_devices") shows the camera only while
# $T/camera exists and counts each call in $T/listcount.
# Stream mode writes "frame N" to the last argument once per second.
#   $T/camera removed -> stream exits with an error (unplugged)
#   $T/fail           -> stream exits with ffmpeg's real error text
#   $T/hang           -> stream stays alive but writes no new frames
cat > "$T/ffmpeg" <<'STUB'
#!/bin/bash
if printf '%s\n' "$@" | grep -qx -- '-list_devices'; then
  echo $(( $(cat "$STUB_DIR/listcount" 2>/dev/null || echo 0) + 1 )) > "$STUB_DIR/listcount"
  echo "[AVFoundation indev @ 0x1] AVFoundation video devices:"
  [ -e "$STUB_DIR/camera" ] && echo "[AVFoundation indev @ 0x1] [0] Logitech Webcam C930e  [uid:x]  [serial:7B5E845E]"
  echo "[AVFoundation indev @ 0x1] [1] FaceTime HD Camera  [uid:y]"
  echo "[AVFoundation indev @ 0x1] AVFoundation audio devices:"
  exit 0
fi
out="${*: -1}"
n=$(cat "$STUB_DIR/count" 2>/dev/null || echo 0)
trap 'exit 0' TERM INT
while :; do
  if [ ! -e "$STUB_DIR/camera" ]; then echo "Error opening input: Input/output error" >&2; exit 1; fi
  if [ -e "$STUB_DIR/fail" ]; then echo "Error: Failed to capture photo." >&2; exit 1; fi
  if [ ! -e "$STUB_DIR/hang" ]; then
    n=$((n + 1)); echo $n > "$STUB_DIR/count"; echo "frame $n" > "$out"
  fi
  sleep 1 & wait $!
done
STUB
chmod +x "$T/ffmpeg"

export STUB_DIR="$T" WBC_FFMPEG="$T/ffmpeg" WBC_DIR="$T/Whiteboard Capture" WBC_NOW_FILE="$T/now"
export WBC_CAMERA_SERIAL=7B5E845E WBC_LIVE_INTERVAL=20 WBC_POLL=0.2 WBC_CAMERA_RETRY=0.2
export WBC_TMP="$T/tmp" WBC_FAIL_RETRY=0.3 WBC_STALL_LIMIT=2 WBC_STOP_GRACE=2 WBC_LOCK_WAIT=0.2
NOW=1791800000   # fixed start time
echo $NOW > "$T/now"; touch "$T/camera"

bash "$ROOT/script/wbcapture.sh" > "$T/log" 2>&1 &
PID=$!

frame() { cat "$WBC_DIR/latest/latest.jpg" 2>/dev/null; }
status() { cat "$WBC_DIR/status.txt" 2>/dev/null; }
# advance SECONDS - move the fake clock and wait until the status line was rewritten.
advance() { local before; before=$(status); NOW=$((NOW + $1)); echo $NOW > "$T/now"; wait_for '[ "$(status)" != "$before" ]'; }
count() { ls -1 "$WBC_DIR/$1" | grep -c '\.jpg$'; }
stream_running() { ps -axo command | grep -F "$T/ffmpeg" | grep -v grep >/dev/null; }

echo "1. Start"
wait_for '[ -s "$WBC_DIR/latest/latest.jpg" ] && grep -q "^OK " "$WBC_DIR/status.txt" 2>/dev/null'
check "latest/latest.jpg written" '[ -s "$WBC_DIR/latest/latest.jpg" ]'
check "status OK" 'grep -q "^OK " "$WBC_DIR/status.txt"'
check "1 hourly, 1 daily" '[ "$(count hourly)" = 1 ] && [ "$(count daily)" = 1 ]'
check "latest/ holds exactly 1 file" '[ "$(ls -A "$WBC_DIR/latest" | wc -l)" -eq 1 ]'

echo "2. No publish before interval (20 s)"
f=$(frame); NOW=$((NOW + 15)); echo $NOW > "$T/now"; sleep 1.5
check "same published frame after 15 s" '[ "$(frame)" = "$f" ]'

echo "3. Hourly tier: 14 hours later"
for i in $(seq 14); do advance 3600; done
check "hourly pruned to 12" '[ "$(count hourly)" = 12 ]'

echo "4. Daily tier: 9 days later"
for i in $(seq 9); do advance 86400; done
check "daily pruned to 7" '[ "$(count daily)" = 7 ]'
check "hourly still 12" '[ "$(count hourly)" = 12 ]'
newest_day=$(ls -1 "$WBC_DIR/daily" | sort | tail -1)
check "newest daily is today" '[ "$newest_day" = "$(date -r $NOW +%Y-%m-%d 2>/dev/null || date -d @$NOW +%Y-%m-%d).jpg" ]'

echo "5. Trigger file (clock frozen)"
sleep 1.2; f=$(frame); touch "$WBC_DIR/capture.request"
wait_for '[ ! -e "$WBC_DIR/capture.request" ]'
check "request consumed" '[ ! -e "$WBC_DIR/capture.request" ]'
check "fresh frame published" '[ "$(frame)" != "$f" ]'

echo "6. Camera unplugged"
rm "$T/camera"
wait_for 'grep -q "^CAMERA_NOT_FOUND " "$WBC_DIR/status.txt"'
touch "$WBC_DIR/capture.request"; sleep 0.5
check "status CAMERA_NOT_FOUND" 'grep -q "^CAMERA_NOT_FOUND " "$WBC_DIR/status.txt"'
check "stream gone" '! stream_running'
check "request kept while absent" '[ -e "$WBC_DIR/capture.request" ]'

echo "7. Camera back"
touch "$T/camera"
wait_for '[ ! -e "$WBC_DIR/capture.request" ]'
check "request served after reconnect" '[ ! -e "$WBC_DIR/capture.request" ]'
check "status OK again" 'grep -q "^OK " "$WBC_DIR/status.txt"'

echo "8. No device queries while the stream runs"
c1=$(cat "$T/listcount"); sleep 2; c2=$(cat "$T/listcount")
check "no device listing between frames" '[ "$c1" = "$c2" ]'

echo "9. Stream error: real error is logged, restart recovers"
touch "$T/fail"; NOW=$((NOW + 20)); echo $NOW > "$T/now"
wait_for 'grep -q "^CAPTURE_FAILED " "$WBC_DIR/status.txt"'
check "status CAPTURE_FAILED" 'grep -q "^CAPTURE_FAILED " "$WBC_DIR/status.txt"'
check "log shows ffmpeg error" 'grep -q "capture failed: process exited: .*Error: Failed to capture photo." "$T/log"'
rm "$T/fail"
wait_for 'grep -q "^OK " "$WBC_DIR/status.txt"'
check "recovers after error" 'grep -q "^OK " "$WBC_DIR/status.txt"'

echo "10. Silent stream (no new frames) is restarted"
NOW=$((NOW + 20)); echo $NOW > "$T/now"
touch "$T/hang"
wait_for 'grep -q "no new frame for 2s" "$T/log"'
check "stall reported in log" 'grep -q "no new frame for 2s, restarting" "$T/log"'
rm "$T/hang"
wait_for 'grep -q "^OK " "$WBC_DIR/status.txt"'
check "recovers after stall" 'grep -q "^OK " "$WBC_DIR/status.txt"'

echo "11. Second instance refuses to start"
bash "$ROOT/script/wbcapture.sh" > "$T/log2" 2>&1; rc2=$?
check "second instance exits" '[ "$rc2" = 0 ]'
check "second instance says already running" 'grep -q "already running (pid $PID)" "$T/log2"'
check "first instance still OK" 'kill -0 $PID && grep -q "^OK " "$WBC_DIR/status.txt"'

echo "12. Stop"
kill -TERM $PID; wait $PID 2>/dev/null
check "status STOPPED" 'grep -q "^STOPPED " "$WBC_DIR/status.txt"'
check "stream stopped" '! stream_running'
check "no temp files left" '[ -z "$(ls -A "$WBC_DIR" "$WBC_DIR/latest" | grep "~$")" ]'
check "lock released" '[ ! -e "$T/tmp/wbcapture.lock" ]'

echo; echo "Passed: $pass  Failed: $fail"
[ $fail -eq 0 ]
