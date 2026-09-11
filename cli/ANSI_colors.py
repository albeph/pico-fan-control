import os
import sys

_COLOR = (
    hasattr(sys.stdout, "isatty")
    and sys.stdout.isatty()
    and os.environ.get("TERM", "") != "dumb"
)

RESET = "\033[0m" if _COLOR else ""
BOLD = "\033[1m" if _COLOR else ""
RED = "\033[91m" if _COLOR else ""
GREEN = "\033[92m" if _COLOR else ""
YELLOW = "\033[93m" if _COLOR else ""
CYAN = "\033[96m" if _COLOR else ""
WHITE = "\033[97m" if _COLOR else ""
DIM = "\033[2m" if _COLOR else ""


def supports_color() -> bool:
    """Restituisce se il terminale corrente supporta i colori ANSI."""
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    return os.environ.get("TERM", "") != "dumb"


def cwrite(text: str, color: str = RESET, bold: bool = False) -> None:
    """Scrive testo colorato senza aggiungere un newline."""
    if supports_color():
        prefix = (BOLD if bold else "") + color
        sys.stdout.write(f"{prefix}{text}{RESET}")
    else:
        sys.stdout.write(text)


def cformat(text: str, color: str = RESET, bold: bool = False) -> str:
    """Restituisce testo colorato per inserirlo in una stringa più ampia."""
    if not supports_color():
        return text
    prefix = (BOLD if bold else "") + color
    return f"{prefix}{text}{RESET}"


def cprint(text: str, color: str = RESET, bold: bool = False) -> None:
    """Stampa testo colorato solo quando l'output è un terminale ANSI."""
    cwrite(text, color, bold)
    sys.stdout.write("\n")