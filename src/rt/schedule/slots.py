"""SlotBoard: per-team lanes of sorted, non-overlapping intervals (ADS 6.2)."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable
from datetime import date, timedelta
from typing import NamedTuple

from rt.model.types import Team
from rt.schedule.types import Interval


def _start_of(interval: Interval) -> date:
    return interval.start


class Lane:
    """One row of a team: intervals sorted by start, never overlapping (RS SC-3)."""

    __slots__ = ("intervals",)

    def __init__(self) -> None:
        self.intervals: list[Interval] = []

    def accepts(self, candidate: Interval) -> bool:
        """The neighbour before the insertion point ends at or before the start, the one after starts at or
        after the end; an ongoing candidate needs the lane empty from its start on."""
        items = self.intervals
        i = bisect_right(items, candidate.start, key=_start_of)
        if i > 0:
            before = items[i - 1]
            if before.end is None or before.end > candidate.start:
                return False
        if i < len(items):
            after = items[i]
            if candidate.end is None or after.start < candidate.end:
                return False
        return True

    def add(self, interval: Interval) -> None:
        i = bisect_right(self.intervals, interval.start, key=_start_of)
        self.intervals.insert(i, interval)

    def finite_ends(self) -> Iterable[date]:
        return (iv.end for iv in self.intervals if iv.end is not None)


class Hit(NamedTuple):
    lane: int  # 1-based
    start: date


class SlotBoard:
    """Lanes for every team: `slots` regular lanes, then overflow lanes created on demand (RS SC-6)."""

    def __init__(self, teams: Iterable[Team]) -> None:
        self._slots: dict[str, int] = {}
        self._lanes: dict[str, list[Lane]] = {}
        for team in teams:
            self._slots[team.id] = team.slots
            self._lanes[team.id] = [Lane() for _ in range(team.slots)]

    def slots(self, team_id: str) -> int:
        return self._slots[team_id]

    def lane_count(self, team_id: str) -> int:
        return len(self._lanes[team_id])

    def lanes(self, team_id: str) -> tuple[Lane, ...]:
        return tuple(self._lanes[team_id])

    def first_fit(self, team_id: str, earliest: date, duration: timedelta | None) -> Hit | None:
        """RS SC-5 steps 2–3 over regular slots: candidate dates in order, then slots 1…N in order."""
        regular = self._lanes[team_id][: self._slots[team_id]]
        candidates = {earliest}
        for lane in regular:
            candidates.update(end for end in lane.finite_ends() if end > earliest)
        for t in sorted(candidates):
            interval = Interval(t, None if duration is None else t + duration)
            for number, lane in enumerate(regular, 1):
                if lane.accepts(interval):
                    return Hit(number, t)
        return None

    def fit_at(self, team_id: str, start: date, duration: timedelta | None) -> Hit:
        """RS SC-6: regular slots, then existing overflow lanes, at `start` only; else a new overflow lane."""
        interval = Interval(start, None if duration is None else start + duration)
        lanes = self._lanes[team_id]
        for number, lane in enumerate(lanes, 1):
            if lane.accepts(interval):
                return Hit(number, start)
        lanes.append(Lane())
        return Hit(len(lanes), start)

    def place(self, team_id: str, lane: int, interval: Interval) -> None:
        lanes = self._lanes[team_id]
        while len(lanes) < lane:
            lanes.append(Lane())
        lanes[lane - 1].add(interval)
