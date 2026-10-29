## Why

The next changes (`022`, `026`, `030`, `040`, `050`, `060`, `090`) plug into seams that the crawl core left unguarded, unlisted or tied to the CLI. Some of these mistakes pass every test and then fail in a user's Crawl or in the next change's branch: a stop flag set from a thread, an extractor that is not module-level, a sync submit inside a Crawl, a writer unit that returns a cursor. Others are seams a contributor will not find: services that validate settings only through the CLI, link reading missing from the package interfaces, Link type knowledge spread over five modules. The recipes in CONTRIBUTING still describe 020's rework as future. This change fixes them before those changes continue.

## What Changes

- **Guards that fail early and name the fix:**
  - the engine: a stop flag set off its loop, and an extractor that is not module-level, are refused;
  - the writer: a sync `submit` or `run` under a loop's commit deadline, and a unit whose result compares by identity, are refused, and a unit that commits ends the writer at once;
  - a post-crawl pass sees only the writer's async calls;
  - a table outside `openlinx.store.schema`, a repeated or inconsistent diagnostic code, a blanket `# noqa`, and an undocumented name used across a package, fail a test;
  - every guard's message says the fix.
- **Hook failures say what failed:** the first `handler_failed` and `parse_failed` warnings carry the error's text and where it was raised.
- **One Link type table** in `openlinx.store.records` drives the follow rule, the Resource types and the element selectors of Link discovery. `LinkElement` and `LinkAttribute` sit beside `LinkType`, and they type `DiscoveredLink`.
- **Link reading by ordinal:** `locate_links` takes all of a Page's Links and refuses a subset.
- **Services validate without the CLI:** the settings tables, the `--subdomains` alias and its conflict, the secret settings, and the error for a refused value move out of `openlinx.cli`. A refused value given with the settings, a flag's included, is `invalid_value` (exit 2) with its key, not `settings_invalid` against a file.
- **Self-description:** `linx commands` gives each option's bounds, leaves out hidden options, and lists no environment variable until one is honoured.
- **SQL home:** the `--where` parser stays in `openlinx.query`, every statement in `openlinx.store`; the docs and the sqlalchemy guard say so.
- **Docs and recipes** describe what is built: the hooks recipe in steps over the real built-ins, two column recipes, the setting and code recipes, the test seams.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `cli-contract`: `linx commands` gives option bounds, leaves out hidden options, and lists no environment variable.
- `workspace`: no environment variable is honoured; a refused given value, a flag's included, is `invalid_value` with its key.
- `crawling`: the first hook failure warning names the error and where it was raised.
- `crawl-store`: the writer refuses units it could not replay and sync calls under a loop's commit deadline, and a unit that commits ends it.

## Impact

- Code: `openlinx.crawl.engine` (stop, hooks), `openlinx.crawl.pages` (preparation, links), `openlinx.crawl.references`, `openlinx.crawl.following`, `openlinx.store` (records, writer), `openlinx.services` (crawling, a new `settings` module), `openlinx.workspace.settings`, `openlinx.cli` (app, crawl, commands, options), `openlinx.output.codes`, `openlinx.extract` (`page_links`, `link_handler`), `pyproject.toml` (ruff).
- Tests: new guards in `tests/test_code_style.py`, `tests/workspace/test_tables.py` and `tests/contract/`; messages on the existing guards; `tests/support/crawling.py` without the app.
- Docs: CONTRIBUTING's recipes, `docs/architecture.md`, `docs/crawl-store.md`, `docs/crawling.md`, `docs/testing.md`, `docs/workspace.md`, AGENTS.md links.
- Other branches: `030` reads the Link type table in its element guard, its passes use the narrow writer, and its new tables go in `openlinx.store.schema`. `040` and `050` register their settings tables in `default_tables()`. `050` compiles `--where` in `openlinx.store.query`.
