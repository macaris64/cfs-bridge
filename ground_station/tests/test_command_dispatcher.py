"""Tests for the CommandDispatcher class.

Covers packet construction, UDP dispatch, sequence counting,
environment variable configuration, and error handling.
"""

import socket
import struct
from unittest.mock import MagicMock, patch

import pytest

from ground_station.command_dispatcher import CommandDispatcher
from sensor_manager.core.ccsds_utils import unpack_cmd_packet
from sensor_manager.core.mission_registry import MID, FC


class TestCommandDispatcherInit:
    """Test CommandDispatcher initialization and configuration."""

    def test_default_host_and_port(self):
        """Defaults to CFS_HOST env or 'cfs-flight' and port 1234."""
        with patch.dict("os.environ", {}, clear=True):
            d = CommandDispatcher()
            assert d.host == "cfs-flight"
            assert d.port == 1234

    def test_custom_host_and_port(self):
        """Accepts explicit host and port arguments."""
        d = CommandDispatcher(host="localhost", port=9999)
        assert d.host == "localhost"
        assert d.port == 9999

    def test_env_override(self):
        """Reads CFS_HOST and CFS_CMD_PORT from environment."""
        env = {"CFS_HOST": "my-cfs", "CFS_CMD_PORT": "5678"}
        with patch.dict("os.environ", env, clear=True):
            d = CommandDispatcher()
            assert d.host == "my-cfs"
            assert d.port == 5678

    def test_explicit_args_override_env(self):
        """Explicit args take precedence over environment variables."""
        env = {"CFS_HOST": "env-host", "CFS_CMD_PORT": "9999"}
        with patch.dict("os.environ", env, clear=True):
            d = CommandDispatcher(host="explicit-host", port=1111)
            assert d.host == "explicit-host"
            assert d.port == 1111

    def test_empty_history_on_init(self):
        """History starts empty."""
        d = CommandDispatcher(host="localhost", port=1234)
        assert d.history == []


class TestCommandDispatcherSend:
    """Test the send() method for packet construction and dispatch."""

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_send_noop_command(self, mock_socket_cls):
        """Sends a valid NOOP command and returns byte count."""
        mock_sock = MagicMock()
        mock_sock.sendto.return_value = 8
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        result = d.send(MID.RADIATION_APP, FC.NOOP)

        assert result == 8
        mock_sock.sendto.assert_called_once()
        args = mock_sock.sendto.call_args
        assert args[0][1] == ("localhost", 1234)
        mock_sock.close.assert_called_once()

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_send_constructs_valid_ccsds_packet(self, mock_socket_cls):
        """The sent packet is a valid CCSDS command packet."""
        mock_sock = MagicMock()
        sent_data = []

        def capture_send(data, addr):
            sent_data.append(data)
            return len(data)

        mock_sock.sendto.side_effect = capture_send
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        d.send(MID.SOLAR_ARRAY_APP, FC.SOLAR_ARRAY_OPEN)

        assert len(sent_data) == 1
        packet = sent_data[0]
        parsed = unpack_cmd_packet(packet)
        assert parsed["apid"] == MID.SOLAR_ARRAY_APP & 0x7FF
        assert parsed["func_code"] == FC.SOLAR_ARRAY_OPEN

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_send_with_payload(self, mock_socket_cls):
        """Payload bytes are included in the packet."""
        mock_sock = MagicMock()
        sent_data = []

        def capture_send(data, addr):
            sent_data.append(data)
            return len(data)

        mock_sock.sendto.side_effect = capture_send
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        payload = struct.pack("!f", 42.0)
        d.send(MID.RADIATION_APP, FC.SEND_DATA, payload=payload)

        packet = sent_data[0]
        parsed = unpack_cmd_packet(packet)
        value = struct.unpack("!f", parsed["payload"])[0]
        assert abs(value - 42.0) < 0.01

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_send_records_history(self, mock_socket_cls):
        """Each send appends to the history list."""
        mock_sock = MagicMock()
        mock_sock.sendto.return_value = 8
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        d.send(MID.SOLAR_ARRAY_APP, FC.SOLAR_ARRAY_OPEN)
        d.send(MID.SOLAR_ARRAY_APP, FC.SOLAR_ARRAY_CLOSE)

        assert len(d.history) == 2
        assert d.history[0]["func_code"] == FC.SOLAR_ARRAY_OPEN
        assert d.history[1]["func_code"] == FC.SOLAR_ARRAY_CLOSE
        assert d.history[0]["mid"] == MID.SOLAR_ARRAY_APP

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_history_record_fields(self, mock_socket_cls):
        """History records contain all expected fields."""
        mock_sock = MagicMock()
        mock_sock.sendto.return_value = 12
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        payload = struct.pack("!f", 100.0)
        d.send(MID.RADIATION_APP, FC.SEND_DATA, payload=payload)

        rec = d.history[0]
        assert rec["mid"] == MID.RADIATION_APP
        assert rec["mid_name"] == "RADIATION_APP"
        assert rec["func_code"] == FC.SEND_DATA
        assert rec["fc_name"] == "SEND_DATA"
        assert rec["seq"] == 0
        assert rec["bytes_sent"] == 12
        assert rec["payload_hex"] == payload.hex()

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_history_unknown_mid(self, mock_socket_cls):
        """Unknown MIDs fall back to hex string in history."""
        mock_sock = MagicMock()
        mock_sock.sendto.return_value = 8
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        d.send(0x1FFF, 99)

        assert d.history[0]["mid_name"] == "0x1FFF"
        assert d.history[0]["fc_name"] == "99"

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_socket_closed_on_success(self, mock_socket_cls):
        """Socket is closed after a successful send."""
        mock_sock = MagicMock()
        mock_sock.sendto.return_value = 8
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        d.send(MID.RADIATION_APP, FC.NOOP)

        mock_sock.close.assert_called_once()

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_socket_closed_on_error(self, mock_socket_cls):
        """Socket is closed even when sendto raises an exception."""
        mock_sock = MagicMock()
        mock_sock.sendto.side_effect = OSError("network down")
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        with pytest.raises(OSError):
            d.send(MID.RADIATION_APP, FC.NOOP)

        mock_sock.close.assert_called_once()


class TestSequenceCounting:
    """Test per-MID sequence counter behavior."""

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_sequence_increments_per_mid(self, mock_socket_cls):
        """Sequence counter increments independently per MID."""
        mock_sock = MagicMock()
        sent_data = []

        def capture(data, addr):
            sent_data.append(data)
            return len(data)

        mock_sock.sendto.side_effect = capture
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        d.send(MID.RADIATION_APP, FC.NOOP)
        d.send(MID.RADIATION_APP, FC.NOOP)
        d.send(MID.THERMAL_APP, FC.NOOP)

        # RAD_APP seq: 0, 1
        p0 = unpack_cmd_packet(sent_data[0])
        p1 = unpack_cmd_packet(sent_data[1])
        p2 = unpack_cmd_packet(sent_data[2])

        assert p0["seq_count"] == 0
        assert p1["seq_count"] == 1
        assert p2["seq_count"] == 0  # Different MID, starts at 0

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_sequence_wraps_at_14_bits(self, mock_socket_cls):
        """Sequence counter wraps at 0x3FFF (16383)."""
        mock_sock = MagicMock()
        mock_sock.sendto.return_value = 8
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        d._seq_counts[MID.RADIATION_APP] = 0x3FFF

        d.send(MID.RADIATION_APP, FC.NOOP)
        assert d.history[0]["seq"] == 0x3FFF
        # Next send should wrap to 0
        d.send(MID.RADIATION_APP, FC.NOOP)
        assert d.history[1]["seq"] == 0


class TestSendWithFloat:
    """Test the send_with_float convenience method."""

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_send_with_float_packs_correctly(self, mock_socket_cls):
        """send_with_float packs the value as Big-Endian IEEE 754."""
        mock_sock = MagicMock()
        sent_data = []

        def capture(data, addr):
            sent_data.append(data)
            return len(data)

        mock_sock.sendto.side_effect = capture
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        d.send_with_float(MID.RADIATION_APP, FC.SEND_DATA, 123.45)

        packet = sent_data[0]
        parsed = unpack_cmd_packet(packet)
        value = struct.unpack("!f", parsed["payload"])[0]
        assert abs(value - 123.45) < 0.01

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_send_with_float_negative_value(self, mock_socket_cls):
        """send_with_float handles negative float values."""
        mock_sock = MagicMock()
        sent_data = []

        def capture(data, addr):
            sent_data.append(data)
            return len(data)

        mock_sock.sendto.side_effect = capture
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        d.send_with_float(MID.THERMAL_APP, FC.SEND_DATA, -25.5)

        packet = sent_data[0]
        parsed = unpack_cmd_packet(packet)
        value = struct.unpack("!f", parsed["payload"])[0]
        assert abs(value - (-25.5)) < 0.01

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_send_with_float_zero(self, mock_socket_cls):
        """send_with_float handles zero correctly."""
        mock_sock = MagicMock()
        sent_data = []

        def capture(data, addr):
            sent_data.append(data)
            return len(data)

        mock_sock.sendto.side_effect = capture
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        d.send_with_float(MID.RADIATION_APP, FC.SEND_DATA, 0.0)

        packet = sent_data[0]
        parsed = unpack_cmd_packet(packet)
        value = struct.unpack("!f", parsed["payload"])[0]
        assert value == 0.0


class TestEnableTelemetryOutput:
    """Test the enable_telemetry_output convenience method."""

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_enable_sends_correct_mid_and_fc(self, mock_socket_cls):
        """enable_telemetry_output sends MID 0x1880 FC 6."""
        mock_sock = MagicMock()
        sent_data = []

        def capture(data, addr):
            sent_data.append(data)
            return len(data)

        mock_sock.sendto.side_effect = capture
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        d.enable_telemetry_output("192.168.1.100")

        packet = sent_data[0]
        parsed = unpack_cmd_packet(packet)
        assert parsed["apid"] == MID.TO_LAB_CMD & 0x7FF
        assert parsed["func_code"] == FC.TO_LAB_OUTPUT_ENABLE

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_enable_payload_is_16_byte_ip_string(self, mock_socket_cls):
        """Payload is a 16-byte null-padded IP string."""
        mock_sock = MagicMock()
        sent_data = []

        def capture(data, addr):
            sent_data.append(data)
            return len(data)

        mock_sock.sendto.side_effect = capture
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        d.enable_telemetry_output("172.18.0.4")

        packet = sent_data[0]
        parsed = unpack_cmd_packet(packet)
        payload = parsed["payload"]
        assert len(payload) == 16
        # Extract the IP string (null-terminated)
        ip_str = payload.split(b"\x00")[0].decode("ascii")
        assert ip_str == "172.18.0.4"

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_enable_total_packet_size(self, mock_socket_cls):
        """Total packet: 6 (pri) + 2 (cmd sec) + 16 (IP) = 24 bytes."""
        mock_sock = MagicMock()
        sent_data = []

        def capture(data, addr):
            sent_data.append(data)
            return len(data)

        mock_sock.sendto.side_effect = capture
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        d.enable_telemetry_output("10.0.0.1")

        assert len(sent_data[0]) == 24

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_enable_records_history(self, mock_socket_cls):
        """enable_telemetry_output records in command history."""
        mock_sock = MagicMock()
        mock_sock.sendto.return_value = 24
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        d.enable_telemetry_output("192.168.1.1")

        assert len(d.history) == 1
        rec = d.history[0]
        assert rec["mid"] == MID.TO_LAB_CMD
        assert rec["func_code"] == FC.TO_LAB_OUTPUT_ENABLE
        assert rec["mid_name"] == "TO_LAB_CMD"
        assert rec["fc_name"] == "TO_LAB_OUTPUT_ENABLE"

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_enable_long_ip_truncated(self, mock_socket_cls):
        """IP strings longer than 15 chars are truncated to fit."""
        mock_sock = MagicMock()
        sent_data = []

        def capture(data, addr):
            sent_data.append(data)
            return len(data)

        mock_sock.sendto.side_effect = capture
        mock_socket_cls.return_value = mock_sock

        d = CommandDispatcher(host="localhost", port=1234)
        d.enable_telemetry_output("111.222.333.444")

        packet = sent_data[0]
        parsed = unpack_cmd_packet(packet)
        payload = parsed["payload"]
        assert len(payload) == 16
        # Must have null terminator
        assert payload[15] == 0
