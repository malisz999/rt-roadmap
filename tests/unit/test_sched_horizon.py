"""Horizon and visibility (RS SC-9, SC-10, SC-12, AT-12, W012)."""

from __future__ import annotations

from datetime import date
from typing import Any

from modelkit import DE, WE, load_path, make_model

from rt.diagnostics import Code, Collector
from rt.model.types import Mode, ResolvedModel
from rt.schedule.horizon import anchor, make_horizon, resolve_horizon, visibility
from rt.schedule.scheduler import schedule
from rt.schedule.types import Horizon, Schedule
from rt.timeutil import Month

D = date


def horizon_of(m: ResolvedModel) -> tuple[Horizon, Schedule, Collector]:
    diags = Collector()
    s = schedule(m, m.settings.on_conflict, anchor(m.settings), diags)
    assert s is not None
    return resolve_horizon(m, s, m.settings, diags), s, diags


def test_make_horizon() -> None:
    h = make_horizon(Month(2027, 1), Month(2027, 6))
    assert (h.h0, h.h1, h.days) == (D(2027, 1, 1), D(2027, 7, 1), 181)


def test_worked_example_auto_horizon() -> None:
    h, _, diags = horizon_of(load_path(WE))
    assert (h.start, h.end) == (Month(2027, 1), Month(2027, 6))
    assert not diags.items


def test_dependencies_example_extended_to_six_months() -> None:
    h, _, _ = horizon_of(load_path(DE))
    assert (h.start, h.end) == (Month(2027, 1), Month(2027, 6))


def test_auto_start_uses_actual_start_month() -> None:
    m = make_model(
        [("a", "sd", 1)],
        [{"team": "a", "size": "M", "start": "2027-05"}, {"team": "a", "size": "S"}],
        today=D(2027, 3, 10),
    )
    h, s, _ = horizon_of(m)
    assert s.placement(2).start == D(2027, 3, 1)
    assert h.start == Month(2027, 3)


def test_end_from_ongoing_start_month() -> None:
    m = make_model(
        [("a", "sd", 2)],
        [{"team": "a", "size": "S", "start": "2027-01"}, {"team": "a", "ongoing": True, "start": "2027-09"}],
    )
    h, _, _ = horizon_of(m)
    assert (h.start, h.end) == (Month(2027, 1), Month(2027, 9))


def test_end_month_contains_last_day() -> None:
    # 4 weeks from 2027-02-01 ends 2027-03-01 (exclusive): last day is in February
    m = make_model(
        [("a", "sd", 1)],
        [{"team": "a", "size": "M", "start": "2027-02"}, {"team": "a", "size": "L", "start": "2027-07"}],
        sizes={"M": 4, "L": 4},
    )
    h, _, _ = horizon_of(m)
    assert h.end == Month(2027, 7)


def test_no_projects_uses_today_month() -> None:
    m = make_model([("a", "sd", 1)], [], today=D(2027, 4, 9))
    h, _, _ = horizon_of(m)
    assert (h.start, h.end) == (Month(2027, 4), Month(2027, 9))


def test_cap_at_120_months_with_w012() -> None:
    m = make_model(
        [("a", "sd", 1)],
        [{"team": "a", "size": "S", "start": "2027-01"}, {"team": "a", "size": "S", "start": "2040-01"}],
    )
    h, _, diags = horizon_of(m)
    assert (h.start, h.end) == (Month(2027, 1), Month(2036, 12))
    assert [(d.code, d.line) for d in diags.items] == [(Code.W012, 1)]
    assert diags.items[0].message == "automatic horizon capped at 120 months (2027-01 to 2036-12)"


def test_explicit_end_with_auto_start_after_it() -> None:
    m = make_model([("a", "sd", 1)], [{"team": "a", "size": "S", "start": "2028-03"}], hend="2027-12")
    h, _, _ = horizon_of(m)
    assert (h.start, h.end) == (Month(2027, 12), Month(2027, 12))


def test_explicit_end_with_long_auto_start_is_capped() -> None:
    m = make_model([("a", "sd", 1)], [{"team": "a", "size": "S", "start": "2020-01"}], hend="2035-12")
    h, _, diags = horizon_of(m)
    assert (h.start, h.end) == (Month(2026, 1), Month(2035, 12))
    assert [d.code for d in diags.items] == [Code.W012]


def test_explicit_start_end_kept_short() -> None:
    m = make_model([("a", "sd", 1)], [{"team": "a", "size": "S", "start": "2027-01"}], hstart="2027-01", hend="2027-02")
    h, _, _ = horizon_of(m)
    assert (h.start, h.end, h.days) == (Month(2027, 1), Month(2027, 2), 59)


def test_explicit_start_after_projects_gets_six_months() -> None:
    m = make_model([("a", "sd", 1)], [{"team": "a", "size": "S", "start": "2027-01"}], hstart="2028-01")
    h, _, _ = horizon_of(m)
    assert (h.start, h.end) == (Month(2028, 1), Month(2028, 6))


def flags_of(m: ResolvedModel) -> dict[int, tuple[Any, ...]]:
    h, s, _ = horizon_of(m)
    vis = visibility(m, s, h)
    return {seq: (v.start, v.end, tuple(sorted(v.flags))) for seq, v in vis.items()}


def test_at12_clipping_and_hidden() -> None:
    f = flags_of(load_path(WE, hfrom="2027-02", hto="2027-04"))
    assert f[1] == (D(2027, 2, 1), D(2027, 2, 26), ("clipped_left",))
    assert f[3] == (D(2027, 2, 1), D(2027, 2, 26), ("clipped_left", "delayed"))
    assert f[2] == (None, None, ("hidden",))
    assert f[9] == (D(2027, 4, 29), D(2027, 5, 1), ("clipped_right", "delayed"))
    assert f[5] == (D(2027, 3, 1), D(2027, 5, 1), ("continues",))


def test_worked_example_flags() -> None:
    f = flags_of(load_path(WE))
    assert f[5] == (D(2027, 3, 1), D(2027, 7, 1), ("continues",))
    assert f[8][2] == ()
    assert f[9][2] == ("delayed",)


def test_dependencies_flags() -> None:
    f = flags_of(load_path(DE))
    assert f[3][2] == ("auto_start",)
    assert f[5][2] == ("auto_start", "continues")


def test_overflow_flag_and_ongoing_after_horizon_hidden() -> None:
    m = make_model(
        [("a", "sd", 1)],
        [
            {"team": "a", "size": "M", "start": "2027-01"},
            {"team": "a", "size": "M", "start": "2027-01"},
            {"team": "a", "ongoing": True, "start": "2027-08"},
        ],
        hstart="2027-01",
        hend="2027-06",
        mode=Mode.OVERFLOW,
    )
    f = flags_of(m)
    assert f[2][2] == ("over_capacity",)
    assert f[3] == (None, None, ("hidden",))
