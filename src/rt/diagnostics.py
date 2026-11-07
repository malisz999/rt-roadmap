"""Diagnostics: codes, positions, the collector, formatters and "did you mean" (ADS 8.1).

All user-facing diagnostic text lives here. Stages never raise for user mistakes; they append to one Collector.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import Any


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class Code(Enum):
    """Stable diagnostic codes (RS 9). Each value is (code, template); `template` is formatted with keyword arguments.

    The code name is part of the value so that members sharing a template never become aliases of each other.
    """

    # Input and structure
    E001 = ("E001", "{detail}")
    E002 = ("E002", 'unknown key "{key}" in {where}{hint}')
    E003 = ("E003", 'duplicate key "{key}"')
    E004 = ("E004", "{detail}")
    E010 = ("E010", '{where} is missing required field "{field}"')
    E011 = ("E011", "{detail}")
    E012 = ("E012", "{detail}")
    E013 = ("E013", "{detail}")
    # Uniqueness
    E020 = ("E020", 'subdomain id "{id}" already defined at line {line}')
    E021 = ("E021", 'team id "{id}" already defined at line {line}')
    E022 = ("E022", 'project "{name}" already exists in team "{team}" (line {line})')
    E023 = ("E023", 'project id "{id}" already defined at line {line}')
    E024 = ("E024", 'product id "{id}" already defined at line {line}')
    E025 = ("E025", 'product name "{name}" already used at line {line}')
    # References
    E030 = ("E030", 'project "{project}" references unknown team "{team}"{hint}')
    E031 = ("E031", 'project "{project}" uses size "{size}", not defined in sizes ({sizes})')
    E032 = ("E032", 'project "{project}" needs exactly one of size or ongoing: true')
    E033 = ("E033", 'color "{color}" is not a palette name or #RRGGBB')
    E034 = ("E034", 'project "{project}" depends on unknown project "{ref}"{hint}')
    E035 = ("E035", '"{ref}" matches {count} projects (lines {lines}); give one an id and use it')
    E036 = ("E036", 'project "{project}" cannot depend on ongoing project "{dep}"')
    E037 = ("E037", "{detail}")
    E038 = ("E038", 'project "{project}" references unknown product "{product}"{hint}')
    E039 = ("E039", 'product "{product}" references unknown domain "{domain}"{hint}')
    # Horizon and lists
    E040 = ("E040", "horizon end {end} is before start {start}")
    E041 = ("E041", "horizon spans {months} months; maximum is 120")
    E042 = ("E042", "sizes must define at least one size")
    E043 = ("E043", "subdomains must contain at least one subdomain")
    # Locked projects (CR-3)
    E050 = ("E050", 'project "{project}" is locked but has no start; a locked project needs a start month')
    E051 = (
        "E051",
        'project "{project}" has promised_to but is not locked; add locked: true or remove promised_to',
    )
    # Scheduling (exit 3)
    E060 = (
        "E060",
        'project "{project}" cannot be scheduled: every slot of team "{team}" is held by an ongoing project',
    )
    E061 = ("E061", 'project "{project}" needs a slot on {date} but team "{team}" has {busy} of {slots} busy')
    # CSV conversion
    E101 = ("E101", "unterminated quoted field starting at line {line}")
    E102 = ("E102", "cannot decode byte 0x{byte} as {encoding} at line {line}, byte {col}; try --encoding cp1250")
    E103 = ("E103", "{detail}")
    E104 = ("E104", 'columns "{first}" ({first_index}) and "{second}" ({second_index}) both map to "{target}"')
    E105 = ("E105", "row has no team and {base} has {count} teams; add a team column or --team")
    E106 = ("E106", "row has {got} fields but the header has {expected}")
    E107 = ("E107", 'team "{team}" is in subdomain "{first}" (line {first_line}) and "{second}" (line {second_line})')
    # Warnings
    W001 = ("W001", 'project "{project}" delayed {days} days (requested {requested}, starts {start}): {why}')
    W002 = ("W002", 'project "{project}" starts before the horizon; left part not shown')
    W003 = ("W003", 'project "{project}" ends after the horizon; right part not shown')
    W004 = ("W004", 'project "{project}" is outside the horizon and not shown')
    W005 = ("W005", 'team "{team}" has no projects')
    W006 = ("W006", 'subdomain "{subdomain}" has no teams')
    W007 = ("W007", 'project "{project}" shares colour "{color}" with an adjacent bar')
    W008 = ("W008", 'team "{team}" has no members in capacity')
    W009 = ("W009", 'projects "{first}" and "{second}" are adjacent and both {how} "{color}"')
    W010 = ("W010", "no projects defined; rendering empty roadmap")
    W011 = ("W011", 'project "{project}" exceeds team "{team}" capacity; placed in overflow lane +{lane}')
    W012 = ("W012", "automatic horizon capped at 120 months ({start} to {end})")
    W013 = ("W013", 'product "{product}" has no projects')
    W014 = ("W014", 'products "{first}" and "{second}" share colour "{color}" (more than {size} products)')
    W015 = ("W015", 'locked project "{project}" cannot keep its promised start {start}: {why}')
    W020 = ("W020", "{detail}")
    W021 = ("W021", 'day of "{value}" ignored; using {month}')

    def __init__(self, code: str, template: str) -> None:
        self.template = template

    @property
    def severity(self) -> Severity:
        return Severity.ERROR if self.name.startswith("E") else Severity.WARNING

    @property
    def is_scheduling(self) -> bool:
        """E060 and E061 lead to exit code 3."""
        return self in (Code.E060, Code.E061)


@dataclass(frozen=True, slots=True)
class Pos:
    """A 1-based position in a named source (file path as given, `<stdin>`, or a CSV name)."""

    line: int
    col: int
    source: str


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: Code
    message: str
    source: str
    line: int | None
    col: int | None

    @property
    def severity(self) -> Severity:
        return self.code.severity

    def sort_key(self) -> tuple[str, int, int, str]:
        return (self.source, self.line or 0, self.col or 0, self.code.name)


class Collector:
    """Collects every diagnostic of a run, in the order reported."""

    def __init__(self, default_source: str = "<input>") -> None:
        self.default_source = default_source
        self._items: list[Diagnostic] = []

    def report(self, code: Code, pos: Pos | None, *, column: str | None = None, **fields: Any) -> Diagnostic:
        """Format the code's template with `fields`; append ` [column "…"]` for CSV cells (RS CV-5)."""
        message = code.template.format(**fields)
        if column is not None:
            message += f' [column "{column}"]'
        source = pos.source if pos is not None else self.default_source
        diag = Diagnostic(code, message, source, pos.line if pos else None, pos.col if pos else None)
        self._items.append(diag)
        return diag

    # error() and warning() are aliases that read well at call sites; severity always comes from the code.
    error = report
    warning = report

    def add(self, diag: Diagnostic) -> None:
        self._items.append(diag)

    def extend(self, diags: Iterable[Diagnostic]) -> None:
        self._items.extend(diags)

    @property
    def items(self) -> tuple[Diagnostic, ...]:
        return tuple(self._items)

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return tuple(d for d in self._items if d.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[Diagnostic, ...]:
        return tuple(d for d in self._items if d.severity is Severity.WARNING)

    def has_errors(self) -> bool:
        return any(d.severity is Severity.ERROR for d in self._items)

    def has_scheduling_errors(self) -> bool:
        return any(d.code.is_scheduling for d in self._items)

    def sorted(self) -> list[Diagnostic]:
        """By file, line, column, then code (RS CLI-6)."""
        return sorted(self._items, key=Diagnostic.sort_key)


def format_text(diag: Diagnostic) -> str:
    """`<file>:<line>:<col>: <error|warning> <code>: <message>` (RS CLI-6)."""
    where = diag.source if diag.line is None else f"{diag.source}:{diag.line}:{diag.col}"
    return f"{where}: {diag.severity.value} {diag.code.name}: {diag.message}"


def format_json(diags: Sequence[Diagnostic]) -> str:
    """`validate --format json`: an array of objects, UTF-8, 2-space indent, trailing newline (ADS 8.1)."""
    items = [
        {
            "code": d.code.name,
            "severity": d.severity.value,
            "file": d.source,
            "line": d.line,
            "column": d.col,
            "message": d.message,
        }
        for d in diags
    ]
    return json.dumps(items, indent=2, ensure_ascii=False) + "\n"


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def closest(word: str, candidates: Iterable[str], max_distance: int = 2) -> str | None:
    """The closest candidate within `max_distance`; ties go to the first in iteration (file) order."""
    best: str | None = None
    best_distance = max_distance + 1
    for candidate in candidates:
        if candidate == word:
            continue
        distance = edit_distance(word, candidate)
        if distance < best_distance:
            best, best_distance = candidate, distance
    return best


def suggest(word: str, candidates: Iterable[str]) -> str:
    """` (did you mean "…"?)` or an empty string (RS IN-3)."""
    hit = closest(word, candidates)
    return "" if hit is None else f' (did you mean "{hit}"?)'
