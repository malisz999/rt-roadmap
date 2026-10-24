"""Team utilisation (RS OUT-13) and monthly load (RS OUT-32); exact integer numerators and denominators."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from fractions import Fraction

from rt.model.types import ResolvedModel
from rt.schedule.types import Horizon, Schedule, Visibility
from rt.timeutil import Month, month_range


@dataclass(frozen=True, slots=True)
class Ratio:
    numerator: int
    denominator: int

    @property
    def exact(self) -> Fraction:
        return Fraction(0) if self.denominator == 0 else Fraction(self.numerator, self.denominator)


@dataclass(frozen=True, slots=True)
class LoadRow:
    key: str  # team or subdomain id; "" for the total row
    occupied: tuple[int, ...]  # slot-days per month
    capacity: tuple[int, ...]  # slots × days per month


@dataclass(frozen=True, slots=True)
class LoadTable:
    months: tuple[Month, ...]
    teams: tuple[LoadRow, ...]
    subdomains: tuple[LoadRow, ...]
    total: LoadRow


def utilisation(m: ResolvedModel, s: Schedule, h: Horizon, vis: dict[int, Visibility]) -> dict[str, Ratio]:
    """Visible days of bars in regular slots ÷ (slots × horizon days), per team; overflow lanes excluded."""
    used = {t.id: 0 for t in m.teams}
    for pl in s.placements:
        v = vis[pl.seq]
        if pl.overflow or v.start is None or v.end is None:
            continue
        used[pl.team_id] += (v.end - v.start).days
    return {t.id: Ratio(used[t.id], t.slots * h.days) for t in m.teams}


def _overlap(start: date, end: date | None, lo: date, hi: date) -> int:
    top = hi if end is None else min(end, hi)
    return max(0, (top - max(start, lo)).days)


def monthly_load(m: ResolvedModel, s: Schedule, h: Horizon) -> LoadTable:
    """Occupied slot-days per horizon month (any lane, ongoing included) over slots × days in the month."""
    months = tuple(month_range(h.start, h.end))
    bounds = [(mo.first_day(), mo.next().first_day()) for mo in months]
    by_team: dict[str, list[int]] = {t.id: [0] * len(months) for t in m.teams}
    for pl in s.placements:
        row = by_team[pl.team_id]
        for i, (lo, hi) in enumerate(bounds):
            row[i] += _overlap(pl.start, pl.end, lo, hi)
    team_rows: dict[str, LoadRow] = {}
    for t in m.teams:
        team_rows[t.id] = LoadRow(t.id, tuple(by_team[t.id]), tuple(t.slots * mo.days() for mo in months))

    def combine(key: str, rows: list[LoadRow]) -> LoadRow:
        occupied = tuple(sum(r.occupied[i] for r in rows) for i in range(len(months)))
        capacity = tuple(sum(r.capacity[i] for r in rows) for i in range(len(months)))
        return LoadRow(key, occupied, capacity)

    sub_rows = tuple(
        combine(sd.id, [team_rows[t.id] for t in m.teams if t.subdomain_id == sd.id]) for sd in m.subdomains
    )
    total = combine("", list(team_rows.values()))
    return LoadTable(months, tuple(team_rows.values()), sub_rows, total)
