"""CLI acceptance tests (RS 11.2; AT-17..AT-21)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from rtkit import EX, WE, assert_ok, copy_fixture, parse_html, run_rt


def test_at_17_strict_writes_nothing(tmp_path: Path) -> None:
    """AT-17: rt render EX --strict (EX has a warning) -> exit 1; output file not created;
    a pre-existing output file unchanged."""
    src = copy_fixture(EX, tmp_path)
    out = tmp_path / "roadmap.example.html"
    r = run_rt(["render", src.name, "--strict"], cwd=tmp_path)
    assert r.code == 1, r.describe()
    assert not out.exists()
    assert "W001" in r.codes()
    assert sorted(p.name for p in tmp_path.iterdir()) == [src.name], "no temporary files left behind"
    out.write_bytes(b"previous content\n")
    r2 = run_rt(["render", src.name, "--strict"], cwd=tmp_path)
    assert r2.code == 1, r2.describe()
    assert out.read_bytes() == b"previous content\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([src.name, out.name])


def test_at_18_init_twice(tmp_path: Path) -> None:
    """AT-18: rt init twice in an empty folder: first exit 0 and the file renders with exit 0;
    second exit 4; with --force exit 0."""
    r1 = run_rt(["init"], cwd=tmp_path)
    assert r1.code == 0, r1.describe()
    target = tmp_path / "roadmap.yaml"
    assert target.exists()
    first = target.read_bytes()
    rr = run_rt(["render", "roadmap.yaml", "--today", "2026-10-23"], cwd=tmp_path)
    assert rr.code == 0, rr.describe()
    assert (tmp_path / "roadmap.html").exists()
    target.write_bytes(first + b"# my edit\n")
    r2 = run_rt(["init"], cwd=tmp_path)
    assert r2.code == 4, r2.describe()
    assert "roadmap.yaml" in r2.stderr, "message must name the file (CLI-4)"
    assert target.read_bytes() == first + b"# my edit\n", "existing file must not be overwritten"
    r3 = run_rt(["init", "--force"], cwd=tmp_path)
    assert r3.code == 0, r3.describe()
    assert target.read_bytes() == first


def test_at_18_init_path_and_minimal(tmp_path: Path) -> None:
    """RS 6.1: rt init <path>, --minimal; both starter files validate."""
    r = run_rt(["init", "plan.yaml", "--minimal"], cwd=tmp_path)
    assert r.code == 0, r.describe()
    assert (tmp_path / "plan.yaml").exists()
    v = run_rt(["validate", "plan.yaml", "--today", "2026-10-23"], cwd=tmp_path)
    assert v.code == 0, v.describe()
    assert run_rt(["init", "plan.yaml"], cwd=tmp_path).code == 4


def test_at_19_stdin_to_stdout(tmp_path: Path) -> None:
    """AT-19: cat EX | rt render - -o - -> HTML on stdout only; summary on stderr."""
    r = run_rt(["render", "-", "-o", "-"], stdin=EX.read_bytes(), cwd=tmp_path)
    assert r.code == 0, r.describe()
    assert r.stdout.lstrip()[:15].lower() == b"<!doctype html>"
    assert r.stdout.rstrip().endswith(b"</html>")
    assert b"rt: wrote" not in r.stdout and b"W001" not in r.stdout.split(b"<body", 1)[0]
    parse_html(r.stdout)
    assert re.search(r"^rt: wrote <stdout> — 4 subdomains, 7 teams, 36 projects, 1 warnings?$", r.stderr, re.M), (
        r.stderr
    )
    assert re.search(r"^<stdin>:252:5: warning W001: ", r.stderr, re.M), r.stderr
    assert list(tmp_path.iterdir()) == [], "nothing written to disk"


def test_at_20_validate_json(tmp_path: Path) -> None:
    """AT-20: rt validate EX --format json -> JSON array of diagnostics on stdout; no file written."""
    src = copy_fixture(EX, tmp_path)
    r = run_rt(["validate", src.name, "--format", "json"], cwd=tmp_path)
    assert r.code == 0, r.describe()
    data = json.loads(r.stdout.decode("utf-8"))
    assert isinstance(data, list)
    assert len(data) == 1
    d = data[0]
    assert d["code"] == "W001"
    assert (d["line"], d["column"]) == (252, 5)
    assert d["severity"] == "warning"
    assert d["file"] == "roadmap.example.yaml"
    assert '"BLIK w aplikacji"' in d["message"]
    assert sorted(p.name for p in tmp_path.iterdir()) == [src.name]


def test_at_20_validate_text_writes_nothing(tmp_path: Path) -> None:
    """RS 6.1: validate writes nothing except --plan / --format json output."""
    src = copy_fixture(WE, tmp_path)
    r = run_rt(["validate", src.name], cwd=tmp_path)
    assert r.code == 0, r.describe()
    assert r.stdout == b""
    assert sorted(p.name for p in tmp_path.iterdir()) == [src.name]
    assert r.codes() == ["W001"] * 4
    r2 = run_rt(["validate", src.name, "--plan", "plan.json"], cwd=tmp_path)
    assert r2.code == 0
    assert (tmp_path / "plan.json").exists()
    assert json.loads((tmp_path / "plan.json").read_text(encoding="utf-8"))["title"] == "Scheduling worked example"


def test_at_21_unknown_option(tmp_path: Path) -> None:
    """AT-21: unknown option --frm -> exit 2 with usage hint."""
    src = copy_fixture(WE, tmp_path)
    r = run_rt(["render", src.name, "--frm", "2027-01"], cwd=tmp_path)
    assert r.code == 2, r.describe()
    assert "usage" in r.stderr.lower()
    assert "--frm" in r.stderr
    assert r.stdout == b""
    assert sorted(p.name for p in tmp_path.iterdir()) == [src.name]


def test_strict_validate_and_quiet(tmp_path: Path) -> None:
    """RS 6.2: --strict on validate -> exit 1; -q suppresses warnings and the summary line."""
    src = copy_fixture(WE, tmp_path)
    r = run_rt(["validate", src.name, "--strict"], cwd=tmp_path)
    assert r.code == 1, r.describe()
    q = run_rt(["render", src.name, "-q", "-o", "q.html"], cwd=tmp_path)
    assert q.code == 0, q.describe()
    assert q.stderr == "", "-q suppresses warnings and the summary line"
    assert (tmp_path / "q.html").exists()


def test_quiet_still_prints_errors(tmp_path: Path) -> None:
    """RS 6.2: -q: errors still print."""
    src = tmp_path / "bad.yaml"
    src.write_text(WE.read_text(encoding="utf-8").replace("team: beta", "team: betaa", 1), encoding="utf-8")
    r = run_rt(["render", src.name, "-q"], cwd=tmp_path)
    assert r.code == 1
    assert [d.code for d in r.diags] == ["E030"]
    assert (r.diags[0].line, r.diags[0].col) == (55, 11)


def test_summary_line_for_file(tmp_path: Path) -> None:
    """CLI-7: rt: wrote <file> — N subdomains, N teams, N projects, N warnings."""
    src = copy_fixture(WE, tmp_path)
    r = run_rt(["render", src.name], cwd=tmp_path)
    assert_ok(r)
    assert re.search(
        r"^rt: wrote scheduling-worked-example\.html — 1 subdomains?, 2 teams, 9 projects, 4 warnings$", r.stderr, re.M
    ), r.stderr
    assert r.stdout == b""


def test_default_output_next_to_input(tmp_path: Path) -> None:
    """RS 6.2: render default output = input path with .html (next to the input, not the cwd)."""
    (tmp_path / "sub").mkdir()
    copy_fixture(WE, tmp_path / "sub")
    r = run_rt(["render", "sub/scheduling-worked-example.yaml"], cwd=tmp_path)
    assert_ok(r)
    assert (tmp_path / "sub" / "scheduling-worked-example.html").exists()
    assert not (tmp_path / "scheduling-worked-example.html").exists()
