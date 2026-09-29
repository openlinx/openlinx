## Purpose

Defines how every Command talks to agents and people:
- output formats and encoding, the single CSV policy, and writing output to a file
- paging of lists
- progress events and diagnostics on stderr, and partial results
- exit codes, the global flags, and the `spider commands` self-description

Conventions used in the scenarios:
- `H` is the absolute path of the home folder.
- Paths are written with `/`, and Windows uses `\`.
- Behaviour that no Command of this change has yet is shown with example Commands. The **example list Command** lists the items `{"n":1,"sq":1}`, `{"n":2,"sq":4}`, `{"n":3,"sq":9}`, `{"n":4,"sq":16}` and `{"n":5,"sq":25}`. Its available fields are `n` and `sq`, its default field is `n`, and `--odd` keeps only the items with an odd `n`. Other example Commands are described where they are used.

## ADDED Requirements

### Requirement: JSON output by default

Without `--format`, a Command SHALL write its result to stdout as one compact JSON document, with no whitespace between tokens, followed by `\n`.
- Non-ASCII characters SHALL be written as UTF-8 characters, not as `\u` escapes.
- JSON output SHALL contain no ANSI escape sequences.
- A Command that fails SHALL write nothing to stdout, unless its result describes the failed outcome (see "Partial results").

#### Scenario: Compact document
- **WHEN** the example list Command runs with `--limit 5`
- **THEN** stdout is exactly `{"total":5,"items":[{"n":1},{"n":2},{"n":3},{"n":4},{"n":5}],"next_cursor":null}` followed by `\n`

#### Scenario: Non-ASCII characters are not escaped
- **WHEN** `spider init --workspace H/work/Проверка` runs
- **THEN** stdout contains the UTF-8 bytes of `Проверка`, not `\u` escapes

#### Scenario: Nothing on stdout when a Command fails
- **WHEN** `spider nosuchcommand` runs
- **THEN** stdout is empty

### Requirement: Output formats

`--format` SHALL accept `json`, `jsonl`, `table` and `csv`. Each Command SHALL support the formats that `spider commands` lists for it:
- document Commands: `json` (the default), `table` and `csv`
- list Commands: `json` (the default), `jsonl`, `table` and `csv`
- rows Commands: `jsonl` (the default) and `csv`

`table` is for people, and its layout is not a contract.

A format that is unknown, or that the Command does not support, SHALL fail with `invalid_value`, and the hint SHALL list the Command's formats. Errors SHALL stay JSON, whatever `--format` says.

With `jsonl`, `table` or `csv`, when more items exist than were printed, the Command SHALL write the info line `more_items` to stderr, with `details.total` and `details.next_cursor`.

#### Scenario: Unsupported format
- **WHEN** `spider commands --format csv` runs
- **THEN** the exit code is 2, and the error has the code `invalid_value` and a hint that contains `json` and `table`

#### Scenario: Unknown format
- **WHEN** `spider init --format xml` runs
- **THEN** the exit code is 2, and the error has the code `invalid_value`

#### Scenario: Table for people
- **WHEN** `spider init --format table` runs in the empty folder `H/work/shop`
- **THEN** stdout contains the text `data_dir`

#### Scenario: Errors stay JSON
- **WHEN** `spider init --format table --workspace H/work/notes.txt/site` runs, and `H/work/notes.txt` is a file
- **THEN** the last line of stderr parses as a JSON object with `"code":"workspace_not_writable"`

#### Scenario: More items notice
- **WHEN** the example list Command runs with `--format csv --limit 2`
- **THEN** stderr has a line with `"level":"info"` and `"code":"more_items"`, whose `details.total` is `5` and whose `details.next_cursor` is a non-empty string

### Requirement: JSON Lines

`--format jsonl` SHALL write one compact JSON object per line, each followed by `\n`: one line per item of a list Command, or one line per row of a rows Command. A rows Command SHALL use `jsonl` by default. Document Commands SHALL NOT support `jsonl`.

#### Scenario: Items as lines
- **WHEN** the example list Command runs with `--format jsonl --limit 2`
- **THEN** stdout is exactly `{"n":1}\n{"n":2}\n`

#### Scenario: Rows by default
- **WHEN** a rows Command that returns the rows `{"n":1}` and `{"n":2}` runs without `--format`
- **THEN** stdout is exactly `{"n":1}\n{"n":2}\n`

#### Scenario: Documents have no JSON Lines
- **WHEN** `spider init --format jsonl` runs
- **THEN** the exit code is 2, and the error has the code `invalid_value`

### Requirement: CSV policy

Every CSV output SHALL follow one policy:
- **Encoding:** UTF-8, starting with a byte-order mark. `--no-bom` leaves the byte-order mark out.
- **Layout:** RFC 4180, with a header row of field names. There is one row per item or row, or one row for a document, and `\r\n` after every row.
- **Values:**
  - Nested values are written as compact JSON.
  - Null is written as an empty cell.
  - Numbers are written unchanged.
- **Formula neutralisation:** a text value that starts with `=`, `+`, `-`, `@`, a tab or a carriage return SHALL be written with a leading `'`.

`--no-bom` given without `--format csv` SHALL fail with `invalid_value`.

#### Scenario: Byte-order mark and CRLF
- **WHEN** the example list Command runs with `--format csv`
- **THEN** stdout is exactly the bytes `EF BB BF` followed by `n\r\n1\r\n2\r\n3\r\n4\r\n5\r\n`

#### Scenario: Without the byte-order mark
- **WHEN** the example list Command runs with `--format csv --no-bom`
- **THEN** stdout is exactly `n\r\n1\r\n2\r\n3\r\n4\r\n5\r\n`

#### Scenario: Formula-like text is neutralised
- **WHEN** a list Command whose items are `{"v":"=1+1"}`, `{"v":"+1"}`, `{"v":"-1"}`, `{"v":"@a"}` and `{"v":"plain"}` runs with `--format csv --no-bom`
- **THEN** stdout is exactly `v\r\n'=1+1\r\n'+1\r\n'-1\r\n'@a\r\nplain\r\n`

#### Scenario: Numbers are unchanged
- **WHEN** a list Command whose only item is `{"v":-5}` runs with `--format csv --no-bom`
- **THEN** stdout is exactly `v\r\n-5\r\n`

#### Scenario: Nested value and null
- **WHEN** a list Command whose only item is `{"a":[1,2],"b":null}` runs with `--format csv --no-bom`
- **THEN** stdout is exactly `a,b\r\n"[1,2]",\r\n`

#### Scenario: A document is one CSV row
- **WHEN** `spider init --format csv --no-bom` runs in the empty folder `H/work/shop`
- **THEN** stdout has exactly two rows, and the first is `workspace,data_dir,settings_file,global,created`

#### Scenario: The byte-order mark flag needs CSV
- **WHEN** `spider init --no-bom` runs
- **THEN** the exit code is 2, and the error has the code `invalid_value`

### Requirement: UTF-8 output on every OS

stdout and stderr SHALL carry UTF-8 bytes on every OS, whatever the console code page, the locale or `PYTHONIOENCODING`. JSON documents, JSON Lines and stderr lines SHALL end with `\n` alone, on Windows too.

#### Scenario: Piped output on Windows
- **WHEN** on Windows `spider init --workspace H\work\Проверка` runs as a real process with stdout piped
- **THEN** stdout contains the bytes `D0 9F D1 80 D0 BE D0 B2 D0 B5 D1 80 D0 BA D0 B0`, the UTF-8 encoding of `Проверка`

#### Scenario: PYTHONIOENCODING does not change the output
- **WHEN** `spider init --workspace H/work/Проверка` runs as a real process with the environment variable `PYTHONIOENCODING=cp1252`
- **THEN** stdout contains the bytes `D0 9F D1 80 D0 BE D0 B2 D0 B5 D1 80 D0 BA D0 B0`

#### Scenario: No carriage returns on Windows
- **WHEN** on Windows `spider commands` runs as a real process
- **THEN** stdout ends with `}` followed by `\n`, and contains no `\r` byte

#### Scenario: UTF-8 on stderr
- **WHEN** `spider init --workspace H/work/Проверка.txt/site` runs as a real process, and `H/work/Проверка.txt` is a file
- **THEN** stderr contains the bytes `D0 9F D1 80 D0 BE D0 B2 D0 B5 D1 80 D0 BA D0 B0`

### Requirement: Writing output to a file with -o

`-o/--output <file>` SHALL write into the file exactly the bytes the Command would write to stdout, and SHALL write nothing to stdout.
- The Command SHALL report the file with the info line `output_written`, whose `details.path` is the file's absolute path.
- A relative path is taken from the current folder.
- Missing parent folders SHALL be created.
- An existing file SHALL be replaced, but only when the Command succeeds. When the Command fails, an existing file SHALL keep its content and no new file SHALL appear.

A target that cannot be written SHALL fail with `output_not_writable`, and the message SHALL name the path. This includes a file that another program holds open.

#### Scenario: Output goes to the file
- **WHEN** the example list Command runs with `--limit 5 -o out.json` in `H/work`, where `out.json` contains `old`
- **THEN** `H/work/out.json` contains exactly `{"total":5,"items":[{"n":1},{"n":2},{"n":3},{"n":4},{"n":5}],"next_cursor":null}` followed by `\n`

#### Scenario: Nothing on stdout with -o
- **WHEN** the example list Command runs with `-o out.json` in `H/work`
- **THEN** stdout is empty

#### Scenario: The written file is reported
- **WHEN** the example list Command runs with `-o out.json` in `H/work`
- **THEN** stderr has a line with `"level":"info"`, `"code":"output_written"` and `"details":{"path":"H/work/out.json"}`

#### Scenario: Parent folders are created
- **WHEN** `spider init -o H/work/new/deeper/init.json` runs in the empty folder `H/work/shop`, and `H/work/new` does not exist
- **THEN** `H/work/new/deeper/init.json` exists

#### Scenario: A failing Command keeps the old file
- **WHEN** `spider init --workspace H/work/notes.txt/site -o out.json` runs in `H/work`, where `notes.txt` is a file and `out.json` contains `old`
- **THEN** `H/work/out.json` still contains exactly `old`

#### Scenario: A failing Command creates no file
- **WHEN** `spider init --workspace H/work/notes.txt/site -o fresh.json` runs in `H/work`, where `notes.txt` is a file
- **THEN** `H/work/fresh.json` does not exist

#### Scenario: Target held open on Windows
- **WHEN** on Windows another process holds `H\work\out.json` open without sharing, as Excel does, and `spider commands -o H\work\out.json` runs
- **THEN** the exit code is 7, and the error has the code `output_not_writable` and a message that contains `H\work\out.json`

### Requirement: Paging envelope for list Commands

With `--format json`, a list Command SHALL return a JSON object with these keys:
- `total`: the number of matching items
- `items`: at most `--limit` items
- `next_cursor`: an opaque string, or `null` on the last page

It MAY add other top-level keys that describe the whole list.

`--limit` SHALL default to 50 and accept values from 0 to 1000. `--limit 0` returns only the count, with `items` `[]` and `next_cursor` `null`.

Items SHALL come in a deterministic order, so the same request against unchanged data returns the same output. Following `next_cursor` until it is `null` SHALL return every item exactly once.

#### Scenario: First page
- **WHEN** the example list Command runs with `--limit 2`
- **THEN** `total` is `5`, `items` is `[{"n":1},{"n":2}]`, and `next_cursor` is a non-empty string

#### Scenario: Following cursors
- **WHEN** the example list Command runs with `--limit 2`, and then again with each `next_cursor` until `next_cursor` is `null`
- **THEN** the pages hold `[{"n":1},{"n":2}]`, `[{"n":3},{"n":4}]` and `[{"n":5}]`, in that order

#### Scenario: Everything on one page
- **WHEN** the example list Command runs without `--limit`
- **THEN** `items` holds 5 items, and `next_cursor` is `null`

#### Scenario: Default limit
- **WHEN** a list Command whose items are `{"n":1}` to `{"n":60}` runs without `--limit`
- **THEN** `items` is `{"n":1}` to `{"n":50}`, and `next_cursor` is a non-empty string

#### Scenario: Count only
- **WHEN** the example list Command runs with `--limit 0`
- **THEN** stdout is exactly `{"total":5,"items":[],"next_cursor":null}` followed by `\n`

#### Scenario: Same request, same output
- **WHEN** the example list Command runs twice with `--limit 2`
- **THEN** both runs write byte-identical stdout

#### Scenario: Limit above the maximum
- **WHEN** the example list Command runs with `--limit 1001`
- **THEN** the exit code is 2, and the error has the code `invalid_value`

#### Scenario: Negative limit
- **WHEN** the example list Command runs with `--limit -1`
- **THEN** the exit code is 2, and the error has the code `invalid_value`

#### Scenario: Limit of the wrong type
- **WHEN** the example list Command runs with `--limit abc`
- **THEN** the exit code is 2, and the error has the code `invalid_value`

### Requirement: Choosing fields with --fields

`--fields` SHALL take a comma-separated list of field names. Each item then has exactly those keys, in that order. `--fields all` SHALL select every available field, in the Command's field order. Without `--fields`, the Command's default fields apply, as listed by `spider commands`.

An unknown field name SHALL fail with `unknown_field`, with `details.field` and `details.available`.

#### Scenario: Default fields
- **WHEN** the example list Command runs with `--limit 1`
- **THEN** `items` is `[{"n":1}]`

#### Scenario: Fields in the requested order
- **WHEN** the example list Command runs with `--fields sq,n --limit 1`
- **THEN** `items` is `[{"sq":1,"n":1}]`

#### Scenario: All fields
- **WHEN** the example list Command runs with `--fields all --limit 1`
- **THEN** `items` is `[{"n":1,"sq":1}]`

#### Scenario: Unknown field
- **WHEN** the example list Command runs with `--fields n,size`
- **THEN** the exit code is 2, and the error has the code `unknown_field` and `"details":{"field":"size","available":["n","sq"]}`

### Requirement: Cursors

A cursor SHALL be an opaque string, accepted only by the Command, arguments and filters that produced it. `--limit`, `--fields` and `--format` MAY change between pages. Any other cursor SHALL fail with `invalid_cursor`. That includes a cursor that was altered or truncated, or one produced by a different request.

#### Scenario: A different limit continues the list
- **WHEN** the `next_cursor` of the example list Command run with `--limit 1` is passed to the same Command with `--limit 2 --cursor <that cursor>`
- **THEN** `items` is `[{"n":2},{"n":3}]`

#### Scenario: Cursor from a different request
- **WHEN** the `next_cursor` of the example list Command run with `--limit 1` is passed to the same Command with `--odd --cursor <that cursor>`
- **THEN** the exit code is 2, and the error has the code `invalid_cursor`

#### Scenario: Garbage cursor
- **WHEN** the example list Command runs with `--cursor abc`
- **THEN** the exit code is 2, and the error has the code `invalid_cursor`

### Requirement: Progress events on stderr

A Command that reports progress SHALL write each event to stderr as one compact JSON line, `{"event":<name>,"ts":<timestamp>,"data":<object>}`, written and flushed as it happens. Its result SHALL go to stdout once, when it ends, as for any other Command. No event SHALL be written to stdout, and there is no result event.

#### Scenario: Event line
- **WHEN** the event `progress` with the data `{"crawled":3}` is written at `2026-09-27T14:03:12.345Z`
- **THEN** the line written is exactly `{"event":"progress","ts":"2026-09-27T14:03:12.345Z","data":{"crawled":3}}` followed by `\n`

#### Scenario: The result goes to stdout
- **WHEN** a Command reports two `progress` events and ends with the result `{"urls":10}`
- **THEN** stdout is exactly `{"urls":10}` followed by `\n`

#### Scenario: Events go to stderr
- **WHEN** a Command reports two `progress` events and ends with the result `{"urls":10}`
- **THEN** stderr has exactly two lines, and both have `"event":"progress"`

#### Scenario: Events and diagnostics share stderr
- **WHEN** a Command reports a `progress` event and a warning
- **THEN** every line of stderr is a JSON object with either an `event` key or a `level` key

### Requirement: Partial results

A Command whose result describes a failed outcome SHALL:
- print that result on stdout
- write exactly one error diagnostic, as its last line on stderr
- exit with that error's exit code

Every other failing Command SHALL write nothing to stdout.

#### Scenario: The result of a failed outcome is printed
- **WHEN** a Command ends with the result `{"state":"failed"}` and an error diagnostic whose exit code is 1
- **THEN** stdout is exactly `{"state":"failed"}` followed by `\n`

#### Scenario: One error and its exit code
- **WHEN** a Command ends with the result `{"state":"failed"}` and an error diagnostic whose exit code is 1
- **THEN** the exit code is 1, and stderr has exactly one line with `"level":"error"`, which is its last line

### Requirement: Diagnostics on stderr

Errors, warnings and notices SHALL be written to stderr, one compact JSON object per line. Each object SHALL have exactly these keys:
- `level`: `error`, `warning` or `info`
- `code`: lowercase snake_case
- `message`
- `hint`: a string, or `null`
- `details`: an object, possibly empty

A failing Command SHALL write exactly one error object, as its last line on stderr. An error or warning reported inside a result, such as an entry in a `warnings` list, SHALL use the same shape.

Errors found while parsing the command line SHALL use the same shape: `usage_error` for an unknown Command, an unknown flag or a missing argument, and `invalid_value` for a value that is not allowed. An unexpected failure SHALL use `internal_error`, with the Python traceback text in `details.traceback`.

Nothing else SHALL appear on stderr apart from progress events: no raw tracebacks, progress bars or log lines.

#### Scenario: Unknown Command
- **WHEN** `spider nosuchcommand` runs
- **THEN** the exit code is 2, and the error has the code `usage_error`

#### Scenario: Error object
- **WHEN** `spider nosuchcommand` runs
- **THEN** the last line of stderr is a JSON object whose keys are exactly `level`, `code`, `message`, `hint` and `details`, with `"level":"error"`

#### Scenario: Only JSON lines on stderr
- **WHEN** `spider init --workspace H/work/notes.txt/site` runs, and `H/work/notes.txt` is a file
- **THEN** every line of stderr parses as a JSON object

#### Scenario: Unexpected failure
- **WHEN** a Command raises `RuntimeError("disk exploded")`
- **THEN** the exit code is 70, and the error has the code `internal_error` and a `details.traceback` that contains `RuntimeError: disk exploded`

#### Scenario: A warning inside a result
- **WHEN** a Command ends with a result whose `warnings` list holds one warning
- **THEN** that entry's keys are exactly `level`, `code`, `message`, `hint` and `details`

### Requirement: Exit codes

Every Command SHALL exit with one of these codes. The meaning of a code SHALL never change, and codes 9 to 63 are reserved:

| Code | Name | Meaning |
|---|---|---|
| 0 | `ok` | success |
| 1 | `failed` | the Command ran but could not do everything asked; the error says what |
| 2 | `usage` | the command line is wrong: an unknown Command, flag or name, or a missing or invalid value |
| 3 | `config` | `spider.toml` or a setting is invalid |
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

#### Scenario: The table is self-described
- **WHEN** `spider commands` runs
- **THEN** the `code` and `name` pairs of `exit_codes` are, in order, `0 ok`, `1 failed`, `2 usage`, `3 config`, `4 not_found`, `5 busy`, `6 incompatible`, `7 io`, `8 network`, `70 internal`, `130 interrupted`

#### Scenario: Error codes of this change
- **WHEN** `spider commands` runs
- **THEN** its `diagnostics` give these exit codes: `usage_error` 2, `invalid_value` 2, `unknown_field` 2, `invalid_cursor` 2, `settings_invalid` 3, `workspace_not_found` 4, `workspace_not_writable` 7, `output_not_writable` 7 and `internal_error` 70

#### Scenario: Naming rule for input errors
- **WHEN** `spider commands` runs
- **THEN** every diagnostic whose code starts with `invalid_` or `unknown_` has `"exit_code":2`

#### Scenario: A warning keeps exit code 0
- **WHEN** `spider init` runs in `H/work/shop/blog`, and `H/work/shop` contains `.spider/`
- **THEN** the exit code is 0

### Requirement: Global flags

`--workspace <dir>`, `--crawl <ref>`, `--format <format>`, `--no-bom` and `-o/--output <file>` SHALL mean the same on every Command that accepts them. They SHALL be given after the Command name.
- A Command SHALL reject a global flag it does not use with `usage_error`.
- A global flag given before the Command name SHALL fail with `usage_error`, whose hint says to put it after the Command name.

`--crawl` is defined by `015-add-crawl-store`.

#### Scenario: After the Command name
- **WHEN** `spider init --format json` runs in the empty folder `H/work/shop`
- **THEN** the exit code is 0

#### Scenario: A flag the Command does not use
- **WHEN** `spider commands --workspace H/work` runs
- **THEN** the exit code is 2, and the error has the code `usage_error`

#### Scenario: Before the Command name
- **WHEN** `spider --format table init` runs
- **THEN** the exit code is 2, and the error has the code `usage_error` and a hint that contains `after the Command name`

#### Scenario: Global flags of init
- **WHEN** `spider commands` runs
- **THEN** the options of the `init` entry include `--workspace`, `--format`, `--no-bom` and `--output`, each with `"global":true`

### Requirement: Self-description with spider commands

`spider commands` SHALL return one JSON document with these keys:

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
- `options`: each with `name`, `short`, `type`, `choices`, `default`, `required`, `multiple`, `global`, `setting` (its `spider.toml` key, or null), `secret` and `description`
- `fields`: `{available, default}` for list and rows Commands, otherwise null
- `examples`

The output SHALL be identical on every OS for the same version, and SHALL NOT need a Workspace.

#### Scenario: The Command lists itself
- **WHEN** `spider commands` runs
- **THEN** `commands` has an entry with `"name":"commands"`

#### Scenario: Entry of a document Command
- **WHEN** `spider commands` runs
- **THEN** the `init` entry has `"output":"document"`, `"events":false`, `"formats":["json","table","csv"]` and `"fields":null`

#### Scenario: Entry of a list Command
- **WHEN** `spider commands` runs in a tool that includes the example list Command
- **THEN** its entry has `"output":"list"`, `"formats":["json","jsonl","table","csv"]` and `"fields":{"available":["n","sq"],"default":["n"]}`

#### Scenario: Option details
- **WHEN** `spider commands` runs
- **THEN** the `--workspace` option of the `init` entry has `"type":"path"`, `"default":null`, `"global":true`, `"setting":null` and `"secret":false`

#### Scenario: Tool version
- **WHEN** `spider commands` runs
- **THEN** `tool` is `{"name":"spider","version":V}`, where V is the `version` in `pyproject.toml`

#### Scenario: Same description on every OS
- **WHEN** `spider commands` runs on Windows, macOS and Linux
- **THEN** the entry for `init` is byte-identical on all three

### Requirement: Help and version are plain text

`--help`, on the tool or on any Command, SHALL print plain-text help to stdout and exit 0. `spider` with no arguments SHALL do the same as `spider --help`. `spider --version` SHALL print `spider <version>` followed by `\n`, and exit 0. These SHALL be the only outputs that are not JSON.

#### Scenario: Help
- **WHEN** `spider init --help` runs
- **THEN** the exit code is 0, and stdout contains `Usage:`

#### Scenario: No arguments
- **WHEN** `spider` runs with no arguments
- **THEN** the exit code is 0, stdout is the same as for `spider --help`, and stderr is empty

#### Scenario: Version
- **WHEN** `spider --version` runs
- **THEN** stdout is exactly `spider `, then the `version` in `pyproject.toml`, then `\n`
