"""Tests for the TelemetryReceiver class.

Covers initialization, packet parsing, buffer management,
callback dispatch, and thread lifecycle.
"""

import struct
import time
import socket
import threading
from unittest.mock import MagicMock, patch

import pytest

from ground_station.telemetry_receiver import (
    TelemetryReceiver,
    RawTelemetryEntry,
    TLM_MID_RAD,
    TLM_MID_THERM,
    CFE_EVS_LONG_EVENT_MSG_MID,
)
from sensor_manager.core.ccsds_utils import pack_telemetry_packet


class TestTelemetryReceiverInit:
    """Test TelemetryReceiver initialization."""

    def test_default_port(self):
        """Default port is 2234."""
        with patch.dict("os.environ", {}, clear=True):
            r = TelemetryReceiver()
            assert r.port == 2234

    def test_custom_port(self):
        """Accepts explicit port argument."""
        r = TelemetryReceiver(port=3456)
        assert r.port == 3456

    def test_env_port_override(self):
        """Reads GS_TLM_PORT from environment."""
        with patch.dict("os.environ", {"GS_TLM_PORT": "7890"}, clear=True):
            r = TelemetryReceiver()
            assert r.port == 7890

    def test_initial_state(self):
        """Receiver starts in stopped state with empty buffer."""
        r = TelemetryReceiver(port=2234)
        assert r.running is False
        assert r.packets_received == 0
        assert r.get_recent() == []

    def test_custom_buffer_size(self):
        """Buffer size is configurable."""
        r = TelemetryReceiver(port=2234, buffer_size=10)
        assert r.buffer_size == 10


class TestRawTelemetryEntry:
    """Test the RawTelemetryEntry dataclass."""

    def test_fields(self):
        """All fields are accessible."""
        entry = RawTelemetryEntry(
            timestamp=1000.0,
            mid=0x0882,
            raw_hex="aabbccdd",
            parsed={"type": "radiation", "value": 50.0},
            size=16,
        )
        assert entry.timestamp == 1000.0
        assert entry.mid == 0x0882
        assert entry.raw_hex == "aabbccdd"
        assert entry.parsed["type"] == "radiation"
        assert entry.size == 16


class TestPacketParsing:
    """Test the internal _parse_packet method."""

    def _make_receiver(self):
        return TelemetryReceiver(port=2234)

    def test_parse_radiation_telemetry(self):
        """Parses radiation telemetry with value and health status."""
        r = self._make_receiver()
        # Payload: 4-byte float (host/little-endian) + 1 byte (health) + 3 bytes (spare)
        value = 123.45
        health = 1  # WARNING
        payload = struct.pack("<f", value) + bytes([health, 0, 0, 0])
        packet = pack_telemetry_packet(TLM_MID_RAD, payload=payload, seconds=1000)

        result = r._parse_packet(TLM_MID_RAD, packet)
        assert result["type"] == "radiation"
        assert abs(result["value"] - 123.45) < 0.01
        assert result["health"] == 1
        assert result["health_label"] == "WARNING"

    def test_parse_thermal_telemetry(self):
        """Parses thermal telemetry with value and health status."""
        r = self._make_receiver()
        value = 85.0
        health = 2  # CRITICAL
        payload = struct.pack("<f", value) + bytes([health, 0, 0, 0])
        packet = pack_telemetry_packet(TLM_MID_THERM, payload=payload, seconds=2000)

        result = r._parse_packet(TLM_MID_THERM, packet)
        assert result["type"] == "thermal"
        assert abs(result["value"] - 85.0) < 0.01
        assert result["health"] == 2
        assert result["health_label"] == "CRITICAL"

    def test_parse_nominal_health(self):
        """Parses NOMINAL health status (0)."""
        r = self._make_receiver()
        payload = struct.pack("<f", 50.0) + bytes([0, 0, 0, 0])
        packet = pack_telemetry_packet(TLM_MID_RAD, payload=payload)

        result = r._parse_packet(TLM_MID_RAD, packet)
        assert result["health"] == 0
        assert result["health_label"] == "NOMINAL"

    def test_parse_evs_message(self):
        """Parses EVS event message text from payload."""
        r = self._make_receiver()
        text = "RAD_APP: FDIR TRIGGERED"
        payload = text.encode("ascii") + b"\x00" * 10
        packet = pack_telemetry_packet(
            CFE_EVS_LONG_EVENT_MSG_MID, payload=payload
        )

        result = r._parse_packet(CFE_EVS_LONG_EVENT_MSG_MID, packet)
        assert result["type"] == "evs"
        assert "RAD_APP" in result["event_text"]
        assert "FDIR" in result["event_text"]

    def test_parse_unknown_mid(self):
        """Unknown MIDs produce type='unknown' with hex payload."""
        r = self._make_receiver()
        payload = b"\x01\x02\x03\x04"
        packet = pack_telemetry_packet(0x08FF, payload=payload)

        result = r._parse_packet(0x08FF, packet)
        assert result["type"] == "unknown"
        assert "payload_hex" in result

    def test_parse_radiation_short_payload(self):
        """Radiation packet with exactly 4-byte payload (no health byte)."""
        r = self._make_receiver()
        payload = struct.pack("<f", 50.0)
        packet = pack_telemetry_packet(TLM_MID_RAD, payload=payload)

        result = r._parse_packet(TLM_MID_RAD, packet)
        assert result["type"] == "radiation"
        assert result["health"] == 0  # Default when missing

    def test_parse_too_short_packet(self):
        """Very short packet returns raw hex."""
        r = self._make_receiver()
        result = r._parse_packet(TLM_MID_RAD, b"\x08\x82\xc0\x00")
        assert "raw" in result

    def test_parse_evs_non_ascii(self):
        """EVS with non-printable bytes returns hex fallback."""
        r = self._make_receiver()
        payload = bytes(range(0, 16))  # Mostly non-printable
        packet = pack_telemetry_packet(
            CFE_EVS_LONG_EVENT_MSG_MID, payload=payload
        )
        result = r._parse_packet(CFE_EVS_LONG_EVENT_MSG_MID, packet)
        assert result["type"] == "evs"


class TestCallbackRegistration:
    """Test callback registration and dispatch."""

    def test_register_callback(self):
        """Callbacks can be registered."""
        r = TelemetryReceiver(port=2234)
        cb = MagicMock()
        r.register_callback(cb)
        assert cb in r._callbacks

    def test_multiple_callbacks(self):
        """Multiple callbacks can be registered."""
        r = TelemetryReceiver(port=2234)
        cb1 = MagicMock()
        cb2 = MagicMock()
        r.register_callback(cb1)
        r.register_callback(cb2)
        assert len(r._callbacks) == 2


class TestBufferManagement:
    """Test the ring buffer and get_recent() method."""

    def test_get_recent_empty(self):
        """get_recent on empty buffer returns empty list."""
        r = TelemetryReceiver(port=2234)
        assert r.get_recent() == []

    def test_get_recent_respects_count(self):
        """get_recent limits to requested count."""
        r = TelemetryReceiver(port=2234)
        for i in range(10):
            entry = RawTelemetryEntry(
                timestamp=float(i), mid=0x0882,
                raw_hex="aa", parsed={}, size=8,
            )
            r._buffer.append(entry)

        result = r.get_recent(count=3)
        assert len(result) == 3
        assert result[0].timestamp == 7.0  # Newest 3

    def test_buffer_size_limit(self):
        """Buffer respects max size (ring buffer behavior)."""
        r = TelemetryReceiver(port=2234, buffer_size=5)
        for i in range(10):
            entry = RawTelemetryEntry(
                timestamp=float(i), mid=0x0882,
                raw_hex="aa", parsed={}, size=8,
            )
            r._buffer.append(entry)

        assert len(r._buffer) == 5
        result = r.get_recent(count=10)
        assert len(result) == 5
        assert result[0].timestamp == 5.0  # Oldest retained


class TestReceiverLifecycle:
    """Test start/stop behavior."""

    def test_start_sets_running(self):
        """start() sets running flag and creates thread."""
        r = TelemetryReceiver(host="127.0.0.1", port=0)  # Port 0 = OS-assigned
        # We'll mock the socket to avoid actually binding
        with patch.object(r, "_listen_loop"):
            r.start()
            assert r.running is True
            r.stop()

    def test_double_start_is_noop(self):
        """Calling start() twice doesn't create a second thread."""
        r = TelemetryReceiver(host="127.0.0.1", port=0)
        with patch.object(r, "_listen_loop"):
            r.start()
            first_thread = r._thread
            r.start()  # Should be a no-op
            assert r._thread is first_thread
            r.stop()

    def test_stop_sets_not_running(self):
        """stop() clears the running flag."""
        r = TelemetryReceiver(host="127.0.0.1", port=0)
        with patch.object(r, "_listen_loop"):
            r.start()
            r.stop()
            assert r.running is False

    def test_stop_without_start(self):
        """stop() on a not-started receiver is safe."""
        r = TelemetryReceiver(port=2234)
        r.stop()  # Should not raise
        assert r.running is False


class TestListenLoopIntegration:
    """Integration test for the actual UDP listen loop."""

    def test_receives_and_parses_udp_packet(self):
        """End-to-end: send a TLM packet and verify it's received."""
        # Find a free port first
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(("127.0.0.1", 0))
        actual_port = probe.getsockname()[1]
        probe.close()

        r = TelemetryReceiver(host="127.0.0.1", port=actual_port)

        received = []
        r.register_callback(lambda e: received.append(e))
        r.start()

        try:
            # Give the listen thread time to bind
            time.sleep(0.3)

            # Send a radiation telemetry packet (cFS stores floats in host/LE order)
            payload = struct.pack("<f", 75.0) + bytes([0, 0, 0, 0])
            packet = pack_telemetry_packet(TLM_MID_RAD, payload=payload)

            send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            send_sock.sendto(packet, ("127.0.0.1", actual_port))
            send_sock.close()

            # Wait for processing
            time.sleep(0.5)

            assert r.packets_received >= 1
            assert len(received) >= 1
            entry = received[0]
            assert entry.mid == TLM_MID_RAD
            assert entry.parsed["type"] == "radiation"
            assert abs(entry.parsed["value"] - 75.0) < 0.01

        finally:
            r.stop()

    def test_ignores_too_short_packets(self):
        """Packets shorter than 6 bytes are silently dropped."""
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(("127.0.0.1", 0))
        actual_port = probe.getsockname()[1]
        probe.close()

        r = TelemetryReceiver(host="127.0.0.1", port=actual_port)
        r.start()

        try:
            time.sleep(0.3)

            send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            send_sock.sendto(b"\x01\x02", ("127.0.0.1", actual_port))
            send_sock.close()

            time.sleep(0.5)
            assert r.packets_received == 0

        finally:
            r.stop()
