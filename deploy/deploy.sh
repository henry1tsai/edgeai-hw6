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
#   DEPLOY_ENV=low_power_demo bash deploy/deploy.sh <vX.Y.Z>
#
# Prerequisites (one-time, see Step 0.0):
#   - NOPASSWD sudo configured for nvpmodel + jetson_clocks (Step 0.0)
#   - STATE_DIR (/var/lib/edgeai-hw6) chowned to the deploy user (Step D5)
#   - GHCR docker login already done (deploy.yml's docker/login-action step)

set -euo pipefail

TAG="${1:?Usage: deploy.sh <vX.Y.Z>}"
ENV="${DEPLOY_ENV:-production}"
STATE_DIR=/var/lib/edgeai-hw6
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# State-dir is chowned to the deploy user during one-time setup (D5), so
# bare > and >> work without sudo. We deliberately keep sudo confined to
# nvpmodel and jetson_clocks (both NOPASSWD-configured per Step 0.0) — that
# way deploy.yml's non-interactive SSH session never blocks on a password.
mkdir -p "$STATE_DIR"

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
  echo "[deploy] Available envs:" >&2
  jq -r 'keys[]' "$PROFILE" >&2
  exit 1
fi

PAT="<\s*POWER_MODEL\s+ID=[0-9]+\s+NAME=${MODE_NAME}\s*>"
MODE_ID=$(grep -oE "$PAT" /etc/nvpmodel.conf \
  | grep -oE "ID=[0-9]+" | cut -d= -f2 | head -1)
if [ -z "$MODE_ID" ]; then
  echo "[deploy] ERROR: power mode '$MODE_NAME' not found in /etc/nvpmodel.conf" >&2
  echo "[deploy] Available modes:" >&2
  grep -oE "<\s*POWER_MODEL\s+ID=[0-9]+\s+NAME=\S+\s*>" /etc/nvpmodel.conf >&2
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
  PREV=$(cat "$STATE_DIR/deployed.txt")
  echo "$PREV" >> "$STATE_DIR/deployed.txt.history"
  echo "[deploy] Previous tag was $PREV (saved for rollback)"
fi

# ---------------------------------------------------------------------------
# 3. Pull the requested tag, recreate the inference container.
# ---------------------------------------------------------------------------
export IMAGE_TAG="$TAG"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"

echo "[deploy] Pulling image for tag $TAG"
# Tolerate transient auth failures — if pull fails, the local cache may
# still be usable (the deploy.yml docker/login-action handles re-auth on
# the next workflow run, but scheduled cron-like runs may lapse).
if ! docker compose -f "$COMPOSE_FILE" pull; then
  echo "[deploy] WARNING: pull failed; falling back to local image cache"
fi

echo "[deploy] Recreating container with tag $TAG"
docker compose -f "$COMPOSE_FILE" up -d --force-recreate

# ---------------------------------------------------------------------------
# 4. Wait for health; roll back on fail.
# ---------------------------------------------------------------------------
if ! bash deploy/healthcheck.sh; then
    echo "[deploy] Healthcheck failed! Activating parameter-driven auto-rollback..." >&2
    
    # 這裡的 CURRENT_TAG 是 v1.0.2，PREV_TAG 是部署前安全存下來的 v1.0.1
    if [ -x deploy/rollback.sh ]; then
        bash deploy/rollback.sh "$1" "$PREV_TAG"
    else
        echo "[deploy] CRITICAL: rollback.sh missing!" >&2
        exit 1
    fi
    exit 1
fi

# ---------------------------------------------------------------------------
# 5. Mark this tag as the new current.
# ---------------------------------------------------------------------------
echo "$TAG" > "$STATE_DIR/deployed.txt"
echo "[deploy] Successfully deployed $TAG at power mode $MODE_NAME (env=$ENV)"