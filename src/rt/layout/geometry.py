"""Pixel geometry of the page (RS OUT-6 to OUT-9, OUT-20, OUT-23, OUT-28; ADS 6.7).

Every value here is an exact `Decimal`; rounding to two decimals happens once, in the view model (`px()`).
Horizontal positions are timeline coordinates (x = 0 at the horizon start); vertical positions are section
coordinates (y = 0 at the top of a subdomain body).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from rt.decimalutil import px
from rt.timeutil import Month, month_range

LABEL_WIDTH = 280  # sticky team label column (RS OUT-6)
LANE_HEIGHT = 40  # slot row (RS OUT-9)
BAR_HEIGHT = 28
BAR_TOP = (LANE_HEIGHT - BAR_HEIGHT) // 2  # 6: bar vertically centred in its lane
TEAM_PAD = 8  # padding above and below the lanes of a team block
BAR_INSET = Decimal(2)  # left and right inset of a bar (RS OUT-8)
MIN_BAR_WIDTH = Decimal(6)
CHIP_MIN_WIDTH = Decimal(120)  # name plus size chip (RS OUT-17)
TEXT_MIN_WIDTH = Decimal(48)  # name only; below this no text
DEP_STUB = Decimal(8)  # connector run-out right of the predecessor and run-in left of the successor (RS OUT-28)

YEAR = "year"
QUARTER = "quarter"
MONTH = "month"


class Scale:
    """The month-scaled time axis of one horizon (RS OUT-6, OUT-7)."""

    __slots__ = ("end", "h0", "h1", "month_width", "months", "start", "width")

    def __init__(self, start: Month, end: Month, month_width: int) -> None:
        self.start = start
        self.end = end
        self.month_width = Decimal(month_width)
        self.months: tuple[Month, ...] = tuple(month_range(start, end))
        self.h0 = start.first_day()
        self.h1 = end.next().first_day()
        self.width = self.month_width * len(self.months)

    def x(self, d: date) -> Decimal:
        """x of a date: (month_index + (day − 1) / days_in_month) × month_width. x(h1) = timeline width."""
        index = Month.of(d).ordinal() - self.start.ordinal()
        days = Month.of(d).days()
        return (Decimal(index) + Decimal(d.day - 1) / Decimal(days)) * self.month_width

    def contains(self, d: date) -> bool:
        return self.h0 <= d < self.h1


@dataclass(frozen=True, slots=True)
class Box:
    """A horizontal extent in timeline coordinates."""

    left: Decimal
    width: Decimal

    @property
    def right(self) -> Decimal:
        return self.left + self.width


def bar_box(scale: Scale, vis_start: date, vis_end: date) -> Box:
    """RS OUT-8: inset 2 px on each side, at least 6 px wide. Ongoing bars end at x(h1) − 2 (ADS C7)."""
    x0 = scale.x(vis_start)
    x1 = scale.x(vis_end)
    return Box(x0 + BAR_INSET, max(x1 - x0 - 2 * BAR_INSET, MIN_BAR_WIDTH))


def lead_box(scale: Scale, requested: date, bar: Box) -> tuple[Box, bool] | None:
    """Dashed lead line of a delayed bar (RS OUT-20): from x(requested) to the bar's left edge.

    Returns the box and whether its start was cut at the horizon's left edge (no circle then); None when nothing
    of it is visible.
    """
    cut = requested < scale.h0
    x0 = Decimal(0) if cut else scale.x(requested)
    if bar.left - BAR_INSET <= x0:  # the requested start is not left of the bar's time start
        return None
    return Box(x0, bar.left - x0), cut


@dataclass(frozen=True, slots=True)
class Mark:
    """A vertical boundary line at a month start strictly inside the horizon (RS OUT-23)."""

    kind: str  # YEAR | QUARTER | MONTH; the strongest style wins where boundaries coincide
    day: date
    x: Decimal


def boundary_marks(scale: Scale) -> tuple[Mark, ...]:
    """One mark per month start strictly inside (h0, h1); none at the left edge (ADS 6.7)."""
    marks: list[Mark] = []
    for i, m in enumerate(scale.months[1:], start=1):
        if m.month == 1:
            kind = YEAR
        elif m.month in (4, 7, 10):
            kind = QUARTER
        else:
            kind = MONTH
        marks.append(Mark(kind, m.first_day(), scale.month_width * i))
    return tuple(marks)


@dataclass(frozen=True, slots=True)
class Span:
    """A labelled run of consecutive months in the timeline header."""

    key: str  # `2027`, `2027-Q2`, `2027-04`
    label: str  # `2027`, `Q2`, `Apr`
    first: Month
    box: Box


def year_spans(scale: Scale) -> tuple[Span, ...]:
    return _spans(scale, lambda m: (str(m.year), str(m.year)))


def quarter_spans(scale: Scale) -> tuple[Span, ...]:
    """Months grouped by calendar quarter; a partly visible quarter spans only the months shown (RS OUT-23)."""
    return _spans(scale, lambda m: (f"{m.year}-Q{m.quarter()}", f"Q{m.quarter()}"))


def month_spans(scale: Scale) -> tuple[Span, ...]:
    return _spans(scale, lambda m: (str(m), m.abbr()))


def _spans(scale: Scale, key_label: Callable[[Month], tuple[str, str]]) -> tuple[Span, ...]:
    out: list[Span] = []
    run_start = 0
    for i, m in enumerate(scale.months):
        key, label = key_label(m)
        last = i + 1 == len(scale.months) or key_label(scale.months[i + 1])[0] != key
        if last:
            first = scale.months[run_start]
            box = Box(scale.month_width * run_start, scale.month_width * (i + 1 - run_start))
            out.append(Span(key, label, first, box))
            run_start = i + 1
    return tuple(out)


@dataclass(frozen=True, slots=True)
class LaneSlot:
    """Vertical position of one lane in section coordinates."""

    top: Decimal

    @property
    def bottom(self) -> Decimal:
        return self.top + LANE_HEIGHT

    @property
    def mid(self) -> Decimal:
        return self.top + LANE_HEIGHT // 2


def team_height(lanes: int) -> int:
    """Team block height: 8 px padding, 40 px per lane, 8 px padding (RS OUT-9). The divider does not add height."""
    return 2 * TEAM_PAD + LANE_HEIGHT * lanes


def lane_slots(lane_counts: list[int]) -> list[list[LaneSlot]]:
    """Lane positions for consecutive team blocks of one section, in render order."""
    out: list[list[LaneSlot]] = []
    top = 0
    for n in lane_counts:
        out.append([LaneSlot(Decimal(top + TEAM_PAD + LANE_HEIGHT * j)) for j in range(n)])
        top += team_height(n)
    return out


def connector_path(pred: Box, pred_lane: LaneSlot, succ: Box, succ_lane: LaneSlot) -> str:
    """Orthogonal dependency route (RS OUT-28, ADS 6.7):

    M x_end,y_mid(pred) H x_end+8 V y_gap H x_start−8 V y_mid(succ) H x_start

    y_gap is the lane boundary just above the successor's lane when it is lower, just below it when it is higher,
    and the lane's own bottom boundary when both share a lane.
    """
    y_gap = succ_lane.top if succ_lane.top > pred_lane.top else succ_lane.bottom
    x_end = pred.right
    x_start = succ.left
    return (
        f"M{px(x_end)} {px(pred_lane.mid)}H{px(x_end + DEP_STUB)}V{px(y_gap)}"
        f"H{px(x_start - DEP_STUB)}V{px(succ_lane.mid)}H{px(x_start)}"
    )
