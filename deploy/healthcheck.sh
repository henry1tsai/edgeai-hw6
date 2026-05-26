#!/usr/bin/env bash
#Copyright (c) 2026 Yanting Lin
#Tatung University 14210 AI實務專題
#deploy/healthcheck.sh - High-reliability polling healthcheck with relaxed latency tolerance

set -euo pipefail

HEALTH_URL="http://localhost:8000/healthz"
MAX_WAIT=60
STREAK_REQUIRED=3

CONSECUTIVE=0
START_TIME=$SECONDS

echo "[healthcheck] Starting reliability verification loop (Required: $STREAK_REQUIRED consecutive successes)..."

while (( (SECONDS - START_TIME) < MAX_WAIT )); do
    # 1. 透過 curl 取得目前端點狀態
    if RESPONSE=$(curl -fsS "$HEALTH_URL" 2>/dev/null); then
        
        # 2. 根源修正：檢查 FastAPI 回傳的 JSON 是否帶有 healthy
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
    
    # 3. 根源修正：加入合理的步進間隔，防止因瘋狂盲刷造成的時序競爭 (Race Condition)
    sleep 2
done

echo "[healthcheck] FAILED — Failed to maintain stable heartbeat within ${MAX_WAIT}s" >&2
exit 1