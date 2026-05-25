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

import paho.mqtt.client as mqtt
import pytest

IMAGE = os.environ["IMAGE"]   # ci.yml 會傳這個 env var
MQTT_TOPIC = "jetson/vision/detections"
SAMPLE_FRAME = Path(__file__).parent / "sample_frame.jpg"
CONTAINER_NAME = "edgeai-hw6-integration-test"
ENGINE_LOAD_TIMEOUT = 600     # 10 分鐘（第一次 compile 很慢）
MQTT_WAIT_TIMEOUT = 30        # 30 秒等 MQTT 訊息


@pytest.fixture
def inference_container():
    """Pull the per-commit image, start container, yield to test, then cleanup."""
    # 1. 確保沒有殘留 container
    subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True, check=False,
    )

    # 2. 拉 image
    subprocess.run(
        ["docker", "pull", IMAGE],
        check=True, timeout=300,
    )

    # 3. 啟動 container
    subprocess.run([
        "docker", "run", "-d",
        "--name", CONTAINER_NAME,
        "--runtime", "nvidia",
        "--network", "host",
        "-v", "lab12-models:/opt/models",
        IMAGE,
    ], check=True)

    yield CONTAINER_NAME

    # 4. 清理（不管成功失敗都跑）
    subprocess.run(
        ["docker", "logs", CONTAINER_NAME],
        capture_output=True, check=False,
    )
    subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True, check=False,
    )


def test_image_is_per_commit_sha_tagged():
    """The image must be the per-commit tag, not a stale :latest."""
    assert "sha-" in IMAGE, f"Expected sha-tagged image, got {IMAGE}"


def test_inference_publishes_mqtt_within_window(inference_container):
    """End-to-end: container should publish MQTT detections within 30s."""
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
