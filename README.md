# manc — macro analysis, news and calendar

A small daily pipeline that reads the economic calendar and trusted news feeds, scores each
tracked asset 0–100 for macro tailwind or headwind, stores every input and score in SQLite,
and shows it on a dashboard. Alongside the score it collects what major institutions
forecast for each asset, extracted from headlines by an LLM.

It is **not** a price predictor or a trading signal: it measures the macro narrative and data
flow, one input among many, and keeps the number explainable.

Tracked by default: 61 assets across forex, metals, commodities, equity indices, crypto and
US Treasury yields (`config/assets.yaml`).

## How it works

```
calendar (Nasdaq) ─┐
news (RSS feeds)  ─┼─► tag headlines (LLM) ─► formula ─► SQLite ◄── FastAPI ◄── static site
forecasts (LLM)   ─┘                                               manc api      GitHub Pages
  manc fetch (timer, every 15 min): the inputs only
  manc run   (timer, once a day):   fetch, tag what is new, forecasts, scores, reports
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
| M4 Report, API and dashboard: markdown report, REST API, static dashboard on GitHub Pages | done |
| M5 Operations: systemd units, journal log, tuning pass | in progress |
| M6 Formula v2: standardised surprise, novelty, dispersion, asymmetry | done |
| M7 Site package: Vue 3 + TypeScript, PrimeVue, Vite | done |

## Setup

For a development checkout:

```sh
uv sync                      # environment
uv run pre-commit install --hook-type pre-commit --hook-type post-merge   # git hooks, once per clone
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
uv run manc chain --since 2024-09-20           # one-off backfill of the on-chain metrics for the coins
uv run manc run                                # today: fetch, tag what is new, extract forecasts, score, store
uv run manc run --date 2026-09-15              # a past day
uv run manc -v run                             # also log every feed and calendar day
uv run manc rescore --formula v1 --from 2026-09-01   # replay stored inputs under a formula
uv run manc forecasts --since 2026-06-01       # one-off forecast backfill from the query feeds
```

Every run logs its start, each step and each tagging batch to stderr with the time; the
scores go to stdout, one line per asset. Scheduling is systemd user units, see Production.

### Dashboard

```sh
uv run manc serve                              # API on :8000 and the dashboard on :8050
uv run manc api                                # the REST API alone (OpenAPI UI at /docs)
uv run manc ui                                 # the static dashboard alone
```

The dashboard is an npm package in `site/` (Vue 3 + TypeScript, PrimeVue, FullCalendar,
Plotly, built with Vite) that only talks to the API:

```sh
cd site && npm ci                              # once per clone
npm run dev                                    # development server with hot reload
npm run build                                  # site/dist, what `manc ui` and the publish script serve
npm run check                                  # vue-tsc + vitest (also a pre-commit hook)
npm run types                                  # regenerate src/api/schema.d.ts from openapi.json
```

Open http://localhost:8050 and it reads `http://localhost:8000`. The field in the header
points it at another backend, for instance the tunnel in front of `manc api`; the
choice stays in the browser. When a route or schema changes, `uv run python
scripts/openapi-schema.py` refreshes `site/openapi.json` (a test fails otherwise) and
`npm run types` the TypeScript types.

Publishing it to GitHub Pages is `scripts/publish-site.sh`: it builds and pushes `site/dist`
to the `gh-pages` branch, which Pages serves (enable Pages on that branch once, the command is
in the script). The published site reads the production backend (`PRODUCTION_API_URL` in
`site/src/api/client.ts`, the tunnel hostname); the header field still overrides it.

### Production

One line installs the whole thing on a machine with `git`, `podman`, `setfacl` (`acl`) and
[Claude Code](https://claude.com/claude-code) logged in under your account, and brings an
existing install up to date (pull `main`, redeploy):

```sh
curl -fsSL https://raw.githubusercontent.com/sbOogway/manc/main/scripts/install.sh | sudo sh
```

The install is system-wide under a dedicated user, apart from any development checkout:

- `manc`, a system user with no login shell, its own subordinate id range and linger on, owns
  the code in `/opt/manc` and runs the API container with rootless podman as its own user
  units, `manc-api.service` (up all the time) and `manc-fetch.timer` (`manc fetch` in the
  container every 15 minutes, no model needed);
- the database is `/var/lib/manc/data/manc.db`, group `manc` with a default ACL so both the
  container and the daily run write it;
- the daily run stays on the host with your Claude Code login: `manc-run.timer` is a system
  unit running `manc run` as you at 06:00 UTC every day (`Persistent=true`: a day the machine
  slept through runs at the next wake). The site is not published from the server; the
  `post-merge` hook in your development checkout does that;
- `/etc/manc/env` (`root:manc 0640`, symlinked as `/opt/manc/.env`) holds the provider keys,
  `MANC_API_BIND` (the address the API listens on: loopback, or the LAN address that the
  machine running the public tunnel reaches; that tunnel's hostname is `PRODUCTION_API_URL`)
  and `MANC_DATA_DIR`. Editing it is the one manual step; then restart the API.

```sh
sudo -u manc XDG_RUNTIME_DIR=/run/user/$(id -u manc) systemctl --user status manc-api manc-fetch.timer
sudo -u manc XDG_RUNTIME_DIR=/run/user/$(id -u manc) systemctl --user restart manc-api
sudo -u manc XDG_RUNTIME_DIR=/run/user/$(id -u manc) journalctl --user -u manc-api -f
sudo systemctl status manc-run.timer
sudo systemctl start manc-run                  # a daily run by hand, same environment
sudo journalctl -u manc-run -f                 # its log
```

The image itself: `Containerfile` and `compose.yaml` work with Podman (rootless) and Docker
alike; `podman compose up -d --build` in a development checkout serves the API on
http://127.0.0.1:8000 from `./data`, migrating on start. To run the daily step inside the
container instead of on the host, set `MANC_LLM_MODEL=mistral/ministral-14b-latest` (or any
keyed model) in the env file, because the image has no Claude CLI, and change `ExecStart` in
`manc-run.service` to `podman compose run --rm api manc run`.

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
- `src/manc/store/schema.py` — declared tables; every change is an Alembic revision in `migrations/`
- `config/` — assets, feeds, calendar maps, scoring params, LLM model, forecast institutions
- `tests/` — one folder per module, recorded fixtures under `tests/fixtures/`

## License

[MIT](LICENSE).
