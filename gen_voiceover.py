#!/usr/bin/env python3
"""Generate Tabclose narration clips via VoiceStudio (onyx voice) on the mini."""
import json
import subprocess
import sys

LINES = [
    ("line1", "Mara runs one Cloud Run API by herself. When it goes down at 2 A M, "
     "she finds out from a customer tweet. Tabclose finds out first, checks with "
     "a second observer so it isn't fooled by a blip, and writes the incident "
     "down while she's asleep."),
    ("line2", "Nobody is typing. Cloud Scheduler just fired the job."),
    ("line3", "This folder didn't exist thirty seconds ago. Status dot M D is a "
     "draft, Tabclose never posts it. That's a boundary, not a bug."),
    ("line4", "One region flaking isn't an outage. The second observer in europe "
     "west 1 disagreed, so the run is rejected. No artifact."),
    ("line5", "Both observers agree now. That's when it writes."),
    ("line6", "Same run I D, same claim, so the second attempt exits without "
     "double writing. Exactly one folder."),
    ("line7", "Each tick keeps its A D K session short and pushes state to "
     "Firestore instead, because A D K caps sessions at 100 events with no "
     "pagination, and replaying a long session past that trips a 429. We just "
     "don't carry long sessions."),
]

OUT_DIR = "/tmp/tabclose_narration"
subprocess.run(["mkdir", "-p", OUT_DIR], check=True)

for name, text in LINES:
    payload = json.dumps({"model": "tts-1", "input": text, "voice": "onyx"})
    remote_out = f"{OUT_DIR}/{name}_onyx.mp3"
    cmd = (
        f"curl -s --max-time 60 -X POST http://localhost:3900/v1/audio/speech "
        f"-H 'Content-Type: application/json' -d @- -o {remote_out} "
        f"-w 'HTTP:%{{http_code}} SIZE:%{{size_download}}\\n'"
    )
    result = subprocess.run(
        ["mini", "run", cmd],
        input=payload,
        capture_output=True,
        text=True,
    )
    print(f"{name}: {result.stdout.strip()} {result.stderr.strip()}")

print("Done. Pulling files back to local...")
subprocess.run(["mini", "pull", f"{OUT_DIR}/", "/tmp/tabclose_narration_local/"], check=False)
