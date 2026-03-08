#!/usr/bin/env bash
###############################################################################
# CFS-Bridge Mission Runner
#
# Orchestrates the full satellite simulation mission:
#   1. Build all Docker containers
#   2. Run unit tests
#   3. Start the mission (cFS + Sensor Manager + Ground Station)
#   4. Optionally run integration verification
#
# Usage:
#   ./run_mission.sh                  # Build, test, and start
#   ./run_mission.sh --skip-tests     # Build and start (skip tests)
#   ./run_mission.sh --integration    # Build, test, start, and verify
#   ./run_mission.sh --stop           # Stop all services
#   ./run_mission.sh --clean          # Stop and remove images
###############################################################################

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

info()  { echo -e "  ${YELLOW}[INFO]${NC}  $1"; }
ok()    { echo -e "  ${GREEN}[OK]${NC}    $1"; }
err()   { echo -e "  ${RED}[ERROR]${NC} $1"; }
header(){ echo -e "\n${CYAN}══════════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $1${NC}"; echo -e "${CYAN}══════════════════════════════════════════════════${NC}\n"; }

SKIP_TESTS=false
RUN_INTEGRATION=false

for arg in "$@"; do
    case $arg in
        --skip-tests)   SKIP_TESTS=true ;;
        --integration)  RUN_INTEGRATION=true ;;
        --stop)
            header "Stopping Mission"
            docker compose down
            ok "All services stopped"
            exit 0
            ;;
        --clean)
            header "Cleaning Up"
            docker compose down --rmi local --remove-orphans 2>/dev/null || true
            ok "Containers and local images removed"
            exit 0
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-tests     Skip unit tests"
            echo "  --integration    Run integration suite after start"
            echo "  --stop           Stop all services"
            echo "  --clean          Stop and remove images"
            echo "  --help, -h       Show this help"
            exit 0
            ;;
        *)
            err "Unknown option: $arg"
            exit 1
            ;;
    esac
done

# ── Step 1: Build ──
header "Step 1: Building Docker Containers"
docker compose build
ok "All containers built"

# ── Step 2: Test ──
if [ "$SKIP_TESTS" = false ]; then
    header "Step 2: Running Unit Tests"
    if python -m pytest sensor_manager/tests/ ground_station/tests/ -v; then
        ok "All unit tests passed"
    else
        err "Unit tests failed. Fix issues before starting mission."
        exit 1
    fi
else
    info "Skipping unit tests (--skip-tests)"
fi

# ── Step 3: Start Mission ──
header "Step 3: Starting Mission"
docker compose up -d
ok "All services starting..."

echo ""
echo "  Services:"
echo "    cFS Flight Software .... container 'cfs-flight'"
echo "    Sensor Manager UI ..... http://localhost:8501"
echo "    Ground Station UI ..... http://localhost:8502"
echo ""

# Wait for cFS to initialize
info "Waiting for cFS to initialize..."
CFS_READY=false
for i in $(seq 1 30); do
    if docker logs cfs-flight 2>&1 | grep -q "RAD_APP.*Initialized"; then
        CFS_READY=true
        break
    fi
    sleep 1
done

if [ "$CFS_READY" = true ]; then
    ok "cFS initialized and ready"
else
    err "cFS did not initialize within 30 seconds"
    info "Check logs: docker logs cfs-flight"
fi

# ── Step 4: Integration (optional) ──
if [ "$RUN_INTEGRATION" = true ]; then
    header "Step 4: Integration Verification"
    python integration_suite.py
fi

header "Mission Ready"
echo "  Sensor Manager:  http://localhost:8501  (Environment Simulator)"
echo "  Ground Station:  http://localhost:8502  (Mission Operations Center)"
echo ""
echo "  Stop:  ./run_mission.sh --stop"
echo "  Clean: ./run_mission.sh --clean"
echo ""
