"""Command Dispatcher — Sends CCSDS command packets to cFS via UDP.

The CommandDispatcher builds well-formed CCSDS command packets and
dispatches them to the cFS CI_LAB endpoint over UDP.  It maintains
a per-MID sequence counter for packet ordering.

Example:
    dispatcher = CommandDispatcher(host="cfs-flight", port=1234)
    dispatcher.send(mid=0x1890, func_code=5)  # Solar Array Open
"""

import os
import socket
import struct
import logging
from typing import Optional

from sensor_manager.core.ccsds_utils import pack_cmd_packet
from sensor_manager.core.mission_registry import MID, FC, MID_NAME, FC_NAME

logger = logging.getLogger(__name__)


class CommandDispatcher:
    """Sends CCSDS command packets to cFS CI_LAB over UDP.

    Attributes:
        host: Target hostname or IP for CI_LAB.
        port: Target UDP port for CI_LAB.
        history: List of sent command records for logging/display.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        """Initialize the command dispatcher.

        Args:
            host: cFS CI_LAB hostname (default: CFS_HOST env or 'cfs-flight').
            port: cFS CI_LAB UDP port (default: CFS_CMD_PORT env or 1234).
        """
        self.host = host or os.environ.get("CFS_HOST", "cfs-flight")
        self.port = port or int(os.environ.get("CFS_CMD_PORT", "1234"))
        self._seq_counts: dict[int, int] = {}
        self.history: list[dict] = []

    def _next_seq(self, mid: int) -> int:
        """Return and increment the 14-bit sequence counter for a MID."""
        seq = self._seq_counts.get(mid, 0)
        self._seq_counts[mid] = (seq + 1) & 0x3FFF
        return seq

    def send(
        self,
        mid: int,
        func_code: int,
        payload: bytes = b"",
    ) -> int:
        """Build and send a CCSDS command packet.

        Args:
            mid: CCSDS Message ID (StreamId).
            func_code: Command function code.
            payload: Optional command payload bytes.

        Returns:
            Number of bytes sent over UDP.
        """
        seq = self._next_seq(mid)
        packet = pack_cmd_packet(mid, func_code, payload=payload, seq_count=seq)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            bytes_sent = sock.sendto(packet, (self.host, self.port))
        finally:
            sock.close()

        mid_name = MID_NAME.get(mid, f"0x{mid:04X}")
        fc_name = FC_NAME.get(func_code, str(func_code))
        record = {
            "mid": mid,
            "mid_name": mid_name,
            "func_code": func_code,
            "fc_name": fc_name,
            "seq": seq,
            "bytes_sent": bytes_sent,
            "payload_hex": payload.hex() if payload else "",
        }
        self.history.append(record)
        logger.info(
            "CMD sent: MID=%s FC=%s seq=%d bytes=%d",
            mid_name, fc_name, seq, bytes_sent,
        )
        return bytes_sent

    def send_with_float(
        self,
        mid: int,
        func_code: int,
        value: float,
    ) -> int:
        """Send a command with a single Big-Endian float payload.

        Args:
            mid: CCSDS Message ID.
            func_code: Command function code.
            value: Float value to pack as payload.

        Returns:
            Number of bytes sent.
        """
        payload = struct.pack("!f", value)
        return self.send(mid, func_code, payload=payload)

    def enable_telemetry_output(self, dest_ip: str) -> int:
        """Send the TO_LAB OUTPUT_ENABLE command to start telemetry forwarding.

        This is required before cFS will send any telemetry packets.
        TO_LAB starts with output disabled and waits for this command
        with the destination IP address.

        The payload is a 16-byte null-padded ASCII string containing
        the destination IP address, matching the C struct:
            typedef struct { char dest_IP[16]; } TO_LAB_EnableOutput_Payload_t;

        Args:
            dest_ip: Destination IP address for telemetry (e.g., 'ground-station').

        Returns:
            Number of bytes sent.
        """
        # Pad IP string to exactly 16 bytes (matching C struct dest_IP[16])
        ip_bytes = dest_ip.encode("ascii")[:15]  # Leave room for null terminator
        payload = ip_bytes.ljust(16, b"\x00")
        logger.info("Enabling TO_LAB telemetry output to %s", dest_ip)
        return self.send(MID.TO_LAB_CMD, FC.TO_LAB_OUTPUT_ENABLE, payload=payload)
