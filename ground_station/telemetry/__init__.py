"""Telemetry processing for the ground station.

Parses incoming CCSDS telemetry packets from cFS TO_LAB and
extracts application-specific data (radiation, thermal, EVS events).
"""

from .processor import TelemetryProcessor, TelemetryPoint

__all__ = ["TelemetryProcessor", "TelemetryPoint"]
