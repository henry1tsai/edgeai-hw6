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
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PORT: int = int(os.environ.get("HEALTHZ_PORT", "8000"))
MODEL_VERSION: str = os.environ.get("MODEL_VERSION", "unknown")

# nvpmodel state files — bind-mounted read-only into the container by
# deploy/docker-compose.yml (see Part D2 of the assignment). Reading these
# directly avoids invoking the nvpmodel binary inside the container, which
# would need procfs paths that can't be bind-mounted at runtime.
_STATUS_PATH: Path = Path("/var/lib/nvpmodel/status")
_CONF_PATH: Path = Path("/etc/nvpmodel.conf")


def _current_power_mode() -> str:
    """Read current power mode by resolving status file ID against conf NAME map.

    Returns:
        Power mode name (e.g. "15W", "MAXN_SUPER"), or empty string when the
        nvpmodel files are unavailable (e.g. running tests on x86 with no
        Jetson, or the bind-mount is missing).
    """
    if not _STATUS_PATH.exists() or not _CONF_PATH.exists():
        return ""
    try:
        # status file format: "pmode:0001 fmode:fanNull"
        status = _STATUS_PATH.read_text().strip()
        mode_id = int(status.split(":")[1].split()[0])
        # conf file has lines like "< POWER_MODEL ID=1 NAME=15W >"
        for line in _CONF_PATH.read_text().splitlines():
            if "POWER_MODEL" not in line or f"ID={mode_id}" not in line:
                continue
            for token in line.split():
                if token.startswith("NAME="):
                    return token.split("=", 1)[1].rstrip(">").strip()
    except (OSError, ValueError, IndexError):
        return ""
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

        Binds to 127.0.0.1 because docker-compose.yml uses network_mode: host,
        so host-side healthcheck.sh reaches this endpoint via the host's
        loopback interface. Avoids the wider attack surface of binding to
        0.0.0.0 while still satisfying the deploy-side healthcheck.

        Returns:
            The started daemon thread.
        """
        self._server = HTTPServer(("127.0.0.1", self._port), _Handler)
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