"""compute_plan assembly, warnings and to_json formatting (RS 8, PL-1 to PL-6, 9.2)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from modelkit import WE, load_path, load_text, make_model

import rt
from rt.diagnostics import Code, Collector, Pos
from rt.model.types import Mode
from rt.plan import compute_plan, to_json
from rt.plan.serialize import to_jsonable
from rt.plan.types import NOT_JSON
from rt.timeutil import Month

D = date


def test_plan_fields_for_renderer() -> None:
    diags = Collector()
    plan = compute_plan(load_path(WE), diags)
    assert plan is not None
    assert plan.rt_version == rt.__version__ and plan.format == 1
    assert plan.today == D(2027, 2, 15) and plan.on_conflict is Mode.DELAY
    assert plan.teams[0].utilization == Decimal("0.7624")
    assert plan.teams[0].utilization_exact == Fraction(276, 362)
    alpha = plan.monthly_load.teams[0]
    assert (alpha.occupied[1], alpha.capacity[1], alpha.load[1]) == (53, 56, Decimal("0.9464"))
    assert plan.monthly_load.total_capacity[0] == 3 * 31
    reporting = plan.projects[2]
    assert reporting.color is not None and reporting.color.accent == "#22C55E" and reporting.color.text == "#1E293B"
    assert plan.model.settings.title == "Scheduling worked example"
    assert [d.code for d in plan.diagnostics] == [Code.W001] * 4
    assert len(plan.warnings) == 4 and plan.warnings[0].line == 38


def test_error_mode_returns_none() -> None:
    diags = Collector()
    assert compute_plan(load_path(WE, on_conflict="error"), diags) is None
    assert [d.code for d in diags.errors] == [Code.E061, Code.E061]


def test_e060_returns_none() -> None:
    m = make_model(
        [("a", "sd", 1)],
        [{"team": "a", "ongoing": True, "start": "2027-01"}, {"team": "a", "start": "2027-02"}],
    )
    diags = Collector()
    assert compute_plan(m, diags) is None
    assert diags.has_scheduling_errors()


STRUCTURE = """\
version: 1
roadmap:
  title: Płatności – łańcuch źródeł
  today: 2027-01-10
sizes: {M: 4}
subdomains:
  - id: core
    name: Core
    teams:
      - id: alpha
        name: Alpha
        parallel_projects: 1
        capacity: {developers: 0}
      - id: idle
        name: Idle
        parallel_projects: 1
  - id: risk
    name: Risk
    teams: []
projects:
  - name: Zażółć
    team: alpha
    size: M
    start: 2027-01
"""


def test_structure_warnings_and_positions() -> None:
    diags = Collector()
    plan = compute_plan(load_text(STRUCTURE, "f.yaml"), diags)
    assert plan is not None
    got = [(w.code, w.line, w.column, w.message) for w in plan.warnings]
    assert got == [
        ("W008", 10, 9, 'team "alpha" has no members in capacity'),
        ("W005", 14, 9, 'team "idle" has no projects'),
        ("W006", 17, 5, 'subdomain "risk" has no teams'),
    ]
    assert [s.subdomain for s in plan.monthly_load.subdomains] == ["core", "risk"]
    text = to_json(plan)
    assert "Płatności – łańcuch źródeł" in text and "Zażółć" in text


def test_no_projects_w010() -> None:
    text = STRUCTURE.split("\nprojects:")[0] + "\nprojects: []\n"
    diags = Collector()
    plan = compute_plan(load_text(text, "f.yaml"), diags)
    assert plan is not None
    w010 = [w for w in plan.warnings if w.code == "W010"]
    assert [(w.line, w.column, w.message) for w in w010] == [(2, 1, "no projects defined; rendering empty roadmap")]
    assert (plan.horizon.start, plan.horizon.end) == (Month(2027, 1), Month(2027, 6))
    assert plan.projects == ()


def test_existing_collector_warnings_are_included_and_sorted() -> None:
    diags = Collector()
    diags.warning(Code.W020, Pos(1, 8, "f.yaml"), detail="validation-time warning")
    diags.warning(Code.W012, None, start="x", end="y")
    plan = compute_plan(load_path(WE), diags)
    assert plan is not None
    assert [(w.code, w.line) for w in plan.warnings][:2] == [("W012", None), ("W020", 1)]
    assert len(plan.diagnostics) == len(plan.warnings) == 6


def test_to_json_format() -> None:
    plan = compute_plan(load_path(WE), Collector())
    assert plan is not None
    text = to_json(plan)
    assert text.endswith("}\n") and "\r" not in text
    data = json.loads(text)
    assert list(data) == [
        "rt_version",
        "format",
        "title",
        "today",
        "horizon",
        "on_conflict",
        "teams",
        "projects",
        "monthly_load",
        "warnings",
    ]
    assert "utilization_exact" not in data["teams"][0]
    assert "color" not in data["projects"][0]
    assert list(data["monthly_load"]["teams"][0]) == ["team", "load"]
    assert re.search(r'"load": \[\n +1\.0,\n +0\.9464,', text)
    assert data["horizon"] == {
        "start": "2027-01",
        "end": "2027-06",
        "start_date": "2027-01-01",
        "end_exclusive": "2027-07-01",
        "days": 181,
    }
    assert data["on_conflict"] == "delay"


def test_to_jsonable_values() -> None:
    @dataclass
    class Box:
        a: Month
        b: tuple[Decimal, ...]
        c: dict[str, date]
        hidden: int = field(default=0, metadata=NOT_JSON)

    assert to_jsonable(Box(Month(2027, 3), (Decimal("1.0000"),), {"d": D(2027, 1, 2)})) == {
        "a": "2027-03",
        "b": [1.0],
        "c": {"d": "2027-01-02"},
    }
    assert to_jsonable(Mode.OVERFLOW) == "overflow"
    assert to_jsonable([True, None, 1.5]) == [True, None, 1.5]
    with pytest.raises(TypeError):
        to_jsonable(object())
