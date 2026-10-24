"""Dependencies, connectors and Polish text in HTML (RS OUT-27, OUT-28; AT-29, AT-36)."""

from __future__ import annotations

import re
import unicodedata

import pytest
from rtkit import (
    DE,
    DE_PLAN,
    Rendered,
    assert_ok,
    effective_lang,
    load_json,
    matching_css,
    norm_ws,
    render_fixture,
    shows_glyph,
    style_decls,
)


def _deps(el) -> set[tuple[str, str]]:
    return {(d.get("data-from"), d.get("data-to")) for d in el.cssselect(".rt-dep")}


def test_at_29_connectors(de_render: Rendered) -> None:
    """AT-29: inside the Product card rt-dep 1->2, 2->4 and 1->7 exist; none for 1->6, 2->6, 2->8."""
    assert_ok(de_render.result)
    doc = de_render.doc
    product = doc.cssselect('.rt-subdomain[data-subdomain="product"]')
    assert len(product) == 1
    in_product = _deps(product[0])
    assert {("1", "2"), ("2", "4"), ("1", "7")} <= in_product, in_product
    everywhere = _deps(doc)
    for cross in [("1", "6"), ("2", "6"), ("2", "8")]:
        assert cross not in everywhere, f"cross-subdomain connector {cross} must not be drawn"
    assert everywhere == {("1", "2"), ("2", "4"), ("1", "7")}, everywhere


def test_at_29_external_dependency_glyph(de_render: Rendered) -> None:
    """AT-29: Load testing and Release audit show the ↤ glyph; in-card successors do not."""
    doc, bars = de_render.doc, de_render.bars
    assert shows_glyph(doc, bars[6], "↤"), "Load testing must show ↤"
    assert shows_glyph(doc, bars[8], "↤"), "Release audit must show ↤"
    for seq in (2, 4, 7):
        assert not shows_glyph(doc, bars[seq], "↤"), f"bar {seq} has all dependencies in its card"


def test_at_29_tooltips_list_dependencies(de_render: Rendered) -> None:
    """AT-29/OUT-28: tooltips list dependencies as "After: API v2 (Product › API)"."""
    bars = de_render.bars
    for seq, refs in {
        2: ["API v2 (Product › API)"],
        4: ["Web checkout (Product › Web)"],
        6: ["API v2 (Product › API)", "Web checkout (Product › Web)"],
        7: ["API v2 (Product › API)"],
        8: ["Web checkout (Product › Web)"],
    }.items():
        for attr in ("title", "aria-label"):
            text = norm_ws(bars[seq].get(attr) or "")
            assert "After: " in text, (seq, attr, text)
            after = text.split("After: ", 1)[1]
            for ref in refs:
                assert ref in after, (seq, attr, ref, text)
    assert "After: API v2 (Product › API)" in norm_ws(bars[7].get("title") or "")
    assert "After:" not in (bars[1].get("title") or ""), "API v2 has no dependencies"


def test_at_29_depends_on_attribute(de_render: Rendered) -> None:
    """RS 7.10: data-depends-on lists seq numbers (space separated)."""
    bars = de_render.bars
    assert (bars[6].get("data-depends-on") or "").split() == ["1", "2"]
    assert (bars[8].get("data-depends-on") or "").split() == ["2"]
    assert (bars[1].get("data-depends-on") or "").split() == []


BNPL = "Płatności odroczone (BNPL) – pilot"  # exact spelling in roadmap.example.yaml (see Q-2)


def test_at_36_polish_text_and_lang(ex_render: Rendered) -> None:
    """AT-36: the BNPL project name appears exactly, its elements carry lang="pl";
    the plan JSON contains Płatności unescaped."""
    assert_ok(ex_render.result)
    doc = ex_render.doc
    assert doc.get("lang") == "en"
    holders = [el for el in doc.iter() if isinstance(el.tag, str) and BNPL in (el.text or "")]
    assert holders, "BNPL project name not found as element text"
    for el in holders:
        assert effective_lang(el) == "pl", f"<{el.tag} class={el.get('class')}> lacks lang=pl"
    for el in doc.iter():
        if not isinstance(el.tag, str):
            continue
        for attr in ("title", "aria-label"):
            if BNPL in (el.get(attr) or ""):
                assert effective_lang(el) == "pl", f"{attr} of <{el.tag} class={el.get('class')}> lacks lang=pl"
    assert BNPL.encode("utf-8") in ex_render.html
    assert "Płatności".encode() in ex_render.plan_bytes
    assert b"\\u0142" not in ex_render.plan_bytes, "plan JSON must not escape non-ASCII (PL-1)"


def test_at_36_lang_on_all_user_text(ex_render: Rendered) -> None:
    """OUT-27: title, subdomain and team names carry lang="pl"; page labels stay English."""
    doc = ex_render.doc
    for text in ["Roadmap płatności 2026–2027", "Kanały płatności", "Integracje acquirerów", "Cyberbezpieczeństwo"]:
        holders = [el for el in doc.iter() if isinstance(el.tag, str) and text in (el.text or "")]
        assert holders, text
        assert all(effective_lang(el) == "pl" for el in holders), text
        for el in holders:
            css = matching_css(doc, el)
            for m in re.finditer(r"text-transform\s*:\s*([\w-]+)", css):
                assert m.group(1) == "none", f"user text {text!r} is case-transformed by CSS"
    title = doc.find(".//title")
    assert title is not None and title.text == "Roadmap płatności 2026–2027"


def test_at_36_decomposed_dependency_name(tmp_path) -> None:
    """AT-36: a depends_on name typed in decomposed Unicode resolves (NFC)."""
    nfc = "Web zamówień"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    lines = DE.read_text(encoding="utf-8").split("\n")
    out = []
    for line in lines:
        if line.startswith("  - name: Web checkout"):
            out.append(line.replace("Web checkout", nfc))
        elif "depends_on" in line:
            out.append(line.replace("Web checkout", nfd))
        else:
            out.append(line)
    (tmp_path / "in").mkdir()
    src = tmp_path / "in" / "de-nfd.yaml"
    src.write_text("\n".join(out), encoding="utf-8")
    assert nfd.encode() in src.read_bytes()
    r = render_fixture(tmp_path, src)
    assert_ok(r.result)
    assert "E034" not in r.result.stderr
    expected = load_json(DE_PLAN)
    for exp in expected["projects"]:
        got = next(p for p in r.plan["projects"] if p["seq"] == exp["seq"])
        for key in ("depends_on", "start", "end", "lane", "delay_days", "delay_reason", "flags"):
            assert got[key] == exp[key], (exp["seq"], key)
    assert r.plan["projects"][1]["name"] == nfc
    assert nfc.encode() in r.html
    assert f"After: {nfc} (Product › Web)" in norm_ws(r.bars[4].get("title") or "")


def _route(path) -> list[tuple[str, float, float | None]]:
    out = []
    for cmd, a, b in re.findall(r"([MLHV])\s*(-?[\d.]+)(?:[ ,]+(-?[\d.]+))?", path.get("d") or ""):
        out.append((cmd, float(a), float(b) if b and cmd in "ML" else None))
    return out


def test_out28_connector_route(de_render: Rendered) -> None:
    """OUT-28: from the predecessor's right end at mid-height, 8 px right, along a lane gap to 8 px left
    of the successor, then into the successor's left edge at mid-height."""
    doc, bars = de_render.doc, de_render.bars

    def edges(seq: int) -> tuple[float, float]:
        d = style_decls(bars[seq])
        left = float(d["left"].removesuffix("px"))
        return left, left + float(d["width"].removesuffix("px"))

    mids = {}
    for path in doc.cssselect(".rt-dep"):
        frm, to = int(path.get("data-from")), int(path.get("data-to"))
        r = _route(path)
        assert r[0][0] == "M" and [c for c, _, _ in r[1:]] == ["H", "V", "H", "V", "H"], path.get("d")
        (_, x0, y0), (_, x1, _), (_, _ygap, _), (_, x2, _), (_, y3, _), (_, x3, _) = r
        assert x0 == pytest.approx(edges(frm)[1], abs=0.01), ("start at predecessor right end", frm, to)
        assert x1 == pytest.approx(x0 + 8, abs=0.01)
        assert x3 == pytest.approx(edges(to)[0], abs=0.01), ("end at successor left edge", frm, to)
        assert x2 == pytest.approx(x3 - 8, abs=0.01)
        mids.setdefault(frm, y0)
        mids.setdefault(to, y3)
    # 40 px slot rows (OUT-9): Partner onboarding (Web lane 2) sits one row below Web checkout (Web lane 1)
    assert mids[7] - mids[2] == pytest.approx(40, abs=0.01)
    assert mids[4] == pytest.approx(mids[2], abs=0.01), "same lane, same mid-height"
