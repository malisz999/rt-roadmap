# Allocating projects to teams

rt does not choose teams: every project names one. rt then schedules deterministically (file order, lowest free
slot, finish-to-start dependencies). "Optimal allocation" therefore means choosing `team` for each project, and
the project order, so that rt's schedule is as good as possible for the stated goals.

## 1. Collect constraints before optimising

Ask for, or infer and state, these. Never invent hard constraints silently.

| Kind | Examples | How it enters the file / optimiser |
| --- | --- | --- |
| Hard: who can do it | "Only Cards can touch the card vault"; skills; system ownership | Candidate list per project (`candidates.yaml`) |
| Hard: fixed dates | Regulatory deadline, contract start | `start:` (requested month); check its delay is 0 |
| Hard: order | "Routing needs both acquirers first" | `depends_on` (predecessor written above) |
| Capacity | 2 squads in team X | `parallel_projects`; split big teams only if they really run parallel streams |
| Preference: ownership | Product owned by domain D | Prefer teams in D (optimiser `--w-affinity`) |
| Preference: stability | Keep teams on their current work | `--w-move` (penalty per moved project) |
| Priority | "BLIK first" | Order in `projects[]` — higher = earlier |

Role head counts (`capacity`) do not limit rt's scheduler, but use them to judge feasibility: a team with no
testers is a poor candidate for test-heavy work; say so rather than encode it silently. rt's team indicators make
this visible (see `input-format.md`). For both indicators higher is worse (red ▲), lower is better (green ▼):
- red ▲ DEV per QA or red `no QA`: testing is the bottleneck. Do not pile extra work onto such a team when another
  candidate is equal; if you must, say that its delivery will likely queue in testing.
- red ▲ DEV per slot: the team has more developers per parallel stream than its peers. rt still schedules it like
  any other, so do not change its allocation for this; raise it as a composition question (more streams, i.e. a
  higher `parallel_projects`, or moving people to another team) and let the user decide.
- green ▼ marks need no action; mention them as the healthy end of the comparison.
Never change `capacity` or `parallel_projects` to clear a mark without the user's agreement.

## 2. Objective

Default, in order of importance (the optimiser's weighted sum mirrors it):

1. Feasible: no E060/E061, no overflow lanes (`over_capacity`).
2. Requested starts kept: minimise total `delay_days` (only projects with `start` can be delayed).
3. Work done early: minimise the sum of finish days (`end`), which also pulls auto-start projects forward and
   evens out load, then the last finish day (makespan).
4. Products stay in their owning domain where possible; fewer moves away from the current team.

If the user states another goal (e.g. "finish product BLIK by June", "keep team X under 80 %"), make it explicit:
add a `start` or `depends_on`, restrict candidates, or adjust weights, and check the result in the plan.

## 3. Method

1. Write a valid file with a reasonable first assignment: each project in its natural team (the team that owns
   the system), product projects in their domain. Run `rt validate f.yaml --plan - -q | python
   scripts/plan_summary.py` to see delays, utilisation, busiest months.
2. Write `candidates.yaml` only for projects that may move, best team first:

   ```yaml
   blik-recurring: [blik, app]          # id or exact name -> allowed team ids
   "Raporty i eksporty v2": [panel, app]
   "Baza wiedzy wsparcia": "*"          # any team
   ```

3. Run the optimiser (it calls rt for every evaluation, so its score is exactly rt's schedule):

   ```bash
   uv run --with ruamel.yaml python .claude/skills/rt-roadmap/scripts/allocate.py \
       roadmap.yaml candidates.yaml -o roadmap.allocated.yaml [--w-move 15] [--w-affinity 10]
   ```

   It does a greedy pass in file order, then local search (single moves and pairwise swaps) until no
   improvement, and never returns something worse than the input. Only `team` values change; everything else
   in the file stays byte-identical. Weights (per day unless noted): `--w-delay 1`, `--w-flow 0.2`,
   `--w-makespan 0.5`, `--w-affinity 10` per off-domain product project, `--w-move 0` per moved project;
   overflow costs 1000 per project. `--max-evals` caps rt runs (default 600; about 0.15 s each).
4. Re-run the summary on the result, diff the two files, and explain every move in plain words ("A4 moves from
   Alpha to Gamma: Alpha had both slots busy until March; Gamma was idle").
5. If delays remain, look at their reason in the plan:
   - `capacity` → more candidate teams, more `parallel_projects` (ask first: it means more people), or move a
     lower-priority project down the list.
   - `dependency` → only the predecessor's finish can help: give the predecessor a freer team, raise it in the
     order, or split it so the dependent part can start earlier.
   - both → handle the dependency first.

## 4. Ordering

The order of `projects[]` is the business priority, so do not reorder silently. When the user allows it, a good
default is: fixed-date projects first, then projects on the critical path of dependency chains, then larger
projects before smaller ones within a team (smaller ones backfill the gaps). Re-run the summary after any
reorder; backfill makes order effects non-obvious.

## 5. Modelling patterns

- **Work spanning teams**: one project per team, same `product`, `depends_on` where one waits for the other.
- **Phased work**: split into projects (e.g. "pilot" M, "rollout" L) linked by `depends_on`.
- **Run / BAU work**: `ongoing: true` with a `start`; it permanently takes one slot, so a 2-slot team with one
  ongoing project has 1 slot for change work.
- **Unknown start**: omit `start`; rt starts it when its dependencies are done and a slot is free, from the
  anchor (horizon start, else the month of `today`).
- **"Domain" in user language** usually means a subdomain; **"product"** is a product; **"initiative" / "epic"**
  is usually a project; **"squad" / "tribe"** is a team / subdomain.
