"""Further HTML rules of RS section 5 and 7 not covered by a single AT (CO-4, 5.3, OUT-11, OUT-14,
OUT-30, OUT-33)."""

from __future__ import annotations

import re
from pathlib import Path

from rtkit import INVALID, Rendered, assert_ok, matching_css, norm_ws, render_fixture, style_decls

COLOURS = """version: 1
roadmap:
  title: Colours
  today: 2027-01-15
  horizon: { start: 2027-01, end: 2027-06 }
sizes:
  S: 2
subdomains:
  - id: core
    name: Core
    teams:
      - id: blik
        name: BLIK
        parallel_projects: 2
        capacity: { developers: 2 }
projects:
  - name: Navy
    team: blik
    size: S
    start: 2027-01
    color: '#000080'
  - name: Pale
    team: blik
    size: S
    start: 2027-01
    color: '#FFFF99'
  - name: Palette fill
    team: blik
    size: S
    start: 2027-04
    color: '#BAE6FD'
  - name: Named
    team: blik
    size: S
    start: 2027-04
    color: teal
"""


def _render(tmp: Path, text: str, *extra: str) -> Rendered:
    (tmp / "src").mkdir()
    src = tmp / "src" / "in.yaml"
    src.write_text(text, encoding="utf-8")
    return render_fixture(tmp, src, *extra)


def test_co4_pinned_and_custom_colours(tmp_path: Path) -> None:
    """CO-4 / 5.3: a hex equal to a palette fill maps to that entry; custom hex keeps its fill;
    text is #1E293B when contrast >= 4.5:1, else #FFFFFF."""
    r = _render(tmp_path, COLOURS)
    assert_ok(r.result)
    plan = {p["name"]: p for p in r.plan["projects"]}
    assert (plan["Palette fill"]["color_index"], plan["Palette fill"]["color_name"]) == (4, "sky")
    assert (plan["Named"]["color_index"], plan["Named"]["color_fill"]) == (7, "#99F6E4")
    assert plan["Navy"]["color_fill"].upper() == "#000080"
    assert plan["Pale"]["color_fill"].upper() == "#FFFF99"
    bars = r.bars
    navy, pale, sky = (style_decls(bars[i]) for i in (1, 2, 3))
    assert navy["--fill"].upper() == "#000080" and navy["--ink"].upper() == "#FFFFFF"
    assert pale["--fill"].upper() == "#FFFF99" and pale["--ink"].upper() == "#1E293B"
    assert (sky["--fill"].upper(), sky["--accent"].upper(), sky["--ink"].upper()) == ("#BAE6FD", "#0EA5E9", "#1E293B")
    assert "W009" not in r.result.codes() and "W007" not in r.result.codes()


def test_palette_fill_and_accent_per_bar(we_render: Rendered) -> None:
    """5.3: each bar's fill/accent are the palette entry of its colour index; text #1E293B."""
    palette = [
        ("#C7D2FE", "#6366F1"),
        ("#BBF7D0", "#22C55E"),
        ("#FED7AA", "#F97316"),
        ("#FBCFE8", "#EC4899"),
        ("#BAE6FD", "#0EA5E9"),
        ("#FDE68A", "#D97706"),
        ("#DDD6FE", "#8B5CF6"),
        ("#99F6E4", "#14B8A6"),
        ("#D9F99D", "#65A30D"),
        ("#EADBC8", "#A16207"),
    ]
    for b in we_render.bars.values():
        idx = int(b.get("data-color-index"))
        css = matching_css(we_render.doc, b).upper()
        assert palette[idx][0] in css and palette[idx][1] in css, (b.get("data-seq"), idx)
        assert "#1E293B" in css


def test_out11_subdomain_without_teams(tmp_path: Path) -> None:
    """OUT-11: a subdomain with no teams shows the band and a muted line "No teams defined"."""
    r = render_fixture(tmp_path, INVALID / "w006_subdomain_without_teams.yaml")
    assert_ok(r.result)
    risk = r.doc.cssselect('.rt-subdomain[data-subdomain="risk"]')
    assert len(risk) == 1
    text = norm_ws(risk[0].text_content())
    assert "Risk" in text and "No teams" in text, text
    assert r.doc.cssselect('.rt-subdomain[data-subdomain="risk"] .rt-team') == []


def test_out14_empty_slots_drawn(tmp_path: Path) -> None:
    """OUT-14: one row per slot, empty slots still drawn."""
    text = COLOURS.replace("parallel_projects: 2", "parallel_projects: 5")
    r = _render(tmp_path, text)
    assert_ok(r.result)
    lanes = r.doc.cssselect('.rt-lane[data-team="blik"]')
    assert [ln.get("data-lane") for ln in lanes] == ["1", "2", "3", "4", "5"]
    assert r.doc.cssselect('.rt-team[data-team="blik"]')[0].get("data-slots") == "5"


def test_w010_empty_roadmap_renders(tmp_path: Path) -> None:
    """W010: no projects -> warning, the empty roadmap is still rendered."""
    r = render_fixture(tmp_path, INVALID / "w010_no_projects.yaml")
    assert_ok(r.result)
    assert "W010" in r.result.codes()
    assert r.doc.cssselect(".rt-bar") == []
    assert len(r.doc.cssselect(".rt-lane")) == 1


def test_out30_kpi_row(we_summary_render: Rendered, we_overflow_render: Rendered) -> None:
    """OUT-30: KPI tiles Subdomains 1, Teams 2, Projects (finite) 8, Ongoing 1, Delayed 4, Slots 3,
    People 10 with DEV · PM · BA · QA breakdown; Over capacity only in overflow mode."""
    text = norm_ws(we_summary_render.doc.cssselect(".rt-summary")[0].text_content())
    for value, label in [("1", "Subdomains"), ("2", "Teams"), ("8", "Projects"), ("1", "Ongoing"), ("4", "Delayed")]:
        assert re.search(rf"(?<!\d){value}\s*{label}|{label}\s*{value}(?!\d)", text), (label, text)
    assert re.search(r"(?<!\d)3\s*Slots|Slots\s*3(?!\d)", text), text
    assert re.search(r"(?<!\d)10\s*People|People\s*10(?!\d)", text), text
    assert "DEV 6 · PM 1 · BA 1 · QA 2" in text
    assert "Over capacity" not in text
    over = norm_ws(we_overflow_render.doc.cssselect(".rt-summary")[0].text_content())
    assert re.search(r"(?<!\d)2\s*Over capacity|Over capacity\s*2(?!\d)", over), over


BINS = {
    ("subdomain", "core", "2027-02"): ("#2563EB", "#FFFFFF"),  # 80 %
    ("team", "alpha", "2027-05"): ("#93C5FD", "#1E293B"),  # 50 %
    ("team", "beta", "2027-06"): ("#93C5FD", "#1E293B"),  # 77 %
    ("team", "alpha", "2027-01"): ("#2563EB", "#FFFFFF"),  # 100 %
}


def test_out33_bin_colours(we_summary_render: Rendered) -> None:
    """OUT-33: load cells coloured by bin (50-79 % #93C5FD, 80-100 % #2563EB, 0 % text #94A3B8)."""
    doc = we_summary_render.doc
    cells = {(c.get("data-kind"), c.get("data-row"), c.get("data-month")): c for c in doc.cssselect(".rt-load-cell")}
    for key, (fill, ink) in BINS.items():
        css = matching_css(doc, cells[key]).upper()
        assert fill in css and ink in css, (key, fill, ink)
    zero = matching_css(doc, cells[("team", "beta", "2027-01")]).upper()
    assert "#94A3B8" in zero
    for fill in ("#2563EB", "#93C5FD", "#DBEAFE", "#FCA5A5"):
        assert fill not in zero, f"0 % cell has no fill, found {fill}"


def test_out33_low_bin(tmp_path: Path) -> None:
    """OUT-33: 1-49 % uses #DBEAFE (one S project in a 2-slot team: Jan 14/62 = 23 %)."""
    text = (
        COLOURS.split("projects:\n")[0]
        + "projects:\n  - name: Small\n    team: blik\n    size: S\n    start: 2027-01\n"
    )
    r = _render(tmp_path, text, "--summary")
    assert_ok(r.result)
    cell = r.doc.cssselect('.rt-load-cell[data-kind="team"][data-row="blik"][data-month="2027-01"]')[0]
    assert cell.get("data-load") == "0.2258"
    assert re.fullmatch(r"23[   ]?%", norm_ws(cell.text_content()))
    assert "#DBEAFE" in matching_css(r.doc, cell).upper()
