#!/usr/bin/env bash
# scripts/build_deb.sh - Script per la generazione del pacchetto .deb
# ====================================================================
# La versione viene rilevata automaticamente nell'ordine:
#   1. Argomento --version <ver> passato da CLI
#   2. Ultimo tag git annotato (git describe --tags --abbrev=0)
#   3. Contenuto del file VERSION nella root del repository
#   4. Fallback: "0.0.0+dev"
#
# Utilizzo:
#   ./scripts/build_deb.sh
#   ./scripts/build_deb.sh --version 1.2.3   (forza versione specifica)
#   ./scripts/build_deb.sh --clean            (pulisce senza costruire)
#
# Genera: pico-fan_<VERSION>_all.deb
#
# Requisiti:
#   - dpkg-dev (apt install dpkg-dev)

set -euo pipefail

# ---------------------------------------------------------------------------
# Path repository
# ---------------------------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_NAME="pico-fan"
ARCH="all"

# ---------------------------------------------------------------------------
# Rilevamento versione
# ---------------------------------------------------------------------------
_detect_version() {
    local forced_version="${1:-}"

    # 1. Versione forzata da CLI
    if [[ -n "$forced_version" ]]; then
        echo "$forced_version"
        return
    fi

    # 2. Tag git annotato (es. "v1.2.3" → "1.2.3")
    local git_tag
    git_tag=$(git -C "${REPO_ROOT}" describe --tags --abbrev=0 2>/dev/null \
              | sed 's/^v//' || true)
    if [[ -n "$git_tag" ]]; then
        echo "$git_tag"
        return
    fi

    # 3. File VERSION nella root
    local version_file="${REPO_ROOT}/VERSION"
    if [[ -f "$version_file" ]]; then
        local file_ver
        file_ver=$(tr -d '[:space:]' < "$version_file")
        if [[ -n "$file_ver" ]]; then
            echo "$file_ver"
            return
        fi
    fi

    # 4. Fallback
    echo "0.0.0+dev"
}

# ---------------------------------------------------------------------------
# Parse argomenti CLI
# ---------------------------------------------------------------------------
FORCED_VERSION=""
DO_CLEAN_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            FORCED_VERSION="${2:?'--version richiede un argomento'}"
            shift 2
            ;;
        --clean)
            DO_CLEAN_ONLY=true
            shift
            ;;
        *)
            echo "Argomento non riconosciuto: $1"
            echo "Uso: $0 [--version <ver>] [--clean]"
            exit 1
            ;;
    esac
done

VERSION=$(_detect_version "$FORCED_VERSION")
DEB_FILE="${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
BUILD_DIR="${REPO_ROOT}/build"
PKG_DIR="${BUILD_DIR}/${PACKAGE_NAME}_${VERSION}_${ARCH}"

# ---------------------------------------------------------------------------
# Directory di destinazione dentro il pacchetto
# ---------------------------------------------------------------------------
DEST_LIB="${PKG_DIR}/usr/lib/pico-fan"
DEST_BIN="${PKG_DIR}/usr/bin"
DEST_SYSTEMD="${PKG_DIR}/lib/systemd/system"
DEST_UDEV="${PKG_DIR}/etc/udev/rules.d"
DEST_DEBIAN="${PKG_DIR}/DEBIAN"

# ---------------------------------------------------------------------------
# Colori
# ---------------------------------------------------------------------------
info()    { echo -e "\033[92m[BUILD]\033[0m $*"; }
warning() { echo -e "\033[93m[BUILD] AVVISO:\033[0m $*"; }
error()   { echo -e "\033[91m[BUILD] ERRORE:\033[0m $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
check_deps() {
    local missing=()
    for cmd in dpkg-deb sed; do
        command -v "$cmd" > /dev/null 2>&1 || missing+=("$cmd")
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        error "Dipendenze mancanti: ${missing[*]}\nInstallare: apt install dpkg-dev"
    fi
}

# ---------------------------------------------------------------------------
clean_build() {
    info "Pulizia directory di build ..."
    rm -rf "${BUILD_DIR}"
    rm -f "${REPO_ROOT}/${PACKAGE_NAME}"_*.deb
    info "Pulizia completata."
}

# ---------------------------------------------------------------------------
create_dirs() {
    info "Creazione struttura directory ..."
    mkdir -p \
        "${DEST_LIB}/kernel_module" \
        "${DEST_LIB}/daemon" \
        "${DEST_LIB}/cli" \
        "${DEST_BIN}" \
        "${DEST_SYSTEMD}" \
        "${DEST_UDEV}" \
        "${DEST_DEBIAN}"
}

# ---------------------------------------------------------------------------
install_files() {
    info "Copia file sorgente ..."

    # Firmware (per riferimento, non eseguito sull'host)
    cp -r "${REPO_ROOT}/firmware" "${DEST_LIB}/"

    # Kernel module rimosso come richiesto

    # Daemon Python
    cp "${REPO_ROOT}/daemon/fan_daemon.py"        "${DEST_LIB}/daemon/"
    cp "${REPO_ROOT}/daemon/hardware_detector.py" "${DEST_LIB}/daemon/"
    cp "${REPO_ROOT}/daemon/version.py"           "${DEST_LIB}/daemon/"

    # CLI
    cp "${REPO_ROOT}/cli/setup_wizard.py" "${DEST_LIB}/cli/"
    cp "${REPO_ROOT}/cli/status.py"       "${DEST_LIB}/cli/"
    cp "${REPO_ROOT}/cli/main.py"         "${DEST_LIB}/cli/"
    cp "${REPO_ROOT}/cli/manual.py"       "${DEST_LIB}/cli/"

    # File VERSION installato (per runtime version resolution)
    echo "${VERSION}" > "${DEST_LIB}/VERSION"
    info "  VERSION=${VERSION} → /usr/lib/pico-fan/VERSION"

    # Config esempio
    cp "${REPO_ROOT}/configs/config.json.example" "${DEST_LIB}/"

    # systemd unit
    cp "${REPO_ROOT}/systemd/pico-fan.service" "${DEST_SYSTEMD}/"

    # udev rules
    cp "${REPO_ROOT}/udev/99-pico-fan.rules" "${DEST_UDEV}/"
}

# ---------------------------------------------------------------------------
create_wrappers() {
    info "Creazione wrapper eseguibili ..."

    cat > "${DEST_BIN}/pico-fan" << 'EOF'
#!/usr/bin/env bash
exec /usr/bin/python3 /usr/lib/pico-fan/cli/main.py "$@"
EOF

    chmod 755 "${DEST_BIN}/pico-fan"
}

# ---------------------------------------------------------------------------
create_debian_meta() {
    info "Generazione metadata DEBIAN ..."

    # Genera il control con la versione corretta iniettata, tenendo solo il blocco Package
    awk '/^Package: /{p=1} p' "${REPO_ROOT}/debian/control" > "${DEST_DEBIAN}/control"

    # Inietta o aggiorna la versione
    if grep -q "^Version:" "${DEST_DEBIAN}/control"; then
        sed -i "s/^Version:.*/Version: ${VERSION}/" "${DEST_DEBIAN}/control"
        info "  Version nel control aggiornato: ${VERSION}"
    else
        sed -i "s/^Package: .*/&\nVersion: ${VERSION}/" "${DEST_DEBIAN}/control"
        info "  Campo Version aggiunto al control: ${VERSION}"
    fi

    # Script hook
    for script in postinst prerm postrm; do
        if [[ -f "${REPO_ROOT}/debian/${script}" ]]; then
            cp "${REPO_ROOT}/debian/${script}" "${DEST_DEBIAN}/${script}"
            chmod 755 "${DEST_DEBIAN}/${script}"
        fi
    done

    # Dimensione installata
    local installed_size
    installed_size=$(du -sk "${PKG_DIR}" | cut -f1)
    if grep -q "^Installed-Size:" "${DEST_DEBIAN}/control"; then
        sed -i "s/^Installed-Size:.*/Installed-Size: ${installed_size}/" \
            "${DEST_DEBIAN}/control"
    fi

    # md5sums
    info "Calcolo checksum ..."
    (
        cd "${PKG_DIR}"
        find . -type f ! -path './DEBIAN/*' \
            -exec md5sum {} \; | sort > "${DEST_DEBIAN}/md5sums"
    )
}

# ---------------------------------------------------------------------------
set_permissions() {
    info "Impostazione permessi ..."
    find "${PKG_DIR}" -type d -exec chmod 755 {} \;
    find "${PKG_DIR}/usr" -type f -exec chmod 644 {} \;
    find "${PKG_DIR}/lib" -type f -exec chmod 644 {} \;
    chmod 755 "${DEST_BIN}/pico-fan"
    for s in postinst prerm postrm; do
        [[ -f "${DEST_DEBIAN}/${s}" ]] && chmod 755 "${DEST_DEBIAN}/${s}"
    done
    find "${DEST_LIB}" -name "*.py" -exec chmod 644 {} \;
}

# ---------------------------------------------------------------------------
build_deb() {
    info "Costruzione pacchetto .deb ..."
    dpkg-deb --build --root-owner-group "${PKG_DIR}" "${REPO_ROOT}/${DEB_FILE}"

    echo ""
    info "✓ Pacchetto generato: ${REPO_ROOT}/${DEB_FILE}"
    echo ""
    info "=== Informazioni pacchetto ==="
    dpkg-deb --info "${REPO_ROOT}/${DEB_FILE}"
}

# ===========================================================================
# Main
# ===========================================================================
main() {
    local ver_source="fallback"
    [[ -n "$FORCED_VERSION" ]] && ver_source="CLI --version" || \
    { git -C "${REPO_ROOT}" describe --tags --abbrev=0 &>/dev/null 2>&1 && ver_source="git tag"; } || \
    { [[ -f "${REPO_ROOT}/VERSION" ]] && ver_source="file VERSION"; } || true

    echo ""
    info "=== Build pico-fan v${VERSION} ==="
    info "    Sorgente versione: ${ver_source}"
    echo ""

    check_deps

    if $DO_CLEAN_ONLY; then
        clean_build
        exit 0
    fi

    [[ -d "${BUILD_DIR}" ]] && clean_build

    create_dirs
    install_files
    create_wrappers
    create_debian_meta
    set_permissions
    build_deb

    echo ""
    info "Build completato!"
    info "  Installa con: sudo dpkg -i ${DEB_FILE}"
    info "  Rimuovi con:  sudo apt remove pico-fan"
    echo ""
}

main "$@"
