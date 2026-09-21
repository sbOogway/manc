#!/usr/bin/env sh
# Build site/ and copy the result to the server's site folder, which `manc api` serves at /.
# MANC_SERVER is the ssh destination (user@host, your own login there). The copy lands in that
# home first and sudo moves it under the manc user, so neither a key for manc nor a sudoers
# rule is needed; sudo asks for the password on the terminal.
set -eu
cd "$(dirname "$0")/.."
server=${MANC_SERVER:?set MANC_SERVER=user@host, the server to publish to}

npm --prefix site run build >&2
[ -f site/dist/index.html ] || { echo "publish-site: site/dist/index.html missing after the build" >&2; exit 1; }

rsync -a --delete site/dist/ "$server:manc-site/"
ssh -t "$server" 'sudo rsync -a --delete --chown=manc:manc manc-site/ /var/lib/manc/site/'
echo "published the site build of $(git rev-parse --short HEAD) to $server:/var/lib/manc/site/"
