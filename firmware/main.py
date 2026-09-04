"""
pico-fan-control - Firmware MicroPython per Raspberry Pi Pico / RP2040
=======================================================================
Autore:   pico-fan-control project
Versione: 1.0.0

Pinout:
  GP15 -> Segnale PWM verso ventola (4 pin, connettore blu)
  GP14 -> Segnale TACH dalla ventola (connettore verde, PULL_UP interno)

Protocollo seriale CDC (115200 baud, line-terminated con \n):
  Comandi IN:
    SET <0-100>   -> Imposta duty cycle percentuale (es. "SET 75")
    <numero>      -> Alias per SET (es. "50")
    RPM           -> Richiede stato corrente
    GET           -> Alias per RPM
  Risposte OUT:
    RPM:<valore> DUTY:<valore>%
    ERR:<messaggio>
    OK
"""

import machine
import utime
import sys
import select

# ---------------------------------------------------------------------------
# Costanti Hardware
# ---------------------------------------------------------------------------
PWM_PIN       = 15          # GP15 - uscita PWM verso la ventola
TACH_PIN      = 14          # GP14 - ingresso tachimetro dalla ventola
PWM_FREQ_HZ   = 25_000     # Frequenza PWM standard ventole PC: 25 kHz
TACH_PULSES_PER_REV = 2    # La maggior parte delle ventole PC: 2 impulsi/giro
RPM_INTERVAL_MS     = 1000  # Finestra di calcolo RPM: 1 secondo

# ---------------------------------------------------------------------------
# Variabili globali condivise (accesso da IRQ e loop principale)
# ---------------------------------------------------------------------------
_pulse_count: int = 0
_rpm: int = 0
_duty_percent: int = 0      # 0..100

# ---------------------------------------------------------------------------
# Setup PWM
# ---------------------------------------------------------------------------
_pwm_pin_obj = machine.Pin(PWM_PIN, machine.Pin.OUT)
_pwm = machine.PWM(_pwm_pin_obj)
_pwm.freq(PWM_FREQ_HZ)
_pwm.duty_u16(0)            # Parte a ventola spenta


def _duty_percent_to_u16(percent: int) -> int:
    """Converte duty cycle 0..100 in valore u16 0..65535."""
    percent = max(0, min(100, percent))
    return int(percent * 65535 / 100)


def set_duty(percent: int) -> None:
    """Imposta il duty cycle della ventola (0-100%)."""
    global _duty_percent
    _duty_percent = max(0, min(100, percent))
    _pwm.duty_u16(_duty_percent_to_u16(_duty_percent))


# ---------------------------------------------------------------------------
# Setup TACH (ingresso IRQ)
# ---------------------------------------------------------------------------
_tach_pin = machine.Pin(TACH_PIN, machine.Pin.IN, machine.Pin.PULL_UP)


def _tach_irq_handler(pin) -> None:
    """ISR: incrementa contatore impulsi. Chiamata su fronte di discesa."""
    global _pulse_count
    _pulse_count += 1


_tach_pin.irq(trigger=machine.Pin.IRQ_FALLING, handler=_tach_irq_handler)


# ---------------------------------------------------------------------------
# Timer per calcolo RPM
# ---------------------------------------------------------------------------
def _rpm_timer_callback(timer) -> None:
    """Callback del Timer hardware: calcola RPM e azzera contatore."""
    global _pulse_count, _rpm
    # Legge e azzera atomicamente il contatore impulsi
    pulses = _pulse_count
    _pulse_count = 0
    # RPM = (impulsi / impulsi_per_giro) * (60000 / intervallo_ms)
    _rpm = int((pulses / TACH_PULSES_PER_REV) * (60_000 / RPM_INTERVAL_MS))


_rpm_timer = machine.Timer()
_rpm_timer.init(
    period=RPM_INTERVAL_MS,
    mode=machine.Timer.PERIODIC,
    callback=_rpm_timer_callback,
)


# ---------------------------------------------------------------------------
# Seriale CDC non bloccante tramite select.poll
# ---------------------------------------------------------------------------
_poll = select.poll()
_poll.register(sys.stdin, select.POLLIN)


def _uart_readline_nonblocking() -> str | None:
    """
    Legge una riga da stdin senza bloccare.
    Restituisce la stringa (senza \\n) se disponibile, altrimenti None.
    """
    events = _poll.poll(0)      # timeout=0 -> non bloccante
    if not events:
        return None
    raw = sys.stdin.readline()
    return raw.strip() if raw else None


def _send(msg: str) -> None:
    """Invia una riga di risposta sulla porta seriale."""
    sys.stdout.write(msg + "\n")


# ---------------------------------------------------------------------------
# Parser comandi
# ---------------------------------------------------------------------------
def _process_command(cmd: str) -> None:
    """Interpreta e gestisce un singolo comando ricevuto via seriale."""
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

    # Compatibilità: solo numero
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
# Loop principale
# ---------------------------------------------------------------------------
def main() -> None:
    """Entry point: loop non bloccante di polling seriale."""
    _send("PICO-FAN-CONTROL READY")
    _send(f"PWM:{PWM_FREQ_HZ}Hz PIN_PWM:GP{PWM_PIN} PIN_TACH:GP{TACH_PIN}")

    while True:
        try:
            line = _uart_readline_nonblocking()
            if line:
                _process_command(line)
            utime.sleep_ms(10)
        except KeyboardInterrupt:
            # Previene l'uscita nella REPL se arriva Ctrl+C sulla seriale
            continue
        except Exception:
            utime.sleep_ms(20)


if __name__ == "__main__":
    main()
