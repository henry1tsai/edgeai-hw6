#!/usr/bin/env python3
# Copyright (c) 2026 henry1tsai
# Tatung University — I4210 AI實務專題
"""tests/test_healthcheck.py — unit tests for HealthCheckServer."""

import json
import threading
import time
from http.client import HTTPConnection
from unittest.mock import MagicMock, patch

from src.healthcheck import HealthCheckServer, _current_power_mode, start_in_thread


def test_current_power_mode_no_nvpmodel() -> None:
    """Return empty string when nvpmodel binary is not found."""
    with patch("src.healthcheck.shutil.which", return_value=None):
        assert _current_power_mode() == ""


def test_current_power_mode_timeout() -> None:
    """Return empty string when nvpmodel times out."""
    import subprocess

    with (
        patch("src.healthcheck.shutil.which", return_value="/usr/sbin/nvpmodel"),
        patch(
            "src.healthcheck.subprocess.run", side_effect=subprocess.TimeoutExpired("nvpmodel", 2)
        ),
    ):
        assert _current_power_mode() == ""


def test_current_power_mode_parses_output() -> None:
    """Parse 'Power Mode' line from nvpmodel -q output."""
    mock_result = MagicMock()
    mock_result.stdout = "NV Power Mode: 15W\nSome other line\n"
    with (
        patch("src.healthcheck.shutil.which", return_value="/usr/sbin/nvpmodel"),
        patch("src.healthcheck.subprocess.run", return_value=mock_result),
    ):
        assert _current_power_mode() == "15W"


def test_healthcheck_server_starts_thread() -> None:
    """start_in_thread() must return a running daemon thread."""
    server = HealthCheckServer(port=18765)
    t = server.start_in_thread()
    assert isinstance(t, threading.Thread)
    assert t.daemon is True
    assert t.is_alive()


def test_healthz_returns_200() -> None:
    """GET /healthz must return 200 with JSON body."""
    server = HealthCheckServer(port=18766)
    server.start_in_thread()
    time.sleep(0.1)
    conn = HTTPConnection("localhost", 18766, timeout=3)
    conn.request("GET", "/healthz")
    resp = conn.getresponse()
    assert resp.status == 200
    body = json.loads(resp.read())
    assert body["status"] == "healthy"
    conn.close()


def test_healthz_404_on_unknown_path() -> None:
    """GET /unknown must return 404."""
    server = HealthCheckServer(port=18767)
    server.start_in_thread()
    time.sleep(0.1)
    conn = HTTPConnection("localhost", 18767, timeout=3)
    conn.request("GET", "/unknown")
    resp = conn.getresponse()
    assert resp.status == 404
    conn.close()


def test_module_start_in_thread() -> None:
    """Module-level start_in_thread() convenience function works."""
    with patch("src.healthcheck.HealthCheckServer.start_in_thread") as mock_start:
        mock_start.return_value = MagicMock(spec=threading.Thread)
        t = start_in_thread()
        mock_start.assert_called_once()
        assert t is mock_start.return_value
