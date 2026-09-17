# Makefile - Build, test, and release automation for pico-fan-control
# ===================================================================
# The version is automatically read from the VERSION file.
# Do not edit VERSION here: update the VERSION file directly or
# use the bump-patch / bump-minor / bump-major targets.
#
# Primary targets:
#   make deb            - Builds .deb package with current version
#   make test           - Runs full local test suite
#   make test-quick     - Runs quick syntax and logic verification
#   make test-hw        - Runs tests with attached Pico hardware
#   make clean          - Removes temporary build artifacts and packages
#   make install        - Installs .deb package locally (requires root)
#   make uninstall      - Removes package (requires root)
#   make version        - Displays current version
#   make bump-patch     - Bumps patch version (1.0.0 -> 1.0.1)
#   make bump-minor     - Bumps minor version (1.0.0 -> 1.1.0)
#   make bump-major     - Bumps major version (1.0.0 -> 2.0.0)
#   make tag            - Creates annotated git tag v$(VERSION)

# ---------------------------------------------------------------------------
# Version: read from VERSION file, with fallback to git describe
# ---------------------------------------------------------------------------
VERSION := $(shell \
    git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//' \
    || cat VERSION 2>/dev/null \
    || echo "0.0.0+dev")

PACKAGE   := pico-fan
ARCH      := all
DEB_FILE  := $(PACKAGE)_$(VERSION)_$(ARCH).deb
PYTHON    := python3
.PHONY: all deb test test-quick test-hw clean install uninstall \
        version bump-patch bump-minor bump-major tag help

# ---------------------------------------------------------------------------
# Default: display help and version
# ---------------------------------------------------------------------------
all: help

# ---------------------------------------------------------------------------
# version: display current version
# ---------------------------------------------------------------------------
version:
	@echo "Current version: $(VERSION)"
	@echo "  VERSION file:   $$(cat VERSION 2>/dev/null || echo 'not found')"
	@echo "  Git tag:        $$(git describe --tags --abbrev=0 2>/dev/null || echo 'no tag')"
	@echo "  .deb target:    $(DEB_FILE)"



# ---------------------------------------------------------------------------
# Test targets
# ---------------------------------------------------------------------------
test:
	@echo ">>> Full test suite (v$(VERSION)) ..."
	@chmod +x scripts/test_local.sh
	@bash scripts/test_local.sh --all

test-quick:
	@echo ">>> Quick test (syntax and logic) ..."
	@chmod +x scripts/test_local.sh
	@bash scripts/test_local.sh

test-hw:
	@echo ">>> Hardware test (requires attached Pico) ..."
	@chmod +x scripts/test_local.sh
	@bash scripts/test_local.sh --scan --daemon

# ---------------------------------------------------------------------------
# DEB: build .deb package
# ---------------------------------------------------------------------------
deb:
	@echo ">>> Building package $(DEB_FILE) ..."
	@chmod +x scripts/build_deb.sh
	@bash scripts/build_deb.sh
	@echo ">>> Package generated: $(DEB_FILE)"

# ---------------------------------------------------------------------------
# Clean build files
# ---------------------------------------------------------------------------
clean:
	@echo ">>> Cleaning build artifacts ..."
	@rm -rf build/
	@rm -f $(PACKAGE)_*.deb
	@find . -name "*.pyc" -delete
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo ">>> Cleanup complete."

# ---------------------------------------------------------------------------
# Install / Uninstall
# ---------------------------------------------------------------------------
install: deb
	@echo ">>> Installing $(DEB_FILE) ..."
	sudo dpkg -i $(DEB_FILE)

uninstall:
	@echo ">>> Removing $(PACKAGE) ..."
	sudo apt remove -y $(PACKAGE) || sudo dpkg -r $(PACKAGE)



# ---------------------------------------------------------------------------
# Versioning: automatic bump updating VERSION file
# ---------------------------------------------------------------------------
bump-patch:
	@$(PYTHON) -c " \
v = open('VERSION').read().strip().split('.'); \
v[2] = str(int(v[2]) + 1); \
ver = '.'.join(v); \
open('VERSION','w').write(ver + '\n'); \
print(f'  Version → {ver}') \
"
	@echo "  Commit with: git add VERSION && git commit -m \"chore: bump version\""

bump-minor:
	@$(PYTHON) -c " \
v = open('VERSION').read().strip().split('.'); \
v[1] = str(int(v[1]) + 1); v[2] = '0'; \
ver = '.'.join(v); \
open('VERSION','w').write(ver + '\n'); \
print(f'  Version → {ver}') \
"
	@echo "  Commit with: git add VERSION && git commit -m \"chore: bump version\""

bump-major:
	@$(PYTHON) -c " \
v = open('VERSION').read().strip().split('.'); \
v[0] = str(int(v[0]) + 1); v[1] = '0'; v[2] = '0'; \
ver = '.'.join(v); \
open('VERSION','w').write(ver + '\n'); \
print(f'  Version → {ver}') \
"
	@echo "  Commit with: git add VERSION && git commit -m \"chore: bump version\""

# ---------------------------------------------------------------------------
# Tag: create annotated git tag v$(VERSION)
# ---------------------------------------------------------------------------
tag:
	@VER=$$(cat VERSION); \
	echo ">>> Creating git tag v$$VER ..."; \
	git diff --quiet || { echo "ERROR: uncommitted changes present."; exit 1; }; \
	git tag -a "v$$VER" -m "Release v$$VER"; \
	echo ">>> Tag v$$VER created."; \
	echo "    Push with: git push origin v$$VER"

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
help:
	@VER=$$(cat VERSION 2>/dev/null || echo "?"); \
	echo ""; \
	echo "  pico-fan-control - Root Makefile  (version: $$VER)"; \
	echo ""; \
	echo "  ── Build ──────────────────────────────────────────────"; \
	echo "    make deb           Build $(PACKAGE)_$$VER_$(ARCH).deb"; \
	echo "    make install       Install package via dpkg (sudo)"; \
	echo "    make uninstall     Remove package (sudo)"; \
	echo ""; \
	echo "  ── Test ───────────────────────────────────────────────"; \
	echo "    make test          Full test suite (Python + daemon)"; \
	echo "    make test-quick    Syntax and logic only"; \
	echo "    make test-hw       Hardware probe with attached Pico"; \
	echo ""; \
	echo "  ── Versioning ─────────────────────────────────────────"; \
	echo "    make version       Display current version"; \
	echo "    make bump-patch    $$VER → $$($(PYTHON) -c \"v='$$VER'.split('.');v[2]=str(int(v[2])+1);print('.'.join(v))\" 2>/dev/null || echo 'N/A')"; \
	echo "    make bump-minor    $$VER → $$($(PYTHON) -c \"v='$$VER'.split('.');v[1]=str(int(v[1])+1);v[2]='0';print('.'.join(v))\" 2>/dev/null || echo 'N/A')"; \
	echo "    make bump-major    $$VER → $$($(PYTHON) -c \"v='$$VER'.split('.');v[0]=str(int(v[0])+1);v[1]='0';v[2]='0';print('.'.join(v))\" 2>/dev/null || echo 'N/A')"; \
	echo "    make tag           Create git tag v$$VER"; \
	echo ""; \
	echo "  ── Utility ────────────────────────────────────────────"; \
	echo "    make clean         Remove temporary build files and .deb"; \
	echo "    make help          Display this help message"; \
	echo ""

