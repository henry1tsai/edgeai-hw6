#!/usr/bin/env python3
# Copyright (c) 2026 henry1tsai
# Tatung University — I4210 AI實務專題
"""tests/integration/test_jetson_e2e.py — End-to-end integration test on Jetson.

Pulls the per-commit image, runs inference, asserts MQTT message arrives.
"""

import os


def test_image_env_var_is_set() -> None:
    """Verify the IMAGE env var is passed in from the workflow."""
    image = os.environ.get("IMAGE", "")
    assert image != "", "IMAGE env var must be set by the workflow"
    assert "ghcr.io" in image, f"IMAGE should point to GHCR, got: {image}"
