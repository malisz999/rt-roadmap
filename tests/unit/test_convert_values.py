"""convert.values: size, start, ongoing, depends_on (RS CV-9 to CV-12)."""

from __future__ import annotations

import pytest

from rt.convert.values import StartValue, match_size, parse_ongoing, parse_start, split_depends

LABELS = ["XS", "S", "M", "L", "XL"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [("M", "M"), ("m", "M"), ("xl", "XL"), ("XXL", None), ("", None)],
)
def test_match_size(value: str, expected: str | None) -> None:
    assert match_size(value, LABELS) == expected


def test_size_ambiguous_case_insensitive_match_is_none_but_exact_wins() -> None:
    assert match_size("m", ["M", "m2", "m"]) == "m"
    assert match_size("m", ["M", "XS"]) == "M"
    assert match_size("s", ["S", "XS", "S2"]) == "S"
    assert match_size("ab", ["AB", "Ab"]) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2027-03", StartValue("2027-03", False)),
        ("2027-03-01", StartValue("2027-03", False)),
        ("2027-03-15", StartValue("2027-03", True)),
        ("01.01.2027", StartValue("2027-01", False)),
        ("31.12.2027", StartValue("2027-12", True)),
        ("2028-02-29", StartValue("2028-02", True)),
    ],
)
def test_parse_start_valid(value: str, expected: StartValue) -> None:
    assert parse_start(value) == expected


@pytest.mark.parametrize(
    "value", ["2027-13", "2027-00", "2027-02-30", "32.01.2027", "2027/03", "1.1.2027", "marzec", "2027-3", "٢٠٢٧-٠٣"]
)
def test_parse_start_invalid(value: str) -> None:
    assert parse_start(value) is None


@pytest.mark.parametrize("value", ["true", "TAK", "Yes", "y", "1", "x", "X", "t"])
def test_ongoing_true(value: str) -> None:
    assert parse_ongoing(value) is True


@pytest.mark.parametrize("value", ["false", "NIE", "No", "n", "0", ""])
def test_ongoing_false(value: str) -> None:
    assert parse_ongoing(value) is False


@pytest.mark.parametrize("value", ["może", "2", "ongoing", "prawda"])
def test_ongoing_invalid(value: str) -> None:
    assert parse_ongoing(value) is None


def test_split_depends_on_pipe_and_line_breaks() -> None:
    assert split_depends("A | B|\nC\r\nD||") == ["A", "B", "C", "D"]
    assert split_depends("") == []
    assert split_depends("Portfele cyfrowe (Apple Pay; Google Pay)") == ["Portfele cyfrowe (Apple Pay; Google Pay)"]
