"""Colour assignment result (ADS 5.2)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ColorRef:
    """A bar's colours. `index` and `name` are None for a custom hex colour (RS CO-4, 5.3)."""

    index: int | None
    name: str | None
    fill: str  # #RRGGBB, upper case
    accent: str  # left border
    text: str  # bar text colour
