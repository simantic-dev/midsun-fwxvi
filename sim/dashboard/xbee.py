# Digi XBee radio on the telemetry board's UART2 (230400 baud), in transparent mode: what the firmware
# writes is what arrives at the pit, here a host pty that Midnight Sun's telemetry dashboard opens, and what
# is written to the pty arrives at the firmware. The firmware's own xb_transmit.c builds the datagrams
# (datagram.h: 0xAA, ID big-endian, DLC, data, 0xBB); this passes bytes through untouched.
# Attach: UART.ScriptedUartPeer, joined to telemetry.usart2 by a `uart` medium in the scenario.
# The pty path goes to XBEE_PTY_FILE (default sim/dashboard/xbee_pty.txt), where run.sh looks for it.
#
# MODELED SIMPLIFICATION: no RF link (latency, range, loss, the far XBee), no API mode or AT commands, and
# the module's XRST and SLEEP_RQ pins are not connected.
import os
import tty

PTY_FILE = os.environ.get("XBEE_PTY_FILE", "sim/dashboard/xbee_pty.txt")
POLL_US = 10_000               # how often bytes written to the pty are read back toward the firmware


class Peer:
    def __init__(self, ctx):
        self.ctx = ctx
        self.master, slave = os.openpty()
        tty.setraw(slave)
        os.set_blocking(self.master, False)
        self.path = os.ttyname(slave)
        with open(PTY_FILE, "w") as f:
            f.write(self.path + "\n")
        self.out = bytearray()
        self.sent = self.dropped = 0
        ctx.schedule_periodic(POLL_US)
        ctx.info(f"xbee: pty {self.path}")

    def on_byte(self, b):
        self.out.append(b)
        if b == 0xBB or len(self.out) >= 256:      # flush at a datagram's end byte
            self._flush()

    def _flush(self):
        try:
            os.write(self.master, bytes(self.out))
            self.sent += len(self.out)
        except (BlockingIOError, OSError):
            self.dropped += len(self.out)          # nobody reading the pty: the radio's bytes are lost
        self.out.clear()

    def on_timer(self):
        if self.out:
            self._flush()
        try:
            data = os.read(self.master, 256)
        except (BlockingIOError, OSError):
            return
        if data:
            self.ctx.send(data)
