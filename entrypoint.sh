#!/usr/bin/env bash
# ==============================================================================
# Copyright (c) 2026 henry1tsai
# Tatung University — I4210 AI實務專題
# ==============================================================================
set -euo pipefail

MODEL_DIR=/opt/models
WEIGHTS="${MODEL_DIR}/best.pt"
ENGINE="${MODEL_DIR}/best.engine"

if [ ! -f "${WEIGHTS}" ]; then
  echo "ERROR: ${WEIGHTS} 不存在。" >&2
  exit 1
fi

if [ ! -f "${ENGINE}" ] || [ "${WEIGHTS}" -nt "${ENGINE}" ]; then
  echo "[entrypoint] 編譯 TensorRT engine (首次需 5–8 分鐘)..."
  (
    cd "${MODEL_DIR}"
    python3 -m ultralytics.models.yolo.detect.export format='engine' imgsz=320 half=True opset=19
  )
  echo "[entrypoint] 編譯完成"
else
  echo "[entrypoint] 使用快取的 engine"
fi

# 執行 Dockerfile CMD 傳進來的參數 (即 python3 -m src.inference_node)
exec "$@"