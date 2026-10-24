"""Palette and custom colours (RS 5.3, CO-4)."""

from __future__ import annotations

from fractions import Fraction

import pytest

from rt.color.palette import (
    DARK_TEXT,
    LIGHT_TEXT,
    PALETTE,
    by_name,
    contrast_ratio,
    custom_color,
    darken,
    hsl_to_rgb,
    key_label,
    key_ref,
    palette_ref,
    rgb_to_hsl,
    spec_key,
    text_color,
)
from rt.color.types import ColorRef
from rt.model.types import ColorSpec


def test_palette_table() -> None:
    assert [(e.index, e.name, e.fill, e.accent) for e in PALETTE][:2] == [
        (0, "indigo", "#C7D2FE", "#6366F1"),
        (1, "green", "#BBF7D0", "#22C55E"),
    ]
    assert [e.name for e in PALETTE] == [
        "indigo",
        "green",
        "orange",
        "pink",
        "sky",
        "amber",
        "violet",
        "teal",
        "lime",
        "sand",
    ]
    assert palette_ref(4) == ColorRef(4, "sky", "#BAE6FD", "#0EA5E9", DARK_TEXT)
    assert by_name("teal") is PALETTE[7] and by_name("red") is None


def test_palette_text_contrast_at_least_9() -> None:
    for e in PALETTE:
        assert contrast_ratio(DARK_TEXT, e.fill) >= 9
        assert text_color(e.fill) == DARK_TEXT


def test_spec_key_mapping() -> None:
    assert spec_key(ColorSpec("sky", None, "sky")) == 4
    assert spec_key(ColorSpec(None, "#BAE6FD", "#bae6fd")) == 4  # hex equal to a palette fill
    assert spec_key(ColorSpec(None, "#123456", "#123456")) == "#123456"
    assert spec_key(ColorSpec(None, None, "#abcdef")) == "#ABCDEF"
    assert key_label(4) == "sky" and key_label("#123456") == "#123456"
    assert key_ref(7).name == "teal"
    assert key_ref("#123456").index is None


@pytest.mark.parametrize(
    ("fill", "accent", "text"),
    [
        ("#FF0000", "#A60000", LIGHT_TEXT),  # L 0.5 → 0.325
        ("#808080", "#535353", LIGHT_TEXT),
        ("#FFFFFF", "#A6A6A6", DARK_TEXT),
        ("#000000", "#000000", LIGHT_TEXT),
        ("#ffe4e6", "#FF3B49", DARK_TEXT),
    ],
)
def test_custom_color(fill: str, accent: str, text: str) -> None:
    ref = custom_color(fill)
    assert ref == ColorRef(None, None, fill.upper(), accent, text)


def test_darken_keeps_hue_and_saturation() -> None:
    for e in PALETTE:
        h, s, _ = rgb_to_hsl(*(int(e.fill[i : i + 2], 16) for i in (1, 3, 5)))
        dh, ds, _ = rgb_to_hsl(*(int(darken(e.fill)[i : i + 2], 16) for i in (1, 3, 5)))
        assert abs(float(h - dh)) < 3 and abs(float(s - ds)) < 0.05


@pytest.mark.parametrize("hex_value", ["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#00FFFF", "#FF00FF", "#123456"])
def test_hsl_round_trip(hex_value: str) -> None:
    rgb = tuple(int(hex_value[i : i + 2], 16) for i in (1, 3, 5))
    assert hsl_to_rgb(*rgb_to_hsl(*rgb)) == rgb


def test_hsl_sectors() -> None:
    assert hsl_to_rgb(Fraction(30), Fraction(1), Fraction(1, 2)) == (255, 128, 0)
    assert hsl_to_rgb(Fraction(90), Fraction(1), Fraction(1, 2)) == (128, 255, 0)
    assert hsl_to_rgb(Fraction(150), Fraction(1), Fraction(1, 2)) == (0, 255, 128)
    assert hsl_to_rgb(Fraction(210), Fraction(1), Fraction(1, 2)) == (0, 128, 255)
    assert hsl_to_rgb(Fraction(270), Fraction(1), Fraction(1, 2)) == (128, 0, 255)
    assert hsl_to_rgb(Fraction(330), Fraction(1), Fraction(1, 2)) == (255, 0, 128)


def test_bad_hex() -> None:
    with pytest.raises(ValueError):
        darken("#FFF")
