"""Header matching: --map, canonical column names, E103, E104, W020 (RS CV-6, CV-7; ADS 6.8 step 4)."""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from rt.convert.csv_source import CsvTable
from rt.diagnostics import Code, Collector, Pos

COLUMNS: tuple[str, ...] = (
    "name",
    "size",
    "team",
    "subdomain",
    "start",
    "ongoing",
    "depends_on",
    "id",
    "description",
    "color",
)
REQUIRED: tuple[str, ...] = ("name", "size")


def clean(text: str) -> str:
    """Trim and NFC-normalise a header or cell (RS CV-6, CV-8)."""
    return unicodedata.normalize("NFC", text.strip())


@dataclass(frozen=True, slots=True)
class Columns:
    """Resolved columns: canonical name → (0-based field index, header as written, trimmed and NFC)."""

    fields: dict[str, tuple[int, str]]

    def index(self, column: str) -> int | None:
        hit = self.fields.get(column)
        return hit[0] if hit else None

    def header(self, column: str) -> str | None:
        hit = self.fields.get(column)
        return hit[1] if hit else None

    def cell(self, cells: Sequence[str], column: str) -> str:
        """The trimmed, NFC-normalised cell of a column; empty when the column or the cell is missing."""
        i = self.index(column)
        return clean(cells[i]) if i is not None and i < len(cells) else ""


def _map_table(column_map: Sequence[tuple[str, str]]) -> dict[str, str]:
    table: dict[str, str] = {}
    for src, dst in column_map:
        table[clean(src).casefold()] = clean(dst).casefold()
    return table


def _has_data(table: CsvTable, index: int) -> bool:
    return any(index < len(r.cells) and r.cells[index].strip() for r in table.records)


def resolve_columns(
    table: CsvTable, column_map: Sequence[tuple[str, str]], base_mode: bool, diags: Collector
) -> Columns | None:
    """Map header cells to column names; report E103/E104 (then return None) and W020 (RS CV-6, CV-7)."""
    renames = _map_table(column_map)
    line = table.header.line
    src = table.source
    fields: dict[str, tuple[int, str]] = {}
    unmatched: list[str] = []
    errors = False
    headers = [clean(h) for h in table.header.cells]
    for i, head in enumerate(headers):
        pos = Pos(line, i + 1, src)
        if not head:
            if _has_data(table, i):
                diags.warning(Code.W020, pos, detail=f"column {i + 1} has no header and was ignored")
            continue
        key = head.casefold()
        canon = renames.get(key, key)
        if canon not in COLUMNS:
            unmatched.append(head)
            diags.warning(Code.W020, pos, detail=f'column "{head}" is not used and was ignored')
            continue
        if canon == "subdomain" and base_mode:
            diags.warning(Code.W020, pos, detail=f'column "{head}" is ignored with --base')
            continue
        if canon in fields:
            first_index, first_head = fields[canon]
            diags.report(
                Code.E104,
                Pos(line, i + 1, src),
                first=head,
                first_index=i + 1,
                second=first_head,
                second_index=first_index + 1,
                target=canon,
            )
            errors = True
            continue
        fields[canon] = (i, head)
    candidates = list(unmatched)
    for column in REQUIRED:
        if column in fields:
            continue
        found = ", ".join(h for h in headers if h) or "no headers"
        guess = candidates.pop(0) if candidates else "<header>"
        detail = f'missing column "{column}"; found: {found}; use --map "{guess}={column}"'
        diags.error(Code.E103, Pos(line, 1, src), detail=detail)
        errors = True
    return None if errors else Columns(fields)
