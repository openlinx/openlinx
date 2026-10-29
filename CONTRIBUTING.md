# Contributing

## Set up

You need [uv](https://docs.astral.sh/uv/). It installs the Python version from `.python-version` and the locked dependencies:

```
uv sync
```

`.python-version` is the newest supported Python, 3.14, because some problems show only on newer Pythons: since 3.13, an unclosed SQLite connection is reported, and the tests treat that as an error. mypy checks against 3.12, the oldest, and CI runs all three.

## How a change is made

### Two lanes

- **A small fix** needs no OpenSpec change: the code contradicts behaviour that is already specified (a scenario in `openspec/specs/` or in an open change's `specs/`) or documented in `docs/`, or a doc is wrong. The pull request holds a regression test at an agreed seam ([docs/testing.md](docs/testing.md)) that fails before the fix, the fix of the root cause rather than the symptom, and the docs that described the bug. Branch from `main` as `fix-<short-name>`. Node and OpenSpec are not needed.
- **Everything that adds or changes behaviour** is an OpenSpec change, as below: a new Command, option, setting, diagnostic code, column or Rule.
- **An area under construction:** while a change is in progress (see [ROADMAP.md](ROADMAP.md)), its capability belongs to that change's branch. Open an issue instead of a competing pull request.

### OpenSpec

Features and fixes are built as OpenSpec changes under `openspec/changes/<id>/`. Each change has a proposal, a design, specs with scenarios and a task list. [ROADMAP.md](ROADMAP.md) lists the changes and what each one owns.

1. `/opsx:propose`: create a change and its planning documents.
2. `/opsx:apply`: implement it, one task group at a time, on a branch named after the change, such as `000-scaffold-project`. Open a draft pull request into `main` early: CI runs on pull requests, not on pushes to other branches.
3. `/opsx:archive`: when every task is done, merge the change's specs into `openspec/specs/`. Then the pull request is merged into `main`.

- Claude Code finds OpenSpec's agent skills in `.claude/skills/`. Codex uses the same agent skills from `.agents/skills/`.
- The exception: fixes to the planning documents of a change that is not in progress go straight to `main`.
- OpenSpec is a Node tool. Install Node (current LTS), then the version CI uses: `npm install -g @fission-ai/openspec@1.13.0`.
- `spider` sends no telemetry, so turn OpenSpec's off before running it:
  - bash: `export OPENSPEC_TELEMETRY=0`
  - PowerShell: `$env:OPENSPEC_TELEMETRY = "0"`

### Writing specs, designs and commits

A reader should get the point of any requirement or decision from one line, and still find every rule when they need it. These rules keep the text short as a consequence; there is no length limit.

- **The point first.** Each requirement and each design decision opens with a one-line `**In short:**`. A spec or design opens with a short overview of what it guarantees. A table or a list replaces a paragraph that enumerates cases.
- **One place per fact.** A spec says what the system does, a design says why, and tasks say what to build. Git keeps how we got there. Everywhere else, point to the fact instead of retelling it.
- **A spec holds what a test can check.** A sentence that no test could check is rationale, and it goes in the design.
- **Every sentence carries a rule or an edge case.** If deleting it loses neither, delete it.
- **No history in specs and designs:** no dates, rulings, "re-grounded", "previously" or task numbers. Git and the pull request keep them.
- **A decision is its outcome:** what was chosen, why, and the alternative that lost. It is not the path to it.
- **Glossary terms are used, not re-explained.**
- **A commit body says what the diff does not:** why, and any consequence that is not obvious. It does not retell the diff or list test names. A one-line fix has a one-line message.
- **Ready when** a contributor reads a requirement once and can write its test, and reads a decision once and knows what was chosen and why.

### Test-driven development

Code is written test-first, in vertical slices. [docs/testing.md](docs/testing.md) has the full rules and the agreed test seams.

1. **Red:** write one failing test for one scenario, at an agreed seam, and watch it fail for the right reason.
2. **Green:** write only enough code to pass it.
3. Run `uv run scripts/check.py`, then commit. One green slice is one commit, and its message names the scenario.

Every task group ends with a review of the group's commits, then refactoring with the checks green. Refactoring happens only there, never inside the red → green loop. The review has two axes:
- **Standards:** does the code follow [Code style](#code-style), [ADR-0006](docs/adr/0006-functional-core-frozen-records-protocols.md) and the rules that only review catches ([AGENTS.md](AGENTS.md))?
- **Spec:** does every scenario of the group have a test named after it, and does the code do what the scenario says, and no more?

A person or an agent can run it. The repository ships no review skill; an agent with a code-review skill of its own may use it.

## Commits and pull requests

- **One commit per green slice.** The subject starts with `feat:`, `fix:`, `test:`, `refactor:` or `docs:` (`docs(plan):` for planning documents, `docs(roadmap):` for ROADMAP.md) and says in one sentence what changed and why. A task of an OpenSpec change ends with its number, such as `(task 10.7)`.
- **No attribution trailers:** no `Co-Authored-By` lines and no "generated with" footers, in commits or pull request descriptions.
- **No competitor names** anywhere in the repository: code, tests, docs, plans, commits or pull requests. Screaming Frog is the one exception, as a plain mention that helps a newcomer, never as a benchmark or a reference to match. Describe a borrowed idea as our own requirement.
- **A pull request** goes into `main`, fills in the template's checklist, and is merged once CI is green on every OS and a maintainer has reviewed it.

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
- **Declared in full:** a new table through `public_table(..., change=<n>)`, a comment on every table and column, a description on every index, the shared column types for timestamps, JSON and booleans, and the conventions of [ADR-0005](docs/adr/0005-crawl-file-schema-conventions.md), summed up in `docs/schema.md`. Tests check them on every declared table.
- **Before v0.1:** no migration. Edit the declared tables directly; `schema_version` stays `1`, and crawl files from earlier development builds are not supported.
- **From v0.1 on:** every schema change adds 1 to `schema_version`, and brings a migration and a test that upgrades a crawl file from every published schema version.

## Common changes

Each recipe lists the files to touch in order, the seam to test at, and what checks it. Steps marked *review* are not checked by any test, so check them yourself. They describe `main`; 020's planned reworks are noted where they change a step.

### A diagnostic code

1. Declare it once, next to related codes, in `spider/output/codes.py`: `NAME = _declare("name", level, ExitCode.X or None, "One sentence.")`. An input error named `invalid_*` or `unknown_*` exits 2, and `*_not_found` exits 4 (`tests/cli/test_commands.py::test_naming_rule_for_input_errors`).
2. Use it: `raise SpiderError(NAME, message, hint=..., details=...)` for an error, `reporter.warn(Diagnostic.of(NAME, ...))` for a warning.
3. Test it at seam 1 or 2: the code, the exit code and the `details` an agent needs.
4. *Review:* document it where its area is documented: the CLI contract in [docs/cli.md](docs/cli.md), the store in [docs/crawl-store.md](docs/crawl-store.md), `spider crawl` in [docs/crawling.md](docs/crawling.md). `spider commands` lists it by itself.

### A setting in an existing table

1. Add the field to the table's pydantic model, such as `CrawlSettings` in `spider/crawl/settings.py`, with a one-line `description` and a default TOML can write, or `None` for a setting that is unset. `tests/workspace/test_tables.py` checks every registered table against the [table rules](docs/architecture.md#settings). `spider init`'s commented template and the error hints come from the model.
2. A secret is declared on the field, `json_schema_extra={"secret": True}`, and is redacted before a Crawl records it.
3. If a flag mirrors it, see the next recipe.
4. *Review:* document it with its table, such as `[crawl]` in docs/crawling.md "Options and `[crawl]` settings".

A table has one owning change, and a new table is registered in `build_app` (`spider/cli/app.py`) by its `"module:Class"` reference, so `--help` never imports it.

### An option that mirrors a setting

1. Declare it on the Command as `--concurrency` is in `spider/cli/crawl.py`: `Annotated[int, typer.Option("--flag", ...), OptionMeta(setting="table.field")] = <default>`. The long name is the field's name with `-` for `_`. `tests/workspace/test_tables.py` checks that the setting exists.
2. The adapter passes `setting_flags(ctx)` to the settings loader, so only a flag given on the command line beats the settings file.
3. *Review:* the option's default, `min`/`max` and help match the field's.
4. A secret option inherits `secret` from its setting and takes only a long name; `check_command` refuses a short one.

### A Command

1. **The service first:** plain Python in `spider/services/<area>.py`, taking a frozen request record and the `Reporter` and returning a result, with no Typer, Click or `Output`. Test it at seam 2. The MCP server (`090`) will call the same service, so any logic a second caller would need belongs here, not in the adapter.
2. **The adapter:** `spider/cli/<command>.py`, a function under `@command_meta(output=..., formats=[...], fields=..., examples=[...])` that builds the request, calls the service and returns its result, as `spider/cli/init.py` does. A `list` Command declares `output_format`, `limit`, `cursor` and `fields` (`spider.cli.options`), and `check_command` refuses a Command that breaks its kind's rules when the app is built. Import sqlalchemy, pydantic and the crawler inside the function body; `tests/cli/test_startup.py` checks what `--help` loads.
3. Register it in the list in `build_app` (`spider/cli/app.py`).
4. Test it at seam 1 with `run_cli` (`tests/support/cli.py`): the JSON on stdout, the exit code, the diagnostics on stderr.
5. *Review:* document it, and its codes as above.

### A table or column of the crawl store

See [Changing the crawl store schema](#changing-the-crawl-store-schema) and [How to add a table](docs/schema.md#how-to-add-a-table). A new column goes into `spider.store.schema` and its `docs/schema.md` row in the same commit, at the same position in both. *Review:* a unit that runs once per URL or Page executes a statement built once at import ([architecture](docs/architecture.md#crawl-store)).

### An extractor, handler or post-crawl pass

Plug it into `default_hooks()` in `spider/services/hooks.py`, as [How 030 and 040 plug in](docs/architecture.md#crawl-pipeline) describes; the engine is never edited. 020 reworks these hooks before it is archived: a handler will name the store function that writes its rows (no separate `row_writers`), a pass will take a `PassContext`, an extractor will carry its own settings, and every request will go through one Requester. Read the architecture section as it stands on your branch before copying an example.

## Conventions

- **Terms:** use the terms of [CONTEXT.md](CONTEXT.md) exactly, capitalised as defined there, such as Workspace, Crawl, Page, Issue and Command. This applies in code, tests, docs and commit messages. Test names use them too.
- **Decisions:** a settled architectural decision is an ADR in [docs/adr/](docs/adr/). Don't reopen a decision that has one. Write a new ADR instead of quietly working around it.
- **Placeholder name:** `spider` is a working name. It appears in `pyproject.toml` (the distribution and the console script), as the import package `spider`, and in the module `spider.naming` for anything users see: `APP_NAME`, the settings file name, the data folder and the global Workspace folder. Use those constants rather than typing a name in `src/`, and say "the settings file" or "the data folder" in comments, so a rename stays mechanical. `tests/test_naming.py` fails on the literals `spider.toml` and `.spider` anywhere else in `src/`; tests keep the literals.

## Code style

- Write a comment only for a non-obvious *why*. Don't add a docstring to a function or method whose name and types already say what it does, and don't add a comment that restates the code.
- Each module starts with a one-line docstring that names the design decision it implements, such as "design D7 of 000-scaffold-project". An empty `__init__.py` that only marks a test package needs none.
- An `__init__.py` holds no code: callers import its submodules. A package's docstring is a summary line and the list of its interface, which lives nowhere else.
- **The paradigm** is [ADR-0006](docs/adr/0006-functional-core-frozen-records-protocols.md): logic in pure functions, data in frozen dataclasses (frozen `msgspec.Struct`s for page preparation's per-response records, which cross the parse pool, and for records that define a JSON document), dependencies as parameters typed by a Protocol, state only where it is inherent, no class hierarchies of our own, and pydantic only at the boundary.
- **A memo** of a pure function, `functools.lru_cache(maxsize=N)` on a function whose result depends only on its arguments, is allowed and is not module-level state (ADR-0006). It always has a bound, never `maxsize=None` or `functools.cache`, and a one-line comment at the decorator says why it pays.
- **Errors:**
  - An error that a user or an agent sees is a `SpiderError` with a `DiagnosticCode` from the registry in `spider.output.codes`. A warning is a `Diagnostic` made with `Diagnostic.of(code, ...)` and given to the `Reporter`. Never report a bare message without a code.
  - A broken contract inside our own code, such as a settings table registered twice, raises a built-in `TypeError` or `RuntimeError`. It is a bug, not a diagnostic.
  - An error class of the store, such as `CrawlWriterClosedError`, is turned into a code by the service that catches it.
- **`# type: ignore[code]` and `# noqa: CODE`** always name the code, and are used only when the fault is not ours: a third-party API or stub, or the one place that one of our banned-API rules (`TID251`) leads to. In a test, a deliberate type guard or a deliberately wrong call takes one too, with its reason. Prefer fixing the type. A short reason goes on the line, or in the comment right above it when the line would grow too long. That comment must not start with `noqa`, which ruff would read as a blanket directive and flag (`RUF100`).
- **Private names** start with `_`. A module's public names are the ones without it, and only those are imported from other modules.
- **Size, a guide and not a gate:** a module past about 300 non-blank lines, or a class past about 10 methods, is a question for review. Today `spider/store/writer.py` (366 lines) and its `CrawlWriter` (25 methods) are past both, and ADR-0006 says how to split them. `spider/store/schema.py` (385 lines) is past the line guide too, but nearly all of it is the declared tables' columns, one to a line, beside a few small helpers: it grows with the schema, not with its logic, so it stays one module. So is `spider/services/crawling.py` (338 lines), which plans a Crawl and runs it: its next split would take the plan, from the settings to the Scope and the Seed's checks, into a module of its own. Complexity rules in ruff stay in the ROADMAP Backlog ("Code quality checks").
- **Imports:**
  - Our own code is imported by name, as in `from spider.output.codes import USAGE_ERROR`, never as a module.
  - A standard-library or third-party module is imported either way: whole where its functions are called through it (`asyncio`, `sqlite3`, `re`, `time`, `orjson`, `typer`), and by name otherwise (`from pathlib import Path`).
  - An import inside a function only keeps a heavy module off the startup path, such as `rich` in `spider.output.table`. `tests/cli/test_startup.py` checks what a startup loads.
- **Formatting** is `ruff format`'s: double quotes, and lines of at most 100 characters.

## Windows notes

- **Checks:** `uv run scripts/check.py` works the same in bash and in Windows PowerShell 5.1 (which has no `&&`).
- **Tests:** use `127.0.0.1`, never `localhost`. On Windows, `localhost` tries `::1` first, and a refused connection there costs about 2 seconds. The fixture site binds `127.0.0.1` only.
- **Line endings:** every text file is checked out with LF, whatever `core.autocrlf` says (`.gitattributes`). The fixture-site pages are the exception: they are served byte for byte.
