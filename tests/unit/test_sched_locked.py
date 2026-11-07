"""Locked projects in the scheduler and the plan (CR-3; RS SC-14, SC-15, W015, PL-9)."""

from __future__ import annotations

from datetime import date

import pytest
from modelkit import FIXTURES, load_path, make_model

from rt.diagnostics import Code, Collector
from rt.model.types import Mode, ResolvedModel
from rt.plan.build import compute_plan
from rt.schedule.horizon import anchor
from rt.schedule.scheduler import schedule
from rt.schedule.types import Schedule

D = date
LE = FIXTURES / "lock-example.yaml"


def run(m: ResolvedModel, mode: Mode | None = None) -> tuple[Schedule | None, Collector]:
    diags = Collector()
    return schedule(m, mode or m.settings.on_conflict, anchor(m.settings), diags), diags


def test_lock_example_table_4_6() -> None:
    s, diags = run(load_path(LE))
    assert s is not None and not diags.items
    got = [(p.seq, p.lane, p.start, p.end, p.delay_days, p.locked, p.lock_risk) for p in s.placements]
    assert got == [
        (1, 1, D(2027, 3, 1), D(2027, 4, 26), 59, False, None),
        (2, 1, D(2027, 2, 1), D(2027, 3, 1), 0, True, None),
        (3, 1, D(2027, 3, 1), D(2027, 3, 29), 0, True, "dependency"),
        (4, 2, D(2027, 3, 1), D(2027, 3, 15), 0, True, None),
        (5, 3, D(2027, 3, 1), D(2027, 3, 15), 0, True, "capacity"),
        (6, 2, D(2027, 3, 15), D(2027, 4, 12), 14, False, None),
        (7, 1, D(2027, 3, 29), D(2027, 4, 12), 0, False, None),
    ]
    assert s.placement(3).earliest == D(2027, 4, 26)
    assert s.lane_count["beta"] == 3


@pytest.mark.parametrize("mode", list(Mode))
def test_locked_project_never_moves_in_any_mode(mode: Mode) -> None:
    m = make_model(
        [("a", "core", 1)],
        [
            {"name": "First", "team": "a", "size": "L", "start": "2027-01"},
            {"name": "Promise", "team": "a", "size": "M", "start": "2027-02", "locked": True},
        ],
    )
    s, diags = run(m, mode)
    if mode is Mode.ERROR:
        assert s is None and [d.code for d in diags.errors] == [Code.E061]
        return
    assert s is not None
    promise = s.placement(2)
    assert (promise.lane, promise.start, promise.lock_risk) == (1, D(2027, 2, 1), None)
    first = s.placement(1)
    if mode is Mode.DELAY:
        assert (first.lane, first.start, first.delay_reason) == (1, D(2027, 3, 1), "capacity")
    else:
        assert (first.lane, first.start, first.overflow) == (2, D(2027, 1, 1), True)


def test_dependency_and_capacity_risk_together() -> None:
    m = make_model(
        [("a", "core", 1)],
        [
            {"name": "Base", "team": "a", "size": "L", "start": "2027-01"},
            {"name": "Held", "team": "a", "size": "M", "start": "2027-02", "locked": True},
            {"name": "Both", "team": "a", "size": "S", "start": "2027-02", "locked": True, "deps": (1,)},
        ],
    )
    s, _ = run(m)
    assert s is not None
    both = s.placement(3)
    assert (both.lane, both.overflow, both.lock_risk) == (2, True, "dependency+capacity")


def test_locked_ongoing_holds_its_slot_and_unlocked_work_waits_or_fails() -> None:
    m = make_model(
        [("a", "core", 1)],
        [
            {"name": "Early", "team": "a", "size": "M", "start": "2027-01"},
            {"name": "Support", "team": "a", "ongoing": True, "start": "2027-03", "locked": True},
            {"name": "Late", "team": "a", "size": "S", "start": "2027-04"},
        ],
    )
    s, diags = run(m)
    assert s is None and [d.code for d in diags.errors] == [Code.E060]
    assert '"Late"' in diags.errors[0].message


def test_locked_chain_dependency_on_locked_project() -> None:
    m = make_model(
        [("a", "core", 1), ("b", "core", 1)],
        [
            {"name": "One", "team": "a", "size": "M", "start": "2027-01", "locked": True},
            {"name": "Two", "team": "b", "size": "M", "start": "2027-01", "locked": True, "deps": (1,)},
            {"name": "Three", "team": "b", "size": "S", "deps": (1,)},
        ],
    )
    s, _ = run(m)
    assert s is not None
    assert s.placement(2).lock_risk == "dependency" and s.placement(2).earliest == D(2027, 1, 29)
    assert s.placement(3).start == D(2027, 1, 29)


def test_w015_messages_and_plan_fields() -> None:
    m = make_model(
        [("a", "core", 1)],
        [
            {"name": "Held", "team": "a", "size": "M", "start": "2027-02", "locked": True},
            {"name": "Extra", "team": "a", "size": "S", "start": "2027-02", "locked": True, "promised_to": "Bank"},
        ],
    )
    diags = Collector()
    plan = compute_plan(m, diags)
    assert plan is not None
    w = [d for d in diags.warnings if d.code is Code.W015]
    assert [d.message for d in w] == [
        'locked project "Extra" cannot keep its promised start 2027-02-01: the only slot of team "a" is taken by '
        "locked projects; shown in overflow lane +1"
    ]
    assert Code.W011 not in {d.code for d in diags.warnings}
    extra = plan.projects[1]
    assert (extra.locked, extra.promised_to, extra.lock_risk) == (True, "Bank", "capacity")
    assert extra.flags == ("at_risk", "locked", "over_capacity")
    held = plan.projects[0]
    assert (held.promised_to, held.flags) == (None, ("locked",))
