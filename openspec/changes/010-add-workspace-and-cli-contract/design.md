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
- Ctrl+C handling. Exit code 130 is reserved here, and `020` implements it together with its scenario.
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

- **A registry of tables:** each change registers one pydantic model per `spider.toml` table, for example `register_settings_table("store", StoreSettings)` in `015`. The root settings model is assembled from the registry when settings load.
  - Code reads a table through a typed getter, `settings.table(StoreSettings)`, so static typing is kept.
  - Tests assemble a registry that includes the `example` table used by the scenarios (D8).
- **Sources**, set by `settings_customise_sources`:
  1. init kwargs, which carry flag values
  2. a TOML source that reads the Workspace's settings file with `tomllib`
  3. defaults

  The environment, `.env` and secrets-dir sources are dropped.
- **Validation:**
  - `extra="forbid"` on every model.
  - The whole file is validated at load, including tables such as `050`'s `[segments]`, which report through the same `settings_invalid`.
- **Error mapping:**
  - pydantic `loc` tuples become dotted keys.
  - `difflib.get_close_matches` supplies the hint.
  - `tomllib.TOMLDecodeError` supplies `line`.
- **The commented template** is generated from the registered models:
  - a header comment that states the precedence
  - then, for each table: the uncommented table header, the field's description as a comment, and `# key = <default as a TOML literal>`
- **Alternatives:**
  - **A static root model to which each change adds a field.** Simpler, but tests could not add the example table without editing production code.
  - **Hand-written validation.** More code for the same errors.

### D3. Output layer (`spider.output`)

- **One `Output` object per invocation.** It holds the format, the optional `-o` target, and byte sinks: `sys.stdout.buffer` and `sys.stderr.buffer`. Nothing is written through the text layer. With PEP 528, the Windows console's raw layer accepts UTF-8 bytes, so the console display is correct too.
- **Output kinds**, declared per Command in `@command_meta`:

  | Kind | Result |
  |---|---|
  | `document` | one object |
  | `list` | the paging envelope, or items as rows with `jsonl`, `csv` and `table` |
  | `rows` | a data stream, `jsonl` by default |

  `events=True` marks a Command that reports progress.
- **Rendering by format:**
  - **JSON and JSON Lines:** `orjson.dumps` (compact, UTF-8) plus `\n`.
  - **CSV:** see D4.
  - **Table:** rich `Console(file=StringIO(), color_system=None, width=…)` rendered to text. The width is the terminal width on a TTY, otherwise 120.
- **When bytes are written:**
  - Documents and lists are rendered fully and written only when the Command ends. That gives "nothing on stdout when a Command fails".
  - Rows are written and flushed row by row.
  - **Partial results (G2):** a Command returns `Outcome(result, error)`. The runner writes the result, then the error line, then exits with the error's exit code.
- **Progress events (G1):** `Output.event(name, data)` writes `{"event","ts","data"}` to stderr and flushes. The time comes from the injected `Clock`, formatted `YYYY-MM-DDTHH:MM:SS.sssZ`. stdout never carries events.
- **`-o`:**
  - The output is written to a temporary file in the target folder, then moved into place with `os.replace`.
  - On Windows, a `PermissionError` is retried for up to 1 s, because indexers and antivirus scanners briefly lock new files. After that it becomes `output_not_writable`.
  - On success the runner writes the info line `output_written`.
- **Lint guard:** ruff `banned-api` forbids `sys.stdout`, `sys.stderr`, `print`, `typer.echo` and `click.echo` outside `spider.output`.
- **Alternatives:**
  - **`sys.stdout.reconfigure(encoding="utf-8")`.** It leaves `\r\n` translation and third-party writes as risks.
  - **Relying on `PYTHONUTF8`.** Not under our control.
  - **A result event at the end of stdout.** Dropped by G1: stdout carries only the result.

### D4. The CSV policy

- **How rows are written:** `csv.writer` over `io.StringIO(newline="")` with `lineterminator="\r\n"`. The text is encoded as UTF-8, and `﻿` goes first unless `--no-bom` is given.
  - The byte-order mark makes Excel read UTF-8 correctly, which matters to the people who read exports and Report CSV files.
  - CSV parsers used by agents skip the mark or accept `--no-bom`.
- **Cell rules:**
  - Nested values become compact JSON, and null becomes an empty cell.
  - Numbers are written unchanged, so negative numbers stay numbers.
  - Text that starts with `=`, `+`, `-`, `@`, `\t` or `\r` gets a leading `'`. This is the OWASP guidance on CSV injection, and crawled text is untrusted.
- **One implementation for everyone:** `050`'s `export` and `070`'s Report CSV files call the same writer, and neither redefines the policy (G5).
- **Alternative:** no byte-order mark by default. Rejected by G5, because Excel users open these files directly.

### D5. Errors, the diagnostic registry and exit codes

- **Errors:** `SpiderError(code, message, hint=None, details={})` subclasses, each bound to an `ExitCode` enum member. Warnings and info lines use the same `Diagnostic` type.
- **Diagnostics inside results:** a result that carries diagnostics, such as `crawl.warnings` or a list of per-target errors, holds `Diagnostic.to_json()` objects with the full shape (G6).
- **The registry:** each module declares its codes, with level, exit code and description. `spider commands` prints the registry. A test enforces the naming rule: `invalid_*`, `unknown_*` and `usage_error` map to 2, and `*_not_found` and `no_crawls` map to 4.
- **Running the app:** the Typer app runs with `standalone_mode=False`.

  | What is raised | Diagnostic |
  |---|---|
  | Click `UsageError` | `usage_error` |
  | Click `BadParameter` | `invalid_value` |
  | a known global flag found before the Command name (checked on `argv` before Click parses) | `usage_error`, with the hint |
  | any other `Exception` | `internal_error` (70), with `traceback.format_exc()` |

- **Why these exit codes:** 1 means "failed" (`080` uses it for failed checks), and 70 (`EX_SOFTWARE`) marks a bug, so agents can tell a failed operation from a defect. Exit code 130 is reserved, and `020` maps Ctrl+C to it.
- **Alternatives:**
  - **Click's plain-text errors.** Not parseable.
  - **Exit code 1 for everything.** Agents could not branch on the kind of failure.
  - **UPPER_CASE codes.** Rejected: lowercase matches the enumeration values stored in the crawl store.

### D6. Paging and cursors

- **Cursor format:** `base64url(orjson({"v":1,"q":fingerprint,"k":keyset}))`, without padding.
  - The fingerprint is the first 16 hex characters of the SHA-256 of the canonical JSON of the Command path plus the arguments that select or order items.
  - `--limit`, `--fields` and `--format` are excluded from the fingerprint.
- **This change provides:**
  - the codec and its validation, which raises `invalid_cursor`
  - field selection, which raises `unknown_field`
  - an in-memory pager for static lists
- **What later changes do:**
  - `015`'s `spider schema` uses the pager.
  - `050` builds its SQL keyset paging on the same codec, and adds the crawl id and its filters to the fingerprint.
- **Alternatives:**
  - **Offset cursors.** Items would be skipped or repeated while a Crawl is running.
  - **Signed cursors.** There is no security need for a local tool.

### D7. `spider commands` and the global flags

- **Walking the Commands:** `spider commands` walks the Click tree of the app and skips hidden Commands.
- **Metadata:**
  - Each Command registers its `output` kind, `events`, formats, fields and examples with `@command_meta(...)`.
  - Options carry `global`, `setting` and `secret` in their Typer `metadata`.
- **Defaults** are printed as JSON values. Defaults that depend on the OS are symbolic (for example `null` plus a description that says `~/.spider`), so the output is identical everywhere.
- **Global flags** are defined once, as reusable annotated option types that each Command adds after its name:
  - this change builds `WorkspaceOpt`, `FormatOpt`, `NoBomOpt` and `OutputOpt`
  - `015` adds `CrawlOpt`
- **Alternative:** root-level Click options. They must come *before* the Command, while agents and examples write them after. Accepting both positions is a possible later relaxation (Open Questions).

### D8. Contract fixtures: example Commands and an example setting

- **The problem:** the contract covers lists, rows, progress events, partial results and unexpected failures, but none of this change's Commands has any of them.
- **The app factory:** `spider.cli.app.build_app(extra=…)` builds the real Typer app, and optionally registers more Commands and settings tables. The installed entry point calls `build_app()` without extras.
- **What tests add:** the tests build a fresh app with contract fixture Commands and the `example` settings table, and run it at the CLI seam through `run_cli(..., app=…)`:
  - the example list Command (items `n`/`sq`, with `--odd`)
  - a 60-item list
  - lists with the CSV edge values
  - a rows Command
  - a progress-reporting Command
  - a partial-result Command
  - a Command that raises `RuntimeError`
  - a Command whose result holds a warning
- **Why this is not a test double:** the fixture Commands use the same public registration API as real Commands, and they replace none of our code. They are consumers of the contract, the way a test route exercises a web framework.
- **Alternatives:**
  - **Make `spider commands` a list Command.** It would bloat the self-description with paging, and leave events and partial results untested all the same.
  - **Leave these scenarios to later changes.** The contract would ship untested in the change that owns it.

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
    - on Windows, a locked `-o` target held by a helper process that opens the file without sharing
- **Services and store API (2):** the Workspace API: `resolve_workspace`, resolving settings with flag overrides, and the environment-variable scenarios.
- **Pure-logic modules (4):** the event-line encoder with `FakeClock`.

Test doubles:
- **The clock (`FakeClock`)** is the only one. It is in the list of allowed boundary doubles.
- **Unwritable folders** are real: a path under a regular file (`notes.txt/site`) fails on every OS without any fake.
- **The contract fixtures of D8** are registered consumers, not doubles.

No new seam is introduced.

## Risks / Trade-offs

- **Fixture Commands could drift from how real Commands use the contract.**
  - They use the same `@command_meta` and `Output` API.
  - `015`'s `spider schema` and every later Command re-check the contract with real data.
- **The byte-order mark surprises Unix tools such as `cut` and `awk`.**
  - `--no-bom` turns it off.
  - `docs/cli.md` shows it next to every CSV example.
- **Neutralisation changes text that starts with `-`,** such as `-webkit-` values, by adding `'`.
  - Accepted as the safe default for untrusted text. JSON and JSON Lines keep the raw value.
- **Some network filesystems and indexers hold new files.**
  - `-o` retries its rename for up to 1 s before reporting `output_not_writable`.
- **The discovery search stops at the home folder, so a Workspace above home is never found.**
  - Accepted. `--workspace` covers that case.

## Migration Plan

Nothing to migrate: this change is greenfield.

## Interface points for later changes

- **Commands:**
  - Register `@command_meta` with the output kind, `events`, formats, fields and examples, and use the global flag types.
  - Raise `SpiderError` subclasses with lowercase codes that follow the naming rule, and register every code.
  - Put diagnostics inside results with `Diagnostic.to_json()`.
- **Streams and outcomes:**
  - Progress goes through `Output.event`.
  - A failed outcome is returned as `Outcome(result, error)`. `020`'s `seed_unreachable` (exit 8) and Ctrl+C (exit 130, which `020` maps) use it, and so do `080`'s failed checks (exit 1).
- **Settings:**
  - Register a table with `register_settings_table`.
  - A setting that mirrors a flag lives in `[<command>]` under the flag's name, with `_` for `-`. Mark it `secret` (`015` redacts it).
  - The first change that adds a path-valued setting also specifies that relative paths are taken from `spider.toml`'s folder.
- **Paging:** list Commands use the codec from D6. SQL-backed lists (`050`) add the crawl id and their filters to the fingerprint, and use `unknown_field` for `--fields` and `unknown_column` for `--where` and `--sort`.
- **CSV:** every CSV writer goes through D4. That includes `050`'s export and `070`'s Report files.

## Open Questions

- Should there be a `spider workspace` Command that shows the resolved Workspace and the effective settings? It would help agents debug, but it is a new Command, so it is left for the maintainer to decide.
- Should global flags also be accepted before the Command name? That would be an additive relaxation of D7.
