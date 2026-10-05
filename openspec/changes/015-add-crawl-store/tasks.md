"Drive" means one TDD slice:
1. Write the failing test for the named scenario at the named seam, and watch it fail for the right reason.
2. Write only enough code to pass.
3. Run `uv run scripts/check.py`.
4. Commit. One task = one commit, and the message names the scenario.

Scenario names are the `#### Scenario:` titles in `specs/crawl-store/spec.md`. Seams are those of docs/testing.md:
- seam 1: CLI
- seam 2: services and the store API
- seam 4: pure logic
- seam 6: store contract

"Done when" says what must be true, not which helper to write. Names appear only where another change depends on them (design, Interface points).

**No schema-first slices:** a table or column is added in the slice whose scenario first needs it, and `docs/schema.md` is updated in the same commit, so the contract test from task 1.2 is never red between commits.

Test doubles:
- `FakeClock`
- an injected random source for the id suffix

A **guard** is a test for a scenario that earlier code already satisfies. It passes on its first run, and it is kept to pin the contract.

**The thin slice** (ROADMAP, Build order) needs groups 1–5: a crawl file, ids, metadata, the writer and `--crawl`, which is what `020` writes through and `050`'s `issues` reads through. Groups 6–9 widen the change after that, in any order. Group 9 (redaction) must land before `022`-min records the proxy variables, and all of them before the v0.1 release.

## 1. The schema contract and the first crawl file (slice)

- [x] 1.1 Setup: add `sqlalchemy` (2.x) to the runtime dependencies and to `tests/dependency_allowlist.txt`.

  Done when: `uv sync --locked` and `uv run scripts/check.py` pass, and the startup allowlist test (`tests/cli/test_startup.py`) still passes without allowing `sqlalchemy`.
- [x] 1.2 Drive "Documentation and declaration agree" at seam 6, over an empty declared schema.

  Done when: `docs/schema.md` exists with its conventions section and no tables, and a parser of it is compared with the schema service's description of the declared schema.
- [x] 1.3 Drive "Location of a crawl file" at seam 2.

  Done when: a Crawl with a given id can be created as `<data folder>/crawls/<id>.sqlite`, with a `crawl` table holding `id` only, and its `docs/schema.md` section. Since 2.3 the id is drawn, never given: the test gets `k3f9` from the injected random source, and chosen ids belong to `060`.
- [x] 1.4 **Guard:** "A new file matches the declaration" at seam 6. It passed at once: `create_crawl` builds the file from the declared tables with `create_all()`.

  Done when: a test compares `PRAGMA table_info` and `PRAGMA foreign_key_list` of every public table in a new crawl file with the declared schema, and fails on any extra public table or column.
- [x] 1.5 Drive "First Crawl in the global Workspace" at seam 2.

  Done when: creating a Crawl creates the data folder, its `.gitignore` and `crawls/` when they are missing, reusing `010`'s Workspace creation.
- [x] 1.6 **Guard:** "No settings file is created by storing a Crawl", at seam 2.
- [x] 1.7 **Guard:** "Unwritable data folder" at seam 2, with a real `H/.spider` that is a file. It passed at once: the data folder comes from `010`'s Workspace creation, which already maps the failed `mkdir` to `workspace_not_writable`.

  Done when: creation fails with `workspace_not_writable` and `details.path`, before any crawl file exists.
- [x] 1.8 Docs: start `docs/crawl-store.md` with crawl files and the data folder.
- [x] 1.9 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. New crawl ids (slice)

- [x] 2.1 Drive "Id from the start time" at seam 4, with `FakeClock` and an injected random source.
- [x] 2.2 **Guard:** "Character set" at seam 4, with a hypothesis property over start times and the system random source. It passed at once: 2.1 already draws from the suffix alphabet.
- [x] 2.3 Drive "A taken id is drawn again" at seam 2.

  Done when: creating a Crawl without an id draws until `<id>.sqlite` is free, and creates the file exclusively.
- [x] 2.4 Docs: add ids to `docs/crawl-store.md`.
- [x] 2.5 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. Crawl metadata and states (slice, seam 2)

- [x] 3.1 Drive "Metadata of a new Crawl".

  Done when: the `crawl` row holds `crawl_mode`, `section_crawl`, `state`, `started_at`, `completed_at`, `command_argv`, `cwd`, `settings_file` and `config`, through the shared timestamp, JSON and boolean column types, each with its `docs/schema.md` row.
- [x] 3.2 **Guard:** "Timestamp text".
- [x] 3.3 Drive "Seeds keep their order". Done when: the `seeds` table and its `docs/schema.md` section exist.
- [x] 3.4 Drive "Version stamp". The test reads `pyproject.toml` with `tomllib`. Done when: `tool_version`, `schema_version` and SQLite `user_version` are written, with their docs rows.
- [x] 3.5 Drive "Environment stamp". Done when: `python_version` and `platform` are written, with their docs rows.
- [x] 3.6 Drive "Completion time". Done when: setting the state sets `completed_at` only for `completed`.
- [x] 3.7 Drive "A stopped Crawl has no completion time".
- [x] 3.8 **Guard:** "A running Crawl has no completion time" and "No settings file", a pair.
- [x] 3.9 Drive "Local disk". Done when: new crawl files use WAL with `synchronous=NORMAL`, and `crawl.journal_mode` records it, with its docs row.
- [x] 3.10 Drive "A copied file opens by its path".

  Done when: a crawl file opens read-only by its path, through a percent-encoded `mode=ro` URI and an engine disposed after the operation.
- [x] 3.11 Drive "Unwritable crawls folder" at seam 2, with a real folder that denies creating files (its mode on POSIX, a deny ACL on Windows, where the read-only attribute does not protect a folder).

  Done when: any `OSError` other than `FileExistsError` from claiming or writing a crawl file becomes `workspace_not_writable` with `details.path`, so no permissions problem reaches an agent as a traceback.
- [x] 3.12 Docs: add the metadata, the Crawl States and the NULL rule to `docs/crawl-store.md`.
- [x] 3.13 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. The transactional writer (slice, seam 2)

- [x] 4.1 Drive "A unit sees the units before it". Done when: `CrawlWriter.run` runs units on a writer thread inside one open transaction.
- [x] 4.2 Drive "A unit updates a row of an earlier unit".
- [x] 4.3 Drive "A failing unit leaves no change". Done when: each unit is atomic, and its error reaches its caller.
- [x] 4.4 **Guard:** "Other units survive a failing unit". It passed at once: 4.3 rolls back only the failing unit's savepoint, inside the open transaction that commits the others.
- [x] 4.5 **Guard:** "Closing commits everything". It passed at once: 4.2 already made `close()` commit.
- [x] 4.6 Drive "Units wait for the batch" and "The 500th unit commits the batch", a trivial pair with `FakeClock` frozen.
- [x] 4.7 Drive "The timer commits", with `FakeClock.advance(1.0)`. Done when: the 1 s commit runs on the injected clock.
- [x] 4.8 Drive "A flush commits at once".
- [x] 4.9 Drive "A read-only crawl file", with the real read-only attribute.

  Done when: opening the writer runs a rolled-back write first, and fails with `crawl_not_writable` (exit 7) and `details.file`, leaving the file unchanged.
- [x] 4.10 Drive the connection pragmas of D2 at seam 2: every connection has `foreign_keys` on, the writer waits up to 30 s for a lock and readers 5 s. Mapping a busy reader to `crawl_busy` stays in 7.4.
- [x] 4.11 Drive concurrent callers at seam 2: units submitted from several threads run one at a time, and each caller's units run in the order it submitted them. `run_async` runs a unit from a real event loop made by `spider.aio.loop_factory`.
- [x] 4.12 Drive the writer's end at seam 2: `close()` can be called twice; a unit submitted after `close()` fails at once with a clear error; a unit that raises a `BaseException`, such as `KeyboardInterrupt`, rolls back like any failing unit, reaches its caller, and the writer keeps running. Done when: D4 records this behaviour.
- [x] 4.13 Docs: add units, commit triggers, the write check and "one writer by construction in v0.1" to `docs/crawl-store.md`.
- [x] 4.14 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Selecting a Crawl (slice, seams 2 and 1)

- [x] 5.1 Drive the idle timer of D4 at seam 2: with no unit submitted, `FakeClock.advance(1.0)` commits the open transaction.

  Done when: `CrawlWriter` takes an optional `on_commit` observer, called on the writer thread after each successful commit with the number of units it committed (`020` can use it for progress and metrics), and the test waits for it on a `threading.Event` with a hard timeout instead of running another unit.
- [x] 5.2 Drive "By id" at seam 2.
- [x] 5.3 Drive "Latest is the most recent start" at seam 2.
- [x] 5.4 **Guard:** "A running Crawl can be latest", at seam 2. It passed at once: `latest` reads the ids, never the state.
- [x] 5.5 Drive "Two Crawls in the same second" at seam 2. Done when: ties break by `started_at`, then by id.
- [x] 5.6 Drive "Only crawl files are Crawls" at seam 2. Done when: only files named `<id>.sqlite` count. The scenario's `.log` file passed at once, so a `notes.sqlite` in `crawls/` drove the id filter.
- [x] 5.7 Drive "No Crawls" at seam 2. Done when: `no_crawls` (exit 4) is declared in `spider.output.codes`, and its hint is built from `spider.naming`.
- [x] 5.8 Drive "Unknown id" at seam 2. Done when: `crawl_not_found` (exit 4) is declared.
- [x] 5.9 Drive "Malformed reference" at seam 2.
- [x] 5.10 Drive "Not a crawl file" at seam 2. Done when: `crawl_file_invalid` (exit 6) is declared, with `details.file`.
- [x] 5.11 Drive "A broken newest file is reported, not skipped" at seam 2.
- [x] 5.12 **Guard:** "Reading creates nothing" at seam 2. It passed at once: resolution only lists `crawls/` and opens files read-only, and the Workspace comes from `resolve_workspace`, which creates nothing.
- [x] 5.13 Drive "The flag defaults to latest" at seam 1, with an example Command that reads a Crawl on the test app.

  Done when: `--crawl` is a global option declared once in `spider.cli.options`, with the default `latest`, and resolving it imports the store only inside the Command's body.
- [x] 5.14 **Guard:** "The flag is described as global" at seam 1. It passed at once: `CrawlOpt` carries `OptionMeta(is_global=True)`, and `spider commands` already reports both from 010.
- [x] 5.15 **Guard:** "Unknown id on the command line" and "No Crawls on the command line" at seam 1, a trivial pair. Both passed at once: the runner of 010 maps every `SpiderError` to its exit code and stderr line.
- [x] 5.16 **Guard:** "A text file on the command line" and "A malformed value on the command line" at seam 1, a trivial pair. Both passed at once, for the reason of 5.15.
- [x] 5.17 Docs: add `--crawl latest|<id>|<path>` to `docs/crawl-store.md` and `docs/cli.md`.
- [x] 5.18 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green.

## 6. `spider schema` and the conventions (widening, seams 1 and 6)

Tasks 6.1–6.3 close the open questions of group 5's review (manager decisions A–C) before group 6's own work.

- [x] 6.1 **Guard:** "Companion files are not Crawls" at seam 2. It passed at once: only `<id>.sqlite` files are listed. Done when: `docs/crawl-store.md` says that selecting creates no folder and no crawl file, and that SQLite's `-wal` and `-shm` companions of an existing crawl file may appear (a WAL reader needs the shared-memory file; `immutable=1` stays rejected, D2). 7.6 still proves that a crawl file can be deleted after a read on Windows.
- [x] 6.2 Drive "A missing crawl file path" at seam 2. Done when: a path is checked for existence before the read-only open, and gives `crawl_not_found` (exit 4) with `details.file`; a file that exists but is not a crawl file stays `crawl_file_invalid`.
- [x] 6.3 Drive "A crawl file that holds another id" at seam 2. Done when: a Crawl selected by id or `latest` whose `crawl` row has another id fails with `crawl_file_invalid` and `details.file`, `details.expected_id` and `details.found_id`; a Crawl selected by path keeps the id of its row, whatever the file is named, pinned by a guard through `resolve_crawl`.
- [x] 6.4 Drive "One table" at seam 1.

  Done when: `spider schema [TABLE]` is the adapter of the schema service, registered with `@command_meta(name=...)` as a list Command, paged with `paginate` and `fingerprint`, and its JSON result starts with `schema_version`.
- [ ] 6.5 Drive "First tables" at seam 1. Done when: tables are ordered by the adding change's number, then by position within the change.
- [ ] 6.6 Drive "Columns of seeds" at seam 1.
- [ ] 6.7 Drive "Column formats" at seam 1.
- [ ] 6.8 Drive "State values are documented" at seam 1.
- [ ] 6.9 Drive "The next page" at seam 1.
- [ ] 6.10 Drive "Unknown table" at seam 1. Done when: `unknown_table` (exit 2) is declared, with `details.tables`.
- [ ] 6.11 **Guard:** "Internal tables are hidden" and "No Workspace needed", at seam 1.
- [ ] 6.12 **Guard:** "Names are snake_case" and "Descriptions are present", at seam 6. They check every later table automatically.
- [ ] 6.13 **Guard:** "Booleans are integers" and "Enumeration values are snake_case", at seam 6.
- [ ] 6.14 **Guard:** "Documentation and declaration agree", now through `spider schema --limit 1000` at seam 6.
- [ ] 6.15 Drive "Self-description of schema" at seam 1.
- [ ] 6.16 Drive "Global flags of schema" and "Default limit of schema" at seam 1, a trivial pair.
- [ ] 6.17 **Guard:** the startup allowlist test passes with `schema` registered: `spider --help` and `spider commands` load no `sqlalchemy`.
- [ ] 6.18 Docs: add "How to add a table" to `docs/schema.md` (docs rows and the declared table in the same slice, the conventions, no migration before v0.1). Add `spider schema` to `docs/cli.md`.
- [ ] 6.19 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.

## 7. Durability and reading across processes (widening, seam 2 with real processes)

- [ ] 7.1 Drive "A killed writer keeps committed units in a sound file". Done when: `tests/support/store_worker.py` exists, a subprocess that runs units, flushes on request and waits to be killed.
- [ ] 7.2 Drive "A killed writer loses uncommitted units".
- [ ] 7.3 Drive "Reading during a write in WAL mode".
- [ ] 7.4 Drive "Busy in rollback-journal mode", with a real process that holds an exclusive lock for 8 s. Mark the test `slow`.

  Done when: readers wait at most 5 s, then fail with `crawl_busy` (exit 5), including `--crawl` resolution, which until then reports a busy read as `crawl_file_invalid`.
- [ ] 7.5 Drive "Bytes are unchanged by reading" and "Writes through a reader fail", a trivial pair.
- [ ] 7.6 Drive "Deleting after a read on Windows", as a Windows-only test.
- [ ] 7.7 Drive "File from a newer tool" and "A refused file is unchanged", a trivial pair. Done when: `crawl_schema_too_new` (exit 6) is declared, with both versions in `details`.
- [ ] 7.8 Docs: add durability, reading during a Crawl and schema versions (no upgrades before v0.1) to `docs/crawl-store.md`.
- [ ] 7.9 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. Journal mode and the store setting (widening)

- [ ] 8.1 Drive "UNC path" at seam 4. Done when: the journal-mode choice is a pure function, and `store_wal_unavailable` is declared as a warning.
- [ ] 8.2 Drive "Local path" at seam 4.
- [ ] 8.3 Drive "Forced WAL on a UNC path" and "Forced rollback journal on a local path" at seam 4, a trivial pair.
- [ ] 8.4 Drive "The store setting in the template" and "An invalid store setting" at seam 1, a trivial pair.

  Done when: `[store]` is registered in `build_app` by its `"module:Class"` reference, and the table-rules test of `010` covers it.
- [ ] 8.5 Drive "Crawl on a UNC path on Windows" at seam 2. It runs through `\\localhost\C$` and is skipped when the share is not reachable. Done when: the warning reaches the Reporter with `details.path`.
- [ ] 8.6 Docs: add the journal mode, the UNC fallback, the `store.journal_mode` override for other network folders, and the v0.2 plan for the mount table to `docs/crawl-store.md`.
- [ ] 8.7 Review: run the code-review skill on group 8's commits, then refactor with the whole suite green.

## 9. Redaction (widening, before `022`-min)

- [ ] 9.1 Drive "Secret option with a separate value" at seam 4.
- [ ] 9.2 Drive "Secret option with a joined value" at seam 4.
- [ ] 9.3 Drive "A URL keeps everything but its password" at seam 4.
- [ ] 9.4 Drive "Secret setting" at seam 4.
- [ ] 9.5 **Guard:** "Other values are kept", at seam 4.
- [ ] 9.6 Drive "The secret is nowhere in the file" at seam 2.

  Done when: creating a Crawl redacts its command line and config before anything is written, with the secret flags and settings read from `010`'s declarations, never declared again.
- [ ] 9.7 Docs: add what is secret and the two shapes of a redacted value to `docs/crawl-store.md`.
- [ ] 9.8 Review: run the code-review skill on group 9's commits, then refactor with the whole suite green.

## 10. Wrap-up

- [ ] 10.1 **Guard:** "Store codes are self-described", at seam 1. Every code was declared by the slice that first raised it.
- [ ] 10.2 Docs:
  - `docs/architecture.md`: the store's public API (creating a Crawl, the writer, `--crawl` resolution, the schema service, redaction), the three-way schema check, and that `sqlalchemy` stays off the startup path
  - `CONTRIBUTING.md`: "Changing the crawl store schema": the declared table and `docs/schema.md` in the same slice; no migration before v0.1; from v0.1 on, a migration and a test from every published schema version
  - link `docs/schema.md` and `docs/crawl-store.md` from `README.md`
- [ ] 10.3 Review: run the code-review skill on group 10's commits and on the whole change, then refactor with the whole suite green.
