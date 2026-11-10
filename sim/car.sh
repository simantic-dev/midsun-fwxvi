#!/usr/bin/env bash
# Run three boards on one CAN bus: rear_controller (BMS, STM32L496RG), front_controller and
# telemetry (both STM32L433CC), plus the ADBMS1818 pack and steering peers from run.sh.
# Prints how many frames each board sent per CAN ID.
# Usage: sim/car.sh [virtual-seconds]   (SIM=/path/to/pyrite/sim to pick a sim binary)
set -euo pipefail
cd "$(dirname "$0")/.."
SIM="${SIM:-sim}"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip -q install scons -r requirements.txt; }
source .venv/bin/activate  # scons shells out to python3 for CAN autogen
for p in rear_controller front_controller telemetry; do scons --project=$p; done
frames=$(mktemp)
trap 'rm -f "$frames"' EXIT
"$SIM" run --scenario sim/car.yaml --timeout "${1:-10}" --ascii --frames "$frames" \
  | grep --line-buffered -E "balance (ON|OFF)|FAULT|failed|steering:" || true
for m in bms front telemetry; do
  echo "== $m sent"
  grep "^\[$m\].*CAN Tx" "$frames" | grep -oE "id=0x[0-9A-Fa-f]+" | sort | uniq -c | sort -rn || true
done
