"""io.loader: decoding, YAML 1.2, E001, E003, E011 tags, NFC (RS 3.3, ST-3, ST-5)."""

from __future__ import annotations

import unicodedata
from datetime import date

from iokit import codes, load_raw, messages
from ruamel.yaml.scalarstring import LiteralScalarString

from rt.diagnostics import Collector
from rt.io.loader import load, load_text
from rt.io.streams import MAX_INPUT_BYTES


def test_yaml_12_keeps_no_and_yes_as_strings() -> None:
    raw, diags = load_raw("a: NO\nb: yes\nc: on\nd: true\n")
    assert raw is not None and not diags.items
    assert raw.root["a"] == "NO" and raw.root["b"] == "yes" and raw.root["c"] == "on"
    assert raw.root["d"] is True


def test_unquoted_date_stays_a_date_and_month_a_string() -> None:
    raw, _ = load_raw("today: 2026-10-23\nstart: 2027-01\n")
    assert raw is not None
    assert raw.root["today"] == date(2026, 10, 23)
    assert raw.root["start"] == "2027-01"


def test_impossible_unquoted_date_stays_text() -> None:
    raw, diags = load_raw("today: 2026-02-30\n")
    assert raw is not None and not diags.items
    assert raw.root["today"] == "2026-02-30"


def test_bom_is_accepted() -> None:
    diags = Collector("x")
    raw = load("﻿a: 1\n".encode(), "x", diags)
    assert raw is not None and raw.root["a"] == 1
    assert load_text("﻿a: 2\n", "x", diags) is not None


def test_empty_and_whitespace_input_is_e001() -> None:
    for data in (b"", b"  \n\t\n", "﻿".encode()):
        diags = Collector("<stdin>")
        assert load(data, "<stdin>", diags) is None
        assert codes(diags) == [("E001", 1, 1)]
        assert diags.items[0].source == "<stdin>"
        assert messages(diags) == ["input is empty (did the previous command fail?)"]


def test_input_too_large() -> None:
    diags = Collector("big")
    assert load(b"a" * (MAX_INPUT_BYTES + 1), "big", diags) is None
    assert messages(diags) == ["input too large (more than 5 MB)"]


def test_bad_utf8_reports_line_and_byte() -> None:
    diags = Collector("x")
    assert load(b"a: 1\nb: \xb3x\n", "x", diags) is None
    assert codes(diags) == [("E001", 2, 4)]
    assert "0xB3" in messages(diags)[0]


def test_syntax_error_position() -> None:
    raw, diags = load_raw("a: b: c\n")
    assert raw is None
    assert codes(diags) == [("E001", 1, 5)]
    assert messages(diags) == ["invalid YAML: mapping values are not allowed here"]


def test_tab_indentation_and_two_documents_are_e001() -> None:
    assert codes(load_raw("a: 1\n\tb: 2\n")[1])[0][0] == "E001"
    assert codes(load_raw("---\na: 1\n---\nb: 2\n")[1])[0][0] == "E001"


def test_control_character_is_e001_with_position() -> None:
    raw, diags = load_raw("a: 1\nb: \x01\n")
    assert raw is None
    assert codes(diags) == [("E001", 2, 4)]


def test_all_duplicate_keys_reported() -> None:
    raw, diags = load_raw("a: 1\nb:\n  c: 1\n  c: 2\na: 3\nf: {x: 1, x: 2}\n")
    assert raw is None
    assert codes(diags) == [("E003", 4, 3), ("E003", 5, 1), ("E003", 6, 11)]
    assert messages(diags)[0] == 'duplicate key "c"'


def test_keys_equal_after_nfc_are_duplicates() -> None:
    raw, diags = load_raw(f"łą: 1\n{unicodedata.normalize('NFD', 'łą')}: 2\n")
    assert raw is None
    assert [c[0] for c in codes(diags)] == ["E003"]


def test_non_core_tags_are_e011() -> None:
    raw, diags = load_raw("a: !foo 1\nb: !!binary aGVsbG8=\nc: !!set {x}\nd: !!str 5\n")
    assert raw is None
    assert codes(diags) == [("E011", 1, 4), ("E011", 2, 4), ("E011", 3, 4)]
    assert messages(diags)[0] == 'tag "!foo" is not allowed; remove it'


def test_core_str_tag_becomes_plain_string() -> None:
    raw, diags = load_raw("a: !!str 5\nb: !!int '7'\n")
    assert raw is not None and not diags.items
    assert raw.root["a"] == "5" and type(raw.root["a"]) is str
    assert raw.root["b"] == 7


def test_nfc_values_keys_and_list_items_keep_positions() -> None:
    nfd = unicodedata.normalize("NFD", "Płatności")
    text = f"{nfd}: x\nname: {nfd}\nlist: [{nfd}, b]\nblock: |\n  {nfd}\n"
    raw, diags = load_raw(text)
    assert raw is not None and not diags.items
    root = raw.root
    assert next(iter(root.keys())) == "Płatności"
    assert root["name"] == "Płatności"
    assert root["list"][0] == "Płatności"
    assert root["block"] == "Płatności\n" and isinstance(root["block"], LiteralScalarString)
    assert raw.key_pos(root, "Płatności").line == 1
    assert raw.value_pos(root, "name").col == 7
    # columns refer to the file as written (the decomposed text is one character longer)
    assert raw.item_pos(root["list"], 1).col == len("list: [") + len(nfd) + len(", ") + 1


def test_aliases_are_walked_once() -> None:
    raw, _diags = load_raw("a: &x {n: b}\nc: *x\n")
    assert raw is not None and raw.root["c"]["n"] == "b"


def test_comment_only_document_loads_as_none_root() -> None:
    raw, diags = load_raw("# nothing\n")
    assert raw is not None and raw.root is None and not diags.items
