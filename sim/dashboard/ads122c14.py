# TI ADS122C14 24-bit delta-sigma ADC as the rear controller's pack-current sense (I2C3, address 0x40,
# projects/rear_controller/src/current_sense.c), reading the shunt current of the drive scenario (drive.py).
# Attach: I2C.ScriptedI2cSlave @ i2c3 0x40.
#
# Framing as the firmware's driver uses it (libraries/ms-drivers/src/arm/current_ads122c14irter.c):
#   write [0x80 | reg, value, 0x80 | reg, value, ...]   register writes, any number of pairs
#   write [0x40 | reg] then read 1                      register read (DEVICE_ID must not be 0)
#   write [0x00] then read 5                            conversion: STATUS_MSB (bit 0 = DRDY), STATUS_LSB, then
#                                                       the 24-bit two's-complement code, MSB first
# Writing CONVERSION_CTRL (reg 4) with the START bit (0x02) starts a single-shot conversion; DRDY is set from
# then on, the result being the shunt voltage at that moment.
#   code = I_pack * R_SHUNT / FSR * 2^23
# with the firmware's 0.5 mOhm shunt and its full-scale range, 2.5 V reference / gain 10 (current_sense.c
# CSENSE_FSR_V).
#
# MODELED SIMPLIFICATION: the full-scale range is the firmware's own constant, not decoded from the GAIN_CFG and
# REFERENCE_CFG it writes (no ADS122C14 datasheet to hand); the conversion is instant (no data-rate delay),
# noiseless, and reads the scenario's pack current rather than a shunt voltage. Other registers are stored and
# read back without effect. DEVICE_ID reads DEVICE_ID_VALUE, an arbitrary non-zero value the firmware accepts.
DRIVE = "sim/dashboard/drive.py"
exec(compile(open(DRIVE).read(), DRIVE, "exec"))

R_SHUNT = 0.0005                    # CSENSE_SHUNT_RESISTANCE_OHM
FSR_V = 2.5 / 10                    # CSENSE_FSR_V
DEVICE_ID_VALUE = 0x01
REG_DEVICE_ID, REG_CONVERSION_CTRL = 0x00, 0x04
START = 0x02


class Slave:
    def __init__(self, ctx):
        self.ctx = ctx
        self.regs = [0] * 16
        self.regs[REG_DEVICE_ID] = DEVICE_ID_VALUE
        self.out = b""
        self.code = 0
        self.ready = False

    def _convert(self):
        v = pack_a(self.ctx.now_us / 1e6) * R_SHUNT
        code = int(round(v / FSR_V * (1 << 23)))
        self.code = max(-(1 << 23), min((1 << 23) - 1, code)) & 0xFFFFFF
        self.ready = True

    def on_write(self, data):
        data = bytes(data)
        if not data:
            return
        cmd = data[0]
        if cmd & 0xC0 == 0x80:                                  # register writes, in pairs
            for i in range(0, len(data) - 1, 2):
                reg, value = data[i] & 0x0F, data[i + 1]
                if reg != REG_DEVICE_ID:
                    self.regs[reg] = value
                if reg == REG_CONVERSION_CTRL and value & START:
                    self._convert()
        elif cmd & 0xC0 == 0x40:                                # register read
            self.out = bytes([self.regs[cmd & 0x0F]])
        elif cmd == 0x00:                                       # conversion data
            status = 0x01 if self.ready else 0x00
            self.out = bytes([status, 0x00, self.code >> 16 & 0xFF, self.code >> 8 & 0xFF, self.code & 0xFF])

    def on_read(self, count):
        out, self.out = self.out[:count], self.out[count:]
        return out + bytes(count - len(out))
