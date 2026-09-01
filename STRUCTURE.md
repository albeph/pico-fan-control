# Struttura del Progetto: pico-fan-control

Questo documento descrive in dettaglio la struttura delle directory, l'organizzazione dei file e l'interazione tra i componenti del sistema `pico-fan-control` (v1.0.6).

---

## 🌳 Albero del Repository

```
pico-fan-control/
├── VERSION                   # File versione sorgente del progetto (es. 1.0.6)
├── Makefile                  # Automation script per build, test, deb e versioning
├── README.md                 # Guida rapida e panoramica del progetto
├── RELAZIONE_PROGETTO.md     # Relazione tecnica completa sullo sviluppo e i vari round
├── STRUCTURE.md              # Questo file - mappa dettagliata della struttura
├── .gitignore                # Regole di esclusione Git per file temporanei e build
│
├── firmware/                 # Firmware per il microcontrollore
│   └── main.py               # Script MicroPython da caricare sul Raspberry Pi Pico (RP2040)
│
├── daemon/                   # Servizio backend in ascolto sul sistema Host
│   ├── fan_daemon.py         # Demone principale (loop RPM, soglie hysteresis, server IPC)
│   ├── hardware_detector.py # Scansione e probe dispositivi RP2040 in /dev/serial/by-id/
│   └── version.py            # Utility per la risoluzione dinamica della versione runtime
│
├── cli/                      # Strumenti di interfaccia a riga di comando (User Tools)
│   ├── setup_wizard.py       # Eseguibile pico-fan-setup: wizard interattivo di configurazione
│   └── status.py             # Eseguibile pico-fan-status: client IPC per lo stato in tempo reale
│
├── systemd/                  # Configurazione del servizio di sistema
│   └── pico-fan.service      # Unit file systemd per l'avvio automatico al boot
│
├── udev/                     # Regole di gestione dispositivi hardware Linux
│   └── 99-pico-fan.rules     # Permessi gruppo dialout e symlink /dev/pico-fan
│
├── debian/                   # Metadata e script per la creazione del pacchetto .deb
│   ├── control               # Metadati del pacchetto Debian (dipendenze, descrizione)
│   ├── postinst              # Hook post-installazione (attiva systemd e udev)
│   ├── prerm                 # Hook pre-rimozione (ferma il servizio)
│   └── postrm                # Hook post-rimozione (ripulisce systemd e udev)
│
├── configs/                  # File di configurazione di esempio
│   └── config.json.example   # Template per /etc/pico-fan/config.json
│
└── scripts/                  # Script Bash helper per build e testing
    ├── build_deb.sh          # Script per assemblare il pacchetto pico-fan_X.X.X_all.deb
    └── test_local.sh         # Test suite di verifica sintassi e logica senza installazione
```

---

## 📁 Descrizione Dettagliata dei Componenti

### 1. `firmware/`
Contiene il codice destinato al microcontrollore Raspberry Pi Pico (RP2040).
* **`main.py`**: Firmware MicroPython da flashare sul Pico. Configura il PWM a 25kHz su GP15 e il conteggio impulsi tachimetrici ad interrupt su GP14. Gestisce il protocollo seriale CDC via USB (`SET <duty>`, `RPM`).

### 2. `daemon/`
Contiene il cuore del servizio di backend in esecuzione sul server/host Linux.
* **`fan_daemon.py`**: Demone principale. Legge gli RPM sorgente (`/proc/acpi/ibm/fan` o `hwmon`), calcola la curva di risposta della ventola (0%, 50%, 100%), controlla la seriale e gestisce un server UNIX Domain Socket su `/run/pico-fan.sock` per fornire lo stato alla CLI. Usa `threading.Event` per consumo CPU < 0.1%.
* **`hardware_detector.py`**: Modulo per scansionare `/dev/serial/by-id/` ed identificare in modo univoco le schede Pico collegate.
* **`version.py`**: Modulo helper per risolvere la versione del software a runtime leggendo da Git o dal file `VERSION`.

### 3. `cli/`
Contiene i tool a riga di comando rivolti all'utente.
* **`setup_wizard.py`** (wrapper: `pico-fan-setup`): Wizard guidato interattivo a colori. Guida l'utente nel rilevamento hardware, test velocità ventola, scelta della sorgente RPM e salvataggio della configurazione in `/etc/pico-fan/config.json`.
* **`status.py`** (wrapper: `pico-fan-status`): Client IPC leggibile. Si connette al socket UNIX `/run/pico-fan.sock` ed eroga la diagnostica formattata (RPM sorgente, RPM Pico, Duty %, Porta Seriale).

### 4. `systemd/`
* **`pico-fan.service`**: File di servizio per `systemd`. Permette di gestire il demone tramite `systemctl start/stop/status/enable pico-fan`.

### 5. `udev/`
* **`99-pico-fan.rules`**: Regole `udev` che vengono copiate in `/etc/udev/rules.d/`. Garantiscono permessi di lettura/scrittura al gruppo `dialout` e creano symlink stabili.

### 6. `debian/`
Contiene i file standard di confezionamento Debian per la generazione del file `.deb`:
* **`control`**: Contiene nome, versione, mantenitore e dipendenze del pacchetto (`python3`, `python3-serial`, `lm-sensors`, `udev`).
* **`postinst`**: Eseguito dopo l'installazione per abilitare i servizi systemd e le regole udev.
* **`prerm`**: Eseguito prima della rimozione per fermare il demone.
* **`postrm`**: Eseguito dopo la rimozione per ricaricare systemd e udev ed eventualmente ripulire `/etc/pico-fan` su `apt purge`.

### 7. `scripts/`
* **`build_deb.sh`**: Prepara l'albero delle directory temporanee sotto `build/`, copia i file di libreria in `/usr/lib/pico-fan/`, crea i wrapper eseguibili in `/usr/bin/` (`pico-fan-daemon`, `pico-fan-setup`, `pico-fan-status`, `pico-fan-version`), imposta i permessi `755`/`644` e invoca `dpkg-deb`.
* **`test_local.sh`**: Suite di test automatica per verificare la sintassi dei file Python e Bash senza dover installare il pacchetto nel sistema.

---

## 🔄 Flusso di Installazione e Generazione Eseguibili

Quando viene installato il pacchetto `.deb`, i file vengono posizionati come segue:

| File Sorgente | Percorso di Installazione | Note |
|---|---|---|
| `daemon/` & `cli/` | `/usr/lib/pico-fan/` | Codice Python di supporto |
| `firmware/` | `/usr/lib/pico-fan/firmware/` | Archivio firmware di riferimento |
| `configs/config.json.example` | `/usr/lib/pico-fan/` & `/etc/pico-fan/` | Template configurazione |
| Wrapper Bash | `/usr/bin/pico-fan-*` | Eseguibili di sistema nel PATH |
| `systemd/pico-fan.service` | `/usr/lib/systemd/system/` | Unità systemd |
| `udev/99-pico-fan.rules` | `/etc/udev/rules.d/` | Regole udev |
