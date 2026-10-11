# The crawl file schema

Every Crawl is one SQLite file, and its tables are a public, versioned contract ([ADR-0002](adr/0002-sqlite-crawl-store-public-schema.md)): agents and people may query them directly with read-only SQL. This page is the reference for those tables. Terms follow [CONTEXT.md](../CONTEXT.md).

This page is written by hand, for people and agents. A test compares it with the schema the tool declares, so the two cannot drift apart. Where crawl files live and how they are written is in [crawl-store.md](crawl-store.md).

## How to read a table section

Each table has a section headed ``## Table `<name>` ``, with a description and one row per column, in table order:

| Heading | Meaning |
|---|---|
| Column | the column name |
| Type | the SQLite type: `INTEGER`, `REAL`, `TEXT` or `BLOB` |
| Null | `yes` when the column may hold NULL, `no` when it may not |
| Key | `PK` for the primary key, ``→ `<table>.<column>` `` for a reference to another table, or empty |
| Format | `timestamp`, `boolean` or `json` when the column holds one of those, otherwise empty |
| Values | the allowed values of an enumeration, otherwise empty |
| Description | what the column holds |

Tables are listed in the order of the change that added them, and within a change in the order it added them.

## Conventions

Every public table, column and index follows the conventions of [ADR-0005](adr/0005-crawl-file-schema-conventions.md), which gives all the naming rules and their reasons. The file enforces the ones it can, and tests over `spider schema` check most of the others:
- **STRICT tables:** every table is `STRICT`, so a column's type is `INTEGER`, `REAL`, `TEXT` or `BLOB`, and the file refuses a value of another type. Reading a crawl file needs SQLite 3.37 or later.
- **Names:** lowercase snake_case. Table names are plural nouns, except the one-row `crawl`.
- **Descriptions:** every table, column and index has one. Two prefixes mark a column that the Crawl itself does not write:
  - `Derived: `: only a post-crawl pass writes it, and it is NULL until the pass has run.
  - `Filled from v<major>.<minor>. `: a later release fills it, and it is NULL in every row until then.
- **Keys and references:**
  - An entity's own key is `id`, INTEGER. Only the public identifiers that a user types, the crawl id and Rule ids, are TEXT. A table with a natural key uses it.
  - A column that refers to another table is named `<table singular>_id`, with a role prefix when a table refers to the same table twice, such as `source_url_id` and `target_url_id`. It is declared as a foreign key.
- **Timestamps:** TEXT in the form `YYYY-MM-DDTHH:MM:SS.sssZ`, in UTC, with the format `timestamp`, in a column whose name ends with `_at`. They sort as text. A header's raw value keeps the header's name and its text.
- **Booleans:** INTEGER `0` or `1`, with the format `boolean`. The file refuses any other value, through a CHECK named `<table>_<column>_flag`. The name reads as yes or no, such as `is_*` or `has_*`, and is never negated.
- **JSON:** TEXT holding valid JSON, with the format `json`, only for recorded inputs and for lists without a fixed shape. A value that queries filter, sort or count by is a column of its own.
- **Enumerations:** TEXT whose allowed values are lowercase snake_case, listed under Values. The file refuses any other value, through a CHECK named `<table>_<column>_values`. Values that a later release adds are listed from v0.1, and one enumeration has one value set in every table that holds it.
- **Errors:** an error is a code column whose values are listed, and its text is in a column named `<code column>_message`. A code is never a prefix inside free text.
- **Measured quantities:** the column name ends with its unit: `_ms`, `_seconds`, `_bytes`, `_px` or `_pct` (a share from 0 to 100). A count ends with `_count`. Each column has one meaning, so two different measures, such as two hashes or two sizes, are two distinctly named columns. A column named after a Screaming Frog column keeps that name.
- **Indexes:** each is named `<table>_<columns>`, and its description names the query it serves. An index is built while the Crawl writes, never after it, so its queries are fast on a running Crawl too.
- **Order:** a table whose rows have an order carries it in an INTEGER column that grows in insert order. List rows in order by that column, never by a timestamp.
- **Counts:** no count or statistic is written while the Crawl runs. Counts are derived from the tables that hold the rows they count. A derived value over the stored rows, such as a score, is stored only by a post-crawl pass, in a `Derived: ` column.
- **Not measured is NULL.** A value that was not measured, or that does not apply, is NULL, never `0` or an empty string. `0` is a measured zero, and an empty string is a value that is present but empty. A later or derived column is NULL until it is filled.

## How to add a table

A change that stores new data adds its tables and columns in the slice whose scenario first needs them:
1. **Declare it** with `public_table(name, *columns, comment=..., change=<n>)` in `spider.store.schema`, the only definition of the schema, with the change's number as `change`. It makes the table `STRICT` and adds the CHECKs of its enumerations and flags, so no CHECK is written by hand.
   - Give every column a `comment`, and use the shared column types for timestamps (`Timestamp`), JSON (`Json`) and booleans (`Flag`).
   - Declare a real number with `sqlalchemy.REAL`: `Float` and `Double` declare `FLOAT` and `DOUBLE`, which STRICT refuses.
   - Read an enumeration's `values` from the `Literal` the code uses.
   - Declare each index with `info={"description": ...}`, naming the query it serves.
2. **Document it here, in the same commit:** a ``## Table `<name>` `` section, placed in change order, with the same description and one row per column. The contract test compares this page with `spider schema --limit 1000`, so it is never red between commits.
3. **Follow the [conventions](#conventions).** Tests over `spider schema` check names, descriptions, types, booleans and enumeration values for every table, including new ones.
4. **No migration before v0.1.** Until the first release the schema is not yet public: a change edits the declared tables directly, and `schema_version` stays `1`. From v0.1 on, a schema change adds 1 to `schema_version` and brings a migration, with a test from every published schema version.

A table whose name starts with `_` is internal: it is left out of `spider schema` and of this page.

## Table `crawl`

The Crawl's metadata, in exactly one row.

| Column | Type | Null | Key | Format | Values | Description |
|---|---|---|---|---|---|---|
| `id` | TEXT | no | PK | | | The crawl id. |
| `crawl_mode` | TEXT | no | | | `spider`, `list`, `sitemap` | How the Crawl finds URLs. |
| `section_crawl` | INTEGER | no | | `boolean` | | 1 for a Section Crawl, whose Scope is one part of a site, otherwise 0. |
| `state` | TEXT | no | | | `running`, `stopped`, `completed`, `failed`, `interrupted` | The Crawl State. |
| `started_at` | TEXT | no | | `timestamp` | | When the Crawl started. |
| `completed_at` | TEXT | yes | | `timestamp` | | When the state became completed; NULL in every other state. |
| `command_argv` | TEXT | no | | `json` | | The command line as an array that starts with the command name, secrets redacted. |
| `cwd` | TEXT | no | | | | The absolute folder the Command ran in. |
| `settings_file` | TEXT | yes | | | | The absolute path of the settings file that was read, or NULL without one. |
| `config` | TEXT | no | | `json` | | The resolved settings as an object of tables and keys, secrets redacted. |
| `tool_version` | TEXT | no | | | | The version of the tool that created the Crawl. |
| `schema_version` | INTEGER | no | | | | The schema version of this file, also stored as SQLite's user_version. |
| `journal_mode` | TEXT | no | | | `wal`, `delete` | The SQLite journal mode the file was created with. |
| `python_version` | TEXT | no | | | | The Python version that created the Crawl. |
| `platform` | TEXT | no | | | | The operating system that created the Crawl, as Python describes it. |

## Table `seeds`

The Seeds the Crawl started from, in the order they were given.

| Column | Type | Null | Key | Format | Values | Description |
|---|---|---|---|---|---|---|
| `position` | INTEGER | no | PK | | | The 1-based order in which the Seed was given. |
| `url` | TEXT | no | | | | The Seed URL as given. |
