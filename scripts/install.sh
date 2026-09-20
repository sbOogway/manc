#!/usr/bin/env sh
# Set manc up on this machine from nothing, or bring an existing install up to date:
#   curl -fsSL https://raw.githubusercontent.com/sbOogway/manc/main/scripts/install.sh | sh
# Clones (or fast-forwards) ~/quant/manc, the path the systemd units expect, installs the
# environment, hooks, database, dashboard and the API container, and enables the units. The
# one thing left to you is editing .env. Safe to run again at any time.
set -eu

repo=${MANC_REPO:-https://github.com/sbOogway/manc.git}
dir=$HOME/quant/manc
export PATH="$HOME/.local/bin:$PATH"

missing=""
for tool in git npm podman claude; do
  command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
done
if [ -n "$missing" ]; then
  echo "install: missing$missing; install them and run this again" >&2
  echo "install: claude is Claude Code (npm install -g @anthropic-ai/claude-code, then claude login)" >&2
  exit 1
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "install: uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  command -v uv >/dev/null 2>&1 || { echo "install: uv did not install" >&2; exit 1; }
fi

if [ -d "$dir/.git" ]; then
  echo "install: updating $dir"
  git -C "$dir" pull -q --ff-only origin main
else
  echo "install: git clone $repo $dir"
  mkdir -p "$(dirname "$dir")"
  git clone -q "$repo" "$dir"
fi
cd "$dir"

uv sync --frozen
uv run pre-commit install --hook-type pre-commit --hook-type post-merge
uv run alembic upgrade head
npm --prefix site ci
npm --prefix site run build

if [ ! -f .env ]; then
  cp .env.example .env
  echo "install: wrote .env from .env.example"
fi

podman compose build
sh scripts/install-systemd.sh
systemctl --user restart manc-api.service
curl -sf http://127.0.0.1:8000/api/v1/assets >/dev/null && echo "install: API answers on http://127.0.0.1:8000" \
  || echo "install: API not answering yet; check journalctl --user -u manc-api" >&2

echo "install: done. Now edit $dir/.env (keys, MANC_API_BIND) and, if you changed it, run:"
echo "  systemctl --user restart manc-api.service"
