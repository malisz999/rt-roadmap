"""cli: argparse, usage errors, input resolution, ST-1, exit codes 2/70/141 (RS 6, ADS 8.3)."""

from __future__ import annotations

from typing import Any

import pytest
from iokit import MINIMAL, run

from rt import app, cli
from rt.io.streams import ClosedPipeError
from rt.options import ConvertOptions


def test_version_goes_to_stdout() -> None:
    code, io = run(["--version"])
    assert code == 0 and io.stdout == b"rt 1.1.0\n" and io.stderr == ""


@pytest.mark.parametrize(
    "argv",
    [
        ["--help"],
        ["render", "--help"],
        ["validate", "-h"],
        ["convert", "--help"],
        ["init", "--help"],
        ["schema", "--help"],
    ],
)
def test_help_fits_80_columns(argv: list[str]) -> None:
    code, io = run(argv)
    assert code == 0
    lines = io.stdout.decode().splitlines()
    assert lines and max(len(line) for line in lines) <= 80


def test_unknown_option_is_usage_error_with_hint() -> None:
    code, io = run(["render", "x.yaml", "--frm", "2027-01"])
    assert code == 2 and io.stdout == b""
    assert io.stderr.startswith("usage: rt render")
    assert 'rt: error: unrecognized arguments: --frm 2027-01 (did you mean "--from"?)' in io.stderr
    assert io.stdin_reads == 0


@pytest.mark.parametrize(
    ("argv", "fragment"),
    [
        ([], "missing command"),
        (["frobnicate"], "invalid choice"),
        (["render", "x.yaml", "--from", "2027-13"], 'argument --from: invalid month "2027-13"; expected YYYY-MM'),
        (["render", "x.yaml", "--to", "27-01"], "argument --to: invalid month"),
        (["validate", "x.yaml", "--today", "2027-02-30"], "argument --today: invalid date"),
        (["render", "x.yaml", "--on-conflict", "nope"], "invalid choice"),
        (["validate", "x.yaml", "--format", "xml"], "invalid choice"),
        (["render", "x.yaml", "-o", "-", "--plan", "-"], "would both go to stdout"),
        (["render", "-", "--plan", "-"], "would both go to stdout"),
        (["validate", "x.yaml", "--format", "json", "--plan", "-"], "would both go to stdout"),
        (["render", "x.yaml", "-o", "p.json", "--plan", "p.json"], "same file"),
        (["render", "x.html"], "overwrite the input"),
        (["render", "x.yaml", "--plan", "x.yaml", "-o", "o.html"], "overwrite the input"),
        (["convert", "x.csv", "--base", "b.yaml", "--title", "T"], "--title cannot be combined with --base"),
        (["convert", "x.csv", "--base", "b.yaml", "--sizes", "S=1", "--slots", "2"], "--sizes, --slots cannot"),
        (["convert", "x.csv", "--base", "-"], "--base must name a file"),
        (["convert", "x.csv", "--append"], "--append needs --base"),
        (["convert", "x.csv", "--slots", "13"], "argument --slots: 13 is out of range"),
        (["convert", "x.csv", "--slots", "two"], "argument --slots"),
        (["convert", "x.csv", "--map", "Projekt=nazwa"], '"nazwa" is not a column'),
        (["convert", "x.csv", "--map", "Projekt=name,Opis, uwagi"], 'got "Opis, uwagi"'),
        (["convert", "x.csv", "--map", "=name"], 'got "=name"'),
        (["convert", "x.csv", "--map", "Projekt"], 'expected "header=column" pairs'),
        (["convert", "x.csv", "--sizes", "S=0"], 'size "S" must be 1–520 weeks'),
        (["convert", "x.csv", "--sizes", "S=x"], "whole number"),
        (["convert", "x.csv", "--sizes", "S=1,S=2"], "given twice"),
        (["convert", "x.csv", "--sizes", "extra-large=1"], "label=weeks"),
        (["convert", "x.csv", "--encoding", "nope"], 'unknown encoding "nope"'),
        (["convert", "x.csv", "--delimiter", "pipe"], "invalid choice"),
        (["convert", "x.csv", "-o", "x.csv"], "overwrite an input"),
    ],
)
def test_usage_errors_exit_2_before_reading(argv: list[str], fragment: str) -> None:
    code, io = run(argv, stdin=MINIMAL.encode())
    assert code == 2, io.stderr
    assert fragment in io.stderr
    assert "rt: error: " in io.stderr and io.stderr.startswith("usage: rt")
    assert io.stdout == b"" and io.stdin_reads == 0 and not io.files


@pytest.mark.parametrize("command", ["render", "validate", "convert"])
def test_no_input_on_a_terminal(command: str) -> None:
    code, io = run([command], stdin_tty=True)
    assert code == 2 and io.stdout == b""
    assert "rt: error: no input; give a file or pipe data into rt" in io.stderr


def test_omitted_input_reads_piped_stdin() -> None:
    code, io = run(["validate"], stdin=MINIMAL.encode())
    assert code == 0, io.stderr
    assert io.stdin_reads == 1
    assert io.stderr.endswith("rt: <stdin> is valid — 1 subdomain, 1 team, 1 project, 0 warnings\n")


def test_convert_options_are_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[ConvertOptions] = []

    def fake_convert(opts: ConvertOptions, io: Any) -> int:
        seen.append(opts)
        return 0

    monkeypatch.setattr(app, "run_convert", fake_convert)
    code, _ = run(
        [
            "convert",
            "--map",
            "Projekt=name, Rozmiar = SIZE",
            "--sizes",
            "S=2,M=4",
            "--slots",
            "2",
            "--delimiter",
            "semicolon",
            "--encoding",
            "cp1250",
            "--team",
            "Zespół",
            "--title",
            "Plan",
            "-q",
        ],
        stdin=b"name,size\n",
    )
    assert code == 0
    opts = seen[0]
    assert opts.input == "-" and opts.output == "-"
    assert opts.column_map == (("Projekt", "name"), ("Rozmiar", "size"))
    assert opts.sizes == (("S", 2), ("M", 4)) and opts.slots == 2
    assert opts.delimiter == ";" and opts.encoding == "cp1250" and opts.team == "Zespół"
    assert opts.title == "Plan" and opts.quiet and opts.base is None


def test_closed_pipe_returns_141_silently(monkeypatch: pytest.MonkeyPatch) -> None:
    code, io = run(["schema"], closed_stdout=True)
    assert code == 141 and io.stderr == "" and io.silenced


def test_internal_error_exit_70(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("kaputt")

    monkeypatch.setattr(app, "run_schema", boom)
    code, io = run(["schema"])
    assert code == 70
    assert io.stderr == "rt: internal error: RuntimeError: kaputt\nplease report this with the input file\n"
    code, io = run(["schema"], env={"RT_DEBUG": "1"})
    assert code == 70 and "Traceback" in io.stderr


def test_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    def stop(*args: Any, **kwargs: Any) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(app, "run_schema", stop)
    assert run(["schema"])[0] == 130


def test_main_entry_and_system_io(monkeypatch: pytest.MonkeyPatch, capsysbinary: pytest.CaptureFixture[bytes]) -> None:
    with pytest.raises(SystemExit) as info:
        monkeypatch.setattr("sys.argv", ["rt", "--version"])
        cli.main_entry()
    assert info.value.code == 0
    assert capsysbinary.readouterr().out == b"rt 1.1.0\n"


def test_closed_pipe_error_type() -> None:
    assert issubclass(ClosedPipeError, Exception)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Projekt=name", (("Projekt", "name"),)),
        (
            "Opis, uwagi, notatki=description,Projekt=name",
            (("Opis, uwagi, notatki", "description"), ("Projekt", "name")),
        ),
        ("Projekt=name,Notatki, inne=Description", (("Projekt", "name"), ("Notatki, inne", "description"))),
        ("a=b=team", (("a=b", "team"),)),
    ],
)
def test_map_headers_may_contain_commas(text: str, expected: tuple[tuple[str, str], ...]) -> None:
    assert cli._column_map(text) == expected
