"""Telemetry Receiver — Listens for CCSDS telemetry from cFS TO_LAB.

Runs a background UDP listener on port 2234 (TO_LAB default) and
dispatches received packets to registered callbacks.  Thread-safe
for use with Streamlit's rerun-based architecture.

Example:
    receiver = TelemetryReceiver(port=2234)
    receiver.register_callback(my_handler)
    receiver.start()
    # ... later ...
    receiver.stop()
"""

import logging
import os
import socket
import struct
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

from sensor_manager.core.ccsds_utils import (
    CCSDS_PRI_HDR_SIZE,
    CCSDS_TLM_SEC_HDR_SIZE,
    unpack_primary_header,
    unpack_tlm_packet,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Known telemetry MIDs — must match firmware C headers and mission_registry.py
# RAD_APP TLM:   topic_id=0x82 → MID = 0x0800 | 0x82 = 0x0882
# THERM_APP TLM: topic_id=0x83 → MID = 0x0800 | 0x83 = 0x0883
# CFE_EVS long:  topic_id=0x08 → MID = 0x0800 | 0x08 = 0x0808
TLM_MID_RAD = 0x0882
TLM_MID_THERM = 0x0883

# cFE EVS long event message MID (matches TO_LAB subscription table)
CFE_EVS_LONG_EVENT_MSG_MID = 0x0808


@dataclass
class RawTelemetryEntry:
    """A single raw telemetry packet with metadata."""

    timestamp: float
    mid: int
    raw_hex: str
    parsed: dict
    size: int


class TelemetryReceiver:
    """UDP telemetry listener for cFS TO_LAB output.

    Listens on a configurable UDP port and collects incoming CCSDS
    telemetry packets.  Packets are stored in a thread-safe buffer
    and optionally forwarded to registered callbacks.

    Attributes:
        port: UDP port to listen on.
        buffer_size: Maximum number of packets to retain.
        running: Whether the listener thread is active.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: Optional[int] = None,
        buffer_size: int = 500,
    ) -> None:
        """Initialize the telemetry receiver.

        Args:
            host: Bind address for the UDP socket.
            port: UDP port to listen on (default: GS_TLM_PORT env or 2234).
            buffer_size: Max packets to retain in the ring buffer.
        """
        self.host = host
        self.port = port or int(os.environ.get("GS_TLM_PORT", "2234"))
        self.buffer_size = buffer_size

        self._buffer: deque[RawTelemetryEntry] = deque(maxlen=buffer_size)
        self._callbacks: list[Callable[[RawTelemetryEntry], None]] = []
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._sock: Optional[socket.socket] = None
        self.running = False
        self.packets_received = 0

    def register_callback(
        self, callback: Callable[[RawTelemetryEntry], None]
    ) -> None:
        """Register a callback invoked for each received packet.

        Args:
            callback: Function accepting a RawTelemetryEntry.
        """
        self._callbacks.append(callback)

    def get_recent(self, count: int = 50) -> list[RawTelemetryEntry]:
        """Return the most recent telemetry entries.

        Args:
            count: Maximum number of entries to return.

        Returns:
            List of recent RawTelemetryEntry objects, newest last.
        """
        with self._lock:
            items = list(self._buffer)
        return items[-count:]

    def start(self) -> None:
        """Start the background listener thread."""
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._listen_loop, daemon=True, name="tlm-receiver"
        )
        self._thread.start()
        self.running = True
        logger.info("TelemetryReceiver started on %s:%d", self.host, self.port)

    def stop(self) -> None:
        """Stop the background listener thread."""
        self._stop_event.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self.running = False
        logger.info("TelemetryReceiver stopped")

    def _listen_loop(self) -> None:
        """Main receive loop running in the background thread."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.settimeout(1.0)
        self._sock.bind((self.host, self.port))
        logger.info(
            "TLM listener bound to %s:%d — waiting for packets",
            self.host, self.port,
        )

        while not self._stop_event.is_set():
            try:
                data, addr = self._sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                if self._stop_event.is_set():
                    break
                logger.exception("Socket error in listen loop")
                raise

            if len(data) < CCSDS_PRI_HDR_SIZE:
                logger.warning(
                    "Dropped short packet (%d bytes < %d min) from %s: %s",
                    len(data), CCSDS_PRI_HDR_SIZE, addr, data.hex(),
                )
                continue

            try:
                # Extract the raw StreamId word directly from the first 2 bytes.
                # In cFS the StreamId IS the MID — it encodes version, type,
                # sec-hdr-flag, and APID in a single 16-bit Big-Endian word.
                # This avoids any reconstruction errors from bit-shifting.
                stream_id = struct.unpack("!H", data[:2])[0]
                mid = stream_id

                logger.debug(
                    "Received %d bytes from %s — StreamId=0x%04X",
                    len(data), addr, mid,
                )

                parsed = self._parse_packet(mid, data)

                entry = RawTelemetryEntry(
                    timestamp=time.time(),
                    mid=mid,
                    raw_hex=data.hex(),
                    parsed=parsed,
                    size=len(data),
                )

                with self._lock:
                    self._buffer.append(entry)
                    self.packets_received += 1

                for cb in self._callbacks:
                    try:
                        cb(entry)
                    except Exception:
                        logger.exception("Callback error for MID 0x%04X", mid)

            except Exception:
                logger.exception(
                    "Failed to parse %d-byte packet from %s: %s",
                    len(data), addr, data.hex()[:80],
                )

        try:
            self._sock.close()
        except OSError:
            pass

    def _parse_packet(self, mid: int, data: bytes) -> dict:
        """Parse a telemetry packet based on its MID.

        Args:
            mid: Reconstructed Message ID.
            data: Raw packet bytes.

        Returns:
            Dictionary with parsed fields.
        """
        result: dict = {"mid": mid, "mid_hex": f"0x{mid:04X}"}

        try:
            tlm = unpack_tlm_packet(data)
            result["seconds"] = tlm["seconds"]
            result["subseconds"] = tlm["subseconds"]
            payload = tlm["payload"]
        except ValueError:
            result["raw"] = data.hex()
            return result

        if mid == TLM_MID_RAD and len(payload) >= 4:
            value = struct.unpack("<f", payload[:4])[0]
            health = payload[4] if len(payload) > 4 else 0
            health_labels = {0: "NOMINAL", 1: "WARNING", 2: "CRITICAL"}
            result["type"] = "radiation"
            result["value"] = value
            result["health"] = health
            result["health_label"] = health_labels.get(health, "UNKNOWN")

        elif mid == TLM_MID_THERM and len(payload) >= 4:
            value = struct.unpack("<f", payload[:4])[0]
            health = payload[4] if len(payload) > 4 else 0
            health_labels = {0: "NOMINAL", 1: "WARNING", 2: "CRITICAL"}
            result["type"] = "thermal"
            result["value"] = value
            result["health"] = health
            result["health_label"] = health_labels.get(health, "UNKNOWN")

        elif mid == CFE_EVS_LONG_EVENT_MSG_MID:
            result["type"] = "evs"
            result["event_text"] = self._parse_evs(payload)

        else:
            result["type"] = "unknown"
            result["payload_hex"] = payload.hex()

        return result

    @staticmethod
    def _parse_evs(payload: bytes) -> str:
        """Extract the event message string from a cFE EVS long event packet.

        The cFE EVS long event message has a fixed-size structure.
        The text message starts at byte offset 12 within the EVS
        application data (after AppName[20] + EventID(2) + EventType(2)
        + SpacecraftID(4) + ProcessorID(4) = 32 bytes into the payload,
        but the layout depends on cFS version).  We do a best-effort
        extraction of printable ASCII from the payload.

        Args:
            payload: EVS payload bytes after the telemetry secondary header.

        Returns:
            Extracted event message string.
        """
        # Try to find printable ASCII region in the payload
        text_bytes = []
        for b in payload:
            if 32 <= b < 127:
                text_bytes.append(chr(b))
            elif text_bytes and b == 0:
                break
            elif text_bytes:
                text_bytes.append(" ")
        return "".join(text_bytes).strip() if text_bytes else payload.hex()
