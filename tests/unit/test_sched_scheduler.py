"""Scheduler (RS 4.2, worked examples 4.4 and 4.5, AT-07 to AT-09, AT-30, AT-31)."""

from __future__ import annotations

from datetime import date

import pytest
from modelkit import DE, WE, load_path, make_model

from rt.diagnostics import Code, Collector
from rt.model.types import Mode, ResolvedModel
from rt.schedule.horizon import anchor
from rt.schedule.scheduler import delay_reason, schedule
from rt.schedule.types import Schedule

D = date


def run(m: ResolvedModel, mode: Mode | None = None) -> tuple[Schedule | None, Collector]:
    diags = Collector()
    s = schedule(m, mode or m.settings.on_conflict, anchor(m.settings), diags)
    return s, diags


def rows(s: Schedule) -> list[tuple[int, int, date, date | None, int, str | None]]:
    return [(p.seq, p.lane, p.start, p.end, p.delay_days, p.delay_reason) for p in s.placements]


def test_worked_example_table_4_4() -> None:
    s, diags = run(load_path(WE))
    assert s is not None and not diags.items
    assert rows(s) == [
        (1, 1, D(2027, 1, 1), D(2027, 2, 26), 0, None),
        (2, 2, D(2027, 1, 1), D(2027, 1, 29), 0, None),
        (3, 2, D(2027, 1, 29), D(2027, 2, 26), 28, "capacity"),
        (4, 1, D(2027, 2, 26), D(2027, 3, 12), 25, "capacity"),
        (5, 2, D(2027, 3, 1), None, 0, None),
        (6, 1, D(2027, 3, 12), D(2027, 4, 9), 11, "capacity"),
        (7, 1, D(2027, 4, 1), D(2027, 4, 29), 0, None),
        (8, 1, D(2027, 2, 1), D(2027, 2, 15), 0, None),
        (9, 1, D(2027, 4, 29), D(2027, 6, 24), 59, "capacity"),
    ]
    assert dict(s.lane_count) == {"alpha": 2, "beta": 2 - 1}
    assert all(not p.overflow for p in s.placements)


def test_dependencies_table_4_5() -> None:
    s, diags = run(load_path(DE))
    assert s is not None and not diags.items
    assert rows(s) == [
        (1, 1, D(2027, 1, 1), D(2027, 2, 26), 0, None),
        (2, 1, D(2027, 2, 26), D(2027, 3, 26), 56, "dependency"),
        (3, 1, D(2027, 1, 1), D(2027, 1, 29), 0, None),
        (4, 1, D(2027, 3, 26), D(2027, 4, 9), 0, None),
        (5, 1, D(2027, 1, 1), None, 0, None),
        (6, 2, D(2027, 3, 26), D(2027, 4, 9), 53, "dependency"),
        (7, 2, D(2027, 3, 1), D(2027, 3, 15), 0, None),
        (8, 2, D(2027, 4, 9), D(2027, 4, 23), 67, "dependency+capacity"),
    ]
    earliest = [p.earliest for p in s.placements]
    assert earliest == [
        D(2027, 1, 1),
        D(2027, 2, 26),
        D(2027, 1, 1),
        D(2027, 3, 26),
        D(2027, 1, 1),
        D(2027, 3, 26),
        D(2027, 3, 1),
        D(2027, 3, 26),
    ]
    assert s.placement(3).requested is None and s.placement(4).requested is None


def test_at07_overflow_mode() -> None:
    s, diags = run(load_path(WE, on_conflict="overflow"))
    assert s is not None and not diags.items  # W011 is emitted by plan.build
    by = {p.seq: p for p in s.placements}
    assert (by[3].lane, by[3].start, by[3].overflow) == (3, D(2027, 1, 1), True)
    assert (by[9].lane, by[9].start, by[9].overflow) == (2, D(2027, 3, 1), True)
    assert (by[4].lane, by[4].start, by[4].end) == (2, D(2027, 2, 1), D(2027, 2, 15))
    assert by[5].lane == 1
    assert (by[6].lane, by[6].start, by[6].end) == (2, D(2027, 3, 1), D(2027, 3, 29))
    assert dict(s.lane_count) == {"alpha": 3, "beta": 2}


def test_at08_error_mode_reports_every_conflict() -> None:
    s, diags = run(load_path(WE, on_conflict="error"))
    assert s is None
    assert [(d.code, d.line, d.col) for d in diags.items] == [(Code.E061, 38, 5), (Code.E061, 62, 5)]
    assert diags.items[0].message == 'project "Reporting" needs a slot on 2027-01-01 but team "alpha" has 2 of 2 busy'
    assert diags.items[1].message == 'project "Big bang" needs a slot on 2027-03-01 but team "beta" has 1 of 1 busy'
    assert diags.has_scheduling_errors()


def test_at09_e060_ongoing_blocks_the_only_slot() -> None:
    m = make_model(
        [("a", "sd", 1)],
        [
            {"name": "Run", "team": "a", "ongoing": True, "start": "2027-01"},
            {"name": "Feature", "team": "a", "size": "M", "start": "2027-02"},
        ],
    )
    s, diags = run(m)
    assert s is None
    assert [d.code for d in diags.items] == [Code.E060]
    assert diags.items[0].message == (
        'project "Feature" cannot be scheduled: every slot of team "a" is held by an ongoing project'
    )


@pytest.mark.parametrize("mode", [Mode.OVERFLOW, Mode.ERROR])
def test_e060_for_auto_start_projects_in_any_mode(mode: Mode) -> None:
    m = make_model(
        [("a", "sd", 1)],
        [
            {"name": "Run", "team": "a", "ongoing": True, "start": "2027-01"},
            {"name": "Auto", "team": "a", "size": "S"},
            {"name": "Dependent", "team": "a", "size": "S", "start": "2027-03", "deps": [2]},
        ],
        mode=mode,
    )
    s, diags = run(m)
    assert s is None
    assert [d.code for d in diags.items] == [Code.E060]  # the dependent project is skipped, not reported


def test_overflow_mode_requested_start_with_dependency_is_delayed_by_dependency() -> None:
    m = make_model(
        [("a", "sd", 1), ("b", "sd", 1)],
        [
            {"name": "Base", "team": "a", "size": "L", "start": "2027-01"},
            {"name": "Next", "team": "b", "size": "S", "start": "2027-01", "deps": [1]},
        ],
        mode=Mode.OVERFLOW,
    )
    s, _ = run(m)
    assert s is not None
    nxt = s.placement(2)
    assert (nxt.start, nxt.delay_days, nxt.delay_reason, nxt.overflow) == (D(2027, 2, 26), 56, "dependency", False)


def test_auto_start_never_overflows() -> None:
    m = make_model(
        [("a", "sd", 1)],
        [
            {"name": "One", "team": "a", "size": "M", "start": "2027-01"},
            {"name": "Two", "team": "a", "size": "S"},
        ],
        mode=Mode.OVERFLOW,
        hstart="2027-01",
    )
    s, _ = run(m)
    assert s is not None
    two = s.placement(2)
    assert (two.lane, two.start, two.overflow, two.delay_days, two.delay_reason) == (1, D(2027, 1, 29), False, 0, None)


def test_at30_anchor_from_horizon_start() -> None:
    m = load_path(DE, hfrom="2027-02")
    assert anchor(m.settings) == D(2027, 2, 1)
    s, _ = run(m)
    assert s is not None
    assert (s.placement(3).lane, s.placement(3).start, s.placement(3).end) == (2, D(2027, 2, 1), D(2027, 3, 1))
    assert s.placement(5).start == D(2027, 2, 1)


def test_at31_dependencies_overflow() -> None:
    s, _ = run(load_path(DE, on_conflict="overflow"))
    assert s is not None
    audit = s.placement(8)
    assert (audit.lane, audit.start, audit.delay_days, audit.delay_reason, audit.overflow) == (
        3,
        D(2027, 3, 26),
        53,
        "dependency",
        True,
    )
    base, _ = run(load_path(DE))
    assert base is not None
    for seq in (3, 4, 5):
        assert s.placement(seq) == base.placement(seq)


def test_anchor_defaults_to_today_month() -> None:
    m = make_model([("a", "sd", 1)], [{"team": "a"}], today=D(2027, 5, 20))
    assert anchor(m.settings) == D(2027, 5, 1)
    s, _ = run(m)
    assert s is not None and s.placement(1).start == D(2027, 5, 1)


@pytest.mark.parametrize(
    ("dep", "cap", "reason"),
    [(0, 0, None), (3, 0, "dependency"), (0, 3, "capacity"), (3, 3, "dependency+capacity")],
)
def test_delay_reason(dep: int, cap: int, reason: str | None) -> None:
    assert delay_reason(dep, cap) == reason


def test_dependency_already_met_is_not_a_delay() -> None:
    s, _ = run(load_path(DE))
    assert s is not None
    assert (s.placement(7).delay_days, s.placement(7).delay_reason) == (0, None)
