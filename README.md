# manc — macro analysis, news and calendar

Daily pipeline that reads the economic calendar (OpenBB) and trusted RSS news
feeds, scores each tracked asset 0–100 for macro tailwind/headwind, stores the
score in SQLite and plots it on a small web page.

Blueprint: [docs/blueprint.md](docs/blueprint.md) (styled render: https://claude.ai/artifact/LqZ6Yg7nVfTK46zYEJUShz)

## Setup

```sh
uv sync                      # creates .venv with Python 3.12 and all dependencies
uv run pre-commit install    # installs the git hooks (once per clone)
uv run pytest                # run the test suite
```

Every commit runs the pre-commit hooks: file hygiene, `ruff format`, `ruff check --fix`
and `pytest` with an 85% coverage floor. A failing hook rejects the commit. There is no
hosted CI. For a work-in-progress commit on a branch, `SKIP=pytest git commit ...`.

## Layout

- `src/manc/` — the application (ingestion, analysis, store, dashboard, CLI)
- `packages/manc-formulas/` — index formulas; standard library only, versioned
- `config/` — assets, feeds, scoring params, LLM model
- `tests/` — application tests; formula tests live next to the formula package

Status: M1 skeleton in progress. See the milestones and issues for progress.
