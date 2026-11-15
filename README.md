## This fork: the whole car in a simulator

This is Simantic's fork of Midnight Sun's firmware. It runs the car's real
firmware, unmodified apart from one line, on simulated hardware: no boards, no bench.

![Steering display, simulated](sim/dashboard/screenshots/09-steering-display.png)

**What runs:** four controllers on one simulated CAN bus, each on its own simulated STM32.

| Board | MCU | Firmware |
| --- | --- | --- |
| Rear controller (BMS) | STM32L496 | `projects/rear_controller` |
| Front controller | STM32L433 | `projects/front_controller` |
| Telemetry | STM32L433 | `projects/telemetry` |
| Steering, with its LTDC display | STM32L4P5 | `projects/steering` |

The parts around them are Python models in `sim/dashboard/`:
- **Cells:** the ADBMS1818 cell monitor (`adbms1818.py`).
- **Pack current:** the ADS122C14 current-sense ADC (`ads122c14.py`).
- **Motor controller:** the WS22 (`ws22_motor_controller.py`).
- **Radio:** the XBee link (`xbee_bridge.py`), which can feed Midnight Sun's own telemetry dashboard.
- **On the boards:** the relay sense lines, the AUX power input, and telemetry's SD card.

All of them follow one drive scenario (`sim/dashboard/drive.csv`): park, accelerate to 60 km/h,
cruise, regen-brake, stop, every 100 s. Speed, pack and motor current, pack and cell voltage, and
state of charge therefore agree on the steering display.

**Replay your own drives:** `sim/dashboard/sd_to_drive.py` turns a log from the telemetry board's SD
card into that scenario, so the firmware re-drives a real run on the simulated boards:

```
python3 sim/dashboard/sd_to_drive.py /Volumes/SDCARD > sim/dashboard/drive.csv
```

**Run it** (needs `scons`, the Arm GNU toolchain, and Simantic's `sim` on PATH):

```
pip install scons -r requirements.txt
for p in rear_controller front_controller telemetry steering; do scons --platform=arm --project=$p; done
sim/dashboard/run.sh 600      # opens the steering display at http://localhost:8765/
```

The one change to the firmware: persistence is off on the steering board
(`INCLUDE_PERSISTENCE 0` in `projects/steering/src/display.c`). `libraries/ms-common/inc/flash.h`
gives every chip the STM32L433's flash layout, which doesn't fit the L4P5.
[`sim/dashboard/README.md`](sim/dashboard/README.md) has the details, the three-board variant and
how to attach the telemetry dashboard.

Everything below is Midnight Sun's README.

---

<img src=doxygen/banner.png width=90%></br>
## Midnight Sun XVI Firmware
This repository contains all firmware for the [University of Waterloo](https://uwaterloo.ca/)'s [Midnight Sun Solar Rayce Car](http://www.uwmidsun.com/) team's car #24.

## Projects:
- Battery Management System (BMS)
- Power Distribution (PD)
- Centre Console (CC)
- Motor Controller Interface (MCI)
- Telemetry (TEL)
- Flash-over-CAN (BOOTLOADER)
- UART Controller (UART CLI)
- IMU Board
- CAN Autogen
- MPXE (Multi-Project x86 Emulation)

## Getting Started

To get started with the firmware, please refer to the [installation guide](https://uwmidsun.atlassian.net/wiki/spaces/Firmware/pages/60260353/Setup) for instructions on setting up the development environment and flashing the firmware onto the vehicle's embedded systems.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.

