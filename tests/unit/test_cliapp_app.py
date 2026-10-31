"""app use cases through cli.main with FakeIO: outputs, exit codes 0/1/3/4, ST-2 ordering (RS 6, ADS 8.4)."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

import pytest
from iokit import FIXTURES, MINIMAL, run

from rt.app import default_html_output
from rt.layout import viewmodel
from rt.render import renderer

WE = (FIXTURES / "scheduling-worked-example.yaml").read_bytes()
WE_PLAN = (FIXTURES / "scheduling-worked-example.expected.json").read_text(encoding="utf-8")
WARNING = MINIMAL.replace(
    "  title: T\n", "  title: T\n  horizon: {start: 2027-02}\n"
)  # W004: First is before the horizon
UNKNOWN_TEAM = MINIMAL.replace("team: alpha", "team: alpah")
CONFLICT = (
    MINIMAL
    + "  - {name: Second, team: alpha, size: M, start: 2027-01}\n"
    + "  - {name: Third, team: alpha, size: M, start: 2027-01}\n"
)


@pytest.fixture(autouse=True)
def fake_renderer(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Keep these tests independent of the layout/render packages: HTML = '<html>' + title."""
    calls: list[dict[str, Any]] = []

    def build_page(plan: Any, *, summary: bool, version: str) -> Any:
        calls.append({"summary": summary, "version": version})
        return plan.title

    monkeypatch.setattr(viewmodel, "build_page", build_page)
    monkeypatch.setattr(renderer, "render_html", lambda page: f"<html>{page}</html>\n")
    return calls


def _plan_equal(got: bytes) -> bool:
    a, b = json.loads(got), json.loads(WE_PLAN)
    a.pop("rt_version")
    b.pop("rt_version")
    return bool(a == b)


def test_render_default_output_next_to_input(fake_renderer: list[dict[str, Any]]) -> None:
    code, io = run(["render", "plans/we.yaml", "--summary"], files={"plans/we.yaml": WE})
    assert code == 0, io.stderr
    assert io.files["plans/we.html"] == b"<html>Scheduling worked example</html>\n"
    assert io.stdout == b""
    assert fake_renderer == [{"summary": True, "version": "1.2.0"}]
    assert io.stderr.splitlines()[-1] == "rt: wrote plans/we.html — 1 subdomain, 2 teams, 9 projects, 4 warnings"


def test_render_stdin_to_stdout_and_plan_file() -> None:
    code, io = run(["render", "--plan", "p.json"], stdin=WE)
    assert code == 0, io.stderr
    assert io.stdout.startswith(b"<html>") and io.stdout_writes == 1
    assert _plan_equal(io.files["p.json"])
    assert "rt: wrote <stdout> — " in io.stderr
    assert "<stdin>:" in io.stderr  # warnings name the stdin source


def test_render_plan_to_stdout_html_to_file() -> None:
    code, io = run(["render", "-", "--plan", "-", "-o", "x.html"], stdin=WE)
    assert code == 0
    assert _plan_equal(io.stdout) and "x.html" in io.files


def test_render_quiet_prints_nothing() -> None:
    code, io = run(["render", "-q", "-o", "-"], stdin=WE)
    assert code == 0 and io.stderr == ""


def test_render_errors_write_nothing() -> None:
    code, io = run(["render", "-o", "-"], stdin=UNKNOWN_TEAM.encode())
    assert code == 1 and io.stdout == b"" and not io.files
    assert io.stderr.startswith("<stdin>:16:11: error E030: ")


def test_render_strict_with_warnings_writes_nothing() -> None:
    files = {"r.yaml": WARNING.encode(), "r.html": b"old"}
    code, io = run(["render", "r.yaml", "--strict"], files=files)
    assert code == 1
    assert io.files["r.html"] == b"old"
    assert "warning W004" in io.stderr and "treated as errors (--strict)" in io.stderr
    code, io = run(["render", "-", "--strict", "-o", "-"], stdin=WARNING.encode())
    assert code == 1 and io.stdout == b""


def test_render_scheduling_error_exit_3() -> None:
    code, io = run(["render", "-", "-o", "-", "--on-conflict", "error"], stdin=CONFLICT.encode())
    assert code == 3 and io.stdout == b""
    assert "error E061" in io.stderr


def test_render_empty_input() -> None:
    code, io = run(["render"], stdin=b"")
    assert code == 1 and io.stdout == b""
    assert io.stderr == "<stdin>:1:1: error E001: input is empty (did the previous command fail?)\n"


def test_render_unreadable_input_exit_4() -> None:
    code, io = run(["render", "missing.yaml"])
    assert code == 4
    assert io.stderr == "rt: error: cannot read missing.yaml: No such file or directory\n"


def test_render_unwritable_output_exit_4() -> None:
    files = {"r.yaml": MINIMAL.encode()}
    code, _io = run(["render", "r.yaml", "-o", "out/r.html"], files=files)
    assert code == 0
    _, io2 = run(["render", "r.yaml", "-o", "bad.html"], files=files)
    io2.fail_write.add("bad.html")
    from rt.cli import main

    assert main(["render", "r.yaml", "-o", "bad.html"], io2) == 4
    assert "rt: error: cannot write bad.html: Permission denied" in io2.stderr
    io2.fail_write.add("p.json")
    assert main(["render", "r.yaml", "-o", "ok.html", "--plan", "p.json"], io2) == 4
    assert "cannot write p.json" in io2.stderr and "ok.html" not in io2.files


def test_render_closed_pipe() -> None:
    code, _io = run(["render", "-o", "-"], stdin=WE, closed_stdout=True)
    assert code == 141


def test_validate_text_and_plan() -> None:
    code, io = run(["validate", "we.yaml", "--plan", "-"], files={"we.yaml": WE})
    assert code == 0 and _plan_equal(io.stdout)
    assert io.stderr.splitlines()[-1] == "rt: we.yaml is valid — 1 subdomain, 2 teams, 9 projects, 4 warnings"
    assert not [k for k in io.files if k != "we.yaml"]


def test_validate_overrides_reach_the_model() -> None:
    code, io = run(
        ["validate", "-", "--plan", "-", "--today", "2027-03-01", "--from", "2027-02", "--to", "2027-04"], stdin=WE
    )
    assert code == 0
    plan = json.loads(io.stdout)
    assert (
        plan["today"] == "2027-03-01" and plan["horizon"]["start"] == "2027-02" and plan["horizon"]["end"] == "2027-04"
    )


def test_validate_json_success_and_failure() -> None:
    code, io = run(["validate", "-", "--format", "json"], stdin=WE)
    assert code == 0
    items = json.loads(io.stdout)
    assert {i["code"] for i in items} == {"W001"} and all(i["file"] == "<stdin>" for i in items)
    assert "warning W001" not in io.stderr  # text diagnostics are not printed with --format json

    code, io = run(["validate", "-", "--format", "json"], stdin=UNKNOWN_TEAM.encode())
    assert code == 1
    items = json.loads(io.stdout)
    assert [i["code"] for i in items] == ["E030"] and items[0]["line"] == 16 and items[0]["column"] == 11

    code, io = run(["validate", "-", "--format", "json", "--strict"], stdin=WARNING.encode())
    assert code == 1 and json.loads(io.stdout)[0]["code"] == "W004"

    code, io = run(["validate", "-", "--format", "json", "--plan", "p.json"], stdin=WE)
    assert code == 0 and _plan_equal(io.files["p.json"])


def test_validate_text_failures() -> None:
    code, io = run(["validate"], stdin=UNKNOWN_TEAM.encode())
    assert code == 1 and io.stdout == b"" and io.stderr.startswith("<stdin>:16:11: error E030")
    code, io = run(["validate", "--strict"], stdin=WARNING.encode())
    assert code == 1 and "treated as errors" in io.stderr
    code, io = run(["validate", "--on-conflict", "error"], stdin=CONFLICT.encode())
    assert code == 3
    code, io = run(["validate", "nope.yaml"])
    assert code == 4


def test_validate_plan_write_failure() -> None:
    from rt.cli import main
    from rt.io.streams import FakeIO

    io = FakeIO(stdin=WE)
    io.fail_write.add("p.json")
    assert main(["validate", "--plan", "p.json"], io) == 4
    io = FakeIO(stdin=WE)
    io.fail_write.add("p.json")
    assert main(["validate", "--plan", "p.json", "--format", "json"], io) == 4


def _resource(name: str) -> bytes:
    return resources.files("rt").joinpath("resources", name).read_bytes()


def test_init_writes_once_then_needs_force() -> None:
    code, io = run(["init"])
    assert code == 0 and io.files["roadmap.yaml"] == _resource("roadmap.example.yaml")
    assert io.stderr == "rt: wrote roadmap.yaml; render it with: rt render roadmap.yaml\n"
    from rt.cli import main

    assert main(["init"], io) == 4
    assert "rt: error: roadmap.yaml already exists; use --force to overwrite it" in io.stderr
    assert main(["init", "--force", "--minimal"], io) == 0
    assert io.files["roadmap.yaml"] == _resource("roadmap.minimal.yaml")


def test_init_to_stdout_and_failure() -> None:
    code, io = run(["init", "-", "--minimal"])
    assert code == 0 and io.stdout == _resource("roadmap.minimal.yaml") and io.stderr == "rt: wrote <stdout>\n"
    from rt.cli import main
    from rt.io.streams import FakeIO

    io = FakeIO()
    io.fail_write.add("x.yaml")
    assert main(["init", "x.yaml"], io) == 4


def test_bundled_starter_files_validate() -> None:
    for name in ("roadmap.example.yaml", "roadmap.minimal.yaml"):
        code, io = run(["validate", "-", "-q"], stdin=_resource(name))
        assert code == 0, io.stderr


def test_schema_unchanged_bytes() -> None:
    code, io = run(["schema"])
    assert code == 0 and io.stdout == _resource("roadmap.schema.json")
    json.loads(io.stdout)
    code, io = run(["schema", "-o", "s.json", "-q"])
    assert code == 0 and io.files["s.json"] == _resource("roadmap.schema.json") and io.stderr == ""
    from rt.cli import main
    from rt.io.streams import FakeIO

    io = FakeIO()
    io.fail_write.add("s.json")
    assert main(["schema", "-o", "s.json"], io) == 4


def test_default_html_output() -> None:
    assert default_html_output("-") == "-"
    assert default_html_output("a/roadmap.yaml") == "a/roadmap.html"
    assert default_html_output("roadmap.yml") == "roadmap.html"
    assert default_html_output("roadmap") == "roadmap.html"
