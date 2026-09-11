#!/usr/bin/env python3
"""
fan_daemon.py - Demone principale di sincronizzazione RPM
==========================================================

Legge gli RPM della ventola interna del ThinkPad (da /proc/acpi/ibm/fan
o da hwmon) e controlla la ventola esterna USB (Pico) in base a soglie.

Curva di funzionamento:
  RPM interni > 4000  -> Ventola esterna a 100% (SET 100)
  2500 <= RPM <= 4000 -> Ventola esterna a 50%  (SET 50)
  RPM < 2500          -> Ventola esterna a 0%   (SET 0)

Autore:   pico-fan-control project
Versione: 1.0.0
"""

from __future__ import annotations

import os
import sys
import json
import socket
import signal
import logging
import threading
from pathlib import Path

from typing import Optional

try:
    from version import __version__
except ImportError:
    __version__ = "unknown"

try:
    from pico_adapter import PicoAdapter
    import serial.serialutil
except ImportError:
    raise SystemExit("Errore: pyserial o pico_adapter non disponibile")

# ---------------------------------------------------------------------------
# Configurazione logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("fan_daemon")

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------
CONFIG_PATH     = "/etc/pico-fan/config.json"
DEFAULT_CONFIG  = {
    "pico_serial_by_id":  "",
    "internal_fan_type":  "ibm_acpi",
    "rpm_threshold_high": 4000,
    "rpm_threshold_mid":  2500,
    "duty_high":          100,
    "duty_mid":           50,
    "duty_low":           0,
    "poll_interval":      2.0,
    "reconnect_interval": 5.0,
    "hwmon_fan_path":      "",    # Auto-rilevato se vuoto
    "ibm_fan_path":       "/proc/acpi/ibm/fan",
}

# ===========================================================================
# Lettura RPM ventola interna
# ===========================================================================

def read_internal_rpm_ibm(ibm_fan_path: str) -> Optional[int]:
    """
    Legge gli RPM da /proc/acpi/ibm/fan (ThinkPad).
    Formato atteso: "speed:      2800"
    """
    try:
        if not os.path.exists(ibm_fan_path):
            return None
        with open(ibm_fan_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("speed:"):
                    parts = line.split(":")
                    if len(parts) == 2:
                        return int(parts[1].strip())
    except (OSError, ValueError) as exc:
        logger.debug("Errore lettura %s: %s", ibm_fan_path, exc)
    return None


def read_internal_rpm_hwmon(fan_file: str | Path | None = None) -> Optional[int]:
    """
    Legge gli RPM da hwmon.

    Se viene indicato un file, legge solo quello; altrimenti cerca il primo
    valore disponibile in /sys/class/hwmon/hwmon*/fan*_input.
    """
    if fan_file is not None:
        try:
            if not Path(fan_file).exists():
                return None
            return int(Path(fan_file).read_text().strip())
        except (OSError, ValueError):
            return None

    base = Path("/sys/class/hwmon")
    if not base.exists():
        return None

    for hwmon_dir in sorted(base.iterdir()):
        # Cerca file fan*_input in questo hwmon
        for fan_file in sorted(hwmon_dir.glob("fan*_input")):
            try:
                rpm = int(fan_file.read_text().strip())
                if rpm > 0:
                    logger.debug("RPM interni da %s: %d", fan_file, rpm)
                    return rpm
            except (OSError, ValueError):
                continue

    return None


def read_internal_rpm(config: dict) -> int:
    """
    Legge gli RPM della ventola interna scelta
    """
    selected_type = config.get("internal_fan_type", "ibm_acpi")
    ibm_path = config.get("ibm_fan_path", DEFAULT_CONFIG["ibm_fan_path"])
    hwmon_path = config.get("hwmon_fan_path", "")

    # Prima prova esclusivamente la sorgente scelta dal wizard.
    if selected_type == "hwmon":
        rpm = read_internal_rpm_hwmon(hwmon_path)
    else:
        rpm = read_internal_rpm_ibm(ibm_path)

    if rpm is not None:
        return rpm
    else:
        return 0


# ===========================================================================
# Curva ventola: calcolo duty target
# ===========================================================================

def compute_target_duty(rpm: int, config: dict) -> int:
    """
    Calcola il duty cycle target basato sugli RPM interni e le soglie.
    """
    high_thr = config.get("rpm_threshold_high", DEFAULT_CONFIG["rpm_threshold_high"])
    mid_thr  = config.get("rpm_threshold_mid",  DEFAULT_CONFIG["rpm_threshold_mid"])
    d_high   = config.get("duty_high",           DEFAULT_CONFIG["duty_high"])
    d_mid    = config.get("duty_mid",            DEFAULT_CONFIG["duty_mid"])
    d_low    = config.get("duty_low",            DEFAULT_CONFIG["duty_low"])

    if rpm > high_thr:
        return d_high
    elif rpm >= mid_thr:
        return d_mid
    else:
        return d_low


# ===========================================================================
# Classe FanDaemon
# ===========================================================================

class FanDaemon:
    """
    Demone principale: gestisce il ciclo di vita della connessione seriale,
    legge gli RPM interni e controlla la ventola esterna in modo fault-tolerant.
    """

    def __init__(self, config: dict):
        self.config          = config
        self.running         = True
        self.current_duty    = -1          # -1 = non ancora inviato
        self.pico_adapter: Optional[PicoAdapter] = None
        self.pico_port: str  = ""
        self.pico_rpm: int   = 0
        self.internal_rpm: int = 0
        self.sock_path       = "/run/pico-fan.sock"
        self._lock           = threading.Lock()
        self._stop_event     = threading.Event()  # usato per sleep interrompibile senza polling
        self.manual_mode     = False              # True quando l'utente ha preso il controllo
        self.manual_duty     = 0                  # Duty impostato manualmente

    # -------------------------------------------------------------------
    # Setup iniziale e IPC
    # -------------------------------------------------------------------

    def _start_ipc_server(self) -> None:
        """Avvia un server socket UNIX per fornire lo stato alla CLI."""
        if os.path.exists(self.sock_path):
            try:
                os.remove(self.sock_path)
            except OSError:
                pass
        
        try:
            self.server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_sock.bind(self.sock_path)
            self.server_sock.listen(5)
            os.chmod(self.sock_path, 0o600)  # Accessibile solo al demone e a root
        except Exception as exc:
            logger.error("Impossibile creare socket IPC: %s", exc)
            return
        def _server_loop():
            while self.running:
                try:
                    self.server_sock.settimeout(1.0)
                    conn, _ = self.server_sock.accept()
                    try:
                        # Legge eventuale comando dal client (max 64 byte)
                        conn.settimeout(0.5)
                        try:
                            raw = conn.recv(64).decode("utf-8", errors="replace").strip()
                        except socket.timeout:
                            raw = ""

                        if raw.upper().startswith("SET "):
                            # Modalità manuale: imposta duty e sospende il controllo automatico
                            try:
                                duty = max(0, min(100, int(raw.split()[1])))
                                with self._lock:
                                    self.manual_mode = True
                                    self.manual_duty = duty
                                    self.current_duty = -1  # forza ri-invio al prossimo ciclo
                                logger.info("Modalità manuale attivata: duty=%d%%", duty)
                                conn.sendall(b"OK\n")
                            except (ValueError, IndexError):
                                conn.sendall(b"ERR duty non valido\n")

                        elif raw.upper() == "RESUME":
                            # Ripristina il controllo automatico
                            with self._lock:
                                self.manual_mode = False
                                self.current_duty = -1  # forza ri-invio al prossimo ciclo
                            logger.info("Controllo automatico ripristinato")
                            conn.sendall(b"OK\n")

                        else:
                            # STATUS (o nessun comando): risponde con lo stato corrente
                            with self._lock:
                                state = {
                                    "connected":    self.pico_adapter is not None and self.pico_adapter.connected,
                                    "pico_port":    self.pico_port,
                                    "internal_rpm": self.internal_rpm,
                                    "pico_rpm":     self.pico_rpm,
                                    "current_duty": self.current_duty if self.current_duty >= 0 else 0,
                                    "manual_mode":  self.manual_mode,
                                    "version":      __version__,
                                }
                            conn.sendall((json.dumps(state) + "\n").encode("utf-8"))

                    finally:
                        conn.close()

                except socket.timeout:
                    continue  # atteso: ricontrolla self.running
                except Exception as exc:
                    if self.running:
                        logger.error("Errore IPC client: %s", exc)

        self.ipc_thread = threading.Thread(target=_server_loop, daemon=True)
        self.ipc_thread.start()

    def _stop_ipc_server(self) -> None:
        """Ferma il server socket IPC e ripulisce il file."""
        if hasattr(self, "server_sock"):
            try:
                self.server_sock.close()
            except Exception:
                pass
        if os.path.exists(self.sock_path):
            try:
                os.remove(self.sock_path)
            except OSError:
                pass

    def setup(self) -> None:
        """Inizializza il path del dispositivo Pico."""
        # Risolvi path seriale
        by_id = self.config.get("pico_serial_by_id", "")
        if not by_id:
            raise ValueError(
                "pico_serial_by_id non configurato. "
                "Eseguire prima: pico-fan-setup"
            )

        real_path = os.path.realpath(by_id)
        if not os.path.exists(real_path):
            logger.warning("Pico non connesso al boot, tentativo di connessione differita")
            self.pico_port = real_path    # Salva per retry
        else:
            self.pico_port = real_path
        
        self._start_ipc_server()

    # -------------------------------------------------------------------
    # Gestione connessione seriale
    # -------------------------------------------------------------------

    def _try_connect(self) -> bool:
        """
        Tenta di aprire la connessione seriale con il Pico.
        Restituisce True se riuscito.
        """
        try:
            # Risolvi di nuovo il symlink (potrebbe essere cambiato)
            by_id = self.config.get("pico_serial_by_id", "")
            real_path = os.path.realpath(by_id) if by_id else self.pico_port

            if not os.path.exists(real_path):
                logger.debug("Device %s non presente", real_path)
                return False

            adapter = PicoAdapter(real_path)
            adapter.connect()
            self.pico_adapter = adapter
            self.pico_port   = real_path
            logger.info("Connesso a Pico su %s", real_path)
            return True

        except serial.serialutil.SerialException as exc:
            logger.debug("Connessione fallita: %s", exc)
            return False

    def _disconnect(self) -> None:
        """Chiude la connessione seriale in modo sicuro."""
        if self.pico_adapter:
            self.pico_adapter.disconnect()
            self.pico_adapter = None
            logger.info("Connessione seriale chiusa")

    # -------------------------------------------------------------------
    # Loop principale
    # -------------------------------------------------------------------

    def run(self) -> None:
        """
        Ciclo principale del demone:
        1. Connessione (con retry)
        2. Lettura RPM interni
        3. Calcolo duty target
        4. Invio comando solo al cambio soglia
        5. Lettura RPM ventola esterna
        """
        poll_interval      = self.config.get("poll_interval",      DEFAULT_CONFIG["poll_interval"])
        reconnect_interval = self.config.get("reconnect_interval", DEFAULT_CONFIG["reconnect_interval"])

        logger.info("Demone avviato. PID=%d versione=%s", os.getpid(), __version__)

        while self.running:
            # ----------------------------------------------------------------
            # Fase 1: Connessione / riconnessione
            # ----------------------------------------------------------------
            if self.pico_adapter is None or not self.pico_adapter.connected:
                connected = self._try_connect()
                if not connected:
                    logger.info(
                        "Pico non raggiungibile, nuovo tentativo tra %ds",
                        reconnect_interval
                    )
                    self._sleep_interruptible(reconnect_interval)
                    continue

            # ----------------------------------------------------------------
            # Fase 2: Lettura RPM interni
            # ----------------------------------------------------------------
            self.internal_rpm = read_internal_rpm(self.config)
            logger.debug("RPM interni: %d", self.internal_rpm)

            # ----------------------------------------------------------------
            # Fase 3: Calcolo duty e invio comando (solo al cambio)
            # ----------------------------------------------------------------
            with self._lock:
                in_manual = self.manual_mode
                man_duty  = self.manual_duty

            if in_manual:
                target_duty = man_duty
            else:
                target_duty = compute_target_duty(self.internal_rpm, self.config)

            if target_duty != self.current_duty:
                logger.info(
                    "Cambio duty: %s%% -> %s%% (RPM interni: %d%s)",
                    self.current_duty if self.current_duty >= 0 else "N/A",
                    target_duty,
                    self.internal_rpm,
                    " [MANUALE]" if in_manual else "",
                )
                success = self.pico_adapter.set_duty(target_duty)
                if success:
                    self.current_duty = target_duty
                else:
                    logger.warning("Invio comando SET fallito")

            # ----------------------------------------------------------------
            # Fase 4: Lettura RPM ventola esterna
            # ----------------------------------------------------------------
            pico_rpm, _ = self.pico_adapter.fetch_rpm()
            self.pico_rpm = pico_rpm or 0
            logger.debug("RPM ventola esterna: %d", self.pico_rpm)

            self._sleep_interruptible(poll_interval)

        # Cleanup all'uscita
        self._disconnect()
        self._stop_ipc_server()
        logger.info("Demone terminato")

    def _sleep_interruptible(self, seconds: float) -> None:
        """Sleep bloccante interrompibile da stop().
        Usa threading.Event: zero wakeup inutili, il thread rimane idle finché
        non scade il timeout o viene segnalato lo stop.
        """
        self._stop_event.wait(timeout=seconds)

    def stop(self) -> None:
        """Segnala al demone di terminare il ciclo principale."""
        logger.info("Richiesta di stop ricevuta")
        self.running = False
        self._stop_event.set()  # Sveglia immediatamente qualsiasi sleep in corso


# ===========================================================================
# Caricamento configurazione
# ===========================================================================

def load_config(path: str = CONFIG_PATH) -> dict:
    """Carica la configurazione da file JSON, usando i default se mancante."""
    config = dict(DEFAULT_CONFIG)
    try:
        with open(path) as f:
            user_cfg = json.load(f)
            config.update(user_cfg)
            logger.info("Configurazione caricata da %s", path)
    except FileNotFoundError:
        logger.warning("Config %s non trovato, uso valori di default", path)
    except json.JSONDecodeError as exc:
        logger.error("Errore JSON in %s: %s. Uso valori di default.", path, exc)
    return config


# ===========================================================================
# Entry point
# ===========================================================================

def setup_logging() -> None:
    """Configura logging verso stdout (catturato automaticamente da systemd/journald)."""
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> None:
    setup_logging()

    config = load_config()
    daemon = FanDaemon(config)

    # Gestione segnali POSIX
    def _handle_signal(signum, frame):  # noqa: ARG001
        logger.info("Ricevuto segnale %d", signum)
        daemon.stop()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT,  _handle_signal)

    try:
        daemon.setup()
        daemon.run()
    except ValueError as exc:
        logger.error("Configurazione non valida: %s", exc)
        sys.exit(1)
    except Exception as exc:  # pylint: disable=broad-except
        logger.critical("Errore fatale: %s", exc, exc_info=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
