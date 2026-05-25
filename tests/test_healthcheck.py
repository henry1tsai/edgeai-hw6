#!/usr/bin/env python3
# Copyright (c) 2026 henry1tsai
# Tatung University — I4210 AI實務專題
"""tests/test_healthcheck.py — unit tests for HealthCheckServer."""

import json
import threading
import time
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.healthcheck import HealthCheckServer, _current_power_mode, start_in_thread


def test_current_power_mode_no_status_file(tmp_path: Path) -> None:
    """Return empty string when nvpmodel status file is not found."""
    nonexistent = tmp_path / "nope"
    with patch("src.healthcheck._STATUS_PATH", nonexistent):
        assert _current_power_mode() == ""


def test_current_power_mode_read_error(tmp_path: Path) -> None:
    """Return empty string when reading nvpmodel files raises OSError."""
    status = tmp_path / "status"
    conf = tmp_path / "conf"
    status.write_text("pmode:0001 fmode:fanNull")
    conf.write_text("< POWER_MODEL ID=1 NAME=15W >")
    with (
        patch("src.healthcheck._STATUS_PATH", status),
        patch("src.healthcheck._CONF_PATH", conf),
        patch.object(Path, "read_text", side_effect=OSError("permission denied")),
    ):
        assert _current_power_mode() == ""


def test_current_power_mode_parses_status_and_conf(tmp_path: Path) -> None:
    """Parse mode ID from status file and resolve NAME from conf."""
    status = tmp_path / "status"
    conf = tmp_path / "conf"
    status.write_text("pmode:0001 fmode:fanNull")
    conf.write_text(
        "< POWER_MODEL ID=0 NAME=MAXN >\n"
        "< POWER_MODEL ID=1 NAME=15W >\n"
        "< POWER_MODEL ID=2 NAME=25W >\n"
    )
    with (
        patch("src.healthcheck._STATUS_PATH", status),
        patch("src.healthcheck._CONF_PATH", conf),
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
        