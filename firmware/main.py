"""
main.py - MicroPython Firmware for Raspberry Pi Pico / RP2040
==============================================================
Provides 25 kHz PWM fan control on GP15 and interrupt-based tachometer
pulse counting on GP14, communicating with the Linux host daemon
over USB CDC serial (115200 baud).

Pinout:
  GP15 -> PWM signal to 4-pin fan (blue wire)
  GP14 -> TACH signal from fan (green wire, internal pull-up)

CDC Serial Protocol (115200 baud, line-terminated with \\n):
  Incoming commands:
    SET <0-100>   -> Set duty cycle percentage (e.g. "SET 75")
    <number>      -> Numeric alias for SET (e.g. "50")
    RPM           -> Query current RPM and duty cycle
    GET           -> Alias for RPM
  Outgoing responses:
    RPM:<value> DUTY:<value>%
    ERR:<message>
    OK
"""

import machine
import utime
import sys
import select

# ---------------------------------------------------------------------------
# Hardware constants
# ---------------------------------------------------------------------------
PWM_PIN       = 15          # GP15 - PWM output to fan
TACH_PIN      = 14          # GP14 - tachometer input from fan
PWM_FREQ_HZ   = 25_000     # Standard PC fan PWM frequency: 25 kHz
TACH_PULSES_PER_REV = 2    # Standard PC fans produce 2 pulses per revolution
RPM_INTERVAL_MS     = 1000  # RPM calculation window: 1 second

# ---------------------------------------------------------------------------
# Shared global variables (accessed from IRQ and main loop)
# ---------------------------------------------------------------------------
_pulse_count: int = 0
_rpm: int = 0
_duty_percent: int = 0      # 0..100

# ---------------------------------------------------------------------------
# PWM setup
# ---------------------------------------------------------------------------
_pwm_pin_obj = machine.Pin(PWM_PIN, machine.Pin.OUT)
_pwm = machine.PWM(_pwm_pin_obj)
_pwm.freq(PWM_FREQ_HZ)
_pwm.duty_u16(0)            # Start with fan stopped


def _duty_percent_to_u16(percent: int) -> int:
    """Converts 0..100 percentage to 0..65535 u16 duty value."""
    percent = max(0, min(100, percent))
    return int(percent * 65535 / 100)


def set_duty(percent: int) -> None:
    """Sets fan duty cycle percentage (0-100%)."""
    global _duty_percent
    _duty_percent = max(0, min(100, percent))
    _pwm.duty_u16(_duty_percent_to_u16(_duty_percent))


# ---------------------------------------------------------------------------
# TACH setup (IRQ input)
# ---------------------------------------------------------------------------
_tach_pin = machine.Pin(TACH_PIN, machine.Pin.IN, machine.Pin.PULL_UP)


def _tach_irq_handler(pin) -> None:
    """ISR: increments pulse counter on falling edge."""
    global _pulse_count
    _pulse_count += 1


_tach_pin.irq(trigger=machine.Pin.IRQ_FALLING, handler=_tach_irq_handler)


# ---------------------------------------------------------------------------
# Hardware timer for RPM calculation
# ---------------------------------------------------------------------------
def _rpm_timer_callback(timer) -> None:
    """Hardware timer callback: calculates RPM and resets pulse counter."""
    global _pulse_count, _rpm
    # Atomically read and reset pulse counter
    pulses = _pulse_count
    _pulse_count = 0
    # RPM = (pulses / pulses_per_rev) * (60000 / interval_ms)
    _rpm = int((pulses / TACH_PULSES_PER_REV) * (60_000 / RPM_INTERVAL_MS))


_rpm_timer = machine.Timer()
_rpm_timer.init(
    period=RPM_INTERVAL_MS,
    mode=machine.Timer.PERIODIC,
    callback=_rpm_timer_callback,
)


# ---------------------------------------------------------------------------
# Non-blocking CDC serial via select.poll
# ---------------------------------------------------------------------------
_poll = select.poll()
_poll.register(sys.stdin, select.POLLIN)


def _uart_readline_nonblocking() -> str | None:
    """
    Reads a line from stdin without blocking.
    Returns stripped string (without \\n) if available, otherwise None.
    """
    events = _poll.poll(0)      # timeout=0 -> non-blocking
    if not events:
        return None
    raw = sys.stdin.readline()
    return raw.strip() if raw else None


def _send(msg: str) -> None:
    """Sends a line of response over the serial port."""
    sys.stdout.write(msg + "\n")


# ---------------------------------------------------------------------------
# Command parser
# ---------------------------------------------------------------------------
def _process_command(cmd: str) -> None:
    """Parses and executes a single command received over serial."""
    cmd = cmd.strip().upper()

    if cmd in ("RPM", "GET", "STATUS"):
        _send(f"RPM:{_rpm} DUTY:{_duty_percent}%")
        return

    if cmd.startswith("SET "):
        parts = cmd.split()
        if len(parts) == 2 and parts[1].isdigit():
            value = int(parts[1])
            if 0 <= value <= 100:
                set_duty(value)
                _send("OK")
            else:
                _send("ERR:valore fuori range (0-100)")
        else:
            _send("ERR:sintassi SET <0-100>")
        return

    # Compatibility: bare numeric input
    if cmd.isdigit():
        value = int(cmd)
        if 0 <= value <= 100:
            set_duty(value)
            _send("OK")
        else:
            _send("ERR:valore fuori range (0-100)")
        return

    _send(f"ERR:comando sconosciuto '{cmd}'")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> None:
    """Entry point: non-blocking serial polling loop."""
    _send("PICO-FAN-CONTROL READY")
    _send(f"PWM:{PWM_FREQ_HZ}Hz PIN_PWM:GP{PWM_PIN} PIN_TACH:GP{TACH_PIN}")

    while True:
        line = _uart_readline_nonblocking()
        if line:
            _process_command(line)
        # Brief pause to avoid saturating CPU
        utime.sleep_ms(10)


if __name__ == "__main__":
    main()
