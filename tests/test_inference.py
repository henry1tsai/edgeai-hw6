#!/usr/bin/env python3
# Copyright (c) 2026 henry1tsai
# Tatung University — I4210 AI實務專題
"""tests/test_inference.py — unit tests for inference pipeline helpers."""

from unittest.mock import MagicMock

import numpy as np
import pytest

from src.inference_node import (
    apply_confidence_threshold,
    detections_to_payload,
    preprocess_frame,
)

# ── preprocess_frame ──────────────────────────────────────────────────


@pytest.mark.parametrize("shape", [(480, 640, 3), (720, 1280, 3), (320, 320, 3)])
def test_preprocess_frame_output_shape(shape: tuple[int, ...]) -> None:
    """preprocess_frame() must return (1, 3, H, W) float32 tensor."""
    frame = (np.random.rand(*shape) * 255).astype(np.uint8)
    out = preprocess_frame(frame, target_size=(320, 320))
    assert out.shape == (1, 3, 320, 320)
    assert out.dtype == np.float32


def test_preprocess_frame_values_normalised() -> None:
    """Output values must be in [0, 1]."""
    frame = (np.random.rand(480, 640, 3) * 255).astype(np.uint8)
    out = preprocess_frame(frame, target_size=(320, 320))
    assert float(out.min()) >= 0.0
    assert float(out.max()) <= 1.0


def test_preprocess_frame_handles_grayscale() -> None:
    """Single-channel input must be broadcast to 3 channels."""
    gray = (np.random.rand(480, 640) * 255).astype(np.uint8)
    out = preprocess_frame(gray, target_size=(320, 320))
    assert out.shape == (1, 3, 320, 320)


# ── apply_confidence_threshold ────────────────────────────────────────

_DETECTIONS = [
    {"cls": 0, "conf": 0.99, "xyxy": [0, 0, 10, 10]},
    {"cls": 1, "conf": 0.75, "xyxy": [10, 10, 20, 20]},
    {"cls": 0, "conf": 0.55, "xyxy": [20, 20, 30, 30]},
    {"cls": 2, "conf": 0.30, "xyxy": [30, 30, 40, 40]},
    {"cls": 1, "conf": 0.10, "xyxy": [40, 40, 50, 50]},
]


@pytest.mark.parametrize(
    "conf_thresh,expected_count",
    [
        (0.0, 5),
        (0.5, 3),
        (0.95, 1),
    ],
)
def test_apply_confidence_threshold(conf_thresh: float, expected_count: int) -> None:
    """Filtering by confidence must drop detections below the threshold."""
    out = apply_confidence_threshold(_DETECTIONS, conf_thresh)
    assert len(out) == expected_count


def test_apply_confidence_threshold_empty_input() -> None:
    """Empty input list must return empty list."""
    assert apply_confidence_threshold([], 0.5) == []


# ── detections_to_payload ─────────────────────────────────────────────


def test_detections_to_payload_required_fields() -> None:
    """Payload must always contain frame, ts, detections, count."""
    payload = detections_to_payload(42, 1700000000.0, [])
    assert payload["frame"] == 42
    assert payload["ts"] == 1700000000.0
    assert payload["detections"] == []
    assert payload["count"] == 0


def test_detections_to_payload_count_matches_list() -> None:
    """Count must equal len(detections)."""
    dets = [{"class": "Hardhat", "conf": 0.9}] * 3
    payload = detections_to_payload(1, 0.0, dets)
    assert payload["count"] == 3


# ── camera mock ───────────────────────────────────────────────────────


@pytest.fixture
def mock_video_capture() -> MagicMock:
    """Mock cv2.VideoCapture so tests don't need a real camera."""
    fake = MagicMock()
    fake.isOpened.return_value = True
    fake.read.side_effect = [
        (True, (np.random.rand(480, 640, 3) * 255).astype(np.uint8)),
        (True, (np.random.rand(480, 640, 3) * 255).astype(np.uint8)),
        (False, None),
    ]
    return fake


def test_mock_video_capture_read_count(mock_video_capture: MagicMock) -> None:
    """Fixture must return exactly the configured number of frames."""
    results = []
    while True:
        ret, frame = mock_video_capture.read()
        if not ret:
            break
        results.append(frame)
    assert len(results) == 2
    assert mock_video_capture.read.call_count == 3


# ── write_health ──────────────────────────────────────────────────────


def test_write_health_creates_file(tmp_path: "pytest.TempPathFactory") -> None:
    """write_health() must write a float timestamp to the given path."""
    from src.inference_node import write_health

    p = tmp_path / "health"
    write_health(str(p))
    assert p.exists()
    assert float(p.read_text()) > 0


def test_write_health_oserror_is_silent(tmp_path: "pytest.TempPathFactory") -> None:
    """write_health() must not raise when the path is unwritable."""
    from src.inference_node import write_health

    bad_path = str(tmp_path / "no_dir" / "health")
    write_health(bad_path)  # must not raise


# ── InferenceNode ─────────────────────────────────────────────────────


def test_inference_node_init() -> None:
    """InferenceNode stores all constructor args correctly."""
    from unittest.mock import MagicMock

    from src.inference_node import InferenceNode, NodeConfig
    from src.mqtt_publisher import MqttPublisher, PublisherConfig

    pub = MqttPublisher(PublisherConfig(), client_factory=lambda: MagicMock())
    factory = MagicMock()
    cfg = NodeConfig(
        model_path="/tmp/m.engine",
        source="/tmp/v.mp4",
        imgsz=320,
        conf=0.25,
        topic="/test/topic",
        model_factory=factory,
    )
    node = InferenceNode(cfg, pub)
    assert node._model_path == "/tmp/m.engine"
    assert node._source == "/tmp/v.mp4"
    assert node._imgsz == 320
    assert node._conf == 0.25
    assert node._topic == "/test/topic"
    assert node._model_factory is factory


def test_inference_node_build_detections() -> None:
    """_build_detections() converts Ultralytics result objects to dicts."""
    from unittest.mock import MagicMock

    import numpy as np

    from src.inference_node import InferenceNode, NodeConfig
    from src.mqtt_publisher import MqttPublisher, PublisherConfig

    pub = MqttPublisher(PublisherConfig(), client_factory=lambda: MagicMock())
    cfg = NodeConfig(model_path="/m", source="/s", imgsz=320, conf=0.25, topic="/t")
    node = InferenceNode(cfg, pub)

    box = MagicMock()
    box.cls = np.array([0])
    box.conf = np.array([0.88])
    box.xyxy = [np.array([10.0, 20.0, 30.0, 40.0])]

    result = MagicMock()
    result.names = {0: "Hardhat"}
    result.boxes = [box]

    dets = node._build_detections([result])
    assert len(dets) == 1
    assert dets[0]["class"] == "Hardhat"
    assert dets[0]["confidence"] == 0.88
    assert dets[0]["conf"] == 0.88


def test_inference_node_build_detections_empty() -> None:
    """_build_detections() returns empty list when results have no boxes."""
    from unittest.mock import MagicMock

    from src.inference_node import InferenceNode, NodeConfig
    from src.mqtt_publisher import MqttPublisher, PublisherConfig

    pub = MqttPublisher(PublisherConfig(), client_factory=lambda: MagicMock())
    cfg = NodeConfig(model_path="/m", source="/s", imgsz=320, conf=0.25, topic="/t")
    node = InferenceNode(cfg, pub)

    result = MagicMock()
    result.boxes = []
    assert node._build_detections([result]) == []


def test_signal_handler_sets_running_false() -> None:
    """_signal_handler must set _running to False."""
    import src.inference_node as mod
    from src.inference_node import _signal_handler

    mod._running = True
    _signal_handler(15, None)
    assert mod._running is False
    mod._running = True  # restore


def test_main_parses_args_and_builds_node() -> None:
    """main() must parse CLI args without crashing (node.run is mocked)."""
    from unittest.mock import MagicMock, patch

    with (
        patch("src.inference_node.MqttPublisher") as mock_pub_cls,
        patch("src.inference_node.InferenceNode") as mock_node_cls,
    ):
        mock_pub_instance = MagicMock()
        mock_pub_cls.return_value = mock_pub_instance
        mock_node_instance = MagicMock()
        mock_node_cls.return_value = mock_node_instance

        from src.inference_node import main

        main(["--mqtt-broker", "testbroker", "--mqtt-port", "1883"])

        mock_pub_cls.assert_called_once()
        mock_pub_instance.connect.assert_called_once()
        mock_node_cls.assert_called_once()
        mock_node_instance.run.assert_called_once()
