# The crawl store

How OpenLinx stores each Crawl. The spec is [openspec/specs/crawl-store/spec.md](../openspec/specs/crawl-store/spec.md), and the tables are documented in [schema.md](schema.md). Terms follow [CONTEXT.md](../CONTEXT.md).

## Crawl files

Each Crawl is one SQLite file in the `crawls/` folder of the Workspace's data folder ([workspace.md](workspace.md)):

```
~/work/shop/.openlinx/crawls/20260927-140312-k3f9.sqlite    a Crawl of the local Workspace ~/work/shop
~/.openlinx/crawls/20260927-140312-k3f9.sqlite              a Crawl of the global Workspace
```

- The file name is the crawl id followed by `.sqlite`.
- The file holds everything the Crawl recorded, with the public schema of [schema.md](schema.md), so it can be copied, archived or attached to a bug report on its own.
- Every new file is built from the schema the tool declares, and a test checks that its tables and columns are exactly the documented ones.

## Crawl ids

A crawl id is the Crawl's UTC start time and 4 random characters:

```
20260927-140312-k3f9
YYYYMMDD-HHMMSS-xxxx
```

- **Sortable:** ids sort by start time, to the second, so `ls` lists Crawls in the order they started.
- **The random characters** come from `0123456789abcdefghjkmnpqrstvwxyz`. It leaves out `i`, `l`, `o` and `u`, so an id read aloud or copied by hand is not mistaken for another.
- **Never a taken id:** an id is taken when its crawl file exists. A new Crawl whose drawn id is taken draws new random characters until the id is free.
- **Two processes cannot get the same id.** The crawl file is created exclusively, so when two processes draw the same id in the same second, only one of them creates the file and the other draws again.

## Selecting a Crawl

Every Command that reads a Crawl takes the global flag `--crawl`, next to `--workspace`:

| Value | Selects |
|---|---|
| `latest` (the default) | the Crawl of the Workspace that started last, whatever its state |
| a crawl id, such as `20260927-140312-k3f9` | the Crawl with that id in the Workspace |
| a path: a value that contains `/` (or `\` on Windows) or ends in `.sqlite` | that crawl file, from any folder; a relative path is taken from the current folder. The Crawl is the one its `crawl` row names, whatever the file is called, so a copied or renamed file works |

- **Latest** is read from the ids, which start with the start time. Among ids of the same second, the later `crawl.started_at` wins, and then the greater id, so the choice is always the same. A `running` Crawl can be the latest.
- **Only crawl files are Crawls.** Only files named `<id>.sqlite` in `crawls/` count; any other file there is ignored.
- **A broken file is reported, never skipped.** The selected file is read before the Command uses it. When the newest file is not a readable crawl file, `latest` fails with `crawl_file_invalid` naming it, instead of quietly reading an older Crawl.
- **Selecting creates no folder and no crawl file:** no data folder, no `crawls/` folder and no `.sqlite` file, even in a global Workspace that has none yet. Reading an existing crawl file may leave SQLite's own `-wal` and `-shm` companions next to it, because a reader in WAL mode needs the shared-memory file. They are part of that crawl file, never Crawls of their own.

| Code | Exit code | When |
|---|---|---|
| `no_crawls` | 4 | the Workspace has no Crawl; the hint says how to start one with `linx crawl` |
| `crawl_not_found` | 4 | no Crawl in the Workspace has the given id, or no file exists at the given path (`details.file`) |
| `crawl_file_invalid` | 6 | the selected file is not a readable crawl file, or a file selected by id or `latest` holds another id (`details.expected_id` and `details.found_id`); `details.file` names it |
| `invalid_value` | 2 | the value is not `latest`, a crawl id or a path |

## The data folder

Storing a Crawl needs no `linx init` first. Creating a Crawl creates whatever is missing of the data folder, as `linx init` would:

| Created | When |
|---|---|
| `.openlinx/` | the data folder is missing |
| `.openlinx/.gitignore` | it is missing; it makes git ignore the crawl data |
| `.openlinx/crawls/` | it is missing |

- **No settings file.** Creating a Crawl never writes `openlinx.toml`. Only `linx init` does.
- **The global Workspace.** When no local Workspace is found, the Crawl goes to `~/.openlinx/crawls/`, and `~/.openlinx/` is created when it is missing.
- **An unwritable data folder** fails with `workspace_not_writable` (exit code 7) before anything is crawled. `details.path` names the path that failed, for example `~/.openlinx` when it is a file instead of a folder, or the new crawl file when `crawls/` does not allow creating files. A permissions problem never shows up as a traceback.

## What a Crawl records about itself

Every crawl file has a one-row table `crawl` with the Crawl's metadata and a table `seeds` with its Seeds. [schema.md](schema.md) documents every column; in short:

| Recorded | Columns |
|---|---|
| what was crawled, and how | `crawl_mode` (`spider`, `list` or `sitemap`), `section_crawl`, and the Seeds in `seeds`, in the order given (`position` 1, 2, …) |
| where it stands | `state`, `stop_reason` (why a `stopped` or `failed` Crawl ended), `started_at`, `completed_at`, and `warnings`, the Crawl's warnings over its whole life |
| what it may crawl | `scope`, the resolved Scope |
| how it was started | `command_argv`, `cwd`, `settings_file`, `config` |
| what made the file | `tool_version`, `schema_version` (also SQLite's `user_version`), `journal_mode`, `python_version`, `platform` |

- **Counts are not recorded while a Crawl runs.** No column that the Crawl writes holds the number of URLs, Pages or Issues: they are counted from the tables that hold them, so they can never disagree. A value derived from the stored rows, such as a score, is stored only by a pass that runs after the Crawl, in a derived column.
- **`started_at`** is the same instant as the time in the crawl id, read once when the Crawl is created.
- **`settings_file`** is the `openlinx.toml` the settings were read from, or NULL when there was none. `config` holds the settings the Crawl ran with, with every table and key, so the file says how it was made even when `openlinx.toml` changes later.
- **The environment stamp** (`python_version` and `platform`) helps when a crawl file is attached to a bug report.

## Secrets are never recorded

`command_argv` and `config` record how a Crawl was started, so a token or a proxy password given to it would end up in a file that is meant to be shared. Creating a Crawl redacts them first, before anything is written: no part of the crawl file holds a secret.

- **What is secret** is declared once, where a setting or an option is defined:
  - a setting marked secret on its settings table, such as a token, and every option that maps to it
  - an option that maps to no setting and is marked secret itself

  `linx commands` shows `"secret": true` on such options. A secret option has only long names, such as `--token`, so the attached short form `-tVALUE` never carries a secret.
- **Where:** the value after a secret flag, in both the `--flag value` and the `--flag=value` forms, and a secret setting's value in `config`, wherever it came from: the flag, `openlinx.toml` (secrets are allowed there) or a default. An unset secret stays `null`.
- **The two shapes of a redacted value:**

  | Secret value | Recorded as |
  |---|---|
  | a URL with a password, such as `http://ann:s3cret@proxy.test:8080` | the same URL without its password: `http://ann:***@proxy.test:8080` |
  | anything else, such as `s3cret` | `***` |

  A URL keeps its scheme, user, host, port and path, so a recorded proxy still says which proxy was used.

## Crawl States

`state` holds one of the Crawl States, as [CONTEXT.md](../CONTEXT.md) defines them:

| State | Meaning |
|---|---|
| `running` | a process is crawling, or was when it last wrote the file |
| `stopped` | paused before its end, resumable |
| `completed` | it ran to the end |
| `failed` | it could not continue, resumable |
| `interrupted` | its process died without recording an end, resumable |

The Crawl Service continues a `stopped` or `failed` Crawl (see [Continuing a Crawl](crawling.md#continuing-a-crawl)); `060-add-crawl-control` gives it the `linx resume` Command.

- A new Crawl starts as `running`.
- `completed` is final. A continue takes a `stopped` or `failed` Crawl back to `running` and clears its `stop_reason`.
- `completed_at` is set when the state becomes `completed`, and is NULL in every other state. A `stopped` or `failed` Crawl has no completion time.
- A `running` state does not prove that a process is still crawling: a process that was killed leaves it behind. Telling the two apart is `060-add-crawl-control`'s job, which records such a Crawl as `interrupted`.

## Writing a Crawl

Creating a Crawl writes its file, its `crawl` row and its Seeds in one transaction. Everything written after that goes through the Crawl's writer, in **units of work**.

- **A unit** is a function that gets a database connection and may insert, update and read rows. It returns a value to its caller, for example the next URL to fetch.
- **One at a time, in order.** The writer runs units on its own thread, one at a time, in the order they were submitted. Units can come from several threads, or from an event loop without blocking it.
- **One open transaction.** Every unit sees what the units before it wrote, committed or not, so a unit can read a row and update it in one step.
- **Atomic units.** A unit that fails leaves no change: its writes are rolled back, its error reaches its caller, and the units before and after it are unaffected. That holds for Ctrl+C inside a unit too. A unit that fails never runs again.
- **When it commits:**

  | Trigger | |
  |---|---|
  | 500 units since the last commit | the batch |
  | 1 second after the first unit since the last commit | the timer, checked after each unit and every 50 ms while idle |
  | a unit failed | the replay commit, described below |
  | `flush()` | at once, before `flush()` returns |
  | `close()` | everything still open |

  A Crawl drives the writer from its event loop and holds `loop_deadline()` while it runs. Then the 1-second timer runs on the loop's clock, from the first unit that `submit_async` or `run_async` gave after the last commit, and the writer's own thread commits only at 500 units, a flush or the close. The sync `submit` and `run` are refused with `RuntimeError("inside a Crawl use submit_async / run_async")`, since no sync call wakes the loop's timer: a post-crawl pass gets a `PassWriter`, which has only the async calls. Once the block ends, the writer's own timer and its sync calls are back.

- **The replay commit.** Units run without a savepoint each, which makes a batch faster. When a unit fails, the writer rolls back the whole open transaction, runs the units before it again, in order, and commits them at once. Only then does the failing unit's caller get its error. If that commit fails, the caller still gets the unit's own error, and the writer ends as after any failed commit.
- **Units may run again.** Because of the replay, a unit may run a second time before it is committed. A unit therefore:
  - has no effect outside the writer's connection: no I/O, no shared state, and nothing reported from inside the unit
  - does not change its input
  - computes its writes from its input and what it reads on the connection, so its second run writes what its first run wrote: no clock, randomness or counter of its own
  - returns a value: `None`, a number, a `str`, a tuple of these, or a frozen dataclass, never a float `NaN`, which never equals itself

  The replay checks what it can: a unit that raises, returns a different result or changes a different number of rows when it runs again ends the writer with no commit, because its caller already holds the first result. The failing unit's caller still gets its own error; later callers get `CrawlWriterClosedError`, caused by a `CrawlWriterReplayError` that names the unit and what differed. A file-level error inside a unit, such as a full disk, usually meets the replay again, so it ends the writer too. No test can check the contract for every unit, so the review of every change that adds units checks it.
- **Waiting for a unit, or submitting it.**
  - `run(unit)`, or `await run_async(unit)`, returns the unit's result once it has run, which may be before its commit.
  - `submit(unit)` returns a `concurrent.futures.Future` at once, and `await submit_async(unit)` an `asyncio.Future` bound to the caller's event loop, whose callbacks run on that loop. The Future holds the unit's result after the commit that makes it durable, the unit's own error if it fails, or the commit's error if that commit fails. Its callbacks run on the writer thread, so like `on_commit` they must be quick, and they cannot hand the writer a unit.
  - Both kinds of unit run in one order.
- **What an outcome means:**

  | Outcome | Means |
  |---|---|
  | `run()` or `run_async()` returns | the unit ran; a crash before the next commit loses it |
  | `flush()` returns | every unit before it is committed |
  | a submitted unit's Future holds its result | the unit is committed |

- **The window.** At most 2,000 submitted units wait for their commit at once, four batches' worth, so memory stays bounded. A submit beyond that waits until a commit frees room, and `submit_async` waits without blocking the event loop. Units handed over with `run()` take no room. A failing submitted unit frees its room once the replay commit, if any, is done.
- **Cancelling** a submitted unit's Future does not withdraw the unit: `cancel()` returns `False`, and the unit runs and is committed as if nothing had happened. Cancelling the Future of `submit_async` only drops the outcome.
- **A failed commit** ends the writer. The caller of the job in hand and every submitted unit of that commit get its error, `crawl_busy` for a busy file. When the replay commit is the one that fails, or a unit runs again differently, the failing unit's caller still gets its own error, and the units that ran again get the error that ended the writer. Every unit still queued, every submit still waiting for room, and every unit handed over later fail with `CrawlWriterClosedError`.
- **Watching commits.** An optional `on_commit` callable, given when the writer is opened, is called on the writer thread after each commit with the number of units that commit made durable, for progress and metrics. It must be quick, and an error it raises ends the writer like a failed commit.
- **What a crash loses.** A process that is killed, even with SIGKILL or TerminateProcess, loses at most the units since the last commit: up to 500 units, or about a second of work. Committed units survive, and the file stays sound: `PRAGMA integrity_check` returns `ok`. Tests kill a real writer process to check both.
- **The write check.** Opening the writer first runs a write that it rolls back. A crawl file that cannot be written, for example one with the read-only attribute, fails at once with `crawl_not_writable` (exit code 7) and `details.file`, before anything is crawled, and the file is left unchanged.
- **One writer per Crawl.** Until `060-add-crawl-control`, only the process that creates a Crawl writes it, because a Crawl cannot be resumed or detached yet. `060` adds a claim on the file when a second process can write.
- **A busy file.** When another connection holds the crawl file, the writer waits up to 30 seconds, on opening, when it starts a transaction or while a unit runs, then fails with `crawl_busy` (exit code 5) and `details.file`. In WAL mode only another writer can hold it that long; in rollback-journal mode a long read can too.
- **After `close()`,** the writer accepts no more units: a unit submitted then fails at once. Closing twice is harmless.

## Reading a Crawl

Commands that only read a Crawl open its file read-only, for one operation at a time:
- **Nothing changes.** Reading leaves the crawl file's bytes as they were, and a write through a reader fails with SQLite's read-only error.
- **Files are released.** Each read closes its connection when it ends, so even a process that keeps running, such as the MCP server, holds no handle to the file: on Windows another process can delete it right after a read. SQLite's `-wal` and `-shm` companions may stay next to it.
- **Reading while a Crawl is written.** In WAL mode, the default on local disks ([the journal mode](#the-journal-mode)), a reader sees every committed row while another process writes, and is not held up by the write (only by SQLite's brief recovery after a killed writer). In rollback-journal mode a write shuts readers out: a reader waits up to 5 seconds, then fails with `crawl_busy` (exit code 5) and `details.file`. `--crawl` resolution reads the same way.
- **Right after a killed writer, on Windows.** While the process of a killed writer is still exiting, it can still hold the crawl file's `-shm` companion; since SQLite 3.50 that shows up as a disk I/O error. Opening the file waits for it like for a lock, 5 seconds for a reader and 30 for the writer, then fails with `crawl_busy`. The file itself is sound.

## The journal mode

A new crawl file gets its SQLite journal mode once, when it is created, and `crawl.journal_mode` records it. The setting `store.journal_mode` in the Workspace's `openlinx.toml` chooses it with the file's location:

| `store.journal_mode` | Local disk | UNC path |
|---|---|---|
| `"auto"` (the default) | `wal` | `delete`, with the warning `store_wal_unavailable` |
| `"wal"` | `wal` | `wal`, with no warning |
| `"delete"` | `delete` | `delete` |

- **WAL** (write-ahead logging) lets a Command read a Crawl while it is written. It relies on shared memory between processes, which network file systems do not provide safely, so SQLite advises against WAL on them.
- **A UNC path** is a data folder whose path starts with `\\` or `//`, such as `\\fileserver\share\site\.openlinx`, including `\\?\UNC\…` paths; the drive forms `\\?\C:\…` and `\\.\C:\…` are local. Only the path is read; nothing is asked of the system. There `"auto"` falls back to a rollback journal (`delete`) and warns with `store_wal_unavailable`, whose `details.path` names the data folder. In that mode a write shuts readers out (see [Reading a Crawl](#reading-a-crawl)).
- **Other network folders,** such as a mapped drive (`Z:`) or an SMB or NFS mount, are not detected in v0.1, so they get WAL. Choose the rollback journal for them yourself:

  ```toml
  [store]
  journal_mode = "delete"
  ```

  v0.2 plans to detect them from the system's mount table.
- **`"wal"` on a UNC path** turns the fallback off, for a share known to support WAL safely.
- **Durability:** WAL files commit with `synchronous=NORMAL`: a commit survives a killed process, and a power cut may lose the last commits but leaves the file sound. Rollback-journal files commit with `synchronous=FULL`.
- **The writer's connection settings.** The writer's connection keeps temporary tables and indexes in memory (`temp_store = MEMORY`) and uses a page cache of up to 64 MiB (`cache_size = -65536`), a ceiling rather than an allocation. In WAL mode it also maps up to 256 MiB of the crawl file into memory (`mmap_size = 268435456`). In the store benchmark the three together cut a 2,000-Page write by a third. Creating a file and reading it keep SQLite's defaults, and no setting changes these values.
- **No memory mapping in rollback-journal mode.** That mode is chosen for network shares, where a mapped file is only as coherent as the share's client cache, so the writer sets `mmap_size = 0` there. It sets it explicitly, because the default is a build-time option of SQLite and is not 0 in every build.

## Describing the schema

`linx schema` lists the public tables and needs neither a Workspace nor a Crawl. For each table it gives:
- its columns, with their types, keys, formats and allowed values, and for a reference the `<table>.<column>` it points to
- its secondary indexes, each with its columns, whether it is unique, the condition of a partial index, and the query it serves

[schema.md](schema.md) documents the same tables. Tests keep both equal to the tables the tool declares, and a new crawl file equal to them too. The file itself refuses a value of another type, an enumeration value outside its list and a flag other than 0 or 1 ([ADR-0005](adr/0005-crawl-file-schema-conventions.md)).

## Schema versions

Every crawl file records its schema version twice: in `crawl.schema_version` and in SQLite's `user_version`, which a tool reads before any table.
- **A file from a newer tool is refused** with `crawl_schema_too_new` (exit code 6), with `details.file_schema_version` and `details.tool_schema_version`, and the file is left unchanged. The hint says to upgrade.
- **No upgrades before v0.1.** Until the first release the schema is not yet public and stays at version `1`: changes edit the tables directly, and a crawl file made by an earlier development build may fail as `crawl_file_invalid`; crawl again. From v0.1 on, every schema change adds 1 to the version and brings an in-place upgrade of older files.

## Not measured is NULL

A value that was not measured, or that does not apply, is stored as NULL, never as `0` or an empty string. `0` is a measured zero, and an empty string is a value that is present but empty. So `completed_at` is NULL while a Crawl runs, and `settings_file` is NULL when there was no settings file. Queries should test `IS NULL`, not `= 0` or `= ''`.

Two kinds of column are NULL for a while, and their descriptions say so:
- **A derived column,** whose description starts with `Derived: `, is written only by a pass that runs after the Crawl, and is NULL until that pass has run.
- **A column that a later release fills,** whose description starts with `Filled from v<major>.<minor>. `, is in the file from v0.1 and is NULL in every row until that release.
