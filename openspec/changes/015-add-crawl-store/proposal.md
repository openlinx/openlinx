## Why

Each Crawl must be stored as one self-contained SQLite file with a public, versioned schema (ADR-0002). Crawling (`020`–`026`), querying (`050`), crawl control (`060`), reports (`070`) and MCP (`090`) all share it.

The store's guarantees must hold before any of them writes data:
- one writer, with transactional units of work
- bounded loss after a crash
- read-only readers
- safe upgrades
- redacted secrets

## What Changes

- **Files and ids**
  - A Crawl is stored as `.spider/crawls/<crawl-id>.sqlite`.
  - Crawl ids look like `20260927-140312-k3f9`: the UTC start time plus 4 random characters.
  - An id counts as taken when any of `<id>.sqlite`, `<id>.lock` or `<id>.log` exists.
  - A caller may choose and reserve the id first, as `060`'s `--detach` needs. A chosen id that already has a crawl file fails with `crawl_id_taken`.
  - Creating a Crawl creates the data folder, or fails with `workspace_not_writable`.
- **`--crawl latest|<id>|<path>`**
  - It is the global flag of every Command that reads a Crawl. It is defined here as `CrawlOpt`, on top of `resolve_crawl`.
  - Its failures are `no_crawls`, `crawl_not_found`, `crawl_file_invalid` and `invalid_value`.
  - A reservation alone is not a Crawl.
- **Tables**
  - `crawl` holds the metadata: the Crawl Mode, the Section Crawl flag, the Crawl State, `started_at`, `completed_at`, the redacted command line and config, the working folder, the settings file, the tool, schema and Python versions, the platform and the journal mode.
  - `seeds` holds the Seeds in their given order.
  - The Crawl States follow CONTEXT.md: `running`, `stopped`, `completed`, `failed` and `interrupted`.
- **Redaction** in recorded commands and config, in three forms:
  - whole values (`--auth ***`)
  - sensitive header values (`Authorization: ***`, `Cookie: ***`)
  - URL passwords (`user:***@proxy`)
- **The transactional writer**
  - Units of work mix inserts, updates and reads, and run in order within one transaction. A failing unit leaves no change.
  - It commits every 500 units, every second, on a flush, and on close.
  - A killed process loses at most the units since the last commit.
- **The writer claim:** one writing process per Crawl (`crawl_locked`). There are two stated exceptions:
  - other processes may write rows of **control tables**, which `060` adds
  - a process that finds a dead Crawl records it as `interrupted`
- **Journal mode**
  - WAL on local disks.
  - Rollback journal on UNC paths, remote drives and network filesystems, with the warning `store_wal_unavailable`.
  - The override is the `[store] journal_mode = "auto" | "wal" | "delete"` setting, registered in `010`'s settings system.
- **Reading**
  - Readers open files read-only and release them after every operation.
  - In rollback-journal mode a busy read fails with `crawl_busy` after 5 s.
- **Schema versions**
  - Older files are upgraded when opened (`crawl_migrated`).
  - Newer or unknown files are refused (`crawl_schema_too_new`, `crawl_schema_unknown`).
  - A failed upgrade changes nothing (`crawl_migration_failed`, `crawl_not_writable`, `crawl_busy`).
- **`spider schema [TABLE]`**
  - A list Command. Its result starts with `schema_version`, and tables are ordered by the number of the change that added them.
  - `docs/schema.md` is the documented contract.
  - The conventions every table follows: snake_case names, descriptions, units in names, timestamps, booleans, enumerations, and NULL for "not measured".

**Commands added:** `spider schema [TABLE]`.

**Flags added:** the global flag `--crawl <ref>`, for Commands that read a Crawl.

**Settings added:** `store.journal_mode`. No MCP tools are added.

**Small additions beyond ROADMAP.md, all needed by the scenarios:**
- the key `schema_version` in `spider schema`'s result
- the code `crawl_id_taken`
- the column name `completed_at`, because CONTEXT.md says to avoid "finished"
- the environment stamp: `python_version` and `platform`, useful when a crawl file is attached to a bug report

## Capabilities

### New Capabilities

- `crawl-store`: crawl files and ids, `--crawl`, crawl metadata and states, redaction, the transactional writer and the writer claim with its two exceptions, the journal mode, reading, upgrades, `spider schema`, and the table conventions.

### Modified Capabilities

None. `010-add-workspace-and-cli-contract` is still in flight. This change registers into its settings and diagnostic registries without changing its requirements.

## Non-goals

- **`020-add-crawl-core` (v0.1):**
  - the tables for URLs, Links and the frontier
  - the `crawl` columns `scope`, `stop_reason` and `warnings`
  - when each state is set, including Ctrl+C, which leaves the Crawl `stopped` with `stop_reason: interrupt` and exits 130
- **`022-add-fetch-policy` (v0.1):**
  - the `response_headers` table, where cookie values are always `***`
  - declaring which fetch flags are secret
- **`050-add-query-and-segments` (v0.1):**
  - the query Commands that use `--crawl`
  - `spider sql` and its SQLite authorizer (v0.2)
  - keyset paging bound to a Crawl
- **`060-add-crawl-control` (v0.2):**
  - `control_requests`, `crawl_runs` and the heartbeat
  - liveness through the writer claim
  - reserving `<id>.log` for `--detach`
  - `crawls rm` removing `.lock` and `.log`
  - `resume` asking for secret flags again
- **`080-add-agent-skill` (v0.1):** doctor's WAL check, which reuses this change's classification.
- **v0.3:** relative Crawl references for `diff A B`.

## Impact

- **New runtime dependencies:** `sqlalchemy` (2.x Core), `alembic`, `psutil` (the mount table) and `filelock` (the writer claim).
- **Code:**
  - `src/spider/store/`: the schema and types, ids, files, the writer, the claim, control writes, the journal mode, redaction and `migrations/`
  - `src/spider/cli/schema.py`
  - `CrawlOpt`
- **Docs:** new `docs/schema.md` (the documented schema) and `docs/crawl-store.md`. Also updates to `docs/architecture.md`, `docs/cli.md` and `CONTRIBUTING.md`.
- **Test support:**
  - `tests/support/store_worker.py`, a subprocess that writes, holds and gets killed
  - an example Command that reads a Crawl
  - test migration chains, and a test control table
- **Every change that stores data** follows these conventions and adds its tables here, through `docs/schema.md` and one Alembic revision each.
