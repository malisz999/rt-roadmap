"""Command line (ADS 8.3, RS 6): argparse, usage checks, exit codes, the clock and the standard streams.

Everything that can be checked without reading input is checked here (RS CLI-2, ST-1, CV-13), so usage errors
exit 2 before a byte of input is read. `date.today()` is read only here (ADR-5).
"""

from __future__ import annotations

import argparse
import codecs
import contextlib
import functools
import os
import sys
import traceback
import unicodedata
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any, NoReturn

from rt import __version__
from rt.diagnostics import suggest
from rt.io.streams import ClosedPipeError, IOPort, SystemIO
from rt.model.fields import SIZE_LABEL_RE, WEEKS
from rt.model.types import Mode
from rt.options import ConvertOptions, InitOptions, RenderOptions, SchemaOptions
from rt.timeutil import Month, parse_date

EXIT_USAGE = 2
EXIT_INTERNAL = 70  # ADS 13.1 C1
EXIT_CLOSED_PIPE = 141  # RS ST-6
EXIT_INTERRUPTED = 130

CONVERT_COLUMNS: tuple[str, ...] = (
    "name",
    "size",
    "team",
    "product",
    "subdomain",
    "start",
    "ongoing",
    "depends_on",
    "id",
    "description",
    "color",
)
DELIMITERS = {"comma": ",", "semicolon": ";", "tab": "\t"}
NO_INPUT = "no input; give a file or pipe data into rt"


class UsageError(Exception):
    """A usage problem: printed as the parser's usage line plus `rt: error: …`, exit 2."""

    def __init__(self, parser: argparse.ArgumentParser, message: str) -> None:
        super().__init__(message)
        self.parser = parser
        self.message = message


class _Exit(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(status)
        self.status = status


class _Parser(argparse.ArgumentParser):
    """ArgumentParser that never calls sys.exit and sends its text through the IOPort."""

    io: IOPort | None = None
    commands: dict[str, _Parser]

    def error(self, message: str) -> NoReturn:
        raise UsageError(self, message)

    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
        if message:
            self._print_message(message, sys.stderr)
        raise _Exit(status)

    def _print_message(self, message: str, file: Any = None) -> None:
        if not message:
            return
        io = self.io
        if io is None:  # pragma: no cover - every parser built here has an io
            super()._print_message(message, file)
        elif file is sys.stderr:
            io.err(message)
        else:  # --help and --version are the content of their run: stdout, as bytes
            io.write("-", message.encode("utf-8"))


_formatter = functools.partial(argparse.HelpFormatter, width=80, max_help_position=30)  # RS NF-9


# --- option value types ---------------------------------------------------------------------------------------


def _month(text: str) -> Month:
    try:
        return Month.parse(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f'invalid month "{text}"; expected YYYY-MM') from None


def _date(text: str) -> date:
    try:
        return parse_date(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f'invalid date "{text}"; expected YYYY-MM-DD') from None


def _slots(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f'"{text}" is not a whole number; expected 1–12') from None
    if not 1 <= value <= 12:
        raise argparse.ArgumentTypeError(f"{value} is out of range; expected 1–12")
    return value


def _encoding(text: str) -> str:
    try:
        codecs.lookup(text)
    except LookupError:
        raise argparse.ArgumentTypeError(f'unknown encoding "{text}"') from None
    return text


def _map_pieces(text: str) -> list[str]:
    """Split on commas; a piece without "=" joins the next one (comma kept), so headers may contain commas:
    `Opis, uwagi=description,Projekt=name` → [`Opis, uwagi=description`, `Projekt=name`]."""
    pieces: list[str] = []
    pending: str | None = None
    for part in text.split(","):
        joined = part if pending is None else f"{pending},{part}"
        if "=" in part:
            pieces.append(joined)
            pending = None
        else:
            pending = joined
    if pending is not None:
        raise argparse.ArgumentTypeError(f'expected "header=column" pairs separated by commas, got "{pending}"')
    return pieces


def _column_map(text: str) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for piece in _map_pieces(text):
        source, _, target = piece.rpartition("=")
        source = unicodedata.normalize("NFC", source.strip())
        target = target.strip().lower()
        if not source or not target:
            raise argparse.ArgumentTypeError(f'expected "header=column" pairs separated by commas, got "{piece}"')
        if target not in CONVERT_COLUMNS:
            raise argparse.ArgumentTypeError(f'"{target}" is not a column; use one of {", ".join(CONVERT_COLUMNS)}')
        pairs.append((source, target))
    return tuple(pairs)


def _sizes(text: str) -> tuple[tuple[str, int], ...]:
    sizes: list[tuple[str, int]] = []
    for part in text.split(","):
        label, sep, weeks_text = part.partition("=")
        label = label.strip()
        if not sep or not SIZE_LABEL_RE.match(label):
            raise argparse.ArgumentTypeError(f'expected "label=weeks" pairs such as "S=2,M=4", got "{part}"')
        try:
            weeks = int(weeks_text.strip())
        except ValueError:
            raise argparse.ArgumentTypeError(f'weeks of "{label}" must be a whole number, got "{weeks_text}"') from None
        if not WEEKS[0] <= weeks <= WEEKS[1]:
            raise argparse.ArgumentTypeError(f'size "{label}" must be {WEEKS[0]}–{WEEKS[1]} weeks, got {weeks}')
        if any(label == seen for seen, _ in sizes):
            raise argparse.ArgumentTypeError(f'size "{label}" is given twice')
        sizes.append((label, weeks))
    return tuple(sizes)


# --- parser -----------------------------------------------------------------------------------------------------


def build_parser(io: IOPort) -> _Parser:
    parser = _Parser(
        prog="rt",
        description="Render a YAML roadmap into one self-contained HTML file.",
        epilog='Run "rt <command> --help" for the options of a command.',
        formatter_class=_formatter,
        allow_abbrev=False,
    )
    parser.io = io
    parser.commands = {}
    parser.add_argument("--version", action="version", version=f"rt {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>", parser_class=_Parser)

    def command(name: str, help_text: str) -> _Parser:
        p: _Parser = sub.add_parser(
            name, help=help_text, description=help_text, formatter_class=_formatter, allow_abbrev=False
        )
        p.io = io
        parser.commands[name] = p
        return p

    def plan_options(p: _Parser) -> None:
        p.add_argument("--from", dest="horizon_start", type=_month, metavar="YYYY-MM", help="first month shown")
        p.add_argument("--to", dest="horizon_end", type=_month, metavar="YYYY-MM", help="last month shown")
        p.add_argument("--today", type=_date, metavar="YYYY-MM-DD", help="date of the Today line and anchor")
        p.add_argument(
            "--on-conflict",
            dest="on_conflict",
            choices=[m.value for m in Mode],
            help="delay | overflow | error",
        )
        p.add_argument("--plan", metavar="PATH", help="also write the plan as JSON (- = stdout)")
        p.add_argument("--strict", action="store_true", help="treat warnings as errors")

    def quiet(p: _Parser) -> None:
        p.add_argument("-q", "--quiet", action="store_true", help="no warnings or summary line")

    render = command("render", "Validate, schedule and write the roadmap as HTML.")
    render.add_argument("input", nargs="?", help="roadmap YAML file (- or omitted = stdin)")
    render.add_argument("-o", "--output", metavar="PATH", help="HTML output (- = stdout; default: <input>.html)")
    render.add_argument("--summary", action="store_true", help="add the summary section with monthly load")
    plan_options(render)
    quiet(render)

    validate = command("validate", "Validate and schedule only; print diagnostics.")
    validate.add_argument("input", nargs="?", help="roadmap YAML file (- or omitted = stdin)")
    plan_options(validate)
    validate.add_argument(
        "--format", choices=["text", "json"], default="text", help="diagnostics as text (stderr) or json (stdout)"
    )
    quiet(validate)

    convert = command("convert", "Convert a CSV project list into rt YAML.")
    convert.add_argument("input", nargs="?", help="CSV file (- or omitted = stdin)")
    convert.add_argument("-o", "--output", metavar="PATH", default="-", help="YAML output (default: stdout)")
    convert.add_argument("--base", metavar="PATH", help="rt YAML file with settings, sizes and teams")
    convert.add_argument("--append", action="store_true", help="keep the base projects; add the CSV rows after")
    convert.add_argument(
        "--map", dest="column_map", type=_column_map, metavar="SRC=COL,...", help="rename CSV headers to columns"
    )
    convert.add_argument("--team", metavar="ID|NAME", help="team for rows without a team")
    convert.add_argument("--title", metavar="TEXT", help="skeleton only: roadmap title (default: Roadmap)")
    convert.add_argument("--sizes", type=_sizes, metavar="L=W,...", help='skeleton only: sizes, e.g. "S=2,M=4,L=8"')
    convert.add_argument("--slots", type=_slots, metavar="N", help="skeleton only: parallel_projects, 1-12")
    convert.add_argument("--encoding", type=_encoding, default="utf-8", help="CSV encoding (default: utf-8)")
    convert.add_argument("--delimiter", choices=list(DELIMITERS), help="skip delimiter detection")
    convert.add_argument("--strict", action="store_true", help="treat warnings as errors")
    quiet(convert)

    init = command("init", "Write a commented starter roadmap file.")
    init.add_argument(
        "path", nargs="?", default="roadmap.yaml", help="file to write (default: roadmap.yaml; - = stdout)"
    )
    init.add_argument("--minimal", action="store_true", help="write the smallest valid file")
    init.add_argument("--force", action="store_true", help="overwrite an existing file")
    quiet(init)

    schema = command("schema", "Print the JSON Schema of the input format.")
    schema.add_argument("-o", "--output", metavar="PATH", default="-", help="output (default: stdout)")
    quiet(schema)
    return parser


# --- usage checks done before any input is read ----------------------------------------------------------------


def _resolve_input(parser: _Parser, given: str | None, io: IOPort) -> str:
    """RS CLI-2."""
    if given is not None:
        return given
    if io.stdin_is_tty():
        raise UsageError(parser, NO_INPUT)
    return "-"


def _same_file(a: str, b: str) -> bool:
    if a == "-" or b == "-":
        return False
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _render_options(parser: _Parser, args: argparse.Namespace, io: IOPort, today: date) -> RenderOptions:
    from rt.app import default_html_output

    source = _resolve_input(parser, args.input, io)
    is_render = args.command == "render"
    output = args.output if is_render else None
    if is_render:
        target = output if output is not None else default_html_output(source)
        if args.plan == "-" and target == "-":
            raise UsageError(
                parser, "the HTML and --plan - would both go to stdout; send one of them to a file (-o or --plan)"
            )
        if args.plan is not None and _same_file(args.plan, target):
            raise UsageError(parser, "--plan and the HTML output name the same file")
        if _same_file(source, target):
            raise UsageError(parser, f"the HTML output would overwrite the input file {source}; use -o")
    elif args.format == "json" and args.plan == "-":
        raise UsageError(
            parser, "--format json and --plan - would both go to stdout; write the plan to a file with --plan"
        )
    if args.plan is not None and _same_file(source, args.plan):
        raise UsageError(parser, f"--plan would overwrite the input file {source}")
    return RenderOptions(
        input=source,
        default_today=today,
        output=output,
        plan=args.plan,
        summary=getattr(args, "summary", False),
        horizon_start=args.horizon_start,
        horizon_end=args.horizon_end,
        today=args.today,
        on_conflict=Mode(args.on_conflict) if args.on_conflict else None,
        strict=args.strict,
        quiet=args.quiet,
        format=getattr(args, "format", "text"),
    )


def _convert_options(parser: _Parser, args: argparse.Namespace, io: IOPort, today: date) -> ConvertOptions:
    if args.base is not None:
        if args.base == "-":
            raise UsageError(parser, "--base must name a file; only the CSV may come from stdin")
        skeleton_only = [
            name
            for name, value in (("--title", args.title), ("--sizes", args.sizes), ("--slots", args.slots))
            if value is not None
        ]
        if skeleton_only:
            raise UsageError(parser, f"{', '.join(skeleton_only)} cannot be combined with --base (skeleton only)")
    elif args.append:
        raise UsageError(parser, "--append needs --base")
    source = _resolve_input(parser, args.input, io)
    if _same_file(source, args.output) or (args.base is not None and _same_file(args.base, args.output)):
        raise UsageError(parser, "the output would overwrite an input file; choose another -o")
    return ConvertOptions(
        input=source,
        default_today=today,
        output=args.output,
        base=args.base,
        append=args.append,
        column_map=args.column_map or (),
        team=unicodedata.normalize("NFC", args.team) if args.team is not None else None,
        title=args.title,
        sizes=args.sizes,
        slots=args.slots,
        encoding=args.encoding,
        delimiter=DELIMITERS[args.delimiter] if args.delimiter else None,
        strict=args.strict,
        quiet=args.quiet,
    )


def _unrecognized(parser: _Parser, extra: list[str]) -> str:
    """`unrecognized arguments: --frm 2027-01 (did you mean "--from"?)`."""
    options = [o for action in parser._actions for o in action.option_strings if o.startswith("--")]
    hint = next((suggest(word, options) for word in extra if word.startswith("--")), "")
    return f"unrecognized arguments: {' '.join(extra)}{hint}"


def _usage(io: IOPort, parser: argparse.ArgumentParser, message: str) -> int:
    io.err(parser.format_usage())
    io.err(f"rt: error: {message}\n")
    return EXIT_USAGE


def _dispatch(argv: Sequence[str] | None, io: IOPort) -> int:
    from rt import app

    parser = build_parser(io)
    run: Callable[[], int]
    try:
        args, extra = parser.parse_known_args(argv)
        if extra:
            target = parser.commands.get(args.command or "", parser)
            raise UsageError(target, _unrecognized(target, extra))
        if args.command is None:
            raise UsageError(parser, "missing command; use one of render, validate, convert, init, schema")
        sub = parser.commands[args.command]
        today = date.today()  # noqa: DTZ011 - the only clock read (ADR-5); local calendar date
        if args.command == "render":
            run = functools.partial(app.run_render, _render_options(sub, args, io, today), io)
        elif args.command == "validate":
            run = functools.partial(app.run_validate, _render_options(sub, args, io, today), io)
        elif args.command == "convert":
            run = functools.partial(app.run_convert, _convert_options(sub, args, io, today), io)
        elif args.command == "init":
            init = InitOptions(path=args.path, minimal=args.minimal, force=args.force, quiet=args.quiet)
            run = functools.partial(app.run_init, init, io)
        else:
            run = functools.partial(app.run_schema, SchemaOptions(output=args.output, quiet=args.quiet), io)
    except _Exit as done:
        return done.status
    except UsageError as exc:
        return _usage(io, exc.parser, exc.message)
    return run()


def _setup_stderr() -> None:
    """RS IN-8: messages with Polish letters print on any console (ADS 8.3)."""
    stderr = sys.stderr
    reconfigure = getattr(stderr, "reconfigure", None)
    if reconfigure is not None:
        with contextlib.suppress(OSError, ValueError):
            reconfigure(encoding="utf-8", errors="backslashreplace")


def main(argv: Sequence[str] | None = None, io: IOPort | None = None) -> int:
    """Run rt and return the exit code. Tests pass a FakeIO; the console script uses the real streams."""
    if io is None:
        _setup_stderr()
        io = SystemIO()
    try:
        return _dispatch(argv, io)
    except ClosedPipeError:
        silence = getattr(io, "silence_stdout", None)
        if callable(silence):
            silence()
        return EXIT_CLOSED_PIPE
    except KeyboardInterrupt:
        io.err("rt: interrupted\n")
        return EXIT_INTERRUPTED
    except Exception as exc:
        io.err(f"rt: internal error: {type(exc).__name__}: {exc}\nplease report this with the input file\n")
        if io.getenv("RT_DEBUG") == "1":
            io.err(traceback.format_exc())
        return EXIT_INTERNAL


def main_entry() -> None:
    sys.exit(main())
