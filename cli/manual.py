#!/usr/bin/env python3
"""
pico-fan manual <percentuale>
==============================
Imposta manualmente la velocità della ventola esterna a una percentuale fissa,
mostrando gli RPM in tempo reale fino a Ctrl+C.
Il controllo automatico del demone viene sospeso per tutta la durata e
ripristinato automaticamente all'uscita.
"""

from __future__ import annotations

import json
import signal
import socket
import sys
import time
from ANSI_colors import BOLD, CYAN, DIM, GREEN, RED, RESET, WHITE, YELLOW, cprint

SOCK_PATH   = "/run/pico-fan.sock"
REFRESH_SEC = 1.0   # Intervallo di aggiornamento RPM



# ---------------------------------------------------------------------------
# IPC helpers
# ---------------------------------------------------------------------------

def _ipc(command: str, timeout: float = 3.0) -> str | None:
    """Invia un comando al socket IPC del demone, restituisce la risposta grezza."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(SOCK_PATH)
            if command:
                s.sendall((command + "\n").encode("utf-8"))
            return s.recv(4096).decode("utf-8", errors="replace").strip()
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _send_set(duty: int) -> bool:
    resp = _ipc(f"SET {duty}")
    return resp == "OK"


def _send_resume() -> None:
    _ipc("RESUME")


def _get_status() -> dict | None:
    raw = _ipc("")   # nessun comando → STATUS
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # -----------------------------------------------------------------------
    # Parsing argomento
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
    # Controlla che il demone sia in ascolto
    # -----------------------------------------------------------------------
    state = _get_status()
    if state is None:
        cprint(
            f"Errore: socket {SOCK_PATH} non trovato.\n"
            "Il demone è in esecuzione? Controlla con: systemctl status pico-fan",
            RED,
        )
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Attiva la modalità manuale
    # -----------------------------------------------------------------------
    if not _send_set(duty):
        cprint("Errore: impossibile impostare il duty cycle. Il demone ha risposto in modo inatteso.", RED)
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Handler Ctrl+C / SIGTERM → ripristina controllo automatico
    # -----------------------------------------------------------------------
    def _cleanup(sig=None, frame=None) -> None:
        # Vai a capo dopo la riga \r in corso
        print()
        cprint("\nRipristino controllo automatico...", YELLOW)
        _send_resume()
        cprint("✓ Controllo automatico ripristinato.", GREEN)
        sys.exit(0)

    signal.signal(signal.SIGINT,  _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    # -----------------------------------------------------------------------
    # Header
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
    # Loop di monitoraggio
    # -----------------------------------------------------------------------
    while True:
        state = _get_status()
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
