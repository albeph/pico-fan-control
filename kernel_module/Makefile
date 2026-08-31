# Makefile per il modulo kernel pico_fan_hwmon
# Supporta compilazione standalone e integrazione DKMS
#
# Utilizzo:
#   make              - Compila il modulo per il kernel corrente
#   make clean        - Rimuove i file intermedi
#   make install      - Installa il modulo (richiede root)
#   make dkms-add     - Registra il sorgente in DKMS
#   make dkms-build   - Compila via DKMS
#   make dkms-install - Installa via DKMS
#   make dkms-remove  - Rimuove da DKMS

MODULE_NAME := pico_fan_hwmon
PACKAGE_NAME := pico-fan

# Versione: ereditata da MODULE_VERSION (passata dal Makefile root) oppure
# letta direttamente dal file VERSION nella directory parent.
MODULE_VERSION ?= $(shell cat ../VERSION 2>/dev/null || cat ../../VERSION 2>/dev/null || echo "0.0.0+dev")

# Kernel source directory
KVER ?= $(shell uname -r)
KDIR ?= /lib/modules/$(KVER)/build
PWD  := $(shell pwd)

# Directory DKMS
DKMS_TREE := /var/lib/dkms
DKMS_SRC  := /usr/src/$(PACKAGE_NAME)-$(MODULE_VERSION)

# Oggetti del modulo
obj-m := $(MODULE_NAME).o

# ---------------------------------------------------------------------------
# Target: compilazione modulo kernel
# ---------------------------------------------------------------------------
.PHONY: all modules clean install dkms-add dkms-build dkms-install dkms-remove

all: modules

modules:
	@echo "  BUILD   $(MODULE_NAME).ko per kernel $(KVER)"
	$(MAKE) -C $(KDIR) M=$(PWD) modules

# ---------------------------------------------------------------------------
# Target: pulizia file temporanei di compilazione
# ---------------------------------------------------------------------------
clean:
	@echo "  CLEAN   $(MODULE_NAME)"
	$(MAKE) -C $(KDIR) M=$(PWD) clean
	@rm -f Module.symvers modules.order

# ---------------------------------------------------------------------------
# Target: installazione manuale del modulo
# ---------------------------------------------------------------------------
install: modules
	@echo "  INSTALL $(MODULE_NAME).ko"
	install -d /lib/modules/$(KVER)/extra
	install -m 644 $(MODULE_NAME).ko /lib/modules/$(KVER)/extra/
	depmod -a $(KVER)
	@echo "  Modulo installato. Caricare con: modprobe $(MODULE_NAME)"

# ---------------------------------------------------------------------------
# Target DKMS: registrazione sorgente
# ---------------------------------------------------------------------------
dkms-add:
	@echo "  DKMS ADD $(PACKAGE_NAME)-$(MODULE_VERSION)"
	install -d $(DKMS_SRC)
	install -m 644 $(MODULE_NAME).c $(DKMS_SRC)/
	install -m 644 Makefile $(DKMS_SRC)/
	@# Genera dkms.conf dalla template con la versione corretta
	sed 's/@VERSION@/$(MODULE_VERSION)/g' dkms.conf.in > $(DKMS_SRC)/dkms.conf
	dkms add -m $(PACKAGE_NAME) -v $(MODULE_VERSION)

# ---------------------------------------------------------------------------
# Target DKMS: compilazione
# ---------------------------------------------------------------------------
dkms-build:
	dkms build -m $(PACKAGE_NAME) -v $(MODULE_VERSION)

# ---------------------------------------------------------------------------
# Target DKMS: installazione
# ---------------------------------------------------------------------------
dkms-install:
	dkms install -m $(PACKAGE_NAME) -v $(MODULE_VERSION)

# ---------------------------------------------------------------------------
# Target DKMS: rimozione
# ---------------------------------------------------------------------------
dkms-remove:
	dkms remove -m $(PACKAGE_NAME) -v $(MODULE_VERSION) --all || true
	rm -rf $(DKMS_SRC) || true
