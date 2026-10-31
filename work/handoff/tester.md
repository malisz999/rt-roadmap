# Tester handoff

Black-box suite written from docs/requirements.md (RS) and docs/architecture.md section 10; no file
under src/ was read. Every test runs the real CLI (`python -m rt …`) in a temporary directory.

## Layout
| Area | Files | Tests |
| --- | --- | --- |
| Golden plans (AT-01, AT-26) + oracle differential (EX, option variants) | tests/golden/test_golden_plans.py | 10 |
| HTML structure (AT-02..06, 13, 22..25, 29, 33..36; OUT-3/4/8/11/12/14/15/17/18/20/22/24/27/28/30/33; CO-4) | tests/html/*.py | 45 |
| Acceptance: scheduling/colour (AT-07..12, 27, 28, 30, 31), validation (AT-14..16, 32), convert (AT-47..55), model rules (IN-1/2/8/9, SC-12), traceability | tests/acceptance/*.py | 47 |
| CLI: commands (AT-17..21), streams (AT-37..46, ST-1..8), exit codes, help ≤ 80 cols, version, NF-3/4/10/11, schema, init, CLI-8 | tests/cli/test_cli_*.py | 73 |
| Validation catalogue (ADS 10.3): 45 fixtures, every RS 9 code for YAML input | tests/cli/test_catalogue_invalid.py, tests/fixtures/invalid/ | 52 |

Shared helpers: tests/conftest.py, imported as `from rtkit import …` (registered under a unique module
name so it never clashes with tests/unit helpers). Fixtures copied verbatim from docs/fixtures into
tests/fixtures (a test checks they stay identical). Traceability: tests/TRACEABILITY.md, guarded by
tests/acceptance/test_at_traceability.py. AT-25's visual review is manual (documented there).

## Status (end of this session)
- `uv run pytest -q tests/acceptance tests/cli tests/html tests/golden`: 227 passed, 0 failed.
- Whole repository `uv run pytest -q`: 629 passed.
- ruff check / ruff format --check clean on all tester-owned files.

## Defects
- D-001 (medium) `-o /dev/null` exited 4 — fixed by the developer during the session, verified.

## Questions
work/questions.md Q-1..Q-7 (W008 with omitted capacity, AT-36 spelling, positions of node-less
diagnostics, custom-hex accent, non-regular output files, AT-51 suggestion, rt init content).
No test is xfail; each assumption is stated in the question and the test docstring.

## Note
Once during this session `ruff format tests` was run on the whole tests/ tree by mistake; it may have
reformatted tests/unit/test_io_streams.py (formatting only, no semantic change).

## CR-1 Products (29 Oct 2026)
- New: `tests/acceptance/test_at_products.py` (AT-56 … AT-65), `PE`/`PE_PLAN` and `pe_render` in conftest,
  catalogue fixtures e024, e025, e038, e039, w013, w014; traceability range now AT-01 … AT-65.
- Changed: AT-10 allows product colours (10–31) and same-product neighbours; AT-19/AT-20 expect the EX W001 at
  line 252 (EX gained a `products` block).

## CR-2 Team indicators (31 Oct 2026)
- New: `tests/acceptance/test_at_team_indicators.py` (AT-66 … AT-74); traceability range AT-01 … AT-74.
- Changed: EX gained a commented `team_norms` example, so its W001 is now at line 259 (AT-19, AT-20);
  products-example AT-56 asserts `products` follows `team_indicators`.
