#!/bin/bash
# Simulated car -> Midnight Sun's telemetry dashboard. Run from the repository root:
#   SIM=/path/to/pyrite/sim DASH=/path/to/fwxvi_telemetry_client sim/dashboard/run.sh [virtual-seconds]
# DASH is a checkout of uw-midsun/fwxvi_telemetry_client with telemetry_client-pty.patch applied and
# built (cargo build --release). Close the dashboard window to stop the car.
set -u
: "${SIM:?set SIM to a pyrite sim binary}"
: "${DASH:?set DASH to the fwxvi_telemetry_client checkout}"
SECS=${1:-600}
PTY_FILE=sim/dashboard/xbee_pty.txt

for elf in rear_controller front_controller telemetry; do
  [ -f "build/arm/bin/projects/$elf.elf" ] || { echo "build $elf first: scons --project=$elf"; exit 1; }
done

rm -f "$PTY_FILE"
"$SIM" run --scenario sim/dashboard/car_dashboard.yaml --timeout "$SECS" \
  > sim/dashboard/sim.log 2> sim/dashboard/peers.log &
SIM_PID=$!
trap 'kill $SIM_PID 2>/dev/null' EXIT

for _ in $(seq 60); do [ -s "$PTY_FILE" ] && break; sleep 1; done
PTY=$(head -1 "$PTY_FILE" 2>/dev/null)
[ -n "$PTY" ] || { echo "the XBee bridge never opened its pty; see sim/dashboard/peers.log"; exit 1; }
echo "XBee stream on $PTY"

EXE="$DASH/target/release"
printf 'com_port = "%s"\nbaud_rate = 230400\ncan_yaml_path = "global_can.yaml"\n' "$PTY" > "$EXE/settings.toml"
(cd "$EXE" && TELEMETRY_AUTOCONNECT=1 TELEMETRY_PTY_RAW=1 ./telemetry_client)
