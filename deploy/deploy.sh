#!/usr/bin/env bash
# Copyright (c) 2026 Yanting Lin
# Tatung University — I4210 AI實務專題
# deploy/deploy.sh — main production deployment script.
#
# Sequence:
#   1. Resolve power mode NAME (from power_profile.json) → numeric ID
#      against the Jetson's /etc/nvpmodel.conf, then apply via nvpmodel.
#   2. Save the currently-deployed tag to deployed.txt.history (so
#      rollback.sh knows what "previous version" means).
#   3. docker compose pull → recreate container with the new IMAGE_TAG.
#   4. Run healthcheck.sh; if it fails, trigger rollback.sh.
#   5. On success, write the new tag to deployed.txt.
#
# Usage:
#   bash deploy/deploy.sh <vX.Y.Z>

set -euo pipefail

# ---------------------------------------------------------------------------
# 0. 核心變數與別名宣告 (精準綁定語意，封死 set -u 地雷)
# ---------------------------------------------------------------------------
TAG="${1:?Usage: deploy.sh <vX.Y.Z>}"
CURRENT_TAG="$TAG"
ENV="${DEPLOY_ENV:-production}"
STATE_DIR=/var/lib/edgeai-hw6
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

mkdir -p "$STATE_DIR"

# 事先安全讀取上一版健康的 Tag 作為備援變數
PREV_TAG=$(cat "$STATE_DIR/deployed.txt" 2>/dev/null || echo "v1.0.1")

# ---------------------------------------------------------------------------
# 1. Resolve the configured power-mode NAME → numeric ID for THIS Jetson SKU.
# ---------------------------------------------------------------------------
PROFILE="${SCRIPT_DIR}/power_profile.json"
if [ ! -f "$PROFILE" ]; then
  echo "[deploy] ERROR: power_profile.json not found at $PROFILE" >&2
  exit 1
fi

MODE_NAME=$(jq -r ".\"$ENV\"" "$PROFILE")
if [ -z "$MODE_NAME" ] || [ "$MODE_NAME" = "null" ]; then
  echo "[deploy] ERROR: env '$ENV' not defined in power_profile.json" >&2
  exit 1
fi

PAT="<\s*POWER_MODEL\s+ID=[0-9]+\s+NAME=${MODE_NAME}\s*>"
MODE_ID=$(grep -oE "$PAT" /etc/nvpmodel.conf \
  | grep -oE "ID=[0-9]+" | cut -d= -f2 | head -1)
if [ -z "$MODE_ID" ]; then
  echo "[deploy] ERROR: power mode '$MODE_NAME' not found in /etc/nvpmodel.conf" >&2
  exit 1
fi

echo "[deploy] Setting nvpmodel to $MODE_NAME (ID=$MODE_ID) for env=$ENV"
sudo nvpmodel -m "$MODE_ID"
sudo jetson_clocks
sleep 2

# ---------------------------------------------------------------------------
# 2. Save the currently-deployed tag for Part E's rollback.sh.
# ---------------------------------------------------------------------------
if [ -f "$STATE_DIR/deployed.txt" ]; then
  PREV_RECORD=$(cat "$STATE_DIR/deployed.txt")
  echo "$PREV_RECORD" >> "$STATE_DIR/deployed.txt.history"
  echo "[deploy] Previous tag was $PREV_RECORD (saved for rollback)"
fi

# ---------------------------------------------------------------------------
# 3. Pull the requested tag, recreate the inference container.
# ---------------------------------------------------------------------------
export IMAGE_TAG="$CURRENT_TAG"

# 🎯 根源修正：強制切換到專案根目錄，導正 Docker Compose 工作視角
cd "$REPO_ROOT"

echo "[deploy] Pulling image for tag $CURRENT_TAG"
if ! docker compose -f deploy/docker-compose.yml pull; then
  echo "[deploy] WARNING: pull failed; falling back to local image cache"
fi

echo "[deploy] Recreating container with tag $CURRENT_TAG"
docker compose -f deploy/docker-compose.yml up -d --force-recreate

# ---------------------------------------------------------------------------
# 4. Wait for health; roll back on fail.
# ---------------------------------------------------------------------------
if ! bash deploy/healthcheck.sh; then
    echo "[deploy] Healthcheck failed! Activating parameter-driven auto-rollback..." >&2
    
    if [ -x deploy/rollback.sh ]; then
        # 精準將當前壞的與確認好的變數傳遞下去
        bash deploy/rollback.sh "$CURRENT_TAG" "$PREV_TAG"
    else
        echo "[deploy] CRITICAL: rollback.sh missing!" >&2
        exit 1
    fi
    exit 1
fi

# ---------------------------------------------------------------------------
# 5. Mark this tag as the new current.
# ---------------------------------------------------------------------------
echo "$CURRENT_TAG" > "$STATE_DIR/deployed.txt"
echo "[deploy] Successfully deployed $CURRENT_TAG at power mode $MODE_NAME (env=$ENV)"