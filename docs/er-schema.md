# Database schema

Generated from `src/manc/store/schema.py` by [paracelsus](https://github.com/tedivm/paracelsus);
a pre-commit hook rejects a commit that changes the schema without regenerating this file:

```sh
uv run paracelsus inject docs/er-schema.md
```

What the columns mean is in `docs/blueprint.md` section 6. The `asset` columns hold symbols
from `config/assets.yaml`; the only foreign key is `news_tags.news_id -> news.id`.

<!-- BEGIN_SQLALCHEMY_DOCS -->
```mermaid
erDiagram
  calendar_events {
    VARCHAR(64) id PK
    DATETIME date
    VARCHAR(64) country
    TEXT event
    VARCHAR(32) category
    INTEGER importance
    FLOAT consensus "nullable"
    FLOAT previous "nullable"
    FLOAT actual "nullable"
    DATETIME fetched_at
  }

  chain_metrics {
    VARCHAR(16) asset PK
    DATE date PK
    VARCHAR(32) metric PK
    FLOAT value
    VARCHAR(32) source
    DATETIME fetched_at
  }

  forecasts_asset {
    VARCHAR(40) id PK
    VARCHAR(64) institution
    VARCHAR(16) asset
    DATE horizon_date
    VARCHAR(64) horizon_label
    FLOAT value
    DATETIME published_at
    TEXT source_url
    VARCHAR(16) source_kind
    FLOAT confidence
    VARCHAR(128) model
    DATETIME fetched_at
  }

  forecasts_macro {
    VARCHAR(40) id PK
    VARCHAR(64) institution
    VARCHAR(64) economy
    VARCHAR(32) metric
    DATE horizon_date
    VARCHAR(64) horizon_label
    FLOAT value
    DATETIME published_at
    TEXT source_url
    VARCHAR(16) source_kind
    FLOAT confidence
    VARCHAR(128) model
    DATETIME fetched_at
  }

  news {
    VARCHAR(40) id PK
    VARCHAR(64) source
    TEXT title
    TEXT url
    DATETIME published_at
    TEXT summary
    DATETIME fetched_at
    DATETIME analyzed_at "nullable"
  }

  news_tags {
    VARCHAR(40) news_id PK,FK
    VARCHAR(16) asset PK
    INTEGER direction
    FLOAT confidence
    VARCHAR(128) model
    VARCHAR(16) prompt_version
    DATETIME tagged_at
  }

  scores {
    VARCHAR(16) asset PK
    VARCHAR(10) date PK
    VARCHAR(16) formula PK
    FLOAT score
    JSON components_json
    INTEGER n_news
    INTEGER n_events
    TEXT report_md
    DATETIME created_at
  }

  spot_prices {
    VARCHAR(16) asset PK
    DATE date PK
    FLOAT close
    VARCHAR(32) source
    DATETIME fetched_at
  }

  news ||--o| news_tags : news_id

```
<!-- END_SQLALCHEMY_DOCS -->
