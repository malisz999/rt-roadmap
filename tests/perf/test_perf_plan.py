"""Performance of the computing core and the stress generator (RS NF-3, ADS 9.6; AT-44 input)."""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))

from modelkit import load_text

from rt.diagnostics import Collector
from rt.plan import compute_plan, to_json

ROOT = Path(__file__).resolve().parents[2]


def gen_stress() -> ModuleType:
    spec = importlib.util.spec_from_file_location("rt_gen_stress", ROOT / "tools" / "gen_stress.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.slow
def test_stress_generator_is_deterministic_and_sized(tmp_path: Path) -> None:
    gen = gen_stress()
    text = gen.generate()
    assert text == gen.generate()
    assert text.count("\n  - id: p-") == 500
    assert text.count("      - id: team-") == 50
    assert "horizon: { start: 2027-01, end: 2031-12 }" in text
    out = tmp_path / "stress.yaml"
    assert gen.main([str(out)]) == 0
    assert out.read_text(encoding="utf-8") == text


@pytest.mark.slow
@pytest.mark.parametrize("mode", ["delay", "overflow"])
def test_schedule_colour_load_budget(mode: str) -> None:
    text = gen_stress().generate()
    model = load_text(text, "stress.yaml", on_conflict=mode)
    best = float("inf")
    for _ in range(3):
        started = time.perf_counter()
        plan = compute_plan(model, Collector())
        best = min(best, time.perf_counter() - started)
        assert plan is not None
    assert best < 0.2  # ADS 9.6: schedule, colour, load within 200 ms at 500 projects
    assert len(plan.projects) == 500 and len(plan.teams) == 50
    assert len(plan.monthly_load.months) == 60
    assert to_json(plan)
