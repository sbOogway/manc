# The backend image: the REST API by default, `manc run` for a scheduled run.
# Build and start with `podman compose up -d --build` (Docker reads this file too).
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv

ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    MANC_API_HOST=0.0.0.0 \
    MANC_DB_URL=sqlite:////data/manc.db

WORKDIR /app
# dependencies first, so a source change does not rebuild them
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY src ./src
COPY config ./config
COPY migrations ./migrations
COPY scripts/container-entrypoint.sh ./scripts/
RUN uv sync --frozen --no-dev

VOLUME /data
EXPOSE 8000
ENTRYPOINT ["sh", "scripts/container-entrypoint.sh"]
CMD ["manc", "api"]
