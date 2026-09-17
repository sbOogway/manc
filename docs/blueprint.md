# manc — macro analysis, news and calendar

**Project blueprint.** Styled render: https://claude.ai/artifact/LqZ6Yg7nVfTK46zYEJUShz
This file is the source of truth; update it when a decision changes.

A small daily pipeline that reads the economic calendar and trusted news feeds, scores each
tracked asset 0–100, stores the score, and plots it.

Stack: Python 3.12 · uv · pytest, TDD · pre-commit · LiteLLM · FastAPI · Dash · SQLite via SQLAlchemy Core + Alembic · Nasdaq calendar.

---

## 1 · What it does

Every morning `manc run` answers one question per asset: *given what was released and reported
recently, and what is scheduled next, does the macro backdrop lean for or against this asset?*
The answer is a single number from 0 (strong headwind) to 100 (strong tailwind), plus a short
written report explaining it.

Initial asset list (all configurable in `config/assets.yaml`):

| Symbol | Kind         | Economies that move it                    |
|--------|--------------|-------------------------------------------|
| EURUSD | forex        | Euro area, United States                  |
| GBPUSD | forex        | United Kingdom, United States             |
| USDJPY | forex        | United States, Japan                      |
| XAUUSD | metal        | United States (rates, dollar)             |
| BRENT  | commodity    | United States, OPEC headlines             |
| SPX    | equity index | United States                             |
| BTCUSD | crypto       | United States (liquidity, risk appetite)  |

What it is **not**: a price predictor or a trading signal. It measures the macro narrative and
data flow, which is one input among many. Prices are deliberately not part of the score so it
stays interpretable.

## 2 · Daily pipeline

One command, seven steps, each behind an interface so it can be swapped or faked in tests.

| Step | Name           | What                                                        | Module          |
|------|----------------|-------------------------------------------------------------|-----------------|
| 01   | Fetch calendar | Next 30 days of events, plus last 7 days with actuals.      | `calendar/`     |
| 02   | Fetch news     | Pull every RSS feed, dedupe by URL, keep last 72h.          | `news/`         |
| 02b  | Fetch forecasts| Institutional forecasts: extracted from the news just stored, plus structured publishers. | `forecasts/` |
| 02c  | Fetch spot     | One daily close per asset, for display next to forecasts only. | `spot/`     |
| 03   | Analyse        | Tag headlines to assets with a direction.                   | `analysis/`     |
| 04   | Score          | Hand the inputs to the configured formula: 0–100 out. No I/O.| `formulas/`     |
| 05   | Store + report | Write score, components and markdown report to SQLite.      | `store/` `report/` |

Reading is separate from writing. The pipeline is the only writer. A REST API (`manc api`)
serves everything a person might look at, and the dashboard (`manc ui`) is one client of that
API; it never touches the database. Scheduling is a plain cron entry; no queue, no workers, no
orchestrator.

```
pipeline (cron) ──► SQLite ◄── FastAPI  ◄── HTTP/JSON ── Dash UI
   manc run                    manc api                  manc ui
```

Because every input to step 04 is
stored, `manc rescore --formula v2` can replay history under a new formula without refetching
anything.

## 3 · Modules and interfaces

Each module exposes one `typing.Protocol` and a set of frozen dataclasses in `manc/models.py`.
Everything else in the module is private. Tests for a module never touch the network: providers
are exercised against recorded fixtures, LLM calls are stubbed at the `litellm.completion`
boundary, and the pipeline is tested with in-memory fakes of each protocol.

| Module     | Interface                                                                 | Default implementation                                                  | Tests cover                                                          |
|------------|---------------------------------------------------------------------------|-------------------------------------------------------------------------|----------------------------------------------------------------------|
| `calendar` | `CalendarProvider.fetch(start, end) -> list[CalendarEvent]`               | Nasdaq's public calendar endpoint over httpx (free, no key)             | parsing, category/importance/country maps, date offset, day windows  |
| `news`     | `NewsProvider.fetch(since) -> list[NewsItem]`                             | feedparser over `config/feeds.yaml`                                     | parsing, dedupe, per-feed failure isolation                          |
| `forecasts`| `ForecastProvider.fetch(since) -> Forecasts` (asset and macro lists)        | `extractor.py`: LiteLLM over stored news rows that pass a regex prefilter; `fed_sep.py`, `worldbank.py` for publishers with structured data (§4) | extractor: prefilter, batching, schema validation, horizon normalisation, dedupe; publishers: recorded fixtures |
| `spot`     | `SpotProvider.fetch(assets, date) -> list[SpotPrice]`                      | `yahoo.py` through `yfinance`, one history call per asset; the ticker per source sits in `config/assets.yaml`, so another source is a new adapter plus a config edit | recorded frames, missing ticker, one asset failing does not stop the rest; isolation test that no formula input carries a price |
| `analysis` | `Analyzer.tag(items, assets) -> list[NewsTag]`                            | LiteLLM `completion()` with a Pydantic response schema, model from config | fake analyzer; batching; schema validation                           |
| `formulas` | `get_formula(name) -> IndexFormula`; `IndexFormula.compute(ScoringInputs) -> IndexScore` | plain Python classes, one per version, standard library only (§5) | property tests on every formula; an isolation test that the package imports nothing else from `manc` |
| `scoring`  | `build_inputs(store, asset, as_of, params) -> ScoringInputs` | thin adapter from the store to the formula contract | adapter builds inputs correctly |
| `store`    | Repository pattern: `Store` composes `news`, `tags`, `events`, `scores` repositories, each with `add()` and named queries (`since`, `tagged`, `between`, `series`) | SQLAlchemy Core over SQLite; schema in `schema.py`, Alembic migrations | round-trips, idempotent upserts; migrations reach `head` and match `schema.py` |
| `report`   | `build_report(asset, score, tags, events) -> str`                         | Markdown, summary paragraph written by the configured LLM               | template output with fake analyzer                                   |
| `queries`  | `overview(store, config, as_of)`, `asset_history(...)`, `headlines_behind(...)`, `upcoming_events(...)` → frozen dataclasses | the read-side logic: bands, deltas, sparklines, event risk, sorting. Plain functions over a `Store` (§7) | unit tests with `FakeStore`; no HTTP involved |
| `api`      | FastAPI app, `GET /api/v1/...` (§7)                                       | thin routes: parse request → call a query → return a Pydantic model      | `TestClient` against `FakeStore`: status, JSON shape, error cases   |
| `manc_ui`  | Dash app in its own package; talks to the API over HTTP only              | Dash + Mantine components + Plotly (§7)                                 | callbacks tested against a mocked API (`respx`); render smoke tests; isolation test that it never imports `manc` |
| `pipeline` | `run(date, config) -> list[IndexScore]`                                   | wires the above; exposed as `manc run`                                  | end-to-end with all fakes                                            |

### Test-driven development

Every feature is built test-first, and every GitHub issue is closed by a pull request whose
first commits are the failing tests. The working loop per issue:

1. **Red.** Write the test that describes the behaviour, run it, watch it fail for the right
   reason. For a provider that means a recorded fixture and the expected dataclasses; for the
   formula, a property such as "no inputs → 50".
2. **Green.** Write the least code that passes. No speculative branches.
3. **Refactor.** Clean up with the tests as the safety net, then commit.

What "test-first" means per layer:

| Layer               | Test style                                                                                                                                  | Doubles and fixtures                                                        |
|---------------------|---------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| `formulas`          | property tests with `hypothesis`: bounds 0–100, exactly 50 on empty inputs, monotonic in N and S, symmetric under sign flip, event risk only shrinks toward 50 | none needed; pure functions                              |
| `calendar`, `news`  | parser tests against recorded responses; one test per failure mode (empty feed, malformed date, HTTP 403 on one feed of many)               | fixture files under `tests/fixtures/`, HTTP stubbed with `respx`            |
| `analysis`          | tagger tests assert prompt batching, schema validation and retry                                                                           | `litellm.completion` monkeypatched to return canned JSON                    |
| `store`             | migration tests (upgrade to head, downgrade to base, no drift between `schema.py` and `head`); round-trip and idempotency tests on a temp SQLite file | `tmp_path`                                                       |
| `pipeline`, `cli`   | end-to-end against in-memory fakes of every Protocol; asserts the rows written, the exit code and the log                                   | `FakeCalendar`, `FakeNews`, `FakeAnalyzer`, `FakeStore` in `tests/fakes.py` |
| `queries`           | unit tests of every read-side function on known rows: band thresholds, deltas, sparkline windows, event-risk badge, ordering              | `FakeStore`                                                                 |
| `api`               | one test per route: status code, response model, 404 for an unknown asset, validation errors for bad dates                                 | FastAPI `TestClient` with `FakeStore` injected                              |
| `manc_ui`           | callback functions tested directly against a mocked API plus one smoke test per page that the layout renders; visual quality is reviewed manually by the owner, not by automated screenshots | `respx` mocking `MANC_API_URL`                                    |

Coverage is not a target on its own, but pytest is configured to fail below 85% so untested
code cannot sneak in. Live-network tests exist for the
real RSS feeds and the Nasdaq calendar; they are marked `@pytest.mark.live`, skipped by default
and run manually before a release.

Enforcement is local, not hosted: there is no GitHub Actions workflow. A `pre-commit`
configuration runs on every commit and blocks it if anything fails.

### Core dataclasses

The value objects are the code: `src/manc/models.py` holds `CalendarEvent`, `NewsItem`,
`NewsTag`, `ForecastAsset`, `ForecastMacro`, `Forecasts` and `SpotPrice`; the score-side types
(`AssetSpec`, `ScoringInputs`, `IndexScore`) live in `src/manc/formulas/contract.py` so the
formula package stays free of app imports, and `models.py` re-exports them. Every one is a
frozen dataclass; ids are content hashes (`NewsItem.id = sha1(url)`, forecast ids are the
vintage key, §4) so re-fetching is idempotent.

## 4 · Data sources

### Economic calendar → Nasdaq, called directly

`https://api.nasdaq.com/api/calendar/economicevents?date=YYYY-MM-DD` needs no API key and
returns, per row, `gmt, country, eventName, actual, previous, consensus, description`. The
provider (`calendar/nasdaq.py`) issues one request per day of the window over httpx with
browser-like headers. Quirks verified on 2026-09-16 and pinned by tests:

- `date=D` returns the events of **D−1**, so the provider requests `D+1` for each wanted day;
- the `gmt` column is really **US Eastern** wall-clock time (payrolls at 08:30, FOMC at
  14:00); it is converted to UTC. `All Day`, `Tentative` and `24H` become midnight Eastern;
- values are strings (`"1,774K"`, `"5.4%"`, `"310.70B"`); K/M/B/T scale the number, `%` is
  dropped, blanks (`"&nbsp;"`, `" "`) become `None`;
- there is **no importance and no category**. Both come from case-insensitive regex maps on
  the event name in `config/calendar.yaml`, first match wins: `categories` (→ inflation |
  employment | growth | rates, else `other`), `importance` (3 for rate decisions, CPI,
  payrolls, GDP; 2 for PMIs, retail sales, claims, PPI; else 1) and `countries` (Nasdaq names
  that differ from our economy keys, e.g. `Euro Zone → euro_area`; others are snake_cased);
- two rows can share a name on one day (UK `Core CPI` YoY and MoM), so the event id is
  `sha1(date | country | event | ordinal)` with the ordinal counting same-name rows in order;
- **horizon**: the past is available for 15+ years (thinner coverage before ~2015), so
  history can be backfilled at one request per day; the future is dense for about two
  weeks only, then almost empty apart from a few central-bank decisions. The 30-day
  look-ahead therefore covers R's 7-day window fully and is blind beyond ~14 days; if a
  longer horizon ever matters, the published FOMC/ECB/BoE/BoJ schedules belong in a small
  static YAML, not in more Nasdaq calls.

OpenBB was the original plan (`openbb-nasdaq`), and its fetcher hits exactly this URL, but it
requests only weekday dates and therefore drops every Friday's releases through the offset
above, stamps the Eastern times as GMT, and pulls in 52 packages. FMP and TradingEconomics
calendars (keyed) remain possible alternative providers behind the same Protocol.

### News → RSS

OpenBB's news endpoints all sit behind paid providers (Benzinga, FMP, Tiingo), so news comes
from RSS. Reuters closed its public RSS in 2020, but its headlines are reachable through a
Google News RSS query. Feeds were probed on 2026-09-15:

| Source                          | Feed                                                         | Status            | Weight |
|---------------------------------|--------------------------------------------------------------|-------------------|--------|
| Reuters (via Google News)       | `news.google.com/rss/search?q=site:reuters.com+markets`      | live · 100 items  | 1.0    |
| Federal Reserve press           | `federalreserve.gov/feeds/press_all.xml`                     | live              | 1.0    |
| ECB press                       | `ecb.europa.eu/rss/press.html`                               | live              | 1.0    |
| Bank of England                 | `bankofengland.co.uk/rss/news`                               | live              | 1.0    |
| CNBC Economy / Top news         | `cnbc.com/id/20910258/device/rss/rss.html`                   | live              | 0.8    |
| MarketWatch Market Pulse        | `feeds.content.dowjones.io/public/rss/mw_marketpulse`        | live              | 0.8    |
| BBC Business                    | `feeds.bbci.co.uk/news/business/rss.xml`                     | live              | 0.7    |
| FXStreet                        | `fxstreet.com/rss/news`                                      | live              | 0.6    |
| Investing.com forex / commodities | `investing.com/rss/news_1.rss`, `news_11.rss`              | live              | 0.6    |
| CoinDesk                        | `coindesk.com/arc/outboundfeeds/rss/`                        | live              | 0.6    |
| OilPrice                        | `oilprice.com/rss/main`                                      | live              | 0.5    |
| ForexLive, BLS, Kitco           | —                                                            | 403 / 404         | skip   |

Source weight expresses trust and signal density; it multiplies each headline's contribution
in §5. Central-bank feeds get full weight because they are primary sources.

### Headline tagging → any LLM, through LiteLLM

Keyword matching is brittle ("Fed" vs "fed up"), so tagging is one LLM call per batch of ~40
headlines with a structured response: for each headline, the list of affected assets with a
direction and confidence. At ~300 headlines a day this is a handful of calls.

All model calls go through LiteLLM's `completion()`, behind `manc.llm.complete()` (the
extractor and the tagger share it), so the model is a single
provider-prefixed string in `config/llm.yaml` (`anthropic/...`, `openai/...`, `ollama/...`,
`openrouter/<vendor>/<model>`) and switching providers is a config edit plus the provider's
API-key env var.

The default is free by design: a named free model on OpenRouter, chosen with the tagger
benchmark (`tests/analysis/test_live_tagger.py`, recorded headlines with the direction a
market reader expects; `MANC_LIVE_MODEL` benchmarks any model). OpenRouter's `openrouter/free`
router was tried first and dropped: it picks a different model per request, and the free
models range from ones that pass the benchmark to ones that tag every asset for the first
headline and stop. Every tag and every extracted forecast stores the `model` string, and
the free tier's caps (about 20 requests a minute and a small daily allowance, raised by
buying credits once) are fine for the daily run but slow a backfill; LiteLLM's retries and
the configured `fallback` absorb 429s. Switching to a paid model, or to a self-hosted
Ollama server (`ollama_chat/<model>` with `OLLAMA_API_BASE`), is one config edit.

The response schema is a Pydantic model passed as `response_format`; LiteLLM translates it to
each provider's native structured-output mechanism (Anthropic, OpenAI, Ollama, Groq, Gemini,
Bedrock all support it) and `litellm.enable_json_schema_validation = True` validates
client-side for the ones that don't. Provider-specific parameters never appear in our code. A
lexicon-based `Analyzer` stays available as an offline fallback and as the test double.

### Institutional forecasts → extracted from news, plus a few publishers

The dashboard shows, per asset, what major institutions expect: price targets (EURUSD 1.18
at year-end, gold 4,000 in 12 months), policy-rate paths and macro projections (US CPI, GDP,
unemployment) for the tracked economies. Forecasts are **display only**: they are stored with
every vintage so a later formula version can be evaluated against them (§9, M6), but v1 does
not read them.

Probed on 2026-09-17: no institution publishes a free, machine-readable price forecast for
the FX pairs, SPX or BTC. Bank calls reach the public as headlines ("ING lifts year-end
EUR/USD forecast to 1.18", "Goldman raises gold target"), so the primary channel is
extraction from the news already ingested, and structured publishers are supplements:

| Channel     | Source                                                     | Covers                          | Cadence     |
|-------------|------------------------------------------------------------|---------------------------------|-------------|
| extracted   | every feed in `feeds.yaml`, plus one Google News RSS query per asset (`EUR/USD forecast (Goldman OR ING OR ...)`) at low news weight | all assets, rate calls | daily; the queries return ~100 items spanning months, used once for a backfill |
| structured  | Fed SEP (`fed_sep.py`): the medians for the policy rate, PCE inflation, real GDP and unemployment per projection year, from the accessible projections page linked on the FOMC calendar; the undated longer run is skipped | `united_states` macro | quarterly |
| structured  | World Bank Commodity Markets Outlook (`worldbank.py`): the forecasts xlsx behind the PDF linked on the commodity-markets page, dated by its release line | BRENT and XAUUSD annual averages | semi-annual |
| not used    | CME FedWatch (403), Bloomberg/Reuters consensus, Trading Economics (paid), bank research pages (scraping; revisit if a must-have appears) | | |

The extractor runs after step 02 over the news rows stored that run: a case-insensitive regex
prefilter (an institution alias next to one of the `signals` regexes, both lists in
`config/forecasts.yaml`; `manc.forecasts.prefilter`) keeps the handful of candidate items, which go to one LiteLLM call per
batch with a Pydantic schema: per item, zero or more forecasts with subject (asset symbol or
economy+metric), value, horizon as stated, institution and a confidence. Rules pinned by tests:

- **horizon normalisation**: "12 months" → published_at + 12 months; "year-end" → 31 Dec of
  the publication year; "Q4 2026" → 2026-12-31; "2027 average" → 2027-12-31; unparseable
  → item dropped with a warning. The label is kept verbatim;
- **dedupe by vintage**: the id is `sha1(institution | subject | horizon_date | value)`, so five
  outlets reporting the same call collapse into one row keyed to the earliest `published_at`
  and its URL; a changed value is a new row, which is how revisions ("raised from 3,700 to
  4,000") stay visible;
- **nothing is dropped on confidence**: every extraction is stored with its confidence, and
  the read side filters with `min_confidence` (default in `config/forecasts.yaml`), so the
  prompt can be tuned against what was actually extracted;
- **institutions are canonical**: `config/forecasts.yaml` lists each institution with its
  aliases (`Goldman`, `GS`, `Goldman Sachs`), a kind (`bank | official | survey | specialist`)
  and a weight used only for ordering in the dashboard. Initial list: Goldman Sachs, JPMorgan,
  Morgan Stanley, Citi, Bank of America, UBS, HSBC, Deutsche Bank, Barclays, ING, MUFG,
  Nomura; Fed, ECB, BoE, BoJ, IMF, OECD, World Bank, EIA, IEA, OPEC; Reuters poll, Bloomberg
  consensus, Philly Fed and ECB SPF, LBMA survey; Standard Chartered and Bernstein (crypto),
  World Gold Council. A forecast from an institution not on the list is stored under the name
  the model returned, snake_cased, so nothing is lost and the list can grow from the data.

`manc forecasts --since 2026-01-01` runs the extractor once over the long window of the
per-asset queries to backfill; the daily run then uses the normal 72h news window.

### Spot price → display only

A target without a spot is unreadable ("gold 4,000" versus what?), so one daily close per
asset is stored in `spot_prices` and shown next to forecasts as a percentage distance. It is
the only price in the system and it never reaches a formula: `ScoringInputs` has no price
field and `tests/formulas/test_isolation.py` keeps it that way. Behind `SpotProvider` the
first adapter is Yahoo Finance through the `yfinance` package (`spot/yahoo.py`): the last
close on or before the run's day, one history call per asset. Stooq's daily CSV was the plan
(no key, one GET per symbol) but since 2026-09 its endpoint answers a JavaScript challenge
instead of the CSV, and Yahoo's chart endpoint refuses requests without the cookie-and-crumb
session that `yfinance` maintains. The per-source ticker lives in `config/assets.yaml`
(`spot: {yahoo: EURUSD=X}`), so switching to Alpha Vantage or Twelve Data is a new adapter
and a config edit. A ticker that fails is a warning, not a failed run.

## 5 · Index formula

The formula is expected to change, so it is kept apart from the rest of the application: the
package `manc.formulas` (in `src/manc/formulas/`) contains plain Python classes, one module per
formula version, and depends on nothing but the standard library and its own `contract.py`. It
owns the contract (what a formula receives and returns). The app only ever calls
`get_formula(config.formula).compute(inputs)`.

The contract is `src/manc/formulas/contract.py`: `ScoringInputs` (the asset spec, the
as-of time, weighted headline tags, released and upcoming event observations, and the
`params` from `config/scoring.yaml`), `IndexScore`, and the `IndexFormula` Protocol
(`name`, `compute(inputs) -> IndexScore`). `registry.py` maps a name to a formula class
(`"v1"` → `FormulaV1` in `v1.py`).

Rules that keep it decoupled: `manc.formulas` imports only the standard library and itself,
never `manc.models`, the store or anything else in the app (enforced by
`tests/formulas/test_isolation.py`); every formula is a pure function of `ScoringInputs`; every
stored score carries the formula name; a new formula is a new module (`v2.py`) plus a registry
entry, never an edit to `v1.py`. Since the app stores every input, `manc rescore --formula v2 --from 2026-09-01`
recomputes history so old and new can be plotted side by side before switching the default.
What a `v2` should contain is grounded in the literature survey in `docs/prior-art.md` and
planned as milestone M6 (§9).

### Formula v1

The score has three ingredients: what the news says (**N**), what the data did versus
expectations (**S**), and how much scheduled risk lies ahead (**R**). N and S give direction;
R only reduces conviction, pulling the score toward 50 when a heavy week is coming.

```
news sentiment
  N = Σᵢ dᵢ·cᵢ·wᵢ·λᵢ / Σᵢ cᵢ·wᵢ·λᵢ          λᵢ = 0.5^(ageᵢ / 48h), items within 72h

data surprise
  sₑ = clip((actual − consensus) / max(|consensus|, |previous|, ε), −1, 1) · sign(asset, category)
  S  = Σₑ sₑ·impₑ / Σₑ impₑ                  events released within 7d, imp ∈ {0.25, 0.5, 1}

event risk ahead
  R = min(1, Σ_upcoming impₑ / 4)            events in next 7d for the asset's economies

index
  raw   = 0.6·N + 0.4·S
  score = 50 + 50·raw·(1 − 0.5·R)
```

The formula receives raw `actual / consensus / previous` per released event and computes sₑ
itself; the surprise rule is part of what a version defines, so it is not split into a
separate module.

- `dᵢ, cᵢ` — direction (−1/0/+1) and confidence (0..1) the tagger assigned to headline *i* for this asset
- `wᵢ` — source weight from the feeds table
- `sign(asset, category)` — small YAML map: e.g. hot US inflation is +1 for USD pairs' dollar leg, −1 for gold, SPX, BTC; unknown pairs default to 0 (ignored)
- empty inputs — no relevant news → N = 0; no released events → S = 0; both empty → score = 50 exactly

Scale: 0–30 headwind · 30–45 lean against · 45–55 neutral · 55–70 lean for · 70–100 tailwind.

Worked example, EURUSD on a day with mildly euro-positive news (N = +0.3), a hot US CPI print
that hurts the euro (S = −0.5), and an ECB decision plus US payrolls next week (R = 0.5):

```
raw = 0.6·0.3 + 0.4·(−0.5) = −0.02  →  score = 50 + 50·(−0.02)·0.75 = 49.25
```

Why this shape: it is bounded by construction, it sits at 50 with no information, every term is
inspectable in the report, and the weights (0.6/0.4, half-life, shrink factor) are `params`
from `config/scoring.yaml` so they can be tuned without a new version. A structural change,
such as moving the surprise normaliser to a per-event z-score once history accumulates, is a
`v2`.

Also stored per day: the formula name, its components (N, S, R for v1) and counts. The
dashboard shows them under the score so a reader can tell whether 62 means "great data" or
"loud news".

## 6 · Storage

One SQLite file, `data/manc.db`, accessed through SQLAlchemy Core (tables, not an ORM) and
versioned with Alembic. `docs/er-schema.md` is the ER diagram, generated from `schema.py` by
paracelsus and kept current by a pre-commit hook.
`src/manc/store/schema.py` declares the tables and is the single source of truth; every
schema change is an Alembic revision generated from it:

```sh
uv run alembic upgrade head                       # bring the database to the current schema
uv run alembic revision --autogenerate -m "..."   # after editing schema.py; review the file
uv run alembic downgrade -1                       # step back one revision
```

The database URL comes from `MANC_DB_URL` (default `sqlite:///data/manc.db`), so moving to
Postgres is a URL change plus a driver. `manc run` and `manc api` refuse to start if the
database is not at `head`, so a forgotten upgrade fails loudly. A test compares `schema.py`
with the migrated database and fails on drift, so a schema edit without a revision cannot be
committed. Backup is still copying one file.

| Table             | Key                      | Columns                                                                          |
|-------------------|--------------------------|----------------------------------------------------------------------------------|
| `news`            | `id`                     | `source, title, url, published_at, summary, fetched_at`                          |
| `news_tags`       | `(news_id, asset)`       | `direction, confidence, model, prompt_version, tagged_at`                        |
| `calendar_events` | `id`                     | `date, country, event, category, importance, consensus, previous, actual, fetched_at` |
| `scores`          | `(asset, date, formula)` | `score, components_json, n_news, n_events, report_md, created_at`                |
| `forecasts_asset` | `id`                     | `institution, asset, horizon_date, horizon_label, value, published_at, source_url, source_kind, confidence, model, fetched_at` |
| `forecasts_macro` | `id`                     | `institution, economy, metric, horizon_date, horizon_label, value, published_at, source_url, source_kind, confidence, model, fetched_at` |
| `spot_prices`     | `(asset, date)`          | `close, source, fetched_at`                                                      |

Column types: timestamps are timezone-aware `DateTime`, `scores.date` is an ISO date string,
`components_json` is a JSON column. Re-running `manc run` for the same day overwrites that
day's row, so a bad run is fixed by running again. `formula` is part of the key so a rescore under `v2` sits next to the `v1` row
instead of replacing it; the dashboard defaults to the configured formula and can overlay
others. Forecast rows are never overwritten: an upsert on an existing id keeps the earlier
`published_at`, and a new value is a new id, so `forecasts_*` is a point-in-time record and
`as_of(date)` queries see only what was known that day.

## 7 · API and dashboard

The backend exposes a read-only REST API; the dashboard is a client of it and nothing more.
That contract is what makes the UI replaceable: a React app, a phone app or a Grafana panel
would consume the same routes, and the OpenAPI spec FastAPI generates is the documentation.

### Read-side logic: `queries.py`

Between rows in the store and JSON on the wire there is real logic: the delta versus yesterday,
the band label for a score, the 30-day sparkline window, the event-risk badge, the ordering of
the overview. It belongs neither in repositories (they only fetch) nor in route handlers (they
only parse and serialize). `src/manc/queries.py` holds it as plain functions over a `Store`
returning frozen dataclasses, tested with `FakeStore` and no HTTP:

```python
overview(store, config, as_of)                    -> list[AssetSummary]
asset_history(store, symbol, formula, start, end) -> AssetHistory
headlines_behind(store, symbol, as_of)            -> list[HeadlineView]
upcoming_events(store, config, start, end, min_importance) -> list[CalendarEvent]
forecasts_for(store, config, symbol, as_of, min_confidence) -> ForecastPanel
```

`ForecastPanel` carries the latest vintage per institution and horizon, its distance from the
latest spot, the previous vintage's value when there is one (a revision arrow in the UI), the
median across institutions per horizon, and the macro forecasts for the asset's economies.

The CLI and the report builder reuse the same functions, so a band label or a delta is
computed in exactly one place.

### REST API: `manc api`

FastAPI, `src/manc/api/`. Routes are thin: parse the request, call one query, return a
Pydantic response model. Read-only in v1; writes stay with the pipeline.

| Route                                                   | Returns                                                        |
|---------------------------------------------------------|----------------------------------------------------------------|
| `GET /api/v1/assets`                                    | tracked assets: symbol, kind, economies                        |
| `GET /api/v1/overview?as_of=`                           | per asset: score, band, delta, 30-day sparkline, event risk    |
| `GET /api/v1/assets/{symbol}/scores?formula=&from=&to=` | score series with components                                   |
| `GET /api/v1/assets/{symbol}/report?date=`              | that day's markdown report                                     |
| `GET /api/v1/assets/{symbol}/headlines?date=`           | headlines that moved the score, with direction and source      |
| `GET /api/v1/events?from=&to=&min_importance=`          | calendar events                                                |
| `GET /api/v1/assets/{symbol}/forecasts?as_of=&min_confidence=` | the forecast panel: latest vintage per institution and horizon, % vs spot, revisions, median; macro forecasts for the asset's economies |
| `GET /api/v1/assets/{symbol}/spot?from=&to=`            | daily closes, display only                                     |
| `GET /api/v1/macro/forecasts?economy=&metric=`          | macro and policy-rate forecasts across institutions            |
| `GET /api/v1/formulas`                                  | known formulas and the configured default                      |
| `GET /health`                                           | database at head, last run date                                |

Unknown asset → 404; malformed dates → 422 from validation. The store is injected through a
FastAPI dependency so tests run the app against `FakeStore`. `uv run manc api` serves it on
`localhost:8000`; `/docs` shows the OpenAPI UI.

### Dashboard: `manc ui`

Dash with Dash Mantine Components for layout and controls, Plotly for charts, `dash.pages` for
routing. No frontend build step. It lives in its own package, `src/manc_ui/`, which may import
`dash`, `plotly` and `httpx` but never `manc`; a test enforces that, the same way
`tests/formulas/test_isolation.py` guards the formulas. The only thing it knows about the
backend is `MANC_API_URL`. `src/manc_ui/client.py` wraps the routes above in typed functions.

- `/` — overview: one card per asset with today's score as a large number, a coloured band
  label, the delta from yesterday, a 30-day sparkline, and an event-risk badge; sorted by
  absolute distance from 50
- `/asset/<symbol>` — score history chart (shaded bands, 50 reference line, formula components
  as faint lines, markers on high-impact event days), date-range and formula selectors, today's
  report, upcoming high-impact events table, the headlines that moved the score with their
  direction and source, and a forecasts panel: one row per institution and horizon with the
  target, its distance from spot, a revision arrow, and a median row; the macro forecasts for
  the asset's economies underneath
- `/events` — the next 30 days of calendar events across all tracked economies, filterable by
  importance

Looking good, concretely:

- One Mantine theme (font, radius, spacing scale, primary colour) and one Plotly template
  derived from the same tokens, so charts and UI agree. Light and dark from Mantine's
  colour-scheme toggle, with the Plotly template switching alongside.
- Score colour is semantic and consistent everywhere: the bearish→bullish scale from §5 drives
  card accents, badges and the chart's band shading.
- Charts drawn with intent: area fill under the score, faint gridlines, emphasised last point
  with its value, hover showing the components, no default Plotly chrome (modebar hidden,
  margins tightened).
- Tabular numbers in every numeric column; skeleton loaders while a callback runs; responsive
  grid down to phone width.

`uv run manc ui` starts it on `localhost:8050`, pointed at `MANC_API_URL` (default
`http://localhost:8000`). `uv run manc serve` starts both processes for local convenience.

## 8 · Repo and tooling

```
manc/
├── pyproject.toml          # uv project; ruff + pytest config
├── .pre-commit-config.yaml # hygiene, ruff format, ruff check, pytest
├── alembic.ini
├── migrations/             # Alembic env.py + versions/
├── config/
│   ├── assets.yaml         # symbols, economies, sign map
│   ├── feeds.yaml          # RSS urls + weights
│   ├── scoring.yaml        # formula: v1, params (weights, half-life, windows)
│   ├── llm.yaml            # model string, fallback, temperature
│   ├── calendar.yaml       # event-name regexes → category and importance; country aliases
│   └── forecasts.yaml      # institutions with aliases, kind and weight; per-asset RSS queries; min_confidence
├── docs/blueprint.md       # this file
├── src/manc/
│   ├── models.py           # frozen dataclasses (§3)
│   ├── config.py
│   ├── formulas/           # stdlib only, never imports the rest of manc
│   │   ├── contract.py     # ScoringInputs, IndexScore, IndexFormula
│   │   ├── registry.py     # get_formula("v1")
│   │   └── v1.py           # class FormulaV1
│   ├── calendar/           # interface.py, nasdaq.py
│   ├── news/               # interface.py, rss.py
│   ├── llm.py              # the one LiteLLM call site: complete(config, messages, response_model)
│   ├── analysis/           # interface.py, llm.py (tagger), lexicon.py
│   ├── forecasts/          # interface.py, extractor.py (LiteLLM), fed_sep.py, worldbank.py
│   ├── spot/               # interface.py, yahoo.py
│   ├── scoring/            # adapter.py: store → ScoringInputs → formula
│   ├── store/              # interface.py, schema.py (tables), db.py (engine, upgrade), sql.py
│   ├── report/             # builder.py
│   ├── queries.py          # read-side logic over a Store, returns frozen dataclasses
│   ├── api/                # app.py (FastAPI), routes.py, schemas.py (Pydantic), deps.py
│   ├── pipeline.py
│   └── cli.py              # manc run | manc rescore | manc forecasts | manc api | manc ui | manc serve
├── src/manc_ui/            # Dash app; imports dash/plotly/httpx, never manc (test-enforced)
│   ├── app.py, theme.py, client.py
│   ├── pages/
│   └── components/
├── tests/                  # one folder per module + fixtures/; isolation tests for formulas and ui
└── data/                   # manc.db (gitignored; the folder is kept)
```

| Dependency                                        | Used for                                                              |
|---------------------------------------------------|-----------------------------------------------------------------------|
| `httpx`                                           | Nasdaq calendar endpoint, RSS fetching, forecast publishers, spot CSV |
| `openpyxl`                                        | World Bank outlook workbook                                           |
| `feedparser`                                      | RSS parsing                                                           |
| `litellm`, `pydantic`                             | forecast extraction, headline tagging and report summary, provider-agnostic; Pydantic for the response schema |
| `sqlalchemy`, `alembic`                           | store: Core tables and versioned migrations                            |
| `pyyaml`                                          | config files                                                          |
| `fastapi`, `uvicorn`, `pydantic`                  | REST API                                                              |
| `dash`, `dash-mantine-components`, `plotly`, `httpx` | dashboard (`manc_ui`)                                              |
| `pytest`, `pytest-cov`, `hypothesis`, `respx`, `ruff`, `pre-commit` | dev: tests, property tests, HTTP stubbing, coverage gate, lint and format, git hooks |

Secrets: the API-key env var of whichever provider `llm.model` names (`ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`, …); LiteLLM reads the standard one per provider, and a local Ollama model
needs none.

No hosted CI. `uv run pre-commit install` once after cloning installs the git hooks; from then
on every commit runs, in order: file hygiene checks (trailing whitespace, end-of-file,
YAML/TOML syntax, large files), `ruff format`, `ruff check --fix`, and `pytest` with the
coverage floor. A commit that fails any step is rejected. Hooks run through `uv run` so they
use the project environment, and `SKIP=pytest git commit` remains available for
work-in-progress commits on a branch.

Scheduling on the host: `0 6 * * 1-5 cd ~/quant/manc && uv run manc run`.

## 9 · Milestones

Six milestones, each shippable on its own. Every feature inside a milestone becomes a GitHub
issue when work on it starts, and each issue lists the tests to write before any
implementation. An issue is done when those tests pass through the pre-commit hook.

**M1 Skeleton** — done when: the pre-commit hooks pass on a clean checkout and `manc run`
prints 50 for every asset using fakes.
- uv project, Python 3.12 pinned, ruff, pre-commit hooks (hygiene, format, lint, pytest with
  coverage floor)
- `tests/fakes.py`: in-memory fakes for every Protocol, written together with the Protocols
- `manc.formulas`: contract, registry, isolation test and a `FormulaV1` stub returning 50
- models.py and every Protocol
- config loader for the YAML files
- SQLAlchemy Core schema, Alembic migrations and `MANC_DB_URL`, with migration tests
- `Store` protocol implementation with round-trip tests
- CLI with `run`, `rescore` and `serve` stubs

**M2 Ingestion** — done when: a run populates `news`, `calendar_events`, `forecasts_asset`,
`forecasts_macro` and `spot_prices` from live sources, and `manc forecasts --since` has
backfilled the forecasts panel for every asset.
- RSS provider with per-feed failure isolation and dedupe
- Nasdaq calendar provider with category, importance and country maps
- recorded fixtures for both
- forecast and spot models, Protocols, tables and fakes
- `config/forecasts.yaml` and the regex prefilter
- LLM forecast extractor through LiteLLM (the first LiteLLM call; brings `litellm` and
  `config/llm.yaml` wiring forward from M3), `manc forecasts --since` backfill
- `SpotProvider` with the Yahoo adapter and the no-price-in-formula isolation test
- Fed SEP and World Bank publishers with recorded fixtures; the pipeline runs every
  forecast provider
- the forecasts panel itself (query, route, page) belongs to M4

**M3 Analysis and index** — done when: real scores are written for all seven assets.
- LLM tagger through LiteLLM: Pydantic response schema, batching, configurable model with fallback;
  each tag stores `model` and `prompt_version` (needed by M6)
- lexicon fallback analyzer
- `FormulaV1` with property tests (news term, surprise term with the sign map, event-risk
  shrink); scoring adapter; `manc rescore`

**M4 Report, API and dashboard** — done when: every route in §7 answers from real data and the
dashboard shows the overview and per-asset history with today's report, in both themes, through
the API only.
- markdown report builder
- `queries.py` with unit tests
- FastAPI app: routes, Pydantic schemas, store dependency, `TestClient` tests, `manc api`
- `manc_ui` package with the isolation test and the typed API client
- Dash app shell: Mantine theme, Plotly template, light/dark
- overview page with asset cards and sparklines
- asset page with history chart, selectors, report, events, headlines
- events page; `manc ui` and `manc serve`

**M5 Operations** — done when: two weeks of daily scores exist without manual intervention.
- cron entry and README runbook
- run log and failure notification (stderr + exit code is enough)
- first tuning pass on weights using the accumulated scores

**M6 Formula v2** — done when: `manc rescore --formula v2` has replayed the whole stored
history, the dashboard overlays v1 and v2 for every asset, and the owner has picked the
default. Grounded in `docs/prior-art.md` (survey of 2026-09-16): every item below cites the
evidence for it. Starts only after M5 has accumulated about three months of scores and
released events, because the surprise normaliser needs history.

Prerequisite, done in M3 when the tagger lands: `news_tags` stores the `model` string and a
`prompt_version`, so tags produced by different models can be told apart when comparing
formulas (LLM labels carry model-specific bias, e.g. ChatGPT's documented dovish lean on
Fedspeak).

Candidates, in order of evidence. Each is a separate issue with its own property tests, and
each is a `params` switch so v2 can be run with any subset on:
- **Standardised surprise.** `sₑ = (actual − consensus) / σₑ`, where `σₑ` is the standard
  deviation of past surprises for that release, estimated from `calendar_events`. Falls back
  to the v1 normaliser while fewer than `min_history` observations exist. This is the
  Balduzzi–Elton–Green (2001) measure that the Citi surprise index and Scotti (2016) aggregate.
  Tests: comparable magnitudes across releases with different units; fallback below the
  history threshold; bounds and symmetry as in v1.
- **Novelty weighting.** The same story carried by several feeds currently counts once per
  URL. Cluster near-duplicate titles inside 24h and weight the k-th copy by a decaying
  sequence (RavenPack uses 1, .75, .56, .42, …). Tests: k copies of one headline never
  outweigh k distinct headlines; a single headline is unchanged.
- **Dispersion component.** Expose the spread of tag directions, `D = std(dᵢ·cᵢ)`, as a
  stored component next to N, S, R, and show it in the dashboard. Dispersion and
  volume-weighted impact were the most informative news features in the 2025 GDELT/FinBERT
  study on EURUSD, USDJPY and Treasuries; storing D costs nothing and lets a later version
  use it. Tests: D = 0 on unanimous tags, maximal on an even split.
- **Bad-news asymmetry.** A param `α ≥ 1` multiplying negative contributions in N and S;
  FX reacts more to bad surprises than to good ones (Andersen–Bollerslev–Diebold–Vega 2003).
  Tests: α = 1 reproduces the symmetric formula; the sign-flip symmetry test becomes
  "score(−x) ≤ 100 − score(x)".
- **Decayed surprise window.** Replace the hard 7-day cut on S with the same half-life decay
  used for N, over a longer window (Citi uses a decayed three-month window). Tests: monotone
  in age; equals v1 at the boundary.
- **Coarse confidence.** Bucket `cᵢ` to three levels before weighting. LLM verbalised
  confidence is over-confident and poorly calibrated, and identical runs can differ by up to
  10%, so a continuous weight suggests precision the tagger does not have. Tests: bucketing
  is monotone and idempotent.

Evaluation, since the index is not a predictor:
- agreement with a hand-rated sample of about 100 tags (the human-benchmark recipe of
  Mavillonio et al. 2026); disagreement rate stored in the issue, not in the database
- v1 and v2 plotted side by side over the replayed history; the report for each day lists
  both and the components that differ
- any return-based sanity check uses only dates after the tagging model's training cutoff,
  and history is never backfilled through the tagger (LLM look-ahead bias); rescoring stored
  tags is safe

## 10 · Decisions taken

Choices made to keep the system small. Any of them can be revisited; none of them are
load-bearing enough to block a start.

- **SQLite, not Postgres — but through SQLAlchemy Core and Alembic.** One user, one writer per
  day, one file; the schema is versioned from day one and the engine is a URL change away.
- **Cron, not a scheduler library.** The run is idempotent, so a missed run is just re-run.
- **An LLM for tagging, not a keyword list.** Tagging quality is the biggest driver of N; the
  cost is cents per day.
- **LiteLLM, not a hand-rolled provider adapter.** One dependency covers every provider; the
  model is a config string and the code never sees provider-specific parameters.
- **Nasdaq's calendar endpoint directly, not through OpenBB.** The OpenBB fetcher wraps the
  same URL but loses Fridays and mislabels times (§4) while adding 52 packages; a 100-line
  module over httpx with recorded fixtures is both smaller and correct.
- **No price data in the score.** The index measures narrative and data, and stays explainable.
  One daily close per asset is stored for display next to forecasts, and a test keeps it out
  of `ScoringInputs`.
- **Forecasts are extracted from headlines, not licensed.** No free structured source covers
  the FX pairs, SPX or BTC; bank calls are public only as news. An LLM extraction over feeds
  already ingested covers every asset, stores every vintage, and the few structured
  publishers (Fed SEP, World Bank) sit behind the same Protocol. Display only until M6
  has evidence for a formula term.
- **REST API between backend and UI.** The dashboard is one client of `manc api` and lives in
  a package that cannot import the backend. Any future UI consumes the same OpenAPI contract;
  the price is a second process.
- **`queries.py` for read-side logic.** Bands, deltas, sparklines and ordering are computed in
  one place, as plain functions, tested without HTTP; routes and pages stay thin.
- **Dash with Mantine components.** Real routing and Plotly first-class, no JS build step, and
  a component library that looks finished out of the box.
- **Git hooks instead of hosted CI.** pre-commit runs format, lint and the test suite before
  every commit; nothing leaves the machine unchecked and there is no workflow file to maintain.
- **Test-driven throughout.** Tests are written before the code they test; the fakes for every
  Protocol are part of the skeleton so nothing waits on a live source to be testable.
- **Formula as a plain Python class in its own subpackage.** It will change; keeping
  `manc.formulas` dependency-free (a test enforces it) and versioned means a change is a new
  file, and stored inputs make history replayable. No separate distribution: one repo, one
  package, one rule.
- **v2 is evidence-driven, not a rewrite.** Each change to the formula is a candidate with a
  cited reason and its own switch in `params` (§9, M6), so the owner can compare v1 against
  v2 with any subset on before changing the default.
- **Single process, synchronous.** A dozen feeds and a few API calls finish in under a minute.
