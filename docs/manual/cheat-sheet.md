# rt cheat sheet (rt 1.2)

YAML in → one offline HTML roadmap out. Full guide: [user-manual.md](user-manual.md).

## Commands

```bash
rt init [--minimal]                       # write a commented roadmap.yaml
rt render roadmap.yaml [--summary]        # → roadmap.html (add KPIs, monthly load, team composition)
rt validate roadmap.yaml [--strict]       # check only; warnings fail with --strict
rt convert projects.csv --base teams.yaml [--map "Projekt=name,Rozmiar=size"] -o roadmap.yaml
rt schema -o roadmap.schema.json          # then first line: # yaml-language-server: $schema=./roadmap.schema.json
```

Override per run: `--from 2027-04 --to 2027-06` · `--today 2027-03-01` · `--on-conflict delay|overflow|error` ·
`--plan plan.json` · `-q`. Pipe: `rt convert x.csv --base b.yaml | rt render -o out.html`.

## The file

```yaml
version: 1
roadmap:
  title: Payments Roadmap 2027          # only required field here
  horizon: { start: 2027-01, end: 2027-12 }   # optional; start = anchor for projects without start
  today: 2027-02-15                     # optional; fixes Today line → reproducible output
sizes: { S: 2, M: 4, L: 8 }             # label → WEEKS (7 calendar days, no holidays)
team_norms: { devs_per_qa: { max: 4 } } # optional targets for team indicators
subdomains:                             # domains = page sections, in file order
  - id: channels                        # ids: lowercase, digits, - _
    name: Payment Channels
    teams:
      - id: blik                        # team ids unique across the file
        name: BLIK Squad
        parallel_projects: 2            # slots = projects at once (the ONLY scheduling limit)
        capacity: { developers: 5, product_managers: 1, analysts: 1, testers: 2 }   # display only
products:                               # optional: one colour per product, shown in legend
  - { id: blik, name: BLIK, domain: channels, owner: Anna Kowalska }
projects:                               # ORDER = PRIORITY
  - id: blik-recurring                  # optional handle for depends_on
    name: Recurring BLIK payments
    team: blik                          # team id (one team per project)
    product: blik                       # optional
    size: L                             # OR  ongoing: true  (never both)
    start: 2027-01                      # optional; omit = first free slot
    depends_on: [other-id]              # ids or unique names, written ABOVE; finish-to-start
    color: sky                          # optional pin (palette name or "#RRGGBB"); wins over product
```

## How scheduling works

- Top to bottom, each project goes to the **lowest free slot** at the **earliest date**; later ones may backfill gaps.
- `start: 2027-03` = requested 1 Mar; if busy → starts later, **W001 delayed**. No `start` = whenever free, never delayed.
- `ongoing: true` holds a slot forever from its start. All slots ongoing → **E060**.
- `scheduling: { on_conflict: delay }` waits · `overflow` adds red `+1` lanes (W011) · `error` stops with E061.

## Reading the page

`+4w` + dashed line = delayed from requested start · stripes + `∞` = ongoing · arrow = dependency (same domain) ·
`↤` = dependency in another domain · `‹ ›` = cut at horizon · red dashed / hatched `+1` lane = over capacity ·
red line = Today · dotted line = quarter.
Team indicators: **DEV/slot** = devs ÷ slots, **DEV/QA** = devs ÷ testers; higher is worse: red `▲` above normal,
green `▼` below, red `! no QA`. Normal = `team_norms`, else median ±50 % (needs ≥ 3 teams).

## CSV import

Columns `name`, `size` (required), `team`, `product`, `start` (`2027-03`/`01.03.2027`), `ongoing` (yes/tak/x), `depends_on`
(`a|b`), `id`, `description`, `color`; others ignored (W020). Excel "CSV UTF-8" or `--encoding cp1250`.

## Pitfalls and diagnostics

`name: Fix #12` → "Fix" (` #` = comment) → quote it · `name: Phase 2: rollout` → E001 → quote it ·
`color: "#FFD6A5"` needs quotes · spaces, never tabs · Polish letters and `no`/`yes` are fine.

**E002** typo in a key (see "did you mean") · **E030** use the team *id* · **E031** size labels are case-sensitive ·
**E032** `size` *or* `ongoing` · **E034/E035/E037** dependency unknown, ambiguous or below → use an `id`, move it
above · **E060** all slots ongoing · **W001** delayed. Exit: **0** ok · **1** errors · **2** usage · **3** E060/E061 · **4** I/O.
