# manc — macro analysis, news and calendar

**Project blueprint, draft 8 (2026-09-15).** Styled render: https://claude.ai/artifact/LqZ6Yg7nVfTK46zYEJUShz
This file is the source of truth; update it when a decision changes.

A small daily pipeline that reads the economic calendar and trusted news feeds, scores each
tracked asset 0–100, stores the score, and plots it.

Stack: Python 3.12 · uv · pytest, TDD · pre-commit · LiteLLM · Dash · SQLite via SQLAlchemy Core + Alembic · OpenBB.

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
| WTI    | commodity    | United States, OPEC headlines             |
| SPX    | equity index | United States                             |
| BTCUSD | crypto       | United States (liquidity, risk appetite)  |

What it is **not**: a price predictor or a trading signal. It measures the macro narrative and
data flow, which is one input among many. Prices are deliberately not part of the score so it
stays interpretable.

## 2 · Daily pipeline

One command, five steps, each behind an interface so it can be swapped or faked in tests.

| Step | Name           | What                                                        | Module          |
|------|----------------|-------------------------------------------------------------|-----------------|
| 01   | Fetch calendar | Next 30 days of events, plus last 7 days with actuals.      | `calendar/`     |
| 02   | Fetch news     | Pull every RSS feed, dedupe by URL, keep last 72h.          | `news/`         |
| 03   | Analyse        | Tag headlines to assets with a direction.                   | `analysis/`     |
| 04   | Score          | Hand the inputs to the configured formula: 0–100 out. No I/O.| `formulas/`     |
| 05   | Store + report | Write score, components and markdown report to SQLite.      | `store/` `report/` |

The web server is a separate process (`manc serve`) that only reads the database. Scheduling is
a plain cron entry; no queue, no workers, no orchestrator. Because every input to step 04 is
stored, `manc rescore --formula v2` can replay history under a new formula without refetching
anything.

## 3 · Modules and interfaces

Each module exposes one `typing.Protocol` and a set of frozen dataclasses in `manc/models.py`.
Everything else in the module is private. Tests for a module never touch the network: providers
are exercised against recorded fixtures, LLM calls are stubbed at the `litellm.completion`
boundary, and the pipeline is tested with in-memory fakes of each protocol.

| Module     | Interface                                                                 | Default implementation                                                  | Tests cover                                                          |
|------------|---------------------------------------------------------------------------|-------------------------------------------------------------------------|----------------------------------------------------------------------|
| `calendar` | `CalendarProvider.fetch(start, end) -> list[CalendarEvent]`               | OpenBB, Nasdaq provider (free, no key)                                  | parsing, importance mapping, date windows                            |
| `news`     | `NewsProvider.fetch(since) -> list[NewsItem]`                             | feedparser over `config/feeds.yaml`                                     | parsing, dedupe, per-feed failure isolation                          |
| `analysis` | `Analyzer.tag(items, assets) -> list[NewsTag]`                            | LiteLLM `completion()` with a Pydantic response schema, model from config | fake analyzer; batching; schema validation                           |
| `formulas` | `get_formula(name) -> IndexFormula`; `IndexFormula.compute(ScoringInputs) -> IndexScore` | plain Python classes, one per version, standard library only (§5) | property tests on every formula; an isolation test that the package imports nothing else from `manc` |
| `scoring`  | `build_inputs(store, asset, as_of, params) -> ScoringInputs` | thin adapter from the store to the formula contract | adapter builds inputs correctly |
| `store`    | Repository pattern: `Store` composes `news`, `tags`, `events`, `scores` repositories, each with `add()` and named queries (`since`, `tagged`, `between`, `series`) | SQLAlchemy Core over SQLite; schema in `schema.py`, Alembic migrations | round-trips, idempotent upserts; migrations reach `head` and match `schema.py` |
| `report`   | `build_report(asset, score, tags, events) -> str`                         | Markdown, summary paragraph written by the configured LLM               | template output with fake analyzer                                   |
| `web`      | Dash app                                                                  | Dash + Mantine components + Plotly (§7)                                 | layouts render, callbacks return expected figures with a seeded DB   |
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
| `web`               | callback functions tested directly (they are plain functions) plus one smoke test per page that the layout renders with a seeded store; visual quality is reviewed manually by the owner, not by automated screenshots | seeded SQLite in a fixture |

Coverage is not a target on its own, but pytest is configured to fail below 85% so untested
code cannot sneak in. Live-network tests exist for the
real RSS feeds and the OpenBB calendar; they are marked `@pytest.mark.live`, skipped by default
and run manually before a release.

Enforcement is local, not hosted: there is no GitHub Actions workflow. A `pre-commit`
configuration runs on every commit and blocks it if anything fails.

### Core dataclasses

```python
@dataclass(frozen=True)
class CalendarEvent:
    id: str  # provider id or hash(date, country, event)
    date: datetime  # UTC
    country: str  # "united_states"
    event: str  # "Consumer Price Index (YoY)"
    category: str  # inflation | employment | growth | rates | ...
    importance: int  # 1 low, 2 medium, 3 high
    consensus: float | None
    previous: float | None
    actual: float | None


@dataclass(frozen=True)
class NewsItem:
    id: str  # sha1(url)
    source: str  # "reuters", "cnbc", "ecb"
    title: str
    url: str
    published_at: datetime
    summary: str  # feed summary, HTML stripped


@dataclass(frozen=True)
class NewsTag:
    news_id: str
    asset: str
    direction: int  # -1 bearish, 0 neutral/irrelevant, +1 bullish
    confidence: float  # 0..1


@dataclass(frozen=True)
class IndexScore:  # defined in manc.formulas.contract, re-exported here
    asset: str
    date: date
    score: float  # 0..100
    formula: str  # "v1"
    components: dict[str, float]  # whatever the formula wants to expose, e.g. N, S, R
    n_news: int
    n_events: int
```

## 4 · Data sources

### Economic calendar → OpenBB

`obb.economy.calendar(provider="nasdaq")` needs no API key and returns
`date, country, event, importance, consensus, previous, actual`. That is everything the score
needs. FMP and TradingEconomics are also wired into OpenBB but need keys; keep them as optional
fallbacks. We can depend on just `openbb-nasdaq` and call its fetcher directly rather than
installing the full `openbb` meta-package.

Nasdaq's feed has no `category`; a small regex map in config turns event names into categories
(`CPI|PPI|PCE → inflation`, `Nonfarm|Unemployment|Claims → employment`,
`GDP|PMI|Retail → growth`, `Rate Decision|FOMC|Minutes → rates`).

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

All model calls go through LiteLLM's `completion()`, so the model is a single string in
`config/llm.yaml` and switching providers is a config edit plus the provider's API-key env var:

```yaml
llm:
  model: anthropic/claude-opus-5     # default
  # model: openai/gpt-5
  # model: ollama/llama3.3           # local, no key
  # model: openrouter/deepseek/deepseek-chat
  fallback: null                     # optional second model tried on error
  temperature: 0
```

The response schema is a Pydantic model passed as `response_format`; LiteLLM translates it to
each provider's native structured-output mechanism (Anthropic, OpenAI, Ollama, Groq, Gemini,
Bedrock all support it) and `litellm.enable_json_schema_validation = True` validates
client-side for the ones that don't. Provider-specific parameters never appear in our code. A
lexicon-based `Analyzer` stays available as an offline fallback and as the test double.

## 5 · Index formula

The formula is expected to change, so it is kept apart from the rest of the application: the
package `manc.formulas` (in `src/manc/formulas/`) contains plain Python classes, one module per
formula version, and depends on nothing but the standard library and its own `contract.py`. It
owns the contract (what a formula receives and returns). The app only ever calls
`get_formula(config.formula).compute(inputs)`.

```python
# manc/formulas/contract.py  — the only thing the app depends on
@dataclass(frozen=True)
class ScoringInputs:
    asset: AssetSpec  # symbol, kind, economies, sign map
    as_of: datetime
    tags: list[NewsTag]  # with source weight + published_at attached
    released: list[CalendarEvent]  # events with actual != None in lookback
    upcoming: list[CalendarEvent]  # events in the look-ahead window
    params: dict[str, float]  # from config/scoring.yaml


class IndexFormula(Protocol):
    name: str  # "v1"

    def compute(self, inputs: ScoringInputs) -> IndexScore: ...


# manc/formulas/v1.py  — a plain class, no framework
class FormulaV1:
    name = "v1"

    def compute(self, inputs: ScoringInputs) -> IndexScore: ...


# manc/formulas/registry.py
def get_formula(name: str) -> IndexFormula: ...  # "v1" → FormulaV1()
```

Rules that keep it decoupled: `manc.formulas` imports only the standard library and itself,
never `manc.models`, the store or anything else in the app (enforced by
`tests/formulas/test_isolation.py`); every formula is a pure function of `ScoringInputs`; every
stored score carries the formula name; a new formula is a new module (`v2.py`) plus a registry
entry, never an edit to `v1.py`. Since the app stores every input, `manc rescore --formula v2 --from 2026-09-01`
recomputes history so old and new can be plotted side by side before switching the default.

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
versioned with Alembic. `src/manc/store/schema.py` declares the tables and is the single
source of truth; every schema change is an Alembic revision generated from it:

```sh
uv run alembic upgrade head                       # bring the database to the current schema
uv run alembic revision --autogenerate -m "..."   # after editing schema.py; review the file
uv run alembic downgrade -1                       # step back one revision
```

The database URL comes from `MANC_DB_URL` (default `sqlite:///data/manc.db`), so moving to
Postgres is a URL change plus a driver. `manc run` and `manc serve` refuse to start if the
database is not at `head`, so a forgotten upgrade fails loudly. A test compares `schema.py`
with the migrated database and fails on drift, so a schema edit without a revision cannot be
committed. Backup is still copying one file.

| Table             | Key                      | Columns                                                                          |
|-------------------|--------------------------|----------------------------------------------------------------------------------|
| `news`            | `id`                     | `source, title, url, published_at, summary, fetched_at`                          |
| `news_tags`       | `(news_id, asset)`       | `direction, confidence, tagged_at`                                               |
| `calendar_events` | `id`                     | `date, country, event, category, importance, consensus, previous, actual, fetched_at` |
| `scores`          | `(asset, date, formula)` | `score, components_json, n_news, n_events, report_md, created_at`                |

Column types: timestamps are timezone-aware `DateTime`, `scores.date` is an ISO date string,
`components_json` is a JSON column. Re-running `manc run` for the same day overwrites that
day's row, so a bad run is fixed by running again. `formula` is part of the key so a rescore under `v2` sits next to the `v1` row
instead of replacing it; the dashboard defaults to the configured formula and can overlay
others.

## 7 · Dashboard

Dash with Dash Mantine Components for layout and controls, Plotly for charts, `dash.pages` for
routing. No frontend build step. The app reads through the `Store` protocol only; it never
touches SQLite directly.

- `/` — overview: one card per asset with today's score as a large number, a coloured band
  label, the delta from yesterday, a 30-day sparkline, and an event-risk badge; sorted by
  absolute distance from 50
- `/asset/<symbol>` — score history chart (shaded bands, 50 reference line, formula components
  as faint lines, markers on high-impact event days), date-range and formula selectors, today's
  report, upcoming high-impact events table, the headlines that moved the score with their
  direction and source
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

`uv run manc serve` starts it on `localhost:8050`.

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
│   └── llm.yaml            # model string, fallback, temperature
├── docs/blueprint.md       # this file
├── src/manc/
│   ├── models.py           # frozen dataclasses (§3)
│   ├── config.py
│   ├── formulas/           # stdlib only, never imports the rest of manc
│   │   ├── contract.py     # ScoringInputs, IndexScore, IndexFormula
│   │   ├── registry.py     # get_formula("v1")
│   │   └── v1.py           # class FormulaV1
│   ├── calendar/           # interface.py, openbb.py
│   ├── news/               # interface.py, rss.py
│   ├── analysis/           # interface.py, llm.py, lexicon.py
│   ├── scoring/            # adapter.py: store → ScoringInputs → formula
│   ├── store/              # interface.py, schema.py (tables), db.py (engine, upgrade), sql.py
│   ├── report/             # builder.py
│   ├── web/                # app.py, theme.py, pages/, components/
│   ├── pipeline.py
│   └── cli.py              # manc run | manc rescore | manc serve
├── tests/                  # one folder per module + fixtures/; formulas/ has the isolation test
└── data/                   # manc.db (gitignored; the folder is kept)
```

| Dependency                                        | Used for                                                              |
|---------------------------------------------------|-----------------------------------------------------------------------|
| `openbb-nasdaq`                                   | economic calendar (pulls in openbb-core)                              |
| `feedparser`, `httpx`                             | RSS fetching and parsing                                              |
| `litellm`, `pydantic`                             | headline tagging and report summary, provider-agnostic; Pydantic for the response schema |
| `sqlalchemy`, `alembic`                           | store: Core tables and versioned migrations                            |
| `pyyaml`                                          | config files                                                          |
| `dash`, `dash-mantine-components`, `plotly`, `pandas` | dashboard                                                         |
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

Five milestones, each shippable on its own. Every feature inside a milestone becomes a GitHub
issue when work on it starts, and each issue lists the tests to write before any
implementation. An issue is done when those tests pass through the pre-commit hook.

**M1 Skeleton** — done when: the pre-commit hooks pass on a clean checkout and `manc run`
prints 50 for every asset using fakes.
- uv project, Python 3.12 pinned, ruff, pre-commit hooks (hygiene, format, lint, pytest with
  coverage floor)
- `tests/fakes.py`: in-memory fakes for every Protocol, written together with the Protocols
- `manc.formulas`: contract, registry, isolation test and a `FormulaV1` stub returning 50
- models.py and every Protocol
- config loader for the four YAML files
- SQLAlchemy Core schema, Alembic migrations and `MANC_DB_URL`, with migration tests
- `Store` protocol implementation with round-trip tests
- CLI with `run`, `rescore` and `serve` stubs

**M2 Ingestion** — done when: a run populates `news` and `calendar_events` from live sources.
- RSS provider with per-feed failure isolation and dedupe
- OpenBB calendar provider with category mapping
- recorded fixtures for both

**M3 Analysis and index** — done when: real scores are written for all seven assets.
- LLM tagger through LiteLLM: Pydantic response schema, batching, configurable model with fallback
- lexicon fallback analyzer
- `FormulaV1` with property tests (news term, surprise term with the sign map, event-risk
  shrink); scoring adapter; `manc rescore`

**M4 Report and web** — done when: the dashboard shows the overview and per-asset history with
today's report, in both themes.
- markdown report builder
- Dash app shell: Mantine theme, Plotly template, light/dark
- overview page with asset cards and sparklines
- asset page with history chart, selectors, report, events, headlines
- events page

**M5 Operations** — done when: two weeks of daily scores exist without manual intervention.
- cron entry and README runbook
- run log and failure notification (stderr + exit code is enough)
- first tuning pass on weights using the accumulated scores

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
- **No price data in the score.** The index measures narrative and data, and stays explainable.
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
- **Single process, synchronous.** A dozen feeds and a few API calls finish in under a minute.
