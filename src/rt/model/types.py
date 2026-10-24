"""Input model (ADS 5.1): frozen dataclasses built by model.build and resolved by model.references.

Projects are identified everywhere by `seq` (1-based file order). Partial models (ADS 8.2): a field that failed
validation is None and its entity has `incomplete=True`; later checks skip what they cannot use.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from types import MappingProxyType

from rt.diagnostics import Pos
from rt.timeutil import Month

__all__ = [
    "Capacity",
    "ColorSpec",
    "DepRef",
    "Mode",
    "Model",
    "Month",
    "Overrides",
    "Pos",
    "Project",
    "ResolvedModel",
    "Settings",
    "Size",
    "Subdomain",
    "Team",
]

EMPTY_POS: Mapping[str, Pos] = MappingProxyType({})
EMPTY_STR: Mapping[str, str] = MappingProxyType({})


class Mode(StrEnum):
    """`scheduling.on_conflict` (RS SC-5 to SC-7)."""

    DELAY = "delay"
    OVERFLOW = "overflow"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Overrides:
    """Command-line values that win over the file (RS CLI-1), plus the run's clock date.

    `default_today` is read once in cli.py (ADR-5) and used when neither `--today` nor `roadmap.today` is given.
    """

    default_today: date
    horizon_start: Month | None = None  # --from
    horizon_end: Month | None = None  # --to
    today: date | None = None  # --today
    on_conflict: Mode | None = None  # --on-conflict


@dataclass(frozen=True, slots=True)
class Settings:
    """`roadmap` and `scheduling` blocks with CLI overrides already applied."""

    title: str
    subtitle: str | None
    horizon_start: Month | None
    horizon_end: Month | None
    today: date
    month_width: int
    content_language: str | None
    on_conflict: Mode
    adjacency_gap_days: int
    pos: Pos | None = None  # position of the `roadmap` key, for whole-roadmap diagnostics


@dataclass(frozen=True, slots=True)
class Size:
    label: str
    weeks: int
    pos: Pos | None = None


@dataclass(frozen=True, slots=True)
class Capacity:
    developers: int = 0
    product_managers: int = 0
    analysts: int = 0
    testers: int = 0

    @property
    def total(self) -> int:
        return self.developers + self.product_managers + self.analysts + self.testers


@dataclass(frozen=True, slots=True)
class Team:
    id: str
    name: str
    subdomain_id: str
    slots: int  # parallel_projects
    capacity: Capacity
    pos: Pos  # first key of the team mapping
    capacity_given: bool = False  # a `capacity` mapping was written (W008 only then)
    field_pos: Mapping[str, Pos] = EMPTY_POS  # value positions by field name
    incomplete: bool = False


@dataclass(frozen=True, slots=True)
class Subdomain:
    id: str
    name: str
    description: str | None
    team_ids: tuple[str, ...]
    pos: Pos
    field_pos: Mapping[str, Pos] = EMPTY_POS
    incomplete: bool = False


@dataclass(frozen=True, slots=True)
class ColorSpec:
    """A pinned colour: a palette name (`sky`) or a hex value normalised to upper case (`#BAE6FD`)."""

    palette_name: str | None
    hex: str | None
    text: str  # as written, for messages


@dataclass(frozen=True, slots=True)
class DepRef:
    """One `depends_on` item as written (NFC-normalised), with its position."""

    text: str
    pos: Pos


@dataclass(frozen=True, slots=True)
class Project:
    seq: int
    id: str | None
    name: str | None  # None only in an incomplete project
    team_id: str | None
    start: Month | None  # None = auto-start (or invalid, then incomplete)
    size: str | None
    ongoing: bool
    depends_on_refs: tuple[DepRef, ...]
    description: str | None
    color: ColorSpec | None
    pos: Pos  # first key of the project mapping (RS 9 location rule)
    field_pos: Mapping[str, Pos] = EMPTY_POS  # value positions: "team", "size", "start", ...
    field_column: Mapping[str, str] = EMPTY_STR  # CSV header per field when the project came from rt convert
    incomplete: bool = False

    @property
    def auto_start(self) -> bool:
        return self.start is None


@dataclass(frozen=True, slots=True)
class Model:
    """Structurally valid input; references not yet checked."""

    settings: Settings
    sizes: tuple[Size, ...]  # declaration order = legend order
    subdomains: tuple[Subdomain, ...]  # file order
    teams: tuple[Team, ...]  # file order across all subdomains
    projects: tuple[Project, ...]  # file order; projects[i].seq == i + 1
    source: str = "<input>"

    def team(self, team_id: str) -> Team:
        for t in self.teams:
            if t.id == team_id:
                return t
        raise KeyError(team_id)

    def subdomain(self, subdomain_id: str) -> Subdomain:
        for s in self.subdomains:
            if s.id == subdomain_id:
                return s
        raise KeyError(subdomain_id)

    def project(self, seq: int) -> Project:
        return self.projects[seq - 1]

    def size_weeks(self, label: str) -> int:
        for s in self.sizes:
            if s.label == label:
                return s.weeks
        raise KeyError(label)


@dataclass(frozen=True, slots=True)
class ResolvedModel:
    """Output of check_references; the only input the scheduler accepts (every project complete)."""

    model: Model
    deps: Mapping[int, tuple[int, ...]]  # seq -> dependency seqs, ascending
    weeks: Mapping[int, int | None]  # seq -> weeks, None for ongoing

    @property
    def settings(self) -> Settings:
        return self.model.settings

    @property
    def teams(self) -> tuple[Team, ...]:
        return self.model.teams

    @property
    def subdomains(self) -> tuple[Subdomain, ...]:
        return self.model.subdomains

    @property
    def projects(self) -> tuple[Project, ...]:
        return self.model.projects
