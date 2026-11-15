# The car on the telemetry dashboard

Midnight Sun's firmware runs on pyrite's simulated STM32s, and Midnight Sun's own telemetry
dashboard ([fwxvi_telemetry_client](https://github.com/uw-midsun/fwxvi_telemetry_client)) shows it live.

![Dashboard tab](screenshots/02-dashboard.png)
![Cells tab](screenshots/03-cells.png)
![Signal table](screenshots/01-signal-table.png)

## What runs

| Part | What it is |
| --- | --- |
| rear_controller (BMS) | real firmware, simulated STM32L496RG |
| front_controller | real firmware, simulated STM32L433CC |
| telemetry | real firmware, simulated STM32L433CC |
| `adbms1818.py` | 2 daisy-chained ADBMS1818 AFEs on SPI2, 36 cells; cell 3 of AFE 1 at 3.95 V and cell 10 of AFE 2 at 3.98 V, the rest at 3.90 V |
| `steering_peer.py` | stand-in for the steering board (STM32L4P5, not simulated yet); sends `steering` with balancing enabled |
| `ws22_motor_controller.py` | WaveSculptor 22 motor controller; status frames every 100 ms, 1200 rpm |
| `xbee_bridge.py` | stand-in for the telemetry board's XBee forwarding (see below) |

All three boards and the peers share one CAN bus. The dashboard decodes every datagram with the
fwxvi CAN definitions: 137 signals, none unmatched.

## What the screenshots show

- **Dashboard:** WS22 at 1200 rpm and 124.4 km/h, pack at 142.24 V and -201 A, 75.46 % state of charge.
- **Cells:** the BMS firmware's readings of the simulated pack. Cell 28 (AFE 2 cell 10) is the high
  cell it is bleeding. The others read 3.945 V: 3.90 V plus the firmware's own
  `ADBMS1818_ADC_DC_OFFSET_10UV`.
- Files 06 to 08 are the same tabs about 60 s later. Values move between the two passes.

## Stand-ins and known gaps

- **XBee:** `projects/telemetry/src/main.c:132` has `xb_transmit_init` commented out, so the stock
  telemetry image sends nothing over XBee. With that line restored it still sent no bytes in a 20 s
  run, which is not explained yet. `xbee_bridge.py` does what `xb_transmit.c` does: it forwards CAN
  frames in the `datagram.h` framing (0xAA, ID big-endian, DLC, data, 0xBB) and re-encodes WS22
  frames into IDs 2039 to 2043 once a second.
- **Drive command is 0:** with no pedal calibration in flash, `brake_pedal.c` computes 0/0 and the
  filter holds NaN (`front_controller.c:79` ignores the `pedal_calib_read` return value).
- **Motor temperature reads -25.5 C:** the dashboard's `postprocess.yaml` negates that field.
- **PCS/Aux currents read 53036 mA:** not looked into.

## Run it

1. Build the three projects (`scons --project=rear_controller` with its STM32L496 preset;
   `front_controller` and `telemetry` with the default L433 preset).
2. Build the dashboard with `telemetry_client-pty.patch` applied (made against upstream
   a431966d). The patch lets it open a pty on macOS, where the serial library fails with "Not a
   typewriter", connect on start (`TELEMETRY_AUTOCONNECT`), and save screenshots of its own window
   (`TELEMETRY_SHOT_DIR`).
3. From the repository root:

```
SIM=/path/to/pyrite/sim DASH=/path/to/fwxvi_telemetry_client sim/dashboard/run.sh 600
```

The simulator is pyrite (Simantic). A `sim` build with the STM32L496 die is needed.

## All four controllers, steering display included

The steering board (STM32L4P5VE) now runs its own firmware too, and its LTDC display is written to PNG
files. With the BMS, front_controller and telemetry on the same CAN bus, the screen shows the car's
live values: pack voltage and current, state of charge, the BMS's min and max cell voltage, motor
speed and temperature.

![Steering display](screenshots/09-steering-display.png)

```
git apply sim/dashboard/steering-persistence-off.patch   # see below
scons --platform=arm --project=steering                   # its own STM32L4P5 preset
SIM=/path/to/pyrite/sim sim/dashboard/run.sh 600              # add DASH=... for the telemetry dashboard too
```

`run.sh` runs all four controllers (`CAR=3` for the three-board car) and serves the steering display at
http://localhost:8765/ (`display_view.py`, standard library only). On an Apple M5 laptop the car
runs about 1.9x slower than real time with a current pyrite: 20 virtual seconds in about 37 s.

`--display-dir` writes one PNG each time the screen's content changes. The pixel clock is taken from
the firmware's own PLLSAI2 setup (HSI16 / 4 x 72 / 8 / 4 = 9 MHz), so frames come at the panel's
real rate. The real steering board replaces `steering_peer.py` here, so cell balancing now waits for
its balancing button instead of being on from the start.

**Why the patch.** `libraries/ms-common/inc/flash.h` defines the L433 flash layout for every chip
(2 KB pages, 128 pages). The steering image is 392 KB, so `persist_init`'s "last page" (127, at
0x0803F800) is inside the firmware's own code. It reads code, never finds a valid marker, and erases
page 127, which on the L4P5 (4 KB pages, 64 per bank on a 512 KB part) is not that address. In the
sim it retries for ever and the display never comes up. The patch sets `INCLUDE_PERSISTENCE 0` in
`display.c` so the rest of the firmware can run; the proper fix is a per-chip page size and page
count in `flash.h`, with the persistence page in bank 2.

Needs a pyrite `sim` newer than 0.9.1: 0.9.1 refuses the STM32L4P5, and also the STM32L496 (an
unread `can2` attribute).
