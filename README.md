# pico-fan-control

> **Controllo ventola USB via Raspberry Pi Pico / RP2040 (Userspace IPC Daemon)**

[![Debian Package](https://img.shields.io/badge/Debian-Package-red?logo=debian)](https://github.com)
[![Kernel](https://img.shields.io/badge/Kernel-5.x%20%7C%206.x%20%7C%207.x-blue?logo=linux)](https://github.com)
[![MicroPython](https://img.shields.io/badge/MicroPython-RP2040-green?logo=micropython)](https://github.com)
[![License: GPL v2](https://img.shields.io/badge/License-GPL%20v2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)

---

## Panoramica

`pico-fan-control` è un sistema completo per controllare una **ventola a 4 pin** tramite un **Raspberry Pi Pico (RP2040)** collegato via USB, sincronizzandola automaticamente con la ventola interna del sistema (ThinkPad o hwmon generico).

### Caratteristiche principali

| Feature | Dettaglio |
|---|---|
| **Firmware** | MicroPython su RP2040, PWM 25 kHz, tachimetro IRQ |
| **Architettura** | Userspace IPC Unix Socket (`/run/pico-fan.sock`), zero kernel-headers |
| **Demone** | Fault-tolerant, riconnessione USB automatica, CPU < 0.1% |
| **Packaging** | Pacchetto `.deb` nativo per Debian / Ubuntu / Proxmox |
| **Setup & Status** | Wizard CLI `pico-fan-setup` e diagnostica `pico-fan-status` |
| **Integrazione** | systemd, udev, journald |

---

## Architettura

```
                    ┌──────────────────────────────────────────┐
                    │            HOST LINUX                    │
                    │                                          │
  ┌──────────┐      │  ┌─────────────┐    ┌────────────────┐  │
  │ Ventola  │      │  │ fan_daemon  │───▶│ Socket IPC     │  │
  │ interna  │─────▶│  │   .py       │    │ UNIX (/run/    │  │
  │ (hwmon / │ RPM  │  │             │    │ pico-fan.sock) │  │
  │  ACPI)   │      │  │  SET <duty> │    └───────┬────────┘  │
  └──────────┘      │  │  RPM query  │            │           │
                    │  │             │            ▼           │
  ┌──────────┐      │  └─────────────┘    ┌────────────────┐  │
  │ Pico     │◀─────│         │           │pico-fan-status │  │
  │ RP2040   │ USB  │         ▼           │ (CLI client)   │  │
  └──────────┘ RPM  │  ┌─────────────┐    └────────────────┘  │
       │            │  │  journald   │                        │
       │ PWM        │  └─────────────┘                        │
       ▼            │                                         │
  ┌──────────┐      └──────────────────────────────────────────┘
  │ Ventola  │
  │ esterna  │
  │ 4-pin    │
  └──────────┘
```

---

## Struttura del repository

> ℹ️ Per la mappa dettagliata e spiegazione di ogni singolo file, consulta [STRUCTURE.md](file:///home/user/Projects/pico-fan-control/STRUCTURE.md).

```
pico-fan-control/
├── VERSION                   # Versione del pacchetto (es. 1.0.6)
├── Makefile                  # Build, test e packaging
├── README.md                 # Guida rapida e panoramica
├── STRUCTURE.md              # Descrizione dettagliata dell'albero delle directory
├── RELAZIONE_PROGETTO.md     # Report completo di sviluppo e cronologia dei round
├── firmware/
│   └── main.py               # Firmware MicroPython RP2040
├── daemon/
│   ├── fan_daemon.py         # Demone sincronizzazione RPM e IPC server
│   ├── hardware_detector.py # Scanner porte seriali Pico
│   └── version.py            # Risoluzione versione runtime
├── cli/
│   ├── main.py               # Eseguibile unificato pico-fan
│   ├── setup_wizard.py       # Sottocomando 'setup' (wizard interattivo)
│   ├── status.py             # Sottocomando 'status' (diagnostica IPC)
│   └── manual.py             # Sottocomando 'set' / 'manual' (controllo manuale)
├── systemd/
│   └── pico-fan.service      # Unit systemd
├── udev/
│   └── 99-pico-fan.rules       # Permessi seriale + symlink
├── debian/
│   ├── control                 # Metadati pacchetto
│   ├── postinst                # Hook post-install
│   ├── prerm                   # Hook pre-rimozione
│   └── postrm                  # Hook post-rimozione
├── configs/
│   └── config.json.example    # Template configurazione
├── scripts/
│   ├── build_deb.sh           # Build pacchetto .deb
│   └── test_local.sh          # Test suite locale
├── Makefile                    # Target principali
└── README.md                   # Questa documentazione
```

---

## Requisiti hardware

### Raspberry Pi Pico / RP2040
- Qualsiasi scheda basata su RP2040 con USB CDC
- MicroPython >= 1.20 installato
- Cavo USB-A ↔ micro-USB (o USB-C a seconda del modello)

### Ventola
- Ventola a **4 pin** standard (12V o 5V)
- Connettore: +V, GND, TACH (segnale), PWM (controllo)

### Piedinatura hardware

```
Ventola (4 pin)          Raspberry Pi Pico
─────────────────────────────────────────────
Pin 1 - GND          ──▶  GND (es. Pin 38)
Pin 2 - +12V/5V      ──▶  Alimentazione esterna (non dal Pico!)
Pin 3 - TACH (verde) ──▶  GP14 (Pin 19)
Pin 4 - PWM  (blu)   ──▶  GP15 (Pin 20)
```

> **⚠️ Attenzione**: Non alimentare una ventola a 12V direttamente dal Pico.
> Utilizzare un alimentatore esterno da 12V con GND comune.

### Schema di collegamento

```
Alimentatore 12V
    +12V ──────────────────────────────▶ Pin 2 ventola
    GND  ──────┬──────────────────────▶ Pin 1 ventola
               │
    Pico GND ──┘  (GND comune OBBLIGATORIO)
    Pico GP15 ────(resistore 1kΩ pull-up opzionale)──▶ Pin 4 ventola (PWM)
    Pico GP14 ◀───(diretta o con resistore 10kΩ)────── Pin 3 ventola (TACH)
```

---

## Installazione rapida

### 1. Installa il pacchetto Debian

```bash
# Genera il pacchetto
make deb

# Installa
sudo dpkg -i pico-fan_1.0.0_all.deb

# Risolvi eventuali dipendenze mancanti
sudo apt -f install
```

### 2. Carica il firmware sul Pico

```bash
# Con mpremote (installare: pip install mpremote)
mpremote connect /dev/ttyACM0 cp firmware/main.py :main.py

# Oppure con Thonny IDE (tool grafico)
```

### 3. Esegui il wizard di configurazione

```bash
sudo pico-fan-setup
```

Il wizard guiderà attraverso:
- ✅ Rilevamento automatico del Pico in `/dev/serial/by-id/`
- ✅ Test della ventola (25% → 50% → 100% → 0%)
- ✅ Selezione della ventola interna da monitorare
- ✅ Configurazione soglie RPM
- ✅ Salvataggio in `/etc/pico-fan/config.json`

### 4. Carica il modulo kernel

```bash
sudo modprobe pico_fan_hwmon
```

### 5. Avvia il demone

```bash
sudo systemctl start pico-fan
sudo systemctl enable pico-fan   # Avvio automatico
```

### 6. Verifica

```bash
sensors
# Output esempio:
# pico_fan-virtual-0
# Adapter: Virtual device
# fan1:       2850 RPM
# pwm1:          50 (50%)

systemctl status pico-fan
journalctl -u pico-fan -f
```

---

## Protocollo seriale

Il firmware risponde sulla porta USB CDC a 115200 baud.

| Comando | Risposta | Descrizione |
|---|---|---|
| `RPM` | `RPM:2850 DUTY:50%` | Legge RPM e duty corrente |
| `GET` | `RPM:2850 DUTY:50%` | Alias per RPM |
| `SET 75` | `OK` | Imposta duty al 75% |
| `75` | `OK` | Alias numerico per SET |

```bash
# Test manuale
echo "RPM" | sudo tee /dev/ttyACM0
cat /dev/ttyACM0

# Oppure con minicom
minicom -D /dev/ttyACM0 -b 115200
```

---

## Curva di funzionamento

| RPM ventola interna | Duty ventola esterna |
|---|---|
| > 4000 RPM | **100%** (massima velocità) |
| 2500 – 4000 RPM | **50%** (velocità media) |
| < 2500 RPM | **0%** (spenta) |

Le soglie sono configurabili in `/etc/pico-fan/config.json`.

---

## Configurazione

File: `/etc/pico-fan/config.json`

```json
{
  "pico_serial_by_id":  "/dev/serial/by-id/usb-MicroPython_Board_...",
  "ibm_fan_path":       "/proc/acpi/ibm/fan",
  "rpm_threshold_high": 4000,
  "rpm_threshold_mid":  2500,
  "duty_high":          100,
  "duty_mid":           50,
  "duty_low":           0,
  "poll_interval":      2.0,
  "reconnect_interval": 5.0
}
```

---

## Comandi CLI pico-fan

Tutte le operazioni sono gestite dal comando unificato `pico-fan`:

```bash
# Mostra la guida dei comandi
pico-fan

# Visualizza lo stato corrente (connessione, RPM interni, RPM Pico, duty)
pico-fan status

# Imposta manualmente la velocità e monitora gli RPM (Ctrl+C per ripristinare auto)
pico-fan set 75
# oppure:
pico-fan manual 75

# Esegui il wizard guidato di configurazione
sudo pico-fan setup

# Mostra la versione installata
pico-fan version

# Gestione servizio di sistema
sudo systemctl restart pico-fan
sudo systemctl status pico-fan
```

---

## Sviluppo e test

```bash
# Test suite completa (senza hardware)
make test

# Test rapido (solo sintassi)
make test-quick

# Test con Pico collegato
make test-hw

# Compila solo il modulo kernel
make build

# Pulizia
make clean
```

---

## Rimozione

```bash
# Rimuove pacchetto (conserva /etc/pico-fan/config.json)
sudo apt remove pico-fan

# Rimozione completa inclusa configurazione
sudo apt purge pico-fan
```

---

## Troubleshooting

### Il Pico non viene rilevato
```bash
ls /dev/serial/by-id/
lsusb | grep -i "2e8a"
dmesg | tail -20 | grep -i "usb\|cdc\|acm"
```

### Il socket IPC non risponde
```bash
# Verifica lo stato del servizio systemd
sudo systemctl status pico-fan

# Visualizza i log in tempo reale
journalctl -u pico-fan -f

# Se necessario, riavvia il servizio
sudo systemctl restart pico-fan
```

### Il demone non si avvia
```bash
# Controlla gli ultimi 50 log di avvio
journalctl -u pico-fan -n 50

# Verifica se il file di configurazione è presente o riesegui il setup:
sudo pico-fan setup
```

---

## Licenza

GPL v2 — Vedi [LICENSE](LICENSE) per i dettagli.

Il modulo kernel `pico_fan_hwmon.c` è rilasciato sotto GPL v2 come richiesto
dal kernel Linux.
