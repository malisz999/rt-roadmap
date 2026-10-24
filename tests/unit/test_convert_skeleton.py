"""convert.skeleton: slug ids and the generated tree (RS CV-14, CV-15)."""

from __future__ import annotations

import pytest

from rt.convert.skeleton import Skeleton, slug, unique_slug


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Płatności Łódź", "platnosci-lodz"),
        ("Kanały płatności", "kanaly-platnosci"),
        ("Zespół wspólny", "zespol-wspolny"),
        ("  --Karty--  ", "karty"),
        ("BLIK & przelewy (PL)", "blik-przelewy-pl"),
        ("ŻÓŁW", "zolw"),
        ("X", "x"),
        ("ﬁnanse", "finanse"),  # NFKD splits the ligature
        ("!!!", ""),
        ("日本", ""),
    ],
)
def test_slug(name: str, expected: str) -> None:
    assert slug(name) == expected


def test_slug_is_cut_to_40_characters_without_trailing_dash() -> None:
    long = "a" * 39 + " b" + "c" * 10
    assert slug(long) == "a" * 39
    assert len(slug("x" * 100)) == 40


def test_unique_slug_suffixes_and_fallback() -> None:
    taken: set[str] = set()
    assert unique_slug("Karty", taken, "team") == "karty"
    assert unique_slug("KARTY", taken, "team") == "karty-2"
    assert unique_slug("karty!", taken, "team") == "karty-3"
    assert unique_slug("日本", taken, "team") == "team"
    assert unique_slug("!!", taken, "team") == "team-2"
    assert unique_slug("X", taken, "team") == "x"  # RS CV-15: only an empty result falls back


def test_unique_slug_keeps_40_characters_with_suffix() -> None:
    taken: set[str] = set()
    name = "y" * 50
    assert unique_slug(name, taken, "team") == "y" * 40
    second = unique_slug(name + "!", taken, "team")
    assert second == "y" * 38 + "-2"


def test_skeleton_orders_subdomains_and_teams_by_first_appearance() -> None:
    sk = Skeleton(title="Plan Q1", sizes=(("S", 2),), slots=2)
    sk.add("Karty", "Kanały płatności", 2)
    sk.add("Karty", "Kanały płatności", 3)
    sk.add("Płatności Łódź", "Merchant", 4)
    sk.add("Zespół wspólny", "Roadmap", 5)
    doc = sk.build()
    assert doc["roadmap"]["title"] == "Plan Q1"
    assert [sd["id"] for sd in doc["subdomains"]] == ["kanaly-platnosci", "merchant", "roadmap"]
    teams = [t for sd in doc["subdomains"] for t in sd["teams"]]
    assert [(t["id"], t["name"], t["parallel_projects"]) for t in teams] == [
        ("karty", "Karty", 2),
        ("platnosci-lodz", "Płatności Łódź", 2),
        ("zespol-wspolny", "Zespół wspólny", 2),
    ]
    assert sk.team_ids["Płatności Łódź"] == "platnosci-lodz"


def test_skeleton_add_returns_first_registration() -> None:
    sk = Skeleton()
    first = sk.add("Karty", "Kanały", 2)
    again = sk.add("Karty", "Merchant", 9)
    assert again is first
    assert (again.subdomain, again.line) == ("Kanały", 2)
