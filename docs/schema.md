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

Every public table and column follows these conventions:
- **Names:** lowercase snake_case. Table names are plural nouns, except the one-row `crawl`.
- **Descriptions:** every table and every column has one.
- **Timestamps:** TEXT in the form `YYYY-MM-DDTHH:MM:SS.sssZ`, in UTC, with the format `timestamp`. They sort as text.
- **Booleans:** INTEGER `0` or `1`, with the format `boolean`.
- **JSON:** TEXT holding valid JSON, with the format `json`, only for recorded inputs and for lists without a fixed shape. A value that queries filter, sort or count by is a column of its own.
- **Enumerations:** TEXT whose allowed values are lowercase snake_case, listed under Values.
- **Measured quantities:** the column name ends with its unit: `_ms`, `_bytes`, `_px` or `_pct`. Each column has one meaning, so two different measures, such as two hashes or two sizes, are two distinctly named columns.
- **Order:** a table whose rows have an order carries it in an INTEGER column that grows in insert order. List rows in order by that column, never by a timestamp.
- **Counts** are derived from the tables that hold the rows they count. No table stores them.
- **Not measured is NULL.** A value that was not measured, or that does not apply, is NULL, never `0` or an empty string. `0` is a measured zero, and an empty string is a value that is present but empty.

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
