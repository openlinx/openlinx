# AGENTS.md

Read this first if you are about to change this repository, whether you are a coding agent or a person. It holds the rules and points to the rest.

OpenLinx is an open-source, agent-first SEO crawler, run as the `linx` command: a Python CLI now, plus an MCP server later. [README.md](README.md) says what works today, and [ROADMAP.md](ROADMAP.md) says what is being built.

## Before you start

- **Choose the lane** ([CONTRIBUTING.md](CONTRIBUTING.md#two-lanes)). A small fix to specified or documented behaviour is a test plus the fix. Anything new is an OpenSpec change. If a change in progress owns the area, open an issue instead.
- **Use the terms of [CONTEXT.md](CONTEXT.md) exactly**, capitalised as defined (Workspace, Crawl, Page, Seed, Scope…), in code, tests, docs and commits.
- **Don't reopen a decision** that has an ADR in [docs/adr/](docs/adr/). Propose a new ADR instead.

## The loop

1. Run `uv sync` once. It installs Python 3.14 and the locked dependencies.
2. **Test first, at an agreed seam** ([docs/testing.md](docs/testing.md#seams)). Red, then green, then commit: one green slice per commit.
3. While you work, run `uv run pytest <test file> --no-cov`.
4. Before each commit, run `uv run scripts/check.py`. It runs ruff, the format check, strict mypy for three platforms, the whole suite with the 90% coverage gate, and then OpenSpec and Node checks when they are installed. The suite runs for minutes, so when several agents share one machine, run one check at a time.
5. When a check fails, fix the cause it points at. Never weaken a test, a guard or a lint rule to get green.

## Rules a check enforces (its message says the fix)

- **ruff:** no `print`, `sys.stdout`, `sys.stderr` or echo outside `openlinx.output`. No event-loop policies. `typer._click` only in `openlinx.cli.click_compat`. Lines of at most 100 characters.
- **mypy:** strict mypy for 3.12. A `# type: ignore` must name its code.
- **`tests/test_code_style.py`:** frozen records only, no class hierarchy of our own, a bound on every memo, sqlalchemy only in `openlinx.store` (and the schema service), and the crawl core never imports its plugins.
- **`tests/cli/test_startup.py`:** `--help` loads only its allowlist, so heavy imports go inside the function body.
- **`tests/test_naming.py`:** the three names, the settings file and the data folder come from `openlinx.naming`, never typed as literals in `src/`.
- **`tests/test_dependencies.py`:** a new runtime dependency goes into `tests/dependency_allowlist.txt`. Telemetry and LLM SDKs are refused.
- **Schema contract tests:** a table or column goes into `openlinx.store.schema` and `docs/schema.md` in the same commit.
- **`tests/workspace/test_tables.py`:** settings tables follow the table rules, and every option's setting exists.

## Rules only review catches (follow them without being asked)

- **Fix the cause, never the symptom.** When there is a bug or a red check, find out why. Don't get to green with a retry, a sleep, a skip, a looser assert or a `# type: ignore`. If a test is wrong, fix the premise it rests on. Where it is cheap, also close the class of bug with a guard, a type or a check.
- **A guard test that passes at once is proven by a mutation.** If a guard test never went red, break the code on purpose and show the test fails. The commit says which mutation it used.
- **Comments:** only for a non-obvious *why*. No docstring that repeats a name and its types. Every module starts with a one-line docstring that names the design decision it implements.
- **[ADR-0006](docs/adr/0006-functional-core-frozen-records-protocols.md):** logic in pure functions. Data in frozen records, with `slots=True` for records made per URL or Page and `kw_only=True` above three fields. Dependencies passed in, typed by a Protocol. pydantic only at the boundary.
- **Errors:** an error a user sees is an `OpenLinxError` with a code from `openlinx.output.codes`. A broken internal contract raises `TypeError` or `RuntimeError`.
- **Tests:** only the boundary doubles listed in docs/testing.md, never a mock of our own modules. Expected values are literals taken from the spec. Use `127.0.0.1`, never `localhost`.
- **Store:** a unit that runs once per URL or Page executes a statement built at import. A unit may run twice, so it has no effect outside its connection.
- **Docs in the same slice:** new codes, settings, options and Commands are documented where their area is.
- **Commits and pull requests:** follow the format in [CONTRIBUTING.md](CONTRIBUTING.md#commits-and-pull-requests). No `Co-Authored-By` or "generated with" lines. No competitor names except Screaming Frog.

## Where things are

| You are changing | Read |
|---|---|
| a common change: a code, setting, option, Command, column or hook | [CONTRIBUTING.md "Common changes"](CONTRIBUTING.md#common-changes) |
| URLs, Scope, Links, `linx crawl` | [docs/crawling.md](docs/crawling.md) |
| output, paging, diagnostics, exit codes | [docs/cli.md](docs/cli.md), or run `linx commands` |
| settings, `linx init`, Workspaces | [docs/workspace.md](docs/workspace.md), [architecture "Settings"](docs/architecture.md#settings) |
| the crawl file: tables, writing, reading | [docs/schema.md](docs/schema.md), [docs/crawl-store.md](docs/crawl-store.md) |
| tests: seams, helpers, the fixture site | [docs/testing.md](docs/testing.md), [tests/fixture_site/README.md](tests/fixture_site/README.md) |

Packages under `src/openlinx/`:
- `cli/`: the Command adapters.
- `services/`: the logic behind them.
- `crawl/`: the engine, Fetcher, Scope, Links and robots.txt.
- `store/`: the crawl file.
- `output/`: formats, the code registry and the Reporter.
- `workspace/`: Workspaces and settings.

`extract/`, `rules/`, `query/`, `report/`, `skill/` and `mcp/` stay empty until the change named in their docstring.

**Reading a design citation.** A docstring may say "020-add-crawl-core D5", "(020 D5)" or "design D5 of 020-add-crawl-core". Each points to the heading `### D5.` in the change's `design.md`: for an archived change, such as this one, `openspec/changes/archive/2026-10-29-020-add-crawl-core/design.md`; for one in progress, `openspec/changes/<id>/design.md`.
