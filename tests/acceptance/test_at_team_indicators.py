"""Team composition indicators (RS 7.13, 3.2 `team_norms`, 7.10, 8; AT-66 to AT-74).

DEV per slot = developers ÷ parallel_projects; DEV per QA = developers ÷ testers. Values more than 50 % away from
the median (3+ teams) or outside `team_norms` are marked: higher is worse (red ▲, and red `no QA`), lower is
better (green ▼). Marks never produce warnings.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rtkit import (
    DE,
    DOCS_FIXTURES,
    EX,
    MINIMAL,
    PE,
    WE,
    Rendered,
    assert_ok,
    load_yaml,
    norm_ws,
    render_fixture,
    run_rt,
)

EX_TEAMS = {  # developers, testers, DEV per slot, DEV per QA, flags (CR-2 section 2)
    "blik": (5, 2, 2.5, 2.5, []),
    "cards": (6, 2, 3.0, 3.0, []),  # 3.0 = median 2.0 + 50 %, on the edge: not marked
    "acq": (7, 3, 2.3333, 2.3333, []),
    "panel": (4, 1, 2.0, 4.0, []),
    "app": (4, 2, 2.0, 2.0, []),
    "ops": (3, 1, 1.5, 3.0, []),
    "sec": (2, 0, 2.0, None, ["no_qa"]),
}

NORMS = "team_norms:\n  devs_per_slot: { min: 2, max: 2.5 }\n  devs_per_qa: { max: 3 }\n"


@pytest.fixture(scope="module")
def ex_summary(tmp_path_factory: pytest.TempPathFactory) -> Rendered:
    return render_fixture(tmp_path_factory.mktemp("ex_ind"), EX, "--summary")


def _teams(plan: dict) -> dict[str, dict]:  # type: ignore[type-arg]
    return {t["id"]: t for t in plan["teams"]}


def _with_norms(tmp: Path, name: str = "ex-norms.yaml") -> Path:
    text = EX.read_text(encoding="utf-8").replace("\nsubdomains:", "\n" + NORMS + "subdomains:", 1)
    path = tmp / name
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- AT-66, AT-67


def test_at_66_team_values_and_flags(ex_summary: Rendered) -> None:
    """AT-66: every team's developers, testers, devs_per_slot, devs_per_qa equal CR-2 section 2; with the 50 %
    band only Cyberbezpieczeństwo is flagged (no_qa)."""
    assert_ok(ex_summary.result)
    teams = _teams(ex_summary.plan)
    got = {
        k: (t["developers"], t["testers"], t["devs_per_slot"], t["devs_per_qa"], t["indicator_flags"])
        for k, t in teams.items()
    }
    assert got == EX_TEAMS
    keys = list(ex_summary.plan["teams"][0])
    assert keys[keys.index("utilization") + 1 :] == [
        "developers",
        "testers",
        "devs_per_slot",
        "devs_per_qa",
        "indicator_flags",
    ]


def test_at_67_roadmap_values(ex_summary: Rendered) -> None:
    """AT-67: team_indicators right after teams, with all, median, band and source."""
    plan = ex_summary.plan
    keys = list(plan)
    assert keys.index("team_indicators") == keys.index("teams") + 1
    assert plan["team_indicators"] == {
        "devs_per_slot": {"all": 2.2143, "median": 2.0, "low": 1.0, "high": 3.0, "source": "median"},
        "devs_per_qa": {"all": 2.6364, "median": 2.75, "low": 1.375, "high": 4.125, "source": "median"},
    }


# --------------------------------------------------------------------------- AT-68


def test_at_68_label_chips_and_hooks(ex_summary: Rendered, tmp_path: Path) -> None:
    """AT-68: rt-team hooks equal the plan; Cyberbezpieczeństwo shows a red `no QA`; with norms Karty shows a
    red ▲ `3.0 DEV/slot` and Utrzymanie i wsparcie a green ▼ `1.5 DEV/slot`; a one-slot team keeps its three
    label rows (chips on the people line)."""
    doc = ex_summary.doc
    teams = _teams(ex_summary.plan)
    for el in doc.cssselect(".rt-team"):
        t = teams[el.get("data-team")]
        expect_slot = "" if t["devs_per_slot"] is None else f"{t['devs_per_slot']:.4f}"
        expect_qa = "" if t["devs_per_qa"] is None else f"{t['devs_per_qa']:.4f}"
        assert el.get("data-devs-per-slot") == expect_slot
        assert el.get("data-devs-per-qa") == expect_qa
        assert el.get("data-indicator-flags") == " ".join(t["indicator_flags"])
        chips = el.cssselect(".rt-team__label .rt-indicator")
        assert [c.get("data-indicator") for c in chips] == ["devs_per_slot", "devs_per_qa"]
    cards = doc.cssselect('.rt-team[data-team="cards"] .rt-indicator')
    assert norm_ws(cards[0].text_content()) == "3.0 DEV/slot" and cards[0].get("data-mark") == ""
    assert "(median 2.0, normal 1.0–3.0)" in cards[0].get("title")
    sec = doc.cssselect('.rt-team[data-team="sec"]')[0]
    assert "rt-team--compact" in sec.get("class")
    qa = sec.cssselect('.rt-indicator[data-indicator="devs_per_qa"]')[0]
    assert qa.get("data-mark") == "no_qa" and "no QA" in qa.text_content()
    assert qa.get("data-tone") == "bad" and "rt-indicator--bad" in qa.get("class")
    # red for worse, green for better (team_norms make both visible on EX)
    (tmp_path / "in").mkdir()
    normed = render_fixture(tmp_path, _with_norms(tmp_path / "in"), plan=False)
    assert_ok(normed.result)
    hi = normed.doc.cssselect('.rt-team[data-team="cards"] .rt-indicator[data-indicator="devs_per_slot"]')[0]
    lo = normed.doc.cssselect('.rt-team[data-team="ops"] .rt-indicator[data-indicator="devs_per_slot"]')[0]
    assert (norm_ws(hi.text_content()), hi.get("data-tone")) == ("▲3.0 DEV/slot", "bad")
    assert (norm_ws(lo.text_content()), lo.get("data-tone")) == ("▼1.5 DEV/slot", "good")
    assert "rt-indicator--bad" in hi.get("class") and "rt-indicator--good" in lo.get("class")
    assert hi.get("title").endswith("high (worse): above the norm 2.5")
    css = normed.css.replace(" ", "")
    assert "--bad:#B91C1C" in css and "--good:#166534" in css
    # one slot: chips sit on the people line; no extra row, so the 56 px label still fits
    assert not sec.cssselect(".rt-team__ratios")
    meta = sec.cssselect(".rt-team__meta")[0]
    assert "3 people · 1 parallel slot" in meta.text_content() and len(meta.cssselect(".rt-indicator")) == 2
    assert doc.cssselect('.rt-team[data-team="blik"] .rt-team__ratios .rt-indicator')
    # marked state also shown by a glyph, not by colour alone (OUT-26)
    for chip in [*doc.cssselect("[data-tone=bad]"), *normed.doc.cssselect("[data-tone=good]")]:
        assert chip.cssselect(".rt-indicator__glyph")[0].text_content() in ("▲", "▼", "!")


# --------------------------------------------------------------------------- AT-69


@pytest.mark.parametrize("fixture", [WE, DE, PE], ids=["WE", "DE", "PE"])
def test_at_69_other_fixtures(tmp_path: Path, fixture: Path) -> None:
    """AT-69: WE Alpha 2.0 / 4.0, Beta 2.0 / 2.0, no marks (2 teams); DE and PE no capacity: null values,
    no_capacity; the rest of each plan equals its expected file."""
    r = render_fixture(tmp_path, fixture)
    assert_ok(r.result)
    teams = _teams(r.plan)
    if fixture == WE:
        assert {k: (t["devs_per_slot"], t["devs_per_qa"], t["indicator_flags"]) for k, t in teams.items()} == {
            "alpha": (2.0, 4.0, []),
            "beta": (2.0, 2.0, []),
        }
        assert {k: v["source"] for k, v in r.plan["team_indicators"].items()} == {
            "devs_per_slot": None,
            "devs_per_qa": None,
        }
    else:
        for t in teams.values():
            assert (t["developers"], t["devs_per_slot"], t["devs_per_qa"]) == (None, None, None)
            assert t["indicator_flags"] == ["no_capacity"]
        assert r.plan["team_indicators"]["devs_per_slot"] == {
            "all": None,
            "median": None,
            "low": None,
            "high": None,
            "source": None,
        }
    expected = json.loads((DOCS_FIXTURES / fixture.name.replace(".yaml", ".expected.json")).read_text("utf-8"))
    actual = dict(r.plan)
    actual["rt_version"] = expected["rt_version"]
    assert actual == expected


# --------------------------------------------------------------------------- AT-70, AT-71


def test_at_70_team_norms(tmp_path: Path) -> None:
    """AT-70: with team_norms the bands come from the file; values on a bound are not marked."""
    src = _with_norms(tmp_path)
    r = run_rt(["render", src.name, "--plan", "p.json", "-o", "x.html"], cwd=tmp_path)
    assert_ok(r)
    plan = json.loads((tmp_path / "p.json").read_text(encoding="utf-8"))
    flags = {k: t["indicator_flags"] for k, t in _teams(plan).items() if t["indicator_flags"]}
    assert flags == {
        "cards": ["devs_per_slot_high"],
        "panel": ["devs_per_qa_high"],
        "ops": ["devs_per_slot_low"],
        "sec": ["no_qa"],
    }
    ind = plan["team_indicators"]
    assert (ind["devs_per_slot"]["low"], ind["devs_per_slot"]["high"], ind["devs_per_slot"]["source"]) == (
        2.0,
        2.5,
        "norm",
    )
    assert (ind["devs_per_qa"]["low"], ind["devs_per_qa"]["high"], ind["devs_per_qa"]["source"]) == (None, 3.0, "norm")
    assert r.codes() == ["W001"], r.stderr  # marks are not warnings


AT71 = """version: 1
roadmap: { title: AT-71 }
sizes: { S: 2 }
team_norms:
  devs_per_slots: { min: 1 }
  devs_per_slot: { min: 5, max: 2 }
  devs_per_qa: { min: "two" }
subdomains:
  - id: core
    name: Core
    teams:
      - { id: a, name: A, parallel_projects: 1, capacity: { developers: 2, testers: 1 } }
projects:
  - { name: P, team: a, size: S }
"""


def test_at_71_invalid_norms(tmp_path: Path) -> None:
    """AT-71: min > max, a non-number and a misspelt key -> exit 1; E012 at the max, E011, E002 with a hint."""
    (tmp_path / "at71.yaml").write_text(AT71, encoding="utf-8")
    r = run_rt(["validate", "at71.yaml"], cwd=tmp_path)
    assert r.code == 1, r.describe()
    found = {(d.code, d.line, d.col): d.message for d in r.diags}
    assert set(found) == {("E002", 5, 3), ("E012", 6, 33), ("E011", 7, 23)}, r.stderr
    assert found[("E002", 5, 3)].endswith('(did you mean "devs_per_slot"?)')
    assert "max must not be below min" in found[("E012", 6, 33)]


# --------------------------------------------------------------------------- AT-72, AT-73, AT-74


def test_at_72_summary(ex_summary: Rendered) -> None:
    """AT-72: KPI tiles DEV per slot 2.2 and DEV per QA 2.6; one rt-composition table with 7 team rows in
    subdomain and team order, then All teams, Median and the band (median ± 50 %)."""
    doc = ex_summary.doc
    kpis = {
        norm_ws(k.cssselect(".rt-kpi__value")[0].text_content()): norm_ws(k.text_content())
        for k in doc.cssselect(".rt-kpi")
    }
    assert any(text.startswith("2.2DEV per slot") for text in kpis.values()), kpis
    assert any(text.startswith("2.6DEV per QA") for text in kpis.values()), kpis
    (table,) = doc.cssselect(".rt-summary .rt-composition")
    rows = table.cssselect(".rt-composition-row")
    assert [r.get("data-team") for r in rows if r.get("data-team")] == list(EX_TEAMS)
    labels = [norm_ws(r.cssselect("th")[0].text_content()) for r in rows if not r.get("data-team")]
    assert labels == ["All teams", "Median", "Normal range"]
    panel = table.cssselect('.rt-composition-row[data-team="panel"] td')
    assert [norm_ws(td.text_content()) for td in panel] == ["4", "1", "2", "2.0", "4.0", ""]
    sec = table.cssselect('.rt-composition-row[data-team="sec"] td')
    assert [norm_ws(td.text_content()) for td in sec] == ["2", "0", "1", "2.0", "!no QA", "no QA"]
    assert sec[4].cssselect(".rt-indicator")[0].get("data-tone") == "bad"


def test_at_72_no_summary_no_table(tmp_path: Path) -> None:
    """Without --summary there is no composition table, but the label chips are always shown."""
    r = render_fixture(tmp_path, EX)
    assert_ok(r.result)
    assert not r.doc.cssselect(".rt-composition") and r.doc.cssselect(".rt-indicator")


def test_at_73_no_new_warnings(tmp_path: Path) -> None:
    """AT-73: EX keeps exactly its one warning; --strict behaves as before."""
    src = tmp_path / EX.name
    src.write_bytes(EX.read_bytes())
    v = run_rt(["validate", src.name], cwd=tmp_path)
    assert v.code == 0 and [(d.code, d.line) for d in v.diags] == [("W001", 259)], v.stderr
    s = run_rt(["render", src.name, "--strict", "-o", "s.html"], cwd=tmp_path)
    assert s.code == 1 and not (tmp_path / "s.html").exists()
    n = _with_norms(tmp_path)
    assert [d.code for d in run_rt(["validate", n.name], cwd=tmp_path).diags] == ["W001"]


def test_at_74_schema(tmp_path: Path) -> None:
    """AT-74: rt schema accepts team_norms and still validates every fixture."""
    jsonschema = pytest.importorskip("jsonschema")
    r = run_rt(["schema"], cwd=tmp_path)
    assert_ok(r)
    validator = jsonschema.Draft202012Validator(json.loads(r.stdout.decode("utf-8")))
    for fixture in (WE, DE, EX, MINIMAL, PE, _with_norms(tmp_path)):
        errors = [e.message for e in validator.iter_errors(load_yaml(fixture.read_bytes()))]
        assert not errors, (fixture.name, errors)
    doc = load_yaml(_with_norms(tmp_path, "n2.yaml").read_bytes())
    assert list(validator.iter_errors({**doc, "team_norms": {"devs_per_slots": {"min": 1}}}))
    assert list(validator.iter_errors({**doc, "team_norms": {"devs_per_qa": {"min": "two"}}}))
    assert list(validator.iter_errors({**doc, "team_norms": {"devs_per_qa": {"max": -1}}}))
