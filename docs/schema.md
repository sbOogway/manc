# manc — database schema

Entity-relationship view of `data/manc.db` as declared in `src/manc/store/schema.py`
(Alembic head `9bbb45ea6917`). The blueprint, section 6, explains the write rules; this page
only draws the tables. Keep it in step with `schema.py`: a new revision means an edit here.

```mermaid
erDiagram
    news {
        string id PK "sha1(url), 40"
        string source "64"
        text title
        text url
        datetime published_at "tz-aware"
        text summary "default ''"
        datetime fetched_at
    }

    news_tags {
        string news_id PK, FK "-> news.id, on delete cascade"
        string asset PK "16"
        int direction "-1 | 0 | +1"
        float confidence "0..1"
        datetime tagged_at
    }

    calendar_events {
        string id PK "sha1(date|country|event|ordinal), 64"
        datetime date "UTC"
        string country "64, e.g. united_states"
        text event
        string category "32: inflation | employment | growth | rates | other"
        int importance "1 | 2 | 3"
        float consensus "nullable"
        float previous "nullable"
        float actual "nullable"
        datetime fetched_at
    }

    scores {
        string asset PK "16"
        string date PK "ISO date, 10"
        string formula PK "16, e.g. v1"
        float score "0..100"
        json components_json "e.g. N, S, R"
        int n_news
        int n_events
        text report_md "default ''"
        datetime created_at
    }

    forecasts_asset {
        string id PK "sha1(institution|asset|horizon_date|value), 40"
        string institution "64"
        string asset "16"
        date horizon_date
        string horizon_label "64, as stated"
        float value
        datetime published_at "earliest sighting"
        text source_url
        string source_kind "16: extracted | structured"
        float confidence "0..1"
        string model "128, '' for structured"
        datetime fetched_at
    }

    forecasts_macro {
        string id PK "sha1(institution|economy:metric|horizon_date|value), 40"
        string institution "64"
        string economy "64"
        string metric "32: policy_rate | cpi | gdp | unemployment"
        date horizon_date
        string horizon_label "64"
        float value
        datetime published_at
        text source_url
        string source_kind "16"
        float confidence "0..1"
        string model "128"
        datetime fetched_at
    }

    spot_prices {
        string asset PK "16"
        date date PK
        float close
        string source "32, e.g. stooq"
        datetime fetched_at
    }

    news ||--o{ news_tags : "tagged for an asset"
```

## Reading the diagram

- **The only foreign key is `news_tags.news_id → news.id`** (cascade on delete). Every other
  table stands alone by design: a rescore or a forecast backfill never has to satisfy a
  constraint against another table.
- **`asset`, `country` / `economy` and `institution` are config keys, not tables.**
  `scores.asset`, `news_tags.asset`, `forecasts_asset.asset` and `spot_prices.asset` hold a
  symbol from `config/assets.yaml`; `calendar_events.country` and `forecasts_macro.economy`
  hold an economy key from the same file; `institution` comes from `config/forecasts.yaml`.
  They are joined in `queries.py`, not in SQL.
- **Composite keys encode the write rules.** `scores` is `(asset, date, formula)`, so a `v2`
  rescore sits next to the `v1` row; `spot_prices` is `(asset, date)` and a re-run overwrites
  the close; the two forecast tables key on the vintage hash and never overwrite, an upsert on
  an existing id only keeps the earlier sighting.
- **Timestamps** are timezone-aware `DateTime` stored as UTC; SQLite drops the zone, the
  store puts it back on read. `scores.date` is an ISO string; `horizon_date` and
  `spot_prices.date` are `Date` columns.
- `alembic_version` is omitted. Revisions so far: `d90ed1931246` initial, `9bbb45ea6917`
  forecasts and spot prices.
