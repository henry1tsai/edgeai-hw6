#!/usr/bin/env bash
# Copyright (c) 2026 Yanting Lin
# Tatung University — I4210 AI實務專題
# deploy/healthcheck.sh — verify the inference container is healthy.
# Polls /healthz; requires 3 consecutive 200 responses inside 60 s total.

set -euo pipefail

URL="${HEALTHZ_URL:-http://localhost:8000/healthz}"
DEADLINE=$((SECONDS + 60))
STREAK=0
NEEDED=3

echo "[healthcheck] Polling $URL (need $NEEDED consecutive successes in 60s)..."

while [ "$SECONDS" -lt "$DEADLINE" ]; do
  if body=$(curl -fsS --max-time 2 "$URL" 2>/dev/null) && \
     echo "$body" | jq -e '.status == "healthy"' >/dev/null 2>&1; then
    STREAK=$((STREAK + 1))
    echo "[healthcheck] OK ($STREAK/$NEEDED): $body"
    if [ "$STREAK" -ge "$NEEDED" ]; then
      echo "[healthcheck] SUCCESS"
      exit 0
    fi
  else
    if [ "$STREAK" -gt 0 ]; then
      echo "[healthcheck] streak broken at $STREAK"
    fi
    STREAK=0
  fi
  sleep 2
done

echo "[healthcheck] FAILED — no $NEEDED consecutive successes in 60 s" >&2
exit 1