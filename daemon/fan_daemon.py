#!/usr/bin/env python3
"""
fan_daemon.py - Main RPM Synchronization Daemon
=================================================
Reads internal system fan RPM (from /proc/acpi/ibm/fan or hwmon)
and dynamically controls the external USB fan (Raspberry Pi Pico)
according to configurable RPM thresholds and duty cycles.

Operating curve overview:
  Internal RPM > 4000  -> External fan at 100% (SET 100)
  2500 <= RPM <= 4000 -> External fan at 50%  (SET 50)
  Internal RPM < 2500  -> External fan at 0%   (SET 0)
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

try:
    from temp_reader import read_temperature, compute_target_duty_temp
except ImportError:
    raise SystemExit("Errore: temp_reader non disponibile")

try:
    from source_adapters import get_source_adapter, SourceAdapter
except ImportError:
    raise SystemExit("Errore: source_adapters non disponibile")

try:
    from duty_stabilizer import DutyStabilizer
except ImportError:
    raise SystemExit("Errore: duty_stabilizer non disponibile")

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logger = logging.getLogger("fan_daemon")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CONFIG_PATH     = "/etc/pico-fan/config.json"
DEFAULT_CONFIG  = {
    "pico_serial_by_id":  "",
    "internal_fan_type":  "ibm_acpi",
    "control_source":     "rpm",       # 'rpm' (internal fan) or 'temp' (temperature sensor)
    "rpm_threshold_high": 4000,
    "rpm_threshold_mid":  2500,
    "duty_high":          100,
    "duty_mid":           50,
    "duty_low":           0,
    "poll_interval":      2.0,
    "reconnect_interval": 5.0,
    "hwmon_fan_path":      "",    # Auto-detected if empty
    "ibm_fan_path":       "/proc/acpi/ibm/fan",
    "hwmon_temp_path":    "",     # Temperature sensor path (auto-detected if empty)
    "temp_threshold_high": 80,   # °C above which duty_high is applied
    "temp_threshold_mid":  60,   # °C above which duty_mid is applied
    "step_down_hold_seconds": 10.0, # Delay (s) before stepping down duty
    "ramp_down_step":     10,    # Duty % decremented per cycle after hold expires
    "temp_hysteresis":    3,     # °C hysteresis to prevent flapping at threshold borders
}

# ===========================================================================
# Internal fan RPM reading
# ===========================================================================

def read_internal_rpm_ibm(ibm_fan_path: str) -> Optional[int]:
    """
    Reads RPM from /proc/acpi/ibm/fan (ThinkPad).
    Expected line format: "speed:      2800"
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
    Reads RPM from hwmon.

    If a specific file is given, reads only that path; otherwise discovers the first
    valid reading in /sys/class/hwmon/hwmon*/fan*_input.
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
        # Search fan*_input files in this hwmon directory
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
    Reads RPM from the chosen internal fan source.
    """
    selected_type = config.get("internal_fan_type", "ibm_acpi")
    ibm_path = config.get("ibm_fan_path", DEFAULT_CONFIG["ibm_fan_path"])
    hwmon_path = config.get("hwmon_fan_path", "")

    # Prioritize the source selected during the setup wizard
    if selected_type == "hwmon":
        rpm = read_internal_rpm_hwmon(hwmon_path)
    else:
        rpm = read_internal_rpm_ibm(ibm_path)

    if rpm is not None:
        return rpm
    else:
        return 0


# ===========================================================================
# Fan curve: target duty calculation
# ===========================================================================

def compute_target_duty(rpm: int, config: dict) -> int:
    """
    Computes target duty cycle based on internal RPM and configured thresholds.
    Delegates to RpmSourceAdapter.
    """
    from source_adapters import RpmSourceAdapter
    return RpmSourceAdapter(config).compute_duty(rpm)


# ===========================================================================
# FanDaemon Class
# ===========================================================================

class FanDaemon:
    """
    Main daemon: manages serial connection lifecycle, reads internal RPM,
    controls external fan with fault tolerance, and serves IPC requests.
    """

    def __init__(self, config: dict):
        self.config          = config
        self.source_adapter  = get_source_adapter(config)
        self.running         = True
        self.current_duty    = -1          # -1 = not yet transmitted
        self.pico_adapter: Optional[PicoAdapter] = None
        self.pico_port: str  = ""
        self.pico_rpm: int   = 0
        self.internal_rpm: int = 0
        self.source_value: float = 0.0     # Current source reading (RPM or °C)
        self.sock_path       = "/run/pico-fan.sock"
        self._lock           = threading.Lock()
        self._stop_event     = threading.Event()  # used for interruptible sleep without busy-polling
        self.manual_mode     = False              # True when user has taken manual control
        self.manual_duty     = 0                  # Manually specified duty cycle

        hold_sec = float(config.get("step_down_hold_seconds", DEFAULT_CONFIG["step_down_hold_seconds"]))
        ramp_st  = int(config.get("ramp_down_step", DEFAULT_CONFIG["ramp_down_step"]))
        self.stabilizer      = DutyStabilizer(
            hold_seconds=hold_sec,
            ramp_step=ramp_st,
            initial_duty=self.current_duty,
        )

    # -------------------------------------------------------------------
    # Initial setup and IPC
    # -------------------------------------------------------------------

    def _start_ipc_server(self) -> None:
        """Starts a UNIX domain socket server to serve status and control to CLI clients."""
        if os.path.exists(self.sock_path):
            try:
                os.remove(self.sock_path)
            except OSError:
                pass
        
        try:
            self.server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_sock.bind(self.sock_path)
            self.server_sock.listen(5)
            os.chmod(self.sock_path, 0o600)  # Accessible only to daemon and root
        except Exception as exc:
            logger.error("Impossibile creare socket IPC: %s", exc)
            return
        def _server_loop():
            while self.running:
                try:
                    self.server_sock.settimeout(1.0)
                    conn, _ = self.server_sock.accept()
                    try:
                        # Read command from client (max 64 bytes)
                        conn.settimeout(0.5)
                        try:
                            raw = conn.recv(64).decode("utf-8", errors="replace").strip()
                        except socket.timeout:
                            raw = ""

                        if raw.upper().startswith("SET "):
                            # Manual mode: set fixed duty cycle and suspend automatic control
                            try:
                                duty = max(0, min(100, int(raw.split()[1])))
                                with self._lock:
                                    self.manual_mode = True
                                    self.manual_duty = duty
                                    self.stabilizer.reset(duty)
                                    self.current_duty = -1  # force re-transmission on next cycle
                                logger.info("Modalità manuale attivata: duty=%d%%", duty)
                                conn.sendall(b"OK\n")
                            except (ValueError, IndexError):
                                conn.sendall(b"ERR duty non valido\n")

                        elif raw.upper() == "RESUME":
                            # Restore automatic control
                            with self._lock:
                                self.manual_mode = False
                                self.stabilizer.reset(self.current_duty if self.current_duty >= 0 else 0)
                                self.current_duty = -1  # force re-transmission on next cycle
                            logger.info("Controllo automatico ripristinato")
                            conn.sendall(b"OK\n")

                        else:
                            # STATUS (or empty command): respond with current state JSON
                            with self._lock:
                                is_temp = self.source_adapter.name == "temp"
                                state = {
                                    "connected":        self.pico_adapter is not None and self.pico_adapter.connected,
                                    "pico_port":        self.pico_port,
                                    "control_source":   self.source_adapter.name,
                                    "source_value":     self.source_value,
                                    "source_formatted": self.source_adapter.format_value(self.source_value),
                                    "internal_rpm":     self.internal_rpm,
                                    "pico_rpm":         self.pico_rpm,
                                    "current_duty":     self.current_duty if self.current_duty >= 0 else 0,
                                    "target_duty":      self.stabilizer.target_duty if is_temp else (self.current_duty if self.current_duty >= 0 else 0),
                                    "hold_active":      self.stabilizer.is_holding if is_temp else False,
                                    "hold_remaining":   round(self.stabilizer.hold_remaining, 1) if is_temp else 0.0,
                                    "ramp_active":      self.stabilizer.is_ramping if is_temp else False,
                                    "manual_mode":      self.manual_mode,
                                    "version":          __version__,
                                }
                            conn.sendall((json.dumps(state) + "\n").encode("utf-8"))

                    finally:
                        conn.close()

                except socket.timeout:
                    continue  # expected: check self.running again
                except Exception as exc:
                    if self.running:
                        logger.error("Errore IPC client: %s", exc)

        self.ipc_thread = threading.Thread(target=_server_loop, daemon=True)
        self.ipc_thread.start()

    def _stop_ipc_server(self) -> None:
        """Stops the IPC socket server and cleans up the socket file."""
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
        """Initializes Pico device path and IPC server."""
        # Resolve serial path
        by_id = self.config.get("pico_serial_by_id", "")
        if not by_id:
            raise ValueError(
                "pico_serial_by_id non configurato. "
                "Eseguire prima: pico-fan-setup"
            )

        real_path = os.path.realpath(by_id)
        if not os.path.exists(real_path):
            logger.warning("Pico non connesso al boot, tentativo di connessione differita")
            self.pico_port = real_path    # Save for retry
        else:
            self.pico_port = real_path
        
        self._start_ipc_server()

    # -------------------------------------------------------------------
    # Serial connection management
    # -------------------------------------------------------------------

    def _try_connect(self) -> bool:
        """
        Attempts to open serial connection with the Pico.
        Returns True if successful.
        """
        try:
            # Re-resolve symlink (device node may have changed)
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
        """Closes serial connection cleanly."""
        if self.pico_adapter:
            self.pico_adapter.disconnect()
            self.pico_adapter = None
            logger.info("Connessione seriale chiusa")

    # -------------------------------------------------------------------
    # Main loop
    # -------------------------------------------------------------------

    def run(self) -> None:
        """
        Main daemon loop:
        1. Connection / reconnection (with retry)
        2. Read internal fan RPM
        3. Compute target duty cycle
        4. Transmit command on duty change
        5. Read external fan RPM
        """
        poll_interval      = self.config.get("poll_interval",      DEFAULT_CONFIG["poll_interval"])
        reconnect_interval = self.config.get("reconnect_interval", DEFAULT_CONFIG["reconnect_interval"])

        logger.info("Demone avviato. PID=%d versione=%s", os.getpid(), __version__)

        while self.running:
            # ----------------------------------------------------------------
            # Phase 1: Connection / reconnection
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
            # Phase 2: Read source value via Adapter
            # ----------------------------------------------------------------
            self.source_value = self.source_adapter.read()
            if self.source_adapter.name == "rpm":
                self.internal_rpm = int(self.source_value)
            else:
                self.internal_rpm = 0

            logger.debug(
                "Lettura sorgente [%s]: %s",
                self.source_adapter.name,
                self.source_adapter.format_value(self.source_value),
            )

            # ----------------------------------------------------------------
            # Phase 3: Calculate duty and send command (only on change)
            # ----------------------------------------------------------------
            with self._lock:
                in_manual = self.manual_mode
                man_duty  = self.manual_duty

            if in_manual:
                target_duty = man_duty
                self.stabilizer.reset(man_duty)
            else:
                raw_target = self.source_adapter.compute_duty(self.source_value)
                if self.source_adapter.name == "temp":
                    target_duty = self.stabilizer.update(raw_target)
                else:
                    target_duty = raw_target

            if target_duty != self.current_duty:
                source_str = self.source_adapter.format_value(self.source_value)
                extra = ""
                if in_manual:
                    extra = " [MANUALE]"
                elif self.source_adapter.name == "temp" and self.stabilizer.is_ramping:
                    extra = f" [RAMPA -> {self.stabilizer.target_duty}%]"
                logger.info(
                    "Cambio duty: %s%% -> %s%% (%s%s)",
                    self.current_duty if self.current_duty >= 0 else "N/A",
                    target_duty,
                    source_str,
                    extra,
                )
                success = self.pico_adapter.set_duty(target_duty)
                if success:
                    self.current_duty = target_duty
                else:
                    logger.warning("Invio comando SET fallito")
            elif not in_manual and self.source_adapter.name == "temp" and self.stabilizer.is_holding:
                logger.debug(
                    "Hold attivo su duty=%d%% (target grezzo=%d%%, %.1fs rimanenti)",
                    self.current_duty,
                    self.stabilizer.target_duty,
                    self.stabilizer.hold_remaining,
                )

            # ----------------------------------------------------------------
            # Phase 4: Read external fan RPM
            # ----------------------------------------------------------------
            pico_rpm, _ = self.pico_adapter.fetch_rpm()
            self.pico_rpm = pico_rpm or 0
            logger.debug("RPM ventola esterna: %d", self.pico_rpm)

            self._sleep_interruptible(poll_interval)

        # Cleanup on exit
        self._disconnect()
        self._stop_ipc_server()
        logger.info("Demone terminato")

    def _sleep_interruptible(self, seconds: float) -> None:
        """Interruptible blocking sleep until timeout or stop() signal.
        Uses threading.Event: zero unnecessary wakeups, thread remains idle
        until timeout expires or stop is signaled.
        """
        self._stop_event.wait(timeout=seconds)

    def stop(self) -> None:
        """Signals the daemon to terminate its main loop."""
        logger.info("Richiesta di stop ricevuta")
        self.running = False
        self._stop_event.set()  # Immediately wake up any active sleep


# ===========================================================================
# Configuration loading
# ===========================================================================

def load_config(path: str = CONFIG_PATH) -> dict:
    """Loads configuration from JSON file, falling back to defaults."""
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
    """Configures stdout logging (captured automatically by systemd/journald)."""
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

    # POSIX signal handling
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
