#!/usr/bin/env bash
#Copyright (c) 2026 Yanting Lin
#Tatung University 14210 AI實務專題
#deploy/rollback.sh - Automated, fast rollback to previous stable tag.

set -euo pipefail

STATE_DIR=/var/lib/edgeai-hw6

echo "[rollback] Commencing atomic rollback procedure..."

# 1. 檢查是否存在持久化狀態檔案
if [ ! -f "$STATE_DIR/deployed.txt" ]; then
    echo "[rollback] CRITICAL ERROR: Current state file missing. Cannot audit versions." >&2
    exit 1
fi

# 2. 尋找並讀取上一個成功運行的穩定版本 Tag
if [ -f "$STATE_DIR/deployed.txt.history" ] && [ -s "$STATE_DIR/deployed.txt.history" ]; then
    PREV_TAG=$(tail -n 1 "$STATE_DIR/deployed.txt.history")
else
    echo "[rollback] ERROR: No deployment history found in records. Aborting." >&2
    exit 1
fi

CURRENT_TAG=$(cat "$STATE_DIR/deployed.txt")
echo "[rollback] Current broken version: $CURRENT_TAG"
echo "[rollback] Recovering to known stable version: $PREV_TAG"

# 3. 容錯拉取：拉取歷史安全映像檔，即使驗證過期也能依賴在地快取（Proceed on auth expiry）
export IMAGE_TAG="$PREV_TAG"
echo "[rollback] Pulling rollback target image: $IMAGE_TAG"
docker compose -f deploy/docker-compose.yml pull || \
    echo "[rollback] WARNING: Registry access unauthenticated; rolling back using local cache."

# 4. 強制重建容器堆疊（與 deploy.sh 共享同一個動態環境變數變更）
echo "[rollback] Restructuring container layers to $IMAGE_TAG..."
docker compose -f deploy/docker-compose.yml up -d --force-recreate

# 5. 呼叫 D3 健康檢查，實施雙重損壞防範
echo "[rollback] Validating fallback environment with healthcheck.sh..."
if bash deploy/healthcheck.sh; then
    # 回滾成功，將狀態檔案還原，並清理歷史記錄檔的最後一行
    echo "$PREV_TAG" > "$STATE_DIR/deployed.txt"
    # 自行移出歷史堆疊中的最後一筆記錄
    sed -i '$d' "$STATE_DIR/deployed.txt.history"
    echo "[rollback] SUCCESS: System recovered and stable at $PREV_TAG."
    exit 0
else
    echo "[rollback] FATAL CRITICAL: Both current and previous tags are broken! Alerting operator immediately." >&2
    exit 1
fi