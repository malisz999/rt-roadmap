# CR-1: Products — draft spec change for review

Status: **approved and implemented (29 Oct 2026)**. RS, ADS, fixtures, schema and oracles updated; AT-56 to AT-65
pass. Choices the CR left open are listed in `work/decisions.md` (CR-1, P1–P10).
Decisions taken with the owner on 29 Oct 2026: a product is delivered through ordinary projects (one team per
project, any domain); a 32-colour palette; a project inherits its product's colour unless it pins its own; all
other defaults as proposed.

## 1. Summary

A **product** is a named group of projects owned by exactly one domain (a subdomain id). Projects may reference one
product; their teams may sit in any subdomain. All bars of a product share the product's colour, so a product is
recognisable across the whole roadmap. Projects without a product ("standalone") are coloured exactly as today.
Existing input files without `products` render with the **same colours as before** (see 4.3).

## 2. Input format (RS 3)

New optional top-level list, after `subdomains` and before `projects`:

```yaml
products:
  - id: blik                       # required, ^[a-z0-9][a-z0-9_-]{0,39}$, unique among products
    name: BLIK                     # required, 1–100 characters, unique among products
    domain: channels               # required, a subdomain id: the owning domain
    owner: Anna Kowalska           # optional, ≤ 100 characters
    description: Płatności BLIK    # optional, ≤ 500 characters
    color: indigo                  # optional, palette name or #RRGGBB; pins the product colour

projects:
  - name: BLIK w aplikacji
    team: app                      # a team in another subdomain is fine
    product: blik                  # optional: product id
    size: L
```

| Field | Rules |
| --- | --- |
| `products` | Optional list (absent = empty). File order = legend order. |
| `products[].domain` | Must equal an existing subdomain id. The product's projects are **owned** by that domain. |
| `projects[].product` | Optional; must equal a product id. A project without it is standalone; its owning domain is its team's subdomain. |

Bars are still drawn in the section of the team that does the work (unchanged); ownership is shown in the tooltip
and the legend (section 5).

## 3. Diagnostics (RS 9)

| Code | Condition | Example message |
| --- | --- | --- |
| E024 | Duplicate product id | `product id "blik" already defined at line 31` |
| E025 | Duplicate product name | `product name "BLIK" already used at line 31` |
| E038 | Unknown product reference (with "did you mean") | `project "BLIK w aplikacji" references unknown product "blk" (did you mean "blik"?)` |
| E039 | Product domain is not a subdomain id (with "did you mean") | `product "BLIK" references unknown domain "chanels" (did you mean "channels"?)` |
| W013 | Product has no projects | `product "Karty" has no projects` |
| W014 | More products than palette colours; some share | `products "A" and "B" share colour "teal" (more than 32 products)` |

E002, E010–E012 and E033 apply to product fields as to other entities. W009 is widened: it also fires when two
adjacent bars of **different** products end up with the same colour (only possible with pinned or shared colours).
Adjacent bars of the **same** product share a colour by design and never cause W007 or W009.

## 4. Colour (RS 5)

### 4.1 Palette: 32 entries

Indices 0–9 are today's palette, unchanged (names, fills, accents, ≥ 9:1 text contrast). Indices 10–31 are new;
each keeps text `#1E293B` at ≥ 7:1 contrast (WCAG AAA). Red stays reserved.

| Index | Name | Fill | Accent | Contrast |
| --- | --- | --- | --- | --- |
| 10 | blue | `#BFDBFE` | `#3B82F6` | 10.3 |
| 11 | cyan | `#A5F3FC` | `#06B6D4` | 11.7 |
| 12 | emerald | `#A7F3D0` | `#10B981` | 11.4 |
| 13 | yellow | `#FEF08A` | `#CA8A04` | 12.6 |
| 14 | fuchsia | `#F5D0FE` | `#D946EF` | 10.7 |
| 15 | purple | `#E9D5FF` | `#A855F7` | 10.8 |
| 16 | stone | `#E7E5E4` | `#78716C` | 11.7 |
| 17 | sand-deep | `#D6C3A5` | `#854D0E` | 8.5 |
| 18 | indigo-deep | `#A5B4FC` | `#4F46E5` | 7.3 |
| 19 | green-deep | `#86EFAC` | `#16A34A` | 10.4 |
| 20 | orange-deep | `#FDBA74` | `#EA580C` | 8.7 |
| 21 | pink-deep | `#F9A8D4` | `#DB2777` | 8.1 |
| 22 | sky-deep | `#7DD3FC` | `#0284C7` | 8.8 |
| 23 | amber-deep | `#FCD34D` | `#B45309` | 10.2 |
| 24 | violet-deep | `#C4B5FD` | `#7C3AED` | 7.9 |
| 25 | teal-deep | `#5EEAD4` | `#0D9488` | 9.9 |
| 26 | lime-deep | `#BEF264` | `#4D7C0F` | 11.2 |
| 27 | blue-deep | `#93C5FD` | `#2563EB` | 8.1 |
| 28 | cyan-deep | `#67E8F9` | `#0891B2` | 10.1 |
| 29 | emerald-deep | `#6EE7B7` | `#059669` | 9.6 |
| 30 | fuchsia-deep | `#F0ABFC` | `#C026D3` | 8.3 |
| 31 | purple-deep | `#D8B4FE` | `#9333EA` | 8.3 |

Any palette name may be used in `color:` of a project or a product.

### 4.2 Order of colouring (replaces CO-4; CO-5 keeps its algorithm)

1. **Project pin.** A project with its own `color` uses it (overrides its product's colour).
2. **Product colour.** Every other project of a product uses the product colour:
   - the product's `color` when given;
   - otherwise products without a pin, in file order, take the lowest-index palette entry not yet taken by any
     product, scanning **10–31 first, then 0–9**. Product colours therefore differ from the colours standalone
     bars use (0–9) for up to 22 auto-coloured products, so a standalone bar is never mistaken for a product.
   - When all 32 are taken, the next product takes the entry used by the fewest products, ties to the lowest
     index, and W014 names the products that share.
3. **Standalone projects** are coloured by DSATUR (CO-5) **over entries 0–9 only**, treating bars coloured in
   steps 1–2 as pre-coloured neighbours: a standalone bar never takes the colour of an adjacent product bar.

### 4.3 Compatibility

A file without `products` and without palette names beyond the first 10 renders with exactly the colours it gets
today, so the existing expected colours stay valid.

## 5. Output

- **Legend** (RS 7.2 item 2): a "Products" row after the symbols: one chip per product with its colour, name,
  owning domain and owner (`BLIK · Kanały płatności · Anna Kowalska`).
- **Tooltip** (OUT-18): a line `Product: BLIK · owned by Kanały płatności (Anna Kowalska)` for product projects.
- **Hooks** (RS 7.10): `rt-bar` gains `data-product` (product id, empty for standalone); legend chips are
  `rt-product` with `data-product` and `data-color-index`.
- **Summary**: unchanged (per-product rows were left for later).
- **Plan JSON** (RS 8):
  - each project gains `"product"` (id or `null`), placed right after `"team"`;
  - a top-level `"products"` list, right after `"teams"`:
    `{ "id", "name", "domain", "owner", "color_index", "color_name", "color_fill", "projects": [seq…] }`.
- **`rt convert`** (RS 3.4, 6.6): optional CSV column `product`, holding a product id or name. With `--base` it
  resolves against the base's `products` (unknown → E038 with suggestion). Without `--base` the column is ignored
  with W020 (the generated skeleton does not create products).

## 6. New acceptance tests (RS 11)

| ID | Given / When | Then |
| --- | --- | --- |
| AT-56 | Products fixture: two products, one with projects in teams of two subdomains | Every bar of a product has the product's `data-color-index`; plan `products[*].projects` lists their seqs |
| AT-57 | Same, one product project with its own `color: sky` | That bar is sky (index 4); the product's other bars keep the product colour |
| AT-58 | Same | Standalone bars use indices 0–9 only and none shares a colour with an adjacent bar of any product |
| AT-59 | WE and DE (no products) | Plans equal the updated expected files: every colour unchanged, `product: null`, `products: []` |
| AT-60 | Unknown product, duplicate product id and name, unknown domain | Exit 1; E038 and E039 with "did you mean", E024, E025, all positioned |
| AT-61 | A product with no projects | W013 |
| AT-62 | 34 products without pins, each with a project | 32 distinct product colours; W014 for the two products that share |
| AT-63 | Render the products fixture | Legend has one `rt-product` chip per product in file order; tooltips show `Product: … · owned by …` |
| AT-64 | CSV with a `product` column, `--base` holding products | `product:` written as the id (a name resolves too); unknown value → E038; without `--base` → W020 |
| AT-65 | `rt schema` | The schema accepts `products` and `project.product`, and still validates every fixture |

## 7. Design (ADS)

| Area | Change |
| --- | --- |
| `model.types` | `Product(id, name, domain_id, owner, description, color, pos)`; `Project.product_id`; `Model.products` |
| `model.build` / `references` | Parse `products`; E024, E025, E038, E039 |
| `color.palette` | 32 entries; `BASE = range(10)` for DSATUR, product order `10…31, 0…9` |
| `color.dsatur` | New step before DSATUR: product colours (pin, then auto), W014; product bars pre-coloured; W009 rule widened |
| `plan.types` / `serialize` | `PlannedProject.product`; `Plan.products` (`ProductPlan`) |
| `layout` / `render` | Legend products row, tooltip line, `data-product` |
| `convert` | `product` column, base resolution, skeleton W020 |
| schema | `products` and `project.product` in `roadmap.schema.json` |
| oracle | `reference_plan.py` learns products, so differential and golden tests cover them |

## 8. Changes to human-owned files: need your permission

`docs/` is yours under CLAUDE.md. Implementing this CR changes:

1. `docs/requirements.md`, `docs/architecture.md`: the sections above (I can write them, or you can).
2. `docs/fixtures/*.expected.json`: add `"product": null` per project and `"products": []`. Colours do not change.
3. `docs/fixtures/roadmap.schema.json`: the new fields.
4. `docs/reference/reference_plan.py`: product colouring, so it stays the oracle.
5. New `docs/fixtures/products-example.yaml` + `.expected.json` (generated by the updated oracle).
6. `docs/fixtures/roadmap.example.yaml` (what `rt init` writes): a `products` block for the Polish example, so
   new users see the feature. Optional.
