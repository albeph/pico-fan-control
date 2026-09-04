#!/usr/bin/env python3
"""
setup_wizard.py - CLI interattiva per configurazione pico-fan-control
=======================================================================
Wizard guidato che:
  1. Scansiona /dev/serial/by-id/ alla ricerca di schede Pico/RP2040
  2. Mostra l'elenco delle schede trovate con stato di risposta
  3. Permette di selezionare il dispositivo da usare
  4. Testa la ventola con vari duty cycle
  5. Scansiona le ventole interne disponibili (hwmon + /proc/acpi/ibm/fan)
  6. Salva la configurazione in /etc/pico-fan/config.json

Autore:   pico-fan-control project
Versione: 1.0.0
"""

from __future__ import annotations

import os
import sys
import json
import time
import shutil
import signal
from pathlib import Path
from typing import Optional

# Aggiungi il path del daemon per importare i moduli
SCRIPT_DIR = Path(__file__).parent.resolve()
DAEMON_DIR = SCRIPT_DIR.parent / "daemon"
sys.path.insert(0, str(DAEMON_DIR))

try:
    from hardware_detector import scan_devices, PicoDevice, probe_pico
    from fan_daemon import (
        read_internal_rpm_ibm,
        read_internal_rpm_hwmon,
    )
    from version import __version__
except ImportError as e:
    print(f"Errore di importazione moduli daemon: {e}")
    print("Assicurarsi che il pacchetto sia installato correttamente.")
    sys.exit(1)

try:
    import serial
    import serial.serialutil
except ImportError:
    print("Errore: pyserial non installato. Eseguire: pip install pyserial")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------
CONFIG_DIR  = "/etc/pico-fan"
CONFIG_FILE = "/etc/pico-fan/config.json"
BAUDRATE    = 115200

# ---------------------------------------------------------------------------
# Colori ANSI per terminale
# ---------------------------------------------------------------------------
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    DIM    = "\033[2m"


def _supports_color() -> bool:
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    term = os.environ.get("TERM", "")
    if term == "dumb":
        return False
    return True


def cprint(text: str, color: str = C.RESET, bold: bool = False) -> None:
    if _supports_color():
        prefix = (C.BOLD if bold else "") + color
        print(f"{prefix}{text}{C.RESET}")
    else:
        print(text)


def banner() -> None:
    cprint(rf"""
╔═══════════════════════════════════════════════════════════╗
║         PICO FAN CONTROL - Setup Wizard v{__version__:<10}         ║
║   Controllo ventola USB via Raspberry Pi Pico / RP2040    ║
╚═══════════════════════════════════════════════════════════╝
""", C.CYAN, bold=True)


def separator(title: str = "") -> None:
    width = 60
    if title:
        pad = (width - len(title) - 2) // 2
        cprint(f"\n{'─' * pad} {title} {'─' * pad}\n", C.BLUE)
    else:
        cprint("─" * width, C.DIM)


def ask(prompt: str, default: str = "") -> str:
    """Input interattivo con valore di default."""
    if default:
        full_prompt = f"{prompt} [{default}]: "
    else:
        full_prompt = f"{prompt}: "
    # Usa print semplice per evitare escape ANSI nell'input interattivo
    if _supports_color():
        sys.stdout.write(f"{C.BOLD}{C.WHITE}{full_prompt}{C.RESET}")
    else:
        sys.stdout.write(full_prompt)
    sys.stdout.flush()
    try:
        answer = input().strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return answer if answer else default


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    """Chiede una conferma Y/N."""
    hint = "Y/n" if default else "y/N"
    answer = ask(f"{prompt} ({hint})", "y" if default else "n")
    return answer.lower() in ("y", "yes", "s", "si", "sì", "1", "true")


def pick_from_list(items: list, prompt: str = "Scelta") -> Optional[int]:
    """Mostra una lista numerata e chiede all'utente di scegliere."""
    for i, item in enumerate(items, 1):
        cprint(f"  [{i}] {item}", C.WHITE)
    answer = ask(f"\n{prompt} (1-{len(items)})", "1")
    try:
        idx = int(answer) - 1
        if 0 <= idx < len(items):
            return idx
    except ValueError:
        pass
    cprint("Scelta non valida, uso la prima opzione.", C.YELLOW)
    return 0


# ===========================================================================
# STEP 1: Scansione dispositivi Pico
# ===========================================================================

def step_scan_devices() -> Optional[PicoDevice]:
    """Scansiona le porte seriali e fa scegliere il Pico da usare."""
    separator("STEP 1 - Scansione hardware")
    cprint("Ricerca dispositivi Pico/RP2040 in /dev/serial/by-id/ ...", C.CYAN)

    devices = scan_devices(probe=True)

    if not devices:
        cprint(
            "\n✗ Nessun dispositivo Pico trovato!\n"
            "  Verificare che:\n"
            "  - Il cavo USB sia collegato\n"
            "  - Il firmware main.py sia caricato sul Pico\n"
            "  - Il driver cdc_acm sia caricato (modprobe cdc_acm)",
            C.RED,
        )
        if not ask_yes_no("\nVuoi riprovare la scansione?", default=True):
            return None
        return step_scan_devices()

    cprint(f"\n✓ Trovati {len(devices)} dispositivo/i:\n", C.GREEN, bold=True)

    descriptions = []
    for dev in devices:
        status = (
            f"✓ {C.GREEN}Risponde{C.RESET} (RPM={dev.rpm}, DUTY={dev.duty}%)"
            if dev.responsive
            else f"✗ {C.RED}Non risponde{C.RESET}"
        )
        descriptions.append(
            f"{dev.hw_id}\n"
            f"      Port: {dev.real_path} | {status}"
        )

    if len(devices) == 1:
        dev = devices[0]
        cprint(f"  Dispositivo selezionato automaticamente: {dev.real_path}", C.GREEN)
        return dev

    idx = pick_from_list(descriptions, "Seleziona il dispositivo da usare")
    return devices[idx] if idx is not None else None


# ===========================================================================
# STEP 2: Test ventola
# ===========================================================================

def step_test_fan(device: PicoDevice) -> bool:
    """Test interattivo della ventola con duty cycle variabili."""
    separator("STEP 2 - Test ventola")

    cprint(
        f"Test della ventola su {device.real_path}\n"
        "La ventola verrà fatta girare a varie velocità.",
        C.CYAN,
    )

    if not ask_yes_no("Procedere con il test?", default=True):
        cprint("Test saltato.", C.YELLOW)
        return True

    test_sequences = [
        (25,  "25% - bassa velocità"),
        (50,  "50% - velocità media"),
        (100, "100% - velocità massima"),
        (0,   "0%  - spenta"),
    ]

    try:
        with serial.Serial(device.real_path, baudrate=BAUDRATE, timeout=3.0) as ser:
            # Aspetta che il Pico sia pronto (reset CDC) e svuota il banner di avvio
            time.sleep(1.0)
            ser.reset_input_buffer()

            for duty, desc in test_sequences:
                cprint(f"\n  → Imposto {desc} ...", C.CYAN)

                # Svuota buffer prima di inviare il comando
                ser.reset_input_buffer()
                ser.write(f"SET {duty}\n".encode())
                ser.flush()

                # Aspetta la risposta con un piccolo ritardo per dare tempo al firmware
                time.sleep(0.3)
                resp = ser.readline().decode("ascii", errors="replace").strip()

                if resp == "OK":
                    cprint(f"    ✓ Risposta: {resp}", C.GREEN)
                else:
                    cprint(f"    Risposta inattesa: '{resp}'", C.YELLOW)

                time.sleep(2.0)

                # Leggi RPM
                ser.reset_input_buffer()
                ser.write(b"RPM\n")
                ser.flush()
                time.sleep(0.3)
                rpm_resp = ser.readline().decode("ascii", errors="replace").strip()
                cprint(f"    Stato: {rpm_resp}", C.DIM)

        cprint("\n✓ Test completato.", C.GREEN, bold=True)
        return ask_yes_no("La ventola ha risposto correttamente?", default=True)

    except serial.serialutil.SerialException as exc:
        cprint(f"\n✗ Errore durante il test: {exc}", C.RED)
        return False


# ===========================================================================
# STEP 3: Selezione ventola interna da monitorare
# ===========================================================================

def _discover_internal_fans() -> list[dict]:
    """
    Raccoglie le ventole interne disponibili da hwmon e /proc/acpi/ibm/fan.
    Restituisce lista di dict con 'label', 'type', 'path', 'rpm'.
    """
    fans = []

    # Cerca in /proc/acpi/ibm/fan (ThinkPad)
    ibm_fan = "/proc/acpi/ibm/fan"
    if os.path.exists(ibm_fan):
        rpm = read_internal_rpm_ibm(ibm_fan)
        fans.append({
            "label": f"ThinkPad ACPI Fan  [{ibm_fan}]  RPM={rpm or 'N/A'}",
            "type":  "ibm_acpi",
            "path":  ibm_fan,
            "rpm":   rpm or 0,
        })

    # Cerca in /sys/class/hwmon/*/fan*_input
    base = Path("/sys/class/hwmon")
    if base.exists():
        for hwmon_dir in sorted(base.iterdir()):
            try:
                hw_name = (hwmon_dir / "name").read_text().strip()
            except OSError:
                hw_name = hwmon_dir.name

            if hw_name == "pico_fan":
                continue    # Salta il nostro vecchio modulo se ancora presente

            for fan_file in sorted(hwmon_dir.glob("fan*_input")):
                try:
                    rpm = int(fan_file.read_text().strip())
                    fans.append({
                        "label": (
                            f"hwmon:{hw_name} {fan_file.name}"
                            f"  [{fan_file}]  RPM={rpm}"
                        ),
                        "type":  "hwmon",
                        "path":  str(fan_file),
                        "rpm":   rpm,
                    })
                except (OSError, ValueError):
                    continue

    return fans


def step_select_internal_fan() -> dict:
    """Permette all'utente di scegliere la ventola interna da monitorare."""
    separator("STEP 3 - Selezione ventola interna")
    cprint("Ricerca ventole interne disponibili ...\n", C.CYAN)

    fans = _discover_internal_fans()

    if not fans:
        cprint(
            "✗ Nessuna ventola interna rilevata.\n"
            "  Sarà usato /proc/acpi/ibm/fan come default.\n"
            "  Installare lm-sensors (apt install lm-sensors) e\n"
            "  eseguire 'sensors-detect' per abilitare i moduli.",
            C.YELLOW,
        )
        return {
            "type": "ibm_acpi",
            "path": "/proc/acpi/ibm/fan",
            "ibm_fan_path": "/proc/acpi/ibm/fan",
        }

    labels = [f["label"] for f in fans]
    idx = pick_from_list(labels, "Seleziona la ventola interna da monitorare")
    selected = fans[idx]
    cprint(f"\n✓ Selezionata: {selected['label']}", C.GREEN)
    return selected


# ===========================================================================
# STEP 4: Configurazione soglie
# ===========================================================================

def step_configure_thresholds() -> dict:
    """Chiede all'utente di configurare le soglie RPM."""
    separator("STEP 4 - Soglie di controllo")

    cprint(
        "Configurazione curva ventola:\n"
        "  RPM > soglia_alta  -> Ventola al 100%\n"
        "  RPM >= soglia_mid  -> Ventola al 50%\n"
        "  RPM < soglia_mid   -> Ventola spenta (0%)\n",
        C.CYAN,
    )

    high = ask("Soglia RPM alta  (default 4000)", "4000")
    mid  = ask("Soglia RPM media (default 2500)", "2500")

    try:
        high_val = int(high)
        mid_val  = int(mid)
    except ValueError:
        cprint("Valori non validi, uso i default.", C.YELLOW)
        high_val, mid_val = 4000, 2500

    if high_val <= mid_val:
        cprint("⚠ La soglia alta deve essere > soglia media. Uso valori di default.", C.YELLOW)
        high_val, mid_val = 4000, 2500

    cprint(
        f"\n✓ Configurazione soglie:\n"
        f"  > {high_val} RPM  → 100%\n"
        f"  {mid_val}-{high_val} RPM → 50%\n"
        f"  < {mid_val} RPM  → 0%",
        C.GREEN,
    )

    return {
        "rpm_threshold_high": high_val,
        "rpm_threshold_mid":  mid_val,
        "duty_high":          100,
        "duty_mid":           50,
        "duty_low":           0,
    }


# ===========================================================================
# STEP 5: Salvataggio configurazione
# ===========================================================================

def step_save_config(
    device: PicoDevice,
    fan_config: dict,
    thresholds: dict,
) -> bool:
    """Scrive la configurazione finale in /etc/pico-fan/config.json."""
    separator("STEP 5 - Salvataggio configurazione")

    config = {
        "pico_serial_by_id":  device.by_id_path,
        "ibm_fan_path":       fan_config.get("path", "/proc/acpi/ibm/fan")
                              if fan_config.get("type") == "ibm_acpi"
                              else "/proc/acpi/ibm/fan",
        "hwmon_fan_path":     fan_config.get("path", "")
                              if fan_config.get("type") == "hwmon"
                              else "",
        "poll_interval":      2.0,
        "reconnect_interval": 5.0,
        **thresholds,
    }

    cprint("Configurazione da salvare:", C.CYAN)
    print(json.dumps(config, indent=2))

    if not ask_yes_no("\nConfermare e salvare?", default=True):
        cprint("Configurazione non salvata.", C.YELLOW)
        return False

    # Crea la directory se non esiste (richiede root)
    try:
        os.makedirs(CONFIG_DIR, mode=0o755, exist_ok=True)
    except PermissionError:
        cprint(
            f"✗ Permessi insufficienti per creare {CONFIG_DIR}.\n"
            f"  Eseguire il wizard come root: sudo pico-fan-setup",
            C.RED,
        )
        return False

    backup = None
    if os.path.exists(CONFIG_FILE):
        backup = CONFIG_FILE + ".bak"
        shutil.copy2(CONFIG_FILE, backup)
        cprint(f"  Backup configurazione precedente: {backup}", C.DIM)

    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")
        os.chmod(CONFIG_FILE, 0o644)
        cprint(f"\n✓ Configurazione salvata in {CONFIG_FILE}", C.GREEN, bold=True)
        return True
    except OSError as exc:
        cprint(f"✗ Errore salvataggio: {exc}", C.RED)
        if backup and os.path.exists(backup):
            shutil.copy2(backup, CONFIG_FILE)
        return False


# ===========================================================================
# Entry point
# ===========================================================================

def main() -> None:
    """Esegue il wizard completo di configurazione."""
    # Gestione SIGINT pulita
    signal.signal(signal.SIGINT, lambda *_: (cprint("\n\nWizard interrotto.", C.YELLOW), sys.exit(0)))

    banner()

    cprint(
        "Questo wizard configurerà il sistema pico-fan-control.\n"
        "Avrai bisogno di:\n"
        "  • Il Raspberry Pi Pico collegato via USB con il firmware main.py caricato\n"
        "  • Privilegi root per salvare la configurazione\n",
        C.DIM,
    )

    if not ask_yes_no("Continuare?", default=True):
        cprint("Uscita.", C.YELLOW)
        sys.exit(0)

    # STEP 1: Scansione e selezione dispositivo
    device = step_scan_devices()
    if device is None:
        cprint("\n✗ Nessun dispositivo selezionato. Uscita.", C.RED)
        sys.exit(1)

    # STEP 2: Test ventola
    test_ok = step_test_fan(device)
    if not test_ok:
        cprint(
            "\n⚠ Il test ventola non è andato a buon fine.\n"
            "  Verificare il firmware e il cablaggio prima di continuare.",
            C.YELLOW,
        )
        if not ask_yes_no("Continuare comunque?", default=False):
            sys.exit(1)

    # STEP 3: Ventola interna
    fan_config = step_select_internal_fan()

    # STEP 4: Soglie
    thresholds = step_configure_thresholds()

    # STEP 5: Salvataggio
    saved = step_save_config(device, fan_config, thresholds)

    # Riepilogo finale
    separator("COMPLETATO")
    if saved:
        cprint(
            "✓ Setup completato con successo!\n\n"
            "  Prossimi passi:\n"
            "  1. Avviare il demone:          sudo systemctl start pico-fan\n"
            "  2. Abilitare all'avvio:        sudo systemctl enable pico-fan\n"
            "  3. Verificare lo stato:        pico-fan-status\n",
            C.GREEN,
            bold=True,
        )
    else:
        cprint(
            "⚠ Setup incompleto. Ricontrollare la configurazione e riprovare.",
            C.YELLOW,
        )


if __name__ == "__main__":
    main()
