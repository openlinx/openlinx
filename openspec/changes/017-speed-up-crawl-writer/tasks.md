"Drive" means one TDD slice:
1. Write the failing test for the named scenario at the named seam, and watch it fail for the right reason.
2. Write only enough code to pass.
3. Run `uv run scripts/check.py`.
4. Commit. One task = one commit, and the message names the scenario.

Scenario names are the `#### Scenario:` titles in `specs/crawl-store/spec.md`. Seams are those of docs/testing.md:
- seam 2: the store API, with a real crawl store in `temp_workspace` and `FakeClock`, in `tests/store/test_writer.py`
- seam 2, process: the same through `StoreWorker`, in `tests/store/test_durability.py`, marked `slow`

"Done when" says what must be true, not which helper to write. Names appear only where another change depends on them (design, Interface points).

A **guard** is a test for a scenario that earlier code already satisfies. It passes on its first run, and it is kept to pin the contract. The scenarios that `015` already tests keep their tests and names; this change runs them again under the new writer.

**The whole change is in the thin slice:** `020` starts after it (ROADMAP, Build order). Group 4's throughput check runs after groups 1–3, on the writer as it ships.

## 1. The optimistic batch (seam 2)

- [x] 1.1 Drive "A failing unit commits the units before it".

  Done when: the units of a batch run with no savepoint each. When a unit raises anything, a `BaseException` included, the writer rolls back the transaction, runs the units before it again in order, commits at once, and raises the unit's own error to its caller (design D6). `on_commit` gets the number of units the replay commit made durable, and a unit that fails in the replay is left out of it.
- [x] 1.2 **Guard:** "A unit that fails half-way after other units leaves no change".
- [x] 1.3 **Guard:** "A failing unit runs once".
- [x] 1.4 **Guard:** "An interrupted unit runs once and the writer goes on". Done when: `015`'s `test_an_interrupted_unit_rolls_back_and_the_writer_goes_on` is renamed after this scenario and also checks the Seed at position 1 and the number of runs.
- [x] 1.5 **Guard:** `015`'s scenarios under the optimistic batch: "A unit sees the units before it", "A unit updates a row of an earlier unit", "A failing unit leaves no change", "Other units survive a failing unit", "Units wait for the batch", "The 500th unit commits the batch", "The timer commits", "A flush commits at once" and "Closing commits everything". Done when: their `015` tests pass unchanged, and so do `015`'s tests for units from several threads, `run_async`, a busy unit, closing, and a unit that waits for its own writer.
- [x] 1.6 **Guard:** "A read through the writer commits nothing".
- [x] 1.7 Docs: in "Writing a Crawl" of `docs/crawl-store.md`, document the replay commit and the unit contract of design D7: a unit may run again before its commit, so it has no effect outside its connection and does not change its input.
- [x] 1.8 Review: run the code-review skill on group 1's commits against the "Transactional writer" requirement, then refactor with the whole suite green.

- [x] 1.9 Drive "A unit that fails or returns differently when it runs again ends the writer" (the ruling on design D6 of 2026-10-11).

  Done when:
  - the batch keeps each unit with its first result and its row-change count (the delta of the driver's `total_changes`)
  - in the replay, a unit that raises, returns a different result or changes a different number of rows ends the writer with no commit, through the path of a failed commit, with `CrawlWriterReplayError` naming the unit's `__qualname__` and what differed; the failing unit's caller still gets its own error first, and later callers and `close()` get `CrawlWriterClosedError`
  - tests also cover a unit that meets `SQLITE_FULL` when it runs again (it lowers `PRAGMA max_page_count` on its second run), and a unit whose change count differs
  - `test_a_unit_that_fails_in_the_replay_is_left_out_of_its_commit` is gone, its behaviour with it; `test_the_failing_unit_gets_its_own_error_when_the_replay_commit_fails` is the test of its new scenario
  - the two test units that return a SQLAlchemy result return `None`
  - "Writing a Crawl" in `docs/crawl-store.md` states the stricter contract of design D7 and what a replay that differs does
- [x] 1.10 Test support: `replay_now(writer)` in `tests/support`, which makes the writer replay every unit since the last commit, so a change's own tests can check that its units run again the same (design D7). Done when: a test uses it, and docs/testing.md lists it under Helpers.
- [x] 1.11 Review: run the code-review skill on 1.9 and 1.10 against the "Transactional writer" requirement, then refactor with the whole suite green.
- [x] 1.12 The replay runs units with no savepoint each (the ruling of 2026-10-11 on the 1.11 review): any failure in the replay ends the writer and its whole transaction goes, so a savepoint per unit only costs statement-journal I/O (design D6).

  Done when: the replay issues no `SAVEPOINT`, and a test that traces the writer's statements through a replay goes red if one comes back.

## 2. Submitting units with their outcome at the commit (seam 2)

- [x] 2.1 Drive "A submitted unit waits for its commit".

  Done when: `CrawlWriter.submit(unit)` returns a `concurrent.futures.Future` that is still pending after the unit has run, and units submitted and units waited for with `run()` run in one order (design D2).
- [x] 2.2 Drive "A flush resolves the submitted units". Done when: right after each successful commit, before `on_commit`, the writer resolves the Futures of the units that commit made durable, with their results.
- [x] 2.3 Drive "A failing submitted unit fails its Future".
- [x] 2.4 Drive "A replay commit resolves the units before a failing one".
- [x] 2.5 Drive "A failed commit fails every Future of its batch".

  Done when:
  - the test creates its own table in the crawl file with a `DEFERRABLE INITIALLY DEFERRED` foreign key, so `COMMIT` itself fails as SQLite reports it, with no mock (design, Test seams)
  - every Future of the batch fails with the error the job in hand gets (`crawl_busy` for a busy file)
  - every job still queued fails with `CrawlWriterClosedError`, and so does a later submit
  - a submit that waits on a full window wakes when the writer ends, from a failed commit or a dead thread, and raises `CrawlWriterClosedError`, so no caller waits forever (design D3)
- [x] 2.6 Drive "A full window holds the next submit".

  Done when:
  - at most 2,000 submitted units are unresolved at once, and units waited for with `run()` do not count (design D3)
  - the test holds the writer on an `Event` inside the first unit, and checks an ordered log (released, committed, returned) with no fixed sleep
- [x] 2.7 Drive "A unit submitted from an event loop is resolved at its commit".

  Done when: `await submit_async(unit)` waits for room in the window without blocking the loop, and returns an `asyncio.Future` bound to the caller's loop, whose callbacks run on that loop.
- [x] 2.8 Drive "Cancelling a submitted unit's Future does not withdraw it".

  Done when: the writer marks each Future running at submit, so `cancel()` returns `False` and the writer thread never meets a cancelled Future. Cancelling `submit_async`'s `asyncio.Future` only drops the outcome, and the test checks that too (design D2).
- [x] 2.9 Docs: in "Writing a Crawl" of `docs/crawl-store.md`, document submitting, the window, cancelling, and what each outcome means: `run()` means the unit ran, `flush()` and a submitted unit's Future mean it is committed.
- [ ] 2.10 Review: run the code-review skill on group 2's commits against the "Submitting units with their outcome at the commit" requirement, then refactor with the whole suite green.

## 3. The writer's connection settings and the killed writer (seam 2)

- [ ] 3.1 Drive "The writer's connection settings in WAL mode".

  Done when: only the writer's engine, through a keyword of `opening()` that only `CrawlWriter` passes, sets `temp_store`, `cache_size` and `mmap_size` in a connect listener after the journal-mode check. Creating the file and readers keep SQLite's defaults, and no setting is added (design D8).
- [ ] 3.2 Drive "The writer's connection settings in rollback-journal mode". Done when: `mmap_size` is set to `0` explicitly, since its default is a build-time option.
- [ ] 3.3 Drive "A new writer opens the file of a killed writer at once", at seam 2, process. If it passes on its first run, it stays as a guard of `020` D16's fresh writer.
- [ ] 3.4 Verify the killed-writer proof on Windows with memory mapping on (design D10).

  Done when:
  - "A killed writer keeps committed units in a sound file", "A killed writer loses uncommitted units" and "A new writer opens the file of a killed writer at once", with the rest of `tests/store/test_durability.py`, pass 200 times in a row on Windows on each of SQLite 3.50.x (the python.org Python 3.14) and SQLite 3.53.x (the uv-managed Python), with 0 failures. That is `015`'s proof: 20 runs cannot catch a race that fails 1–2% of the time.
  - throughout the proof, a second process runs the full test suite (`pytest --no-cov`) in a loop, and the two configurations run one at a time (design D10). `015`'s held `-shm` reading tests are left out, because they inject the fault.
  - they pass in CI on Windows, macOS and Linux
  - the PR description records the Windows and SQLite versions
  - if a run fails with a new SQLite error at open or a lost commit, the work stops and is reported. The fallback (`mmap_size = 0` on Windows only) is decided with the maintainer.
- [ ] 3.5 Docs: in `docs/crawl-store.md`, document the writer's connection settings, and why `delete` mode maps no memory.
- [ ] 3.6 Review: run the code-review skill on group 3's commits against "The writer's connection settings" and the durability scenarios, then refactor with the whole suite green.

## 4. Prebuilt statements and the throughput check

- [ ] 4.1 Docs: in the "Crawl store" section of `docs/architecture.md`, document the prebuilt-statement rule of design D9: a unit that runs per URL or per Page executes statements built once at import, as `execute(stmt, params)`, never `.values(<literals>)` per unit and never `insert().values(list)`. Also document why no guard test enforces it.
- [ ] 4.2 Check script: `scripts/writer_throughput.py`, as design D11 describes.

  Done when:
  - it prepares 20,000 Pages of ~466 Link rows and ~367 discovered targets each before the clock starts, and submits one unit per Page through `submit()` with prebuilt statements
  - it runs a reader process during the run, and fails 1 unit in 997 half-way
  - its provisional `urls` and `links` tables exist only in its scratch crawl file, never in the declared schema
  - it prints one JSON document: Pages/s overall and per 5k window, Link rows/s, the WAL peak, the RSS, and the atomicity check
  - it exits non-zero below 12 Pages/s, above a 300 MB WAL peak or a 400 MB RSS, or on a failed atomicity check
  - `psutil` is a dev dependency, not a runtime one
  - neither CI nor `scripts/check.py` runs it
- [ ] 4.3 Check: run `scripts/writer_throughput.py` on the maintainer's machine. Done when: it passes its floor, and a "Writer capacity" section of `docs/benchmarks.md` records the machine, the numbers and the provisional links layout. If it misses the floor, the work stops and is reported before anything changes.
- [ ] 4.4 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Change check

- [ ] 5.1 Verify that every `#### Scenario:` in `specs/crawl-store/spec.md` has exactly one test named after it, with a small script over the test ids.
- [ ] 5.2 Docs: the writer bullet in the "Crawl store" section of `docs/architecture.md` describes the writer as built: one thread, the optimistic batch, `submit()` and its window, and the connection settings.
- [ ] 5.3 Verify that the whole suite passes in CI on Windows, macOS and Linux × Python 3.12–3.14 with the coverage gate.
- [ ] 5.4 Review: run the code-review skill on the whole change against `specs/crawl-store/spec.md`, then refactor with the whole suite green.
