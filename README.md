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
| M5 Operations: systemd units, journal log, tuning pass | in progress |
| M6 Formula v2: standardised surprise, novelty, dispersion, asymmetry | done |
| M7 Site package: Vue 3 + TypeScript, PrimeVue, Vite | done |
| M8 Security hardening: sanitised site, bounded API, pinned install, confined units, tool-less tagger | done |

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
scores go to stdout, one line per asset. Scheduling is systemd timers, see Production.

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

Publishing it is `MANC_SERVER=you@server scripts/publish-site.sh`: it builds and copies
`site/dist` to `/var/lib/manc/site` on the server (through your login there and one `sudo`),
where `manc api` serves it. Run it whenever the site changed; nothing publishes on its own.

### Production

One machine runs everything as a dedicated `manc` user: the API with the dashboard, a fetch
every 15 minutes and the daily run, whose headline tagging uses that user's own Claude Code
login. A Cloudflare tunnel (on this machine or another on the LAN) publishes the API's
hostname, and Cloudflare Access on it makes the whole thing yours alone; the API has no auth
of its own.

1. Packages: `sudo dnf install uv python3.12 git` (the distro's `uv` does not download
   interpreters, hence `python3.12`; the project pins 3.12). For the daily mail, a working
   `mail` (`echo test | mail -s test you@example.com`).
2. Install, and later upgrade, with the same line (it is idempotent; `--source` takes a tag
   or another URL instead of `main`):

   ```sh
   sudo uvx --from git+https://github.com/sbOogway/manc@main manc install
   ```

   It creates the `manc` system user (home `/var/lib/manc`, no login shell), installs the
   tool under that home with `uv tool install` and the dependencies pinned by `uv.lock`,
   migrates `/var/lib/manc/manc.db`, writes `/etc/manc/env` from the packaged example when
   missing, and enables `manc-api.service`, `manc-fetch.timer` and `manc-run.timer` (06:00
   UTC daily, caught up after a missed day). Every unit is confined to `/var/lib/manc`
   (`systemd-analyze security` says "OK").
3. Claude Code for the `manc` user, once: install it under that home and log in.

   ```sh
   sudo -u manc -H bash -c 'curl -fsSL https://claude.ai/install.sh | bash'   # → /var/lib/manc/.local/bin/claude
   sudo -u manc -H /var/lib/manc/.local/bin/claude                            # /login: open the URL, paste the code
   ```

   A machine without a Claude login can tag with a keyed model instead:
   `MANC_LLM_MODEL=mistral/ministral-14b-latest` and the key in the env file.
4. Edit `/etc/manc/env` (`root:manc 0640`, never overwritten), then
   `sudo systemctl restart manc-api`: `MANC_API_HOST` is `127.0.0.1` when cloudflared runs
   on this machine, `0.0.0.0` when it runs elsewhere; `MANC_MAIL_TO` your address, or empty;
   the provider keys only for a keyed model. When cloudflared runs elsewhere, the unit lets
   nothing but loopback in, whatever the firewall opens, so add that machine once in a
   drop-in that upgrades leave alone:

   ```sh
   sudo systemctl edit manc-api      # under [Service]: IPAddressAllow=<tunnel machine IP>
   sudo systemctl restart manc-api
   ```
5. Cloudflare: in cloudflared a public hostname, say `manc.<your-domain>`, with service
   `http://<MANC_API_HOST or this machine's LAN IP>:8888`; in Zero Trust an Access
   application (self-hosted) on that hostname with an Allow policy for your email and a
   long session; optionally a rate-limiting rule on the hostname. Nothing else: the page
   and the API share the hostname, so the default cookie and CORS settings are right.
6. Publish the dashboard from your checkout: `MANC_SERVER=you@server scripts/publish-site.sh`
   (step "Dashboard" above), then open `https://manc.<your-domain>/`.
7. Check, and run the first day by hand:

   ```sh
   curl -s http://127.0.0.1:8888/health          # {"status":"ok","last_run":null}
   sudo systemctl status manc-api manc-fetch.timer manc-run.timer
   sudo systemctl start manc-run                 # a daily run now, same environment as the timer
   sudo journalctl -u manc-run -f                # its log; then /health shows last_run
   ```

Your own account and the dev checkout are not involved. Branch protection on `main` (no
force-push, no deletion) and 2FA on the GitHub account are the repository's side:

```sh
gh api -X PUT repos/sbOogway/manc/branches/main/protection --input - <<'EOF'
{"required_status_checks":null,"enforce_admins":false,"required_pull_request_reviews":null,"restrictions":null,"allow_force_pushes":false,"allow_deletions":false}
EOF
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
- `site/` — the dashboard package; `npm run check` type-checks it and runs its vitest suite
- `src/manc/store/schema.py` — declared tables; every change is an Alembic revision in `src/manc/migrations/`
- `src/manc/config/` — assets, feeds, calendar maps, scoring params, LLM model, forecast institutions
- `tests/` — one folder per module, recorded fixtures under `tests/fixtures/`

## License

[MIT](LICENSE).
