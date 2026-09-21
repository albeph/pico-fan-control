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


## Operating Curve

| Internal fan RPM | External fan duty |
|---|---|
| > 4000 RPM | **100%** (maximum speed) |
| 2500 – 4000 RPM | **50%** (medium speed) |
| < 2500 RPM | **0%** (off) |

Thresholds are configurable in `/etc/pico-fan/config.json`.

---

## Configuration

File: `/etc/pico-fan/config.json`

```json
{
  "pico_serial_by_id":  "/dev/serial/by-id/usb-MicroPython_Board_...",
  "ibm_fan_path":       "/proc/acpi/ibm/fan",
  "rpm_threshold_high": 4000,
  "rpm_threshold_mid":  2500,
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
