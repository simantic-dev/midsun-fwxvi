#!/usr/bin/env bash
# Build rear_controller (the BMS) for its real STM32L496 preset and run it on pyrite with a
# simulated 2 x ADBMS1818 pack and a steering node that enables balancing over CAN.
# Usage: sim/run.sh [virtual-seconds]   (SIM=/path/to/pyrite/sim to pick a sim binary)
set -euo pipefail
cd "$(dirname "$0")/.."
SIM="${SIM:-sim}"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip -q install scons -r requirements.txt; }
source .venv/bin/activate  # scons shells out to python3 for CAN autogen
scons --project=rear_controller
"$SIM" run --scenario sim/scenario.yaml --timeout "${1:-120}" --ascii \
  | grep --line-buffered -E "balance (ON|OFF)|MAX VOLTAGE|MIN VOLTAGE|UNBALANCE|FAULT|steering:"
