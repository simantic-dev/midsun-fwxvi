#!/usr/bin/env bash
# Build rear_controller (the BMS) for its real STM32L496 preset and run it on pyrite with a
# simulated 2 x ADBMS1818 pack and a steering node that enables balancing over CAN.
# Usage: sim/run.sh build                 # build rear_controller with scons (once; into .venv/ and build/)
#        sim/run.sh [virtual-seconds]     # run it (default 120); needs the build first
# SIM=/path/to/pyrite/sim picks a sim binary.
set -euo pipefail
cd "$(dirname "$0")/.."
SIM="${SIM:-sim}"
if [ "${1:-}" = build ]; then
  [ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip -q install scons -r requirements.txt; }
  source .venv/bin/activate  # scons shells out to python3 for CAN autogen
  scons --project=rear_controller
  exit 0
fi
[ -f build/arm/bin/projects/rear_controller.elf ] || { echo "firmware missing: run ./demo build first" >&2; exit 1; }
"$SIM" run --scenario sim/scenario.yaml --timeout "${1:-120}" --ascii 2>&1 \
  | grep --line-buffered -E "pack min|FAULT|steering:|Elapsed"
echo "bms: run complete, ${1:-120} virtual s"
