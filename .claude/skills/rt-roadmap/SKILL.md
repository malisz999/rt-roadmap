---
name: rt-roadmap
description: Build, edit and render delivery roadmaps with the rt roadmap tool. Use when the user wants to plan projects across teams, domains (subdomains) and products; turn a list of initiatives, a spreadsheet or meeting notes into an rt YAML input file; decide which team should take which project (allocate work to teams optimally, balance load, reduce delays); compare team composition (developers per parallel project, developers per QA) and spot badly composed teams; or produce, validate or explain the roadmap HTML page. Also use for questions about rt input fields, its diagnostics (E0xx/W0xx) or `rt render` / `rt validate` / `rt convert`.
---

# rt roadmap: prepare input, allocate work, render

rt reads one YAML file (domains = `subdomains`, `teams`, `products`, t-shirt `sizes`, `projects`), schedules each
project into its team's parallel slots, and writes one self-contained HTML page. Your job: turn what the user
knows into a valid file, choose good team assignments, run rt, and explain the result.

Read when needed:
- `references/input-format.md` — every field, rule and diagnostic code (read before writing a file).
- `references/allocation.md` — how to allocate projects to teams and what "optimal" means here (read before
  assigning or re-assigning teams).

Paths below are relative to this skill's folder (`.claude/skills/rt-roadmap/` in the rt repository).

## 0. Find rt

Use the first that works and remember it as `RT` for the session:
`rt --version` (installed; needs 1.1.0+ for products, 1.2.0+ for team indicators) · `uv run rt --version` (inside the rt repository) ·
`python3 -m rt --version` · a release binary `rt-<version>-<os>-<arch>`.
If none works and this skill has a `wheels/` folder (the exported version does), install it:
`pip install wheels/rt_roadmap-*.whl` (add `--break-system-packages` if pip refuses; it pulls ruamel.yaml and
Jinja2 from PyPI). Then use `rt`, or `python3 -m rt` if `rt` is not on PATH. Otherwise tell the user how to
install (`uv tool install <path to the rt repo>`).

Without `uv`, run the scripts with plain `python3` after `pip install ruamel.yaml` (allocate.py needs it;
plan_summary.py needs nothing). Save outputs the user should get (HTML, YAML) where they can download them.

## 1. Understand the entities

| User says | rt entity | Key facts |
| --- | --- | --- |
| domain, area, tribe, business line | `subdomains[]` | Section of the page; owns teams and products |
| team, squad | `subdomains[].teams[]` | `parallel_projects` = projects at once (the only capacity rt schedules by); `capacity` head counts are shown and feed the team indicators, never the schedule |
| team composition, staffing ratio | team indicators (computed) | DEV per slot = developers ÷ `parallel_projects`; DEV per QA = developers ÷ testers; more than 50 % above the median (3+ teams) or above `team_norms` = red ▲ (worse), more than 50 % below = green ▼ (better); red `no QA` when developers have no tester |
| team norms, targets | `team_norms` | Optional roadmap-wide `{ min, max }` per indicator; replaces the median rule |
| product | `products[]` | Owned by one domain (`domain:`); its projects may run in any team; all its bars share one colour |
| project, initiative, epic | `projects[]` | Exactly one team; `size` (weeks via `sizes`) or `ongoing: true`; optional `start`, `depends_on`, `product` |
| T-shirt size | `sizes` | Label → whole weeks |
| priority | order of `projects[]` | Earlier = scheduled first |

Ownership: a product project is owned by the product's domain even when another domain's team builds it; the
bar is drawn in the building team's section, and the legend and tooltip show the owner.

## 2. Workflow

1. **Gather** what is missing; ask only for what you cannot sensibly default. Minimum: teams (with slots) per
   domain, projects with size and team or candidate teams. Useful: products and their owning domains, owners,
   fixed dates, dependencies, priorities, horizon, `today`. Defaults if unstated: sizes `XS 1, S 2, M 4, L 8,
   XL 13, XXL 26`; `parallel_projects: 1`; `on_conflict: delay`; auto horizon; `content_language` matching the
   names. State every assumption you made.
2. **Draft** the YAML (see the skeleton in `references/input-format.md`; `RT init -` prints a commented
   example). Keep the user's own names (Polish is fine); derive ids as lower-case slugs. Put dependencies above
   their dependants. From a spreadsheet, prefer `RT convert file.csv --base base.yaml --map "..."`.
3. **Validate**: `RT validate roadmap.yaml`. Fix every error (the message names the line, column and usually a
   "did you mean"); repeat until exit code 0. Warnings may stay but explain them.
4. **Allocate** when the user asked for an assignment or the plan shows delays/imbalance: follow
   `references/allocation.md`. Inspect with
   `RT validate roadmap.yaml --plan - -q | python3 scripts/plan_summary.py`, then optimise with
   `uv run --with ruamel.yaml python scripts/allocate.py roadmap.yaml candidates.yaml -o roadmap.allocated.yaml`.
   Show the before/after numbers and justify each move; let the user accept before overwriting their file.
5. **Render**: `RT render roadmap.yaml -o roadmap.html` (add `--summary` for KPIs and the monthly load heatmap,
   `--plan plan.json` for the machine-readable schedule). Set `roadmap.today` or pass `--today` so the result is
   reproducible.
6. **Report** briefly: where the HTML is; horizon; delayed projects with reasons; team utilisation and the
   busiest months; products and when each is done; team composition marks (which teams are red ▲ / worse or green ▼ / better on DEV
   per slot or DEV per QA, which have no QA, which lack `capacity`) with what they suggest; remaining warnings; the
   assumptions you made. `scripts/plan_summary.py` prints all of these from the plan.

## 3. Guardrails

- Never edit a user's roadmap in place without saying so; write to a new file or show the diff first.
- Do not change project order, sizes, fixed `start` months or dependencies to make the numbers look better
  unless the user agrees: they are business decisions. Team choices among the user's candidates are yours to
  optimise.
- One project = one team. Split shared work into several projects linked by `product` and `depends_on`.
- Raising `parallel_projects` means adding people; propose it, do not do it silently. It also lowers that
  team's DEV per slot, so check the indicator afterwards.
- Team indicators are signals for a conversation, not errors: never "fix" a marked team by editing its
  `capacity` or `parallel_projects` without the user; explain the mark and the options instead. Add
  `team_norms` only when the user gives targets.
- Exit code 3 (E060/E061) is a scheduling impossibility, not a syntax error: explain which team is blocked.
- `rt` never needs network access; all output is local files.
