# rt — roadmap renderer (shared rules for all agents)

## Documents
- `docs/requirements.md` — requirements specification (RS). Source of truth for behaviour.
- `docs/architecture.md` — architecture and design specification (ADS). Source of truth for structure.
- `docs/fixtures/` — example inputs, expected plans, JSON Schema; `docs/fixtures/convert/` — CSV inputs, base file,
  expected YAML. Read-only.
- `docs/reference/reference_plan.py`, `docs/reference/reference_convert.py` — oracles for plans and CSV conversion;
  test tooling only, never imported from `src/`.

## Commands
- Install: `uv sync`
- Run: `uv run rt render <file.yaml> [--summary] [--plan plan.json]` · `uv run rt convert <file.csv> [--base base.yaml]`
- Pipes: `uv run rt convert x.csv --base b.yaml | uv run rt render -o out.html`
- Quality gates: `uv run ruff check .` · `uv run ruff format --check .` · `uv run mypy src` · `uv run pytest -q`

## Ownership (enforced by the orchestrator after every turn)
| Path | Owner |
| --- | --- |
| `src/**`, `tests/unit/**`, `tests/property/**`, `tools/**`, `pyproject.toml`, `uv.lock` | developer |
| `tests/acceptance/**`, `tests/golden/**`, `tests/html/**`, `tests/cli/**`, `tests/fixtures/**`, `tests/conftest.py` | tester |
| `work/defects/**`, `work/handoff/tester.md`, `work/questions.md` | tester |
| `work/handoff/developer.md` | developer |
| `docs/**`, `scripts/**`, `CLAUDE.md`, `.claude/**` | human only |

Changes outside your own paths are reverted automatically and reported back to you.

## Conventions
- Never run `git commit`, `git push` or `git reset`; the orchestrator commits after each turn.
- English in code, comments and docs. User data (project names) may be Polish — keep UTF-8 everywhere.
- When RS and ADS disagree, RS wins; note the conflict in your handoff file.
