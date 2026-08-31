#!/usr/bin/env bash
# Fires the moment the screen is clear. One continuous screen recording,
# real command sequence (record_take.sh), timestamped log for post-align.
set -uo pipefail
cd /Users/kamal/Desktop/devpost/projects/tabclose
chmod +x infra/ts.sh infra/record_take.sh

OUT=~/Desktop/tabclose-demo-raw.mov
LOG=~/Desktop/tabclose-take.log
echo "Recording start (wall clock): $(date -u '+%Y-%m-%d %H:%M:%S UTC')" | tee "$LOG"

# -V 600 = hard cap at 10 minutes (safety net; actual cut happens in post)
screencapture -v -V 600 -x "$OUT" &
REC_PID=$!
sleep 2

bash infra/record_take.sh 2>&1 | bash infra/ts.sh | tee -a "$LOG"

echo "Sequence done, stopping recording..."
kill -INT "$REC_PID" 2>/dev/null
wait "$REC_PID" 2>/dev/null
echo "Recording saved to $OUT"
ls -la "$OUT"
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUT"
