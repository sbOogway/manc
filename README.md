# manc — macro analysis, news and calendar

A small daily pipeline that reads the economic calendar and trusted news feeds, scores each
tracked asset 0–100 for macro tailwind or headwind, stores every input and score in SQLite,
and shows it on a dashboard. Alongside the score it collects what major institutions
forecast for each asset, extracted from headlines by an LLM.

It is **not** a price predictor or a trading signal: it measures the macro narrative and data
flow, one input among many, and keeps the number explainable.

Tracked by default: 62 assets across forex, metals, commodities, equity indices, crypto and
US Treasury yields (`config/assets.yaml`).

## How it works

```
calendar (Nasdaq) ─┐
news (RSS feeds)  ─┼─► tag headlines (LLM) ─► formula ─► SQLite ◄── FastAPI ◄── static site
forecasts (LLM)   ─┘                                               manc api      GitHub Pages
  manc fetch (cron, every 15 min): the inputs only
  manc run   (cron, once a day):   fetch, tag what is new, forecasts, scores, reports
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
  is one string in `config/llm.yaml`, Claude Code headless on your own login by default, a
  free-tier model as fallback. Headlines no model tags fall back to a lexicon in
  `config/lexicon.yaml`.

The design, data sources, formula and milestones are in [docs/blueprint.md](docs/blueprint.md);
the tables in [docs/er-schema.md](docs/er-schema.md); the literature behind the formula in
[docs/prior-art.md](docs/prior-art.md).

## Status

| Milestone | State |
|-----------|-------|
| M1 Skeleton: models, store, migrations, CLI, fakes, hooks | done |
| M2 Ingestion: RSS news, Nasdaq calendar, LLM forecast extractor, Yahoo spot closes, Fed SEP and World Bank publishers | done |
| M3 Analysis and index: LLM tagger, lexicon fallback, formula v1 | done |
| M4 Report, API and dashboard: markdown report, REST API, static dashboard on GitHub Pages | in progress |
| M5 Operations, M6 Formula v2 | planned |

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync                      # environment
uv run pre-commit install    # git hooks, once per clone
uv run alembic upgrade head  # create or migrate data/manc.db (MANC_DB_URL for another database)
uv run pytest                # tests, no network
```

The default model, `claude_code/opus`, runs Claude Code headless (`claude -p`) on your own
Claude login, so `claude` must be installed and logged in; no API key. Any other provider
in `config/llm.yaml` needs its key: the fallback (Mistral, free tier) reads
`MISTRAL_API_KEY=...` from a `.env` file at the repo root (gitignored) or the environment. Live tests that hit real sources are marked `live` and skipped by default:
`uv run pytest -m live`.

## Running

```sh
uv run manc fetch                              # calendar, news and closes into the store; seconds, no model
uv run manc run                                # today: fetch, tag what is new, extract forecasts, score, store
uv run manc run --date 2026-09-15              # a past day
uv run manc -v run                             # also log every feed and calendar day
uv run manc rescore --formula v1 --from 2026-09-01   # replay stored inputs under a formula
uv run manc forecasts --since 2026-06-01       # one-off forecast backfill from the query feeds
```

Every run logs its start, each step and each tagging batch to stderr with the time; the
scores go to stdout, one line per asset. Scheduling is two cron lines:

```
*/15 * * * * cd ~/quant/manc && uv run manc fetch
0 6 * * 1-5  cd ~/quant/manc && uv run manc run
```

### Dashboard

```sh
uv run manc serve                              # API on :8000 and the dashboard on :8050
uv run manc api                                # the REST API alone (OpenAPI UI at /docs)
uv run manc ui                                 # the static dashboard alone
```

The dashboard is a static site (`site/`, Vue 3 and Plotly.js from a CDN, no build step) that
only talks to the API; open http://localhost:8050 and it reads `http://localhost:8000`. The
field in the header points it at another backend, for instance a Cloudflare tunnel in front of
`manc api`; the choice stays in the browser.

Publishing it to GitHub Pages is `scripts/publish-site.sh`: it pushes `site/` to the `gh-pages`
branch, which Pages serves (enable Pages on that branch once, the command is in the script).
The published site reads the production backend (`PRODUCTION_API_URL` in `site/client.js`, the
tunnel hostname); the header field still overrides it.

### Production

The backend is one container; `Containerfile` and `compose.yaml` work with Podman (rootless)
and Docker alike. The SQLite database stays in `./data`, bind-mounted, so the daily run can
happen on the host with Claude Code or inside the container with a keyed model.

```sh
podman compose up -d --build                   # API on http://127.0.0.1:8000, migrates on start
podman compose logs -f api                     # uvicorn log
podman compose run --rm api manc run           # a daily run inside the container (see below)
podman compose --profile tunnel up -d          # also cloudflared, with TUNNEL_TOKEN from .env
podman compose down                            # stop everything; the data folder stays
```

`.env` holds the provider keys (`MISTRAL_API_KEY`, ...) and, for the tunnel, `TUNNEL_TOKEN`
from the Zero Trust dashboard (Networks → Tunnels → Create, connector type cloudflared; give
the tunnel a public hostname whose service is `http://api:8000`). Runs inside the container
need `MANC_LLM_MODEL=mistral/ministral-14b-latest` (or any keyed model) in `.env`, because the
image has no Claude CLI; a run on the host uses `config/llm.yaml` as usual and the container
serves the result immediately. Either way the cron lines are

```
*/15 * * * * cd ~/quant/manc && podman compose run --rm api manc fetch  # the inputs, no model
0 6 * * 1-5  cd ~/quant/manc && uv run manc run                          # host, Claude Code
0 6 * * 1-5  cd ~/quant/manc && podman compose run --rm api manc run     # or: container, keyed model
```

## Development

Test-driven: the failing test comes before the code. Every commit runs the pre-commit
hooks (file hygiene, `ruff format`, `ruff check --fix`, `pytest` with a coverage floor);
there is no hosted CI. One issue, one branch, one PR. The conventions are in
[CLAUDE.md](CLAUDE.md), which the maintainer also uses to drive an AI coding assistant.

Layout:

- `src/manc/` — the application: `calendar/`, `news/`, `forecasts/`, `spot/`, `analysis/`,
  `scoring/`, `store/`, `pipeline.py`, `cli.py`, `llm.py`
- `src/manc/formulas/` — index formulas as plain classes, standard library only, versioned
- `src/manc/api/` — the FastAPI routes; `src/manc/queries.py` the read-side logic behind them
- `site/` — the dashboard; its pure modules are tested with `node --test 'site/tests/*.test.js'`
- `src/manc/store/schema.py` — declared tables; every change is an Alembic revision in `migrations/`
- `config/` — assets, feeds, calendar maps, scoring params, LLM model, forecast institutions
- `tests/` — one folder per module, recorded fixtures under `tests/fixtures/`

## License

[MIT](LICENSE).
