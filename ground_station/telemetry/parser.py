"""Telemetry parsing utilities for the Ground Station.

Provides a modular parser that converts raw CCSDS packet bytes into a
structured Python dictionary suitable for JSON display. EVS (MID 0x0808)
messages are decoded to extract printable ASCII event strings.
"""
from __future__ import annotations

import json
import struct
from typing import Dict

from sensor_manager.core import ccsds_utils

# Known telemetry MIDs
TLM_MID_RAD = 0x0882
TLM_MID_THERM = 0x0883
CFE_EVS_LONG_EVENT_MSG_MID = 0x0808


def parse_packet(data: bytes) -> Dict:
    """Parse a raw CCSDS packet (bytes) into a structured dictionary.

    Uses existing ccsds_utils helpers for primary and telemetry unpacking.
    The returned dict contains header fields plus a `type` and decoded
    payload fields where applicable.
    """
    result: Dict = {}

    # Primary header
    try:
        pri = ccsds_utils.unpack_primary_header(data)
    except Exception:
        # If header can't be unpacked, return raw hex
        return {"raw": data.hex()}

    mid = data and struct.unpack("!H", data[:2])[0]
    result.update(pri)
    result["mid"] = int(mid)
    result["mid_hex"] = f"0x{mid:04X}"

    # If telemetry packet, unpack telemetry secondary header and payload
    try:
        tlm = ccsds_utils.unpack_tlm_packet(data)
        result["seconds"] = tlm.get("seconds")
        result["subseconds"] = tlm.get("subseconds")
        payload = tlm.get("payload", b"")
    except Exception:
        # Not a telemetry packet (or too short) — return header-only dict
        result["raw"] = data.hex()
        return result

    # Decode payload by known MIDs
    if mid == TLM_MID_RAD and len(payload) >= 4:
        # cFS telemetry floats are little-endian in the payload
        value = struct.unpack("<f", payload[:4])[0]
        health = payload[4] if len(payload) > 4 else 0
        health_labels = {0: "NOMINAL", 1: "WARNING", 2: "CRITICAL"}
        result.update(
            {
                "type": "radiation",
                "value": value,
                "health": int(health),
                "health_label": health_labels.get(int(health), "UNKNOWN"),
            }
        )

    elif mid == TLM_MID_THERM and len(payload) >= 4:
        value = struct.unpack("<f", payload[:4])[0]
        health = payload[4] if len(payload) > 4 else 0
        health_labels = {0: "NOMINAL", 1: "WARNING", 2: "CRITICAL"}
        result.update(
            {
                "type": "thermal",
                "value": value,
                "health": int(health),
                "health_label": health_labels.get(int(health), "UNKNOWN"),
            }
        )

    elif mid == CFE_EVS_LONG_EVENT_MSG_MID:
        result["type"] = "evs"
        result["event_text"] = _parse_evs(payload)

    else:
        result["type"] = "unknown"
        result["payload_hex"] = payload.hex()

    return result


def _parse_evs(payload: bytes) -> str:
    """Best-effort extraction of printable ASCII from an EVS payload.

    The layout of cFE EVS long messages varies; extract a contiguous
    ASCII region if present, otherwise return hex.
    """
    text_bytes = []
    for b in payload:
        if 32 <= b < 127:
            text_bytes.append(chr(b))
        elif text_bytes and b == 0:
            break
        elif text_bytes:
            # Preserve word separation for non-printables encountered after start
            text_bytes.append(" ")
    txt = "".join(text_bytes).strip()
    return txt if txt else payload.hex()


def to_json(obj: Dict) -> str:
    """Return a pretty-printed JSON string for UI display."""
    return json.dumps(obj, indent=2, sort_keys=False)

