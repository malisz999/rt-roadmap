"""Pixel geometry (RS OUT-6 to OUT-9, OUT-20, OUT-23, OUT-28; ADS 6.7)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from rt.decimalutil import px
from rt.layout import geometry as g
from rt.timeutil import Month

WE = g.Scale(Month(2027, 1), Month(2027, 6), 120)
EX = g.Scale(Month(2026, 10), Month(2027, 6), 120)


def test_x_follows_the_month_scale() -> None:
    assert WE.x(date(2027, 1, 1)) == 0
    assert px(WE.x(date(2027, 1, 29))) == "108.39"  # 28/31 × 120
    assert WE.x(date(2027, 2, 15)) == 180  # AT-05 today
    assert WE.x(WE.h1) == WE.width == 720
    assert WE.h0 == date(2027, 1, 1) and WE.h1 == date(2027, 7, 1)
    assert WE.contains(date(2027, 6, 30)) and not WE.contains(WE.h1)


def test_bar_boxes_of_at03_and_at04() -> None:
    cases = {
        (date(2027, 1, 29), date(2027, 2, 26)): ("110.39", "114.76"),  # Reporting
        (date(2027, 2, 1), date(2027, 2, 15)): ("122.00", "56.00"),  # Quick win
        (date(2027, 4, 29), date(2027, 6, 24)): ("474.00", "216.00"),  # Big bang
        (date(2027, 3, 1), date(2027, 7, 1)): ("242.00", "476.00"),  # Maintenance, ongoing to h1 (C7)
    }
    for (start, end), (left, width) in cases.items():
        box = g.bar_box(WE, start, end)
        assert (px(box.left), px(box.width)) == (left, width)


def test_minimum_bar_width_is_6px() -> None:
    box = g.bar_box(WE, date(2027, 1, 1), date(2027, 1, 2))  # 3.87 px of time
    assert box.width == 6 and box.left == 2
    assert box.right == 8


def test_lead_box() -> None:
    bar = g.bar_box(WE, date(2027, 1, 29), date(2027, 2, 26))
    hit = g.lead_box(WE, date(2027, 1, 1), bar)
    assert hit is not None
    lead, cut = hit
    assert (lead.left, px(lead.width), cut) == (0, "110.39", False)
    # requested before the horizon: starts at the left edge, no circle
    hit = g.lead_box(WE, date(2026, 12, 1), bar)
    assert hit is not None and hit[1] is True and hit[0].left == 0
    # bar at the left edge: nothing visible
    assert g.lead_box(WE, date(2026, 12, 1), g.bar_box(WE, date(2027, 1, 1), date(2027, 2, 1))) is None


def test_boundary_marks_skip_the_left_edge_and_prefer_the_strongest_style() -> None:
    marks = g.boundary_marks(WE)
    assert [(m.kind, m.day.isoformat(), m.x) for m in marks] == [
        ("month", "2027-02-01", 120),
        ("month", "2027-03-01", 240),
        ("quarter", "2027-04-01", 360),
        ("month", "2027-05-01", 480),
        ("month", "2027-06-01", 600),
    ]
    ex = {m.day: m.kind for m in g.boundary_marks(EX)}
    assert date(2026, 10, 1) not in ex  # horizon left edge (AT-33)
    assert ex[date(2027, 1, 1)] == g.YEAR
    assert ex[date(2027, 4, 1)] == g.QUARTER
    assert ex[date(2026, 11, 1)] == g.MONTH


def test_header_spans() -> None:
    quarters = g.quarter_spans(EX)
    assert [(s.key, s.label, s.box.left, s.box.width) for s in quarters] == [
        ("2026-Q4", "Q4", 0, 360),
        ("2027-Q1", "Q1", 360, 360),
        ("2027-Q2", "Q2", 720, 360),
    ]
    partial = g.quarter_spans(g.Scale(Month(2027, 2), Month(2027, 4), 60))
    assert [(s.key, s.box.left, s.box.width) for s in partial] == [("2027-Q1", 0, 120), ("2027-Q2", 120, 60)]
    years = g.year_spans(EX)
    assert [(s.label, s.box.width) for s in years] == [("2026", 360), ("2027", 720)]
    months = g.month_spans(WE)
    assert [s.label for s in months] == ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    assert months[1].key == "2027-02" and months[1].box.left == 120


def test_lane_positions() -> None:
    assert g.team_height(2) == 96 and g.team_height(1) == 56
    lanes = g.lane_slots([2, 1])
    assert [[slot.top for slot in team] for team in lanes] == [[8, 48], [104]]
    assert lanes[0][1].mid == 68 and lanes[0][1].bottom == 88


def test_connector_routes() -> None:
    lanes = g.lane_slots([1, 2])
    pred = g.Box(Decimal(2), Decimal(100))  # right end 102
    succ = g.Box(Decimal(106), Decimal(50))  # left edge 106
    # successor lower: run along the boundary just above its lane
    assert g.connector_path(pred, lanes[0][0], succ, lanes[1][0]) == ("M102.00 28.00H110.00V64.00H98.00V84.00H106.00")
    # successor higher: the boundary just below its lane
    assert g.connector_path(pred, lanes[1][1], succ, lanes[1][0]) == ("M102.00 124.00H110.00V104.00H98.00V84.00H106.00")
    # same lane: the lane's own bottom boundary
    assert g.connector_path(pred, lanes[0][0], succ, lanes[0][0]) == ("M102.00 28.00H110.00V48.00H98.00V28.00H106.00")
