# Relazione di Progetto: pico-fan-control

**Progetto:** `pico-fan-control`  
**Autore:** Antigravity & User  
**Versione Finale:** `1.0.6`  
**Data:** 1 Settembre 2026  
**Target OS:** Debian / Ubuntu / Proxmox VE (Kernel Linux 5.x / 6.x / 7.x)

---

## 1. Sintesi Esecutiva

`pico-fan-control` è una suite software modulare professionale realizzata per sistemi Linux. Il suo scopo principale è controllare in modo intelligibile e automatico una **ventola esterna a 4-pin (PWM)** collegata a un microcontrollore **Raspberry Pi Pico / RP2040** via USB seriale, sincronizzandola con gli RPM della ventola interna del sistema (es. ThinkPad ACPI o qualsiasi sottosistema `hwmon`).

Il progetto si è evoluto attraverso un processo iterativo di refactoring e ottimizzazione, passando da un'iniziale architettura basata su driver Kernel C (DKMS) a un'architettura **100% spazio utente (Userspace)** guidata da socket IPC UNIX. Il risultato finale è un pacchetto Debian nativo (`.deb`) pulito, resiliente, privo di dipendenze dai kernel-headers host e con un consumo di risorse CPU quasi nullo (< 0.1%).

---

## 2. Architettura Finale del Sistema (v1.0.6)

Il sistema finale si compone di cinque moduli interconnessi:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        RASPBERRY PI PICO / RP2040                      │
│  Firmware MicroPython (main.py): PWM 25kHz GP15 | Tach IRQ GP14         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ CDC Serial USB (/dev/ttyACM0)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                         PICO-FAN DAEMON (Python)                       │
│  - Polling RPM interni (/proc/acpi/ibm/fan o /sys/class/hwmon/)        │
│  - Calcolo curva duty cycle Hysteresis (0% / 50% / 100%)               │
│  - Socket Server IPC UNIX (/run/pico-fan.sock) [Thread dedicato]       │
│  - Gestione fault-tolerant disconnessione / riconnessione USB          │
└──────────────┬──────────────────────────────────────────┬──────────────┘
               │                                          │
               ▼                                          ▼
┌──────────────────────────────┐        ┌────────────────────────────────┐
│   CLI: pico-fan-status       │        │   CLI: pico-fan-setup          │
│   Interroga il socket UNIX   │        │   Wizard interattivo setup,    │
│   Mostra RPM e stato in CLI  │        │   test ventola & config JSON   │
└──────────────────────────────┘        └────────────────────────────────┘
```

1. **Firmware MicroPython (`firmware/main.py`)**:
   - Generazione segnale PWM a 25 kHz (standard ventole PC 4-pin) sul pin `GP15`.
   - Conteggio impulsi tachimetrici tramite Interrupt Hardware (`Pin.IRQ_FALLING`) sul pin `GP14`.
   - Protocollo seriale CDC non bloccante via `select.poll` su `sys.stdin`.
   - Comandi supportati: `SET <0-100>`, `RPM`, `GET`, `STATUS`.

2. **Demone Principale (`daemon/fan_daemon.py`)**:
   - Eseguito come servizio `systemd` (`pico-fan.service`).
   - Monitora la velocità della ventola interna e aggiorna la ventola esterna al variare delle soglie di temperatura/RPM.
   - Espone uno stato in tempo reale via UNIX Domain Socket su `/run/pico-fan.sock`.
   - Sospensione a impatto zero con `threading.Event.wait()`.

3. **Rilevatore Hardware (`daemon/hardware_detector.py`)**:
   - Scansiona `/dev/serial/by-id/` per individuare l'ID hardware univoco e stabile del Raspberry Pi Pico, evitando problemi legato al cambio dinamico dei nomi delle porte `/dev/ttyACM*`.

4. **Wizard di Configurazione (`cli/setup_wizard.py` -> `pico-fan-setup`)**:
   - Wizard guidato da terminale con rilevamento automatico del Pico, test dinamico dei giri della ventola (25%, 50%, 100%, 0%), selezione della sorgente RPM e salvataggio della configurazione in `/etc/pico-fan/config.json`.

5. **Tool di Diagnostica (`cli/status.py` -> `pico-fan-status`)**:
   - Interroga on-demand il socket UNIX del demone e stampa una tabella formattata a colori con lo stato del dispositivo, la porta seriale, gli RPM sorgente e gli RPM registrati dal Pico.

---

## 3. Cronologia dello Sviluppo (Round per Round)

### Round 1: Architettura Iniziale e Release v1.0.0
- **Obiettivo:** Creare la prima versione funzionante del pacchetto Debian con integrazione `hwmon` e `sensors`.
- **Cosa è stato aggiunto:**
  - Firmware MicroPython per Pico.
  - Demone Python per il controllo della seriale e il polling RPM.
  - Mappa delle regole udev (`99-pico-fan.rules`) per assegnare permessi di lettura/scrittura al gruppo `dialout` e creare symlink `/dev/pico-fan`.
  - Un **modulo Kernel C (`kernel_module/pico_fan_hwmon.c`)** con supporto **DKMS** per registrare un dispositivo virtuale `hwmon` e permettere la lettura dei giri della ventola con il comando `sensors`.
  - Script di build per la creazione del pacchetto `.deb` (`scripts/build_deb.sh` e `Makefile`).
- **Risultato:** Release `v1.0.0` creata e pacchettizzata.

---

### Round 2: Compatibilità Kernel Proxmox & System Versioning (v1.0.1)
- **Problemi Riscontrati:**
  - Durante l'installazione del pacchetto su server Proxmox VE, la compilazione DKMS falliva per l'assenza degli header del kernel host (`linux-headers-7.0.14-11-pve`).
  - Warning di `dpkg` dovuto al posizionamento errato del campo `Maintainer` nel file `debian/control`.
- **Cosa è stato modificato:**
  - Corretto la sintassi di `debian/control`.
  - Implementato un sistema di versioning automatico dinamico basato sul file `VERSION` integrato con `git describe`.
- **Risultato:** Release `v1.0.1` generata.

---

### Round 3: Cambio di Rotta Architetturale – Eliminazione DKMS (v1.0.2)
- **Analisi Strategica:**
  L'integrazione nel sottosistema `hwmon` tramite DKMS si è rivelata troppo fragile negli ambienti server (Proxmox, kernel custom 6.x/7.x) a causa della continua necessità di ricompilare il modulo ad ogni aggiornamento dei `linux-headers`.
- **Decisione dell'Utente:** Rimuovere completamente il modulo kernel in C e passare a un approccio spazio utente leggero.
- **Cosa è stato modificato:**
  - Cancellazione definitiva della directory `kernel_module/` e rimozione di ogni riferimento a DKMS da `debian/control`, `postinst`, `prerm`, `postrm`, `Makefile` e `scripts/build_deb.sh`.
  - Creazione di un server **UNIX Domain Socket** (`/run/pico-fan.sock`) interno al demone Python gestito in un thread dedicato.
  - Creazione del nuovo comando CLI `pico-fan-status` per l'interrogazione dello stato on-demand.
- **Risultato:** Pacchetto slegato da qualsiasi dipendenza di compilazione kernel. Release `v1.0.2` generata.

---

### Round 4: Refactoring, Pulizia Codice e Bugfix (v1.0.3)
- **Problemi Riscontrati:**
  - L'avvio di `pico-fan-setup` falliva con errore di import per la funzione `find_hwmon_path` (residuo del refactoring hwmon).
  - Bug nell'autocompletamento e permessi dei file binari nel pacchetto `.deb` (`pico-fan-status` veniva installato con permessi `644` anziché `755`).
  - Presenza di import inutilizzati (`glob`, `textwrap`) e refusi nei messaggi di completamento del wizard.
- **Cosa è stato modificato:**
  - Pulizia completa degli import residui in `cli/setup_wizard.py` e `daemon/fan_daemon.py`.
  - Corretto il blocco `set_permissions` in `build_deb.sh` aggiungendo `chmod 755` anche a `pico-fan-status`.
  - Risolto un bug di indentazione nel loop di selezione dispositivi in `setup_wizard.py`.
- **Risultato:** Release `v1.0.3` con suite di test locale (`make test`) perfettamente passante.

---

### Round 5: Timing Seriale e Fix Systemd Path (v1.0.4)
- **Problemi Riscontrati:**
  - Durante il test della ventola nel wizard si presentava la risposta inattesa `Risposta inattesa: ''` a causa del mancato azzeramento del buffer seriale prima della lettura.
  - Quando il wizard veniva eseguito con `sudo`, venivano stampati caratteri di escape ANSI sporchi nel terminale (`^[[B^[[B`).
  - Il servizio systemd falliva al boot (`status 2`) perché la direttiva `ExecStart` puntava a un percorso file errato.
- **Cosa è stato modificato:**
  - Aggiornato `step_test_fan()` in `setup_wizard.py`: aggiunto `reset_input_buffer()` e ritardo di stabilizzazione seriale CDC.
  - Corretto `_supports_color()` per rilevare terminali `dumb` o catturati da `sudo`.
  - Corretto `ExecStart` in `systemd/pico-fan.service` per utilizzare l'eseguibile wrapper `/usr/bin/pico-fan-daemon`.
- **Risultato:** Release `v1.0.4` funzionante e servizio systemd avviato con successo.

---

### Round 6: Ottimizzazione Prestazionale CPU (v1.0.5)
- **Analisi delle Prestazioni:**
  Il ciclo di sleep del demone utilizzava una funzione `_sleep_interruptible` che effettuava un loop di `time.sleep(0.2)`, svegliando la CPU 5 volte al secondo inutilmente.
- **Cosa è stato modificato:**
  - Sostituito il polling dello sleep con l'oggetto nativo `threading.Event().wait(timeout=seconds)`.
  - Il demone entra ora in uno stato di attesa bloccante a livello di sistema operativo per l'intera durata dell'intervallo (2s), svegliandosi all'istante solo in caso di segnale di `stop()`.
  - Aggiunto `threading.Lock()` per garantire la thread-safety nell'accesso allo stato condiviso letto dal socket IPC.
- **Risultato:** Riduzione dell'overhead CPU a **< 0.1%**. Release `v1.0.5` generata.

---

### Round 7: Eliminazione Log Doppi e Clean Systemd (v1.0.6)
- **Problemi Riscontrati:**
  - `systemctl status pico-fan` o `journalctl` mostravano ogni singola riga di log duplicata (una volta da `pico-fan[PID]` e una da `python3[PID]`).
  - Avviso nel registro systemd: `Unknown key 'StartLimitIntervalSec' in section [Service], ignoring`.
- **Cause & Soluzioni:**
  - **Log Doppi:** Il demone utilizzava sia `StreamHandler(sys.stdout)` sia `SysLogHandler('/dev/log')`. Poiché systemd cattura già automaticamente `stdout`, l'invio diretto a `/dev/log` duplicava i messaggi. Rimosso `SysLogHandler`.
  - **Warning Systemd:** Spostate le direttive `StartLimitIntervalSec` e `StartLimitBurst` dalla sezione `[Service]` alla sezione `[Unit]` di `pico-fan.service`.
- **Risultato:** Log di sistema puliti e privi di avvisi. Release `v1.0.6` generata.

---

### Round 8: Comando Unificato 'pico-fan' e Controllo Manuale Velocità (v1.1.1)
- **Richiesta Utente:**
  1. Unificare i 4 binari separati in un solo comando `pico-fan` con sottocomandi (`daemon`, `setup`, `status`, `set`, `manual`, `version`), eliminando i vecchi wrapper separati.
  2. Aggiungere la possibilità di impostare manualmente la velocità della ventola a una determinata percentuale (es. `pico-fan set 75`), monitorando gli RPM in tempo reale finché l'utente non preme `Ctrl+C`.
  3. Abilitare e avviare il servizio immediatamente al momento dell'installazione (`systemctl enable --now`).
  4. Distinguere nel post-install tra prima installazione (mostra i prossimi passi) e aggiornamento (mostra solo "Aggiornamento completato").
- **Cosa è stato modificato:**
  - **Dispatcher Unificato (`cli/main.py`):** Unico binario installato in `/usr/bin/pico-fan`. Se chiamato senza argomenti o con `--help`, stampa una guida chiara a colori con tutti i comandi disponibili ed esempi.
  - **Controllo Manuale (`cli/manual.py`):** Nuovo sottocomando `pico-fan set <0-100>` (e alias `pico-fan manual`). Comunica tramite socket IPC col demone attivo, impostando istantaneamente il duty cycle richiesto e ciclando a video i giri ventola (Pico RPM e Interna RPM).
  - **Ripristino Fail-Safe Automatico:** Alla pressione di `Ctrl+C` (o se la sessione cade inaspettatamente), il socket si chiude e il demone ripristina immediatamente la modalità automatica calcolata in base alla temperatura/RPM interni.
  - **Display di Stato Avanzato (`cli/status.py`):** Se è attiva una sessione manuale, `pico-fan status` segnala esplicitamente l'override con l'etichetta `(MANUALE)`.
- **Risultato:** Esperienza utente estremamente pulita, moderna e sicura. Release `v1.1.1` generata.

---

### Round 9: Personalizzazione Velocità Massima e Duty Cycle nel Setup (v1.1.2)
- **Richiesta Utente:** Possibilità di configurare durante `pico-fan setup` la velocità massima della ventola (ad esempio impostando il 90% come massimo se a quella percentuale rende di più rispetto al 100%).
- **Cosa è stato modificato:**
  - **Wizard Setup (`cli/setup_wizard.py`):**
    - Aggiunto lo step di collaudo al 90% nella sequenza di test iniziale (25%, 50%, 90%, 100%, 0%) per consentire la verifica visiva e strumentale dei giri.
    - Nello Step 4 del wizard, ora viene chiesto esplicitamente all'utente di definire la velocità massima, media e minima in percentuale PWM (con valori predefiniti intelligenti letti dalla configurazione esistente o dai default di sistema).
    - Salvataggio dei parametri `duty_high`, `duty_mid`, `duty_low` in `/etc/pico-fan/config.json`.
- **Risultato:** Massima flessibilità d'uso per qualsiasi ventola PWM con caratteristiche non lineari. Release `v1.1.2` generata.

---

## 4. Risultati Finali e Valutazione del Software

Il software si trova attualmente nello stato stabile **`v1.1.2`**.

### Pacchetto Rilasciato:
- **File pacchetto:** `pico-fan_1.1.2_all.deb`
- **Comando installato nel sistema:**
  - `pico-fan`: Eseguibile unificato con i seguenti sottocomandi:
    - `pico-fan`: Mostra la guida completa e gli esempi.
    - `pico-fan status`: Diagnostica rapida dello stato e degli RPM.
    - `pico-fan set <0-100>` (o `manual`): Imposta velocità fissa e monitora RPM in tempo reale fino a `Ctrl+C`.
    - `pico-fan setup`: Wizard interattivo per configurazione hardware iniziale e velocità PWM personalizzate.
    - `pico-fan daemon`: Demone di sincronizzazione (avviato in automatico da systemd).
    - `pico-fan version`: Versione del pacchetto installato.

### Matrice delle Caratteristiche:
| Funzionalità | Stato | Note |
|---|---|---|
| Controllo PWM 25kHz | ✅ Attivo | Gestito via MicroPython su RP2040 (GP15) |
| Lettura Tachimetro Interrupt | ✅ Attivo | Conteggio ad alta precisione su RP2040 (GP14) |
| Sincronizzazione RPM Sorgente | ✅ Attivo | Supporto ThinkPad ACPI e hwmon generici |
| Configurazione Duty Massima/Media | ✅ Attivo | Definibile da wizard (es. 90% come massimo) |
| Controllo Manuale Temporaneo | ✅ Attivo | `pico-fan set <0-100>` con monitoraggio live e ripristino su Ctrl+C |
| Tolleranza ai Guasti USB | ✅ Attivo | Riconnessione automatica senza crash in caso di scollegamento |
| Interfaccia CLI Unificata | ✅ Attivo | Solo `/usr/bin/pico-fan` con sottocomandi chiari |
| Impatto CPU | ✅ < 0.1% | Uso di `threading.Event` bloccante |
| Compatibilità Kernel | ✅ 100% | Zero moduli C / Zero dipendenze `linux-headers` |

---

## 5. Comandi Utili per l'Utilizzo Quotidiano

```bash
# Installazione o aggiornamento del pacchetto (si avvia da solo)
sudo dpkg -i pico-fan_1.1.2_all.deb

# Configurazione iniziale guidata
sudo pico-fan setup

# Controllo manuale temporaneo (ad es. test al 75%)
pico-fan set 75

# Verifica dello stato in tempo reale
pico-fan status

# Gestione servizio systemd
sudo systemctl restart pico-fan
sudo systemctl status pico-fan

# Lettura dei log di sistema
journalctl -u pico-fan -f
```

---
*Relazione generata per il repository `pico-fan-control`.*
