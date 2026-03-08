"""Tests for the SolarArrayCommands class.

Covers command definitions, dispatch to CommandDispatcher,
and correct MID/FC values.
"""

import struct
from unittest.mock import MagicMock, patch, call

import pytest

from ground_station.command_dispatcher import CommandDispatcher
from ground_station.commands.solar_array import SolarArrayCommands
from sensor_manager.core.mission_registry import MID, FC


class TestSolarArrayCommandsConstants:
    """Test that SolarArrayCommands exposes correct constants."""

    def test_mid_value(self):
        """MID matches SOLAR_ARRAY_APP (0x1890)."""
        assert SolarArrayCommands.MID == 0x1890

    def test_fc_open_value(self):
        """FC_OPEN matches SOLAR_ARRAY_OPEN (5)."""
        assert SolarArrayCommands.FC_OPEN == 5

    def test_fc_close_value(self):
        """FC_CLOSE matches SOLAR_ARRAY_CLOSE (6)."""
        assert SolarArrayCommands.FC_CLOSE == 6


class TestSolarArrayOpen:
    """Test the open_array() method."""

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_open_sends_correct_mid_and_fc(self, mock_socket_cls):
        """open_array sends MID 0x1890 with FC 5."""
        mock_sock = MagicMock()
        mock_sock.sendto.return_value = 8
        mock_socket_cls.return_value = mock_sock

        dispatcher = CommandDispatcher(host="localhost", port=1234)
        cmds = SolarArrayCommands(dispatcher)
        result = cmds.open_array()

        assert result == 8
        assert len(dispatcher.history) == 1
        assert dispatcher.history[0]["mid"] == MID.SOLAR_ARRAY_APP
        assert dispatcher.history[0]["func_code"] == FC.SOLAR_ARRAY_OPEN

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_open_returns_bytes_sent(self, mock_socket_cls):
        """open_array returns the byte count from dispatcher."""
        mock_sock = MagicMock()
        mock_sock.sendto.return_value = 8
        mock_socket_cls.return_value = mock_sock

        dispatcher = CommandDispatcher(host="localhost", port=1234)
        cmds = SolarArrayCommands(dispatcher)
        assert cmds.open_array() == 8


class TestSolarArrayClose:
    """Test the close_array() method."""

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_close_sends_correct_mid_and_fc(self, mock_socket_cls):
        """close_array sends MID 0x1890 with FC 6."""
        mock_sock = MagicMock()
        mock_sock.sendto.return_value = 8
        mock_socket_cls.return_value = mock_sock

        dispatcher = CommandDispatcher(host="localhost", port=1234)
        cmds = SolarArrayCommands(dispatcher)
        result = cmds.close_array()

        assert result == 8
        assert dispatcher.history[0]["mid"] == MID.SOLAR_ARRAY_APP
        assert dispatcher.history[0]["func_code"] == FC.SOLAR_ARRAY_CLOSE

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_close_returns_bytes_sent(self, mock_socket_cls):
        """close_array returns the byte count from dispatcher."""
        mock_sock = MagicMock()
        mock_sock.sendto.return_value = 8
        mock_socket_cls.return_value = mock_sock

        dispatcher = CommandDispatcher(host="localhost", port=1234)
        cmds = SolarArrayCommands(dispatcher)
        assert cmds.close_array() == 8


class TestSolarArraySequence:
    """Test sequence counter behavior through SolarArrayCommands."""

    @patch("ground_station.command_dispatcher.socket.socket")
    def test_sequence_increments(self, mock_socket_cls):
        """Multiple commands increment the sequence counter."""
        mock_sock = MagicMock()
        mock_sock.sendto.return_value = 8
        mock_socket_cls.return_value = mock_sock

        dispatcher = CommandDispatcher(host="localhost", port=1234)
        cmds = SolarArrayCommands(dispatcher)
        cmds.open_array()
        cmds.close_array()
        cmds.open_array()

        seqs = [h["seq"] for h in dispatcher.history]
        assert seqs == [0, 1, 2]
