"""
Mission Registry — Single Source of Truth
==========================================

Central message dictionary for the CFS-Bridge satellite simulation.
All Message IDs (MIDs) and Function Codes (FCs) are defined here.
Every module that needs to reference a cFS message or command
must import from this file to ensure consistency.

CCSDS MID encoding (16-bit StreamId):
  CMD: 0x1800 | topic_id   (Version=0, Type=1, SecHdr=1, APID=topic_id)
  TLM: 0x0800 | topic_id   (Version=0, Type=0, SecHdr=1, APID=topic_id)
"""


class MID:
    """Message IDs (MIDs) — StreamId values on the cFS Software Bus.

    Each MID is a 16-bit value encoding version, type, secondary header
    flag, and APID per the CCSDS Space Packet Protocol v1.
    """

    # ── Command MIDs (Type=1, SecHdr=1 → base 0x1800) ──
    RADIATION_APP    = 0x1882   # Radiation environment monitor
    THERMAL_APP      = 0x1883   # Thermal management system
    SOLAR_ARRAY_APP  = 0x1890   # Solar array drive controller

    # ── Telemetry MIDs (Type=0, SecHdr=1 → base 0x0800) ──
    TO_LAB_TLM       = 0x0880   # TO_LAB housekeeping telemetry


class FC:
    """Function Codes (FCs) — Command identifiers within an application.

    Common codes (0–4) follow cFS convention.
    Application-specific codes start at 5.
    """

    # Common function codes
    NOOP              = 0
    RESET             = 1

    # Sensor data injection (used by sensor simulator)
    SEND_DATA         = 2

    # Solar Array application-specific codes
    SOLAR_ARRAY_OPEN  = 5
    SOLAR_ARRAY_CLOSE = 6


# ── Human-readable name lookups for logging and diagnostics ──

MID_NAME = {
    MID.RADIATION_APP:   "RADIATION_APP",
    MID.THERMAL_APP:     "THERMAL_APP",
    MID.SOLAR_ARRAY_APP: "SOLAR_ARRAY_APP",
    MID.TO_LAB_TLM:      "TO_LAB_TLM",
}

FC_NAME = {
    FC.NOOP:              "NOOP",
    FC.RESET:             "RESET",
    FC.SEND_DATA:         "SEND_DATA",
    FC.SOLAR_ARRAY_OPEN:  "SOLAR_ARRAY_OPEN",
    FC.SOLAR_ARRAY_CLOSE: "SOLAR_ARRAY_CLOSE",
}
