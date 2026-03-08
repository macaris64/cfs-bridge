import struct

from sensor_manager.core import ccsds_utils
from ground_station.telemetry import parser
import importlib
import sys
import types


def _import_ground_app_safe():
    """Return ground_station.ground_app module with minimal shims for heavy deps."""
    if "ground_station.ground_app" in sys.modules:
        return importlib.import_module("ground_station.ground_app")

    if "pandas" not in sys.modules:
        sys.modules["pandas"] = types.ModuleType("pandas")
    if "streamlit" not in sys.modules:
        st = types.ModuleType("streamlit")
        def cache_resource(fn=None):
            if fn is None:
                def _decorator(f):
                    return f
                return _decorator
            return fn
        st.cache_resource = cache_resource
        st.columns = lambda *args, **kwargs: []
        st.checkbox = lambda *args, **kwargs: False
        st.button = lambda *args, **kwargs: False
        st.caption = lambda *args, **kwargs: None
        st.subheader = lambda *args, **kwargs: None
        st.header = lambda *args, **kwargs: None
        st.set_page_config = lambda *args, **kwargs: None
        sys.modules["streamlit"] = st

    return importlib.import_module("ground_station.ground_app")


def test_parse_evs_payload():
    # Create a telemetry packet with MID 0x0808 and ASCII payload
    mid = 0x0808
    msg = b"CFE_EVT_TEST: Solar Array OPEN"
    pkt = ccsds_utils.pack_telemetry_packet(mid=mid, payload=msg, seq_count=1, seconds=123456789, subseconds=0)

    parsed = parser.parse_packet(pkt)
    assert parsed["mid"] == mid
    assert parsed["type"] == "evs"
    assert "SOLAR" in parsed["event_text"].upper()


def test_parse_radiation_payload():
    # Pack a radiation telemetry payload: little-endian float + health byte
    mid = 0x0882
    value = 42.5
    payload = struct.pack("<fB", value, 0)  # health=0
    pkt = ccsds_utils.pack_telemetry_packet(mid=mid, payload=payload, seq_count=2)

    parsed = parser.parse_packet(pkt)
    assert parsed["mid"] == mid
    assert parsed["type"] == "radiation"
    assert abs(parsed["value"] - value) < 1e-6
    assert parsed["health"] == 0


def test_parse_short_packet_returns_raw():
    data = b"\x01\x02"  # too short to be a CCSDS primary header
    parsed = parser.parse_packet(data)
    assert "raw" in parsed


def test_parse_evs_stops_at_null():
    payload = b"HELLO_WORLD\x00TRAILING_BYTES"
    txt = parser._parse_evs(payload)
    assert txt == "HELLO_WORLD"


def test_receiver_parses_radiation_packet():
    from ground_station.telemetry_receiver import TelemetryReceiver

    recv = TelemetryReceiver()
    mid = 0x0882
    value = 3.14159
    payload = struct.pack("<fB", value, 0)
    pkt = ccsds_utils.pack_telemetry_packet(mid=mid, payload=payload, seq_count=5)

    parsed = recv._parse_packet(mid, pkt)
    assert parsed.get("type") == "radiation"
    assert abs(parsed.get("value") - value) < 1e-6


def test_get_own_ip_returns_string():
    ground_app = _import_ground_app_safe()
    ip = ground_app._get_own_ip()
    assert isinstance(ip, str)
    assert ip != ""


def test_pack_cmd_packet_parsed_as_raw_header():
    # Create a command packet (not telemetry) and ensure parser returns header-only raw
    mid = 0x1882  # command MID (Type=1)
    pkt = ccsds_utils.pack_cmd_packet(mid=mid, func_code=3, payload=b"")
    parsed = parser.parse_packet(pkt)
    assert "raw" in parsed

