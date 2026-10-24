"""Anchor, automatic horizon, visible intervals and flags (RS SC-9, SC-10, SC-12; ADS 6.3)."""

from __future__ import annotations

from datetime import date, timedelta

from rt.diagnostics import Code, Collector
from rt.model.types import ResolvedModel, Settings
from rt.schedule.types import (
    AUTO_START,
    CLIPPED_LEFT,
    CLIPPED_RIGHT,
    CONTINUES,
    DELAYED,
    HIDDEN,
    OVER_CAPACITY,
    Horizon,
    Schedule,
    Visibility,
)
from rt.timeutil import Month, months_between

MIN_MONTHS = 6
MAX_MONTHS = 120
_ONE_DAY = timedelta(days=1)


def anchor(cfg: Settings) -> date:
    """RS SC-12: the explicit horizon start (file or --from), else the 1st of today's month."""
    if cfg.horizon_start is not None:
        return cfg.horizon_start.first_day()
    return Month.of(cfg.today).first_day()


def make_horizon(start: Month, end: Month) -> Horizon:
    h0 = start.first_day()
    h1 = end.next().first_day()
    return Horizon(start=start, end=end, h0=h0, h1=h1, days=(h1 - h0).days)


def resolve_horizon(m: ResolvedModel, s: Schedule, cfg: Settings, diags: Collector) -> Horizon:
    """RS SC-9 for each horizon part not given in the file or on the command line.

    Interpretations beyond the RS: when only the end is explicit and the automatic start falls after it, the start
    is set to the end month; when only the end is explicit and the span exceeds 120 months, the start moves
    forward to 120 months before the end, with W012.
    """
    start = cfg.horizon_start
    if start is None:
        firsts = [Month.of(pl.requested if pl.requested is not None else pl.start) for pl in s.placements]
        start = min(firsts) if firsts else Month.of(cfg.today)
        if cfg.horizon_end is not None and start > cfg.horizon_end:
            start = cfg.horizon_end
    end = cfg.horizon_end
    if end is None:
        lasts = [Month.of(pl.end - _ONE_DAY) if pl.end is not None else Month.of(pl.start) for pl in s.placements]
        end = max(lasts) if lasts else start
        if months_between(start, end) < MIN_MONTHS:
            end = start.add(MIN_MONTHS - 1)
        if months_between(start, end) > MAX_MONTHS:
            end = start.add(MAX_MONTHS - 1)
            diags.warning(Code.W012, cfg.pos, start=str(start), end=str(end))
    elif cfg.horizon_start is None and months_between(start, end) > MAX_MONTHS:
        start = end.add(1 - MAX_MONTHS)
        diags.warning(Code.W012, cfg.pos, start=str(start), end=str(end))
    return make_horizon(start, end)


def visibility(m: ResolvedModel, s: Schedule, h: Horizon) -> dict[int, Visibility]:
    """RS SC-10 visible intervals plus every RS PL-4 flag; warnings are emitted by plan.build."""
    out: dict[int, Visibility] = {}
    for pl in s.placements:
        flags: set[str] = set()
        if pl.delay_days > 0:
            flags.add(DELAYED)
        if pl.requested is None:
            flags.add(AUTO_START)
        if pl.overflow:
            flags.add(OVER_CAPACITY)
        vis_start = max(pl.start, h.h0)
        vis_end = h.h1 if pl.end is None else min(pl.end, h.h1)
        if vis_start >= vis_end:
            flags.add(HIDDEN)
            out[pl.seq] = Visibility(None, None, frozenset(flags))
            continue
        if pl.start < h.h0:
            flags.add(CLIPPED_LEFT)
        if pl.end is None:
            flags.add(CONTINUES)
        elif pl.end > h.h1:
            flags.add(CLIPPED_RIGHT)
        out[pl.seq] = Visibility(vis_start, vis_end, frozenset(flags))
    return out
