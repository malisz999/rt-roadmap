"""Streams and chaining (RS 6.5; AT-37..AT-46)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from rtkit import (
    EX,
    INVALID,
    WE,
    WE_PLAN,
    assert_ok,
    copy_fixture,
    make_stress_yaml,
    mask_version,
    parse_html,
    rt_cmd,
    rt_env,
    run_rt,
)


def test_at_37_stdin_equals_file(tmp_path: Path) -> None:
    """AT-37: cat EX | rt render > a.html, then rt render EX -o b.html -> byte-identical;
    the first run's summary names <stdout>."""
    a = run_rt(["render"], stdin=EX.read_bytes(), cwd=tmp_path)
    assert a.code == 0, a.describe()
    (tmp_path / "a.html").write_bytes(a.stdout)
    assert re.search(r"^rt: wrote <stdout> — ", a.stderr, re.M), a.stderr
    src = copy_fixture(EX, tmp_path)
    b = run_rt(["render", src.name, "-o", "b.html"], cwd=tmp_path)
    assert b.code == 0, b.describe()
    assert re.search(r"^rt: wrote b\.html — ", b.stderr, re.M), b.stderr
    assert (tmp_path / "a.html").read_bytes() == (tmp_path / "b.html").read_bytes()


def test_at_38_plan_to_stdout(tmp_path: Path) -> None:
    """AT-38: cat WE | rt render --plan - -o x.html -> stdout equals the expected plan; x.html written."""
    r = run_rt(["render", "--plan", "-", "-o", "x.html"], stdin=WE.read_bytes(), cwd=tmp_path)
    assert r.code == 0, r.describe()
    assert mask_version(r.stdout).decode("utf-8") == mask_version(WE_PLAN.read_bytes()).decode("utf-8")
    assert (tmp_path / "x.html").exists()
    parse_html((tmp_path / "x.html").read_bytes())


def _run_with_open_stdin(args: list[str], cwd: Path, timeout: float = 30) -> tuple[int, bytes, str]:
    """Run rt with a stdin pipe that is never closed: a run that tried to read input would hang."""
    proc = subprocess.Popen(
        rt_cmd(args), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=rt_env()
    )
    try:
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        pytest.fail(f"rt {' '.join(args)} read stdin instead of failing before reading input")
    finally:
        assert proc.stdin is not None
        proc.stdin.close()
    assert proc.stdout is not None and proc.stderr is not None
    return code, proc.stdout.read(), proc.stderr.read().decode("utf-8", "replace")


def test_at_39_two_artifacts_on_stdout(tmp_path: Path) -> None:
    """AT-39: rt render EX -o - --plan -, and cat EX | rt render --plan - -> exit 2 without reading
    input; stdout empty."""
    src = copy_fixture(EX, tmp_path)
    r = run_rt(["render", src.name, "-o", "-", "--plan", "-"], cwd=tmp_path)
    assert r.code == 2, r.describe()
    assert r.stdout == b""
    # the file argument is not even opened: a missing file still gives the usage error
    r_missing = run_rt(["render", "missing.yaml", "-o", "-", "--plan", "-"], cwd=tmp_path)
    assert r_missing.code == 2, r_missing.describe()
    assert r_missing.stdout == b""
    r2 = run_rt(["render", "--plan", "-"], stdin=EX.read_bytes(), cwd=tmp_path)
    assert r2.code == 2, r2.describe()
    assert r2.stdout == b""
    # stdin stays open: rt must decide before reading it
    code, out, _err = _run_with_open_stdin(["render", "--plan", "-"], tmp_path)
    assert code == 2 and out == b""
    code, out, _err = _run_with_open_stdin(["render", "-", "-o", "-", "--plan", "-"], tmp_path)
    assert code == 2 and out == b""


@pytest.mark.skipif(sys.platform == "win32", reason="pty is POSIX only (FakeIO covers Windows)")
def test_at_40_terminal_stdin(tmp_path: Path) -> None:
    """AT-40: rt render with no argument and stdin a terminal -> exit 2, 'no input; give a file or
    pipe data into rt'; stdout empty."""
    import pty

    master, slave = pty.openpty()
    try:
        proc = subprocess.Popen(
            rt_cmd(["render"]), stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=tmp_path, env=rt_env()
        )
        try:
            out, err = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            pytest.fail("rt waited for terminal input instead of exiting with a usage error")
    finally:
        os.close(slave)
        os.close(master)
    assert proc.returncode == 2, err.decode("utf-8", "replace")
    assert out == b""
    assert "no input; give a file or pipe data into rt" in err.decode("utf-8", "replace")
    assert "rt: error: no input; give a file or pipe data into rt" in err.decode("utf-8", "replace")


@pytest.mark.parametrize(
    ("command", "data"),
    [("render", b""), ("validate", b"  \n")],
    ids=["render-empty", "validate-whitespace"],
)
def test_at_41_empty_input(tmp_path: Path, command: str, data: bytes) -> None:
    """AT-41: printf '' | rt render, and printf '  \\n' | rt validate -> exit 1; E001 'input is empty'
    for <stdin>; stdout empty."""
    r = run_rt([command], stdin=data, cwd=tmp_path)
    assert r.code == 1, r.describe()
    assert r.stdout == b""
    e001 = [d for d in r.diags if d.code == "E001"]
    assert len(e001) == 1, r.stderr
    assert e001[0].file == "<stdin>"
    assert e001[0].message.startswith("input is empty"), e001[0].message
    assert list(tmp_path.iterdir()) == []


def test_at_42_stdin_diagnostics(tmp_path: Path) -> None:
    """AT-42: rt validate < e030_unknown_team.yaml -> stderr lines start with <stdin>:, exit 1;
    rt validate - --format json -> JSON array with "file": "<stdin>", exit 1."""
    data = (INVALID / "e030_unknown_team.yaml").read_bytes()
    r = run_rt(["validate"], stdin=data, cwd=tmp_path)
    assert r.code == 1, r.describe()
    lines = [ln for ln in r.stderr.splitlines() if re.search(r"(error|warning) [EW]\d{3}:", ln)]
    assert lines and all(ln.startswith("<stdin>:") for ln in lines), r.stderr
    assert [(d.code, d.line, d.col) for d in r.diags] == [("E030", 25, 11)]
    assert r.stdout == b""
    j = run_rt(["validate", "-", "--format", "json"], stdin=data, cwd=tmp_path)
    assert j.code == 1, j.describe()
    arr = json.loads(j.stdout.decode("utf-8"))
    assert isinstance(arr, list) and len(arr) == 1
    assert arr[0]["file"] == "<stdin>"
    assert (arr[0]["code"], arr[0]["severity"], arr[0]["line"], arr[0]["column"]) == ("E030", "error", 25, 11)


def test_at_43_failure_writes_nothing_to_stdout(tmp_path: Path) -> None:
    """AT-43: cat e030_unknown_team.yaml | rt render -o -, and rt render EX --strict -o - -> exit 1;
    stdout 0 bytes."""
    r = run_rt(["render", "-o", "-"], stdin=(INVALID / "e030_unknown_team.yaml").read_bytes(), cwd=tmp_path)
    assert r.code == 1, r.describe()
    assert r.stdout == b""
    src = copy_fixture(EX, tmp_path)
    r2 = run_rt(["render", src.name, "--strict", "-o", "-"], cwd=tmp_path)
    assert r2.code == 1, r2.describe()
    assert r2.stdout == b""
    assert [d.code for d in r2.diags] == ["W001"]


@pytest.fixture(scope="module")
def stress_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("stress")
    p = d / "stress.yaml"
    p.write_text(make_stress_yaml(), encoding="utf-8")
    return p


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX pipe semantics; C9 covers Windows")
def test_at_44_closed_pipe(stress_file: Path) -> None:
    """AT-44: rt render stress.yaml -o - | head -c 1 -> rt exits 141; stderr empty."""
    # sanity: the HTML is over 64 KB
    full = run_rt(["render", stress_file.name, "-o", "-", "-q"], cwd=stress_file.parent)
    assert full.code == 0, full.describe()
    assert len(full.stdout) > 64 * 1024
    r_fd, w_fd = os.pipe()
    proc = subprocess.Popen(
        rt_cmd(["render", stress_file.name, "-o", "-"]),
        stdin=subprocess.DEVNULL,
        stdout=w_fd,
        stderr=subprocess.PIPE,
        cwd=stress_file.parent,
        env=rt_env(),
    )
    os.close(w_fd)
    first = os.read(r_fd, 1)
    os.close(r_fd)
    assert proc.stderr is not None
    err = proc.stderr.read()
    code = proc.wait(timeout=120)
    assert first == b"<"
    assert code == 141, err.decode("utf-8", "replace")
    assert err == b"", err.decode("utf-8", "replace")


@pytest.mark.skipif(shutil.which("bash") is None or shutil.which("head") is None, reason="needs bash and head")
def test_at_44_closed_pipe_shell(stress_file: Path) -> None:
    """AT-44 exactly as written: ${PIPESTATUS[0]} of `rt render stress.yaml -o - | head -c 1` is 141."""
    cmd = " ".join(f"'{c}'" for c in rt_cmd(["render", stress_file.name, "-o", "-"]))
    script = f"{cmd} 2>err.txt | head -c 1 >/dev/null; echo ${{PIPESTATUS[0]}}"
    proc = subprocess.run(
        ["bash", "-c", script], stdout=subprocess.PIPE, cwd=stress_file.parent, env=rt_env(), timeout=120, check=False
    )
    assert proc.stdout.decode().strip() == "141"
    assert (stress_file.parent / "err.txt").read_bytes() == b""


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX variant of AT-45")
def test_at_45_stdout_bytes_independent_of_locale(tmp_path: Path) -> None:
    """AT-45: EX to stdout with PYTHONIOENCODING=cp1252 LANG=C -> stdout bytes equal the -o file
    bytes; Płatności present as UTF-8; no CR byte."""
    src = copy_fixture(EX, tmp_path)
    ref = run_rt(["render", src.name, "-o", "ref.html"], cwd=tmp_path)
    assert ref.code == 0, ref.describe()
    env = rt_env(PYTHONIOENCODING="cp1252", LANG="C", LC_ALL="C")
    r = run_rt(["render", src.name, "-o", "-"], cwd=tmp_path, env=env)
    assert r.code == 0, r.describe()
    assert r.stdout == (tmp_path / "ref.html").read_bytes()
    assert "Płatności".encode() in r.stdout
    assert b"\r" not in r.stdout
    # stdin path too
    r2 = run_rt(["render"], stdin=EX.read_bytes(), cwd=tmp_path, env=env)
    assert r2.code == 0, r2.describe()
    assert r2.stdout == r.stdout


def test_at_46_chaining(tmp_path: Path) -> None:
    """AT-46: rt init --minimal - | rt render -o - > m.html, and rt schema | python -m json.tool -> exit 0."""
    init = subprocess.Popen(
        rt_cmd(["init", "--minimal", "-"]), stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=tmp_path, env=rt_env()
    )
    assert init.stdout is not None
    render = subprocess.Popen(
        rt_cmd(["render", "-o", "-", "--today", "2027-01-10"]),
        stdin=init.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=tmp_path,
        env=rt_env(),
    )
    init.stdout.close()
    html, render_err = render.communicate(timeout=60)
    assert init.wait(timeout=60) == 0
    assert render.returncode == 0, render_err.decode("utf-8", "replace")
    (tmp_path / "m.html").write_bytes(html)
    assert html.lstrip()[:15].lower() == b"<!doctype html>"
    assert html.rstrip().endswith(b"</html>")
    doc = parse_html(html)
    assert doc.find(".//title").text == "My Roadmap"
    assert {p.name for p in tmp_path.iterdir()} == {"m.html"}, "init - must not write roadmap.yaml"

    schema = subprocess.Popen(rt_cmd(["schema"]), stdout=subprocess.PIPE, cwd=tmp_path, env=rt_env())
    assert schema.stdout is not None
    tool = subprocess.Popen([sys.executable, "-m", "json.tool"], stdin=schema.stdout, stdout=subprocess.PIPE)
    schema.stdout.close()
    out, _ = tool.communicate(timeout=60)
    assert schema.wait(timeout=60) == 0
    assert tool.returncode == 0
    assert isinstance(json.loads(out), dict)


def test_st5_input_too_large(tmp_path: Path) -> None:
    """ST-5: the 5 MB limit applies to stdin -> E001 'input too large', exit 1."""
    big = WE.read_bytes() + b"#" + b"x" * (5 * 1024 * 1024) + b"\n"
    r = run_rt(["validate"], stdin=big, cwd=tmp_path)
    assert r.code == 1, r.describe()
    e001 = [d for d in r.diags if d.code == "E001"]
    assert e001 and e001[0].file == "<stdin>"
    assert "too large" in e001[0].message


def test_st3_empty_file(tmp_path: Path) -> None:
    """ST-3: zero bytes or only whitespace from a file is E001, exit 1."""
    (tmp_path / "empty.yaml").write_bytes(b"")
    (tmp_path / "blank.yaml").write_bytes(b" \n\t\n")
    for name in ("empty.yaml", "blank.yaml"):
        r = run_rt(["render", name], cwd=tmp_path)
        assert r.code == 1, r.describe()
        assert [(d.code, d.file) for d in r.diags] == [("E001", name)]
        assert "input is empty" in r.diags[0].message
    assert not (tmp_path / "empty.html").exists()


def test_st4_bom_accepted_on_stdin(tmp_path: Path) -> None:
    """ST-4: stdin decoded as UTF-8, BOM accepted."""
    r = run_rt(["render", "--plan", "-", "-o", "x.html"], stdin=b"\xef\xbb\xbf" + WE.read_bytes(), cwd=tmp_path)
    assert r.code == 0, r.describe()
    assert mask_version(r.stdout) == mask_version(WE_PLAN.read_bytes())


def test_st8_base_is_always_a_file(tmp_path: Path) -> None:
    """ST-8: --base never reads stdin; `--base -` names a file called '-' (or is a usage error)."""
    from rtkit import CONVERT

    csv = copy_fixture(CONVERT / "projects.minimal.csv", tmp_path)
    code, out, _err = _run_with_open_stdin(["convert", csv.name, "--base", "-"], tmp_path)
    assert code != 0
    assert out == b""


def test_convert_render_pipeline_with_failing_upstream(tmp_path: Path) -> None:
    """ST-2: a failing command upstream leaves stdout empty, so the next command stops with E001."""
    bad = tmp_path / "bad.csv"
    bad.write_text("name,team\nX,y\n", encoding="utf-8")
    up = run_rt(["convert", bad.name], cwd=tmp_path)
    assert up.code == 1 and up.stdout == b""
    down = run_rt(["render", "-o", "-"], stdin=up.stdout, cwd=tmp_path)
    assert down.code == 1
    assert [d.code for d in down.diags] == ["E001"]
    assert down.stdout == b""


def test_validate_json_is_content_on_failure(tmp_path: Path) -> None:
    """ST-2 exception: validate --format json writes its diagnostics even when the exit code is 1."""
    src = copy_fixture(INVALID / "e030_unknown_team.yaml", tmp_path)
    r = run_rt(["validate", src.name, "--format", "json"], cwd=tmp_path)
    assert r.code == 1
    arr = json.loads(r.stdout)
    assert [a["code"] for a in arr] == ["E030"]
    assert set(arr[0]) >= {"code", "severity", "file", "line", "column", "message"}


def test_plan_and_html_to_files_and_stdout_is_empty(tmp_path: Path) -> None:
    """CLI-5: with file outputs, stdout carries nothing."""
    src = copy_fixture(WE, tmp_path)
    r = run_rt(["render", src.name, "-o", "out.html", "--plan", "plan.json"], cwd=tmp_path)
    assert_ok(r)
    assert r.stdout == b""
    assert (tmp_path / "out.html").exists() and (tmp_path / "plan.json").exists()
