## Context

- **What this change builds on:** `015-add-crawl-store` as built on its branch (PR #3), and its archived `crawl-store` spec:
  - `CrawlWriter(path, clock, on_commit=None, busy_seconds=30.0)` in `spider.store.writer`. One thread owns the connection and runs units (`Callable[[Connection], T]`) from a queue bounded at 50,000 jobs, each unit in its own savepoint (`begin_nested()`). It commits after 500 units, 1 s after the first uncommitted unit (by the injected `Clock`, checked every 50 ms and after each unit), on `flush()` and on `close()`, which also runs `wal_checkpoint(TRUNCATE)`. `on_commit(units)` is called on the writer thread with the number of units the commit made durable.
  - `run(unit)` and `await run_async(unit)` return once the unit has run and the commit check is done, before the commit unless that unit triggered one. A failed commit ends the writer: the job in hand gets the error, and every other caller gets `CrawlWriterClosedError`.
  - `spider.store.connections.opening()` builds a `NullPool` engine whose connect listeners set `isolation_level = None` and `synchronous` by journal mode, with `BEGIN IMMEDIATE` on begin. `connect()` waits out a `-shm` file still held by a killed writer (`SQLITE_IOERR_TRUNCATE`).
  - `StoreWorker` runs a `CrawlWriter` in its own process for the durability tests, with a frozen `FakeClock`, and `kill()` reaches the writer process itself.
- **The evidence:**
  - The store benchmark of 2026-10-10 (recommendations R1–R10).
  - The writer prototype of 2026-10-11, with its comparative runs at 20k Pages (writer-only) and 15k Pages (with Pages prepared in the loop or in a pool of 6).
  - Both ran on the maintainer's laptop: 16 GB, a hybrid i5-12450H (4 performance cores with SMT plus 4 efficiency cores, 12 threads), under memory pressure from other programs. Runs made at different times vary by up to ~50%, so the numbers below compare back-to-back runs only, and a delta under ~20% is read as a direction, not a size.
- **The rulings of 2026-10-11:** the implementer's review of the prototype and the rulings on it (thread host only, `run()` unchanged, a new `submit()` with a window, closures kept, reads without a commit, prebuilt statements as a rule), and the user's decisions: the optimistic batch is kept, the pragmas become defaults with no setting, and the throughput check is local.
- **The writer's place in the build order:** 015 → 017 → 020 (slice) → 026. `020`'s per-URL unit is the first heavy user.

## Goals / Non-Goals

**Goals:**
- More Pages per second through the same writer, with no change for `015`'s callers.
- An outcome at the commit for callers that need it (`020`'s hot path), with bounded memory.
- Every guarantee of `015` kept: order, atomic units, bounded loss on a kill, a sound file, `crawl_busy`.
- A measured floor that later changes can check locally.

**Non-Goals:**
- A writer process, units as records, or a new setting (D1, D4, D8).
- The `links` table, the frontier index and the per-URL unit (`020`, `030`, and the schema blueprint).
- End-to-end throughput and the parse pool (`026`).

## Decisions

### D1. The writer stays a thread
The prototype built both hosts around one batch core. Back-to-back runs at 20k Pages, writer-only, with a concurrent reader:

| Run | Link rows per Page | Pages/s | WAL peak | RSS |
|---|---|---|---|---|
| `015`'s writer as built | ~466 | 13.8 | 215 MB | 397 MB |
| thread, optimistic batch | ~466 | 17.2 | 212 MB | 259 MB |
| process, optimistic batch | ~466 | 17.6 | 402 MB | 88 MB crawler + 168 MB writer |
| thread, optimistic batch, Pages prepared in a pool of 6 (15k Pages) | ~120 | 40.4 | 36 MB | |
| process, optimistic batch, Pages prepared in a pool of 6 (15k Pages) | ~120 | 40.1 | 51 MB | |

- The process host ties the thread host, and its WAL peaks almost twice as high.
- It would cost: units as records with a registry (closures do not cross a process boundary), errors sent over a pipe as data, a spawn of about 0.6 s per writer, a slow test group, ignoring console signals, and an import allowlist for its entry module.
- **The caveat:** the prototype's loop did no real networking, so the GIL was nearly free, which favours the thread. `026`'s benchmark on the real pipeline is where that would show. If it ever does, a writer process can sit behind the same `submit()` and window (D2, D3), so `020`'s engine does not change.
- *Alternative:* one core with two hosts, the product using the process. Rejected by the numbers above.

### D2. `run()` unchanged; `submit()` resolved at the commit
- **`run(unit) -> T` and `await run_async(unit) -> T`** keep `015`'s meaning: the result says the unit ran. `flush()` says it is committed. Every `015` test and scenario stays as it is.
- **`submit(unit) -> concurrent.futures.Future[T]`** queues the unit and returns at once, unless the window is full (D3). The Future is:
  - resolved with the unit's result after the commit that holds the unit
  - failed with the unit's own error when it fails
  - failed with the commit's error when that commit fails. The commit's error is the same object the job in hand gets today: `crawl_busy` for a busy file, otherwise the error raised. The writer then ends, as in `015`, and every queued job fails with `CrawlWriterClosedError`.
- **`await submit_async(unit) -> asyncio.Future[T]`** waits for room in the window without blocking the loop, as `run_async` waits for queue room. The Future it returns is bound to the caller's loop, so its callbacks run on the loop, never on the writer thread. `020`'s engine can then end a URL's task at the submit and handle the outcome in a callback.
- **The writer keeps the Futures of its open batch** in submission order. Right after each successful commit, before `on_commit`, it resolves them and frees their window slots.
- Submitting after `close()`, or from the writer's own thread, fails at once, exactly as `run()` does.
- **Cancelling never withdraws a unit.**
  - The writer marks each Future running when it is submitted (`set_running_or_notify_cancel()`), so `cancel()` returns `False`. The unit runs and is committed, and its window slot is freed at the commit.
  - The `asyncio.Future` of `submit_async` is a wrapper: cancelling it only drops the outcome.
  - Why: `020`'s TaskGroup cancels its tasks on a stop. A cancelled, still-pending Future would make the writer thread hit `InvalidStateError` when it resolves it. That would end the writer for every caller.
- *Alternative:* resolve every `run()` at the commit, as the prototype did. Rejected:
  - With the frozen `FakeClock` of `015`'s tests, the 499 units of "Units wait for the batch" would never return.
  - "A unit sees the units before it" and `run_async` need a return value at once.
  - The 015 gap stays documented instead: `run()` means ran, `flush()` means committed, and `submit()` gives the outcome at the commit.

### D3. The window
- **A waiting submit never waits forever:** when the writer ends, from a failed commit or a dead thread, it wakes every submit that waits for room, and each one raises `CrawlWriterClosedError`.
- At most 2,000 submitted units are unresolved at once; a submit beyond that waits on a condition that each commit signals.
- 2,000 is four commits of 500, so the writer never waits for a caller while the window has room. In the prototype, a Page unit without HTML was about 18 KB of rows, which puts the window at about 36 MB.
- Units waited for with `run()` do not count: their caller already waits for each one. The 50,000-job queue of `015` still bounds both kinds.
- **The test** holds the writer inside the first submitted unit, on an `Event`. A second thread signals that it is about to submit the 2,001st unit, and the test then releases the held unit. Each step appends to an ordered log: released, committed (from `on_commit`), returned. With no fixed sleep, a broken window could still pass only if the second thread were slower than a whole commit of 500 units. It can never fail falsely.

### D4. Units stay closures
- A unit stays `Callable[[Connection], T]`, defined in a `spider.store.*` module (`020` D14).
- *Alternative:* units as data plus a name, dispatched through a registry. It is needed only for a process boundary (D1). Rejected. `020` D14's frozen row records stay its hygiene rule, and they keep a writer process possible later.

### D5. Reads through the writer commit nothing
- A unit that only reads runs in the open transaction like any other, so it sees every unit before it and commits nothing. This is already `015`'s behaviour, now pinned by a guard scenario.
- `020`'s frontier batch and its "anything left deeper" count are such units.
- *Alternative:* commit what is pending before every read, as the prototype's writer process did. It adds a commit per frontier read, and "Units wait for the batch" could no longer be tested. Rejected.
- *Alternative:* a second, read-only connection in the crawler. It needs a flush before every read at a depth barrier, and it pins a WAL snapshot. Rejected.

### D6. The optimistic batch
- **Clean path:** the units of a batch run in the open transaction with no savepoint each.
- **When a unit raises anything, a `BaseException` included:**
  1. The writer rolls back the whole transaction.
  2. It begins a new one, and runs the units before the failing one again, in order, with no savepoint each: any failure in the replay ends the writer and its whole transaction goes, so a savepoint would only cost statement-journal I/O (task 1.12).
  3. It commits at once. This is the replay commit, and `on_commit` gets the number of units it made durable.
  4. The failing unit's caller gets the error the unit raised. The failing unit never runs again: its error is already known, and running it again would run its code twice. Above all, it would run code again after a `KeyboardInterrupt`.
  5. The next unit starts a new optimistic batch.
- **When the failing unit's caller learns its outcome:** only after the replay commit. Its Future fails and its window slot is freed at that point.
  - If the replay commit itself fails, the failing unit's caller still gets its own error. The replayed units' Futures fail with the commit's error, and the writer ends.
  - A busy file at the replay's `BEGIN` ends the writer, as a busy `BEGIN` does in `015`.
- **The replay must reproduce the first run** (ruling of 2026-10-11). For each unit the batch keeps its first result and its row-change count, the delta of the driver's `total_changes`. In the replay, a unit that raises, returns a different result or changes a different number of rows ends the writer with no commit, through the path of a failed commit:
  - The failing unit's caller still gets its own error first.
  - The writer fails with `CrawlWriterReplayError`, which names the unit's `__qualname__` and what differed: it raised, its result or its change count. It is chained from the replay's exception, if any.
  - Later callers, and `close()`, get `CrawlWriterClosedError` from it, as after any failed commit.
  - Why not drop the unit and commit the rest: `run()` callers already hold the results of the first run, and may have built later units on them. A silent hole in the file would surface far from its cause.
  - A file-level error inside a unit (`SQLITE_FULL`, an I/O error, a busy spill in `delete` mode) usually meets the replay again, so it now ends the writer, where in `015` only that unit failed. A full disk stops the Crawl loudly.
- **The evidence:** back-to-back runs on the clean path, thread host, writer-only, 20k Pages:

  | Link rows per Page | Savepoint per unit | Optimistic | Gain | Per-Page overhead of the savepoints |
  |---|---|---|---|---|
  | 120 | 52.8 Pages/s | 60.9 Pages/s | +15% | 2.5 ms |
  | ~466 | 15.8 Pages/s | 18.0 Pages/s | +14% | 7.7 ms |

  All 8 windows of 5k Pages were faster. The overhead grows with the rows per unit, so it does not shrink at realistic Link counts. A likely cause, inferred but not measured: SQLite's statement journal copies each page that a unit dirties inside a savepoint. The gain is just over the ~10% bar set before the runs, and this machine is noisy.
- **The replay's cost:** a failing unit runs up to 499 units again. In the prototype's runs, 1 unit in 997 failed half-way, and in the 1,500-Page smoke runs 1 in 97 did; both left no rows from the failed units, and the URLs ended as `error` through the fallback unit. Real write failures are far rarer. If one kind of unit failed often, the savepoint per unit would be the better trade.
- **Atomicity** is tested with a unit that fails half-way after other units: it updates an earlier unit's row and then raises.
- *Alternative:* drop the optimistic batch and keep a savepoint per unit. It is simpler and has no replay or second run, but it is 14–15% slower. Rejected by the user on 2026-10-11.
- *Alternative:* a setting to turn it off. It would put an internal trade-off into the public settings. Rejected.

### D7. Units may run again: the contract
- A unit runs a second time when a later unit of its batch fails. A unit therefore:
  - has no effect outside the writer's connection: no I/O, no shared state, and nothing reported from inside the unit
  - does not change its input
  - computes its writes from its input and what it reads on the connection, so its second run writes what its first run wrote: it is deterministic given the file's state, with no clock, randomness or counter of its own
  - returns a value: `None`, a number, a `str`, a tuple of these, or a frozen dataclass, so that the replay can compare its results. A float `NaN` never equals itself, so a unit does not return one.
- `docs/crawl-store.md` states the contract, and every code review of a change that adds units checks it. A test cannot prove it for every unit, so the replay checks what it can (D6), and `replay_now(writer)` in `tests/support` lets a change's own tests replay its units. `020` D14 helps: its units write frozen records that handlers built before the unit.

### D8. The writer's connection settings
- **What changes:** `opening()` gets a keyword that only `CrawlWriter` passes. With it, the engine gets one more connect listener, after the journal-mode check: `temp_store = MEMORY`, `cache_size = -65536` (64 MiB), and `mmap_size`.
  - `mmap_size` is `268435456` (256 MiB) when the journal mode is `wal`.
  - It is set explicitly to `0` in `delete` mode, because `SQLITE_DEFAULT_MMAP_SIZE` is a build-time option and may not be 0 in every build.
  - Creating the file and reading it keep SQLite's defaults.
- **The evidence:** at 2k Pages in the store benchmark, the whole run took 41.7 s as built, 34.3 s with `temp_store`, and 27.8 s with the cache and `mmap_size` too (−33%). Kernel time fell from 18.6 to 7.2 s.
- **Why no memory mapping in `delete` mode:** that mode is chosen for UNC paths (`015` D3), and a memory-mapped file on a network share is only as coherent as the share's client cache. The gain does not justify that risk on the path we already treat as fragile.
- **No setting:** the values are safe on every supported OS, and a setting would add a contract to keep. The cache is a ceiling, not an allocation.
- *Alternative:* the same settings for readers. Readers open per operation and run briefly, and `050` measures its own queries. Not now.

### D9. Prebuilt statements: a rule, not a guard test
- **The rule,** for every store module from `020` on: a unit that runs once per URL or per Page executes statements built once at import, as `execute(stmt, params)`. It never builds `.values(<literals>)` per unit, and never uses `insert().values(list)`.
- **The evidence:** in the store benchmark, statements built per unit regenerated their cache keys and coerced every value, and prebuilt statements were about 2× faster in the profile. A multi-values insert compiled per call was 60× slower than `executemany`.
- **Where it lives:** the "Crawl store" section of `docs/architecture.md`, and the review task of every group that adds units.
- **`015`'s own units** run a bounded number of times per Crawl (the write check, `set_state`), so they keep their statements as they are.
- *Alternative:* an AST guard over `src/spider/store/`. It cannot tell a statement built once from one built per call without false positives: expanding bind parameters and column lists chosen at import look the same as per-call statements. Rejected for now. If a review finds the rule broken twice, a guard is reconsidered.

### D10. The killed-writer proof with memory mapping, on Windows
- Memory-mapped views caused `015`'s `-shm` trouble on Windows: a killed process that is still exiting keeps its mapped views. With `mmap_size` on, the crawl file itself is mapped too.
- `015`'s durability tests already use `CrawlWriter`, so after D8 they run with the new settings. Group 3 runs them, plus the new scenario "A new writer opens the file of a killed writer at once" (`020` D16's fresh writer), as `015`'s proof did, and with one stricter condition:
  - 200 times in a row on Windows on each of SQLite 3.50.x (the python.org Python 3.14) and 3.53.x (the uv-managed Python), with 0 failures, then in CI on all three OSes. Fewer runs could not catch a race that fails 1–2% of the time, like the one `015` hit.
  - **Under parallel load:** for the whole proof, a second process runs the full test suite (`pytest --no-cov`) in a loop. The two proof configurations run one at a time.
  - `015`'s held `-shm` reading tests are not part of it: they inject the fault, so repeating them proves nothing about memory mapping.
- **If one fails** with a new SQLite error at open or a lost commit, the fallback is `mmap_size = 0` on Windows only. It is decided with the maintainer, and `docs/crawl-store.md` records why.

### D11. The throughput check
- **What it measures:** the writer's capacity, not a Crawl's. `scripts/writer_throughput.py` prepares 20,000 Pages before the clock starts. That is about 466 Link rows and about 367 discovered targets per Page, from template navigation, header and footer Links as in the prototype's `--template-links` stream.
- **What it runs:** it submits one unit per Page through `submit()`, with D6 and D8 on. Each unit upserts the discovered URLs, reads back their ids, updates the Page's URL row and inserts its Link rows, all through prebuilt statements. A reader process queries the file during the run, and 1 unit in 997 fails half-way.
- **Its tables are provisional:** `urls` and `links` shaped like the prototype's (`020`'s draft tables, with the two secondary indexes on `links`), created in the check's own scratch crawl file. They are never in the declared schema. When the schema blueprint's links layout lands, the check switches to it, and the floor is restated against realistic fetch rates.
- **It reports,** as one JSON document: Pages/s overall and per 5k window, Link rows/s, the WAL peak, the process RSS, and the atomicity check (no row from a failed unit, every other Page stored).
- **Its floor:** at least 12 Pages/s (70% of the 17.2–18.0 measured), a WAL peak of at most 300 MB, and an RSS of at most 400 MB. Below the floor it exits non-zero.
- **Where it runs:** locally, by hand. It is never part of the CI gate or of `scripts/check.py`, and `docs/benchmarks.md` records the machine and the numbers.

## Test seams

Seams from docs/testing.md:
- **Services and store API (2):** every scenario, with a real crawl store in `temp_workspace` and `FakeClock`:
  - `submit()` and `submit_async()`, the window, and the optimistic batch
  - the connection settings, read back with `PRAGMA` from inside a unit, as `015`'s busy-timeout test does
  - the killed-writer scenarios, through `StoreWorker` (marked `slow`)
- **A failed commit, without a double:** the test creates its own table in the crawl file with a foreign key `DEFERRABLE INITIALLY DEFERRED`, and a submitted unit inserts a row that breaks it, so `COMMIT` itself fails as SQLite reports it. The table exists only in that test's file. No mock and no new boundary double.
- **The throughput check** is a script, not a test, and no seam is added for it.

Boundary doubles used: `FakeClock` only.

## Risks / Trade-offs

- [A unit with an effect outside its connection runs twice after a later unit fails] → The contract of D7 in the spec and in `docs/crawl-store.md`, checked in every review. `020` D14 keeps units to writing frozen records.
- [Memory mapping brings back `-shm`-like trouble on Windows after a kill] → D10 proves it before anything builds on it, with a Windows-only fallback.
- [The thread host loses to the GIL once the event loop really fetches and parses] → `026`'s pool takes parsing out of the loop, and its benchmark measures the whole pipeline. A writer process can be added behind `submit()` without changing `020` (D1).
- [The +14–15% is close to the noise of the machine it was measured on] → Every window of 5k Pages agreed, and the overhead grows with the rows per unit. The throughput check pins the floor, not the gain.
- [In `delete` mode, a unit that waits out the busy timeout fails, and the replay may wait again for each unit before it] → A busy file in `delete` mode already fails the Crawl with `crawl_busy` (`020`'s risks), and the 64 MiB cache makes spills inside a unit rarer.
- [The throughput floor is set on a provisional links layout] → The check is marked provisional, and the schema blueprint restates it.
- [A busy `BEGIN` in the replay ends the writer, and no test covers it] → The code takes the same path as any failed replay. A deterministic test would need a lock taken between the rollback and the `BEGIN`. Deferred.
- [A busy error inside a unit that runs again is raised as it is, so the writer ends with `crawl_busy`, and no test covers it] → It needs a cache spill in `delete` mode while a reader holds the file. Deferred.
- [The row-change count is masked to 32 bits, because SQLite's `total_changes` is a C int that wraps, and no test covers the wrap] → A test would need 2^31 changes. Deferred.
- [A submit that waits for room is woken when the writer thread ends for a reason other than a failed commit, and no test covers that] → Every end of the thread goes through the same `finally` that wakes the waiters, which the failed-commit test covers. Deferred.
- [A job queued just after the writer drained its queue on the way out is failed by its submitter, and no test covers it] → It needs the thread to end between a submit's closed check and its `put`; a deterministic test would need a hook inside the writer. Deferred.
- [`submit_async` gives its window slot back when the 50,000-job queue is full, and no test covers it] → A test would need the queue full while the window has room. Deferred.

## Migration Plan

None. No schema change. `015`'s callers keep `run()`, `run_async()`, `flush()` and `close()` as they are.

## Interface points for later changes

- **`020`:**
  - Its per-URL unit uses `await writer.submit_async(unit)`. The URL's task ends at the submit, and the unit's outcome arrives at the commit.
  - A failed unit gets a fallback unit that records the URL as `error`. A failed commit, or `CrawlWriterClosedError`, is `write_failed` (D16).
  - Frontier reads are writer units (D5), with the partial index from its checklist.
  - Its store modules follow the statement rule (D9) and the unit contract (D7). Progress counts come from `on_commit`.
- **`026`:** the writer must never be short of CPU. 6 workers (physical cores minus 2) on the hybrid laptop still starved it, so `026`'s benchmark sweeps the worker count up to that bound and records machine-wide CPU and clock frequency. It also measures the GIL effect of D1's caveat.
- **`030` and `040`:** their units follow D7 and D9.
- **`060`:** the writer is a thread of the Crawl's process, so the claim belongs to that process. A detached Crawl needs no second spawn for the writer.

## Open Questions

None that block the tasks. The fallback of D10 is decided only if group 3's proof fails.
