# Contributing

## Set up

You need [uv](https://docs.astral.sh/uv/). It installs the Python version from `.python-version` and the locked dependencies:

```
uv sync --locked
```

`.python-version` is the newest supported Python, 3.14, because some problems show only on newer Pythons: since 3.13, an unclosed SQLite connection is reported, and the tests treat that as an error. mypy checks against 3.12, the oldest, and CI runs all three.

For development agents, restore the local skill aliases after each clone or new worktree:

```
uv run --locked python scripts/setup_agents.py
```

This stdlib-only script finds the repository from its own location and needs no
credentials. It creates Windows junctions or relative POSIX symlinks from
`.claude/skills/<name>` to the canonical `.agents/skills/<name>` directories.
Running it again leaves correct aliases in place. It checks for conflicts before
creating aliases and refuses existing real directories, files or links to other
targets. Move a conflicting path aside yourself after reviewing its contents,
then rerun setup; the script never deletes or overwrites it. Git ignores aliases
and `.agents/migration-backup/`; edit only the canonical skills.

Both agents follow [AGENTS.md](AGENTS.md); `CLAUDE.md` imports it and Codex also
reads [.agents/CODEX.md](.agents/CODEX.md). Continue an existing task from
[docs/development-state.md](docs/development-state.md), then verify its branch and
files. Personal global skills, MCP connections and private memory are not part of
the public clone or this setup. The project does not need a private handoff file
under `.git/` to resume development.

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

- Both agents use the canonical OpenSpec workflows in `.agents/skills/`. Claude Code discovers them through the local `.claude/skills/` aliases created above; `/opsx:*` entries load the same SKILL.md and preserve their arguments.
- The exception: fixes to the planning documents of a change that is not in progress go straight to `main`.
- OpenSpec is a Node tool. Use Node's current LTS, selected by CI as `lts/*`, then install the pinned CLI: `npm install -g @fission-ai/openspec@1.13.0`.
- OpenLinx sends no telemetry, so turn OpenSpec's off before running it:
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
7. The wheel smoke test: `uv build`, then `linx --version` and `openlinx --version` from the built wheel in an isolated environment, which must print the same `OpenLinx <version>` line.
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
- **In one slice:** add the table or column to the declared schema (`openlinx.store.schema`) and to [docs/schema.md](docs/schema.md) in the same commit, in the slice whose scenario first needs it. The store contract test compares the two, so neither may lead. [How to add a table](docs/schema.md#how-to-add-a-table) has the details.
- **Declared in full:** a new table through `public_table(..., change=<n>)`, a comment on every table and column, a description on every index, the shared column types for timestamps, JSON and booleans, and the conventions of [ADR-0005](docs/adr/0005-crawl-file-schema-conventions.md), summed up in `docs/schema.md`, whose [How to add a table](docs/schema.md#how-to-add-a-table) says which of them tests check on every declared table and which only review checks.
- **Before v0.1:** no migration. Edit the declared tables directly; `schema_version` stays `1`, and crawl files from earlier development builds are not supported.
- **From v0.1 on:** every schema change adds 1 to `schema_version`, and brings a migration and a test that upgrades a crawl file from every published schema version.

## Common changes

Each recipe lists the files to touch in order, the seam to test at, and what checks it. Obligations marked *review* are not checked by a test, so check them yourself. Use the built-ins below as the examples.

### A diagnostic code

1. Declare it once, next to related codes, in
   [codes.py](src/openlinx/output/codes.py), through `_declare`. An error has an
   `ExitCode`; warnings and info have `None`. At import, `_declare` refuses duplicate
   names and inconsistent level/exit codes. An input error named `invalid_*` or
   `unknown_*` exits 2, and `*_not_found` exits 4, checked by
   [test_commands.py](tests/cli/test_commands.py)::`test_naming_rule_for_input_errors`.
2. **Choose `kept=` for a Crawl warning.**
   [warning_log.py](src/openlinx/crawl/engine/warning_log.py) implements these five
   modes. *Review:* choose by what the warning describes, and use its matching log
   call; setting `kept` alone does not count URLs or time a pause.

   | `kept` | Choose it when / call | Existing check |
   |---|---|---|
   | `each` (default) | Every occurrence matters: `warn` keeps and forwards each one. | [test_warning_log.py](tests/crawl/test_warning_log.py)::`test_a_warning_is_kept_once_per_what_its_code_names` keeps both `max_urls_reached` calls in the current run; `run` uses the same write path as `each`. *Review:* a new `each` warning's own scenario checks its occurrences. |
   | `once` | The same code and named detail describe one problem over the Crawl's life: call `warn`, and set `once_per="host"`, `"origin"` or the relevant detail key. | [test_warning_log.py](tests/crawl/test_warning_log.py)::`test_a_warning_is_written_once_per_code_and_host` and `test_a_warning_kept_once_per_a_detail_carries_that_detail`. |
   | `counted` | Count affected URLs in one entry per code: call `count(diagnostic, url)`. Only the first is forwarded; the stored result updates `count` and retains `first_url`. | [test_hooks.py](tests/crawl/test_hooks.py)::`test_parse_failures_are_counted_in_one_warning`; [test_continue.py](tests/crawl/test_continue.py)::`test_a_counted_warning_adds_up_over_the_crawls_whole_life`. |
   | `pauses` | The `network_paused` entry counts pauses and their total seconds, through `pause_began` and `pause_ended`; only the first beginning is forwarded. | [test_network_pause.py](tests/crawl/test_network_pause.py)::`test_network_paused_counts_the_pauses_and_their_seconds`; [test_warning_log.py](tests/crawl/test_warning_log.py)::`test_a_continuing_log_adds_its_pauses_to_the_stored_ones`. |
   | `run` | The warning describes this run, such as `max_urls_reached`: call `warn`; a continue drops the earlier run's entry and may write a new one. | [test_continue.py](tests/crawl/test_continue.py)::`test_warnings_cover_the_crawl_s_whole_life`. |

   `once_per` is required for `once` and forbidden for every other mode; `_declare`
   checks this at import. Earlier `each`, `once`, `counted` and `pauses` entries
   survive a continue without being forwarded again.
3. Use `OpenLinxError` for an error, or `Diagnostic.of` for a warning, both from
   [diagnostics.py](src/openlinx/output/diagnostics.py). Give the
   warning to the Reporter (the Crawl's warning log inside a Crawl). Test at
   seam 1 or 2: literal code, exit code and needed `details`, as
   [test_diagnostics.py](tests/cli/test_diagnostics.py)::`test_unknown_command_is_a_usage_error`
   and `test_error_object_has_exactly_the_diagnostic_keys` do. *Review:* the warning's
   own scenario also checks its chosen retention and continuation behaviour.
4. *Review:* document it where its area is documented: the CLI contract in [docs/cli.md](docs/cli.md), the store in [docs/crawl-store.md](docs/crawl-store.md), `linx crawl` in [docs/crawling.md](docs/crawling.md). `linx commands` lists it by itself.

### A setting in an existing table

1. Add the field to its pydantic model, such as `CrawlSettings` in
   [settings.py](src/openlinx/crawl/settings.py), with its bounds, a one-line
   description and a TOML-writable default, or `None` when unset.
   [test_tables.py](tests/workspace/test_tables.py)::`test_every_registered_table_follows_the_rules`
   checks the [table rules](docs/architecture.md#settings); the commented template
   and error hints come from the model. A new table belongs to one change and is
   registered in `default_tables()` in
   [services/settings.py](src/openlinx/services/settings.py) by `"module:Class"`.
   `test_a_table_resolves_from_its_reference` checks reference resolution;
   [test_startup.py](tests/cli/test_startup.py)::`test_settings_tables_load_with_the_settings`
   checks that settings models remain unloaded during `--help`.
2. **Every `[crawl]` field always gets a matching option** in
   [cli/crawl.py](src/openlinx/cli/crawl.py), with its name, default and bounds; follow
   the option recipe below. [test_commands.py](tests/cli/test_commands.py)::`test_mirrored_options_match_their_fields`
   also refuses a `[crawl]` field with no option. *Review:* a setting in another
   table gets an option when its contract calls for one.
3. For a secret, set `json_schema_extra={"secret": True}` on the field.
   [test_crawl_service.py](tests/crawl/test_crawl_service.py)::`test_a_secret_setting_is_redacted_in_the_recorded_config`
   checks recording. At seam 2, test validation through `plan_crawl` in
   [crawling.py](src/openlinx/services/crawling.py), with `default_tables()` and no app;
   `test_a_refused_value_given_with_the_settings_names_its_key` checks the literal
   `invalid_value`, exit 2 and dotted key for a refused caller value.
4. *Review:* document the default, bounds and meaning beside the table in
   [crawling.md](docs/crawling.md#options-and-crawl-settings) for `[crawl]`, in the
   same feature slice. Check the new field's valid and invalid values through its
   service scenario; the table guard does not prove its meaning.

### An option that mirrors a setting

1. In [cli/crawl.py](src/openlinx/cli/crawl.py), follow `--concurrency`:
   `Annotated[int, typer.Option("--concurrency", min=1, max=50, ...), OptionMeta(setting="crawl.concurrency")] = 5`.
   Use the field name with `-` for `_`, the same default, and `ge`/`le` as Click's
   `min`/`max`. A validated value such as `rate` uses a callback sharing the field's
   rule, without inventing inclusive bounds. The matching guard is
   [test_commands.py](tests/cli/test_commands.py)::`test_mirrored_options_match_their_fields`;
   [test_tables.py](tests/workspace/test_tables.py)::`test_every_option_setting_names_a_setting_of_a_registered_table`
   checks the dotted key. *Review:* keep help accurate and validation equivalent.
2. Pass `setting_flags(ctx)` from [options.py](src/openlinx/cli/options.py) through
   `CrawlRequest.flags` to `plan_crawl`, as the adapter does; only explicitly given
   flags override the file. At seam 2,
   [test_settings.py](tests/workspace/test_settings.py)::`test_flag_over_settings_file`
   checks precedence. *Review:* keep the adapter's mapping free of service logic.
3. A secret option inherits secrecy from its field and has only a long name,
   checked by [test_tables.py](tests/workspace/test_tables.py)::`test_options_of_secret_settings_have_only_long_names`.
   Keep model imports off the startup path;
   [test_startup.py](tests/cli/test_startup.py)::`test_startup_loads_only_the_allowlist`
   checks `--help`, and `test_settings_tables_load_with_the_settings` checks that
   settings models remain unloaded during `--help`.

### A Command

1. **The service first:** plain Python in `openlinx/services/<area>.py`, taking a frozen request record and the `Reporter` and returning a result, with no Typer, Click or `Output`. Test it at seam 2. The MCP server (`090`) will call the same service, so any logic a second caller would need belongs here, not in the adapter.
2. **The adapter:** `openlinx/cli/<command>.py`, a function under `@command_meta(output=..., formats=[...], fields=..., examples=[...])` that builds the request, calls the service and returns its result, as `openlinx/cli/init.py` does. A `list` Command declares `output_format`, `limit`, `cursor` and `fields` (`openlinx.cli.options`), and `check_command` refuses a Command that breaks its kind's rules when the app is built. Import sqlalchemy, pydantic and the crawler inside the function body; `tests/cli/test_startup.py` checks what `--help` loads.
3. Register it in the list in `build_app` (`openlinx/cli/app.py`).
4. Test it at seam 1 with `run_cli` (`tests/support/cli.py`): the JSON on stdout, the exit code, the diagnostics on stderr.
5. *Review:* document it, and its codes as above.

### A table or column of the crawl store

See [Changing the crawl store schema](#changing-the-crawl-store-schema) and [How to add a table](docs/schema.md#how-to-add-a-table). A new column goes into `openlinx.store.schema` and its `docs/schema.md` row in the same commit, at the same position in both. *Review:* a unit that runs once per URL or Page executes a statement built once at import ([architecture](docs/architecture.md#crawl-store)).

#### A URL column written by the Crawl

Use the integrated `urls.attempt_count` as the example; these are the files in
data-flow order for a future column, not new assignments to add to the existing field.

1. **Declare and document together.** Change [schema.py](src/openlinx/store/schema.py)
   and [schema.md](docs/schema.md#table-urls) in the same slice: type, nullability,
   default, description and any constraints. `attempt_count` is a non-null integer
   defaulting to 0, for the dispatch that recorded the URL, retries included.
   At seam 6, [test_schema.py](tests/contract/test_schema.py)::`test_documentation_and_declaration_agree`
   checks docs against `linx schema`; `test_a_new_file_matches_the_declaration`
   checks the created file. *Review:* use the schema conventions above.
2. **Produce the value and carry it through the outcome.**
   [requester.py](src/openlinx/crawl/fetch/requester.py) returns `Attempted`, with the
   final outcome and attempt count. [units.py](src/openlinx/crawl/engine/units.py)
   puts the count on the frozen `UrlResult` from
   [hooks.py](src/openlinx/crawl/engine/hooks.py), then `_fetched_record` or
   `_errored_record` builds `FetchedUrl` or `ErroredUrl` from
   [records.py](src/openlinx/store/records.py). At seam 3+6,
   [test_retries.py](tests/crawl/test_retries.py)::`test_a_temporary_503_is_retried`
   expects `(200, 2)`, `test_a_persistent_500_is_recorded_after_the_retries` expects
   `("fetched", 500, 3)`, and `test_a_404_is_not_retried` expects `(404, 1)`.
   *Review:* cover every applicable outcome, including no request and recording
   failure; do not count robots.txt requests as the URL's attempts.
3. **Map to the store unit.** In [urls.py](src/openlinx/store/urls.py),
   `record_fetched` and `record_error` map the record's count to the `attempts`
   parameter of import-built `_FETCHED` and `_ERRORED`; `record_unwritten` preserves
   it in `_UNWRITTEN` when the original unit failed. The fallback receives the
   `UrlResult` count through [outcomes.py](src/openlinx/crawl/engine/outcomes.py).
   *Review:* extend all relevant mappings, keep effects on the connection, inputs
   unchanged and statements built at import. The seam 3+6 retry tests above check
   the persisted value through the real engine, not a fabricated row assignment.
4. **Prove replay at seam 2.** Extend
   [test_urls.py](tests/store/test_urls.py)::`test_the_units_of_urls_run_again_the_same`:
   run the affected units through `CrawlWriter`, call `replay_now` from
   [tests/support/writer.py](tests/support/writer.py) before the batch commits, then
   read the new column with independent literal expected values. The existing test
   exercises fetched, skipped, error and fallback units and forces replay; its
   current SQL assertion does not select `attempt_count`, so a future field needs
   its own value assertion as well as the replay check.

#### A Page column written by a handler

Use `pages.title_1` as the example. The extractor returns `PageData`; the handler
constructs the final `PageRow`, which also includes URL/response fields.

1. **Declare and document together.** Update [schema.py](src/openlinx/store/schema.py)
   and [schema.md](docs/schema.md#table-pages) in the same slice. `title_1` is nullable:
   no title, an unanalysed Page or a failed Page extractor leaves it NULL. The two
   [schema checks](tests/contract/test_schema.py) named in the URL recipe check the
   declaration, docs and file at seam 6; *review* checks the new field's meaning.
2. **Define the row and extraction output.** Put the stored field in `PageRow` in
   [page_records.py](src/openlinx/store/page_records.py), in schema order; put an HTML
   result field in `PageData` and `extract_page_data` in
   [page_data.py](src/openlinx/extract/page_data.py). Title reading uses
   [head_metadata.py](src/openlinx/extract/head_metadata.py). At seam 4,
   [test_page_data.py](tests/extract/test_page_data.py)::`test_whitespace_is_collapsed_before_measuring`
   expects `("Hello World", 11)` and `test_missing_title` expects `(0, None, None)`
   through `page_row` in [tests/support/page_data.py](tests/support/page_data.py),
   which runs preparation and the handler. `test_a_full_page_fills_every_html_column`
   checks the full fixture; extend it for a new HTML field, with separate literal
   assertions for its meaning.
3. **Map the result, then register the pipeline.** In
   [page_handler.py](src/openlinx/extract/page_handler.py), `page_rows` reads
   `PAGE_DATA.output(result.outputs)` and expands present `PageData` fields into
   `PageRow`, alongside response and URL values; absent output leaves HTML fields
   at their row defaults. [services/hooks.py](src/openlinx/services/hooks.py)
   registers `page_data_extractor(area)` and `handler("pages", page_rows, write_pages)`.
   At seam 3+6, [test_pages.py](tests/extract/test_pages.py)::`test_error_page_keeps_response_data`
   checks `(404, None)` for status/title, and
   `test_a_page_whose_page_extractor_failed_keeps_its_response_data_and_links` checks
   NULL title with the remaining data preserved. The seam-4 literal tests above
   cover the successful HTML mapping. *Review:* add a new column's literal readback
   through the Crawl too; an extraction output is not itself a stored Page row.
4. **Write and replay.** [pages.py](src/openlinx/store/pages.py)::`write_pages`
   maps `PageRow` fields into import-built `_INSERT_PAGE`; the engine includes these
   handler rows in the URL's recording unit. At seam 2,
   [test_pages.py](tests/store/test_pages.py)::`test_the_page_row_has_every_pages_column_in_order`
   checks row coverage (except `crawl_depth`, which the unit reads from `urls`).
   Extend `test_the_units_of_pages_run_again_the_same`: supply the field in its
   `PageRow`, run `record_fetched`, call `replay_now`, and read back the field with a
   literal expected value. Its existing query checks address fields, not title.
   *Review:* no I/O outside the connection, no input mutation or transaction control;
   a derived value such as inlinks belongs to the post-crawl pass in the next recipe.

### An extractor, handler or post-crawl pass

Follow the Link pipeline below, with seams from [testing](docs/testing.md#seams).
Register hooks at the composition root; the crawl core takes them as inputs.

1. **Prepare the extractor.** In
   [page_links.py](src/openlinx/extract/page_links.py), `PAGE_LINKS` is built with
   `extractor("page_links", extract_page_links, None)` from
   [preparation.py](src/openlinx/crawl/pages/preparation.py). Keep the extraction
   function and output/config struct classes at module level. Return a typed frozen
   `msgspec.Struct`; config is `None` or a frozen struct resolved when hooks are built,
   and must survive pickle with the Page settings. At seam 4,
   [test_extractors.py](tests/crawl/test_extractors.py) checks config delivery in
   `test_an_extractor_gets_its_own_config`, refuses nested/lambda functions in
   `test_an_extractor_whose_function_is_not_module_level_cannot_be_built`, and checks
   the built-in settings in `test_the_default_page_settings_pickle`.
   *Review:* config fields must themselves hold immutable values.
2. **Locate complete Links before filtering.** `extract_page_links` in
   [page_links.py](src/openlinx/extract/page_links.py) calls
   `locate_links(tree, page.links, expected_total=len(page.links))` from
   [links.py](src/openlinx/crawl/pages/links.py), using the original `PageInput.links`.
   The locator checks the complete count, ordinals 1 to N and headers-first order,
   then returns HTML locations by ordinal; header Links have no DOM location.
   Filter only afterwards. At seam 4,
   [test_links.py](tests/crawl/test_links.py) checks this in
   `test_a_subset_of_a_page_s_links_is_refused`,
   `test_links_out_of_ordinal_order_are_refused` and
   `test_header_links_after_html_links_are_refused`.
3. **Map output to rows.** `link_rows` in
   [link_handler.py](src/openlinx/extract/link_handler.py) reads
   `PAGE_LINKS.output(result.outputs)` and returns `LinkRow` values for the URL's
   Links, including header Links and Links whose extractor output is absent.
   At seam 4, [test_links.py](tests/extract/test_links.py) exercises preparation
   through the handler with literal rows, including
   `test_header_and_repeated_html_links_keep_their_ordinals_and_positions` and
   `test_links_declared_in_a_header`. Build the handler with `handler(...)` from
   [hooks.py](src/openlinx/crawl/engine/hooks.py); strict mypy checks its row type
   against the writer in [test_handler_types.py](tests/test_handler_types.py),
   `test_a_handler_and_a_writer_of_different_row_types_fail_mypy`.
   *Review:* the mapper is pure, with no SQL or other I/O.
4. **Write through the URL's unit.** `write_links(connection, rows)` in
   [store/links.py](src/openlinx/store/links.py) executes the import-built
   `_INSERT_LINK`; the engine includes the handler's rows in the unit that records
   the URL. At seam 2, [test_links.py](tests/store/test_links.py) checks the writer
   with `test_the_units_of_links_run_again_the_same`, which uses `replay_now`, and
   checks row/schema coverage with `test_the_link_row_has_every_links_column`.
   *Review:* build per-URL statements at import, keep effects inside the supplied
   connection, do not mutate inputs, and never commit or roll back inside a unit.
5. **Order post-crawl work.** `count_inlinks` in
   [services/hooks.py](src/openlinx/services/hooks.py) orders the units from
   [store/links.py](src/openlinx/store/links.py). Its `PassContext.writer` is the
   async-only `PassWriter` from [engine/hooks.py](src/openlinx/crawl/engine/hooks.py):
   use `run_async`, `submit_async` and `flush_async`; the Crawl owns closing it.
   Seam 2's [test_links.py](tests/store/test_links.py) checks replay with
   `test_the_units_of_the_inlink_pass_run_again_the_same`. At seam 3+6,
   [test_link_counts.py](tests/extract/test_link_counts.py) checks the registered
   pass's results in `test_counts_for_a_linked_page`;
   [test_hooks.py](tests/crawl/test_hooks.py) checks pass execution/order in
   `test_post_crawl_passes_run_before_a_crawl_is_completed` and
   `test_post_crawl_passes_run_in_the_order_the_hooks_declare`.
   Strict mypy checks the writer boundary in
   [test_handler_types.py](tests/test_handler_types.py),
   `test_a_pass_that_closes_the_crawl_s_writer_fails_mypy`.
6. **Register the composition.** Extend `default_hooks()` in
   [services/hooks.py](src/openlinx/services/hooks.py): it includes `PAGE_LINKS`,
   `handler("links", link_rows, write_links)` and `Pass("inlinks", count_inlinks)`.
   Retain the other registrations, including the `response_headers` handler.
   At seam 3+6, [test_hooks.py](tests/crawl/test_hooks.py) checks registration with
   `test_a_registered_handler_sees_each_recorded_outcome_once`.
   [test_code_style.py](tests/test_code_style.py) enforces the factory boundary in
   `test_hooks_and_links_are_built_only_through_their_factories` and keeps plugin
   imports out of the crawl core in `test_the_crawl_core_imports_no_plugin_layer`.
   If a new cross-package import is needed, update its package interface docstring;
   [test_package_interfaces.py](tests/test_package_interfaces.py) checks
   `test_every_name_used_across_a_package_is_listed`.

## Conventions

- **Terms:** use the terms of [CONTEXT.md](CONTEXT.md) exactly, capitalised as defined there, such as Workspace, Crawl, Page, Issue and Command. This applies in code, tests, docs and commit messages. Test names use them too.
- **Decisions:** a settled architectural decision is an ADR in [docs/adr/](docs/adr/). Don't reopen a decision that has one. Write a new ADR instead of quietly working around it.
- **Names:** the module `openlinx.naming` holds every name users see: `COMMAND_NAME` (`linx`), `PACKAGE_NAME` (`openlinx`), `PRODUCT_NAME` (`OpenLinx`), the settings file name, the data folder and the global Workspace folder. Use those constants rather than typing a name in `src/`, and say "the settings file" or "the data folder" in comments. `tests/test_naming.py` fails on the literals `openlinx.toml`, `.openlinx`, `"linx"`, `"openlinx"` and `"OpenLinx"` anywhere else in `src/`; tests keep the literals.

## Code style

- Write a comment only for a non-obvious *why*. Don't add a docstring to a function or method whose name and types already say what it does, and don't add a comment that restates the code.
- Each module starts with a one-line docstring that names the design decision it implements, such as "design D7 of 000-scaffold-project". An empty `__init__.py` that only marks a test package needs none.
- An `__init__.py` holds no code: callers import its submodules. A package's docstring is a summary line and the list of its interface, which lives nowhere else.
- **The paradigm** is [ADR-0006](docs/adr/0006-functional-core-frozen-records-protocols.md): logic in pure functions, data in frozen dataclasses (frozen `msgspec.Struct`s for page preparation's per-response records, which cross the parse pool, and for records that define a JSON document), dependencies as parameters typed by a Protocol, state only where it is inherent, no class hierarchies of our own, and pydantic only at the boundary.
- **A memo** of a pure function, `functools.lru_cache(maxsize=N)` on a function whose result depends only on its arguments, is allowed and is not module-level state (ADR-0006). It always has a bound, never `maxsize=None` or `functools.cache`, and a one-line comment at the decorator says why it pays.
- **Errors:**
  - An error that a user or an agent sees is an `OpenLinxError` with a `DiagnosticCode` from the registry in `openlinx.output.codes`. A warning is a `Diagnostic` made with `Diagnostic.of(code, ...)` and given to the `Reporter`. Never report a bare message without a code.
  - A broken contract inside our own code, such as a settings table registered twice, raises a built-in `TypeError` or `RuntimeError`. It is a bug, not a diagnostic.
  - An error class of the store, such as `CrawlWriterClosedError`, is turned into a code by the service that catches it.
- **`# type: ignore[code]` and `# noqa: CODE`** always name the code, and are used only when the fault is not ours: a third-party API or stub, or the one place that one of our banned-API rules (`TID251`) leads to. In a test, a deliberate type guard or a deliberately wrong call takes one too, with its reason. Prefer fixing the type. A short reason goes on the line, or in the comment right above it when the line would grow too long. That comment must not start with `noqa`, which ruff would read as a blanket directive and flag (`RUF100`).
- **Private names** start with `_`. A module's public names are the ones without it, and only those are imported from other modules.
- **Size, a guide and not a gate:** a module past about 300 non-blank lines, or a class past about 10 methods, is a question for review. The table below records each one and its next split or why it stays together. Complexity rules in ruff stay in the ROADMAP Backlog ("Code quality checks").

  Counts include non-blank comments and docstrings. Methods are directly declared, including `__init__` and properties. Paths are under `src/openlinx/`.

  | Module | Non-blank lines | Class (methods) | Next split, or why it stays together |
  |---|---:|---|---|
  | `crawl/engine/dispatch.py` | 335 | — | Frontier traversal and dispatch apart from pause and outage coordination. |
  | `crawl/engine/pause.py` | 345 | `NetworkPause` (17) | Extract redispatch and probe scheduling and classification; `NetworkPause` keeps its count and state transitions. |
  | `crawl/engine/units.py` | 370 | — | Response preparation and handler rows apart from URL record construction. |
  | `crawl/fetch/requester.py` | 288 | `Requester` (14) | Extract retry and backoff orchestration into functions; `Requester` keeps request admission and the watchdog for each attempt. |
  | `extract/unicode_scripts.py` | 1193 | — | Generated Unicode range tables, with no runtime logic; keep one generated module for the pinned Unicode version. |
  | `output/codes.py` | 343 | — | One declaration per diagnostic code; it grows with the registry, not with its logic. |
  | `services/crawling.py` | 574 | — | Move planning, from settings to Scope and the Seed's checks, into its own module. |
  | `store/schema.py` | 1179 | — | Declared tables and columns; keep the public schema in its owning module. |
  | `store/urls.py` | 484 | — | Split by kind of unit: recording, frontier and counts, each with its statements built at import. |
  | `store/writer.py` | 518 | `CrawlWriter` (35) | Batch and replay functions, and a separate submission window, as ADR-0006 describes. |

- **Imports:**
  - Our own code is imported by name, as in `from openlinx.output.codes import USAGE_ERROR`, never as a module.
  - A standard-library or third-party module is imported either way: whole where its functions are called through it (`asyncio`, `sqlite3`, `re`, `time`, `orjson`, `typer`), and by name otherwise (`from pathlib import Path`).
  - An import inside a function only keeps a heavy module off the startup path, such as `rich` in `openlinx.output.table`. `tests/cli/test_startup.py` checks what a startup loads.
- **Formatting** is `ruff format`'s: double quotes, and lines of at most 100 characters.

## Windows notes

- **Checks:** `uv run scripts/check.py` works the same in bash and in Windows PowerShell 5.1 (which has no `&&`).
- **Tests:** use `127.0.0.1`, never `localhost`. On Windows, `localhost` tries `::1` first, and a refused connection there costs about 2 seconds. The fixture site binds `127.0.0.1` only.
- **Line endings:** every text file is checked out with LF, whatever `core.autocrlf` says (`.gitattributes`). The fixture-site pages are the exception: they are served byte for byte.
