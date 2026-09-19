#!/usr/bin/env sh
# Publish site/ to the gh-pages branch of origin; GitHub Pages serves that branch at its root.
# The branch holds the site/ tree of HEAD as its own commit chain (git commit-tree, no
# subtree needed). One-off, to enable Pages on the repository:
#   gh api -X POST repos/sbOogway/manc/pages -f 'source[branch]=gh-pages' -f 'source[path]=/'
set -eu
cd "$(dirname "$0")/.."

if [ -n "$(git status --porcelain -- site)" ]; then
  echo "publish-site: uncommitted changes under site/; commit them first" >&2
  exit 1
fi

tree=$(git rev-parse "HEAD:site")
git fetch -q origin gh-pages >/dev/null 2>&1 || true
parent=$(git rev-parse -q --verify FETCH_HEAD 2>/dev/null || true)
if [ -n "$parent" ] && [ "$(git rev-parse "$parent^{tree}")" = "$tree" ]; then
  echo "publish-site: gh-pages already holds site/ of $(git rev-parse --short HEAD)"
  exit 0
fi
commit=$(git commit-tree "$tree" ${parent:+-p "$parent"} -m "site/ from $(git rev-parse --short HEAD)")
git push -q origin "$commit:refs/heads/gh-pages"

remote=$(git remote get-url origin)
owner_repo=$(printf '%s' "$remote" | sed -E 's#\.git$##; s#.*[:/]([^/]+)/([^/]+)$#\1 \2#')
owner=$(printf '%s' "${owner_repo%% *}" | tr '[:upper:]' '[:lower:]')
repo=${owner_repo##* }
echo "published site/ to gh-pages: https://$owner.github.io/$repo/"
