#!/usr/bin/env bash
# Copyright (c) 2026 Yanting Lin
# Tatung University — I4210 AI實務專題
# deploy/rollback.sh — revert to the previous deployed tag.

set -euo pipefail

STATE_DIR=/var/lib/edgeai-hw6
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HISTORY="$STATE_DIR/deployed.txt.history"
CURRENT="$STATE_DIR/deployed.txt"

# 從參數獲取（deploy.sh 呼叫時傳入），或從檔案備援
BROKEN_TAG="${1:-}"
PREV_TAG="${2:-}"

if [ -z "$PREV_TAG" ]; then
  if [ ! -f "$HISTORY" ] || [ ! -s "$HISTORY" ]; then
    echo "[rollback] ERROR: no rollback history at $HISTORY" >&2
    echo "[rollback] At least one prior successful deploy is required" >&2
    exit 1
  fi
  PREV_TAG=$(tail -1 "$HISTORY")
  BROKEN_TAG=$(cat "$CURRENT" 2>/dev/null || echo "unknown")
fi

if [ -z "$PREV_TAG" ]; then
  echo "[rollback] ERROR: PREV_TAG is empty" >&2
  exit 1
fi

echo "[rollback] Rolling back from $BROKEN_TAG to $PREV_TAG"

cd "$REPO_ROOT"
export IMAGE_TAG="$PREV_TAG"

if ! docker compose -f deploy/docker-compose.yml pull; then
  echo "[rollback] WARNING: pull failed; using local image cache"
fi

docker compose -f deploy/docker-compose.yml up -d --force-recreate

if ! bash deploy/healthcheck.sh; then
  echo "[rollback] CRITICAL: rollback container also unhealthy" >&2
  echo "[rollback] Both $BROKEN_TAG and $PREV_TAG are broken" >&2
  exit 1
fi

# 更新狀態檔案
echo "$PREV_TAG" > "$CURRENT"
if [ -f "$HISTORY" ] && [ "$(wc -l < "$HISTORY")" -gt 1 ]; then
  head -n -1 "$HISTORY" > "$HISTORY.tmp" && mv "$HISTORY.tmp" "$HISTORY"
fi

echo "[rollback] SUCCESS: rolled back to $PREV_TAG"