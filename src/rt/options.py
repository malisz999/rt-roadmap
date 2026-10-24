"""Parsed command-line options handed from cli.py to the use cases (RS 6.2). Usage checks are done in cli.py."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from rt.model.types import Mode
from rt.timeutil import Month


@dataclass(frozen=True, slots=True)
class RenderOptions:
    """`rt render` and `rt validate`."""

    input: str  # path or "-" (already resolved per RS CLI-2)
    default_today: date  # the run's clock date, read once in cli.py
    output: str | None = None  # render: path, "-" or None = default (RS 6.2); unused by validate
    plan: str | None = None  # --plan path or "-"
    summary: bool = False
    horizon_start: Month | None = None  # --from
    horizon_end: Month | None = None  # --to
    today: date | None = None  # --today
    on_conflict: Mode | None = None
    strict: bool = False
    quiet: bool = False
    format: str = "text"  # validate --format text|json


@dataclass(frozen=True, slots=True)
class ConvertOptions:
    """`rt convert` (RS 6.6)."""

    input: str  # path or "-"
    default_today: date
    output: str = "-"
    base: str | None = None
    append: bool = False
    column_map: tuple[tuple[str, str], ...] = ()  # --map pairs (source header, target column), in given order
    team: str | None = None
    title: str | None = None
    sizes: tuple[tuple[str, int], ...] | None = None  # --sizes
    slots: int | None = None  # --slots
    encoding: str = "utf-8"
    delimiter: str | None = None  # "," ";" "\t" or None = detect
    strict: bool = False
    quiet: bool = False


@dataclass(frozen=True, slots=True)
class InitOptions:
    path: str = "roadmap.yaml"  # or "-"
    minimal: bool = False
    force: bool = False
    quiet: bool = False


@dataclass(frozen=True, slots=True)
class SchemaOptions:
    output: str = "-"
    quiet: bool = False
