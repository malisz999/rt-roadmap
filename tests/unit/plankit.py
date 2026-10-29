"""Test helper: build `Plan` objects for layout and render tests without the production pipeline.

Scheduling, colours and loads come from the reference oracle (`docs/reference/reference_plan.py`); names,
capacities, sizes and settings come from the same YAML read with ruamel. Test tooling only.
"""

from __future__ import annotations

import importlib.util
import tempfile
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any

from ruamel.yaml import YAML

from rt.color.types import ColorRef
from rt.decimalutil import ratio4
from rt.diagnostics import Pos
from rt.model.types import (
    Capacity,
    ColorSpec,
    Mode,
    Model,
    Product,
    Project,
    ResolvedModel,
    Settings,
    Size,
    Subdomain,
    Team,
)
from rt.plan.types import (
    HorizonOut,
    MonthlyLoad,
    Plan,
    PlannedProject,
    PlanWarning,
    ProductPlan,
    SubdomainLoad,
    TeamLoad,
    TeamPlan,
    VisibleOut,
)
from rt.timeutil import Month, parse_date

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "docs" / "fixtures"
WE = FIXTURES / "scheduling-worked-example.yaml"
DE = FIXTURES / "dependencies-example.yaml"
EX = FIXTURES / "roadmap.example.yaml"

PALETTE: tuple[tuple[str, str, str], ...] = (
    ("indigo", "#C7D2FE", "#6366F1"),
    ("green", "#BBF7D0", "#22C55E"),
    ("orange", "#FED7AA", "#F97316"),
    ("pink", "#FBCFE8", "#EC4899"),
    ("sky", "#BAE6FD", "#0EA5E9"),
    ("amber", "#FDE68A", "#D97706"),
    ("violet", "#DDD6FE", "#8B5CF6"),
    ("teal", "#99F6E4", "#14B8A6"),
    ("lime", "#D9F99D", "#65A30D"),
    ("sand", "#EADBC8", "#A16207"),
    ("blue", "#BFDBFE", "#3B82F6"),
    ("cyan", "#A5F3FC", "#06B6D4"),
    ("emerald", "#A7F3D0", "#10B981"),
    ("yellow", "#FEF08A", "#CA8A04"),
    ("fuchsia", "#F5D0FE", "#D946EF"),
    ("purple", "#E9D5FF", "#A855F7"),
    ("stone", "#E7E5E4", "#78716C"),
    ("sand-deep", "#D6C3A5", "#854D0E"),
    ("indigo-deep", "#A5B4FC", "#4F46E5"),
    ("green-deep", "#86EFAC", "#16A34A"),
    ("orange-deep", "#FDBA74", "#EA580C"),
    ("pink-deep", "#F9A8D4", "#DB2777"),
    ("sky-deep", "#7DD3FC", "#0284C7"),
    ("amber-deep", "#FCD34D", "#B45309"),
    ("violet-deep", "#C4B5FD", "#7C3AED"),
    ("teal-deep", "#5EEAD4", "#0D9488"),
    ("lime-deep", "#BEF264", "#4D7C0F"),
    ("blue-deep", "#93C5FD", "#2563EB"),
    ("cyan-deep", "#67E8F9", "#0891B2"),
    ("emerald-deep", "#6EE7B7", "#059669"),
    ("fuchsia-deep", "#F0ABFC", "#C026D3"),
    ("purple-deep", "#D8B4FE", "#9333EA"),
)

_reference: ModuleType | None = None


def reference() -> ModuleType:
    global _reference
    if _reference is None:
        spec = importlib.util.spec_from_file_location("rt_reference_plan", REPO / "docs/reference/reference_plan.py")
        assert spec is not None and spec.loader is not None
        _reference = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_reference)
    return _reference


def _d(text: str | None) -> date | None:
    return None if text is None else parse_date(text)


def _pos(line: int = 1, col: int = 1) -> Pos:
    return Pos(line, col, "<test>")


def plan_from_text(text: str, **kwargs: Any) -> Plan:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "roadmap.yaml"
        path.write_text(text, encoding="utf-8")
        return plan_from_file(path, **kwargs)


def plan_from_file(
    path: Path,
    *,
    on_conflict: str | None = None,
    hfrom: str | None = None,
    hto: str | None = None,
    edit: Callable[[dict[str, Any]], None] | None = None,
) -> Plan:
    """Plan for a YAML file; `edit` may change the oracle's JSON-like output before conversion."""
    kw = {k: v for k, v in {"on_conflict": on_conflict, "hfrom": hfrom, "hto": hto}.items() if v is not None}
    out: dict[str, Any] = reference().run(str(path), **kw)
    if edit is not None:
        edit(out)
    doc = YAML().load(path.read_text(encoding="utf-8"))
    return _to_plan(doc, out)


def _to_plan(doc: Any, out: dict[str, Any]) -> Plan:
    rm = doc["roadmap"]
    hz = out["horizon"]
    start, end = Month.parse(hz["start"]), Month.parse(hz["end"])
    sched = doc.get("scheduling") or {}
    settings = Settings(
        title=str(rm["title"]),
        subtitle=str(rm["subtitle"]) if rm.get("subtitle") else None,
        horizon_start=start,
        horizon_end=end,
        today=parse_date(str(rm.get("today"))),
        month_width=int(rm.get("month_width", 120)),
        content_language=str(rm["content_language"]) if rm.get("content_language") else None,
        on_conflict=Mode(out["on_conflict"]),
        adjacency_gap_days=int(sched.get("adjacency_gap_days", 14)),
    )
    sizes = tuple(Size(str(k), int(v)) for k, v in doc["sizes"].items())
    subdomains: list[Subdomain] = []
    teams: list[Team] = []
    for sd in doc["subdomains"]:
        tids = []
        for t in sd.get("teams") or []:
            cap = t.get("capacity") or {}
            teams.append(
                Team(
                    id=str(t["id"]),
                    name=str(t["name"]),
                    subdomain_id=str(sd["id"]),
                    slots=int(t["parallel_projects"]),
                    capacity=Capacity(
                        int(cap.get("developers", 0)),
                        int(cap.get("product_managers", 0)),
                        int(cap.get("analysts", 0)),
                        int(cap.get("testers", 0)),
                    ),
                    pos=_pos(),
                )
            )
            tids.append(str(t["id"]))
        desc = sd.get("description")
        subdomains.append(Subdomain(str(sd["id"]), str(sd["name"]), str(desc) if desc else None, tuple(tids), _pos()))
    projects: list[Project] = []
    for seq, p in enumerate(doc["projects"] or [], 1):
        color = p.get("color")
        projects.append(
            Project(
                seq=seq,
                id=p.get("id"),
                name=str(p["name"]),
                team_id=str(p["team"]),
                start=Month.parse(str(p["start"])[:7]) if "start" in p else None,
                size=str(p["size"]) if "size" in p else None,
                ongoing=bool(p.get("ongoing", False)),
                depends_on_refs=(),
                description=str(p["description"]) if p.get("description") else None,
                color=ColorSpec(str(color), None, str(color)) if color else None,
                pos=_pos(seq),
                product_id=str(p["product"]) if p.get("product") else None,
            )
        )
    products = tuple(
        Product(
            id=str(q["id"]),
            name=str(q["name"]),
            domain_id=str(q["domain"]),
            owner=str(q["owner"]) if q.get("owner") else None,
            description=str(q["description"]) if q.get("description") else None,
            color=ColorSpec(str(q["color"]), None, str(q["color"])) if q.get("color") else None,
            pos=_pos(),
        )
        for q in doc.get("products") or []
    )
    model = Model(settings, sizes, tuple(subdomains), tuple(teams), tuple(projects), products=products)
    deps = {pp["seq"]: tuple(pp["depends_on"]) for pp in out["projects"]}
    weeks = {pp["seq"]: pp["weeks"] for pp in out["projects"]}
    resolved = ResolvedModel(model, MappingProxyType(deps), MappingProxyType(weeks))

    h0, h1 = parse_date(hz["start_date"]), parse_date(hz["end_exclusive"])
    planned = tuple(_project(pp) for pp in out["projects"])
    team_plans = tuple(_team_plan(tp, planned, h0, h1) for tp in out["teams"])
    return Plan(
        rt_version="1.1.0",
        format=1,
        title=out["title"],
        today=settings.today,
        horizon=HorizonOut(start, end, h0, h1, hz["days"]),
        on_conflict=Mode(out["on_conflict"]),
        teams=team_plans,
        products=tuple(_product_plan(pp) for pp in out["products"]),
        projects=planned,
        monthly_load=_load(out["monthly_load"], planned, teams, subdomains),
        warnings=tuple(PlanWarning(w["code"], w["line"], w["column"], w["message"]) for w in out["warnings"]),
        model=resolved,
    )


def _color(ci: int | None) -> ColorRef | None:
    if ci is None:
        return None
    name, fill, accent = PALETTE[ci]
    return ColorRef(ci, name, fill, accent, "#1E293B")


def _product_plan(pp: dict[str, Any]) -> ProductPlan:
    color = _color(pp["color_index"])
    assert color is not None
    return ProductPlan(
        id=pp["id"],
        name=pp["name"],
        domain=pp["domain"],
        owner=pp["owner"],
        color_index=pp["color_index"],
        color_name=pp["color_name"],
        color_fill=pp["color_fill"],
        projects=tuple(pp["projects"]),
        color=color,
    )


def _project(pp: dict[str, Any]) -> PlannedProject:
    ci = pp["color_index"]
    color = _color(ci)
    vis = pp["visible"]
    start = _d(pp["start"])
    earliest = _d(pp["earliest_start"])
    assert start is not None and earliest is not None
    return PlannedProject(
        seq=pp["seq"],
        id=pp["id"],
        name=pp["name"],
        team=pp["team"],
        product=pp["product"],
        size=pp["size"],
        weeks=pp["weeks"],
        ongoing=pp["ongoing"],
        requested_start=_d(pp["requested_start"]),
        depends_on=tuple(pp["depends_on"]),
        earliest_start=earliest,
        start=start,
        end=_d(pp["end"]),
        last_day=_d(pp["last_day"]),
        lane=pp["lane"],
        overflow=pp["overflow"],
        delay_days=pp["delay_days"],
        delay_reason=pp["delay_reason"],
        visible=None if vis is None else VisibleOut(parse_date(vis["start"]), parse_date(vis["end"])),
        color_index=ci,
        color_name=pp["color_name"],
        color_fill=pp["color_fill"],
        flags=tuple(pp["flags"]),
        neighbors=tuple(pp["neighbors"]),
        color=color,
    )


def _team_plan(tp: dict[str, Any], planned: tuple[PlannedProject, ...], h0: date, h1: date) -> TeamPlan:
    days = sum(
        (p.visible.end - p.visible.start).days
        for p in planned
        if p.team == tp["id"] and p.visible is not None and not p.overflow
    )
    exact = Fraction(days, tp["slots"] * (h1 - h0).days)
    return TeamPlan(
        tp["id"], tp["subdomain"], tp["slots"], tp["overflow_lanes"], ratio4(days, tp["slots"] * (h1 - h0).days), exact
    )


def _occupied(planned: tuple[PlannedProject, ...], team: str, a: date, b: date) -> int:
    far = date(9999, 12, 31)
    return sum(max(0, (min(p.end or far, b) - max(p.start, a)).days) for p in planned if p.team == team)


def _load(
    ml: dict[str, Any], planned: tuple[PlannedProject, ...], teams: list[Team], subs: list[Subdomain]
) -> MonthlyLoad:
    months = tuple(Month.parse(m) for m in ml["months"])
    bounds = [(m.first_day(), m.next().first_day()) for m in months]
    slots = {t.id: t.slots for t in teams}
    occ = {t.id: tuple(_occupied(planned, t.id, a, b) for a, b in bounds) for t in teams}
    cap = {t.id: tuple(slots[t.id] * (b - a).days for a, b in bounds) for t in teams}
    team_loads = tuple(TeamLoad(tl["team"], _dec(tl["load"]), occ[tl["team"]], cap[tl["team"]]) for tl in ml["teams"])
    sub_loads = []
    for sl in ml["subdomains"]:
        members = [t.id for t in teams if t.subdomain_id == sl["subdomain"]]
        o = tuple(sum(occ[t][i] for t in members) for i in range(len(months)))
        c = tuple(sum(cap[t][i] for t in members) for i in range(len(months)))
        sub_loads.append(SubdomainLoad(sl["subdomain"], _dec(sl["load"]), o, c))
    to = tuple(sum(occ[t.id][i] for t in teams) for i in range(len(months)))
    tc = tuple(sum(cap[t.id][i] for t in teams) for i in range(len(months)))
    del subs
    return MonthlyLoad(months, team_loads, tuple(sub_loads), _dec(ml["total"]), to, tc)


def _dec(values: list[float]) -> tuple[Decimal, ...]:
    return tuple(Decimal(str(v)).quantize(Decimal("0.0001")) for v in values)


def shift(d: date, days: int) -> date:
    return d + timedelta(days=days)
