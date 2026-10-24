"""SlotBoard and Lane (RS SC-3, SC-5 steps 2–3, SC-6, SC-8; ADS 6.2)."""

from __future__ import annotations

from datetime import date, timedelta

from rt.diagnostics import Pos
from rt.model.types import Capacity, Team
from rt.schedule.slots import Hit, Lane, SlotBoard
from rt.schedule.types import Interval

D = date
W4 = timedelta(days=28)


def team(tid: str = "a", slots: int = 2) -> Team:
    return Team(tid, tid, "sd", slots, Capacity(), Pos(1, 1, "<t>"))


def test_interval_overlap_rules() -> None:
    a = Interval(D(2027, 1, 1), D(2027, 1, 29))
    assert not a.overlaps(Interval(D(2027, 1, 29), D(2027, 2, 5)))  # touching
    assert a.overlaps(Interval(D(2027, 1, 28), D(2027, 2, 5)))
    assert a.overlaps(Interval(D(2026, 12, 1), None))
    assert not Interval(D(2027, 2, 1), None).overlaps(a)
    assert Interval(D(2027, 1, 5), None).overlaps(Interval(D(2027, 3, 1), None))


def test_lane_accepts_touching_and_gaps() -> None:
    lane = Lane()
    lane.add(Interval(D(2027, 1, 1), D(2027, 1, 29)))
    lane.add(Interval(D(2027, 3, 1), D(2027, 3, 29)))
    assert lane.accepts(Interval(D(2027, 1, 29), D(2027, 2, 26)))  # fits the gap exactly
    assert lane.accepts(Interval(D(2027, 1, 29), D(2027, 3, 1)))
    assert not lane.accepts(Interval(D(2027, 1, 29), D(2027, 3, 2)))
    assert not lane.accepts(Interval(D(2027, 1, 1), D(2027, 1, 2)))  # same start
    assert not lane.accepts(Interval(D(2027, 2, 1), None))  # ongoing needs the lane empty from its start
    assert lane.accepts(Interval(D(2027, 3, 29), None))
    assert lane.accepts(Interval(D(2026, 12, 1), D(2027, 1, 1)))
    assert [iv.start for iv in lane.intervals] == [D(2027, 1, 1), D(2027, 3, 1)]


def test_lane_with_ongoing_blocks_later_starts() -> None:
    lane = Lane()
    lane.add(Interval(D(2027, 3, 1), None))
    assert not lane.accepts(Interval(D(2027, 5, 1), D(2027, 6, 1)))
    assert lane.accepts(Interval(D(2027, 1, 1), D(2027, 3, 1)))
    assert not lane.accepts(Interval(D(2027, 1, 1), D(2027, 3, 2)))
    assert list(lane.finite_ends()) == []


def test_first_fit_prefers_earliest_date_then_lowest_slot() -> None:
    board = SlotBoard([team(slots=2)])
    board.place("a", 1, Interval(D(2027, 1, 1), D(2027, 2, 26)))
    board.place("a", 2, Interval(D(2027, 1, 1), D(2027, 2, 26)))
    assert board.first_fit("a", D(2027, 2, 1), timedelta(days=14)) == Hit(1, D(2027, 2, 26))  # tie → slot 1
    board.place("a", 2, Interval(D(2027, 2, 26), D(2027, 4, 1)))
    assert board.first_fit("a", D(2027, 1, 1), W4) == Hit(1, D(2027, 2, 26))


def test_first_fit_backfills_before_a_later_interval() -> None:
    board = SlotBoard([team(slots=1)])
    board.place("a", 1, Interval(D(2027, 4, 1), D(2027, 4, 29)))
    assert board.first_fit("a", D(2027, 2, 1), timedelta(days=14)) == Hit(1, D(2027, 2, 1))
    assert board.first_fit("a", D(2027, 3, 1), timedelta(days=56)) == Hit(1, D(2027, 4, 29))


def test_first_fit_none_when_every_slot_is_ongoing() -> None:
    board = SlotBoard([team(slots=1)])
    board.place("a", 1, Interval(D(2027, 1, 1), None))
    assert board.first_fit("a", D(2027, 2, 1), W4) is None
    assert board.first_fit("a", D(2026, 1, 1), W4) == Hit(1, D(2026, 1, 1))  # fits before it


def test_fit_at_uses_regular_then_existing_overflow_then_new_lane() -> None:
    board = SlotBoard([team(slots=1)])
    board.place("a", 1, Interval(D(2027, 1, 1), D(2027, 3, 1)))
    assert board.fit_at("a", D(2027, 3, 1), W4) == Hit(1, D(2027, 3, 1))  # regular slot free again
    hit = board.fit_at("a", D(2027, 1, 15), W4)
    assert hit == Hit(2, D(2027, 1, 15))
    assert board.lane_count("a") == 2
    board.place("a", hit.lane, Interval(hit.start, hit.start + W4))  # [01-15, 02-12)
    assert board.fit_at("a", D(2027, 2, 12), W4) == Hit(2, D(2027, 2, 12))  # existing overflow lane is free
    assert board.fit_at("a", D(2027, 1, 20), W4) == Hit(3, D(2027, 1, 20))
    assert len(board.lanes("a")) == 3
    assert board.slots("a") == 1


def test_place_creates_missing_lanes() -> None:
    board = SlotBoard([team(slots=1)])
    board.place("a", 3, Interval(D(2027, 1, 1), None))
    assert board.lane_count("a") == 3
