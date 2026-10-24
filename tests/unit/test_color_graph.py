"""Adjacency and DSATUR colouring (RS CO-1 to CO-6, 5.4, AT-10, AT-11, W007, W009)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from typing import Any

from modelkit import DE, FIXTURES, WE, load_path, make_model

from rt.color.adjacency import lane_indices, neighbours
from rt.color.dsatur import assign_colors, assign_keys
from rt.diagnostics import Code, Collector
from rt.model.types import ResolvedModel
from rt.schedule.horizon import anchor, resolve_horizon, visibility
from rt.schedule.scheduler import schedule
from rt.schedule.types import Schedule, Visibility

D = date


def graph(m: ResolvedModel) -> tuple[Schedule, dict[int, Visibility], dict[int, frozenset[int]]]:
    diags = Collector()
    s = schedule(m, m.settings.on_conflict, anchor(m.settings), diags)
    assert s is not None
    h = resolve_horizon(m, s, m.settings, diags)
    vis = visibility(m, s, h)
    return s, vis, neighbours(m, s, vis, m.settings.adjacency_gap_days)


def expected(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


def test_worked_example_neighbours_and_colours() -> None:
    m = load_path(WE)
    _, vis, nb = graph(m)
    exp = expected("scheduling-worked-example.expected.json")
    assert {seq: sorted(v) for seq, v in nb.items()} == {p["seq"]: p["neighbors"] for p in exp["projects"]}
    diags = Collector()
    colors = assign_colors(m, vis, nb, diags)
    assert {seq: c.index for seq, c in colors.items()} == {p["seq"]: p["color_index"] for p in exp["projects"]}
    assert not diags.items
    for a, ns in nb.items():
        for b in ns:
            assert colors[a].index != colors[b].index


def test_lanes_numbered_per_subdomain_section() -> None:
    m = load_path(DE)
    s, _, nb = graph(m)
    rows = lane_indices(m, s.lane_count)
    assert rows == {
        ("api", 1): ("product", 0),
        ("web", 1): ("product", 1),
        ("web", 2): ("product", 2),
        ("ops", 1): ("platform", 0),
        ("ops", 2): ("platform", 1),
    }
    assert 5 not in nb[1] and 6 not in nb[1]  # different subdomains are never adjacent


def test_gap_threshold() -> None:
    def pair(gap: int, second_start: str) -> frozenset[int]:
        m = make_model(
            [("a", "sd", 1)],
            [{"team": "a", "size": "S", "start": "2027-01"}, {"team": "a", "size": "S", "start": second_start}],
            gap=gap,
        )
        return graph(m)[2][1]

    # first bar [01-01, 01-15); second from 02-01 → gap 17 days
    assert pair(17, "2027-02") == frozenset({2})
    assert pair(16, "2027-02") == frozenset()


def test_rows_two_apart_are_not_adjacent() -> None:
    m = make_model(
        [("a", "sd", 3)],
        [{"team": "a", "start": "2027-01"}, {"team": "a", "start": "2027-01"}, {"team": "a", "start": "2027-01"}],
    )
    _, _, nb = graph(m)
    assert nb == {1: frozenset({2}), 2: frozenset({1, 3}), 3: frozenset({2})}


def test_at11_pinned_colour_kept_and_avoided() -> None:
    m = make_model(
        [("a", "sd", 2)],
        [
            {"team": "a", "start": "2027-01"},
            {"team": "a", "start": "2027-01", "color": "sky"},
            {"team": "a", "start": "2027-02"},
        ],
    )
    _, vis, nb = graph(m)
    colors = assign_colors(m, vis, nb, Collector())
    assert colors[2].index == 4 and colors[2].name == "sky"
    assert colors[1].index != 4 and colors[3].index != 4


def test_w009_adjacent_pinned_same_colour() -> None:
    m = make_model(
        [("a", "sd", 2)],
        [
            {"name": "A", "team": "a", "start": "2027-01", "color": "sky"},
            {"name": "B", "team": "a", "start": "2027-01", "color": "#BAE6FD"},
        ],
    )
    _, vis, nb = graph(m)
    diags = Collector()
    colors = assign_colors(m, vis, nb, diags)
    assert colors[1].index == colors[2].index == 4
    assert [(d.code, d.line) for d in diags.items] == [(Code.W009, 102)]
    assert diags.items[0].message == 'projects "A" and "B" are adjacent and both pinned to "sky"'


def test_custom_hex_conflicts_only_with_same_hex() -> None:
    m = make_model(
        [("a", "sd", 2)],
        [
            {"name": "A", "team": "a", "start": "2027-01", "color": "#123456"},
            {"name": "B", "team": "a", "start": "2027-01"},
            {"name": "C", "team": "a", "start": "2027-02", "color": "#123456"},
        ],
    )
    _, vis, nb = graph(m)
    diags = Collector()
    keys = assign_keys(m, vis, nb, diags)
    assert keys == {1: "#123456", 3: "#123456", 2: 0}  # custom colours do not count toward palette use
    assert [d.code for d in diags.items] == [Code.W009]
    assert diags.items[0].message == 'projects "A" and "C" are adjacent and both pinned to "#123456"'
    colors = assign_colors(m, vis, nb, Collector())
    assert colors[1].index is None and colors[1].fill == "#123456" and colors[1].text == "#FFFFFF"


def test_hidden_bars_get_no_colour() -> None:
    m = make_model(
        [("a", "sd", 1)],
        [{"team": "a", "start": "2027-01", "color": "teal"}, {"team": "a", "start": "2027-06"}],
        hstart="2027-06",
        hend="2027-08",
    )
    _, vis, nb = graph(m)
    colors = assign_colors(m, vis, nb, Collector())
    assert set(colors) == {2}
    assert colors[2].index == 0  # the hidden pinned teal does not count toward use


def test_w007_when_palette_exhausted() -> None:
    m = make_model([("a", "sd", 12)], [{"name": f"P{i}", "team": "a", "start": "2027-01"} for i in range(1, 12)])
    _, vis, _ = graph(m)
    clique: Mapping[int, frozenset[int]] = {s: frozenset(set(range(1, 12)) - {s}) for s in range(1, 12)}
    diags = Collector()
    keys = assign_keys(m, vis, clique, diags)
    assert sorted(keys.values()) == [0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert [d.code for d in diags.items] == [Code.W007]
    assert diags.items[0].message == 'project "P11" shares colour "indigo" with an adjacent bar'


def test_least_used_colour_spreads_use() -> None:
    m = make_model([("a", "sd", 1)], [{"team": "a", "size": "S", "start": f"2027-{i:02d}"} for i in range(1, 7)], gap=0)
    _, vis, nb = graph(m)
    assert all(not v for v in nb.values())
    keys = assign_keys(m, vis, nb, Collector())
    assert [keys[s] for s in range(1, 7)] == [0, 1, 2, 3, 4, 5]
