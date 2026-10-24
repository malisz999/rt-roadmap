"""The Plan: the single seam between computing and rendering (ADR-6, RS 8).

Serialized fields mirror RS section 8 key for key and in the same order: plan.serialize writes dataclass fields
in declaration order. Fields with metadata `{"json": False}` are extra data for the renderer and never written.
Values are typed (date, Month, Decimal); the serializer formats them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from fractions import Fraction

from rt.color.types import ColorRef
from rt.diagnostics import Diagnostic
from rt.model.types import Mode, ResolvedModel
from rt.timeutil import Month

NOT_JSON = {"json": False}


@dataclass(frozen=True, slots=True)
class HorizonOut:
    start: Month
    end: Month
    start_date: date
    end_exclusive: date
    days: int


@dataclass(frozen=True, slots=True)
class TeamPlan:
    id: str
    subdomain: str
    slots: int
    overflow_lanes: int
    utilization: Decimal  # 4 decimals, half up (RS OUT-13, PL-5)
    utilization_exact: Fraction = field(default=Fraction(0), metadata=NOT_JSON)


@dataclass(frozen=True, slots=True)
class VisibleOut:
    start: date
    end: date


@dataclass(frozen=True, slots=True)
class PlannedProject:
    seq: int
    id: str | None
    name: str
    team: str
    size: str | None
    weeks: int | None
    ongoing: bool
    requested_start: date | None
    depends_on: tuple[int, ...]
    earliest_start: date
    start: date
    end: date | None
    last_day: date | None
    lane: int
    overflow: bool
    delay_days: int
    delay_reason: str | None
    visible: VisibleOut | None
    color_index: int | None
    color_name: str | None
    color_fill: str | None
    flags: tuple[str, ...]  # sorted
    neighbors: tuple[int, ...]  # sorted
    color: ColorRef | None = field(default=None, metadata=NOT_JSON)  # fill, accent and text for the renderer


@dataclass(frozen=True, slots=True)
class TeamLoad:
    team: str
    load: tuple[Decimal, ...]
    occupied: tuple[int, ...] = field(default=(), metadata=NOT_JSON)  # slot-days per month (numerators)
    capacity: tuple[int, ...] = field(default=(), metadata=NOT_JSON)  # slots × days per month (denominators)


@dataclass(frozen=True, slots=True)
class SubdomainLoad:
    subdomain: str
    load: tuple[Decimal, ...]
    occupied: tuple[int, ...] = field(default=(), metadata=NOT_JSON)
    capacity: tuple[int, ...] = field(default=(), metadata=NOT_JSON)


@dataclass(frozen=True, slots=True)
class MonthlyLoad:
    months: tuple[Month, ...]
    teams: tuple[TeamLoad, ...]
    subdomains: tuple[SubdomainLoad, ...]
    total: tuple[Decimal, ...]
    total_occupied: tuple[int, ...] = field(default=(), metadata=NOT_JSON)
    total_capacity: tuple[int, ...] = field(default=(), metadata=NOT_JSON)


@dataclass(frozen=True, slots=True)
class PlanWarning:
    code: str
    line: int | None
    column: int | None
    message: str


@dataclass(frozen=True, slots=True)
class Plan:
    rt_version: str
    format: int
    title: str
    today: date
    horizon: HorizonOut
    on_conflict: Mode
    teams: tuple[TeamPlan, ...]
    projects: tuple[PlannedProject, ...]
    monthly_load: MonthlyLoad
    warnings: tuple[PlanWarning, ...]  # sorted by line, column, code
    model: ResolvedModel = field(metadata=NOT_JSON)  # names, capacities, sizes, settings for the renderer
    diagnostics: tuple[Diagnostic, ...] = field(default=(), metadata=NOT_JSON)  # all warnings of the run, sorted
