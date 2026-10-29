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

## CR-1 Products (implemented 29 Oct 2026)

`work/cr-products.md` is built in full: RS and ADS updated (sections listed at the top of each), 32-colour palette,
product colours, E024/E025/E038/E039, W013/W014, widened W009, legend row, tooltip line, `data-product`, plan
`product`/`products`, `rt convert` `product` column, schema, both oracles, `products-example.yaml` + expected plan,
`products` block in `roadmap.example.yaml`, AT-56 … AT-65. The expected WE and DE plans changed only by
`"product": null` and `"products": []` (every colour unchanged). Choices the CR left open:

| # | Topic | Decision | Why |
| --- | --- | --- | --- |
| P1 | "ties to the lowest index" when all 32 entries are taken | Lowest palette index, so product 33 takes indigo (0), product 34 green (1) | Literal reading; by then products already use 0–9 |
| P2 | Pinned versus automatic products | Every pinned product takes its entry first, whatever its file position; automatic products then skip it | A pin reserves the colour; otherwise a later pin could clash with an earlier automatic product |
| P3 | W009 wording | `… both pinned to "sky"` when both bars are project pins, else `… both coloured "teal"` | The old text says "pinned", which is wrong for a product colour |
| P4 | W013 / W014 names and position | Product names (as in the CR examples), at the product's first key; W014 names the first product that holds the shared entry | Same location rule as projects |
| P5 | Products without visible bars | Still get a colour (legend and plan); `products[*].projects` lists hidden projects too | Membership, not visibility |
| P6 | DSATUR saturation | Counts every neighbour colour, 10–31 included (affects pick order only) | "Distinct colours among neighbours", as CO-5 says |
| P7 | Hook and tooltip order | `data-product` right after `data-team`; the `Product:` tooltip line right after `Team:` | Mirrors the plan, where `product` follows `team` |
| P8 | Product `description` | Shown in the legend chip's `title` | The CR gives the field but no place to show it |
| P9 | `rt convert` | `product` written after `team` (CV-18 order); E038 suggestion case-insensitive over ids and names (like E030); skeleton W020 reads `column "Produkt" is ignored without --base` | Same rules as the team column |
| P10 | EX | Products BLIK and Tokenizacja kart added; still exactly one warning, now at line 252 (was 226), so two CLI tests changed their line number | CR section 8 item 6 |

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
