# Questions from the tester

Tests are written against the reading given under "Assumed"; none is xfail at the moment because the
implementation already behaves as assumed (Q-5 was filed as D-001, since fixed and verified).

## Q-1 — W008 when `capacity` is omitted (RS 3.2, 9.2 W008, AT-26)
RS 3.2 gives every capacity role a default of 0, so a team without `capacity` has 0 people, which is
the W008 condition. But `dependencies-example.yaml` (no capacity anywhere) must produce a plan
byte-equal to `dependencies-example.expected.json`, which lists only three W001 (AT-26, AT-27).
**Assumed:** W008 fires only when `capacity` is given and sums to 0. The catalogue fixture
`w008_team_without_people.yaml` uses explicit zeros, so it holds under both readings.

## Q-2 — AT-36 project name (RS 11.4 AT-36, roadmap.example.yaml line 132)
AT-36 quotes "Płatności odroczone (BNPL) pilot"; the fixture spells it
"Płatności odroczone (BNPL) – pilot" (en dash). **Assumed:** the fixture spelling is meant.

## Q-3 — Positions of diagnostics that have no single offending node (RS 9 location rule, IN-5)
RS 9 pins value errors to the value and project-level diagnostics to the project's first key.
For the following the node is not specified, so the catalogue asserts the code only:
E001 (syntax: parser position; empty input), E004 (missing version), E032 when both size and ongoing
are present, E040, E041, E042, E043, W005, W006, W008, W009, W010, W012; CSV: E101/E104/E106/E107
column, E103 and E032 column.
**Assumed (asserted):** E010 (missing field) and E032 (neither size nor ongoing) point to the first
key of the project mapping, like the other project-level diagnostics. Please confirm.

## Q-4 — Accent of a custom hex colour (RS 5.3)
"the same hue darkened by 35 % in HSL lightness": relative (L × 0.65) or absolute (L − 35 points)?
The tool uses relative (`#000080` → `#000053`). Not asserted by any test until answered.

## Q-5 — Output to non-regular files (RS CLI-3 vs 6.4)
CLI-3's temp-file-and-rename cannot work for `/dev/null` or `/dev/stdout`. **Assumed:** such targets
are written directly and exit 0 (6.4: exit 4 only when the output is not writable). Filed as D-001.

## Q-6 — Suggestion for unknown CSV team `Apka` (RS AT-51 b, IN-3)
"E030 with a suggestion": "Apka" is 2 edits from "app" only case-insensitively. **Assumed:** any
"did you mean" is acceptable; the test does not pin the suggested value.

## Q-7 — Content of `rt init` (RS 6.1, 13.2)
13.2 lists roadmap.example.yaml as the source of `rt init` and roadmap.minimal.yaml as the source of
`rt init --minimal`. **Assumed:** the written files carry the same data as those fixtures (compared as
parsed YAML, not bytes).
