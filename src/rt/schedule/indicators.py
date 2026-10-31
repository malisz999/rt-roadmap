"""Team composition indicators (RS 7.13, TI-1 to TI-7): developers per slot and developers per QA (pure).

Values are exact fractions; rounding happens when the plan is assembled. Slots are `parallel_projects` as written
(slots held by ongoing work count, overflow lanes never do). A value is marked `low` / `high` against the
roadmap-wide `team_norms` band, else when it differs from the median by more than 50 % and at least three teams
have the indicator. For both indicators higher is worse: `high` and `no_qa` are shown as bad, `low` as good.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType

from rt.model.types import Band, Team, TeamNorms

DEVS_PER_SLOT = "devs_per_slot"
DEVS_PER_QA = "devs_per_qa"
INDICATORS: tuple[str, ...] = (DEVS_PER_SLOT, DEVS_PER_QA)

LOW = "low"
HIGH = "high"
NO_CAPACITY = "no_capacity"
NO_QA = "no_qa"

SOURCE_NORM = "norm"
SOURCE_MEDIAN = "median"

BAND_BELOW = Fraction(1, 2)  # median − 50 %
BAND_ABOVE = Fraction(3, 2)  # median + 50 %
MIN_TEAMS = 3  # fewer teams with a value: nothing meaningful to compare with


@dataclass(frozen=True, slots=True)
class TeamIndicators:
    team_id: str
    developers: int | None  # None without a capacity mapping
    testers: int | None
    devs_per_slot: Fraction | None
    devs_per_qa: Fraction | None
    marks: Mapping[str, str]  # indicator -> low | high (only marked indicators)
    flags: tuple[str, ...]  # sorted (TI-7)

    def value(self, indicator: str) -> Fraction | None:
        return self.devs_per_slot if indicator == DEVS_PER_SLOT else self.devs_per_qa


@dataclass(frozen=True, slots=True)
class IndicatorStats:
    all: Fraction | None  # summed numerators ÷ summed denominators (TI-4)
    median: Fraction | None
    low: Fraction | None  # band limits; None = not checked
    high: Fraction | None
    source: str | None  # norm | median | None (fewer than MIN_TEAMS values and no norm)


@dataclass(frozen=True, slots=True)
class Indicators:
    teams: Mapping[str, TeamIndicators]  # by team id, file order
    devs_per_slot: IndicatorStats
    devs_per_qa: IndicatorStats

    def stats(self, indicator: str) -> IndicatorStats:
        return self.devs_per_slot if indicator == DEVS_PER_SLOT else self.devs_per_qa


def median(values: Sequence[Fraction]) -> Fraction | None:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return None
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _stats(values: Sequence[Fraction], numerator: int, denominator: int, norm: Band | None) -> IndicatorStats:
    total = Fraction(numerator, denominator) if denominator else None
    mid = median(values)
    if norm is not None:
        return IndicatorStats(total, mid, norm.min, norm.max, SOURCE_NORM)
    if mid is not None and len(values) >= MIN_TEAMS:
        return IndicatorStats(total, mid, mid * BAND_BELOW, mid * BAND_ABOVE, SOURCE_MEDIAN)
    return IndicatorStats(total, mid, None, None, None)


def _mark(value: Fraction | None, stats: IndicatorStats) -> str | None:
    if value is None:
        return None
    if stats.low is not None and value < stats.low:
        return LOW
    if stats.high is not None and value > stats.high:
        return HIGH
    return None


def team_indicators(teams: Sequence[Team], norms: TeamNorms) -> Indicators:
    """Indicators of every team (file order) and the roadmap-wide values and bands."""
    raw: dict[str, tuple[int | None, int | None, Fraction | None, Fraction | None]] = {}
    per_slot: list[Fraction] = []
    per_qa: list[Fraction] = []
    devs_all = slots_all = devs_with_qa = testers_all = 0
    for t in teams:
        if not t.capacity_given:
            raw[t.id] = (None, None, None, None)
            continue
        devs, testers = t.capacity.developers, t.capacity.testers
        slot = Fraction(devs, t.slots)
        qa = Fraction(devs, testers) if testers else None
        raw[t.id] = (devs, testers, slot, qa)
        per_slot.append(slot)
        devs_all += devs
        slots_all += t.slots
        if qa is not None:
            per_qa.append(qa)
            devs_with_qa += devs
            testers_all += testers
    slot_stats = _stats(per_slot, devs_all, slots_all, norms.devs_per_slot)
    qa_stats = _stats(per_qa, devs_with_qa, testers_all, norms.devs_per_qa)

    out: dict[str, TeamIndicators] = {}
    for t in teams:
        t_devs, t_testers, t_slot, t_qa = raw[t.id]
        marks: dict[str, str] = {}
        flags: list[str] = []
        for indicator, value, stats in ((DEVS_PER_SLOT, t_slot, slot_stats), (DEVS_PER_QA, t_qa, qa_stats)):
            mark = _mark(value, stats)
            if mark is not None:
                marks[indicator] = mark
                flags.append(f"{indicator}_{mark}")
        if t_devs is None:
            flags.append(NO_CAPACITY)
        elif t_devs > 0 and not t_testers:
            flags.append(NO_QA)
        out[t.id] = TeamIndicators(t.id, t_devs, t_testers, t_slot, t_qa, MappingProxyType(marks), tuple(sorted(flags)))
    return Indicators(MappingProxyType(out), slot_stats, qa_stats)
