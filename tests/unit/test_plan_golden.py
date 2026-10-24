"""Plan JSON against the expected files and the reference oracle (RS AT-01, AT-07, AT-12, AT-26, AT-30, AT-31)."""

from __future__ import annotations

import json
import re

import pytest
from modelkit import DE, FIXTURES, WE, load_path, oracle

from rt.diagnostics import Collector
from rt.plan import compute_plan, to_json


def plan_json(path: object, **kw: str) -> str:
    plan = compute_plan(load_path(str(path), **kw), Collector())
    assert plan is not None
    return to_json(plan)


def mask_version(text: str) -> str:
    return re.sub(r'"rt_version": "[^"]*"', '"rt_version": "X"', text, count=1)


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [(WE, "scheduling-worked-example.expected.json"), (DE, "dependencies-example.expected.json")],
)
def test_expected_files_byte_for_byte(fixture: object, expected: str) -> None:
    want = (FIXTURES / expected).read_bytes().decode("utf-8")
    assert mask_version(plan_json(fixture)) == mask_version(want)


@pytest.mark.parametrize(
    ("fixture", "kw"),
    [
        (WE, {"on_conflict": "overflow"}),  # AT-07, AT-35
        (WE, {"hfrom": "2027-02", "hto": "2027-04"}),  # AT-12
        (DE, {"hfrom": "2027-02"}),  # AT-30
        (DE, {"on_conflict": "overflow"}),  # AT-31
        (DE, {"hto": "2027-03"}),
        (WE, {"hfrom": "2026-11"}),
    ],
)
def test_variants_equal_oracle(fixture: object, kw: dict[str, str]) -> None:
    ref = json.dumps(oracle().run(str(fixture), **kw), indent=2, ensure_ascii=False) + "\n"
    assert mask_version(plan_json(fixture, **kw)) == mask_version(ref)


def test_at12_warnings() -> None:
    data = json.loads(plan_json(WE, hfrom="2027-02", hto="2027-04"))
    codes = {(w["code"], w["message"].split('"')[1]) for w in data["warnings"]}
    assert {("W002", "Core API"), ("W002", "Reporting"), ("W003", "Big bang"), ("W004", "Onboarding")} <= codes
    onboarding = data["projects"][1]
    assert onboarding["flags"] == ["hidden"] and onboarding["visible"] is None and onboarding["color_index"] is None


def test_at27_w001_reasons() -> None:
    data = json.loads(plan_json(DE))
    messages = [w["message"] for w in data["warnings"] if w["code"] == "W001"]
    assert [m.split(": ", 1)[1] for m in messages] == [
        "waiting for dependencies",
        "waiting for dependencies",
        'waiting for dependencies, then no free slot in team "ops"',
    ]


def test_at31_w011() -> None:
    data = json.loads(plan_json(DE, on_conflict="overflow"))
    w011 = [w for w in data["warnings"] if w["code"] == "W011"]
    assert [w["message"] for w in w011] == [
        'project "Release audit" exceeds team "ops" capacity; placed in overflow lane +1'
    ]
    audit = data["projects"][7]
    assert audit["flags"] == ["delayed", "over_capacity"] and audit["delay_reason"] == "dependency"
