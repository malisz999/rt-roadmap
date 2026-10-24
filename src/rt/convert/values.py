"""Cell values: size, start, ongoing, depends_on (RS CV-8 to CV-12). Pure functions, no diagnostics."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

TRUE_WORDS = frozenset({"true", "yes", "y", "1", "x", "tak", "t"})
FALSE_WORDS = frozenset({"false", "no", "n", "0", "nie", ""})

_YM = re.compile(r"([0-9]{4})-([0-9]{2})")
_YMD = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_DMY = re.compile(r"([0-9]{2})\.([0-9]{2})\.([0-9]{4})")
_DEP_SPLIT = re.compile(r"[|\r\n]")


def match_size(value: str, labels: Sequence[str]) -> str | None:
    """Exact label, else the unique case-insensitive match (`m` → `M`), else None (RS CV-9)."""
    if value in labels:
        return value
    folded = value.casefold()
    hits = [label for label in labels if label.casefold() == folded]
    return hits[0] if len(hits) == 1 else None


@dataclass(frozen=True, slots=True)
class StartValue:
    month: str  # YYYY-MM
    day_dropped: bool  # a day other than 01 was given (W021)


def parse_start(value: str) -> StartValue | None:
    """`YYYY-MM`, `YYYY-MM-DD` or `DD.MM.YYYY` → `YYYY-MM`; None for anything else or an impossible date
    (RS CV-10)."""
    if m := _YM.fullmatch(value):
        year, month, day = int(m.group(1)), int(m.group(2)), 1
    elif m := _YMD.fullmatch(value):
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    elif m := _DMY.fullmatch(value):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        return None
    try:
        date(year, month, day)
    except ValueError:
        return None
    return StartValue(f"{year:04d}-{month:02d}", day != 1)


def parse_ongoing(value: str) -> bool | None:
    """True / False for the two word lists (case-insensitive), None for anything else (RS CV-11)."""
    folded = value.casefold()
    if folded in TRUE_WORDS:
        return True
    if folded in FALSE_WORDS:
        return False
    return None


def split_depends(value: str) -> list[str]:
    """Items separated by `|` or line breaks, each trimmed (cells are already NFC); empty items dropped
    (RS CV-12)."""
    return [item.strip() for item in _DEP_SPLIT.split(value) if item.strip()]
