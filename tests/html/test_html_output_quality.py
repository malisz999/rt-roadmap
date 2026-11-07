"""Output quality and page structure (RS 7.1-7.11; AT-22..AT-25)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from rtkit import (
    DE,
    EX,
    WE,
    Rendered,
    assert_ok,
    css_text,
    matching_css,
    norm_ws,
    parse_html,
    render_fixture,
    style_decls,
)

HEADER = """version: 1
roadmap:
  title: {title}
  today: 2027-01-15
  horizon: {{ start: 2027-01, end: 2027-06 }}
sizes:
  M: 4
subdomains:
  - id: core
    name: {subdomain}
    teams:
      - id: {team_id}
        name: {team_name}
        parallel_projects: 1
        capacity: {{ developers: 1 }}
projects:
"""


def _write(tmp: Path, text: str, name: str = "in.yaml") -> Path:
    p = tmp / name
    p.write_text(text, encoding="utf-8")
    return p


def _render_text(tmp: Path, text: str, *extra: str) -> tuple[Rendered, Path]:
    (tmp / "src").mkdir(exist_ok=True)
    src = _write(tmp / "src", text)
    return render_fixture(tmp, src, *extra), src


# --------------------------------------------------------------------------- AT-22 / OUT-4


def test_at_22_script_name_is_literal_text(tmp_path) -> None:
    """AT-22: project name <script>alert(1)</script> appears as literal text; no <script element."""
    text = HEADER.format(title="Escaping", subdomain="Core", team_id="blik", team_name="BLIK") + (
        '  - name: "<script>alert(1)</script>"\n    team: blik\n    size: M\n    start: 2027-01\n'
    )
    r, _ = _render_text(tmp_path, text)
    assert_ok(r.result)
    assert b"<script" not in r.html.lower()
    doc = r.doc
    assert list(doc.iter("script")) == []
    assert "<script>alert(1)</script>" in doc.text_content()
    bar = r.bars[1]
    assert "<script>alert(1)</script>" in (bar.get("title") or "")
    assert "<script>alert(1)</script>" in r.plan["projects"][0]["name"]


def test_out4_all_user_strings_escaped(tmp_path) -> None:
    """OUT-4: & < > " ' in every kind of user string are escaped and survive as literal text."""
    nasty_title = 'Tom & Jerry\'s "<b>plan</b>"'
    text = (
        HEADER.format(
            title="'Tom & Jerry''s \"<b>plan</b>\"'",
            subdomain="'R&D <i>lab</i>'",
            team_id="blik",
            team_name="'<u>Team</u> & co'",
        )
        + "  - name: 'A & B <em>x</em> \"q\" ''s'''\n"
        + "    team: blik\n    size: M\n    start: 2027-01\n"
        + "    description: '<img src=x onerror=alert(1)> & \"d\"'\n"
    )
    r, _ = _render_text(tmp_path, text)
    assert_ok(r.result)
    doc = r.doc
    for tag, inner in (("b", "plan"), ("i", "lab"), ("u", "Team"), ("em", "x")):
        injected = [el for el in doc.iter(tag) if (el.text or "") == inner]
        assert injected == [], f"user markup <{tag}>{inner}</{tag}> was not escaped"
    assert list(doc.iter("img")) == [], "user markup <img> was not escaped"
    body = doc.text_content()
    assert nasty_title in body
    assert "R&D <i>lab</i>" in body
    assert "<u>Team</u> & co" in body
    assert "A & B <em>x</em> \"q\" 's'" in body
    assert doc.find(".//title").text == nasty_title
    bar_title = r.bars[1].get("title") or ""
    assert '<img src=x onerror=alert(1)> & "d"' in bar_title
    assert b"<img" not in r.html and b"<em>" not in r.html


# --------------------------------------------------------------------------- AT-23


def test_at_23_polish_and_no_string(tmp_path) -> None:
    """AT-23: names with ąćęłńóśźż and a team named NO: text preserved exactly; NO is a string."""
    polish = "Zażółć gęślą jaźń ąćęłńóśźż ĄĆĘŁŃÓŚŹŻ"
    text = HEADER.format(title="Polski test", subdomain="Kanały płatności", team_id="no", team_name="NO") + (
        f"  - name: {polish}\n    team: no\n    size: M\n    start: 2027-01\n"
        "  - name: on\n    team: no\n    size: M\n    start: 2027-03\n"
    )
    r, _ = _render_text(tmp_path, text)
    assert_ok(r.result)
    plan = r.plan
    assert [p["name"] for p in plan["projects"]] == [polish, "on"]
    assert all(p["team"] == "no" for p in plan["projects"])
    assert [t["id"] for t in plan["teams"]] == ["no"]
    doc = r.doc
    team = doc.cssselect('.rt-team[data-team="no"]')
    assert len(team) == 1
    names = [el for el in team[0].iter() if isinstance(el.tag, str) and (el.text or "").strip() == "NO"]
    assert names, "team name NO must be shown as its own text"
    assert not [el for el in team[0].iter() if isinstance(el.tag, str) and (el.text or "").strip().lower() == "false"]
    assert polish in doc.text_content()
    assert "Kanały płatności" in doc.text_content()
    assert polish.encode("utf-8") in r.html
    assert polish.encode("utf-8") in r.plan_bytes


# --------------------------------------------------------------------------- AT-24 / OUT-3 / OUT-5

URL_ATTR = re.compile(r"^\s*(https?:|//)", re.I)
CSS_URL = re.compile(r"url\(\s*['\"]?\s*(https?:|//)", re.I)


def assert_no_external_urls(html: bytes) -> None:
    doc = parse_html(html)
    for el in doc.iter():
        if not isinstance(el.tag, str):
            continue
        for attr in ("src", "href", "xlink:href", "{http://www.w3.org/1999/xlink}href", "srcset", "action"):
            v = el.get(attr)
            if v is not None:
                assert not URL_ATTR.search(v), f"external URL in <{el.tag} {attr}={v!r}>"
        style = el.get("style") or ""
        assert not CSS_URL.search(style), f"external url() in inline style: {style}"
    assert not CSS_URL.search(css_text(doc)), "external url() in CSS"
    assert not re.search(rb"@import", html), "no @import allowed"


def test_at_24_deterministic_and_offline(tmp_path, ex_render: Rendered) -> None:
    """AT-24: render EX twice -> identical SHA-256; no http:, https: or // URL in src, href, url()."""
    assert_ok(ex_render.result)
    second = render_fixture(tmp_path, EX)
    assert_ok(second.result)
    assert hashlib.sha256(ex_render.html).hexdigest() == hashlib.sha256(second.html).hexdigest()
    assert_no_external_urls(ex_render.html)


@pytest.mark.parametrize("fixture", [WE, DE], ids=["WE", "DE"])
def test_out3_no_external_resources(tmp_path, fixture: Path) -> None:
    """OUT-3 for WE and DE with --summary; system font stack."""
    r = render_fixture(tmp_path, fixture, "--summary")
    assert_ok(r.result)
    assert_no_external_urls(r.html)
    css = r.css
    assert "system-ui" in css and "Segoe UI" in css, "system font stack (OUT-3)"


# --------------------------------------------------------------------------- AT-25 (structural part)


def _check_page(r: Rendered, title: str, n_warnings: int, sizes: list[tuple[str, int]]) -> None:
    assert_ok(r.result)
    html, doc, css = r.html, r.doc, r.css
    # OUT-1
    assert html.lstrip()[:15].lower() == b"<!doctype html>"
    assert doc.get("lang") == "en"
    assert doc.find(".//title").text == title
    assert re.search(rb"<meta[^>]+charset=[\"']?utf-8", html, re.I)
    # OUT-2: all CSS in one <style>
    assert len(list(doc.iter("style"))) == 1
    assert doc.cssselect('link[rel="stylesheet"]') == []
    # header and sticky timeline
    h1 = list(doc.iter("h1"))
    assert len(h1) == 1 and norm_ws(h1[0].text_content()) == title
    assert re.search(r"position\s*:\s*sticky", css), "sticky timeline header / labels (7.2, OUT-6)"
    # legend: size chips in declaration order, then the symbols
    legend = [el for el in doc.iter() if isinstance(el.tag, str) and "legend" in (el.get("class") or "")]
    assert legend, "no legend element"
    legend_text = norm_ws(legend[0].text_content())
    pos = []
    for label, weeks in sizes:
        m = re.search(rf"(?<![A-Za-z]){re.escape(label)}\s*{weeks}w", legend_text)
        assert m, f"legend chip {label} {weeks}w missing: {legend_text}"
        pos.append(m.start())
    assert pos == sorted(pos), "legend chips must follow declaration order"
    # warnings panel (closed <details>)
    panels = [d for d in doc.iter("details") if d.cssselect(".rt-warning") or "warning" in (d.get("class") or "")]
    if n_warnings:
        assert len(panels) == 1, "one warnings panel"
        assert panels[0].get("open") is None, "warnings panel is closed"
        assert len(panels[0].cssselect(".rt-warning")) == n_warnings
        summary = panels[0].find("summary")
        assert summary is not None
        assert re.search(rf"\b{n_warnings} warnings?\b", norm_ws(summary.text_content()))
    else:
        assert panels == [] and doc.cssselect(".rt-warning") == []
    # footer
    assert "Generated by rt 1.3.0" in norm_ws(doc.text_content())
    # print rules (OUT-25)
    page = re.search(r"@page\s*\{([^}]*)\}", css)
    assert page, "@page rule missing"
    assert re.search(r"size\s*:\s*A3\s+landscape", page.group(1))
    assert re.search(r"margin\s*:\s*10mm", page.group(1))
    assert re.search(r"print-color-adjust\s*:\s*exact", css)
    assert re.search(r"break-inside\s*:\s*avoid", css)
    # headings (OUT-26)
    subs = doc.cssselect(".rt-subdomain")
    assert subs
    for s in subs:
        assert len(list(s.iter("h2"))) >= 1
    assert len(list(doc.iter("h3"))) >= len(doc.cssselect(".rt-team"))


def test_at_25_visual_review_structure(tmp_path) -> None:
    """AT-25: the visual review in Chrome, Firefox, Safari and Edge is MANUAL (documented in
    tests/TRACEABILITY.md). Automated part: EX, WE and DE render, and the reviewed structure is
    present: sticky header CSS, legend, warnings panel, footer, A3-landscape print rules."""
    (tmp_path / "ex").mkdir()
    ex = render_fixture(tmp_path / "ex", EX)
    _check_page(
        ex, "Roadmap płatności 2026–2027", 1, [("XS", 1), ("S", 2), ("M", 4), ("L", 8), ("XL", 13), ("XXL", 26)]
    )
    text = norm_ws(ex.doc.text_content())
    assert "Oct 2026 – Jun 2027" in text
    assert "As of 23 Oct 2026" in text
    assert "Today · 23 Oct" in text
    (tmp_path / "we").mkdir()
    we = render_fixture(tmp_path / "we", WE)
    _check_page(we, "Scheduling worked example", 4, [("S", 2), ("M", 4), ("L", 8)])
    assert "Jan 2027 – Jun 2027" in norm_ws(we.doc.text_content())
    (tmp_path / "de").mkdir()
    de = render_fixture(tmp_path / "de", DE, "--summary")
    _check_page(de, "Dependencies worked example", 3, [("S", 2), ("M", 4), ("L", 8)])


# --------------------------------------------------------------------------- bars and lanes (OUT-12..OUT-22)


def test_out18_tooltip_content(we_render: Rendered) -> None:
    """OUT-18: title and aria-label hold name, team, size, dates as '29 Jan 2027'; tabindex=0."""
    bars = we_render.bars
    for b in bars.values():
        assert b.get("tabindex") == "0"
        assert b.get("title") and b.get("aria-label")
    rep = norm_ws(bars[3].get("title"))
    for part in ("Reporting", "Alpha", "4w", "1 Jan 2027", "29 Jan 2027", "25 Feb 2027"):
        assert part in rep, (part, rep)
    aria = norm_ws(bars[3].get("aria-label"))
    for part in ("Reporting", "Alpha", "29 Jan 2027", "25 Feb 2027"):
        assert part in aria, (part, aria)
    assert "Ongoing" in (bars[5].get("title") or "")


def test_out17_out20_bar_content(we_render: Rendered) -> None:
    """OUT-17: >=120 px -> name and chip 'L · 8w'; 48-119 px -> name only.
    OUT-20: delay pill +Nw (59 days -> +8w)."""
    bars = we_render.bars
    big = norm_ws(bars[9].text_content())
    assert "Big bang" in big and "L · 8w" in big and "+8w" in big, big
    quick = norm_ws(bars[8].text_content())
    assert "Quick win" in quick and "S · 2w" not in quick, quick
    core = norm_ws(bars[1].text_content())
    assert "Core API" in core and "L · 8w" in core


def test_out12_team_label(we_render: Rendered) -> None:
    """OUT-12: role badges DEV/PM/BA/QA, parallel slots; OUT-10: subdomain counts."""
    doc = we_render.doc
    alpha = norm_ws(doc.cssselect('.rt-team[data-team="alpha"]')[0].text_content())
    for badge in ("DEV 4", "PM 1", "BA 1", "QA 1", "2 parallel slots"):
        assert badge in alpha, (badge, alpha)
    beta = norm_ws(doc.cssselect('.rt-team[data-team="beta"]')[0].text_content())
    for badge in ("DEV 2", "PM 0", "BA 0", "QA 1"):
        assert badge in beta, (badge, beta)
    assert re.search(r"1 parallel slots?", beta)
    core = norm_ws(doc.cssselect(".rt-subdomain")[0].text_content())
    assert "2 teams · 9 projects" in core


def test_out24_no_today_line_outside_horizon(tmp_path) -> None:
    """OUT-24: the Today line is drawn only when today is inside the horizon."""
    r = render_fixture(tmp_path, WE, "--today", "2026-01-10")
    assert_ok(r.result)
    assert r.doc.cssselect(".rt-today") == []
    assert r.plan["today"] == "2026-01-10"


def test_out15_out22_overflow_lanes(we_overflow_render: Rendered) -> None:
    """OUT-15/OUT-22: overflow lanes +1 after the slots, 'Over capacity', dashed #DC2626 outline."""
    assert_ok(we_overflow_render.result)
    doc = we_overflow_render.doc
    lanes = [(ln.get("data-team"), ln.get("data-lane"), ln.get("data-overflow")) for ln in doc.cssselect(".rt-lane")]
    assert lanes == [
        ("alpha", "1", "false"),
        ("alpha", "2", "false"),
        ("alpha", "3", "true"),
        ("beta", "1", "false"),
        ("beta", "2", "true"),
    ]
    text = norm_ws(doc.text_content())
    assert "Over capacity" in text and "+1" in text
    rep = we_overflow_render.bars[3]
    assert "over_capacity" in (rep.get("data-flags") or "").split()
    css = matching_css(doc, rep).lower()
    assert "dashed" in css and "#dc2626" in css


NARROW = """version: 1
roadmap:
  title: Narrow bars
  today: 2027-01-15
  month_width: 60
  horizon: { start: 2027-02, end: 2027-06 }
sizes:
  XS: 1
  N9: 9
subdomains:
  - id: core
    name: Core
    teams:
      - id: blik
        name: BLIK
        parallel_projects: 2
        capacity: { developers: 1 }
projects:
  - name: Mostly before
    team: blik
    size: N9
    start: 2026-12
  - name: Tiny
    team: blik
    size: XS
    start: 2027-03
"""


def test_out8_minimum_width_and_inset(tmp_path) -> None:
    """OUT-8 at month_width 60: inset 2 px each side, minimum drawn width 6 px.

    Mostly before: 2026-12-01 + 63 d = 2027-02-02, visible 1 day -> x 0..2.14 -> left 2.00, width 6.00.
    Tiny: x(1 Mar) = 60, x(8 Mar) = 60 + 7/31*60 = 73.548 -> left 62.00, width 9.55.
    """
    r, _ = _render_text(tmp_path, NARROW)
    assert_ok(r.result)
    d1 = style_decls(r.bars[1])
    assert (d1["left"], d1["width"]) == ("2.00px", "6.00px")
    assert "clipped_left" in (r.bars[1].get("data-flags") or "").split()
    d2 = style_decls(r.bars[2])
    assert (d2["left"], d2["width"]) == ("62.00px", "9.55px")
