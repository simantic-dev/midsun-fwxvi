# Wavesculptor 22 motor controller on the front-controller CAN bus (fwxvi
# libraries/ms-drivers/inc/ws22_motor_can.h). Ids and little-endian float layouts are the
# firmware's own (ws22_motor_can.c); no DBC is used.
#   0x501 drive command (host to WS22): float current, float velocity. Logged, not answered.
#   0x081 status info: two u16 limit flags, two u16 error flags (all zero here).
#   0x082 bus measurement: float bus_voltage, float bus_current.
#   0x083 velocity measurement: float motor_velocity (rpm), float vehicle_kph (unused by the firmware).
#   0x088 rail 15 V: float at bytes 4..7.
#   0x08B temperature: float motor_temp, float heat_sink_temp.
# Status frames go out every STATUS_PERIOD_US, as the WS22 does. Speed, bus current and bus voltage follow the
# drive scenario (drive.py): the bus is the pack, so the rear controller's precharge compare can complete.
import struct

DRIVE = "sim/dashboard/drive.py"
exec(compile(open(DRIVE).read(), DRIVE, "exec"))

DRIVE_CMD_ID = 0x501
STATUS_PERIOD_US = 100_000

# The steering board turns rpm into km/h as rpm * 3.141 * 0.558 * 0.001 * 60 (display.c): 0.558 m wheels.
KPH_PER_RPM = 3.141 * 0.558 * 0.001 * 60
RAIL_15V = 14.9
MOTOR_TEMP_C = 25.5
HEAT_SINK_TEMP_C = 30.0


def frames(t_s):
    f = struct.pack
    kph = speed_kph(t_s)
    return [
        (0x081, bytes(8)),
        (0x082, f("<ff", pack_v(t_s), motor_bus_a(t_s))),
        (0x083, f("<ff", kph / KPH_PER_RPM, kph)),
        (0x088, bytes(4) + f("<f", RAIL_15V)),
        (0x08B, f("<ff", MOTOR_TEMP_C, HEAT_SINK_TEMP_C)),
    ]


class Node:
    def __init__(self, ctx):
        self.ctx = ctx
        self.logged = False
        ctx.schedule_periodic(STATUS_PERIOD_US)

    def on_timer(self):
        for fid, data in frames(self.ctx.now_us / 1e6):
            self.ctx.send(fid, data)

    def on_frame(self, frame):
        if frame["id"] != DRIVE_CMD_ID or len(frame["data"]) < 8 or self.logged:
            return
        current, velocity = struct.unpack("<ff", bytes(frame["data"][:8]))
        self.ctx.info(f"ws22: drive command current={current:.3f} velocity={velocity:.1f}")
        self.logged = True
