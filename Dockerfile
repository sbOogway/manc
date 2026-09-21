# The manc image: the application with its locked dependencies, plus `claude` for the tagger
# and supercronic for the schedule. `api` and `cron` in compose.yaml run it; the login for
# claude lives in the volume at CLAUDE_CONFIG_DIR (`docker compose run --rm api claude`, once).
FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.11.11 /uv /usr/local/bin/uv
ARG SUPERCRONIC=https://github.com/aptible/supercronic/releases/download/v0.2.49/supercronic-linux-amd64
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL -o /usr/local/bin/supercronic "$SUPERCRONIC" && chmod 755 /usr/local/bin/supercronic \
    && useradd -r -m -d /var/lib/manc -s /usr/sbin/nologin manc \
    && mkdir /claude && chown manc:manc /claude

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md LICENSE ./
COPY src ./src
COPY crontab ./crontab
RUN uv sync --frozen --no-dev && chown -R manc:manc /app

USER manc
RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH=/app/.venv/bin:/var/lib/manc/.local/bin:/usr/local/bin:/usr/bin:/bin
ENV CLAUDE_CONFIG_DIR=/claude DISABLE_AUTOUPDATER=1
ENV MANC_DB_URL=sqlite:////var/lib/manc/manc.db MANC_API_HOST=0.0.0.0 MANC_API_PORT=8888
WORKDIR /var/lib/manc
CMD ["manc", "api"]
