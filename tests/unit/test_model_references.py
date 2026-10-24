"""model.references: uniqueness, team/size references, depends_on resolution (RS 3.2, 9; AT-14, AT-32, AT-36)."""

from __future__ import annotations

import unicodedata
from pathlib import Path

from iokit import FIXTURES, MINIMAL, TODAY, codes, doc, load_raw, messages, resolve
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from rt.diagnostics import Collector
from rt.io.loader import load
from rt.io.rawdoc import CsvRow
from rt.model import build_model, check_references
from rt.model.types import Overrides

HEAD = doc(
    """\
    version: 1
    roadmap: {title: T}
    sizes: {S: 2, M: 4, L: 8, XL: 13}
    subdomains:
      - id: core
        name: Core
        teams:
          - {id: blik, name: BLIK, parallel_projects: 2}
          - {id: ops, name: Ops, parallel_projects: 1}
    projects:
    """
)


def test_fixtures_resolve() -> None:
    for name in ("dependencies-example.yaml", "scheduling-worked-example.yaml", "roadmap.example.yaml"):
        diags = Collector(name)
        raw = load((FIXTURES / name).read_bytes(), name, diags)
        assert raw is not None
        model = build_model(raw, diags, Overrides(default_today=TODAY))
        assert model is not None
        assert check_references(model, diags) is not None, messages(diags)


def test_dependencies_example_deps_and_weeks() -> None:
    resolved, diags = resolve((FIXTURES / "dependencies-example.yaml").read_text(encoding="utf-8"))
    assert resolved is not None and not diags.items
    assert dict(resolved.deps) == {1: (), 2: (1,), 3: (), 4: (2,), 5: (), 6: (1, 2), 7: (1,), 8: (2,)}
    assert resolved.weeks[1] == 8 and resolved.weeks[5] is None and resolved.weeks[8] == 2


def test_at14_unknown_team_size_and_bad_month_reported_together() -> None:
    text = HEAD + doc(
        """\
          - name: Card tokens
            team: blik2
            size: XXL
            start: 2027-13
        """
    )
    resolved, diags = resolve(text)
    assert resolved is None
    assert codes(diags) == [("E030", 12, 9), ("E031", 13, 9), ("E013", 14, 10)]
    assert messages(diags)[:2] == [
        'project "Card tokens" references unknown team "blik2" (did you mean "blik"?)',
        'project "Card tokens" uses size "XXL", not defined in sizes (S, M, L, XL)',
    ]


def test_at32_dependency_errors() -> None:
    text = HEAD + doc(
        """\
          - id: web-checkout
            name: Web checkout
            team: blik
            size: M
          - name: Maintenance
            team: blik
            size: S
          - name: Maintenance
            team: ops
            size: S
          - name: Ops maintenance
            team: ops
            ongoing: true
          - id: web-checkout
            name: Mobile release
            team: blik
            size: S
            depends_on: [Web chekout, Maintenance, Ops maintenance, API v2, Mobile release]
          - name: API v2
            team: ops
            size: S
        """
    )
    resolved, diags = resolve(text)
    assert resolved is None
    assert [c[0] for c in codes(diags)] == ["E023", "E034", "E035", "E036", "E037", "E037"]
    msgs = messages(diags)
    assert 'project id "web-checkout" already defined at line 11' in msgs
    assert 'project "Mobile release" depends on unknown project "Web chekout" (did you mean "Web checkout"?)' in msgs
    assert '"Maintenance" matches 2 projects (lines 15, 18); give one an id and use it' in msgs
    assert 'project "Mobile release" cannot depend on ongoing project "Ops maintenance"' in msgs
    assert 'project "Mobile release" depends on "API v2", which appears later (line 29); move "API v2" above it' in msgs
    assert 'project "Mobile release" depends on itself' in msgs


def test_uniqueness_errors() -> None:
    text = doc(
        """\
        version: 1
        roadmap: {title: T}
        sizes: {S: 2}
        subdomains:
          - id: core
            name: Core
            teams:
              - {id: a, name: A, parallel_projects: 1}
          - id: core
            name: Core 2
            teams:
              - {id: a, name: A2, parallel_projects: 1}
        projects:
          - {name: X, team: a, size: S}
          - {name: X, team: a, size: S}
        """
    )
    _, diags = resolve(text)
    assert codes(diags) == [("E020", 9, 9), ("E021", 12, 14), ("E022", 15, 12)]
    assert messages(diags) == [
        'subdomain id "core" already defined at line 5',
        'team id "a" already defined at line 8',
        'project "X" already exists in team "a" (line 14)',
    ]


def test_id_wins_over_name_and_single_string_dependency() -> None:
    text = HEAD + doc(
        """\
          - {id: x, name: First, team: blik, size: S}
          - {id: first, name: x, team: blik, size: S}
          - {name: Third, team: ops, size: S, depends_on: x}
          - {name: Fourth, team: ops, size: S, depends_on: [first, First, First]}
        """
    )
    resolved, diags = resolve(text)
    assert resolved is not None and not diags.items
    assert resolved.deps[3] == (1,)
    assert resolved.deps[4] == (1, 2)


def test_decomposed_unicode_reference_resolves() -> None:
    nfd = unicodedata.normalize("NFD", "Płatności BLIK")
    text = HEAD + doc(
        f"""\
          - {{name: Płatności BLIK, team: blik, size: S}}
          - {{name: Next, team: blik, size: S, depends_on: [{nfd}]}}
        """
    )
    resolved, diags = resolve(text)
    assert resolved is not None and not diags.items
    assert resolved.deps[2] == (1,)


def test_reference_checks_run_with_empty_blocks() -> None:
    text = "version: 1\nroadmap: {title: T}\nsizes: {}\nsubdomains: []\nprojects:\n  - {name: A, team: x, size: Q}\n"
    _, diags = resolve(text)
    assert [c[0] for c in codes(diags)] == ["E042", "E043", "E030", "E031"]
    assert messages(diags)[3] == 'project "A" uses size "Q", not defined in sizes (none)'


def test_empty_subdomain_still_checks_teams() -> None:
    text = (
        "version: 1\nroadmap: {title: T}\nsizes: {S: 1}\nsubdomains:\n  - {id: a, name: A, teams: []}\n"
        "projects:\n  - {name: A, team: x, size: S}\n"
    )
    _, diags = resolve(text)
    assert [c[0] for c in codes(diags)] == ["E030"]


def test_incomplete_project_blocks_resolution() -> None:
    resolved, _diags = resolve(MINIMAL)
    assert resolved is not None
    assert resolved.settings.title == "T" and resolved.teams and resolved.subdomains and resolved.projects


def _csv_tree(source: str) -> tuple[object, Collector]:
    """A tree like rt convert builds: base text plus CommentedMap rows registered as CSV rows."""
    base_text = HEAD.replace("projects:\n", "projects: []\n")
    diags = Collector("teams.base.yaml")
    raw = load(base_text.encode(), "teams.base.yaml", diags)
    assert raw is not None
    rows = CommentedSeq()
    first = CommentedMap(name="Płatności", team="blk", size="XXL", start="2027-13")
    second = CommentedMap(name="Next", team="blik", size="S")
    second["depends_on"] = CommentedSeq(["Płatnośći", "Next"])
    rows.extend([first, second])
    raw.root["projects"] = rows
    cells = {"name": (1, "Projekt"), "team": (3, "Zespół"), "size": (2, "Rozmiar"), "start": (4, "Start")}
    raw.register_csv_row(first, CsvRow(source, 2, cells))
    raw.register_csv_row(second, CsvRow(source, 3, {**cells, "depends_on": (5, "Zależności")}))
    return raw, diags


def test_csv_rows_report_csv_positions_and_columns() -> None:
    raw, diags = _csv_tree("projects.pl.csv")
    model = build_model(raw, diags, Overrides(default_today=TODAY))  # type: ignore[arg-type]
    assert model is not None
    assert check_references(model, diags) is None
    got = [(d.code.name, d.source, d.line, d.col, d.message) for d in diags.sorted()]
    assert got == [
        (
            "E031",
            "projects.pl.csv",
            2,
            2,
            'project "Płatności" uses size "XXL", not defined in sizes (S, M, L, XL) [column "Rozmiar"]',
        ),
        (
            "E030",
            "projects.pl.csv",
            2,
            3,
            'project "Płatności" references unknown team "blk" (did you mean "blik"?) [column "Zespół"]',
        ),
        ("E013", "projects.pl.csv", 2, 4, 'invalid month "2027-13"; expected YYYY-MM [column "Start"]'),
        (
            "E034",
            "projects.pl.csv",
            3,
            5,
            'project "Next" depends on unknown project "Płatnośći" (did you mean "Płatności"?) [column "Zależności"]',
        ),
        ("E037", "projects.pl.csv", 3, 5, 'project "Next" depends on itself [column "Zależności"]'),
    ]
    assert model.projects[0].field_column["team"] == "Zespół"


def test_csv_missing_size_points_at_size_cell(tmp_path: Path) -> None:
    raw, diags = _csv_tree("x.csv")
    row = raw.root["projects"][1]  # type: ignore[attr-defined]
    del row["size"]
    model = build_model(raw, diags, Overrides(default_today=TODAY))  # type: ignore[arg-type]
    assert model is not None
    e032 = [d for d in diags.items if d.code.name == "E032"]
    assert [(d.source, d.line, d.col) for d in e032] == [("x.csv", 3, 2)]
    assert e032[0].message.endswith('[column "Rozmiar"]')


def test_load_raw_helper_reports_nothing_for_minimal() -> None:
    raw, diags = load_raw(MINIMAL)
    assert raw is not None and not diags.items
