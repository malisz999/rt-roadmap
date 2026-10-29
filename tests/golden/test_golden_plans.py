"""Golden plan JSON (RS section 8, AT-01, AT-26) and golden YAML guards."""

from __future__ import annotations

import filecmp

import pytest
from rtkit import (
    CONVERT,
    DE_PLAN,
    DOCS_FIXTURES,
    EX,
    FIXTURES,
    WE_PLAN,
    Rendered,
    assert_ok,
    mask_version,
    run_oracle,
)


def test_fixture_copies_match_docs() -> None:
    """tests/fixtures are verbatim copies of docs/fixtures (read-only sources of truth)."""
    for src in sorted(DOCS_FIXTURES.glob("*.*")):
        assert filecmp.cmp(src, FIXTURES / src.name, shallow=False), src.name
    for src in sorted((DOCS_FIXTURES / "convert").glob("*")):
        assert filecmp.cmp(src, CONVERT / src.name, shallow=False), src.name


def test_at_01_worked_example_plan(we_render: Rendered) -> None:
    """AT-01: rt render WE --plan p.json -> exit 0; plan byte-equal to the expected file."""
    assert_ok(we_render.result)
    assert we_render.html_path.exists(), "default output scheduling-worked-example.html not written"
    expected = mask_version(WE_PLAN.read_bytes())
    actual = mask_version(we_render.plan_bytes)
    assert actual.decode("utf-8") == expected.decode("utf-8")


def test_at_01_plan_rt_version(we_render: Rendered) -> None:
    """PL-1/section 8: rt_version is the tool version (masked in the byte comparison)."""
    assert we_render.plan["rt_version"] == "1.1.0"
    assert we_render.plan_bytes.endswith(b"}\n"), "plan must end with a single trailing newline"
    assert b"\r" not in we_render.plan_bytes


def test_at_26_dependencies_plan(de_render: Rendered) -> None:
    """AT-26: rt render DE --plan p.json -> exit 0; plan byte-equal to the expected file."""
    assert_ok(de_render.result)
    expected = mask_version(DE_PLAN.read_bytes())
    actual = mask_version(de_render.plan_bytes)
    assert actual.decode("utf-8") == expected.decode("utf-8")


def _strip_messages(plan: dict) -> dict:  # type: ignore[type-arg]
    plan = dict(plan)
    plan["warnings"] = [{k: v for k, v in w.items() if k != "message"} for w in plan["warnings"]]
    plan.pop("rt_version", None)
    return plan


def test_golden_example_plan_matches_oracle(ex_render: Rendered) -> None:
    """Differential: rt's plan for EX equals tools/reference_plan.py (warning texts excluded)."""
    assert_ok(ex_render.result)
    oracle = run_oracle(EX)
    assert _strip_messages(ex_render.plan) == _strip_messages(oracle)


@pytest.mark.parametrize(
    ("fixture", "kwargs", "args"),
    [
        ("scheduling-worked-example.yaml", {"on_conflict": "overflow"}, ["--on-conflict", "overflow"]),
        (
            "scheduling-worked-example.yaml",
            {"hfrom": "2027-02", "hto": "2027-04"},
            ["--from", "2027-02", "--to", "2027-04"],
        ),
        ("dependencies-example.yaml", {"hfrom": "2027-02"}, ["--from", "2027-02"]),
        ("dependencies-example.yaml", {"on_conflict": "overflow"}, ["--on-conflict", "overflow"]),
        ("roadmap.minimal.yaml", {}, ["--today", "2027-01-10"]),
    ],
    ids=["we-overflow", "we-from-to", "de-from", "de-overflow", "minimal"],
)
def test_golden_variants_match_oracle(tmp_path, fixture, kwargs, args) -> None:  # type: ignore[no-untyped-def]
    """Differential: option variants used by AT-07, AT-12, AT-30, AT-31 agree with the oracle."""
    from rtkit import render_fixture

    src = FIXTURES / fixture
    r = render_fixture(tmp_path, src, *args)
    assert_ok(r.result)
    if fixture == "roadmap.minimal.yaml":
        # the oracle has no --today option; give it the same value through a copy of the file
        text = src.read_text(encoding="utf-8").replace(
            "  title: My Roadmap\n", "  title: My Roadmap\n  today: 2027-01-10\n"
        )
        patched = tmp_path / "minimal-oracle.yaml"
        patched.write_text(text, encoding="utf-8")
        oracle = run_oracle(patched)
        actual = _strip_messages(r.plan)
        expected = _strip_messages(oracle)
        # W008: the minimal file has no capacity; the oracle does not implement W008 (see Q-1)
        actual["warnings"] = [w for w in actual["warnings"] if w["code"] != "W008"]
        assert actual == expected
    else:
        assert _strip_messages(r.plan) == _strip_messages(run_oracle(r.dir / fixture, **kwargs))
