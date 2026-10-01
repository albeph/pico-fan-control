#!/usr/bin/env python3
"""
wizard_helpers.py - Shared interactive helpers for CLI wizards
===============================================================
Provides reusable prompt functions (ask, ask_yes_no, pick_from_list,
separator) used by both setup_wizard and temp_wizard.

Extracted to its own module to avoid circular imports between
setup_wizard ↔ temp_wizard.
"""

from __future__ import annotations

import sys
from typing import Optional

from ANSI_colors import CYAN, DIM, WHITE, YELLOW, cprint, cwrite


def separator(title: str = "") -> None:
    width = 60
    if title:
        pad = (width - len(title) - 2) // 2
        cprint(f"\n{'─' * pad} {title} {'─' * pad}\n", CYAN)
    else:
        cprint("─" * width, DIM)


def ask(prompt: str, default: str = "") -> str:
    """Interactive prompt with default value support."""
    if default:
        full_prompt = f"{prompt} [{default}]: "
    else:
        full_prompt = f"{prompt}: "
    cwrite(full_prompt, WHITE, bold=True)
    sys.stdout.flush()
    try:
        answer = input().strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return answer if answer else default


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    """Prompts for Y/N confirmation."""
    hint = "Y/n" if default else "y/N"
    answer = ask(f"{prompt} ({hint})", "y" if default else "n")
    return answer.lower() in ("y", "yes", "s", "si", "sì", "1", "true")


def pick_from_list(items: list, prompt: str = "Scelta") -> Optional[int]:
    """Displays a numbered list and prompts the user to select an option."""
    for i, item in enumerate(items, 1):
        cprint(f"  [{i}] {item}", WHITE)
    answer = ask(f"\n{prompt} (1-{len(items)})", "1")
    try:
        idx = int(answer) - 1
        if 0 <= idx < len(items):
            return idx
    except ValueError:
        pass
    cprint("Scelta non valida, uso la prima opzione.", YELLOW)
    return 0
