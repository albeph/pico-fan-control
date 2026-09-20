#!/usr/bin/env bash
# scripts/build_deb.sh - Debian (.deb) package build script
# ==========================================================
# Version is resolved automatically in the following order:
#   1. CLI argument --version <ver>
#   2. Content of VERSION file in repository root
#   3. Latest annotated git tag (git describe --tags --abbrev=0)
#   4. Fallback: "0.0.0+dev"
#
# Usage:
#   ./scripts/build_deb.sh
#   ./scripts/build_deb.sh --version 1.2.3   (forces specific version)
#   ./scripts/build_deb.sh --clean            (cleans build files without packaging)
#
# Generates: pico-fan_<VERSION>_all.deb
#
# Requirements:
#   - dpkg-dev (apt install dpkg-dev)

set -euo pipefail

# ---------------------------------------------------------------------------
# Repository path
# ---------------------------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_NAME="pico-fan"
ARCH="all"

# ---------------------------------------------------------------------------
# Version detection
# ---------------------------------------------------------------------------
_detect_version() {
    local forced_version="${1:-}"

    # 1. Version forced from CLI
    if [[ -n "$forced_version" ]]; then
        echo "$forced_version"
        return
    fi

    # 2. VERSION file in repository root
    local version_file="${REPO_ROOT}/VERSION"
    if [[ -f "$version_file" ]]; then
        local file_ver
        file_ver=$(tr -d '[:space:]' < "$version_file")
        if [[ -n "$file_ver" ]]; then
            echo "$file_ver"
            return
        fi
    fi

    # 3. Annotated git tag (e.g. "v1.2.3" -> "1.2.3")
    local git_tag
    git_tag=$(git -C "${REPO_ROOT}" describe --tags --abbrev=0 2>/dev/null \
              | sed 's/^v//' || true)
    if [[ -n "$git_tag" ]]; then
        echo "$git_tag"
        return
    fi

    # 4. Fallback
    echo "0.0.0+dev"
}

# ---------------------------------------------------------------------------
# Parse CLI arguments
# ---------------------------------------------------------------------------
FORCED_VERSION=""
DO_CLEAN_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            FORCED_VERSION="${2:?'--version requires an argument'}"
            shift 2
            ;;
        --clean)
            DO_CLEAN_ONLY=true
            shift
            ;;
        *)
            echo "Unrecognized argument: $1"
            echo "Usage: $0 [--version <ver>] [--clean]"
            exit 1
            ;;
    esac
done

VERSION=$(_detect_version "$FORCED_VERSION")
DEB_FILE="${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
BUILD_DIR="${REPO_ROOT}/build"
PKG_DIR="${BUILD_DIR}/${PACKAGE_NAME}_${VERSION}_${ARCH}"

# ---------------------------------------------------------------------------
# Target directories inside package
# ---------------------------------------------------------------------------
DEST_LIB="${PKG_DIR}/usr/lib/pico-fan"
DEST_BIN="${PKG_DIR}/usr/bin"
DEST_SYSTEMD="${PKG_DIR}/lib/systemd/system"
DEST_DEBIAN="${PKG_DIR}/DEBIAN"

# ---------------------------------------------------------------------------
# Colors and logging
# ---------------------------------------------------------------------------
info()    { echo -e "\033[92m[BUILD]\033[0m $*"; }
warning() { echo -e "\033[93m[BUILD] WARNING:\033[0m $*"; }
error()   { echo -e "\033[91m[BUILD] ERROR:\033[0m $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
check_deps() {
    local missing=()
    for cmd in dpkg-deb sed; do
        command -v "$cmd" > /dev/null 2>&1 || missing+=("$cmd")
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        error "Missing dependencies: ${missing[*]}\nInstall with: apt install dpkg-dev"
    fi
}

# ---------------------------------------------------------------------------
clean_build() {
    info "Cleaning build directory ..."
    rm -rf "${BUILD_DIR}"
    rm -f "${REPO_ROOT}/${PACKAGE_NAME}"_*.deb
    find "${REPO_ROOT}" -name "*.pyc" -delete 2>/dev/null || true
    find "${REPO_ROOT}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    info "Cleanup complete."
}

# ---------------------------------------------------------------------------
create_dirs() {
    info "Creating directory structure ..."
    mkdir -p \
        "${DEST_LIB}/daemon" \
        "${DEST_LIB}/cli" \
        "${DEST_LIB}/firmware" \
        "${DEST_BIN}" \
        "${DEST_SYSTEMD}" \
        "${DEST_DEBIAN}"
}

# ---------------------------------------------------------------------------
install_files() {
    info "Copying source files ..."

    # Firmware (for reference, not executed on host)
    cp "${REPO_ROOT}/firmware/"*.py "${DEST_LIB}/firmware/"

    # Python daemon
    cp "${REPO_ROOT}/daemon/"*.py "${DEST_LIB}/daemon/"

    # CLI (including ANSI_colors.py, main.py, setup_wizard.py, status.py, manual.py, ipc_adapter.py)
    cp "${REPO_ROOT}/cli/"*.py "${DEST_LIB}/cli/"

    # Installed VERSION file (for runtime version resolution)
    echo "${VERSION}" > "${DEST_LIB}/VERSION"
    info "  VERSION=${VERSION} → /usr/lib/pico-fan/VERSION"

    # Example configuration
    cp "${REPO_ROOT}/configs/config.json.example" "${DEST_LIB}/"

    # systemd unit
    cp "${REPO_ROOT}/systemd/pico-fan.service" "${DEST_SYSTEMD}/"

    # udev rule is generated by setup wizard for selected USB serial ID
}

# ---------------------------------------------------------------------------
create_wrappers() {
    info "Creating executable CLI wrapper ..."

    cat > "${DEST_BIN}/pico-fan" << 'EOF'
#!/usr/bin/env bash
exec /usr/bin/python3 /usr/lib/pico-fan/cli/main.py "$@"
EOF

    chmod 755 "${DEST_BIN}/pico-fan"
}

# ---------------------------------------------------------------------------
create_debian_meta() {
    info "Generating DEBIAN metadata ..."

    # Generate control file with correct version injected, keeping Package block
    awk '/^Package: /{p=1} p' "${REPO_ROOT}/debian/control" > "${DEST_DEBIAN}/control"

    # Inject or update version field
    if grep -q "^Version:" "${DEST_DEBIAN}/control"; then
        sed -i "s/^Version:.*/Version: ${VERSION}/" "${DEST_DEBIAN}/control"
        info "  Version updated in control: ${VERSION}"
    else
        sed -i "s/^Package: .*/&\nVersion: ${VERSION}/" "${DEST_DEBIAN}/control"
        info "  Version field added to control: ${VERSION}"
    fi

    # Hook scripts
    for script in postinst prerm postrm; do
        if [[ -f "${REPO_ROOT}/debian/${script}" ]]; then
            cp "${REPO_ROOT}/debian/${script}" "${DEST_DEBIAN}/${script}"
            chmod 755 "${DEST_DEBIAN}/${script}"
        fi
    done

    # Installed size
    local installed_size
    installed_size=$(du -sk "${PKG_DIR}" | cut -f1)
    if grep -q "^Installed-Size:" "${DEST_DEBIAN}/control"; then
        sed -i "s/^Installed-Size:.*/Installed-Size: ${installed_size}/" \
            "${DEST_DEBIAN}/control"
    fi

    # md5sums
    info "Calculating checksums ..."
    (
        cd "${PKG_DIR}"
        find . -type f ! -path './DEBIAN/*' \
            -exec md5sum {} \; | sort > "${DEST_DEBIAN}/md5sums"
    )
}

# ---------------------------------------------------------------------------
set_permissions() {
    info "Setting file permissions ..."
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
    info "Building .deb package ..."
    dpkg-deb --build --root-owner-group "${PKG_DIR}" "${REPO_ROOT}/${DEB_FILE}"

    echo ""
    info "✓ Package generated: ${REPO_ROOT}/${DEB_FILE}"
    echo ""
    info "=== Package Information ==="
    dpkg-deb --info "${REPO_ROOT}/${DEB_FILE}"
}

# ===========================================================================
# Main
# ===========================================================================
main() {
    local ver_source="fallback"
    [[ -n "$FORCED_VERSION" ]] && ver_source="CLI --version" || \
    { [[ -f "${REPO_ROOT}/VERSION" ]] && ver_source="file VERSION"; } || \
    { git -C "${REPO_ROOT}" describe --tags --abbrev=0 &>/dev/null 2>&1 && ver_source="git tag"; } || true

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
