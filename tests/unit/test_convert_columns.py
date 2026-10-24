"""convert.columns: header matching, --map, E103, E104, W020 (RS CV-6, CV-7)."""

from __future__ import annotations

from rt.convert.columns import resolve_columns
from rt.convert.csv_source import CsvTable, read_csv
from rt.diagnostics import Collector

PL_MAP = (
    ("Projekt", "name"),
    ("Rozmiar", "size"),
    ("Zespół", "team"),
    ("Start", "start"),
    ("Zależności", "depends_on"),
    ("Ciągły", "ongoing"),
    ("Opis", "description"),
)


def _table(text: str) -> CsvTable:
    table = read_csv(text.encode("utf-8"), "x.csv", "utf-8", None, Collector())
    assert table is not None
    return table


def test_canonical_headers_match_case_insensitively_after_trim() -> None:
    diags = Collector()
    cols = resolve_columns(_table(" NAME ,Size,Depends_On,team\nA,M,,\n"), (), False, diags)
    assert cols is not None
    assert cols.fields == {
        "name": (0, "NAME"),
        "size": (1, "Size"),
        "depends_on": (2, "Depends_On"),
        "team": (3, "team"),
    }
    assert not diags.items


def test_map_renames_polish_headers_and_unused_column_is_w020() -> None:
    diags = Collector()
    text = "Projekt;Rozmiar;Zespół;Start;Zależności;Ciągły;Opis;Właściciel\nA;M;b;;;;;\n"
    cols = resolve_columns(_table(text), PL_MAP, True, diags)
    assert cols is not None
    assert cols.header("team") == "Zespół"
    assert cols.index("description") == 6
    [w] = diags.items
    assert (w.code.name, w.line, w.col) == ("W020", 1, 8)
    assert w.message == 'column "Właściciel" is not used and was ignored'


def test_map_source_matches_case_insensitively_and_nfc() -> None:
    decomposed = "Zespo\u0301ł"  # o + combining acute
    cols = resolve_columns(
        _table(f"PROJEKT,size,{decomposed}\nA,M,b\n"), (("projekt", "name"), ("Zespół", "team")), False, Collector()
    )
    assert cols is not None
    assert set(cols.fields) == {"name", "size", "team"}


def test_subdomain_column_with_base_is_w020() -> None:
    diags = Collector()
    cols = resolve_columns(_table("name,size,Subdomain\nA,M,x\n"), (), True, diags)
    assert cols is not None
    assert "subdomain" not in cols.fields
    [w] = diags.items
    assert (w.code.name, w.col) == ("W020", 3)
    assert w.message == 'column "Subdomain" is ignored with --base'


def test_missing_size_is_e103_with_found_headers_and_map_hint() -> None:
    diags = Collector()
    cols = resolve_columns(_table("Projekt,Rozmiar,Zespół\nA,M,b\n"), (("Projekt", "name"),), False, diags)
    assert cols is None
    errors = [d for d in diags.items if d.code.name == "E103"]
    assert [(d.line, d.col, d.message) for d in errors] == [
        (1, 1, 'missing column "size"; found: Projekt, Rozmiar, Zespół; use --map "Rozmiar=size"')
    ]


def test_missing_name_and_size_suggest_different_headers() -> None:
    diags = Collector()
    assert resolve_columns(_table("Projekt,Rozmiar\nA,M\n"), (), False, diags) is None
    messages = [d.message for d in diags.items if d.code.name == "E103"]
    assert messages[0].endswith('use --map "Projekt=name"')
    assert messages[1].endswith('use --map "Rozmiar=size"')


def test_two_headers_for_one_column_is_e104() -> None:
    diags = Collector()
    cols = resolve_columns(_table("Projekt,size,Name\nA,M,B\n"), (("Projekt", "name"),), False, diags)
    assert cols is None
    [e] = diags.items
    assert (e.code.name, e.line, e.col) == ("E104", 1, 3)
    assert e.message == 'columns "Name" (3) and "Projekt" (1) both map to "name"'


def test_empty_header_is_silent_unless_its_column_has_data() -> None:
    diags = Collector()
    assert resolve_columns(_table("name,size,\nA,M,\n"), (), False, diags) is not None
    assert not diags.items
    assert resolve_columns(_table("name,size,\nA,M,x\n"), (), False, diags) is not None
    [w] = diags.items
    assert (w.code.name, w.col, w.message) == ("W020", 3, "column 3 has no header and was ignored")


def test_cell_is_trimmed_nfc_and_missing_cells_are_empty() -> None:
    table = _table("name,size,team\n  Pr\u0301  ,M\n")
    cols = resolve_columns(table, (), False, Collector())
    assert cols is not None
    row = table.rows[0]
    assert cols.cell(row.cells, "name") == "Pŕ"
    assert cols.cell(row.cells, "team") == ""
    assert cols.cell(row.cells, "start") == ""
