"""Shared helpers for the black-box test suite (acceptance, cli, html, golden).

Every test drives the real CLI in a subprocess (``python -m rt``) inside a temporary
directory, so no test writes into the repository and no test imports ``rt`` code.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from functools import cached_property
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
DOCS_FIXTURES = REPO / "docs" / "fixtures"
FIXTURES = REPO / "tests" / "fixtures"
CONVERT = FIXTURES / "convert"
INVALID = FIXTURES / "invalid"
TOOLS = REPO / "tools"

WE = FIXTURES / "scheduling-worked-example.yaml"
WE_PLAN = FIXTURES / "scheduling-worked-example.expected.json"
DE = FIXTURES / "dependencies-example.yaml"
DE_PLAN = FIXTURES / "dependencies-example.expected.json"
EX = FIXTURES / "roadmap.example.yaml"
PE = FIXTURES / "products-example.yaml"
PE_PLAN = FIXTURES / "products-example.expected.json"
LE = FIXTURES / "lock-example.yaml"
LE_PLAN = FIXTURES / "lock-example.expected.json"
MINIMAL = FIXTURES / "roadmap.minimal.yaml"
SCHEMA = FIXTURES / "roadmap.schema.json"

PL_MAP = "Projekt=name,Rozmiar=size,Zespół=team,Start=start,Zależności=depends_on,Ciągły=ongoing,Opis=description"

VERSION = "1.3.0"

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
DIAG_RE = re.compile(
    r"^(?P<file>.+?)(?::(?P<line>\d+):(?P<col>\d+))?: (?P<sev>error|warning) (?P<code>[EW]\d{3}): (?P<msg>.*)$"
)


# --------------------------------------------------------------------------- running rt


@dataclasses.dataclass
class Diag:
    file: str
    line: int | None
    col: int | None
    severity: str
    code: str
    message: str

    @property
    def pos(self) -> tuple[int | None, int | None]:
        return (self.line, self.col)


def parse_diagnostics(stderr: str) -> list[Diag]:
    """Parse RS CLI-6 lines ``<file>:<line>:<col>: <error|warning> <code>: <message>``."""
    out = []
    for raw in _ANSI.sub("", stderr).splitlines():
        m = DIAG_RE.match(raw)
        if m:
            out.append(
                Diag(
                    file=m["file"],
                    line=int(m["line"]) if m["line"] else None,
                    col=int(m["col"]) if m["col"] else None,
                    severity=m["sev"],
                    code=m["code"],
                    message=m["msg"],
                )
            )
    return out


@dataclasses.dataclass
class Result:
    args: list[str]
    code: int
    stdout: bytes
    stderr: str

    @property
    def diags(self) -> list[Diag]:
        return parse_diagnostics(self.stderr)

    def codes(self, severity: str | None = None) -> list[str]:
        return [d.code for d in self.diags if severity is None or d.severity == severity]

    def describe(self) -> str:
        out = self.stdout[:400].decode("utf-8", "replace")
        head = f"rt {' '.join(self.args)} -> exit {self.code}"
        return f"{head}\n--- stderr ---\n{self.stderr[-3000:]}\n--- stdout ---\n{out}"


def rt_env(**extra: str) -> dict[str, str]:
    """Environment for rt: inherited, minus variables that would change stream behaviour."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("PYTHONIOENCODING", "PYTHONUTF8", "RT_DEBUG", "NO_COLOR", "PYTHONWARNINGS")
    }
    env.update(extra)
    return env


def rt_cmd(args: Iterable[Any]) -> list[str]:
    return [sys.executable, "-m", "rt", *[str(a) for a in args]]


def run_rt(
    args: Sequence[Any],
    stdin: bytes | None = b"",
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 120,
) -> Result:
    """Run ``python -m rt <args>``; stdin bytes are piped (``None`` = /dev/null)."""
    kwargs: dict[str, Any] = {}
    if stdin is None:
        kwargs["stdin"] = subprocess.DEVNULL
    else:
        kwargs["input"] = stdin
    proc = subprocess.run(
        rt_cmd(args),
        capture_output=True,
        cwd=str(cwd) if cwd is not None else None,
        env=env if env is not None else rt_env(),
        timeout=timeout,
        check=False,
        **kwargs,
    )
    # stderr is human text: Windows writes it with CRLF; compare messages line by line as LF.
    stderr = proc.stderr.decode("utf-8", "replace").replace("\r\n", "\n")
    return Result([str(a) for a in args], proc.returncode, proc.stdout, stderr)


def assert_ok(r: Result) -> None:
    assert r.code == 0, r.describe()


def copy_fixture(src: Path, dest_dir: Path, name: str | None = None) -> Path:
    dest = dest_dir / (name or src.name)
    shutil.copyfile(src, dest)
    return dest


# --------------------------------------------------------------------------- JSON / plan helpers

_VERSION_RE = re.compile(rb'"rt_version": "[^"]*"')


def mask_version(data: bytes) -> bytes:
    return _VERSION_RE.sub(b'"rt_version": "<masked>"', data)


def load_json(data: bytes | Path) -> Any:
    if isinstance(data, Path):
        data = data.read_bytes()
    return json.loads(data.decode("utf-8"))


def plan_project(plan: dict[str, Any], seq: int) -> dict[str, Any]:
    for p in plan["projects"]:
        if p["seq"] == seq:
            return p
    raise AssertionError(f"project seq {seq} not in plan")


def project_by_name(plan: dict[str, Any], name: str) -> dict[str, Any]:
    hits = [p for p in plan["projects"] if p["name"] == name]
    assert len(hits) == 1, f"expected exactly one project named {name!r}, got {len(hits)}"
    return hits[0]


def run_oracle(path: Path, **kwargs: str) -> dict[str, Any]:
    """Run tools/reference_plan.py (test oracle) on a YAML file in a subprocess."""
    args = [f"{k}={v}" for k, v in kwargs.items()]
    proc = subprocess.run(
        [sys.executable, str(TOOLS / "reference_plan.py"), str(path), *args],
        capture_output=True,
        check=True,
        timeout=120,
    )
    return json.loads(proc.stdout.decode("utf-8"))


def run_convert_oracle(args: Sequence[str], cwd: Path, stdin: bytes = b"") -> tuple[int, bytes, str]:
    proc = subprocess.run(
        [sys.executable, str(TOOLS / "reference_convert.py"), *args],
        input=stdin,
        capture_output=True,
        cwd=str(cwd),
        check=False,
        timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr.decode("utf-8", "replace")


# --------------------------------------------------------------------------- HTML helpers


def parse_html(data: bytes) -> Any:
    import lxml.html

    assert data, "no HTML produced"
    parser = lxml.html.HTMLParser(encoding="utf-8")
    return lxml.html.document_fromstring(data, parser=parser)


def style_decls(el: Any) -> dict[str, str]:
    """Inline style as {property: value}; whitespace-insensitive (``left:1px`` == ``left: 1px``)."""
    out: dict[str, str] = {}
    for part in (el.get("style") or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def css_text(doc: Any) -> str:
    return "\n".join((s.text or "") for s in doc.iter("style"))


def _css_rules(css: str) -> list[tuple[str, str]]:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(m.group(1).strip(), m.group(2)) for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css)]


def _custom_props(css: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for _sel, body in _css_rules(css):
        for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;]+)", body):
            props.setdefault(m.group(1), m.group(2).strip())
    return props


def _resolve_vars(text: str, props: dict[str, str]) -> str:
    for _ in range(5):
        new = re.sub(r"var\(\s*(--[\w-]+)\s*(?:,[^)]*)?\)", lambda m: props.get(m.group(1), m.group(0)), text)
        if new == text:
            break
        text = new
    return text


_PSEUDO = re.compile(r"::?[a-zA-Z-]+(\([^)]*\))?")


def matching_css(doc: Any, el: Any, css: str | None = None) -> str:
    """Concatenated declarations of every CSS rule (pseudo-classes/elements ignored) that
    matches ``el``, plus its inline style, with ``var(--x)`` references resolved."""
    from lxml.cssselect import CSSSelector

    css = css if css is not None else css_text(doc)
    bodies = [el.get("style") or ""]
    for selectors, body in _css_rules(css):
        if selectors.startswith("@"):
            continue
        for sel in selectors.split(","):
            plain = _PSEUDO.sub("", sel).strip()
            if not plain:
                continue
            try:
                matched = CSSSelector(plain)(doc)
            except Exception:
                continue
            if any(m is el for m in matched):
                bodies.append(body)
                break
    # inline custom properties of the element and its ancestors also feed var()
    props = _custom_props(css)
    for anc in [el, *el.iterancestors()]:
        for k, v in style_decls(anc).items():
            if k.startswith("--"):
                props[k] = v
    return _resolve_vars("\n".join(bodies), props)


def _glyph_escapes(glyph: str) -> list[str]:
    cp = ord(glyph)
    return [glyph, f"\\{cp:x}", f"\\{cp:X}", f"\\{cp:04x}", f"\\{cp:04X}", f"\\{cp:06x}"]


def shows_glyph(doc: Any, el: Any, glyph: str) -> bool:
    """True when ``glyph`` is in the element's text or in a CSS ``content`` that applies to it."""
    if glyph in el.text_content():
        return True
    css = css_text(doc)
    from lxml.cssselect import CSSSelector

    for selectors, body in _css_rules(css):
        if "content" not in body or not any(g in body for g in _glyph_escapes(glyph)):
            continue
        for sel in selectors.split(","):
            plain = _PSEUDO.sub("", sel).strip()
            if not plain:
                continue
            try:
                matched = CSSSelector(plain)(doc)
            except Exception:
                continue
            if any(m is el for m in matched):
                return True
    return False


def bars(doc: Any) -> dict[int, Any]:
    out = {}
    for b in doc.cssselect(".rt-bar"):
        seq = b.get("data-seq")
        assert seq is not None, "rt-bar without data-seq"
        assert int(seq) not in out, f"two rt-bar elements for seq {seq}"
        out[int(seq)] = b
    return out


def effective_lang(el: Any) -> str | None:
    for anc in [el, *el.iterancestors()]:
        if anc.get("lang") is not None:
            return str(anc.get("lang"))
    return None


def norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


PCT_SPACE = "[   ]?"


def pct_re(n: int) -> re.Pattern[str]:
    return re.compile(rf"(?<!\d){n}{PCT_SPACE}%")


# --------------------------------------------------------------------------- rendered fixtures


@dataclasses.dataclass
class Rendered:
    result: Result
    dir: Path
    html_path: Path
    plan_path: Path | None

    @cached_property
    def html(self) -> bytes:
        assert self.result.code == 0, self.result.describe()
        assert self.html_path.exists(), f"{self.html_path.name} was not written\n{self.result.describe()}"
        return self.html_path.read_bytes()

    @cached_property
    def plan_bytes(self) -> bytes:
        assert self.result.code == 0, self.result.describe()
        assert self.plan_path is not None and self.plan_path.exists(), "plan JSON was not written"
        return self.plan_path.read_bytes()

    @cached_property
    def plan(self) -> dict[str, Any]:
        return load_json(self.plan_bytes)  # type: ignore[no-any-return]

    @cached_property
    def doc(self) -> Any:
        return parse_html(self.html)

    @cached_property
    def css(self) -> str:
        return css_text(self.doc)

    @cached_property
    def bars(self) -> dict[int, Any]:
        return bars(self.doc)


def render_fixture(tmp: Path, fixture: Path, *extra: str, plan: bool = True, html_name: str | None = None) -> Rendered:
    """Copy ``fixture`` into ``tmp`` and run ``rt render <name> [--plan p.json] <extra>`` there.

    Without ``html_name`` the default output path (input with ``.html``) is used, as in AT-01.
    """
    src = copy_fixture(fixture, tmp)
    args: list[str] = ["render", src.name]
    if html_name:
        args += ["-o", html_name]
    if plan:
        args += ["--plan", "p.json"]
    args += list(extra)
    r = run_rt(args, cwd=tmp)
    html_path = tmp / (html_name or src.with_suffix(".html").name)
    return Rendered(r, tmp, html_path, tmp / "p.json" if plan else None)


@pytest.fixture(scope="session")
def we_render(tmp_path_factory: pytest.TempPathFactory) -> Rendered:
    """``rt render WE --plan p.json`` (AT-01..AT-06, AT-13)."""
    return render_fixture(tmp_path_factory.mktemp("we"), WE)


@pytest.fixture(scope="session")
def we_summary_render(tmp_path_factory: pytest.TempPathFactory) -> Rendered:
    return render_fixture(tmp_path_factory.mktemp("we_summary"), WE, "--summary")


@pytest.fixture(scope="session")
def we_overflow_render(tmp_path_factory: pytest.TempPathFactory) -> Rendered:
    return render_fixture(tmp_path_factory.mktemp("we_overflow"), WE, "--on-conflict", "overflow", "--summary")


@pytest.fixture(scope="session")
def de_render(tmp_path_factory: pytest.TempPathFactory) -> Rendered:
    """``rt render DE --plan p.json`` (AT-26..AT-29)."""
    return render_fixture(tmp_path_factory.mktemp("de"), DE)


@pytest.fixture(scope="session")
def pe_render(tmp_path_factory: pytest.TempPathFactory) -> Rendered:
    """``rt render PE --plan p.json``: the products example (AT-56..AT-58, AT-63)."""
    return render_fixture(tmp_path_factory.mktemp("pe"), PE)


@pytest.fixture(scope="session")
def ex_render(tmp_path_factory: pytest.TempPathFactory) -> Rendered:
    """``rt render EX --plan p.json``."""
    return render_fixture(tmp_path_factory.mktemp("ex"), EX)


# --------------------------------------------------------------------------- YAML helper


def load_yaml(data: bytes | str) -> Any:
    """Load YAML 1.2 into plain Python data (dates turned into ISO strings)."""
    import datetime as dt
    import io

    from ruamel.yaml import YAML

    if isinstance(data, bytes):
        data = data.decode("utf-8-sig")
    y = YAML(typ="safe", pure=True)
    obj = y.load(io.StringIO(data))

    def fix(o: Any) -> Any:
        if isinstance(o, dict):
            return {str(k): fix(v) for k, v in o.items()}
        if isinstance(o, list):
            return [fix(v) for v in o]
        if isinstance(o, dt.date):
            return o.isoformat()
        return o

    return fix(obj)


# --------------------------------------------------------------------------- stress input


def make_stress_yaml(teams: int = 50, projects: int = 500, months: int = 60) -> str:
    """NF-3 stress file: 50 teams, 500 projects, 60 months (generated here, not by tools/)."""
    out = [
        "version: 1",
        "roadmap:",
        "  title: Stress test",
        "  today: 2027-06-15",
        "  horizon: { start: 2027-01, end: " + f"{2027 + (months - 1) // 12}-{(months - 1) % 12 + 1:02d}" + " }",
        "sizes:",
        "  S: 2",
        "  M: 4",
        "  L: 8",
        "  XL: 13",
        "subdomains:",
    ]
    per_sub = 5
    for s in range(teams // per_sub):
        out += [f"  - id: sub-{s:02d}", f"    name: Subdomena {s:02d} – łańcuch źródeł", "    teams:"]
        for t in range(per_sub):
            tid = s * per_sub + t
            out += [
                f"      - id: team-{tid:02d}",
                f"        name: Zespół {tid:02d}",
                f"        parallel_projects: {1 + tid % 3}",
                f"        capacity: {{ developers: {2 + tid % 5}, testers: 1 }}",
            ]
    out.append("projects:")
    sizes = ["S", "M", "L", "XL"]
    for p in range(projects):
        team = p % teams
        month = (p // teams) * 6 % months
        y, m = 2027 + month // 12, month % 12 + 1
        out += [
            f"  - name: Projekt {p:03d} – płatności",
            f"    team: team-{team:02d}",
            f"    size: {sizes[p % 4]}",
            f"    start: {y}-{m:02d}",
            f"    description: Opis projektu {p} z polskimi znakami ąćęłńóśźż",
        ]
    return "\n".join(out) + "\n"


# Test modules import the helpers above with ``from rtkit import ...``. Registering the
# module under a unique name avoids clashes with other ``conftest`` modules (tests/unit…).
sys.modules.setdefault("rtkit", sys.modules[__name__])
