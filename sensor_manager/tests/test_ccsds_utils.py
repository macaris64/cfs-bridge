"""Pytest suite for CCSDS Space Packet Protocol utilities."""

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
    unpack_primary_header,
    unpack_cmd_packet,
    unpack_tlm_packet,
    compute_checksum,
)

# Well-known cFS MIDs for testing
SAMPLE_APP_CMD_MID = 0x1882  # CMD base 0x1800 | topic 0x82
SAMPLE_APP_HK_TLM_MID = 0x0883  # TLM base 0x0800 | topic 0x83
TO_LAB_CMD_MID = 0x1880  # CMD base 0x1800 | topic 0x80


class TestCCSDSPrimaryHeader:
    """Tests for CCSDS Primary Header pack/unpack and bit-masking."""

    def test_pack_cmd_header_known_mid(self):
        """StreamId for SAMPLE_APP_CMD_MID=0x1882 should produce bytes 0x18 0x82."""
        hdr = CCSDSPrimaryHeader(
            version=0,
            pkt_type=CCSDS_TYPE_CMD,
            sec_hdr_flag=1,
            apid=0x082,
            seq_flags=CCSDS_SEQ_STANDALONE,
            seq_count=0,
            data_length=1,
        )
        packed = hdr.pack()
        assert len(packed) == CCSDS_PRI_HDR_SIZE
        # StreamId word should equal the MID value
        stream_id = struct.unpack('!H', packed[:2])[0]
        assert stream_id == SAMPLE_APP_CMD_MID

    def test_pack_tlm_header_known_mid(self):
        """StreamId for SAMPLE_APP_HK_TLM_MID=0x0883 should produce bytes 0x08 0x83."""
        hdr = CCSDSPrimaryHeader(
            version=0,
            pkt_type=CCSDS_TYPE_TLM,
            sec_hdr_flag=1,
            apid=0x083,
            seq_flags=CCSDS_SEQ_STANDALONE,
            seq_count=0,
            data_length=5,
        )
        packed = hdr.pack()
        stream_id = struct.unpack('!H', packed[:2])[0]
        assert stream_id == SAMPLE_APP_HK_TLM_MID

    def test_unpack_roundtrip(self):
        """Pack then unpack should return identical field values."""
        original = CCSDSPrimaryHeader(
            version=0,
            pkt_type=CCSDS_TYPE_CMD,
            sec_hdr_flag=1,
            apid=0x082,
            seq_flags=CCSDS_SEQ_STANDALONE,
            seq_count=42,
            data_length=15,
        )
        packed = original.pack()
        recovered = CCSDSPrimaryHeader.unpack(packed)
        assert recovered.version == original.version
        assert recovered.pkt_type == original.pkt_type
        assert recovered.sec_hdr_flag == original.sec_hdr_flag
        assert recovered.apid == original.apid
        assert recovered.seq_flags == original.seq_flags
        assert recovered.seq_count == original.seq_count
        assert recovered.data_length == original.data_length

    def test_apid_bit_masking(self):
        """APID is 11 bits, only lower 11 bits should be preserved."""
        hdr = CCSDSPrimaryHeader(apid=0x7FF)  # max APID
        packed = hdr.pack()
        recovered = CCSDSPrimaryHeader.unpack(packed)
        assert recovered.apid == 0x7FF

    def test_sequence_count_14bit(self):
        """Sequence count is 14 bits, max value 0x3FFF."""
        hdr = CCSDSPrimaryHeader(
            seq_flags=CCSDS_SEQ_STANDALONE,
            seq_count=0x3FFF,
        )
        packed = hdr.pack()
        recovered = CCSDSPrimaryHeader.unpack(packed)
        assert recovered.seq_count == 0x3FFF

    def test_unpack_too_short_raises(self):
        """Unpacking fewer than 6 bytes should raise ValueError."""
        with pytest.raises(ValueError, match="Need 6 bytes"):
            CCSDSPrimaryHeader.unpack(b'\x00' * 5)

    def test_sequence_count_nonzero(self):
        """Non-zero sequence counts should encode correctly."""
        for count in [1, 100, 1000, 0x3FFF]:
            hdr = CCSDSPrimaryHeader(seq_count=count)
            recovered = CCSDSPrimaryHeader.unpack(hdr.pack())
            assert recovered.seq_count == count


class TestPackCmdPacket:
    """Tests for complete command packet assembly."""

    def test_noop_packet_size(self):
        """NOOP command (no payload) should be 8 bytes (6 pri + 2 sec)."""
        pkt = pack_cmd_packet(SAMPLE_APP_CMD_MID, func_code=0)
        assert len(pkt) == CCSDS_PRI_HDR_SIZE + CCSDS_CMD_SEC_HDR_SIZE

    def test_noop_data_length_field(self):
        """NOOP packet data_length = total(8) - 7 = 1."""
        pkt = pack_cmd_packet(SAMPLE_APP_CMD_MID, func_code=0)
        _, _, data_length = struct.unpack('!HHH', pkt[:6])
        assert data_length == 1

    def test_stream_id_matches_mid(self):
        """StreamId word should equal the provided MID."""
        pkt = pack_cmd_packet(SAMPLE_APP_CMD_MID, func_code=0)
        stream_id = struct.unpack('!H', pkt[:2])[0]
        assert stream_id == SAMPLE_APP_CMD_MID

    def test_with_payload(self):
        """Command with 16-byte payload should be 24 bytes total."""
        payload = b'192.168.1.1\x00' + b'\x00' * 4  # 16 bytes (IP string)
        pkt = pack_cmd_packet(TO_LAB_CMD_MID, func_code=6, payload=payload)
        assert len(pkt) == 6 + 2 + 16
        _, _, data_length = struct.unpack('!HHH', pkt[:6])
        assert data_length == 24 - 7  # 17

    def test_func_code_in_secondary_header(self):
        """Function code should appear in byte 6 of the packet."""
        pkt = pack_cmd_packet(SAMPLE_APP_CMD_MID, func_code=3)
        assert pkt[6] == 3

    def test_sequence_count(self):
        """Sequence count should be encoded in the sequence word."""
        pkt = pack_cmd_packet(SAMPLE_APP_CMD_MID, func_code=0, seq_count=99)
        seq_word = struct.unpack('!H', pkt[2:4])[0]
        seq_count = seq_word & 0x3FFF
        assert seq_count == 99


class TestChecksum:
    """Tests for CCSDS command checksum computation."""

    def test_checksum_xor_0xff(self):
        """XOR of all bytes in a packed command should equal 0xFF."""
        pkt = pack_cmd_packet(SAMPLE_APP_CMD_MID, func_code=0)
        xor_result = 0
        for b in pkt:
            xor_result ^= b
        assert xor_result == 0xFF

    def test_checksum_with_payload(self):
        """Checksum should be valid even with payload data."""
        payload = bytes(range(16))
        pkt = pack_cmd_packet(SAMPLE_APP_CMD_MID, func_code=5, payload=payload)
        xor_result = 0
        for b in pkt:
            xor_result ^= b
        assert xor_result == 0xFF

    def test_compute_checksum_basic(self):
        """compute_checksum on known bytes should return correct value."""
        # All zeros: XOR with 0xFF start -> 0xFF
        assert compute_checksum(b'\x00\x00\x00') == 0xFF
        # Single byte 0xFF: 0xFF ^ 0xFF = 0x00
        assert compute_checksum(b'\xff') == 0x00


class TestUnpackCmdPacket:
    """Tests for command packet disassembly."""

    def test_roundtrip(self):
        """Pack then unpack should recover all fields."""
        pkt = pack_cmd_packet(SAMPLE_APP_CMD_MID, func_code=3, seq_count=7)
        result = unpack_cmd_packet(pkt)
        assert result['apid'] == 0x082
        assert result['pkt_type'] == CCSDS_TYPE_CMD
        assert result['sec_hdr_flag'] == 1
        assert result['func_code'] == 3
        assert result['seq_count'] == 7
        assert result['payload'] == b''

    def test_roundtrip_with_payload(self):
        """Pack then unpack with payload should recover payload bytes."""
        payload = b'\xDE\xAD\xBE\xEF'
        pkt = pack_cmd_packet(SAMPLE_APP_CMD_MID, func_code=1, payload=payload)
        result = unpack_cmd_packet(pkt)
        assert result['payload'] == payload

    def test_too_short_raises(self):
        """Unpacking fewer than 8 bytes should raise ValueError."""
        with pytest.raises(ValueError, match="too short"):
            unpack_cmd_packet(b'\x00' * 7)


class TestUnpackTlmPacket:
    """Tests for telemetry packet disassembly."""

    def test_unpack_mock_telemetry(self):
        """Construct a mock telemetry packet and verify unpacking."""
        # Primary header: TLM type, APID 0x083
        # Total = 6 pri + 6 sec + 4 spare + 4 payload = 20
        hdr = CCSDSPrimaryHeader(
            pkt_type=CCSDS_TYPE_TLM,
            sec_hdr_flag=1,
            apid=0x083,
            seq_flags=CCSDS_SEQ_STANDALONE,
            seq_count=10,
            data_length=20 - 7,
        )
        pri = hdr.pack()
        tlm_sec = struct.pack('!IH', 1000, 500)
        spare = b'\x00' * 4
        payload = b'\x01\x02\x03\x04'
        pkt = pri + tlm_sec + spare + payload

        result = unpack_tlm_packet(pkt)
        assert result['pkt_type'] == CCSDS_TYPE_TLM
        assert result['apid'] == 0x083
        assert result['seconds'] == 1000
        assert result['subseconds'] == 500
        assert result['payload'] == payload

    def test_too_short_raises(self):
        """Unpacking fewer than 16 bytes should raise ValueError."""
        with pytest.raises(ValueError, match="too short"):
            unpack_tlm_packet(b'\x00' * 15)


class TestEdgeCases:
    """Edge case tests for boundary values."""

    def test_max_apid(self):
        """Maximum APID value 0x7FF should round-trip correctly."""
        pkt = pack_cmd_packet(0x1FFF, func_code=0)  # max APID with CMD bits
        result = unpack_cmd_packet(pkt)
        assert result['apid'] == 0x7FF

    def test_max_seq_count(self):
        """Maximum sequence count 0x3FFF should round-trip correctly."""
        pkt = pack_cmd_packet(SAMPLE_APP_CMD_MID, func_code=0, seq_count=0x3FFF)
        result = unpack_cmd_packet(pkt)
        assert result['seq_count'] == 0x3FFF

    def test_zero_length_payload(self):
        """Zero-length payload should produce valid 8-byte packet."""
        pkt = pack_cmd_packet(SAMPLE_APP_CMD_MID, func_code=0, payload=b'')
        assert len(pkt) == 8
        result = unpack_cmd_packet(pkt)
        assert result['payload'] == b''
