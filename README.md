# rt — roadmap renderer (Roadmap as Code)

`rt` reads one hand-written YAML file describing subdomains, teams, t-shirt sizes and projects, schedules the
projects into each team's parallel slots, and writes one self-contained HTML page: month-scaled swimlanes grouped
by subdomain, with quarters, a Today line, dependency connectors and an optional monthly-load summary. The page
has no JavaScript and no external resources, so it opens offline and prints on A3 landscape.

The behaviour is specified in [docs/requirements.md](docs/requirements.md); the design in
[docs/architecture.md](docs/architecture.md).

## Install

```bash
uv tool install rt-roadmap      # or: pipx install rt-roadmap
rt --version
```

For development: `uv sync`, then `uv run rt …`.

## Quick start

```bash
rt init                          # writes a commented roadmap.yaml (Polish payments example)
rt render roadmap.yaml           # writes roadmap.html next to it
rt render roadmap.yaml --summary # adds KPIs and a monthly load heatmap
rt validate roadmap.yaml         # check only; diagnostics on stderr
```

A minimal file:

```yaml
version: 1
roadmap:
  title: My Roadmap
sizes: { S: 2, M: 4, L: 8 }          # weeks
subdomains:
  - id: product
    name: Product
    teams:
      - id: core
        name: Core Team
        parallel_projects: 2
projects:
  - name: First project
    team: core
    size: M
    start: 2027-01                   # omit to start as soon as a slot is free
  - name: Follow-up
    team: core
    size: S
    depends_on: [First project]      # finish-to-start
```

## Products

A product groups projects across teams and is owned by one domain (a subdomain id). All of its bars share one
colour, and the legend lists each product with its owning domain and owner:

```yaml
products:
  - id: blik
    name: BLIK
    domain: product                  # the owning subdomain
    owner: Anna Kowalska             # optional
projects:
  - name: BLIK in the app
    team: core                       # a team in any subdomain
    product: blik
    size: M
```

Projects without `product` are coloured as before. A project's own `color` wins over its product's colour.

## Locked projects

A locked project's start month has been promised to the business, a customer or a partner. rt places locked
projects first, exactly at their start, and never moves them; other projects are scheduled around them:

```yaml
projects:
  - name: Partner launch
    team: core
    size: M
    start: 2027-02                   # required for a locked project
    locked: true
    promised_to: Partner X           # optional
```

Locked bars have a dark frame and a padlock. When a promise cannot be kept (a dependency ends later, or other locked
work fills every slot of the team), the bar stays at its date, turns red ("promise at risk") and rt warns W015.
`--summary` adds a "Commitments" table listing every promise and its status. In `rt convert`, a `locked` column
accepts the same values as `ongoing` (`1`/`0`, `yes`/`no`, `tak`/`nie`, `x`).

## Team indicators

Each team label shows two ratios that make team composition comparable: **DEV per slot** (developers ÷
`parallel_projects`) and **DEV per QA** (developers ÷ testers), both from `capacity`. For both, higher is worse: a value more
than 50 % above the median of all teams is marked red ▲, more than 50 % below it green ▼, and a team with
developers but no testers shows a red `! no QA`.
Write your own targets instead of the median rule with an optional block:

```yaml
team_norms:
  devs_per_slot: { min: 2, max: 3 }
  devs_per_qa: { max: 4 }
```

`--summary` adds a "Team composition" table; the plan JSON carries the values in `teams[]` and `team_indicators`.

`rt schema` prints the JSON Schema; add `# yaml-language-server: $schema=./roadmap.schema.json` at the top of
your file for completion and validation in editors such as VS Code.

## Commands

| Command | Purpose |
| --- | --- |
| `rt render [<input>] [-o PATH] [--summary] [--plan PATH]` | Validate, schedule, colour and write the HTML |
| `rt validate [<input>] [--format text\|json] [--plan PATH]` | Validate and schedule only |
| `rt convert [<input.csv>] [--base FILE] [--map "Projekt=name,…"]` | Turn a CSV project list into rt YAML |
| `rt init [<path> \| -] [--minimal] [--force]` | Write a starter file |
| `rt schema [-o PATH]` | Print the JSON Schema of the input format |

Common options: `--from YYYY-MM`, `--to YYYY-MM`, `--today YYYY-MM-DD`, `--on-conflict delay|overflow|error`,
`--strict` (warnings fail the run), `-q` (no warnings or summary line). Run `rt <command> --help` for all options.

Exit codes: 0 success · 1 validation or conversion errors (or warnings with `--strict`) · 2 usage error ·
3 scheduling conflict (E060/E061) · 4 I/O error · 141 output pipe closed early.

## Pipelines

Every command reads standard input and writes its content to standard output; messages always go to standard
error, and nothing is written to stdout when a command fails.

```bash
# spreadsheet → YAML → HTML in one go
rt convert projects.csv --base teams.yaml | rt render -o roadmap.html

# check a converted file without saving it
rt convert projects.csv --base teams.yaml | rt validate

# HTML to a file, plan JSON down the pipe: list delayed projects
rt render roadmap.yaml -o roadmap.html --plan - | jq -r '.projects[] | select(.delay_days > 0) | .name'

# stdin to stdout
cat roadmap.yaml | rt render --summary > roadmap.html

# starter file, edited on the fly, rendered without touching the disk
rt init --minimal - | sed 's/My Roadmap/Q1 plan/' | rt render > q1.html
```

Windows PowerShell 5.1 re-encodes text between programs; there, use `-o` for files and set
`$OutputEncoding = [Text.UTF8Encoding]::new()` before piping. cmd.exe and PowerShell 7.4+ pass bytes unchanged.

## Spreadsheet import

Export the project list as CSV (UTF-8, or `--encoding cp1250` for Excel's plain CSV on Polish Windows). Only the
`name` and `size` columns are required; `team`, `product`, `subdomain`, `start`, `ongoing`, `depends_on`,
`id`, `description` and `color` are optional (`product` needs a base file that defines the products). Rename other headers with `--map`, and keep teams and settings in a base
file:

```bash
rt convert projects.pl.csv --base teams.base.yaml \
  --map "Projekt=name,Rozmiar=size,Zespół=team,Start=start,Zależności=depends_on,Ciągły=ongoing,Opis=description" \
  -o roadmap.yaml
```

Without `--base`, rt generates a skeleton (sizes XS–XXL, one team per `team` value) around the projects.

## Development

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q
uv run pytest -q -m slow          # performance tests (RS NF-3, NF-11)
```

Tests: `tests/unit` and `tests/property` (developer), `tests/acceptance`, `tests/cli`, `tests/html`,
`tests/golden` (black-box acceptance suite, one test per AT-01 … AT-74). `tools/reference_plan.py` and
`tools/reference_convert.py` are the differential oracles; `tools/gen_stress.py` generates the stress roadmap.
