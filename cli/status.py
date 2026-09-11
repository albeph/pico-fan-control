#!/usr/bin/env python3
"""
status.py - CLI tool per controllare lo stato di pico-fan-control
==================================================================

Interroga il demone in esecuzione tramite socket UNIX e stampa
una tabella riassuntiva formattata.
"""

import os
import sys
import json
import socket
from ANSI_colors import BOLD, CYAN, DIM, GREEN, RED, RESET, WHITE, YELLOW, cprint


SOCK_PATH = "/run/pico-fan.sock"


def main():
    if not os.path.exists(SOCK_PATH):
        cprint(f"ERRORE: Socket {SOCK_PATH} non trovato.", RED, bold=True)
        cprint("Il demone pico-fan è in esecuzione? Controlla con: systemctl status pico-fan")
        sys.exit(1)

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect(SOCK_PATH)
            
            # Leggi risposta (fino a newline)
            data = b""
            while b"\n" not in data:
                chunk = s.recv(1024)
                if not chunk:
                    break
                data += chunk
                
        if not data:
            raise ValueError("Risposta vuota dal demone")
            
        state = json.loads(data.decode("utf-8").strip())
        
    except Exception as exc:
        cprint(f"ERRORE: Impossibile comunicare con il demone: {exc}", RED, bold=True)
        sys.exit(1)

    # Parsing dati
    connected = state.get("connected", False)
    port = state.get("pico_port", "N/A")
    int_rpm = state.get("internal_rpm", 0)
    ext_rpm = state.get("pico_rpm", 0)
    duty = state.get("current_duty", 0)
    version = state.get("version", "unknown")

    # Formattazione
    status_str = f"{GREEN}Connesso{RESET}" if connected else f"{RED}Scollegato{RESET}"
    
    cprint(f"\n=== pico-fan-control v{version} ===\n", CYAN, bold=True)
    cprint(f" Stato dispositivo:  {status_str} ({port})", BOLD)
    cprint(f" Sorgente (Server):  {int_rpm} RPM", BOLD)
    cprint(f" Destinazione (Pico): {ext_rpm} RPM  [Target PWM: {duty}%]", BOLD)
    print()

if __name__ == "__main__":
    main()
