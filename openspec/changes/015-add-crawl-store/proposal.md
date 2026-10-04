## Why

"Your crawl is a database" is the product's first promise (ROADMAP, Positioning): each Crawl is one self-contained SQLite file with a public, versioned, documented schema that agents query with read-only SQL (ADR-0002). Crawling (`020`, `022`), page data (`030`), Rules (`040`) and queries (`050`) all write or read it, so the store's guarantees must hold before any of them stores data:
- transactional units of work, with bounded loss after a crash
- read-only readers that release their files
- a schema whose documentation, declaration and files cannot drift apart
- no stored secrets

## What Changes

> **Re-grounded (2026-10-05)** against the archived `010-add-workspace-and-cli-contract`. v0.1 keeps only what the thin slice and the v0.1 Commands need. The writer claim, control writes, recording `interrupted`, reserved and chosen crawl ids, and the `.lock`/`.log` files move to `060-add-crawl-control` (v0.1.1/v0.2). Alembic and in-place upgrades wait for the first schema change after the v0.1 release.

- **Files and ids**
  - A Crawl is stored as `.spider/crawls/<crawl-id>.sqlite`.
  - Crawl ids look like `20260927-140312-k3f9`: the UTC start time plus 4 random characters. A taken id is drawn again, and the file is created exclusively.
  - Creating a Crawl creates the data folder, or fails with `workspace_not_writable`.
- **`--crawl latest|<id>|<path>`**
  - The global flag of every Command that reads a Crawl, declared once next to `--workspace`.
  - Its failures are `no_crawls`, `crawl_not_found`, `crawl_file_invalid` and `invalid_value`.
- **Tables**
  - `crawl` holds the metadata: the Crawl Mode, the Section Crawl flag, the Crawl State, `started_at`, `completed_at`, the redacted command line and config, the working folder, the settings file, the tool, schema and Python versions, the platform and the journal mode. It holds no counts: counts are derived from the tables.
  - `seeds` holds the Seeds in their given order.
  - The Crawl States follow CONTEXT.md: `running`, `stopped`, `completed`, `failed` and `interrupted`.
- **Redaction** of secret options and settings, as `010` declares them, in recorded commands and config: a whole value becomes `***`, and a URL keeps everything but its password (`user:***@proxy`).
- **The transactional writer**
  - Units of work mix inserts, updates and reads, and run in order within one transaction. A failing unit leaves no change.
  - It commits every 500 units, every second, on a flush, and on close. A killed process loses at most the units since the last commit.
  - Opening it runs a rolled-back write first, so an unwritable crawl file fails at once with `crawl_not_writable`.
- **Journal mode**
  - WAL on local disks, with `synchronous=NORMAL` and a busy timeout.
  - A rollback journal on UNC paths, with the warning `store_wal_unavailable`.
  - The override is the `[store] journal_mode = "auto" | "wal" | "delete"` setting, the first real table of `010`'s settings registry.
- **Reading**
  - Readers open files read-only and release them after every operation.
  - In rollback-journal mode a busy read fails with `crawl_busy` after 5 s.
  - A file from a newer tool is refused with `crawl_schema_too_new`.
- **The public schema reference**
  - `spider schema [TABLE]`, a list Command paged by `010`'s pager. Its result starts with `schema_version`, and tables are ordered by the number of the change that added them.
  - `docs/schema.md`, the public schema reference, is checked against the declared schema, and a new crawl file is checked against it through `PRAGMA table_info`, so the documentation, the code and the database cannot drift.
  - The conventions every table follows: snake_case names, descriptions, units in names, timestamps, booleans, enumerations, JSON only for recorded inputs, one meaning per column, an explicit order column, and NULL for "not measured".

**Commands added:** `spider schema [TABLE]`.

**Flags added:** the global flag `--crawl <ref>`, for Commands that read a Crawl.

**Settings added:** `store.journal_mode`. No MCP tools are added; `090` mirrors `schema` in v0.1.1.

**Small additions beyond ROADMAP.md, all needed by the scenarios:**
- the key `schema_version` in `spider schema`'s result
- the column name `completed_at`, because CONTEXT.md says to avoid "finished"
- the environment stamp: `python_version` and `platform`, useful when a crawl file is attached to a bug report

## Capabilities

### New Capabilities

- `crawl-store`: crawl files and ids, `--crawl`, crawl metadata and states, redaction, the transactional writer and its write check, the journal mode, reading, refusing newer files, `spider schema`, `docs/schema.md`, and the table conventions.

### Modified Capabilities

None. This change uses `workspace` and `cli-contract` from `010-add-workspace-and-cli-contract` (its settings registry, error-code registry, paging and global-flag metadata) without changing their requirements.

## Non-goals

- **`020-add-crawl-core` (v0.1):**
  - the tables for URLs, Links and the frontier, including a row for every requested URL, failed fetches too
  - the `crawl` columns `scope`, `stop_reason` and `warnings`
  - when each state is set, including Ctrl+C, which leaves the Crawl `stopped` with `stop_reason: interrupt` and exits 130
- **`022-add-fetch-policy` (v0.1):** the size columns, the body-truncated flag, `response_headers`, and redacting proxy passwords from the proxy variables it records. **(v0.2)** the header form of redaction for `--header`.
- **`050-add-query-and-segments` (v0.1):** the query Commands that use `--crawl`, `spider sql` with its SQLite authorizer, and keyset paging bound to a Crawl.
- **`060-add-crawl-control` (v0.1.1 and v0.2):**
  - the writer claim (`crawl_locked`), liveness, and recording a dead Crawl as `interrupted`
  - control tables and control writes by other processes
  - chosen and reserved crawl ids (`crawl_id_taken`), and the `.lock` and `.log` files
  - refusing a resume whose Scope changed, `crawls rm`, and asking for secret flags again on resume
- **After the v0.1 release:** in-place upgrades of older crawl files (`crawl_migrated`, `crawl_migration_failed`, `crawl_schema_unknown`) and the migration tool, with the first schema change after v0.1. The migration test from every published schema version starts at v0.1.
- **v0.2:** detecting network drives other than UNC paths (mapped drives, SMB and NFS mounts) from the mount table.
- **v0.3:** relative Crawl references for `diff A B`.

## Impact

- **New runtime dependency:** `sqlalchemy` (2.x Core), imported only by the Commands and services that use the store, never on the `--help` or `spider commands` path.
- **Code:**
  - `src/spider/store/`: the declared schema and its column types, ids, crawl files, the writer, the journal mode, redaction and the `[store]` settings table
  - `src/spider/services/`: the schema description behind `spider schema`, and resolving `--crawl`
  - `src/spider/cli/schema.py`, and `--crawl` among the global flags in `spider.cli.options`
  - the store's codes in `spider.output.codes`
- **Docs:** new `docs/schema.md` (the public schema reference) and `docs/crawl-store.md`. Also updates to `docs/architecture.md`, `docs/cli.md` and `CONTRIBUTING.md`.
- **Test support:**
  - `tests/support/store_worker.py`, a subprocess that writes and gets killed
  - an example Command that reads a Crawl, on the test app
- **Every change that stores data** follows these conventions, and adds its tables to the declared schema and to `docs/schema.md` in the same slice.
