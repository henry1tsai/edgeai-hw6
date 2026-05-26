#!/usr/bin/env python3
# Copyright (c) 2026 henry1tsai
# Tatung University — I4210 AI實務專題
"""src/inference_node.py — YOLO TensorRT inference node.

Reads frames from a video file or camera, runs detection,
and publishes results via MqttPublisher.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import Protocol, cast, runtime_checkable

import cv2
import numpy as np

from src import healthcheck
from src.mqtt_publisher import MqttPublisher, PublisherConfig

# ── module-level state ────────────────────────────────────────────────
_running: bool = True
_GRAYSCALE_NDIM: int = 2


def _signal_handler(sig: int, _frame: object) -> None:
    """Set the global stop flag on SIGTERM or SIGINT."""
    global _running
    print(f"\n[inference] received signal {sig}, shutting down...")
    _running = False


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)

# ── helpers ───────────────────────────────────────────────────────────

HEALTH_PATH: str = os.environ.get("HEALTH_PATH", "/app/inference_health")


def write_health(path: str = HEALTH_PATH) -> None:
    """Write a heartbeat timestamp file for Docker HEALTHCHECK."""
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(str(time.time()))
    except OSError:
        pass


def preprocess_frame(
    frame: np.ndarray,
    target_size: tuple[int, int] = (320, 320),
) -> np.ndarray:
    """Resize and normalise a BGR/grayscale frame to a float32 CHW tensor.

    Args:
        frame: Input image as a NumPy array (HWC BGR or HW grayscale).
        target_size: ``(width, height)`` to resize to.

    Returns:
        Float32 array of shape ``(1, 3, H, W)`` with values in [0, 1].
    """
    if frame.ndim == _GRAYSCALE_NDIM:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    resized = cv2.resize(frame, target_size)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    chw = rgb.transpose(2, 0, 1).astype(np.float32) / 255.0
    return chw[np.newaxis, ...]


def apply_confidence_threshold(
    detections: list[dict[str, object]],
    conf_thresh: float,
) -> list[dict[str, object]]:
    """Filter detections whose confidence is below *conf_thresh*.

    Args:
        detections: List of detection dicts, each with a ``"conf"`` key.
        conf_thresh: Minimum confidence value (inclusive).

    Returns:
        Filtered list containing only detections with conf >= conf_thresh.
    """
    return [d for d in detections if float(str(d["conf"])) >= conf_thresh]


def detections_to_payload(
    frame_id: int,
    ts: float,
    detections: list[dict[str, object]],
) -> dict[str, object]:
    """Build the MQTT JSON payload dict.

    Args:
        frame_id: Sequential frame counter.
        ts: Unix timestamp in seconds.
        detections: List of detection dicts.

    Returns:
        Dict with keys ``frame``, ``ts``, ``detections``, ``count``.
    """
    return {
        "frame": frame_id,
        "ts": ts,
        "detections": detections,
        "count": len(detections),
    }


# ── Protocol for model results ────────────────────────────────────────


@runtime_checkable
class _Box(Protocol):
    """Protocol describing a paho detection box."""

    cls: object
    conf: object
    xyxy: object


@runtime_checkable
class _Result(Protocol):
    """Protocol describing an Ultralytics result object."""

    names: dict[int, str]
    boxes: list[_Box]


def _default_model_factory(path: str, task: str) -> object:  # pragma: no cover
    """Load a YOLO model lazily so unit tests do not import torch.

    Args:
        path: Path to the model weights or engine file.
        task: Ultralytics task string, e.g. ``"detect"``.

    Returns:
        A loaded YOLO model instance.
    """
    from ultralytics import YOLO

    return YOLO(path, task=task)


# ── InferenceNode class ───────────────────────────────────────────────


@dataclass
class NodeConfig:
    """Configuration bundle for InferenceNode."""

    model_path: str
    source: str
    imgsz: int
    conf: float
    topic: str
    model_factory: object = None


class InferenceNode:
    """Orchestrate frame capture, inference, and MQTT publishing."""

    def __init__(
        self,
        config: NodeConfig,
        publisher: MqttPublisher,
    ) -> None:
        """Initialise the node.

        Args:
            config: NodeConfig with model, source, and inference settings.
            publisher: Connected MqttPublisher instance.
        """
        self._model_path = config.model_path
        self._source = config.source
        self._imgsz = config.imgsz
        self._conf = config.conf
        self._publisher = publisher
        self._topic = config.topic
        self._model_factory = config.model_factory or _default_model_factory

    def _build_detections(self, results: list[_Result]) -> list[dict[str, object]]:
        """Convert Ultralytics result objects to plain dicts.

        Args:
            results: List of Ultralytics ``Results`` objects.

        Returns:
            List of detection dicts with ``class``, ``confidence``, ``bbox``.
        """
        detections: list[dict[str, object]] = []
        for r in results:
            for box in r.boxes:
                cls_val = box.cls
                conf_val = box.conf
                xyxy_val = box.xyxy
                cls_int = int(cls_val.item()) if hasattr(cls_val, "item") else int(str(cls_val))
                conf_float = round(
                    float(conf_val.item()) if hasattr(conf_val, "item") else float(str(conf_val)),
                    3,
                )
                xyxy_list = cast(list[list[float]], xyxy_val)
                bbox = [round(float(x), 1) for x in xyxy_list[0]]
                detections.append(
                    {
                        "class": r.names[cls_int],
                        "confidence": conf_float,
                        "bbox": bbox,
                        "conf": conf_float,
                    }
                )
        return detections

    def run(self) -> None:  # pragma: no cover
        """Run the inference loop until SIGTERM or video exhaustion."""
        model = self._model_factory(self._model_path, "detect")  # type: ignore[operator]
        cap = cv2.VideoCapture(self._source)
        if not cap.isOpened():
            print(f"[inference] cannot open source: {self._source}")
            sys.exit(1)

        frame_count = 0
        fps_start = time.monotonic()

        while _running:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
                if not ret:
                    break

            results = model.predict(frame, imgsz=self._imgsz, conf=self._conf, verbose=False)
            detections = self._build_detections(results)
            filtered = apply_confidence_threshold(detections, self._conf)
            payload = detections_to_payload(frame_count, round(time.time(), 3), filtered)

            self._publisher.publish(self._topic, json.dumps(payload))
            frame_count += 1

            if frame_count % 10 == 0:
                write_health()

            if frame_count % 100 == 0:
                elapsed = time.monotonic() - fps_start
                fps = frame_count / elapsed if elapsed > 0 else 0.0
                print(f"[inference] frame={frame_count} FPS={fps:.1f} det={len(filtered)}")

        cap.release()
        self._publisher.disconnect()
        print(f"[inference] done, total frames={frame_count}")


# ── entry point ───────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    """Parse CLI args and start the InferenceNode."""
    healthcheck.start_in_thread()
    parser = argparse.ArgumentParser(description="YOLO TensorRT inference node")
    parser.add_argument("--model", default="/opt/models/best.engine")
    parser.add_argument("--source", default="/opt/data/test_video.mp4")
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--mqtt-broker", default=os.getenv("MQTT_BROKER", "localhost"))
    parser.add_argument("--mqtt-port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    parser.add_argument("--mqtt-topic", default="/sense/vision/detections")
    args = parser.parse_args(argv)

    config = PublisherConfig(
        host=args.mqtt_broker,
        port=args.mqtt_port,
        topic=args.mqtt_topic,
    )
    publisher = MqttPublisher(config)
    publisher.connect()

    node_config = NodeConfig(
        model_path=args.model,
        source=args.source,
        imgsz=args.imgsz,
        conf=args.conf,
        topic=args.mqtt_topic,
    )
    node = InferenceNode(node_config, publisher)
    node.run()


if __name__ == "__main__":
    main()
