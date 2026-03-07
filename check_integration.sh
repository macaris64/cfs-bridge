#!/usr/bin/env bash
###############################################################################
# CFS-Bridge End-to-End Integration Verification Script
#
# Verifies that:
#   1. cFS boots and RAD_APP / THERM_APP initialize successfully
#   2. Python Sensor Manager can send CCSDS packets to cFS via CI_LAB
#   3. C apps correctly unpack Big-Endian float payloads
#   4. RAD_APP FDIR triggers Solar Array Close when Radiation > 150.0
#
# Usage:  ./check_integration.sh
# Prereq: Docker and docker-compose installed
###############################################################################

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0

pass() { echo -e "  ${GREEN}[PASS]${NC} $1"; PASS=$((PASS + 1)); }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; FAIL=$((FAIL + 1)); }
info() { echo -e "  ${YELLOW}[INFO]${NC} $1"; }

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

###############################################################################
# Step 1: Build and start containers
###############################################################################
echo ""
echo "=========================================="
echo " CFS-Bridge Integration Verification"
echo "=========================================="
echo ""

info "Building and starting containers..."
cd "$PROJECT_DIR"
docker compose down --remove-orphans 2>/dev/null || true
docker compose up --build -d 2>&1 | tail -5

###############################################################################
# Step 2: Wait for cFS to boot
###############################################################################
info "Waiting for cFS to boot (up to 30s)..."
CFS_READY=false
for i in $(seq 1 30); do
    if docker logs cfs-flight 2>&1 | grep -q "RAD_APP.*Initialized"; then
        CFS_READY=true
        break
    fi
    sleep 1
done

if [ "$CFS_READY" = true ]; then
    pass "cFS booted successfully"
else
    fail "cFS did not boot within 30 seconds"
    info "Last 20 lines of cFS logs:"
    docker logs cfs-flight 2>&1 | tail -20
    echo ""
    echo "Aborting. Check 'docker logs cfs-flight' for details."
    exit 1
fi

###############################################################################
# Step 3: Verify app initialization
###############################################################################
echo ""
echo "--- App Initialization ---"

CFS_LOGS=$(docker logs cfs-flight 2>&1)

if echo "$CFS_LOGS" | grep -q "RAD_APP.*Initialized.*CMD MID=0x1882"; then
    pass "RAD_APP initialized with CMD MID 0x1882"
else
    fail "RAD_APP initialization not found"
fi

if echo "$CFS_LOGS" | grep -q "THERM_APP.*Initialized.*CMD MID=0x1883"; then
    pass "THERM_APP initialized with CMD MID 0x1883"
else
    fail "THERM_APP initialization not found"
fi

if echo "$CFS_LOGS" | grep -q "BRIDGE_APP.*Initialized"; then
    pass "BRIDGE_APP initialized (legacy listener)"
else
    fail "BRIDGE_APP initialization not found"
fi

###############################################################################
# Step 4: Send nominal radiation value (50.0 mSv/h - below threshold)
###############################################################################
echo ""
echo "--- Nominal Radiation Test (50.0 mSv/h) ---"

docker exec sensor-manager python3 -c "
import struct, socket
from sensor_manager.core.ccsds_utils import pack_cmd_packet
payload = struct.pack('!f', 50.0)
pkt = pack_cmd_packet(0x1882, 2, payload=payload)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(pkt, ('cfs-flight', 1234))
print('Sent radiation=50.0 mSv/h packet')
" 2>&1 || fail "Failed to send nominal radiation packet"

sleep 2
CFS_LOGS=$(docker logs cfs-flight 2>&1)

if echo "$CFS_LOGS" | grep -q "RAD_APP.*Radiation = 50.00 mSv/h"; then
    pass "RAD_APP received and unpacked radiation=50.0 correctly"
else
    fail "RAD_APP did not report radiation=50.0 (Big-Endian float mismatch?)"
fi

###############################################################################
# Step 5: Send nominal temperature value (25.0 C - below threshold)
###############################################################################
echo ""
echo "--- Nominal Temperature Test (25.0 C) ---"

docker exec sensor-manager python3 -c "
import struct, socket
from sensor_manager.core.ccsds_utils import pack_cmd_packet
payload = struct.pack('!f', 25.0)
pkt = pack_cmd_packet(0x1883, 2, payload=payload)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(pkt, ('cfs-flight', 1234))
print('Sent temperature=25.0 C packet')
" 2>&1 || fail "Failed to send nominal temperature packet"

sleep 2
CFS_LOGS=$(docker logs cfs-flight 2>&1)

if echo "$CFS_LOGS" | grep -q "THERM_APP.*Temperature = 25.00 C"; then
    pass "THERM_APP received and unpacked temperature=25.0 correctly"
else
    fail "THERM_APP did not report temperature=25.0 (Big-Endian float mismatch?)"
fi

###############################################################################
# Step 6: Send critical radiation value (200.0 mSv/h - above 150.0 limit)
###############################################################################
echo ""
echo "--- FDIR Radiation Test (200.0 mSv/h > 150.0 limit) ---"

docker exec sensor-manager python3 -c "
import struct, socket
from sensor_manager.core.ccsds_utils import pack_cmd_packet
payload = struct.pack('!f', 200.0)
pkt = pack_cmd_packet(0x1882, 2, payload=payload)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(pkt, ('cfs-flight', 1234))
print('Sent radiation=200.0 mSv/h packet (FDIR trigger expected)')
" 2>&1 || fail "Failed to send critical radiation packet"

sleep 2
CFS_LOGS=$(docker logs cfs-flight 2>&1)

if echo "$CFS_LOGS" | grep -q "RAD_APP.*Radiation = 200.00 mSv/h"; then
    pass "RAD_APP received and unpacked radiation=200.0 correctly"
else
    fail "RAD_APP did not report radiation=200.0"
fi

if echo "$CFS_LOGS" | grep -q "RAD_APP.*FDIR TRIGGERED"; then
    pass "RAD_APP FDIR triggered for radiation > 150.0"
else
    fail "RAD_APP FDIR did not trigger"
fi

if echo "$CFS_LOGS" | grep -q "SOLAR ARRAY CLOSE CMD"; then
    pass "RAD_APP sent Solar Array Close command (MID 0x1890 FC 6)"
else
    fail "RAD_APP did not send Solar Array Close command"
fi

###############################################################################
# Step 7: Send critical temperature value (120.0 C - above 100.0 limit)
###############################################################################
echo ""
echo "--- FDIR Temperature Test (120.0 C > 100.0 limit) ---"

docker exec sensor-manager python3 -c "
import struct, socket
from sensor_manager.core.ccsds_utils import pack_cmd_packet
payload = struct.pack('!f', 120.0)
pkt = pack_cmd_packet(0x1883, 2, payload=payload)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(pkt, ('cfs-flight', 1234))
print('Sent temperature=120.0 C packet (FDIR trigger expected)')
" 2>&1 || fail "Failed to send critical temperature packet"

sleep 2
CFS_LOGS=$(docker logs cfs-flight 2>&1)

if echo "$CFS_LOGS" | grep -q "THERM_APP.*Temperature = 120.00 C"; then
    pass "THERM_APP received and unpacked temperature=120.0 correctly"
else
    fail "THERM_APP did not report temperature=120.0"
fi

if echo "$CFS_LOGS" | grep -q "THERM_APP.*FDIR TRIGGERED"; then
    pass "THERM_APP FDIR triggered for temperature > 100.0 C"
else
    fail "THERM_APP FDIR did not trigger"
fi

###############################################################################
# Summary
###############################################################################
echo ""
echo "=========================================="
echo " Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}"
echo "=========================================="
echo ""

if [ "$FAIL" -gt 0 ]; then
    info "Dumping last 30 lines of cFS logs for debugging:"
    echo "---"
    docker logs cfs-flight 2>&1 | tail -30
    echo "---"
    exit 1
fi

info "All integration checks passed!"
info "Containers are still running. Use 'docker compose down' to stop."
