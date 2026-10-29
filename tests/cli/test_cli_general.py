"""General CLI behaviour: exit codes (RS 6.4), version/help (NF-9), determinism (NF-4),
input never modified (NF-10), schema, init content."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest
from rtkit import (
    CONVERT,
    DE,
    EX,
    INVALID,
    MINIMAL,
    SCHEMA,
    WE,
    assert_ok,
    copy_fixture,
    load_yaml,
    run_rt,
)


def test_version() -> None:
    """RS 6.1: rt --version prints `rt 1.1.0`."""
    r = run_rt(["--version"])
    assert r.code == 0, r.describe()
    text = (r.stdout.decode("utf-8") + r.stderr).strip()
    assert text == "rt 1.1.0"


@pytest.mark.parametrize("command", [[], ["render"], ["validate"], ["convert"], ["init"], ["schema"]])
def test_help_fits_80_columns(command: list[str]) -> None:
    """NF-9: rt --help and each command's help fit in 80 columns."""
    r = run_rt([*command, "--help"])
    assert r.code == 0, r.describe()
    text = r.stdout.decode("utf-8") + r.stderr
    assert "usage" in text.lower()
    long = [ln for ln in text.splitlines() if len(ln) > 80]
    assert not long, long


def test_help_lists_commands() -> None:
    r = run_rt(["--help"])
    text = r.stdout.decode("utf-8") + r.stderr
    for cmd in ("render", "validate", "convert", "init", "schema"):
        assert cmd in text


# --------------------------------------------------------------------------- exit codes (RS 6.4)


@pytest.mark.parametrize(
    "args",
    [
        ["frobnicate"],
        ["render", "WE", "--on-conflict", "sometimes"],
        ["render", "WE", "--from", "2027-13"],
        ["render", "WE", "--today", "yesterday"],
        ["render", "WE", "--to", "27-01"],
        ["validate", "WE", "--format", "xml"],
        ["render", "WE", "--frm", "2027-01"],
        ["convert", "projects.minimal.csv", "--delimiter", "pipe"],
        ["convert", "projects.minimal.csv", "--slots", "13"],
        ["convert", "projects.minimal.csv", "--map", "name=nazwa"],
        ["convert", "projects.minimal.csv", "--base", "teams.base.yaml", "--title", "X"],
        ["convert", "projects.minimal.csv", "--base", "teams.base.yaml", "--sizes", "S=2"],
        ["convert", "projects.minimal.csv", "--encoding", "no-such-codec"],
    ],
    ids=lambda a: " ".join(a),
)
def test_exit_2_usage_errors(tmp_path: Path, args: list[str]) -> None:
    """Exit 2: unknown command or option, bad option value (RS 6.4, CV-6, CV-13, ADS 6.8)."""
    copy_fixture(WE, tmp_path, "WE")
    copy_fixture(CONVERT / "projects.minimal.csv", tmp_path)
    copy_fixture(CONVERT / "teams.base.yaml", tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    r = run_rt(args, cwd=tmp_path)
    assert r.code == 2, r.describe()
    assert r.stdout == b""
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_exit_4_missing_input(tmp_path: Path) -> None:
    """Exit 4: input unreadable."""
    r = run_rt(["render", "nope.yaml"], cwd=tmp_path)
    assert r.code == 4, r.describe()
    assert "nope.yaml" in r.stderr
    assert "Traceback" not in r.stderr
    assert run_rt(["validate", "nope.yaml"], cwd=tmp_path).code == 4
    assert run_rt(["convert", "nope.csv"], cwd=tmp_path).code == 4


def test_exit_4_output_not_writable(tmp_path: Path) -> None:
    """Exit 4: output not writable (directory does not exist)."""
    src = copy_fixture(WE, tmp_path)
    r = run_rt(["render", src.name, "-o", "no/such/dir/out.html"], cwd=tmp_path)
    assert r.code == 4, r.describe()
    assert "Traceback" not in r.stderr
    r2 = run_rt(["render", src.name, "--plan", "no/such/dir/p.json", "-o", "ok.html"], cwd=tmp_path)
    assert r2.code == 4, r2.describe()


def test_exit_4_base_missing(tmp_path: Path) -> None:
    copy_fixture(CONVERT / "projects.minimal.csv", tmp_path)
    r = run_rt(["convert", "projects.minimal.csv", "--base", "missing.yaml"], cwd=tmp_path)
    assert r.code == 4, r.describe()
    assert r.stdout == b""


def test_no_traceback_on_errors(tmp_path: Path) -> None:
    for f in INVALID.glob("*.yaml"):
        src = copy_fixture(f, tmp_path)
        r = run_rt(["render", src.name], cwd=tmp_path)
        assert "Traceback" not in r.stderr, f.name


def test_no_ansi_colour_when_not_a_tty(tmp_path: Path) -> None:
    """CLI-8: coloured output only when stderr is a TTY."""
    src = copy_fixture(WE, tmp_path)
    r = run_rt(["validate", src.name], cwd=tmp_path)
    assert "\x1b[" not in r.stderr


# --------------------------------------------------------------------------- NF-4 / NF-10


@pytest.mark.parametrize("fixture", [WE, DE, EX], ids=["WE", "DE", "EX"])
def test_nf4_deterministic_html_and_plan(tmp_path: Path, fixture: Path) -> None:
    """NF-4/OUT-5: same input, options and today -> byte-identical HTML and plan."""
    src = copy_fixture(fixture, tmp_path)
    hashes = []
    for i in range(2):
        r = run_rt(["render", src.name, "--summary", "-o", f"o{i}.html", "--plan", f"p{i}.json"], cwd=tmp_path)
        assert_ok(r)
        hashes.append(
            (
                hashlib.sha256((tmp_path / f"o{i}.html").read_bytes()).hexdigest(),
                hashlib.sha256((tmp_path / f"p{i}.json").read_bytes()).hexdigest(),
            )
        )
    assert hashes[0] == hashes[1]


def test_nf10_input_never_modified(tmp_path: Path) -> None:
    """NF-10: the tool never modifies the input file (render, validate, convert incl. base)."""
    files = [copy_fixture(f, tmp_path) for f in (WE, DE, EX)]
    csv = copy_fixture(CONVERT / "projects.pl.csv", tmp_path)
    base = copy_fixture(CONVERT / "teams.base.yaml", tmp_path)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in [*files, csv, base]}
    for f in files:
        run_rt(["render", f.name, "--summary", "--plan", f.stem + ".json"], cwd=tmp_path)
        run_rt(["validate", f.name, "--format", "json"], cwd=tmp_path)
    run_rt(
        ["convert", csv.name, "--base", base.name, "--map", "Projekt=name,Rozmiar=size", "-o", "out.yaml"], cwd=tmp_path
    )
    run_rt(["convert", csv.name, "--base", base.name, "--append", "--map", "Projekt=name,Rozmiar=size"], cwd=tmp_path)
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before}
    assert before == after


def test_cli1_option_overrides_file(tmp_path: Path) -> None:
    """CLI-1: command-line option > value in file (today)."""
    src = copy_fixture(WE, tmp_path)
    r = run_rt(["render", src.name, "--today", "2027-03-01", "--plan", "-", "-o", "x.html"], cwd=tmp_path)
    assert_ok(r)
    plan = json.loads(r.stdout)
    assert plan["today"] == "2027-03-01"


# --------------------------------------------------------------------------- schema and init


def _schema_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def test_schema_command(tmp_path: Path) -> None:
    """RS 6.1 / 3: rt schema prints the JSON Schema shipped with the tool; -o writes the same bytes."""
    r = run_rt(["schema"], cwd=tmp_path)
    assert r.code == 0, r.describe()
    data = json.loads(r.stdout.decode("utf-8"))
    assert data == json.loads(SCHEMA.read_text(encoding="utf-8"))
    r2 = run_rt(["schema", "-o", "s.json"], cwd=tmp_path)
    assert r2.code == 0
    assert (tmp_path / "s.json").read_bytes() == r.stdout


@pytest.mark.parametrize("fixture", [WE, DE, EX, MINIMAL], ids=["WE", "DE", "EX", "minimal"])
def test_schema_accepts_fixtures(tmp_path: Path, fixture: Path) -> None:
    """The schema printed by rt schema validates every valid fixture (jsonschema, draft 2020-12)."""
    jsonschema = pytest.importorskip("jsonschema")
    r = run_rt(["schema"], cwd=tmp_path)
    assert r.code == 0, r.describe()
    schema = json.loads(r.stdout.decode("utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(load_yaml(fixture.read_bytes())))
    assert not errors, [e.message for e in errors]


def test_schema_rejects_structural_errors() -> None:
    v = _schema_validator()
    for name in ("e002_unknown_key.yaml", "e010_missing_team.yaml", "e011_wrong_type.yaml"):
        data = load_yaml((INVALID / name).read_bytes())
        assert list(v.iter_errors(data)), name


def test_init_stdout_content(tmp_path: Path) -> None:
    """RS 6.1/13.2: rt init - writes the commented starter (roadmap.example.yaml) to stdout;
    --minimal writes the minimal example."""
    r = run_rt(["init", "-"], cwd=tmp_path)
    assert r.code == 0, r.describe()
    assert list(tmp_path.iterdir()) == []
    assert load_yaml(r.stdout) == load_yaml(EX.read_bytes())
    assert b"#" in r.stdout, "starter file is commented"
    m = run_rt(["init", "--minimal", "-"], cwd=tmp_path)
    assert m.code == 0, m.describe()
    assert load_yaml(m.stdout) == load_yaml(MINIMAL.read_bytes())
    assert re.search(rb"\r", r.stdout + m.stdout) is None


# --------------------------------------------------------------------------- outputs and limits


@pytest.mark.skipif(not Path("/dev/null").exists(), reason="POSIX device files")
def test_output_to_dev_null(tmp_path: Path) -> None:
    """RS 6.4: exit 4 only when the output is not writable; /dev/null is writable, so
    `rt render WE -o /dev/null` succeeds (see work/defects/D-001.md, CLI-3)."""
    src = copy_fixture(WE, tmp_path)
    r = run_rt(["render", src.name, "-o", "/dev/null", "-q"], cwd=tmp_path)
    assert r.code == 0, r.describe()
    p = run_rt(["render", src.name, "--plan", "/dev/null", "-o", "x.html", "-q"], cwd=tmp_path)
    assert p.code == 0, p.describe()


def test_st1_validate_json_and_plan_to_stdout(tmp_path: Path) -> None:
    """ST-1: validate --format json --plan - sends two artifacts to stdout -> exit 2."""
    src = copy_fixture(WE, tmp_path)
    r = run_rt(["validate", src.name, "--format", "json", "--plan", "-"], cwd=tmp_path)
    assert r.code == 2, r.describe()
    assert r.stdout == b""


def test_nf3_stress_performance(tmp_path: Path) -> None:
    """NF-3: 50 teams, 500 projects, 60 months render in under 2 s with HTML under 2 MB."""
    import time

    from rtkit import make_stress_yaml

    src = tmp_path / "stress.yaml"
    src.write_text(make_stress_yaml(), encoding="utf-8")
    run_rt(["--version"])  # warm the interpreter caches
    t0 = time.perf_counter()
    r = run_rt(["render", src.name, "-o", "stress.html", "-q"], cwd=tmp_path)
    elapsed = time.perf_counter() - t0
    assert r.code == 0, r.describe()
    size = (tmp_path / "stress.html").stat().st_size
    assert size < 2 * 1024 * 1024, size
    assert elapsed < 2.0, f"render took {elapsed:.2f} s"


def test_nf11_convert_performance(tmp_path: Path) -> None:
    """NF-11: rt convert handles a 10,000-row CSV in under 2 s."""
    import time

    rows = ["name,size,team,subdomain,start,description"]
    for i in range(10_000):
        size = ["S", "M", "L", "XL"][i % 4]
        rows.append(
            f"Projekt {i:05d} – płatności,{size},Zespół {i % 50},Obszar {i % 10},2027-{i % 12 + 1:02d},Opis {i}"
        )
    (tmp_path / "big.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    t0 = time.perf_counter()
    r = run_rt(["convert", "big.csv", "-o", "big.yaml", "-q"], cwd=tmp_path)
    elapsed = time.perf_counter() - t0
    assert r.code == 0, r.describe()
    assert elapsed < 2.0, f"convert took {elapsed:.2f} s"


@pytest.mark.skipif(sys.platform == "win32", reason="pty is POSIX only")
def test_no_color_env_on_tty(tmp_path: Path) -> None:
    """CLI-8: with NO_COLOR set there are no ANSI colours even when stderr is a terminal."""
    import os
    import pty
    import subprocess

    from rtkit import rt_cmd, rt_env

    src = copy_fixture(WE, tmp_path)
    master, slave = pty.openpty()
    try:
        proc = subprocess.Popen(
            rt_cmd(["validate", src.name]),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=slave,
            cwd=tmp_path,
            env=rt_env(NO_COLOR="1"),
        )
        os.close(slave)  # the child keeps its own copy; EOF/EIO arrives when it exits
        chunks = []
        while True:
            try:
                data = os.read(master, 4096)
            except OSError:
                break
            if not data:
                break
            chunks.append(data)
        proc.wait(timeout=60)
    finally:
        os.close(master)
    text = b"".join(chunks).decode("utf-8", "replace")
    assert proc.returncode == 0
    assert "W001" in text
    assert "\x1b[" not in text
