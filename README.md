# manc — macro analysis, news and calendar

A small daily pipeline that reads the economic calendar and trusted news feeds, scores each
tracked asset 0–100 for macro tailwind or headwind, stores every input and score in SQLite,
and shows it on a dashboard. Alongside the score it collects what major institutions
forecast for each asset, extracted from headlines by an LLM.

It is **not** a price predictor or a trading signal: it measures the macro narrative and data
flow, one input among many, and keeps the number explainable.

Tracked by default: 61 assets across forex, metals, commodities, equity indices, crypto and
US Treasury yields (`src/manc/config/assets.yaml`).

## How it works

```
calendar (Nasdaq) ─┐
news (RSS feeds)  ─┼─► tag headlines (LLM) ─► formula ─► SQLite ◄── FastAPI ◄── static site
forecasts (LLM)   ─┘                                               manc api ───── serves ─┘
  manc fetch (timer, every 15 min): the inputs only
  manc run   (timer, once a day):   fetch, tag what is new, forecasts, scores, reports
```

- **Calendar**: Nasdaq's public economic-calendar endpoint; category and importance come
  from regex maps in `src/manc/config/calendar.yaml`.
- **News**: every RSS feed in `src/manc/config/feeds.yaml` (wires, central banks, newsletters), deduped
  by URL, each with a trust weight.
- **Forecasts**: headlines that name an institution and sound like a forecast go to an LLM
  with a structured schema; the result is stored per vintage, so revisions stay visible.
  A few publishers with structured data (Fed projections, World Bank outlook) sit behind
  the same interface.
- **Score**: a versioned formula, plain Python with no dependencies, over stored inputs:
  news sentiment, data surprise versus consensus, and event risk ahead. Every input is
  stored, so any date range can be replayed under a new formula.
- **LLM**: every call goes through [LiteLLM](https://github.com/BerriAI/litellm); the model
  is one string in `src/manc/config/llm.yaml`, Claude Code headless on your own login by default, a
  free-tier model as fallback. Headlines no model tags fall back to a lexicon in
  `src/manc/config/lexicon.yaml`.

The design, data sources, formula and milestones are in [docs/blueprint.md](docs/blueprint.md);
the tables in [docs/er-schema.md](docs/er-schema.md); the literature behind the formula in
[docs/prior-art.md](docs/prior-art.md).

## Status

| Milestone | State |
|-----------|-------|
| M1 Skeleton: models, store, migrations, CLI, fakes, hooks | done |
| M2 Ingestion: RSS news, Nasdaq calendar, LLM forecast extractor, Yahoo spot closes, Fed SEP and World Bank publishers | done |
| M3 Analysis and index: LLM tagger, lexicon fallback, formula v1 | done |
| M4 Report, API and dashboard: markdown report, REST API, static dashboard | done |
| M5 Operations: scheduled runs, run log, tuning pass | in progress |
| M6 Formula v2: standardised surprise, novelty, dispersion, asymmetry | done |
| M7 Site package: Vue 3 + TypeScript, PrimeVue, Vite | done |
| M8 Security hardening: sanitised site, bounded API, tool-less tagger | done |
| M9 One origin: the site served next to the API, no CORS, no GitHub Pages | done |
| M10 Compose: web published, api internal, cron, the Claude login in a volume | done |

## Setup

For a development checkout:

```sh
uv sync                      # environment
uv run pre-commit install    # git hooks, once per clone
uv run manc migrate          # create or migrate data/manc.db (MANC_DB_URL for another database)
uv run pytest                # tests, no network
```

The default model, `claude_code/opus`, runs Claude Code headless (`claude -p`) on your own
Claude login, so `claude` must be installed and logged in; no API key. Any other provider
in `src/manc/config/llm.yaml` needs its key: the fallback (Mistral, free tier) reads
`MISTRAL_API_KEY=...` from a `.env` file at the repo root (gitignored) or the environment. Live tests that hit real sources are marked `live` and skipped by default:
`uv run pytest -m live`.

## Running

```sh
uv run manc fetch                              # calendar, news and closes into the store; seconds, no model
uv run manc chain --since 2024-09-20           # one-off backfill of the on-chain metrics for the coins
uv run manc run                                # today: fetch, tag what is new, extract forecasts, score, store
uv run manc run --date 2026-09-15              # a past day
uv run manc -v run                             # also log every feed and calendar day
uv run manc rescore --formula v1 --from 2026-09-01   # replay stored inputs under a formula
uv run manc forecasts --since 2026-06-01       # one-off forecast backfill from the query feeds
uv run manc report                             # the stored reports of the newest day, to pipe anywhere
```

Every run logs its start, each step and each tagging batch to stderr with the time; the
scores go to stdout, one line per asset. Scheduling is cron in the stack, see Production.

### Dashboard

```sh
uv run manc api                                # the REST API and the built dashboard on :8888 (OpenAPI UI at /docs)
```

The dashboard is an npm package in `site/` (Vue 3 + TypeScript, PrimeVue, FullCalendar,
Plotly, built with Vite) that only talks to the API:

```sh
cd site && npm ci                              # once per clone
npm run dev                                    # development server with hot reload, API proxied to :8888
npm run build                                  # site/dist, what `manc api` serves at /
npm run check                                  # vue-tsc + vitest (also a pre-commit hook)
npm run types                                  # regenerate src/api/schema.d.ts from openapi.json
```

The page and the API share one origin: `manc api` serves `site/dist` at `/` when it is
built (`MANC_SITE_DIR` points it elsewhere), and `npm run dev` proxies the API paths to it.
When a route or schema changes, `uv run python scripts/openapi-schema.py` refreshes
`site/openapi.json` (a test fails otherwise) and `npm run types` the TypeScript types.

In production the site is built into its own image and served by nginx, which proxies the
API paths to the API container (Production below); `manc api` serving `site/dist` is for the
local test.

### Production

One compose stack, `compose.yaml` at the repo root, three containers from two images:

| container | image | what it does |
|---|---|---|
| `web`  | `site/Dockerfile`: the site built with Vite, served by nginx | the only published port (`MANC_PORT`, 8080); proxies `/api/` and `/health` to `api`, so page and requests share one origin |
| `api`  | `Dockerfile`: Python 3.12, the locked dependencies (`uv sync --frozen`), `claude` | `manc migrate && manc api`, on the internal network only |
| `cron` | the same image, under supercronic (`crontab`) | `manc fetch` every 15 minutes, `manc run` daily at 06:00 UTC |

Two volumes: `data` (`/var/lib/manc`, the database) and `claude` (the Claude Code login,
`CLAUDE_CONFIG_DIR`). Settings and keys in `.env` next to the compose file.

```sh
git clone https://github.com/sbOogway/manc && cd manc
cp .env.example .env                          # MANC_PORT, keys; the defaults are fine
docker compose up -d --build                  # builds both images, starts the three containers
docker compose run --rm api claude            # once: /login, open the URL, paste the code, /exit
curl -s http://localhost:8080/health          # {"status":"ok","last_run":null}
docker compose run --rm cron manc run         # the first day by hand; then /health shows last_run
docker compose logs -f cron                   # the schedule and every run
```

The login survives restarts and rebuilds in the `claude` volume; the auto-updater is off in
the image, so `claude` stays the version the image was built with until a rebuild. A machine
without a Claude login tags with a keyed model instead: `MANC_LLM_MODEL=mistral/…` and its
key in `.env`.

Upgrading is `git pull && docker compose up -d --build`. The API is not reachable from
outside the stack; put the tunnel (cloudflared, on this machine or another on the LAN) in
front of `http://<this machine>:8080` with Cloudflare Access on the hostname, since the
API has no auth of its own. Mail is not part of the stack; the reports are on the
dashboard.

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
- `site/` — the dashboard package; `npm run check` type-checks it and runs its vitest suite
- `src/manc/store/schema.py` — declared tables; every change is an Alembic revision in `src/manc/migrations/`
- `src/manc/config/` — assets, feeds, calendar maps, scoring params, LLM model, forecast institutions
- `tests/` — one folder per module, recorded fixtures under `tests/fixtures/`

## License

[MIT](LICENSE).
