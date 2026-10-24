"""The `rt convert` use case."""

from __future__ import annotations

from rt.console import plural, print_diagnostics, print_line
from rt.convert.csv_source import read_csv
from rt.convert.emit import display_name
from rt.convert.merge import convert_csv
from rt.diagnostics import Collector
from rt.io.rawdoc import RawDoc
from rt.io.streams import STDOUT_NAME, IOPort
from rt.options import ConvertOptions

EXIT_OK = 0
EXIT_ERRORS = 1
EXIT_IO = 4


def _io_error(io: IOPort, action: str, spec: str, exc: OSError) -> int:
    reason = exc.strerror or str(exc)
    io.err(f"rt: error: cannot {action} {spec}: {reason}\n")
    return EXIT_IO


def _load_base(io: IOPort, path: str, diags: Collector) -> RawDoc | None:
    from rt.io.loader import load  # dev A's round-trip loader (ADS 6.8 step 6)

    data, source = io.read(path)
    return load(data, source, diags)


def run_convert(opts: ConvertOptions, io: IOPort) -> int:
    """Read the CSV (and --base), convert, validate, write YAML; print diagnostics and the summary line
    (RS CLI-7) to stderr. Returns the exit code."""
    diags = Collector()
    try:
        data, source = io.read(opts.input)
    except OSError as exc:
        return _io_error(io, "read", opts.input, exc)
    diags.default_source = source
    text: str | None = None
    table = read_csv(data, source, opts.encoding, opts.delimiter, diags)
    if table is not None and opts.base is not None:
        try:
            base = _load_base(io, opts.base, diags)
        except OSError as exc:
            return _io_error(io, "read", opts.base, exc)
        if base is not None:
            text = convert_csv(table, base, opts, diags)
    elif table is not None:
        text = convert_csv(table, None, opts, diags)

    failed = text is None or diags.has_errors() or (opts.strict and bool(diags.warnings))
    if failed or text is None:
        print_diagnostics(io, diags.sorted(), quiet=opts.quiet)
        return EXIT_ERRORS
    try:
        io.write(opts.output, text.encode("utf-8"))
    except OSError as exc:
        return _io_error(io, "write", opts.output, exc)
    print_diagnostics(io, diags.sorted(), quiet=opts.quiet)
    target = STDOUT_NAME if opts.output == "-" else opts.output
    count = len(table.rows) if table is not None else 0
    summary = f"rt: wrote {target} — {plural(count, 'project')} from {display_name(source)}"
    print_line(io, f"{summary}, {plural(len(diags.warnings), 'warning')}", quiet=opts.quiet)
    return EXIT_OK
