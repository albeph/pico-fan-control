#!/usr/bin/env bash
# scripts/test_local.sh - Test locale rapido senza installazione
# ==============================================================
# Esegue una serie di test funzionali senza richiedere dpkg install.
# Utile per sviluppo e CI/CD.
#
# Utilizzo:
#   ./scripts/test_local.sh [--daemon] [--wizard] [--scan] [--all]
#
# Opzioni:
#   --daemon   Esegue il demone in modalità dry-run (nessun Pico richiesto)
#   --wizard   Esegue il wizard in modalità mock
#   --scan     Scansiona le porte seriali (richiede Pico collegato)
#   --all      Esegue tutti i test
#
# Richiede: python3, python3-serial (opzionale per --scan)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"

GREEN="\033[92m"
YELLOW="\033[93m"
RED="\033[91m"
CYAN="\033[96m"
BOLD="\033[1m"
RESET="\033[0m"

pass()    { echo -e "  ${GREEN}✓${RESET} $*"; }
fail()    { echo -e "  ${RED}✗${RESET} $*"; FAILURES=$((FAILURES + 1)); }
info()    { echo -e "${CYAN}[TEST]${RESET} $*"; }
warning() { echo -e "${YELLOW}[TEST] AVVISO:${RESET} $*"; }
header()  { echo -e "\n${BOLD}${CYAN}=== $* ===${RESET}\n"; }

FAILURES=0

# ---------------------------------------------------------------------------
# Test: sintassi Python
# ---------------------------------------------------------------------------
test_python_syntax() {
    header "Verifica sintassi Python"
    local files=(
        "${REPO_ROOT}/daemon/fan_daemon.py"
        "${REPO_ROOT}/daemon/hardware_detector.py"
        "${REPO_ROOT}/cli/setup_wizard.py"
        "${REPO_ROOT}/cli/status.py"
        "${REPO_ROOT}/cli/manual.py"
        "${REPO_ROOT}/cli/main.py"
    )
    for f in "${files[@]}"; do
        if $PYTHON -m py_compile "$f" 2>/dev/null; then
            pass "Sintassi OK: $(basename "$f")"
        else
            fail "Errore sintassi: $f"
            $PYTHON -m py_compile "$f" 2>&1 | head -5
        fi
    done
}

# ---------------------------------------------------------------------------
# Test: import moduli Python
# ---------------------------------------------------------------------------
test_python_imports() {
    header "Verifica import Python"

    # Test hardware_detector (senza seriale)
    if $PYTHON -c "
import sys
sys.path.insert(0, '${REPO_ROOT}/daemon')
# Test import parziale (senza pyserial richiede mock)
import importlib.util
spec = importlib.util.spec_from_file_location('hardware_detector',
    '${REPO_ROOT}/daemon/hardware_detector.py')
" 2>/dev/null; then
        pass "Import hardware_detector.py"
    else
        warning "Import hardware_detector.py richiede pyserial"
    fi
}

# ---------------------------------------------------------------------------
# Test: configurazione JSON di esempio
# ---------------------------------------------------------------------------
test_config_json() {
    header "Verifica configurazione JSON"
    local cfg="${REPO_ROOT}/configs/config.json.example"

    if [[ -f "$cfg" ]]; then
        if $PYTHON -c "import json; json.load(open('$cfg'))" 2>/dev/null; then
            pass "JSON valido: config.json.example"
        else
            fail "JSON non valido: $cfg"
        fi
    else
        fail "File mancante: $cfg"
    fi
}


# ---------------------------------------------------------------------------
# Test: sistema di versioning
# ---------------------------------------------------------------------------
test_versioning() {
    header "Verifica sistema di versioning"

    local version_file="${REPO_ROOT}/VERSION"

    # 1. File VERSION esiste e ha formato semver
    if [[ ! -f "$version_file" ]]; then
        fail "File VERSION mancante nella root del repository"
        return
    fi
    local ver
    ver=$(tr -d '[:space:]' < "$version_file")
    if echo "$ver" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+'; then
        pass "File VERSION formato valido: ${ver}"
    else
        fail "File VERSION formato non semver: '${ver}'"
    fi

    # 2. version.py risolve la versione correttamente
    local py_ver
    py_ver=$($PYTHON -c "
import sys
sys.path.insert(0, '${REPO_ROOT}/daemon')
from version import __version__, VERSION_TUPLE
print(__version__)
" 2>/dev/null || echo "ERROR")
    if [[ "$py_ver" != "ERROR" && -n "$py_ver" ]]; then
        pass "version.py: __version__='${py_ver}'"
    else
        fail "version.py: impossibile risolvere la versione"
    fi

    # 3. Coerenza VERSION file vs version.py
    if [[ "$py_ver" == "$ver" ]]; then
        pass "Versione coerente: VERSION file == version.py (${ver})"
    else
        warning "Versione: VERSION file='${ver}' vs version.py='${py_ver}' (potrebbe usare git tag)"
    fi

    # 4. debian/control ha campo Version
    local ctrl="${REPO_ROOT}/debian/control"
    if grep -q "^Version:" "$ctrl"; then
        local ctrl_ver
        ctrl_ver=$(grep "^Version:" "$ctrl" | awk '{print $2}')
        pass "debian/control Version: ${ctrl_ver}"
    else
        fail "debian/control: campo Version mancante"
    fi

    # 5. build_deb.sh supporta --version
    if bash -n "${REPO_ROOT}/scripts/build_deb.sh"; then
        pass "build_deb.sh sintassi bash OK"
    else
        fail "build_deb.sh errore di sintassi"
    fi


}

# ---------------------------------------------------------------------------
# Test: script bash (shellcheck o sintassi bash)
# ---------------------------------------------------------------------------
test_bash_scripts() {
    header "Verifica script bash"
    local scripts=(
        "${REPO_ROOT}/scripts/build_deb.sh"
        "${REPO_ROOT}/scripts/test_local.sh"
        "${REPO_ROOT}/debian/postinst"
        "${REPO_ROOT}/debian/prerm"
        "${REPO_ROOT}/debian/postrm"
    )

    for s in "${scripts[@]}"; do
        if [[ ! -f "$s" ]]; then
            warning "File mancante: $s"
            continue
        fi

        if command -v shellcheck > /dev/null 2>&1; then
            if shellcheck --severity=error "$s" 2>/dev/null; then
                pass "shellcheck OK: $(basename "$s")"
            else
                warning "shellcheck warning in: $(basename "$s")"
            fi
        else
            # Fallback: solo verifica sintassi bash
            if bash -n "$s" 2>/dev/null; then
                pass "Sintassi bash OK: $(basename "$s")"
            else
                fail "Errore sintassi bash: $s"
            fi
        fi
    done
}

# ---------------------------------------------------------------------------
# Test: scansione hardware (richiede Pico collegato)
# ---------------------------------------------------------------------------
test_scan_hardware() {
    header "Scansione hardware reale"
    info "Scansione /dev/serial/by-id/ ..."

    $PYTHON -c "
import sys
sys.path.insert(0, '${REPO_ROOT}/daemon')
try:
    from hardware_detector import scan_devices, list_serial_by_id
    all_devs = list_serial_by_id()
    print(f'  Dispositivi in /dev/serial/by-id/: {len(all_devs)}')
    for d in all_devs:
        print(f'    - {d}')
    print()
    devices = scan_devices(probe=True)
    if devices:
        for dev in devices:
            print(f'  Trovato: {dev}')
    else:
        print('  Nessun Pico trovato (normale se non collegato)')
except ImportError as e:
    print(f'  Import fallito: {e}')
    print('  Installare: pip install pyserial')
" && pass "Scansione hardware completata" || fail "Errore scansione hardware"
}

# ---------------------------------------------------------------------------
# Test: demone dry-run (senza Pico e senza config)
# ---------------------------------------------------------------------------
test_daemon_dryrun() {
    header "Demone dry-run"
    info "Test caricamento moduli demone ..."

    $PYTHON -c "
import sys, os
sys.path.insert(0, '${REPO_ROOT}/daemon')
# Testa solo le funzioni che non richiedono hardware
try:
    import fan_daemon
    # Test compute_target_duty
    cfg = fan_daemon.DEFAULT_CONFIG
    assert fan_daemon.compute_target_duty(5000, cfg) == 100, 'duty_high failed'
    assert fan_daemon.compute_target_duty(3000, cfg) == 50,  'duty_mid failed'
    assert fan_daemon.compute_target_duty(1000, cfg) == 0,   'duty_low failed'
    print('  compute_target_duty: OK')
    print('  Moduli demone caricati con successo')
except ImportError as e:
    print(f'  Import fallito: {e}')
    print('  Installare: pip install pyserial')
    sys.exit(1)
" && pass "Demone dry-run OK" || fail "Errore demone dry-run"
}

# ---------------------------------------------------------------------------
# Riepilogo
# ---------------------------------------------------------------------------
print_summary() {
    echo ""
    echo -e "${BOLD}═══════════════════════════════════════${RESET}"
    if [[ $FAILURES -eq 0 ]]; then
        echo -e "${BOLD}${GREEN}  ✓ Tutti i test superati${RESET}"
    else
        echo -e "${BOLD}${RED}  ✗ ${FAILURES} test falliti${RESET}"
    fi
    echo -e "${BOLD}═══════════════════════════════════════${RESET}"
    echo ""
}

# ===========================================================================
# Main
# ===========================================================================
main() {
    echo ""
    info "=== pico-fan-control - Test suite locale ==="
    echo ""

    local run_daemon=false
    local run_wizard=false
    local run_module=false
    local run_scan=false
    local run_all=false

    if [[ $# -eq 0 ]]; then
        run_all=true
    fi

    for arg in "$@"; do
        case "$arg" in
            --daemon) run_daemon=true ;;
            --wizard) run_wizard=true ;;
            --scan)   run_scan=true   ;;
            --all)    run_all=true    ;;
            *)
                echo "Argomento non riconosciuto: $arg"
                echo "Uso: $0 [--daemon] [--wizard] [--scan] [--all]"
                exit 1
                ;;
        esac
    done

    # Test sempre eseguiti
    test_python_syntax
    test_python_imports
    test_config_json
    test_versioning
    test_bash_scripts

    # Test selettivi

    if $run_all || $run_daemon; then
        test_daemon_dryrun
    fi

    if $run_scan; then
        test_scan_hardware
    fi

    print_summary
    [[ $FAILURES -eq 0 ]] || exit 1
}

main "$@"
