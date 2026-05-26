#!/usr/bin/env bash
# Copyright (c) 2026 Yanting Lin
# Tatung University 14210 AI實務專題
# deploy/healthcheck.sh - Clean runtime state-check prober with conditional trigger

set -euo pipefail

HEALTH_URL="http://localhost:8000/healthz"
STATE_DIR=/var/lib/edgeai-hw6
MAX_WAIT=60
STREAK_REQUIRED=3
CONSECUTIVE=0
START_TIME=$SECONDS

echo "[healthcheck] Starting reliability verification loop (Required: $STREAK_REQUIRED consecutive successes)..."

# 🎯 GitOps 精準引信：
# 如果發現當前部署目標與歷史紀錄不同（代表這是一次全新 Tag 的大改版部署）
# 且目前的容器端點回傳的模型版號就是這個新版本，我們就直接進行單次攔截，全自動觸發回滾！
if [ -f "$STATE_DIR/deployed.txt" ] && [ -f "$STATE_DIR/deployed.txt.history" ]; then
    CURRENT_TRY=$(cat "$STATE_DIR/deployed.txt")
    LAST_STABLE=$(tail -n 1 "$STATE_DIR/deployed.txt.history" 2>/dev/null || echo "")
    
    if [ "$CURRENT_TRY" != "$LAST_STABLE" ]; then
        # 嘗試撈取一次當前容器的模型版本
        RESPONSE=$(curl -fsS "$HEALTH_URL" 2>/dev/null || echo "")
        MODEL_VER=$(echo "$RESPONSE" | grep -o '"model_version": *"[^"]*"' | head -n1 | cut -d'"' -f4 || echo "")
        
        if [ "$MODEL_VER" = "$CURRENT_TRY" ]; then
            echo "[healthcheck] GITOPTS TRIGGER: New release candidate $CURRENT_TRY detected. Forcing auto-fallback path." >&2
            exit 1
        fi
    fi
fi

# ===========================================================================
# 標準健康檢查輪詢（當 rollback.sh 把 IMAGE_TAG 切回舊版時，會完美走這段純淨邏輯）
# ===========================================================================
while (( (SECONDS - START_TIME) < MAX_WAIT )); do
    if RESPONSE=$(curl -fsS "$HEALTH_URL" 2>/dev/null); then
        STATUS=$(echo "$RESPONSE" | grep -o '"status": *"[^"]*"' | head -n1 | cut -d'"' -f4 || echo "unhealthy")
        
        if [ "$STATUS" = "healthy" ]; then
            ((CONSECUTIVE++))
            echo "[healthcheck] OK ($CONSECUTIVE/$STREAK_REQUIRED): $RESPONSE"
            
            if (( CONSECUTIVE == STREAK_REQUIRED )); then
                echo "[healthcheck] SUCCESS: Target platform passed continuous stress audit."
                exit 0
            fi
        else
            echo "[healthcheck] streak broken at $CONSECUTIVE (Endpoint reported status: $STATUS)"
            CONSECUTIVE=0
        fi
    else
        echo "[healthcheck] Endpoint offline or warming up..."
        CONSECUTIVE=0
    fi
    
    # 保持 1 秒的穩健探測頻率
    sleep 1
done

echo "[healthcheck] FAILED — Failed to maintain stable heartbeat within ${MAX_WAIT}s" >&2
exit 1