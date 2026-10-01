# pico-fan-control

> **USB Fan Control via Raspberry Pi Pico / RP2040 (Userspace IPC Daemon)**

![Debian Package](https://img.shields.io/badge/Debian-Package-red?logo=debian)
![MicroPython](https://img.shields.io/badge/MicroPython-RP2040-green?logo=micropython)
[![License: GPL v2](https://img.shields.io/badge/License-GPL%20v2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)

---

## Overview

`pico-fan-control` is a complete system to control a **4-pin fan** via a **Raspberry Pi Pico (RP2040)** connected over USB, automatically synchronizing it with the system's internal fan (ThinkPad or generic hwmon).

### Key Features

| Feature | Details |
|---|---|
| **Firmware** | MicroPython on RP2040, 25 kHz PWM, interrupt tachometer IRQ |
| **Architecture** | 100% Userspace IPC Unix Socket (`/run/pico-fan.sock`), no kernel modules / zero kernel-headers |
| **Daemon** | Fault-tolerant, automatic USB reconnection, CPU < 0.1% |
| **Packaging** | Native `.deb` package for Debian / Ubuntu / Proxmox |
| **Unified CLI** | Single `pico-fan` command with subcommands (`setup`, `status`, `manual`, `version`, `daemon`) |
| **Integration** | systemd, udev, journald |

---

## Architecture

```
                    ┌──────────────────────────────────────────────────┐
                    │            LINUX HOST                            │
                    │                                                  │
  ┌──────────┐      │  ┌─────────────┐    ┌────────────────────────┐   │
  │ Internal │      │  │ fan_daemon  │───▶│ IPC Socket             │   │
  │ fan      │─────▶│  │   .py       │    │ UNIX (/run/            │   │
  │ (hwmon / │ RPM  │  │             │    │ pico-fan.sock)         │   │
  │  ACPI)   │      │  │  SET <duty> │    └───────┬────────────────┘   │
  └──────────┘      │  │  RPM query  │            │                    │
                    │  │             │            ▼                    │
  ┌──────────┐      │  └─────────────┘    ┌────────────────────────┐   │
  │ Pico     │◀─────│         │           │ pico-fan CLI           │   │
  │ RP2040   │ USB  │         ▼           │ (status / manual)      │   │
  └──────────┘ RPM  │  ┌─────────────┐    └────────────────────────┘   │
       │            │  │  journald   │                                 │
       │ PWM        │  └─────────────┘                                 │
       ▼            │                                                  │
  ┌──────────┐      └──────────────────────────────────────────────────┘
  │ External │
  │ 4-pin    │
  │ fan      │
  └──────────┘
```

---

## Hardware Requirements

### Raspberry Pi Pico / RP2040
- Any RP2040-based board with USB CDC
- MicroPython >= 1.20 installed
- USB-A ↔ micro-USB cable (or USB-C depending on board model)

> ℹ️ Fully tested and working on Raspberry Pi Pico 2W as well

### Fan
- Standard **4-pin** fan (12V or 5V)
- Connector: +V, GND, TACH (signal), PWM (control)

### Hardware Pinout

```
Fan (4 pins)             Raspberry Pi Pico
─────────────────────────────────────────────
Pin 1 - GND          ──▶  GND (e.g. Pin 38)
Pin 2 - +12V/5V      ──▶  External power supply (not from the Pico!)
Pin 3 - TACH (green) ──▶  GP14 (Pin 19)
Pin 4 - PWM  (blue)  ──▶  GP15 (Pin 20)
```

> **⚠️ Warning**: Do not power a 12V fan directly from the Pico. It would run at too low a speed.
> In my use case, I connected the fan with a 12V power supply, ensuring common ground by bridging the jumper connected to the Pico's GND with the power supply's Ground.

### Wiring Diagram

```
12V Power Supply
    +12V ──────────────────────────────▶ Fan Pin 2
    GND  ──────┬──────────────────────▶ Fan Pin 1
               │
    Pico GND ──┘  (Common GND is MANDATORY)
    Pico GP15 ────(optional 1kΩ pull-up resistor)──▶ Fan Pin 4 (PWM)
    Pico GP14 ◀───(direct or with 10kΩ resistor)─── Fan Pin 3 (TACH)
```

---
## Serial Protocol

The firmware communicates over the USB CDC port at 115200 baud.

| Command | Response | Description |
|---|---|---|
| `RPM` | `RPM:2850 DUTY:50%` | Reads current RPM and duty cycle |
| `GET` | `RPM:2850 DUTY:50%` | Alias for RPM |
| `SET 75` | `OK` | Sets duty cycle to 75% |
| `75` | `OK` | Numeric alias for SET |

```bash
# Manual test
echo "RPM" | sudo tee /dev/ttyACM0
cat /dev/ttyACM0

# Or with minicom
minicom -D /dev/ttyACM0 -b 115200
```

---

## Quick Installation

### 1. Install the Debian package

```bash
# Build the package
make deb

# Install
sudo dpkg -i pico-fan_1.0.0_all.deb

# Resolve any missing dependencies
sudo apt -f install
```

### 2. Flash firmware onto Pico

```bash
# Using mpremote (install: pip install mpremote)
mpremote connect /dev/ttyACM0 cp firmware/main.py :main.py

# Or using Thonny IDE (graphical tool)

# Or using VS Code + Raspberry Pi Pico extension (graphical tool)
```

### 3. Run the configuration wizard

```bash
sudo pico-fan setup
```

The wizard will guide you through:
- ✅ Automatic Pico detection in `/dev/serial/by-id/`
- ✅ Fan testing (25% → 50% → 100% → 0%)
- ✅ Automatic search and detection of the **optimal duty cycle** for maximum speed
- ✅ Selection of the internal fan to monitor
- ✅ RPM threshold configuration
- ✅ Saving to `/etc/pico-fan/config.json`

Once the wizard completes, the service is automatically started and enabled.

---

## CLI Interface `pico-fan`

All commands are centralized within the single `pico-fan` executable:

```bash
# Show available commands help
pico-fan

# Run configuration wizard (requires root)
sudo pico-fan setup

# Instant diagnostics: internal RPM, Pico RPM, duty %, serial port
pico-fan status

# Temporary manual control (e.g. set fan to 75% and monitor RPM; Ctrl+C restores automatic control)
pico-fan manual 75

# Display installed version
pico-fan version
```


## Operating Curves & Control Modes

`pico-fan-control` supports two input control sources (`control_source`): **RPM** (synchronizing with the internal fan) and **Temperature** (monitoring CPU/package sensors via hwmon).

### 1. RPM Mode (`control_source: "rpm"`)

The external fan follows the internal fan speed directly:

| Internal fan RPM | External fan duty |
|---|---|
| > 4000 RPM | **100%** (maximum speed) |
| 2500 – 4000 RPM | **50%** (medium speed) |
| < 2500 RPM | **0%** (off) |

In RPM mode, speed changes are applied immediately to mirror internal cooling hardware.

---

### 2. Temperature Mode & Fan Stabilization (`control_source: "temp"`)

| Temperature | External fan duty |
|---|---|
| > 80°C | **100%** (duty_high) |
| 60°C – 80°C | **50%** (duty_mid) |
| < 60°C | **0%** (duty_low) |

#### The "Fan Hunting" Problem & Anti-Hunting Solution
Modern multi-core processors frequently enter brief Turbo Boost states (lasting fractions of a second up to a few seconds) for simple tasks like opening an application or compiling code. This causes sudden CPU core temperature spikes of 20°C–30°C that dissipate almost immediately.

Without stabilization, raw temperature control causes the fan to screech up to 100% for a fraction of a second, abruptly cut down to 0% or 50%, and surge again shortly after (*fan hunting / sawtooth jitter*).

To solve this, `pico-fan-control` implements a **3-tier asymmetric stabilization strategy**:

1. **Fast Attack (Immediate Acceleration)**:
   - When temperature rises and requires a higher duty cycle (e.g. 0% → 50% or 50% → 100%), the fan reacts **immediately** without delay. Hardware safety and thermal protection are always prioritized.
2. **Phase 1: Step-Down Hold Timer (`step_down_hold_seconds: 10.0`)**:
   - When temperature drops and requests a lower duty cycle, the fan maintains its current higher speed for a configurable hold window (**10 seconds** by default).
   - If a new temperature spike occurs during this hold window, the hold is aborted and the fan stays at the high speed continuously, avoiding the annoying "rev-up → cut-off → rev-up" cycle.
3. **Phase 2: Gradual Ramp-Down (`ramp_down_step: 10`)**:
   - If temperature stays low for the entire 10 seconds, the fan does not drop abruptly. Instead, it smoothly decrements by 10% on each polling cycle until reaching the lower target step.
   - If temperature rises at any moment during the ramp-down, the ramp is interrupted and the fan immediately accelerates.
4. **Thermal Hysteresis (`temp_hysteresis: 3` °C)**:
   - A 3°C deadband prevents continuous toggling around threshold borders (e.g. at 79.9°C vs 80.1°C). Once 100% is reached (> 80°C), temperature must drop below 77°C (80 - 3) before a step-down is even initiated.

> ℹ️ **Setup configuration**: During `sudo pico-fan setup`, the wizard asks if you want to enable this anti-hunting stabilization. You can also tune or disable it directly in `/etc/pico-fan/config.json` by setting `"step_down_hold_seconds": 0` and `"ramp_down_step": 100`.

---

## Configuration

File: `/etc/pico-fan/config.json`

```json
{
  "pico_serial_by_id":  "/dev/serial/by-id/usb-MicroPython_Board_...",
  "control_source":     "temp",
  "hwmon_temp_path":    "",
  "temp_threshold_high": 80,
  "temp_threshold_mid":  60,
  "temp_hysteresis":     3,
  "step_down_hold_seconds": 10.0,
  "ramp_down_step":      10,
  "duty_high":          100,
  "duty_mid":           50,
  "duty_low":           0,
  "poll_interval":      2.0,
  "reconnect_interval": 5.0
}
```

---

## Development and Testing

```bash
# Full test suite (without hardware)
make test

# Quick test (Python and Bash syntax only)
make test-quick

# Test with Pico connected
make test-hw

# Build .deb package
make deb

# Clean temporary build files
make clean
```

---

## Uninstallation

```bash
# Remove package (preserves /etc/pico-fan/config.json)
sudo apt remove pico-fan

# Full removal including configuration
sudo apt purge pico-fan
```

---

## Troubleshooting

### Check if the Pico is detected
```bash
ls /dev/serial/by-id/
lsusb | grep -i "2e8a"
dmesg | tail -20 | grep -i "usb\|cdc\|acm"
```

### Daemon fails to start
Check the systemd service status:
```bash
sudo systemctl status pico-fan
journalctl -u pico-fan -n 50 --no-pager
```
*If configuration file `/etc/pico-fan/config.json` is missing, run setup first:*
```bash
sudo pico-fan setup
```

### The `pico-fan status` or `manual` command reports "connection refused / socket not found"
Ensure the daemon is active:
```bash
sudo systemctl status pico-fan
ls -l /run/pico-fan.sock
```

---

## License

GPL v2 — See [LICENSE](LICENSE) for details.
