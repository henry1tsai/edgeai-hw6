#!/usr/bin/env bash
# entrypoint.sh — 容器在 Jetson 啟動時執行的入口腳本
#
# 功能：
# 1. 如果 best.engine 缺失或比 best.pt 舊，則使用 Ultralytics YOLO 重新編譯 TensorRT engine。
#    編譯需要 GPU (--runtime nvidia)，並使用容器內的 TensorRT 10.3。
# 2. exec 執行 inference_node.py，確保 SIGTERM (docker stop) 能傳遞到 Python 程式。
#
# 為什麼在 runtime 編譯而不是 Dockerfile 的 RUN？
# - GitHub x86 runner 雖可模擬 aarch64 指令，但無法提供 CUDA 裝置，
#   所以 build 時執行 `yolo export format=engine` 會失敗。
# - 在 Jetson 啟動時編譯可避免此問題，並確保 engine 與執行環境相符。
#
# 首次編譯需 5–8 分鐘。建議將 /opt/models 掛載為 volume，以便後續重用：
# docker run -v lab12-models:/opt/models ...
set -euo pipefail

MODEL_DIR=/opt/models
WEIGHTS="${MODEL_DIR}/best.pt"
ENGINE="${MODEL_DIR}/best.engine"

# 檢查權重檔是否存在
if [ ! -f "${WEIGHTS}" ]; then
  echo "ERROR: ${WEIGHTS} 不存在。請確認已將 best.pt 複製到映像檔中。" >&2
  exit 1
fi

# 若 engine 缺失或比權重舊，則重新編譯
if [ ! -f "${ENGINE}" ] || [ "${WEIGHTS}" -nt "${ENGINE}" ]; then
  echo "[entrypoint] 編譯 TensorRT engine (首次需 5–8 分鐘)..."
  (
    cd "${MODEL_DIR}"
    python3 -c "
from ultralytics import YOLO
YOLO('best.pt', task='detect').export(format='engine', imgsz=320, half=True, opset=19)
"
  )
  echo "[entrypoint] 編譯完成: $(ls -lh ${ENGINE} | awk '{print $5}')"
else
  echo "[entrypoint] 使用快取的 engine: $(ls -lh ${ENGINE} | awk '{print $5}')"
fi

# 執行 Dockerfile CMD (預設: python3 inference_node.py)
# 使用 exec 取代 bash，讓 SIGTERM 能直接傳遞到 Python 程式
exec "$@"