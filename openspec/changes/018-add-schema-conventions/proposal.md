## Why

From v0.1 the crawl file is a public contract, and every change to it costs a migration (ADR-0002). Five changes are about to add tables to it: `020`, `022`, `030`, `040` and `060`. The schema inventory of 2026-10-10 found that they disagree on keys, reference names, time suffixes, flag names, value lists and indexes. It also found that `spider schema` and `docs/schema.md` cannot describe indexes at all, and that nothing in the file refuses a bad value.

The user decided on one schema blueprint before `020` is built (2026-10-10), and a separate small change for its conventions after `017` and before `020` (2026-10-11). This is that change. It records the rules in ADR-0005, makes the file enforce what can be enforced, and teaches the schema description and the contract test what the rules need. The tables themselves are added by their owners, which then follow the rules from their first slice.

## What Changes

> **Re-grounded (2026-10-11)** against the code of `015-add-crawl-store` as built on its branch (`spider.store.schema`, `spider.store.types`, `spider.services.schema`, `docs/schema.md` and `tests/contract/test_schema.py`), the archived `crawl-store` spec on that branch, the schema inventory of 2026-10-10 and the blueprint outline of 2026-10-11 with its rulings. **Re-grounded again (2026-10-11)** on `main` after `017`'s merge (PR #4): `opening(role=...)` and `ConnectionRole`, the writer's connect listeners and its optimistic batch, and the `crawl-store` spec on `main`, against which this change's modified requirements still differ only by its own additions.

- **ADR-0005,** "The crawl file's schema conventions":
  - the user's four schema decisions of 2026-10-10
  - indexes built during the Crawl
  - every Link occurrence as a row
  - STRICT tables
  - 15 naming rules
- **The file refuses bad values:**
  - every public table is `STRICT`
  - every enumeration column gets a CHECK of its listed values
  - every boolean column gets a CHECK of 0 and 1
  - the CHECKs come from the declaration, never from hand-written DDL
- **`spider schema` describes more:**
  - `references` is filled from the declared foreign keys
  - each table item gains `indexes`: name, description, columns, uniqueness and partial condition
- **`docs/schema.md` and the contract test follow:**
  - an index table under each table section
  - the conventions from ADR-0005
  - the three-way check (documentation, declaration, file) covers indexes, STRICT and `WITHOUT ROWID`
- **The conventions are revised:**
  - Derived values may be stored when a post-crawl pass writes them, marked `Derived: `.
  - Columns that a later release fills exist from v0.1, marked `Filled from v<major>.<minor>. `.
  - Keys and references, `_at`, `_seconds` and `_count`, flag names, error code and message, index names and descriptions.
- **015's two tables follow at once:** `crawl` and `seeds` become `STRICT`, and `crawl.crawl_mode`, `crawl.state`, `crawl.journal_mode` and `crawl.section_crawl` get their CHECKs. `schema_version` stays `1` (no migrations before v0.1).
- **Commands:** `spider schema` gains the `indexes` field (`--fields indexes`). No other Command, flag, setting or MCP tool is added or changed.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `crawl-store`:
  - **Crawl metadata:** a derived value written by a post-crawl pass may be stored.
  - **Listing the schema with spider schema:** `references` filled, and `indexes` added.
  - **The documented schema, the declared schema and the file agree:** also indexes, STRICT and `WITHOUT ROWID`.
  - **Public schema conventions:** ADR-0005's testable rules, with 7 new scenarios.
  - **Unmeasured values are NULL:** later and derived columns.

## Non-goals

- The tables and indexes of `urls`, `origins`, `response_headers`, `pages`, `links`, `cookies`, `page_sources`, `rules`, `issues`, `affected_urls`, `crawl_runs` and `control_requests`. Their owners add them under these rules: `020`, `022`, `030`, `040` and `060`, all v0.1. `page_sources` is filled only when HTML storage is opted in.
- The links layout: chosen by the links benchmark, then specified by `030`.
- Agent documentation of the schema (keys, references, values, indexes, an ER overview, cheap and expensive queries): `080-add-agent-skill`, v0.1.
- Migrations: the first schema change after v0.1 (`015` D5).
- A minimum SQLite version checked at runtime: `080`'s `doctor` reports the version (design D3).

## Impact

- **Depends on:**
  - `015-add-crawl-store` as built: the declared `MetaData` with `info={"change": n}`, the `Timestamp`, `Json` and `Flag` types, `describe_schema`, `docs/schema.md` and its contract test.
  - `017-speed-up-crawl-writer` as merged (PR #4): `CrawlWriter`'s optimistic batch, through which a refused unit fails alone, and `opening(role=...)`. The requirements that `017` modified ("Transactional writer") or added are not touched here.
- **Used by:** every change that adds a table: `020`, `022`, `030`, `040`, `060` and later ones.
- **Code:** `src/spider/store/schema.py`, `src/spider/services/schema.py`, the new `src/spider/services/schema_doc.py`, and the `schema` Command's fields.
- **Repository tooling and code style,** brought in by tasks 1.7 to 1.9 because `018` is the next change built: the line-endings check skips paths missing on disk, an `ast` guard holds ADR-0006's decidable rules, and four `noqa` and `type: ignore` uses follow CONTRIBUTING's "Code style".
- **Tests:** `tests/contract/test_schema.py`, the `spider schema` tests and the store tests.
- **Docs:** `docs/adr/0005-crawl-file-schema-conventions.md` (added with this change), `docs/schema.md` and `docs/crawl-store.md`.
- **New dependencies:** none.
