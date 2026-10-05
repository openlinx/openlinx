## Context

- **What this change builds on:** the archived `010-add-workspace-and-cli-contract` (openspec/specs/workspace and cli-contract, and its design):
  - a Command is an adapter plus a service with typed inputs and a `Reporter` (010 D9)
  - the error-code registry in `spider.output.codes`, with `ExitCode.BUSY` (5), `INCOMPATIBLE` (6) and `IO` (7) (010 D5)
  - the settings registry with lazy `"module:Class"` tables, `None` defaults and `secret` on the settings field (010 D2)
  - `Page`, `paginate` and `fingerprint` in `spider.output.paging` (010 D6)
  - `@command_meta(name=...)`, `OptionMeta(is_global, setting, secret)` and the global flags in `spider.cli.options` (010 D7)
  - the startup allowlist test, `tests/cli/test_startup.py` (010 D10)
  - `spider.naming` for every name-derived string (010 D11)
  - `000-scaffold-project`: `FakeClock`, the network guard and the gates
- **The stack is settled:** SQLite through SQLAlchemy 2 Core (ADR-0002, ADR-0003). The migration tool waits for the first schema change after v0.1 (D5).
- **Who depends on it in v0.1:** `020` and `022` write through the writer, `030` and `040` add tables, and `050` reads through `--crawl`. In v0.1.1, `060-min` adds the writer claim and liveness, and `090` reads crawl files from a long-running process.
- **The thin slice** (ROADMAP, Build order) needs the crawl file, ids, metadata, the writer and `--crawl` first. `spider schema`, reading across processes, the journal-mode fallback and redaction can follow; tasks.md marks each group.
- See proposal.md for why.

## Goals / Non-Goals

**Goals:**
- Guarantees that hold whichever service uses the store:
  - atomic units and bounded loss
  - a precise error before crawling when a crawl file cannot be written
  - read-only readers and released handles
  - no stored secrets
- One declared schema, with `docs/schema.md`, `spider schema` and every new crawl file checked against it, so "your crawl is a database" stays true by construction.

**Non-Goals:**
- Any table beyond `crawl` and `seeds`.
- When each Crawl State is set (`020` and `060`).
- More than one writing process per Crawl: the writer claim belongs to `060` (D4).
- Upgrading older files in place (D5).
- Keyset SQL paging (`050`).

## Decisions

### D1. Crawl ids

- **Format:** `YYYYMMDD-HHMMSS-xxxx`, where the time is the injected `Clock`'s UTC time. The suffix is 4 characters drawn from a Crockford-style alphabet without `i`, `l`, `o` or `u`. The random source is injected (docs/testing.md lists randomness as a boundary double), and production uses `secrets.choice`.
- **Taken ids:** an id is taken when `<id>.sqlite` exists. A drawn id is drawn again until it is free, and the file is created with exclusive create, so two creators of the same id cannot both succeed.
- **Later:** `060` reserves ids by creating `<id>.log` before it spawns a detached Crawl, adds chosen ids and `crawl_id_taken`, and extends "taken" to its own files.
- **Alternatives:**
  - **ULID or UUIDv7:** sortable, but not readable.
  - **Integers:** they collide when crawl files are copied between Workspaces.
  - **A host slug:** untrusted text in file names.

### D2. Opening crawl files

- **One engine per operation**, created with `NullPool`.
  - A `creator` calls `sqlite3.connect(<uri>, uri=True)`.
  - The URI is percent-encoded from the absolute path, which handles spaces, `#`, `?`, `%`, non-ASCII characters and drive letters. Readers add `mode=ro`.
  - A UNC path keeps its host inside the path, `file:////host/share/…`: SQLite refuses a URI authority other than `localhost`, so `Path.as_uri()` cannot be used.
  - `spider.store.connections` is the only code that opens a crawl file.
  - The context manager disposes the engine, so no handle outlives the operation. This matters on Windows (the deletion scenario) and for `090`'s long-running MCP server.
- **Connection pragmas:**
  - `foreign_keys=ON`
  - `busy_timeout`: 30 s for the writer, 5 s for readers, after which the error is `crawl_busy`
  - `synchronous`: `NORMAL` in WAL mode, `FULL` in delete mode
  - `cache_size` and `temp_store` keep SQLite's defaults until `026`'s benchmark shows a reason to change them.
- **Alternatives:**
  - **Cached engines.** Rejected: Windows would refuse to delete or rename the files, and long read transactions starve WAL checkpoints.
  - **`immutable=1` readers.** Rejected: unsafe while a Crawl is being written.

### D3. Journal mode

- **One pure function** chooses the mode from the setting and the location, and returns the mode and an optional warning. A location is a UNC path when it starts with `\\` or `//`, which also covers `\\?\UNC\`. No system call is made.
- **Defensive fallback:** after asking for WAL, the store checks that `PRAGMA journal_mode=WAL` returned `wal`. If it did not, it falls back to `delete` with the same warning. No scenario covers this, because no test can make SQLite refuse.
- **The integration test** runs on Windows through the admin share `\\localhost\C$`, which is a real UNC path. It is skipped when the share is not reachable.
- **The `[store]` settings table** is registered in `build_app` as `("store", "spider.store.settings:StoreSettings")`. It is the first real table of the registry, so the table-rules test of 010 D2 covers it.
- **`080`'s doctor** calls the same function for its WAL check.
- **Deferred to v0.2:** mapped network drives and SMB, NFS or other network mounts, read from the mount table. That needs `psutil`, a compiled dependency, and per-OS mount data. Until then, `store.journal_mode = "delete"` is the documented answer for such folders.
- **Alternatives:**
  - **Trust the pragma alone.** Rejected: SQLite accepts WAL on SMB shares, where it is unsafe.
  - **The mount table in v0.1.** Deferred: more code and a compiled dependency for a rare case that the setting already covers.

### D4. The transactional writer

- **API**, which `020`, `022`, `030` and `040` use:
  - `CrawlWriter.run(unit) -> T` is thread-safe and blocking. `await CrawlWriter.run_async(unit)` serves event-loop callers.
  - A unit is `Callable[[Connection], T]`. The writer runs units one at a time, on its own thread, in submission order, inside one open transaction.
- **The write check:** opening the writer runs `BEGIN IMMEDIATE`, a write to the `crawl` row, and `ROLLBACK`, before it accepts units. A failure becomes `crawl_not_writable` with `details.file`, so a read-only file or folder is reported before anything is crawled.
- **Atomic units:** each unit runs inside its own SAVEPOINT (SQLAlchemy's `begin_nested()`, with pysqlite in autocommit so that `BEGIN IMMEDIATE` and the savepoints are the writer's own).
  - On success the savepoint is released.
  - On an exception the writer rolls back to the savepoint, and the exception is raised to that unit's caller. Earlier and later units are unaffected.
- **Commits:** after 500 units, 1 s after the first uncommitted unit (measured with the injected `Clock`'s `monotonic()`, checked every 50 ms and after each unit), on `flush()`, and on `close()`.
  - `close()` commits, runs `wal_checkpoint(TRUNCATE)` and joins the thread.
  - **The commit observer:** `CrawlWriter(path, clock, on_commit=None)`. When given, `on_commit(units)` is called on the writer thread after each successful commit, with the number of units that commit made durable; it is not called when the commit made no unit durable (nothing was pending, or every pending unit failed). `020` can use it for progress and metrics; the idle-timer test waits on it. An exception it raises ends the writer like a failed commit, and reaches the caller of the unit in hand even though that unit was committed.
- **Reads inside units** see every earlier unit's effects, because they share the transaction. `020`'s frontier can therefore take the next URL and mark it in a single unit.
- **Backpressure:** the submission queue is bounded at 50,000 units, and `run` blocks when the queue is full.
- **Callers and threads:** units may come from any thread, or from an event loop through `run_async`, which never blocks the loop. The writer thread alone owns the connection, runs one unit at a time and keeps each caller's order. A caller gets its unit's result only after the commit check, so a reader that runs after the 500th unit returns sees the batch.
- **The writer's end:**
  - `close()` may be called again; the second call does nothing.
  - A unit or flush submitted after `close()` fails with `CrawlWriterClosedError`, a bug in the caller (exit code 70), never a hang: at once, or within 0.5 s for one that raced `close()` into the queue.
  - A unit that submits to its own writer gets a `RuntimeError` instead of waiting for itself.
  - A unit that raises any `BaseException`, `KeyboardInterrupt` included, rolls back to its savepoint, the exception reaches that unit's caller, and the writer goes on. Ctrl+C is the Crawl service's to handle (`020`), not the writer's.
  - If the writer thread ends unexpectedly, for example on a failed commit, the caller of the unit in hand gets that error, and every other waiting or later caller gets `CrawlWriterClosedError`. `close()` then raises it too, with the failure as its cause, so a commit that failed while no unit waited is never lost silently. Nothing is raised on the writer thread, whose traceback would reach stderr as raw text.
  - Opening the writer and `close()` block (the write check can wait for a lock for up to 30 s, and `close()` commits and checkpoints). `020` calls them through `asyncio.to_thread` from its event loop.
  - The writer opens its file with `mode=rw`, never SQLite's default `rwc`, so a missing crawl file is an error and never a new empty file.
- **Creating a Crawl is the one write outside the writer.** The new file's tables, its `crawl` row and its Seeds are written in the file's first transaction, before any writer opens; the write check needs that row. Every later write is a unit.
- **One writer per Crawl, by construction in v0.1:** only the process that creates a Crawl writes it, because v0.1 has no resume and no detach. `060-min` (v0.1.1) adds the writer claim when a second process can write: a detached Crawl and `status`, then `resume` in v0.2.
- **Alternatives:**
  - **Row batches without units.** They cannot express the frontier's read-then-update steps.
  - **One transaction per unit.** Too slow.
  - **aiosqlite.** It is a thread anyway, plus a second API.
  - **Writing on the event loop.** It blocks crawling.

### D5. Schema versions, without migrations until the first release

- **New files** are made with `metadata.create_all()`, and stamped with `crawl.schema_version` and `PRAGMA user_version`, both `1`.
- **Opening a file** reads `user_version` without the declared schema:

  | Condition | Result |
  |---|---|
  | not a SQLite file, or no `crawl` row | `crawl_file_invalid` |
  | file version > tool version | `crawl_schema_too_new`, file unchanged |
  | otherwise | open |

- **Before v0.1, the schema is not yet public.** Changes `020` to `040` edit the declared tables freely, and `schema_version` stays `1`. Development files from before such an edit are not supported, which ADR-0002 allows, since the chain is squashed before v0.1 anyway.
- **After v0.1:** the first released schema change adds 1 to `schema_version`, and brings the migration tool (Alembic, as ADR-0003 chose) with in-place upgrades, `crawl_migrated`, `crawl_migration_failed` and `crawl_schema_unknown`. Its migration test starts from every published schema version, the first being v0.1's.
- **The `crawl` columns `id`, `schema_version`, `started_at` and `tool_version` never change**, so every tool version can identify every crawl file.

### D6. The declared schema, `spider schema` and `docs/schema.md`

- **One declaration:** the Core `MetaData` in `spider.store` is the only definition of the public schema. Later changes add their tables to it.
  - Descriptions come from `Table(comment=…)` and `Column(comment=…)`.
  - `values` and the adding change's number (`info={"change": 15}`) come from `info`. `values` is read from the `Literal` type that the code uses, such as `CrawlState`, so it is declared once.
  - `format` comes from the column's type: `Timestamp`, `Json` and `Flag` in `spider.store.types` each carry theirs, so a column's format cannot disagree with how it is stored.
  - **Column types** shared with later changes: a UTC timestamp stored as TEXT `YYYY-MM-DDTHH:MM:SS.sssZ`, JSON stored as TEXT encoded with orjson, and a boolean stored as INTEGER.
- **The schema service** builds the description of the public tables from the metadata: items in `(change number, position within the change)` order, so the order does not depend on which change was merged first, without tables whose names start with `_`. `spider schema` is its adapter, and `090`'s `schema` tool calls the same service.
- **`spider schema`** is a list Command, `@command_meta(name=SCHEMA)` with the name as a module constant. It pages the static description with `paginate`, and its fingerprint holds the Command name and TABLE. Its JSON result is `010`'s envelope with `schema_version` added as the first key.
- **`docs/schema.md` is written by hand,** one `## Table \`<name>\`` section per table: a description paragraph, and a pipe table `| Column | Type | Null | Key | Format | Values | Description |`. It is the public schema reference, written for people and agents, which is why it is not generated.
- **Three-way check:**
  - **docs ⇔ declaration:** the store contract test parses `docs/schema.md` and requires equality with the schema service's description, which `spider schema --limit 1000` prints. In the thin slice it calls the service; group 6 adds the CLI check.
  - **declaration ⇔ file:** a test creates a crawl file and compares `PRAGMA table_info` and `PRAGMA foreign_key_list` of every public table with the metadata.
  - **conventions:** tests over `spider schema` check names, descriptions, booleans and enumeration values for every table, including those later changes add.
- **No schema-first slices:** the contract test is written first, over an empty schema. After that, every slice that adds a table or column updates `docs/schema.md` in the same commit, so the contract test is never red between commits.
- **Conventions learned from a code review of similar crawlers:**
  - Counts and statistics are derived from tables, never stored as a JSON blob on `crawl`.
  - JSON only for recorded inputs (`command_argv`, `config`) and lists without a fixed shape. A value queries filter, sort or count by gets its own column.
  - One meaning per column: two hashes or two sizes are two distinctly named columns (`022` adds `size_bytes` and `transferred_bytes`, and a body-truncated flag).
  - A deterministic order: rows with an order carry a growing INTEGER column (`seeds.position`, `020`'s `seq` on URLs), never a timestamp tie-break.
- **Alternatives:**
  - **Generating `docs/schema.md` from code.** The docs test would then be tautological, and docs/testing.md forbids auto-accepted snapshots.
  - **Table order by merge order.** It would depend on the order of parallel merges.

### D7. Redaction

- **What is secret** comes from `010`: an option is secret when its setting is secret (`SettingsTables.is_secret`), or when it maps to no setting and declares `secret=True` on its `OptionMeta`. Settings are secret through `json_schema_extra={"secret": True}`. Nothing is declared twice.
- **One pure function** takes the argv, the config, the secret flag names and the secret dotted keys, and returns both redacted. The adapter that creates a Crawl (`020`'s `crawl`) collects the secret flag names from its Click params with `options_with_meta`. `060` reuses the function for `crawl_runs.command_argv`.
- **The two shapes of a secret value:**
  - a URL with a password keeps its scheme, user, host, port and path: `user:***@host`
  - any other value becomes `***`
- **Who calls it:** the Crawl service, before anything is written.
- **Later:** `022` (v0.2) adds the header shape for `--header`, which keeps the header name and redacts the value of sensitive headers only. `022` (v0.1) redacts the proxy passwords of the proxy variables it records, with the URL shape.
- **Secrets in `spider.toml`** are allowed. They are redacted in `crawl.config` like any other secret.
- **Alternatives:**
  - **A form per secret (`whole`, `header`, `url`)** declared on each option. Rejected for v0.1: `010` declares `secret` as a boolean, and the URL shape can be read from the value.
  - **Redacting every header value.** Left to `022`'s v0.2 design.

### D8. `--crawl`

- **The option** is declared once in `spider.cli.options`, next to `--workspace`: `str`, default `latest`, with `OptionMeta(is_global=True)`. Its module imports no sqlalchemy: it takes `LATEST` from `spider.store.records`, which loads none, so `--help` and `spider commands` stay on the startup allowlist.
- **Resolution** is the store function `spider.store.selection.resolve_crawl(reference, workspace=, cwd=)`, which the query services call (`050` and `090`) inside their bodies:
  - Only `<id>.sqlite` files count as Crawls. `spider.store.ids` owns the id format and the file name.
  - A path (a value with a path separator or ending in `.sqlite`) is taken from `cwd`. The returned `CrawlFile` carries the id from the file's `crawl` row.
  - `latest` sorts by id, and breaks ties between ids of the same second with `crawl.started_at`, then the id itself.
  - Every selected file is read before it is returned. A broken newest file is reported, never skipped, so an agent never reads an older Crawl without knowing it; a broken file among the ids of the newest second fails the tie-break the same way. Not a SQLite file, no `crawl` table, or not exactly one `crawl` row is `crawl_file_invalid`.
  - It never creates a folder or a crawl file, so it resolves the Workspace with `resolve_workspace`, not the creating path. SQLite's `-wal` and `-shm` companions of an existing crawl file may appear, because a WAL reader needs the shared-memory file; `immutable=1` stays rejected (D2), and the companions never count as Crawls.
  - A path that does not exist is `crawl_not_found`, checked before the read-only open; an existing file that is not a crawl file is `crawl_file_invalid`.
  - By id or `latest`, the file name is the id: a `crawl` row with another id is `crawl_file_invalid`, with `details.expected_id` and `details.found_id`, so `--crawl X` never returns Crawl Y. By path, the row's id is authoritative and the name does not matter (ADR-0002 allows copied and renamed files).
- **Hints** are built from `spider.naming` (`f"{APP_NAME} crawl"`), never from a literal.
- **The CLI scenarios** use an example Command that reads a Crawl, registered on the test app (`tests/support/app.py`). The real consumers arrive in `050`.

### D9. Services and the startup path

- **Services:** creating a Crawl (used by `020`'s Crawl service), resolving `--crawl`, and describing the schema are plain functions with typed inputs, a `Reporter` for warnings such as `store_wal_unavailable`, and no Click.
- **Codes:** `no_crawls`, `crawl_not_found`, `crawl_busy`, `crawl_file_invalid`, `crawl_schema_too_new`, `crawl_not_writable`, `unknown_table` and `store_wal_unavailable` are declared as `DiagnosticCode` constants in `spider.output.codes`, and follow its naming-rule test.
- **The startup path:** `sqlalchemy` is imported only inside the bodies of store-using Commands and services. `spider --help` and `spider commands` with `schema` registered still pass the allowlist test.

## Test seams

Seams from docs/testing.md used by this change:
- **CLI (1):**
  - `spider schema` and its entry in `spider commands`
  - `--crawl`, through the example Command
  - the `[store]` template and validation, through `spider init`
- **Services and store API (2):**
  - creating a Crawl, resolving `--crawl`, and the metadata
  - the writer and its write check
  - reading, and refusing newer files

  These run on real SQLite files in `temp_workspace`. The kill scenarios use real subprocesses from `tests/support/store_worker.py`, killed with `Popen.kill()` (SIGKILL on POSIX, TerminateProcess on Windows).
- **Pure-logic modules (4):**
  - the id format, including a hypothesis property
  - choosing the journal mode
  - redaction
- **Store contract (6):** `docs/schema.md` against `spider schema --limit 1000`, a new file against the declared schema, and the convention checks.

Test doubles:
- **The clock (`FakeClock`):** the writer's commit timer and the ids.
- **Randomness:** an injected suffix source for the id scenarios.
- **No file-system fakes:**
  - An unwritable data folder is a real `H/.spider` that is a file.
  - A read-only crawl file uses the real read-only attribute.
- **Extension points, not doubles:** the example `--crawl` Command, and the test app's `example-settings` Command for redaction.

No new seam is introduced. The store API is seam 2.

## Risks / Trade-offs

- **Network drives other than UNC paths are not detected in v0.1.**
  - `store.journal_mode = "delete"` covers them, `docs/crawl-store.md` says so, and `080`'s doctor shows the chosen mode.
- **Pre-release crawl files break after a schema edit.**
  - Accepted until v0.1 (D5). `crawl_file_invalid` names the file, and the hint says to crawl again.
- **The WAL grows while a reader holds a long read transaction.**
  - Readers are opened per operation.
  - The writer checkpoints with `TRUNCATE` on close.
- **The timing scenarios (the 5 s busy wait, kills) are slow.**
  - The commit timer uses `FakeClock`, so only the busy test and the subprocess tests take real seconds. Those are marked `slow`.
- **A new crawl file is empty for a few milliseconds.**
  - A `--crawl latest` that runs during the milliseconds between claiming and creating a file reports `crawl_file_invalid`. Accepted for v0.1. `060` removes the window with `.tmp` + rename alongside its reservations.

## Migration Plan

This is the first store version, so there is nothing to migrate. The migration tool arrives with the first schema change after v0.1 (D5).

## Interface points for later changes

- **Tables:**
  1. In the slice that first needs a table or column, add it to the declared schema and to `docs/schema.md` together. Use `info={"change": <n>}`, give every table and column a comment, and use the shared column types for timestamps, JSON and booleans.
  2. Follow the conventions (D6), with NULL for "not measured".
  3. No migration before v0.1 (D5).
- **Creating a Crawl:** `020`'s Crawl service calls `spider.services.crawls.create_crawl` with a `NewCrawl`, including the settings file it read the settings from.
- **Writing:** all Crawl data goes through `CrawlWriter` units. `020` adds `crawl.scope`, `crawl.stop_reason` and `crawl.warnings`, and stores a row for every requested URL, including 403s, 5xx responses and network errors.
- **States:**
  - `020` sets `running`, then `completed` (with `completed_at`), `stopped` (with `stop_reason`: `max_urls`, or `interrupt` for Ctrl+C with exit code 130) or `failed` (an unreachable Seed, exit code 8).
  - `060` adds the writer claim, records `interrupted`, and resumes `stopped`, `interrupted` and `failed` Crawls.
- **Secrets:** a setting is marked secret on its field, and an option without a setting on its `OptionMeta`; the Crawl service redacts both (D7).
- **Reading:** query Commands take `--crawl` and call the resolution function. `050` adds the crawl id to its cursor fingerprint.
- **`080`:** doctor calls the journal-mode function.

## Open Questions

- Should `spider schema` show which change added each table, for example `added_by: "015"`? It is additive, and not needed by any scenario.
