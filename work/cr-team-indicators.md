# CR-2: Team composition indicators — draft spec change for review

Status: **implemented (31 Oct 2026, rt 1.2.0), including the second-round changes of section 11**. RS (7.13, OUT-12, OUT-30, OUT-34, PL-8, 11.8), ADS, schema,
oracle and expected plans updated; AT-66 to AT-74 pass. Refinements made while building are listed in
section 10.
Requested on 31 Oct 2026: show, per team, (1) developers per simultaneous project and (2) developers per QA, so
teams can be compared and discrepancies (signs of bad organisation or bad composition) are noticed.

## 1. Summary

Two indicators are computed for every team from data the file already has (`capacity`, `parallel_projects`):

| Indicator | Formula | Reads as |
| --- | --- | --- |
| **DEV per slot** | `capacity.developers` ÷ `parallel_projects` | How many developers stand behind each project the team runs at once |
| **DEV per QA** | `capacity.developers` ÷ `capacity.testers` | How many developers one tester has to keep up with (QA works downstream of development) |

Only developers count in both indicators: they are the upstream of the delivery flow; product managers and
analysts do not enter either ratio. Each team is compared with the other teams of the roadmap (or with
roadmap-wide norms written in the file), and values far from the rest are marked, so an understaffed team, a team
running too many parallel streams for its developers, or a team with too few testers stands out. The indicators
are shown in the team label, in the `--summary` section and in the plan JSON. They never change scheduling and
never produce warnings.

## 2. Calculation (new RS section 7.13 "Team indicators")

- **TI-1 Inputs.** Developers = `capacity.developers`; testers (QA) = `capacity.testers`; slots =
  `parallel_projects` as written. Every slot counts, including slots held by ongoing (run) projects; overflow
  lanes never count (they are not defined capacity).
- **TI-2 DEV per slot** = developers ÷ slots. Not defined (`null`) when the team has no `capacity` mapping.
  Developers = 0 gives 0.0.
- **TI-3 DEV per QA** = developers ÷ testers. Not defined when the team has no `capacity`, or when testers = 0
  (then flag `no_qa` if developers > 0). Developers = 0 with testers > 0 gives 0.0.
- **TI-4 Roadmap values.** "All teams" = summed numerators ÷ summed denominators over the teams where the
  indicator is defined (as OUT-32). The median over the same teams is the comparison baseline.
- **TI-5 Discrepancy.** For each indicator, a team value is marked `low` / `high` when it lies outside its band;
  a value exactly on a bound is not marked:
  - with `team_norms` for that indicator in the file (section 3): below `min` / above `max`;
  - otherwise **more than 50 % from the median**: below median × 0.5 or above median × 1.5, and only when at least 3 teams
    have the indicator defined (with fewer there is nothing meaningful to compare). Computed with exact fractions.
- **TI-6 Rounding.** Plan values: 4 decimals half up (as PL-5). Display: 1 decimal half up (`2.3`, `2.6`).
- **TI-7 Flags** per team, sorted: `devs_per_qa_high`, `devs_per_qa_low`, `devs_per_slot_high`,
  `devs_per_slot_low`, `no_capacity` (no `capacity` mapping), `no_qa` (developers > 0, testers 0).

Worked values for `roadmap.example.yaml` (EX). DEV per slot: median 2.0, band 1.0–3.0. DEV per QA: median 2.75,
band 1.375–4.125 (Cyberbezpieczeństwo has no QA, so it is left out of the median and the All teams value). Karty's
3.0 lies exactly on the edge and is not marked; only `no_qa` remains:

| Team | DEV | QA | Slots | DEV per slot | DEV per QA | Flags |
| --- | --- | --- | --- | --- | --- | --- |
| BLIK i przelewy | 5 | 2 | 2 | 2.5 | 2.5 | — |
| Karty | 6 | 2 | 2 | 3.0 | 3.0 | — |
| Integracje acquirerów | 7 | 3 | 3 | 2.3 | 2.3 | — |
| Panel merchanta | 4 | 1 | 2 | 2.0 | 4.0 | — |
| Aplikacja mobilna | 4 | 2 | 2 | 2.0 | 2.0 | — |
| Utrzymanie i wsparcie | 3 | 1 | 2 | 1.5 | 3.0 | — |
| Cyberbezpieczeństwo | 2 | 0 | 1 | 2.0 | — | `no_qa` |
| **All teams** | 31 | 11 | 14 | 2.2 | 2.6 | |

All teams: DEV per slot 31 ÷ 14 = 2.2143; DEV per QA 29 ÷ 11 = 2.6364 (teams with QA only).
WE: Alpha 2.0 per slot, DEV per QA 4.0; Beta 2.0 and 2.0; only 2 teams, so no `low`/`high` marks.
DE and PE have no `capacity`: every team `no_capacity`, indicators `null`.

## 3. Input format (RS 3): optional `team_norms`

New optional top-level block after `scheduling`; the norms apply to every team of the roadmap. Without it, the
50 % median rule of TI-5 applies.

```yaml
team_norms:                      # optional: the organisation's own targets, for all teams
  devs_per_slot: { min: 2, max: 2.5 }   # each bound optional
  devs_per_qa: { max: 3 }
```

| Field | Rules |
| --- | --- |
| `team_norms.devs_per_slot.min` / `.max` | Optional numbers (integer or decimal), 0 ≤ value ≤ 999, `min` ≤ `max` |
| `team_norms.devs_per_qa.min` / `.max` | Same |

An indicator with a norm uses only the written bounds (a missing bound is not checked); an indicator without a
norm uses the median rule. Existing diagnostics apply: E002 (unknown key, with "did you mean"), E011 (not a
number), E012 (out of range, or `min` > `max`, reported at `max`). No new codes.

## 4. Diagnostics (RS 9)

None. The indicators describe the organisation, not the input file; marks are shown in the HTML and the plan JSON,
never as warnings, so `--strict` runs and EX's single warning (AT-17, AT-43) are unaffected.

## 5. Output

- **Team label (OUT-12).** A new row under "9 people · 2 parallel slots" with two indicator chips: `2.5 DEV/slot`
  and `2.5 DEV/QA`. Undefined values show `–`, or `no QA` for flag `no_qa`. A marked value is a coloured chip with a
  glyph — `▲` high, `▼` low, `!` no QA — never red (red is reserved for over capacity and Today), so the state is
  not shown by colour alone (OUT-26). Each chip's `title` explains it, e.g. `DEV per slot 3.0 — high: above 2.7
  (median 2.0 + 50 %)` or `… above the norm 2.5`. Colours (second round, section 11): higher is worse — `high` and
  `no QA` red; `low` green. Teams with one regular slot (56 px compact label) put the two
  chips on the people line instead of a new row, so team heights and all bar geometry stay unchanged.
- **Summary (`--summary`, RS 7.12).**
  - KPI row (OUT-30): two tiles after People: `DEV per slot 2.2` and `DEV per QA 2.6` (All teams values).
  - New table **Team composition** after the monthly load table: rows grouped by subdomain like OUT-31; columns
    Team · DEV · QA · Slots · DEV per slot · DEV per QA · Notes; marked cells use the chip style above; footer
    rows "All teams" and "Median" (and "Norm" when `team_norms` is given).
- **Hooks (RS 7.10).** `rt-team` gains `data-devs-per-slot`, `data-devs-per-qa` (4 decimals or empty) and
  `data-indicator-flags` (space-separated, alphabetical). Chips: `rt-indicator` with `data-indicator`
  (`devs_per_slot` | `devs_per_qa`) and `data-mark` (`low` | `high` | `no_qa` | empty). Summary table:
  `rt-composition`; rows `rt-composition-row` with `data-team`.
- **Plan JSON (RS 8).**
  - each `teams[]` item gains, after `utilization`: `"developers"`, `"testers"` (integers, `null` without
    `capacity`), `"devs_per_slot"`, `"devs_per_qa"` (numbers or `null`), `"indicator_flags"` (sorted list);
  - a top-level `"team_indicators"` object right after `"teams"`:
    `{ "devs_per_slot": { "all", "median", "low", "high", "source" }, "devs_per_qa": { … } }`, where `low` /
    `high` are the band limits (or `null` for a missing bound) and `source` is `"norm"`, `"median"` or `null`
    (fewer than 3 teams and no norm).
- **Unchanged:** scheduling, colours, warnings, `rt convert` (skeleton teams have no capacity → `no_capacity`).

## 6. New acceptance tests (RS 11.8)

| ID | Given / When | Then |
| --- | --- | --- |
| AT-66 | `rt render EX --plan p.json` | Every team's `developers`, `testers`, `devs_per_slot`, `devs_per_qa` equal the table in section 2; only Cyberbezpieczeństwo flagged (`no_qa`, `devs_per_qa` null) |
| AT-67 | Same run | `team_indicators.devs_per_slot`: all 2.2143, median 2.0, low 1.0, high 3.0, source `median`; `devs_per_qa`: all 2.6364, median 2.75, low 1.375, high 4.125, source `median` |
| AT-68 | Same run, HTML | Each `rt-team` carries the `data-*` hooks equal to the plan; with the AT-70 norms Karty shows a red `▲` chip `3.0 DEV/slot` and Utrzymanie i wsparcie a green `▼` one; Cyberbezpieczeństwo shows `no QA`; one-slot teams keep their height (`rt-team` heights equal those of rt 1.1.0) |
| AT-69 | WE and DE | WE: Alpha 2.0 / 4.0, Beta 2.0 / 2.0, no marks, source `null` for both. DE: all `no_capacity`, values null. Schedules and colours equal the expected files apart from the new fields |
| AT-70 | EX with `team_norms: { devs_per_slot: { min: 2, max: 2.5 }, devs_per_qa: { max: 3 } }` | Karty `devs_per_slot_high`, Utrzymanie i wsparcie `devs_per_slot_low`, Panel merchanta `devs_per_qa_high`; values on a bound (BLIK 2.5, Karty 3.0 DEV/QA) not marked; source `norm` for both |
| AT-71 | `team_norms` with `min: 5, max: 2`, `min: "two"` and the key `devs_per_slots` | Exit 1; E012 at the `max`, E011, E002 with "did you mean" |
| AT-72 | `rt render EX --summary` | KPI tiles `DEV per slot 2.2` and `DEV per QA 2.6`; one `rt-composition` table, 7 team rows plus All teams and Median, in subdomain and team order |
| AT-73 | `rt render EX --strict` and `rt validate EX` | Same diagnostics as before the change (no new warnings) |
| AT-74 | `rt schema` | Accepts `team_norms`; still validates every fixture |

## 7. Design (ADS)

| Area | Change |
| --- | --- |
| `model.types` / `fields` / `build` | `Band(min, max)` with `Fraction` bounds, `TeamNorms(devs_per_slot: Band \| None, devs_per_qa: Band \| None)`; `Model.team_norms`; parse and check `team_norms` (E002, E011, E012) |
| new `schedule.indicators` (pure) | `team_indicators(m) -> (dict[team_id, TeamIndicators], RoadmapIndicators)`: exact `Fraction`s, median, 50 % median band or norms, flags (TI-1 … TI-7) |
| `plan.types` / `build` | `TeamPlan.developers`, `testers`, `devs_per_slot`, `devs_per_qa`, `indicator_flags`; `Plan.team_indicators` (after `teams`); `ratio4` rounding |
| `layout.viewmodel` | `TeamVM.indicators` (chips: text, mark, glyph, title); compact teams merge chips into the people line; `SummaryVM` KPI tiles and `CompositionVM` table |
| `render` | `_section.html.j2` chip row, `_summary.html.j2` composition table; CSS for `rt-indicator` (red bad / green good states, light and dark tokens); stay within the 15 KB CSS budget |
| schema | `team_norms` in `roadmap.schema.json` |
| oracle | `reference_plan.py` computes the new plan fields, so golden and differential tests cover them |

## 8. Changes to human-owned files: need your permission

1. `docs/requirements.md`, `docs/architecture.md`: sections 3.2, 7.5 (OUT-12), 7.10, 7.12, new 7.13, 8, 11.8, 13.2.
2. `docs/fixtures/*.expected.json` (WE, DE, PE): the new team fields and `team_indicators`; nothing else changes.
3. `docs/fixtures/roadmap.schema.json`: `team_norms`.
4. `docs/reference/reference_plan.py`: the indicators.
5. Optional: a commented-out `team_norms` example in `roadmap.example.yaml` (kept commented, so EX stays on the
   median rule and AT-66/AT-67 hold).

## 9. Decisions (owner, 31 Oct 2026)

| # | Question | Decision |
| --- | --- | --- |
| Q1 | Who counts as a team member in indicator 1? | Developers only: they are upstream of QA; product managers and analysts are not counted. Indicator 1 is therefore DEV per slot |
| Q2 | Discrepancy band without norms | ±33 % of the median at first; changed in the second round to **more than 50 %** (below median × 0.5, above median × 1.5), from 3 teams up |
| Q6 | Colours (second round) | For both indicators higher is worse: high → red, low → green; `no QA` red (the extreme of a high DEV per QA) |
| Q3 | Should a marked team produce a warning? | No |
| Q4 | Norms: roadmap-wide or per team? | Roadmap-wide `team_norms` block |
| Q5 | Do slots held by ongoing (run) projects count? | Yes: every slot of `parallel_projects` counts, ongoing work included |

## 10. Implementation notes (31 Oct 2026)

| # | Topic | What was built | Why |
| --- | --- | --- | --- |
| N1 | One-slot team labels | Chips on the people line in short form (`2.0/slot`, `2.0/QA`, `no QA`); if they still do not fit, the people text is cut with an ellipsis, never the chips | Measured in Chromium: the 56 px label has about 90 px free next to "3 people · 1 parallel slot"; the full chip texts need 140 px |
| N2 | Composition table cells | Plain numbers; only marked values are chips | Easier to scan; marks stand out |
| N3 | Band row | "Normal range" (median ± 50 %) or "Norm" (`team_norms`), with ≥ / ≤ for one-sided norms | Shows the reader what was compared |
| N4 | CSS budget | The stylesheet compactor also drops the space after `:` (commas keep theirs, so the RS OUT-3 font stack stays verbatim) | The new rules pushed the stylesheet over the 15 KB ADS target; now 15.2 KB with ~100 bytes spare |
| N5 | Key order | Plan JSON: `teams`, `team_indicators`, `products`, … (CR-1's "products after teams" now reads "after team_indicators") | PL-8 places `team_indicators` right after `teams` |
| N6 | `roadmap.example.yaml` | A commented-out `team_norms` example after `scheduling`; EX stays on the median rule. Its single W001 moved from line 252 to 259 (AT-19, AT-20, AT-73 updated) | CR section 8 item 5 |
| N7 | AT-68 | Asserts that one-slot teams have no extra chip row (the chips are on the people line) instead of comparing block heights with rt 1.1.0 | Heights are not in the HTML; the absence of the row is what keeps them unchanged |
| N8 | Oracle | `reference_plan.py` computes the indicators; the differential property test now generates capacities and `team_norms` (W008, which the oracle does not model, is masked) | Golden and differential coverage of the new fields |

## 11. Second round (owner, 31 Oct 2026)

| # | Request | Built |
| --- | --- | --- |
| R1 | Change the colour only when the difference is more than 50 % | Median band median × 0.5 … × 1.5 (was × 0.67 … × 1.33); a value on the edge is not marked. On EX only `no_qa` remains (Karty's 3.0 is exactly median 2.0 + 50 %) |
| R2 | DEV per slot: more is worse (red), less is better (green) | `high` → red chip `▲` (`rt-indicator--bad`, `data-tone="bad"`), `low` → green chip `▼` (`rt-indicator--good`, `data-tone="good"`); tooltips say "high (worse)" / "low (better)" |
| R3 | DEV per QA: less is better (green), more is worse (red) | Same colours; `no QA` is red too, as the extreme of a high DEV per QA |

Light: worse `#FEE2E2` / `#B91C1C`, better `#DCFCE7` / `#166534`; dark: `#450A0A` / `#FCA5A5`, `#052E16` / `#86EFAC`
(text contrast ≥ 5.3:1). The glyphs keep the state readable without colour. The expected plan files did not change
(their teams have no capacity or fewer than 3 comparable teams).
