"""HTML structure of the worked example (RS 7.3-7.12 hooks; AT-02..AT-06, AT-13, AT-33..AT-35)."""

from __future__ import annotations

import re

from rtkit import (
    WE_PLAN,
    Rendered,
    assert_ok,
    load_json,
    matching_css,
    norm_ws,
    pct_re,
    shows_glyph,
    style_decls,
)

EXPECTED = load_json(WE_PLAN)


def _geom(bar) -> tuple[str, str]:
    d = style_decls(bar)
    return d.get("left", ""), d.get("width", "")


def test_at_02_bar_attributes_match_plan(we_render: Rendered) -> None:
    """AT-02: each rt-bar has data-start, data-end, data-lane, data-color-index equal to the plan."""
    assert_ok(we_render.result)
    plan = we_render.plan
    bars = we_render.bars
    visible = {p["seq"] for p in plan["projects"] if p["visible"] is not None}
    assert set(bars) == visible == set(range(1, 10))
    for p in plan["projects"]:
        b = bars[p["seq"]]
        assert b.get("data-start") == p["start"], p["name"]
        assert b.get("data-end") == (p["end"] if p["end"] is not None else "ongoing"), p["name"]
        assert b.get("data-lane") == str(p["lane"]), p["name"]
        assert b.get("data-color-index") == str(p["color_index"]), p["name"]
        assert b.get("data-team") == p["team"], p["name"]
        assert b.get("data-requested") == (p["requested_start"] or "auto"), p["name"]
        assert b.get("data-delay-days") == str(p["delay_days"]), p["name"]
        assert (b.get("data-flags") or "").split() == p["flags"], p["name"]
        assert (b.get("data-depends-on") or "").split() == [str(d) for d in p["depends_on"]], p["name"]


def test_at_02_plan_matches_expected_schedule(we_render: Rendered) -> None:
    """AT-02 relies on the plan; the plan's schedule must also be the RS 4.4 table."""
    for exp in EXPECTED["projects"]:
        got = next(p for p in we_render.plan["projects"] if p["seq"] == exp["seq"])
        for key in ("start", "end", "lane", "color_index", "flags", "delay_days"):
            assert got[key] == exp[key], (exp["name"], key)


def test_at_03_bar_geometry(we_render: Rendered) -> None:
    """AT-03: Reporting left 110.39/width 114.76; Quick win 122.00/56.00; Big bang 474.00/216.00."""
    bars = we_render.bars
    assert _geom(bars[3]) == ("110.39px", "114.76px")  # Reporting
    assert _geom(bars[8]) == ("122.00px", "56.00px")  # Quick win
    assert _geom(bars[9]) == ("474.00px", "216.00px")  # Big bang


def test_at_03_all_bar_geometry(we_render: Rendered) -> None:
    """OUT-7/OUT-8 for every WE bar (values derived from the RS formulas)."""
    expected = {
        1: ("2.00px", "223.14px"),  # Core API 01-01..02-26
        2: ("2.00px", "104.39px"),  # Onboarding 01-01..01-29
        4: ("229.14px", "51.44px"),  # Hotfix pack 02-26..03-12
        6: ("284.58px", "105.42px"),  # Fraud rules 03-12..04-09
        7: ("362.00px", "108.00px"),  # Q2 launch 04-01..04-29
    }
    for seq, geom in expected.items():
        assert _geom(we_render.bars[seq]) == geom, seq


def test_at_04_ongoing_bar(we_render: Rendered) -> None:
    """AT-04: Maintenance left 242.00/width 476.00, flag continues, shows the infinity glyph."""
    bar = we_render.bars[5]
    assert _geom(bar) == ("242.00px", "476.00px")
    assert "continues" in (bar.get("data-flags") or "").split()
    assert bar.get("data-end") == "ongoing"
    assert shows_glyph(we_render.doc, bar, "∞"), "ongoing bar must show the ∞ glyph (OUT-19)"


def test_at_05_today_line(we_render: Rendered) -> None:
    """AT-05: rt-today with data-date="2027-02-15" at x = 180.00 px."""
    todays = we_render.doc.cssselect(".rt-today")
    assert todays, "no .rt-today element"
    assert all(t.get("data-date") == "2027-02-15" for t in todays)
    positioned = [style_decls(t)["left"] for t in todays if "left" in style_decls(t)]
    assert positioned, "rt-today has no inline left position"
    assert all(v == "180.00px" for v in positioned), positioned


def test_at_05_today_label(we_render: Rendered) -> None:
    """OUT-24: the timeline header labels the line "Today · 15 Feb"."""
    text = norm_ws(we_render.doc.text_content())
    assert "Today · 15 Feb" in text


def test_at_06_backfill_order(we_render: Rendered) -> None:
    """AT-06: Beta lane 1 holds Quick win, Q2 launch, Big bang in that left-to-right order."""
    doc = we_render.doc
    lanes = doc.cssselect('.rt-lane[data-team="beta"][data-lane="1"]')
    assert len(lanes) == 1
    assert lanes[0].get("data-overflow") == "false"
    in_lane = doc.cssselect('.rt-bar[data-team="beta"][data-lane="1"]')
    ordered = sorted(in_lane, key=lambda b: float(style_decls(b)["left"].removesuffix("px")))
    assert [int(b.get("data-seq")) for b in ordered] == [8, 7, 9]
    # the bars sit inside that lane element
    assert all(lanes[0] in list(b.iterancestors()) for b in in_lane)


def test_at_06_lanes_and_teams(we_render: Rendered) -> None:
    """RS 7.10: rt-subdomain / rt-team / rt-lane hooks for WE."""
    doc = we_render.doc
    subs = doc.cssselect(".rt-subdomain")
    assert [s.get("data-subdomain") for s in subs] == ["core"]
    teams = doc.cssselect(".rt-team")
    assert [(t.get("data-team"), t.get("data-slots")) for t in teams] == [("alpha", "2"), ("beta", "1")]
    lanes = [
        (lane.get("data-team"), lane.get("data-lane"), lane.get("data-overflow")) for lane in doc.cssselect(".rt-lane")
    ]
    assert lanes == [("alpha", "1", "false"), ("alpha", "2", "false"), ("beta", "1", "false")]


def test_at_13_team_utilisation(we_render: Rendered) -> None:
    """AT-13: Alpha data-utilization="0.7624" shown as 76 %, Beta "0.5414" shown as 54 %."""
    doc = we_render.doc
    alpha = doc.cssselect('.rt-team[data-team="alpha"]')
    beta = doc.cssselect('.rt-team[data-team="beta"]')
    assert len(alpha) == 1 and len(beta) == 1
    assert alpha[0].get("data-utilization") == "0.7624"
    assert beta[0].get("data-utilization") == "0.5414"
    assert pct_re(76).search(alpha[0].text_content()), "Alpha must show 76 %"
    assert pct_re(54).search(beta[0].text_content()), "Beta must show 54 %"


def test_at_33_quarters_worked_example(we_render: Rendered) -> None:
    """AT-33 (WE): quarter labels 2027-Q1, 2027-Q2; one dotted quarter line at 2027-04-01, x = 360.00 px."""
    doc = we_render.doc
    labels = [q.get("data-quarter") for q in doc.cssselect(".rt-quarter")]
    assert list(dict.fromkeys(labels)) == ["2027-Q1", "2027-Q2"]
    assert [q for q in labels if q] == ["2027-Q1", "2027-Q2"], "each quarter labelled once"
    lines = doc.cssselect(".rt-quarter-line")
    assert lines, "no rt-quarter-line"
    assert {ln.get("data-date") for ln in lines} == {"2027-04-01"}
    lefts = [style_decls(ln)["left"] for ln in lines if "left" in style_decls(ln)]
    assert lefts and all(v == "360.00px" for v in lefts), lefts
    css = matching_css(doc, lines[0])
    assert re.search(r"dotted", css), "quarter line must be dotted (OUT-23)"


def test_at_33_quarters_example(ex_render: Rendered) -> None:
    """AT-33 (EX): labels 2026-Q4, 2027-Q1, 2027-Q2; dotted line at 2027-04-01; 2027-01-01 a solid
    year line; no line at the horizon's left edge."""
    assert_ok(ex_render.result)
    doc = ex_render.doc
    labels = [q.get("data-quarter") for q in doc.cssselect(".rt-quarter")]
    assert labels == ["2026-Q4", "2027-Q1", "2027-Q2"]
    lines = doc.cssselect(".rt-quarter-line")
    assert {ln.get("data-date") for ln in lines} == {"2027-04-01"}
    lefts = [style_decls(ln)["left"] for ln in lines if "left" in style_decls(ln)]
    assert lefts and all(v == "720.00px" for v in lefts), lefts  # month index 6 from 2026-10
    # 2027-01-01 (x = 360.00 px in EX, horizon starts 2026-10) is drawn as a year line
    year_marks = [
        el
        for el in doc.iter()
        if isinstance(el.tag, str)
        and "year" in (el.get("class") or "")
        and style_decls(el).get("left") == "360.00px"
        and not el.text_content().strip()  # a line, not the year label of the scale
    ]
    assert year_marks, "no year boundary mark at 2027-01-01 (x = 360.00px)"
    css = matching_css(doc, year_marks[0])
    assert "dotted" not in css, "2027-01-01 must be a solid year line, not a dotted quarter line"
    assert "#94a3b8" in css.lower(), "year line colour #94A3B8 (OUT-23)"
    # no boundary line at the left edge of the horizon (labels of the scale may start at x = 0)
    for el in doc.iter():
        if not isinstance(el.tag, str) or el.text_content().strip():
            continue
        tokens = (el.get("class") or "").split()
        if any(t.startswith("rt-mark") or t == "rt-quarter-line" or "year" in t for t in tokens):
            assert style_decls(el).get("left") not in ("0.00px", "0px", "0"), f"line at horizon left edge: {tokens}"


def _cells(doc) -> dict[tuple[str, str, str], object]:
    out = {}
    for c in doc.cssselect(".rt-load-cell"):
        key = (c.get("data-kind"), c.get("data-row"), c.get("data-month"))
        assert key not in out, f"duplicate load cell {key}"
        out[key] = c
    return out


WE_LOAD_TEXT = {
    ("subdomain", "core"): ["67", "80", "67", "76", "67", "59"],
    ("team", "alpha"): ["100", "95", "100", "63", "50", "50"],
    ("team", "beta"): ["–", "50", "–", "100", "100", "77"],
    ("all", "all"): ["67", "80", "67", "76", "67", "59"],
}
MONTHS = ["2027-01", "2027-02", "2027-03", "2027-04", "2027-05", "2027-06"]


def test_at_34_summary_load_cells(we_summary_render: Rendered, we_render: Rendered) -> None:
    """AT-34: one rt-summary; rt-load-cell values equal RS 7.12 (Alpha Feb 0.9464 shown 95 %,
    Beta Jan shown '–'); without --summary there is no rt-summary."""
    assert_ok(we_summary_render.result)
    doc = we_summary_render.doc
    assert len(doc.cssselect(".rt-summary")) == 1
    cells = _cells(doc)
    ml = EXPECTED["monthly_load"]
    expected_loads = {("team", t["team"]): t["load"] for t in ml["teams"]}
    expected_loads |= {("subdomain", s["subdomain"]): s["load"] for s in ml["subdomains"]}
    expected_loads[("all", "all")] = ml["total"]
    assert set(cells) == {(k, r, m) for (k, r) in expected_loads for m in MONTHS}
    for (kind, row), loads in expected_loads.items():
        for month, load, shown in zip(MONTHS, loads, WE_LOAD_TEXT[(kind, row)], strict=True):
            cell = cells[(kind, row, month)]
            assert cell.get("data-load") == f"{load:.4f}", (kind, row, month)
            text = norm_ws(cell.text_content())
            if shown == "–":
                assert text == "–", (kind, row, month, text)
            else:
                assert re.fullmatch(rf"{shown}[   ]?%", text), (kind, row, month, text)
    assert cells[("team", "alpha", "2027-02")].get("data-load") == "0.9464"
    # without --summary
    assert_ok(we_render.result)
    assert we_render.doc.cssselect(".rt-summary") == []
    assert we_render.doc.cssselect(".rt-load-cell") == []


def test_at_34_summary_heading_and_order(we_summary_render: Rendered) -> None:
    """OUT-29: h2 "Summary" after the legend and before the timeline/subdomain sections."""
    doc = we_summary_render.doc
    summary = doc.cssselect(".rt-summary")[0]
    assert any(norm_ws(h.text_content()) == "Summary" for h in summary.iter("h2"))
    order = [el for el in doc.iter() if isinstance(el.tag, str)]
    first_sub = doc.cssselect(".rt-subdomain")[0]
    assert order.index(summary) < order.index(first_sub)


def test_out33_load_cell_tooltip(we_summary_render: Rendered) -> None:
    """OUT-33: tooltip "Alpha · Feb 2027 · 53 of 56 slot-days (95 %)"."""
    cell = _cells(we_summary_render.doc)[("team", "alpha", "2027-02")]
    texts = [cell.get("title") or ""] + [d.get("title") or "" for d in cell.iterdescendants() if isinstance(d.tag, str)]
    texts.append(cell.text_content())
    blob = " | ".join(norm_ws(t) for t in texts)
    assert re.search(r"Alpha · Feb 2027 · 53 of 56 slot-days \(95[   ]?%\)", blob), blob


def test_at_35_overflow_summary(we_overflow_render: Rendered) -> None:
    """AT-35: Alpha Jan 140 % and Beta Apr 177 % in the over-100 % colour #FCA5A5; Core Jan 94 %."""
    assert_ok(we_overflow_render.result)
    doc = we_overflow_render.doc
    cells = _cells(doc)
    alpha_jan = cells[("team", "alpha", "2027-01")]
    beta_apr = cells[("team", "beta", "2027-04")]
    core_jan = cells[("subdomain", "core", "2027-01")]
    assert re.fullmatch(r"140[   ]?%", norm_ws(alpha_jan.text_content()))
    assert re.fullmatch(r"177[   ]?%", norm_ws(beta_apr.text_content()))
    assert re.fullmatch(r"94[   ]?%", norm_ws(core_jan.text_content()))
    for cell in (alpha_jan, beta_apr):
        assert "#fca5a5" in matching_css(doc, cell).lower(), "over-100 % cell must use #FCA5A5"
    assert "#fca5a5" not in matching_css(doc, core_jan).lower()
