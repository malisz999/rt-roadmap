# rt input format (version 1) — working reference

Source of truth: `docs/requirements.md` sections 3, 5 and 9 (in the rt repository). `rt schema` prints the JSON
Schema; `rt init -` prints a fully commented example. This page is the subset you need to write files that
validate on the first try.

## Skeleton

```yaml
# yaml-language-server: $schema=./roadmap.schema.json
version: 1                          # required, must be 1

roadmap:                            # required
  title: Roadmap płatności 2027     # 1–120 chars
  subtitle: Delivery plan           # optional, ≤ 200
  horizon: { start: 2027-01, end: 2027-12 }   # optional; omitted parts are automatic (≤ 120 months)
  today: 2027-01-15                 # optional; set it so output is reproducible
  month_width: 120                  # optional px per month, 60–400
  content_language: pl              # optional BCP 47 tag of names/descriptions

sizes:                              # required, ≥ 1; label -> whole weeks (1–520); order = legend order
  S: 2
  M: 4
  L: 8

scheduling:                         # optional
  on_conflict: delay                # delay (default) | overflow | error
  adjacency_gap_days: 14            # 0–90, colouring only

team_norms:                         # optional (rt 1.2+): roadmap-wide targets for the team indicators
  devs_per_slot: { min: 2, max: 3 } # numbers 0–999, either bound optional, min ≤ max
  devs_per_qa: { max: 4 }           # without an entry: marked when > 50 % from the median (3+ teams)

subdomains:                         # required, ≥ 1; drawn in file order. A subdomain = a "domain"
  - id: channels                    # ^[a-z0-9][a-z0-9_-]{0,39}$, unique among subdomains
    name: Kanały płatności          # 1–80
    description: Metody płatności   # optional, ≤ 300
    teams:                          # ≥ 1 (empty list = W006)
      - id: blik                    # same pattern, unique across ALL teams
        name: BLIK i przelewy       # 1–60
        parallel_projects: 2        # 1–12 slots = projects at the same time
        capacity: { developers: 5, product_managers: 1, analysts: 1, testers: 2 }   # display only, 0–999

products:                           # optional; legend order = file order
  - id: blik                        # same pattern, unique among products (own namespace)
    name: BLIK                      # 1–100, unique among products
    domain: channels                # required: a subdomain id = the owning domain
    owner: Anna Kowalska            # optional, ≤ 100
    description: Płatności BLIK     # optional, ≤ 500
    color: indigo-deep              # optional palette name or #RRGGBB

projects:                           # required (may be [] = W010); FILE ORDER = SCHEDULING PRIORITY
  - id: blik-recurring              # optional handle for depends_on, unique
    name: Płatności cykliczne BLIK  # 1–100, unique within its team
    team: blik                      # required, a team id (exactly one team per project)
    product: blik                   # optional product id; team may be in any subdomain
    start: 2027-01                  # optional requested start month; omit = auto-start (first free slot)
    size: L                         # a key of sizes ... 
    # ongoing: true                 # ... OR ongoing: true (exactly one of the two)
    depends_on: [other-id]          # optional ids or unique names; must be ABOVE this project; not ongoing
    description: Subskrypcje        # optional, ≤ 500, tooltip
    color: sky                      # optional pin; wins over the product colour
```

## Rules that most often bite

- **Order is priority.** rt places projects top to bottom, each into the lowest free slot at its earliest date;
  later projects may backfill gaps. Put what matters most first. A dependency must appear earlier in the file.
- **One team per project.** Work shared by two teams = two projects (same `product`, often linked with
  `depends_on`).
- **Sizes are whole weeks** (7 calendar days); no holidays. Durations: `weeks × 7` days.
- **Ongoing** projects (`ongoing: true`, no `size`) hold a slot forever from their start. A team whose every slot
  is held by ongoing work cannot schedule anything else (E060).
- **Delay** happens only to projects with a `start`; auto-start projects simply start when possible.
- Months `YYYY-MM`, dates `YYYY-MM-DD`; quotes optional. YAML 1.2: `no`, `yes`, `on` stay strings.
- Unknown keys are errors (E002) with a "did you mean". Polish text is fine everywhere (UTF-8).
- `capacity` is shown, never used for scheduling. Only `parallel_projects` limits throughput. Give every team a
  `capacity` with at least `developers` and `testers` if the user wants team indicators; teams without it are
  `no_capacity` and left out of the comparison.
- Palette names: `indigo green orange pink sky amber violet teal lime sand` (0–9, standalone bars) and
  `blue cyan emerald yellow fuchsia purple stone sand-deep indigo-deep green-deep orange-deep pink-deep sky-deep
  amber-deep violet-deep teal-deep lime-deep blue-deep cyan-deep emerald-deep fuchsia-deep purple-deep` (10–31,
  used first for products). Red is reserved. Usually leave colours automatic.

## Diagnostics cheat sheet

Format: `file:line:col: error|warning CODE: message`. Exit 0 ok (warnings allowed), 1 validation errors,
2 usage, 3 scheduling (E060/E061), 4 I/O.

| Code | Meaning | Typical fix |
| --- | --- | --- |
| E002 | Unknown key | Use the suggested key |
| E010 / E011 / E012 / E013 | Missing field / wrong type / out of range or bad id / bad month or date | Fix the value |
| E020 / E021 / E022 / E023 | Duplicate subdomain id / team id / project name in a team / project id | Rename |
| E024 / E025 | Duplicate product id / name | Rename |
| E030 / E031 | Unknown team / size | Use an existing id or label |
| E032 | Not exactly one of `size` / `ongoing: true` | Keep one |
| E033 | Bad colour | Palette name or `#RRGGBB` |
| E034–E037 | Unknown, ambiguous, ongoing, self or later dependency | Use ids; move the dependency above |
| E038 / E039 | Unknown product / product domain not a subdomain | Fix the id |
| E040–E043 | Horizon end < start / > 120 months / empty sizes / empty subdomains | — |
| E060 | Every slot of the team is held by ongoing projects | More slots, or end the ongoing work |
| E061 | Conflict in `error` mode | Use `delay`, or re-plan |
| W001 | Project starts later than requested (reason: dependency, capacity, both) | Re-allocate, reorder, or move the start |
| W002–W004 | Clipped left / right / outside horizon | Widen the horizon if it matters |
| W005 / W006 / W008 | Team without projects / subdomain without teams / capacity sums to 0 | Informational |
| W007 / W009 | Colours exhausted / two adjacent pre-coloured bars share a colour | Drop pins |
| W010 | No projects | — |
| W011 | Overflow lane used (`overflow` mode) | More slots or re-allocate |
| W012 | Automatic horizon capped at 120 months | Set the horizon |
| W013 / W014 | Product without projects / more than 32 products share colours | Informational |

## Team indicators (rt 1.2+)

Computed per team, shown as chips under the team name, in `--summary` ("Team composition" table and two KPI
tiles) and in the plan JSON (`teams[].devs_per_slot`, `devs_per_qa`, `indicator_flags`; top-level
`team_indicators` with `all`, `median`, `low`, `high`, `source`).

| Indicator | Formula | Notes |
| --- | --- | --- |
| DEV per slot | `developers ÷ parallel_projects` | Every slot counts, ongoing work included; overflow lanes do not. Product managers and analysts never count |
| DEV per QA | `developers ÷ testers` | Not defined with 0 testers (flag `no_qa` when there are developers) |

Marks (`indicator_flags`): `devs_per_slot_low/high`, `devs_per_qa_low/high` — strictly outside the band
(`team_norms`, else median × 0.5 … × 1.5, i.e. more than 50 % away, when ≥ 3 teams have a value); `no_qa`;
`no_capacity`. Marks are never warnings, so `--strict` is unaffected. For both indicators **higher is worse**: `high`
is a red ▲ chip, `no_qa` a red `!` chip, `low` a green ▼ chip (better). Reading them (the owner's view): DEV per slot
high = too many people per parallel stream for the team (oversized team or too few streams); DEV per QA high =
testing is the bottleneck, and no QA is its extreme; low values on either are the healthier side.

## CSV import

`rt convert projects.csv --base teams.yaml [--map "Projekt=name,Rozmiar=size,Zespół=team,Produkt=product"]`
turns a spreadsheet export into the `projects` list of a base file that holds settings, sizes, subdomains,
teams and products. Columns: `name`, `size` (required), `team`, `product`, `subdomain`, `start`, `ongoing`,
`depends_on` (`|`-separated), `id`, `description`, `color`. Without `--base` it generates a skeleton (the
`product` column is then ignored, W020). Pipe straight on: `rt convert x.csv --base b.yaml | rt render -o x.html`.
