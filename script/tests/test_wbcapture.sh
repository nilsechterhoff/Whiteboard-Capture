#!/bin/bash
# test_wbcapture.sh - runs script/wbcapture.sh against a stubbed imagesnap and a
# fake clock. No camera needed; runs on Linux and macOS. ~10 s.
set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"
trap 'kill $PID 2>/dev/null; rm -rf "$T"' EXIT
pass=0; fail=0
check() { if eval "$2"; then echo "  PASS  $1"; pass=$((pass+1)); else echo "  FAIL  $1"; fail=$((fail+1)); fi; }
wait_for() { local i=0; while [ $i -lt 100 ]; do eval "$1" && return 0; sleep 0.1; i=$((i+1)); done; return 1; }

# Stub: camera "present" while $T/camera exists; each frame holds a counter.
cat > "$T/imagesnap" <<'EOF'
#!/bin/bash
if [ "$1" = "-l" ]; then echo "Video Devices:"; [ -e "$STUB_DIR/camera" ] && echo "=> J1455"; exit 0; fi
[ -e "$STUB_DIR/camera" ] || exit 1
n=$(( $(cat "$STUB_DIR/count" 2>/dev/null || echo 0) + 1 )); echo $n > "$STUB_DIR/count"
for out; do :; done; echo "frame $n" > "$out"
EOF
chmod +x "$T/imagesnap"

export STUB_DIR="$T" IMAGESNAP="$T/imagesnap" WBC_DIR="$T/Whiteboard Capture" WBC_NOW_FILE="$T/now"
export WBC_LIVE_INTERVAL=30 WBC_POLL=0.2 WBC_CAMERA_RETRY=0.2 WBC_WARMUP=0
NOW=1791800000   # fixed start time
echo $NOW > "$T/now"; touch "$T/camera"

bash "$ROOT/script/wbcapture.sh" > "$T/log" 2>&1 &
PID=$!

frame() { cat "$WBC_DIR/latest/latest.jpg" 2>/dev/null; }
advance() { local before; before=$(frame); NOW=$((NOW + $1)); echo $NOW > "$T/now"; wait_for '[ "$(frame)" != "$before" ]'; }
count() { ls -1 "$WBC_DIR/$1" | grep -c '\.jpg$'; }

echo "1. Start"
wait_for '[ -s "$WBC_DIR/latest/latest.jpg" ]'
check "latest/latest.jpg written" '[ -s "$WBC_DIR/latest/latest.jpg" ]'
check "status OK" 'grep -q "^OK " "$WBC_DIR/status.txt"'
check "1 hourly, 1 daily" '[ "$(count hourly)" = 1 ] && [ "$(count daily)" = 1 ]'
check "latest/ holds exactly 1 file" '[ "$(ls -A "$WBC_DIR/latest" | wc -l)" -eq 1 ]'

echo "2. No capture before interval (30 s)"
f=$(frame); NOW=$((NOW + 20)); echo $NOW > "$T/now"; sleep 1
check "same frame after 20 s" '[ "$(frame)" = "$f" ]'

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
f=$(frame); touch "$WBC_DIR/capture.request"
wait_for '[ ! -e "$WBC_DIR/capture.request" ]'
check "request consumed" '[ ! -e "$WBC_DIR/capture.request" ]'
check "fresh frame" '[ "$(frame)" != "$f" ]'

echo "6. Camera unplugged"
rm "$T/camera"; touch "$WBC_DIR/capture.request"
wait_for 'grep -q "^CAMERA_NOT_FOUND " "$WBC_DIR/status.txt"'
check "status CAMERA_NOT_FOUND" 'grep -q "^CAMERA_NOT_FOUND " "$WBC_DIR/status.txt"'
check "request kept while absent" '[ -e "$WBC_DIR/capture.request" ]'

echo "7. Camera back"
touch "$T/camera"
wait_for '[ ! -e "$WBC_DIR/capture.request" ]'
check "request served after reconnect" '[ ! -e "$WBC_DIR/capture.request" ]'
check "status OK again" 'grep -q "^OK " "$WBC_DIR/status.txt"'

echo "8. Stop"
kill -TERM $PID; wait $PID 2>/dev/null
check "status STOPPED" 'grep -q "^STOPPED " "$WBC_DIR/status.txt"'
check "no temp files left" '[ -z "$(ls -A "$WBC_DIR" | grep "~$")" ]'

echo; echo "Passed: $pass  Failed: $fail"
[ $fail -eq 0 ]
