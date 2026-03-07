"""
Abstract Base Sensor
====================

Defines the interface and shared logic for all sensor simulators.
Each sensor wraps its value into a CCSDS command packet and dispatches
it via UDP to the cFS firmware on CI_LAB (port 1234).
"""

import os
import socket
import struct
from abc import ABC, abstractmethod

from .ccsds_utils import pack_cmd_packet


class BaseSensor(ABC):
    """Abstract base class for environment sensors.

    Subclasses must define:
        name        — Human-readable sensor name.
        mid         — CCSDS Message ID (StreamId) for this sensor's app.
        func_code   — Function code for sending sensor data.
        unit        — Unit string for display (e.g., "rad", "°C").
        min_value   — Minimum value for UI slider.
        max_value   — Maximum value for UI slider.
        default     — Default/initial sensor value.
    """

    name: str
    mid: int
    func_code: int
    unit: str
    min_value: float
    max_value: float
    default: float

    def __init__(self):
        self._value: float = self.default
        self._seq_count: int = 0
        self._host: str = os.environ.get("CFS_HOST", "cfs-flight")
        self._port: int = int(os.environ.get("CFS_CMD_PORT", "1234"))

    @property
    def value(self) -> float:
        """Current sensor reading."""
        return self._value

    @value.setter
    def value(self, new_value: float) -> None:
        self._value = max(self.min_value, min(self.max_value, new_value))

    def _pack_payload(self) -> bytes:
        """Pack current value as a 4-byte big-endian float payload."""
        return struct.pack("!f", self._value)

    def send(self) -> int:
        """Build a CCSDS command packet and send it via UDP to cFS.

        Returns:
            Number of bytes sent.
        """
        payload = self._pack_payload()
        packet = pack_cmd_packet(
            self.mid, self.func_code, payload=payload, seq_count=self._seq_count
        )
        self._seq_count = (self._seq_count + 1) & 0x3FFF

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            bytes_sent = sock.sendto(packet, (self._host, self._port))
        finally:
            sock.close()
        return bytes_sent

    def update_and_send(self, new_value: float) -> int:
        """Update the sensor value and immediately dispatch to cFS.

        Args:
            new_value: New sensor reading.

        Returns:
            Number of bytes sent.
        """
        self.value = new_value
        return self.send()
