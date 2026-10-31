"""Team indicators (RS 7.13, TI-1 to TI-7): DEV per slot, DEV per QA, median band, norms, flags."""

from __future__ import annotations

from fractions import Fraction as F

from modelkit import EX, load_path

from rt.diagnostics import Pos
from rt.model.types import Band, Capacity, Team, TeamNorms
from rt.schedule.indicators import (
    DEVS_PER_QA,
    DEVS_PER_SLOT,
    SOURCE_MEDIAN,
    SOURCE_NORM,
    median,
    team_indicators,
)


def team(tid: str, slots: int, devs: int | None, testers: int = 0, pm: int = 0) -> Team:
    cap = Capacity() if devs is None else Capacity(developers=devs, product_managers=pm, testers=testers)
    return Team(tid, tid.upper(), "sd", slots, cap, Pos(1, 1, "<t>"), capacity_given=devs is not None)


def test_median() -> None:
    assert median([]) is None
    assert median([F(3), F(1), F(2)]) == 2
    assert median([F(4), F(1), F(2), F(3)]) == F(5, 2)


def test_example_values_flags_and_bands() -> None:
    m = load_path(EX)
    ind = team_indicators(m.teams, m.model.team_norms)
    rows = {k: (t.developers, t.testers, t.devs_per_slot, t.devs_per_qa, t.flags) for k, t in ind.teams.items()}
    assert rows == {
        "blik": (5, 2, F(5, 2), F(5, 2), ()),
        "cards": (6, 2, F(3), F(3), ()),  # exactly on the band edge 3.0: not marked
        "acq": (7, 3, F(7, 3), F(7, 3), ()),
        "panel": (4, 1, F(2), F(4), ()),
        "app": (4, 2, F(2), F(2), ()),
        "ops": (3, 1, F(3, 2), F(3), ()),
        "sec": (2, 0, F(2), None, ("no_qa",)),
    }
    s, q = ind.devs_per_slot, ind.devs_per_qa
    assert (s.all, s.median, s.low, s.high, s.source) == (F(31, 14), F(2), F(1), F(3), SOURCE_MEDIAN)
    assert (q.all, q.median, q.low, q.high) == (F(29, 11), F(11, 4), F(11, 8), F(33, 8))
    assert ind.teams["cards"].marks == {} and ind.stats(DEVS_PER_QA) is q


def test_only_developers_count_and_every_slot_counts() -> None:
    ind = team_indicators([team("a", 2, 4, testers=2, pm=5)], TeamNorms())
    assert ind.teams["a"].devs_per_slot == 2  # product managers do not count (Q1)


def test_fewer_than_three_teams_are_not_marked() -> None:
    ind = team_indicators([team("a", 1, 10, 1), team("b", 1, 1, 1)], TeamNorms())
    assert ind.devs_per_slot.source is None and ind.devs_per_slot.low is None
    assert ind.devs_per_slot.median == F(11, 2) and all(not t.marks for t in ind.teams.values())


def test_band_bounds_are_inclusive() -> None:
    # median 3: band 1.5-4.5 (more than 50 % away is marked); 1.5 and 4.5 themselves stay unmarked
    teams = [team("a", 2, 3, 1), team("b", 1, 3, 1), team("c", 2, 9, 1), team("d", 1, 1, 1), team("e", 1, 5, 1)]
    ind = team_indicators(teams, TeamNorms())
    assert ind.devs_per_slot.median == 3
    assert {k: t.marks.get(DEVS_PER_SLOT) for k, t in ind.teams.items()} == {
        "a": None,
        "b": None,
        "c": None,
        "d": "low",
        "e": "high",
    }


def test_norms_replace_the_median_rule_per_indicator() -> None:
    teams = [team("a", 2, 6, 2), team("b", 2, 3, 1), team("c", 2, 10, 1)]
    ind = team_indicators(teams, TeamNorms(devs_per_slot=Band(F(2), None)))
    assert ind.devs_per_slot.source == SOURCE_NORM and ind.devs_per_slot.high is None
    assert ind.teams["b"].flags == ("devs_per_slot_low",)
    assert ind.devs_per_qa.source == SOURCE_MEDIAN  # no norm for DEV per QA: median rule
    assert ind.teams["c"].flags == ("devs_per_qa_high",)


def test_missing_capacity_and_zero_counts() -> None:
    teams = [team("none", 2, None), team("zero", 2, 0, 0), team("idle", 1, 0, 2), team("solo", 1, 3, 0)]
    ind = team_indicators(teams, TeamNorms())
    t = ind.teams
    assert (t["none"].devs_per_slot, t["none"].devs_per_qa, t["none"].flags) == (None, None, ("no_capacity",))
    assert (t["zero"].devs_per_slot, t["zero"].devs_per_qa, t["zero"].flags) == (0, None, ())
    assert t["idle"].devs_per_qa == 0
    # three teams with a value (0, 0, 3): median 0, so the band is 0-0 and 3 is high
    assert t["solo"].flags == ("devs_per_slot_high", "no_qa")
    assert ind.devs_per_slot.all == F(3, 4)  # 3 developers over 2 + 1 + 1 slots; no capacity left out
    assert ind.devs_per_qa.all == 0  # only teams with testers: 0 developers / 2 testers


def test_no_team_with_capacity() -> None:
    ind = team_indicators([team("a", 1, None)], TeamNorms())
    assert ind.devs_per_slot.all is None and ind.devs_per_slot.median is None and ind.devs_per_slot.source is None
