# CFS-Bridge

A bidirectional bridge between NASA's Core Flight System (cFS) and a Python Sensor Manager using the CCSDS Space Packet Protocol over UDP.

## Architecture

```
 Sensor Manager (Python)                       Flight Software (cFS)
+-------------------------+     UDP       +------------------------------------+
|                         |   :1234       |  CI_LAB (Command Ingest)           |
|  core/ccsds_utils.py    |------------->|         |                           |
|  (pack CCSDS packets)   |  sensor      |         v  Software Bus             |
|                         |  data        |  +------------+  +------------+     |
|  manager_app.py         |              |  |  RAD_APP   |  | THERM_APP  |     |
|  (Streamlit UI)         |              |  |  (0x1882)  |  |  (0x1883)  |     |
|                         |              |  +------+-----+  +------+-----+     |
|  sensors/               |              |         |               |           |
|  (radiation, thermal)   |              |    FDIR | >150 mSv/h    | FDIR      |
|                         |              |         v               v           |
|                         |              |  Solar Array     CFE_EVS Critical   |
|                         |              |  Close Cmd       Event Log          |
|                         |              |  (0x1890 FC=6)   (>100 C)           |
|                         |              |                                     |
|                         |              |  BRIDGE_APP (packet logger)         |
|                         |              |                                     |
|                         |  TLM :2234   |  TO_LAB -------> TLM (0x0882,      |
|                         |<-------------|  (Telemetry Out)   0x0883)          |
+-------------------------+              +------------------------------------+
```

### Communication Flow

1. **Sensor Simulation (Python -> cFS):** The Sensor Manager packs sensor readings into CCSDS command packets and sends via UDP to CI_LAB on port **1234**
2. **Software Bus Fan-out:** CI_LAB publishes to the cFS Software Bus. RAD_APP, THERM_APP, and BRIDGE_APP receive commands routed by MID
3. **FDIR Processing:** RAD_APP and THERM_APP extract the Big-Endian float payload, evaluate FDIR rules, and take autonomous action
4. **Telemetry Generation:** Both apps publish processed telemetry packets (with health status) to the Software Bus for downlink via TO_LAB

### FDIR Rules

| Application | Threshold | Action |
|-------------|-----------|--------|
| RAD_APP | Radiation > 150.0 mSv/h | Publish Solar Array Close command (MID `0x1890`, FC `6`) |
| THERM_APP | Temperature > 100.0 C | Log CRITICAL event via `CFE_EVS_SendEvent` |

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
  check_integration.sh            # End-to-end integration verification script
  firmware/
    Dockerfile                    # Builds cFS on Ubuntu 22.04
    apps/
      bridge_app/                 # cFS packet logger (subscribes to 0x1882)
      rad_app/                    # Radiation monitor + FDIR (subscribes to 0x1882)
      therm_app/                  # Thermal monitor + FDIR (subscribes to 0x1883)
    defs/                         # Mission config overlays
      targets.cmake               # Defines all apps in the mission build
      cpu1_cfe_es_startup.scr     # Application startup sequence
    patches/                      # cFS app patches
      to_lab_sub.c                # TO_LAB subscription table (TLM forwarding)
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
      radiation_sensor.py         # Radiation environment sensor (0-1000 rad)
      thermal_sensor.py           # Thermal sensor (-40-85 C)
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
- **cfs-flight**: cFS with CI_LAB, TO_LAB, BRIDGE_APP, RAD_APP, and THERM_APP
- **sensor-manager**: Streamlit UI for injecting simulated sensor data into cFS

### 3. Open the Sensor Manager UI

Navigate to [http://localhost:8501](http://localhost:8501) in your browser. Use the sliders to adjust sensor values and click **Send** to dispatch CCSDS packets to cFS.

### 4. Verify

Check that all apps initialized:

```bash
docker logs cfs-flight 2>&1 | grep -E "(BRIDGE_APP|RAD_APP|THERM_APP).*Initialized"
```

Expected output:
```
BRIDGE_APP: Initialized. Listening on MID 0x1882
RAD_APP: Initialized. Listening on CMD MID 0x1882, TLM MID 0x0882
THERM_APP: Initialized. Listening on CMD MID 0x1883, TLM MID 0x0883
```

Watch for received sensor data:

```bash
docker logs -f cfs-flight 2>&1 | grep -E "(RAD_APP|THERM_APP).*\[Pkt"
```

### 5. Run Unit Tests

```bash
python -m venv .venv
source .venv/bin/activate
pip install pytest streamlit
python -m pytest sensor_manager/tests/ -v
```

### 6. Run Integration Verification

Automated end-to-end check (builds, starts, sends test packets, verifies FDIR):

```bash
./check_integration.sh
```

Or run the Python integration test (requires containers running):

```bash
python -m pytest sensor_manager/tests/integration_test.py -v
```

### 7. Teardown

```bash
docker compose down
```

## cFS Applications

### RAD_APP (Radiation Monitor)

Subscribes to radiation sensor commands on MID `0x1882`. Extracts the Big-Endian float payload, evaluates FDIR thresholds, and generates telemetry.

- **FDIR**: If radiation > 150.0 mSv/h, publishes a Solar Array Close command (MID `0x1890`, FC `6`) to protect hardware
- **Telemetry**: Sends processed radiation value + health status on MID `0x0882`
- **Health Codes**: `0` = NOMINAL, `1` = WARNING (> 100 mSv/h), `2` = CRITICAL (> 150 mSv/h)

### THERM_APP (Thermal Monitor)

Subscribes to thermal sensor commands on MID `0x1883`. Extracts the Big-Endian float payload, evaluates FDIR thresholds, and generates telemetry.

- **FDIR**: If temperature > 100.0 C, logs a CRITICAL event via `CFE_EVS_SendEvent`
- **Telemetry**: Sends processed temperature value + health status on MID `0x0883`
- **Health Codes**: `0` = NOMINAL, `1` = WARNING (> 80 C), `2` = CRITICAL (> 100 C)

### BRIDGE_APP (Packet Logger)

Subscribes to MID `0x1882` and logs all received packets via `CFE_ES_WriteToSysLog`. Demonstrates SB fan-out.

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

| Application     | MID      | Type | Description                       |
|-----------------|----------|------|-----------------------------------|
| RAD_APP         | `0x1882` | CMD  | Radiation sensor data             |
| THERM_APP       | `0x1883` | CMD  | Thermal sensor data               |
| SOLAR_ARRAY_APP | `0x1890` | CMD  | Solar array commands              |
| RAD_APP         | `0x0882` | TLM  | Processed radiation telemetry     |
| THERM_APP       | `0x0883` | TLM  | Processed thermal telemetry       |
| TO_LAB          | `0x0880` | TLM  | Housekeeping telemetry            |

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
