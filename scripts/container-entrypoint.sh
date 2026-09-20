#!/usr/bin/env sh
# Container entrypoint: bring the database to the current schema, then run the command
# (`manc api` by default, `manc run` for a daily run inside the container).
set -eu
alembic upgrade head
exec "$@"
