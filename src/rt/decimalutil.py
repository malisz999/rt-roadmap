"""Half-up rounding helpers (ADR-7, ADS 9.2). The built-in round() is banned in src/."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Context, Decimal
from fractions import Fraction

_CTX = Context(prec=28, rounding=ROUND_HALF_UP)
_CENT = Decimal("0.01")
_RATIO = Decimal("0.0001")
_ONE = Decimal(1)

Number = int | Decimal | Fraction


def to_decimal(value: Number) -> Decimal:
    """Exact for int and Decimal; a Fraction is divided at 28 significant digits."""
    if isinstance(value, Fraction):
        return _CTX.divide(Decimal(value.numerator), Decimal(value.denominator))
    return Decimal(value)


def half_up(value: Number) -> int:
    """Round to an integer, halves away from zero."""
    return int(to_decimal(value).quantize(_ONE, rounding=ROUND_HALF_UP))


def px(value: Number) -> str:
    """Pixel string with exactly two decimals, half away from zero: `110.39`."""
    return str(to_decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP))


def pct(value: Number) -> int:
    """A ratio (0.7624…) as a whole percentage, half up: 76."""
    return half_up(to_decimal(value) * 100)


def ratio4(numerator: int, denominator: int) -> Decimal:
    """Exact ratio rounded half up to 4 decimals (plan `utilization`, `monthly_load`)."""
    if denominator == 0:
        return Decimal("0.0000")
    return to_decimal(Fraction(numerator, denominator)).quantize(_RATIO, rounding=ROUND_HALF_UP)


def fmt4(value: Decimal) -> str:
    """A 4-decimal value as written in `data-*` attributes: `0.7624`, `1.0000`."""
    return str(value.quantize(_RATIO, rounding=ROUND_HALF_UP))
