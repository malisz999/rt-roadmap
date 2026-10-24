"""Validation acceptance tests (RS 11.2, 11.4; AT-14..AT-16, AT-32)."""

from __future__ import annotations

from pathlib import Path

from rtkit import run_rt

HEAD = """version: 1
roadmap:
  title: Validation
  today: 2027-01-15
  horizon: { start: 2027-01, end: 2027-06 }
sizes:
  S: 2
  M: 4
  L: 8
  XL: 13
subdomains:
  - id: channels
    name: Channels
    teams:
      - id: blik
        name: BLIK
        parallel_projects: 2
        capacity: { developers: 3 }
"""


def _validate(tmp: Path, text: str, *extra: str):
    src = tmp / "roadmap.yaml"
    src.write_text(text, encoding="utf-8")
    return run_rt(["validate", src.name, *extra], cwd=tmp)


AT14 = (
    HEAD
    + """projects:
  - name: Valid one
    team: blik
    size: M
    start: 2027-01
  - name: Card tokens
    team: blik2
    size: XXL
    start: 2027-13
"""
)


def test_at_14_all_errors_collected(tmp_path: Path) -> None:
    """AT-14: unknown team, undefined size and month 2027-13 -> exit 1; E030, E031, E013 all reported,
    sorted by line, with line and column."""
    r = _validate(tmp_path, AT14)
    assert r.code == 1, r.describe()
    errors = [(d.code, d.line, d.col) for d in r.diags if d.severity == "error"]
    assert errors == [("E030", 25, 11), ("E031", 26, 11), ("E013", 27, 12)], r.stderr
    e030 = next(d for d in r.diags if d.code == "E030")
    assert e030.file == "roadmap.yaml"
    assert '"blik2"' in e030.message and 'did you mean "blik"?' in e030.message
    e031 = next(d for d in r.diags if d.code == "E031")
    assert '"XXL"' in e031.message and "S, M, L, XL" in e031.message
    assert r.stdout == b""


def test_at_14_diagnostics_sorted(tmp_path: Path) -> None:
    """CLI-6: diagnostics sorted by file, line, then column (render as well as validate)."""
    src = tmp_path / "roadmap.yaml"
    src.write_text(AT14, encoding="utf-8")
    r = run_rt(["render", src.name], cwd=tmp_path)
    assert r.code == 1
    keys = [(d.line or 0, d.col or 0) for d in r.diags]
    assert keys == sorted(keys) and len(keys) >= 3
    assert not (tmp_path / "roadmap.html").exists()


AT15 = (
    HEAD.replace("parallel_projects: 2", "paralel_projects: 2")
    + """projects:
  - name: Valid one
    team: blik
    size: M
    start: 2027-01
"""
)


def test_at_15_unknown_key_suggestion(tmp_path: Path) -> None:
    """AT-15: team key paralel_projects -> E002 with 'did you mean "parallel_projects"?'."""
    r = _validate(tmp_path, AT15)
    assert r.code == 1, r.describe()
    e002 = [d for d in r.diags if d.code == "E002"]
    assert len(e002) == 1, r.stderr
    assert (e002[0].line, e002[0].col) == (17, 9)
    assert 'did you mean "parallel_projects"?' in e002[0].message
    assert '"paralel_projects"' in e002[0].message


AT16 = (
    HEAD
    + """projects:
  - name: Both kinds
    team: blik
    size: M
    ongoing: true
    start: 2027-01
"""
)


def test_at_16_size_and_ongoing(tmp_path: Path) -> None:
    """AT-16: project with both size and ongoing: true -> E032."""
    r = _validate(tmp_path, AT16)
    assert r.code == 1, r.describe()
    assert [d.code for d in r.diags if d.severity == "error"] == ["E032"], r.stderr
    assert '"Both kinds"' in next(d for d in r.diags if d.code == "E032").message


AT32 = (
    HEAD.replace(
        "        capacity: { developers: 3 }\n",
        "        capacity: { developers: 3 }\n"
        "      - id: ops\n        name: Ops\n        parallel_projects: 2\n        capacity: { developers: 1 }\n",
    )
    + """projects:
  - id: api-v2
    name: API v2
    team: blik
    size: L
    start: 2027-01
  - name: Web checkout
    team: blik
    size: M
    start: 2027-01
  - name: Maintenance
    team: blik
    size: S
    start: 2027-03
  - name: Maintenance
    team: ops
    size: S
    start: 2027-03
  - id: ops-run
    name: Ops maintenance
    team: ops
    ongoing: true
    start: 2027-01
  - name: Mobile release
    team: blik
    size: S
    depends_on: [Web chekout]
  - name: Audit
    team: ops
    size: S
    start: 2027-04
    depends_on: [Maintenance]
  - name: Ops audit
    team: ops
    size: S
    start: 2027-05
    depends_on: [Ops maintenance]
  - name: Early bird
    team: blik
    size: S
    start: 2027-05
    depends_on: [Late comer]
  - name: Late comer
    team: blik
    size: S
    start: 2027-06
  - id: api-v2
    name: API v3
    team: blik
    size: S
    start: 2027-06
"""
)


def test_at_32_dependency_errors(tmp_path: Path) -> None:
    """AT-32: depends_on typo, ambiguous name, dependency on ongoing, dependency on a later project
    and a duplicate project id -> exit 1; E034 (with did you mean), E035, E036, E037, E023."""
    r = _validate(tmp_path, AT32)
    assert r.code == 1, r.describe()
    errors = [(d.code, d.line, d.col) for d in r.diags if d.severity == "error"]
    assert sorted(errors, key=lambda e: (e[1], e[2])) == errors, "sorted by line"
    assert errors == [
        ("E034", 49, 18),
        ("E035", 54, 18),
        ("E036", 59, 18),
        ("E037", 64, 18),
        ("E023", 69, 9),
    ], r.stderr
    e034 = next(d for d in r.diags if d.code == "E034")
    assert 'did you mean "Web checkout"?' in e034.message
    assert '"Web chekout"' in e034.message
