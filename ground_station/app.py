"""
CFS-Bridge Ground Station Application

Sends CCSDS-wrapped commands to NASA cFS via CI_LAB (UDP 1234) and
receives telemetry from TO_LAB (UDP 2234).

Usage:
    python app.py                          # Run with defaults (cfs-flight:1234)
    CFS_HOST=localhost python app.py       # Override target host
"""

import os
import socket
import struct
import sys
import time

from ccsds_utils import pack_cmd_packet, unpack_primary_header, unpack_tlm_packet

# cFS Message IDs (CMD base 0x1800 | topic_id)
SAMPLE_APP_CMD_MID = 0x1882   # SAMPLE_APP command
TO_LAB_CMD_MID = 0x1880       # TO_LAB command

# Function codes
SAMPLE_APP_NOOP_CC = 0        # SAMPLE_APP NOOP command
TO_LAB_OUTPUT_ENABLE_CC = 6   # TO_LAB enable output command


def send_command(host: str, port: int, mid: int, func_code: int,
                 payload: bytes = b'', seq_count: int = 0) -> int:
    """Pack and send a CCSDS command packet via UDP.

    Returns:
        Number of bytes sent.
    """
    packet = pack_cmd_packet(mid, func_code, payload, seq_count)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        bytes_sent = sock.sendto(packet, (host, port))
    finally:
        sock.close()
    return bytes_sent


def send_noop(host: str, port: int, seq_count: int = 0) -> int:
    """Send a NOOP command to SAMPLE_APP (MID 0x1882, FC=0).

    Both SAMPLE_APP and BRIDGE_APP receive this via SB fan-out.
    BRIDGE_APP logs receipt via CFE_ES_WriteToSysLog.
    """
    print(f"[TX] NOOP -> {host}:{port} (MID=0x{SAMPLE_APP_CMD_MID:04X}, FC={SAMPLE_APP_NOOP_CC})")
    return send_command(host, port, SAMPLE_APP_CMD_MID, SAMPLE_APP_NOOP_CC,
                        seq_count=seq_count)


def enable_to_lab_output(host: str, port: int, dest_ip: str) -> int:
    """Send EnableOutput command to TO_LAB to start telemetry forwarding.

    Args:
        host: CI_LAB host address
        port: CI_LAB UDP port
        dest_ip: Ground station IP for TO_LAB to send telemetry to
    """
    # TO_LAB EnableOutput payload: 16-byte null-terminated IP string
    ip_bytes = dest_ip.encode('ascii')
    payload = ip_bytes + b'\x00' * (16 - len(ip_bytes))
    print(f"[TX] EnableOutput -> {host}:{port} (dest_ip={dest_ip})")
    return send_command(host, port, TO_LAB_CMD_MID, TO_LAB_OUTPUT_ENABLE_CC,
                        payload=payload)


def receive_telemetry(bind_port: int, timeout: float = 5.0):
    """Listen for telemetry packets from TO_LAB.

    Args:
        bind_port: UDP port to bind and listen on (default: 2234)
        timeout: Socket timeout in seconds
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', bind_port))
    sock.settimeout(timeout)

    print(f"[RX] Listening for telemetry on UDP port {bind_port}...")

    try:
        while True:
            try:
                data, addr = sock.recvfrom(4096)
                hdr = unpack_primary_header(data)
                print(f"[RX] Telemetry from {addr}: "
                      f"APID=0x{hdr['apid']:03X} "
                      f"Seq={hdr['seq_count']} "
                      f"Len={hdr['data_length']} "
                      f"({len(data)} bytes)")
            except socket.timeout:
                print("[RX] Timeout waiting for telemetry")
                break
    finally:
        sock.close()


def main():
    cfs_host = os.environ.get('CFS_HOST', 'cfs-flight')
    cmd_port = int(os.environ.get('CFS_CMD_PORT', '1234'))
    tlm_port = int(os.environ.get('CFS_TLM_PORT', '2234'))

    print("=" * 60)
    print("CFS-Bridge Ground Station")
    print(f"  Target:    {cfs_host}:{cmd_port} (commands)")
    print(f"  Telemetry: port {tlm_port}")
    print("=" * 60)

    # Wait for cFS to boot
    print("\nWaiting for cFS to initialize...")
    time.sleep(8)

    # Step 1: Enable TO_LAB telemetry output
    try:
        # Get our own IP for TO_LAB to send telemetry back to us
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((cfs_host, cmd_port))
        our_ip = s.getsockname()[0]
        s.close()
        enable_to_lab_output(cfs_host, cmd_port, our_ip)
        time.sleep(1)
    except Exception as e:
        print(f"[WARN] Could not enable TO_LAB output: {e}")

    # Step 2: Send NOOP commands to SAMPLE_APP
    for i in range(3):
        send_noop(cfs_host, cmd_port, seq_count=i)
        time.sleep(1)

    # Step 3: Listen for telemetry
    print()
    receive_telemetry(tlm_port, timeout=10.0)

    print("\nGround station session complete.")


if __name__ == '__main__':
    main()
