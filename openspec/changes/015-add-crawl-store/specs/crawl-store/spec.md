## Purpose

Defines how each Crawl is stored as one self-contained SQLite file with a public, versioned schema. It covers:
- crawl ids, and selecting a Crawl with `--crawl`
- crawl metadata and the redaction of secrets
- the transactional writer and the one-writer claim, with its two exceptions
- the journal mode, concurrent reading, and schema upgrades
- `spider schema` and the conventions every table follows

Conventions used in the scenarios:
- `H` is the absolute path of the home folder.
- Paths are written with `/`, and Windows uses `\`.
- "A Command that reads a Crawl" is any Command with the `--crawl` option. Until `050-add-query-and-segments` adds the real ones, an example Command stands in, and it reports the id of the Crawl it read.

## ADDED Requirements

### Requirement: One file per Crawl

Each Crawl SHALL be stored as one SQLite file, `<data folder>/crawls/<crawl-id>.sqlite`. The file SHALL be self-contained: a copy SHALL open as the same Crawl from any folder when its path is given to `--crawl`.

#### Scenario: Location of a crawl file
- **WHEN** a Crawl with the id `20260927-140312-k3f9` is created in the local Workspace `H/work/shop`
- **THEN** the file `H/work/shop/.spider/crawls/20260927-140312-k3f9.sqlite` exists

#### Scenario: A copied file opens by its path
- **WHEN** the crawl file of the Crawl `20260927-140312-k3f9` is copied to `H/work/copy/c.sqlite`, and the Crawl `H/work/copy/c.sqlite` is opened
- **THEN** its `crawl.id` is `"20260927-140312-k3f9"`

### Requirement: Crawl ids

A crawl id SHALL consist of:
- the Crawl's UTC start time, formatted `YYYYMMDD-HHMMSS`
- a hyphen
- 4 random characters from `0123456789abcdefghjkmnpqrstvwxyz`

An id SHALL count as taken in a Workspace when any of `<id>.sqlite`, `<id>.lock` or `<id>.log` exists in its `crawls/` folder. A new id SHALL never be a taken one: new random characters SHALL be drawn until it is not.

A caller MAY choose the id of the Crawl it creates. That is usually an id it reserved first, by creating `<id>.lock` or `<id>.log`.
- Creating a Crawl with a chosen id SHALL succeed when `<id>.sqlite` does not exist.
- It SHALL fail with `crawl_id_taken` when `<id>.sqlite` exists.
- It SHALL fail with `invalid_value` when the id does not have the form above.

#### Scenario: Id from the start time
- **WHEN** a Crawl is created at `2026-09-27T14:03:12.345Z`, and the random source yields `k3f9`
- **THEN** its id is `20260927-140312-k3f9`

#### Scenario: An id with a crawl file is taken
- **WHEN** `20260927-140312-k3f9.sqlite` exists, and a Crawl is created at `2026-09-27T14:03:12.900Z` while the random source yields `k3f9` and then `m2p7`
- **THEN** the new Crawl's id is `20260927-140312-m2p7`

#### Scenario: An id with a log file is taken
- **WHEN** `20260927-140312-k3f9.log` exists, and a Crawl is created at `2026-09-27T14:03:12.900Z` while the random source yields `k3f9` and then `m2p7`
- **THEN** the new Crawl's id is `20260927-140312-m2p7`

#### Scenario: An id with a lock file is taken
- **WHEN** `20260927-140312-k3f9.lock` exists, and a Crawl is created at `2026-09-27T14:03:12.900Z` while the random source yields `k3f9` and then `m2p7`
- **THEN** the new Crawl's id is `20260927-140312-m2p7`

#### Scenario: Character set
- **WHEN** ids are created with the system random source for any UTC start time from `2000-01-01T00:00:00.000Z` to `2099-12-31T23:59:59.999Z`
- **THEN** every id matches `^[0-9]{8}-[0-9]{6}-[0-9a-hjkmnp-tv-z]{4}$`

#### Scenario: A chosen id is used
- **WHEN** a Crawl is created with the chosen id `20260927-140312-k3f9`, and only `20260927-140312-k3f9.log` exists
- **THEN** the file `20260927-140312-k3f9.sqlite` exists in the Workspace's `crawls/` folder

#### Scenario: A chosen id that has a crawl file is refused
- **WHEN** a Crawl is created with the chosen id `20260927-140312-k3f9`, and `20260927-140312-k3f9.sqlite` exists
- **THEN** creation fails with the error code `crawl_id_taken`

#### Scenario: A malformed chosen id is refused
- **WHEN** a Crawl is created with the chosen id `crawl-1`
- **THEN** creation fails with the error code `invalid_value`

### Requirement: Storing a Crawl creates the data folder

Creating a Crawl SHALL create the Workspace's data folder, its `.gitignore` (as `010-add-workspace-and-cli-contract` defines it) and its `crawls/` folder when they are missing. It SHALL NOT create `spider.toml`. When the data folder cannot be created or written, creating the Crawl SHALL fail with `workspace_not_writable`.

#### Scenario: First Crawl in the global Workspace
- **WHEN** a Crawl with the id `20260927-140312-k3f9` is created in the global Workspace, and `H/.spider` does not exist
- **THEN** the file `H/.spider/crawls/20260927-140312-k3f9.sqlite` exists

#### Scenario: No settings file is created by storing a Crawl
- **WHEN** a Crawl is created in the local Workspace `H/work/shop`, which has `.spider/` but no `spider.toml`
- **THEN** `H/work/shop/spider.toml` does not exist

#### Scenario: Unwritable data folder
- **WHEN** a Crawl is created in the global Workspace, and `H/.spider` is a file
- **THEN** creation fails with the error code `workspace_not_writable`

### Requirement: Selecting a Crawl with --crawl

A Command that reads a Crawl SHALL take the global flag `--crawl` with one of these values:
- `latest`, the default
- a crawl id
- the path of a crawl file: a value that contains a path separator or ends in `.sqlite`

`latest` SHALL be the Crawl that started most recently, whatever its state. The start time is taken from the id; among ids with the same second, it is taken from `crawl.started_at`.

Only files named `<id>.sqlite` SHALL count as Crawls; a reservation alone is not one. Selecting a Crawl SHALL NOT create any file or folder.

Failures SHALL use these error codes:

| Code | When |
|---|---|
| `no_crawls` | the Workspace has no Crawl; the hint names `spider crawl` |
| `crawl_not_found` | no Crawl has the given id |
| `crawl_file_invalid` | the selected file is not a readable crawl file |
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

#### Scenario: A reservation is not a Crawl
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

### Requirement: Crawl metadata

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
- **WHEN** a List-mode Crawl is created with the Seeds `https://example.com/b` and then `https://example.com/a`
- **THEN** `seeds` holds exactly the rows `(1, "https://example.com/b")` and `(2, "https://example.com/a")`

#### Scenario: Version stamp
- **WHEN** a Crawl is created
- **THEN** `crawl.tool_version` equals the `version` in `pyproject.toml`, and `crawl.schema_version` is `1`

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

`crawl.state` SHALL hold one of these Crawl States, and a new Crawl SHALL start as `running`:

| State | Meaning |
|---|---|
| `running` | a process is crawling, or was when it last wrote the file |
| `stopped` | paused before its end; it can be resumed |
| `completed` | it ran to the end |
| `failed` | it could not continue; it can be resumed |
| `interrupted` | its process died without recording an end; it can be resumed |

#### Scenario: State values are documented
- **WHEN** `spider schema crawl` runs
- **THEN** the `state` column has `"values":["running","stopped","completed","failed","interrupted"]`

### Requirement: Redacting secrets

When a Crawl is created, the secrets in its recorded command line (`crawl.command_argv`) and its recorded config (`crawl.config`) SHALL be replaced by `***`. There are three forms:
- **A whole secret value,** such as the value of `--auth`.
- **The value of a sensitive header,** keeping the header's name: `Authorization: ***`. The sensitive headers are `Cookie`, and every header whose name contains `auth`, `token`, `secret`, `key` or `password`, ignoring case.
- **The password in a URL's user information,** keeping the user name: `http://ann:***@proxy.test:8080`.

Redaction SHALL cover both the `--flag value` and the `--flag=value` forms. The Command that owns a flag or setting declares whether it is secret, and in which form. No part of the crawl file SHALL contain a redacted value.

#### Scenario: Secret flag with a separate value
- **WHEN** the command line `["spider","crawl","https://example.com/","--auth","ann:s3cret"]` is redacted, with `--auth` a whole secret
- **THEN** the result is `["spider","crawl","https://example.com/","--auth","***"]`

#### Scenario: Secret flag with a joined value
- **WHEN** the command line `["spider","crawl","https://example.com/","--auth=ann:s3cret"]` is redacted, with `--auth` a whole secret
- **THEN** the result is `["spider","crawl","https://example.com/","--auth=***"]`

#### Scenario: A sensitive header keeps its name
- **WHEN** the command line `["spider","crawl","https://example.com/","--header","Authorization: Bearer abc123"]` is redacted, with `--header` a header secret
- **THEN** the result is `["spider","crawl","https://example.com/","--header","Authorization: ***"]`

#### Scenario: Cookie header
- **WHEN** the command line `["spider","crawl","https://example.com/","--header","Cookie: sid=abc"]` is redacted, with `--header` a header secret
- **THEN** the result is `["spider","crawl","https://example.com/","--header","Cookie: ***"]`

#### Scenario: Other headers are kept
- **WHEN** the command line `["spider","crawl","https://example.com/","--header","Accept-Language: de"]` is redacted, with `--header` a header secret
- **THEN** the result is `["spider","crawl","https://example.com/","--header","Accept-Language: de"]`

#### Scenario: Proxy password
- **WHEN** the command line `["spider","crawl","https://example.com/","--proxy","http://ann:s3cret@proxy.test:8080"]` is redacted, with `--proxy` a URL secret
- **THEN** the result is `["spider","crawl","https://example.com/","--proxy","http://ann:***@proxy.test:8080"]`

#### Scenario: Secret setting
- **WHEN** the config `{"crawl":{"auth":"ann:s3cret"}}` is redacted, with `crawl.auth` a whole secret
- **THEN** the result is `{"crawl":{"auth":"***"}}`

#### Scenario: Header setting
- **WHEN** the config `{"crawl":{"header":["Authorization: Bearer abc123","Accept-Language: de"]}}` is redacted, with `crawl.header` a header secret
- **THEN** the result is `{"crawl":{"header":["Authorization: ***","Accept-Language: de"]}}`

#### Scenario: The secret is nowhere in the file
- **WHEN** a Crawl is created with the command line `["spider","crawl","https://example.com/","--auth","ann:s3cret"]`, with `--auth` a whole secret, and its writer is closed
- **THEN** the bytes of the crawl file do not contain `s3cret`

### Requirement: Transactional writer

Crawl data SHALL be written only through the Crawl's transactional writer. Callers submit units of work, and each unit may insert, update and read rows.
- **Order:** units SHALL run one at a time, in the order they were submitted. Each unit runs in the writer's open transaction and sees the effects of every unit before it.
- **Atomic units:** a unit that fails SHALL leave no change, and its error SHALL be raised to its caller. The other units SHALL be unaffected.
- **Commits:** the writer SHALL commit its open transaction when any of these happens:
  - 500 units have run since the last commit
  - 1 second has passed since the first unit after the last commit
  - a caller asks for a flush
  - the writer is closed
- **Durability:** a unit whose transaction was committed SHALL survive the writing process being killed. A kill SHALL lose at most the units that ran after the last commit.

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

#### Scenario: Units wait for the batch
- **WHEN** 499 units that each insert one Seed have run, the clock has not moved, and there has been no flush
- **THEN** a separate reader sees 0 rows in `seeds`

#### Scenario: The 500th unit commits the batch
- **WHEN** 500 units that each insert one Seed have run, and the clock has not moved
- **THEN** a separate reader sees 500 rows in `seeds`

#### Scenario: The timer commits
- **WHEN** 3 units that each insert one Seed have run, and the clock then moves forward by 1 second
- **THEN** a separate reader sees 3 rows in `seeds`

#### Scenario: A flush commits at once
- **WHEN** 3 units that each insert one Seed have run, and a flush is requested
- **THEN** a separate reader sees 3 rows in `seeds` as soon as the flush returns

#### Scenario: Closing commits everything
- **WHEN** 1,000 units that each insert one Seed have run, and the writer is closed at once
- **THEN** a separate reader sees 1,000 rows in `seeds`

#### Scenario: A killed writer leaves a sound file
- **WHEN** a process runs 3 units, flushes, and is then killed: SIGKILL on Linux and macOS, TerminateProcess on Windows
- **THEN** `PRAGMA integrity_check` on the crawl file returns `ok`

#### Scenario: A killed writer keeps committed units
- **WHEN** a process runs 3 units that each insert one Seed, flushes, and is then killed: SIGKILL on Linux and macOS, TerminateProcess on Windows
- **THEN** a reader sees 3 rows in `seeds`

#### Scenario: A killed writer loses uncommitted units
- **WHEN** a process runs 3 units that each insert one Seed, and is killed less than a second later without a flush
- **THEN** a reader sees 0 rows in `seeds`

### Requirement: One writing process per Crawl

At most one process at a time SHALL hold a Crawl's writer claim, which is needed to write its data. That covers the Crawl itself, a resume, and a schema upgrade.

Another process that tries to take the claim SHALL fail with `crawl_locked` without changing the file. The claim SHALL end when the writing process ends, even when it is killed.

Reading SHALL NOT be blocked by the claim.

#### Scenario: A second writer is refused
- **WHEN** process A holds the writer claim of the Crawl `20260927-140312-k3f9`, and process B tries to take it
- **THEN** process B fails with the error code `crawl_locked`

#### Scenario: A killed writer releases the Crawl
- **WHEN** the process holding the writer claim of the Crawl `20260927-140312-k3f9` is killed, and another process then takes the claim
- **THEN** it succeeds

#### Scenario: Readers are not blocked
- **WHEN** process A holds the writer claim of the Crawl `20260927-140312-k3f9`, and process B reads `crawl.state`
- **THEN** process B reads `"running"`

### Requirement: Control writes by other processes

A process that does not hold a Crawl's writer claim SHALL be able to write rows of the Crawl's control tables, which are the tables the schema marks as control tables. It writes them in short transactions that wait up to 5 seconds for SQLite's locks, even while another process writes the Crawl.

Through such a control write it SHALL NOT be able to change any other table.

This change defines no control table. `060-add-crawl-control` adds `control_requests`.

#### Scenario: A control row is written while the Crawl is written
- **WHEN** process A holds the writer claim of a Crawl that has a control table, and process B inserts a row into that control table
- **THEN** the row is committed

#### Scenario: A control write cannot change Crawl data
- **WHEN** a control write tries to insert a row into `seeds`
- **THEN** it fails with a not-authorized error, and `seeds` is unchanged

### Requirement: Recording a dead Crawl as interrupted

When a process finds a Crawl whose state is `running` but whose writer claim no process holds, it SHALL be able to record the state `interrupted`. It takes the writer claim, sets `crawl.state` to `interrupted`, and releases the claim.

A Crawl whose claim is held SHALL be left unchanged. When the crawl file cannot be written, nothing SHALL be recorded, and the check SHALL still report that no process is writing the Crawl.

#### Scenario: A dead Crawl is recorded as interrupted
- **WHEN** the process writing a Crawl in the state `running` is killed, and another process checks the Crawl
- **THEN** `crawl.state` is `"interrupted"`

#### Scenario: A live Crawl is left running
- **WHEN** a process holds the writer claim of a Crawl in the state `running`, and another process checks the Crawl
- **THEN** `crawl.state` is still `"running"`

#### Scenario: A read-only file records nothing
- **WHEN** the process writing a Crawl in the state `running` is killed, its crawl file then gets the read-only file attribute, and another process checks the Crawl
- **THEN** `crawl.state` is still `"running"`

### Requirement: Journal mode on local and network locations

A new crawl file SHALL use the journal mode chosen from the setting `store.journal_mode` and the file's location:

| Setting | Local location | Network location |
|---|---|---|
| `"auto"` (the default) | `wal` | `delete` (rollback journal), with the warning `store_wal_unavailable` |
| `"wal"` | `wal` | `wal`, with no warning |
| `"delete"` | `delete` | `delete`, with no warning |

A network location is any of:
- a UNC path
- a Windows drive whose type is remote
- a path whose filesystem type is `nfs`, `nfs4`, `cifs`, `smb3`, `smbfs`, `afpfs`, `webdav`, `9p` or `fuse.sshfs`

`crawl.journal_mode` SHALL record the mode used.

#### Scenario: UNC path
- **WHEN** the location `\\fileserver\share\site\.spider` is classified
- **THEN** it is a network location

#### Scenario: Mapped network drive
- **WHEN** the location `Z:\site\.spider` is classified, and the mount table reports drive `Z:` as remote
- **THEN** it is a network location

#### Scenario: Local drive
- **WHEN** the location `C:\site\.spider` is classified, and the mount table reports drive `C:` as fixed
- **THEN** it is a local location

#### Scenario: SMB share on macOS
- **WHEN** the location `/Volumes/share/site/.spider` is classified, and the mount table reports its mount point `/Volumes/share` with the filesystem type `smbfs`
- **THEN** it is a network location

#### Scenario: Local filesystem on Linux
- **WHEN** the location `/home/ann/site/.spider` is classified, and the mount table reports its mount point `/` with the filesystem type `ext4`
- **THEN** it is a local location

#### Scenario: Automatic mode on a network location
- **WHEN** the journal mode is chosen for `"auto"` and a network location
- **THEN** it is `delete`, with the warning `store_wal_unavailable`

#### Scenario: Forced WAL on a network location
- **WHEN** the journal mode is chosen for `"wal"` and a network location
- **THEN** it is `wal`, with no warning

#### Scenario: Forced rollback journal on a local location
- **WHEN** the journal mode is chosen for `"delete"` and a local location
- **THEN** it is `delete`, with no warning

#### Scenario: Local disk
- **WHEN** a Crawl is created in a Workspace inside the test's temporary folder on the local disk
- **THEN** `crawl.journal_mode` is `"wal"`

#### Scenario: Crawl on a UNC path on Windows
- **WHEN** on Windows a Crawl is created in a Workspace reached through the UNC path `\\localhost\C$\…` of the test's temporary folder
- **THEN** `crawl.journal_mode` is `"delete"`, and the warning `store_wal_unavailable` is reported with `details.path` equal to the Workspace's data folder

### Requirement: The store setting

This change SHALL register the `spider.toml` table `[store]`, with the setting `journal_mode`: `"auto"`, `"wal"` or `"delete"`, with the default `"auto"`. It follows the settings rules of `010-add-workspace-and-cli-contract`.

#### Scenario: The store setting in the template
- **WHEN** `spider init` runs in the empty folder `H/work/shop`
- **THEN** `H/work/shop/spider.toml` contains the line `[store]`, followed later by the line `# journal_mode = "auto"`

#### Scenario: An invalid store setting
- **WHEN** `spider init` runs in `H/work/shop`, whose `spider.toml` contains `[store]\njournal_mode = "fast"\n`
- **THEN** the exit code is 3, and the error has the code `settings_invalid` and `details.errors[0].key` `"store.journal_mode"`

### Requirement: Reading while a Crawl is written

In `wal` mode, a process SHALL be able to read a Crawl while another process writes it, and it SHALL see every committed row.

In `delete` mode, a reader that cannot read within 5 seconds because a write is in progress SHALL fail with `crawl_busy` instead of waiting longer.

#### Scenario: Reading during a write in WAL mode
- **WHEN** a writer process has committed 3 Seed rows and keeps holding the writer claim, and another process reads `seeds`
- **THEN** the reader sees 3 rows

#### Scenario: Busy in rollback-journal mode
- **WHEN** a crawl file in `delete` mode is held under an exclusive write lock for 8 seconds, and another process reads it during that time
- **THEN** the reader fails with the error code `crawl_busy`

### Requirement: Readers never change a crawl file

Commands that only read a Crawl SHALL open its file read-only. Reading SHALL leave the file's bytes unchanged. There are three exceptions:
- a schema upgrade
- a control write
- recording `interrupted`

Any attempt to write through a read-only handle SHALL fail.

#### Scenario: Bytes are unchanged by reading
- **WHEN** the metadata and Seeds of a completed Crawl are read
- **THEN** the SHA-256 of its crawl file is the same as before the read

#### Scenario: Writes through a reader fail
- **WHEN** `INSERT INTO seeds (position, url) VALUES (9, 'https://example.com/x')` is executed through a read-only handle
- **THEN** it fails with a read-only error

### Requirement: Crawl files are released after each operation

When an operation on a Crawl finishes, the process SHALL hold no open handle to the crawl file or its `-wal` and `-shm` files. This SHALL hold even when the process keeps running, as the MCP server does.

#### Scenario: Deleting after a read on Windows
- **WHEN** on Windows a process reads the metadata of a completed Crawl and then keeps running
- **THEN** another process can delete the crawl file

### Requirement: Older crawl files are upgraded when opened

When a crawl file with an older schema version is opened for any purpose, the tool SHALL first upgrade the file in place to its own schema version.

The upgrade SHALL:
- keep all of the file's data
- report the warning `crawl_migrated` with `details.from` and `details.to`
- be all-or-nothing
- be done by at most one process at a time

It SHALL fail without changing the file, with these codes:

| Code | When |
|---|---|
| `crawl_busy` | another process is writing the Crawl |
| `crawl_not_writable` | the file cannot be written |
| `crawl_migration_failed` | an upgrade step fails |

#### Scenario: Schema version after the upgrade
- **WHEN** a crawl file at schema version 1 is opened by a tool whose schema version is 2
- **THEN** `crawl.schema_version` is `2`

#### Scenario: SQLite user_version after the upgrade
- **WHEN** a crawl file at schema version 1 is opened by a tool whose schema version is 2
- **THEN** SQLite's `user_version` of the file is `2`

#### Scenario: Data survives the upgrade
- **WHEN** a crawl file at schema version 1, holding the Seed `(1, "https://example.com/")`, is opened by a tool whose schema version is 2
- **THEN** `seeds` holds exactly the row `(1, "https://example.com/")`

#### Scenario: Upgrade warning
- **WHEN** a crawl file at schema version 1 is opened by a tool whose schema version is 2
- **THEN** the warning `crawl_migrated` is reported with `"details":{"from":1,"to":2}`

#### Scenario: No upgrade while another process writes
- **WHEN** a crawl file at schema version 1 is being written by another process, and a tool whose schema version is 2 opens it
- **THEN** the open fails with the error code `crawl_busy`, and `crawl.schema_version` is still `1`

#### Scenario: Read-only file
- **WHEN** a crawl file at schema version 1 has the read-only file attribute, and a tool whose schema version is 2 opens it
- **THEN** the open fails with the error code `crawl_not_writable`

#### Scenario: Failed upgrade step
- **WHEN** a crawl file at schema version 1 is opened by a tool whose step from version 1 to 2 fails
- **THEN** the open fails with the error code `crawl_migration_failed`, and `crawl.schema_version` is still `1`

#### Scenario: Two processes open the same old file
- **WHEN** two processes of a tool whose schema version is 2 open the same crawl file at schema version 1 at the same time
- **THEN** both opens succeed, and `crawl.schema_version` is `2`

### Requirement: Newer or unknown crawl files are refused

A crawl file whose schema version is newer than the tool's SHALL be refused with `crawl_schema_too_new`:
- `details.file_schema_version` and `details.tool_schema_version` give the two versions
- the hint says to upgrade the tool

A crawl file whose schema revision the tool does not know SHALL be refused with `crawl_schema_unknown`. This happens, for example, with a file from a pre-release build.

In both cases the file SHALL NOT be changed.

#### Scenario: File from a newer tool
- **WHEN** a crawl file at schema version 99 is opened by a tool whose schema version is 1
- **THEN** the open fails with the error code `crawl_schema_too_new` and `"details":{"file_schema_version":99,"tool_schema_version":1}`

#### Scenario: A refused file is unchanged
- **WHEN** a crawl file at schema version 99 is opened by a tool whose schema version is 1
- **THEN** the SHA-256 of the crawl file is the same as before

#### Scenario: Unknown schema revision
- **WHEN** a crawl file at schema version 1 records the schema revision `deadbeef0000`, which the tool does not know
- **THEN** the open fails with the error code `crawl_schema_unknown`

### Requirement: Listing the schema with spider schema

`spider schema [TABLE]` SHALL be a list Command that follows the paging and output rules of `010-add-workspace-and-cli-contract`, with the formats `json`, `jsonl`, `table` and `csv`.
- Its JSON result SHALL start with the key `schema_version`, the tool's schema version, before `total`.
- Its items are the public tables. They are ordered by the number of the change that added them, and within a change in the order it added them. So `crawl` and `seeds` (from `015`) come first.
- With TABLE, it SHALL list only that table.

Each item SHALL have `name`, `kind` (`table` or `view`), `description` and `columns`. Each column, in table order, SHALL have:
- `name` and `description`
- `type`: `INTEGER`, `REAL`, `TEXT` or `BLOB`
- `nullable` and `primary_key`
- `references`: `<table>.<column>` or `null`
- `format`: `timestamp`, `boolean`, `json` or `null`
- `values`: the allowed values, or `null`

An unknown TABLE SHALL fail with `unknown_table`, whose `details.tables` lists the table names. Tables whose names start with `_` are internal and SHALL NOT be listed. The Command SHALL NOT need a Workspace.

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

#### Scenario: Unknown table
- **WHEN** `spider schema nosuch` runs
- **THEN** the exit code is 2, and the error has the code `unknown_table` and a `details.tables` that contains `"crawl"` and `"seeds"`

#### Scenario: Internal tables are hidden
- **WHEN** `spider schema --fields name --limit 1000` runs
- **THEN** no listed name starts with `_`

#### Scenario: No Workspace needed
- **WHEN** `spider schema` runs in `H/work/notes`, which is not a Workspace, while `H/.spider` does not exist
- **THEN** the exit code is 0

#### Scenario: Self-description of schema
- **WHEN** `spider commands` runs
- **THEN** the `schema` entry has `"output":"list"`, `"formats":["json","jsonl","table","csv"]` and `"fields":{"available":["name","kind","description","columns"],"default":["name","kind","description","columns"]}`

#### Scenario: Global flags of schema
- **WHEN** `spider commands` runs
- **THEN** the options of the `schema` entry include `--format`, `--no-bom` and `--output`, and do not include `--workspace` or `--crawl`

#### Scenario: Default limit of schema
- **WHEN** `spider commands` runs
- **THEN** the `--limit` option of the `schema` entry has `"type":"integer"`, `"default":50` and `"global":false`

### Requirement: Documented schema matches the store

`docs/schema.md` SHALL document every public table and column. For each one it SHALL give the same name, type, nullability, key, reference, format, values and description that `spider schema` reports. `spider schema` SHALL report nothing that `docs/schema.md` lacks.

#### Scenario: Documentation and store agree
- **WHEN** the output of `spider schema --limit 1000` is compared with the tables parsed from `docs/schema.md`
- **THEN** they are equal

### Requirement: Public schema conventions

Every public table and column SHALL follow these conventions:
- **Names:** lowercase snake_case. Table names are plural nouns, except the one-row `crawl`.
- **Descriptions:** every table and every column has a non-empty description.
- **Timestamps:** TEXT in the form `YYYY-MM-DDTHH:MM:SS.sssZ`, in UTC, with the format `timestamp`.
- **Booleans:** INTEGER `0` or `1`, with the format `boolean`.
- **JSON:** TEXT holding valid JSON, with the format `json`.
- **Enumerations:** TEXT whose allowed values are lowercase snake_case, listed in `values`.
- **Measured quantities:** the column name ends with its unit: `_ms`, `_bytes`, `_px` or `_pct`.

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

### Requirement: Unmeasured values are NULL

A value that was not measured, or that does not apply, SHALL be stored as NULL. It SHALL never be stored as `0` or as an empty string. `0` SHALL mean a measured zero, and an empty string SHALL mean a value that is present but empty.

#### Scenario: A running Crawl has no completion time
- **WHEN** the `crawl` row of a running Crawl is read
- **THEN** `completed_at` is NULL

#### Scenario: No settings file
- **WHEN** the `crawl` row of a Crawl created in a Workspace without `spider.toml` is read
- **THEN** `settings_file` is NULL

### Requirement: Crawl store diagnostics

This change's diagnostic codes SHALL be registered with these exit codes, and `spider commands` SHALL list them:

| Code | Level | Exit code |
|---|---|---|
| `no_crawls`, `crawl_not_found` | error | 4 |
| `crawl_id_taken`, `crawl_locked`, `crawl_busy` | error | 5 |
| `crawl_file_invalid`, `crawl_schema_too_new`, `crawl_schema_unknown`, `crawl_migration_failed` | error | 6 |
| `crawl_not_writable` | error | 7 |
| `unknown_table` | error | 2 |
| `store_wal_unavailable`, `crawl_migrated` | warning | none |

#### Scenario: Store codes are self-described
- **WHEN** `spider commands` runs
- **THEN** its `diagnostics` give these exit codes:
  - `crawl_not_found` 4
  - `crawl_id_taken` 5, `crawl_locked` 5
  - `crawl_schema_too_new` 6
  - `crawl_not_writable` 7
  - `unknown_table` 2
  - `store_wal_unavailable` null
