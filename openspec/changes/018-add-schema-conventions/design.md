## Context

- **What this change builds on:** `015-add-crawl-store` as built on its branch, and its archived `crawl-store` spec:
  - The public schema is declared once, in `spider.store.schema.metadata`, as SQLAlchemy Core tables (015 D6).
  - Each table carries `info={"change": n}` and a `comment`. Each column carries a `comment`, and an enumeration column carries `info={"values": [...]}`, read from the `Literal` the code uses.
  - The shared column types `Timestamp` and `Json` are `TypeDecorator`s over `Text`, and `Flag` is one over `Integer`. Each has a `format` class attribute.
  - `spider.services.schema.describe_schema()` builds the `spider schema` items from the declaration. It sets `references` to `None` for every column today, because no table has a foreign key yet.
  - `docs/schema.md` has one section per table. `tests/contract/test_schema.py` parses it and compares it with `spider schema --limit 1000`, and checks a new file through `PRAGMA table_info` and `PRAGMA foreign_key_list`.
  - SQLAlchemy is 2.1.3. Python's SQLite is 3.50.x (python.org 3.14) or 3.53.x (uv-managed).
- **The decisions it records:**
  - The user's four schema decisions of 2026-10-10 (inventory).
  - The blueprint outline of 2026-10-11 and the rulings on it (the user decided Q7, Q8, Q9 and Q14).
  - ADR-0005 holds the rules. This change makes the testable ones part of the spec.
- **Its place in the build order:** 015 → 017 → 018 → 020 (slice). `020` adds the first foreign key (`urls.found_on_url_id`) and the first secondary indexes (the unique `urls_url` and the partial frontier index `urls_crawl_depth_id`), both under these rules.

## Goals / Non-Goals

**Goals:**
- A file that refuses values outside its declared types, enumerations and flags.
- A schema description, a reference page and a contract test that cover keys, references, indexes and the derived and later columns, so later changes cannot drift from the rules.
- One place for the rules (ADR-0005), and their testable part in the spec.

**Non-Goals:**
- Any table beyond `crawl` and `seeds` (their owners add them).
- Migrations (015 D5).
- A runtime check of the SQLite version.

## Decisions

### D1. The rules live in ADR-0005; the spec holds what a test can check
- **ADR-0005** records:
  - the user's decisions (one blueprint, stored derived values, later columns as NULL, TEXT + CHECK enumerations)
  - indexes built during the Crawl
  - every Link occurrence as a row
  - STRICT tables
  - the 15 naming rules
- **The crawl-store spec** carries the rules a test can check over the declaration or a new file:
  - names, descriptions, types and STRICT
  - enumerations and flags refused by the file
  - references declared
  - index names and descriptions
  - derived and later columns nullable
- **The other rules** are the review's: time suffixes, units, flag wording, one value set per enumeration, URL text and errors. They need judgment about meaning.
- *Alternative:* everything in the spec. Rules about meaning cannot become literal scenarios. Rejected.

### D2. CHECKs come from the declaration
- **The source of each CHECK:** the declaration already says what is allowed.
  - A column with `info["values"]` gets `CHECK (<column> IN (...))`, or `<column> IS NULL OR …` when it is nullable.
  - A `Flag` column gets `CHECK (<column> IN (0, 1))`.
- **One helper in `spider.store.schema` adds them:** it runs over each table as the table is declared. Each change's tables call it, and nothing writes a CHECK by hand.
  - The constraints are named `<table>_<column>_values` and `<table>_<column>_flag`, so a failure names its column.
  - They live in the `MetaData`, so `create_all` emits them and the contract test sees them.
- **The scenarios prove it through the file:** a unit that writes `crawl.state = 'paused'` or `crawl.section_crawl = 2` fails with SQLite's error.
- *Alternative:* SQLAlchemy's `Enum` type with `create_constraint=True`. It declares the type `VARCHAR(n)`, which is not STRICT-legal, and it duplicates the `values` list. Rejected.
- *Alternative:* CHECKs written by hand per table. They drift from `values`. Rejected.

### D3. STRICT tables
- **Checked, as the ruling asked:** SQLAlchemy 2.1.3 renders `sqlite_strict=True` as `STRICT`, also together with `WITHOUT ROWID`. The shared types compile to their `impl` types: `Timestamp` and `Json` to `TEXT`, and `Flag` to `INTEGER`. `LargeBinary` compiles to `BLOB`.
- **The one trap:** `Float` and `Double` compile to `FLOAT` and `DOUBLE`, which STRICT refuses. A REAL column, such as 030's `average_words_per_sentence`, is declared with `sqlalchemy.REAL`. The convention "a column's type is `INTEGER`, `REAL`, `TEXT` or `BLOB`", checked over `spider schema`, catches any other type before a file is ever created.
- **How tables become STRICT:** the same declaration helper as D2 sets `sqlite_strict=True` on every public table. Checked by "Every table is strict" through `PRAGMA table_list`.
- **What it costs readers:** a STRICT table can be opened only by SQLite 3.37 or later (2021-11). Our own tool runs on 3.50 or later. `docs/schema.md` states the minimum for other tools, and `080`'s `doctor` reports the SQLite version.
- *Alternative:* CHECKs on `typeof()` for every column. They are verbose and duplicate what STRICT does. Rejected.

### D4. References and indexes in the schema description
- **`references`:** for a column with a declared foreign key, `<table>.<column>` of the key's target, read from `column.foreign_keys`. Otherwise `null`.
- **Each table item gains `indexes`,** read from `table.indexes`:
  - It lists only secondary indexes, in name order, without the indexes SQLite makes for primary keys.
  - Each index gives `name`, `description` (the index's `info["description"]`, which names the query it serves), `columns`, `unique`, and `where` (the compiled condition of a partial index, or `null`).
  - `spider schema` lists `indexes` as an available and default field.
- **`docs/schema.md`:** under each table's column table, an "Indexes" table with the same five values. A table with no secondary index has none.
- **The contract test** parses that table too. The parser of the table sections lives in one importable module, `spider.services.schema_doc.parse_tables(text)`, not inside the test file, because `080` reads its generated reference back with it. The file check reads `PRAGMA index_list` and `PRAGMA index_xinfo` for the columns, and `sqlite_master.sql` for a partial index's condition.
- *Alternative:* indexes kept out of the contract, as today. The inventory found that 060's design relied on an index that no change declares. Rejected.

### D5. Derived and later columns
- **The markers:**
  - A derived column's description starts with `Derived: `. Only a post-crawl pass writes it, and it is NULL until the pass runs.
  - A column that a later release fills starts with `Filled from v<major>.<minor>. `, and it is NULL in every row until then.
- **The test:** both kinds must be nullable, checked over `spider schema`. Who writes a derived column is the review's to check, in the owner's change.
- **The machine-readable form is the description itself:** no new `spider schema` field is added. The prefix is stable, which keeps `docs/schema.md` and the description equal without a new column in the reference table.
- *Alternative:* `derived` and `filled_from` fields on each column. That would be more output for every table, for a fact that the description already states. Rejected; `080` can decide to surface it.

### D6. Counts in the `crawl` row
- 015's rule "the `crawl` row holds no counts or statistics" becomes: no counts or statistics are written while the Crawl runs, and a derived value over the stored rows may be stored only when a post-crawl pass writes it. 040's Health Score columns are the first such values.
- Counts during the Crawl still come from the tables, or from the writer's counters for progress (017, 020).

### D7. 015's tables follow at once
- `crawl` and `seeds` become `STRICT`.
- `crawl.crawl_mode`, `crawl.state` and `crawl.journal_mode` get their value CHECKs, and `crawl.section_crawl` its flag CHECK.
- No column is renamed. `schema_version` stays `1`, because there are no migrations before v0.1 (015 D5). A crawl file made by an earlier development build is not upgraded.

## Test seams

Seams from docs/testing.md:
- **CLI (1):** `spider schema` output and `spider commands`, through `run_cli`.
- **Services and store API (2):** units that write refused values, through `CrawlWriter`, with a real crawl file in `temp_workspace`.
- **Store contract (6):** `docs/schema.md` against `spider schema --limit 1000`, and a new file through `PRAGMA table_list`, `table_info`, `foreign_key_list`, `index_list` and `index_xinfo`.
- Scenarios that only `crawl` and `seeds` exercise today, such as reference columns and index names, are guards. They pass at once, and they bind every table that later changes add.

No boundary double is used.

## Risks / Trade-offs

- [A tool built on SQLite older than 3.37 cannot open a crawl file] → `docs/schema.md` states the minimum, and `080`'s `doctor` reports the version. Python 3.12+ on our supported platforms ships 3.40 or later through uv.
- [A CHECK refuses a value that a later change adds without listing it] → The rule lists later values from v0.1. A missed value fails loudly at the first write, in that change's tests.
- [Guards that pass trivially today could hide a broken check] → In this change they pass vacuously, because `crawl` and `seeds` have no foreign key, secondary index, or derived or later column. Each guard's assertion that it saw at least one match switches on in the `020` task that adds the first foreign key (`found_on_url_id`) or the first index (`urls_url`). A later change does the same for the first derived or later column: `022`'s `origins.http_version` (filled from v0.2) or `030`'s later `pages` columns, whichever lands first.

## Migration Plan

None. Before v0.1 the schema is not yet public, and `schema_version` stays `1` (015 D5).

## Interface points for later changes

- **`020`:**
  - Declares `urls` and `origins` through the D2 helper: CHECKs, STRICT, and `REAL` for real numbers.
  - Its `found_on_url_id` is the first declared reference, and `origin_id` the second.
  - `urls_url` (unique) is the first index with a description, and `urls_crawl_depth_id` (`(crawl_depth, id) WHERE fetch_state = 'queued'`, the frontier) the first partial one.
- **`022`:** adds `urls.redirect_url_id` with its partial index `urls_redirect_url_id` (`WHERE redirect_url_id IS NOT NULL`).
- **`022`, `030`, `040` and `060`:** their tables follow ADR-0005 from their first slice. `030` takes the links layout from the links benchmark, and `040`'s `health_*` columns are derived.
- **`080`:** the agent documentation of the schema builds on `spider schema`'s `references` and `indexes`, and on the two description prefixes. It adds `render_tables(items, compact=...)` next to `spider.services.schema_doc.parse_tables`, renders its `sql-schema.md` in the table-section layout of `docs/schema.md`, and reads it back with `parse_tables`. `docs/schema.md` stays written by hand; a change to its layout changes the parser, and so `080`'s renderer with it.

## Open Questions

None that block the tasks.
