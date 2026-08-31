#!/usr/bin/env bash
# Runs entirely INSIDE the dedicated Terminal window: starts a window-scoped
# screen recording of itself, then runs record_take.sh, then stops. This is
# the actual command typed into the demo terminal.
set -uo pipefail
cd /Users/kamal/Desktop/devpost/projects/tabclose

WINDOW_ID=22815
OUT=~/Desktop/tabclose-demo-raw.mov
LOG=~/Desktop/tabclose-take.log

echo "Recording window $WINDOW_ID -> $OUT"
# -V0 = unbounded, we stop it ourselves once record_take.sh finishes. Prior
# attempt used -V600 and the real Cloud Run Job latency (measured 800s+ end
# to end across 5 executions + a deliberate crash/retry) cut the recording
# off before the idempotency and console beats. No cap this time.
screencapture -v -x -l"$WINDOW_ID" "$OUT" &
REC_PID=$!
sleep 2

bash infra/record_take.sh 2>&1 | bash infra/ts.sh | tee "$LOG"

echo "Sequence complete. Stopping recording in 2s..."
sleep 2
kill -INT "$REC_PID" 2>/dev/null
wait "$REC_PID" 2>/dev/null
echo "RECORDING_COMPLETE"
ls -la "$OUT"
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUT"
