"""Computed scheduling types (ADS 5.2). Intervals are half-open [start, end); end None = ongoing (∞)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from rt.timeutil import Month

# Flag names (RS PL-4); always emitted sorted.
AUTO_START = "auto_start"
CLIPPED_LEFT = "clipped_left"
CLIPPED_RIGHT = "clipped_right"
CONTINUES = "continues"
DELAYED = "delayed"
HIDDEN = "hidden"
OVER_CAPACITY = "over_capacity"

# delay_reason values (RS PL-4)
REASON_DEPENDENCY = "dependency"
REASON_CAPACITY = "capacity"
REASON_BOTH = "dependency+capacity"


@dataclass(frozen=True, slots=True)
class Interval:
    start: date
    end: date | None  # None = ongoing

    def overlaps(self, other: Interval) -> bool:
        """RS SC-3: [a, b) and [c, d) overlap iff a < d and c < b; touching intervals do not."""
        a_before_d = other.end is None or self.start < other.end
        c_before_b = self.end is None or other.start < self.end
        return a_before_d and c_before_b


@dataclass(frozen=True, slots=True)
class Placement:
    """Where and when one project runs."""

    seq: int
    team_id: str
    lane: int  # 1-based; lanes > team.slots are overflow lanes
    overflow: bool
    requested: date | None  # None for auto-start projects
    earliest: date
    start: date
    end: date | None  # exclusive; None = ongoing
    delay_days: int  # 0 for auto-start projects
    delay_reason: str | None


@dataclass(frozen=True, slots=True)
class Schedule:
    placements: tuple[Placement, ...]  # indexed by seq - 1
    lane_count: Mapping[str, int]  # team id -> lanes in use, regular slots plus overflow lanes

    def placement(self, seq: int) -> Placement:
        return self.placements[seq - 1]


@dataclass(frozen=True, slots=True)
class Horizon:
    start: Month
    end: Month  # inclusive
    h0: date  # first day of start
    h1: date  # first day after end
    days: int  # (h1 - h0).days


@dataclass(frozen=True, slots=True)
class Visibility:
    start: date | None  # None when hidden
    end: date | None  # ongoing bars end at h1
    flags: frozenset[str]

    @property
    def visible(self) -> bool:
        return self.start is not None
