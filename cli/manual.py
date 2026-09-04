#!/usr/bin/env python3
"""
manual.py - Impostazione manuale velocità ventola e monitoraggio RPM
===================================================================

Imposta la velocità della ventola a una percentuale fissa (0-100%)
e mostra gli RPM in tempo reale finché l'utente non preme Ctrl+C.
All'uscita, ripristina automaticamente il controllo automatico del demone.
"""

from __future__ import annotations

import os
import sys
import json
import time
import socket
import select
import signal
from pathlib import Path
from typing import Optional

# Path di libreria
SCRIPT_DIR = Path(__file__).parent.resolve()
DAEMON_DIR = SCRIPT_DIR.parent / "daemon"
sys.path.insert(0, str(DAEMON_DIR))

SOCK_PATH = "/run/pico-fan.sock"

# Colori terminale
class Col:
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RESET  = "\033[0m"


def _disable_colors():
    Col.GREEN = Col.YELLOW = Col.RED = Col.CYAN = Col.BOLD = Col.DIM = Col.RESET = ""


def _parse_duty_arg() -> int:
    """Valida e restituisce il duty cycle dagli argomenti CLI."""
    # sys.argv può essere:
    # ['pico-fan set', '75'] oppure ['manual.py', '75']
    args = [a for a in sys.argv[1:] if not a.startswith("-")]

    if not args:
        print(f"{Col.BOLD}{Col.YELLOW}Uso:{Col.RESET} pico-fan set <percentuale 0-100>")
        print(f"     pico-fan manual <percentuale 0-100>")
        print(f"\n{Col.BOLD}Esempio:{Col.RESET} pico-fan set 75")
        print("Imposta la ventola al 75% e mostra gli RPM finché non premi Ctrl+C.")
        sys.exit(1)

    try:
        val = int(args[0])
    except ValueError:
        print(f"{Col.BOLD}{Col.RED}Errore:{Col.RESET} '{args[0]}' non è un numero valido.")
        print("Specificare un valore intero compreso tra 0 e 100 (es. pico-fan set 50).")
        sys.exit(1)

    if not (0 <= val <= 100):
        print(f"{Col.BOLD}{Col.RED}Errore:{Col.RESET} La percentuale deve essere compresa tra 0 e 100.")
        sys.exit(1)

    return val


def _run_manual_via_daemon(duty: int) -> bool:
    """
    Invia il comando manuale al demone tramite socket IPC e monitora gli RPM.
    Ritorna True se eseguito con successo, False se il socket non è disponibile.
    """
    if not os.path.exists(SOCK_PATH):
        return False

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(SOCK_PATH)
    except (socket.error, OSError):
        return False

    stop_requested = False

    def _sig_handler(sig, frame):  # noqa: ARG001
        nonlocal stop_requested
        stop_requested = True

    prev_int = signal.signal(signal.SIGINT, _sig_handler)
    prev_term = signal.signal(signal.SIGTERM, _sig_handler)

    try:
        # Invia comando di impostazione manuale
        req = json.dumps({"cmd": "manual", "duty": duty}) + "\n"
        sock.sendall(req.encode("utf-8"))

        # Ricevi ACK
        ack_raw = sock.recv(1024)
        if not ack_raw:
            return False

        is_tty = sys.stdout.isatty()

        print(f"\n{Col.BOLD}{Col.CYAN}=== pico-fan-control - Controllo Manuale ({duty}%) ==={Col.RESET}")
        print(f"{Col.DIM}Premi CTRL+C in qualsiasi momento per ripristinare la modalità automatica.{Col.RESET}\n")

        sock.settimeout(1.5)

        # Loop di monitoraggio
        while not stop_requested:
            try:
                rlist, _, _ = select.select([sock], [], [], 1.0)
                if not rlist:
                    continue

                chunk = sock.recv(2048)
                if not chunk:
                    # Connessione chiusa dal server
                    break

                lines = chunk.decode("utf-8", errors="replace").strip().split("\n")
                last_line = lines[-1]
                if not last_line:
                    continue

                state = json.loads(last_line)
                pico_rpm = state.get("pico_rpm", 0)
                int_rpm  = state.get("internal_rpm", 0)
                cur_duty = state.get("current_duty", duty)

                if is_tty:
                    sys.stdout.write(
                        f"\r  {Col.BOLD}Ventola Pico:{Col.RESET} {Col.GREEN}{pico_rpm:>4} RPM{Col.RESET} [{cur_duty:>3}%]  "
                        f"|  {Col.BOLD}Ventola Interna:{Col.RESET} {Col.YELLOW}{int_rpm:>4} RPM{Col.RESET}   "
                        f"{Col.DIM}(CTRL+C per uscire){Col.RESET}   "
                    )
                    sys.stdout.flush()
                else:
                    print(f"Pico: {pico_rpm} RPM [{cur_duty}%] | Interna: {int_rpm} RPM")

            except (socket.timeout, json.JSONDecodeError):
                continue
            except (socket.error, OSError):
                break

    finally:
        # Ripristino segnali
        signal.signal(signal.SIGINT, prev_int)
        signal.signal(signal.SIGTERM, prev_term)

        print("\n\nRipristino modalità automatica in corso...")
        try:
            sock.sendall(b'{"cmd": "auto"}\n')
            time.sleep(0.2)
            sock.close()
        except Exception:
            pass

        print(f"{Col.BOLD}{Col.GREEN}✓ Modalità automatica ripristinata con successo.{Col.RESET}\n")

    return True


def _run_manual_direct_serial(duty: int) -> None:
    """
    Fallback: se il demone non è attivo, controlla il Pico direttamente su seriale.
    """
    try:
        import serial
        from hardware_detector import scan_devices
    except ImportError as e:
        print(f"{Col.BOLD}{Col.RED}ERRORE:{Col.RESET} Modulo seriale non disponibile: {e}")
        sys.exit(1)

    devices = scan_devices(probe=False)
    if not devices:
        print(f"{Col.BOLD}{Col.RED}ERRORE:{Col.RESET} Demone pico-fan non attivo e nessun dispositivo Pico trovato.")
        print("Avviare il demone con: sudo systemctl start pico-fan")
        sys.exit(1)

    device = devices[0]
    print(f"{Col.YELLOW}Avviso:{Col.RESET} Demone non attivo. Connessione seriale diretta su {device.real_path}...")

    try:
        ser = serial.Serial(device.real_path, baudrate=115200, timeout=1.0)
        time.sleep(0.5)
        ser.reset_input_buffer()
        ser.write(f"SET {duty}\n".encode("ascii"))
        ser.flush()
    except Exception as exc:
        print(f"{Col.BOLD}{Col.RED}ERRORE:{Col.RESET} Impossibile aprire la porta seriale: {exc}")
        sys.exit(1)

    stop_requested = False

    def _sig_handler(sig, frame):  # noqa: ARG001
        nonlocal stop_requested
        stop_requested = True

    prev_int = signal.signal(signal.SIGINT, _sig_handler)
    prev_term = signal.signal(signal.SIGTERM, _sig_handler)

    is_tty = sys.stdout.isatty()
    print(f"\n{Col.BOLD}{Col.CYAN}=== Controllo Diretto Seriale ({duty}%) ==={Col.RESET}")
    print(f"{Col.DIM}Premi CTRL+C per uscire e fermare la ventola.{Col.RESET}\n")

    try:
        while not stop_requested:
            try:
                ser.reset_input_buffer()
                ser.write(b"RPM\n")
                ser.flush()
                resp = ser.readline().decode("ascii", errors="replace").strip()
                pico_rpm = 0
                if resp.startswith("RPM:"):
                    parts = resp.split()
                    pico_rpm = int(parts[0][4:])

                if is_tty:
                    sys.stdout.write(
                        f"\r  {Col.BOLD}Ventola Pico:{Col.RESET} {Col.GREEN}{pico_rpm:>4} RPM{Col.RESET} [{duty:>3}%]   "
                        f"{Col.DIM}(CTRL+C per uscire){Col.RESET}   "
                    )
                    sys.stdout.flush()
                else:
                    print(f"Pico: {pico_rpm} RPM [{duty}%]")

                time.sleep(1.0)
            except Exception:
                time.sleep(1.0)

    finally:
        signal.signal(signal.SIGINT, prev_int)
        signal.signal(signal.SIGTERM, prev_term)
        print("\n\nChiusura connessione...")
        try:
            ser.write(b"SET 0\n")
            ser.flush()
            ser.close()
        except Exception:
            pass
        print(f"{Col.BOLD}{Col.GREEN}✓ Ventola arrestata e connessione chiusa.{Col.RESET}\n")


def main() -> None:
    if not sys.stdout.isatty():
        _disable_colors()

    duty = _parse_duty_arg()

    # Tenta prima tramite il demone in esecuzione (IPC)
    ok = _run_manual_via_daemon(duty)
    if not ok:
        # Fallback a controllo seriale diretto
        _run_manual_direct_serial(duty)


if __name__ == "__main__":
    main()
