# Contributing

## Set up

You need [uv](https://docs.astral.sh/uv/). It installs the Python version from `.python-version` and the locked dependencies:

```
uv sync
```

`.python-version` is the newest supported Python, 3.14, because some problems show only on newer Pythons: since 3.13, an unclosed SQLite connection is reported, and the tests treat that as an error. mypy checks against 3.12, the oldest, and CI runs all three.

## How a change is made

### OpenSpec

Features and fixes are built as OpenSpec changes under `openspec/changes/<id>/`. Each change has a proposal, a design, specs with scenarios and a task list. [ROADMAP.md](ROADMAP.md) lists the changes and what each one owns.

1. `/opsx:propose`: create a change and its planning documents.
2. `/opsx:apply`: implement it, one task group at a time, on a branch named after the change, such as `000-scaffold-project`. Open a draft pull request into `main` early: CI runs on pull requests, not on pushes to other branches.
3. `/opsx:archive`: when every task is done, merge the change's specs into `openspec/specs/`. Then the pull request is merged into `main`.

- Claude Code finds OpenSpec's agent skills in `.claude/skills/`. Codex uses the same agent skills from `.agents/skills/`.
- The exception: fixes to the planning documents of a change that is not in progress go straight to `main`.
- `spider` sends no telemetry, so turn OpenSpec's off before running it:
  - bash: `export OPENSPEC_TELEMETRY=0`
  - PowerShell: `$env:OPENSPEC_TELEMETRY = "0"`

### Test-driven development

Code is written test-first, in vertical slices. [docs/testing.md](docs/testing.md) has the full rules and the agreed test seams.

1. **Red:** write one failing test for one scenario, at an agreed seam, and watch it fail for the right reason.
2. **Green:** write only enough code to pass it.
3. Run `uv run scripts/check.py`, then commit. One green slice is one commit, and its message names the scenario.

Every task group ends with a review task: run the `code-review` agent skill on the group's commits, then refactor with the checks green. Refactoring happens only there, never inside the red → green loop.

## Checks

Run CI's gates in CI's order. The script stops at the first failure. Only the wheel smoke test is left to CI:

```
uv run scripts/check.py
```

Each gate on its own:

| Gate | Command |
|---|---|
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format --check .` (`uv run ruff format .` fixes it) |
| Types | `uv run mypy` |
| Tests and coverage | `uv run pytest` |
| Specs | `openspec validate --all --strict` |
| Report script (seam 9) | `node --test "tests/js/**/*.test.mjs"` |

- **One test file:** add `--no-cov`, for example `uv run pytest tests/cli/test_version.py --no-cov`. The 90% coverage gate is meant for the whole suite, and a partial run can fall below it.
- **Specs:** `openspec` is a Node tool. If it is not on `PATH`, the check script skips this step with a notice, and CI still runs it. Run by hand, it needs its telemetry turned off first (see [OpenSpec](#openspec)); the check script does that by itself.
- **Report script:** also needs Node, and is skipped with a notice without it. Keep the quotes around the glob: Node expands it itself.

## What CI runs

`.github/workflows/ci.yml` runs on:
- every push to `main`
- every pull request
- a manual run ("Run workflow" on the Actions page)

A push to any other branch runs nothing until a pull request is open for it.

Each run is a matrix of 9 cells: Ubuntu, macOS and Windows × Python 3.12, 3.13 and 3.14. No cell stops the others, and each has a 30-minute limit. On a pull request, a newer push cancels the run still in progress; every run on `main` finishes.

Every cell runs these steps in order, all in bash, including on Windows. It stops at the first failure:

1. Check out the code, and install uv with the cell's Python.
2. `uv sync --locked`, which fails if `uv.lock` is out of date.
3. Check that the cell really runs its matrix Python, since `.python-version` pins 3.14.
4. `ruff check .`, then `ruff format --check .`.
5. `mypy` (strict).
6. `pytest`, with the 90% coverage gate and the hypothesis `ci` profile.
7. The wheel smoke test: `uv build`, then `spider --version` from the built wheel in an isolated environment.
8. Install Node (current LTS) and OpenSpec 1.13.0.
9. `openspec validate --all --strict`, with telemetry off.
10. `node --test "tests/js/**/*.test.mjs"`.

`uv run scripts/check.py` runs the gate commands of steps 4–6, 9 and 10 locally. It also runs mypy for Linux and macOS (`--platform linux` and `darwin`, each with its own cache), because some standard-library types differ per platform and CI's other cells would catch what a single OS misses. Pytest runs with the `dev` hypothesis profile. Steps 9 and 10 are skipped when `openspec` or `node` is not on `PATH`.

## Adding a dependency

- **Runtime:** `uv add <name>`. In the same commit, add the new package and everything it pulls in to `tests/dependency_allowlist.txt`, one name per line with a short reason. `uv run pytest tests/test_dependencies.py --no-cov` names whatever is missing. Telemetry and LLM SDKs are refused even when allowlisted.
- **Version caps:** cap the major version of a runtime dependency that a public contract rests on: `sqlalchemy` (the crawl file schema) and `typer` (the CLI, pinned to its minor version for `typer._click`). Leave the others uncapped.
- **Development only:** `uv add --dev <name>`. The allowlist covers runtime dependencies only.

## Changing the crawl store schema

The schema of a crawl file is a public contract ([ADR-0002](docs/adr/0002-sqlite-crawl-store-public-schema.md)): agents query it with SQL. It changes only this way:
- **In one slice:** add the table or column to the declared schema (`spider.store.schema`) and to [docs/schema.md](docs/schema.md) in the same commit, in the slice whose scenario first needs it. The store contract test compares the two, so neither may lead. [How to add a table](docs/schema.md#how-to-add-a-table) has the details.
- **Declared in full:** `info={"change": <n>}` on a new table, a comment on every table and column, the shared column types for timestamps, JSON and booleans, and the conventions of `docs/schema.md`. Tests check them on every declared table.
- **Before v0.1:** no migration. Edit the declared tables directly; `schema_version` stays `1`, and crawl files from earlier development builds are not supported.
- **From v0.1 on:** every schema change adds 1 to `schema_version`, and brings a migration and a test that upgrades a crawl file from every published schema version.

## Conventions

- **Terms:** use the terms of [CONTEXT.md](CONTEXT.md) exactly, capitalised as defined there, such as Workspace, Crawl, Page, Issue and Command. This applies in code, tests, docs and commit messages. Test names use them too.
- **Decisions:** a settled architectural decision is an ADR in [docs/adr/](docs/adr/). Don't reopen a decision that has one. Write a new ADR instead of quietly working around it.
- **Placeholder name:** `spider` is a working name. It appears in `pyproject.toml` (the distribution and the console script), as the import package `spider`, and in the module `spider.naming` for anything users see: `APP_NAME`, the settings file name, the data folder and the global Workspace folder. Use those constants rather than typing a name in `src/`, and say "the settings file" or "the data folder" in comments, so a rename stays mechanical. `tests/test_naming.py` fails on the literals `spider.toml` and `.spider` anywhere else in `src/`; tests keep the literals.

## Code style

- Write a comment only for a non-obvious *why*. Don't add a docstring to a function or method whose name and types already say what it does, and don't add a comment that restates the code.
- Each module starts with a one-line docstring that names the design decision it implements, such as "design D7 of 000-scaffold-project". An empty `__init__.py` that only marks a test package needs none.
- **The paradigm** is [ADR-0006](docs/adr/0006-functional-core-frozen-records-protocols.md): logic in pure functions, data in frozen dataclasses, dependencies as parameters typed by a Protocol, state only where it is inherent, no class hierarchies of our own, and pydantic only at the boundary.
- **Errors:**
  - An error that a user or an agent sees is a `SpiderError` with a `DiagnosticCode` from the registry in `spider.output.codes`. A warning is a `Diagnostic` made with `Diagnostic.of(code, ...)` and given to the `Reporter`. Never report a bare message without a code.
  - A broken contract inside our own code, such as a settings table registered twice, raises a built-in `TypeError` or `RuntimeError`. It is a bug, not a diagnostic.
  - An error class of the store, such as `CrawlWriterClosedError`, is turned into a code by the service that catches it.
- **`# type: ignore[code]` and `# noqa: CODE`** always name the code, and are used only when the fault is not ours: a third-party API or stub, or the one place that one of our banned-API rules (`TID251`) leads to. Prefer fixing the type. A short reason goes on the line, or in the comment right above it when the line would grow too long, in words that don't start with `noqa`: ruff reads such a comment as a blanket directive (`RUF100`).
- **Private names** start with `_`. A module's public names are the ones without it, and only those are imported from other modules.
- **Size, a guide and not a gate:** a module past about 300 non-blank lines, or a class past about 10 methods, is a question for review. Today only `spider/store/writer.py` (366 lines) and its `CrawlWriter` (25 methods) are past either, and ADR-0006 says how it would split. Complexity rules in ruff stay in the ROADMAP Backlog ("Code quality checks").
- **Imports:**
  - Our own code is imported by name, as in `from spider.output.codes import USAGE_ERROR`, never as a module.
  - A standard-library or third-party module is imported either way: whole where its functions are called through it (`asyncio`, `sqlite3`, `re`, `time`, `orjson`, `typer`), and by name otherwise (`from pathlib import Path`).
  - An import inside a function only keeps a heavy module off the startup path, such as `rich` in `spider.output.table`. `tests/cli/test_startup.py` checks what a startup loads.
- **Formatting** is `ruff format`'s: double quotes, and lines of at most 100 characters.

## Windows notes

- **Checks:** `uv run scripts/check.py` works the same in bash and in Windows PowerShell 5.1 (which has no `&&`).
- **Tests:** use `127.0.0.1`, never `localhost`. On Windows, `localhost` tries `::1` first, and a refused connection there costs about 2 seconds. The fixture site binds `127.0.0.1` only.
- **Line endings:** every text file is checked out with LF, whatever `core.autocrlf` says (`.gitattributes`). The fixture-site pages are the exception: they are served byte for byte.
