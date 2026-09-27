"Drive" means one TDD slice:
1. Write the failing test for the named scenario at the named seam, and watch it fail for the right reason.
2. Write only enough code to pass.
3. Run `uv run scripts/check.py`.
4. Commit. One task = one commit, and the message names the scenario.

Scenario names are the `#### Scenario:` titles in `specs/crawl-store/spec.md`. Seams are those of docs/testing.md:
- seam 1: CLI
- seam 2: the store API
- seam 4: pure logic
- seam 6: store contract

**No schema-first slices:** a table or column is added in the slice whose scenario first needs it, and `docs/schema.md` is updated in the same commit, so the contract test from task 1.2 is never red between commits.

Test doubles:
- `FakeClock`
- the injected id suffix source (see design, Open Questions)

Subprocess tests use `tests/support/store_worker.py`, killed with `Popen.kill()`.

A **guard** is a test for a scenario that earlier code already satisfies. It passes on its first run, and it is kept to pin the contract.

## 1. The schema contract and the first crawl file

- [ ] 1.1 Setup: add `sqlalchemy`, `alembic`, `psutil` and `filelock` to the runtime dependencies and to `tests/dependency_allowlist.txt`.

  Verify: `uv sync --locked` and `uv run scripts/check.py` pass.
- [ ] 1.2 Drive "Documentation and store agree" at seam 6, over an empty public schema.
  - Red: a parser for `docs/schema.md` that compares its tables with `spider schema --limit 1000`.
  - Green:
    - `docs/schema.md`, with its conventions section and no tables yet
    - a minimal `spider schema` returning `010`'s envelope over the registered tables
- [ ] 1.3 Drive "Location of a crawl file" at seam 2. Green:
  - `create_crawl` with a chosen id, which creates the file with exclusive create
  - the `crawl` table with `id` only, and its `docs/schema.md` section
- [ ] 1.4 Drive "First Crawl in the global Workspace" at seam 2. Green: create the data folder, its `.gitignore` and `crawls/` when they are missing.
- [ ] 1.5 **Guard:** "No settings file is created by storing a Crawl", at seam 2.
- [ ] 1.6 Drive "Unwritable data folder" at seam 2, with a real `H/.spider` that is a file. Green: `workspace_not_writable`.
- [ ] 1.7 Drive "A chosen id that has a crawl file is refused" at seam 2. Green: `crawl_id_taken`, registered with exit code 5.
- [ ] 1.8 Drive "A malformed chosen id is refused" at seam 2. Green: validate the id against its form, raising `invalid_value`.
- [ ] 1.9 **Guard:** "A chosen id is used", at seam 2. Only `<id>.sqlite` blocks a chosen id.
- [ ] 1.10 Docs: start `docs/crawl-store.md` with the crawl files, ids, reservations and chosen ids.
- [ ] 1.11 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. New crawl ids

- [ ] 2.1 Drive "Id from the start time" at seam 4, with `FakeClock` and an injected suffix source. Green: `new_crawl_id`.
- [ ] 2.2 Drive "Character set" at seam 4, with a hypothesis property over start times and the system random source.
- [ ] 2.3 Drive "An id with a crawl file is taken" at seam 2. Green: `create_crawl` without an id draws until the id is free.
- [ ] 2.4 Drive "An id with a log file is taken" and "An id with a lock file is taken" at seam 2, a trivial pair. Green: `.log` and `.lock` make an id taken.
- [ ] 2.5 Docs: add id generation to `docs/crawl-store.md`.
- [ ] 2.6 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. Crawl metadata and states (seam 2)

- [ ] 3.1 Drive "Metadata of a new Crawl". Green:
  - the `crawl` columns `crawl_mode`, `section_crawl`, `state`, `started_at`, `completed_at`, `command_argv`, `cwd`, `settings_file` and `config`
  - the `UtcTimestamp`, `JsonText` and `Bool01` types
  - their `docs/schema.md` rows
- [ ] 3.2 **Guard:** "Timestamp text".
- [ ] 3.3 Drive "Seeds keep their order". Green: the `seeds` table and its `docs/schema.md` section.
- [ ] 3.4 Drive "Version stamp". The test reads `pyproject.toml` with `tomllib`. Green: `tool_version`, `schema_version` and SQLite `user_version`, with their docs rows.
- [ ] 3.5 Drive "Environment stamp". Green: `python_version` and `platform`, with their docs rows.
- [ ] 3.6 Drive "Completion time". Green: `set_state`, which sets `completed_at` only for `completed`.
- [ ] 3.7 Drive "A stopped Crawl has no completion time".
- [ ] 3.8 **Guard:** "A running Crawl has no completion time" and "No settings file", a pair.
- [ ] 3.9 Drive "A copied file opens by its path". Green: opening by path with a percent-encoded `mode=ro` URI and a `NullPool` engine.
- [ ] 3.10 Docs: add the metadata, the Crawl States and the NULL rule to `docs/crawl-store.md`.
- [ ] 3.11 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. `spider schema` and the conventions (seams 1 and 6)

- [ ] 4.1 Drive "One table" at seam 1. Green: the TABLE argument, and the `schema_version` key before `total`.
- [ ] 4.2 Drive "First tables" at seam 1. Green: order by `info["change"]`, then by position within the change.
- [ ] 4.3 Drive "Columns of seeds" at seam 1. Green: the column descriptions.
- [ ] 4.4 Drive "Column formats" at seam 1. Green: `format` from `info`.
- [ ] 4.5 Drive "State values are documented" at seam 1. Green: `values` from `info`.
- [ ] 4.6 Drive "Unknown table" at seam 1. Green: `unknown_table` with `details.tables`.
- [ ] 4.7 **Guard:** "Internal tables are hidden" and "No Workspace needed", at seam 1.
- [ ] 4.8 **Guard:** "Names are snake_case" and "Descriptions are present", at seam 6. They check every later table automatically.
- [ ] 4.9 **Guard:** "Booleans are integers" and "Enumeration values are snake_case", at seam 6.
- [ ] 4.10 Drive "Self-description of schema" at seam 1. Green: `@command_meta` for `schema`.
- [ ] 4.11 Drive "Global flags of schema" and "Default limit of schema" at seam 1, a trivial pair.
- [ ] 4.12 Docs: add "How to add a table" to `docs/schema.md`: docs rows and the Core table in the same slice, then one Alembic revision on the head. Add `spider schema` to `docs/cli.md`.
- [ ] 4.13 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Selecting a Crawl (seams 2 and 1)

- [ ] 5.1 Drive "By id" at seam 2. Green: `resolve_crawl`.
- [ ] 5.2 Drive "Latest is the most recent start" at seam 2.
- [ ] 5.3 **Guard:** "A running Crawl can be latest", at seam 2.
- [ ] 5.4 Drive "Two Crawls in the same second" at seam 2. Green: the `started_at` tie-break.
- [ ] 5.5 Drive "A reservation is not a Crawl" at seam 2.
- [ ] 5.6 Drive "No Crawls" at seam 2. Green: `no_crawls`, registered with exit code 4.
- [ ] 5.7 Drive "Unknown id" at seam 2. Green: `crawl_not_found`.
- [ ] 5.8 Drive "Malformed reference" at seam 2.
- [ ] 5.9 Drive "Not a crawl file" at seam 2. Green: `crawl_file_invalid`, registered with exit code 6.
- [ ] 5.10 Drive "A broken newest file is reported, not skipped" at seam 2.
- [ ] 5.11 Drive "Reading creates nothing" at seam 2.
- [ ] 5.12 Drive "The flag defaults to latest" at seam 1, with an example Command that reads a Crawl on `010`'s fixture app. Green: `CrawlOpt`.
- [ ] 5.13 Drive "Unknown id on the command line" and "No Crawls on the command line" at seam 1, a trivial pair. Green: exit code 4, and the `spider crawl` hint.
- [ ] 5.14 Drive "A text file on the command line" and "A malformed value on the command line" at seam 1, a trivial pair.
- [ ] 5.15 Docs: add `--crawl latest|<id>|<path>` to `docs/crawl-store.md` and `docs/cli.md`.
- [ ] 5.16 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green.

## 6. Redaction (seams 4 and 2)

- [ ] 6.1 Drive "Secret flag with a separate value" at seam 4. Green: `redact` with the `whole` form.
- [ ] 6.2 Drive "Secret flag with a joined value" at seam 4.
- [ ] 6.3 Drive "A sensitive header keeps its name" at seam 4. Green: the `header` form.
- [ ] 6.4 Drive "Cookie header" and "Other headers are kept" at seam 4, a trivial pair. Green: the sensitive-name rule.
- [ ] 6.5 Drive "Proxy password" at seam 4. Green: the `url` form.
- [ ] 6.6 Drive "Secret setting" at seam 4.
- [ ] 6.7 Drive "Header setting" at seam 4.
- [ ] 6.8 Drive "The secret is nowhere in the file" at seam 2. Green: `create_crawl` redacts before anything is written.
- [ ] 6.9 Docs: add the three redaction forms and how a Command declares them to `docs/crawl-store.md`.
- [ ] 6.10 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.

## 7. The transactional writer (seam 2)

- [ ] 7.1 Drive "A unit sees the units before it". Green: `CrawlWriter.run`, with a writer thread and one open transaction.
- [ ] 7.2 Drive "A unit updates a row of an earlier unit".
- [ ] 7.3 Drive "A failing unit leaves no change". Green: `SAVEPOINT` per unit, and the error raised to its caller.
- [ ] 7.4 Drive "Other units survive a failing unit".
- [ ] 7.5 Drive "Closing commits everything". Green: `close()`.
- [ ] 7.6 Drive "Units wait for the batch" and "The 500th unit commits the batch", a trivial pair with `FakeClock` frozen. Green: the 500-unit commit.
- [ ] 7.7 Drive "The timer commits", with `FakeClock.advance(1.0)`. Green: the 1 s commit on the injected clock.
- [ ] 7.8 Drive "A flush commits at once". Green: `flush()`.
- [ ] 7.9 Drive "A killed writer leaves a sound file". Green: add `tests/support/store_worker.py`.
- [ ] 7.10 Drive "A killed writer keeps committed units".
- [ ] 7.11 Drive "A killed writer loses uncommitted units".
- [ ] 7.12 Docs: add units, commit triggers and durability to `docs/crawl-store.md`.
- [ ] 7.13 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. Claim, control writes, liveness and reading (seam 2, with real processes)

- [ ] 8.1 Drive "A second writer is refused". Green: `filelock` on `<id>.lock`, and `crawl_locked` with exit code 5.
- [ ] 8.2 Drive "A killed writer releases the Crawl".
- [ ] 8.3 Drive "Readers are not blocked".
- [ ] 8.4 Drive "Reading during a write in WAL mode". Green: new crawl files use WAL.
- [ ] 8.5 Drive "A control row is written while the Crawl is written", with a control table that the test creates and flags with `info={"control": True}`. Green: `write_control`.
- [ ] 8.6 Drive "A control write cannot change Crawl data". Green: the SQLite authorizer.
- [ ] 8.7 Drive "A dead Crawl is recorded as interrupted". Green: `check_writer`.
- [ ] 8.8 Drive "A live Crawl is left running".
- [ ] 8.9 Drive "A read-only file records nothing".
- [ ] 8.10 Drive "Bytes are unchanged by reading" and "Writes through a reader fail", a trivial pair.
- [ ] 8.11 Drive "Deleting after a read on Windows", as a Windows-only test. Green: engines disposed after every operation.
- [ ] 8.12 Docs: add the claim, the two exceptions and reading during a Crawl to `docs/crawl-store.md`.
- [ ] 8.13 Review: run the code-review skill on group 8's commits, then refactor with the whole suite green.

## 9. Journal mode and the store setting

- [ ] 9.1 Drive "UNC path" at seam 4. Green: `classify_location` over literal mount data.
- [ ] 9.2 Drive "Mapped network drive" and "Local drive" at seam 4, a trivial pair.
- [ ] 9.3 Drive "SMB share on macOS" and "Local filesystem on Linux" at seam 4, a trivial pair.
- [ ] 9.4 Drive "Automatic mode on a network location" at seam 4. Green: `choose_journal_mode`, and the warning `store_wal_unavailable`.
- [ ] 9.5 Drive "Forced WAL on a network location" and "Forced rollback journal on a local location" at seam 4, a trivial pair.
- [ ] 9.6 Drive "The store setting in the template" and "An invalid store setting" at seam 1, a trivial pair. Green: register `[store]` with `journal_mode`.
- [ ] 9.7 Drive "Local disk" at seam 2. Green: the `crawl.journal_mode` column and its docs row, and the mount table read through psutil.
- [ ] 9.8 Drive "Crawl on a UNC path on Windows" at seam 2. It runs through `\\localhost\C$` and is skipped when the share is not reachable.
- [ ] 9.9 Drive "Busy in rollback-journal mode" at seam 2, with a real process that holds an exclusive lock for 8 s. Mark the test `slow`. Green: the 5 s reader timeout, and `crawl_busy`.
- [ ] 9.10 Docs: add the journal mode, the network fallback and the `store.journal_mode` override to `docs/crawl-store.md`.
- [ ] 9.11 Review: run the code-review skill on group 9's commits, then refactor with the whole suite green.

## 10. Schema versions and upgrades (seam 2)

- [ ] 10.1 Setup, with two **guards**:
  - the in-process Alembic runner (design D7) and the baseline revision
  - Guard: a file upgraded from the first revision has the same schema as one made by `create_all`.
  - Guard: the revision chain has exactly one head.
- [ ] 10.2 Drive "Schema version after the upgrade", with a two-step test chain injected through `script_location`.
- [ ] 10.3 Drive "SQLite user_version after the upgrade".
- [ ] 10.4 Drive "Data survives the upgrade".
- [ ] 10.5 Drive "Upgrade warning". Green: `crawl_migrated`.
- [ ] 10.6 Drive "File from a newer tool" and "A refused file is unchanged", a trivial pair. Green: `crawl_schema_too_new`.
- [ ] 10.7 Drive "Unknown schema revision". Green: `crawl_schema_unknown`.
- [ ] 10.8 Drive "Failed upgrade step", with a test chain whose step raises. Green: a single-transaction upgrade, and `crawl_migration_failed`.
- [ ] 10.9 Drive "Read-only file". Green: `crawl_not_writable` with exit code 7.
- [ ] 10.10 Drive "No upgrade while another process writes", with `store_worker.py` holding the claim. Green: the 5 s wait for the claim, then `crawl_busy`.
- [ ] 10.11 Drive "Two processes open the same old file", with two real processes.
- [ ] 10.12 Docs: add schema versions and upgrades to `docs/crawl-store.md`. Add "Changing the crawl store schema" to `CONTRIBUTING.md`: rebase the revision onto the head, and keep `schema_version` at 1 before v0.1.
- [ ] 10.13 Review: run the code-review skill on group 10's commits, then refactor with the whole suite green.

## 11. Wrap-up

- [ ] 11.1 Drive "Store codes are self-described" at seam 1. Green: register every code of this change.
- [ ] 11.2 Docs: add the crawl store's public API (writer, claim, control writes, `check_writer`, `redact`, `CrawlOpt`) to `docs/architecture.md`, and link `docs/crawl-store.md` from `README.md`.
- [ ] 11.3 Review: run the code-review skill on group 11's commits and on the whole change, then refactor with the whole suite green.
