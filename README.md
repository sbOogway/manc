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
forecasts (LLM)   ─┘                                               manc api      GitHub Pages
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
| M4 Report, API and dashboard: markdown report, REST API, static dashboard on GitHub Pages | done |
| M5 Operations: systemd units, journal log, tuning pass | in progress |
| M6 Formula v2: standardised surprise, novelty, dispersion, asymmetry | done |
| M7 Site package: Vue 3 + TypeScript, PrimeVue, Vite | done |
| M8 Security hardening: sanitised site, bounded API, pinned install, confined units, tool-less tagger | done |

## Setup

For a development checkout:

```sh
uv sync                      # environment
uv run pre-commit install --hook-type pre-commit --hook-type post-merge   # git hooks, once per clone
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
scores go to stdout, one line per asset. Scheduling is systemd user units, see Production.

### Dashboard

```sh
uv run manc serve                              # API on :8888 and the dashboard on :8050
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

Open http://localhost:8050 and it reads `http://localhost:8888`. The field in the header
points it at another backend, for instance the tunnel in front of `manc api`; the
choice stays in the browser. When a route or schema changes, `uv run python
scripts/openapi-schema.py` refreshes `site/openapi.json` (a test fails otherwise) and
`npm run types` the TypeScript types.

Publishing it to GitHub Pages is `scripts/publish-site.sh`: it builds and pushes `site/dist`
to the `gh-pages` branch, which Pages serves (enable Pages on that branch once, the command is
in the script). The published site reads the production backend (`PRODUCTION_API_URL` in
`site/src/api/client.ts`, the tunnel hostname); the header field still overrides it.

### Production

One line installs the whole thing on a machine with `uv` (`sudo dnf install uv`) and [Claude Code](https://claude.com/claude-code) logged in under your account; the
same line brings an existing install up to date:

```sh
sudo uvx --from git+https://github.com/sbOogway/manc@v0.2.0 manc install --owner $USER
```

`uvx` runs `manc install` from the release tag once; that command installs the same tag for
good (`uv tool install`, its own Python 3.12 and the dependencies pinned by `uv.lock` under
`/opt/manc`, the entry point on everyone's `PATH` as `/usr/local/bin/manc`; `--source` takes
another git URL, `main` included) and lays the machine out, idempotently:

- `manc`, a system user with no login shell, runs the API and the fetch as system units
  confined to `/var/lib/manc`: `manc-api.service` (up all the time, restarts on failure) and
  `manc-fetch.timer` (`manc fetch` every 15 minutes, no model needed);
- the database is `/var/lib/manc/manc.db`, mode `0660` in a setgid group-`manc` directory, so
  both `manc` and you write it (you are added to the group; every unit runs with umask
  `0002`, and SQLite gives its journal files the database's mode);
- the daily run stays with your Claude Code login: `manc-run@<you>.timer` runs `manc run` as
  you at 06:00 UTC every day (`Persistent=true`: a day the machine slept through runs at the
  next wake). The site is not published from the server; the `post-merge` hook in your
  development checkout does that;
- `/etc/manc/env` (`root:manc 0640`, written once from the packaged example, never
  overwritten) holds the provider keys, `MANC_DB_URL`, `MANC_API_PORT` (8888) and
  `MANC_API_HOST` (the address the API listens on: loopback, or the LAN address that the
  machine running the public tunnel reaches; that tunnel's hostname is `PRODUCTION_API_URL`).
  Editing it is the one manual step;
- the API is read-only and the dashboard is yours, so the tunnel hostname gets a Cloudflare
  Access application: a policy that allows your login, and in its CORS settings the allowed
  origin `https://sboogway.github.io`, credentials on, method GET. The site sends the Access
  cookie with every request; open the API hostname once in a tab to log in and the dashboard
  works from then on. A rate-limiting rule on the same hostname covers what Access lets
  through, and when `MANC_API_HOST` is a LAN address let only the tunnel machine reach port
  8888 through the firewall.

```sh
sudo systemctl status manc-api manc-fetch.timer manc-run@$USER.timer
sudo systemctl restart manc-api                # after editing /etc/manc/env
sudo journalctl -u manc-api -f                 # uvicorn log
sudo systemctl start manc-run@$USER            # a daily run by hand, same environment
sudo journalctl -u manc-run@$USER -f           # its log
```

A machine without a Claude Code login can run the daily step with a keyed model instead:
`MANC_LLM_MODEL=mistral/ministral-14b-latest` in the env file.

The day's reports by mail: set `MANC_MAIL_TO` in the env file and the run unit pipes
`manc report` (the stored report of every active asset, newest day) into the machine's own
`mail` after every run; the MTA is yours (msmtp, sendmail, …), manc sends nothing itself.

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
