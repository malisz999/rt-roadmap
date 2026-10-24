"""Plan → PageVM (ADS 5.3): strings, classes and data attributes."""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from fractions import Fraction

import plankit
import pytest

from rt.color.types import ColorRef
from rt.layout.viewmodel import BarVM, PageVM, build_page, delay_label, load_bin, plural
from rt.plan.types import Plan


def page_of(plan: Plan, summary: bool = True) -> PageVM:
    return build_page(plan, summary=summary, version="9.9.9")


def bars(page: PageVM) -> dict[str, BarVM]:
    return {b.name: b for s in page.sections for t in s.teams for lane in t.lanes for b in lane.bars}


@pytest.fixture(scope="module")
def we() -> PageVM:
    return page_of(plankit.plan_from_file(plankit.WE))


@pytest.fixture(scope="module")
def de() -> PageVM:
    return page_of(plankit.plan_from_file(plankit.DE))


def test_small_formatters() -> None:
    assert [delay_label(d) for d in (1, 11, 13, 14, 25, 28, 59)] == ["+1d", "+11d", "+13d", "+2w", "+4w", "+4w", "+8w"]
    assert [load_bin(p) for p in (0, 1, 49, 50, 79, 80, 100, 101)] == [0, 1, 1, 2, 2, 3, 3, 4]
    assert plural(1, "team", "teams") == "1 team" and plural(0, "team", "teams") == "0 teams"


def test_page_header_and_scale(we: PageVM) -> None:
    assert we.title == "Scheduling worked example" and we.subtitle is None and we.lang is None
    assert we.horizon_label == "Jan 2027 – Jun 2027" and we.horizon_months == "6 months"
    assert we.as_of == "As of 15 Feb 2027" and we.mode_label == "Conflicts: delay"
    assert [s.label for s in we.legend.sizes] == ["S", "M", "L"] and we.legend.sizes[1].weeks == "4w"
    assert [(q.key, q.label, q.edge) for q in we.quarters] == [("2027-Q1", "Q1", ""), ("2027-Q2", "Q2", "quarter")]
    assert [(m.kind, m.date, m.left) for m in we.marks if m.kind == "quarter"] == [("quarter", "2027-04-01", "360.00")]
    assert all("rt-quarter-line" in m.classes for m in we.marks if m.kind == "quarter")
    assert not any("rt-quarter-line" in m.classes for m in we.marks if m.kind != "quarter")
    assert we.today is not None and (we.today.date, we.today.left, we.today.label) == (
        "2027-02-15",
        "180.00",
        "Today · 15 Feb",
    )
    assert we.today.align == "center"
    assert we.timeline_width == "720.00" and "--tw:720.00px" in we.css_vars and "--mw:120px" in we.css_vars
    assert we.version == "9.9.9"
    assert (
        we.warnings_label == "4 warnings" and we.warnings[0].code == "W001" and we.warnings[0].location == "line 38:5"
    )


def test_bars_of_the_worked_example(we: PageVM) -> None:
    b = bars(we)
    assert (b["Reporting"].left, b["Reporting"].width) == ("110.39", "114.76")
    assert (b["Quick win"].left, b["Quick win"].width) == ("122.00", "56.00")
    assert (b["Big bang"].left, b["Big bang"].width) == ("474.00", "216.00")
    m = b["Maintenance"]
    assert (m.left, m.width, m.ongoing) == ("242.00", "476.00", True)
    assert m.classes == "rt-bar rt-bar--ongoing" and m.chip is None
    assert dict(m.data)["data-end"] == "ongoing" and dict(m.data)["data-flags"] == "continues"

    r = b["Reporting"]
    assert dict(r.data) == {
        "data-seq": "3",
        "data-team": "alpha",
        "data-lane": "2",
        "data-requested": "2027-01-01",
        "data-start": "2027-01-29",
        "data-end": "2027-02-26",
        "data-delay-days": "28",
        "data-delay-reason": "capacity",
        "data-depends-on": "",
        "data-color-index": "1",
        "data-flags": "delayed",
    }
    assert r.data[0][0] == "data-seq"
    assert r.delay == "+4w" and r.chip is None and r.classes == "rt-bar rt-bar--delayed rt-bar--narrow"
    assert r.lead is not None and (r.lead.left, r.lead.width, r.lead.cut) == ("0.00", "110.39", False)
    assert (r.fill, r.accent, r.ink) == ("#BBF7D0", "#22C55E", "#1E293B")
    assert r.title.split("\n") == [
        "Reporting",
        "Team: Alpha",
        "Size: M · 4 weeks",
        "Requested start: 1 Jan 2027",
        "Actual start: 29 Jan 2027",
        "Last day: 25 Feb 2027",
        "Delay: 28 days (+4w), no free slot",
    ]
    assert r.aria == "; ".join(r.title.split("\n"))

    core = b["Core API"]
    assert core.chip == "L · 8w" and core.delay is None and core.lead is None and core.show_name
    hotfix = b["Hotfix pack"]  # 51 px: name only, no pill (the lead line shows the delay)
    assert hotfix.delay is None and hotfix.lead is not None and hotfix.show_name
    assert "rt-bar--tip-end" in b["Big bang"].classes and core.classes == "rt-bar"


def test_lanes_and_teams(we: PageVM) -> None:
    (section,) = we.sections
    assert (section.id, section.name, section.counts, section.height) == ("core", "Core", "2 teams · 9 projects", "152")
    alpha, beta = section.teams
    assert (alpha.utilization, alpha.util_text, alpha.util_width) == ("0.7624", "76 %", "76.24")
    assert (beta.utilization, beta.util_text) == ("0.5414", "54 %")
    assert alpha.people == "7 people" and alpha.slots_label == "2 parallel slots" and not alpha.compact
    assert beta.slots_label == "1 parallel slot" and beta.compact
    assert [(x.role, x.count, x.zero) for x in beta.badges] == [
        ("DEV", 2, False),
        ("PM", 0, True),
        ("BA", 0, True),
        ("QA", 1, False),
    ]
    # AT-06: backfill keeps left-to-right order within the lane
    assert [b.name for b in beta.lanes[0].bars] == ["Quick win", "Q2 launch", "Big bang"]
    assert [(lane.label, lane.overflow, lane.even) for lane in alpha.lanes] == [("1", False, False), ("2", False, True)]
    assert section.deps == ()


def test_summary(we: PageVM) -> None:
    s = we.summary
    assert s is not None
    assert [(k.label, k.value) for k in s.kpis] == [
        ("Subdomains", "1"),
        ("Teams", "2"),
        ("Projects", "8"),
        ("Ongoing", "1"),
        ("Delayed", "4"),
        ("Slots", "3"),
        ("People", "10"),
    ]
    assert s.kpis[-1].note == "DEV 6 · PM 1 · BA 1 · QA 2"
    assert [r.kind for r in s.rows] == ["subdomain", "team", "team", "all"]
    assert [m.label for m in s.months] == ["Jan", "Feb", "Mar", "Apr", "May", "Jun"] and s.months[0].year == "2027"
    texts = {r.name: [c.text for c in r.cells] for r in s.rows}
    assert texts == {
        "Core": ["67 %", "80 %", "67 %", "76 %", "67 %", "59 %"],
        "Alpha": ["100 %", "95 %", "100 %", "63 %", "50 %", "50 %"],
        "Beta": ["–", "50 %", "–", "100 %", "100 %", "77 %"],
        "All teams": ["67 %", "80 %", "67 %", "76 %", "67 %", "59 %"],
    }
    feb = s.rows[1].cells[1]
    assert (feb.row, feb.kind, feb.month, feb.load, feb.bin) == ("alpha", "team", "2027-02", "0.9464", 3)
    assert feb.title == "Alpha · Feb 2027 · 53 of 56 slot-days (95 %)"
    assert s.rows[-1].cells[0].row == "all" and not s.rows[-1].user_text
    assert page_of(plankit.plan_from_file(plankit.WE), summary=False).summary is None


def test_overflow_summary_and_lanes() -> None:
    page = page_of(plankit.plan_from_file(plankit.WE, on_conflict="overflow"))
    s = page.summary
    assert s is not None
    assert ("Over capacity", "2") in [(k.label, k.value) for k in s.kpis]
    alpha = next(r for r in s.rows if r.name == "Alpha")
    beta = next(r for r in s.rows if r.name == "Beta")
    core = next(r for r in s.rows if r.name == "Core")
    assert (alpha.cells[0].text, alpha.cells[0].bin) == ("140 %", 4)
    assert (beta.cells[3].text, beta.cells[3].bin) == ("177 %", 4)
    assert core.cells[0].text == "94 %"
    alpha_team = page.sections[0].teams[0]
    over = alpha_team.lanes[2]
    assert (over.label, over.overflow, over.number) == ("+1", True, 3)
    (reporting,) = over.bars
    assert "rt-bar--over" in reporting.classes and "Over capacity: overflow lane +1" in reporting.title


def test_dependencies(de: PageVM) -> None:
    product, platform = de.sections
    assert [(d.from_seq, d.to_seq) for d in product.deps] == [(1, 2), (2, 4), (1, 7)]
    assert product.deps[0].d == "M225.14 28.00H233.14V64.00H221.14V84.00H229.14"
    assert product.marker_id == "rt-arrow-product"
    assert platform.deps == ()
    b = bars(de)
    for name in ("Load testing", "Release audit"):
        assert b[name].dep_ext and "rt-bar--dep-ext" in b[name].classes.split()
    assert not b["Web checkout"].dep_ext and not b["Mobile release"].dep_ext
    assert "After: API v2 (Product › API), Web checkout (Product › Web)" in b["Load testing"].title.split("\n")
    assert dict(b["Release audit"].data)["data-delay-reason"] == "dependency+capacity"
    assert dict(b["Load testing"].data)["data-depends-on"] == "1 2"
    design = b["Design system"]
    assert dict(design.data)["data-requested"] == "auto" and "auto_start" in dict(design.data)["data-flags"]
    assert "Requested start: auto (first free slot)" in design.title and design.lead is None
    ops = b["Ops maintenance"]
    assert "Last day: none (ongoing)" in ops.title and "Size: Ongoing" in ops.title
    assert de.today is not None and de.today.align == "start"


def test_clipping_and_hidden() -> None:
    page = page_of(plankit.plan_from_file(plankit.WE, hfrom="2027-02", hto="2027-04"))
    b = bars(page)
    assert "Onboarding" not in b  # hidden: not drawn
    assert b["Core API"].clip_left and "rt-bar--clip-l" in b["Core API"].classes
    assert b["Big bang"].clip_right and "rt-bar--clip-r" in b["Big bang"].classes
    assert b["Reporting"].lead is None  # requested before the horizon and the bar starts at the edge
    assert page.today is not None and page.today.left == "60.00"


def test_lead_line_cut_at_the_horizon_edge() -> None:
    web = bars(page_of(plankit.plan_from_file(plankit.DE, hfrom="2027-02")))["Web checkout"]
    assert web.lead is not None and web.lead.cut and web.lead.left == "0.00"
    assert (web.left, web.lead.width) == ("109.14", "109.14")  # 25/28 × 120 + 2


def test_today_outside_the_horizon_and_at_the_right_edge() -> None:
    late = plankit.plan_from_file(plankit.WE)
    assert page_of(dataclasses.replace(late, today=late.horizon.end_exclusive), summary=False).today is None
    near_end = dataclasses.replace(late, today=late.horizon.end_exclusive.replace(day=1).replace(month=6, day=29))
    today = page_of(near_end, summary=False).today
    assert today is not None and today.align == "end"


def test_example_file_texts() -> None:
    page = page_of(plankit.plan_from_file(plankit.EX))
    assert page.lang == "pl" and page.subtitle == "Delivery plan by subdomain and team"
    assert [s.counts for s in page.sections] == [
        "2 teams · 9 projects",
        "1 team · 7 projects",
        "2 teams · 11 projects",
        "2 teams · 9 projects",
    ]
    assert [q.key for q in page.quarters] == ["2026-Q4", "2027-Q1", "2027-Q2"]
    year = next(m for m in page.marks if m.date == "2027-01-01")
    assert year.kind == "year" and "rt-quarter-line" not in year.classes
    assert "Płatności odroczone (BNPL) – pilot" in bars(page)
    assert page.warnings_label == "1 warning"


def test_custom_colours_and_missing_load_details() -> None:
    plan = plankit.plan_from_file(plankit.WE)
    custom = ColorRef(None, None, "#123456", "#0B2236", "#FFFFFF")
    projects = tuple(
        dataclasses.replace(p, color=custom, color_index=None, color_name=None, color_fill="#123456")
        if p.seq == 1
        else dataclasses.replace(p, color=None)
        if p.seq == 2
        else p
        for p in plan.projects
    )
    ml = plan.monthly_load
    bare = dataclasses.replace(
        ml,
        teams=tuple(dataclasses.replace(t, occupied=(), capacity=()) for t in ml.teams),
        total_occupied=(),
    )
    teams = tuple(dataclasses.replace(t, utilization_exact=Fraction(0)) for t in plan.teams)
    page = page_of(dataclasses.replace(plan, projects=projects, monthly_load=bare, teams=teams))
    b = bars(page)
    assert (b["Core API"].fill, b["Core API"].ink, dict(b["Core API"].data)["data-color-index"]) == (
        "#123456",
        "#FFFFFF",
        "",
    )
    assert b["Onboarding"].fill == "#FDE68A"  # falls back to the plan's color_fill
    assert page.sections[0].teams[0].util_text == "76 %"  # from the rounded value
    assert page.summary is not None
    alpha = page.summary.rows[1].cells[1]
    assert alpha.title == "Alpha · Feb 2027 · 95 %"


def test_description_empty_subdomain_and_xss_names() -> None:
    text = """version: 1
roadmap:
  title: <b>T</b> & co
  today: 2027-01-10
  content_language: pl
sizes: {S: 1, XL: 20}
subdomains:
  - id: empty
    name: Pusta
    teams: []
  - id: core
    name: Core
    description: Opis "core"
    teams:
      - {id: a, name: Zespół, parallel_projects: 1}
projects:
  - name: <script>alert(1)</script>
    team: a
    size: XL
    start: 2027-01
    description: Ważny projekt
  - name: Tiny
    team: a
    size: S
    start: 2027-06
"""
    page = page_of(plankit.plan_from_text(text))
    empty, core = page.sections
    assert empty.teams == () and empty.counts == "0 teams · 0 projects"
    assert core.description == 'Opis "core"'
    b = bars(page)
    xss = b["<script>alert(1)</script>"]
    assert xss.title.endswith("\nWażny projekt") and xss.aria.endswith("; Ważny projekt")
    assert xss.chip == "XL · 20w"
    tiny = b["Tiny"]
    assert "rt-bar--tiny" in tiny.classes and not tiny.show_name and tiny.chip is None
    assert page.summary is not None and [r.name for r in page.summary.rows] == ["Core", "Zespół", "All teams"]
    assert all(isinstance(c.load, str) for r in page.summary.rows for c in r.cells)
    assert Decimal(page.sections[1].teams[0].utilization) > 0
