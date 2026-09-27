## Context

- **What this change builds on:**
  - `010-add-workspace-and-cli-contract`: Workspace resolution, the settings registry, the output layer, diagnostics, exit codes, the in-memory pager, and the app factory with its contract fixtures
  - `000-scaffold-project`: `FakeClock`, the network guard and the gates
- **The stack is settled:** SQLite through SQLAlchemy 2 Core plus Alembic (ADR-0002, ADR-0003).
- **Who depends on it:**
  - `020`–`026` write through the transactional writer.
  - `050` reads through `--crawl`.
  - `060` builds liveness on the writer claim, stop requests on control writes, and `--detach` on chosen ids.
  - `090` is a long-running process that reads crawl files.
- See proposal.md for why.

## Goals / Non-Goals

**Goals:**
- Guarantees that hold whichever service uses the store:
  - atomic units and bounded loss
  - one writer, with exactly two stated exceptions
  - read-only readers
  - released handles
  - safe upgrades
  - no stored secrets
- A schema reference, `spider schema` plus `docs/schema.md`, that stays true by construction.

**Non-Goals:**
- Any table beyond `crawl` and `seeds`.
- When each Crawl State is set (`020` and `060`).
- Keyset SQL paging (`050`).

## Decisions

### D1. Crawl ids, reservations and chosen ids

- **Format:** `YYYYMMDD-HHMMSS-xxxx`, where the time is the injected `Clock`'s UTC time. The suffix is 4 characters drawn from a Crockford-style alphabet without `i`, `l`, `o` or `u`. The random source is injected, and production uses `secrets.choice`.
- **When an id is taken:** any of `<id>.sqlite`, `<id>.lock` or `<id>.log` exists. `.lock` is this change's claim file, and `.log` is `060`'s detached log.
  - A drawn id is re-drawn until it is free.
  - A reservation is simply one of those files, created exclusively.
- **Chosen ids:** `create_crawl(id=…)` accepts a chosen id when `<id>.sqlite` is absent. It creates the file with exclusive create, so two creators of the same id cannot both succeed.
  - `060`'s parent reserves an id by creating `<id>.log`, and the child creates the Crawl with that id.
- **Alternatives:**
  - **ULID or UUIDv7:** sortable, but not readable.
  - **Integers:** they collide when crawl files are copied between Workspaces.
  - **A host slug:** untrusted text in file names.

### D2. Opening crawl files

- **One engine per operation**, created with `NullPool`.
  - A `creator` calls `sqlite3.connect(<uri>, uri=True)`.
  - The URI is percent-encoded from the absolute path, which handles spaces, `#`, `?`, `%`, non-ASCII characters and drive letters. Readers add `mode=ro`.
  - The context manager disposes the engine, so no handle outlives the operation. This matters on Windows (the deletion scenario) and for the long-running MCP server.
- **Connection pragmas:**
  - `foreign_keys=ON`
  - `busy_timeout`: 30 s for the writer, 5 s for readers and control writes, after which the error is `crawl_busy`
  - `synchronous`: `NORMAL` in WAL mode, `FULL` in delete mode
- **Alternatives:**
  - **Cached engines.** Rejected: Windows would refuse to delete or rename the files, and long read transactions starve WAL checkpoints.
  - **`immutable=1` readers.** Rejected: unsafe while a Crawl is being written.

### D3. Journal mode

- **Two pure functions:**
  - `classify_location(path, mounts) -> "local" | "network"`:
    - It checks UNC prefixes (`\\server\share`, `\\?\UNC\`) as plain strings.
    - Otherwise it finds the longest matching mount point in `mounts` and reports `network` when the Windows options contain `remote`, or when the filesystem type is in the network set.
  - `choose_journal_mode(setting, location) -> (mode, warning | None)`.
- **The mount table** is read only at the edge, through `psutil.disk_partitions(all=True)`. Tests pass literal mount data to the pure functions, so no system call is faked.
- **The integration test** runs on Windows through the admin share `\\localhost\C$`, which is a real UNC path. It is skipped when the share is not reachable.
- **Defensive fallback:** after asking for WAL, the store checks that `PRAGMA journal_mode=WAL` returned `wal`. If it did not, it falls back to `delete` with the same warning. No scenario covers this, because no test can make SQLite refuse.
- **The `[store]` settings table** is registered through `010`'s registry.
- **`080`'s doctor** calls the same two functions.
- **Alternatives:**
  - **Trust the pragma alone.** Rejected: SQLite accepts WAL on SMB shares, where it is unsafe.
  - **Per-OS ctypes calls or `/proc/self/mountinfo` parsing.** Rejected: more code for the same answer.

### D4. The transactional writer

- **API:**
  - `CrawlWriter.run(unit) -> T` is thread-safe and blocking. `await CrawlWriter.run_async(unit)` serves event-loop callers.
  - A unit is `Callable[[Connection], T]`. The writer runs units one at a time, on its own thread, in submission order, inside one open transaction.
- **Atomic units:** each unit runs inside `SAVEPOINT unit`.
  - On success the savepoint is released.
  - On an exception the writer rolls back to the savepoint, and the exception is raised to that unit's caller. Earlier and later units are unaffected.
- **Commits:** the writer commits after 500 units, 1 s after the first uncommitted unit (measured with the injected `Clock`'s `monotonic()`, which the writer checks every 50 ms and after each unit), on `flush()`, and on `close()`.
  - `close()` commits, runs `wal_checkpoint(TRUNCATE)`, joins the thread and releases the claim.
- **Reads inside units** see every earlier unit's effects, because they share the transaction. `020`'s frontier can therefore take the next URL and mark it in a single unit.
- **Backpressure:** the submission queue is bounded at 50,000 units, and `run` blocks when the queue is full.
- **Alternatives:**
  - **Row batches without units.** They cannot express the frontier's read-then-update steps.
  - **One transaction per unit.** Too slow.
  - **aiosqlite.** It is a thread anyway, plus a second API.
  - **Writing on the event loop.** It blocks crawling.

### D5. The writer claim

- **The claim is `filelock.FileLock` on `<id>.lock`**, taken with `timeout=0`. Failure to take it means `crawl_locked`.
- **The OS releases the lock when the process dies**, including SIGKILL and TerminateProcess.
- **The lock file itself stays behind.** It is harmless, and `060`'s `crawls rm` deletes it.
- **Liveness for `060`:** a non-blocking attempt to take the claim tells whether the writer is alive.
- **Alternatives:**
  - **A lock inside SQLite.** SQLite locks last one transaction, not a process lifetime.
  - **A PID file.** PIDs are reused, and nothing releases the file automatically.
  - **Byte-range locks on the database file.** POSIX `fcntl` locks are per process, so they would clash with SQLite's own locks on the same file.

### D6. The two exceptions to "one writer"

- **Control writes:**
  - A table is a control table when its Core definition carries `info={"control": True}`.
  - `write_control(crawl, table, values)` opens a read-write connection *without* the claim, with a 5 s busy timeout. An SQLite authorizer denies every write to any other table.
  - This change defines no control table. `060`'s `control_requests` is the first.
  - The positive scenario uses a control table that the test creates in its crawl file, flagged through the same `info` mechanism.
- **Recording `interrupted`:**
  - `check_writer(crawl) -> Liveness(alive, recorded)` tries the claim without blocking.
  - When the claim is free and `state` is `running`, it sets `interrupted` under the claim, then releases it.
  - A read-only file yields `alive=False, recorded=False`, and `060` turns that into its `state_not_recorded` warning.
- **Why only these two:** stopping a Crawl and noticing a dead one must work while no writer is running, or while another process is writing. Everything else goes through the writer.

### D7. Schema versions and migrations

- **Alembic runs in-process.**
  - A `Config` object points `script_location` at `spider.store:migrations`, so no `alembic.ini` is needed at runtime.
  - The version table is `_alembic_version`, and `render_as_batch=True`.
  - `transaction_per_migration=False`: one transaction wraps the whole upgrade, together with `crawl.schema_version` and `PRAGMA user_version`.
  - It runs under the writer claim, inside `BEGIN IMMEDIATE`.
- **Waiting for the claim:** an opener that finds an old file waits up to 5 s for the claim, and re-reads the version each time it tries.
  - If another process has already upgraded the file in the meantime, the opener goes on.
  - If the file is still old when the wait ends, the opener fails with `crawl_busy`.
- **New files** are created with `metadata.create_all()` plus a stamp at the head revision. A guard proves that "upgrade from the first revision" and "create_all" produce the same schema.
- **Decision on open**, reading `user_version` and the revision without the ORM:

  | Condition | Result |
  |---|---|
  | file version > tool version | `crawl_schema_too_new` |
  | unknown revision | `crawl_schema_unknown` |
  | revision behind the head | upgrade |
  | otherwise | open |

  The `crawl` columns `id`, `schema_version`, `started_at` and `tool_version` never change, so every tool version can identify every crawl file.
- **Version policy:**
  - `schema_version` stays `1` through pre-release development. The v0.1 release squashes the chain into the first public revision.
  - After v0.1, every released schema change adds 1 to `schema_version`.
  - Development files from before the squash get `crawl_schema_unknown`.
- **Tests:**
  - They inject revision chains through the runner's `script_location` parameter: a two-step chain for the upgrade, and a chain whose step raises for `crawl_migration_failed`.
  - A guard asserts that the chain has exactly one head. A change that adds a migration rebases it onto the current head before merging.
- **Alternatives:**
  - **Hand-written SQL scripts.** ADR-0003 chose Alembic.
  - **Copying into a fresh schema on every upgrade.** Slow for crawl files that run to gigabytes.

### D8. Schema metadata, `spider schema` and `docs/schema.md`

- **Descriptions** come from `Table(comment=…)` and `Column(comment=…)`. `format`, `values`, `control` and the adding change's number (`info={"change": 15}`) come from `info`.
- **Custom column types:**
  - `UtcTimestamp`: TEXT `YYYY-MM-DDTHH:MM:SS.sssZ`
  - `JsonText`: TEXT, encoded with orjson
  - `Bool01`: INTEGER
- **Order:** `spider schema` sorts tables by `(change number, position within the change)`, so the order does not depend on which change was merged first.
- **Its result** is `010`'s paging envelope, with `schema_version` as the first key. It uses `010`'s in-memory pager.
- **`docs/schema.md` is written by hand**, one `## Table \`<name>\`` section per table:
  - a description paragraph
  - a pipe table `| Column | Type | Null | Key | Format | Values | Description |`

  The store contract test parses it and requires equality with `spider schema --limit 1000`.
- **No schema-first slices (G16):**
  - The contract test is written first, over an empty schema.
  - After that, every slice that adds a table or column updates `docs/schema.md` in the same commit, so the contract test is never red between commits.
- **Convention tests** run over `spider schema`, so every later table is checked automatically.
- **Alternatives:**
  - **Generating `docs/schema.md` from code.** The contract test would then be tautological, and docs/testing.md forbids auto-accepted snapshots.
  - **Table order by merge order.** It would depend on the order of parallel merges.

### D9. Redaction

- **One pure function,** `redact(argv, config, secrets) -> (argv, config)`. `secrets` maps each flag and setting to its form:

  | Form | Example |
  |---|---|
  | `whole` | `--auth ***` |
  | `header` | `Name: ***` when the name is sensitive |
  | `url` | `user:***@host` |

- **Where the forms come from:** a Command declares them in its option metadata, `secret="whole" | "header" | "url"`. This is `010`'s `secret` attribute, refined here.
- **Sensitive header names:** `Cookie`, and any name containing `auth`, `token`, `secret`, `key` or `password`, ignoring case. Other headers stay readable, so a recorded config still reproduces a Crawl.
- **Who calls it:** `create_crawl` calls it before anything is written, and `060` calls it for `crawl_runs.command_argv`.
- **Secrets in `spider.toml`** are allowed. Resume re-reads them from `spider.toml`, and asks for secret flags again (`060`).
- **Alternatives:**
  - **Redacting every header value.** Safe, but it loses the reproducibility of harmless headers such as `Accept-Language`.
  - **Refusing secrets in `spider.toml`.** Overruled by G8.

### D10. `--crawl` (`CrawlOpt`)

- `CrawlOpt` is the reusable global option, with the default `latest`. It calls `resolve_crawl(workspace, ref)` and maps its errors to the codes and exit codes of the "Crawl store diagnostics" requirement.
- **Resolution:**
  - Only `<id>.sqlite` files count as Crawls.
  - `latest` sorts by id, and breaks ties between ids of the same second with `crawl.started_at`.
  - A broken newest file is reported, never skipped, so an agent never reads an older Crawl without knowing it.
- **The CLI scenarios** use an example Command that reads a Crawl, registered on `010`'s fixture app. The real consumers arrive in `050`, `060` and `070`.

## Test seams

Seams from docs/testing.md used by this change:
- **CLI (1):**
  - `spider schema` and its entry in `spider commands`
  - `CrawlOpt`, through the example Command
  - the `[store]` template and validation, through `spider init`
- **Services and store API (2):**
  - `create_crawl` and `resolve_crawl`
  - the metadata
  - `CrawlWriter`, the claim, `write_control` and `check_writer`
  - reading, and upgrades

  These run on real SQLite files in `temp_workspace`, with real subprocesses from `tests/support/store_worker.py`, killed with `Popen.kill()` (SIGKILL on POSIX, TerminateProcess on Windows).
- **Pure-logic modules (4):**
  - the id format, including a hypothesis property
  - `classify_location` and `choose_journal_mode`
  - `redact`
- **Store contract (6):** `spider schema --limit 1000` against `docs/schema.md`, and the convention checks.

Test doubles:
- **The clock (`FakeClock`):** the writer's commit timer and the ids.
- **Randomness:** an injected suffix source for the id scenarios. docs/testing.md's Rules name randomness as a system boundary, but its list of boundary doubles does not (see Open Questions).
- **No file-system fakes:**
  - An unwritable data folder is a real `H/.spider` that is a file.
  - A read-only crawl file uses the real read-only attribute.
- **Extension points, not doubles:**
  - test migration chains
  - a test control table
  - the example `--crawl` Command

No new seam is introduced. The store API is seam 2.

## Risks / Trade-offs

- **Network filesystem detection misses FUSE mounts or cloud-sync folders.**
  - `store.journal_mode` overrides it, and `080`'s doctor shows the detected mode.
- **OS file locks can be unreliable on some network filesystems.**
  - Documented. WAL is off there anyway.
- **The WAL grows while a reader holds a long read transaction.**
  - Readers are opened per operation.
  - The writer checkpoints with `TRUNCATE` on close.
- **The timing scenarios (the 5 s busy wait, kills) are slow.**
  - The commit timer uses `FakeClock`, so only the busy test and the subprocess tests take real seconds. Those are marked `slow`.
- **An upgrade on read surprises a user whose file is shared or read-only.**
  - The warning `crawl_migrated` says what happened, `crawl_not_writable` explains a refusal, and `docs/crawl-store.md` covers both.
- **The sensitive-header heuristic can miss a custom secret header,** for example `X-Session: …`.
  - Such a header can be declared as a `whole` secret by the owning flag (`022`).
- **This change has about two dozen requirements.**
  - `openspec archive` prints a non-blocking "consider splitting" notice for changes with more than 10 deltas.

## Migration Plan

This is the first store version, so there is nothing to migrate. Before the v0.1 release, the development migration chain is squashed into one revision, which becomes the public schema version 1 (D7).

## Interface points for later changes

- **Tables:**
  1. In the slice that first needs a table or column, add it to `docs/schema.md` and to the Core metadata together. Use `info={"change": <n>}`, and give every table and column a comment.
  2. Add one Alembic revision on the current head.
  3. Follow the conventions, with NULL for "not measured".
- **Writing:** all Crawl data goes through `CrawlWriter` units. `020` adds `crawl.scope`, `crawl.stop_reason` and `crawl.warnings`.
- **States:**
  - `020` sets `running`, then `completed` (with `completed_at`), `stopped` (with `stop_reason`: `max_urls`, or `interrupt` for Ctrl+C with exit code 130) or `failed` (an unreachable Seed, exit code 8).
  - `060` uses `check_writer` to record `interrupted`, and resumes `stopped`, `interrupted` and `failed` Crawls.
- **Control:** `060` defines `control_requests` with `info={"control": True}`, and writes it with `write_control`.
- **Ids:** `060` reserves `<id>.log`, then creates the Crawl with that chosen id. `crawls rm` deletes `.sqlite`, `-wal`, `-shm`, `.lock` and `.log`.
- **Secrets:** a Command declares `secret="whole" | "header" | "url"` on its options. `022` declares its flags, including `--header` as `header` and `--proxy` as `url`. `060` redacts `crawl_runs.command_argv` with `redact`.
- **Reading:** query Commands use `CrawlOpt`. `050` adds the crawl id to its cursor fingerprint.
- **`080`:** doctor calls `classify_location` and `choose_journal_mode`.

## Open Questions

- docs/testing.md allows mocking randomness in its Rules, but its list of boundary doubles omits randomness. This change injects the id's random source to make the collision scenarios deterministic. Please confirm, or the three collision scenarios become a property test over many ids.
- Should `spider schema` show which change added each table, for example `added_by: "015"`? It is additive, and not needed by any scenario.
