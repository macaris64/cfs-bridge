"""
Unit Tests for CCSDS Space Packet Protocol Utilities
=====================================================

Verifies:
  1. Primary header bit-shifting (APID, Type, Version extraction)
  2. Checksum calculation matches NASA cFS CI_LAB expectations
  3. Round-trip consistency (Pack -> Unpack -> original values)
  4. Telemetry packet packing with secondary header timestamps

Run:  pytest sensor_manager/tests/test_ccsds.py -v
"""

import struct
import pytest

from sensor_manager.core.ccsds_utils import (
    CCSDSPrimaryHeader,
    CCSDS_TYPE_CMD,
    CCSDS_TYPE_TLM,
    CCSDS_SEQ_STANDALONE,
    CCSDS_PRI_HDR_SIZE,
    CCSDS_CMD_SEC_HDR_SIZE,
    CCSDS_TLM_SEC_HDR_SIZE,
    pack_cmd_packet,
    pack_telemetry_packet,
    unpack_cmd_packet,
    unpack_tlm_packet,
    compute_checksum,
)
from sensor_manager.core.mission_registry import MID, FC


# ── Primary Header Bit-Shifting ──────────────────────────────────────


class TestPrimaryHeaderBitShifting:
    """Verify that version, type, sec-hdr flag, and APID are encoded
    in the correct bit positions of the 16-bit StreamId word."""

    def test_version_bits_15_to_13(self):
        """Version occupies bits [15:13] of the StreamId."""
        hdr = CCSDSPrimaryHeader(version=0, pkt_type=0, sec_hdr_flag=0, apid=0)
        stream_id = struct.unpack('!H', hdr.pack()[:2])[0]
        assert (stream_id >> 13) & 0x07 == 0

        hdr2 = CCSDSPrimaryHeader(version=7, pkt_type=0, sec_hdr_flag=0, apid=0)
        stream_id2 = struct.unpack('!H', hdr2.pack()[:2])[0]
        assert (stream_id2 >> 13) & 0x07 == 7

    def test_type_bit_12(self):
        """Packet type (CMD=1, TLM=0) occupies bit 12."""
        cmd_hdr = CCSDSPrimaryHeader(pkt_type=CCSDS_TYPE_CMD)
        tlm_hdr = CCSDSPrimaryHeader(pkt_type=CCSDS_TYPE_TLM)

        cmd_sid = struct.unpack('!H', cmd_hdr.pack()[:2])[0]
        tlm_sid = struct.unpack('!H', tlm_hdr.pack()[:2])[0]

        assert (cmd_sid >> 12) & 0x01 == 1
        assert (tlm_sid >> 12) & 0x01 == 0

    def test_sec_hdr_flag_bit_11(self):
        """Secondary header flag occupies bit 11."""
        with_sec = CCSDSPrimaryHeader(sec_hdr_flag=1)
        without_sec = CCSDSPrimaryHeader(sec_hdr_flag=0)

        sid_with = struct.unpack('!H', with_sec.pack()[:2])[0]
        sid_without = struct.unpack('!H', without_sec.pack()[:2])[0]

        assert (sid_with >> 11) & 0x01 == 1
        assert (sid_without >> 11) & 0x01 == 0

    def test_apid_bits_10_to_0(self):
        """APID occupies the lower 11 bits [10:0]."""
        for apid in [0x000, 0x082, 0x090, 0x7FF]:
            hdr = CCSDSPrimaryHeader(apid=apid)
            sid = struct.unpack('!H', hdr.pack()[:2])[0]
            assert sid & 0x7FF == apid

    def test_radiation_app_mid_encoding(self):
        """RADIATION_APP MID 0x1882 encodes: ver=0, type=1, sec=1, apid=0x082."""
        hdr = CCSDSPrimaryHeader(
            version=0, pkt_type=CCSDS_TYPE_CMD,
            sec_hdr_flag=1, apid=0x082,
        )
        sid = struct.unpack('!H', hdr.pack()[:2])[0]
        assert sid == MID.RADIATION_APP

    def test_thermal_app_mid_encoding(self):
        """THERMAL_APP MID 0x1883 encodes: ver=0, type=1, sec=1, apid=0x083."""
        hdr = CCSDSPrimaryHeader(
            version=0, pkt_type=CCSDS_TYPE_CMD,
            sec_hdr_flag=1, apid=0x083,
        )
        sid = struct.unpack('!H', hdr.pack()[:2])[0]
        assert sid == MID.THERMAL_APP

    def test_solar_array_app_mid_encoding(self):
        """SOLAR_ARRAY_APP MID 0x1890 encodes: ver=0, type=1, sec=1, apid=0x090."""
        hdr = CCSDSPrimaryHeader(
            version=0, pkt_type=CCSDS_TYPE_CMD,
            sec_hdr_flag=1, apid=0x090,
        )
        sid = struct.unpack('!H', hdr.pack()[:2])[0]
        assert sid == MID.SOLAR_ARRAY_APP

    def test_to_lab_tlm_mid_encoding(self):
        """TO_LAB_TLM MID 0x0880 encodes: ver=0, type=0, sec=1, apid=0x080."""
        hdr = CCSDSPrimaryHeader(
            version=0, pkt_type=CCSDS_TYPE_TLM,
            sec_hdr_flag=1, apid=0x080,
        )
        sid = struct.unpack('!H', hdr.pack()[:2])[0]
        assert sid == MID.TO_LAB_TLM

    def test_unpack_extracts_all_fields(self):
        """Unpack correctly extracts version, type, sec-hdr, APID from raw bytes."""
        # Manually construct StreamId = 0x1890 (SOLAR_ARRAY_APP)
        raw = struct.pack('!HHH', 0x1890, 0xC000, 0x0001)
        hdr = CCSDSPrimaryHeader.unpack(raw)
        assert hdr.version == 0
        assert hdr.pkt_type == CCSDS_TYPE_CMD
        assert hdr.sec_hdr_flag == 1
        assert hdr.apid == 0x090
        assert hdr.seq_flags == CCSDS_SEQ_STANDALONE
        assert hdr.seq_count == 0


# ── Checksum (cFS CI_LAB XOR Validation) ─────────────────────────────


class TestChecksumCILAB:
    """Verify the 8-bit XOR checksum matches NASA cFS CI_LAB expectations.

    CI_LAB validates incoming commands by XOR-ing every byte in the
    packet; the result must equal 0xFF.
    """

    def test_noop_checksum(self):
        """NOOP command packet XOR of all bytes == 0xFF."""
        pkt = pack_cmd_packet(MID.RADIATION_APP, FC.NOOP)
        xor = 0
        for b in pkt:
            xor ^= b
        assert xor == 0xFF

    def test_solar_array_open_checksum(self):
        """Solar Array Open command XOR of all bytes == 0xFF."""
        pkt = pack_cmd_packet(MID.SOLAR_ARRAY_APP, FC.SOLAR_ARRAY_OPEN)
        xor = 0
        for b in pkt:
            xor ^= b
        assert xor == 0xFF

    def test_command_with_payload_checksum(self):
        """Command with arbitrary payload still passes XOR == 0xFF."""
        payload = bytes(range(32))
        pkt = pack_cmd_packet(MID.THERMAL_APP, FC.RESET, payload=payload)
        xor = 0
        for b in pkt:
            xor ^= b
        assert xor == 0xFF

    def test_checksum_byte_position(self):
        """Checksum byte is at offset 7 (second byte of cmd secondary header)."""
        pkt = pack_cmd_packet(MID.RADIATION_APP, FC.NOOP)
        # Remove checksum byte, compute what it should be
        without_cksum = pkt[:7] + b'\x00' + pkt[8:]
        expected_cksum = compute_checksum(without_cksum)
        assert pkt[7] == expected_cksum

    def test_compute_checksum_identity(self):
        """compute_checksum on all-zero bytes returns 0xFF (identity)."""
        assert compute_checksum(b'\x00' * 10) == 0xFF

    def test_compute_checksum_0xff_input(self):
        """compute_checksum on single 0xFF byte returns 0x00."""
        assert compute_checksum(b'\xff') == 0x00


# ── Round-Trip Tests (Pack → Unpack) ─────────────────────────────────


class TestRoundTrip:
    """Pack then Unpack must return the original values exactly."""

    def test_cmd_roundtrip_noop(self):
        """NOOP command round-trip preserves all fields."""
        pkt = pack_cmd_packet(MID.RADIATION_APP, FC.NOOP, seq_count=42)
        result = unpack_cmd_packet(pkt)
        assert result['apid'] == 0x082
        assert result['pkt_type'] == CCSDS_TYPE_CMD
        assert result['sec_hdr_flag'] == 1
        assert result['func_code'] == FC.NOOP
        assert result['seq_count'] == 42
        assert result['payload'] == b''

    def test_cmd_roundtrip_with_payload(self):
        """Command with payload round-trips payload bytes exactly."""
        payload = b'\xCA\xFE\xBA\xBE\x00\x01\x02\x03'
        pkt = pack_cmd_packet(MID.SOLAR_ARRAY_APP, FC.SOLAR_ARRAY_OPEN,
                              payload=payload, seq_count=100)
        result = unpack_cmd_packet(pkt)
        assert result['apid'] == 0x090
        assert result['func_code'] == FC.SOLAR_ARRAY_OPEN
        assert result['seq_count'] == 100
        assert result['payload'] == payload

    def test_cmd_roundtrip_all_registry_mids(self):
        """Every CMD MID in mission_registry round-trips correctly."""
        cmd_mids = [MID.RADIATION_APP, MID.THERMAL_APP, MID.SOLAR_ARRAY_APP]
        for mid in cmd_mids:
            pkt = pack_cmd_packet(mid, FC.NOOP)
            result = unpack_cmd_packet(pkt)
            # Reconstruct the StreamId from unpacked fields
            reconstructed_sid = (
                (result['version'] & 0x07) << 13
                | (result['pkt_type'] & 0x01) << 12
                | (result['sec_hdr_flag'] & 0x01) << 11
                | (result['apid'] & 0x7FF)
            )
            assert reconstructed_sid == mid

    def test_tlm_roundtrip(self):
        """Telemetry packet round-trip preserves timestamps and payload."""
        payload = b'\x01\x02\x03\x04'
        pkt = pack_telemetry_packet(
            MID.TO_LAB_TLM, payload=payload,
            seq_count=7, seconds=86400, subseconds=1000,
        )
        result = unpack_tlm_packet(pkt)
        assert result['pkt_type'] == CCSDS_TYPE_TLM
        assert result['sec_hdr_flag'] == 1
        assert result['apid'] == 0x080
        assert result['seq_count'] == 7
        assert result['seconds'] == 86400
        assert result['subseconds'] == 1000
        assert result['payload'] == payload

    def test_tlm_roundtrip_empty_payload(self):
        """Telemetry with no payload round-trips correctly."""
        pkt = pack_telemetry_packet(MID.TO_LAB_TLM, seconds=0, subseconds=0)
        result = unpack_tlm_packet(pkt)
        assert result['seconds'] == 0
        assert result['subseconds'] == 0
        assert result['payload'] == b''

    def test_primary_header_roundtrip_exact(self):
        """CCSDSPrimaryHeader pack/unpack returns identical field values."""
        original = CCSDSPrimaryHeader(
            version=0, pkt_type=CCSDS_TYPE_CMD, sec_hdr_flag=1,
            apid=0x090, seq_flags=CCSDS_SEQ_STANDALONE,
            seq_count=999, data_length=15,
        )
        recovered = CCSDSPrimaryHeader.unpack(original.pack())
        assert recovered.version == original.version
        assert recovered.pkt_type == original.pkt_type
        assert recovered.sec_hdr_flag == original.sec_hdr_flag
        assert recovered.apid == original.apid
        assert recovered.seq_flags == original.seq_flags
        assert recovered.seq_count == original.seq_count
        assert recovered.data_length == original.data_length


# ── Telemetry Packet Structure ───────────────────────────────────────


class TestTelemetryPacket:
    """Verify pack_telemetry_packet produces correct structure."""

    def test_packet_size_no_payload(self):
        """TLM packet with no payload = 6 (pri) + 6 (sec) = 12 bytes."""
        pkt = pack_telemetry_packet(MID.TO_LAB_TLM, seconds=0)
        assert len(pkt) == CCSDS_PRI_HDR_SIZE + CCSDS_TLM_SEC_HDR_SIZE

    def test_packet_size_with_payload(self):
        """TLM packet with 8-byte payload = 12 + 8 = 20 bytes."""
        pkt = pack_telemetry_packet(MID.TO_LAB_TLM, payload=b'\x00' * 8, seconds=0)
        assert len(pkt) == 20

    def test_data_length_field(self):
        """data_length = total_bytes - 7."""
        pkt = pack_telemetry_packet(MID.TO_LAB_TLM, payload=b'\x00' * 4, seconds=0)
        _, _, data_length = struct.unpack('!HHH', pkt[:6])
        total = CCSDS_PRI_HDR_SIZE + CCSDS_TLM_SEC_HDR_SIZE + 4
        assert data_length == total - 7

    def test_seconds_at_correct_offset(self):
        """Seconds field is a big-endian uint32 at bytes [6:10]."""
        pkt = pack_telemetry_packet(MID.TO_LAB_TLM, seconds=0x12345678)
        secs = struct.unpack('!I', pkt[6:10])[0]
        assert secs == 0x12345678

    def test_subseconds_at_correct_offset(self):
        """Subseconds field is a big-endian uint16 at bytes [10:12]."""
        pkt = pack_telemetry_packet(MID.TO_LAB_TLM, seconds=0, subseconds=0xABCD)
        subsecs = struct.unpack('!H', pkt[10:12])[0]
        assert subsecs == 0xABCD

    def test_default_seconds_uses_epoch(self):
        """When seconds is omitted, it defaults to current epoch time."""
        import time
        before = int(time.time())
        pkt = pack_telemetry_packet(MID.TO_LAB_TLM)
        after = int(time.time())
        secs = struct.unpack('!I', pkt[6:10])[0]
        assert before <= secs <= after


# ── Edge Cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    """Boundary value tests."""

    def test_max_apid_roundtrip(self):
        """Maximum APID 0x7FF round-trips through pack/unpack."""
        hdr = CCSDSPrimaryHeader(apid=0x7FF)
        assert CCSDSPrimaryHeader.unpack(hdr.pack()).apid == 0x7FF

    def test_max_seq_count_roundtrip(self):
        """Maximum sequence count 0x3FFF round-trips."""
        hdr = CCSDSPrimaryHeader(seq_count=0x3FFF)
        assert CCSDSPrimaryHeader.unpack(hdr.pack()).seq_count == 0x3FFF

    def test_unpack_too_short_raises(self):
        """Unpacking < 6 bytes raises ValueError."""
        with pytest.raises(ValueError):
            CCSDSPrimaryHeader.unpack(b'\x00' * 5)

    def test_cmd_unpack_too_short_raises(self):
        """Command unpack < 8 bytes raises ValueError."""
        with pytest.raises(ValueError):
            unpack_cmd_packet(b'\x00' * 7)

    def test_tlm_unpack_too_short_raises(self):
        """Telemetry unpack < 12 bytes raises ValueError."""
        with pytest.raises(ValueError):
            unpack_tlm_packet(b'\x00' * 11)
