# Drive scenario shared by the peers: one table, read at the same virtual time by every peer, so speed,
# currents, state of charge and cell voltages agree. It is a replay: it does not react to the firmware's
# pedal or drive commands.
#
# drive.csv: t_s, speed_kph, motor_bus_a (into the WS22, regen negative), solar_a (into the pack), linear
# between rows, looping. Pack current, in the BMS's sign (discharge negative, current_sense.c), is
#   pack_a = solar_a - motor_bus_a - AUX_A.
# The battery is the rear controller's own: 36s9p of 4.5 Ah cells (rear_controller_config.h), 15 mOhm a cell
# (state_of_charge.c SOC_DEFAULT_R0_CELL_OHM), and its SOC -> OCV table (state_of_charge_lut.h). State of
# charge is counted from SOC_START; a cell reads OCV(soc) + pack_a / 9 * R0.
#
# Load it from a peer with:  exec(compile(open(DRIVE).read(), DRIVE, "exec"))  where DRIVE = "sim/dashboard/drive.py"
import re

DRIVE_CSV = "sim/dashboard/drive.csv"
LUT_H = "projects/rear_controller/inc/state_of_charge_lut.h"
SERIES, PARALLEL, CELL_AH, R0_CELL = 36, 9, 4.5, 0.015
AUX_A = 0.8                    # low-voltage loads through the DC-DC, a constant draw
SOC_START = 0.80


def _rows():
    lines = open(DRIVE_CSV).read().split()
    return [tuple(float(x) for x in ln.split(",")) for ln in lines[1:]]


def _lut():
    # OCV_TABLE_VALUES falls (4.19 V first) while SOC_TABLE_VALUES rises: entry i of the OCV table is the
    # cell at SOC 1 - soc[i]. Pair them that way, so a full cell reads 4.19 V.
    text = open(LUT_H).read()
    grab = lambda name: [float(x) for x in re.findall(r"[-0-9.]+(?=f)", text.split(f"#define {name}")[1].split("}")[0])]
    soc_t, ocv_t = grab("SOC_TABLE_VALUES"), grab("OCV_TABLE_VALUES")
    if ocv_t[0] > ocv_t[-1]:
        ocv_t = ocv_t[::-1]
    return soc_t, ocv_t


ROWS = _rows()
PERIOD = ROWS[-1][0]
SOC_T, OCV_T = _lut()


def _interp(xs, ys, x):
    if x <= xs[0]:
        return ys[0]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            return ys[i - 1] + (ys[i] - ys[i - 1]) * (x - xs[i - 1]) / (xs[i] - xs[i - 1])
    return ys[-1]


def _at(t_s, col):
    t = t_s % PERIOD
    return _interp([r[0] for r in ROWS], [r[col] for r in ROWS], t)


def speed_kph(t_s):
    return _at(t_s, 1)


def motor_bus_a(t_s):
    return _at(t_s, 2)


def solar_a(t_s):
    return _at(t_s, 3)


def pack_a(t_s):
    return solar_a(t_s) - motor_bus_a(t_s) - AUX_A


def _charge_ah(t_s):
    # Integral of pack_a from 0 to t_s, in Ah: whole loops, then the trapezoids of this one.
    xs = [r[0] for r in ROWS]
    per = [solar - motor - AUX_A for _, _, motor, solar in ROWS]
    loop = sum((per[i] + per[i - 1]) / 2 * (xs[i] - xs[i - 1]) for i in range(1, len(xs)))
    n, t = divmod(t_s, PERIOD)
    q = n * loop
    for i in range(1, len(xs)):
        if t <= xs[i - 1]:
            break
        hi = min(t, xs[i])
        q += (per[i - 1] + _interp(xs, per, hi)) / 2 * (hi - xs[i - 1])
    return q / 3600.0


def soc(t_s):
    return min(1.0, max(0.0, SOC_START + _charge_ah(t_s) / (PARALLEL * CELL_AH)))


def cell_v(t_s):
    return _interp(SOC_T, OCV_T, soc(t_s)) + pack_a(t_s) / PARALLEL * R0_CELL


def pack_v(t_s):
    return SERIES * cell_v(t_s)


if __name__ == "__main__":
    for t in (0, 12, 20, 50, 72, 80, 95, 200, 1000):
        print(f"t={t:5}s speed {speed_kph(t):5.1f} motor {motor_bus_a(t):6.1f} A  pack {pack_a(t):6.1f} A"
              f"  soc {soc(t)*100:6.2f}%  cell {cell_v(t):.4f} V  pack {pack_v(t):6.2f} V")
    # Self-check: a parked car only draws AUX against solar, so SOC rises at (4 - 0.8) A.
    assert abs(pack_a(5) - (4 - AUX_A)) < 1e-9
    assert soc(PERIOD * 3) < SOC_START, "a loop must net discharge"
    assert 3.95 < cell_v(0) < 4.15, "a cell at 80% reads about 4.0-4.1 V"
    assert OCV_T[-1] > 4.18 and OCV_T[0] < OCV_T[-1]
