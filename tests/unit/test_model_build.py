"""model.build: structure checks, positions, partial models and CLI overrides (RS 3.2, CLI-1; ADS 8.2)."""

from __future__ import annotations

from datetime import date

import pytest
from iokit import MINIMAL, TODAY, build, codes, doc, messages

from rt.model.types import Mode, Overrides
from rt.timeutil import Month


def test_minimal_builds_with_defaults() -> None:
    model, diags = build(MINIMAL)
    assert model is not None and not diags.items
    s = model.settings
    assert s.title == "T" and s.today == TODAY and s.month_width == 120
    assert s.on_conflict is Mode.DELAY and s.adjacency_gap_days == 14
    assert s.horizon_start is None and s.horizon_end is None
    assert [(z.label, z.weeks) for z in model.sizes] == [("S", 2), ("M", 4)]
    assert model.teams[0].subdomain_id == "core" and model.teams[0].slots == 2
    assert model.subdomains[0].team_ids == ("alpha",)
    p = model.projects[0]
    assert (p.seq, p.name, p.team_id, p.size, p.start) == (1, "First", "alpha", "M", Month(2027, 1))
    assert (p.pos.line, p.pos.col) == (15, 5)
    assert (p.field_pos["team"].line, p.field_pos["team"].col) == (16, 11)
    assert model.source == "r.yaml"


def test_full_settings_and_overrides_win() -> None:
    text = (
        MINIMAL.replace(
            "  title: T\n",
            "  title: T\n  subtitle: Sub\n  horizon: {start: 2027-01, end: 2027-06}\n  today: 2026-10-23\n"
            "  month_width: 80\n  content_language: pl\n",
        )
        + "scheduling:\n  on_conflict: overflow\n  adjacency_gap_days: 0\n"
    )
    model, diags = build(text)
    assert model is not None and not diags.items
    s = model.settings
    assert (s.subtitle, s.today, s.month_width, s.content_language) == ("Sub", date(2026, 10, 23), 80, "pl")
    assert (s.horizon_start, s.horizon_end) == (Month(2027, 1), Month(2027, 6))
    assert s.on_conflict is Mode.OVERFLOW and s.adjacency_gap_days == 0
    over = Overrides(
        default_today=TODAY,
        horizon_start=Month(2027, 2),
        horizon_end=Month(2027, 3),
        today=date(2027, 2, 15),
        on_conflict=Mode.ERROR,
    )
    model, _ = build(text, over)
    assert model is not None
    s = model.settings
    assert (s.horizon_start, s.horizon_end, s.today, s.on_conflict) == (
        Month(2027, 2),
        Month(2027, 3),
        date(2027, 2, 15),
        Mode.ERROR,
    )


def test_today_quoted_string_accepted() -> None:
    model, diags = build(MINIMAL.replace("  title: T\n", "  title: T\n  today: '2027-02-15'\n"))
    assert model is not None and not diags.items and model.settings.today == date(2027, 2, 15)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a: 1\n", [("E004", 1, 1)]),
        ("version: 2\n", [("E004", 1, 10)]),
        ("version: true\n", [("E004", 1, 10)]),
        ("- 1\n", [("E011", 1, 1)]),
    ],
)
def test_fatal_documents(text: str, expected: list[tuple[str, int, int]]) -> None:
    model, diags = build(text)
    assert model is None
    assert codes(diags) == expected


def test_version_message() -> None:
    _, diags = build("version: 2\n")
    assert messages(diags) == ["unsupported version 2; this rt supports version 1"]


def test_missing_top_level_blocks() -> None:
    model, diags = build("version: 1\nsizez: {}\n")
    assert model is not None
    assert [c[0] for c in codes(diags)] == ["E010", "E010", "E010", "E010", "E002"]
    assert 'unknown key "sizez" in the file (did you mean "sizes"?)' in messages(diags)
    assert 'the file is missing required field "projects"' in messages(diags)


def test_e002_did_you_mean_in_team() -> None:
    _, diags = build(MINIMAL.replace("parallel_projects: 2", "paralel_projects: 2"))
    assert codes(diags) == [("E010", 11, 9), ("E002", 13, 9)]
    assert messages(diags)[1] == 'unknown key "paralel_projects" in team "alpha" (did you mean "parallel_projects"?)'


def test_wrong_types_and_ranges() -> None:
    text = doc(
        """\
        version: 1
        roadmap:
          title: ""
          subtitle: 5
          month_width: 10
          content_language: "p l"
          horizon: [1]
          today: 2026-10-23T10:00:00
        sizes:
          S: 2
          XL: 0
          M: 1.5
          extra-large: 2
        scheduling:
          on_conflict: dely
          adjacency_gap_days: true
        subdomains:
          - id: Core
            name: C
            teams:
              - id: alpha
                name: Alpha
                parallel_projects: two
                capacity: {developers: -1, testerz: 1}
          - nope
        projects: []
        """
    )
    model, diags = build(text)
    assert model is not None
    got = codes(diags)
    assert got == [
        ("E012", 3, 10),  # title length
        ("E011", 4, 13),  # subtitle type
        ("E012", 5, 16),  # month_width range
        ("E012", 6, 21),  # content_language
        ("E011", 7, 12),  # horizon not a mapping
        ("E013", 8, 10),  # today with time
        ("E012", 11, 7),  # size weeks range
        ("E011", 12, 6),  # size weeks type
        ("E012", 13, 3),  # size label
        ("E012", 15, 16),  # on_conflict
        ("E011", 16, 23),  # adjacency_gap_days bool
        ("E012", 18, 9),  # subdomain id pattern
        ("E011", 23, 28),  # parallel_projects type
        ("E012", 24, 32),  # capacity range
        ("E002", 24, 36),  # capacity unknown key
        ("E011", 25, 5),  # subdomain not a mapping
    ]
    msgs = messages(diags)
    assert '"parallel_projects" must be an integer, got "two"' in msgs
    assert 'size "XL" must be 1–520 weeks, got 0' in msgs
    assert '"on_conflict" must be delay, overflow or error, got "dely" (did you mean "delay"?)' in msgs
    assert 'unknown key "testerz" in capacity of team "alpha" (did you mean "testers"?)' in msgs
    # partial model: the team is kept, marked incomplete, with placeholders
    team = model.teams[0]
    assert team.incomplete and team.slots == 1 and team.capacity_given
    assert model.subdomains[0].id == "Core" and model.subdomains[0].incomplete


def test_empty_sizes_and_subdomains() -> None:
    text = MINIMAL.replace("sizes:\n  S: 2\n  M: 4\n", "sizes: {}\n")
    text = text[: text.index("subdomains:")] + "subdomains: []\nprojects: []\n"
    _, diags = build(text)
    assert codes(diags) == [("E042", 4, 8), ("E043", 5, 13)]


def test_project_fields() -> None:
    text = doc(
        """\
        version: 1
        roadmap: {title: T}
        sizes: {S: 2, 1: 1}
        subdomains:
          - id: core
            name: Core
            teams:
              - {id: alpha, name: Alpha, parallel_projects: 1}
        projects:
          - name: A
            id: a
            team: alpha
            size: S
            color: sky
            description: Opis
            depends_on: []
          - name: B
            team: alpha
            size: 1
            color: "#bae6fd"
            depends_on: a
          - name: C
            team: alpha
            ongoing: true
            depends_on: [a, B]
        """
    )
    model, diags = build(text)
    assert model is not None and not diags.items, messages(diags)
    a, b, c = model.projects
    assert a.color is not None and a.color.palette_name == "sky" and a.description == "Opis"
    assert b.size == "1" and b.color is not None and b.color.hex == "#BAE6FD" and b.color.text == "#bae6fd"
    assert [r.text for r in b.depends_on_refs] == ["a"] and b.depends_on_refs[0].pos.line == 21
    assert c.ongoing and c.size is None and [r.text for r in c.depends_on_refs] == ["a", "B"]
    assert (c.depends_on_refs[1].pos.line, c.depends_on_refs[1].pos.col) == (25, 21)
    assert model.sizes[1].label == "1"


def test_project_errors_and_partial_model() -> None:
    text = doc(
        """\
        version: 1
        roadmap: {title: T}
        sizes: {S: 2}
        subdomains:
          - id: core
            name: Core
            teams:
              - {id: alpha, name: Alpha, parallel_projects: 1}
        projects:
          - name: Both
            team: alpha
            size: S
            ongoing: true
          - name: Neither
            team: alpha
          - name: Bad
            id: Bad_Id
            team: 5
            size: [S]
            ongoing: yes
            start: 2027-13
            color: blu
            depends_on: {a: 1}
          - team: alpha
            size: S
            start: 2027-01-15
            colour: sky
            depends_on: [x, 3]
            description: 7
          - 5
        """
    )
    model, diags = build(text)
    assert model is not None
    assert codes(diags) == [
        ("E032", 12, 11),
        ("E032", 14, 5),
        ("E012", 17, 9),
        ("E011", 18, 11),
        ("E011", 19, 11),
        ("E011", 20, 14),
        ("E013", 21, 12),
        ("E033", 22, 12),
        ("E011", 23, 17),
        ("E010", 24, 5),
        ("E013", 26, 12),
        ("E002", 27, 5),
        ("E011", 28, 21),
        ("E011", 29, 18),
        ("E011", 30, 5),
    ]
    msgs = messages(diags)
    assert 'project #6 is missing required field "name"' not in msgs
    assert 'project #4 is missing required field "name"' in msgs
    assert 'project "Both" needs exactly one of size or ongoing: true' in msgs
    assert '"ongoing" must be true or false, got "yes"' in msgs
    assert 'invalid month "2027-13"; expected YYYY-MM' in msgs
    assert 'invalid month "2027-01-15"; expected YYYY-MM' in msgs
    assert 'color "blu" is not a palette name or #RRGGBB' in msgs
    assert 'unknown key "colour" in project #4 (did you mean "color"?)' in msgs
    assert [p.seq for p in model.projects] == [1, 2, 3, 4, 5]
    bad = model.projects[2]
    assert bad.incomplete and bad.team_id is None and bad.start is None and bad.id == "Bad_Id"
    assert model.projects[4].incomplete and model.projects[4].name is None
    assert model.projects[0].incomplete  # E032 marks it


def test_horizon_errors_use_effective_values() -> None:
    text = MINIMAL.replace("  title: T\n", "  title: T\n  horizon: {start: 2027-06, end: 2027-01}\n")
    _, diags = build(text)
    assert codes(diags) == [("E040", 4, 34)]
    assert messages(diags) == ["horizon end 2027-01 is before start 2027-06"]
    # --to fixes it
    _, diags = build(text, Overrides(default_today=TODAY, horizon_end=Month(2027, 9)))
    assert not diags.items
    # CLI-only values: points at the roadmap key
    _, diags = build(MINIMAL, Overrides(default_today=TODAY, horizon_start=Month(2030, 1), horizon_end=Month(2029, 1)))
    assert codes(diags) == [("E040", 2, 1)]
    _, diags = build(MINIMAL, Overrides(default_today=TODAY, horizon_start=Month(2020, 1), horizon_end=Month(2031, 12)))
    assert codes(diags) == [("E041", 2, 1)]
    assert messages(diags) == ["horizon spans 144 months; maximum is 120"]
    # only start in the file, end from the CLI → points at the start value
    text = MINIMAL.replace("  title: T\n", "  title: T\n  horizon: {start: 2027-06}\n")
    _, diags = build(text, Overrides(default_today=TODAY, horizon_end=Month(2027, 1)))
    assert codes(diags) == [("E040", 4, 20)]


def test_non_mapping_blocks() -> None:
    text = "version: 1\nroadmap: x\nsizes: [1]\nscheduling: 3\nsubdomains: {}\nprojects: x\n"
    model, diags = build(text)
    assert model is not None
    assert [c[0] for c in codes(diags)] == ["E011"] * 5
    assert model.settings.title == ""


def test_team_without_id_and_bad_team_item() -> None:
    text = doc(
        """\
        version: 1
        roadmap: {title: T}
        sizes: {S: 2}
        subdomains:
          - name: Core
            teams:
              - name: Alpha
                parallel_projects: 1
              - x
            extra: 1
        projects: []
        """
    )
    model, diags = build(text)
    assert model is not None and model.teams == ()
    assert messages(diags) == [
        'subdomain #1 is missing required field "id"',
        'team #1 of subdomain #1 is missing required field "id"',
        'team #2 of subdomain #1 must be a mapping, got "x"',
        'unknown key "extra" in subdomain #1',
    ]


# --- products (RS 3.2) ----------------------------------------------------------------------------------------

PRODUCTS = MINIMAL.replace(
    "projects:\n",
    "products:\n"
    "  - id: blik\n"
    "    name: BLIK\n"
    "    domain: core\n"
    "    owner: Anna\n"
    "    description: Płatności\n"
    "    color: sand-deep\n"
    "  - id: cards\n"
    "    name: Cards\n"
    "    domain: core\n"
    "projects:\n",
).replace("    team: alpha\n", "    team: alpha\n    product: blik\n", 1)


def test_products_and_project_product() -> None:
    model, diags = build(PRODUCTS)
    assert model is not None and not diags.items
    blik, cards = model.products
    assert (blik.id, blik.name, blik.domain_id, blik.owner, blik.description) == (
        "blik",
        "BLIK",
        "core",
        "Anna",
        "Płatności",
    )
    assert blik.color is not None and blik.color.palette_name == "sand-deep"
    assert (blik.pos.line, blik.pos.col) == (15, 5) and blik.field_pos["domain"].line == 17
    assert (cards.owner, cards.description, cards.color) == (None, None, None)
    assert model.product("cards") is cards
    assert model.projects[0].product_id == "blik"
    with pytest.raises(KeyError):
        model.product("nope")


def test_products_absent_is_empty() -> None:
    model, diags = build(MINIMAL)
    assert model is not None and not diags.items
    assert model.products == () and model.projects[0].product_id is None


def test_product_structure_errors() -> None:
    text = MINIMAL.replace(
        "projects:\n",
        "products:\n"
        "  - just a string\n"
        "  - name: No id\n"
        "    domain: core\n"
        "  - id: Bad Id\n"
        "    name: X\n"
        "    domain: [core]\n"
        "    colour: sky\n"
        "    color: blu\n"
        "    owner: " + "o" * 101 + "\n"
        "  - id: noname\n"
        "projects:\n",
    ).replace("    team: alpha\n", "    team: alpha\n    product: [blik]\n", 1)
    model, diags = build(text)
    assert model is not None
    found = [(c, line) for c, line, _ in codes(diags)]
    assert found == [
        ("E011", 15),  # product #1 is not a mapping
        ("E010", 16),  # product #2 has no id
        ("E012", 18),  # bad id pattern (kept)
        ("E011", 20),  # domain is a list
        ("E002", 21),  # colour
        ("E033", 22),  # blu
        ("E012", 23),  # owner too long
        ("E010", 24),  # noname: name
        ("E010", 24),  # noname: domain
        ("E011", 28),  # project.product is a list
    ]
    msgs = messages(diags)
    assert msgs[0] == 'product #1 must be a mapping, got "just a string"'
    assert 'unknown key "colour" in product "Bad Id" (did you mean "color"?)' in msgs
    assert '"domain" must be a subdomain id, got a list' in msgs
    assert [p.id for p in model.products] == ["Bad Id", "noname"]
    bad, noname = model.products
    assert bad.incomplete and bad.domain_id == "" and bad.color is None
    assert noname.name == "noname" and noname.incomplete
    assert model.projects[0].product_id is None and model.projects[0].incomplete


def test_products_must_be_a_list() -> None:
    model, diags = build(MINIMAL.replace("projects:\n", "products: {}\nprojects:\n"))
    assert model is not None and model.products == ()
    assert messages(diags) == ['"products" must be a list, got a mapping']
