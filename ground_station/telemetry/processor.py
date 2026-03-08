"""Telemetry Processor — Aggregates and tracks telemetry data points.

Processes raw telemetry entries from the TelemetryReceiver and
maintains time-series buffers for charting, health status tracking,
and event log aggregation.
"""

import struct
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from ground_station.telemetry_receiver import (
    RawTelemetryEntry,
    TLM_MID_RAD,
    TLM_MID_THERM,
    CFE_EVS_LONG_EVENT_MSG_MID,
)

HEALTH_LABELS = {0: "NOMINAL", 1: "WARNING", 2: "CRITICAL"}


@dataclass
class TelemetryPoint:
    """A single processed telemetry data point for charting.

    Attributes:
        timestamp: Unix epoch timestamp.
        value: Sensor reading (float).
        health: Health status code (0=NOMINAL, 1=WARNING, 2=CRITICAL).
        health_label: Human-readable health string.
    """

    timestamp: float
    value: float
    health: int = 0
    health_label: str = "NOMINAL"


class TelemetryProcessor:
    """Aggregates telemetry into time-series and event logs.

    Maintains separate ring buffers for radiation, thermal, and
    event data.  Designed to be registered as a callback with
    TelemetryReceiver.

    Attributes:
        radiation_history: Deque of radiation TelemetryPoint entries.
        thermal_history: Deque of thermal TelemetryPoint entries.
        event_log: Deque of event message strings.
        solar_array_status: Current solar array status string.
    """

    def __init__(self, max_points: int = 200) -> None:
        """Initialize the processor.

        Args:
            max_points: Maximum data points to retain per sensor.
        """
        self.radiation_history: deque[TelemetryPoint] = deque(maxlen=max_points)
        self.thermal_history: deque[TelemetryPoint] = deque(maxlen=max_points)
        self.event_log: deque[str] = deque(maxlen=500)
        self.raw_log: deque[str] = deque(maxlen=200)
        self.solar_array_status: str = "Unknown"
        self._lock = threading.Lock()
        self.last_radiation: Optional[TelemetryPoint] = None
        self.last_thermal: Optional[TelemetryPoint] = None

    def process(self, entry: RawTelemetryEntry) -> None:
        """Process a raw telemetry entry from the receiver.

        This method is designed to be used as a TelemetryReceiver
        callback via receiver.register_callback(processor.process).

        Args:
            entry: Raw telemetry entry to process.
        """
        parsed = entry.parsed
        ptype = parsed.get("type", "unknown")

        with self._lock:
            # Always log the raw hex
            ts_str = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
            self.raw_log.append(
                f"[{ts_str}] MID={parsed.get('mid_hex', '????')} "
                f"Size={entry.size}B | {entry.raw_hex[:80]}"
            )

            if ptype == "radiation":
                point = TelemetryPoint(
                    timestamp=entry.timestamp,
                    value=parsed["value"],
                    health=parsed.get("health", 0),
                    health_label=parsed.get("health_label", "NOMINAL"),
                )
                self.radiation_history.append(point)
                self.last_radiation = point

                if point.health == 2:
                    self.solar_array_status = "Closed (FDIR Auto)"
                    self.event_log.append(
                        f"[{ts_str}] FDIR: Radiation CRITICAL "
                        f"({point.value:.1f} mSv/h) — Solar Array Auto-Closed"
                    )

            elif ptype == "thermal":
                point = TelemetryPoint(
                    timestamp=entry.timestamp,
                    value=parsed["value"],
                    health=parsed.get("health", 0),
                    health_label=parsed.get("health_label", "NOMINAL"),
                )
                self.thermal_history.append(point)
                self.last_thermal = point

                if point.health == 2:
                    self.event_log.append(
                        f"[{ts_str}] FDIR: Temperature CRITICAL "
                        f"({point.value:.1f} C)"
                    )

            elif ptype == "evs":
                event_text = parsed.get("event_text", "")
                self.event_log.append(f"[{ts_str}] EVS: {event_text}")

                # Detect solar array status changes from EVS messages
                if "SOLAR" in event_text.upper() and "CLOSE" in event_text.upper():
                    self.solar_array_status = "Closed"
                elif "SOLAR" in event_text.upper() and "OPEN" in event_text.upper():
                    self.solar_array_status = "Open"

    def get_radiation_series(self) -> list[TelemetryPoint]:
        """Return a copy of the radiation time-series.

        Returns:
            List of TelemetryPoint for radiation data.
        """
        with self._lock:
            return list(self.radiation_history)

    def get_thermal_series(self) -> list[TelemetryPoint]:
        """Return a copy of the thermal time-series.

        Returns:
            List of TelemetryPoint for thermal data.
        """
        with self._lock:
            return list(self.thermal_history)

    def get_events(self, count: int = 50) -> list[str]:
        """Return recent event log entries.

        Args:
            count: Maximum number of entries to return.

        Returns:
            List of event message strings, newest last.
        """
        with self._lock:
            items = list(self.event_log)
        return items[-count:]

    def get_raw_log(self, count: int = 50) -> list[str]:
        """Return recent raw telemetry log entries.

        Args:
            count: Maximum number of entries to return.

        Returns:
            List of raw hex log strings, newest last.
        """
        with self._lock:
            items = list(self.raw_log)
        return items[-count:]

    def update_solar_array_status(self, status: str) -> None:
        """Manually update the solar array status (Operator Override).

        Args:
            status: New status string (e.g., 'Open', 'Closed').
        """
        with self._lock:
            self.solar_array_status = status
            ts_str = time.strftime("%H:%M:%S", time.localtime(time.time()))
            self.event_log.append(
                f"[{ts_str}] OPERATOR: Solar Array manually set to '{status}'"
            )
