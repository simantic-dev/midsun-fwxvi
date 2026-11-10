# STAND-IN for the telemetry board's XBee forwarding (fallback, see DASH.md).
# The telemetry firmware's XBee task (xb_transmit.c) is not linked into the stock image, so
# this peer does what that task does: non-WS22 frames pass through unchanged, and the WS22
# raw frames are re-encoded into the telemetry's synthetic IDs 2039-2043 once a second
# (s_update_ws22_cache). Every datagram is written to a host pty in the framing of
# datagram.h: 0xAA, ID (u16 big-endian), DLC, data, 0xBB. The pty path goes to xbee_pty.txt.
import os
import struct
import tty

PTY_FILE = os.environ.get("XBEE_PTY_FILE", "sim/dashboard/xbee_pty.txt")
REFRESH_US = 1_000_000

WS22_IDS = set(range(0x081, 0x08C))
WS22_DRIVE_CMD = 0x501
SYNTH_STATUS, SYNTH_BUS, SYNTH_VELOCITY, SYNTH_TEMP, SYNTH_DRIVE = 2039, 2040, 2041, 2042, 2043
VEHICLE_RPM_TO_KPH = 0.10367


def _i16(v):
    return struct.pack("<h", max(-32768, min(32767, int(v))))


def _u16(v):
    return struct.pack("<H", max(0, min(65535, int(v))))


class Node:
    def __init__(self, ctx):
        self.ctx = ctx
        self.master, self.slave = os.openpty()
        tty.setraw(self.slave)
        os.set_blocking(self.master, False)
        self.path = os.ttyname(self.slave)
        with open(PTY_FILE, "w") as f:
            f.write(self.path + "\n")
        self.ws22 = {}  # raw WS22 frame id -> data (8 bytes)
        self.sent = 0
        self.dropped = 0
        ctx.schedule_periodic(REFRESH_US)
        ctx.info(f"xbee-bridge: pty {self.path}")

    def _datagram(self, can_id, data):
        data = bytes(data)[:8]
        return bytes([0xAA]) + struct.pack(">H", can_id) + bytes([len(data)]) + data + bytes([0xBB])

    def _write(self, can_id, data):
        try:
            os.write(self.master, self._datagram(can_id, data))
            self.sent += 1
        except BlockingIOError:
            self.dropped += 1

    def on_frame(self, frame):
        can_id, data = frame["id"], bytes(frame["data"])
        if can_id in WS22_IDS:
            self.ws22[can_id] = data
        elif can_id == WS22_DRIVE_CMD:
            self.ws22[can_id] = data
        else:
            self._write(can_id, data)

    def on_timer(self):
        s = self.ws22
        if 0x081 in s:  # status: limit flags then error flags in the raw frame
            d = s[0x081]
            self._write(SYNTH_STATUS, d[2:4] + d[0:2])  # error_flags then limit_flags, both LE
        if 0x082 in s:  # bus: voltage cV u16, current cA i16
            v, i = struct.unpack("<ff", s[0x082][:8])
            self._write(SYNTH_BUS, _u16(v * 100) + _i16(i * 100))
        if 0x083 in s:  # velocity: motor rpm x10 i16, vehicle kph x100 u16 (firmware derives kph from rpm)
            rpm = struct.unpack("<f", s[0x083][:4])[0]
            self._write(SYNTH_VELOCITY, _i16(rpm * 10) + _u16(rpm * VEHICLE_RPM_TO_KPH * 100))
        if 0x08B in s:  # temperature: motor x10 i16, heatsink x10 i16
            m, h = struct.unpack("<ff", s[0x08B][:8])
            self._write(SYNTH_TEMP, _i16(m * 10) + _i16(h * 10))
        if WS22_DRIVE_CMD in s:  # drive cmd: current x10000 u16, velocity rpm i16 (as sent by front)
            c, r = struct.unpack("<ff", s[WS22_DRIVE_CMD][:8])
            self._write(SYNTH_DRIVE, _u16(c * 10000) + _i16(r))
