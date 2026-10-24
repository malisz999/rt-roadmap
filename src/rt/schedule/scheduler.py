"""Slot assignment in delay, overflow and error mode (RS SC-5 to SC-8, SC-12, SC-13; ADS 6.2)."""

from __future__ import annotations

from datetime import date, timedelta
from types import MappingProxyType

from rt.diagnostics import Code, Collector
from rt.model.types import Mode, Project, ResolvedModel
from rt.schedule.slots import SlotBoard
from rt.schedule.types import (
    REASON_BOTH,
    REASON_CAPACITY,
    REASON_DEPENDENCY,
    Interval,
    Placement,
    Schedule,
)


def delay_reason(dep_days: int, cap_days: int) -> str | None:
    """`dependency`, `capacity`, `dependency+capacity` or None, from which part of the delay is non-zero."""
    if dep_days and cap_days:
        return REASON_BOTH
    if dep_days:
        return REASON_DEPENDENCY
    if cap_days:
        return REASON_CAPACITY
    return None


def _make_placement(
    p: Project, team_id: str, lane: int, slots: int, earliest: date, start: date, dur: timedelta | None
) -> Placement:
    requested = None if p.start is None else p.start.first_day()
    if requested is None:
        delay_days, reason = 0, None
    else:
        delay_days = (start - requested).days
        reason = delay_reason((earliest - requested).days, (start - earliest).days)
    return Placement(
        seq=p.seq,
        team_id=team_id,
        lane=lane,
        overflow=lane > slots,
        requested=requested,
        earliest=earliest,
        start=start,
        end=None if dur is None else start + dur,
        delay_days=delay_days,
        delay_reason=reason,
    )


def schedule(m: ResolvedModel, mode: Mode, anchor: date, diags: Collector) -> Schedule | None:
    """Place every project in file order. Returns None when E060 or E061 was reported.

    In error mode, conflicting projects are still placed in virtual overflow lanes so later projects are judged
    as in overflow mode and every conflict is reported in one run (ADS C6).
    """
    board = SlotBoard(m.teams)
    placed: list[Placement | None] = []
    failed = False
    for p in m.projects:
        team_id = p.team_id
        if team_id is None:  # pragma: no cover - the validator guarantees a team
            raise ValueError(f"project #{p.seq} has no team")
        base = anchor if p.start is None else p.start.first_day()
        dep_ends: list[date] = []
        blocked = False
        for d in m.deps.get(p.seq, ()):
            dep = placed[d - 1] if 0 < d <= len(placed) else None
            if dep is None:
                blocked = True  # dependency unschedulable (already reported); skip this project
            elif dep.end is not None:
                dep_ends.append(dep.end)
        if blocked:
            placed.append(None)
            continue
        earliest = max([base, *dep_ends])
        weeks = m.weeks.get(p.seq)
        dur = None if p.ongoing or weeks is None else timedelta(days=weeks * 7)
        slots = board.slots(team_id)
        if mode is Mode.DELAY or p.start is None:  # SC-5, SC-12
            hit = board.first_fit(team_id, earliest, dur)
            if hit is None:
                diags.error(Code.E060, p.pos, project=p.name, team=team_id)
                failed = True
                placed.append(None)
                continue
        else:  # SC-6, SC-7
            hit = board.fit_at(team_id, earliest, dur)
            if hit.lane > slots and mode is Mode.ERROR:
                diags.error(
                    Code.E061, p.pos, project=p.name, date=earliest.isoformat(), team=team_id, busy=slots, slots=slots
                )
                failed = True
        board.place(team_id, hit.lane, Interval(hit.start, None if dur is None else hit.start + dur))
        placed.append(_make_placement(p, team_id, hit.lane, slots, earliest, hit.start, dur))
    if failed:
        return None
    placements = tuple(pl for pl in placed if pl is not None)
    lane_count = MappingProxyType({t.id: board.lane_count(t.id) for t in m.teams})
    return Schedule(placements, lane_count)
