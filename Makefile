# Makefile root - pico-fan-control
# =================================
# La versione viene letta automaticamente dal file VERSION.
# Non modificare VERSION qui: aggiornare il file VERSION oppure
# usare i target bump-patch / bump-minor / bump-major.
#
# Target principali:
#   make build          - Compila il modulo kernel
#   make deb            - Genera il pacchetto .deb con la versione corrente
#   make test           - Esegue la test suite locale
#   make clean          - Rimuove file temporanei
#   make install        - Installa localmente (richiede root)
#   make version        - Mostra la versione corrente
#   make bump-patch     - Incrementa patch (1.0.0 → 1.0.1)
#   make bump-minor     - Incrementa minor (1.0.0 → 1.1.0)
#   make bump-major     - Incrementa major (1.0.0 → 2.0.0)
#   make tag            - Crea tag git v$(VERSION) e fa push

# ---------------------------------------------------------------------------
# Versione: letta dal file VERSION, con fallback a git describe
# ---------------------------------------------------------------------------
VERSION := $(shell \
    git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//' \
    || cat VERSION 2>/dev/null \
    || echo "0.0.0+dev")

PACKAGE   := pico-fan
ARCH      := all
DEB_FILE  := $(PACKAGE)_$(VERSION)_$(ARCH).deb
PYTHON    := python3
KVER      ?= $(shell uname -r)
KDIR      ?= /lib/modules/$(KVER)/build

.PHONY: all build deb test test-quick test-hw clean install uninstall \
        dkms dkms-clean version bump-patch bump-minor bump-major tag help

# ---------------------------------------------------------------------------
# Default: mostra versione e aiuto
# ---------------------------------------------------------------------------
all: help

# ---------------------------------------------------------------------------
# version: mostra la versione corrente
# ---------------------------------------------------------------------------
version:
	@echo "Versione corrente: $(VERSION)"
	@echo "  File VERSION:    $$(cat VERSION 2>/dev/null || echo 'non trovato')"
	@echo "  Git tag:         $$(git describe --tags --abbrev=0 2>/dev/null || echo 'nessun tag')"
	@echo "  .deb target:     $(DEB_FILE)"

# ---------------------------------------------------------------------------
# Build: compila il modulo kernel (richiede linux-headers)
# ---------------------------------------------------------------------------
build:
	@echo ">>> Compilazione modulo kernel pico_fan_hwmon (v$(VERSION)) ..."
	$(MAKE) -C kernel_module KDIR=$(KDIR) MODULE_VERSION=$(VERSION) modules
	@echo ">>> Modulo compilato: kernel_module/pico_fan_hwmon.ko"

# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
test:
	@echo ">>> Test suite completa (v$(VERSION)) ..."
	@chmod +x scripts/test_local.sh
	@bash scripts/test_local.sh --all

test-quick:
	@echo ">>> Test rapido (sintassi e logica) ..."
	@chmod +x scripts/test_local.sh
	@bash scripts/test_local.sh

test-hw:
	@echo ">>> Test con hardware (richiede Pico collegato) ..."
	@chmod +x scripts/test_local.sh
	@bash scripts/test_local.sh --scan --daemon

# ---------------------------------------------------------------------------
# DEB: genera il pacchetto .deb
# ---------------------------------------------------------------------------
deb:
	@echo ">>> Generazione pacchetto $(DEB_FILE) ..."
	@chmod +x scripts/build_deb.sh
	@bash scripts/build_deb.sh
	@echo ">>> Pacchetto generato: $(DEB_FILE)"

# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------
clean:
	@echo ">>> Pulizia ..."
	-$(MAKE) -C kernel_module clean 2>/dev/null || true
	@rm -rf build/
	@rm -f $(PACKAGE)_*.deb
	@find . -name "*.pyc" -delete
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo ">>> Pulizia completata."

# ---------------------------------------------------------------------------
# Install / Uninstall
# ---------------------------------------------------------------------------
install: deb
	@echo ">>> Installazione $(DEB_FILE) ..."
	sudo dpkg -i $(DEB_FILE)

uninstall:
	@echo ">>> Rimozione $(PACKAGE) ..."
	sudo apt remove -y $(PACKAGE) || sudo dpkg -r $(PACKAGE)

# ---------------------------------------------------------------------------
# DKMS manuale
# ---------------------------------------------------------------------------
dkms:
	@echo ">>> Setup DKMS manuale (v$(VERSION)) ..."
	sudo install -d /usr/src/$(PACKAGE)-$(VERSION)
	sudo cp kernel_module/pico_fan_hwmon.c /usr/src/$(PACKAGE)-$(VERSION)/
	sudo cp kernel_module/Makefile          /usr/src/$(PACKAGE)-$(VERSION)/
	@# Genera dkms.conf con la versione corretta
	sudo sh -c "sed 's/@VERSION@/$(VERSION)/g' kernel_module/dkms.conf.in \
	    > /usr/src/$(PACKAGE)-$(VERSION)/dkms.conf"
	sudo dkms add     -m $(PACKAGE) -v $(VERSION)
	sudo dkms build   -m $(PACKAGE) -v $(VERSION)
	sudo dkms install -m $(PACKAGE) -v $(VERSION)
	sudo modprobe pico_fan_hwmon
	@echo ">>> DKMS configurato e modulo caricato."

dkms-clean:
	@echo ">>> Pulizia DKMS ..."
	-sudo modprobe -r pico_fan_hwmon 2>/dev/null || true
	-sudo dkms remove -m $(PACKAGE) -v $(VERSION) --all 2>/dev/null || true
	-sudo rm -rf /usr/src/$(PACKAGE)-$(VERSION) 2>/dev/null || true
	@echo ">>> DKMS pulito."

# ---------------------------------------------------------------------------
# Versioning: bump automatico con aggiornamento file VERSION
# ---------------------------------------------------------------------------
bump-patch:
	@$(PYTHON) -c " \
v = open('VERSION').read().strip().split('.'); \
v[2] = str(int(v[2]) + 1); \
ver = '.'.join(v); \
open('VERSION','w').write(ver + '\n'); \
print(f'  Versione → {ver}') \
"
	@echo "  Aggiornare git: git add VERSION && git commit -m \"chore: bump version\""

bump-minor:
	@$(PYTHON) -c " \
v = open('VERSION').read().strip().split('.'); \
v[1] = str(int(v[1]) + 1); v[2] = '0'; \
ver = '.'.join(v); \
open('VERSION','w').write(ver + '\n'); \
print(f'  Versione → {ver}') \
"
	@echo "  Aggiornare git: git add VERSION && git commit -m \"chore: bump version\""

bump-major:
	@$(PYTHON) -c " \
v = open('VERSION').read().strip().split('.'); \
v[0] = str(int(v[0]) + 1); v[1] = '0'; v[2] = '0'; \
ver = '.'.join(v); \
open('VERSION','w').write(ver + '\n'); \
print(f'  Versione → {ver}') \
"
	@echo "  Aggiornare git: git add VERSION && git commit -m \"chore: bump version\""

# ---------------------------------------------------------------------------
# Tag: crea e pubblica un tag git annotato v$(VERSION)
# ---------------------------------------------------------------------------
tag:
	@VER=$$(cat VERSION); \
	echo ">>> Creazione tag git v$$VER ..."; \
	git diff --quiet || { echo "ERRORE: ci sono modifiche non committate."; exit 1; }; \
	git tag -a "v$$VER" -m "Release v$$VER"; \
	echo ">>> Tag v$$VER creato."; \
	echo "    Pubblicare con: git push origin v$$VER"

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
help:
	@VER=$$(cat VERSION 2>/dev/null || echo "?"); \
	echo ""; \
	echo "  pico-fan-control - Makefile root  (versione: $$VER)"; \
	echo ""; \
	echo "  ── Build ──────────────────────────────────────────────"; \
	echo "    make build         Compila il modulo kernel"; \
	echo "    make deb           Genera $(PACKAGE)_$$VER_$(ARCH).deb"; \
	echo "    make install       Build + installazione dpkg (sudo)"; \
	echo "    make uninstall     Rimuove il pacchetto (sudo)"; \
	echo ""; \
	echo "  ── Test ───────────────────────────────────────────────"; \
	echo "    make test          Suite completa (Python + kernel + demone)"; \
	echo "    make test-quick    Solo sintassi e logica"; \
	echo "    make test-hw       Con hardware Pico collegato"; \
	echo ""; \
	echo "  ── Versioning ─────────────────────────────────────────"; \
	echo "    make version       Mostra la versione corrente"; \
	echo "    make bump-patch    $$VER → $$($(PYTHON) -c \"v='$$VER'.split('.');v[2]=str(int(v[2])+1);print('.'.join(v))\" 2>/dev/null || echo 'N/A')"; \
	echo "    make bump-minor    $$VER → $$($(PYTHON) -c \"v='$$VER'.split('.');v[1]=str(int(v[1])+1);v[2]='0';print('.'.join(v))\" 2>/dev/null || echo 'N/A')"; \
	echo "    make bump-major    $$VER → $$($(PYTHON) -c \"v='$$VER'.split('.');v[0]=str(int(v[0])+1);v[1]='0';v[2]='0';print('.'.join(v))\" 2>/dev/null || echo 'N/A')"; \
	echo "    make tag           Crea tag git v$$VER"; \
	echo ""; \
	echo "  ── DKMS ───────────────────────────────────────────────"; \
	echo "    make dkms          Setup DKMS manuale (sudo)"; \
	echo "    make dkms-clean    Pulizia DKMS completa (sudo)"; \
	echo ""; \
	echo "  ── Utility ────────────────────────────────────────────"; \
	echo "    make clean         Rimuove file temporanei e .deb"; \
	echo "    make help          Questo messaggio"; \
	echo ""
