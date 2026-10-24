"""Model and scheduling rules of RS 3 and 4 not covered by a single AT (IN-1, IN-8, IN-9, SC-9, SC-12)."""

from __future__ import annotations

import unicodedata
from pathlib import Path

from rtkit import assert_ok, plan_project, run_rt

HEAD = """version: 1
roadmap:
  title: Rules
  today: 2027-03-10
sizes:
  S: 2
  M: 4
subdomains:
  - id: core
    name: Core
    teams:
      - id: blik
        name: BLIK
        parallel_projects: 2
        capacity: { developers: 2 }
projects:
"""


def _run(tmp: Path, text: str, *args: str):
    (tmp / "in.yaml").write_text(text, encoding="utf-8")
    return run_rt(["validate", "in.yaml", "--plan", "-", *args], cwd=tmp)


def test_sc12_anchor_is_month_of_today(tmp_path: Path) -> None:
    """SC-12: without a horizon start the auto-start anchor is the 1st of today's month;
    SC-9: the automatic horizon starts at the actual start of auto-start projects."""
    import json

    r = _run(tmp_path, HEAD + "  - name: Auto\n    team: blik\n    size: M\n")
    assert_ok(r)
    plan = json.loads(r.stdout)
    p = plan_project(plan, 1)
    assert (p["start"], p["requested_start"], p["flags"]) == ("2027-03-01", None, ["auto_start"])
    assert plan["horizon"]["start"] == "2027-03" and plan["horizon"]["end"] == "2027-08"
    r2 = _run(tmp_path, HEAD + "  - name: Auto\n    team: blik\n    size: M\n", "--today", "2027-05-31")
    assert json.loads(r2.stdout)["projects"][0]["start"] == "2027-05-01"
    r3 = _run(tmp_path, HEAD + "  - name: Auto\n    team: blik\n    size: M\n", "--from", "2027-01")
    assert json.loads(r3.stdout)["projects"][0]["start"] == "2027-01-01"


def test_in8_duplicate_name_after_nfc(tmp_path: Path) -> None:
    """IN-8: name uniqueness is checked after NFC normalisation (E022)."""
    nfc = "Płatności zwrotne"
    nfd = unicodedata.normalize("NFD", nfc)
    text = HEAD + f"  - name: {nfc}\n    team: blik\n    size: S\n    start: 2027-03\n"
    text += f"  - name: {nfd}\n    team: blik\n    size: S\n    start: 2027-04\n"
    r = _run(tmp_path, text)
    assert r.code == 1, r.describe()
    assert [(d.code, d.line, d.col) for d in r.diags if d.severity == "error"] == [("E022", 21, 11)]


def test_in1_yaml_12_booleans_stay_strings(tmp_path: Path) -> None:
    """IN-1: yes/no/on/off/NO stay strings (names, ids)."""
    import json

    text = HEAD.replace("id: blik", "id: off").replace("name: BLIK", "name: NO")
    for i, name in enumerate(["yes", "no", "on", "off", "NO", "Off"]):
        text += f"  - name: {name}\n    team: off\n    size: S\n    start: 2027-0{i + 1}\n"
    r = _run(tmp_path, text)
    assert_ok(r)
    plan = json.loads(r.stdout)
    assert [p["name"] for p in plan["projects"]] == ["yes", "no", "on", "off", "NO", "Off"]
    assert {p["team"] for p in plan["projects"]} == {"off"}


def test_in9_depends_on_forms(tmp_path: Path) -> None:
    """IN-9: depends_on may be a single string; an empty list equals no dependencies."""
    import json

    text = HEAD + (
        "  - name: First\n    team: blik\n    size: M\n    start: 2027-03\n"
        "  - name: Second\n    team: blik\n    size: S\n    start: 2027-03\n    depends_on: First\n"
        "  - name: Third\n    team: blik\n    size: S\n    start: 2027-03\n    depends_on: []\n"
    )
    r = _run(tmp_path, text)
    assert_ok(r)
    plan = json.loads(r.stdout)
    assert plan_project(plan, 2)["depends_on"] == [1]
    assert plan_project(plan, 2)["start"] == "2027-03-29"
    assert plan_project(plan, 3)["depends_on"] == []
    assert plan_project(plan, 3)["start"] == "2027-03-01"


def test_in2_quoted_and_unquoted_months(tmp_path: Path) -> None:
    """IN-2: months and dates may be quoted or unquoted."""
    import json

    text = HEAD.replace("today: 2027-03-10", "today: '2027-03-10'") + (
        "  - name: Quoted\n    team: blik\n    size: S\n    start: '2027-04'\n"
        "  - name: Unquoted\n    team: blik\n    size: S\n    start: 2027-04\n"
    )
    r = _run(tmp_path, text)
    assert_ok(r)
    plan = json.loads(r.stdout)
    assert plan["today"] == "2027-03-10"
    assert [p["start"] for p in plan["projects"]] == ["2027-04-01", "2027-04-01"]
