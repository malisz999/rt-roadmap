"""Calendar helpers: months, day counts and fixed English date formats (ADS 9.3).

No locale, no time zones, no clock: month names come from the tables below, never from strftime.
"""

from __future__ import annotations

import calendar
import re
from datetime import date
from typing import NamedTuple

MONTH_ABBR: tuple[str, ...] = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


class Month(NamedTuple):
    """A calendar month; ordering and hashing come from the tuple."""

    year: int
    month: int

    @classmethod
    def parse(cls, text: str) -> Month:
        """Parse `YYYY-MM`; raise ValueError for any other text or an impossible month."""
        m = _MONTH_RE.match(text)
        if m is None:
            raise ValueError(f"invalid month {text!r}")
        year, month = int(m.group(1)), int(m.group(2))
        if not 1 <= month <= 12 or year < 1:
            raise ValueError(f"invalid month {text!r}")
        return cls(year, month)

    @classmethod
    def of(cls, d: date) -> Month:
        return cls(d.year, d.month)

    def first_day(self) -> date:
        return date(self.year, self.month, 1)

    def days(self) -> int:
        return calendar.monthrange(self.year, self.month)[1]

    def add(self, n: int) -> Month:
        index = self.year * 12 + (self.month - 1) + n
        return Month(index // 12, index % 12 + 1)

    def next(self) -> Month:
        return self.add(1)

    def ordinal(self) -> int:
        """Months since year 0; differences give month distances."""
        return self.year * 12 + (self.month - 1)

    def label(self) -> str:
        """`Jan 2027`."""
        return f"{MONTH_ABBR[self.month - 1]} {self.year}"

    def abbr(self) -> str:
        """`Jan`."""
        return MONTH_ABBR[self.month - 1]

    def quarter(self) -> int:
        return (self.month - 1) // 3 + 1

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


def parse_date(text: str) -> date:
    """Parse `YYYY-MM-DD`; raise ValueError for any other text or an impossible date."""
    m = _DATE_RE.match(text)
    if m is None:
        raise ValueError(f"invalid date {text!r}")
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def months_between(first: Month, last: Month) -> int:
    """Number of months from `first` to `last`, both inclusive."""
    return last.ordinal() - first.ordinal() + 1


def month_range(first: Month, last: Month) -> list[Month]:
    """Every month from `first` to `last`, inclusive."""
    return [first.add(i) for i in range(months_between(first, last))]


def fmt_date(d: date) -> str:
    """`29 Jan 2027`."""
    return f"{d.day} {MONTH_ABBR[d.month - 1]} {d.year}"


def fmt_day_month(d: date) -> str:
    """`23 Oct`."""
    return f"{d.day} {MONTH_ABBR[d.month - 1]}"
