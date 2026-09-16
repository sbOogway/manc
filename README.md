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
uv run alembic upgrade head  # create/upgrade data/manc.db (set MANC_DB_URL to use another database)
```

Every commit runs the pre-commit hooks: file hygiene, `ruff format`, `ruff check --fix`
and `pytest` with an 85% coverage floor. A failing hook rejects the commit. There is no
hosted CI. For a work-in-progress commit on a branch, `SKIP=pytest git commit ...`.

## Running

```sh
uv run manc run                      # today's scores for every asset (fetch, tag, score, store)
uv run manc run --date 2026-09-15    # score a past day from what is stored
uv run manc -v run                   # same, logging each step to stderr
uv run manc rescore --formula v1 --from 2026-09-01   # replay stored inputs under a formula
```

`manc run` prints one line per asset: `date asset score formula news=N events=N`. Until the
real providers land (M2, M3) the calendar, news and tagger are empty, so every score is 50.
The database must be migrated first (`uv run alembic upgrade head`); `manc` refuses to run
otherwise and tells you so.

## Layout

- `src/manc/` — the application (ingestion, analysis, store, dashboard, CLI)
- `src/manc/formulas/` — index formulas as plain Python classes; standard library only, versioned
- `src/manc/store/schema.py` — declared tables; every change becomes an Alembic revision in `migrations/`
- `config/` — assets, feeds, scoring params, LLM model
- `tests/` — all tests, one folder per module

Status: M1 skeleton complete; M2 ingestion next. See the milestones and issues for progress.
