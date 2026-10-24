"""Human messages on stderr: diagnostics and the summary line (RS CLI-6 to CLI-8, ST-7)."""

from __future__ import annotations

from collections.abc import Iterable

from rt.diagnostics import Diagnostic, Severity, format_text
from rt.io.streams import IOPort

_RED = "\x1b[31m"
_YELLOW = "\x1b[33m"
_RESET = "\x1b[0m"


def use_color(io: IOPort) -> bool:
    """Coloured output only when stderr is a terminal and NO_COLOR is unset (RS CLI-8)."""
    return io.stderr_is_tty() and io.getenv("NO_COLOR") is None


def print_diagnostics(io: IOPort, diags: Iterable[Diagnostic], *, quiet: bool = False) -> None:
    """One line per diagnostic in the given order; `quiet` drops warnings, never errors."""
    color = use_color(io)
    for d in diags:
        if quiet and d.severity is Severity.WARNING:
            continue
        line = format_text(d)
        if color:
            tint = _RED if d.severity is Severity.ERROR else _YELLOW
            line = f"{tint}{line}{_RESET}"
        io.err(line + "\n")


def print_line(io: IOPort, text: str, *, quiet: bool = False) -> None:
    """The success summary line, e.g. `rt: wrote roadmap.html — 3 subdomains, …` (RS CLI-7)."""
    if not quiet:
        io.err(text + "\n")


def plural(count: int, word: str) -> str:
    """`1 warning`, `2 warnings`, `0 warnings`."""
    return f"{count} {word}" if count == 1 else f"{count} {word}s"
