#!/usr/bin/env python3
"""
status.py - CLI Status Diagnostic Tool
=======================================
Queries the running pico-fan daemon via UNIX domain socket and displays
a formatted summary table of device connection, internal RPM, Pico RPM,
and target PWM duty cycle.
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
DAEMON_DIR = SCRIPT_DIR.parent / "daemon"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(DAEMON_DIR))

from ANSI_colors import BOLD, CYAN, DIM, GREEN, RED, RESET, WHITE, YELLOW, cprint
from ipc_adapter import IpcAdapter, SOCK_PATH


def main():
    state = IpcAdapter(timeout=2.0).get_status()
    if state is None:
        cprint(f"ERRORE: Impossibile comunicare con il socket {SOCK_PATH}.", RED, bold=True)
        cprint("Il demone pico-fan è in esecuzione? Controlla con: systemctl status pico-fan")
        sys.exit(1)

    # Parse received state
    connected = state.get("connected", False)
    port = state.get("pico_port", "N/A")
    control_source = state.get("control_source", "rpm")
    source_value = state.get("source_value", 0)
    int_rpm = state.get("internal_rpm", 0)
    ext_rpm = state.get("pico_rpm", 0)
    duty = state.get("current_duty", 0)
    version = state.get("version", "unknown")

    # Format output strings
    status_str = f"{GREEN}Connesso{RESET}" if connected else f"{RED}Scollegato{RESET}"

    source_formatted = state.get("source_formatted", "")

    if control_source == "temp":
        source_label = "Sorgente (Temperatura)"
        source_str = source_formatted or (f"{source_value:.1f}°C" if isinstance(source_value, (int, float)) else "N/A")
    else:
        source_label = "Sorgente (RPM)"
        source_str = source_formatted or f"{int_rpm} RPM"

    hold_active = state.get("hold_active", False)
    hold_rem = state.get("hold_remaining", 0.0)
    ramp_active = state.get("ramp_active", False)
    target_duty = state.get("target_duty", duty)

    duty_extra = ""
    if hold_active:
        duty_extra = f" {YELLOW}[Hold: {hold_rem:.1f}s rimanenti]{RESET}"
    elif ramp_active:
        duty_extra = f" {CYAN}[Rampa discesa -> {target_duty}%]{RESET}"

    cprint(f"\n=== pico-fan-control v{version} ===\n", CYAN, bold=True)
    cprint(f" Stato dispositivo:   {status_str} ({port})", BOLD)
    cprint(f" Modalità controllo:  {control_source.upper()}", BOLD)
    cprint(f" {source_label}:  {source_str}", BOLD)
    cprint(f" Destinazione (Pico): {ext_rpm} RPM  [Target PWM: {duty}%]{duty_extra}", BOLD)
    print()

if __name__ == "__main__":
    main()
