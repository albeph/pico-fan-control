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

SOCK_PATH = "/run/pico-fan.sock"

# Colori terminale
class Col:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

def main():
    if not sys.stdout.isatty():
        # Disabilita colori se non è un TTY
        Col.GREEN = Col.YELLOW = Col.RED = Col.CYAN = Col.BOLD = Col.RESET = ""

    if not os.path.exists(SOCK_PATH):
        print(f"{Col.BOLD}{Col.RED}ERRORE:{Col.RESET} Socket {SOCK_PATH} non trovato.")
        print("Il demone pico-fan è in esecuzione? Controlla con: systemctl status pico-fan")
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
        print(f"{Col.BOLD}{Col.RED}ERRORE:{Col.RESET} Impossibile comunicare con il demone: {exc}")
        sys.exit(1)

    # Parsing dati
    connected = state.get("connected", False)
    port = state.get("pico_port", "N/A")
    int_rpm = state.get("internal_rpm", 0)
    ext_rpm = state.get("pico_rpm", 0)
    duty = state.get("current_duty", 0)
    version = state.get("version", "unknown")

    # Formattazione
    status_str = f"{Col.GREEN}Connesso{Col.RESET}" if connected else f"{Col.RED}Scollegato{Col.RESET}"
    
    print(f"\n{Col.BOLD}{Col.CYAN}=== pico-fan-control v{version} ==={Col.RESET}\n")
    print(f" {Col.BOLD}Stato dispositivo:{Col.RESET}  {status_str} ({port})")
    print(f" {Col.BOLD}Sorgente (Server):{Col.RESET}  {int_rpm} RPM")
    print(f" {Col.BOLD}Destinazione (Pico):{Col.RESET} {ext_rpm} RPM  [Target PWM: {duty}%]")
    print("")

if __name__ == "__main__":
    main()
