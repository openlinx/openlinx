"Drive" means one TDD slice:
1. Write the failing test for the named scenario at the named seam, and watch it fail for the right reason.
2. Write only enough code to pass.
3. Run `uv run scripts/check.py`.
4. Commit. One task = one commit, and the message names the scenario.

Scenario names are the `#### Scenario:` titles in `specs/<capability>/spec.md`. Seams are those of docs/testing.md:
- seam 1: CLI
- seam 2: the Workspace API
- seam 4: pure logic

"The fixture app" is the app from `build_app(extra=…)` with the contract fixture Commands, the `example` settings table and, from task 9.3, the keyed `groups` table (design D8). The only test double is `FakeClock`.

A **guard** is a test for a scenario that earlier code already satisfies. It passes on its first run, and it is kept to pin the contract.

## 1. CLI core and `spider commands` (seam 1)

- [x] 1.1 Setup:
  - Add `pydantic-settings`, `orjson` and `rich` to the runtime dependencies, and to `tests/dependency_allowlist.txt` from 000.
  - Add ruff `banned-api` entries for `sys.stdout`, `sys.stderr`, `typer.echo` and `click.echo` outside `spider.output`.
  - Move 000's `--version` write into `spider.output`. In 000 it writes to `sys.stdout.buffer` directly from `spider.cli.app`, and the new ban would flag it. `Output` takes the write over in task 1.2.
  - Add `build_app()` in `spider.cli.app`, with the entry point calling it.

  Verify: `uv run scripts/check.py` passes, including 000's `--version` tests.
- [x] 1.2 Drive "The Command lists itself" (cli-contract).
  - Red: add `CliResult.json()` to `tests/support/cli.py`.
  - Green:
    - the `Output` object writing orjson bytes to `sys.stdout.buffer`
    - `@command_meta`
    - a minimal `spider commands`
- [x] 1.3 Drive "Tool version" (cli-contract). Green: the `tool` block.
- [x] 1.4 Drive "Unknown Command" (cli-contract).
  - Red: add `CliResult.stderr_json_lines()` to the helper.
  - Green:
    - `SpiderError` and the diagnostic line writer
    - running the app with `standalone_mode=False`
    - `usage_error` with exit code 2
- [x] 1.5 Drive "Error object" (cli-contract). Green: the exact diagnostic keys.
- [x] 1.6 Drive "Nothing on stdout when a Command fails" (cli-contract). Green: documents are written only when the Command ends.
- [x] 1.7 Drive "The table is self-described" (cli-contract). Green: the `ExitCode` enum and `exit_codes`.
- [x] 1.8 Drive "Unsupported format" (cli-contract). Green:
  - `FormatOpt`
  - `formats` in `@command_meta`
  - `invalid_value`, with a hint listing the Command's formats
- [x] 1.9 **Guard:** "Help" and "Version" (cli-contract). Typer and 000 already provide both.
- [x] 1.10 Drive "No arguments" (cli-contract). Typer's `no_args_is_help` exits 2 from Click 8.2 on. Green: bare `spider` prints the root help and exits 0.
- [x] 1.11 Docs: write `docs/cli.md` with stdout versus stderr, the diagnostic shape and the exit code table.
- [x] 1.12 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. Workspace resolution (seam 2)

- [x] 2.1 Drive "Workspace in the current folder" (workspace). Green: `resolve_workspace(cwd, flag, home)`.
- [x] 2.2 Drive "Workspace in a parent folder" and "The nearest Workspace wins" (workspace), a trivial pair. Green: walk up to the home folder.
- [x] 2.3 Drive "A settings file alone marks a Workspace" (workspace).
- [x] 2.4 Drive "Fallback to the global Workspace" (workspace).
- [x] 2.5 Drive "The home folder is the global Workspace" and "Location of the global Workspace" (workspace), a trivial pair.
- [x] 2.6 Drive "The flag wins" (workspace).
- [x] 2.7 Drive "The home folder given with --workspace" (workspace). This is the `.mcpb` default for `spider mcp --workspace` (`090`).
- [x] 2.8 Drive "Missing --workspace folder" (workspace). Green: `workspace_not_found`, registered with exit code 4.
- [x] 2.9 Drive "Forward slashes on Windows" (workspace), as a Windows-only test.
- [x] 2.10 Drive "Home folder with non-ASCII characters on Windows" (workspace), as a Windows-only test.
- [x] 2.11 **Guard:** "A Workspace variable is ignored" (workspace). Nothing reads the environment, and the test keeps it that way.
- [x] 2.12 Docs: write `docs/workspace.md` on the Workspace layout and discovery, including the home-folder stop, `spider.toml` as a marker, and "no environment variables".
- [x] 2.13 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. `spider init` and encoding (seam 1)

- [x] 3.1 Drive "First run" (workspace). Green: `spider init`, creating the folders and writing a placeholder `spider.toml`.
- [x] 3.2 Drive "Files of a new local Workspace" (workspace).
- [x] 3.3 Drive "Data folder ignores its own contents" (workspace). Green: the `.gitignore` content.
- [x] 3.4 Drive "Second run creates nothing" (workspace).
- [x] 3.5 Drive "Existing settings file is kept byte for byte" (workspace).
- [x] 3.6 Drive "Target folder is created" (workspace). Green: `WorkspaceOpt` on `init`.
- [x] 3.7 Drive "Initialising the home folder" (workspace).
- [x] 3.8 Drive "Nested Workspace warning" (workspace) and "A warning keeps exit code 0" (cli-contract), a trivial pair. Green: warning diagnostics, and the registered code `workspace_nested`.
- [x] 3.9 Drive "Unwritable target folder" (workspace), using a real path under a regular file. Green: `workspace_not_writable` with exit code 7, whose message names the folder.
- [x] 3.10 Drive "Only JSON lines on stderr" (cli-contract).
- [x] 3.11 Drive "Non-ASCII characters are not escaped" (cli-contract).
- [x] 3.12 Drive "Piped output on Windows" (cli-contract) with `run_cli_process`, as a Windows-only test.
- [x] 3.13 Drive "PYTHONIOENCODING does not change the output" (cli-contract) with `run_cli_process`, on every OS.
- [x] 3.14 Drive "UTF-8 on stderr" (cli-contract) with `run_cli_process`.
- [x] 3.15 Drive "No carriage returns on Windows" (cli-contract) with `run_cli_process`, as a Windows-only test.
- [x] 3.16 Docs: add `spider init` and its result to `docs/workspace.md`.
- [x] 3.17 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. Settings (seams 2 and 1, with the `example` table registered by tests)

- [x] 4.1 Drive "Default" (workspace). Green: the settings registry, `register_settings_table`, and resolved settings.
- [x] 4.2 Drive "Settings file over default" (workspace). Green: the TOML source.
- [x] 4.3 Drive "A settings file in the home folder is not read" (workspace), with the `example` table registered by the test. Moved here from group 2: it needs the settings of 4.1 and 4.2. Green: settings load only from the resolved Workspace's settings file.
- [x] 4.4 Drive "Flag over settings file" (workspace). Green: flag values passed as init kwargs.
- [x] 4.5 Drive "Setting variables are ignored" (workspace). Green: drop the env, dotenv and secrets sources.
- [x] 4.6 Drive "Invalid value" (workspace) at seam 1. Green:
  - `spider init` validates an existing `spider.toml`
  - `settings_invalid` with exit code 3, `details.file` and `details.errors`
- [x] 4.7 Drive "Unknown key with a suggestion" (workspace). Green: `extra="forbid"` and the closest-match hint.
- [x] 4.8 Drive "Output flags have no settings key" (workspace).
- [x] 4.9 Drive "TOML syntax error" (workspace). Green: `line` from `TOMLDecodeError`.
- [x] 4.10 Drive "Every problem is listed" (workspace).
- [x] 4.11 Drive "Nothing is created when the settings are invalid" (workspace).
- [x] 4.12 Drive "Commands without a Workspace ignore the settings file" (workspace).
- [x] 4.13 Drive "A setting in the template" (workspace). Green: generate the commented template from the registered tables, replacing the placeholder from task 3.1.
- [x] 4.14 Drive "Template loads as defaults" (workspace) at seam 2.
- [x] 4.15 Docs: add the `spider.toml` section to `docs/workspace.md`: registered tables, precedence, validation and errors, and the template.
- [x] 4.16 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Formats and JSON Lines (seam 1, fixture app)

- [x] 5.1 Drive "Compact document" (cli-contract). Green:
  - the fixture app with the example list Command
  - the `list` output kind, with a minimal envelope
- [x] 5.2 Drive "Table for people" (cli-contract). Green: the rich table rendered to text, then UTF-8 bytes.
- [x] 5.3 Drive "Unknown format" (cli-contract).
- [x] 5.4 Drive "Errors stay JSON" (cli-contract).
- [x] 5.5 Drive "Items as lines" (cli-contract). Green: `jsonl` for lists.
- [x] 5.6 Drive "Rows by default" (cli-contract). Green: the `rows` output kind, written and flushed per row.
- [x] 5.7 Drive "Documents have no JSON Lines" (cli-contract).
- [x] 5.8 Docs: add the formats and JSON Lines to `docs/cli.md`.
- [x] 5.9 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green.

## 6. Paging, fields and cursors (seams 4 and 1, example list Command)

The paging logic lives in the pure module `spider.output.paging` (design D6): the cursor codec, the fingerprint, the `Page(items, total, next_cursor)` type, field selection and the in-memory pager. It imports only the standard library, orjson and `spider`, never Click. `050` builds SQL keyset paging on the same `Page` and codec, and `090` calls it without Click.

- [x] 6.1 Drive "Cursor round trip" and "Cursor characters" (cli-contract) at seam 4, a trivial pair. Green: `spider.output.paging` with the cursor codec of design D6, without padding.
- [x] 6.2 Drive "Undecodable cursor" (cli-contract) at seam 4, table-driven: `abc`, the empty string, base64 that is not JSON, a wrong `v`, a missing `k`, and a different fingerprint. Green: the codec's validation, which raises `invalid_cursor`.
- [x] 6.3 Drive "First page" (cli-contract) at seam 1. Green:
  - `Page(items, total, next_cursor)` and the in-memory pager in `spider.output.paging`
  - `--limit` pages through the pager, whose `next_cursor` comes from the codec
  - the example list Command returns a `Page`. The `@command_meta` wrapper only adapts a `Page` to the formats: it never slices, pages or projects items.
- [x] 6.4 Drive "Following cursors" (cli-contract). Green: `--cursor`, read back by the pager.
- [x] 6.5 Drive "Everything on one page" and "Default limit" (cli-contract), a trivial pair, using the 60-item fixture list.
- [x] 6.6 Drive "Count only" (cli-contract).
- [x] 6.7 **Guard:** "Same request, same output" (cli-contract).
- [x] 6.8 Drive "Limit above the maximum" and "Negative limit" (cli-contract), a trivial pair.
- [x] 6.9 **Guard:** "Limit of the wrong type" (cli-contract). Task 5.3 already maps Click `BadParameter` to `invalid_value`.
- [x] 6.10 Drive "Default fields" and "Fields in the requested order" (cli-contract), a trivial pair. Green: `--fields`, and field selection in `spider.output.paging`, with the default fields from `@command_meta`.
- [x] 6.11 Drive "Default format comes first" and "Default fields are available" (cli-contract), a trivial pair. Green: `check_command` refuses a Command whose `--format` default is not `formats[0]`, or whose default fields are not a subset of `available`. Today the second would surface as a `KeyError` at run time.
- [x] 6.12 Drive "All fields" (cli-contract).
- [x] 6.13 Drive "Unknown field" (cli-contract). Green: `unknown_field` with `details.available`.
- [x] 6.14 **Guard:** "A different limit continues the list" (cli-contract). The keyset of task 6.4 is a position, not a page number, so it already holds.
- [x] 6.15 Drive "Cursor from a different request" (cli-contract). Green: the fingerprint in `spider.output.paging`, from the Command path and the arguments that select or order items.
- [x] 6.16 **Guard:** "Garbage cursor" (cli-contract) at seam 1. The codec of 6.2 already rejects it.
- [x] 6.17 Drive "More items notice" (cli-contract). Green: the info line `more_items` for `jsonl` and `table`.
- [x] 6.18 Docs: add paging, `--fields` and cursors to `docs/cli.md`.
- [x] 6.19 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.

## 7. Progress events, partial results and diagnostics

The streams and the Reporter follow design D3: `Output(stdout, stderr)` takes its byte streams and is built once, in the runner. Every stderr line is written under one `threading.Lock` and flushed. Services report through the `Reporter` protocol, never through `Output`. In the real-process tests, every wait has a hard timeout of a few seconds, so a missing line or signal file fails the test instead of hanging CI. The handshake has no fixed sleeps: each side acts only on what it has read.

- [x] 7.1 Drive "Spaces and repeats in --fields" and "Empty field name" (cli-contract), a trivial pair, decided in the group 6 review. Green: `select_fields` strips each name, keeps the first of a repeated name, and refuses an empty name with `invalid_value`.
- [x] 7.2 Drive "Event line" (cli-contract) at seam 4, with `FakeClock`. Green: the event encoder.
- [x] 7.3 Drive "The result goes to stdout" (cli-contract) at seam 1, with the fixture progress Command. Green:
  - `Output(stdout, stderr)` takes its byte streams. The runner builds it once from `sys.stdout.buffer` and `sys.stderr.buffer`, and `spider.output.writer` no longer reads `sys.*`.
  - the `Reporter` protocol: `warn(diagnostic)` and `event(name, **data)`
  - the CLI reporter, which writes through `Output` and is reached from the `Invocation`
  - `init`'s `workspace_nested` warning goes through the reporter
- [x] 7.4 **Guard:** "Events go to stderr" (cli-contract) at seam 1. The CLI reporter of 7.3 already writes events to stderr.
- [x] 7.5 **Guard:** "Events and diagnostics share stderr" (cli-contract), as a real process with `run_example_process`, which runs the fixture app, proving that the lines come out in emission order.
- [x] 7.6 Drive "A warning is readable at once" (cli-contract) as a real process, with a fixture Command that warns and then waits for a line on its stdin, so the handshake needs no polling. Green: every stderr line, event or diagnostic, is written under one `threading.Lock` and flushed. Today `Output.diagnostic` never flushes, and a piped `sys.stderr.buffer` is block-buffered.
- [x] 7.7 Drive "The result of a failed outcome is printed" (cli-contract) at seam 1. Green: `Outcome(result, error)`.
- [x] 7.8 **Guard:** "One error and its exit code" (cli-contract) at seam 1. The runner of 7.7 already writes the error last and exits with its code.
- [x] 7.9 Drive "Unexpected failure" (cli-contract) at seam 1, with the fixture Command that raises. Green: `internal_error` with exit code 70 and `details.traceback`.
- [x] 7.10 Drive "A warning inside a result" (cli-contract) at seam 1. Green: `Diagnostic.to_json()`.
- [x] 7.11 Docs: add progress events, partial results, the order and flushing of stderr lines, and diagnostics inside results to `docs/cli.md`.
- [x] 7.12 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. Global flags, the error-code registry and the complete self-description (seam 1)

Each part of the self-description has one source (design D5 and D7): options and arguments come from the Click params, output kinds, formats and fields from `@command_meta`, and diagnostics from the error-code registry. Nothing is listed twice.

- [x] 8.1 Drive "Before the Command name" (cli-contract). Green: the `argv` check with its hint.
- [x] 8.2 **Guard:** "After the Command name" and "A flag the Command does not use" (cli-contract).
- [x] 8.3 Drive "Global flags of init" (cli-contract). Green: `global` in the option metadata.
- [x] 8.4 Drive "Entry of a document Command" (cli-contract). Green: `output`, `events`, `formats` and `fields` in the entries, derived from `@command_meta`.
- [x] 8.5 Drive "Entry of a list Command" (cli-contract), with the fixture app. Also give the fingerprint its Command identity from one source: the Command name that `@command_meta` and registration know, the same string an MCP tool maps to. No list Command passes its name as a literal, and the Click path is not used, because `090`'s services have no Click.
- [x] 8.6 Drive "Option details" (cli-contract). Green: option and argument entries derived from the Click params.
- [x] 8.7 Drive "Error codes of this change" and "Warning and info codes of this change" (cli-contract), a trivial pair. Green: the error-code registry of design D5.
  - Each code is one constant holding its code, level, exit code and description.
  - `SpiderError` takes that constant instead of a loose string. Migrate every call site: `init.py`, `creation.py`, `discovery.py`, `settings.py`, `runner.py` and `meta.py`.
  - `EXIT_CODE_DESCRIPTIONS` folds into the `ExitCode` enum, so each member carries its description.
  - `spider commands` lists `diagnostics` from the registry.
- [x] 8.8 Drive "Interrupted" (cli-contract) at seam 1, with a fixture Command that raises `KeyboardInterrupt`, and Click's `Abort` too. Green: the runner maps both to `interrupted` (exit 130), registered in the error-code registry of 8.7.
- [x] 8.9 **Guard:** "Naming rule for input errors" (cli-contract). The test reads the same registry that `spider commands` prints and that `090` maps errors from.
- [x] 8.10 Drive "The proxy variables are the one exception" (workspace). Green: the `environment` key of `spider commands`, which lists the proxy family that `022` honours.
- [x] 8.11 **Guard:** "Detection signals change nothing" (workspace), with `CODEX_SANDBOX_NETWORK_DISABLED=1` set for one of the two runs.
- [x] 8.12 Drive "Same description on every OS" (cli-contract). Compare the `init` and `commands` entries with hand-written expected JSON in `tests/contract/commands/`, on every OS.
- [x] 8.13 Docs: add "Using spider" (`init`, `commands`) to `README.md`, and the error-code registry to `docs/cli.md`.
- [x] 8.14 Review: run the code-review skill on group 8's commits, then refactor with the whole suite green. Also switch `example-rows-waiting` to the stdin handshake, so no test polls or sleeps, and give the missing-argument test its own small fixture Command.

## 9. Foundations for later changes

Each task is one commit. Guards and refactors are allowed here, and a refactor names the scenarios that must stay green.

- [ ] 9.1 Drive "Initialising without the CLI" (workspace) at seam 2. Green, following design D9:
  - `spider.services.workspace.init_workspace(request, tables, reporter)`, with a typed `InitRequest` and `InitResult`
  - the `Collected` reporter, which keeps warnings and events in memory. It is production code: `090` uses it to put warnings into a tool result.
  - `spider.cli.init` becomes a thin adapter: it builds the request from the flags, calls the service with the CLI reporter, and returns the result. Every group 3 and group 4 scenario stays green.
- [ ] 9.2 Drive "An unset setting in the template" (workspace), with `example.token` added to the fixture table. Green: the table rules of design D2 allow a `None` default, and the template writes `# <key> =` for it.
- [ ] 9.3 Drive "Named entries" and "Unknown key in a named entry" (workspace), a trivial pair, with the fixture keyed table `[groups]`. Green:
  - a registered table may be `dict[str, V]`, where V is a table model or a TOML literal type (design D2)
  - the closest-key hint walks into the entries of a keyed table
- [ ] 9.4 Drive "A keyed table in the template" (workspace). Green: the template writes a keyed table as its description and a commented `# [<table>.<name>]` header, followed by its entry's settings.
- [ ] 9.5 Drive "Settings tables load with the settings" (cli-contract) as a real process. Green:
  - tables are registered as `"module:Class"` references, resolved only when settings load (design D2)
  - `register()` no longer checks the table rules. A test resolves every table registered by `build_app()` and by the fixture app, and checks the rules of D2 on each.
- [ ] 9.6 Drive "A secret option inherits from its setting" and "A secret option without a setting" (cli-contract), a trivial pair, with the fixture `example` settings Command. Green (design D7):
  - `secret` is declared once, on the settings field
  - an option mapped to a setting inherits it, and `check_command` refuses such an option that also declares `secret`
  - an option without a setting declares `secret` itself
- [ ] 9.7 Drive "Help starts light" and "The self-description starts light" (cli-contract), a trivial pair, replacing 000's deny-list guard. Green: the allowlist of design D10, with Typer's own dependencies, checked by running `spider --help` and `spider commands` in a subprocess and reading `sys.modules`. Today `spider --help` loads rich through Typer's rich help, so this task turns rich help off.
- [ ] 9.8 Refactor: the Typer compatibility module of design D10. Move the `typer._click` imports of `spider.cli.runner` into `spider.cli.click_compat`, ban `typer._click` elsewhere with ruff `banned-api`, and pin `typer>=0.27.2,<0.28`. "Unknown Command", "Limit of the wrong type" and the missing-argument test stay green.
- [ ] 9.9 Refactor: one source for the product name (design D11). Every name-derived string in `src/` comes from the constants of one module, `spider.naming`: the command name in hints and help, the settings file name `spider.toml`, the data folder `.spider`, the global Workspace folder `~/.spider`, and every other use, such as messages, the `.gitignore` line and the template header. Comments and docstrings say "the settings file" or "the data folder" instead of the literal names. A guard test greps `src/` for the literals `spider.toml` and `.spider` outside `spider.naming` and fails on a hit. The Python package name `spider` stays; renaming it is a separate, mechanical step. Tests may keep the literals. Every scenario stays green.
- [ ] 9.10 Docs: in `docs/architecture.md`:
  - add the output layer, the `Reporter` and the services rule: a Command is an adapter plus a service, and `090` calls the service directly
  - add the settings rules of D2: table ownership, `None` defaults, keyed tables, lazy references, and secrets on the field
  - add the error-code registry and the startup allowlist
  - check the HTTP client text against ADR-0001, and fix it only if something has drifted
- [ ] 9.11 Review: run the code-review skill on the whole change, then refactor with the whole suite green.
