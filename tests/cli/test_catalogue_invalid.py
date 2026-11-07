"""Validation catalogue (ADS 10.3, RS section 9): one fixture per error / warning code.

Each ``tests/fixtures/invalid/<code>_<name>.yaml`` starts with

    # expect: E030 at 25:11, W005
    # args: --on-conflict error          (optional)

``CODE at L:C`` asserts code and 1-based position; a bare ``CODE`` asserts the code only (used where
RS section 9 does not pin the node, see work/questions.md Q-3). The set of reported diagnostics
must equal the expectation exactly. Expected exit: 3 with E060/E061, else 1 with any error, else 0.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest
from rtkit import INVALID, copy_fixture, run_rt

FILES = sorted(INVALID.glob("*.yaml"))
ITEM = re.compile(r"^(?P<code>[EW]\d{3})(?: at (?P<line>\d+):(?P<col>\d+))?$")

RS_CODES_FOR_YAML = (
    ["E001", "E002", "E003", "E004", "E010", "E011", "E012", "E013"]
    + [f"E02{i}" for i in range(6)]
    + [f"E03{i}" for i in range(10)]
    + ["E040", "E041", "E042", "E043", "E050", "E051", "E060", "E061"]
    + [f"W{i:03d}" for i in range(1, 16)]
)


def parse_header(path: Path) -> tuple[list[tuple[str, int | None, int | None]], list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# expect: "), f"{path.name}: first line must be '# expect: …'"
    expected = []
    for item in lines[0].removeprefix("# expect: ").split(","):
        m = ITEM.match(item.strip())
        assert m, f"{path.name}: bad expectation {item!r}"
        expected.append((m["code"], int(m["line"]) if m["line"] else None, int(m["col"]) if m["col"] else None))
    args = shlex.split(lines[1].removeprefix("# args: ")) if len(lines) > 1 and lines[1].startswith("# args: ") else []
    return expected, args


def test_catalogue_covers_every_yaml_code() -> None:
    """Every error and warning code of RS 9 that applies to YAML input has at least one fixture."""
    covered = {c for f in FILES for c, _, _ in parse_header(f)[0]}
    assert set(RS_CODES_FOR_YAML) <= covered, sorted(set(RS_CODES_FOR_YAML) - covered)
    for f in FILES:
        assert re.match(r"^[ew]\d{3}_[a-z0-9_]+\.yaml$", f.name), f.name
        assert f.name[:4].upper() in {c for c, _, _ in parse_header(f)[0]}, f"{f.name}: code prefix not expected"


@pytest.mark.parametrize("path", FILES, ids=[f.stem for f in FILES])
def test_catalogue(path: Path, tmp_path: Path) -> None:
    expected, args = parse_header(path)
    src = copy_fixture(path, tmp_path)
    r = run_rt(["validate", src.name, *args], cwd=tmp_path)
    actual = [(d.code, d.line, d.col) for d in r.diags]
    for d in r.diags:
        assert d.file == src.name, f"diagnostic file must be the input name: {d.file!r}"
        assert d.severity == ("error" if d.code.startswith("E") else "warning"), d
    remaining = list(actual)
    missing = []
    for code, line, col in [e for e in expected if e[1] is not None] + [e for e in expected if e[1] is None]:
        hit = next(
            (a for a in remaining if a[0] == code and (line is None or (a[1], a[2]) == (line, col))),
            None,
        )
        if hit is None:
            missing.append((code, line, col))
        else:
            remaining.remove(hit)
    assert not missing and not remaining, f"\nmissing:    {missing}\nunexpected: {remaining}\n{r.describe()}"
    codes = {c for c, _, _ in expected}
    want_exit = 3 if codes & {"E060", "E061"} else 1 if any(c.startswith("E") for c in codes) else 0
    assert r.code == want_exit, r.describe()
    assert r.stdout == b""
    assert sorted(p.name for p in tmp_path.iterdir()) == [src.name]


def test_catalogue_strict_turns_warnings_into_failure(tmp_path: Path) -> None:
    """--strict: any warning fixture fails with exit 1."""
    src = copy_fixture(INVALID / "w001_delay.yaml", tmp_path)
    r = run_rt(["validate", src.name, "--strict"], cwd=tmp_path)
    assert r.code == 1, r.describe()
    assert "W001" in r.codes()


@pytest.mark.parametrize(
    ("fixture", "code", "fragment"),
    [
        ("e002_unknown_key.yaml", "E002", 'did you mean "color"?'),
        (
            "e030_unknown_team.yaml",
            "E030",
            'project "Card tokens" references unknown team "blik2" (did you mean "blik"?)',
        ),
        ("e034_unknown_dependency.yaml", "E034", 'did you mean "Base project"?'),
        (
            "w001_delay.yaml",
            "W001",
            'project "Delayed" delayed 14 days (requested 2027-01-01, starts 2027-01-15): no free slot in team "blik"',
        ),
        (
            "w011_over_capacity.yaml",
            "W011",
            'project "Overflowing" exceeds team "blik" capacity; placed in overflow lane +1',
        ),
    ],
)
def test_catalogue_message_fragment(tmp_path: Path, fixture: str, code: str, fragment: str) -> None:
    """Message parts the RS fixes: did-you-mean hints (IN-3) and plan-contract texts (W001, W011)."""
    path = INVALID / fixture
    _, args = parse_header(path)
    src = copy_fixture(path, tmp_path)
    r = run_rt(["validate", src.name, *args], cwd=tmp_path)
    msgs = [d.message for d in r.diags if d.code == code]
    assert msgs, r.describe()
    assert any(fragment in m for m in msgs), msgs
