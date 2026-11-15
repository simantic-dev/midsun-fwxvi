#!/bin/bash
# The simulated car, with the steering display in a browser and Midnight Sun's telemetry dashboard.
# Run from the repository root:
#   [SIM=/path/to/pyrite/sim] [DASH=/path/to/fwxvi_telemetry_client] sim/dashboard/run.sh [virtual-seconds]
# All four controllers run (car4.yaml); CAR=3 runs the three-board car with the steering stand-in
# (car_dashboard.yaml) instead. The steering display is at http://localhost:8765/.
# DASH, if set, is a checkout of uw-midsun/fwxvi_telemetry_client with telemetry_client-pty.patch
# applied and built (cargo build --release); close its window to stop the car. Without DASH, Ctrl-C stops it.
set -u
SIM=${SIM:-sim}   # the `sim` on PATH unless SIM names another
command -v "$SIM" >/dev/null || { echo "no pyrite sim: put 'sim' on PATH or set SIM"; exit 1; }
SECS=${1:-600}
PTY_FILE=sim/dashboard/xbee_pty.txt
FRAMES=sim/dashboard/steering-frames

ELFS="rear_controller front_controller telemetry steering"
SCENARIO=sim/dashboard/car4.yaml
if [ "${CAR:-4}" = 3 ]; then
  ELFS="rear_controller front_controller telemetry"
  SCENARIO=sim/dashboard/car_dashboard.yaml
fi
for elf in $ELFS; do
  [ -f "build/arm/bin/projects/$elf.elf" ] || { echo "build $elf first: scons --platform=arm --project=$elf"; exit 1; }
done

rm -rf "$PTY_FILE" "$FRAMES"
"$SIM" run --scenario "$SCENARIO" --timeout "$SECS" --display-dir "$FRAMES" \
  > sim/dashboard/sim.log 2> sim/dashboard/peers.log &
SIM_PID=$!
python3 sim/dashboard/display_view.py "$FRAMES" &
VIEW_PID=$!
trap 'kill $SIM_PID $VIEW_PID 2>/dev/null' EXIT

if [ -z "${DASH:-}" ]; then
  echo "car running (log: sim/dashboard/sim.log, peers: sim/dashboard/peers.log); Ctrl-C to stop"
  wait $SIM_PID
  exit
fi

for _ in $(seq 60); do [ -s "$PTY_FILE" ] && break; sleep 1; done
PTY=$(head -1 "$PTY_FILE" 2>/dev/null)
[ -n "$PTY" ] || { echo "the XBee bridge never opened its pty; see sim/dashboard/peers.log"; exit 1; }
echo "XBee stream on $PTY"

EXE="$DASH/target/release"
printf 'com_port = "%s"\nbaud_rate = 230400\ncan_yaml_path = "global_can.yaml"\n' "$PTY" > "$EXE/settings.toml"
(cd "$EXE" && TELEMETRY_AUTOCONNECT=1 TELEMETRY_PTY_RAW=1 ./telemetry_client)
