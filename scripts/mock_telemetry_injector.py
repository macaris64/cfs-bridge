"""Simple UDP telemetry injector for manual integration testing.

Usage:
    python scripts/mock_telemetry_injector.py --host 127.0.0.1 --port 2234
"""
import argparse
import socket
import struct
import time

from sensor_manager.core import ccsds_utils


def send_packet(sock, addr, pkt):
    sock.sendto(pkt, addr)
    print("Sent", len(pkt), "bytes")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=2234)
    args = p.parse_args()

    addr = (args.host, args.port)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # EVS message
    evs_msg = b"CFE_EVT: Test EVS — Solar Array OPEN"
    pkt_evs = ccsds_utils.pack_telemetry_packet(mid=0x0808, payload=evs_msg)
    send_packet(s, addr, pkt_evs)
    time.sleep(0.2)

    # Radiation sample
    rad_payload = struct.pack("<fB", 12.34, 0)
    pkt_rad = ccsds_utils.pack_telemetry_packet(mid=0x0882, payload=rad_payload)
    send_packet(s, addr, pkt_rad)
    time.sleep(0.2)

    # Thermal sample
    thr_payload = struct.pack("<fB", 23.5, 0)
    pkt_thr = ccsds_utils.pack_telemetry_packet(mid=0x0883, payload=thr_payload)
    send_packet(s, addr, pkt_thr)

    s.close()


if __name__ == "__main__":
    main()

