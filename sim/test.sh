#!/bin/sh
# Runs the committed rear_controller (BMS) image on an STM32L496 with an ADBMS1818 pair and a steering peer
# for 40 virtual s (the full demo is 120 s). Pass = balancing enabled over CAN, the two high cells are
# discharged, the pack delta shrinks, and nothing faults.
cd "$(dirname "$0")/.." || exit 1
out=$(mktemp)
${SIM:-sim} run --scenario sim/scenario.yaml --timeout 40 --ascii >"$out" 2>&1
rc=0
chk() { if grep -qF -- "$2" "$out"; then echo "ok   $1"; else echo "FAIL $1"; rc=1; fi; }
chk "steering enables balancing" "balancing_enabled=1"
chk "first read: delta 80 mV" "t=0.3s pack min 3.900V max 3.980V delta 80 mV"
chk "AFE2 cell10 discharged" "dev1 cell10 balance ON"
chk "AFE1 cell3 discharged" "dev0 cell3 balance ON"
chk "delta shrinks to 54 mV by 30 s" "t=30.3s pack min 3.900V max 3.954V delta 54 mV"
if grep -v "^warning:" "$out" | grep -qiE "fault|panic|assert"; then echo "FAIL fault lines"; grep -v "^warning:" "$out" | grep -iE "fault|panic|assert" | head -3; rc=1; else echo "ok   no fault lines"; fi
rm -f "$out"
exit $rc
