"""
version.py - Single Version Source for pico-fan-control
=========================================================
All Python modules import __version__ from here.

Resolution strategy (in order of priority):
  1. VERSION file installed in /usr/lib/pico-fan/VERSION (runtime, .deb package)
  2. VERSION file in parent repository root (development environment)
  3. "0.0.0+unknown" (safe fallback)
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Candidates for VERSION file (in order of priority)
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).parent.resolve()

_VERSION_CANDIDATES: list[Path] = [
    Path("/usr/lib/pico-fan/VERSION"),          # installed via .deb
    _THIS_DIR.parent / "VERSION",               # daemon/ -> repo root
    _THIS_DIR / "VERSION",                      # if copied locally
]


def _read_version_file() -> str | None:
    """Reads the VERSION file from the first existing candidate path."""
    for candidate in _VERSION_CANDIDATES:
        try:
            content = candidate.read_text().strip()
            if content:
                return content
        except OSError:
            continue
    return None



def _resolve_version() -> str:
    """Resolves the version string using the fallback strategy."""
    # 1. VERSION file (installed or in repository)
    v = _read_version_file()
    if v:
        return v

    # 2. Fallback
    return "0.0.0+unknown"


# Version as a semver string (e.g. "1.0.0")
__version__: str = _resolve_version()

# Numeric tuple for programmatic comparisons (e.g. (1, 0, 0))
# Handles post-tag versions like "1.2.3-5-gabcdef"
def _to_tuple(v: str) -> tuple[int, ...]:
    """Converts "1.2.3" or "1.2.3-5-gabc" into (1, 2, 3)."""
    base = v.split("-")[0].split("+")[0]
    try:
        return tuple(int(x) for x in base.split("."))
    except ValueError:
        return (0, 0, 0)


VERSION_TUPLE: tuple[int, ...] = _to_tuple(__version__)


if __name__ == "__main__":
    print(f"pico-fan-control version: {__version__}")
    print(f"Tuple: {VERSION_TUPLE}")
