"""Plan → PageVM: all formatting and pixel maths (ADS 5.3, 6.7).

The view model holds display-ready values only: formatted strings, pixel values already rounded (`"110.39"`),
CSS classes and `data-*` attribute pairs. Templates loop and branch; they never compute.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

from rt.decimalutil import fmt1, fmt4, frac4, half_up, pct, px
from rt.layout import geometry as g
from rt.model.types import Capacity, Mode, Subdomain, Team
from rt.plan.types import Plan, PlannedProject, ProductPlan, TeamPlan
from rt.schedule import indicators as ti
from rt.schedule.types import (
    CLIPPED_LEFT,
    CLIPPED_RIGHT,
    DELAYED,
    OVER_CAPACITY,
    REASON_BOTH,
    REASON_CAPACITY,
    REASON_DEPENDENCY,
)
from rt.timeutil import Month, fmt_date, fmt_day_month

__all__ = [
    "BadgeVM",
    "BarVM",
    "CompositionRowVM",
    "CompositionVM",
    "DepVM",
    "IndicatorVM",
    "KpiVM",
    "LaneVM",
    "LeadVM",
    "LegendProductVM",
    "LegendVM",
    "LoadCellVM",
    "LoadRowVM",
    "MarkVM",
    "PageVM",
    "SectionVM",
    "SpanVM",
    "SummaryVM",
    "TeamVM",
    "TipRow",
    "TodayVM",
    "WarningVM",
    "build_page",
]

PILL_MIN_WIDTH = Decimal(80)  # narrower bars keep their name and drop the delay pill (the lead line remains)
LOCK_ROOM = 24  # px: padlock (11) plus gap, added to the text threshold of a locked bar
TIP_WIDTH = Decimal(330)  # styled tooltip max width plus margin: anchor it right when it would leave the timeline
TODAY_LABEL_HALF = Decimal(56)  # half the width of the "Today · 23 Oct" pill, for edge alignment

_REASON_TEXT: Mapping[str, str] = {
    REASON_DEPENDENCY: "waiting for dependencies",
    REASON_CAPACITY: "no free slot",
    REASON_BOTH: "waiting for dependencies, then no free slot",
}

_FALLBACK_FILL = "#E2E8F0"
_FALLBACK_ACCENT = "#64748B"
_INK = "#1E293B"


# --------------------------------------------------------------------------------------------- view model types


@dataclass(frozen=True, slots=True)
class TipRow:
    key: str
    value: str


@dataclass(frozen=True, slots=True)
class LeadVM:
    """Dashed lead line from the requested start to a delayed bar (RS OUT-20), a sibling of the bar in its lane."""

    left: str
    width: str
    cut: bool  # starts at the horizon's left edge: no circle


@dataclass(frozen=True, slots=True)
class BarVM:
    seq: int
    classes: str
    left: str
    width: str
    fill: str
    accent: str
    ink: str
    name: str
    show_name: bool
    chip: str | None
    delay: str | None  # pill text `+4w`
    clip_left: bool  # `‹` from .rt-bar--clip-l::before
    clip_right: bool  # `›` from .rt-bar--clip-r::after
    ongoing: bool  # `∞` and the fade from .rt-bar--ongoing::after
    dep_ext: bool  # a dependency not drawn as a connector: `↤` from .rt-bar--dep-ext::before
    title: str  # native tooltip and the styled .rt-tip text, one fact per line
    aria: str
    data: tuple[tuple[str, str], ...]  # RS 7.10, in contract order
    lead: LeadVM | None
    locked: bool = False  # padlock and frame (RS OUT-35)
    risk: str | None = None  # `! at risk` pill text, on bars wide enough for the size chip (RS OUT-36)


@dataclass(frozen=True, slots=True)
class LaneVM:
    team: str
    number: int
    label: str  # `1`, `+1`
    overflow: bool
    even: bool
    bars: tuple[BarVM, ...]


@dataclass(frozen=True, slots=True)
class BadgeVM:
    role: str  # DEV, PM, BA, QA
    count: int
    zero: bool
    title: str  # `Developers`


@dataclass(frozen=True, slots=True)
class IndicatorVM:
    """One team indicator chip (RS 7.13): `2.5 DEV/slot`; high and no QA are bad (red), low is good (green)."""

    kind: str  # devs_per_slot | devs_per_qa
    text: str
    mark: str  # low | high | no_qa | ""
    glyph: str  # ▲ ▼ ! or ""
    title: str
    tone: str = ""  # bad | good | "" (for both indicators, higher is worse)


@dataclass(frozen=True, slots=True)
class TeamVM:
    id: str
    name: str
    slots: int
    badges: tuple[BadgeVM, ...]
    people: str  # `9 people`
    slots_label: str  # `2 parallel slots`
    utilization: str  # `0.7624`
    util_text: str  # `76 %`
    util_width: str  # `76.24` (percent of the meter)
    util_title: str
    height: str
    compact: bool  # one regular slot: the label sits at the top with tight spacing to fit 56 px
    lanes: tuple[LaneVM, ...]
    indicators: tuple[IndicatorVM, ...] = ()  # compact teams: short texts, shown on the people line
    data: tuple[tuple[str, str], ...] = ()  # indicator hooks (RS 7.10)


@dataclass(frozen=True, slots=True)
class DepVM:
    from_seq: int
    to_seq: int
    d: str


@dataclass(frozen=True, slots=True)
class SectionVM:
    id: str
    name: str
    description: str | None
    counts: str  # `3 teams · 14 projects`
    height: str
    teams: tuple[TeamVM, ...]
    deps: tuple[DepVM, ...]
    marker_id: str


@dataclass(frozen=True, slots=True)
class SpanVM:
    key: str
    label: str
    left: str
    width: str
    edge: str  # boundary style at the span's left edge: "", "month", "quarter" or "year"
    title: str


@dataclass(frozen=True, slots=True)
class MarkVM:
    kind: str  # year | quarter | month
    classes: str  # quarter boundaries also carry the `rt-quarter-line` hook (RS 7.10)
    date: str
    left: str


@dataclass(frozen=True, slots=True)
class TodayVM:
    date: str
    left: str
    label: str  # `Today · 23 Oct`
    align: str  # start | center | end


@dataclass(frozen=True, slots=True)
class LegendSizeVM:
    label: str
    weeks: str  # `2w`


@dataclass(frozen=True, slots=True)
class LegendProductVM:
    """One product chip (RS 7.2 item 2): colour, name, owning domain and owner."""

    id: str
    name: str
    details: str  # ` · Kanały płatności · Anna Kowalska`
    color_index: str  # empty for a custom hex colour
    fill: str
    accent: str
    ink: str
    title: str


@dataclass(frozen=True, slots=True)
class LegendVM:
    sizes: tuple[LegendSizeVM, ...]
    products: tuple[LegendProductVM, ...] = ()
    locks: bool = False  # the file has locked projects: show the two lock symbols (CR-3)


@dataclass(frozen=True, slots=True)
class KpiVM:
    label: str
    value: str
    note: str | None


@dataclass(frozen=True, slots=True)
class LoadCellVM:
    text: str  # `95 %` or `–`
    bin: int  # 0…4 (RS OUT-33)
    title: str
    row: str
    kind: str
    month: str
    load: str


@dataclass(frozen=True, slots=True)
class LoadRowVM:
    kind: str  # subdomain | team | all
    name: str
    user_text: bool  # the name comes from the input (carries `lang`)
    cells: tuple[LoadCellVM, ...]


@dataclass(frozen=True, slots=True)
class MonthHeadVM:
    label: str  # `Feb`
    year: str | None  # shown on the first month and on Januaries


@dataclass(frozen=True, slots=True)
class CompositionRowVM:
    kind: str  # subdomain | team | all | median | band
    name: str
    user_text: bool
    team: str  # team id for team rows, else ""
    developers: str
    testers: str
    slots: str
    cells: tuple[IndicatorVM, ...]  # DEV per slot, DEV per QA
    notes: str


@dataclass(frozen=True, slots=True)
class CompositionVM:
    """The "Team composition" table of the summary (RS 7.13)."""

    rows: tuple[CompositionRowVM, ...]


@dataclass(frozen=True, slots=True)
class CommitmentVM:
    """One row of the "Commitments" table: a locked project and whether its promise holds (RS OUT-37)."""

    seq: int
    name: str
    team: str
    product: str
    promised_to: str
    start: str
    last_day: str
    status: str  # on_track | at_risk
    status_text: str  # `On track`, `At risk`
    reason: str  # why at risk, else ""


@dataclass(frozen=True, slots=True)
class SummaryVM:
    kpis: tuple[KpiVM, ...]
    months: tuple[MonthHeadVM, ...]
    rows: tuple[LoadRowVM, ...]
    composition: CompositionVM | None = None
    commitments: tuple[CommitmentVM, ...] = ()  # locked projects, file order (RS OUT-37)


@dataclass(frozen=True, slots=True)
class WarningVM:
    code: str
    location: str  # `line 38:5` or empty
    message: str


@dataclass(frozen=True, slots=True)
class PageVM:
    title: str
    subtitle: str | None
    lang: str | None  # content_language, written on every element holding user text (RS OUT-27)
    horizon_label: str  # `Jan 2027 – Dec 2027`
    horizon_months: str  # `12 months`
    as_of: str  # `As of 23 Oct 2026`
    mode_label: str  # `Conflicts: delay`
    legend: LegendVM
    summary: SummaryVM | None
    years: tuple[SpanVM, ...]
    quarters: tuple[SpanVM, ...]
    months: tuple[SpanVM, ...]
    marks: tuple[MarkVM, ...]
    today: TodayVM | None
    timeline_width: str
    sections: tuple[SectionVM, ...]
    warnings: tuple[WarningVM, ...]
    warnings_label: str  # `4 warnings`
    version: str
    css_vars: str  # generated `:root` custom properties (numbers only)


# --------------------------------------------------------------------------------------------- small formatters


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def delay_label(days: int) -> str:
    """RS OUT-20: `+Nd` under 14 days, else `+Nw` with N = days ÷ 7 rounded half up."""
    if days < 14:
        return f"+{days}d"
    return f"+{half_up(Fraction(days, 7))}w"


def load_bin(percent: int) -> int:
    """RS OUT-33 bins by displayed percentage: 0, 1–49, 50–79, 80–100, > 100."""
    if percent <= 0:
        return 0
    if percent < 50:
        return 1
    if percent < 80:
        return 2
    if percent <= 100:
        return 3
    return 4


def _ratio(exact: Fraction | None, rounded: Decimal) -> Fraction | Decimal:
    return exact if exact is not None else rounded


# --------------------------------------------------------------------------------------------- page


def build_page(plan: Plan, *, summary: bool, version: str) -> PageVM:
    settings = plan.model.settings
    scale = g.Scale(plan.horizon.start, plan.horizon.end, settings.month_width)
    lang = settings.content_language or None
    sections = _sections(plan, scale)
    warnings = tuple(
        WarningVM(w.code, "" if w.line is None else f"line {w.line}:{w.column or 1}", w.message) for w in plan.warnings
    )
    n_months = len(scale.months)
    return PageVM(
        title=settings.title,
        subtitle=settings.subtitle or None,
        lang=lang,
        horizon_label=f"{plan.horizon.start.label()} – {plan.horizon.end.label()}",
        horizon_months=plural(n_months, "month", "months"),
        as_of=f"As of {fmt_date(plan.today)}",
        mode_label=f"Conflicts: {Mode(plan.on_conflict).value}",
        legend=LegendVM(
            tuple(LegendSizeVM(s.label, f"{s.weeks}w") for s in plan.model.model.sizes),
            _legend_products(plan),
            any(p.locked for p in plan.projects),
        ),
        summary=_summary(plan, scale) if summary else None,
        years=_spans(g.year_spans(scale), scale, lambda s: s.label),
        quarters=_spans(g.quarter_spans(scale), scale, lambda s: f"{s.label} {s.first.year}"),
        months=_spans(g.month_spans(scale), scale, lambda s: s.first.label()),
        marks=tuple(_mark(m) for m in g.boundary_marks(scale)),
        today=_today(plan.today, scale),
        timeline_width=px(scale.width),
        sections=sections,
        warnings=warnings,
        warnings_label=plural(len(warnings), "warning", "warnings"),
        version=version,
        css_vars=(f":root{{--tw:{px(scale.width)}px;--mw:{settings.month_width}px;--label:{g.LABEL_WIDTH}px}}"),
    )


def _owned_by(plan: Plan, pr: ProductPlan) -> tuple[str, str | None]:
    """The owning domain's name and the product owner."""
    names = {s.id: s.name for s in plan.model.subdomains}
    return names.get(pr.domain, pr.domain), pr.owner


def _legend_products(plan: Plan) -> tuple[LegendProductVM, ...]:
    out: list[LegendProductVM] = []
    for pr in plan.products:
        domain, owner = _owned_by(plan, pr)
        details = " · ".join(x for x in (domain, owner) if x)
        description = plan.model.model.product(pr.id).description
        title = f"Product {pr.name}, owned by {domain}" + (f" ({owner})" if owner else "")
        out.append(
            LegendProductVM(
                id=pr.id,
                name=pr.name,
                details=f" · {details}",
                color_index="" if pr.color_index is None else str(pr.color_index),
                fill=pr.color.fill,
                accent=pr.color.accent,
                ink=pr.color.text,
                title=f"{title}: {description}" if description else title,
            )
        )
    return tuple(out)


def _spans(spans: Sequence[g.Span], scale: g.Scale, title: Callable[[g.Span], str]) -> tuple[SpanVM, ...]:
    kinds = {m.day: m.kind for m in g.boundary_marks(scale)}
    return tuple(
        SpanVM(s.key, s.label, px(s.box.left), px(s.box.width), kinds.get(s.first.first_day(), ""), title(s))
        for s in spans
    )


def _mark(m: g.Mark) -> MarkVM:
    classes = f"rt-mark rt-mark--{m.kind}"
    if m.kind == g.QUARTER:
        classes += " rt-quarter-line"
    return MarkVM(m.kind, classes, m.day.isoformat(), px(m.x))


def _today(today: date, scale: g.Scale) -> TodayVM | None:
    """RS OUT-24: only when today lies inside the horizon."""
    if not scale.contains(today):
        return None
    x = scale.x(today)
    if x < TODAY_LABEL_HALF:
        align = "start"
    elif x > scale.width - TODAY_LABEL_HALF:
        align = "end"
    else:
        align = "center"
    return TodayVM(today.isoformat(), px(x), f"Today · {fmt_day_month(today)}", align)


# --------------------------------------------------------------------------------------------- sections


def _sections(plan: Plan, scale: g.Scale) -> tuple[SectionVM, ...]:
    model = plan.model
    teams_by_id = {t.id: t for t in model.teams}
    subdomain_of = {t.id: t.subdomain_id for t in model.teams}
    subdomain_names = {s.id: s.name for s in model.subdomains}
    team_plans = {t.id: t for t in plan.teams}
    by_seq = {p.seq: p for p in plan.projects}
    drawn = {p.seq for p in plan.projects if p.visible is not None}
    out: list[SectionVM] = []
    for sub in model.subdomains:
        out.append(_section(plan, sub, scale, teams_by_id, team_plans, by_seq, drawn, subdomain_of, subdomain_names))
    return tuple(out)


def _section(
    plan: Plan,
    sub: Subdomain,
    scale: g.Scale,
    teams_by_id: Mapping[str, Team],
    team_plans: Mapping[str, TeamPlan],
    by_seq: Mapping[int, PlannedProject],
    drawn: set[int],
    subdomain_of: Mapping[str, str],
    subdomain_names: Mapping[str, str],
) -> SectionVM:
    teams = [teams_by_id[tid] for tid in sub.team_ids if tid in teams_by_id]
    lane_counts = [_lane_count(t, team_plans.get(t.id)) for t in teams]
    slots = g.lane_slots(lane_counts)
    lane_pos = {(t.id, j + 1): slots[i][j] for i, t in enumerate(teams) for j in range(lane_counts[i])}
    members = set(sub.team_ids)
    projects = [p for p in plan.projects if p.team in members]

    boxes: dict[int, g.Box] = {}
    for p in projects:
        if p.visible is not None:
            boxes[p.seq] = g.bar_box(scale, p.visible.start, p.visible.end)

    deps: list[DepVM] = []
    external: set[int] = set()
    for p in projects:
        if p.seq not in boxes:
            continue
        for d in p.depends_on:
            if d in boxes and (by_seq[d].team, by_seq[d].lane) in lane_pos:
                pred = by_seq[d]
                path = g.connector_path(
                    boxes[d], lane_pos[(pred.team, pred.lane)], boxes[p.seq], lane_pos[(p.team, p.lane)]
                )
                deps.append(DepVM(d, p.seq, path))
            else:
                external.add(p.seq)
    deps.sort(key=lambda v: (v.to_seq, v.from_seq))

    team_vms: list[TeamVM] = []
    for i, t in enumerate(teams):
        lanes: list[LaneVM] = []
        for j in range(lane_counts[i]):
            lane_no = j + 1
            lane_projects = sorted(
                (p for p in projects if p.team == t.id and p.lane == lane_no and p.seq in boxes),
                key=lambda p: (p.visible.start if p.visible else date.min, p.seq),
            )
            bars = tuple(
                _bar(plan, p, boxes[p.seq], scale, t, p.seq in external, by_seq, teams_by_id, subdomain_names)
                for p in lane_projects
            )
            overflow = lane_no > t.slots
            lanes.append(
                LaneVM(
                    team=t.id,
                    number=lane_no,
                    label=f"+{lane_no - t.slots}" if overflow else str(lane_no),
                    overflow=overflow,
                    even=lane_no % 2 == 0,
                    bars=bars,
                )
            )
        team_vms.append(_team(t, team_plans.get(t.id), lanes, indicators_of(plan)))

    n_projects = len(projects)
    return SectionVM(
        id=sub.id,
        name=sub.name,
        description=sub.description or None,
        counts=f"{plural(len(teams), 'team', 'teams')} · {plural(n_projects, 'project', 'projects')}",
        height=str(sum(g.team_height(n) for n in lane_counts)),
        teams=tuple(team_vms),
        deps=tuple(deps),
        marker_id=f"rt-arrow-{sub.id}",
    )


def _lane_count(team: Team, tp: TeamPlan | None) -> int:
    if tp is None:
        return team.slots
    return tp.slots + tp.overflow_lanes


_ROLES: tuple[tuple[str, str], ...] = (
    ("DEV", "Developers"),
    ("PM", "Product managers"),
    ("BA", "Analysts"),
    ("QA", "Testers"),
)


def _role_counts(c: Capacity) -> tuple[int, int, int, int]:
    return (c.developers, c.product_managers, c.analysts, c.testers)


def _team(t: Team, tp: TeamPlan | None, lanes: list[LaneVM], ind: ti.Indicators | None = None) -> TeamVM:
    counts = _role_counts(t.capacity)
    badges = tuple(BadgeVM(role, n, n == 0, title) for (role, title), n in zip(_ROLES, counts, strict=True))
    if tp is not None:
        exact: Fraction | Decimal = tp.utilization_exact if tp.utilization_exact else tp.utilization
        utilization = fmt4(tp.utilization)
        percent = pct(exact)
        width = px(min(tp.utilization, Decimal(1)) * 100)
    else:  # pragma: no cover - every team has a TeamPlan
        utilization, percent, width = "0.0000", 0, "0.00"
    return TeamVM(
        id=t.id,
        name=t.name,
        slots=t.slots,
        badges=badges,
        people=plural(t.capacity.total, "person", "people"),
        slots_label=plural(t.slots, "parallel slot", "parallel slots"),
        utilization=utilization,
        util_text=f"{percent} %",
        util_width=width,
        util_title=f"Slot utilisation over the horizon: {percent} %",
        height=str(g.team_height(len(lanes))),
        compact=t.slots == 1,
        lanes=tuple(lanes),
        indicators=_chips(ind, t.id, short=t.slots == 1) if ind is not None else (),
        data=_indicator_data(ind.teams[t.id]) if ind is not None and t.id in ind.teams else (),
    )


# --------------------------------------------------------------------------------------------- team indicators

_IND_NAME: Mapping[str, str] = {ti.DEVS_PER_SLOT: "DEV per slot", ti.DEVS_PER_QA: "DEV per QA"}
_IND_UNIT: Mapping[str, str] = {ti.DEVS_PER_SLOT: "DEV/slot", ti.DEVS_PER_QA: "DEV/QA"}
_IND_SHORT: Mapping[str, str] = {ti.DEVS_PER_SLOT: "/slot", ti.DEVS_PER_QA: "/QA"}
_GLYPH: Mapping[str, str] = {ti.LOW: "▼", ti.HIGH: "▲", ti.NO_QA: "!"}
_TONE: Mapping[str, str] = {ti.LOW: "good", ti.HIGH: "bad", ti.NO_QA: "bad"}
_TONE_WORD: Mapping[str, str] = {ti.LOW: "low (better)", ti.HIGH: "high (worse)"}
_FLAG_NOTE: Mapping[str, str] = {
    "devs_per_slot_high": "DEV per slot high (worse)",
    "devs_per_slot_low": "DEV per slot low (better)",
    "devs_per_qa_high": "DEV per QA high (worse)",
    "devs_per_qa_low": "DEV per QA low (better)",
    ti.NO_QA: "no QA",
    ti.NO_CAPACITY: "no capacity given",
}


def indicators_of(plan: Plan) -> ti.Indicators:
    """The plan's exact indicators; computed from the model for plans assembled without them."""
    if plan.indicators is not None:
        return plan.indicators
    return ti.team_indicators(plan.model.teams, plan.model.model.team_norms)


def _range(stats: ti.IndicatorStats) -> str:
    """The band in words: `median 2.0, normal 1.3–2.7`, `norm 2.0–2.5`, `norm ≤ 3.0`."""
    if stats.source == ti.SOURCE_NORM:
        if stats.low is not None and stats.high is not None:
            return f"norm {fmt1(stats.low)}–{fmt1(stats.high)}"
        if stats.low is not None:
            return f"norm ≥ {fmt1(stats.low)}"
        return f"norm ≤ {fmt1(stats.high)}" if stats.high is not None else "no norm bounds"
    if (
        stats.source == ti.SOURCE_MEDIAN
        and stats.median is not None
        and stats.low is not None
        and stats.high is not None
    ):
        return f"median {fmt1(stats.median)}, normal {fmt1(stats.low)}–{fmt1(stats.high)}"
    return "fewer than 3 teams to compare" if stats.median is not None else "no team to compare"


def _why(mark: str, stats: ti.IndicatorStats) -> str:
    """`high (worse): above 3.0 (median 2.0 + 50 %)` or `low (better): below the norm 2.0`."""
    if mark == ti.HIGH:
        limit, side, sign = stats.high, "above", "+"
    else:
        limit, side, sign = stats.low, "below", "−"
    assert limit is not None
    word = _TONE_WORD[mark]
    if stats.source == ti.SOURCE_NORM:
        return f"{word}: {side} the norm {fmt1(limit)}"
    assert stats.median is not None
    return f"{word}: {side} {fmt1(limit)} (median {fmt1(stats.median)} {sign} 50 %)"


def _chip(ind: ti.Indicators, team: ti.TeamIndicators, kind: str, short: bool, unit: bool = True) -> IndicatorVM:
    name = _IND_NAME[kind]
    suffix = (_IND_SHORT[kind] if short else f" {_IND_UNIT[kind]}") if unit else ""
    value = team.value(kind)
    if team.developers is None:
        return IndicatorVM(kind, f"–{suffix}", "", "", f"{name}: no capacity given for this team")
    if kind == ti.DEVS_PER_QA and value is None:
        title = f"No QA: {plural(team.developers, 'developer', 'developers')} and no testers"
        mark = ti.NO_QA if ti.NO_QA in team.flags else ""
        return IndicatorVM(kind, "no QA", mark, _GLYPH.get(mark, ""), title, _TONE.get(mark, ""))
    assert value is not None
    stats = ind.stats(kind)
    mark = team.marks.get(kind, "")
    shown = fmt1(value)
    detail = _why(mark, stats) if mark else _range(stats)
    title = f"{name} {shown} — {detail}" if mark else f"{name} {shown} ({detail})"
    return IndicatorVM(kind, f"{shown}{suffix}", mark, _GLYPH.get(mark, ""), title, _TONE.get(mark, ""))


def _chips(ind: ti.Indicators, team_id: str, short: bool) -> tuple[IndicatorVM, ...]:
    team = ind.teams.get(team_id)
    if team is None:  # pragma: no cover - every team has indicators
        return ()
    return tuple(_chip(ind, team, kind, short) for kind in ti.INDICATORS)


def _indicator_data(team: ti.TeamIndicators) -> tuple[tuple[str, str], ...]:
    def f4(v: Fraction | None) -> str:
        rounded = frac4(v)
        return "" if rounded is None else fmt4(rounded)

    return (
        ("data-devs-per-slot", f4(team.devs_per_slot)),
        ("data-devs-per-qa", f4(team.devs_per_qa)),
        ("data-indicator-flags", " ".join(team.flags)),
    )


def _composition(plan: Plan) -> CompositionVM:
    model = plan.model
    ind = indicators_of(plan)
    teams_by_id = {t.id: t for t in model.teams}
    rows: list[CompositionRowVM] = []
    for sub in model.subdomains:
        rows.append(CompositionRowVM("subdomain", sub.name, True, "", "", "", "", (), ""))
        for tid in sub.team_ids:
            t, team = teams_by_id.get(tid), ind.teams.get(tid)
            if t is None or team is None:
                continue
            cells = tuple(_chip(ind, team, kind, short=False, unit=False) for kind in ti.INDICATORS)
            notes = ", ".join(_FLAG_NOTE[f] for f in sorted(team.flags, key=list(_FLAG_NOTE).index))
            rows.append(
                CompositionRowVM(
                    "team",
                    t.name,
                    True,
                    t.id,
                    "–" if team.developers is None else str(team.developers),
                    "–" if team.testers is None else str(team.testers),
                    str(t.slots),
                    cells,
                    notes,
                )
            )
    measured = [t for t in model.teams if t.capacity_given]
    dev = sum(t.capacity.developers for t in measured)
    qa = sum(t.capacity.testers for t in measured)
    slots = sum(t.slots for t in measured)

    def plain(kind: str, value: Fraction | None, title: str) -> IndicatorVM:
        return IndicatorVM(kind, "–" if value is None else fmt1(value), "", "", title)

    stats = [ind.stats(kind) for kind in ti.INDICATORS]
    rows.append(
        CompositionRowVM(
            "all",
            "All teams",
            False,
            "",
            str(dev) if measured else "–",
            str(qa) if measured else "–",
            str(slots) if measured else "–",
            tuple(plain(k, s.all, f"{_IND_NAME[k]} over all teams") for k, s in zip(ti.INDICATORS, stats, strict=True)),
            "teams without capacity are left out" if len(measured) < len(model.teams) else "",
        )
    )
    rows.append(
        CompositionRowVM(
            "median",
            "Median",
            False,
            "",
            "",
            "",
            "",
            tuple(plain(k, s.median, f"Median {_IND_NAME[k]}") for k, s in zip(ti.INDICATORS, stats, strict=True)),
            "",
        )
    )
    if any(s.source is not None for s in stats):
        norm = any(s.source == ti.SOURCE_NORM for s in stats)
        band_cells = []
        for k, st in zip(ti.INDICATORS, stats, strict=True):
            if st.source is None:
                text = "–"
            elif st.low is not None and st.high is not None:
                text = f"{fmt1(st.low)}–{fmt1(st.high)}"
            elif st.low is not None:
                text = f"≥ {fmt1(st.low)}"
            elif st.high is not None:
                text = f"≤ {fmt1(st.high)}"
            else:
                text = "–"
            band_cells.append(IndicatorVM(k, text, "", "", f"{_IND_NAME[k]}: {_range(st)}"))
        rows.append(
            CompositionRowVM(
                "band",
                "Norm" if norm else "Normal range",
                False,
                "",
                "",
                "",
                "",
                tuple(band_cells),
                "team_norms" if norm else "median ± 50 %",
            )
        )
    return CompositionVM(tuple(rows))


# --------------------------------------------------------------------------------------------- bars


def _bar(
    plan: Plan,
    p: PlannedProject,
    box: g.Box,
    scale: g.Scale,
    team: Team,
    dep_ext: bool,
    by_seq: Mapping[int, PlannedProject],
    teams_by_id: Mapping[str, Team],
    subdomain_names: Mapping[str, str],
) -> BarVM:
    flags = set(p.flags)
    ongoing = p.ongoing
    at_risk = p.lock_risk is not None
    delayed = DELAYED in flags
    clip_l = CLIPPED_LEFT in flags
    clip_r = CLIPPED_RIGHT in flags
    width = box.width  # label rules use the unrounded width (ADS 6.7)
    # A locked bar also needs room for its padlock: below 72 px it shows the padlock only (RS OUT-35).
    tiny = width < g.TEXT_MIN_WIDTH + (LOCK_ROOM if p.locked else 0)
    narrow = not tiny and width < g.CHIP_MIN_WIDTH

    if p.color is not None:
        fill, accent, ink = p.color.fill, p.color.accent, p.color.text
    else:
        fill, accent, ink = p.color_fill or _FALLBACK_FILL, _FALLBACK_ACCENT, _INK

    # ADS 7.2 state modifiers; glyphs (‹ › ∞ ↤) come from their ::before / ::after rules.
    classes = ["rt-bar"]
    for on, modifier in (
        (ongoing, "ongoing"),
        (delayed, "delayed"),
        (clip_l, "clip-l"),
        (clip_r, "clip-r"),
        (OVER_CAPACITY in flags and not at_risk, "over"),
        (p.locked, "locked"),
        (at_risk, "risk"),
        (dep_ext, "dep-ext"),
        (narrow, "narrow"),
        (tiny, "tiny"),
        (box.left + TIP_WIDTH > scale.width, "tip-end"),
    ):
        if on:
            classes.append(f"rt-bar--{modifier}")

    chip = None
    if not tiny and not narrow and not ongoing and p.size is not None:
        chip = f"{p.size} · {p.weeks}w"
    risk = None
    if at_risk and not tiny and not narrow:  # the pill takes the size chip's place (RS OUT-36)
        risk, chip = "! at risk", None
    delay = delay_label(p.delay_days) if delayed and width >= PILL_MIN_WIDTH else None

    lead = None
    if delayed and p.requested_start is not None:
        hit = g.lead_box(scale, p.requested_start, box)
        if hit is not None:
            lbox, cut = hit
            lead = LeadVM(px(lbox.left), px(lbox.width), cut)

    description = plan.model.projects[p.seq - 1].description or None
    rows = _facts(plan, p, team, by_seq, teams_by_id, subdomain_names)
    lines = [p.name] + [f"{r.key}: {r.value}" for r in rows]
    if description:
        lines.append(description)

    data = (
        ("data-seq", str(p.seq)),
        ("data-team", p.team),
        ("data-product", p.product or ""),
        ("data-lane", str(p.lane)),
        ("data-requested", p.requested_start.isoformat() if p.requested_start else "auto"),
        ("data-start", p.start.isoformat()),
        ("data-end", p.end.isoformat() if p.end is not None else "ongoing"),
        ("data-delay-days", str(p.delay_days)),
        ("data-delay-reason", p.delay_reason or ""),
        ("data-lock-risk", p.lock_risk or ""),
        ("data-depends-on", " ".join(str(d) for d in p.depends_on)),
        ("data-color-index", "" if p.color_index is None else str(p.color_index)),
        ("data-flags", " ".join(sorted(p.flags))),
    )
    return BarVM(
        seq=p.seq,
        classes=" ".join(classes),
        left=px(box.left),
        width=px(box.width),
        fill=fill,
        accent=accent,
        ink=ink,
        name=p.name,
        show_name=not tiny,
        chip=chip,
        delay=delay,
        clip_left=clip_l,
        clip_right=clip_r,
        ongoing=ongoing,
        dep_ext=dep_ext,
        title="\n".join(lines),
        aria="; ".join(lines),
        data=data,
        lead=lead,
        locked=p.locked,
        risk=risk,
    )


def _facts(
    plan: Plan,
    p: PlannedProject,
    team: Team,
    by_seq: Mapping[int, PlannedProject],
    teams_by_id: Mapping[str, Team],
    subdomain_names: Mapping[str, str],
) -> list[TipRow]:
    """Tooltip facts in RS OUT-18 order: team; product; size; requested start; actual start; last day; delay;
    After."""
    rows = [TipRow("Team", team.name)]
    if p.product is not None:
        pr = next(x for x in plan.products if x.id == p.product)
        domain, owner = _owned_by(plan, pr)
        rows.append(TipRow("Product", f"{pr.name} · owned by {domain}" + (f" ({owner})" if owner else "")))
    if p.locked:
        fixed = f"start fixed {fmt_date(p.start)}"
        rows.append(TipRow("Locked", f"promised to {p.promised_to} · {fixed}" if p.promised_to else fixed))
        if p.lock_risk is not None:
            rows.append(TipRow("Promise at risk", lock_risk_text(p, team, by_seq)))
    if p.ongoing or p.size is None:
        rows.append(TipRow("Size", "Ongoing"))
    else:
        rows.append(TipRow("Size", f"{p.size} · {plural(p.weeks or 0, 'week', 'weeks')}"))
    if p.requested_start is None:
        rows.append(TipRow("Requested start", "auto (first free slot)"))
    else:
        rows.append(TipRow("Requested start", fmt_date(p.requested_start)))
    rows.append(TipRow("Actual start", fmt_date(p.start)))
    if p.end is None:
        rows.append(TipRow("Last day", "none (ongoing)"))
    else:
        last = p.last_day if p.last_day is not None else p.end - timedelta(days=1)
        rows.append(TipRow("Last day", fmt_date(last)))
    if p.delay_days > 0:
        why = _REASON_TEXT.get(p.delay_reason or "", "")
        text = f"{plural(p.delay_days, 'day', 'days')} ({delay_label(p.delay_days)})"
        rows.append(TipRow("Delay", f"{text}, {why}" if why else text))
    else:
        rows.append(TipRow("Delay", "none"))
    if p.depends_on:
        parts = []
        for d in p.depends_on:
            dep = by_seq[d]
            dep_team = teams_by_id[dep.team]
            parts.append(f"{dep.name} ({subdomain_names[dep_team.subdomain_id]} › {dep_team.name})")
        rows.append(TipRow("After", ", ".join(parts)))
    if p.overflow and p.lock_risk is None:
        rows.append(TipRow("Over capacity", f"overflow lane +{p.lane - team.slots}"))
    return rows


def lock_risk_text(p: PlannedProject, team: Team, by_seq: Mapping[int, PlannedProject]) -> str:
    """Why a locked project cannot keep its promise (RS OUT-36): the dependency that ends last, a full team, or
    both."""
    parts: list[str] = []
    late = [(end, -d.seq, d) for d in map(by_seq.__getitem__, p.depends_on) if (end := d.end) and end > p.start]
    if late:
        dep = max(late)[2]
        last = dep.last_day or dep.start
        parts.append(f"depends on {dep.name} (last day {fmt_date(last)})")
    if p.overflow:
        parts.append(f"no free slot in team {team.name} (overflow lane +{p.lane - team.slots})")
    return "; ".join(parts)


# --------------------------------------------------------------------------------------------- summary


def _summary(plan: Plan, scale: g.Scale) -> SummaryVM:
    model = plan.model
    projects = plan.projects
    totals = [0, 0, 0, 0]
    for t in model.teams:
        for i, n in enumerate(_role_counts(t.capacity)):
            totals[i] += n
    people_note = " · ".join(f"{role} {n}" for (role, _), n in zip(_ROLES, totals, strict=True))
    kpis = [
        KpiVM("Subdomains", str(len(model.subdomains)), None),
        KpiVM("Teams", str(len(model.teams)), None),
        KpiVM("Projects", str(sum(1 for p in projects if not p.ongoing)), "finite"),
        KpiVM("Ongoing", str(sum(1 for p in projects if p.ongoing)), None),
        KpiVM("Delayed", str(sum(1 for p in projects if DELAYED in p.flags)), None),
    ]
    if Mode(plan.on_conflict) is Mode.OVERFLOW:
        kpis.append(KpiVM("Over capacity", str(sum(1 for p in projects if OVER_CAPACITY in p.flags)), None))
    if any(p.locked for p in projects):  # CR-3 (RS OUT-30)
        kpis.append(KpiVM("Locked", str(sum(1 for p in projects if p.locked)), "promised"))
        kpis.append(KpiVM("At risk", str(sum(1 for p in projects if p.lock_risk is not None)), "promises"))
    kpis.append(KpiVM("Slots", str(sum(t.slots for t in model.teams)), None))
    kpis.append(KpiVM("People", str(sum(totals)), people_note))
    ind = indicators_of(plan)
    for kind in ti.INDICATORS:
        value = ind.stats(kind).all
        kpis.append(KpiVM(_IND_NAME[kind], "–" if value is None else fmt1(value), "all teams"))

    ml = plan.monthly_load
    months = ml.months
    heads = tuple(MonthHeadVM(m.abbr(), str(m.year) if i == 0 or m.month == 1 else None) for i, m in enumerate(months))
    team_loads = {tl.team: tl for tl in ml.teams}
    sub_loads = {sl.subdomain: sl for sl in ml.subdomains}
    teams_by_id = {t.id: t for t in model.teams}
    rows: list[LoadRowVM] = []
    for sub in model.subdomains:
        sl = sub_loads.get(sub.id)
        if sl is not None:
            rows.append(
                LoadRowVM(
                    "subdomain",
                    sub.name,
                    True,
                    _cells(sub.name, sub.id, "subdomain", months, sl.load, sl.occupied, sl.capacity),
                )
            )
        for tid in sub.team_ids:
            tl = team_loads.get(tid)
            if tl is None or tid not in teams_by_id:
                continue
            name = teams_by_id[tid].name
            rows.append(
                LoadRowVM("team", name, True, _cells(name, tid, "team", months, tl.load, tl.occupied, tl.capacity))
            )
    rows.append(
        LoadRowVM(
            "all",
            "All teams",
            False,
            _cells("All teams", "all", "all", months, ml.total, ml.total_occupied, ml.total_capacity),
        )
    )
    return SummaryVM(tuple(kpis), heads, tuple(rows), _composition(plan), _commitments(plan))


def _commitments(plan: Plan) -> tuple[CommitmentVM, ...]:
    """Every locked project with its promise and status, in file order (RS OUT-37)."""
    teams = {t.id: t for t in plan.model.teams}
    products = {pr.id: pr.name for pr in plan.products}
    by_seq = {p.seq: p for p in plan.projects}
    out: list[CommitmentVM] = []
    for p in plan.projects:
        if not p.locked:
            continue
        team = teams[p.team]
        risky = p.lock_risk is not None
        out.append(
            CommitmentVM(
                seq=p.seq,
                name=p.name,
                team=team.name,
                product=products.get(p.product or "", "–"),
                promised_to=p.promised_to or "–",
                start=fmt_date(p.start),
                last_day="none (ongoing)" if p.last_day is None else fmt_date(p.last_day),
                status="at_risk" if risky else "on_track",
                status_text="At risk" if risky else "On track",
                reason=lock_risk_text(p, team, by_seq) if risky else "",
            )
        )
    return tuple(out)


def _cells(
    name: str,
    row: str,
    kind: str,
    months: Sequence[Month],
    loads: Sequence[Decimal],
    occupied: Sequence[int],
    capacity: Sequence[int],
) -> tuple[LoadCellVM, ...]:
    out: list[LoadCellVM] = []
    exact_known = len(occupied) == len(months) and len(capacity) == len(months)
    for i, m in enumerate(months):
        load = loads[i]
        exact = Fraction(occupied[i], capacity[i]) if exact_known and capacity[i] else None
        percent = pct(_ratio(exact, load))
        text = "–" if percent == 0 else f"{percent} %"
        if exact_known:
            title = f"{name} · {m.label()} · {occupied[i]} of {capacity[i]} slot-days ({percent} %)"
        else:
            title = f"{name} · {m.label()} · {percent} %"
        out.append(LoadCellVM(text, load_bin(percent), title, row, kind, str(m), fmt4(load)))
    return tuple(out)
