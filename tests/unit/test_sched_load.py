"""Utilisation and monthly load (RS OUT-13, OUT-32, 7.12 table, AT-13, AT-35)."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

from modelkit import WE, load_path, make_model

from rt.decimalutil import pct, ratio4
from rt.diagnostics import Collector
from rt.model.types import ResolvedModel
from rt.schedule.horizon import anchor, resolve_horizon, visibility
from rt.schedule.load import LoadRow, LoadTable, Ratio, monthly_load, utilisation
from rt.schedule.scheduler import schedule


def compute(m: ResolvedModel) -> tuple[dict[str, Ratio], LoadTable]:
    diags = Collector()
    s = schedule(m, m.settings.on_conflict, anchor(m.settings), diags)
    assert s is not None
    h = resolve_horizon(m, s, m.settings, diags)
    return utilisation(m, s, h, visibility(m, s, h)), monthly_load(m, s, h)


def r4(row: LoadRow) -> list[Decimal]:
    return [ratio4(n, d) for n, d in zip(row.occupied, row.capacity, strict=True)]


def test_at13_utilisation() -> None:
    util, _ = compute(load_path(WE))
    assert (util["alpha"].numerator, util["alpha"].denominator) == (276, 362)
    assert (util["beta"].numerator, util["beta"].denominator) == (98, 181)
    assert ratio4(276, 362) == Decimal("0.7624") and pct(util["alpha"].exact) == 76
    assert ratio4(98, 181) == Decimal("0.5414") and pct(util["beta"].exact) == 54


def test_ratio_exact_zero_denominator() -> None:
    assert Ratio(0, 0).exact == Fraction(0)
    assert Ratio(1, 2).exact == Fraction(1, 2)


def test_monthly_load_table_7_12() -> None:
    _, load = compute(load_path(WE))
    assert [str(mo) for mo in load.months] == ["2027-01", "2027-02", "2027-03", "2027-04", "2027-05", "2027-06"]
    alpha, beta = load.teams
    assert [pct(v) for v in r4(alpha)] == [100, 95, 100, 63, 50, 50]
    assert [pct(v) for v in r4(beta)] == [0, 50, 0, 100, 100, 77]
    assert [pct(v) for v in r4(load.subdomains[0])] == [67, 80, 67, 76, 67, 59]
    assert [pct(v) for v in r4(load.total)] == [67, 80, 67, 76, 67, 59]
    assert (alpha.occupied[1], alpha.capacity[1]) == (53, 56)  # tooltip "53 of 56 slot-days (95 %)"
    assert r4(alpha)[1] == Decimal("0.9464")


def test_at35_overflow_load_over_100() -> None:
    _, load = compute(load_path(WE, on_conflict="overflow"))
    alpha, beta = load.teams
    assert r4(alpha)[0] == Decimal("1.4032") and pct(r4(alpha)[0]) == 140
    assert r4(beta)[3] == Decimal("1.7667") and pct(r4(beta)[3]) == 177
    assert r4(load.subdomains[0])[0] == Decimal("0.9355") and pct(r4(load.subdomains[0])[0]) == 94


def test_overflow_lanes_excluded_from_utilisation() -> None:
    util, _ = compute(load_path(WE, on_conflict="overflow"))
    assert ratio4(util["alpha"].numerator, util["alpha"].denominator) == Decimal("0.6851")
    assert ratio4(util["beta"].numerator, util["beta"].denominator) == Decimal("0.2320")


def test_subdomain_without_teams_has_zero_capacity() -> None:
    m = make_model([("a", "x", 1)], [{"team": "a", "start": "2027-01"}], subdomains=["x", "empty"])
    _, load = compute(m)
    assert [r.key for r in load.subdomains] == ["x", "empty"]
    assert set(load.subdomains[1].capacity) == {0}
    assert set(r4(load.subdomains[1])) == {Decimal("0.0000")}
    assert load.total.key == ""
