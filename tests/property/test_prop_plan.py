"""Property tests for scheduling and colouring (ADS 10.2) and the differential test against the oracle (ADS 10.1).

Generated models: 1–5 teams with 1–4 slots, 0–40 projects, sizes 1–26 weeks, starts within 24 months or omitted,
~10 % ongoing, dependencies only to earlier finite projects.
"""

from __future__ import annotations

import itertools
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))

from modelkit import load_text, oracle

from rt.diagnostics import Code, Collector
from rt.plan import compute_plan, to_json
from rt.plan.types import Plan
from rt.schedule.horizon import anchor

EXAMPLES = int(os.environ.get("RT_HYPOTHESIS_EXAMPLES", "150"))  # CI: 500 (ADS 10.1)
COLORS = ("indigo", "green", "orange", "pink", "sky", "amber", "violet", "teal", "lime", "sand")


@dataclass(frozen=True)
class Spec:
    yaml: str
    has_pins: bool
    project_count: int


@st.composite
def roadmaps(draw: st.DrawFn, *, pins: bool = False, min_projects: int = 0) -> Spec:
    team_count = draw(st.integers(1, 5))
    split = draw(st.integers(1, team_count))  # teams [0, split) in subdomain one, the rest in two
    slots = [draw(st.integers(1, 4)) for _ in range(team_count)]
    sizes = {f"Z{i}": draw(st.integers(1, 26)) for i in range(draw(st.integers(1, 4)))}
    lines = ["version: 1", "roadmap:", "  title: Generated"]
    hstart = draw(st.none() | st.integers(0, 12))
    if hstart is not None:
        lines.append(f"  horizon: {{ start: 2027-{hstart % 12 + 1:02d} }}")
    lines.append(f"  today: 2027-{draw(st.integers(1, 12)):02d}-{draw(st.integers(1, 28)):02d}")
    gap = draw(st.sampled_from([0, 7, 14, 30]))
    lines += ["sizes:", *(f"  {k}: {v}" for k, v in sizes.items())]
    lines += ["scheduling:", f"  adjacency_gap_days: {gap}", "subdomains:"]
    for sd, teams in (("one", range(split)), ("two", range(split, team_count))):
        if not teams:
            continue
        lines += [f"  - id: {sd}", f"    name: {sd}", "    teams:"]
        for t in teams:
            lines += [f"      - id: t{t}", f"        name: T{t}", f"        parallel_projects: {slots[t]}"]
    lines.append("projects:")
    count = draw(st.integers(min_projects, 40))
    finite: list[int] = []
    has_pins = False
    if count == 0:
        lines[-1] = "projects: []"
    for seq in range(1, count + 1):
        lines += [f"  - id: p{seq}", f"    name: P{seq}", f"    team: t{draw(st.integers(0, team_count - 1))}"]
        ongoing = draw(st.integers(0, 9)) == 0
        if ongoing:
            lines.append("    ongoing: true")
        else:
            lines.append(f"    size: {draw(st.sampled_from(sorted(sizes)))}")
        start = draw(st.none() | st.integers(0, 23))
        if start is not None:
            lines.append(f"    start: {2027 + start // 12}-{start % 12 + 1:02d}")
        if finite and draw(st.booleans()):
            deps = draw(st.lists(st.sampled_from(finite), min_size=1, max_size=3, unique=True))
            lines.append(f"    depends_on: [{', '.join(f'p{d}' for d in deps)}]")
        if pins and draw(st.integers(0, 4)) == 0:
            has_pins = True
            lines.append(f"    color: {draw(st.sampled_from(COLORS))}")
        if not ongoing:
            finite.append(seq)
    return Spec("\n".join(lines) + "\n", has_pins, count)


def plan_of(text: str, **kw: Any) -> tuple[Plan | None, Collector]:
    diags = Collector()
    return compute_plan(load_text(text, "gen.yaml", **kw), diags), diags


def check_schedule_invariants(text: str, mode: str) -> None:
    m = load_text(text, "gen.yaml", on_conflict=mode)
    plan, diags = plan_of(text, on_conflict=mode)
    if plan is None:
        codes = {d.code for d in diags.errors}
        assert codes <= {Code.E060, Code.E061}
        if mode != "error":
            assert Code.E061 not in codes
        return
    base_anchor = anchor(m.settings)
    by_seq = {p.seq: p for p in plan.projects}
    lanes: dict[tuple[str, int], list[Any]] = {}
    for p in plan.projects:
        lanes.setdefault((p.team, p.lane), []).append(p)
        base = p.requested_start or base_anchor
        assert p.earliest_start >= base
        for d in p.depends_on:
            dep_end = by_seq[d].end
            assert dep_end is not None and p.earliest_start >= dep_end
        assert p.start >= p.earliest_start
        if p.requested_start is None:
            assert not p.overflow and p.delay_days == 0 and "auto_start" in p.flags
        else:
            assert p.delay_days == (p.start - p.requested_start).days
        if mode == "delay":
            assert not p.overflow
        if mode == "overflow" and p.requested_start is not None:
            assert p.start == p.earliest_start
        if p.end is not None:
            weeks = p.weeks
            assert weeks is not None and p.end - p.start == timedelta(days=7 * weeks)
    for items in lanes.values():
        items.sort(key=lambda x: x.start)
        for a, b in itertools.pairwise(items):
            assert a.end is not None and a.end <= b.start
    again, _ = plan_of(text, on_conflict=mode)
    assert again is not None and to_json(again) == to_json(plan)


@settings(max_examples=EXAMPLES, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(spec=roadmaps(), mode=st.sampled_from(["delay", "overflow", "error"]))
def test_schedule_invariants(spec: Spec, mode: str) -> None:
    check_schedule_invariants(spec.yaml, mode)


@settings(max_examples=EXAMPLES, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(spec=roadmaps(pins=True))
def test_colouring_invariants(spec: Spec) -> None:
    plan, _ = plan_of(spec.yaml)
    if plan is None:
        return
    w007 = any(w.code == "W007" for w in plan.warnings)
    w009 = any(w.code == "W009" for w in plan.warnings)
    by_seq = {p.seq: p for p in plan.projects}
    for p in plan.projects:
        if p.visible is None:
            assert p.color_index is None and not p.neighbors
            continue
        assert p.color_index is not None
        for n in p.neighbors:
            assert p.seq in by_seq[n].neighbors
            if not w007 and not w009:
                assert by_seq[n].color_index != p.color_index
    if not spec.has_pins and all(len(p.neighbors) < 10 for p in plan.projects):
        assert not w007


def _normalise(data: dict[str, Any]) -> dict[str, Any]:
    """Mask what the oracle does not model: W005 positions (oracle: none) and W007 wording."""
    rows = []
    for w in data["warnings"]:
        if w["code"] == "W005":
            w = {**w, "line": None, "column": None}
        if w["code"] == "W007":
            w = {**w, "message": "W007"}
        rows.append(w)
    data = {**data, "warnings": sorted(rows, key=lambda w: (w["code"], w["line"] or 0, w["column"] or 0))}
    data["rt_version"] = "X"
    return data


@settings(max_examples=EXAMPLES, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(spec=roadmaps(min_projects=1), mode=st.sampled_from(["delay", "delay", "overflow"]))
def test_differential_against_reference_oracle(spec: Spec, mode: str) -> None:
    ref_module = oracle()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "gen.yaml"
        path.write_text(spec.yaml, encoding="utf-8")
        try:
            ref: dict[str, Any] | None = ref_module.run(str(path), on_conflict=mode)
        except SystemExit as exc:
            assert str(exc).startswith("E060")
            ref = None
    plan, diags = plan_of(spec.yaml, on_conflict=mode)
    if ref is None:
        assert plan is None and Code.E060 in {d.code for d in diags.errors}
        return
    assert plan is not None
    mine = json.loads(to_json(plan))
    assert _normalise(mine) == _normalise(json.loads(json.dumps(ref)))
