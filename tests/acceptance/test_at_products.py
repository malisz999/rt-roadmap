"""Products (RS 3.2, 5.2, 7.2, 7.10, 8, 9; AT-56 to AT-65).

PE = products-example.yaml: product BLIK (owned by Kanały płatności) has projects in teams of both
subdomains; product Raporty (owned by Merchant) has one project pinned to sky; the other projects are
standalone.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rtkit import (
    CONVERT,
    DE,
    DE_PLAN,
    DOCS_FIXTURES,
    EX,
    INVALID,
    MINIMAL,
    PE,
    PE_PLAN,
    WE,
    WE_PLAN,
    Rendered,
    assert_ok,
    copy_fixture,
    effective_lang,
    load_yaml,
    mask_version,
    norm_ws,
    project_by_name,
    render_fixture,
    run_oracle,
    run_rt,
)

STANDALONE = range(10)  # RS 5.2 step 3: palette entries for bars without a product


def _products(plan: dict) -> dict[str, dict]:  # type: ignore[type-arg]
    return {p["id"]: p for p in plan["products"]}


def _pinned(src: Path) -> set[int]:
    """seqs of projects with their own `color` in the input."""
    doc = load_yaml(src.read_bytes())
    return {seq for seq, p in enumerate(doc["projects"], 1) if "color" in p}


# --------------------------------------------------------------------------- AT-56


def test_at_56_product_bars_share_the_product_colour(pe_render: Rendered) -> None:
    """AT-56: every bar of a product has the product's data-color-index; plan products[*].projects lists
    their seqs; BLIK has bars in teams of two subdomains."""
    assert_ok(pe_render.result)
    plan = pe_render.plan
    products = _products(plan)
    assert list(products) == ["blik", "raporty"]
    pinned = _pinned(PE)
    sections: set[str] = set()
    for pid, product in products.items():
        members = [p for p in plan["projects"] if p["product"] == pid]
        assert product["projects"] == [p["seq"] for p in members]
        for p in members:
            bar = pe_render.bars[p["seq"]]
            assert bar.get("data-product") == pid
            if p["seq"] in pinned:
                continue
            assert p["color_index"] == product["color_index"]
            assert bar.get("data-color-index") == str(product["color_index"])
            if pid == "blik":
                sections.add(next(bar.iterancestors("section")).get("data-subdomain"))
    assert sections == {"channels", "merchant"}, "BLIK bars should sit in both subdomain cards"
    # automatic product colours come from entries 10-31 first, in file order (RS 5.2)
    assert [p["color_index"] for p in plan["products"]] == [10, 11]
    assert products["blik"] == {
        "id": "blik",
        "name": "BLIK",
        "domain": "channels",
        "owner": "Anna Kowalska",
        "color_index": 10,
        "color_name": "blue",
        "color_fill": "#BFDBFE",
        "projects": [1, 3, 5],
    }


def test_at_56_products_plan_is_golden(pe_render: Rendered) -> None:
    """The products example plan equals products-example.expected.json byte for byte (rt_version masked),
    and the oracle agrees."""
    assert mask_version(pe_render.plan_bytes).decode("utf-8") == mask_version(PE_PLAN.read_bytes()).decode("utf-8")
    oracle = run_oracle(PE)
    assert json.loads(PE_PLAN.read_text(encoding="utf-8")) == oracle
    plan = pe_render.plan
    keys = list(plan)
    assert keys.index("products") == keys.index("team_indicators") + 1 == keys.index("teams") + 2
    project_keys = list(plan["projects"][0])
    assert project_keys.index("product") == project_keys.index("team") + 1


# --------------------------------------------------------------------------- AT-57


def test_at_57_project_pin_wins_over_product_colour(pe_render: Rendered) -> None:
    """AT-57: the product project pinned to sky is sky (index 4); the product's other bars keep its colour."""
    plan = pe_render.plan
    export = project_by_name(plan, "Eksport CSV")
    assert export["product"] == "raporty"
    assert (export["color_index"], export["color_name"]) == (4, "sky")
    assert pe_render.bars[export["seq"]].get("data-color-index") == "4"
    raporty = _products(plan)["raporty"]
    daily = project_by_name(plan, "Raport dzienny")
    assert daily["color_index"] == raporty["color_index"] != 4
    assert pe_render.bars[daily["seq"]].get("data-color-index") == str(raporty["color_index"])


# --------------------------------------------------------------------------- AT-58


def test_at_58_standalone_bars_avoid_product_colours(pe_render: Rendered) -> None:
    """AT-58: standalone bars use indices 0-9 only; none shares a colour with an adjacent bar of any product."""
    plan = pe_render.plan
    by_seq = {p["seq"]: p for p in plan["projects"]}
    standalone = [p for p in plan["projects"] if p["product"] is None and p["visible"] is not None]
    assert standalone
    checked = 0
    for p in standalone:
        assert p["color_index"] in STANDALONE, p["name"]
        for n in p["neighbors"]:
            other = by_seq[n]
            if other["product"] is not None:
                checked += 1
                assert other["color_index"] != p["color_index"], (p["name"], other["name"])
    assert checked, "the fixture should place standalone bars next to product bars"
    assert not {"W007", "W009"} & set(pe_render.result.codes())


# --------------------------------------------------------------------------- AT-59


@pytest.mark.parametrize(("fixture", "expected"), [(WE, WE_PLAN), (DE, DE_PLAN)], ids=["WE", "DE"])
def test_at_59_files_without_products_keep_their_colours(tmp_path: Path, fixture: Path, expected: Path) -> None:
    """AT-59: WE and DE plans equal the updated expected files: every colour unchanged, product null,
    products []."""
    r = render_fixture(tmp_path, fixture)
    assert_ok(r.result)
    assert mask_version(r.plan_bytes) == mask_version(expected.read_bytes())
    assert r.plan["products"] == []
    assert all(p["product"] is None for p in r.plan["projects"])
    assert all(b.get("data-product") == "" for b in r.bars.values())
    assert not r.doc.cssselect(".rt-product")


def test_at_59_colours_equal_the_reference_colours() -> None:
    """The colours in the expected file are the version 1 colours: RS section 8 shows Reporting green (1), and
    every colour comes from the first ten palette entries."""
    plan = json.loads(WE_PLAN.read_text(encoding="utf-8"))
    reporting = project_by_name(plan, "Reporting")
    assert (reporting["color_index"], reporting["color_name"], reporting["color_fill"]) == (1, "green", "#BBF7D0")
    assert all(p["color_index"] is None or p["color_index"] < 10 for p in plan["projects"])


# --------------------------------------------------------------------------- AT-60

AT60 = """version: 1
roadmap:
  title: AT-60
  horizon: { start: 2027-01, end: 2027-06 }
  today: 2027-01-15
sizes: { S: 2, M: 4 }
subdomains:
  - id: channels
    name: Kanały płatności
    teams:
      - id: blik
        name: BLIK
        parallel_projects: 2
products:
  - id: blik
    name: BLIK
    domain: channels
  - id: blik
    name: Karty
    domain: channels
  - id: karty
    name: BLIK
    domain: chanels
projects:
  - name: BLIK w aplikacji
    team: blik
    product: blk
    size: M
"""


def test_at_60_product_reference_errors(tmp_path: Path) -> None:
    """AT-60: unknown product, duplicate product id and name, unknown domain -> exit 1; E038 and E039 with
    "did you mean", E024, E025, all positioned."""
    (tmp_path / "at60.yaml").write_text(AT60, encoding="utf-8")
    r = run_rt(["validate", "at60.yaml"], cwd=tmp_path)
    assert r.code == 1, r.describe()
    found = {(d.code, d.line, d.col): d.message for d in r.diags}
    assert set(found) == {("E024", 18, 9), ("E025", 22, 11), ("E039", 23, 13), ("E038", 27, 14)}, r.stderr
    assert found[("E024", 18, 9)] == 'product id "blik" already defined at line 15'
    assert found[("E025", 22, 11)] == 'product name "BLIK" already used at line 16'
    assert found[("E039", 23, 13)] == ('product "BLIK" references unknown domain "chanels" (did you mean "channels"?)')
    assert found[("E038", 27, 14)] == (
        'project "BLIK w aplikacji" references unknown product "blk" (did you mean "blik"?)'
    )
    assert [d.line for d in r.diags] == sorted(d.line for d in r.diags)
    assert r.stdout == b""


# --------------------------------------------------------------------------- AT-61


def test_at_61_product_without_projects(tmp_path: Path) -> None:
    """AT-61: a product with no projects -> W013 (exit 0, output still written)."""
    src = copy_fixture(INVALID / "w013_product_without_projects.yaml", tmp_path)
    r = run_rt(["render", src.name, "-o", "out.html"], cwd=tmp_path)
    assert_ok(r)
    assert [(d.code, d.line, d.col) for d in r.diags] == [("W013", 23, 5)]
    assert r.diags[0].message == 'product "Karty" has no projects'
    assert (tmp_path / "out.html").exists()
    strict = run_rt(["render", src.name, "-o", "strict.html", "--strict"], cwd=tmp_path)
    assert strict.code == 1 and not (tmp_path / "strict.html").exists()


# --------------------------------------------------------------------------- AT-62


def _many_products(n: int) -> str:
    lines = [
        "version: 1",
        "roadmap:",
        "  title: AT-62",
        "  horizon: { start: 2027-01 }",
        "  today: 2027-01-15",
        "sizes: { S: 2 }",
        "subdomains:",
        "  - id: core",
        "    name: Core",
        "    teams:",
        "      - id: t1",
        "        name: T1",
        "        parallel_projects: 1",
        "products:",
        *(f"  - {{ id: p{i:02d}, name: P{i:02d}, domain: core }}" for i in range(1, n + 1)),
        "projects:",
        *(f"  - {{ name: X{i:02d}, team: t1, product: p{i:02d}, size: S }}" for i in range(1, n + 1)),
    ]
    return "\n".join(lines) + "\n"


def test_at_62_more_products_than_colours(tmp_path: Path) -> None:
    """AT-62: 34 products without pins, each with a project -> 32 distinct product colours; W014 for the two
    products that share."""
    (tmp_path / "at62.yaml").write_text(_many_products(34), encoding="utf-8")
    r = run_rt(["render", "at62.yaml", "--plan", "p.json", "-o", "at62.html"], cwd=tmp_path)
    assert_ok(r)
    plan = json.loads((tmp_path / "p.json").read_text(encoding="utf-8"))
    indices = [p["color_index"] for p in plan["products"]]
    assert len(set(indices)) == 32
    assert indices[:32] == [*range(10, 32), *range(10)]
    assert indices[32:] == [0, 1]  # the least-used entries, lowest index first
    w014 = [d for d in r.diags if d.code == "W014"]
    assert [d.message for d in w014] == [
        'products "P23" and "P33" share colour "indigo" (more than 32 products)',
        'products "P24" and "P34" share colour "green" (more than 32 products)',
    ]
    assert [d.line for d in w014] == [15 + 32, 15 + 33]
    assert set(r.codes()) == {"W014"}


# --------------------------------------------------------------------------- AT-63


def test_at_63_legend_and_tooltips(pe_render: Rendered) -> None:
    """AT-63: the legend has one rt-product chip per product in file order; tooltips show
    `Product: … · owned by …`."""
    doc = pe_render.doc
    chips = doc.cssselect(".rt-legend .rt-product")
    assert [c.get("data-product") for c in chips] == ["blik", "raporty"]
    assert [c.get("data-color-index") for c in chips] == ["10", "11"]
    assert norm_ws(chips[0].text_content()) == "BLIK · Kanały płatności · Anna Kowalska"
    assert norm_ws(chips[1].text_content()) == "Raporty · Merchant · Piotr Nowak"
    assert all(effective_lang(c) == "pl" for c in chips)
    assert "#BFDBFE" in (chips[0].get("style") or "")
    # the Products row comes after the symbols (RS 7.2 item 2)
    groups = [norm_ws(g.cssselect(".rt-legend__title")[0].text_content()) for g in doc.cssselect(".rt-legend__group")]
    assert groups == ["Sizes", "Symbols", "Products"]

    plan = pe_render.plan
    line_blik = "Product: BLIK · owned by Kanały płatności (Anna Kowalska)"
    line_raporty = "Product: Raporty · owned by Merchant (Piotr Nowak)"
    for p in plan["projects"]:
        bar = pe_render.bars[p["seq"]]
        title = bar.get("title").split("\n")
        expected = {"blik": line_blik, "raporty": line_raporty}.get(p["product"])
        if expected is None:
            assert not any(t.startswith("Product:") for t in title), p["name"]
            assert bar.get("data-product") == ""
        else:
            assert title[1].startswith("Team: ") and title[2] == expected, title
            assert expected in bar.get("aria-label")
    # the BLIK bar in the Merchant card names its owning domain (Kanały płatności)
    portal = pe_render.bars[project_by_name(plan, "BLIK w portalu")["seq"]]
    assert next(portal.iterancestors("section")).get("data-subdomain") == "merchant"
    assert line_blik in portal.get("title")


# --------------------------------------------------------------------------- AT-64

PRODUCTS_BASE = """
products:
  - id: blik
    name: BLIK
    domain: channels
    owner: Anna Kowalska
  - id: app-core
    name: Aplikacja
    domain: merchant
"""


def _products_base(tmp: Path) -> None:
    text = (CONVERT / "teams.base.yaml").read_text(encoding="utf-8")
    (tmp / "base.yaml").write_text(text.replace("\nprojects: []", PRODUCTS_BASE + "\nprojects: []"), encoding="utf-8")


def test_at_64_convert_product_column(tmp_path: Path) -> None:
    """AT-64: CSV with a product column, --base holding products -> product written as the id (a name resolves
    too); unknown value -> E038; without --base -> W020."""
    _products_base(tmp_path)
    (tmp_path / "ok.csv").write_text(
        "Projekt;Rozmiar;Zespół;Produkt\nA;M;blik;blik\nB;S;app;Aplikacja\nC;S;app;\n", encoding="utf-8"
    )
    mapping = "Projekt=name,Rozmiar=size,Zespół=team,Produkt=product"
    r = run_rt(["convert", "ok.csv", "--base", "base.yaml", "--map", mapping], cwd=tmp_path)
    assert_ok(r)
    out = load_yaml(r.stdout)
    assert [p.get("product") for p in out["projects"]] == ["blik", "app-core", None]
    assert "  - name: A\n    team: blik\n    product: blik\n    size: M\n" in r.stdout.decode("utf-8")
    assert r.codes() == []
    rendered = run_rt(["render", "--plan", "-", "-o", "x.html"], stdin=r.stdout, cwd=tmp_path)
    assert_ok(rendered)
    plan = json.loads(rendered.stdout)
    assert [p["projects"] for p in plan["products"]] == [[1], [2]]

    (tmp_path / "bad.csv").write_text("name,size,team,product\nA,M,blik,BLlK\nB,S,app,nope\n", encoding="utf-8")
    bad = run_rt(["convert", "bad.csv", "--base", "base.yaml"], cwd=tmp_path)
    assert bad.code == 1 and bad.stdout == b""
    found = [(d.file, d.line, d.col, d.code) for d in bad.diags]
    assert found == [("bad.csv", 2, 4, "E038"), ("bad.csv", 3, 4, "E038")], bad.stderr
    assert bad.diags[0].message == (
        'project "A" references unknown product "BLlK" (did you mean "blik"?) [column "product"]'
    )

    skeleton = run_rt(["convert", "ok.csv", "--map", mapping], cwd=tmp_path)
    assert_ok(skeleton)
    assert [(d.line, d.col, d.code) for d in skeleton.diags] == [(1, 4, "W020")]
    assert skeleton.diags[0].message == 'column "Produkt" is ignored without --base'
    assert "product" not in skeleton.stdout.decode("utf-8")


# --------------------------------------------------------------------------- AT-65


def test_at_65_schema_accepts_products(tmp_path: Path) -> None:
    """AT-65: rt schema accepts products and project.product, and still validates every fixture."""
    jsonschema = pytest.importorskip("jsonschema")
    r = run_rt(["schema"], cwd=tmp_path)
    assert_ok(r)
    schema = json.loads(r.stdout.decode("utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    for fixture in (PE, WE, DE, EX, MINIMAL, *sorted(DOCS_FIXTURES.glob("*.yaml"))):
        errors = [e.message for e in validator.iter_errors(load_yaml(fixture.read_bytes()))]
        assert not errors, (fixture.name, errors)
    pe = load_yaml(PE.read_bytes())
    assert pe["products"] and any("product" in p for p in pe["projects"])
    bad = dict(pe, products=[{**pe["products"][0], "colour": "blue"}])
    assert list(validator.iter_errors(bad))
    missing = dict(pe, products=[{"id": "x", "name": "X"}])
    assert list(validator.iter_errors(missing)), "domain is required"
    wrong = dict(pe, projects=[{**pe["projects"][0], "product": "Not An Id"}])
    assert list(validator.iter_errors(wrong))
    pinned = dict(pe, products=[{**pe["products"][0], "color": "purple-deep"}])
    assert not list(validator.iter_errors(pinned))
