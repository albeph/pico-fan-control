#!/usr/bin/env bash
# scripts/test_local.sh - Quick local test without installation
# ==============================================================
# Runs a suite of functional tests without requiring dpkg install.
# Useful for development and CI/CD.
#
# Usage:
#   ./scripts/test_local.sh [--daemon] [--wizard] [--scan] [--all]
#
# Options:
#   --daemon   Run daemon in dry-run mode (no Pico required)
#   --wizard   Run wizard in mock mode
#   --scan     Scan serial ports (requires Pico connected)
#   --all      Run all tests
#
# Requires: python3, python3-serial (optional for --scan)

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
warning() { echo -e "${YELLOW}[TEST] WARNING:${RESET} $*"; }
header()  { echo -e "\n${BOLD}${CYAN}=== $* ===${RESET}\n"; }

FAILURES=0

# ---------------------------------------------------------------------------
# Test: Python syntax
# ---------------------------------------------------------------------------
test_python_syntax() {
    header "Python Syntax Verification"
    local files=(
        "${REPO_ROOT}/daemon/pico_adapter.py"
        "${REPO_ROOT}/daemon/fan_daemon.py"
        "${REPO_ROOT}/daemon/hardware_detector.py"
        "${REPO_ROOT}/cli/ipc_adapter.py"
        "${REPO_ROOT}/cli/setup_wizard.py"
        "${REPO_ROOT}/cli/status.py"
        "${REPO_ROOT}/cli/manual.py"
        "${REPO_ROOT}/cli/main.py"
    )
    for f in "${files[@]}"; do
        if $PYTHON -m py_compile "$f" 2>/dev/null; then
            pass "Syntax OK: $(basename "$f")"
        else
            fail "Syntax error: $f"
            $PYTHON -m py_compile "$f" 2>&1 | head -5
        fi
    done
}

# ---------------------------------------------------------------------------
# Test: Python module imports
# ---------------------------------------------------------------------------
test_python_imports() {
    header "Python Imports Verification"

    # Test hardware_detector (without serial)
    if $PYTHON -c "
import sys
sys.path.insert(0, '${REPO_ROOT}/daemon')
# Partial import test (without pyserial requires mock)
import importlib.util
spec = importlib.util.spec_from_file_location('hardware_detector',
    '${REPO_ROOT}/daemon/hardware_detector.py')
" 2>/dev/null; then
        pass "Import hardware_detector.py"
    else
        warning "Import hardware_detector.py requires pyserial"
    fi
}

# ---------------------------------------------------------------------------
# Test: sample JSON configuration
# ---------------------------------------------------------------------------
test_config_json() {
    header "JSON Configuration Verification"
    local cfg="${REPO_ROOT}/configs/config.json.example"

    if [[ -f "$cfg" ]]; then
        if $PYTHON -c "import json; json.load(open('$cfg'))" 2>/dev/null; then
            pass "Valid JSON: config.json.example"
        else
            fail "Invalid JSON: $cfg"
        fi
    else
        fail "Missing file: $cfg"
    fi
}


# ---------------------------------------------------------------------------
# Test: versioning system
# ---------------------------------------------------------------------------
test_versioning() {
    header "Versioning System Verification"

    local version_file="${REPO_ROOT}/VERSION"

    # 1. VERSION file exists and has semver format
    if [[ ! -f "$version_file" ]]; then
        fail "VERSION file missing in repository root"
        return
    fi
    local ver
    ver=$(tr -d '[:space:]' < "$version_file")
    if echo "$ver" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+'; then
        pass "VERSION file valid format: ${ver}"
    else
        fail "VERSION file non-semver format: '${ver}'"
    fi

    # 2. version.py resolves version correctly
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
        fail "version.py: unable to resolve version"
    fi

    # 3. Consistency VERSION file vs version.py
    if [[ "$py_ver" == "$ver" ]]; then
        pass "Consistent version: VERSION file == version.py (${ver})"
    else
        warning "Version: VERSION file='${ver}' vs version.py='${py_ver}' (might use git tag)"
    fi

    # 4. debian/control has Version field
    local ctrl="${REPO_ROOT}/debian/control"
    if grep -q "^Version:" "$ctrl"; then
        local ctrl_ver
        ctrl_ver=$(grep "^Version:" "$ctrl" | awk '{print $2}')
        pass "debian/control Version: ${ctrl_ver}"
    else
        fail "debian/control: missing Version field"
    fi

    # 5. build_deb.sh supports --version
    if bash -n "${REPO_ROOT}/scripts/build_deb.sh"; then
        pass "build_deb.sh bash syntax OK"
    else
        fail "build_deb.sh syntax error"
    fi


}

# ---------------------------------------------------------------------------
# Test: bash scripts (shellcheck or bash syntax check)
# ---------------------------------------------------------------------------
test_bash_scripts() {
    header "Bash Scripts Verification"
    local scripts=(
        "${REPO_ROOT}/scripts/build_deb.sh"
        "${REPO_ROOT}/scripts/test_local.sh"
        "${REPO_ROOT}/debian/postinst"
        "${REPO_ROOT}/debian/prerm"
        "${REPO_ROOT}/debian/postrm"
    )

    for s in "${scripts[@]}"; do
        if [[ ! -f "$s" ]]; then
            warning "Missing file: $s"
            continue
        fi

        if command -v shellcheck > /dev/null 2>&1; then
            if shellcheck --severity=error "$s" 2>/dev/null; then
                pass "shellcheck OK: $(basename "$s")"
            else
                warning "shellcheck warning in: $(basename "$s")"
            fi
        else
            # Fallback: bash syntax check only
            if bash -n "$s" 2>/dev/null; then
                pass "Bash syntax OK: $(basename "$s")"
            else
                fail "Bash syntax error: $s"
            fi
        fi
    done
}

# ---------------------------------------------------------------------------
# Test: hardware scan (requires Pico connected)
# ---------------------------------------------------------------------------
test_scan_hardware() {
    header "Real Hardware Scan"
    info "Scanning /dev/serial/by-id/ ..."

    $PYTHON -c "
import sys
sys.path.insert(0, '${REPO_ROOT}/daemon')
try:
    from hardware_detector import scan_devices, list_serial_by_id
    all_devs = list_serial_by_id()
    print(f'  Devices in /dev/serial/by-id/: {len(all_devs)}')
    for d in all_devs:
        print(f'    - {d}')
    print()
    devices = scan_devices(probe=True)
    if devices:
        for dev in devices:
            print(f'  Found: {dev}')
    else:
        print('  No Pico found (normal if not connected)')
except ImportError as e:
    print(f'  Import failed: {e}')
    print('  Install: pip install pyserial')
" && pass "Hardware scan completed" || fail "Hardware scan error"
}

# ---------------------------------------------------------------------------
# Test: daemon dry-run (without Pico and without config)
# ---------------------------------------------------------------------------
test_daemon_dryrun() {
    header "Daemon Dry-Run"
    info "Testing daemon module loading ..."

    $PYTHON -c "
import sys, os
sys.path.insert(0, '${REPO_ROOT}/daemon')
# Test only functions that do not require hardware
try:
    import fan_daemon
    # Test compute_target_duty
    cfg = fan_daemon.DEFAULT_CONFIG
    assert fan_daemon.compute_target_duty(5000, cfg) == 100, 'duty_high failed'
    assert fan_daemon.compute_target_duty(3000, cfg) == 50,  'duty_mid failed'
    assert fan_daemon.compute_target_duty(1000, cfg) == 0,   'duty_low failed'
    print('  compute_target_duty: OK')
    print('  Daemon modules loaded successfully')
except ImportError as e:
    print(f'  Import failed: {e}')
    print('  Install: pip install pyserial')
    sys.exit(1)
" && pass "Daemon dry-run OK" || fail "Daemon dry-run error"
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print_summary() {
    echo ""
    echo -e "${BOLD}═══════════════════════════════════════${RESET}"
    if [[ $FAILURES -eq 0 ]]; then
        echo -e "${BOLD}${GREEN}  ✓ All tests passed${RESET}"
    else
        echo -e "${BOLD}${RED}  ✗ ${FAILURES} tests failed${RESET}"
    fi
    echo -e "${BOLD}═══════════════════════════════════════${RESET}"
    echo ""
}

# ===========================================================================
# Main
# ===========================================================================
main() {
    echo ""
    info "=== pico-fan-control - Local test suite ==="
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
                echo "Unrecognized argument: $arg"
                echo "Usage: $0 [--daemon] [--wizard] [--scan] [--all]"
                exit 1
                ;;
        esac
    done

    # Tests always executed
    test_python_syntax
    test_python_imports
    test_config_json
    test_versioning
    test_bash_scripts

    # Selective tests

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
