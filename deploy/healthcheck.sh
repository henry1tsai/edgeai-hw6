#!/usr/bin/env bash
# Copyright (c) 2026 Yanting Lin
# Tatung University 14210 AI實務專題
# deploy/healthcheck.sh - Conditional Trigger for Rollback Verification

set -euo pipefail

HEALTH_URL="http://localhost:8000/healthz"
MAX_WAIT=60
STREAK_REQUIRED=3

CONSECUTIVE=0
START_TIME=$SECONDS

echo "[healthcheck] Starting reliability verification loop (Required: $STREAK_REQUIRED consecutive successes)..."

while (( (SECONDS - START_TIME) < MAX_WAIT )); do
    if RESPONSE=$(curl -fsS "$HEALTH_URL" 2>/dev/null); then
        
        # 1. 抓取目前容器實體回傳的模型版號
        MODEL_VER=$(echo "$RESPONSE" | grep -o '"model_version": *"[^"]*"' | head -n1 | cut -d'"' -f4 || echo "")
        
        # 🎯 核心黑名單機制：如果抓到是正在測試的 v1.0.8，無條件直接攔截判定失敗！
        if [ "$MODEL_VER" = "v1.0.8" ]; then
            echo "[healthcheck] CONDITION MATCHED: Version v1.0.8 detected! Intentionally triggering deployment failure for rollback demo." >&2
            exit 1
        fi
        
        # 2. 檢查 FastAPI 回傳的 JSON 是否帶有 healthy
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
    
    sleep 2
done

echo "[healthcheck] FAILED — Failed to maintain stable heartbeat within ${MAX_WAIT}s" >&2
exit 1