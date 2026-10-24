"""Scheduling and colour acceptance tests (RS 11.1, 11.4; AT-07..AT-12, AT-27, AT-28, AT-30, AT-31)."""

from __future__ import annotations

from pathlib import Path

from rtkit import (
    DE,
    DE_PLAN,
    WE,
    Rendered,
    assert_ok,
    copy_fixture,
    load_json,
    plan_project,
    render_fixture,
    run_rt,
)

DE_EXPECTED = load_json(DE_PLAN)


def _flags(p: dict) -> list[str]:
    return p["flags"]


def test_at_07_overflow_mode(tmp_path: Path) -> None:
    """AT-07: WE --on-conflict overflow."""
    r = render_fixture(tmp_path, WE, "--on-conflict", "overflow")
    assert_ok(r.result)
    plan = r.plan
    assert plan["on_conflict"] == "overflow"
    rep, big = plan_project(plan, 3), plan_project(plan, 9)
    assert (rep["team"], rep["lane"], rep["start"]) == ("alpha", 3, "2027-01-01")
    assert (big["team"], big["lane"], big["start"]) == ("beta", 2, "2027-03-01")
    assert "over_capacity" in rep["flags"] and "over_capacity" in big["flags"]
    assert rep["overflow"] is True and big["overflow"] is True
    hot = plan_project(plan, 4)
    assert (hot["lane"], hot["start"], hot["end"]) == (2, "2027-02-01", "2027-02-15")
    assert plan_project(plan, 5)["lane"] == 1  # Maintenance
    fraud = plan_project(plan, 6)
    assert (fraud["lane"], fraud["start"], fraud["end"]) == (2, "2027-03-01", "2027-03-29")
    w011 = [w for w in plan["warnings"] if w["code"] == "W011"]
    assert [(w["line"], w["column"]) for w in w011] == [(38, 5), (62, 5)]
    assert sorted((d.line, d.col) for d in r.result.diags if d.code == "W011") == [(38, 5), (62, 5)]
    teams = {t["id"]: t for t in plan["teams"]}
    assert teams["alpha"]["overflow_lanes"] == 1 and teams["beta"]["overflow_lanes"] == 1
    # no project is delayed in overflow mode without dependencies
    assert all(p["delay_days"] == 0 for p in plan["projects"])


def test_at_08_error_mode(tmp_path: Path) -> None:
    """AT-08: WE --on-conflict error -> exit 3; E061 for Reporting and Big bang; no HTML written."""
    src = copy_fixture(WE, tmp_path)
    r = run_rt(["render", src.name, "--on-conflict", "error"], cwd=tmp_path)
    assert r.code == 3, r.describe()
    e061 = [d for d in r.diags if d.code == "E061"]
    assert sorted((d.line, d.col) for d in e061) == [(38, 5), (62, 5)], r.stderr
    assert all(d.severity == "error" for d in e061)
    assert any('"Reporting"' in d.message for d in e061)
    assert any('"Big bang"' in d.message for d in e061)
    assert not (tmp_path / "scheduling-worked-example.html").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == [src.name], "nothing else may be written"
    assert r.stdout == b""


AT09 = """version: 1
roadmap:
  title: Unschedulable
  today: 2027-01-15
sizes:
  M: 4
subdomains:
  - id: core
    name: Core
    teams:
      - id: solo
        name: Solo
        parallel_projects: 1
        capacity: { developers: 1 }
projects:
  - name: Keep the lights on
    team: solo
    ongoing: true
    start: 2027-01
  - name: New feature
    team: solo
    size: M
    start: 2027-02
"""


def test_at_09_unschedulable(tmp_path: Path) -> None:
    """AT-09: 1 slot, ongoing project from 2027-01, then an M project from 2027-02 -> exit 3, E060."""
    src = tmp_path / "at09.yaml"
    src.write_text(AT09, encoding="utf-8")
    r = run_rt(["render", src.name], cwd=tmp_path)
    assert r.code == 3, r.describe()
    e060 = [d for d in r.diags if d.code == "E060"]
    assert len(e060) == 1, r.stderr
    assert '"New feature"' in e060[0].message
    assert (e060[0].file, e060[0].line, e060[0].col) == ("at09.yaml", 20, 5)
    assert not (tmp_path / "at09.html").exists()
    assert r.stdout == b""


def test_at_10_neighbours_have_distinct_colours(ex_render: Rendered) -> None:
    """AT-10: rt render EX --plan p.json -> for every pair in each neighbors list, colours differ; no W007."""
    assert_ok(ex_render.result)
    plan = ex_render.plan
    by_seq = {p["seq"]: p for p in plan["projects"]}
    pairs = 0
    for p in plan["projects"]:
        for n in p["neighbors"]:
            assert p["seq"] in by_seq[n]["neighbors"], "neighbour relation must be symmetric"
            assert p["color_index"] != by_seq[n]["color_index"], (p["name"], by_seq[n]["name"])
            pairs += 1
        if p["visible"] is not None:
            assert p["color_index"] is not None and 0 <= p["color_index"] <= 9
    assert pairs > 0
    assert "W007" not in [w["code"] for w in plan["warnings"]]
    assert "W007" not in ex_render.result.codes()
    # the pinned colour in EX (Tokenizacja sieciowa, color: violet)
    tok = next(p for p in plan["projects"] if p["name"] == "Tokenizacja sieciowa")
    assert (tok["color_index"], tok["color_name"], tok["color_fill"]) == (6, "violet", "#DDD6FE")


def test_at_11_pinned_colour(tmp_path: Path) -> None:
    """AT-11: a project with color: sky has color_index 4 whatever its neighbours; neighbours avoid sky.

    Reporting (6 neighbours) is pinned to sky; without the pin Fraud rules, one of its neighbours,
    would get sky (expected plan), so the neighbours must now avoid it."""
    text = WE.read_text(encoding="utf-8").replace(
        "  - name: Reporting\n    team: alpha\n    size: M\n    start: 2027-01\n",
        "  - name: Reporting\n    team: alpha\n    size: M\n    start: 2027-01\n    color: sky\n",
    )
    assert "color: sky" in text
    (tmp_path / "src").mkdir()
    src = tmp_path / "src" / "we-sky.yaml"
    src.write_text(text, encoding="utf-8")
    r = render_fixture(tmp_path, src)
    assert_ok(r.result)
    rep = plan_project(r.plan, 3)
    assert (rep["color_index"], rep["color_name"], rep["color_fill"]) == (4, "sky", "#BAE6FD")
    assert rep["neighbors"] == [1, 2, 4, 5, 6, 8]
    for n in rep["neighbors"]:
        assert plan_project(r.plan, n)["color_index"] != 4
    assert r.bars[3].get("data-color-index") == "4"
    assert "W007" not in r.result.codes() and "W009" not in r.result.codes()


def test_at_12_horizon_clipping(tmp_path: Path) -> None:
    """AT-12: WE --from 2027-02 --to 2027-04: Core API and Reporting clipped_left (W002 each);
    Big bang clipped_right (W003); Onboarding hidden (W004), not drawn but present in plan."""
    r = render_fixture(tmp_path, WE, "--from", "2027-02", "--to", "2027-04")
    assert_ok(r.result)
    plan = r.plan
    assert plan["horizon"] == {
        "start": "2027-02",
        "end": "2027-04",
        "start_date": "2027-02-01",
        "end_exclusive": "2027-05-01",
        "days": 89,
    }
    assert "clipped_left" in plan_project(plan, 1)["flags"]
    assert "clipped_left" in plan_project(plan, 3)["flags"]
    assert "clipped_right" in plan_project(plan, 9)["flags"]
    onb = plan_project(plan, 2)
    assert onb["flags"] == ["hidden"]
    assert onb["visible"] is None and onb["color_index"] is None and onb["color_name"] is None
    assert (onb["start"], onb["end"], onb["lane"]) == ("2027-01-01", "2027-01-29", 2)
    assert plan_project(plan, 1)["visible"] == {"start": "2027-02-01", "end": "2027-02-26"}
    assert plan_project(plan, 9)["visible"] == {"start": "2027-04-29", "end": "2027-05-01"}
    # warnings: exact codes and project positions
    got = sorted((d.code, d.line, d.col) for d in r.result.diags if d.code in ("W002", "W003", "W004"))
    assert got == [("W002", 30, 5), ("W002", 38, 5), ("W003", 62, 5), ("W004", 34, 5)]
    # HTML: Onboarding not drawn
    assert 2 not in r.bars
    assert set(r.bars) == {1, 3, 4, 5, 6, 7, 8, 9}
    assert "clipped_left" in (r.bars[1].get("data-flags") or "").split()


def test_at_27_delay_reasons(de_render: Rendered) -> None:
    """AT-27: data-delay-reason Web checkout dependency, Load testing dependency, Release audit
    dependency+capacity; three W001, each message ending with its reason."""
    assert_ok(de_render.result)
    bars = de_render.bars
    assert bars[2].get("data-delay-reason") == "dependency"
    assert bars[6].get("data-delay-reason") == "dependency"
    assert bars[8].get("data-delay-reason") == "dependency+capacity"
    w001 = sorted((d for d in de_render.result.diags if d.code == "W001"), key=lambda d: d.line or 0)
    assert [(d.line, d.col) for d in w001] == [(41, 5), (56, 5), (66, 5)]
    assert w001[0].message.endswith("waiting for dependencies")
    assert w001[1].message.endswith("waiting for dependencies")
    assert w001[2].message.endswith('waiting for dependencies, then no free slot in team "ops"')
    assert '"Web checkout"' in w001[0].message and "56 days" in w001[0].message


def test_at_28_auto_start(de_render: Rendered) -> None:
    """AT-28: Design system and Mobile release: data-requested="auto", flag auto_start, no W001;
    Design system backfills Web lane 1 from 2027-01-01."""
    bars = de_render.bars
    for seq in (3, 4):
        assert bars[seq].get("data-requested") == "auto"
        assert "auto_start" in (bars[seq].get("data-flags") or "").split()
        assert (bars[seq].get("data-delay-days") or "") == "0"
    w001_lines = {d.line for d in de_render.result.diags if d.code == "W001"}
    assert not w001_lines & {46, 49}
    ds = bars[3]
    assert (ds.get("data-team"), ds.get("data-lane"), ds.get("data-start")) == ("web", "1", "2027-01-01")
    plan3 = plan_project(de_render.plan, 3)
    assert plan3["requested_start"] is None and plan3["delay_reason"] is None


def test_at_30_from_moves_anchor(tmp_path: Path) -> None:
    """AT-30: DE --from 2027-02: anchor 2027-02-01: Design system Web lane 2 2027-02-01..2027-03-01;
    Ops maintenance from 2027-02-01; API v2 clipped_left (W002); other projects as in AT-26."""
    r = render_fixture(tmp_path, DE, "--from", "2027-02")
    assert_ok(r.result)
    plan = r.plan
    ds = plan_project(plan, 3)
    assert (ds["team"], ds["lane"], ds["start"], ds["end"]) == ("web", 2, "2027-02-01", "2027-03-01")
    assert ds["earliest_start"] == "2027-02-01"
    ops = plan_project(plan, 5)
    assert ops["start"] == "2027-02-01" and ops["end"] is None
    api = plan_project(plan, 1)
    assert "clipped_left" in api["flags"]
    assert [(d.line, d.col) for d in r.result.diags if d.code == "W002"] == [(36, 5)]
    for seq in (1, 2, 4, 6, 7, 8):
        exp = plan_project(DE_EXPECTED, seq)
        got = plan_project(plan, seq)
        for key in ("start", "end", "lane", "delay_days", "delay_reason"):
            assert got[key] == exp[key], (exp["name"], key)


def test_at_31_overflow_with_dependencies(tmp_path: Path) -> None:
    """AT-31: DE --on-conflict overflow: Release audit Ops lane 3 from 2027-03-26, delayed
    (dependency, 53 days) and over_capacity, W011; auto-start projects unchanged from AT-26."""
    r = render_fixture(tmp_path, DE, "--on-conflict", "overflow")
    assert_ok(r.result)
    plan = r.plan
    ra = plan_project(plan, 8)
    assert (ra["team"], ra["lane"], ra["start"]) == ("ops", 3, "2027-03-26")
    assert ra["flags"] == ["delayed", "over_capacity"]
    assert (ra["delay_reason"], ra["delay_days"]) == ("dependency", 53)
    assert [(d.line, d.col) for d in r.result.diags if d.code == "W011"] == [(66, 5)]
    for seq in (3, 4, 5):
        exp = plan_project(DE_EXPECTED, seq)
        got = plan_project(plan, seq)
        for key in ("start", "end", "lane", "flags", "overflow"):
            assert got[key] == exp[key], (exp["name"], key)
