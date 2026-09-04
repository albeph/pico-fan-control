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

# Aggiunge i path di libreria al sys.path
SCRIPT_DIR  = Path(__file__).parent.resolve()
DAEMON_DIR  = SCRIPT_DIR.parent / "daemon"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(DAEMON_DIR))

try:
    from version import __version__
except ImportError:
    __version__ = "unknown"

# ---------------------------------------------------------------------------
# Colori ANSI
# ---------------------------------------------------------------------------
_COLOR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
RESET  = "\033[0m"    if _COLOR else ""
BOLD   = "\033[1m"    if _COLOR else ""
CYAN   = "\033[96m"   if _COLOR else ""
GREEN  = "\033[92m"   if _COLOR else ""
YELLOW = "\033[93m"   if _COLOR else ""
DIM    = "\033[2m"    if _COLOR else ""

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
HELP = f"""\
{BOLD}{CYAN}pico-fan{RESET} {DIM}v{__version__}{RESET} — Controllo ventola USB via Raspberry Pi Pico

{BOLD}Uso:{RESET}
  pico-fan <comando> [opzioni]

{BOLD}Comandi:{RESET}
  {GREEN}daemon{RESET}       Avvia il demone di sincronizzazione RPM (usato da systemd)
  {GREEN}setup{RESET}        Wizard interattivo di configurazione e test hardware
  {GREEN}status{RESET}       Mostra lo stato corrente del demone (RPM, duty, porta)
  {GREEN}manual <N>{RESET}   Imposta manualmente la ventola a N% e mostra RPM in tempo reale
  {GREEN}version{RESET}      Mostra la versione installata

{BOLD}Esempi:{RESET}
  {DIM}# Primo avvio:{RESET}
  sudo pico-fan setup

  {DIM}# Avvia il demone manualmente:{RESET}
  sudo pico-fan daemon

  {DIM}# Oppure tramite systemd (raccomandato):{RESET}
  sudo systemctl start pico-fan

  {DIM}# Diagnostica rapida:{RESET}
  pico-fan status

  {DIM}# Imposta manualmente la ventola al 75% e monitora:{RESET}
  pico-fan manual 75

  {DIM}# Versione installata:{RESET}
  pico-fan version

{BOLD}File di configurazione:{RESET}
  /etc/pico-fan/config.json

{BOLD}Log di sistema:{RESET}
  journalctl -u pico-fan -f
"""


def _cmd_version() -> None:
    """Stampa la versione installata."""
    version_file = Path("/usr/lib/pico-fan/VERSION")
    if version_file.exists():
        print(version_file.read_text().strip())
    else:
        print(__version__)


def _cmd_daemon() -> None:
    """Avvia il demone di sincronizzazione RPM."""
    from fan_daemon import main
    main()


def _cmd_setup() -> None:
    """Avvia il wizard di configurazione interattivo."""
    from setup_wizard import main
    main()


def _cmd_status() -> None:
    """Mostra lo stato corrente del demone via socket IPC."""
    from status import main
    main()


def _cmd_manual() -> None:
    """Imposta manualmente la velocità della ventola e mostra gli RPM."""
    from manual import main
    main()


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
        print(HELP)
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd not in COMMANDS:
        print(f"{BOLD}pico-fan:{RESET} comando sconosciuto: '{cmd}'")
        print(f"Esegui {BOLD}pico-fan --help{RESET} per la lista dei comandi disponibili.")
        sys.exit(1)

    # Rimuove il sottocomando da sys.argv così i moduli ricevono i propri argomenti
    sys.argv = [f"pico-fan {cmd}"] + sys.argv[2:]

    _, fn = COMMANDS[cmd]
    fn()


if __name__ == "__main__":
    main()
