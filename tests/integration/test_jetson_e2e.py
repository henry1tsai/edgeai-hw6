#!/usr/bin/env python3
# Copyright (c) 2026 Yanting Lin
# Tatung University — I4210 AI實務專題
"""tests/integration/test_jetson_e2e.py — single-mode E2E inference test.

Runs on the self-hosted Jetson runner. Pulls the per-commit image,
starts the container with --runtime nvidia, waits for the TensorRT
engine to load, then validates one MQTT detection round-trip.
"""

import json
import os
import queue
import subprocess
import time
from pathlib import Path

import cv2
import paho.mqtt.client as mqtt
import pytest

IMAGE = os.environ["IMAGE"]  # ci.yml 會傳這個 env var
MQTT_TOPIC = "jetson/vision/detections"
SAMPLE_FRAME = Path(__file__).parent / "sample_frame.jpg"
CONTAINER_NAME = "edgeai-hw6-integration-test"
ENGINE_LOAD_TIMEOUT = 600  # 10 分鐘（第一次 compile 很慢）
MQTT_WAIT_TIMEOUT = 60     # 調寬至 60 秒，給予 Jetson 足夠的時間初始化 CUDA 與第一幀推論


@pytest.fixture
def inference_container(tmp_path):
    """Generate a short video from sample_frame.jpg, start container."""
    sample_path = Path(__file__).parent / "sample_frame.jpg"
    if not sample_path.exists():
        pytest.skip(f"sample_frame.jpg not found at {sample_path}")

    # 用 OpenCV 把單張 JPG 轉成 5 秒影片
    img = cv2.imread(str(sample_path))
    if img is None:
        pytest.fail(f"Cannot read {sample_path}")

    h, w = img.shape[:2]
    video_path = tmp_path / "test_video.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, 10.0, (w, h))
    if not writer.isOpened():
        pytest.fail("Cannot open VideoWriter")
    for _ in range(50):  # 50 frames @ 10 fps = 5 seconds
        writer.write(img)
    writer.release()

    # 確保檔案有寫出來
    if not video_path.exists() or video_path.stat().st_size == 0:
        pytest.fail("Failed to generate video from sample frame")

    # 後續 docker run
    subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True,
        check=False,
    )
    subprocess.run(["docker", "pull", IMAGE], check=True, timeout=300)
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            CONTAINER_NAME,
            "--runtime",
            "nvidia",
            "--network",
            "host",
            "-v",
            "lab12-models:/opt/models",
            "-v",
            f"{video_path}:/opt/data/test_video.mp4:ro",
            IMAGE,
        ],
        check=True,
    )

    yield CONTAINER_NAME

    # 修正 cleanup 與日誌完整輸出機制，確保能看到 Python 的錯誤 Traceback
    logs = subprocess.run(
        ["docker", "logs", CONTAINER_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    print("\n========== Container STDOUT ==========")
    print(logs.stdout if logs.stdout.strip() else "(Empty)")
    print("\n========== Container STDERR ==========")
    print(logs.stderr if logs.stderr.strip() else "(Empty)")

    subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True,
        check=False,
    )


def test_image_is_per_commit_sha_tagged():
    """The image must be the per-commit tag, not a stale :latest."""
    assert "sha-" in IMAGE, f"Expected sha-tagged image, got {IMAGE}"


def test_inference_publishes_mqtt_within_window(inference_container):
    """End-to-end: container should publish MQTT detections within window."""
    # 訂閱 MQTT
    msg_queue = queue.Queue()

    def on_message(_client, _userdata, msg):
        msg_queue.put(json.loads(msg.payload))

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="integration-test-subscriber",
    )
    client.on_message = on_message
    client.connect("localhost", 1883, keepalive=60)
    client.subscribe(MQTT_TOPIC, qos=1)
    client.loop_start()

    try:
        # 等訊息進來
        deadline = time.time() + MQTT_WAIT_TIMEOUT
        while time.time() < deadline:
            try:
                msg = msg_queue.get(timeout=1)
                # 收到訊息了
                assert "frame" in msg, f"MQTT payload missing 'frame': {msg}"
                assert "detections" in msg, "MQTT payload missing 'detections'"
                return
            except queue.Empty:
                continue

        pytest.fail(
            f"No MQTT messages on {MQTT_TOPIC} within {MQTT_WAIT_TIMEOUT}s. "
            f"Check 'docker logs {CONTAINER_NAME}' for clues."
        )
    finally:
        client.loop_stop()
        client.disconnect()
