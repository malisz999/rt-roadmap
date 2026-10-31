"""Orchestrates anchor → schedule → horizon → visibility → colour → load → Plan (ADS 6.1)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal

import rt
from rt.color.adjacency import neighbours
from rt.color.dsatur import assign_colors, product_keys
from rt.color.palette import ColorKey, key_ref
from rt.color.types import ColorRef
from rt.decimalutil import frac4, ratio4
from rt.diagnostics import Code, Collector, Diagnostic
from rt.model.types import ResolvedModel
from rt.plan.types import (
    HorizonOut,
    IndicatorPlan,
    MonthlyLoad,
    Plan,
    PlannedProject,
    PlanWarning,
    ProductPlan,
    SubdomainLoad,
    TeamIndicatorsPlan,
    TeamLoad,
    TeamPlan,
    VisibleOut,
)
from rt.schedule.horizon import anchor, resolve_horizon, visibility
from rt.schedule.indicators import Indicators, IndicatorStats, team_indicators
from rt.schedule.load import LoadRow, LoadTable, Ratio, monthly_load, utilisation
from rt.schedule.scheduler import schedule
from rt.schedule.types import (
    CLIPPED_LEFT,
    CLIPPED_RIGHT,
    HIDDEN,
    REASON_CAPACITY,
    REASON_DEPENDENCY,
    Horizon,
    Schedule,
    Visibility,
)

PLAN_FORMAT = 1
_ONE_DAY = timedelta(days=1)


def compute_plan(model: ResolvedModel, diags: Collector) -> Plan | None:
    """Compute the full plan; return None when scheduling failed (E060/E061 in the collector, exit 3).

    Emits W001–W012 (except W020/W021) into the collector. Plan.warnings holds every warning in the collector
    after the run (validation warnings included), sorted by line, column, code; Plan.diagnostics the same as
    Diagnostic objects."""
    settings = model.settings
    structure_warnings(model, diags)
    sched = schedule(model, settings.on_conflict, anchor(settings), diags)
    if sched is None:
        return None
    horizon = resolve_horizon(model, sched, settings, diags)
    vis = visibility(model, sched, horizon)
    project_warnings(model, sched, vis, diags)
    nb = neighbours(model, sched, vis, settings.adjacency_gap_days)
    pkeys = product_keys(model, diags)
    colors = assign_colors(model, vis, nb, diags, pkeys)
    util = utilisation(model, sched, horizon, vis)
    load = monthly_load(model, sched, horizon)
    return build_plan(model, sched, horizon, vis, nb, colors, util, load, diags, pkeys)


def structure_warnings(m: ResolvedModel, diags: Collector) -> None:
    """W005 (team without projects), W006 (subdomain without teams), W008 (capacity given, 0 people), W010,
    W013 (product without projects)."""
    teams_with_projects = {p.team_id for p in m.projects}
    products_with_projects = {p.product_id for p in m.projects}
    for sd in m.subdomains:
        if not sd.team_ids:
            diags.warning(Code.W006, sd.pos, subdomain=sd.id)
    for team in m.teams:
        if team.id not in teams_with_projects:
            diags.warning(Code.W005, team.pos, team=team.id)
        if team.capacity_given and team.capacity.total == 0:
            diags.warning(Code.W008, team.pos, team=team.id)
    for pr in m.products:
        if pr.id not in products_with_projects:
            diags.warning(Code.W013, pr.pos, product=pr.name)
    if not m.projects:
        diags.warning(Code.W010, m.settings.pos)


def _why(reason: str | None, team: str) -> str:
    if reason == REASON_CAPACITY:
        return f'no free slot in team "{team}"'
    if reason == REASON_DEPENDENCY:
        return "waiting for dependencies"
    return f'waiting for dependencies, then no free slot in team "{team}"'


def project_warnings(m: ResolvedModel, s: Schedule, vis: Mapping[int, Visibility], diags: Collector) -> None:
    """Per project, in the oracle's order: W004, W001, W011, W002, W003."""
    for pl in s.placements:
        p = m.model.project(pl.seq)
        flags = vis[pl.seq].flags
        if HIDDEN in flags:
            diags.warning(Code.W004, p.pos, project=p.name)
        if pl.delay_days > 0 and pl.requested is not None:
            diags.warning(
                Code.W001,
                p.pos,
                project=p.name,
                days=pl.delay_days,
                requested=pl.requested.isoformat(),
                start=pl.start.isoformat(),
                why=_why(pl.delay_reason, pl.team_id),
            )
        if pl.overflow:
            slots = m.model.team(pl.team_id).slots
            diags.warning(Code.W011, p.pos, project=p.name, team=pl.team_id, lane=pl.lane - slots)
        if CLIPPED_LEFT in flags:
            diags.warning(Code.W002, p.pos, project=p.name)
        if CLIPPED_RIGHT in flags:
            diags.warning(Code.W003, p.pos, project=p.name)


def _warning_key(d: Diagnostic) -> tuple[int, int, str]:
    return (d.line or 0, d.col or 0, d.code.name)


def _load_values(row: LoadRow) -> tuple[Decimal, ...]:
    return tuple(ratio4(n, d) for n, d in zip(row.occupied, row.capacity, strict=True))


def build_plan(
    m: ResolvedModel,
    s: Schedule,
    h: Horizon,
    vis: Mapping[int, Visibility],
    nb: Mapping[int, frozenset[int]],
    colors: Mapping[int, ColorRef],
    util: Mapping[str, Ratio],
    load: LoadTable,
    diags: Collector,
    product_colors: Mapping[str, ColorKey] | None = None,
) -> Plan:
    """Assemble the Plan from the computed parts; warnings are taken from the collector as they stand."""
    ind = team_indicators(m.teams, m.model.team_norms)
    teams = tuple(
        TeamPlan(
            id=t.id,
            subdomain=t.subdomain_id,
            slots=t.slots,
            overflow_lanes=max(0, s.lane_count.get(t.id, t.slots) - t.slots),
            utilization=ratio4(util[t.id].numerator, util[t.id].denominator),
            developers=ind.teams[t.id].developers,
            testers=ind.teams[t.id].testers,
            devs_per_slot=frac4(ind.teams[t.id].devs_per_slot),
            devs_per_qa=frac4(ind.teams[t.id].devs_per_qa),
            indicator_flags=ind.teams[t.id].flags,
            utilization_exact=util[t.id].exact,
        )
        for t in m.teams
    )
    projects = tuple(_planned(m, pl.seq, s, vis, nb, colors) for pl in s.placements)
    if product_colors is None:  # callers that skip compute_plan: the same colours, warnings not collected
        product_colors = product_keys(m, Collector(m.model.source))
    products = tuple(_product(m, pr.id, product_colors[pr.id]) for pr in m.products)
    monthly = MonthlyLoad(
        months=load.months,
        teams=tuple(TeamLoad(r.key, _load_values(r), r.occupied, r.capacity) for r in load.teams),
        subdomains=tuple(SubdomainLoad(r.key, _load_values(r), r.occupied, r.capacity) for r in load.subdomains),
        total=_load_values(load.total),
        total_occupied=load.total.occupied,
        total_capacity=load.total.capacity,
    )
    warnings = sorted(diags.warnings, key=_warning_key)
    settings = m.settings
    return Plan(
        rt_version=rt.__version__,
        format=PLAN_FORMAT,
        title=settings.title,
        today=settings.today,
        horizon=HorizonOut(h.start, h.end, h.h0, h.h1, h.days),
        on_conflict=settings.on_conflict,
        teams=teams,
        team_indicators=indicators_plan(ind),
        products=products,
        projects=projects,
        monthly_load=monthly,
        warnings=tuple(PlanWarning(d.code.name, d.line, d.col, d.message) for d in warnings),
        model=m,
        diagnostics=tuple(warnings),
        indicators=ind,
    )


def _indicator(stats: IndicatorStats) -> IndicatorPlan:
    return IndicatorPlan(frac4(stats.all), frac4(stats.median), frac4(stats.low), frac4(stats.high), stats.source)


def indicators_plan(ind: Indicators) -> TeamIndicatorsPlan:
    """Roadmap-wide indicator values for the plan JSON (RS PL-8)."""
    return TeamIndicatorsPlan(_indicator(ind.devs_per_slot), _indicator(ind.devs_per_qa))


def _product(m: ResolvedModel, product_id: str, key: ColorKey) -> ProductPlan:
    pr = m.model.product(product_id)
    color = key_ref(key)
    return ProductPlan(
        id=pr.id,
        name=pr.name,
        domain=pr.domain_id,
        owner=pr.owner,
        color_index=color.index,
        color_name=color.name,
        color_fill=color.fill,
        projects=tuple(p.seq for p in m.projects if p.product_id == product_id),
        color=color,
    )


def _planned(
    m: ResolvedModel,
    seq: int,
    s: Schedule,
    vis: Mapping[int, Visibility],
    nb: Mapping[int, frozenset[int]],
    colors: Mapping[int, ColorRef],
) -> PlannedProject:
    p = m.model.project(seq)
    pl = s.placement(seq)
    v = vis[seq]
    color = colors.get(seq)
    return PlannedProject(
        seq=seq,
        id=p.id,
        name=p.name or "",
        team=pl.team_id,
        product=p.product_id,
        size=None if p.ongoing else p.size,
        weeks=None if p.ongoing else m.weeks.get(seq),
        ongoing=p.ongoing,
        requested_start=pl.requested,
        depends_on=tuple(sorted(m.deps.get(seq, ()))),
        earliest_start=pl.earliest,
        start=pl.start,
        end=pl.end,
        last_day=None if pl.end is None else pl.end - _ONE_DAY,
        lane=pl.lane,
        overflow=pl.overflow,
        delay_days=pl.delay_days,
        delay_reason=pl.delay_reason,
        visible=None if v.start is None or v.end is None else VisibleOut(v.start, v.end),
        color_index=None if color is None else color.index,
        color_name=None if color is None else color.name,
        color_fill=None if color is None else color.fill,
        flags=tuple(sorted(v.flags)),
        neighbors=tuple(sorted(nb.get(seq, frozenset()))),
        color=color,
    )
