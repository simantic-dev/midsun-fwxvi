# BMS demo on pyrite

Runs the real `rear_controller` (BMS) firmware, built for its STM32L496 preset, on pyrite's
simulated STM32L496RG. The board around it:

- `adbms1818.py`: 2 daisy-chained ADBMS1818 AFEs on SPI2 (CS PB12), 36 cells at 3.90 V, two of
  them high (AFE1 cell 3 at 3.95 V, AFE2 cell 10 at 3.98 V). A cell with its DCC bit set
  drains at 1 mV/s.
- `steering_peer.py`: stands in for the steering board on CAN1. It sends `steering` (id 0x64)
  with `buttons.balancing_enabled` set; the firmware only balances when this bit is set.

```
SIM=/path/to/pyrite/target/release/sim sim/run.sh 120   # virtual seconds, default 120
```

What you see: the firmware reads all 36 cells every 5 s, prints MAX/MIN/UNBALANCE (units of
100 uV), and sets discharge on the high cells only. The AFE logs each `balance ON/OFF`, and
the imbalance falls from 8.0 mV to about 1 mV (inside the firmware's deadband) in about 80 s.

Firmware readings are 50 mV above the simulated cells because `cell_sense.c` adds
`ADBMS1818_ADC_DC_OFFSET_10UV` to each reading. That offset is the firmware's own
calibration.

The STM32L496 needs a pyrite `sim` newer than 0.9.1 (0.9.1 refuses it over an unread `can2`
attribute).

## Three boards on one CAN bus

```
SIM=/path/to/pyrite/target/release/sim sim/car.sh 10   # virtual seconds, default 10
```

`sim/car.yaml` adds front_controller and telemetry (both STM32L433CC, the default preset) to the BMS
setup above, all on one CAN bus. front_controller sends WaveSculptor 22 drive commands (0x501) at about
50 Hz, the motor reset (0x503) once, and its system messages. telemetry receives all traffic. With no
pedal, motor, IMU (BMI323) or SD card peers, those inputs read idle: pedals at 0, no motor replies, no IMU
data, and no card on the SD SPI bus.
