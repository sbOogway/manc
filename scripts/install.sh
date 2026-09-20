#!/usr/bin/env sh
# Install manc system-wide, or bring an install up to date. Run as root from your own account:
#   curl -fsSL https://raw.githubusercontent.com/sbOogway/manc/main/scripts/install.sh | sudo sh
# A dedicated `manc` user owns the code in /opt/manc and runs the API container with rootless
# podman (its own user units, linger on); the database sits in /var/lib/manc/data, writable by
# manc and by you, because the daily run stays on the host with your Claude Code login (a
# system unit running as you). The env file /etc/manc/env is the one thing left to edit.
# Safe to run again at any time: it pulls main and redeploys.
set -eu

repo=${MANC_REPO:-https://github.com/sbOogway/manc.git}
root=${MANC_ROOT:-}            # a prefix standing in for /, used by the tests
owner=${MANC_OWNER:-${SUDO_USER:-}}
user=manc
opt=$root/opt/manc
lib=$root/var/lib/manc
etc=$root/etc/manc
system_units=$root/etc/systemd/system
user_units=$lib/.config/systemd/user

[ "$(id -u)" -eq 0 ] || { echo "install: run me as root: curl ... | sudo sh" >&2; exit 1; }
[ -n "$owner" ] || { echo "install: which user runs the daily run? sudo keeps it in SUDO_USER; else set MANC_OWNER" >&2; exit 1; }

missing=""
for tool in git podman setfacl; do
  command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
done
if [ -n "$missing" ]; then
  echo "install: missing$missing; install them and run this again" >&2
  exit 1
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "install: uv into /usr/local/bin"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
  command -v uv >/dev/null 2>&1 || { echo "install: uv did not install" >&2; exit 1; }
fi

# the service user: system account, home under /var/lib, a subordinate id range for rootless
# podman (system accounts get none by default), linger so its units run without a session
if ! getent passwd $user >/dev/null 2>&1; then
  echo "install: user $user"
  useradd -r -m -d /var/lib/manc -s /usr/sbin/nologin $user
  start=$(awk -F: 'BEGIN { max = 100000 } $3 + 0 > 0 { end = $2 + $3; if (end > max) max = end } END { print max }' "$root/etc/subuid" 2>/dev/null || echo 100000)
  usermod --add-subuids "$start-$((start + 65535))" --add-subgids "$start-$((start + 65535))" $user
fi
uid=$(id -u $user)
loginctl enable-linger $user
usermod -aG $user "$owner"

mkdir -p "$opt" "$lib/data" "$etc" "$user_units" "$system_units"
chown $user:$user "$opt" "$lib" "$lib/data" "$user_units"
chmod 2770 "$lib/data"                               # group manc writes; new files inherit the group
setfacl -d -m "g:$user:rwx" "$lib/data"              # ...and are group-writable whatever the umask

as_manc() { sudo -u $user env HOME=/var/lib/manc XDG_RUNTIME_DIR=/run/user/$uid "$@"; }

if [ -d "$opt/.git" ]; then
  echo "install: updating $opt"
  as_manc git -C "$opt" pull -q --ff-only origin main
else
  echo "install: git clone $repo $opt"
  as_manc git clone -q "$repo" "$opt"
fi

if [ ! -f "$etc/env" ]; then
  sed 's|^MANC_DATA_DIR=.*|MANC_DATA_DIR=/var/lib/manc/data|' "$opt/.env.example" > "$etc/env"
  echo "install: wrote $etc/env from .env.example"
fi
chown root:$user "$etc/env"
chmod 0640 "$etc/env"
ln -sfn /etc/manc/env "$opt/.env"                    # compose reads .env next to compose.yaml

cd "$opt"
as_manc uv sync --frozen
as_manc env MANC_DB_URL=sqlite:////var/lib/manc/data/manc.db uv run alembic upgrade head
as_manc podman compose build

# the container as manc's user units; the daily run as a system unit running as the owner
cp systemd/manc-api.service systemd/manc-fetch.service systemd/manc-fetch.timer "$user_units/"
chown $user:$user "$user_units"/*
as_manc systemctl --user daemon-reload
as_manc systemctl --user enable --now manc-api.service
as_manc systemctl --user enable --now manc-fetch.timer
as_manc systemctl --user restart manc-api.service    # pick up a rebuilt image
sed "s|@OWNER@|$owner|g" systemd/manc-run.service > "$system_units/manc-run.service"
cp systemd/manc-run.timer "$system_units/"
systemctl daemon-reload
systemctl enable --now manc-run.timer

curl -sf http://127.0.0.1:8000/api/v1/assets >/dev/null && echo "install: API answers on http://127.0.0.1:8000" \
  || echo "install: API not answering yet; check: sudo -u manc XDG_RUNTIME_DIR=/run/user/$uid journalctl --user -u manc-api" >&2

echo "install: done. Edit /etc/manc/env (keys, MANC_API_BIND), then:"
echo "  sudo -u manc XDG_RUNTIME_DIR=/run/user/$uid systemctl --user restart manc-api.service"
echo "  sudo systemctl start manc-run.service        # a daily run by hand; journalctl -u manc-run"
