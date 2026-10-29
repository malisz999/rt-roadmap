"""Test helper: YAML file or text → ResolvedModel without the validator (assumes a valid file).

Mirrors what model.build + model.references produce for valid input, so scheduling, colouring and plan tests can
run independently of the loader and validator. Also offers small builders for hand-made models.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any

from ruamel.yaml import YAML

from rt.diagnostics import Pos
from rt.model.types import (
    Capacity,
    ColorSpec,
    DepRef,
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
from rt.timeutil import Month, parse_date

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "docs" / "fixtures"
WE = FIXTURES / "scheduling-worked-example.yaml"
DE = FIXTURES / "dependencies-example.yaml"
EX = FIXTURES / "roadmap.example.yaml"
PALETTE_NAMES = (
    *("indigo", "green", "orange", "pink", "sky", "amber", "violet", "teal", "lime", "sand"),
    *("blue", "cyan", "emerald", "yellow", "fuchsia", "purple", "stone", "sand-deep", "indigo-deep", "green-deep"),
    *("orange-deep", "pink-deep", "sky-deep", "amber-deep", "violet-deep", "teal-deep", "lime-deep", "blue-deep"),
    *("cyan-deep", "emerald-deep", "fuchsia-deep", "purple-deep"),
)


def _month(value: Any) -> Month:
    if isinstance(value, date):
        return Month(value.year, value.month)
    return Month.parse(str(value))


def _date(value: Any) -> date:
    return value if isinstance(value, date) else parse_date(str(value))


def _pos(node: Any, source: str) -> Pos:
    return Pos(node.lc.line + 1, node.lc.col + 1, source)


def _key_pos(node: Any, key: str, source: str) -> Pos:
    line, col = node.lc.key(key)
    return Pos(line + 1, col + 1, source)


def _color(value: Any) -> ColorSpec | None:
    if value is None:
        return None
    text = str(value)
    if text in PALETTE_NAMES:
        return ColorSpec(text, None, text)
    return ColorSpec(None, text.upper(), text)


def resolve(model: Model) -> ResolvedModel:
    """Resolve `depends_on` (id, then unique name) and weeks, as model.references does for valid input."""
    by_id = {p.id: p.seq for p in model.projects if p.id is not None}
    by_name: dict[str, list[int]] = {}
    for p in model.projects:
        by_name.setdefault(p.name or "", []).append(p.seq)
    deps: dict[int, tuple[int, ...]] = {}
    weeks: dict[int, int | None] = {}
    for p in model.projects:
        seqs = set()
        for ref in p.depends_on_refs:
            seqs.add(by_id[ref.text] if ref.text in by_id else by_name[ref.text][0])
        deps[p.seq] = tuple(sorted(seqs))
        weeks[p.seq] = None if p.ongoing else model.size_weeks(p.size or "")
    return ResolvedModel(model, MappingProxyType(deps), MappingProxyType(weeks))


def from_doc(
    doc: Any,
    source: str = "<input>",
    *,
    on_conflict: str | None = None,
    hfrom: str | None = None,
    hto: str | None = None,
    today: str | None = None,
    default_today: date = date(2026, 10, 24),
) -> ResolvedModel:
    rm = doc["roadmap"]
    hz = rm.get("horizon") or {}
    sched = doc.get("scheduling") or {}
    settings = Settings(
        title=str(rm["title"]),
        subtitle=rm.get("subtitle"),
        horizon_start=_month(hfrom) if hfrom else (_month(hz["start"]) if "start" in hz else None),
        horizon_end=_month(hto) if hto else (_month(hz["end"]) if "end" in hz else None),
        today=_date(today) if today else (_date(rm["today"]) if "today" in rm else default_today),
        month_width=int(rm.get("month_width", 120)),
        content_language=rm.get("content_language"),
        on_conflict=Mode(on_conflict or sched.get("on_conflict", "delay")),
        adjacency_gap_days=int(sched.get("adjacency_gap_days", 14)),
        pos=_key_pos(doc, "roadmap", source) if hasattr(doc, "lc") else None,
    )
    sizes = tuple(Size(str(k), int(v)) for k, v in doc["sizes"].items())
    subdomains: list[Subdomain] = []
    teams: list[Team] = []
    for sd in doc["subdomains"]:
        sd_teams = sd.get("teams") or []
        subdomains.append(
            Subdomain(sd["id"], sd["name"], sd.get("description"), tuple(t["id"] for t in sd_teams), _pos(sd, source))
        )
        for t in sd_teams:
            cap = t.get("capacity")
            teams.append(
                Team(
                    id=t["id"],
                    name=t["name"],
                    subdomain_id=sd["id"],
                    slots=int(t["parallel_projects"]),
                    capacity=Capacity(**{k: int(v) for k, v in (cap or {}).items()}),
                    pos=_pos(t, source),
                    capacity_given=cap is not None,
                )
            )
    projects: list[Project] = []
    for seq, p in enumerate(doc["projects"] or [], 1):
        refs = p.get("depends_on") or []
        refs = [refs] if isinstance(refs, str) else list(refs)
        ongoing = bool(p.get("ongoing", False))
        projects.append(
            Project(
                seq=seq,
                id=p.get("id"),
                name=str(p["name"]),
                team_id=p["team"],
                start=_month(p["start"]) if "start" in p else None,
                size=None if ongoing else str(p["size"]),
                ongoing=ongoing,
                depends_on_refs=tuple(DepRef(str(r), _pos(p, source)) for r in refs),
                description=p.get("description"),
                color=_color(p.get("color")),
                pos=_pos(p, source),
                product_id=p.get("product"),
            )
        )
    products = tuple(
        Product(
            id=q["id"],
            name=str(q["name"]),
            domain_id=q["domain"],
            owner=q.get("owner"),
            description=q.get("description"),
            color=_color(q.get("color")),
            pos=_pos(q, source),
        )
        for q in doc.get("products") or []
    )
    model = Model(settings, sizes, tuple(subdomains), tuple(teams), tuple(projects), source, products)
    return resolve(model)


def load_text(text: str, source: str = "<input>", **kw: Any) -> ResolvedModel:
    return from_doc(YAML().load(io.StringIO(text)), source, **kw)


def load_path(path: Path | str, **kw: Any) -> ResolvedModel:
    p = Path(path)
    return load_text(p.read_text(encoding="utf-8"), str(path), **kw)


# --- hand-made models ----------------------------------------------------------------------------------------


def make_model(
    teams: Sequence[tuple[str, str, int]],
    projects: Sequence[dict[str, Any]],
    *,
    sizes: dict[str, int] | None = None,
    mode: Mode = Mode.DELAY,
    hstart: str | None = None,
    hend: str | None = None,
    today: date = date(2027, 1, 15),
    gap: int = 14,
    subdomains: Sequence[str] | None = None,
    products: Sequence[tuple[str, str, str | None]] = (),
) -> ResolvedModel:
    """teams: (id, subdomain, slots); projects: dicts with name, team, size|ongoing, start, deps (seqs), color,
    product; products: (id, domain, color or None)."""
    sizes = sizes or {"S": 2, "M": 4, "L": 8}
    sd_ids = list(subdomains) if subdomains is not None else list(dict.fromkeys(t[1] for t in teams))
    settings = Settings(
        title="T",
        subtitle=None,
        horizon_start=Month.parse(hstart) if hstart else None,
        horizon_end=Month.parse(hend) if hend else None,
        today=today,
        month_width=120,
        content_language=None,
        on_conflict=mode,
        adjacency_gap_days=gap,
        pos=Pos(1, 1, "<t>"),
    )
    team_objs = tuple(
        Team(tid, tid.title(), sd, slots, Capacity(1), Pos(10 + i, 3, "<t>"))
        for i, (tid, sd, slots) in enumerate(teams)
    )
    sd_objs = tuple(
        Subdomain(sd, sd.title(), None, tuple(t[0] for t in teams if t[1] == sd), Pos(5 + i, 3, "<t>"))
        for i, sd in enumerate(sd_ids)
    )
    proj_objs: list[Project] = []
    deps: dict[int, tuple[int, ...]] = {}
    weeks: dict[int, int | None] = {}
    for seq, spec in enumerate(projects, 1):
        ongoing = bool(spec.get("ongoing", False))
        color = spec.get("color")
        proj_objs.append(
            Project(
                seq=seq,
                id=spec.get("id"),
                name=spec.get("name", f"P{seq}"),
                team_id=spec["team"],
                start=Month.parse(spec["start"]) if spec.get("start") else None,
                size=None if ongoing else spec.get("size", "M"),
                ongoing=ongoing,
                depends_on_refs=(),
                description=None,
                color=_color(color),
                pos=Pos(100 + seq, 5, "<t>"),
                product_id=spec.get("product"),
            )
        )
        deps[seq] = tuple(sorted(spec.get("deps", ())))
        weeks[seq] = None if ongoing else sizes[spec.get("size", "M")]
    prod_objs = tuple(
        Product(pid, pid.upper(), domain, None, None, _color(color), Pos(50 + i, 3, "<t>"))
        for i, (pid, domain, color) in enumerate(products)
    )
    model = Model(
        settings, tuple(Size(k, v) for k, v in sizes.items()), sd_objs, team_objs, tuple(proj_objs), "<t>", prod_objs
    )
    return ResolvedModel(model, MappingProxyType(deps), MappingProxyType(weeks))


# --- the reference oracle ------------------------------------------------------------------------------------


def oracle() -> ModuleType:
    """tools/reference_plan.py imported by path (test tooling only)."""
    name = "rt_reference_plan_oracle"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / "reference_plan.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
