# Stands in for the steering board: answers every frame the rear controller sends with a
# `steering` message (id (6<<4)|4 = 0x64) whose buttons.balancing_enabled bit is set.
STEERING_ID = 0x64
BALANCING = bytes([0, 0, 0, 0, 0x00, 0x01, 0, 0])  # buttons at byte 4; balancing_enabled = bit 8


class Node:
    def __init__(self, ctx):
        self.ctx = ctx
        self.sent = False

    def on_frame(self, frame):
        if not self.sent:
            self.ctx.info("steering: balancing_enabled=1")
            self.sent = True
        self.ctx.send(STEERING_ID, BALANCING)
