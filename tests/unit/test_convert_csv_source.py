"""convert.csv_source: decoding, delimiter detection, records (RS CV-1 to CV-5; E001, E101, E102, E106)."""

from __future__ import annotations

from pathlib import Path

import pytest

from rt.convert.csv_source import decode, detect_delimiter, read_csv, split_records
from rt.diagnostics import Collector
from rt.io.streams import MAX_INPUT_BYTES

PL_CSV = Path(__file__).resolve().parents[2] / "docs" / "fixtures" / "convert" / "projects.pl.csv"


def _codes(diags: Collector) -> list[tuple[str, int | None, int | None]]:
    return [(d.code.name, d.line, d.col) for d in diags.items]


def test_utf8_bom_is_accepted() -> None:
    diags = Collector()
    assert decode(b"\xef\xbb\xbfname,size\n", "x.csv", "utf-8", diags) == "name,size\n"
    assert decode(b"\xef\xbb\xbfa", "x.csv", "UTF8", diags) == "a"
    assert not diags.items


def test_cp1250_file_without_encoding_is_e102_at_1_21() -> None:
    data = PL_CSV.read_bytes().decode("utf-8-sig").encode("cp1250")
    diags = Collector()
    assert read_csv(data, "projects.pl.csv", "utf-8", None, diags) is None
    [d] = diags.items
    assert (d.code.name, d.line, d.col, d.source) == ("E102", 1, 21, "projects.pl.csv")
    assert d.message == "cannot decode byte 0xF3 as utf-8 at line 1, byte 21; try --encoding cp1250"


def test_cp1250_with_encoding_decodes() -> None:
    text = PL_CSV.read_bytes().decode("utf-8-sig")
    diags = Collector()
    table = read_csv(text.encode("cp1250"), "p.csv", "cp1250", None, diags)
    assert table is not None
    assert table.header.cells[2] == "Zespół"


def test_e102_line_and_byte_column_count_from_the_raw_bytes() -> None:
    diags = Collector()
    data = b"\xef\xbb\xbfname,size\nab\xb3c,M\n"
    assert decode(data, "x.csv", "utf-8", diags) is None
    [d] = diags.items
    assert (d.line, d.col) == (2, 3)


@pytest.mark.parametrize("data", [b"", b"   \n\r\n\t", b"\xef\xbb\xbf"])
def test_empty_input_is_e001(data: bytes) -> None:
    diags = Collector()
    assert read_csv(data, "<stdin>", "utf-8", None, diags) is None
    [d] = diags.items
    assert d.code.name == "E001"
    assert d.message == "input is empty (did the previous command fail?)"
    assert d.source == "<stdin>"


def test_input_over_5_mb_is_e001() -> None:
    diags = Collector()
    assert read_csv(b"a" * (MAX_INPUT_BYTES + 1), "big.csv", "utf-8", None, diags) is None
    [d] = diags.items
    assert d.code.name == "E001"
    assert "input too large" in d.message


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("name,size", ","),
        ("name;size;team", ";"),
        ("name\tsize", "\t"),
        ("name", ","),
        ("a,b;c", ","),  # tie → comma
        ("a;b\tc", ";"),  # tie → semicolon
        ('"a,b,c";d;e', ";"),  # delimiters inside quotes do not count
        ('"Projekt; nazwa",Rozmiar', ","),
    ],
)
def test_detect_delimiter(line: str, expected: str) -> None:
    assert detect_delimiter(line) == expected


def test_delimiter_option_overrides_detection() -> None:
    diags = Collector()
    table = read_csv(b"name;x,size\nA;b,M\n", "x.csv", "utf-8", ",", diags)
    assert table is not None
    assert table.header.cells == ("name;x", "size")


def test_records_carry_their_physical_start_lines() -> None:
    text = 'name,description\r\nA,"two\r\nlines"\r\n\r\nB,"x ""quoted"""\r\nC,\n'
    records = split_records(text, ",", "x.csv", Collector())
    assert records is not None
    assert [(r.line, r.cells) for r in records] == [
        (1, ("name", "description")),
        (2, ("A", "two\r\nlines")),
        (4, ()),
        (5, ("B", 'x "quoted"')),
        (6, ("C", "")),
    ]


def test_all_empty_records_are_skipped_in_rows() -> None:
    table = read_csv(b"name,size\n,\n  ,  \nA,M\n\n", "x.csv", "utf-8", None, Collector())
    assert table is not None
    assert [r.line for r in table.rows] == [4]


def test_unterminated_quote_is_e101_at_record_start() -> None:
    diags = Collector()
    data = b'name,size\nA,M\nB,M\n"C,M\nD,M\n'
    assert read_csv(data, "x.csv", "utf-8", None, diags) is None
    [d] = diags.items
    assert (d.code.name, d.line, d.col) == ("E101", 4, 1)
    assert d.message == "unterminated quoted field starting at line 4"


def test_more_cells_than_header_is_e106_at_first_extra_field() -> None:
    diags = Collector()
    data = b"a,b,c,d,e,f,g,h\n1,2,3,4,5,6,7,8,9\n1,2,3,4,5,6,7,8,,\n1,2\n"
    table = read_csv(data, "x.csv", "utf-8", None, diags)
    assert table is not None  # the remaining rows are still checked
    assert _codes(diags) == [("E106", 2, 9)]
    assert diags.items[0].message == "row has 9 fields but the header has 8"
