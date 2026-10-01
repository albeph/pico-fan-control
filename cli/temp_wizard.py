#!/usr/bin/env python3
"""
temp_wizard.py - Temperature Sensor Setup Wizard Steps
=======================================================
Provides interactive wizard steps for:
  1. Scanning and selecting a temperature sensor
  2. Configuring temperature thresholds for the fan curve
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add daemon directory to module search path
SCRIPT_DIR = Path(__file__).parent.resolve()
DAEMON_DIR = SCRIPT_DIR.parent / "daemon"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(DAEMON_DIR))

from ANSI_colors import CYAN, DIM, GREEN, RED, WHITE, YELLOW, cprint
from temp_reader import discover_temp_sensors

# Import shared wizard helpers
from wizard_helpers import ask, ask_yes_no, pick_from_list, separator


# ===========================================================================
# STEP: Scan and select temperature sensor
# ===========================================================================

def step_select_temp_sensor() -> dict:
    """
    Scans hwmon for temperature sensors and lets the user pick one.
    Returns a dict with 'path', 'name', 'label', 'temp'.
    """
    separator("Selezione sensore di temperatura")
    cprint("Ricerca sensori di temperatura disponibili ...\n", CYAN)

    sensors = discover_temp_sensors()

    # Filter out sensors with no valid reading
    valid_sensors = [s for s in sensors if s["temp"] is not None]

    if not valid_sensors:
        cprint(
            "✗ Nessun sensore di temperatura rilevato!\n"
            "  Installare lm-sensors (apt install lm-sensors) e\n"
            "  eseguire 'sensors-detect' per abilitare i moduli.\n\n"
            "  Sarà usato l'auto-rilevamento a runtime.",
            YELLOW,
        )
        return {
            "path": "",
            "name": "auto",
            "label": "Auto-detect",
            "temp": None,
        }

    cprint(f"✓ Trovati {len(valid_sensors)} sensore/i:\n", GREEN, bold=True)

    labels = []
    for s in valid_sensors:
        temp_str = f"{s['temp']:.1f}°C" if s["temp"] is not None else "N/A"
        labels.append(
            f"{s['name']}:{s['label']}  [{s['path']}]  {temp_str}"
        )

    idx = pick_from_list(labels, "Seleziona il sensore di temperatura")
    selected = valid_sensors[idx]

    temp_str = f"{selected['temp']:.1f}°C" if selected["temp"] is not None else "N/A"
    cprint(
        f"\n✓ Selezionato: {selected['name']}:{selected['label']}  ({temp_str})",
        GREEN,
    )
    return selected


# ===========================================================================
# STEP: Configure temperature thresholds
# ===========================================================================

def step_configure_temp_thresholds(duty_high: int = 100) -> dict:
    """
    Prompts the user to configure temperature thresholds (in °C).
    Returns a dict with threshold and duty values.
    """
    separator("Soglie di temperatura")

    cprint(
        f"Configurazione curva ventola (duty massimo: {duty_high}%):\n"
        f"  Temp > soglia_alta  → Ventola al {duty_high}%\n"
        "  Temp >= soglia_mid  → Ventola al 50%\n"
        "  Temp < soglia_mid   → Ventola spenta (0%)\n",
        CYAN,
    )

    high = ask("Soglia temperatura alta in °C (default 80)", "80")
    mid  = ask("Soglia temperatura media in °C (default 60)", "60")

    try:
        high_val = int(high)
        mid_val  = int(mid)
    except ValueError:
        cprint("Valori non validi, uso i default.", YELLOW)
        high_val, mid_val = 80, 60

    if high_val <= mid_val:
        cprint("⚠ La soglia alta deve essere > soglia media. Uso valori di default.", YELLOW)
        high_val, mid_val = 80, 60

    cprint("\nStabilizzazione termica (Anti-Hunting & Cooldown):", CYAN, bold=True)
    cprint(
        "  Evita che la ventola scatti al massimo per frazioni di secondo e crolli subito dopo\n"
        "  a causa di repentini burst della CPU (mantiene il regime per 10s e scende gradualmente).\n"
        "  ℹ Nota: La spiegazione dettagliata di questo comportamento è presente nel file README.md.\n",
        DIM,
    )

    enable_smoothing = ask_yes_no(
        "Abilitare la stabilizzazione della ventola (hold 10s + discesa graduale)?",
        default=True,
    )

    if enable_smoothing:
        hold_val = 10.0
        ramp_val = 10
        hyst_val = 3
        smoothing_summary = f"Attiva (Hold {hold_val:.0f}s, rampa {ramp_val}%, isteresi {hyst_val}°C)"
    else:
        hold_val = 0.0
        ramp_val = 100
        hyst_val = 0
        smoothing_summary = "Disattivata (risposta istantanea diretta)"

    cprint(
        f"\n✓ Configurazione soglie:\n"
        f"  > {high_val}°C  → {duty_high}%\n"
        f"  {mid_val}-{high_val}°C → 50%\n"
        f"  < {mid_val}°C  → 0%\n"
        f"  Stabilizzazione: {smoothing_summary}",
        GREEN,
    )

    return {
        "temp_threshold_high": high_val,
        "temp_threshold_mid":  mid_val,
        "temp_hysteresis":     hyst_val,
        "step_down_hold_seconds": hold_val,
        "ramp_down_step":      ramp_val,
        "duty_high":           duty_high,
        "duty_mid":            50,
        "duty_low":            0,
    }
