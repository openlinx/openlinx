## MODIFIED Requirements

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

### Requirement: Listing the schema with spider schema

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

A value that was not measured, or that does not apply, SHALL be stored as NULL. It SHALL never be stored as `0` or as an empty string. `0` SHALL mean a measured zero, and an empty string SHALL mean a value that is present but empty. A column that a later release measures SHALL be NULL in every row until then, and a derived column SHALL be NULL until its post-crawl pass has run.

#### Scenario: A running Crawl has no completion time
- **WHEN** the `crawl` row of a running Crawl is read
- **THEN** `completed_at` is NULL

#### Scenario: No settings file
- **WHEN** the `crawl` row of a Crawl created in a Workspace without `spider.toml` is read
- **THEN** `settings_file` is NULL
