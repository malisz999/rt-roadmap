# Decisions for the spec owner

The tool implements the requirements spec (RS) and the architecture spec (ADS) as written. Where they are silent,
ambiguous, or disagree with the reference oracles, the build made the choices below. Each one is implemented and
covered by tests. Please confirm or overrule; a change of mind is usually a one-line code change plus a test.
Tester questions with more detail: `work/questions.md` (Q-1 … Q-7).

## Spec questions answered by the owner (24 Oct 2026)

| ID | Question | Answer |
| --- | --- | --- |
| RS 12.3 / A1 | Can one team work for more than one subdomain? | Not needed: a subdomain is only an extra description of the team. The team's key parameter is how many projects it runs at once (`parallel_projects`), drawn as separate lanes. The model keeps one subdomain per team. |
| RS 12.3 | Dependency lag or start-to-start links? | No: finish-to-start only, as in version 1. |
| ADS 13.2 | PyPI name | Keep `rt-roadmap` (PyPI publishing stays commented out in `release.yml` until first release). |

## Interpretations where the RS is silent or ambiguous

| # | Topic | Decision | Why |
| --- | --- | --- | --- |
| 1 | W008 for a team without `capacity` (Q-1) | Only when `capacity` is written and sums to 0 | Otherwise `dependencies-example.expected.json` (AT-26) would need W008 entries it does not have |
| 2 | Custom hex accent "darkened by 35 %" (Q-4) | Relative: HSL lightness × 0.65 | Works for every input; absolute −35 points clamps any colour with lightness ≤ 35 % to pure black |
| 3 | AT-36 project name (Q-2) | Fixture spelling with the en dash | The fixture is the data under test |
| 4 | Positions of E010 / E032 (Q-3) | First key of the project mapping | Same rule as other project-level diagnostics |
| 5 | `-o /dev/null`, FIFOs (Q-5) | Written directly; the temp-file-and-rename rule (CLI-3) applies to regular files | A rename cannot replace a device |
| 6 | `rt init` content (Q-7) | Writes the bundled `roadmap.example.yaml` / `roadmap.minimal.yaml` unchanged | RS 13.2 names them as the source |
| 7 | W005, W008 / W006 / W010, W012 positions | Team / subdomain / `roadmap` key | The location rule names no node for them |
| 8 | Monthly load for a subdomain without teams | Listed with 0.0 every month | PL-6 says "per-subdomain arrays"; the oracle omits it (no fixture has one) |
| 9 | Only `horizon.end` explicit and the automatic start falls after it | Start = end month; over 120 months: start moved back, W012 | Not covered by SC-9 |
| 10 | Extra usage errors (exit 2) | `--append` without `--base`; an output or `--plan` path equal to the input; `-o` and `--plan` naming the same file | Protects the input file (NF-10) and avoids silent overwrites |
| 11 | Delay pill on narrow bars | Shown only when the bar is ≥ 80 px; the dashed lead line always shows | Keeps names readable; OUT-20 does not fix a width |

## `rt convert`: where the RS and `reference_convert.py` differ (the RS was followed)

1. A name that slugs to `x` keeps `x`; the oracle replaces it with `team`/`subdomain`. CV-15 falls back only for an empty result.
2. Impossible dates (`2027-02-30`, `31.04.2027`) are E013; the oracle accepts them.
3. A CSV with a header and no rows (skeleton mode) still gets the default subdomain and team, so the output validates; the oracle writes `subdomains: []`, which fails E043.
4. `--append` extends the base's project list in place, so comments on base projects survive (CV-13 "comments kept").
5. E030 for an unknown CSV team suggests case-insensitively over team ids and names (`Apka` → `app`), as AT-51(b) asks for a suggestion.

None of these affect the expected fixture files, which match the oracle byte for byte.

## Where the HTML differs in detail from the ADS (the RS 7.10 contract is kept in full)

The page follows the ADS 7.1 skeleton class names, the ADS 7.2 bar-state modifier classes and the `.rt-tip`
tooltip child. Remaining details, all within the ADS's intent:

1. The marks layer has no explicit `z-index: 0` (lane tints are translucent instead), so grid lines show through
   lane backgrounds; the Today line is z 1 and connectors z 2 as ADS 7.2 orders them.
2. The subdomain title sits in a sticky `rt-subdomain__intro` wrapper with its counts and description.
3. The `∞` and `↤` glyphs come from CSS `content`.
4. Additions: `rt-bar--tip-end` (tooltip anchored right near the timeline end), `role="img"` on bars (so
   `aria-label` applies), and `rt-summary__*` / `rt-kpi*` / `rt-load__row--*` classes in the summary.
5. Sizes: CSS 14.1 KB (target ≤ 15 KB); about 1.06–1.10 KB of HTML per bar (ADS estimate ~1.2 KB);
   500-project stress page with `--summary` 1.43 MB in about 0.4 s (RS NF-3: < 2 MB, < 2 s).
6. Diagnostics `Code` values are `(code, template)` pairs, so codes sharing a template stay distinct.
