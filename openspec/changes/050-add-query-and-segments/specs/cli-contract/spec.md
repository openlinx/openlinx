## Purpose

Adds to the CLI contract of `010-add-workspace-and-cli-contract`:
- the `csv` format for document, list and rows Commands
- the single CSV policy, which `export` and the Report CSV files of `070-add-html-report` share
- the global flags `--no-bom` and `-o/--output`, and writing output to a file

Conventions used in the scenarios: the **example list Command**, `H` and the way paths are written are as defined in the conventions of the `cli-contract` spec of `010-add-workspace-and-cli-contract`.

## ADDED Requirements

### Requirement: CSV format

`--format` SHALL also accept `csv`. With it, the formats a Command can support are:
- document Commands: `json` (the default), `table` and `csv`
- list Commands: `json` (the default), `jsonl`, `table` and `csv`
- rows Commands: `jsonl` (the default) and `csv`

Each Command SHALL support the formats that `linx commands` lists for it, and a Command MAY support fewer. `linx init` SHALL support `csv`. `linx commands` keeps `json` and `table`, so `--format csv` on it SHALL fail with `invalid_value`. CSV output SHALL follow the requirement "CSV policy".

With `csv`, as with `jsonl` and `table`, when more items exist than were printed, the Command SHALL write the info line `more_items` to stderr, with `details.total` and `details.next_cursor`.

#### Scenario: More items notice in CSV
- **WHEN** the example list Command runs with `--format csv --limit 2`
- **THEN** stderr has a line with `"level":"info"` and `"code":"more_items"`, whose `details.total` is `5` and whose `details.next_cursor` is a non-empty string

#### Scenario: Rows as CSV
- **WHEN** a rows Command that returns the rows `{"n":1}` and `{"n":2}` runs with `--format csv --no-bom`
- **THEN** stdout is exactly `n\r\n1\r\n2\r\n`

#### Scenario: Formats of a document Command
- **WHEN** `linx commands` runs
- **THEN** the `init` entry has `"formats":["json","table","csv"]`

#### Scenario: Formats of a list Command
- **WHEN** `linx commands` runs in a tool that includes the example list Command
- **THEN** its entry has `"formats":["json","jsonl","table","csv"]`

#### Scenario: linx commands refuses CSV
- **WHEN** `linx commands --format csv` runs
- **THEN** the exit code is 2, and the error has the code `invalid_value` and a hint that contains `json` and `table`

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
- **WHEN** `linx init --format csv --no-bom` runs in the empty folder `H/work/shop`
- **THEN** stdout has exactly two rows, and the first is `workspace,data_dir,settings_file,global,created`

#### Scenario: The byte-order mark flag needs CSV
- **WHEN** `linx init --no-bom` runs
- **THEN** the exit code is 2, and the error has the code `invalid_value`

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
- **WHEN** `linx init -o H/work/new/deeper/init.json` runs in the empty folder `H/work/shop`, and `H/work/new` does not exist
- **THEN** `H/work/new/deeper/init.json` exists

#### Scenario: A failing Command keeps the old file
- **WHEN** `linx init --workspace H/work/notes.txt/site -o out.json` runs in `H/work`, where `notes.txt` is a file and `out.json` contains `old`
- **THEN** `H/work/out.json` still contains exactly `old`

#### Scenario: A failing Command creates no file
- **WHEN** `linx init --workspace H/work/notes.txt/site -o fresh.json` runs in `H/work`, where `notes.txt` is a file
- **THEN** `H/work/fresh.json` does not exist

#### Scenario: Target held open on Windows
- **WHEN** on Windows another process holds `H\work\out.json` open without sharing, as Excel does, and `linx commands -o H\work\out.json` runs
- **THEN** the exit code is 7, and the error has the code `output_not_writable` and a message that contains `H\work\out.json`

### Requirement: Global flags --no-bom and -o

`--no-bom` and `-o/--output <file>` SHALL be global flags, as the requirement "Global flags" of the `cli-contract` spec defines them:
- They SHALL mean the same on every Command that accepts them, and SHALL be given after the Command name.
- A global flag given before the Command name SHALL fail with `usage_error`, whose hint says to put it after the Command name.
- Every Command that supports `csv` SHALL accept `--no-bom`. `linx init` and `linx commands` SHALL accept `-o/--output`.
- They SHALL have no `openlinx.toml` key.

`linx commands` SHALL list both in the `options` of every Command that accepts them, with `"global":true` and `"setting":null`.

#### Scenario: -o after the Command name
- **WHEN** `linx init --format csv --no-bom -o H/work/init.csv` runs in the empty folder `H/work/shop`
- **THEN** the exit code is 0, and `H/work/init.csv` exists

#### Scenario: -o before the Command name
- **WHEN** `linx -o out.json init` runs
- **THEN** the exit code is 2, and the error has the code `usage_error` and a hint that contains `after the Command name`

#### Scenario: Global output flags of init
- **WHEN** `linx commands` runs
- **THEN** the options of the `init` entry include `--no-bom` and `--output`, each with `"global":true`

#### Scenario: Output-file flags have no settings key
- **WHEN** `linx commands` runs
- **THEN** the `--no-bom` and `--output` options of the `init` entry each have `"setting":null`

### Requirement: Diagnostic codes of output files

`linx commands` SHALL list in its `diagnostics` the codes that this change adds to the CLI contract:
- `output_not_writable`: an error, with exit code 7 (`io`)
- `output_written`: an info line, with `exit_code` null

#### Scenario: Error code of output files
- **WHEN** `linx commands` runs
- **THEN** its `diagnostics` give `output_not_writable` the level `error` and the exit code 7

#### Scenario: Info line of output files
- **WHEN** `linx commands` runs
- **THEN** its `diagnostics` give `output_written` the level `info` and `"exit_code":null`
