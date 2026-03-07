"""
Unit Tests for Sensor Implementations
======================================

Verifies:
  1. Sensor class attributes (name, MID, FC, value range)
  2. BaseSensor value clamping
  3. CCSDS payload packing
  4. Dynamic sensor discovery

Run:  pytest sensor_manager/tests/test_sensors.py -v
"""

import struct
from unittest.mock import patch

import pytest

from sensor_manager.core.base_sensor import BaseSensor
from sensor_manager.core.mission_registry import MID, FC
from sensor_manager.sensors.radiation_sensor import RadiationSensor
from sensor_manager.sensors.thermal_sensor import ThermalSensor


class TestRadiationSensor:
    """Verify RadiationSensor configuration and behavior."""

    def test_class_attributes(self):
        sensor = RadiationSensor()
        assert sensor.name == "Radiation Sensor"
        assert sensor.mid == MID.RADIATION_APP
        assert sensor.func_code == FC.SEND_DATA
        assert sensor.unit == "rad"
        assert sensor.min_value == 0.0
        assert sensor.max_value == 1000.0

    def test_default_value(self):
        sensor = RadiationSensor()
        assert sensor.value == 50.0

    def test_update_value(self):
        sensor = RadiationSensor()
        sensor.value = 500.0
        assert sensor.value == 500.0

    def test_value_clamped_to_max(self):
        sensor = RadiationSensor()
        sensor.value = 9999.0
        assert sensor.value == 1000.0

    def test_value_clamped_to_min(self):
        sensor = RadiationSensor()
        sensor.value = -10.0
        assert sensor.value == 0.0


class TestThermalSensor:
    """Verify ThermalSensor configuration and behavior."""

    def test_class_attributes(self):
        sensor = ThermalSensor()
        assert sensor.name == "Thermal Sensor"
        assert sensor.mid == MID.THERMAL_APP
        assert sensor.func_code == FC.SEND_DATA
        assert sensor.unit == "\u00b0C"
        assert sensor.min_value == -40.0
        assert sensor.max_value == 85.0

    def test_default_value(self):
        sensor = ThermalSensor()
        assert sensor.value == 20.0

    def test_negative_value_allowed(self):
        sensor = ThermalSensor()
        sensor.value = -30.0
        assert sensor.value == -30.0


class TestBaseSensorPayload:
    """Verify payload packing produces correct CCSDS-compatible bytes."""

    def test_payload_is_4byte_float(self):
        sensor = RadiationSensor()
        sensor.value = 123.456
        payload = sensor._pack_payload()
        assert len(payload) == 4
        (val,) = struct.unpack("!f", payload)
        assert abs(val - 123.456) < 0.001

    @patch("sensor_manager.core.base_sensor.socket.socket")
    def test_send_dispatches_udp(self, mock_socket_cls):
        mock_sock = mock_socket_cls.return_value
        mock_sock.sendto.return_value = 12

        sensor = RadiationSensor()
        sensor._host = "testhost"
        sensor._port = 1234
        result = sensor.send()

        assert result == 12
        mock_sock.sendto.assert_called_once()
        args = mock_sock.sendto.call_args
        assert args[0][1] == ("testhost", 1234)
        # Packet should be: 6 pri + 2 cmd sec + 4 payload = 12 bytes
        assert len(args[0][0]) == 12

    @patch("sensor_manager.core.base_sensor.socket.socket")
    def test_update_and_send(self, mock_socket_cls):
        mock_sock = mock_socket_cls.return_value
        mock_sock.sendto.return_value = 12

        sensor = ThermalSensor()
        sensor._host = "testhost"
        sensor._port = 1234
        result = sensor.update_and_send(42.0)

        assert sensor.value == 42.0
        assert result == 12

    @patch("sensor_manager.core.base_sensor.socket.socket")
    def test_seq_count_increments(self, mock_socket_cls):
        mock_sock = mock_socket_cls.return_value
        mock_sock.sendto.return_value = 12

        sensor = RadiationSensor()
        sensor._host = "testhost"
        sensor._port = 1234

        assert sensor._seq_count == 0
        sensor.send()
        assert sensor._seq_count == 1
        sensor.send()
        assert sensor._seq_count == 2
