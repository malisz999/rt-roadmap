"""convert.merge: team resolution, base merge, skeleton edge cases, CSV positions of validator errors."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from rt.cli import main
from rt.convert.emit import dump, dump_slow, header_comment
from rt.convert.merge import BaseTeam, base_size_labels, base_teams, resolve_team, team_hint
from rt.io.streams import FakeIO

BASE = (Path(__file__).resolve().parents[2] / "docs" / "fixtures" / "convert" / "teams.base.yaml").read_bytes()
TEAMS = [BaseTeam("blik", "BLIK i przelewy"), BaseTeam("app", "Aplikacja mobilna")]


class _Run(FakeIO):
    code = -1


def _run(csv: str, *argv: str, **files: bytes) -> _Run:
    io = _Run(files={"in.csv": csv.encode("utf-8"), "base.yaml": BASE, **files})
    io.code = main(["convert", "in.csv", *argv], io)
    return io


def _errors(io: FakeIO) -> list[str]:
    return [line for line in io.stderr.splitlines() if ": error " in line]


def test_base_teams_and_sizes_are_read_defensively() -> None:
    doc = YAML().load(BASE)
    assert base_teams(doc) == TEAMS
    assert base_size_labels(doc) == ["S", "M", "L"]
    assert base_teams({"subdomains": [{"teams": [{"id": 3}, "x", {"id": "ok"}]}, None]}) == [BaseTeam("ok", None)]
    assert base_teams(["not", "a", "map"]) == []
    assert base_size_labels({"sizes": ["S"]}) == []


def test_resolve_team_by_id_then_name() -> None:
    assert resolve_team("app", TEAMS) == "app"
    assert resolve_team("BLIK i przelewy", TEAMS) == "blik"
    assert resolve_team("APP", TEAMS) is None
    assert resolve_team("blik i przelewy", TEAMS) is None
    assert resolve_team("app", [BaseTeam("x", "app"), BaseTeam("app", "y")]) == "app"


def test_team_hint_is_case_insensitive_over_ids_and_names() -> None:
    assert team_hint("Apka", TEAMS) == ' (did you mean "app"?)'
    assert team_hint("APP", TEAMS) == ' (did you mean "app"?)'
    assert team_hint("aplikacja Mobilna", TEAMS) == ' (did you mean "Aplikacja mobilna"?)'
    assert team_hint("Karty", TEAMS) == ""


def test_unknown_team_option_is_e030_per_row_with_hint() -> None:
    io = _run("name,size\nA,M\nB,S\n", "--base", "base.yaml", "--team", "blk")
    assert io.code == 1
    assert _errors(io) == [
        'in.csv:2:1: error E030: project "A" references unknown team "blk" (did you mean "blik"?)',
        'in.csv:3:1: error E030: project "B" references unknown team "blk" (did you mean "blik"?)',
    ]


def test_invalid_ongoing_with_empty_size_reports_only_e011() -> None:
    io = _run("name,size,team,ongoing\nA,,app,może\n", "--base", "base.yaml")
    [error] = _errors(io)
    assert error.startswith("in.csv:2:4: error E011: ")
    assert error.endswith('got "może" [column "ongoing"]')


def test_validator_errors_on_rows_carry_csv_cells() -> None:
    io = _run("name,size,color,id\n,M,blu,Bad Id\n")
    errors = _errors(io)
    assert [e.split(": error ")[0] for e in errors] == ["in.csv:2:1", "in.csv:2:3", "in.csv:2:4"]
    assert errors[1].endswith('[column "color"]')


def test_generated_team_errors_point_at_the_team_cell() -> None:
    io = _run(f"name,size,team\nA,M,{'Z' * 70}\n")
    [error] = _errors(io)
    assert error.startswith("in.csv:2:3: error E012: ")


def test_header_only_skeleton_is_still_valid() -> None:
    io = _run("name,size\n", "--team", "Ops")
    assert io.code == 0
    out = io.stdout.decode()
    assert "      - id: ops\n        name: Ops\n" in out
    assert out.endswith("projects: []\n")


def test_append_keeps_base_project_comments_and_fast_dump_matches_ruamel() -> None:
    base = BASE.replace(b"projects: []", b"projects:\n  # first\n  - name: Old  # kept\n    team: blik\n    size: S\n")
    io = _run("name,size,team\nNew,M,app\n", "--base", "b.yaml", "--append", **{"b.yaml": base})
    assert io.code == 0, io.stderr
    out = io.stdout.decode()
    assert "  # first\n  - name: Old  # kept\n" in out
    assert out.endswith("  - name: New\n    team: app\n    size: M\n")
    doc = YAML().load(out)
    assert dump(doc, "in.csv") == header_comment("in.csv") + dump_slow(doc)


def test_replace_drops_base_projects() -> None:
    base = BASE.replace(b"projects: []", b"projects:\n  - name: Old\n    team: blik\n    size: S\n")
    io = _run("name,size,team\nNew,M,app\n", "--base", "b.yaml", **{"b.yaml": base})
    assert "Old" not in io.stdout.decode()


def test_base_without_projects_key_gets_one_at_the_end() -> None:
    base = BASE.replace(b"\nprojects: []\n", b"\n")
    io = _run("name,size,team\nNew,M,app\n", "--base", "b.yaml", **{"b.yaml": base})
    assert io.code == 0, io.stderr
    assert io.stdout.decode().endswith("projects:\n  - name: New\n    team: app\n    size: M\n")


def test_skeleton_subdomain_conflict_with_default_subdomain_is_e107() -> None:
    io = _run("name,size,team,subdomain\nA,M,Karty,Kanały\nB,M,Karty,\n")
    [error] = _errors(io)
    assert error == (
        'in.csv:3:4: error E107: team "Karty" is in subdomain "Kanały" (line 2) and "Roadmap" (line 3) '
        '[column "subdomain"]'
    )
