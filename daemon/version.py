"""
version.py - Sorgente unica della versione per pico-fan-control
================================================================
Tutti i moduli Python importano __version__ da qui.

Strategia di risoluzione (in ordine di priorità):
  1. File VERSION installato in /usr/lib/pico-fan/VERSION  (runtime, .deb)
  2. File VERSION nella root del repository               (sviluppo locale)
  3. Tag git più recente (git describe --tags)             (sviluppo locale)
  4. "0.0.0+unknown"                                       (fallback sicuro)

Autore:   pico-fan-control project
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Candidati per il file VERSION (in ordine di priorità)
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).parent.resolve()

_VERSION_CANDIDATES: list[Path] = [
    Path("/usr/lib/pico-fan/VERSION"),          # installato via .deb
    _THIS_DIR.parent / "VERSION",               # daemon/ → root repo
    _THIS_DIR / "VERSION",                      # se copiato localmente
]


def _read_version_file() -> str | None:
    """Legge il file VERSION dal primo candidato esistente."""
    for candidate in _VERSION_CANDIDATES:
        try:
            content = candidate.read_text().strip()
            if content:
                return content
        except OSError:
            continue
    return None


def _read_git_version() -> str | None:
    """
    Interroga git per ottenere la versione dall'ultimo tag annotato.
    Formato restituito: "1.2.3" o "1.2.3-5-gabcdef" (post-tag commits).
    Restituisce None se git non è disponibile o il repo non ha tag.
    """
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty=+dirty"],
            capture_output=True,
            text=True,
            timeout=3,
            cwd=str(_THIS_DIR),
        )
        if result.returncode == 0:
            tag = result.stdout.strip().lstrip("v")
            if tag:
                return tag
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _resolve_version() -> str:
    """Risolve la versione usando la strategia a cascata."""
    # 1. File VERSION (installato o nel repo)
    v = _read_version_file()
    if v:
        return v

    # 2. Tag git
    v = _read_git_version()
    if v:
        return v

    # 3. Fallback
    return "0.0.0+unknown"


# Versione come stringa semver (es. "1.0.0")
__version__: str = _resolve_version()

# Tuple numerica per confronti programmatici (es. (1, 0, 0))
# Gestisce versioni post-tag tipo "1.2.3-5-gabcdef"
def _to_tuple(v: str) -> tuple[int, ...]:
    """Converte "1.2.3" o "1.2.3-5-gabc" in (1, 2, 3)."""
    base = v.split("-")[0].split("+")[0]
    try:
        return tuple(int(x) for x in base.split("."))
    except ValueError:
        return (0, 0, 0)


VERSION_TUPLE: tuple[int, ...] = _to_tuple(__version__)


if __name__ == "__main__":
    print(f"pico-fan-control versione: {__version__}")
    print(f"Tuple: {VERSION_TUPLE}")
