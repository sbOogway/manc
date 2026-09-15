# manc — instructions for Claude Code

Read `docs/blueprint.md` first: it is the source of truth for architecture, data sources,
the index formula, storage, dashboard and milestones. Keep it updated when a decision changes.

## Working conventions

- **Keep it simple.** Do not make the system more complicated than it needs to be.
- **One issue, one branch, one PR.** Every feature is a GitHub issue under its milestone
  (`gh issue create -R sbOogway/manc --milestone "M1 Skeleton" --label <module>`), opened when
  work starts and listing the tests to write first. Branch names: `feat/<issue>-<slug>`.
- **Test-driven.** Write the failing test before the code (red → green → refactor). Property
  tests with `hypothesis` for formulas; recorded fixtures for providers; `tests/fakes.py` for
  Protocol fakes. Never hit the network in the default test run (`@pytest.mark.live` for the
  rare exceptions).
- **Hooks, not CI.** `pre-commit` runs hygiene, `ruff format`, `ruff check --fix` and `pytest`
  (85% coverage floor) on every commit. No GitHub Actions workflows.
- **Formula package stays pure.** `packages/manc-formulas` imports only the standard library
  (enforced by a test). A formula change is a new versioned module, never an edit to an old one.
- **All LLM calls go through LiteLLM**; the model is a string in `config/llm.yaml`.
- **Dashboard look is reviewed by the owner manually.** Do not take screenshots or drive a
  browser to check the Dash pages; test callbacks and page rendering only.

## Commands

```sh
uv sync                              # environment
uv run pre-commit install            # git hooks, once per clone
uv run pytest                        # tests with coverage
uv run pre-commit run --all-files    # every hook on every tracked file
```
