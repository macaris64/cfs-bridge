"""Tests for the TelemetryProcessor class.

Covers data aggregation, time-series tracking, event logging,
solar array status management, and thread safety.
"""

import struct
import time
from unittest.mock import MagicMock

import pytest

from ground_station.telemetry_receiver import RawTelemetryEntry, TLM_MID_RAD, TLM_MID_THERM
from ground_station.telemetry.processor import TelemetryProcessor, TelemetryPoint


def _make_entry(mid, ptype, value=50.0, health=0, health_label="NOMINAL", raw_hex="aabb"):
    """Helper to create a RawTelemetryEntry with parsed data."""
    parsed = {
        "mid": mid,
        "mid_hex": f"0x{mid:04X}",
        "type": ptype,
    }
    if ptype in ("radiation", "thermal"):
        parsed["value"] = value
        parsed["health"] = health
        parsed["health_label"] = health_label
    elif ptype == "evs":
        parsed["event_text"] = f"EVS message at value {value}"
    return RawTelemetryEntry(
        timestamp=time.time(),
        mid=mid,
        raw_hex=raw_hex,
        parsed=parsed,
        size=20,
    )


class TestTelemetryProcessorInit:
    """Test processor initialization."""

    def test_default_state(self):
        """Processor starts with empty histories."""
        p = TelemetryProcessor()
        assert len(p.radiation_history) == 0
        assert len(p.thermal_history) == 0
        assert len(p.event_log) == 0
        assert p.solar_array_status == "Unknown"
        assert p.last_radiation is None
        assert p.last_thermal is None

    def test_custom_max_points(self):
        """Max points configuration is respected."""
        p = TelemetryProcessor(max_points=10)
        assert p.radiation_history.maxlen == 10


class TestRadiationProcessing:
    """Test radiation telemetry processing."""

    def test_nominal_radiation(self):
        """Nominal radiation is added to history."""
        p = TelemetryProcessor()
        entry = _make_entry(TLM_MID_RAD, "radiation", value=50.0, health=0)
        p.process(entry)

        series = p.get_radiation_series()
        assert len(series) == 1
        assert abs(series[0].value - 50.0) < 0.01
        assert series[0].health == 0
        assert series[0].health_label == "NOMINAL"

    def test_warning_radiation(self):
        """Warning radiation is recorded with correct health."""
        p = TelemetryProcessor()
        entry = _make_entry(TLM_MID_RAD, "radiation", value=120.0, health=1, health_label="WARNING")
        p.process(entry)

        assert p.last_radiation.health == 1

    def test_critical_radiation_triggers_fdir_status(self):
        """Critical radiation updates solar array status to Closed."""
        p = TelemetryProcessor()
        entry = _make_entry(TLM_MID_RAD, "radiation", value=200.0, health=2, health_label="CRITICAL")
        p.process(entry)

        assert p.solar_array_status == "Closed (FDIR Auto)"
        events = p.get_events()
        assert any("FDIR" in e and "Radiation CRITICAL" in e for e in events)

    def test_multiple_radiation_points(self):
        """Multiple radiation points build up the time series."""
        p = TelemetryProcessor()
        for v in [10.0, 20.0, 30.0, 40.0, 50.0]:
            entry = _make_entry(TLM_MID_RAD, "radiation", value=v)
            p.process(entry)

        series = p.get_radiation_series()
        assert len(series) == 5
        values = [pt.value for pt in series]
        assert abs(values[-1] - 50.0) < 0.01

    def test_last_radiation_updated(self):
        """last_radiation always points to the most recent point."""
        p = TelemetryProcessor()
        entry = _make_entry(TLM_MID_RAD, "radiation", value=99.0)
        p.process(entry)
        assert abs(p.last_radiation.value - 99.0) < 0.01


class TestThermalProcessing:
    """Test thermal telemetry processing."""

    def test_nominal_thermal(self):
        """Nominal thermal is added to history."""
        p = TelemetryProcessor()
        entry = _make_entry(TLM_MID_THERM, "thermal", value=25.0, health=0)
        p.process(entry)

        series = p.get_thermal_series()
        assert len(series) == 1
        assert abs(series[0].value - 25.0) < 0.01

    def test_critical_thermal_logs_event(self):
        """Critical thermal logs an FDIR event."""
        p = TelemetryProcessor()
        entry = _make_entry(TLM_MID_THERM, "thermal", value=120.0, health=2, health_label="CRITICAL")
        p.process(entry)

        events = p.get_events()
        assert any("Temperature CRITICAL" in e for e in events)

    def test_last_thermal_updated(self):
        """last_thermal always points to the most recent point."""
        p = TelemetryProcessor()
        entry = _make_entry(TLM_MID_THERM, "thermal", value=42.0)
        p.process(entry)
        assert abs(p.last_thermal.value - 42.0) < 0.01


class TestEVSProcessing:
    """Test EVS event message processing."""

    def test_evs_message_logged(self):
        """EVS messages appear in the event log."""
        p = TelemetryProcessor()
        parsed = {
            "mid": 0x0808,
            "mid_hex": "0x0808",
            "type": "evs",
            "event_text": "RAD_APP: Radiation received",
        }
        entry = RawTelemetryEntry(
            timestamp=time.time(), mid=0x0808,
            raw_hex="ff", parsed=parsed, size=32,
        )
        p.process(entry)

        events = p.get_events()
        assert any("RAD_APP: Radiation received" in e for e in events)

    def test_evs_solar_close_detection(self):
        """EVS message containing SOLAR CLOSE updates array status."""
        p = TelemetryProcessor()
        parsed = {
            "mid": 0x0808, "mid_hex": "0x0808",
            "type": "evs",
            "event_text": "SOLAR ARRAY CLOSE CMD SENT",
        }
        entry = RawTelemetryEntry(
            timestamp=time.time(), mid=0x0808,
            raw_hex="ff", parsed=parsed, size=32,
        )
        p.process(entry)
        assert p.solar_array_status == "Closed"

    def test_evs_solar_open_detection(self):
        """EVS message containing SOLAR OPEN updates array status."""
        p = TelemetryProcessor()
        parsed = {
            "mid": 0x0808, "mid_hex": "0x0808",
            "type": "evs",
            "event_text": "SOLAR ARRAY OPEN CMD RECEIVED",
        }
        entry = RawTelemetryEntry(
            timestamp=time.time(), mid=0x0808,
            raw_hex="ff", parsed=parsed, size=32,
        )
        p.process(entry)
        assert p.solar_array_status == "Open"


class TestRawLogging:
    """Test raw telemetry hex logging."""

    def test_raw_log_populated(self):
        """Every processed packet adds a raw log entry."""
        p = TelemetryProcessor()
        entry = _make_entry(TLM_MID_RAD, "radiation", value=50.0)
        p.process(entry)

        raw = p.get_raw_log()
        assert len(raw) == 1
        assert "0x0882" in raw[0]

    def test_raw_log_limit(self):
        """get_raw_log respects count parameter."""
        p = TelemetryProcessor()
        for i in range(10):
            entry = _make_entry(TLM_MID_RAD, "radiation", value=float(i))
            p.process(entry)

        raw = p.get_raw_log(count=3)
        assert len(raw) == 3


class TestSolarArrayStatus:
    """Test manual solar array status updates."""

    def test_update_solar_array_status(self):
        """Operator can manually set solar array status."""
        p = TelemetryProcessor()
        p.update_solar_array_status("Open")
        assert p.solar_array_status == "Open"

    def test_manual_update_logged(self):
        """Manual updates appear in the event log."""
        p = TelemetryProcessor()
        p.update_solar_array_status("Open")
        events = p.get_events()
        assert any("OPERATOR" in e and "Open" in e for e in events)

    def test_manual_override_after_fdir(self):
        """Operator can override FDIR-triggered status."""
        p = TelemetryProcessor()
        # FDIR triggers close
        entry = _make_entry(TLM_MID_RAD, "radiation", value=200.0, health=2, health_label="CRITICAL")
        p.process(entry)
        assert p.solar_array_status == "Closed (FDIR Auto)"

        # Operator overrides
        p.update_solar_array_status("Open")
        assert p.solar_array_status == "Open"


class TestTelemetryPoint:
    """Test the TelemetryPoint dataclass."""

    def test_default_values(self):
        """TelemetryPoint has sensible defaults."""
        pt = TelemetryPoint(timestamp=1000.0, value=50.0)
        assert pt.health == 0
        assert pt.health_label == "NOMINAL"

    def test_all_fields(self):
        """All fields are settable."""
        pt = TelemetryPoint(
            timestamp=2000.0, value=200.0,
            health=2, health_label="CRITICAL",
        )
        assert pt.value == 200.0
        assert pt.health == 2


class TestEventLogLimit:
    """Test event log buffer limits."""

    def test_event_log_respects_count(self):
        """get_events limits output to requested count."""
        p = TelemetryProcessor()
        for i in range(20):
            entry = _make_entry(
                TLM_MID_RAD, "radiation",
                value=200.0, health=2, health_label="CRITICAL",
            )
            p.process(entry)

        events = p.get_events(count=5)
        assert len(events) == 5

    def test_ring_buffer_overflow(self):
        """History respects max_points ring buffer."""
        p = TelemetryProcessor(max_points=5)
        for i in range(10):
            entry = _make_entry(TLM_MID_RAD, "radiation", value=float(i))
            p.process(entry)

        series = p.get_radiation_series()
        assert len(series) == 5
        assert abs(series[0].value - 5.0) < 0.01  # Oldest retained
