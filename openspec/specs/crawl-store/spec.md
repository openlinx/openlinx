# crawl-store Specification

## Purpose

Defines how each Crawl is stored as one self-contained SQLite file with a public, versioned, documented schema ("your crawl is a database"). It covers:
- crawl ids, and selecting a Crawl with `--crawl`
- crawl metadata, Crawl States and the redaction of secrets
- the transactional writer, its write check, and reading while a Crawl is written
- the journal mode
- `spider schema`, `docs/schema.md`, and the conventions every table follows

Conventions used in the scenarios:
- `H` is the absolute path of the home folder.
- Paths are written with `/`, and Windows uses `\`.
- "A Command that reads a Crawl" is any Command with the `--crawl` option. Until `050-add-query-and-segments` adds the real ones, an example Command on the test app stands in, and it reports the id of the Crawl it read.
- Redaction scenarios use the test app's `example-settings` Command (`010-add-workspace-and-cli-contract`): `--token` maps to the secret setting `example.token`, `--level` maps to the plain setting `example.level`, and `--api-key` maps to no setting and is secret on its own.

## Requirements

### Requirement: One file per Crawl

**In short:** each Crawl is one self-contained SQLite file that opens from anywhere by its path.

Each Crawl SHALL be stored as one SQLite file, `<data folder>/crawls/<crawl-id>.sqlite`. The file SHALL be self-contained: a copy SHALL open as the same Crawl from any folder when its path is given to `--crawl`.

#### Scenario: Location of a crawl file
- **WHEN** a Crawl with the id `20260927-140312-k3f9` is created in the local Workspace `H/work/shop`
- **THEN** the file `H/work/shop/.spider/crawls/20260927-140312-k3f9.sqlite` exists

#### Scenario: A copied file opens by its path
- **WHEN** the crawl file of the Crawl `20260927-140312-k3f9` is copied to `H/work/copy/c.sqlite`, and the Crawl `H/work/copy/c.sqlite` is opened
- **THEN** its `crawl.id` is `"20260927-140312-k3f9"`

### Requirement: Crawl ids

**In short:** a crawl id is the Crawl's UTC start time plus 4 random characters, and is never one already taken in the Workspace.

A crawl id SHALL consist of:
- the Crawl's UTC start time, formatted `YYYYMMDD-HHMMSS`
- a hyphen
- 4 random characters from `0123456789abcdefghjkmnpqrstvwxyz`

An id SHALL count as taken in a Workspace when `<id>.sqlite` exists in its `crawls/` folder. A new id SHALL never be a taken one: new random characters SHALL be drawn until it is not, and the crawl file SHALL be created exclusively, so two processes can never create the same id.

#### Scenario: Id from the start time
- **WHEN** a Crawl is created at `2026-09-27T14:03:12.345Z`, and the random source yields `k3f9`
- **THEN** its id is `20260927-140312-k3f9`

#### Scenario: A taken id is drawn again
- **WHEN** `20260927-140312-k3f9.sqlite` exists, and a Crawl is created at `2026-09-27T14:03:12.900Z` while the random source yields `k3f9` and then `m2p7`
- **THEN** the new Crawl's id is `20260927-140312-m2p7`

#### Scenario: Character set
- **WHEN** ids are created with the system random source for any UTC start time from `2000-01-01T00:00:00.000Z` to `2099-12-31T23:59:59.999Z`
- **THEN** every id matches `^[0-9]{8}-[0-9]{6}-[0-9a-hjkmnp-tv-z]{4}$`

### Requirement: Storing a Crawl creates the data folder

**In short:** creating a Crawl creates a missing data folder, never the settings file, and fails before crawling when that folder cannot be written.

Creating a Crawl SHALL create the Workspace's data folder, its `.gitignore` and its `crawls/` folder, as `010-add-workspace-and-cli-contract` defines them, when they are missing. It SHALL NOT create the settings file. When the data folder cannot be created or written, creating the Crawl SHALL fail with `workspace_not_writable`, whose `details.path` names the path that failed, before anything is crawled.

#### Scenario: First Crawl in the global Workspace
- **WHEN** a Crawl with the id `20260927-140312-k3f9` is created in the global Workspace, and `H/.spider` does not exist
- **THEN** the file `H/.spider/crawls/20260927-140312-k3f9.sqlite` exists

#### Scenario: No settings file is created by storing a Crawl
- **WHEN** a Crawl is created in the local Workspace `H/work/shop`, which has `.spider/` but no `spider.toml`
- **THEN** `H/work/shop/spider.toml` does not exist

#### Scenario: Unwritable data folder
- **WHEN** a Crawl is created in the global Workspace, and `H/.spider` is a file
- **THEN** creation fails with the error code `workspace_not_writable`, and `details.path` starts with `H/.spider`

#### Scenario: Unwritable crawls folder
- **WHEN** a Crawl is created in the local Workspace `H/work/shop`, and no new file can be created in `H/work/shop/.spider/crawls/`
- **THEN** creation fails with the error code `workspace_not_writable`, and `details.path` starts with `H/work/shop/.spider/crawls`

### Requirement: The writer checks that it can write

**In short:** the writer proves it can write to the crawl file before any work runs, and fails with `crawl_not_writable` otherwise.

Opening a Crawl's writer SHALL first run a write inside a transaction that it rolls back. When that fails, opening SHALL fail with `crawl_not_writable`, whose `details.file` is the crawl file, before any unit of work runs. The file SHALL be left unchanged.

#### Scenario: A read-only crawl file
- **WHEN** the writer is opened for a crawl file that has the read-only file attribute
- **THEN** opening fails with the error code `crawl_not_writable`, `details.file` is that file's path, and the SHA-256 of the file is unchanged

### Requirement: Selecting a Crawl with --crawl

**In short:** `--crawl` selects the latest Crawl by default, or a Crawl given by id or by file path, and never creates a folder or crawl file.

A Command that reads a Crawl SHALL take the global flag `--crawl` with one of these values:
- `latest`, the default
- a crawl id
- the path of a crawl file: a value that contains a path separator or ends in `.sqlite`

`latest` SHALL be the Crawl that started most recently, whatever its state. The start time is taken from the id. Among ids of the same second, the later `crawl.started_at` wins, and then the greater id, so the choice is always the same.

Only files named `<id>.sqlite` SHALL count as Crawls. Selecting a Crawl SHALL NOT create any folder or crawl file. SQLite's own `-wal` and `-shm` companions of an existing crawl file MAY appear, because a reader in WAL mode needs the shared-memory file; they never count as Crawls.

A Crawl selected by id or by `latest` SHALL be the Crawl of that id: its file is named after its id, so a `crawl` row with another id makes the file invalid. A Crawl selected by path SHALL have the id of its `crawl` row, whatever the file is named.

Failures SHALL use these error codes:

| Code | When |
|---|---|
| `no_crawls` | the Workspace has no Crawl; the hint names `spider crawl` |
| `crawl_not_found` | no Crawl has the given id, or no file exists at the given path |
| `crawl_file_invalid` | the selected file is not a readable crawl file, or a file selected by id or `latest` holds another id; `details.file` names it |
| `invalid_value` | any other value |

#### Scenario: Latest is the most recent start
- **WHEN** `latest` is resolved in a Workspace holding `20260927-100000-aaaa`, started at `2026-09-27T10:00:00.000Z`, and `20260927-110000-bbbb`, started at `2026-09-27T11:00:00.000Z`
- **THEN** the Crawl `20260927-110000-bbbb` is selected

#### Scenario: A running Crawl can be latest
- **WHEN** `latest` is resolved in a Workspace holding `20260927-100000-aaaa`, in the state `completed`, and `20260927-110000-bbbb`, in the state `running`
- **THEN** the Crawl `20260927-110000-bbbb` is selected

#### Scenario: Two Crawls in the same second
- **WHEN** `latest` is resolved in a Workspace holding `20260927-100000-zzzz`, started at `2026-09-27T10:00:00.100Z`, and `20260927-100000-aaaa`, started at `2026-09-27T10:00:00.900Z`
- **THEN** the Crawl `20260927-100000-aaaa` is selected

#### Scenario: Only crawl files are Crawls
- **WHEN** `latest` is resolved in a Workspace holding `20260927-100000-aaaa.sqlite` and only `20260927-110000-bbbb.log` for the later id
- **THEN** the Crawl `20260927-100000-aaaa` is selected

#### Scenario: By id
- **WHEN** `20260927-100000-aaaa` is resolved in a Workspace holding that Crawl
- **THEN** the Crawl `20260927-100000-aaaa` is selected

#### Scenario: No Crawls
- **WHEN** `latest` is resolved in a Workspace with no Crawl
- **THEN** resolution fails with the error code `no_crawls`

#### Scenario: Unknown id
- **WHEN** `20260101-000000-zzzz` is resolved, and no Crawl has that id
- **THEN** resolution fails with the error code `crawl_not_found`

#### Scenario: Malformed reference
- **WHEN** `yesterday` is resolved
- **THEN** resolution fails with the error code `invalid_value`

#### Scenario: Not a crawl file
- **WHEN** `H/work/notes.sqlite`, a text file containing `hello`, is resolved
- **THEN** resolution fails with the error code `crawl_file_invalid`

#### Scenario: A missing crawl file path
- **WHEN** `H/work/none.sqlite` is resolved, and no such file exists
- **THEN** resolution fails with the error code `crawl_not_found`

#### Scenario: A crawl file that holds another id
- **WHEN** `20260927-100000-aaaa` is resolved, and the `crawl` row of `20260927-100000-aaaa.sqlite` has the id `20260927-090000-zzzz`
- **THEN** resolution fails with the error code `crawl_file_invalid`, and `details` has `expected_id` `"20260927-100000-aaaa"` and `found_id` `"20260927-090000-zzzz"`

#### Scenario: Companion files are not Crawls
- **WHEN** `latest` is resolved in a Workspace holding `20260927-100000-aaaa.sqlite` and only `20260927-110000-bbbb.sqlite-wal` for the later id
- **THEN** the Crawl `20260927-100000-aaaa` is selected

#### Scenario: A broken newest file is reported, not skipped
- **WHEN** `latest` is resolved in a Workspace holding a valid `20260927-100000-aaaa` and an empty file `20260927-110000-bbbb.sqlite`
- **THEN** resolution fails with the error code `crawl_file_invalid`, and `details.file` ends with `20260927-110000-bbbb.sqlite`

#### Scenario: Reading creates nothing
- **WHEN** `latest` is resolved from the current folder `H/work/notes`, which resolves to the global Workspace, and `H/.spider` does not exist
- **THEN** `H/.spider` still does not exist afterwards

#### Scenario: The flag defaults to latest
- **WHEN** a Command that reads a Crawl runs without `--crawl` in a Workspace holding `20260927-100000-aaaa` and `20260927-110000-bbbb`
- **THEN** it reads the Crawl `20260927-110000-bbbb`

#### Scenario: Unknown id on the command line
- **WHEN** a Command that reads a Crawl runs with `--crawl 20260101-000000-zzzz`, and no Crawl has that id
- **THEN** the exit code is 4, and the error has the code `crawl_not_found`

#### Scenario: No Crawls on the command line
- **WHEN** a Command that reads a Crawl runs in a Workspace with no Crawl
- **THEN** the exit code is 4, and the error has the code `no_crawls` and a hint that contains `spider crawl`

#### Scenario: A text file on the command line
- **WHEN** a Command that reads a Crawl runs with `--crawl H/work/notes.sqlite`, a text file containing `hello`
- **THEN** the exit code is 6, and the error has the code `crawl_file_invalid`

#### Scenario: A malformed value on the command line
- **WHEN** a Command that reads a Crawl runs with `--crawl yesterday`
- **THEN** the exit code is 2, and the error has the code `invalid_value`

#### Scenario: The flag is described as global
- **WHEN** `spider commands` runs on the test app
- **THEN** the example Command's `--crawl` option has `"global":true` and `"default":"latest"`

### Requirement: Crawl metadata

**In short:** every crawl file records when and how its Crawl started, with its Seeds and resolved settings, and holds no running counts.

Every crawl file SHALL hold the table `crawl`, with exactly one row, and the table `seeds`, with one row per Seed. They SHALL have these columns:

| Column | Content |
|---|---|
| `crawl.id` | the crawl id |
| `crawl.crawl_mode` | `spider`, `list` or `sitemap` |
| `crawl.section_crawl` | `1` for a Section Crawl, otherwise `0` |
| `crawl.state` | the Crawl State |
| `crawl.started_at` | the start time |
| `crawl.completed_at` | the time the state became `completed`; NULL in every other state |
| `crawl.command_argv` | the command line, as a JSON array that starts with `"spider"`, with secrets redacted |
| `crawl.cwd` | the absolute folder the Command ran in |
| `crawl.settings_file` | the absolute path of the `spider.toml` that was read, or NULL |
| `crawl.config` | the resolved settings, as a JSON object of tables and keys, with secrets redacted |
| `crawl.tool_version` | the tool version that created the Crawl |
| `crawl.schema_version` | the file's schema version, also stored as SQLite `user_version` |
| `crawl.journal_mode` | `wal` or `delete` |
| `crawl.python_version` | the Python version that created the Crawl |
| `crawl.platform` | the operating system description |
| `seeds.position` | the 1-based order in which the Seed was given |
| `seeds.url` | the Seed URL as given |

The `crawl` row SHALL hold no counts or statistics that are written while the Crawl runs. Counts are derived from the tables that hold the rows they count. A derived value over the stored rows, such as a score, MAY be stored only when a post-crawl pass writes it, and its column is marked as derived (see "Public schema conventions").

#### Scenario: Metadata of a new Crawl
- **WHEN** a Spider-mode Crawl is created with:
  - the time `2026-09-27T14:03:12.345Z`
  - the Seed `https://example.com/`
  - the command line `["spider","crawl","https://example.com/"]`
  - the current folder `H/work/shop`, which has no `spider.toml`
  - the resolved config `{"store":{"journal_mode":"auto"}}`
- **THEN** its `crawl` row has:
  - `crawl_mode` `"spider"`, `section_crawl` `0` and `state` `"running"`
  - `started_at` `"2026-09-27T14:03:12.345Z"` and `completed_at` NULL
  - `command_argv` `["spider","crawl","https://example.com/"]`, `cwd` `"H/work/shop"`, `settings_file` NULL
  - `config` `{"store":{"journal_mode":"auto"}}`

#### Scenario: Seeds keep their order
- **WHEN** a Crawl is created with the Seeds `https://example.com/b` and then `https://example.com/a`
- **THEN** `seeds` holds exactly the rows `(1, "https://example.com/b")` and `(2, "https://example.com/a")`

#### Scenario: Version stamp
- **WHEN** a Crawl is created
- **THEN** `crawl.tool_version` equals the `version` in `pyproject.toml`, and `crawl.schema_version` and SQLite's `user_version` are both `1`

#### Scenario: Environment stamp
- **WHEN** a Crawl is created
- **THEN** `crawl.python_version` matches `^3\.(12|13|14)\.[0-9]+$`, and `crawl.platform` is a non-empty string

#### Scenario: Completion time
- **WHEN** a Crawl's state is set to `completed` at `2026-09-27T15:00:00.000Z`
- **THEN** `crawl.completed_at` is `"2026-09-27T15:00:00.000Z"`

#### Scenario: A stopped Crawl has no completion time
- **WHEN** a Crawl's state is set to `stopped`
- **THEN** `crawl.completed_at` is NULL

### Requirement: Crawl states

**In short:** a Crawl is always in one of the five Crawl States, and starts as *running*.

`crawl.state` SHALL hold one of these Crawl States, and a new Crawl SHALL start as `running`:

| State | Meaning |
|---|---|
| `running` | a process is crawling, or was when it last wrote the file |
| `stopped` | ended before its end |
| `completed` | it ran to the end |
| `failed` | it could not continue |
| `interrupted` | its process died without recording an end |

#### Scenario: State values are documented
- **WHEN** `spider schema crawl` runs
- **THEN** the `state` column has `"values":["running","stopped","completed","failed","interrupted"]`

### Requirement: Redacting secrets

**In short:** secrets in the recorded command line and settings are masked, so the crawl file never contains them.

When a Crawl is created, the secrets in its recorded command line (`crawl.command_argv`) and its recorded config (`crawl.config`) SHALL be replaced:
- A secret is the value of a secret option or a secret setting, as `010-add-workspace-and-cli-contract` declares them: once, on the settings field, or on an option that maps to no setting.
- A secret value that is a URL with a password SHALL keep everything but the password: `http://ann:***@proxy.test:8080`.
- Any other secret value SHALL become `***`.

Redaction SHALL cover both the `--flag value` and the `--flag=value` forms. No part of the crawl file SHALL contain a redacted value.

A secret option SHALL have only long names, so that the attached short form (`-tVALUE`) can never carry a secret. Registering a Command that declares a short name on an option that is secret on its own SHALL fail. An option that is secret through its setting SHALL be checked by a test over every registered Command, because registering a Command loads no settings table.

#### Scenario: Secret option with a separate value
- **WHEN** the command line `["spider","example-settings","--token","s3cret"]` is redacted
- **THEN** the result is `["spider","example-settings","--token","***"]`

#### Scenario: Secret option with a joined value
- **WHEN** the command line `["spider","example-settings","--api-key=s3cret"]` is redacted
- **THEN** the result is `["spider","example-settings","--api-key=***"]`

#### Scenario: A URL keeps everything but its password
- **WHEN** the command line `["spider","example-settings","--token","http://ann:s3cret@proxy.test:8080"]` is redacted
- **THEN** the result is `["spider","example-settings","--token","http://ann:***@proxy.test:8080"]`

#### Scenario: Secret setting
- **WHEN** the config `{"example":{"level":"high","token":"s3cret"}}` is redacted
- **THEN** the result is `{"example":{"level":"high","token":"***"}}`

#### Scenario: Other values are kept
- **WHEN** the command line `["spider","example-settings","--level","high"]` is redacted
- **THEN** the result is `["spider","example-settings","--level","high"]`

#### Scenario: An unset secret stays null
- **WHEN** the config `{"example":{"level":"high","token":null}}` is redacted
- **THEN** the result is `{"example":{"level":"high","token":null}}`

#### Scenario: A malformed secret URL
- **WHEN** the command line `["spider","example-settings","--token","http://[ann:s3cret@proxy.test"]` is redacted
- **THEN** the result is `["spider","example-settings","--token","***"]`

#### Scenario: A secret setting that is not a string
- **WHEN** the config `{"example":{"token":12345}}` is redacted
- **THEN** the result is `{"example":{"token":"***"}}`

#### Scenario: A secret option with a short name is refused
- **WHEN** a Command that declares the option `--api-key` with the short name `-k`, secret on its own, is registered
- **THEN** registering fails with an error that names `api_key`

#### Scenario: Options of secret settings have only long names
- **WHEN** every option of every registered Command is checked against the registered settings tables
- **THEN** no option mapped to a secret setting has a short name

#### Scenario: The secret is nowhere in the file
- **WHEN** a Crawl is created with the command line `["spider","example-settings","--token","s3cret"]` and the config `{"example":{"token":"s3cret"}}`, and its writer is closed
- **THEN** the bytes of the crawl file and of its `-wal` file do not contain `s3cret`

### Requirement: Transactional writer

**In short:** all Crawl data goes through one writer that runs units of work in order, each all-or-nothing, and commits them in batches that survive a crash.

Crawl data SHALL be written only through the Crawl's transactional writer. Callers submit units of work, and each unit may insert, update and read rows.
- **Order:** units SHALL run one at a time, in the order they were submitted. Each unit runs in the writer's open transaction and sees the effects of every unit before it. A unit that only reads SHALL commit nothing.
- **Atomic units:** a unit that fails SHALL leave no change, and its error SHALL be raised to its caller. The other units SHALL be unaffected. A unit that fails SHALL NOT run again.
- **Units may run again:** when a unit fails, the units that ran before it since the last commit MAY run a second time before they are committed. A unit SHALL therefore have no effect outside the writer's connection, SHALL NOT change its input, SHALL be deterministic given the file's state, and SHALL return a value that compares by value. When a unit that runs again raises, returns a different result or changes a different number of rows, the writer SHALL end without that commit: the failing unit's caller still gets its own error, and later units fail with the error that the writer is closed.
- **Commits:** the writer SHALL commit its open transaction when any of these happens:
  - 500 units have run since the last commit
  - 1 second has passed since the first unit after the last commit
  - a unit failed, and the units before it since the last commit have run again (the replay commit)
  - a caller asks for a flush
  - the writer is closed
- **What a result means:** a caller that waits for its unit gets the unit's result once the unit has run, which may be before its commit. A flush, or the Future of a submitted unit (see "Submitting units with their outcome at the commit"), tells the caller that the unit is committed.
- **Durability:** a unit whose transaction was committed SHALL survive the writing process being killed. A kill SHALL lose at most the units that ran after the last commit, and SHALL leave a sound file.

#### Scenario: A unit sees the units before it
- **WHEN** one unit inserts the Seed `(1, "https://example.com/a")`, and the next unit counts the rows of `seeds`, before any commit
- **THEN** the second unit returns `1`

#### Scenario: A unit updates a row of an earlier unit
- **WHEN** one unit inserts the Seed `(1, "https://example.com/a")`, the next unit changes its `url` to `https://example.com/b`, and the writer is closed
- **THEN** `seeds` holds exactly the row `(1, "https://example.com/b")`

#### Scenario: A failing unit leaves no change
- **WHEN** a unit inserts the Seed `(2, "https://example.com/b")` and then raises `ValueError("bad")`, and the writer is closed
- **THEN** the caller of that unit receives `ValueError("bad")`, and `seeds` has no row with position 2

#### Scenario: Other units survive a failing unit
- **WHEN** units insert the Seeds at positions 1 and 3, a unit between them fails, and the writer is closed
- **THEN** `seeds` holds exactly the positions 1 and 3

#### Scenario: A unit that fails half-way after other units leaves no change
- **WHEN** units insert the Seeds `(1, "https://example.com/a")` and `(2, "https://example.com/b")`, the next unit inserts the Seed `(3, "https://example.com/c")`, changes the `url` of position 1 to `https://example.com/z` and then raises `ValueError("bad")`, and the writer is closed
- **THEN** `seeds` holds exactly the rows `(1, "https://example.com/a")` and `(2, "https://example.com/b")`

#### Scenario: A failing unit runs once
- **WHEN** a unit inserts the Seed at position 1, the next unit counts each time it runs, inserts the Seed at position 2 and raises `ValueError("bad")`, and the writer is closed
- **THEN** the failing unit ran exactly once

#### Scenario: An interrupted unit runs once and the writer goes on
- **WHEN** a unit inserts the Seed at position 1, the next unit counts each time it runs, inserts the Seed at position 2 and raises `KeyboardInterrupt`, a third unit inserts the Seed at position 3, and the writer is closed
- **THEN** the caller of the second unit receives `KeyboardInterrupt`, the second unit ran exactly once, and `seeds` holds exactly the positions 1 and 3

#### Scenario: A unit that fails or returns differently when it runs again ends the writer
- **WHEN** a unit inserts the Seed at position 1 and returns how many times it has run, the next unit raises `ValueError("bad")`, and the writer is closed
- **THEN** the caller of the second unit receives `ValueError("bad")`, closing the writer raises `CrawlWriterClosedError("The crawl writer is closed.")`, and `seeds` has no rows

#### Scenario: The failing unit gets its own error when the replay commit fails
- **WHEN** a unit writes a row that breaks a foreign key checked only at the commit, the next unit raises `ValueError("bad")`, and the writer is closed
- **THEN** the caller of the second unit receives `ValueError("bad")`, closing the writer raises `CrawlWriterClosedError("The crawl writer is closed.")`, and the file has no row of the first unit

#### Scenario: A read through the writer commits nothing
- **WHEN** 3 units that each insert one Seed have run, a fourth unit counts the rows of `seeds`, the clock has not moved, and there has been no flush
- **THEN** the fourth unit returns `3`, and a separate reader sees 0 rows in `seeds`

#### Scenario: Units wait for the batch
- **WHEN** 499 units that each insert one Seed have run, the clock has not moved, and there has been no flush
- **THEN** a separate reader sees 0 rows in `seeds`

#### Scenario: The 500th unit commits the batch
- **WHEN** 500 units that each insert one Seed have run, and the clock has not moved
- **THEN** a separate reader sees 500 rows in `seeds`

#### Scenario: The timer commits
- **WHEN** 3 units that each insert one Seed have run, and the clock then moves forward by 1 second
- **THEN** a separate reader sees 3 rows in `seeds`

#### Scenario: A failing unit commits the units before it
- **WHEN** 3 units insert the Seeds at positions 1, 2 and 3, the next unit inserts the Seed at position 4 and raises `ValueError("bad")`, the clock has not moved, and there has been no flush
- **THEN** a separate reader sees exactly the positions 1, 2 and 3 in `seeds`

#### Scenario: A flush commits at once
- **WHEN** 3 units that each insert one Seed have run, and a flush is requested
- **THEN** a separate reader sees 3 rows in `seeds` as soon as the flush returns

#### Scenario: Closing commits everything
- **WHEN** 1,000 units that each insert one Seed have run, and the writer is closed at once
- **THEN** a separate reader sees 1,000 rows in `seeds`

#### Scenario: A killed writer keeps committed units in a sound file
- **WHEN** a process runs 3 units that each insert one Seed, flushes, and is then killed: SIGKILL on Linux and macOS, TerminateProcess on Windows
- **THEN** `PRAGMA integrity_check` on the crawl file returns `ok`, and a reader sees 3 rows in `seeds`

#### Scenario: A killed writer loses uncommitted units
- **WHEN** a process runs 3 units that each insert one Seed, and is killed less than a second later without a flush
- **THEN** a reader sees 0 rows in `seeds`

#### Scenario: A new writer opens the file of a killed writer at once
- **WHEN** a process runs 3 units that each insert one Seed, flushes, and is killed (SIGKILL on Linux and macOS, TerminateProcess on Windows), and a new writer is then opened on the crawl file at once, runs a unit that inserts a fourth Seed, and is closed
- **THEN** `PRAGMA integrity_check` on the crawl file returns `ok`, and a reader sees 4 rows in `seeds`

### Requirement: Journal mode

**In short:** crawl files use WAL by default, and fall back to a rollback journal, with a warning, on a UNC path or when SQLite refuses WAL.

A new crawl file SHALL use the journal mode chosen from the setting `store.journal_mode` and the file's location:

| Setting | Local location | UNC path |
|---|---|---|
| `"auto"` (the default) | `wal` | `delete` (rollback journal), with the warning `store_wal_unavailable` |
| `"wal"` | `wal` | `wal`, with no warning |
| `"delete"` | `delete` | `delete`, with no warning |

A UNC path is one that starts with `\\` or `//`, such as `\\host\share`, `//host/share` and the extended-length form `\\?\UNC\host\share`. The extended-length and device forms of a drive path, `\\?\C:\` and `\\.\C:\`, are local. `crawl.journal_mode` SHALL record the mode used. When SQLite does not grant the WAL mode it was asked for, the file SHALL use `delete` with the same warning.

#### Scenario: UNC path
- **WHEN** the journal mode is chosen for `"auto"` and the location `\\fileserver\share\site\.spider`
- **THEN** it is `delete`, with the warning `store_wal_unavailable`

#### Scenario: Local path
- **WHEN** the journal mode is chosen for `"auto"` and the location `C:\site\.spider`
- **THEN** it is `wal`, with no warning

#### Scenario: Forced WAL on a UNC path
- **WHEN** the journal mode is chosen for `"wal"` and the location `\\fileserver\share\site\.spider`
- **THEN** it is `wal`, with no warning

#### Scenario: Forced rollback journal on a local path
- **WHEN** the journal mode is chosen for `"delete"` and the location `/home/ann/site/.spider`
- **THEN** it is `delete`, with no warning

#### Scenario: WAL refused by SQLite
- **WHEN** the journal mode `wal` was asked for in the location `C:\site\.spider`, and SQLite granted `memory`
- **THEN** it is `delete`, with the warning `store_wal_unavailable`

#### Scenario: WAL granted by SQLite
- **WHEN** the journal mode `wal` was asked for in the location `C:\site\.spider`, and SQLite granted `wal`
- **THEN** it is `wal`, with no warning

#### Scenario: A local extended-length path
- **WHEN** the journal mode is chosen for `"auto"` and the location `\\?\C:\site\.spider`
- **THEN** it is `wal`, with no warning

#### Scenario: A local device path
- **WHEN** the journal mode is chosen for `"auto"` and the location `\\.\C:\site\.spider`
- **THEN** it is `wal`, with no warning

#### Scenario: An extended-length UNC path
- **WHEN** the journal mode is chosen for `"auto"` and the location `\\?\UNC\fileserver\share\site\.spider`
- **THEN** it is `delete`, with the warning `store_wal_unavailable`

#### Scenario: Local disk
- **WHEN** a Crawl is created in a Workspace inside the test's temporary folder on the local disk
- **THEN** `crawl.journal_mode` is `"wal"`

#### Scenario: Crawl on a UNC path on Windows
- **WHEN** on Windows a Crawl is created in a Workspace reached through the UNC path `\\localhost\C$\…` of the test's temporary folder
- **THEN** `crawl.journal_mode` is `"delete"`, and the warning `store_wal_unavailable` is reported with `details.path` equal to the Workspace's data folder

### Requirement: The store setting

**In short:** `[store] journal_mode` in `spider.toml` chooses the journal mode, `"auto"` by default.

This change SHALL register the `spider.toml` table `[store]`, with the setting `journal_mode`: `"auto"`, `"wal"` or `"delete"`, with the default `"auto"`. It follows the settings rules of `010-add-workspace-and-cli-contract`.

#### Scenario: The store setting in the template
- **WHEN** `spider init` runs in the empty folder `H/work/shop`
- **THEN** `H/work/shop/spider.toml` contains the line `[store]`, followed later by the line `# journal_mode = "auto"`

#### Scenario: An invalid store setting
- **WHEN** `spider init` runs in `H/work/shop`, whose `spider.toml` contains `[store]\njournal_mode = "fast"\n`
- **THEN** the exit code is 3, and the error has the code `settings_invalid` and `details.errors[0].key` `"store.journal_mode"`

### Requirement: Reading while a Crawl is written, and waiting for a lock

**In short:** a Crawl can be read while it is written, and a reader or writer kept out by a lock gives up with `crawl_busy` instead of waiting forever.

In `wal` mode, a process SHALL be able to read a Crawl while another process writes it, and it SHALL see every committed row.

In `delete` mode, a reader that cannot read within 5 seconds because a write is in progress SHALL fail with `crawl_busy` instead of waiting longer.

In either mode, a writer that cannot write within 30 seconds because another connection holds the crawl file, on opening, on starting a transaction, while a unit runs or on committing, SHALL fail with `crawl_busy`. In both cases `details.file` SHALL name the crawl file.

On Windows, while the process of a killed writer is still exiting, it can still hold the crawl file's `-shm` file, and SQLite then reports `SQLITE_IOERR_TRUNCATE` when the file is opened. Opening a crawl file, for a reader or the writer, SHALL wait for such a file within the same timeout as for a lock (5 seconds for a reader, 30 for the writer) and then fail with `crawl_busy`, never with `crawl_file_invalid` or a disk I/O error.

#### Scenario: Reading during a write in WAL mode
- **WHEN** a writer process has committed 3 Seed rows and keeps its writer open, and another process reads `seeds`
- **THEN** the reader sees 3 rows

#### Scenario: Busy in rollback-journal mode
- **WHEN** a crawl file in `delete` mode is held under an exclusive write lock for 8 seconds, and another process reads it during that time
- **THEN** the reader fails with the error code `crawl_busy`

#### Scenario: A busy writer on open
- **WHEN** a crawl file in `delete` mode is held under an exclusive lock by another process, and its writer is opened and waits out its busy timeout
- **THEN** opening fails with the error code `crawl_busy`, and `details.file` is that file's path

#### Scenario: A busy writer in a unit
- **WHEN** the writer of a crawl file in `delete` mode is open, another process then holds the file under an exclusive lock, and a unit waits out the writer's busy timeout
- **THEN** the unit's caller receives the error code `crawl_busy`, and `details.file` is that file's path

#### Scenario: A file still held by a killed writer is read once it is released
- **WHEN** the first two attempts to open a crawl file report `SQLITE_IOERR_TRUNCATE`, and the third does not
- **THEN** reading the file returns its `crawl` row

#### Scenario: A file held past the timeout is reported as crawl_busy
- **WHEN** every attempt to open a crawl file reports `SQLITE_IOERR_TRUNCATE` for longer than the opener's busy timeout
- **THEN** opening fails with the error code `crawl_busy`, and `details.file` is that file's path

### Requirement: Readers never change a crawl file

**In short:** reading a Crawl never changes its file.

Commands that only read a Crawl SHALL open its file read-only. Reading SHALL leave the file's bytes unchanged, and any attempt to write through a read-only handle SHALL fail.

#### Scenario: Bytes are unchanged by reading
- **WHEN** the metadata and Seeds of a completed Crawl are read
- **THEN** the SHA-256 of its crawl file is the same as before the read

#### Scenario: Writes through a reader fail
- **WHEN** `INSERT INTO seeds (position, url) VALUES (9, 'https://example.com/x')` is executed through a read-only handle
- **THEN** it fails with a read-only error

### Requirement: Crawl files are released after each operation

**In short:** once an operation on a Crawl ends, the process lets go of its files, so another process can delete them even while this one keeps running.

When an operation on a Crawl finishes, the process SHALL hold no open handle to the crawl file or its `-wal` and `-shm` files. This SHALL hold even when the process keeps running, as the MCP server does.

#### Scenario: Deleting after a read on Windows
- **WHEN** on Windows a process reads the metadata of a completed Crawl and then keeps running
- **THEN** another process can delete the crawl file

#### Scenario: Deleting after a failed read on Windows
- **WHEN** on Windows a process fails to read a file that is not a database as a crawl file, and then keeps running
- **THEN** another process can delete that file

### Requirement: Crawl files from a newer tool are refused

**In short:** a crawl file from a newer tool is refused and left untouched, with a hint to upgrade.

A crawl file whose schema version is newer than the tool's SHALL be refused with `crawl_schema_too_new`, without changing the file:
- `details.file_schema_version` and `details.tool_schema_version` give the two versions
- the hint says to upgrade the tool

#### Scenario: File from a newer tool
- **WHEN** a crawl file at schema version 99 is opened by a tool whose schema version is 1
- **THEN** the open fails with the error code `crawl_schema_too_new` and `"details":{"file_schema_version":99,"tool_schema_version":1}`

#### Scenario: A refused file is unchanged
- **WHEN** a crawl file at schema version 99 is opened by a tool whose schema version is 1
- **THEN** the SHA-256 of the crawl file is the same as before

### Requirement: Listing the schema with spider schema

**In short:** `spider schema` lists the public tables of a crawl file with their columns and indexes, and needs no Workspace or Crawl.

`spider schema [TABLE]` SHALL be a list Command that follows the paging and output rules of `010-add-workspace-and-cli-contract`, with the formats `json`, `jsonl` and `table`.
- Its JSON result SHALL start with the key `schema_version`, the tool's schema version, before `total`.
- Its items are the public tables. They are ordered by the number of the change that added them, and within a change in the order it added them. So `crawl` and `seeds` (from `015`) come first.
- With TABLE, it SHALL list only that table.

Each item SHALL have `name`, `kind` (`table` or `view`), `description`, `columns` and `indexes`. Each column, in table order, SHALL have:
- `name` and `description`
- `type`: `INTEGER`, `REAL`, `TEXT` or `BLOB`
- `nullable` and `primary_key`
- `references`: `<table>.<column>` or `null`
- `format`: `timestamp`, `boolean`, `json` or `null`
- `values`: the allowed values, or `null`

`indexes` SHALL list the table's secondary indexes in name order, without the indexes SQLite makes for primary keys. Each index SHALL have:
- `name` and `description`, the query it serves
- `columns`: its column names, in index order
- `unique`: `true` or `false`
- `where`: the condition of a partial index as SQL text, or `null`

An unknown TABLE SHALL fail with `unknown_table`, whose `details.tables` lists the table names. Tables whose names start with `_` are internal and SHALL NOT be listed. The Command SHALL NOT need a Workspace or a Crawl.

#### Scenario: One table
- **WHEN** `spider schema seeds --fields name` runs
- **THEN** stdout is exactly `{"schema_version":1,"total":1,"items":[{"name":"seeds"}],"next_cursor":null}` followed by `\n`

#### Scenario: First tables
- **WHEN** `spider schema --fields name,kind --limit 2` runs
- **THEN** `items` is `[{"name":"crawl","kind":"table"},{"name":"seeds","kind":"table"}]`

#### Scenario: Columns of seeds
- **WHEN** `spider schema seeds` runs
- **THEN** the item's columns, reduced to `name`, `type`, `nullable` and `primary_key`, are `[{"name":"position","type":"INTEGER","nullable":false,"primary_key":true},{"name":"url","type":"TEXT","nullable":false,"primary_key":false}]`

#### Scenario: Column formats
- **WHEN** `spider schema crawl` runs
- **THEN** the columns `started_at`, `section_crawl` and `config` have the formats `"timestamp"`, `"boolean"` and `"json"`, respectively

#### Scenario: The next page
- **WHEN** `spider schema --fields name --limit 1` runs, and then runs again with `--cursor` set to the first result's `next_cursor`
- **THEN** the second result's `items` is `[{"name":"seeds"}]`

#### Scenario: Unknown table
- **WHEN** `spider schema nosuch` runs
- **THEN** the exit code is 2, and the error has the code `unknown_table` and a `details.tables` that contains `"crawl"` and `"seeds"`

#### Scenario: Internal tables are hidden
- **WHEN** `spider schema --fields name --limit 1000` runs
- **THEN** no listed name starts with `_`

#### Scenario: No Workspace needed
- **WHEN** `spider schema` runs in `H/work/notes`, which is not a Workspace, while `H/.spider` does not exist
- **THEN** the exit code is 0, and `H/.spider` still does not exist

#### Scenario: Self-description of schema
- **WHEN** `spider commands` runs
- **THEN** the `schema` entry has `"output":"list"`, `"formats":["json","jsonl","table"]` and `"fields":{"available":["name","kind","description","columns","indexes"],"default":["name","kind","description","columns","indexes"]}`

#### Scenario: Global flags of schema
- **WHEN** `spider commands` runs
- **THEN** the options of the `schema` entry include `--format` and do not include `--workspace` or `--crawl`

#### Scenario: Default limit of schema
- **WHEN** `spider commands` runs
- **THEN** the `--limit` option of the `schema` entry has `"type":"integer"`, `"default":50` and `"global":false`

#### Scenario: A table without secondary indexes lists none
- **WHEN** `spider schema seeds --fields name,indexes` runs
- **THEN** `items` is `[{"name":"seeds","indexes":[]}]`

### Requirement: The documented schema, the declared schema and the file agree

**In short:** `docs/schema.md`, the declared schema and every new crawl file always describe the same tables, columns and indexes.

The public schema SHALL be declared once, as the store's table definitions, and the two other places that show it SHALL agree with them:
- **`docs/schema.md`,** the public schema reference, SHALL document every public table, column and index with the same name, type, nullability, key, reference, format, values, index columns, uniqueness, condition and description as the declared schema, and SHALL document nothing else.
- **A new crawl file** SHALL have exactly the declared tables, columns and indexes, with the same types, nullability, primary keys, foreign keys, index columns, uniqueness and conditions, as SQLite reports them. Every public table SHALL be `STRICT`, and every table the schema declares `WITHOUT ROWID` SHALL be so in the file.

#### Scenario: Documentation and declaration agree
- **WHEN** the tables parsed from `docs/schema.md` are compared with the description of the declared schema, which `spider schema --limit 1000` prints
- **THEN** they are equal

#### Scenario: A new file matches the declaration
- **WHEN** a Crawl is created, and `PRAGMA table_list`, `PRAGMA table_info`, `PRAGMA foreign_key_list` and `PRAGMA index_list` are read for each table of its file
- **THEN** every public table, column and index of the declared schema is there, with the declared type, nullability, primary key, reference, index columns, uniqueness and condition, every public table is `STRICT`, and the file has no other public table, column or index

### Requirement: Public schema conventions

**In short:** every public table, column and index follows one set of naming, type and value conventions, so the schema reads the same everywhere.

Every public table, column and index SHALL follow these conventions (ADR-0005):
- **Names:** lowercase snake_case. Table names are plural nouns, except the one-row `crawl`.
- **Descriptions:** every table, column and index has a non-empty description.
- **Derived and later columns:** a column that only a post-crawl pass writes is derived. Its description starts with `Derived: `, and it may hold NULL until the pass runs. A column that a later release fills exists from v0.1, holds NULL until then, and its description starts with `Filled from v<major>.<minor>. `.
- **Keys and references:**
  - An entity's own key is `id`, INTEGER, except the public identifiers that a user types (the crawl id and Rule ids), which are TEXT. A table with a natural key uses it.
  - A column that refers to another table is named `<table singular>_id`, with a role prefix when a table refers to the same table twice, and SHALL be declared as a foreign key.
- **Types:** every table is `STRICT`, so a column's type is `INTEGER`, `REAL`, `TEXT` or `BLOB`, and the file refuses a value of another type.
- **Timestamps:** TEXT in the form `YYYY-MM-DDTHH:MM:SS.sssZ`, in UTC, with the format `timestamp`, in a column whose name ends with `_at`. A header's raw value keeps the header's name and text.
- **Booleans:** INTEGER `0` or `1`, with the format `boolean`. The file SHALL refuse any other value. The name reads as yes or no, and is never negated.
- **JSON:** TEXT holding valid JSON, with the format `json`, only for recorded inputs and for lists without a fixed shape. A value that queries filter, sort or count by SHALL be a column of its own.
- **Enumerations:** TEXT whose allowed values are lowercase snake_case, listed in `values`. The file SHALL refuse any other value. Values that a later release adds are listed from v0.1, and one enumeration has one value set in every table that holds it.
- **Errors:** an error is a code column whose values are listed, and its text is in a column named `<code column>_message`.
- **Measured quantities:** the column name ends with its unit: `_ms`, `_seconds`, `_bytes`, `_px` or `_pct` (a share from 0 to 100). A count ends with `_count`. Each column has one meaning, so two different measures, such as two hashes or two sizes, are two distinctly named columns. A column named after a Screaming Frog column keeps that name.
- **Indexes:** each is named `<table>_<columns>`, and its description names the query it serves. An index is built while the Crawl writes, never after it.
- **Order:** a table whose rows have an order SHALL carry it in an INTEGER column that grows in insert order, such as `seeds.position`. Queries that list rows in order SHALL use that column, never a timestamp.

#### Scenario: Names are snake_case
- **WHEN** `spider schema --limit 1000` runs
- **THEN** every table name and column name matches `^[a-z][a-z0-9_]*$`

#### Scenario: Descriptions are present
- **WHEN** `spider schema --limit 1000` runs
- **THEN** every table description and every column description is a non-empty string

#### Scenario: Booleans are integers
- **WHEN** `spider schema --limit 1000` runs
- **THEN** every column with the format `"boolean"` has the type `"INTEGER"`

#### Scenario: Enumeration values are snake_case
- **WHEN** `spider schema --limit 1000` runs
- **THEN** every entry of every non-null `values` matches `^[a-z][a-z0-9_]*$`

#### Scenario: Timestamp text
- **WHEN** the `crawl` row of a Crawl created at `2026-09-27T14:03:12.345Z` is read
- **THEN** `started_at` is the 24-character text `2026-09-27T14:03:12.345Z`

#### Scenario: An unknown enumeration value is refused
- **WHEN** a unit sets `crawl.state` to `"paused"`
- **THEN** the unit fails with SQLite's `CHECK constraint failed` error, and `crawl.state` is unchanged

#### Scenario: A flag outside 0 and 1 is refused
- **WHEN** a unit sets `crawl.section_crawl` to `2`
- **THEN** the unit fails with SQLite's `CHECK constraint failed` error, and `crawl.section_crawl` is unchanged

#### Scenario: A value of another type is refused
- **WHEN** a unit sets `crawl.schema_version` to the text `"first"`
- **THEN** the unit fails with SQLite's `cannot store TEXT value in INTEGER column` error, and `crawl.schema_version` is unchanged

#### Scenario: Every table is strict
- **WHEN** a Crawl is created, and `PRAGMA table_list` is read on its file
- **THEN** every public table has `strict` = `1`

#### Scenario: Reference columns are declared
- **WHEN** `spider schema --limit 1000` runs
- **THEN** every column whose name ends with `_id` has a non-null `references`

#### Scenario: Index names start with their table
- **WHEN** `spider schema --limit 1000` runs
- **THEN** every index name starts with its table's name followed by `_`, and every index has a non-empty `description`

#### Scenario: Derived and later columns may hold NULL
- **WHEN** `spider schema --limit 1000` runs
- **THEN** every column whose description starts with `Derived: ` or matches `^Filled from v[0-9]+\.[0-9]+\. ` has `nullable` `true`

### Requirement: Unmeasured values are NULL

**In short:** a value that was not measured or does not apply is NULL, never `0` or an empty string.

A value that was not measured, or that does not apply, SHALL be stored as NULL. It SHALL never be stored as `0` or as an empty string. `0` SHALL mean a measured zero, and an empty string SHALL mean a value that is present but empty. A column that a later release measures SHALL be NULL in every row until then, and a derived column SHALL be NULL until its post-crawl pass has run.

#### Scenario: A running Crawl has no completion time
- **WHEN** the `crawl` row of a running Crawl is read
- **THEN** `completed_at` is NULL

#### Scenario: No settings file
- **WHEN** the `crawl` row of a Crawl created in a Workspace without `spider.toml` is read
- **THEN** `settings_file` is NULL

### Requirement: Crawl store diagnostics

**In short:** the crawl store's error and warning codes are declared with fixed levels and exit codes, so `spider commands` lists them.

This change's diagnostic codes SHALL be declared in the registry of `010-add-workspace-and-cli-contract`, with these levels and exit codes, so `spider commands` lists them:

| Code | Level | Exit code |
|---|---|---|
| `no_crawls`, `crawl_not_found` | error | 4 |
| `crawl_busy` | error | 5 |
| `crawl_file_invalid`, `crawl_schema_too_new` | error | 6 |
| `crawl_not_writable` | error | 7 |
| `unknown_table` | error | 2 |
| `store_wal_unavailable` | warning | none |

#### Scenario: Store codes are self-described
- **WHEN** `spider commands` runs
- **THEN** its `diagnostics` give these exit codes:
  - `no_crawls` 4, `crawl_not_found` 4
  - `crawl_busy` 5
  - `crawl_file_invalid` 6, `crawl_schema_too_new` 6
  - `crawl_not_writable` 7
  - `unknown_table` 2
  - `store_wal_unavailable` null

### Requirement: Submitting units with their outcome at the commit

**In short:** a caller can submit a unit without waiting, and gets a Future that settles only when the unit is committed or fails.

A caller SHALL be able to submit a unit without waiting for it to run. Submitting returns a Future for that unit, which is:
- resolved with the unit's result after the commit that holds the unit, never before it
- failed with the unit's error when the unit fails
- failed with the commit's error when the commit that holds the unit fails. Every Future of that commit's units fails with it, the writer then ends, and a unit submitted afterwards fails at once with the error that the writer is closed.

Submitted units follow the order, atomicity and commit rules of the transactional writer, in one order with the units whose callers wait for them.

**Window:** at most 2,000 submitted units SHALL be unresolved at once. A submit beyond that SHALL wait until a commit resolves some of them. A submit from an event loop SHALL wait without blocking the loop, and its Future SHALL be completed on that loop. A submit that waits for room when the writer ends SHALL fail with the error that the writer is closed.

**Cancelling:** cancelling a submitted unit's Future SHALL NOT withdraw the unit. The unit runs and is committed as if nothing had been cancelled, the writer goes on, and the unit's window slot is freed at its commit. Cancelling the Future of a submit from an event loop only drops the outcome.

#### Scenario: A submitted unit waits for its commit
- **WHEN** 3 units that each insert one Seed are submitted, a fourth unit that counts the rows of `seeds` then runs and returns `3`, the clock has not moved, and there has been no flush
- **THEN** none of the 3 Futures is done

#### Scenario: A flush resolves the submitted units
- **WHEN** 3 units are submitted that insert the Seeds at positions 1, 2 and 3 and return their positions, and a flush is requested
- **THEN** as soon as the flush returns, the 3 Futures hold `1`, `2` and `3`, and a separate reader sees 3 rows in `seeds`

#### Scenario: A failing submitted unit fails its Future
- **WHEN** a submitted unit raises `ValueError("bad")`, and a flush is requested
- **THEN** its Future fails with `ValueError("bad")`

#### Scenario: A replay commit resolves the units before a failing one
- **WHEN** 3 submitted units insert the Seeds at positions 1, 2 and 3, a fourth submitted unit raises `ValueError("bad")`, the clock has not moved, and there has been no flush
- **THEN** the Futures of the first 3 units are resolved

#### Scenario: A failed commit fails every Future of its batch
- **WHEN** 2 submitted units insert the Seeds at positions 1 and 2, a third submitted unit writes a row that breaks a foreign key checked only at the commit, and a flush is requested
- **THEN** each of the 3 Futures fails with SQLite's `FOREIGN KEY constraint failed` error, and a unit submitted afterwards fails at once with `CrawlWriterClosedError("The crawl writer is closed.")`

#### Scenario: A full window holds the next submit
- **WHEN** the writer is held inside the first of 2,000 submitted units, another thread then submits one more unit, and the held unit is released
- **THEN** that submit returns only after the writer's first commit

#### Scenario: A unit submitted from an event loop is resolved at its commit
- **WHEN** on an event loop a unit that inserts one Seed and returns `1` is submitted, and the writer is then flushed
- **THEN** awaiting the unit's Future on that loop returns `1`

#### Scenario: Cancelling a submitted unit's Future does not withdraw it
- **WHEN** a unit that inserts the Seed at position 1 is submitted, its Future is cancelled before any commit, a second unit that inserts the Seed at position 2 is submitted, and a flush is requested
- **THEN** cancelling returned `False`, a separate reader sees the positions 1 and 2 in `seeds`, and the second unit's Future holds its result

### Requirement: The writer's connection settings

**In short:** the writer's connection uses fixed memory and cache settings, while creating and reading a crawl file keep SQLite's defaults.

The writer's connection SHALL keep temporary tables and indexes in memory, and SHALL use a page cache of 64 MiB. In `wal` mode it SHALL also use memory-mapped I/O for up to 256 MiB of the crawl file; in `delete` mode it SHALL use none. No setting changes these values. Creating a crawl file and reading it SHALL keep SQLite's defaults. The durability scenarios of the transactional writer SHALL hold with them, on Windows too.

#### Scenario: The writer's connection settings in WAL mode
- **WHEN** a unit of the writer of a crawl file in `wal` mode reads `PRAGMA temp_store`, `PRAGMA cache_size` and `PRAGMA mmap_size`
- **THEN** they are `2`, `-65536` and `268435456`

#### Scenario: The writer's connection settings in rollback-journal mode
- **WHEN** a unit of the writer of a crawl file in `delete` mode reads `PRAGMA temp_store`, `PRAGMA cache_size` and `PRAGMA mmap_size`
- **THEN** they are `2`, `-65536` and `0`

#### Scenario: A reader keeps SQLite's defaults
- **WHEN** a reader of a crawl file reads `PRAGMA temp_store`, `PRAGMA cache_size` and `PRAGMA mmap_size`
- **THEN** they are the values that a plain SQLite connection to the same file reads
