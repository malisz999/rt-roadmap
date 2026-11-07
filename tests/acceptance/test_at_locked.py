"""Locked projects (CR-3; RS 3.2, SC-14, SC-15, 4.6, OUT-35 to OUT-37, PL-9; AT-75 to AT-86).

A locked project's start month has been promised. Locked projects are placed first, exactly at their start, and
never moved; unlocked projects go around them. A promise that cannot be kept stays at its date, is flagged
`at_risk` and gives W015.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rtkit import (
    DE,
    DOCS_FIXTURES,
    EX,
    LE,
    LE_PLAN,
    MINIMAL,
    PE,
    WE,
    Rendered,
    assert_ok,
    copy_fixture,
    load_json,
    load_yaml,
    mask_version,
    norm_ws,
    project_by_name,
    render_fixture,
    run_rt,
)

LOCKED = ("Partner launch", "Mobile release", "Data migration", "Audit")


@pytest.fixture(scope="module")
def le(tmp_path_factory: pytest.TempPathFactory) -> Rendered:
    return render_fixture(tmp_path_factory.mktemp("le"), LE, "--summary")


def _seq(plan: dict, name: str) -> int:  # type: ignore[type-arg]
    return int(project_by_name(plan, name)["seq"])


# --------------------------------------------------------------------------- AT-75 to AT-78: scheduling


def test_at_75_lock_plan_is_golden(le: Rendered) -> None:
    """AT-75: the LE plan equals lock-example.expected.json byte for byte (ignoring rt_version)."""
    assert_ok(le.result)
    assert mask_version(le.plan_bytes) == mask_version(LE_PLAN.read_bytes())


def test_at_76_locked_projects_are_placed_first(le: Rendered) -> None:
    """AT-76: Partner launch keeps 2027-02-01 in Alpha lane 1 although written after Core API; Core API yields."""
    partner = project_by_name(le.plan, "Partner launch")
    assert (partner["lane"], partner["start"], partner["end"]) == (1, "2027-02-01", "2027-03-01")
    assert partner["locked"] is True and partner["promised_to"] == "Partner X"
    assert partner["delay_days"] == 0 and partner["lock_risk"] is None and partner["flags"] == ["locked"]
    core = project_by_name(le.plan, "Core API")
    assert core["seq"] < partner["seq"]
    assert (core["lane"], core["start"], core["delay_days"], core["delay_reason"]) == (1, "2027-03-01", 59, "capacity")
    assert core["locked"] is False and core["promised_to"] is None and core["lock_risk"] is None
    keys = list(core)
    assert keys[keys.index("ongoing") + 1 : keys.index("ongoing") + 3] == ["locked", "promised_to"]
    assert keys[keys.index("delay_reason") + 1] == "lock_risk"


def test_at_77_dependency_risk(le: Rendered) -> None:
    """AT-77: Mobile release keeps 1 March although Core API now ends 26 April; at risk (dependency), W015."""
    mobile = project_by_name(le.plan, "Mobile release")
    assert (mobile["start"], mobile["earliest_start"], mobile["lock_risk"]) == (
        "2027-03-01",
        "2027-04-26",
        "dependency",
    )
    assert mobile["flags"] == ["at_risk", "locked"] and mobile["delay_days"] == 0 and mobile["delay_reason"] is None
    w015 = [d for d in le.result.diags if d.code == "W015" and '"Mobile release"' in d.message]
    assert [d.message for d in w015] == [
        'locked project "Mobile release" cannot keep its promised start 2027-03-01: '
        'depends on "Core API", which ends 2027-04-26'
    ]


def test_at_78_capacity_risk(le: Rendered) -> None:
    """AT-78: Audit keeps 1 March in Beta's overflow lane 3: capacity risk, W015 and no W011."""
    audit = project_by_name(le.plan, "Audit")
    assert (audit["lane"], audit["overflow"], audit["start"], audit["lock_risk"]) == (3, True, "2027-03-01", "capacity")
    assert audit["flags"] == ["at_risk", "locked", "over_capacity"]
    assert le.result.codes() == ["W001", "W015", "W015", "W001"]
    msg = [d.message for d in le.result.diags if d.code == "W015" and '"Audit"' in d.message]
    assert msg == [
        'locked project "Audit" cannot keep its promised start 2027-03-01: all 2 slots of team "beta" are taken '
        "by locked projects; shown in overflow lane +1"
    ]
    reporting = project_by_name(le.plan, "Reporting")
    assert (reporting["lane"], reporting["start"], reporting["delay_days"]) == (2, "2027-03-15", 14)
    polish = project_by_name(le.plan, "Polish")
    assert (polish["lane"], polish["start"], polish["flags"]) == (1, "2027-03-29", ["auto_start"])


# --------------------------------------------------------------------------- AT-79, AT-80: other modes


def test_at_79_error_mode_reports_unlocked_conflicts_only(tmp_path: Path) -> None:
    """AT-79: --on-conflict error: exit 3, E061 for Core API and Reporting only; no HTML."""
    src = copy_fixture(LE, tmp_path)
    r = run_rt(["render", src.name, "--on-conflict", "error"], cwd=tmp_path)
    assert r.code == 3, r.describe()
    errors = [(d.code, d.message.split('"')[1]) for d in r.diags if d.severity == "error"]
    assert errors == [("E061", "Core API"), ("E061", "Reporting")]
    assert not (tmp_path / "lock-example.html").exists()


def test_at_80_overflow_mode(tmp_path: Path) -> None:
    """AT-80: overflow mode: Core API from 1 January in Alpha lane 2 (W011), Reporting in Beta lane 4; locked
    projects keep their dates; Mobile release on track, Audit at risk."""
    r = render_fixture(tmp_path, LE, "--on-conflict", "overflow")
    assert_ok(r.result)
    core = project_by_name(r.plan, "Core API")
    assert (core["lane"], core["start"], core["flags"]) == (2, "2027-01-01", ["over_capacity"])
    reporting = project_by_name(r.plan, "Reporting")
    assert (reporting["lane"], reporting["start"]) == (4, "2027-03-01")
    starts = {n: project_by_name(r.plan, n)["start"] for n in LOCKED}
    assert starts == {
        "Partner launch": "2027-02-01",
        "Mobile release": "2027-03-01",
        "Data migration": "2027-03-01",
        "Audit": "2027-03-01",
    }
    assert project_by_name(r.plan, "Mobile release")["lock_risk"] is None
    assert project_by_name(r.plan, "Audit")["lock_risk"] == "capacity"
    assert r.result.codes() == ["W011", "W015", "W011"]


# --------------------------------------------------------------------------- AT-81: validation


def test_at_81_lock_input_errors(tmp_path: Path) -> None:
    """AT-81: E050, E051, E011, E012 and E002 "did you mean "locked"", all positioned."""
    (tmp_path / "bad.yaml").write_text(
        "version: 1\nroadmap: {title: T}\nsizes: {S: 2}\n"
        "subdomains: [{id: a, name: A, teams: [{id: t, name: T, parallel_projects: 1}]}]\n"
        "projects:\n"
        "  - {name: A, team: t, size: S, locked: true}\n"
        "  - {name: B, team: t, size: S, start: 2027-01, promised_to: X}\n"
        "  - {name: C, team: t, size: S, start: 2027-01, locked: 1}\n"
        f"  - {{name: D, team: t, size: S, start: 2027-01, locked: true, promised_to: {'x' * 101}}}\n"
        "  - {name: E, team: t, size: S, start: 2027-01, lock: true}\n",
        encoding="utf-8",
    )
    r = run_rt(["validate", "bad.yaml"], cwd=tmp_path)
    assert r.code == 1, r.describe()
    assert [(d.line, d.code) for d in r.diags] == [(6, "E050"), (7, "E051"), (8, "E011"), (9, "E012"), (10, "E002")]
    msgs = [d.message for d in r.diags]
    assert msgs[0] == 'project "A" is locked but has no start; a locked project needs a start month'
    assert msgs[1] == 'project "B" has promised_to but is not locked; add locked: true or remove promised_to'
    assert msgs[2] == '"locked" must be true or false, got 1'
    assert 'did you mean "locked"' in msgs[4]


# --------------------------------------------------------------------------- AT-82, AT-83: HTML


def test_at_82_locked_bars_legend_and_tooltips(le: Rendered) -> None:
    """AT-82: framed, padlocked bars; at-risk bars red; data-lock-risk equals the plan; legend; tooltips."""
    doc, plan = le.doc, le.plan
    by_seq = {p["seq"]: p for p in plan["projects"]}
    for seq, bar in le.bars.items():
        p = by_seq[seq]
        classes = bar.get("class").split()
        assert ("rt-bar--locked" in classes) is p["locked"]
        assert ("rt-bar--risk" in classes) is (p["lock_risk"] is not None)
        assert len(bar.cssselect(".rt-bar__lock")) == (1 if p["locked"] else 0)
        assert bar.get("data-lock-risk") == (p["lock_risk"] or "")
        assert bar.get("data-flags") == " ".join(p["flags"])
    audit = le.bars[_seq(plan, "Audit")]
    assert "rt-bar--over" not in audit.get("class").split()  # one outline: the at-risk frame
    legend = norm_ws(doc.cssselect(".rt-legend")[0].text_content())
    assert "Locked: date promised" in legend and "Promise at risk" in legend
    partner = le.bars[_seq(plan, "Partner launch")].get("title").splitlines()
    assert "Locked: promised to Partner X · start fixed 1 Feb 2027" in partner
    data = le.bars[_seq(plan, "Data migration")].get("title").splitlines()
    assert "Locked: start fixed 1 Mar 2027" in data
    mobile = le.bars[_seq(plan, "Mobile release")].get("title").splitlines()
    assert "Promise at risk: depends on Core API (last day 25 Apr 2027)" in mobile
    assert "Promise at risk: no free slot in team Beta (overflow lane +1)" in audit.get("title").splitlines()
    css = le.css.replace(" ", "")
    assert ".rt-bar--locked{outline:2pxsolidvar(--lock)" in css and "--lock:#0F172A" in css


def test_at_83_summary_commitments(le: Rendered) -> None:
    """AT-83: KPI tiles Locked 4 and At risk 2; one Commitments table with 4 rows in file order."""
    kpis = {norm_ws(k.text_content()) for k in le.doc.cssselect(".rt-kpi")}
    assert {"4Lockedpromised", "2At riskpromises"} <= kpis, kpis
    tables = le.doc.cssselect("table.rt-commitments")
    assert len(tables) == 1
    rows = tables[0].cssselect("tr.rt-commitment")
    plan = le.plan
    assert [int(r.get("data-seq")) for r in rows] == [_seq(plan, n) for n in LOCKED]
    assert [r.get("data-status") for r in rows] == ["on_track", "at_risk", "on_track", "at_risk"]
    first = [norm_ws(c.text_content()) for c in rows[0].cssselect("th, td")]
    assert first == ["Partner launch", "Alpha", "–", "Partner X", "1 Feb 2027", "28 Feb 2027", "On track"]


# --------------------------------------------------------------------------- AT-84: compatibility


@pytest.mark.parametrize("fixture", [EX, WE, DE, PE], ids=["EX", "WE", "DE", "PE"])
def test_at_84_files_without_locks_are_unchanged(fixture: Path, tmp_path: Path) -> None:
    """AT-84: no lock symbol, no locked bar; every project locked false, promised_to and lock_risk null."""
    r = render_fixture(tmp_path, fixture, "--summary")
    assert_ok(r.result)
    assert not r.doc.cssselect(".rt-bar--locked, .rt-sym--locked, .rt-commitments")
    assert not [k for k in r.doc.cssselect(".rt-kpi") if "Locked" in k.text_content()]
    for p in r.plan["projects"]:
        assert (p["locked"], p["promised_to"], p["lock_risk"]) == (False, None, None)
        assert "locked" not in p["flags"] and "at_risk" not in p["flags"]
    assert "W015" not in r.result.codes()


# --------------------------------------------------------------------------- AT-85: rt convert


def test_at_85_convert_locked_columns(tmp_path: Path) -> None:
    """AT-85: locked cells 1/0/tak/x and promised_to; CV-18 key order; a locked row without start is E050."""
    src = LE.read_text(encoding="utf-8")
    (tmp_path / "base.yaml").write_text(src[: src.index("\nprojects:")] + "\nprojects: []\n", encoding="utf-8")
    mapping = "Projekt=name,Rozmiar=size,Zespół=team,Zablokowany=locked,Obiecany dla=promised_to"
    (tmp_path / "ok.csv").write_text(
        "Projekt;Rozmiar;Zespół;Start;Zablokowany;Obiecany dla\n"
        "A;M;alpha;2027-02;1;Partner X\nB;S;beta;2027-03;0;\nC;S;beta;2027-03;tak;\nD;S;beta;01.03.2027;x;Regulator\n",
        encoding="utf-8",
    )
    r = run_rt(["convert", "ok.csv", "--base", "base.yaml", "--map", mapping], cwd=tmp_path)
    assert_ok(r)
    out = load_yaml(r.stdout)
    assert [p.get("locked") for p in out["projects"]] == [True, None, True, True]
    assert [p.get("promised_to") for p in out["projects"]] == ["Partner X", None, None, "Regulator"]
    text = r.stdout.decode("utf-8")
    assert (
        "  - name: A\n    team: alpha\n    start: 2027-02\n    size: M\n    locked: true\n    promised_to: Partner X\n"
        in text
    )
    (tmp_path / "bad.csv").write_text("name,size,team,start,locked\nE,S,beta,,1\n", encoding="utf-8")
    bad = run_rt(["convert", "bad.csv", "--base", "base.yaml"], cwd=tmp_path)
    assert bad.code == 1 and bad.stdout == b""
    assert [(d.file, d.line, d.col, d.code) for d in bad.diags] == [("bad.csv", 2, 5, "E050")]


# --------------------------------------------------------------------------- AT-86: schema


def test_at_86_schema_accepts_locks(tmp_path: Path) -> None:
    """AT-86: the schema accepts locked and promised_to and still validates every fixture, LE included."""
    jsonschema = pytest.importorskip("jsonschema")
    r = run_rt(["schema"], cwd=tmp_path)
    assert_ok(r)
    validator = jsonschema.Draft202012Validator(json.loads(r.stdout.decode("utf-8")))
    for fixture in (LE, PE, WE, DE, EX, MINIMAL, *sorted(DOCS_FIXTURES.glob("*.yaml"))):
        errors = [e.message for e in validator.iter_errors(load_yaml(fixture.read_bytes()))]
        assert not errors, (fixture.name, errors)
    le_doc = load_yaml(LE.read_bytes())
    first = next(p for p in le_doc["projects"] if p.get("locked"))
    no_start = {k: v for k, v in first.items() if k != "start"}
    assert list(validator.iter_errors(dict(le_doc, projects=[no_start]))), "locked needs start"
    orphan = {k: v for k, v in first.items() if k != "locked"}
    assert list(validator.iter_errors(dict(le_doc, projects=[orphan]))), "promised_to needs locked: true"
    assert list(validator.iter_errors(dict(le_doc, projects=[{**first, "locked": 1}])))
    assert load_json(LE_PLAN)["projects"]
