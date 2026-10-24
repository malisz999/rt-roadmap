"""RawDoc: a loaded ruamel round-trip tree plus positions and per-node sources (ADS 4.2, 6.8 step 7).

Nodes parsed from YAML carry ruamel line/column info (0-based). Project mappings produced by rt convert are
registered with their CSV source, line and per-field column number and header, so the same validator reports
positions inside the CSV (RS CV-5, CV-17). Registration is keyed on id(node) and is valid while the tree lives.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from rt.diagnostics import Pos


@dataclass(frozen=True, slots=True)
class CsvRow:
    source: str  # CSV name used in messages
    line: int  # physical line where the record starts (header = 1)
    cells: Mapping[str, tuple[int, str]]  # field name -> (1-based field number, header as written)


@dataclass
class RawDoc:
    root: Any  # ruamel CommentedMap (or any node when the document is not a mapping)
    source: str  # file path as given, or <stdin>
    _rows: dict[int, CsvRow] = field(default_factory=dict)
    _keepalive: list[Any] = field(default_factory=list)

    # --- registration (rt convert) -------------------------------------------------------------
    def register_csv_row(self, node: Any, row: CsvRow) -> None:
        self._rows[id(node)] = row
        self._keepalive.append(node)

    def csv_row(self, node: Any) -> CsvRow | None:
        return self._rows.get(id(node))

    # --- queries ---------------------------------------------------------------------------------
    def source_of(self, node: Any) -> str:
        row = self._rows.get(id(node))
        return row.source if row else self.source

    def node_pos(self, node: Any) -> Pos:
        """Position of a mapping or sequence: its first key or item (RS 9 location rule)."""
        row = self._rows.get(id(node))
        if row is not None:
            return Pos(row.line, 1, row.source)
        lc = getattr(node, "lc", None)
        if lc is not None and lc.line is not None:
            return Pos(lc.line + 1, lc.col + 1, self.source)
        return Pos(1, 1, self.source)

    def key_pos(self, node: Any, key: Any) -> Pos:
        row = self._rows.get(id(node))
        if row is not None:
            cell = row.cells.get(str(key))
            return Pos(row.line, cell[0] if cell else 1, row.source)
        try:
            line, col = node.lc.key(key)
            return Pos(line + 1, col + 1, self.source)
        except (AttributeError, KeyError, TypeError):
            return self.node_pos(node)

    def value_pos(self, node: Any, key: Any) -> Pos:
        """Position of node[key]'s value; for CSV rows, the cell of that field even when the key is absent."""
        row = self._rows.get(id(node))
        if row is not None:
            cell = row.cells.get(str(key))
            return Pos(row.line, cell[0] if cell else 1, row.source)
        try:
            line, col = node.lc.value(key)
            return Pos(line + 1, col + 1, self.source)
        except (AttributeError, KeyError, TypeError):
            return self.key_pos(node, key)

    def item_pos(self, seq: Any, index: int, owner: Any = None, key: Any = None) -> Pos:
        """Position of seq[index]. For a sequence built by rt convert, pass the owning mapping and key."""
        if owner is not None and id(owner) in self._rows:
            return self.value_pos(owner, key)
        try:
            line, col = seq.lc.item(index)
            return Pos(line + 1, col + 1, self.source)
        except (AttributeError, KeyError, TypeError, IndexError):
            return self.node_pos(seq)

    def column_label(self, node: Any, key: Any) -> str | None:
        """CSV header that produced node[key], appended to messages as ` [column "…"]` (RS CV-5)."""
        row = self._rows.get(id(node))
        if row is None:
            return None
        cell = row.cells.get(str(key))
        return cell[1] if cell else None
