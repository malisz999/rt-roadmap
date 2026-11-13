"""Use cases: render, validate, convert, init, schema (ADS 4.2, 8.4). Each returns the process exit code.

Order for every command (ADS 8.4, RS ST-2): compute everything first; when errors exist (or warnings under
--strict) write no content, except `validate --format json` whose diagnostics are its content; otherwise write
the plan (if requested) and then the main output; diagnostics and the summary line go to stderr last.
"""

from __future__ import annotations

from importlib import resources
from typing import TYPE_CHECKING

from rt import __version__
from rt.console import plural, print_diagnostics, print_line
from rt.convert.command import run_convert
from rt.diagnostics import Collector, format_json
from rt.io.loader import load
from rt.io.streams import STDIN_NAME, STDOUT_NAME, IOPort
from rt.model.build import build_model
from rt.model.references import check_references
from rt.model.types import Overrides, ResolvedModel
from rt.options import InitOptions, RenderOptions, SchemaOptions

if TYPE_CHECKING:
    from rt.plan.types import Plan

__all__ = ["run_convert", "run_init", "run_render", "run_schema", "run_validate"]

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_SCHEDULING = 3
EXIT_IO = 4


def output_name(spec: str) -> str:
    """How an output is named in the summary line (RS ST-7)."""
    return STDOUT_NAME if spec == "-" else spec


def default_html_output(input_spec: str) -> str:
    """RS 6.2: the input path with `.html` instead of its suffix; stdout when the input is stdin."""
    if input_spec == "-":
        return "-"
    # String-based so the user's own separators survive (`a/roadmap.yaml` stays `a/roadmap.html` on Windows).
    name_start = max(input_spec.rfind("/"), input_spec.rfind("\\")) + 1
    dot = input_spec.rfind(".")
    if name_start < dot < len(input_spec) - 1:  # a suffix, as PurePath.suffix defines it
        return input_spec[:dot] + ".html"
    return input_spec + ".html"


def _error_text(exc: OSError) -> str:
    return exc.strerror or str(exc) or type(exc).__name__


def _io_error(io: IOPort, action: str, target: str, exc: OSError) -> int:
    io.err(f"rt: error: cannot {action} {target}: {_error_text(exc)}\n")
    return EXIT_IO


def _counts(model: ResolvedModel) -> str:
    return ", ".join(
        (
            plural(len(model.subdomains), "subdomain"),
            plural(len(model.teams), "team"),
            plural(len(model.projects), "project"),
        )
    )


def _analyse(opts: RenderOptions, io: IOPort, diags: Collector) -> tuple[ResolvedModel | None, Plan | None, str]:
    """Read → load → build → references → plan. Raises OSError when the input cannot be read."""
    data, source = io.read(opts.input)
    diags.default_source = source
    raw = load(data, source, diags)
    if raw is None:
        return None, None, source
    overrides = Overrides(
        default_today=opts.default_today,
        horizon_start=opts.horizon_start,
        horizon_end=opts.horizon_end,
        today=opts.today,
        on_conflict=opts.on_conflict,
    )
    model = build_model(raw, diags, overrides)
    if model is None:
        return None, None, source
    resolved = check_references(model, diags)
    if resolved is None or diags.has_errors():
        return resolved, None, source
    from rt.plan.build import compute_plan

    return resolved, compute_plan(resolved, diags), source


def _failure_code(diags: Collector) -> int:
    return EXIT_SCHEDULING if diags.has_scheduling_errors() else EXIT_INVALID


def _strict_failed(opts: RenderOptions, diags: Collector) -> bool:
    return opts.strict and bool(diags.warnings)


def _strict_note(io: IOPort, diags: Collector) -> None:
    io.err(f"rt: {plural(len(diags.warnings), 'warning')} treated as errors (--strict); nothing written\n")


def run_render(opts: RenderOptions, io: IOPort) -> int:
    diags = Collector(STDIN_NAME if opts.input == "-" else opts.input)
    try:
        model, plan, _source = _analyse(opts, io, diags)
    except OSError as exc:
        return _io_error(io, "read", opts.input, exc)

    if diags.has_errors() or plan is None or model is None:
        print_diagnostics(io, diags.sorted(), quiet=opts.quiet)
        return _failure_code(diags)
    if _strict_failed(opts, diags):
        print_diagnostics(io, diags.sorted())
        _strict_note(io, diags)
        return EXIT_INVALID

    # Build every output in memory before writing anything (ADR-13). Jinja2 is imported only here (ADS 9.6).
    from rt.layout.viewmodel import build_page
    from rt.plan.serialize import to_json
    from rt.render.renderer import render_html

    plan_bytes = to_json(plan).encode("utf-8") if opts.plan is not None else None
    html = render_html(build_page(plan, summary=opts.summary, version=__version__)).encode("utf-8")
    target = opts.output if opts.output is not None else default_html_output(opts.input)

    current = target
    try:
        if opts.plan is not None and plan_bytes is not None:
            current = opts.plan
            io.write(opts.plan, plan_bytes)
        current = target
        io.write(target, html)
    except OSError as exc:
        print_diagnostics(io, diags.sorted(), quiet=opts.quiet)
        return _io_error(io, "write", output_name(current), exc)

    print_diagnostics(io, diags.sorted(), quiet=opts.quiet)
    print_line(
        io,
        f"rt: wrote {output_name(target)} — {_counts(model)}, {plural(len(diags.warnings), 'warning')}",
        quiet=opts.quiet,
    )
    return EXIT_OK


def run_validate(opts: RenderOptions, io: IOPort) -> int:
    diags = Collector(STDIN_NAME if opts.input == "-" else opts.input)
    try:
        model, plan, source = _analyse(opts, io, diags)
    except OSError as exc:
        return _io_error(io, "read", opts.input, exc)

    failed = diags.has_errors() or plan is None or model is None
    strict_failed = not failed and _strict_failed(opts, diags)
    json_format = opts.format == "json"

    if json_format:
        # The diagnostics array is this command's content: written even when the run fails (RS ST-2).
        try:
            if not failed and not strict_failed and opts.plan is not None and plan is not None:
                _write_plan(io, opts.plan, plan)
            io.write("-", format_json(diags.sorted()).encode("utf-8"))
        except OSError as exc:
            return _io_error(io, "write", output_name(opts.plan or "-"), exc)
        if failed:
            return _failure_code(diags)
        if strict_failed:
            return EXIT_INVALID
    else:
        if failed:
            print_diagnostics(io, diags.sorted(), quiet=opts.quiet)
            return _failure_code(diags)
        if strict_failed:
            print_diagnostics(io, diags.sorted())
            _strict_note(io, diags)
            return EXIT_INVALID
        if opts.plan is not None and plan is not None:
            try:
                _write_plan(io, opts.plan, plan)
            except OSError as exc:
                print_diagnostics(io, diags.sorted(), quiet=opts.quiet)
                return _io_error(io, "write", output_name(opts.plan), exc)
        print_diagnostics(io, diags.sorted(), quiet=opts.quiet)

    assert model is not None
    print_line(
        io,
        f"rt: {source} is valid — {_counts(model)}, {plural(len(diags.warnings), 'warning')}",
        quiet=opts.quiet,
    )
    return EXIT_OK


def _write_plan(io: IOPort, spec: str, plan: Plan) -> None:
    from rt.plan.serialize import to_json

    io.write(spec, to_json(plan).encode("utf-8"))


def _resource(name: str) -> bytes:
    return resources.files("rt").joinpath("resources", name).read_bytes()


def run_init(opts: InitOptions, io: IOPort) -> int:
    data = _resource("roadmap.minimal.yaml" if opts.minimal else "roadmap.example.yaml")
    try:
        io.write(opts.path, data, exclusive=not opts.force and opts.path != "-")
    except FileExistsError:
        io.err(f"rt: error: {opts.path} already exists; use --force to overwrite it\n")
        return EXIT_IO
    except OSError as exc:
        return _io_error(io, "write", output_name(opts.path), exc)
    hint = "" if opts.path == "-" else f"; render it with: rt render {opts.path}"
    print_line(io, f"rt: wrote {output_name(opts.path)}{hint}", quiet=opts.quiet)
    return EXIT_OK


def run_schema(opts: SchemaOptions, io: IOPort) -> int:
    try:
        io.write(opts.output, _resource("roadmap.schema.json"))
    except OSError as exc:
        return _io_error(io, "write", output_name(opts.output), exc)
    print_line(io, f"rt: wrote {output_name(opts.output)}", quiet=opts.quiet)
    return EXIT_OK
