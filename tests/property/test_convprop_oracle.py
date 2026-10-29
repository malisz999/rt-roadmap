"""Differential test: rt convert equals tools/reference_convert.py on generated valid CSVs (ADS 10.1).

Random delimiter, quoting, BOM, CRLF, header case and column order, Polish text, optional columns (product
included), skeleton and base mode; the base gets a products block. The oracle runs in a subprocess with the same
interpreter (it needs only ruamel.yaml).
"""

from __future__ import annotations

import csv
import io
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from rt.convert.command import run_convert
from rt.io.streams import FakeIO
from rt.options import ConvertOptions

ROOT = Path(__file__).resolve().parents[2]
ORACLE = ROOT / "tools" / "reference_convert.py"
BASE_FIXTURE = ROOT / "docs" / "fixtures" / "convert" / "teams.base.yaml"
PRODUCTS_BLOCK = """
products:
  - id: blik
    name: BLIK
    domain: channels
    owner: Anna Kowalska   # product owner
  - id: app-core
    name: Aplikacja
    domain: merchant
"""

WORDS = [
    "Płatności",
    "BLIK",
    "raty",
    "Łódź",
    "zwroty",
    "API",
    "v2",
    "ąćęłńóśźż",
    "Żółw",
    "eksport",
    "123",
    "yes",
    "a:b",
]
TEXT_CHARS = list("abcXYZ ąęłŻ;,\t\"'|#:-[]{}!&*?%@`0123456789")
SKELETON_TEAMS = [
    ("Karty", "Kanały płatności"),
    ("Płatności Łódź", "Merchant"),
    ("Zespół wspólny", ""),
    ("BLIK", "Kanały płatności"),
]
BASE_TEAMS = ["blik", "BLIK i przelewy", "app", "Aplikacja mobilna"]
PRODUCTS = ["blik", "BLIK", "app-core", "Aplikacja", ""]
SKELETON_SIZES = ["XS", "S", "M", "L", "XL", "XXL", "m", "xl", "s"]
BASE_SIZES = ["S", "M", "L", "s", "l"]


@dataclass
class Case:
    data: bytes
    base: bool


def _start(d: date, style: int) -> str:
    if style == 0:
        return f"{d.year:04d}-{d.month:02d}"
    if style == 1:
        return d.isoformat()
    return f"{d.day:02d}.{d.month:02d}.{d.year:04d}"


@st.composite
def cases(draw: st.DrawFn) -> Case:
    base = draw(st.booleans())
    optional = ["start", "ongoing", "depends_on", "id", "description", "color", "owner", "product"]
    if not base:
        optional += ["subdomain", "team"]
    required = ["name", "size", "team"] if base else ["name", "size"]  # the base has two teams (E105 otherwise)
    columns = [*required, *draw(st.lists(st.sampled_from(optional), unique=True))]
    columns = draw(st.permutations(columns))
    n = draw(st.integers(1, 8))
    rows: list[dict[str, str]] = []
    finite: list[str] = []
    ids: list[str] = []
    for i in range(n):
        name = " ".join(draw(st.lists(st.sampled_from(WORDS), min_size=1, max_size=3))) + f" {i}"
        ongoing = "ongoing" in columns and draw(st.integers(0, 4)) == 0
        row = {"name": draw(st.sampled_from([name, f" {name} "]))}
        sizes = BASE_SIZES if base else SKELETON_SIZES
        row["size"] = "" if ongoing and draw(st.booleans()) else draw(st.sampled_from(sizes))
        if ongoing and row["size"]:
            row["size"] = ""
        if "team" in columns:
            pool = BASE_TEAMS if base else [t for t, _ in SKELETON_TEAMS]
            row["team"] = draw(st.sampled_from(pool))
            if not base:
                row["subdomain"] = dict(SKELETON_TEAMS)[row["team"]]
        elif not base:
            row["subdomain"] = ""
        if "start" in columns and draw(st.booleans()):
            d = draw(st.dates(min_value=date(2026, 1, 1), max_value=date(2028, 12, 31)))
            row["start"] = _start(d, draw(st.integers(0, 2)))
        if "ongoing" in columns:
            row["ongoing"] = draw(
                st.sampled_from(["tak", "TRUE", "x", "1"] if ongoing else ["", "nie", "No", "0", "false"])
            )
        if "depends_on" in columns and finite:
            deps = draw(st.lists(st.sampled_from(finite), max_size=2, unique=True))
            row["depends_on"] = draw(st.sampled_from(["|", " | ", "\n"])).join(deps)
        if "id" in columns and draw(st.booleans()):
            ident = f"p{i}-x"
            ids.append(ident)
            row["id"] = ident
        if "description" in columns and draw(st.booleans()):
            row["description"] = draw(st.text(alphabet=TEXT_CHARS, min_size=1, max_size=30)).strip() or "opis"
        if "color" in columns and draw(st.booleans()):
            row["color"] = draw(st.sampled_from(["sky", "teal", "#AABBCC", "#c7d2fe"]))
        if "owner" in columns:
            row["owner"] = draw(st.sampled_from(["", "Anna", "Piotr"]))
        if "product" in columns:  # ignored with W020 in skeleton mode
            row["product"] = draw(st.sampled_from(PRODUCTS))
        if not ongoing:
            finite.append(row.get("name", name).strip())
        rows.append(row)
    if not base and "team" not in columns and "subdomain" in columns:
        for row in rows:
            row["subdomain"] = ""
    header = {c: draw(st.sampled_from([c, c.upper(), c.title(), f" {c} "])) for c in columns}
    header["owner"] = "Właściciel"
    delimiter = draw(st.sampled_from([",", ";", "\t"]))
    buf = io.StringIO(newline="")
    terminator = draw(st.sampled_from(["\n", "\r\n"]))
    if draw(st.booleans()):
        writer = csv.writer(buf, delimiter=delimiter, lineterminator=terminator, quoting=csv.QUOTE_ALL)
    else:
        writer = csv.writer(buf, delimiter=delimiter, lineterminator=terminator, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([header[c] for c in columns])
    for row in rows:
        writer.writerow([row.get(c, "") for c in columns])
        if draw(st.integers(0, 5)) == 0:
            writer.writerow([""] * len(columns))
    data = buf.getvalue().encode("utf-8")
    if draw(st.booleans()):
        data = b"\xef\xbb\xbf" + data
    return Case(data, base)


def _base(tmp: Path) -> Path:
    path = tmp / "teams.base.yaml"
    text = BASE_FIXTURE.read_text(encoding="utf-8").replace("\nprojects: []", PRODUCTS_BLOCK + "\nprojects: []")
    path.write_text(text, encoding="utf-8")
    return path


def _oracle(path: Path, base: Path | None) -> tuple[int, bytes]:
    argv = [sys.executable, str(ORACLE), str(path)]
    if base is not None:
        argv += ["--base", str(base)]
    proc = subprocess.run(argv, capture_output=True, check=False, timeout=60)
    return proc.returncode, proc.stdout


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
@given(cases())
def test_convert_equals_reference(tmp_path_factory: pytest.TempPathFactory, case: Case) -> None:
    tmp = tmp_path_factory.mktemp("conv")
    path = tmp / "projects.csv"
    path.write_bytes(case.data)
    base = _base(tmp) if case.base else None
    io_port = FakeIO(real_fs=True)
    opts = ConvertOptions(input=str(path), default_today=date(2026, 10, 24), base=str(base) if base else None)
    code = run_convert(opts, io_port)
    assert code == 0, io_port.stderr
    oracle_code, oracle_out = _oracle(path, base)
    assert oracle_code == 0
    assert io_port.stdout == oracle_out
