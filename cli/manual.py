#!/usr/bin/env python3
"""
manual.py - pico-fan manual <percentage>
=========================================
Manually sets the external fan speed to a fixed percentage, displaying
RPM in real-time until interrupted (Ctrl+C).
Automatic daemon control is suspended for the duration and restored
automatically upon exit.
"""

from __future__ import annotations

import signal
import sys
import time
from ANSI_colors import BOLD, CYAN, DIM, GREEN, RED, RESET, WHITE, YELLOW, cprint
from ipc_adapter import IpcAdapter, SOCK_PATH

REFRESH_SEC = 1.0   # RPM refresh interval in seconds

ipc = IpcAdapter()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # -----------------------------------------------------------------------
    # Argument parsing
    # -----------------------------------------------------------------------
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        cprint(
            "Uso:  pico-fan manual <percentuale>\n"
            "\n"
            "Imposta la ventola esterna a una velocità fissa (0-100%) e\n"
            "mostra gli RPM in tempo reale. Premi Ctrl+C per\n"
            "ripristinare il controllo automatico.\n"
            "\n"
            "Esempi:\n"
            "  pico-fan manual 75    # ventola al 75%\n"
            "  pico-fan manual 0     # ventola al minimo\n"
            "  pico-fan manual 100   # ventola al massimo\n",
            BOLD,
        )
        sys.exit(0)

    try:
        duty = int(sys.argv[1])
        if not 0 <= duty <= 100:
            raise ValueError
    except ValueError:
        cprint(f"Errore: percentuale non valida '{sys.argv[1]}' (deve essere 0-100).", RED)
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Check that daemon is listening
    # -----------------------------------------------------------------------
    state = ipc.get_status()
    if state is None:
        cprint(
            f"Errore: socket {SOCK_PATH} non trovato.\n"
            "Il demone è in esecuzione? Controlla con: systemctl status pico-fan",
            RED,
        )
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Activate manual mode
    # -----------------------------------------------------------------------
    if not ipc.set_manual_duty(duty):
        cprint("Errore: impossibile impostare il duty cycle. Il demone ha risposto in modo inatteso.", RED)
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Handler Ctrl+C / SIGTERM -> restore automatic control
    # -----------------------------------------------------------------------
    def _cleanup(sig=None, frame=None) -> None:
        # Move to new line after active carriage return \r
        print()
        cprint("\nRipristino controllo automatico...", YELLOW)
        ipc.resume()
        cprint("✓ Controllo automatico ripristinato.", GREEN)
        sys.exit(0)

    signal.signal(signal.SIGINT,  _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    # -----------------------------------------------------------------------
    # Header display
    # -----------------------------------------------------------------------
    cprint(
        f"\nModalità manuale — ventola al {duty}%\n"
        "Premi Ctrl+C per ripristinare il controllo automatico.\n",
        CYAN,
        bold=True,
    )
    print(f"  {'RPM esterna':>12}   {'RPM interna':>12}   {'Duty':>6}")
    print(f"  {'─' * 12}   {'─' * 12}   {'─' * 6}")

    # -----------------------------------------------------------------------
    # Monitoring loop
    # -----------------------------------------------------------------------
    while True:
        state = ipc.get_status()
        if state is None:
            print(f"\r  {RED}Connessione al demone persa.{RESET}                          ", end="", flush=True)
        else:
            pico_rpm     = state.get("pico_rpm",     0)
            internal_rpm = state.get("internal_rpm", 0)
            current_duty = state.get("current_duty", duty)
            print(
                f"\r  {GREEN}{pico_rpm:>9} RPM{RESET}   "
                f"{internal_rpm:>9} RPM   "
                f"{BOLD}{current_duty:>5}%{RESET}   ",
                end="",
                flush=True,
            )
        time.sleep(REFRESH_SEC)


if __name__ == "__main__":
    main()
