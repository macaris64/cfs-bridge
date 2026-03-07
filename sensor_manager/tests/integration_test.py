"""
Sensor Manager Integration Test

End-to-end test that verifies the sensor manager can send a
CCSDS-wrapped command to NASA cFS via CI_LAB, and that the bridge_app
receives and logs it via CFE_ES_WriteToSysLog.

Run from the host machine after `docker compose up -d`:
    python -m pytest sensor_manager/tests/integration_test.py -v
"""

import os
import socket
import subprocess
import sys
import time

from sensor_manager.core.ccsds_utils import pack_cmd_packet

# Test configuration
CFS_HOST = os.environ.get('CFS_HOST', 'localhost')
CFS_CMD_PORT = int(os.environ.get('CFS_CMD_PORT', '1234'))
CFS_CONTAINER = os.environ.get('CFS_CONTAINER', 'cfs-flight')

# cFS Message IDs
SAMPLE_APP_CMD_MID = 0x1882
NOOP_FC = 0


def wait_for_cfs_ready(timeout: int = 60) -> bool:
    """Wait for cFS to finish booting by polling container logs."""
    print(f"Waiting for cFS container '{CFS_CONTAINER}' to be ready...")
    start = time.time()

    while time.time() - start < timeout:
        try:
            result = subprocess.run(
                ['docker', 'logs', CFS_CONTAINER],
                capture_output=True, text=True, timeout=10,
            )
            # CI_LAB logs this message when it starts listening
            if 'CI_LAB' in result.stdout and 'Listening' in result.stdout:
                print(f"  cFS ready (took {time.time() - start:.1f}s)")
                return True
            # Also check for bridge_app initialization
            if 'BRIDGE_APP: Initialized' in result.stdout:
                print(f"  cFS ready (took {time.time() - start:.1f}s)")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        time.sleep(2)

    # If specific markers not found but container is running, proceed anyway
    try:
        result = subprocess.run(
            ['docker', 'inspect', '-f', '{{.State.Running}}', CFS_CONTAINER],
            capture_output=True, text=True, timeout=5,
        )
        if 'true' in result.stdout:
            print(f"  Container running (waited {timeout}s, proceeding)")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return False


def send_noop_command():
    """Send a SAMPLE_APP NOOP command via UDP to CI_LAB."""
    packet = pack_cmd_packet(SAMPLE_APP_CMD_MID, NOOP_FC, seq_count=1)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        bytes_sent = sock.sendto(packet, (CFS_HOST, CFS_CMD_PORT))
        print(f"  Sent {bytes_sent} bytes to {CFS_HOST}:{CFS_CMD_PORT}")
        print(f"  Packet: {packet.hex()}")
    finally:
        sock.close()
    return bytes_sent


def check_bridge_app_log() -> bool:
    """Check cFS container logs for BRIDGE_APP receipt confirmation."""
    try:
        result = subprocess.run(
            ['docker', 'logs', CFS_CONTAINER],
            capture_output=True, text=True, timeout=10,
        )
        stdout = result.stdout + result.stderr
        if 'BRIDGE_APP: Received MID=0x1882' in stdout:
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  Error checking logs: {e}")
    return False


def test_bridge_receives_noop():
    """Integration test: NOOP command reaches bridge_app and is logged."""
    # 1. Wait for cFS to boot
    assert wait_for_cfs_ready(), \
        f"cFS container '{CFS_CONTAINER}' did not become ready"

    # 2. Send NOOP command
    print("\nSending NOOP command to SAMPLE_APP (MID=0x1882)...")
    bytes_sent = send_noop_command()
    assert bytes_sent > 0, "Failed to send UDP packet"

    # 3. Wait for cFS to process the command
    print("Waiting for cFS to process command...")
    time.sleep(3)

    # 4. Verify bridge_app logged the receipt
    print("Checking cFS container logs for BRIDGE_APP receipt...")
    found = check_bridge_app_log()

    if found:
        print("\n  PASS: BRIDGE_APP received and logged MID=0x1882")
    else:
        # Print container logs for debugging
        try:
            result = subprocess.run(
                ['docker', 'logs', '--tail', '50', CFS_CONTAINER],
                capture_output=True, text=True, timeout=10,
            )
            print(f"\n  Container stdout (last 50 lines):\n{result.stdout}")
            print(f"\n  Container stderr (last 50 lines):\n{result.stderr}")
        except Exception:
            pass

    assert found, \
        "BRIDGE_APP did not log receipt of MID=0x1882. Check container logs above."


if __name__ == '__main__':
    print("=" * 60)
    print("Sensor Manager Integration Test")
    print("=" * 60)

    try:
        test_bridge_receives_noop()
        print("\nResult: ALL TESTS PASSED")
        sys.exit(0)
    except AssertionError as e:
        print(f"\nResult: FAILED - {e}")
        sys.exit(1)
