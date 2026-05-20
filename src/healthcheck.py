#!/usr/bin/env python3
# Copyright (c) 2026 henry1tsai
# Tatung University — I4210 AI實務專題
"""src/healthcheck.py — Minimal /healthz HTTP endpoint for the inference container.

Started as a background thread by inference_node.main() so every container
gets the endpoint for free without a sidecar.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT: int = int(os.environ.get("HEALTHZ_PORT", "8000"))
MODEL_VERSION: str = os.environ.get("MODEL_VERSION", "unknown")


def _current_power_mode() -> str:
    """Read the live nvpmodel state; return empty string if unavailable."""
    nvpmodel_bin = shutil.which("nvpmodel") or ""
    if not nvpmodel_bin:
        return ""
    try:
        out = subprocess.run(
            [nvpmodel_bin, "-q"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        for line in out.stdout.splitlines():
            if "Power Mode" in line:
                return line.split(":", 1)[1].strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""


class HealthCheckServer:
    """Lightweight HTTP server exposing a /healthz endpoint."""

    def __init__(self, port: int = PORT) -> None:
        """Initialise with the given port.

        Args:
            port: TCP port to listen on.
        """
        self._port = port
        self._server: HTTPServer | None = None

    def start_in_thread(self) -> threading.Thread:
        """Start the healthz server on a daemon thread.

        Returns:
            The started daemon thread.
        """
        self._server = HTTPServer(("0.0.0.0", self._port), _Handler)
        t = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="healthz",
        )
        t.start()
        return t


class _Handler(BaseHTTPRequestHandler):
    """Handle GET /healthz requests."""

    def do_GET(self) -> None:
        """Respond to GET requests on /healthz."""
        if self.path != "/healthz":
            self.send_error(404)
            return
        body = json.dumps(
            {
                "status": "healthy",
                "model_version": MODEL_VERSION,
                "power_mode": _current_power_mode(),
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        """Suppress per-request stderr logging."""


def start_in_thread() -> threading.Thread:
    """Start the healthz server as a module-level convenience function.

    Returns:
        The started daemon thread.
    """
    return HealthCheckServer().start_in_thread()
