"""Slot assignment in delay, overflow and error mode (RS SC-5 to SC-8, SC-12, SC-13; ADS 6.2)."""

from __future__ import annotations

from dataclasses import replace
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


def _duration(m: ResolvedModel, p: Project) -> timedelta | None:
    weeks = m.weeks.get(p.seq)
    return None if p.ongoing or weeks is None else timedelta(days=weeks * 7)


def _place_locked(m: ResolvedModel, board: SlotBoard) -> dict[int, Placement]:
    """RS SC-14 pass 1: every locked project, in file order, exactly at its requested start. No regular slot free
    (only other locked work is on the board) -> the first free overflow lane, in every mode."""
    placed: dict[int, Placement] = {}
    for p in m.projects:
        if not p.locked or p.start is None or p.team_id is None:
            continue
        start = p.start.first_day()
        dur = _duration(m, p)
        hit = board.fit_at(p.team_id, start, dur)
        board.place(p.team_id, hit.lane, Interval(start, None if dur is None else start + dur))
        slots = board.slots(p.team_id)
        placed[p.seq] = Placement(
            seq=p.seq,
            team_id=p.team_id,
            lane=hit.lane,
            overflow=hit.lane > slots,
            requested=start,
            earliest=start,
            start=start,
            end=None if dur is None else start + dur,
            delay_days=0,
            delay_reason=None,
            locked=True,
        )
    return placed


def _with_risk(m: ResolvedModel, pl: Placement, placed: dict[int, Placement]) -> Placement:
    """RS SC-15: earliest start from the dependencies once everything is placed; lock risk from it and the lane."""
    dep_ends = [d.end for s in m.deps.get(pl.seq, ()) if (d := placed.get(s)) is not None and d.end is not None]
    earliest = max([pl.start, *dep_ends])
    return replace(
        pl,
        earliest=earliest,
        lock_risk=delay_reason((earliest - pl.start).days, 1 if pl.overflow else 0),
    )


def schedule(m: ResolvedModel, mode: Mode, anchor: date, diags: Collector) -> Schedule | None:
    """Place every project: locked projects first at their promised start (RS SC-14), then all others in file
    order. Returns None when E060 or E061 was reported.

    In error mode, conflicting projects are still placed in virtual overflow lanes so later projects are judged
    as in overflow mode and every conflict is reported in one run (ADS C6).
    """
    board = SlotBoard(m.teams)
    placed: dict[int, Placement] = _place_locked(m, board)
    failed = False
    for p in m.projects:
        if p.seq in placed:
            continue
        team_id = p.team_id
        if team_id is None:  # pragma: no cover - the validator guarantees a team
            raise ValueError(f"project #{p.seq} has no team")
        base = anchor if p.start is None else p.start.first_day()
        dep_ends: list[date] = []
        blocked = False
        for d in m.deps.get(p.seq, ()):
            dep = placed.get(d)
            if dep is None:
                blocked = True  # dependency unschedulable (already reported); skip this project
            elif dep.end is not None:
                dep_ends.append(dep.end)
        if blocked:
            continue
        earliest = max([base, *dep_ends])
        dur = _duration(m, p)
        slots = board.slots(team_id)
        if mode is Mode.DELAY or p.start is None:  # SC-5, SC-12
            hit = board.first_fit(team_id, earliest, dur)
            if hit is None:
                diags.error(Code.E060, p.pos, project=p.name, team=team_id)
                failed = True
                continue
        else:  # SC-6, SC-7
            hit = board.fit_at(team_id, earliest, dur)
            if hit.lane > slots and mode is Mode.ERROR:
                diags.error(
                    Code.E061, p.pos, project=p.name, date=earliest.isoformat(), team=team_id, busy=slots, slots=slots
                )
                failed = True
        board.place(team_id, hit.lane, Interval(hit.start, None if dur is None else hit.start + dur))
        placed[p.seq] = _make_placement(p, team_id, hit.lane, slots, earliest, hit.start, dur)
    if failed:
        return None
    for seq, pl in list(placed.items()):
        if pl.locked:
            placed[seq] = _with_risk(m, pl, placed)
    placements = tuple(placed[p.seq] for p in m.projects if p.seq in placed)
    lane_count = MappingProxyType({t.id: board.lane_count(t.id) for t in m.teams})
    return Schedule(placements, lane_count)
