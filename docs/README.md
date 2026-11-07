# rt — project layout

What each folder is for. Everything under `docs/`, `scripts/`, `.claude/` and `CLAUDE.md` is human-owned;
the developer and tester agents may read it but never change it (see `CLAUDE.md`).

```
roadmap/
├── CLAUDE.md                     Shared rules for all agents: documents, commands, file ownership
├── .claude/agents/
│   ├── developer.md              Developer agent: implements src/, fixes defects
│   └── tester.md                 Tester agent: black-box acceptance tests, files defects
├── scripts/
│   └── dev_test_loop.py          Orchestrator: runs developer <-> tester rounds per milestone (M1–M8)
└── docs/
    ├── README.md                 This file
    ├── requirements.md           Requirements specification (RS): what rt must do, AT-01…AT-74
    ├── architecture.md           Architecture and design spec (ADS): stack, modules, milestones M1–M8
    ├── manual/                   User manual and one-page cheat sheet (Markdown + A4 PDF), with screenshots
    ├── images/                   Diagrams referenced by the two specs
    │   ├── page-layout.svg               RS 7.2: page layout, worked example drawn to scale
    │   └── architecture-pipeline.svg     ADS 3: pipeline stages, output branches, diagnostics
    ├── fixtures/                 Inputs and expected outputs (read-only test data)
    │   ├── roadmap.schema.json           JSON Schema for the YAML input format, version 1
    │   ├── roadmap.minimal.yaml          Smallest valid input
    │   ├── roadmap.example.yaml          Full, commented example (Polish payments roadmap)
    │   ├── scheduling-worked-example.yaml          "WE" fixture: capacity scheduling (RS 4.4)
    │   ├── scheduling-worked-example.expected.json Expected plan for WE
    │   ├── dependencies-example.yaml               "DE" fixture: dependencies, auto start (RS 4.5)
    │   ├── dependencies-example.expected.json      Expected plan for DE
    │   ├── products-example.yaml                   "PE" fixture: products and their colours (RS 5.2)
    │   ├── products-example.expected.json          Expected plan for PE
    │   ├── lock-example.yaml                       "LE" fixture: locked projects (RS 4.6, CR-3)
    │   ├── lock-example.expected.json              Expected plan for LE
    │   └── convert/              Fixtures for `rt convert` (CSV -> YAML)
    │       ├── projects.minimal.csv              Two-column CSV, no base file
    │       ├── projects.minimal.expected.yaml    Expected output of the above
    │       ├── teams.base.yaml                   Base file (everything but projects)
    │       ├── projects.pl.csv                   Polish headers, ';' delimiter, UTF-8 BOM, CRLF
    │       └── projects.pl.expected.yaml         Expected output with --base teams.base.yaml
    └── reference/                Test oracles — test tooling only, never imported from src/
        ├── reference_plan.py             Produces the *.expected.json plans
        └── reference_convert.py          Produces the convert/*.expected.yaml files
```

## Regenerating / checking expected outputs

Requires `ruamel.yaml` (0.19.x). Run from the repository root:

```
python docs/reference/reference_plan.py docs/fixtures/scheduling-worked-example.yaml
python docs/reference/reference_plan.py docs/fixtures/dependencies-example.yaml
python docs/reference/reference_plan.py docs/fixtures/products-example.yaml
python docs/reference/reference_plan.py docs/fixtures/lock-example.yaml
python docs/reference/reference_convert.py docs/fixtures/convert/projects.minimal.csv
python docs/reference/reference_convert.py docs/fixtures/convert/projects.pl.csv \
    --base docs/fixtures/convert/teams.base.yaml \
    --map "Projekt=name,Rozmiar=size,Zespół=team,Start=start,Zależności=depends_on,Ciągły=ongoing,Opis=description"
```

Each command's stdout matches the corresponding expected file byte for byte.
`projects.pl.csv` has Polish headers, so it needs the `--map` option shown above.

## Where the specs come from

`requirements.md` and `architecture.md` are Markdown exports of the living docs
"Roadmap Renderer CLI — Requirements Specification" and "rt — Architecture and Design Specification"
(as of 23 Oct 2026). The diagrams embedded in those docs are saved as SVG files in `images/`.
When a spec changes, re-export it here so the agents read the current version.
