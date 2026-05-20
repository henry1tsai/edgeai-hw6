#!/usr/bin/env python3
# Copyright (c) 2026 henry1tsai
# Tatung University — I4210 AI實務專題
"""tests/test_mqtt.py — unit tests for MqttPublisher."""

import json
from unittest.mock import MagicMock

import paho.mqtt.client as mqtt
import pytest

from src.mqtt_publisher import MqttPublisher, PublisherConfig


@pytest.fixture
def mock_client() -> MagicMock:
    """Return a MagicMock that behaves like paho.mqtt.client.Client."""
    client = MagicMock(spec=mqtt.Client)
    info = MagicMock()
    info.rc = mqtt.MQTT_ERR_SUCCESS
    client.publish.return_value = info
    return client


@pytest.fixture
def publisher(mock_client: MagicMock) -> MqttPublisher:
    """Build a publisher wired to the mock client (no real network)."""
    return MqttPublisher(
        PublisherConfig(host="test-broker"),
        client_factory=lambda: mock_client,
    )


def test_publish_sends_json_payload(publisher: MqttPublisher, mock_client: MagicMock) -> None:
    """publish() must JSON-encode dicts and call client.publish()."""
    publisher._connected = True
    payload = {"frame": 1, "ts": 1234567890.0}
    assert publisher.publish("jetson/vision/detections", payload) is True
    args, _ = mock_client.publish.call_args
    topic, body = args
    assert topic == "jetson/vision/detections"
    assert json.loads(body) == payload


def test_publish_when_disconnected_returns_false(
    publisher: MqttPublisher, mock_client: MagicMock
) -> None:
    """publish() before connect() must NOT raise — just return False."""
    assert publisher.connected is False
    assert publisher.publish("any/topic", {"x": 1}) is False
    mock_client.publish.assert_not_called()


def test_publish_string_payload_is_passed_through(
    publisher: MqttPublisher, mock_client: MagicMock
) -> None:
    """If caller passes a str, don't double-JSON-encode it."""
    publisher._connected = True
    publisher.publish("topic", "already-a-string")
    args, _ = mock_client.publish.call_args
    assert args[1] == "already-a-string"


def test_disconnect_stops_loop(publisher: MqttPublisher, mock_client: MagicMock) -> None:
    """disconnect() must call loop_stop and disconnect on the client."""
    publisher._connected = True
    publisher.disconnect()
    mock_client.loop_stop.assert_called_once()
    mock_client.disconnect.assert_called_once()
    assert publisher.connected is False


def test_reconnect_delays_set(publisher: MqttPublisher, mock_client: MagicMock) -> None:
    """Verify the publisher configured paho exponential reconnect."""
    mock_client.reconnect_delay_set.assert_called_once()


def test_publish_list_payload_is_json_encoded(
    publisher: MqttPublisher, mock_client: MagicMock
) -> None:
    """publish() must JSON-encode lists just like dicts."""
    publisher._connected = True
    payload = [1, 2, 3]
    publisher.publish("topic", payload)
    args, _ = mock_client.publish.call_args
    assert json.loads(args[1]) == payload


def test_on_connect_sets_connected_flag(publisher: MqttPublisher) -> None:
    """_on_connect sets _connected=True when reason_code == 0."""
    rc = MagicMock()
    rc.value = 0
    publisher._on_connect(MagicMock(), None, None, rc)
    assert publisher.connected is True


def test_on_connect_failed_keeps_disconnected(publisher: MqttPublisher) -> None:
    """_on_connect keeps _connected=False when reason_code != 0."""
    rc = MagicMock()
    rc.value = 5
    publisher._on_connect(MagicMock(), None, None, rc)
    assert publisher.connected is False


def test_on_disconnect_clears_flag(publisher: MqttPublisher) -> None:
    """_on_disconnect sets _connected=False."""
    publisher._connected = True
    publisher._on_disconnect(MagicMock(), None, None, 0)
    assert publisher.connected is False


def test_connect_returns_true_on_success(publisher: MqttPublisher, mock_client: MagicMock) -> None:
    """connect() returns True when paho connect succeeds."""
    mock_client.connect.return_value = None
    result = publisher.connect()
    assert result is True
    mock_client.loop_start.assert_called_once()


def test_connect_returns_false_on_oserror(publisher: MqttPublisher, mock_client: MagicMock) -> None:
    """connect() returns False when paho raises OSError."""
    mock_client.connect.side_effect = OSError("refused")
    result = publisher.connect()
    assert result is False


def test_on_connect_integer_reason_code(publisher: MqttPublisher) -> None:
    """_on_connect handles plain int reason_code (no .value attribute)."""
    publisher._on_connect(MagicMock(), None, None, 0)
    assert publisher.connected is True
