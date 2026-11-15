#!/usr/bin/env python3
"""Turn a telemetry SD-card log into a drive scenario, so the simulated car re-drives a real run.

    python3 sim/dashboard/sd_to_drive.py /Volumes/SDCARD > sim/dashboard/drive.csv
    python3 sim/dashboard/sd_to_drive.py logs_12.log > sim/dashboard/drive.csv
    sim/dashboard/run.sh 600

Input: a log the telemetry board wrote (projects/telemetry/src/telemetry_log.c), one line a CAN frame,
    (<seconds>.<microseconds>) can0 <id in decimal> #<data in hex>
or a folder holding logs_<n>.log files (the SD card mounted on a computer), of which it takes the largest.

Output, to stdout: drive.csv for drive.py, one row every --step seconds from the log's first frame:
    speed_kph    from the WS22's velocity frame (0x083, rpm), as the steering display converts it
    motor_bus_a  from the WS22's bus measurement frame (0x082)
    solar_a      pack_a + motor_bus_a + AUX_A, so drive.py gives back the logged pack current
with pack_a the rear controller's battery_stats_B.pack_current_a, decoded with its scaling in
can/boards/rear_controller.yaml. Each value holds until its next frame; rows start once all three are seen.
The state of charge still starts at drive.py's SOC_START.
"""
import argparse
import os
import re
import struct
import sys

import yaml

LINE = re.compile(r"\((\d+)\.(\d+)\)\s+can\d+\s+(\d+)\s*#([0-9A-Fa-f]*)")
WS22_BUS, WS22_VELOCITY = 0x082, 0x083
KPH_PER_RPM = 3.141 * 0.558 * 0.001 * 60       # steering/src/display.c: rpm * 3.141 * 0.558 * 0.001 * 60
AUX_A = 0.8                                     # drive.py's low-voltage load
REAR_YAML = "can/boards/rear_controller.yaml"


def signal_layout(yaml_path, message, signal):
    """(message id, bit offset, length, min, max) of a signal: fields are packed in order from bit 0."""
    msg = yaml.safe_load(open(yaml_path))["Messages"][message]
    offset = 0
    for name, sig in msg["signals"].items():
        if name == signal:
            return msg["id"], offset, sig["length"], sig.get("min"), sig.get("max")
        offset += sig["length"]
    raise KeyError(f"{message}.{signal} not in {yaml_path}")


def scaled(raw, length, lo, hi):
    """The generated getter's decode: raw 0 is below range, all ones above, the rest linear over (lo, hi)."""
    top = (1 << length) - 1
    if raw in (0, top):
        return None
    return (raw - 1) / (top - 2) * (hi - lo) + lo


def pick_log(path):
    if os.path.isdir(path):
        logs = [os.path.join(path, n) for n in os.listdir(path) if re.fullmatch(r"logs_\d+\.log", n, re.I)]
        if not logs:
            sys.exit(f"no logs_<n>.log in {path}")
        path = max(logs, key=os.path.getsize)
    print(f"reading {path}", file=sys.stderr)
    return path


def convert(path, step, out):
    pack_id, pack_off, pack_len, pack_lo, pack_hi = signal_layout(REAR_YAML, "battery_stats_B", "pack_current_a")
    now = {}
    t0 = next_row = None
    rows = frames = 0
    out.write("t_s,speed_kph,motor_bus_a,solar_a\n")
    for line in open(path, errors="replace"):
        m = LINE.match(line)
        if not m:
            continue
        frames += 1
        t = int(m[1]) + int(m[2]) / 1e6
        cid, data = int(m[3]), bytes.fromhex(m[4])
        if cid == WS22_BUS and len(data) == 8:
            now["motor"] = struct.unpack("<ff", data)[1]
        elif cid == WS22_VELOCITY and len(data) == 8:
            now["speed"] = struct.unpack("<ff", data)[0] * KPH_PER_RPM
        elif cid >> 4 == pack_id and cid != WS22_BUS and cid != WS22_VELOCITY and len(data) * 8 >= pack_off + pack_len:
            raw = int.from_bytes(data, "little") >> pack_off & ((1 << pack_len) - 1)
            amps = scaled(raw, pack_len, pack_lo, pack_hi)
            if amps is not None:
                now["pack"] = amps
        if len(now) < 3:
            continue
        if t0 is None:
            t0, next_row = t, t
        while t >= next_row:
            solar = now["pack"] + now["motor"] + AUX_A
            out.write(f"{next_row - t0:.1f},{now['speed']:.2f},{now['motor']:.2f},{solar:.2f}\n")
            rows += 1
            next_row += step
    print(f"{frames} frames, {rows} rows ({rows * step:.0f} s)", file=sys.stderr)
    if rows < 2:
        sys.exit("fewer than two rows: the log needs WS22 frames 0x082/0x083 and the rear controller's battery_stats_B")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("log", help="a logs_<n>.log file, or a folder (the SD card) holding them")
    p.add_argument("--step", type=float, default=0.5, help="seconds between rows (default 0.5)")
    a = p.parse_args()
    convert(pick_log(a.log), a.step, sys.stdout)
