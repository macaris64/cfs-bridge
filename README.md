# CFS-Bridge

A bidirectional bridge between NASA's Core Flight System (cFS) and a Python Ground Station using the CCSDS Space Packet Protocol over UDP.

## Architecture

```
 Ground Station (Python)                    Flight Software (cFS)
+-------------------------+     UDP      +---------------------------+
|                         |   :1234      |  CI_LAB (Command Ingest)  |
|  ccsds_utils.py         |------------>|       |                    |
|  (pack CCSDS packets)   |  commands   |       v  Software Bus     |
|                         |             |  +----------+----------+  |
|  app.py                 |             |  | SAMPLE   | BRIDGE   |  |
|  (send cmds / recv tlm) |             |  | APP      | APP      |  |
|                         |   :2234     |  | (0x1882) | (0x1882) |  |
|  Telemetry receiver     |<------------|  +----------+----------+  |
|                         |  telemetry  |       ^                   |
+-------------------------+             |  TO_LAB (Telemetry Output) |
                                        +---------------------------+
```

### Communication Flow

1. **Commands (Python -> cFS):** Ground station packs CCSDS command packets and sends via UDP to CI_LAB on port **1234**
2. **Software Bus Fan-out:** CI_LAB publishes to the cFS Software Bus. Both `sample_app` and `bridge_app` subscribe to MID `0x1882` and receive the command
3. **Bridge Logging:** `bridge_app` logs every received packet via `CFE_ES_WriteToSysLog`
4. **Telemetry (cFS -> Python):** TO_LAB subscribes to telemetry MIDs and forwards them via UDP on port **2234**

### CCSDS Primary Header (6 bytes, Big-Endian)

| Word     | Bits | Fields                                      |
|----------|------|---------------------------------------------|
| StreamId | 16   | Version(3), Type(1), SecHdrFlag(1), APID(11) |
| Sequence | 16   | SeqFlags(2), SeqCount(14)                    |
| Length   | 16   | TotalPacketBytes - 7                         |

## Repository Structure

```
cfs-bridge/
  docker-compose.yml              # Orchestrates cFS + ground station
  firmware/
    Dockerfile                    # Builds cFS on Ubuntu 22.04
    apps/bridge_app/              # Custom cFS app (subscribes to 0x1882)
      CMakeLists.txt
      fsw/src/bridge_app.c
      fsw/inc/bridge_app.h
    defs/                         # Mission config overlays
      targets.cmake               # Adds bridge_app to build
      cpu1_cfe_es_startup.scr     # Adds bridge_app to startup
    patches/
      to_lab_sub.c                # Enables telemetry subscriptions
    cFS/                          # NASA cFS submodule (unchanged)
  ground_station/
    Dockerfile                    # Python 3.10 container
    ccsds_utils.py                # CCSDS packet pack/unpack module
    test_ccsds_utils.py           # pytest suite (24 tests)
    app.py                        # Ground station main application
    integration_test.py           # End-to-end integration test
    requirements.txt              # Python dependencies
```

## Prerequisites

- Docker & Docker Compose
- Python 3.10+ (for running tests locally)

## Quick Start

### 1. Build

```bash
docker compose build
```

### 2. Run

```bash
docker compose up -d
```

This starts:
- **cfs-flight**: cFS with CI_LAB, TO_LAB, SAMPLE_APP, and BRIDGE_APP
- **ground-station**: Python app that sends NOOP commands and listens for telemetry

### 3. Verify

Check that cFS booted and bridge_app initialized:

```bash
docker logs cfs-flight 2>&1 | grep BRIDGE_APP
```

Expected output:
```
BRIDGE_APP: Initialized. Listening on MID 0x1882
```

### 4. Run Integration Test

From the host machine (requires Python 3.10+ with pytest):

```bash
python -m venv .venv
source .venv/bin/activate
pip install pytest
cd ground_station
python -m pytest integration_test.py -v
```

Or send a manual NOOP command:

```bash
cd ground_station
python -c "
from app import send_noop
send_noop('localhost', 1234)
"
```

Then verify receipt:

```bash
docker logs cfs-flight 2>&1 | grep "BRIDGE_APP: Received"
```

### 5. Run Unit Tests

```bash
source .venv/bin/activate
cd ground_station
python -m pytest test_ccsds_utils.py -v
```

All 24 tests cover APID bit-masking, sequence count encoding, checksum XOR validation, and pack/unpack round-trips.

### 6. Teardown

```bash
docker compose down
```

## Key Message IDs

| Application   | MID      | Type    | Description            |
|---------------|----------|---------|------------------------|
| SAMPLE_APP    | `0x1882` | CMD     | Ground commands        |
| SAMPLE_APP    | `0x0883` | TLM     | Housekeeping telemetry |
| TO_LAB        | `0x1880` | CMD     | TO_LAB commands        |
| CI_LAB        | `0x1884` | CMD     | CI_LAB commands        |

## UDP Port Map

| Port   | Direction       | Protocol | Purpose                    |
|--------|-----------------|----------|----------------------------|
| `1234` | Python -> cFS   | UDP      | CI_LAB command ingest      |
| `2234` | cFS -> Python   | UDP      | TO_LAB telemetry output    |

## Python CCSDS API

```python
from ccsds_utils import pack_cmd_packet, unpack_tlm_packet

# Send a NOOP command to SAMPLE_APP
packet = pack_cmd_packet(mid=0x1882, func_code=0)

# Unpack received telemetry
info = unpack_tlm_packet(raw_bytes)
print(f"APID={info['apid']:#05x} Time={info['seconds']}s")
```

## License

This project uses NASA cFS which is licensed under Apache 2.0.
