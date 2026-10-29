## RENAMED Requirements

- FROM: `### Requirement: Self-description with spider commands`
- TO: `### Requirement: Self-description with linx commands`

## MODIFIED Requirements

### Requirement: JSON output by default

**In short:** by default a Command prints its result as one compact JSON document, and a failing Command prints nothing unless its result describes the failure.

Without `--format`, a Command SHALL write its result to stdout as one compact JSON document, with no whitespace between tokens, followed by `\n`.
- Non-ASCII characters SHALL be written as UTF-8 characters, not as `\u` escapes.
- JSON output SHALL contain no ANSI escape sequences.
- A Command that fails SHALL write nothing to stdout, unless its result describes the failed outcome (see "Partial results").

#### Scenario: Compact document
- **WHEN** the example list Command runs with `--limit 5`
- **THEN** stdout is exactly `{"total":5,"items":[{"n":1},{"n":2},{"n":3},{"n":4},{"n":5}],"next_cursor":null}` followed by `\n`

#### Scenario: Non-ASCII characters are not escaped
- **WHEN** `linx init --workspace H/work/Проверка` runs
- **THEN** stdout contains the UTF-8 bytes of `Проверка`, not `\u` escapes

#### Scenario: Nothing on stdout when a Command fails
- **WHEN** `linx nosuchcommand` runs
- **THEN** stdout is empty

### Requirement: Output formats

**In short:** `--format` chooses `json`, `jsonl` or `table` among the formats a Command supports, and errors stay JSON whatever the format.

`--format` SHALL accept `json`, `jsonl` and `table`. Each Command SHALL support the formats that `linx commands` lists for it:
- document Commands: `json` (the default) and `table`
- list Commands: `json` (the default), `jsonl` and `table`
- rows Commands: `jsonl` (the default)

`table` is for people, and its layout is not a contract.

A format that is unknown, or that the Command does not support, SHALL fail with `invalid_value`, and the hint SHALL list the Command's formats. Errors SHALL stay JSON, whatever `--format` says.

With `jsonl` or `table`, when more items exist than were printed, the Command SHALL write the info line `more_items` to stderr, with `details.total` and `details.next_cursor`.

#### Scenario: Unsupported format
- **WHEN** `linx commands --format jsonl` runs
- **THEN** the exit code is 2, and the error has the code `invalid_value` and a hint that contains `json` and `table`

#### Scenario: Unknown format
- **WHEN** `linx init --format xml` runs
- **THEN** the exit code is 2, and the error has the code `invalid_value`

#### Scenario: Table for people
- **WHEN** `linx init --format table` runs in the empty folder `H/work/shop`
- **THEN** stdout contains the text `data_dir`

#### Scenario: Errors stay JSON
- **WHEN** `linx init --format table --workspace H/work/notes.txt/site` runs, and `H/work/notes.txt` is a file
- **THEN** the last line of stderr parses as a JSON object with `"code":"workspace_not_writable"`

#### Scenario: More items notice
- **WHEN** the example list Command runs with `--format jsonl --limit 2`
- **THEN** stderr has a line with `"level":"info"` and `"code":"more_items"`, whose `details.total` is `5` and whose `details.next_cursor` is a non-empty string

### Requirement: JSON Lines

**In short:** `--format jsonl` prints one JSON object per item or row, and is the default for rows Commands.

`--format jsonl` SHALL write one compact JSON object per line, each followed by `\n`: one line per item of a list Command, or one line per row of a rows Command. A rows Command SHALL use `jsonl` by default. Document Commands SHALL NOT support `jsonl`.

#### Scenario: Items as lines
- **WHEN** the example list Command runs with `--format jsonl --limit 2`
- **THEN** stdout is exactly `{"n":1}\n{"n":2}\n`

#### Scenario: Rows by default
- **WHEN** a rows Command that returns the rows `{"n":1}` and `{"n":2}` runs without `--format`
- **THEN** stdout is exactly `{"n":1}\n{"n":2}\n`

#### Scenario: Documents have no JSON Lines
- **WHEN** `linx init --format jsonl` runs
- **THEN** the exit code is 2, and the error has the code `invalid_value`

### Requirement: UTF-8 output on every OS

**In short:** output is UTF-8 with `\n` line endings on every OS, whatever the console or locale.

stdout and stderr SHALL carry UTF-8 bytes on every OS, whatever the console code page, the locale or `PYTHONIOENCODING`. JSON documents, JSON Lines and stderr lines SHALL end with `\n` alone, on Windows too.

#### Scenario: Piped output on Windows
- **WHEN** on Windows `linx init --workspace H\work\Проверка` runs as a real process with stdout piped
- **THEN** stdout contains the bytes `D0 9F D1 80 D0 BE D0 B2 D0 B5 D1 80 D0 BA D0 B0`, the UTF-8 encoding of `Проверка`

#### Scenario: PYTHONIOENCODING does not change the output
- **WHEN** `linx init --workspace H/work/Проверка` runs as a real process with the environment variable `PYTHONIOENCODING=cp1252`
- **THEN** stdout contains the bytes `D0 9F D1 80 D0 BE D0 B2 D0 B5 D1 80 D0 BA D0 B0`

#### Scenario: No carriage returns on Windows
- **WHEN** on Windows `linx commands` runs as a real process
- **THEN** stdout ends with `}` followed by `\n`, and contains no `\r` byte

#### Scenario: UTF-8 on stderr
- **WHEN** `linx init --workspace H/work/Проверка.txt/site` runs as a real process, and `H/work/Проверка.txt` is a file
- **THEN** stderr contains the bytes `D0 9F D1 80 D0 BE D0 B2 D0 B5 D1 80 D0 BA D0 B0`

### Requirement: Choosing fields with --fields

**In short:** `--fields` chooses which keys each item has, and in what order.

`--fields` SHALL take a comma-separated list of field names. Each item then has exactly those keys, in that order. `--fields all` SHALL select every available field, in the Command's field order. Without `--fields`, the Command's default fields apply, as listed by `linx commands`.

An unknown field name SHALL fail with `unknown_field`, with `details.field` and `details.available`.

Spaces around a name SHALL be ignored, and a name given twice SHALL count once, at its first place. An empty name SHALL fail with `invalid_value`.

#### Scenario: Default fields
- **WHEN** the example list Command runs with `--limit 1`
- **THEN** `items` is `[{"n":1}]`

#### Scenario: Fields in the requested order
- **WHEN** the example list Command runs with `--fields sq,n --limit 1`
- **THEN** `items` is `[{"sq":1,"n":1}]`

#### Scenario: All fields
- **WHEN** the example list Command runs with `--fields all --limit 1`
- **THEN** `items` is `[{"n":1,"sq":1}]`

#### Scenario: Spaces and repeats in --fields
- **WHEN** the example list Command runs with `--fields " sq , n,sq" --limit 1`
- **THEN** `items` is `[{"sq":1,"n":1}]`

#### Scenario: Empty field name
- **WHEN** the example list Command runs with `--fields n,,sq`
- **THEN** the exit code is 2, and the error has the code `invalid_value`

#### Scenario: Unknown field
- **WHEN** the example list Command runs with `--fields n,size`
- **THEN** the exit code is 2, and the error has the code `unknown_field` and `"details":{"field":"size","available":["n","sq"]}`

### Requirement: Diagnostics on stderr

**In short:** errors, warnings and notices go to stderr as JSON lines of one fixed shape, and a failing Command ends with exactly one error.

Errors, warnings and notices SHALL be written to stderr, one compact JSON object per line. Each line, diagnostic or progress event, SHALL be written whole and flushed as it happens, and stderr lines SHALL appear in the order they were reported. Each object SHALL have exactly these keys:
- `level`: `error`, `warning` or `info`
- `code`: lowercase snake_case
- `message`
- `hint`: a string, or `null`
- `details`: an object, possibly empty

A failing Command SHALL write exactly one error object, as its last line on stderr. An error or warning reported inside a result, such as an entry in a `warnings` list, SHALL use the same shape.

Errors found while parsing the command line SHALL use the same shape: `usage_error` for an unknown Command, an unknown flag or a missing argument, and `invalid_value` for a value that is not allowed. An unexpected failure SHALL use `internal_error`, with the Python traceback text in `details.traceback`. A Command stopped with Ctrl+C SHALL use `interrupted`, never `internal_error`.

Nothing else SHALL appear on stderr apart from progress events: no raw tracebacks, progress bars or log lines.

#### Scenario: Unknown Command
- **WHEN** `linx nosuchcommand` runs
- **THEN** the exit code is 2, and the error has the code `usage_error`

#### Scenario: Error object
- **WHEN** `linx nosuchcommand` runs
- **THEN** the last line of stderr is a JSON object whose keys are exactly `level`, `code`, `message`, `hint` and `details`, with `"level":"error"`

#### Scenario: Only JSON lines on stderr
- **WHEN** `linx init --workspace H/work/notes.txt/site` runs, and `H/work/notes.txt` is a file
- **THEN** every line of stderr parses as a JSON object

#### Scenario: Unexpected failure
- **WHEN** a Command raises `RuntimeError("disk exploded")`
- **THEN** the exit code is 70, and the error has the code `internal_error` and a `details.traceback` that contains `RuntimeError: disk exploded`

#### Scenario: A warning is readable at once
- **WHEN** a Command running as a real process with stderr piped writes a warning, and then waits for a line on its stdin before it ends
- **THEN** the warning line can be read from stderr before that line is sent

#### Scenario: Interrupted
- **WHEN** a Command is stopped with Ctrl+C
- **THEN** the exit code is 130, and the last line of stderr is an error with the code `interrupted`

#### Scenario: A warning inside a result
- **WHEN** a Command ends with a result whose `warnings` list holds one warning
- **THEN** that entry's keys are exactly `level`, `code`, `message`, `hint` and `details`

### Requirement: Exit codes

**In short:** every Command exits with one of a fixed set of documented codes, and every error code maps to exactly one of them.

Every Command SHALL exit with one of these codes. The meaning of a code SHALL never change, and codes 9 to 63 are reserved:

| Code | Name | Meaning |
|---|---|---|
| 0 | `ok` | success |
| 1 | `failed` | the Command ran but could not do everything asked; the error says what |
| 2 | `usage` | the command line is wrong: an unknown Command, flag or name, or a missing or invalid value |
| 3 | `config` | `openlinx.toml` or a setting is invalid |
| 4 | `not_found` | a Workspace, Crawl or item named on the command line does not exist |
| 5 | `busy` | another process holds the Crawl |
| 6 | `incompatible` | the crawl file cannot be used by this version |
| 7 | `io` | reading or writing a file or folder failed |
| 8 | `network` | the network or a required host cannot be reached |
| 70 | `internal` | an unexpected failure, which is a bug in the tool |
| 130 | `interrupted` | stopped with Ctrl+C |

Every diagnostic code that is an error SHALL map to exactly one exit code:
- `usage_error` and every code starting with `invalid_` or `unknown_` map to 2
- every code ending with `_not_found`, and `no_crawls`, map to 4

Warnings and info lines SHALL NOT change the exit code.

Every diagnostic code SHALL be declared once, with its level, its exit code (none for warnings and info) and a description. `linx commands` SHALL list exactly the declared codes, and no Command SHALL report a code that is not declared.

#### Scenario: The table is self-described
- **WHEN** `linx commands` runs
- **THEN** the `code` and `name` pairs of `exit_codes` are, in order, `0 ok`, `1 failed`, `2 usage`, `3 config`, `4 not_found`, `5 busy`, `6 incompatible`, `7 io`, `8 network`, `70 internal`, `130 interrupted`

#### Scenario: Error codes of this change
- **WHEN** `linx commands` runs
- **THEN** its `diagnostics` give these exit codes: `usage_error` 2, `invalid_value` 2, `unknown_field` 2, `invalid_cursor` 2, `settings_invalid` 3, `workspace_not_found` 4, `workspace_not_writable` 7, `internal_error` 70 and `interrupted` 130

#### Scenario: Warning and info codes of this change
- **WHEN** `linx commands` runs
- **THEN** its `diagnostics` include `workspace_nested` with `"level":"warning"` and `more_items` with `"level":"info"`, both with `"exit_code":null`

#### Scenario: Naming rule for input errors
- **WHEN** `linx commands` runs
- **THEN** every diagnostic whose code starts with `invalid_` or `unknown_` has `"exit_code":2`

#### Scenario: A warning keeps exit code 0
- **WHEN** `linx init` runs in `H/work/shop/blog`, and `H/work/shop` contains `.openlinx/`
- **THEN** the exit code is 0

### Requirement: Global flags

**In short:** `--workspace`, `--crawl` and `--format` mean the same on every Command that takes them, and go after the Command name.

`--workspace <dir>`, `--crawl <ref>` and `--format <format>` SHALL mean the same on every Command that accepts them. They SHALL be given after the Command name.
- A Command SHALL reject a global flag it does not use with `usage_error`.
- A global flag given before the Command name SHALL fail with `usage_error`, whose hint says to put it after the Command name.

`--crawl` is defined by `015-add-crawl-store`.

#### Scenario: After the Command name
- **WHEN** `linx init --format json` runs in the empty folder `H/work/shop`
- **THEN** the exit code is 0

#### Scenario: A flag the Command does not use
- **WHEN** `linx commands --workspace H/work` runs
- **THEN** the exit code is 2, and the error has the code `usage_error`

#### Scenario: Before the Command name
- **WHEN** `linx --format table init` runs
- **THEN** the exit code is 2, and the error has the code `usage_error` and a hint that contains `after the Command name`

#### Scenario: Global flags of init
- **WHEN** `linx commands` runs
- **THEN** the options of the `init` entry include `--workspace` and `--format`, each with `"global":true`

### Requirement: Self-description with linx commands

**In short:** `linx commands` describes every Command, exit code, diagnostic and honoured environment variable in one JSON document, the same on every OS.

`linx commands` SHALL return one JSON document with these keys:

| Key | Content |
|---|---|
| `tool` | `name` and `version` |
| `commands` | every Command that `--help` shows, including `commands` itself, sorted by name |
| `exit_codes` | `code`, `name` and `description` of each exit code |
| `diagnostics` | every diagnostic code, with `level`, `exit_code` (null for warnings and info) and `description` |
| `environment` | the environment variables the tool honours, as entries with `names` (matched in any letter case) and `description`; only the proxy family, as the workspace capability says |

A Command's name is its full path, for example `crawls list`. Each Command entry SHALL have:
- `name`, `summary` and `description`
- `output`: `document`, `list` or `rows`
- `events`: `true` when the Command reports progress events
- `formats`
- `arguments`: each with `name`, `type`, `required`, `variadic`, `default` and `description`
- `options`: each with `name`, `short`, `type`, `choices`, `default`, `required`, `multiple`, `global`, `setting` (its `openlinx.toml` key, or null), `secret` and `description`
- `fields`: `{available, default}` for list and rows Commands, otherwise null
- `examples`

The output SHALL be identical on every OS for the same version, and SHALL NOT need a Workspace.

The description SHALL be consistent, and the tool SHALL refuse to start with a Command that would break this:
- the default of a Command's `--format` is the first of its `formats`
- the default fields of a Command are all among its available fields

An option whose `setting` is not null SHALL take `secret` from that setting, so a secret setting and its flag are never described differently. An option without a setting SHALL declare `secret` itself.

#### Scenario: Default format comes first
- **WHEN** the tool is built with a document Command whose formats are `json` and `table`, and whose `--format` defaults to `table`
- **THEN** building the tool fails, naming that Command

#### Scenario: Default fields are available
- **WHEN** the tool is built with a list Command whose available fields are `n` and `sq`, and whose default fields are `n` and `size`
- **THEN** building the tool fails, naming that Command

#### Scenario: A secret option inherits from its setting
- **WHEN** `linx commands` runs in a tool that includes the example settings Command, whose `--level` maps to `example.level` and whose `--token` maps to the secret setting `example.token`
- **THEN** its `--token` option has `"setting":"example.token"` and `"secret":true`, and its `--level` option has `"setting":"example.level"` and `"secret":false`

#### Scenario: A secret option without a setting
- **WHEN** `linx commands` runs in a tool that includes the example settings Command, whose `--api-key` maps to no setting and is declared secret
- **THEN** its `--api-key` option has `"setting":null` and `"secret":true`

#### Scenario: The Command lists itself
- **WHEN** `linx commands` runs
- **THEN** `commands` has an entry with `"name":"commands"`

#### Scenario: Entry of a document Command
- **WHEN** `linx commands` runs
- **THEN** the `init` entry has `"output":"document"`, `"events":false`, `"formats":["json","table"]` and `"fields":null`

#### Scenario: Entry of a list Command
- **WHEN** `linx commands` runs in a tool that includes the example list Command
- **THEN** its entry has `"output":"list"`, `"formats":["json","jsonl","table"]` and `"fields":{"available":["n","sq"],"default":["n"]}`

#### Scenario: Option details
- **WHEN** `linx commands` runs
- **THEN** the `--workspace` option of the `init` entry has `"type":"path"`, `"default":null`, `"global":true`, `"setting":null` and `"secret":false`

#### Scenario: Tool version
- **WHEN** `linx commands` runs
- **THEN** `tool` is `{"name":"spider","version":V}`, where V is the `version` in `pyproject.toml`

#### Scenario: Same description on every OS
- **WHEN** `linx commands` runs on Windows, macOS and Linux
- **THEN** the entry for `init` is byte-identical on all three

### Requirement: Light start

**In short:** `linx --help` and `linx commands` load only a small, fixed set of modules, and a settings table loads only with the settings.

`linx --help` and `linx commands` SHALL start without loading any module outside the standard library, Typer and the modules Typer itself depends on, orjson and `linx`. `linx commands` MAY also load pydantic when an option maps to a setting. A settings table SHALL be loaded only when settings load, or when the settings template is written.

#### Scenario: Help starts light
- **WHEN** `linx --help` runs in a fresh process
- **THEN** every top-level module loaded is in the standard library, Typer or its dependencies, orjson or `linx`

#### Scenario: The self-description starts light
- **WHEN** `linx commands` runs in a fresh process
- **THEN** every top-level module loaded is in the standard library, Typer or its dependencies, orjson or `linx`

#### Scenario: Settings tables load with the settings
- **WHEN** `linx --help` runs in a fresh process, in a tool whose `example` table is registered
- **THEN** the module that defines the `example` table is not loaded

### Requirement: Help and version are plain text

**In short:** `--help` and `--version` print plain text and exit 0, and are the only outputs that are not JSON.

`--help`, on the tool or on any Command, SHALL print plain-text help to stdout and exit 0. `linx` with no arguments SHALL do the same as `linx --help`. `linx --version` SHALL print `OpenLinx <version>` followed by `\n`, and exit 0. These SHALL be the only outputs that are not JSON.

#### Scenario: Help
- **WHEN** `linx init --help` runs
- **THEN** the exit code is 0, and stdout contains `Usage:`

#### Scenario: No arguments
- **WHEN** `linx` runs with no arguments
- **THEN** the exit code is 0, stdout is the same as for `linx --help`, and stderr is empty

#### Scenario: Version
- **WHEN** `linx --version` runs
- **THEN** stdout is exactly `OpenLinx `, then the `version` in `pyproject.toml`, then `\n`


## ADDED Requirements

### Requirement: Two console scripts

**In short:** the package installs `linx` and `openlinx`, which run the same entry point, and the usage line and the recorded command line name the one that ran.

The distribution SHALL install two console scripts with the same entry point: `linx`, the name the docs use, and `openlinx`, for a machine where another package's `linx` comes first on PATH.
- The usage line of `--help` SHALL name the script that ran, and `linx` when the tool runs some other way, such as `python -m openlinx`.
- `crawl.command_argv` SHALL start with that same name (`crawl-store`).
- Hints that name a command SHALL name `linx`.

#### Scenario: Both console scripts run the same entry point
- **WHEN** the console scripts of the installed distribution are read
- **THEN** `linx` and `openlinx` both name `openlinx.cli.app:main`

#### Scenario: Usage names the script that ran
- **WHEN** `openlinx --help` runs through its console script, and then `python -m openlinx --help` runs
- **THEN** the first stdout starts with `Usage: openlinx `, and the second with `Usage: linx `

#### Scenario: The recorded command line starts with the script that ran
- **WHEN** `openlinx crawl <url>` runs through its console script, for a URL of the local fixture site
- **THEN** the Crawl's `crawl.command_argv` starts with `"openlinx"`, `"crawl"`
