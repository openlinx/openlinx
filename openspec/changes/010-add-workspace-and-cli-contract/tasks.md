"Drive" means one TDD slice:
1. Write the failing test for the named scenario at the named seam, and watch it fail for the right reason.
2. Write only enough code to pass.
3. Run `uv run scripts/check.py`.
4. Commit. One task = one commit, and the message names the scenario.

Scenario names are the `#### Scenario:` titles in `specs/<capability>/spec.md`. Seams are those of docs/testing.md:
- seam 1: CLI
- seam 2: the Workspace API
- seam 4: pure logic

"The fixture app" is the app from `build_app(extra=…)` with the contract fixture Commands and the `example` settings table (design D8). The only test double is `FakeClock`.

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
- [ ] 2.11 **Guard:** "A Workspace variable is ignored" (workspace). Nothing reads the environment, and the test keeps it that way.
- [ ] 2.12 Docs: write `docs/workspace.md` on the Workspace layout and discovery, including the home-folder stop, `spider.toml` as a marker, and "no environment variables".
- [ ] 2.13 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. `spider init` and encoding (seam 1)

- [ ] 3.1 Drive "First run" (workspace). Green: `spider init`, creating the folders and writing a placeholder `spider.toml`.
- [ ] 3.2 Drive "Files of a new local Workspace" (workspace).
- [ ] 3.3 Drive "Data folder ignores its own contents" (workspace). Green: the `.gitignore` content.
- [ ] 3.4 Drive "Second run creates nothing" (workspace).
- [ ] 3.5 Drive "Existing settings file is kept byte for byte" (workspace).
- [ ] 3.6 Drive "Target folder is created" (workspace). Green: `WorkspaceOpt` on `init`.
- [ ] 3.7 Drive "Initialising the home folder" (workspace).
- [ ] 3.8 Drive "Nested Workspace warning" (workspace) and "A warning keeps exit code 0" (cli-contract), a trivial pair. Green: warning diagnostics, and the registered code `workspace_nested`.
- [ ] 3.9 Drive "Unwritable target folder" (workspace), using a real path under a regular file. Green: `workspace_not_writable` with exit code 7, whose message names the folder.
- [ ] 3.10 Drive "Only JSON lines on stderr" (cli-contract).
- [ ] 3.11 Drive "Non-ASCII characters are not escaped" (cli-contract).
- [ ] 3.12 Drive "Piped output on Windows" (cli-contract) with `run_cli_process`, as a Windows-only test.
- [ ] 3.13 Drive "PYTHONIOENCODING does not change the output" (cli-contract) with `run_cli_process`, on every OS.
- [ ] 3.14 Drive "UTF-8 on stderr" (cli-contract) with `run_cli_process`.
- [ ] 3.15 Drive "No carriage returns on Windows" (cli-contract) with `run_cli_process`, as a Windows-only test.
- [ ] 3.16 Docs: add `spider init` and its result to `docs/workspace.md`.
- [ ] 3.17 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. Settings (seams 2 and 1, with the `example` table registered by tests)

- [ ] 4.1 Drive "Default" (workspace). Green: the settings registry, `register_settings_table`, and resolved settings.
- [ ] 4.2 Drive "Settings file over default" (workspace). Green: the TOML source.
- [ ] 4.3 Drive "A settings file in the home folder is not read" (workspace), with the `example` table registered by the test. Moved here from group 2: it needs the settings of 4.1 and 4.2. Green: settings load only from the resolved Workspace's settings file.
- [ ] 4.4 Drive "Flag over settings file" (workspace). Green: flag values passed as init kwargs.
- [ ] 4.5 Drive "Setting variables are ignored" (workspace). Green: drop the env, dotenv and secrets sources.
- [ ] 4.6 Drive "Invalid value" (workspace) at seam 1. Green:
  - `spider init` validates an existing `spider.toml`
  - `settings_invalid` with exit code 3, `details.file` and `details.errors`
- [ ] 4.7 Drive "Unknown key with a suggestion" (workspace). Green: `extra="forbid"` and the closest-match hint.
- [ ] 4.8 Drive "Output flags have no settings key" (workspace).
- [ ] 4.9 Drive "TOML syntax error" (workspace). Green: `line` from `TOMLDecodeError`.
- [ ] 4.10 Drive "Every problem is listed" (workspace).
- [ ] 4.11 Drive "Nothing is created when the settings are invalid" (workspace).
- [ ] 4.12 Drive "Commands without a Workspace ignore the settings file" (workspace).
- [ ] 4.13 Drive "A setting in the template" (workspace). Green: generate the commented template from the registered tables, replacing the placeholder from task 3.1.
- [ ] 4.14 Drive "Template loads as defaults" (workspace) at seam 2.
- [ ] 4.15 Docs: add the `spider.toml` section to `docs/workspace.md`: registered tables, precedence, validation and errors, and the template.
- [ ] 4.16 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Formats and JSON Lines (seam 1, fixture app)

- [ ] 5.1 Drive "Compact document" (cli-contract). Green:
  - the fixture app with the example list Command
  - the `list` output kind, with a minimal envelope
- [ ] 5.2 Drive "Table for people" (cli-contract). Green: the rich table rendered to text, then UTF-8 bytes.
- [ ] 5.3 Drive "Unknown format" (cli-contract).
- [ ] 5.4 Drive "Errors stay JSON" (cli-contract).
- [ ] 5.5 Drive "Items as lines" (cli-contract). Green: `jsonl` for lists.
- [ ] 5.6 Drive "Rows by default" (cli-contract). Green: the `rows` output kind, written and flushed per row.
- [ ] 5.7 Drive "Documents have no JSON Lines" (cli-contract).
- [ ] 5.8 Docs: add the formats and JSON Lines to `docs/cli.md`.
- [ ] 5.9 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green.

## 6. Paging, fields and cursors (seam 1, example list Command)

- [ ] 6.1 Drive "First page" (cli-contract). Green: the in-memory pager, `--limit`, and the cursor codec of design D6.
- [ ] 6.2 Drive "Following cursors" (cli-contract).
- [ ] 6.3 Drive "Everything on one page" and "Default limit" (cli-contract), a trivial pair, using the 60-item fixture list.
- [ ] 6.4 Drive "Count only" (cli-contract).
- [ ] 6.5 **Guard:** "Same request, same output" (cli-contract).
- [ ] 6.6 Drive "Limit above the maximum" and "Negative limit" (cli-contract), a trivial pair.
- [ ] 6.7 Drive "Limit of the wrong type" (cli-contract). Green: map Click `BadParameter` to `invalid_value`.
- [ ] 6.8 Drive "Default fields" and "Fields in the requested order" (cli-contract), a trivial pair. Green: `--fields`, and the default fields from `@command_meta`.
- [ ] 6.9 Drive "All fields" (cli-contract).
- [ ] 6.10 Drive "Unknown field" (cli-contract). Green: `unknown_field` with `details.available`.
- [ ] 6.11 Drive "A different limit continues the list" (cli-contract).
- [ ] 6.12 Drive "Cursor from a different request" (cli-contract). Green: the fingerprint and `invalid_cursor`.
- [ ] 6.13 Drive "Garbage cursor" (cli-contract).
- [ ] 6.14 Drive "More items notice" (cli-contract). Green: the info line `more_items` for `jsonl` and `table`.
- [ ] 6.15 Docs: add paging, `--fields` and cursors to `docs/cli.md`.
- [ ] 6.16 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.

## 7. Progress events, partial results and diagnostics

- [ ] 7.1 Drive "Event line" (cli-contract) at seam 4, with `FakeClock`. Green: the event encoder.
- [ ] 7.2 Drive "The result goes to stdout" (cli-contract) at seam 1, with the fixture progress Command. Green: `Output.event`.
- [ ] 7.3 Drive "Events go to stderr" (cli-contract) at seam 1.
- [ ] 7.4 Drive "Events and diagnostics share stderr" (cli-contract) at seam 1.
- [ ] 7.5 Drive "The result of a failed outcome is printed" (cli-contract) at seam 1. Green: `Outcome(result, error)`.
- [ ] 7.6 Drive "One error and its exit code" (cli-contract) at seam 1.
- [ ] 7.7 Drive "Unexpected failure" (cli-contract) at seam 1, with the fixture Command that raises. Green: `internal_error` with exit code 70 and `details.traceback`.
- [ ] 7.8 Drive "A warning inside a result" (cli-contract) at seam 1. Green: `Diagnostic.to_json()`.
- [ ] 7.9 Docs: add progress events, partial results and diagnostics inside results to `docs/cli.md`.
- [ ] 7.10 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. Global flags and the complete self-description (seam 1)

- [ ] 8.1 Drive "Before the Command name" (cli-contract). Green: the `argv` check with its hint.
- [ ] 8.2 **Guard:** "After the Command name" and "A flag the Command does not use" (cli-contract).
- [ ] 8.3 Drive "Global flags of init" (cli-contract). Green: `global` in the option metadata.
- [ ] 8.4 Drive "Entry of a document Command" (cli-contract). Green: `output`, `events`, `formats` and `fields` in the entries.
- [ ] 8.5 Drive "Entry of a list Command" (cli-contract), with the fixture app.
- [ ] 8.6 Drive "Option details" (cli-contract).
- [ ] 8.7 Drive "Error codes of this change" and "Naming rule for input errors" (cli-contract), a trivial pair. Green: register every code of this change.
- [ ] 8.8 Drive "The proxy variables are the one exception" (workspace). Green: the `environment` key of `spider commands`, which lists the proxy family that `022` honours.
- [ ] 8.9 **Guard:** "Detection signals change nothing" (workspace), with `CODEX_SANDBOX_NETWORK_DISABLED=1` set for one of the two runs.
- [ ] 8.10 Drive "Same description on every OS" (cli-contract). Compare the `init` and `commands` entries with hand-written expected JSON in `tests/contract/commands/`, on every OS.
- [ ] 8.11 Docs:
  - Add "Using spider" (`init`, `commands`) to `README.md`.
  - Add the output layer and the settings registry to `docs/architecture.md`.
- [ ] 8.12 Review: run the code-review skill on group 8's commits and on the whole change, then refactor with the whole suite green.
