#!/usr/bin/env python3
# Copyright (c) 2026 henry1tsai
# Tatung University — I4210 AI實務專題
"""src/mqtt_publisher.py — Thin paho-mqtt wrapper with reconnect and JSON encoding.

Pulled out of inference_node so it is unit-testable without starting a real broker.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

logger = logging.getLogger(__name__)


@dataclass
class PublisherConfig:
    """Configuration for MqttPublisher."""

    host: str = "localhost"
    port: int = 1883
    keepalive: int = 60
    client_id: str = ""
    reconnect_min_delay: float = 1.0
    reconnect_max_delay: float = 30.0
    topic: str = "/sense/vision/detections"
    extra_fields: dict[str, str] = field(default_factory=dict)


class MqttPublisher:
    """Publish JSON messages to MQTT with automatic reconnection.

    The constructor accepts an optional ``client_factory`` so tests can
    inject a mock paho-mqtt Client without monkeypatching globals.
    """

    def __init__(
        self,
        config: PublisherConfig,
        client_factory: Callable[[], mqtt.Client] | None = None,
    ) -> None:
        """Initialise the publisher and attach paho callbacks."""
        self.config = config
        factory = client_factory or (
            lambda: mqtt.Client(
                callback_api_version=CallbackAPIVersion.VERSION2,
                client_id=config.client_id,
            )
        )
        self.client: mqtt.Client = factory()
        self.client.reconnect_delay_set(
            min_delay=int(config.reconnect_min_delay),
            max_delay=int(config.reconnect_max_delay),
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self._connected: bool = False

    # ------------------------------------------------------------------
    # paho callbacks
    # ------------------------------------------------------------------

    def _on_connect(
        self,
        _client: mqtt.Client,
        _userdata: object,
        _flags: object,
        reason_code: object,
        _properties: object = None,
    ) -> None:
        """Set connected flag when broker acknowledges the connection."""
        success = reason_code.value == 0 if hasattr(reason_code, "value") else reason_code == 0
        self._connected = success
        if success:
            logger.info("MQTT connected to %s:%s", self.config.host, self.config.port)
        else:
            logger.warning("MQTT connect failed, reason_code=%s", reason_code)

    def _on_disconnect(
        self,
        _client: mqtt.Client,
        _userdata: object,
        _flags: object,
        reason_code: object,
        _properties: object = None,
    ) -> None:
        """Set _connected to False on disconnect."""
        self._connected = False
        logger.info("MQTT disconnected, reason_code=%s", reason_code)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self, timeout: float = 5.0) -> bool:
        """Connect to the broker and start the network loop.

        Args:
            timeout: Seconds to wait (currently unused; reserved for future use).

        Returns:
            True if the connection was accepted, False otherwise.
        """
        del timeout  # reserved for future use
        try:
            self.client.connect(self.config.host, self.config.port, self.config.keepalive)
            self.client.loop_start()
            return True
        except OSError as exc:
            logger.error("MQTT connect error: %s", exc)
            return False

    def publish(self, topic: str, payload: object) -> bool:
        """Publish a message to *topic*.

        Dicts and lists are JSON-encoded; strings are passed through unchanged.

        Args:
            topic: The MQTT topic string.
            payload: Data to publish.  Dicts/lists are JSON-encoded; str passed as-is.

        Returns:
            True on success, False when not connected or on paho error.
        """
        if not self._connected:
            return False
        body = payload if isinstance(payload, str) else json.dumps(payload)
        result = self.client.publish(topic, body, qos=0)
        return bool(result.rc == mqtt.MQTT_ERR_SUCCESS)

    def disconnect(self) -> None:
        """Stop the network loop and disconnect cleanly."""
        self.client.loop_stop()
        self.client.disconnect()
        self._connected = False

    @property
    def connected(self) -> bool:
        """Return True if the broker connection is currently active."""
        return self._connected
