"""
Core Verification Script
========================

Builds a 'Solar Array Open' CCSDS command packet and prints a
formatted hex dump with annotated byte fields so you can visually
verify byte alignment against the CCSDS Space Packet Protocol v1.

Run:  python -m sensor_manager.verify_core
"""

from sensor_manager.core.mission_registry import MID, FC, MID_NAME, FC_NAME
from sensor_manager.core.ccsds_utils import pack_cmd_packet, unpack_cmd_packet


def hex_dump(data: bytes, label: str = "") -> None:
    """Print a formatted hex dump: offset | hex bytes | ASCII."""
    if label:
        print(f"\n{label}")
        print("-" * 60)
    for offset in range(0, len(data), 16):
        chunk = data[offset:offset + 16]
        hex_part = ' '.join(f'{b:02X}' for b in chunk)
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        print(f"  {offset:04X}:  {hex_part:<48s}  |{ascii_part}|")


def main():
    print("=" * 60)
    print("Sensor Manager — Core Verification")
    print("CCSDS Space Packet Protocol v1")
    print("=" * 60)

    # ── Build Solar Array Open command ──
    mid = MID.SOLAR_ARRAY_APP
    fc = FC.SOLAR_ARRAY_OPEN

    packet = pack_cmd_packet(mid, fc)

    print(f"\nCommand: {MID_NAME[mid]} / {FC_NAME[fc]}")
    print(f"  MID:           0x{mid:04X}")
    print(f"  Function Code: {fc}")
    print(f"  Packet Size:   {len(packet)} bytes")

    hex_dump(packet, "Packet Hex Dump")

    # ── Annotated byte breakdown ──
    seq_word = (packet[2] << 8) | packet[3]
    data_len = (packet[4] << 8) | packet[5]

    print("\nByte Breakdown:")
    print(f"  [0:2]  StreamId:     0x{packet[0]:02X}{packet[1]:02X}"
          f"  (MID=0x{mid:04X})")
    print(f"  [2:4]  Sequence:     0x{packet[2]:02X}{packet[3]:02X}"
          f"  (Flags={seq_word >> 14}, Count={seq_word & 0x3FFF})")
    print(f"  [4:6]  DataLength:   0x{packet[4]:02X}{packet[5]:02X}"
          f"  ({data_len})")
    print(f"  [6]    FunctionCode: 0x{packet[6]:02X}  ({packet[6]})")
    print(f"  [7]    Checksum:     0x{packet[7]:02X}")

    # ── Checksum verification ──
    xor = 0
    for b in packet:
        xor ^= b
    status = "PASS" if xor == 0xFF else "FAIL"
    print(f"\nChecksum Verification:")
    print(f"  XOR of all bytes = 0x{xor:02X}  [{status}]")

    # ── Round-trip verification ──
    result = unpack_cmd_packet(packet)
    print(f"\nRound-Trip Verification:")
    print(f"  APID:     0x{result['apid']:03X}  (expected 0x090)")
    print(f"  Type:     {result['pkt_type']}      (expected 1=CMD)")
    print(f"  SecHdr:   {result['sec_hdr_flag']}      (expected 1)")
    print(f"  FuncCode: {result['func_code']}      (expected {fc})")
    rt_ok = (result['apid'] == 0x090
             and result['pkt_type'] == 1
             and result['func_code'] == fc)
    print(f"  Status:   {'PASS' if rt_ok else 'FAIL'}")

    print("\n" + "=" * 60)
    print("Verification complete.")


if __name__ == '__main__':
    main()
