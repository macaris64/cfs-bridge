# CFS-Bridge

A bidirectional bridge between NASA's Core Flight System (cFS) and a Python Sensor Manager using the CCSDS Space Packet Protocol over UDP.

## Architecture

```
 Sensor Manager (Python)                    Flight Software (cFS)
+-------------------------+     UDP      +---------------------------+
|                         |   :1234      |  CI_LAB (Command Ingest)  |
|  core/ccsds_utils.py    |------------>|       |                    |
|  (pack CCSDS packets)   |  sensor     |       v  Software Bus     |
|                         |  data       |  +----------+----------+  |
|  manager_app.py         |             |  | RAD_APP  | THERM_APP|  |
|  (Streamlit UI)         |             |  | (0x1882) | (0x1883) |  |
|                         |             |  +----------+----------+  |
|  sensors/               |             |       ^                   |
|  (radiation, thermal)   |             |  BRIDGE_APP (logger)      |
+-------------------------+             +---------------------------+
```

### Communication Flow

1. **Sensor Simulation (Python -> cFS):** The Sensor Manager packs sensor readings into CCSDS command packets and sends via UDP to CI_LAB on port **1234**
2. **Software Bus Fan-out:** CI_LAB publishes to the cFS Software Bus. Application-specific apps receive commands routed by MID
3. **Bridge Logging:** `bridge_app` logs every received packet via `CFE_ES_WriteToSysLog`

### CCSDS Primary Header (6 bytes, Big-Endian)

| Word     | Bits | Fields                                      |
|----------|------|---------------------------------------------|
| StreamId | 16   | Version(3), Type(1), SecHdrFlag(1), APID(11) |
| Sequence | 16   | SeqFlags(2), SeqCount(14)                    |
| Length   | 16   | TotalPacketBytes - 7                         |

## Repository Structure

```
cfs-bridge/
  docker-compose.yml              # Orchestrates cFS + sensor manager
  pyproject.toml                  # Pytest config & project metadata
  firmware/
    Dockerfile                    # Builds cFS on Ubuntu 22.04
    apps/bridge_app/              # Custom cFS app (subscribes to 0x1882)
    defs/                         # Mission config overlays
    patches/                      # cFS app patches
    cFS/                          # NASA cFS submodule (unchanged)
  sensor_manager/
    Dockerfile                    # Python 3.10 + Streamlit container
    requirements.txt              # pytest + streamlit
    manager_app.py                # Streamlit UI for real-time sensor simulation
    verify_core.py                # CCSDS packet verification script
    core/
      __init__.py                 # Re-exports all core symbols
      base_sensor.py              # Abstract BaseSensor class
      ccsds_utils.py              # CCSDS packet pack/unpack utilities
      mission_registry.py         # Single source of truth for MIDs & FCs
    sensors/
      __init__.py                 # Auto-exports all sensor classes
      radiation_sensor.py         # Radiation environment sensor (0–1000 rad)
      thermal_sensor.py           # Thermal sensor (-40–85 °C)
    tests/
      test_ccsds.py               # CCSDS protocol tests (32 tests)
      test_ccsds_utils.py         # CCSDS utility tests (24 tests)
      test_sensors.py             # Sensor framework tests (12 tests)
      integration_test.py         # End-to-end Docker integration test
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
- **sensor-manager**: Streamlit UI for injecting simulated sensor data into cFS

### 3. Open the Sensor Manager UI

Navigate to [http://localhost:8501](http://localhost:8501) in your browser. Use the sliders to adjust sensor values and click **Send** to dispatch CCSDS packets to cFS.

### 4. Verify

Check that cFS booted and bridge_app initialized:

```bash
docker logs cfs-flight 2>&1 | grep BRIDGE_APP
```

Expected output:
```
BRIDGE_APP: Initialized. Listening on MID 0x1882
```

### 5. Run Unit Tests

```bash
python -m venv .venv
source .venv/bin/activate
pip install pytest
python -m pytest sensor_manager/tests/ -v
```

### 6. Run Integration Test

Requires Docker containers to be running:

```bash
python -m pytest sensor_manager/tests/integration_test.py -v
```

### 7. Teardown

```bash
docker compose down
```

## Sensor Manager Framework

The Sensor Manager uses an extensible plugin architecture. To add a new sensor:

1. Create a new file in `sensor_manager/sensors/` (e.g., `pressure_sensor.py`)
2. Define a class inheriting from `BaseSensor` with the required attributes
3. The Streamlit UI discovers it automatically on next launch

```python
from sensor_manager.core.base_sensor import BaseSensor
from sensor_manager.core.mission_registry import MID, FC

class PressureSensor(BaseSensor):
    name = "Pressure Sensor"
    mid = MID.SOME_APP          # Add MID to mission_registry.py
    func_code = FC.SEND_DATA
    unit = "hPa"
    min_value = 0.0
    max_value = 1100.0
    default = 1013.25
```

## Key Message IDs

| Application     | MID      | Type | Description                |
|-----------------|----------|------|----------------------------|
| RADIATION_APP   | `0x1882` | CMD  | Radiation sensor data      |
| THERMAL_APP     | `0x1883` | CMD  | Thermal sensor data        |
| SOLAR_ARRAY_APP | `0x1890` | CMD  | Solar array commands       |
| TO_LAB_TLM      | `0x0880` | TLM  | Housekeeping telemetry     |

## UDP Port Map

| Port   | Direction        | Protocol | Purpose                    |
|--------|------------------|----------|----------------------------|
| `1234` | Python -> cFS    | UDP      | CI_LAB command ingest      |
| `8501` | Browser -> Python| TCP      | Streamlit Sensor Manager UI|

## Python CCSDS API

```python
from sensor_manager.core import pack_cmd_packet, unpack_tlm_packet, MID, FC

# Send a sensor data command to RADIATION_APP
packet = pack_cmd_packet(mid=MID.RADIATION_APP, func_code=FC.SEND_DATA,
                         payload=struct.pack('!f', 123.45))

# Unpack received telemetry
info = unpack_tlm_packet(raw_bytes)
print(f"APID={info['apid']:#05x} Time={info['seconds']}s")
```

## License

This project uses NASA cFS which is licensed under Apache 2.0.
