# manc — macro analysis, news and calendar

A small daily pipeline that reads the economic calendar and trusted news feeds, scores each
tracked asset 0–100 for macro tailwind or headwind, stores every input and score in SQLite,
and shows it on a dashboard. Alongside the score it collects what major institutions
forecast for each asset, extracted from headlines by an LLM.

It is **not** a price predictor or a trading signal: it measures the macro narrative and data
flow, one input among many, and keeps the number explainable.

Tracked by default: EURUSD, GBPUSD, USDJPY, XAUUSD, BRENT, SPX, BTCUSD (`config/assets.yaml`).

## How it works

```
calendar (Nasdaq) ─┐
news (RSS feeds)  ─┼─► tag headlines (LLM) ─► formula v1 ─► SQLite ◄── FastAPI ◄── Dash UI
forecasts (LLM)   ─┘                                                  manc api      manc ui
                       manc run (cron, once a day)
```

- **Calendar**: Nasdaq's public economic-calendar endpoint; category and importance come
  from regex maps in `config/calendar.yaml`.
- **News**: every RSS feed in `config/feeds.yaml` (wires, central banks, newsletters), deduped
  by URL, each with a trust weight.
- **Forecasts**: headlines that name an institution and sound like a forecast go to an LLM
  with a structured schema; the result is stored per vintage, so revisions stay visible.
  A few publishers with structured data (Fed projections, World Bank outlook) sit behind
  the same interface.
- **Score**: a versioned formula, plain Python with no dependencies, over stored inputs:
  news sentiment, data surprise versus consensus, and event risk ahead. Every input is
  stored, so any date range can be replayed under a new formula.
- **LLM**: every call goes through [LiteLLM](https://github.com/BerriAI/litellm); the model
  is one string in `config/llm.yaml`, a free OpenRouter model by default. Headlines the LLM
  cannot tag fall back to a lexicon in `config/lexicon.yaml`.

The design, data sources, formula and milestones are in [docs/blueprint.md](docs/blueprint.md);
the tables in [docs/er-schema.md](docs/er-schema.md); the literature behind the formula in
[docs/prior-art.md](docs/prior-art.md).

## Status

| Milestone | State |
|-----------|-------|
| M1 Skeleton: models, store, migrations, CLI, fakes, hooks | done |
| M2 Ingestion: RSS news, Nasdaq calendar, LLM forecast extractor, Yahoo spot closes, Fed SEP and World Bank publishers | done |
| M3 Analysis and index: LLM tagger, formula v1 | next |
| M4 Report, API and dashboard | planned |
| M5 Operations, M6 Formula v2 | planned |

Until M3 lands the tagger is a stub and every score is 50; the calendar, news and
forecasts are real.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync                      # environment
uv run pre-commit install    # git hooks, once per clone
uv run alembic upgrade head  # create or migrate data/manc.db (MANC_DB_URL for another database)
uv run pytest                # tests, no network
```

The LLM needs an API key for whichever provider `config/llm.yaml` names. For the default
(OpenRouter) put `OPENROUTER_API_KEY=...` in a `.env` file at the repo root (gitignored) or
export it. Live tests that hit real sources are marked `live` and skipped by default:
`uv run pytest -m live`.

## Running

```sh
uv run manc run                                # today: fetch, tag, extract forecasts, score, store
uv run manc run --date 2026-09-15              # a past day
uv run manc -v run                             # log each step to stderr
uv run manc rescore --formula v1 --from 2026-09-01   # replay stored inputs under a formula
uv run manc forecasts --since 2026-06-01       # one-off forecast backfill from the query feeds
```

Scheduling is a cron line: `0 6 * * 1-5 cd ~/quant/manc && uv run manc run`.

## Development

Test-driven: the failing test comes before the code. Every commit runs the pre-commit
hooks (file hygiene, `ruff format`, `ruff check --fix`, `pytest` with a coverage floor);
there is no hosted CI. One issue, one branch, one PR. The conventions are in
[CLAUDE.md](CLAUDE.md), which the maintainer also uses to drive an AI coding assistant.

Layout:

- `src/manc/` — the application: `calendar/`, `news/`, `forecasts/`, `spot/`, `analysis/`,
  `scoring/`, `store/`, `pipeline.py`, `cli.py`, `llm.py`
- `src/manc/formulas/` — index formulas as plain classes, standard library only, versioned
- `src/manc/store/schema.py` — declared tables; every change is an Alembic revision in `migrations/`
- `config/` — assets, feeds, calendar maps, scoring params, LLM model, forecast institutions
- `tests/` — one folder per module, recorded fixtures under `tests/fixtures/`

## License

[MIT](LICENSE).
