"""Traceability (ADS 10.4): every RS acceptance test AT-01..AT-74 has a test_at_<nn>_ function,
and tests/TRACEABILITY.md maps each AT to the file that holds it."""

from __future__ import annotations

import re
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1]
DEF = re.compile(r"^\s*def (test_at_(\d{2})_\w+)\(", re.M)


def _found() -> dict[int, set[str]]:
    out: dict[int, set[str]] = {}
    for f in TESTS.rglob("test_*.py"):
        for m in DEF.finditer(f.read_text(encoding="utf-8")):
            out.setdefault(int(m.group(2)), set()).add(f.relative_to(TESTS).as_posix())
    return out


def test_at_traceability_every_acceptance_test_has_a_function() -> None:
    found = _found()
    missing = [f"AT-{n:02d}" for n in range(1, 75) if n not in found]
    assert not missing, f"acceptance tests without a test_at_<nn>_ function: {missing}"
    extra = sorted(n for n in found if not 1 <= n <= 74)
    assert not extra, f"unknown AT numbers: {extra}"


def test_at_traceability_matrix_is_current() -> None:
    found = _found()
    matrix = (TESTS / "TRACEABILITY.md").read_text(encoding="utf-8")
    rows = dict(re.findall(r"^\| AT-(\d{2}) \|[^|]*\| ([^|]+?) \|", matrix, re.M))
    for n in range(1, 75):
        key = f"{n:02d}"
        assert key in rows, f"AT-{key} missing from tests/TRACEABILITY.md"
        files = {x.strip().strip("`") for x in rows[key].split(",")}
        assert files == found.get(n, set()), f"AT-{key}: matrix lists {files}, tests are in {found.get(n)}"
