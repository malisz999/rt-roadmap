"""The fixed 32-colour palette and custom hex colour derivation (RS 5.3, CO-4).

Entries 0–9 colour standalone bars; products take 10–31 first, then 0–9 (RS 5.2).

Custom colours: the accent is the same hue with HSL lightness multiplied by 0.65 ("darkened by 35 %", read as a
relative reduction), computed exactly with fractions and rounded half up per channel. The text colour is
`#1E293B` when its WCAG 2 contrast ratio against the fill is at least 4.5:1, else `#FFFFFF`.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from rt.color.types import ColorRef
from rt.decimalutil import half_up
from rt.model.types import ColorSpec

DARK_TEXT = "#1E293B"
LIGHT_TEXT = "#FFFFFF"
MIN_CONTRAST = 4.5
ACCENT_LIGHTNESS = Fraction(65, 100)  # L × 0.65 = lightness reduced by 35 %


@dataclass(frozen=True, slots=True)
class PaletteEntry:
    index: int
    name: str
    fill: str
    accent: str

    def ref(self) -> ColorRef:
        return ColorRef(self.index, self.name, self.fill, self.accent, DARK_TEXT)


PALETTE: tuple[PaletteEntry, ...] = (
    PaletteEntry(0, "indigo", "#C7D2FE", "#6366F1"),
    PaletteEntry(1, "green", "#BBF7D0", "#22C55E"),
    PaletteEntry(2, "orange", "#FED7AA", "#F97316"),
    PaletteEntry(3, "pink", "#FBCFE8", "#EC4899"),
    PaletteEntry(4, "sky", "#BAE6FD", "#0EA5E9"),
    PaletteEntry(5, "amber", "#FDE68A", "#D97706"),
    PaletteEntry(6, "violet", "#DDD6FE", "#8B5CF6"),
    PaletteEntry(7, "teal", "#99F6E4", "#14B8A6"),
    PaletteEntry(8, "lime", "#D9F99D", "#65A30D"),
    PaletteEntry(9, "sand", "#EADBC8", "#A16207"),
    # 10–31: extra entries for products (RS 5.3); text contrast ≥ 7:1.
    PaletteEntry(10, "blue", "#BFDBFE", "#3B82F6"),
    PaletteEntry(11, "cyan", "#A5F3FC", "#06B6D4"),
    PaletteEntry(12, "emerald", "#A7F3D0", "#10B981"),
    PaletteEntry(13, "yellow", "#FEF08A", "#CA8A04"),
    PaletteEntry(14, "fuchsia", "#F5D0FE", "#D946EF"),
    PaletteEntry(15, "purple", "#E9D5FF", "#A855F7"),
    PaletteEntry(16, "stone", "#E7E5E4", "#78716C"),
    PaletteEntry(17, "sand-deep", "#D6C3A5", "#854D0E"),
    PaletteEntry(18, "indigo-deep", "#A5B4FC", "#4F46E5"),
    PaletteEntry(19, "green-deep", "#86EFAC", "#16A34A"),
    PaletteEntry(20, "orange-deep", "#FDBA74", "#EA580C"),
    PaletteEntry(21, "pink-deep", "#F9A8D4", "#DB2777"),
    PaletteEntry(22, "sky-deep", "#7DD3FC", "#0284C7"),
    PaletteEntry(23, "amber-deep", "#FCD34D", "#B45309"),
    PaletteEntry(24, "violet-deep", "#C4B5FD", "#7C3AED"),
    PaletteEntry(25, "teal-deep", "#5EEAD4", "#0D9488"),
    PaletteEntry(26, "lime-deep", "#BEF264", "#4D7C0F"),
    PaletteEntry(27, "blue-deep", "#93C5FD", "#2563EB"),
    PaletteEntry(28, "cyan-deep", "#67E8F9", "#0891B2"),
    PaletteEntry(29, "emerald-deep", "#6EE7B7", "#059669"),
    PaletteEntry(30, "fuchsia-deep", "#F0ABFC", "#C026D3"),
    PaletteEntry(31, "purple-deep", "#D8B4FE", "#9333EA"),
)
PALETTE_SIZE = len(PALETTE)
BASE: tuple[int, ...] = tuple(range(10))  # standalone bars: DSATUR over these only (RS CO-5)
PRODUCT_ORDER: tuple[int, ...] = (*range(10, PALETTE_SIZE), *BASE)  # automatic product colours (RS 5.2)
_BY_NAME = {e.name: e for e in PALETTE}
_BY_FILL = {e.fill: e for e in PALETTE}

# A colour key: a palette index, or an upper-case `#RRGGBB` for a custom colour (ADS 6.5).
ColorKey = int | str


def by_name(name: str) -> PaletteEntry | None:
    return _BY_NAME.get(name)


def palette_ref(index: int) -> ColorRef:
    return PALETTE[index].ref()


def spec_key(spec: ColorSpec) -> ColorKey:
    """Palette name or a hex equal to a palette fill → that palette index; any other hex → the hex (CO-4)."""
    if spec.palette_name is not None:
        entry = _BY_NAME.get(spec.palette_name)
        if entry is not None:
            return entry.index
    hex_value = (spec.hex or spec.text).upper()
    entry = _BY_FILL.get(hex_value)
    return entry.index if entry is not None else hex_value


def key_ref(key: ColorKey) -> ColorRef:
    return palette_ref(key) if isinstance(key, int) else custom_color(key)


def key_label(key: ColorKey) -> str:
    """Name used in messages: palette name or the hex value."""
    return PALETTE[key].name if isinstance(key, int) else key


# --- custom colours ------------------------------------------------------------------------------------------


def _parse_hex(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    if len(text) != 6:
        raise ValueError(f"not a #RRGGBB colour: {value!r}")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def rgb_to_hsl(r: int, g: int, b: int) -> tuple[Fraction, Fraction, Fraction]:
    """Exact HSL: hue in degrees [0, 360), saturation and lightness in [0, 1]."""
    rf, gf, bf = Fraction(r, 255), Fraction(g, 255), Fraction(b, 255)
    hi, lo = max(rf, gf, bf), min(rf, gf, bf)
    lightness = (hi + lo) / 2
    delta = hi - lo
    if delta == 0:
        return Fraction(0), Fraction(0), lightness
    saturation = delta / (1 - abs(2 * lightness - 1))
    if hi == rf:
        hue = 60 * (((gf - bf) / delta) % 6)
    elif hi == gf:
        hue = 60 * ((bf - rf) / delta + 2)
    else:
        hue = 60 * ((rf - gf) / delta + 4)
    return hue, saturation, lightness


def hsl_to_rgb(hue: Fraction, saturation: Fraction, lightness: Fraction) -> tuple[int, int, int]:
    """Exact inverse of rgb_to_hsl; channels rounded half up."""
    chroma = (1 - abs(2 * lightness - 1)) * saturation
    sector = hue / 60
    x = chroma * (1 - abs(sector % 2 - 1))
    m = lightness - chroma / 2
    if sector < 1:
        r1, g1, b1 = chroma, x, Fraction(0)
    elif sector < 2:
        r1, g1, b1 = x, chroma, Fraction(0)
    elif sector < 3:
        r1, g1, b1 = Fraction(0), chroma, x
    elif sector < 4:
        r1, g1, b1 = Fraction(0), x, chroma
    elif sector < 5:
        r1, g1, b1 = x, Fraction(0), chroma
    else:
        r1, g1, b1 = chroma, Fraction(0), x
    r, g, b = (min(255, max(0, half_up((c + m) * 255))) for c in (r1, g1, b1))
    return r, g, b


def darken(hex_value: str, factor: Fraction = ACCENT_LIGHTNESS) -> str:
    """Same hue and saturation, HSL lightness multiplied by `factor`."""
    hue, saturation, lightness = rgb_to_hsl(*_parse_hex(hex_value))
    return _to_hex(*hsl_to_rgb(hue, saturation, lightness * factor))


def _channel(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_value: str) -> float:
    """WCAG 2 relative luminance."""
    r, g, b = _parse_hex(hex_value)
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(first: str, second: str) -> float:
    a, b = relative_luminance(first), relative_luminance(second)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def text_color(fill: str) -> str:
    return DARK_TEXT if contrast_ratio(DARK_TEXT, fill) >= MIN_CONTRAST else LIGHT_TEXT


def custom_color(hex_value: str) -> ColorRef:
    """A custom `#RRGGBB` colour: index and name None, derived accent and text (RS 5.3)."""
    fill = hex_value.upper()
    return ColorRef(None, None, fill, darken(fill), text_color(fill))
