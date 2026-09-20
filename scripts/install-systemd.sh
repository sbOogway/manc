#!/usr/bin/env sh
# Link the user units under systemd/ into ~/.config/systemd/user, enable them and let them run
# without an open session. Re-run after changing a unit file.
set -eu
cd "$(dirname "$0")/.."

target=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
mkdir -p "$target"
for unit in systemd/*; do
  ln -sfn "$(pwd)/$unit" "$target/$(basename "$unit")"
done

loginctl enable-linger "$(id -un)"
systemctl --user daemon-reload
systemctl --user enable --now manc-api.service
systemctl --user enable --now manc-fetch.timer
systemctl --user enable --now manc-run.timer
systemctl --user list-timers --no-pager manc-fetch.timer manc-run.timer
