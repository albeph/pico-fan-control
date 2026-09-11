# pico-fan-control

> **Controllo ventola USB via Raspberry Pi Pico / RP2040 (Userspace IPC Daemon)**

[![Debian Package](https://img.shields.io/badge/Debian-Package-red?logo=debian)](https://github.com)
[![Linux](https://img.shields.io/badge/Linux-Userspace%20Daemon-blue?logo=linux)](https://github.com)
[![MicroPython](https://img.shields.io/badge/MicroPython-RP2040-green?logo=micropython)](https://github.com)
[![License: GPL v2](https://img.shields.io/badge/License-GPL%20v2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)

---

## Panoramica

`pico-fan-control` è un sistema completo per controllare una **ventola a 4 pin** tramite un **Raspberry Pi Pico (RP2040)** collegato via USB, sincronizzandola automaticamente con la ventola interna del sistema (ThinkPad o hwmon generico).

### Caratteristiche principali

| Feature | Dettaglio |
|---|---|
| **Firmware** | MicroPython su RP2040, PWM 25 kHz, tachimetro IRQ |
| **Architettura** | 100% Userspace IPC Unix Socket (`/run/pico-fan.sock`), nessun modulo kernel / zero kernel-headers |
| **Demone** | Fault-tolerant, riconnessione USB automatica, CPU < 0.1% |
| **Packaging** | Pacchetto `.deb` nativo per Debian / Ubuntu / Proxmox |
| **CLI Unificata** | Comando unico `pico-fan` con sottocomandi (`setup`, `status`, `manual`, `version`, `daemon`) |
| **Integrazione** | systemd, udev, journald |

---

## Architettura

```
                    ┌──────────────────────────────────────────┐
                    │            HOST LINUX                    │
                    │                                          │
  ┌──────────┐      │  ┌─────────────┐    ┌────────────────────────┐   │
  │ Ventola  │      │  │ fan_daemon  │───▶│ Socket IPC             │   │
  │ interna  │─────▶│  │   .py       │    │ UNIX (/run/            │   │
  │ (hwmon / │ RPM  │  │             │    │ pico-fan.sock)         │   │
  │  ACPI)   │      │  │  SET <duty> │    └───────┬────────────────┘   │
  └──────────┘      │  │  RPM query  │            │                    │
                    │  │             │            ▼                    │
  ┌──────────┐      │  └─────────────┘    ┌────────────────────────┐   │
  │ Pico     │◀─────│         │           │ pico-fan CLI           │   │
  │ RP2040   │ USB  │         ▼           │ (status / manual)      │   │
  └──────────┘ RPM  │  ┌─────────────┐    └────────────────────────┘   │
       │            │  │  journald   │                                 │
       │ PWM        │  └─────────────┘                                 │
       ▼            │                                                  │
  ┌──────────┐      └──────────────────────────────────────────────────┘
  │ Ventola  │
  │ esterna  │
  │ 4-pin    │
  └──────────┘
```

---

## Struttura del repository

> ℹ️ Per la mappa dettagliata e spiegazione di ogni singolo file, consulta STRUCTURE.md.

```
pico-fan-control/
├── VERSION                   # Versione del pacchetto (es. 1.1.7)
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
│   ├── main.py               # Dispatcher CLI unificato (pico-fan)
│   ├── setup_wizard.py       # Wizard CLI (pico-fan setup)
│   ├── status.py             # Diagnostica CLI (pico-fan status)
│   └── manual.py             # Controllo manuale (pico-fan manual)
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

> ℹ️ Risulta completamente funzionante anche con Raspberry Pi Pico 2W 

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

> **⚠️ Attenzione**: Non alimentare una ventola a 12V direttamente dal Pico. Andrebbe a velocità troppo basse
> Nel mio usecase, ho collegato la ventola con l'alimentatore da 12 V, ho fatto in modo che facesse contatto incastrando il jumper collegato al GND del Pico, con il Ground dell'alimentatore

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

# Oppure con VS Code + Extension per Raspberry Pi Pico (tool grafico)
```

### 3. Esegui il wizard di configurazione

```bash
sudo pico-fan setup
```

Il wizard guiderà attraverso:
- ✅ Rilevamento automatico del Pico in `/dev/serial/by-id/`
- ✅ Test della ventola (25% → 50% → 100% → 0%)
- ✅ Ricerca e impostazione automatica del **duty cycle ottimale** per la velocità massima
- ✅ Selezione della ventola interna da monitorare
- ✅ Configurazione soglie RPM
- ✅ Salvataggio in `/etc/pico-fan/config.json`


### 4. Avvia il demone

```bash
sudo systemctl start pico-fan
sudo systemctl enable pico-fan   # Avvio automatico al boot
```

---

## Interfaccia CLI `pico-fan`

Tutti i comandi sono centralizzati nell'eseguibile unico `pico-fan`:

```bash
# Mostra la guida dei comandi disponibili
pico-fan

# Diagnostica istantanea: RPM interno, RPM Pico, duty %, porta seriale
pico-fan status

# Controllo manuale temporaneo (es. porta la ventola al 75% e monitora i giri; Ctrl+C ripristina il controllo automatico)
pico-fan manual 75

# Esegui il wizard di configurazione (richiede root)
sudo pico-fan setup

# Visualizza versione installata
pico-fan version
```


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

## Sviluppo e test

```bash
# Test suite completa (senza hardware)
make test

# Test rapido (solo sintassi Python e Bash)
make test-quick

# Test con Pico collegato
make test-hw

# Genera pacchetto .deb
make deb

# Pulizia file temporanei di build
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

### Il demone non si avvia
Verifica lo stato del servizio systemd:
```bash
sudo systemctl status pico-fan
journalctl -u pico-fan -n 50 --no-pager
```
*Se il file di configurazione `/etc/pico-fan/config.json` è mancante, esegui prima:*
```bash
sudo pico-fan setup
sudo systemctl restart pico-fan
```

### Il comando `pico-fan status` o `manual` dice "connessione rifiutata / socket non trovato"
Assicurati che il demone sia attivo:
```bash
sudo systemctl status pico-fan
ls -l /run/pico-fan.sock
```

---

## Licenza

GPL v2 — Vedi [LICENSE](LICENSE) per i dettagli.
