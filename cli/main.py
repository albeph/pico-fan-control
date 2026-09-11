#!/usr/bin/env python3
"""
pico-fan - Comando unificato pico-fan-control
=============================================
Dispatcher principale che instrada i sottocomandi ai rispettivi moduli.

Uso: pico-fan <comando> [opzioni]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from ANSI_colors import BOLD, CYAN, DIM, GREEN, RED, RESET, WHITE, YELLOW, cprint


SCRIPT_DIR  = Path(__file__).parent.resolve()
DAEMON_DIR  = SCRIPT_DIR.parent / "daemon" #./pico-fan-control/daemon

# Aggiunge entrambe le cartelle nei percorsi in cui Python cerca i moduli
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
    """Stampa la versione installata."""
    print(__version__)


def _cmd_daemon() -> None:
    """Avvia il demone di sincronizzazione RPM."""
    from fan_daemon import main as fd_main
    fd_main()


def _cmd_setup() -> None:
    """Avvia il wizard di configurazione interattivo."""
    from setup_wizard import main as sw_main
    sw_main()


def _cmd_status() -> None:
    """Mostra lo stato corrente del demone via socket IPC."""
    from status import main as status_main
    status_main()


def _cmd_manual() -> None:
    """Imposta manualmente la velocità della ventola e mostra gli RPM."""
    from manual import main as manual_main
    manual_main()


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
COMMANDS: dict[str, tuple[str, callable]] = {
    "daemon":  ("Avvia il demone di sincronizzazione RPM",             _cmd_daemon),
    "setup":   ("Wizard interattivo di configurazione",                _cmd_setup),
    "status":  ("Mostra stato in tempo reale",                         _cmd_status),
    "manual":  ("Imposta manualmente la velocità e monitora gli RPM",  _cmd_manual),
    "version": ("Mostra la versione installata",                       _cmd_version),
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

    # Rimuove il sottocomando da sys.argv così i moduli ricevono i propri argomenti
    sys.argv = [f"pico-fan {cmd}"] + sys.argv[2:]

    _, fn = COMMANDS[cmd]   #ad esempio se cmd == cmd_manual, allora fn() sarà come eseguire _cmd_manual
    fn()


if __name__ == "__main__":
    main()
