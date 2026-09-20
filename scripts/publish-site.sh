#!/usr/bin/env sh
# Build site/ and publish the result to the gh-pages branch of origin; GitHub Pages serves that
# branch at its root. The branch holds each build as its own commit chain (git commit-tree over
# a temporary index, no subtree needed). One-off, to enable Pages on the repository:
#   gh api -X POST repos/sbOogway/manc/pages -f 'source[branch]=gh-pages' -f 'source[path]=/'
set -eu
cd "$(dirname "$0")/.."

if [ -n "$(git status --porcelain -- site)" ]; then
  echo "publish-site: uncommitted changes under site/; commit them first" >&2
  exit 1
fi

npm --prefix site run build >&2
[ -f site/dist/index.html ] || { echo "publish-site: site/dist/index.html missing after the build" >&2; exit 1; }

scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
index=$scratch/index  # git wants a path that does not exist yet, not an empty file
GIT_INDEX_FILE=$index git add -f site/dist
tree=$(GIT_INDEX_FILE=$index git write-tree --prefix=site/dist/)

git fetch -q origin gh-pages >/dev/null 2>&1 || true
parent=$(git rev-parse -q --verify FETCH_HEAD 2>/dev/null || true)
if [ -n "$parent" ] && [ "$(git rev-parse "$parent^{tree}")" = "$tree" ]; then
  echo "publish-site: gh-pages already holds the build of $(git rev-parse --short HEAD)"
  exit 0
fi
commit=$(git commit-tree "$tree" ${parent:+-p "$parent"} -m "site build from $(git rev-parse --short HEAD)")
git push -q origin "$commit:refs/heads/gh-pages"

remote=$(git remote get-url origin)
owner_repo=$(printf '%s' "$remote" | sed -E 's#\.git$##; s#.*[:/]([^/]+)/([^/]+)$#\1 \2#')
owner=$(printf '%s' "${owner_repo%% *}" | tr '[:upper:]' '[:lower:]')
repo=${owner_repo##* }
echo "published the site build to gh-pages: https://$owner.github.io/$repo/"
