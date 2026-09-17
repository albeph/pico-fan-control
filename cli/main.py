#!/usr/bin/env python3
"""
main.py - pico-fan Unified CLI Dispatcher
===========================================
Primary command dispatcher for pico-fan-control, routing subcommands
(daemon, setup, status, manual, version) to their respective modules.

Usage: pico-fan <command> [options]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from ANSI_colors import BOLD, CYAN, DIM, GREEN, RED, RESET, WHITE, YELLOW, cprint


SCRIPT_DIR  = Path(__file__).parent.resolve()
DAEMON_DIR  = SCRIPT_DIR.parent / "daemon"

# Add both directories to Python's module search path
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(DAEMON_DIR))

try:
    from version import __version__
except ImportError:
    __version__ = "unknown"


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
HELP = f"""\
{BOLD}{CYAN}pico-fan{RESET} {DIM}v{__version__}{RESET} — Controllo ventola USB via Raspberry Pi Pico

{BOLD}Uso:{RESET}
  pico-fan <comando> [opzioni]

{BOLD}Comandi:{RESET}
  {GREEN}daemon{RESET}       Avvia il demone di sincronizzazione RPM (usato da systemd o nel caso si voglia installare manualmente)
  {GREEN}setup{RESET}        Wizard interattivo di configurazione e test hardware
  {GREEN}status{RESET}       Mostra lo stato corrente del demone (RPM, duty, porta)
  {GREEN}manual <N>{RESET}   Imposta manualmente la ventola a N% e mostra RPM in tempo reale
  {GREEN}version{RESET}      Mostra la versione installata

{BOLD}File di configurazione:{RESET}
  /etc/pico-fan/config.json

{BOLD}Log di sistema:{RESET}
  journalctl -u pico-fan -f
"""


def _cmd_version() -> None:
    """Prints the installed version."""
    print(__version__)


def _cmd_daemon() -> None:
    """Starts the RPM synchronization daemon."""
    from fan_daemon import main as fd_main
    fd_main()


def _cmd_setup() -> None:
    """Starts the interactive configuration wizard."""
    from setup_wizard import main as sw_main
    sw_main()


def _cmd_status() -> None:
    """Displays current daemon status via IPC socket."""
    from status import main as status_main
    status_main()


def _cmd_manual() -> None:
    """Manually sets fan speed and displays real-time RPM."""
    from manual import main as manual_main
    manual_main()


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
COMMANDS: dict[str, tuple[str, callable]] = {
    "daemon":  ("Start RPM synchronization daemon",          _cmd_daemon),
    "setup":   ("Interactive configuration wizard",          _cmd_setup),
    "status":  ("Display real-time daemon status",           _cmd_status),
    "manual":  ("Manually set fan speed and monitor RPM",    _cmd_manual),
    "version": ("Display installed version",                 _cmd_version),
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        cprint(HELP)
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd not in COMMANDS:
        cprint(f"pico-fan: comando sconosciuto: '{cmd}'", RED, bold=True)
        cprint("Esegui pico-fan --help per la lista dei comandi disponibili.", BOLD)
        sys.exit(1)

    # Permission check

    if cmd != "version" and os.geteuid() != 0:
        cprint(
            "Errore: questo comando richiede i permessi di root.\n"
            f"Eseguire: sudo pico-fan {cmd}",
            RED,
            bold=True,
        )
        sys.exit(1)

    # Remove the subcommand from sys.argv so modules receive their own arguments
    sys.argv = [f"pico-fan {cmd}"] + sys.argv[2:]

    _, fn = COMMANDS[cmd]   # e.g., if cmd == "manual", fn() executes _cmd_manual
    fn()


if __name__ == "__main__":
    main()
