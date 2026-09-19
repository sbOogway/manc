# manc — instructions for Claude Code

Read `docs/blueprint.md` first: it is the source of truth for architecture, data sources,
the index formula, storage, dashboard and milestones. Keep it updated when a decision changes.

## Working conventions

- **Keep it simple.** Do not make the system more complicated than it needs to be.
- **One issue, one branch, one PR.** Every feature is a GitHub issue under its milestone
  (`gh issue create -R sbOogway/manc --milestone "M1 Skeleton" --label <module>`), opened when
  work starts and listing the tests to write first. Branch names: `feat/<issue>-<slug>`.
  Always branch from `main`. Open the PR, merge it yourself once the hooks are green
  (`gh pr merge --merge --delete-branch`), pull `main` and start the next issue; the owner does
  not review PRs. One open PR at a time, never stacked branches.
- **Test-driven.** Write the failing test before the code (red → green → refactor). Property
  tests with `hypothesis` for formulas; recorded fixtures for providers; `tests/fakes.py` for
  Protocol fakes. Never hit the network in the default test run (`@pytest.mark.live` for the
  rare exceptions).
- **Hooks, not CI.** `pre-commit` runs hygiene, `ruff format`, `ruff check --fix` and `pytest`
  (85% coverage floor) on every commit. No GitHub Actions workflows.
- **Formulas stay pure.** `src/manc/formulas/` holds plain Python classes that import only the
  standard library and each other, never the rest of `manc` (enforced by
  `tests/formulas/test_isolation.py`). A formula change is a new versioned module (`v2.py`),
  never an edit to an old one.
- **All LLM calls go through LiteLLM**; the model is a string in `config/llm.yaml`.
- **UI talks to the backend over the REST API only.** The dashboard is a static site in
  `site/` (Vue 3 and Plotly.js from a CDN, no build step, published to GitHub Pages from the
  `gh-pages` branch by `scripts/publish-site.sh`); it knows the API URL and nothing else.
  Read-side logic (bands, deltas, sparklines, ordering) lives in `src/manc/queries.py` as plain
  functions; API routes and pages stay thin. Site logic that is not rendering (client, formats,
  chart data) goes in plain ES modules tested with `node --test`.
- **Schema changes are Alembic revisions.** Edit `src/manc/store/schema.py`, then
  `uv run alembic revision --autogenerate -m "..."` and review the file. Never hand-edit the
  database; a test fails on drift between `schema.py` and `head`.
- **Dashboard look is reviewed by the owner manually.** Do not take screenshots or drive a
  browser to check the pages; test the pure modules only.

## Code style

- Descriptive variable names everywhere, including loops, comprehensions and lambdas: `for event
  in events`, `key=lambda score: score.date`. Never single-letter names (`e`, `i`, `t`, `s`).
- Commit per module within a PR, each commit green on its own; subject prefixed with the module
  (`store: ...`, `formulas: ...`).

## Commands

```sh
uv sync                              # environment
uv run pre-commit install            # git hooks, once per clone
uv run pytest                        # tests with coverage
uv run pre-commit run --all-files    # every hook on every tracked file
uv run alembic upgrade head          # migrate the database (MANC_DB_URL, default data/manc.db)
```
