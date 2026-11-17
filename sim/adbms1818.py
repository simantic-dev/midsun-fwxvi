# ADBMS1818 battery-cell monitor daisy chain on one SPI bus, as a scripted SPI
# peer. One peer models the whole chain: the MCU sees one chip select and one
# byte stream, and the devices are numbered 0..N-1 in the order the chain
# delivers them.
#
# Wiring: chip select is the peer's CS, wired to on_select / on_deselect by the
# scripted SPI host. Frames are delimited by CS, never by byte counts, so the
# driver's wakeup pulses (CS low/high with no bytes) are empty frames.
#
# Config (ctx.config, JSON), all optional. NOTE: pyrite's SPI.ScriptedSpiSlave
# arm does not pass `config:` to the script (only Scripted.ScriptedGpioPeer does),
# so with a board file these keys are ignored and the defaults below apply.
#   num_devices        chain length, default 2
#   cell_v             default cell voltage in volts, default 3.90
#   cell_overrides     {"dev:cell": volts}, merged onto the defaults
#                      (defaults: dev0 cell3 3.95 V, dev1 cell10 3.98 V, so balancing triggers)
#   aux_v              GPIO/thermistor input voltage in volts, default 1.5
#   discharge_mv_per_s drop rate of a discharging cell, default 1.0 mV/s (below the firmware's 10 mV deadband per 4.4 s window)
#   summary_every      print a pack summary every N ADCV conversions, default 2
#
# Protocol: the driver's framing (ms-drivers adbms_afe.c, adbms_afe_crc15.c)
# and CRC15 (seed 16, result shifted left one bit). The ADBMS1818 datasheet is
# not in this repo, so the datasheet section numbers are not cited here:
#   command: CMD0, CMD1, PEC0, PEC1 (PEC over the two command bytes).
#   write (WRCFGA/WRCFGB, WRPWM, WRPSB): then per device, in chain order, 6 data
#     bytes and a 2-byte PEC. The first packet goes to the device farthest from
#     the MCU; the chain shifts it down.
#   read (RDCVx, RDAUXx, RDCFGx): after the four command bytes the chain returns
#     per device, nearest the MCU first, 6 data bytes and a 2-byte PEC.
#   Device index 0 here is the device nearest the MCU: the first block read is
#     index 0, the first packet written is index N-1. This is the LTC681x/ADBMS181x
#     daisy-chain order (ADI's LTC681x library writes ic[N-1] first and parses
#     ic[0] first); Midnight Sun's adbms_afe_toggle_cell_discharge relies on it
#     by swapping device indices on write.
#
# UNVERIFIED against silicon or a cited datasheet section; confirm before a
# silicon comparison.
#
# Register layout (config bytes are stored raw, so readback is exact):
#   CFGRA byte 4 = DCC cells 1-8 (bit 0 = cell 0 here), byte 5 low nibble = DCC
#   cells 9-12. CFGRB byte 0 high nibble = DCC cells 13-16, byte 1 low 3 bits =
#   cells 17-18 (bit 0 = cell 12 here).
#
# Cell voltages are 16-bit, 100 uV per LSB, little-endian on the wire. Aux
# inputs return the same value for every input (no mux or GPIO conversion).
#
# MODELED SIMPLIFICATIONS
#   - DCP (discharge permitted during conversion) is ignored: a DCC bit always
#     discharges, though the driver sends DCP=0.
#   - ADCV, ADAX and the PWM writes are accepted; ADCV only advances the summary
#     count. WRPWM/WRPSB data is consumed and discarded.
#   - Cell readings are the modelled voltage, quantized to 100 uV. No noise or
#     ADC error.
#   - Discharge is a linear ramp (mV/s) on any cell with its DCC bit set. Real
#     cells discharge through a resistor with a temperature-dependent rate.
#   - The config registers power up as zero, with no reset-to-defaults.
CMD_SIZE = 4
PEC_SIZE = 2
CELLS_PER_DEVICE = 18
GROUP_BYTES = 6
PACKET_BYTES = GROUP_BYTES + PEC_SIZE
LSB_V = 100e-6                 # 100 uV per cell-voltage LSB

# Command words, 11 bits (the driver's ADBMS1818_*_RESERVED values).
WRCFGA, WRCFGB = 0x001, 0x024
RDCFGA, RDCFGB = 0x002, 0x026
RDCV = {0x004: 0, 0x006: 1, 0x008: 2, 0x00A: 3, 0x009: 4, 0x00B: 5}   # group A..F
RDAUX = {0x00C, 0x00E, 0x00D, 0x00F}                                   # group A..D
ADCV_BITS, ADAX_BITS = 0x260, 0x460   # MD (bits 8:7) and CH/DCP bits are masked out
ADCV_MASK = 0x660                     # bits 10, 9, 6, 5 identify ADCV/ADAX
WRPWM, WRPSB = 0x020, 0x03C           # accepted, data discarded

CRC15_POLYNOMIAL = 0x4599


def _build_crc15_table():
    table = []
    for i in range(256):
        remainder = i << 7
        for _ in range(8):
            if remainder & 0x4000:
                remainder = (remainder << 1) ^ CRC15_POLYNOMIAL
            else:
                remainder <<= 1
        table.append(remainder & 0xFFFF)
    return table


CRC15_TABLE = _build_crc15_table()


def pec15(data):
    """CRC15 as adbms_afe_crc15.c computes it: seed 16, result << 1."""
    remainder = 16
    for byte in data:
        addr = ((remainder >> 7) ^ byte) & 0xFF
        remainder = ((remainder << 8) ^ CRC15_TABLE[addr]) & 0xFFFF
    return (remainder << 1) & 0xFFFF


def _packet(group):
    crc = pec15(group)
    return list(group) + [crc >> 8, crc & 0xFF]


def _dcc_a(a):
    return a[4] | ((a[5] & 0x0F) << 8)


def _dcc_b(b):
    return (b[0] >> 4) | ((b[1] & 0x07) << 4)


class Slave:
    def __init__(self, ctx):
        self.ctx = ctx
        cfg = getattr(ctx, "config", None) or {}
        self.num_devices = int(cfg.get("num_devices", 2))
        self.aux_v = float(cfg.get("aux_v", 1.5))
        self.rate_v_per_s = float(cfg.get("discharge_mv_per_s", 1.0)) / 1000.0
        self.summary_every = int(cfg.get("summary_every", 2))
        self.bal_seen = set()  # cells discharged since the last summary (log only)
        cell_v = float(cfg.get("cell_v", 3.90))
        self.volts = [[cell_v] * CELLS_PER_DEVICE for _ in range(self.num_devices)]
        overrides = {"0:3": 3.95, "1:10": 3.98}
        overrides.update(cfg.get("cell_overrides", {}))
        for key, v in overrides.items():
            dev, cell = (int(x) for x in key.split(":"))
            if 0 <= dev < self.num_devices and 0 <= cell < CELLS_PER_DEVICE:
                self.volts[dev][cell] = float(v)
        self.cfg_a = [bytearray(GROUP_BYTES) for _ in range(self.num_devices)]
        self.cfg_b = [bytearray(GROUP_BYTES) for _ in range(self.num_devices)]
        self.t_last = ctx.now_us
        self.conversions = 0
        self._reset_frame()

    # -- frame --------------------------------------------------------------

    def _reset_frame(self):
        self.cmd = []
        self.command = None
        self.out = []
        self.write_buf = []
        self.writing = False
        self._packet_index = 0

    def on_select(self):
        self._reset_frame()
        self._advance()

    def on_deselect(self):
        self._reset_frame()

    on_finish = on_deselect

    def on_transmit(self, b):
        if len(self.cmd) < CMD_SIZE:
            self.cmd.append(b)
            if len(self.cmd) == CMD_SIZE:
                self._command()
            return 0
        idx = len(self.cmd) - CMD_SIZE
        self.cmd.append(b)
        if self.out:
            return self.out[idx] if idx < len(self.out) else 0
        if self.writing:
            self.write_buf.append(b)
            if len(self.write_buf) == PACKET_BYTES:
                self._write_packet(self.write_buf)
                self.write_buf = []
        return 0

    def _command(self):
        cmd = self.cmd
        if pec15(cmd[:2]) != (cmd[2] << 8) | cmd[3]:
            self.command = None   # bad command PEC: the frame is ignored
            return
        word = (cmd[0] << 8) | cmd[1]
        self.command = word
        self._advance()
        if word == WRCFGA or word == WRCFGB or word in (WRPWM, WRPSB):
            self.writing = True
            self._packet_index = 0
        elif word in RDCV:
            self.out = self._read_voltages(RDCV[word])
        elif word in RDAUX:
            self.out = self._read_aux()
        elif word == RDCFGA:
            self.out = self._read_cfg(self.cfg_a)
        elif word == RDCFGB:
            self.out = self._read_cfg(self.cfg_b)
        elif (word & ADCV_MASK) == ADCV_BITS:
            self._conversion()
        elif (word & ADCV_MASK) == ADAX_BITS:
            pass                  # aux conversion: values are constant here

    # -- writes -------------------------------------------------------------

    def _write_packet(self, packet):
        # The chain shifts every packet, so a bad one still uses its device slot.
        index = self._packet_index
        self._packet_index += 1
        group = packet[:GROUP_BYTES]
        if pec15(group) != (packet[6] << 8) | packet[7]:
            self.ctx.warning("adbms1818: bad data PEC, packet ignored")
            return
        if index >= self.num_devices:
            return
        index = self.num_devices - 1 - index  # first packet written lands in the farthest device
        if self.command == WRCFGA:
            self._apply_cfg_a(index, group)
        elif self.command == WRCFGB:
            self._apply_cfg_b(index, group)

    def _apply_cfg_a(self, dev, group):
        before = _dcc_a(self.cfg_a[dev])
        self.cfg_a[dev][:] = group
        self._log_dcc(dev, before, _dcc_a(group), 0)

    def _apply_cfg_b(self, dev, group):
        before = _dcc_b(self.cfg_b[dev])
        self.cfg_b[dev][:] = group
        self._log_dcc(dev, before, _dcc_b(group), 12)

    def _log_dcc(self, dev, before, after, first_cell):
        changed = before ^ after
        for bit in range(CELLS_PER_DEVICE):
            if not changed & (1 << bit) or bit + first_cell >= CELLS_PER_DEVICE:
                continue
            cell = bit + first_cell
            state = "ON" if after & (1 << bit) else "OFF"
            self.ctx.info(f"adbms1818: dev{dev} cell{cell} balance {state} ({self.volts[dev][cell]:.3f}V)")

    # -- reads --------------------------------------------------------------

    def _read_voltages(self, group):
        self._advance()
        out = []
        for dev in range(self.num_devices):
            group_bytes = []
            for cell in range(group * 3, group * 3 + 3):
                raw = max(0, min(0xFFFF, round(self.volts[dev][cell] / LSB_V)))
                group_bytes += [raw & 0xFF, raw >> 8]
            out += _packet(group_bytes)
        return out

    def _read_aux(self):
        raw = max(0, min(0xFFFF, round(self.aux_v / LSB_V)))
        group_bytes = [raw & 0xFF, raw >> 8] * 3
        out = []
        for _ in range(self.num_devices):
            out += _packet(group_bytes)
        return out

    def _read_cfg(self, regs):
        out = []
        for dev in range(self.num_devices):
            out += _packet(regs[dev])
        return out

    # -- time and conversions -----------------------------------------------

    def _advance(self):
        now = self.ctx.now_us
        dt_s = (now - self.t_last) / 1e6
        self.t_last = now
        if dt_s <= 0:
            return
        drop = self.rate_v_per_s * dt_s
        for dev in range(self.num_devices):
            mask = _dcc_a(self.cfg_a[dev]) | (_dcc_b(self.cfg_b[dev]) << 12)
            for cell in range(CELLS_PER_DEVICE):
                if mask & (1 << cell):
                    self.volts[dev][cell] = max(0.0, self.volts[dev][cell] - drop)
                    self.bal_seen.add((dev, cell))

    def _conversion(self):
        self.conversions += 1
        if self.summary_every > 0 and self.conversions % self.summary_every == 0:
            flat = [v for dev in self.volts for v in dev]
            lo, hi = min(flat), max(flat)
            bal = [f"dev{d}:c{c}={self.volts[d][c]:.3f}V" for d, c in sorted(self.bal_seen)]
            self.bal_seen.clear()
            self.ctx.info(
                f"adbms1818: pack min {lo:.3f}V max {hi:.3f}V delta {round((hi - lo) * 1000)} mV "
                f"(after {self.conversions} conversions) balancing: {' '.join(bal) or 'none'}"
            )
