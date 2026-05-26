#!/usr/bin/env bash
# Copyright (c) 2026 Yanting Lin
# Tatung University 14210 AI實務專題
# deploy/rollback.sh - Robust parameter-driven atomic rollback

set -euo pipefail

STATE_DIR=/var/lib/edgeai-hw6

# 從參數直接獲取精準的版本版號，不再盲讀檔案
BROKEN_TAG="${1:-}"
PREV_TAG="${2:-}"

# 如果沒傳參數，才降級去讀取現地檔案作為備援
if [ -z "$BROKEN_TAG" ] || [ -z "$PREV_TAG" ]; then
    echo "[rollback] No arguments provided, falling back to file auditing..."
    BROKEN_TAG=$(cat "$STATE_DIR/deployed.txt" 2>/dev/null || echo "v1.0.2")
    PREV_TAG=$(tail -n 1 "$STATE_DIR/deployed.txt.history" 2>/dev/null || echo "v1.0.1")
fi

echo "[rollback] Commencing atomic rollback procedure..."
echo "[rollback] Identified broken version: $BROKEN_TAG"
echo "[rollback] Executing recovery to guaranteed stable version: $PREV_TAG"

# 強制將容器拉回真正穩定的上一版
export IMAGE_TAG="$PREV_TAG"

# 🎯 根源修正：回滾執行時也強制切回專案根目錄，防止相對路徑與專案定義錯位
cd /home/jetson/edgeai-hw6

docker compose -f deploy/docker-compose.yml up -d --force-recreate

# 進行回滾後的健康檢查
if bash deploy/healthcheck.sh; then
    # 回滾成功後，精準導正狀態檔案
    echo "$PREV_TAG" > "$STATE_DIR/deployed.txt"
    echo "[rollback] SUCCESS: System safely recovered and locked at $PREV_TAG."
    exit 0
else
    echo "[rollback] FATAL CRITICAL: Rollback target $PREV_TAG also failed healthcheck!" >&2
    exit 1
fi