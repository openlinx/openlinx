## Context

- `000-scaffold-project` provides what this change builds on:
  - the package layout and the Typer skeleton (`spider --version` only)
  - `spider.clock` with `FakeClock`
  - the CliRunner helpers, home isolation and `temp_workspace`
  - the network guard and the strict quality gates
- The stack is settled: Typer, pydantic-settings, and orjson/msgspec for JSON (docs/architecture.md).
- See proposal.md for why this change comes first.
- The build order is 000 → 010 → 015 → 020.
  - None of this change's own Commands (`init`, `commands`) is a list, a rows Command, a streaming Command or a Command with a partial result.
  - Yet the contract for all of those is fixed here. D8 explains how it is tested all the same.

## Goals / Non-Goals

**Goals:**
- One place that decides the Workspace, the settings, the output and the errors. Later changes plug into it and never reimplement any of it.
- A contract precise enough that `spider commands` can drive the Skill (`080`), and that every Command behaves the same for agents.

**Non-Goals:**
- Crawl files, `spider schema` and `--crawl` (`015`).
- The Crawl's side of Ctrl+C. This change maps an interrupt to `interrupted` (130) for every Command; `020` adds the Crawl state `stopped` with its stop reason.
- Any real setting. The settings system ships here, and its first real table is `[store]` (`015`).

## Decisions

### D1. Workspace model and discovery

- **The model:** a Workspace has a *root*, a *data folder* and a *settings file*.
  - **Local Workspace:** the root is the folder, the data folder is `<root>/.spider`, and the settings file is `<root>/spider.toml`.
  - **Global Workspace:** the data folder is `~/.spider`, and the settings file is `~/.spider/spider.toml`.
- **Discovery** walks up from the current folder and stops at the home folder, which always means the global Workspace. `temp_workspace` (from 000) puts every test root under the fake home, so a test can never climb into the real parents of the temp folder.
- **No environment variables (G7):**
  - Settings come only from flags and `spider.toml`.
  - `SPIDER_WORKSPACE` does not exist. MCP clients pass `spider mcp --workspace <path>` (`090`).
  - **Proxy exception:** the standard proxy variables are honoured because they are the operating system's network configuration. `022` owns that behaviour, and `spider commands` lists them under `environment`.
  - **Detection exception:** signals such as `CODEX_SANDBOX_NETWORK_DISABLED` only shape diagnostics and hints (`080`'s doctor). A test keeps `spider commands` byte-identical with and without one.
- **Alternatives:**
  - **Only `.spider/` marks a Workspace.** Rejected: a fresh clone of a repository with a committed `spider.toml` would silently use the global Workspace.
  - **Settings inside `.spider/`.** Rejected: the data folder is git-ignored, so the settings could not be shared.
  - **`~/spider.toml` for the global Workspace.** Rejected: it clutters the home folder.

### D2. The settings system

- **A registry of tables:** each change contributes one pydantic model per `spider.toml` table. The root settings model is assembled from the registry when settings load.
  - **Registration** is `SettingsTables.register(name, "module:Class")` on a registry built per app, not a global one. `build_app` registers the tool's own tables first (none in this change), then those of `AppExtra(settings_tables=...)`. A later change registers its table in `build_app`, for example `("store", "spider.store.settings:StoreSettings")` in `015`.
  - **Lazy references:** a table is registered by its `"module:Class"` reference and resolved only when settings load, or when the template is written. Building the app, `--help` and `spider commands` without setting-mapped options import no table module, and so no pydantic.
  - Code reads a table through a typed getter, `settings.table(StoreSettings)`, so static typing is kept.
  - Tests build a fresh app whose registry includes the `example` and `groups` tables used by the scenarios (D8), so no test's table leaks into another.
  - `SettingsTables` imports pydantic only for typing, and Commands import the settings module inside their body, so pydantic stays off the CLI's startup path.
- **Ownership:** one table has one owning change, the change that registers it. A later change adds fields by editing that table's model, and never registers a second table for the same concern. For example, `[crawl]` is owned by `020`, and `022`, `024` and `030` add their fields to `CrawlSettings`.
- **Table rules.** The template and the error hints depend on them. They are checked by a test that resolves every table registered by `build_app()` and by the fixture app, not by `register()` at startup, because checking would mean importing every table.
  - `extra="forbid"` on the model.
  - A one-line description on every setting.
  - A default that TOML can write: a string, a finite number, a boolean, or a list of those.
  - Or a `None` default, which makes the setting unset. The template writes it as `# <key> =`, commented out like every other setting.
  - Flat: every key is a setting, with no nested tables, with one exception.
  - **Keyed tables:** a table may be `dict[str, V]`, where V is a table model that follows these rules, or a TOML literal type. Its reference names a module-level alias, such as `RulesTable = dict[str, RuleSettings]`. Only a whole table can be keyed: a field inside a table cannot be a `dict`, until a change needs one. Its keys are names chosen by the user, or ids from a known set, and the entries are written `[<table>.<name>]` for a model, or `<name> = <value>` for a literal. `040`'s `[rules.<id>]` is `dict[str, RuleSettings]`, and `050`'s `[segments]` is `dict[str, str]`. The owning change validates the keys with a pydantic validator, and the problems surface as `settings_invalid` with keys such as `rules.title-to-long`. The template writes a keyed table as its description and a commented `# [<table>.<name>]` header, followed by the entry model's settings, so the file still sets no value.
- **Secrets** are declared once, on the settings field (`json_schema_extra={"secret": True}`). An option mapped to that setting inherits it (D7). `015`'s redaction reads the same declaration.
- **Sources**, set by `settings_customise_sources`:
  1. init kwargs, which carry flag values
  2. a TOML source that reads the Workspace's settings file with `tomllib`
  3. defaults

  The environment, `.env` and secrets-dir sources are dropped.
- **Validation:**
  - `extra="forbid"` on every model.
  - The whole file is validated at load, including tables such as `050`'s `[segments]`, which report through the same `settings_invalid`.
- **Error mapping:**
  - pydantic `loc` tuples become dotted keys, listed in the order the keys appear in the file.
  - `difflib.get_close_matches` supplies the hint.
  - `tomllib.TOMLDecodeError` supplies `line`: its `lineno` on Python 3.14, the message's "at line N" on 3.12 and 3.13.
  - A settings file that is not UTF-8, or that is a folder, is `settings_invalid` too.
  - **Flag values are not file problems.** When the first setting-mirroring flag is wired, a flag value that fails validation SHALL be reported as `invalid_value` (exit code 2), naming the flag. It must not become `settings_invalid` against `details.file`. `load_settings` today reports every validation error against the file, because no Command passes flags yet.
- **The commented template** is generated from the registered models:
  - a header comment that states the precedence
  - then, for each table: the uncommented table header, the field's description as a comment, and `# key = <default as a TOML literal>`
- **Alternatives:**
  - **A static root model to which each change adds a field.** Simpler, but tests could not add the example table without editing production code.
  - **Hand-written validation.** More code for the same errors.

### D3. Output layer (`spider.output`)

- **One `Output` object per invocation.** `Output(stdout, stderr)` takes its two byte streams. The runner builds it once, from `sys.stdout.buffer` and `sys.stderr.buffer`, and puts it on the `Invocation`; `spider.output` never reads `sys.*` itself, so tests and `090` can hand it other streams. Nothing is written through the text layer. With PEP 528, the Windows console's raw layer accepts UTF-8 bytes, so the console display is correct too.
- **stderr lines are atomic and immediate.** Every stderr line, event or diagnostic, is written under one `threading.Lock` and flushed. A piped `sys.stderr.buffer` is block-buffered, so without the flush a warning would reach an agent only when the process ends, and without the lock lines written from two threads could interleave. Lines come out in emission order.
- **The Reporter.** Services and Commands report through a `Reporter` protocol with two methods, `warn(diagnostic)` and `event(name, **data)`, and never touch `Output`.
  - The CLI reporter writes each call through `Output` as one stderr line.
  - The `Collected` reporter keeps the calls in memory. It is production code: `090` puts the collected warnings into a tool result, and seam-2 tests read it.
- **Output kinds**, declared per Command in `@command_meta`:

  | Kind | Result |
  |---|---|
  | `document` | one object |
  | `list` | the paging envelope, or items as rows with `jsonl` and `table` |
  | `rows` | a data stream, `jsonl` by default |

  `events=True` marks a Command that reports progress.
- **Rendering by format:**
  - **JSON and JSON Lines:** `orjson.dumps` (compact, UTF-8) plus `\n`.
  - **Table:** rich `Console(file=StringIO(), color_system=None, width=…)` rendered to text. The width is the terminal width on a TTY, otherwise 120.
- **When bytes are written:**
  - Documents and lists are rendered fully and written only when the Command ends. That gives "nothing on stdout when a Command fails".
  - Rows are written and flushed row by row.
  - **Partial results (G2):** a document Command returns `Outcome(result, error)`. Lists and rows have no partial result: a list fails whole, and a rows Command's earlier rows are already written. The runner writes the result, then the error line, then exits with the error's exit code.
- **Progress events (G1):** the CLI reporter's `event(name, **data)` writes `{"event","ts","data"}` to stderr through `Output`, and flushes. The time comes from the injected `Clock`, formatted `YYYY-MM-DDTHH:MM:SS.sssZ`. stdout never carries events.
- **Lint guard:** ruff `banned-api` forbids `sys.stdout`, `sys.stderr`, `print`, `typer.echo` and `click.echo` outside `spider.output`.
- **Alternatives:**
  - **`sys.stdout.reconfigure(encoding="utf-8")`.** It leaves `\r\n` translation and third-party writes as risks.
  - **Relying on `PYTHONUTF8`.** Not under our control.
  - **A result event at the end of stdout.** Dropped by G1: stdout carries only the result.

### D4. The CSV policy

Moved to `050-add-query-and-segments`, together with the `csv` format, `--no-bom` and `-o`, as decided by the maintainer on 2026-10-01.

### D5. Errors, the diagnostic registry and exit codes

- **The error-code registry:** every diagnostic code is one constant, `DiagnosticCode(code, level, exit_code, description)`, declared in the pure module `spider.output.codes`. The module's constants, in declaration order, are the one list of codes.
  - `spider commands` prints `diagnostics` from it, the naming-rule test reads it, and `090` maps errors to MCP errors from it.
  - A later change adds its codes to that module. Codes are never declared anywhere else, so nothing has to be imported to list them.
  - A test enforces the naming rule: `invalid_*`, `unknown_*` and `usage_error` map to 2, and `*_not_found` and `no_crawls` map to 4. Warnings and info codes have no exit code.
- **Exit codes:** the `ExitCode` enum carries each member's description, so the exit code table has one source too.
- **Errors:** `SpiderError(code, message, hint=None, details={})` takes a `DiagnosticCode` constant, never a loose string, and its exit code comes from that constant. Warnings and info lines are `Diagnostic` objects built from a constant of their level, such as `WORKSPACE_NESTED`.
- **Diagnostics inside results:** a result that carries diagnostics, such as `crawl.warnings` or a list of per-target errors, holds `Diagnostic.to_json()` objects with the full shape (G6).
- **Running the app:** the Typer app runs with `standalone_mode=False`.

  | What is raised | Diagnostic |
  |---|---|
  | Click `UsageError` | `usage_error` |
  | Click `BadParameter` | `invalid_value` |
  | a known global flag found before the Command name (checked on `argv` before Click parses) | `usage_error`, with the hint |
  | `KeyboardInterrupt`, or Click's `Abort` (Ctrl+C or end of input inside Click) | `interrupted` (130) |
  | any other `Exception` | `internal_error` (70), with `traceback.format_exc()` |

- **Why these exit codes:** 1 means "failed" (`080` uses it for failed checks), and 70 (`EX_SOFTWARE`) marks a bug, so agents can tell a failed operation from a defect. Ctrl+C is `interrupted` (130): a user's interrupt is not a bug, so it never becomes `internal_error`.
- **Alternatives:**
  - **Click's plain-text errors.** Not parseable.
  - **Exit code 1 for everything.** Agents could not branch on the kind of failure.
  - **UPPER_CASE codes.** Rejected: lowercase matches the enumeration values stored in the crawl store.

### D6. Paging and cursors

- **Cursor format:** `base64url(orjson({"v":1,"q":fingerprint,"k":keyset}))`, without padding.
  - The fingerprint is the first 16 hex characters of the SHA-256 of the canonical JSON of the Command path plus the arguments that select or order items.
  - `--limit`, `--fields` and `--format` are excluded from the fingerprint.
- **This change provides,** in the pure module `spider.output.paging` (standard library, orjson and `spider` only, never Click):
  - the codec and its validation, which raises `invalid_cursor`
  - the fingerprint
  - `Page(items, total, next_cursor)`, the one type every list result is
  - field selection, which raises `unknown_field`
  - an in-memory pager for static lists, which returns a `Page`
- **Who does what:**
  - The service, or the Command for a static list, selects the fields, pages the items and returns a `Page`.
  - The `@command_meta` wrapper only checks the format and adapts the `Page`: the envelope for `json`, items as lines for `jsonl`, a table for `table`, plus the `more_items` notice. It never slices, pages or projects items, so a pager that is not in memory needs no change to the wrapper.
- **What later changes do:**
  - `015`'s `spider schema` uses the in-memory pager.
  - `050` builds its SQL keyset paging on the same `Page` and codec, and adds the crawl id and its filters to the fingerprint.
  - `090` calls the same services and returns the same `Page`, with no Click involved.
- **Alternatives:**
  - **Offset cursors.** Items would be skipped or repeated while a Crawl is running.
  - **Signed cursors.** There is no security need for a local tool.

### D7. `spider commands` and the global flags

- **Walking the Commands:** `spider commands` walks the Click tree of the app and skips hidden Commands.
- **Metadata:**
  - Each Command registers its `output` kind, `events`, formats, fields and examples with `@command_meta(...)`.
  - Options carry `global` and `setting` in their Typer `metadata`, and `secret` only when they map to no setting.
- **One source for each fact:** arguments and options, with their types, defaults and choices, are read from the Click params. Nothing restates them.
- **Secrets:** an option mapped to a setting inherits `secret` from the settings field (D2), and `check_command` refuses such an option that also declares `secret`. An option with no setting declares `secret` itself. Resolving the inherited flag imports the table's model, so `spider commands` loads pydantic once an option maps to a setting (D10).
- **Consistency, checked by `check_command` when the app is built:**
  - the kind can serve every listed format, and the Command declares the parameters its kind reads
  - the `--format` default is `formats[0]`
  - the default fields are a subset of `available`, and only list and rows Commands have fields
- **Defaults** are printed as JSON values. Defaults that depend on the OS are symbolic (for example `null` plus a description that says `~/.spider`), so the output is identical everywhere.
- **Global flags** are defined once, as reusable annotated option types that each Command adds after its name:
  - this change builds `WorkspaceOpt` and `FormatOpt`
  - `015` adds `CrawlOpt`
- **Alternative:** root-level Click options. They must come *before* the Command, while agents and examples write them after. Accepting both positions is a possible later relaxation (Open Questions).

### D8. Contract fixtures: example Commands and an example setting

- **The problem:** the contract covers lists, rows, progress events, partial results and unexpected failures, but none of this change's Commands has any of them.
- **The app factory:** `spider.cli.app.build_app(extra=…)` builds the real Typer app, and optionally registers more Commands and settings tables. The installed entry point calls `build_app()` without extras.
- **What tests add:** the tests build a fresh app with contract fixture Commands and the `example` settings table, and run it at the CLI seam through `run_cli(..., app=…)`:
  - the example list Command (items `n`/`sq`, with `--odd`)
  - a 60-item list
  - a rows Command
  - a progress-reporting Command
  - a partial-result Command
  - a Command that raises `RuntimeError`
  - a Command whose result holds a warning
  - a Command that writes a warning and then waits for a line on its stdin
  - the `example` settings Command, whose `--level` maps to `example.level`, whose `--token` maps to the secret `example.token`, and whose `--api-key` maps to no setting and is secret
  - the keyed settings table `groups`, whose entries each have a `level`
- **Why this is not a test double:** the fixture Commands use the same public registration API as real Commands, and they replace none of our code. They are consumers of the contract, the way a test route exercises a web framework.
- **Alternatives:**
  - **Make `spider commands` a list Command.** It would bloat the self-description with paging, and leave events and partial results untested all the same.
  - **Leave these scenarios to later changes.** The contract would ship untested in the change that owns it.

### D9. Services: a Command is an adapter plus a service

- **The rule:** a Command is a thin Click adapter over a service. The adapter turns flags into a typed request, picks the reporter, calls the service and returns its result. The service holds the logic: plain Python with typed inputs and outputs, a `Reporter` for warnings and events (D3), and no Click, Typer or `Output`.
- **This change:** `spider.services.workspace.init_workspace(request, tables, reporter)` takes an `InitRequest` and returns an `InitResult`. `spider.cli.init` is its adapter. `spider commands` is a pure description of the Click tree, so it has no service.
- **Later changes:** every Command follows the rule. `090`'s MCP tools call the same services with the `Collected` reporter, so the CLI and MCP never differ in behaviour, and seam 2 tests the services directly.
- **Alternative:** MCP tools that invoke the Click Commands. Rejected: they would parse argv, and capture and re-parse stdout.

### D10. Startup imports and the Typer dependency

- **An allowlist, not a deny list:** a test runs `spider --help` and `spider commands` in a fresh interpreter and reads `sys.modules`. Every loaded top-level module must be in the standard library (`sys.stdlib_module_names`), Typer and its own dependencies, orjson or `spider`. A new dependency then fails the test until it is allowed or imported lazily, which a deny list of known heavy libraries cannot catch.
  - `spider commands` may also load pydantic once an option maps to a setting, because the inherited `secret` flag is read from the settings field (D7). In this change no option of the real app maps to a setting.
  - Typer's own dependencies, such as shellingham and annotated_doc, are allowed.
  - Typer's rich help is turned off: our main readers are agents, and plain Click help is cheaper to parse and keeps rich, markdown_it and pygments off the startup path. rich stays a runtime dependency, imported only for `--format table`.
- **Typer compatibility:** Typer 0.27 vendors Click as the private `typer._click`, and does not re-export `UsageError` or `MissingParameter`. Those imports live in one module, `spider.cli.click_compat`, ruff bans `typer._click` everywhere else, and `typer` is pinned below 0.28. A Typer upgrade then touches one file and one pin.

## Test seams

Seams from docs/testing.md used by this change:
- **CLI (1).**
  - CliRunner covers:
    - `spider init` and `spider commands`
    - the fixture Commands of D8
    - every output, format, paging, diagnostic and exit-code scenario
  - Real subprocess runs on every OS cover:
    - UTF-8 bytes
    - `PYTHONIOENCODING`
    - no `\r`
- **Services and store API (2):** the Workspace API: `resolve_workspace`, resolving settings with flag overrides, the environment-variable scenarios, and the `init_workspace` service with the `Collected` reporter (D9).
- **Pure-logic modules (4):** the event-line encoder with `FakeClock`, and the cursor codec of `spider.output.paging`.

Test doubles:
- **The clock (`FakeClock`)** is the only one. It is in the list of allowed boundary doubles.
- **Unwritable folders** are real: a path under a regular file (`notes.txt/site`) fails on every OS without any fake.
- **The contract fixtures of D8** are registered consumers, not doubles.
- **The `Collected` reporter** is production code that `090` uses, not a double.

No new seam is introduced.

## Risks / Trade-offs

- **Fixture Commands could drift from how real Commands use the contract.**
  - They use the same `@command_meta` and `Output` API.
  - `015`'s `spider schema` and every later Command re-check the contract with real data.
- **The discovery search stops at the home folder, so a Workspace above home is never found.**
  - Accepted. `--workspace` covers that case.

## Migration Plan

Nothing to migrate: this change is greenfield.

## Interface points for later changes

- **Commands:**
  - Write the logic as a service with typed inputs and a `Reporter`, and the Command as its thin adapter (D9).
  - Register `@command_meta` with the output kind, `events`, formats, fields and examples, and use the global flag types.
  - Declare every code as a `DiagnosticCode` constant in `spider.output.codes`, lowercase and following the naming rule, and raise `SpiderError` with it.
  - Put diagnostics inside results with `Diagnostic.to_json()`.
- **Streams and outcomes:**
  - Warnings and progress go through the `Reporter`, never `Output`.
  - A failed outcome is returned as `Outcome(result, error)`. `020`'s `seed_unreachable` (exit 8) and a Crawl stopped with Ctrl+C (exit 130) use it, and so do `080`'s failed checks (exit 1).
- **Settings:**
  - Register a table by its `"module:Class"` reference in `build_app`. The table-rules test of D2 checks it. A table belongs to one change, and later changes add fields to its model.
  - A setting that mirrors a flag lives in `[<command>]` under the flag's name, with `_` for `-`. Mark it `secret` on the settings field (`015` redacts it), and the option inherits the flag.
  - Use a `None` default for an unset setting, and a keyed table for user-named entries such as `[rules.<id>]` and `[segments]`.
  - The first change that adds a path-valued setting also specifies that relative paths are taken from `spider.toml`'s folder.
- **Paging:** list Commands return a `Page` and use the codec from D6. SQL-backed lists (`050`) add the crawl id and their filters to the fingerprint, and use `unknown_field` for `--fields` and `unknown_column` for `--where` and `--sort`.
- **CSV:** every CSV writer goes through `050`'s policy. That includes `050`'s export and `070`'s Report files.

## Open Questions

- Should there be a `spider workspace` Command that shows the resolved Workspace and the effective settings? It would help agents debug, but it is a new Command, so it is left for the maintainer to decide.
- Should global flags also be accepted before the Command name? That would be an additive relaxation of D7.
