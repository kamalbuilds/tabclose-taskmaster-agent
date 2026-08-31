#!/usr/bin/env bash
# Prefix every line of stdin with a UTC timestamp (HH:MM:SS.mmm), used to
# timestamp record_take.sh's output for later video/log alignment.
while IFS= read -r line; do
  printf '%s %s\n' "$(date -u '+%H:%M:%S.%3N')" "$line"
done
