"""CSV source: decode, detect the delimiter, split records with their start lines (RS CV-1 to CV-5; ADS 6.8 1-3).

Pure: works on bytes already read by IOPort. Reports E001, E101, E102, E106.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

from rt.diagnostics import Code, Collector, Diagnostic, Pos
from rt.io.streams import MAX_INPUT_BYTES

UTF8_BOM = b"\xef\xbb\xbf"
DELIMITERS: tuple[str, ...] = (",", ";", "\t")  # tie order (RS CV-3)
_FIRST_LINE = re.compile(r"[^\r\n]*")


@dataclass(frozen=True, slots=True)
class CsvRecord:
    line: int  # physical line where the record starts (header = 1)
    cells: tuple[str, ...]  # raw cell text as parsed (not trimmed)

    def is_empty(self) -> bool:
        return all(not c.strip() for c in self.cells)


@dataclass(frozen=True, slots=True)
class CsvTable:
    source: str  # CSV name for messages: the path as given, or <stdin>
    delimiter: str
    header: CsvRecord
    records: tuple[CsvRecord, ...]  # body records in file order, including all-empty ones

    @property
    def rows(self) -> tuple[CsvRecord, ...]:
        """Body records that hold at least one non-empty cell (RS CV-4)."""
        return tuple(r for r in self.records if not r.is_empty())


def is_utf8(encoding: str) -> bool:
    return encoding.strip().lower().replace("_", "-") in ("utf-8", "utf8")


def decode(data: bytes, source: str, encoding: str, diags: Collector) -> str | None:
    """Decode strictly; UTF-8 accepts a BOM. Undecodable bytes are E102 at line and byte column (RS CV-1)."""
    offset = 0
    body = data
    codec = encoding
    if is_utf8(encoding):
        codec = "utf-8"
        if data.startswith(UTF8_BOM):
            offset = len(UTF8_BOM)
            body = data[offset:]
    try:
        return body.decode(codec, errors="strict")
    except UnicodeDecodeError as exc:
        bad = offset + exc.start
        line = data.count(b"\n", 0, bad) + 1
        line_start = data.rfind(b"\n", 0, bad) + 1
        col = bad - line_start + 1
        diags.error(
            Code.E102,
            Pos(line, col, source),
            byte=f"{data[bad]:02X}",
            encoding=encoding,
            line=line,
            col=col,
        )
        return None


def detect_delimiter(header_line: str) -> str:
    """Count `,` `;` and tab outside double quotes; most frequent wins; ties: comma, semicolon, tab (RS CV-3)."""
    counts = dict.fromkeys(DELIMITERS, 0)
    inside = False
    for ch in header_line:
        if ch == '"':
            inside = not inside
        elif not inside and ch in counts:
            counts[ch] += 1
    best = max(counts.values())
    if best == 0:
        return ","
    return next(d for d in DELIMITERS if counts[d] == best)


def _empty_input(source: str, detail: str) -> Diagnostic:
    return Diagnostic(Code.E001, Code.E001.template.format(detail=detail), source, None, None)


def split_records(text: str, delimiter: str, source: str, diags: Collector) -> list[CsvRecord] | None:
    """RFC 4180 records with their physical start lines; a csv.Error is E101 at the record's start line."""
    reader = csv.reader(
        io.StringIO(text, newline=""), delimiter=delimiter, quotechar='"', doublequote=True, strict=True
    )
    records: list[CsvRecord] = []
    prev_end = 0
    while True:
        start = prev_end + 1
        try:
            cells = next(reader)
        except StopIteration:
            return records
        except csv.Error:
            diags.error(Code.E101, Pos(start, 1, source), line=start)
            return None
        prev_end = reader.line_num
        records.append(CsvRecord(start, tuple(cells)))


def _check_widths(header: CsvRecord, records: list[CsvRecord], source: str, diags: Collector) -> None:
    """E106: a record with a non-empty cell beyond the header's last column (RS CV-4)."""
    width = len(header.cells)
    for rec in records:
        used = len(rec.cells)
        while used > 0 and not rec.cells[used - 1].strip():
            used -= 1
        if used > width:
            diags.error(Code.E106, Pos(rec.line, width + 1, source), got=used, expected=width)


def read_csv(data: bytes, source: str, encoding: str, delimiter: str | None, diags: Collector) -> CsvTable | None:
    """Bytes → CsvTable (RS CV-1 to CV-5). Returns None after E001, E101 or E102; E106 is reported but the table
    is still returned so the remaining rows can be checked (RS IN-6)."""
    if len(data) > MAX_INPUT_BYTES:
        diags.add(_empty_input(source, "input too large (over 5 MB)"))
        return None
    text = decode(data, source, encoding, diags)
    if text is None:
        return None
    if not text.strip():
        diags.add(_empty_input(source, "input is empty (did the previous command fail?)"))
        return None
    first = _FIRST_LINE.match(text)
    delim = delimiter or detect_delimiter(first.group(0) if first else "")
    records = split_records(text, delim, source, diags)
    if records is None:
        return None
    # A leading blank line yields an empty record; the header is the first record (RS CV-4).
    header, body = records[0], records[1:]
    _check_widths(header, body, source, diags)
    return CsvTable(source, delim, header, tuple(body))
