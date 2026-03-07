"""
CCSDS Space Packet Protocol v1 - Primary Header Pack/Unpack Utilities

Implements the 6-byte CCSDS Primary Header and command/telemetry
secondary headers for communication with NASA cFS via CI_LAB/TO_LAB.

On-wire format (Big-Endian):
  Primary Header (6 bytes):
    StreamId [16]: Version(3) | Type(1) | SecHdrFlag(1) | APID(11)
    Sequence [16]: SeqFlags(2) | SeqCount(14)
    Length   [16]: TotalPacketBytes - 7

  Command Secondary Header (2 bytes):
    FunctionCode [8]
    Checksum     [8]   (XOR of all bytes = 0xFF)

  Telemetry Secondary Header (6 bytes):
    Seconds    [32]
    Subseconds [16]
"""

import struct
import time
from dataclasses import dataclass
from typing import Optional

# Packet type indicators
CCSDS_TYPE_TLM = 0
CCSDS_TYPE_CMD = 1

# Sequence flags
CCSDS_SEQ_FIRST = 0x01
CCSDS_SEQ_LAST = 0x02
CCSDS_SEQ_STANDALONE = 0x03

# Header sizes
CCSDS_PRI_HDR_SIZE = 6
CCSDS_CMD_SEC_HDR_SIZE = 2
CCSDS_TLM_SEC_HDR_SIZE = 6


@dataclass
class CCSDSPrimaryHeader:
    """CCSDS Space Packet Primary Header (6 bytes)."""
    version: int = 0
    pkt_type: int = CCSDS_TYPE_TLM
    sec_hdr_flag: int = 0
    apid: int = 0
    seq_flags: int = CCSDS_SEQ_STANDALONE
    seq_count: int = 0
    data_length: int = 0

    def pack(self) -> bytes:
        stream_id = (
            (self.version & 0x07) << 13
            | (self.pkt_type & 0x01) << 12
            | (self.sec_hdr_flag & 0x01) << 11
            | (self.apid & 0x7FF)
        )
        sequence = (
            (self.seq_flags & 0x03) << 14
            | (self.seq_count & 0x3FFF)
        )
        return struct.pack('!HHH', stream_id, sequence, self.data_length)

    @classmethod
    def unpack(cls, data: bytes) -> 'CCSDSPrimaryHeader':
        if len(data) < CCSDS_PRI_HDR_SIZE:
            raise ValueError(
                f"Need {CCSDS_PRI_HDR_SIZE} bytes, got {len(data)}"
            )
        stream_id, sequence, data_length = struct.unpack('!HHH', data[:6])
        return cls(
            version=(stream_id >> 13) & 0x07,
            pkt_type=(stream_id >> 12) & 0x01,
            sec_hdr_flag=(stream_id >> 11) & 0x01,
            apid=stream_id & 0x7FF,
            seq_flags=(sequence >> 14) & 0x03,
            seq_count=sequence & 0x3FFF,
            data_length=data_length,
        )


def compute_checksum(packet_bytes: bytes) -> int:
    """Compute CCSDS command checksum.

    The checksum byte is chosen so that XOR of all packet bytes
    (including the checksum itself) equals 0xFF.
    """
    result = 0xFF
    for b in packet_bytes:
        result ^= b
    return result


def pack_cmd_packet(
    mid: int,
    func_code: int,
    payload: bytes = b'',
    seq_count: int = 0,
) -> bytes:
    """Pack a complete CCSDS command packet.

    The MID value (e.g. 0x1882) is used directly as the StreamId word.
    For cFS commands, the MID already encodes Version=0, Type=1, SecHdr=1.

    Args:
        mid: Message ID (used as StreamId, e.g. 0x1882 for SAMPLE_APP_CMD)
        func_code: Command function code (7-bit, 0-127)
        payload: Command payload bytes
        seq_count: Sequence counter value

    Returns:
        Complete command packet bytes ready for UDP transmission.
    """
    total_length = CCSDS_PRI_HDR_SIZE + CCSDS_CMD_SEC_HDR_SIZE + len(payload)
    data_length = total_length - 7

    # Build primary header using MID directly as StreamId
    sequence = (CCSDS_SEQ_STANDALONE << 14) | (seq_count & 0x3FFF)
    pri_hdr = struct.pack('!HHH', mid, sequence, data_length)

    # Build command secondary header (checksum placeholder = 0)
    cmd_sec_hdr = struct.pack('BB', func_code & 0x7F, 0)

    # Compute checksum over entire packet with checksum byte = 0
    partial = pri_hdr + cmd_sec_hdr + payload
    chksum = compute_checksum(partial)

    # Rebuild with correct checksum
    cmd_sec_hdr = struct.pack('BB', func_code & 0x7F, chksum)
    return pri_hdr + cmd_sec_hdr + payload


def pack_telemetry_packet(
    mid: int,
    payload: bytes = b'',
    seq_count: int = 0,
    seconds: Optional[int] = None,
    subseconds: int = 0,
) -> bytes:
    """Pack a complete CCSDS telemetry packet.

    Builds a telemetry packet with a 6-byte secondary header containing
    a timestamp (Seconds + Subseconds).  The MID value is used directly
    as the StreamId word — for cFS telemetry the MID already encodes
    Version=0, Type=0, SecHdr=1.

    Args:
        mid: Message ID (used as StreamId, e.g. 0x0880 for TO_LAB_TLM)
        payload: Telemetry payload bytes
        seq_count: Sequence counter value
        seconds: Timestamp seconds since epoch (defaults to int(time.time()))
        subseconds: Timestamp sub-seconds (16-bit)

    Returns:
        Complete telemetry packet bytes.
    """
    if seconds is None:
        seconds = int(time.time())

    total_length = CCSDS_PRI_HDR_SIZE + CCSDS_TLM_SEC_HDR_SIZE + len(payload)
    data_length = total_length - 7

    # Primary header — MID encodes version/type/sec-hdr/APID
    sequence = (CCSDS_SEQ_STANDALONE << 14) | (seq_count & 0x3FFF)
    pri_hdr = struct.pack('!HHH', mid, sequence, data_length)

    # Telemetry secondary header: 4-byte seconds + 2-byte subseconds
    tlm_sec_hdr = struct.pack('!IH', seconds & 0xFFFFFFFF, subseconds & 0xFFFF)

    return pri_hdr + tlm_sec_hdr + payload


def unpack_primary_header(data: bytes) -> dict:
    """Unpack a CCSDS primary header into a dictionary.

    Returns:
        Dict with keys: version, pkt_type, sec_hdr_flag, apid,
                        seq_flags, seq_count, data_length
    """
    hdr = CCSDSPrimaryHeader.unpack(data)
    return {
        'version': hdr.version,
        'pkt_type': hdr.pkt_type,
        'sec_hdr_flag': hdr.sec_hdr_flag,
        'apid': hdr.apid,
        'seq_flags': hdr.seq_flags,
        'seq_count': hdr.seq_count,
        'data_length': hdr.data_length,
    }


def unpack_cmd_packet(data: bytes) -> dict:
    """Unpack a complete CCSDS command packet.

    Returns:
        Dict with primary header fields plus func_code, checksum, payload.
    """
    if len(data) < CCSDS_PRI_HDR_SIZE + CCSDS_CMD_SEC_HDR_SIZE:
        raise ValueError(
            f"Command packet too short: {len(data)} bytes"
        )
    result = unpack_primary_header(data)
    func_code, checksum = struct.unpack(
        'BB', data[CCSDS_PRI_HDR_SIZE:CCSDS_PRI_HDR_SIZE + 2]
    )
    result['func_code'] = func_code & 0x7F
    result['checksum'] = checksum
    result['payload'] = data[CCSDS_PRI_HDR_SIZE + CCSDS_CMD_SEC_HDR_SIZE:]
    return result


def unpack_tlm_packet(data: bytes) -> dict:
    """Unpack a CCSDS telemetry packet.

    Telemetry secondary header is 6 bytes: 4-byte seconds + 2-byte subseconds.

    Returns:
        Dict with primary header fields plus seconds, subseconds, payload.
    """
    tlm_total_hdr = CCSDS_PRI_HDR_SIZE + CCSDS_TLM_SEC_HDR_SIZE
    if len(data) < tlm_total_hdr:
        raise ValueError(
            f"Telemetry packet too short: {len(data)} bytes"
        )
    result = unpack_primary_header(data)
    seconds, subseconds = struct.unpack(
        '!IH', data[CCSDS_PRI_HDR_SIZE:tlm_total_hdr]
    )
    result['seconds'] = seconds
    result['subseconds'] = subseconds
    result['payload'] = data[tlm_total_hdr:]
    return result
