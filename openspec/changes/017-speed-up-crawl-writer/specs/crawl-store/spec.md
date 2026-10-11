## MODIFIED Requirements

### Requirement: Transactional writer

Crawl data SHALL be written only through the Crawl's transactional writer. Callers submit units of work, and each unit may insert, update and read rows.
- **Order:** units SHALL run one at a time, in the order they were submitted. Each unit runs in the writer's open transaction and sees the effects of every unit before it. A unit that only reads SHALL commit nothing.
- **Atomic units:** a unit that fails SHALL leave no change, and its error SHALL be raised to its caller. The other units SHALL be unaffected. A unit that fails SHALL NOT run again.
- **Units may run again:** when a unit fails, the units that ran before it since the last commit MAY run a second time before they are committed. A unit SHALL therefore have no effect outside the writer's connection, SHALL NOT change its input, SHALL be deterministic given the file's state, and SHALL return a value that compares by value. When a unit that runs again raises, returns a different result or changes a different number of rows, the writer SHALL end without that commit: the failing unit's caller still gets its own error, and later units fail with the error that the writer is closed.
- **Commits:** the writer SHALL commit its open transaction when any of these happens:
  - 500 units have run since the last commit
  - 1 second has passed since the first unit after the last commit
  - a unit failed, and the units before it since the last commit have run again (the replay commit)
  - a caller asks for a flush
  - the writer is closed
- **What a result means:** a caller that waits for its unit gets the unit's result once the unit has run, which may be before its commit. A flush, or the Future of a submitted unit (see "Submitting units with their outcome at the commit"), tells the caller that the unit is committed.
- **Durability:** a unit whose transaction was committed SHALL survive the writing process being killed. A kill SHALL lose at most the units that ran after the last commit, and SHALL leave a sound file.

#### Scenario: A unit sees the units before it
- **WHEN** one unit inserts the Seed `(1, "https://example.com/a")`, and the next unit counts the rows of `seeds`, before any commit
- **THEN** the second unit returns `1`

#### Scenario: A unit updates a row of an earlier unit
- **WHEN** one unit inserts the Seed `(1, "https://example.com/a")`, the next unit changes its `url` to `https://example.com/b`, and the writer is closed
- **THEN** `seeds` holds exactly the row `(1, "https://example.com/b")`

#### Scenario: A failing unit leaves no change
- **WHEN** a unit inserts the Seed `(2, "https://example.com/b")` and then raises `ValueError("bad")`, and the writer is closed
- **THEN** the caller of that unit receives `ValueError("bad")`, and `seeds` has no row with position 2

#### Scenario: Other units survive a failing unit
- **WHEN** units insert the Seeds at positions 1 and 3, a unit between them fails, and the writer is closed
- **THEN** `seeds` holds exactly the positions 1 and 3

#### Scenario: A unit that fails half-way after other units leaves no change
- **WHEN** units insert the Seeds `(1, "https://example.com/a")` and `(2, "https://example.com/b")`, the next unit inserts the Seed `(3, "https://example.com/c")`, changes the `url` of position 1 to `https://example.com/z` and then raises `ValueError("bad")`, and the writer is closed
- **THEN** `seeds` holds exactly the rows `(1, "https://example.com/a")` and `(2, "https://example.com/b")`

#### Scenario: A failing unit runs once
- **WHEN** a unit inserts the Seed at position 1, the next unit counts each time it runs, inserts the Seed at position 2 and raises `ValueError("bad")`, and the writer is closed
- **THEN** the failing unit ran exactly once

#### Scenario: An interrupted unit runs once and the writer goes on
- **WHEN** a unit inserts the Seed at position 1, the next unit counts each time it runs, inserts the Seed at position 2 and raises `KeyboardInterrupt`, a third unit inserts the Seed at position 3, and the writer is closed
- **THEN** the caller of the second unit receives `KeyboardInterrupt`, the second unit ran exactly once, and `seeds` holds exactly the positions 1 and 3

#### Scenario: A unit that fails or returns differently when it runs again ends the writer
- **WHEN** a unit inserts the Seed at position 1 and returns how many times it has run, the next unit raises `ValueError("bad")`, and the writer is closed
- **THEN** the caller of the second unit receives `ValueError("bad")`, closing the writer raises `CrawlWriterClosedError("The crawl writer is closed.")`, and `seeds` has no rows

#### Scenario: The failing unit gets its own error when the replay commit fails
- **WHEN** a unit writes a row that breaks a foreign key checked only at the commit, the next unit raises `ValueError("bad")`, and the writer is closed
- **THEN** the caller of the second unit receives `ValueError("bad")`, closing the writer raises `CrawlWriterClosedError("The crawl writer is closed.")`, and the file has no row of the first unit

#### Scenario: A read through the writer commits nothing
- **WHEN** 3 units that each insert one Seed have run, a fourth unit counts the rows of `seeds`, the clock has not moved, and there has been no flush
- **THEN** the fourth unit returns `3`, and a separate reader sees 0 rows in `seeds`

#### Scenario: Units wait for the batch
- **WHEN** 499 units that each insert one Seed have run, the clock has not moved, and there has been no flush
- **THEN** a separate reader sees 0 rows in `seeds`

#### Scenario: The 500th unit commits the batch
- **WHEN** 500 units that each insert one Seed have run, and the clock has not moved
- **THEN** a separate reader sees 500 rows in `seeds`

#### Scenario: The timer commits
- **WHEN** 3 units that each insert one Seed have run, and the clock then moves forward by 1 second
- **THEN** a separate reader sees 3 rows in `seeds`

#### Scenario: A failing unit commits the units before it
- **WHEN** 3 units insert the Seeds at positions 1, 2 and 3, the next unit inserts the Seed at position 4 and raises `ValueError("bad")`, the clock has not moved, and there has been no flush
- **THEN** a separate reader sees exactly the positions 1, 2 and 3 in `seeds`

#### Scenario: A flush commits at once
- **WHEN** 3 units that each insert one Seed have run, and a flush is requested
- **THEN** a separate reader sees 3 rows in `seeds` as soon as the flush returns

#### Scenario: Closing commits everything
- **WHEN** 1,000 units that each insert one Seed have run, and the writer is closed at once
- **THEN** a separate reader sees 1,000 rows in `seeds`

#### Scenario: A killed writer keeps committed units in a sound file
- **WHEN** a process runs 3 units that each insert one Seed, flushes, and is then killed: SIGKILL on Linux and macOS, TerminateProcess on Windows
- **THEN** `PRAGMA integrity_check` on the crawl file returns `ok`, and a reader sees 3 rows in `seeds`

#### Scenario: A killed writer loses uncommitted units
- **WHEN** a process runs 3 units that each insert one Seed, and is killed less than a second later without a flush
- **THEN** a reader sees 0 rows in `seeds`

#### Scenario: A new writer opens the file of a killed writer at once
- **WHEN** a process runs 3 units that each insert one Seed, flushes, and is killed (SIGKILL on Linux and macOS, TerminateProcess on Windows), and a new writer is then opened on the crawl file at once, runs a unit that inserts a fourth Seed, and is closed
- **THEN** `PRAGMA integrity_check` on the crawl file returns `ok`, and a reader sees 4 rows in `seeds`

## ADDED Requirements

### Requirement: Submitting units with their outcome at the commit

A caller SHALL be able to submit a unit without waiting for it to run. Submitting returns a Future for that unit, which is:
- resolved with the unit's result after the commit that holds the unit, never before it
- failed with the unit's error when the unit fails
- failed with the commit's error when the commit that holds the unit fails. Every Future of that commit's units fails with it, the writer then ends, and a unit submitted afterwards fails at once with the error that the writer is closed.

Submitted units follow the order, atomicity and commit rules of the transactional writer, in one order with the units whose callers wait for them.

**Window:** at most 2,000 submitted units SHALL be unresolved at once. A submit beyond that SHALL wait until a commit resolves some of them. A submit from an event loop SHALL wait without blocking the loop, and its Future SHALL be completed on that loop. A submit that waits for room when the writer ends SHALL fail with the error that the writer is closed.

**Cancelling:** cancelling a submitted unit's Future SHALL NOT withdraw the unit. The unit runs and is committed as if nothing had been cancelled, the writer goes on, and the unit's window slot is freed at its commit. Cancelling the Future of a submit from an event loop only drops the outcome.

#### Scenario: A submitted unit waits for its commit
- **WHEN** 3 units that each insert one Seed are submitted, a fourth unit that counts the rows of `seeds` then runs and returns `3`, the clock has not moved, and there has been no flush
- **THEN** none of the 3 Futures is done

#### Scenario: A flush resolves the submitted units
- **WHEN** 3 units are submitted that insert the Seeds at positions 1, 2 and 3 and return their positions, and a flush is requested
- **THEN** as soon as the flush returns, the 3 Futures hold `1`, `2` and `3`, and a separate reader sees 3 rows in `seeds`

#### Scenario: A failing submitted unit fails its Future
- **WHEN** a submitted unit raises `ValueError("bad")`, and a flush is requested
- **THEN** its Future fails with `ValueError("bad")`

#### Scenario: A replay commit resolves the units before a failing one
- **WHEN** 3 submitted units insert the Seeds at positions 1, 2 and 3, a fourth submitted unit raises `ValueError("bad")`, the clock has not moved, and there has been no flush
- **THEN** the Futures of the first 3 units are resolved

#### Scenario: A failed commit fails every Future of its batch
- **WHEN** 2 submitted units insert the Seeds at positions 1 and 2, a third submitted unit writes a row that breaks a foreign key checked only at the commit, and a flush is requested
- **THEN** each of the 3 Futures fails with SQLite's `FOREIGN KEY constraint failed` error, and a unit submitted afterwards fails at once with `CrawlWriterClosedError("The crawl writer is closed.")`

#### Scenario: A full window holds the next submit
- **WHEN** the writer is held inside the first of 2,000 submitted units, another thread then submits one more unit, and the held unit is released
- **THEN** that submit returns only after the writer's first commit

#### Scenario: A unit submitted from an event loop is resolved at its commit
- **WHEN** on an event loop a unit that inserts one Seed and returns `1` is submitted, and the writer is then flushed
- **THEN** awaiting the unit's Future on that loop returns `1`

#### Scenario: Cancelling a submitted unit's Future does not withdraw it
- **WHEN** a unit that inserts the Seed at position 1 is submitted, its Future is cancelled before any commit, a second unit that inserts the Seed at position 2 is submitted, and a flush is requested
- **THEN** cancelling returned `False`, a separate reader sees the positions 1 and 2 in `seeds`, and the second unit's Future holds its result

### Requirement: The writer's connection settings

The writer's connection SHALL keep temporary tables and indexes in memory, and SHALL use a page cache of 64 MiB. In `wal` mode it SHALL also use memory-mapped I/O for up to 256 MiB of the crawl file; in `delete` mode it SHALL use none. No setting changes these values. The durability scenarios of the transactional writer SHALL hold with them, on Windows too.

#### Scenario: The writer's connection settings in WAL mode
- **WHEN** a unit of the writer of a crawl file in `wal` mode reads `PRAGMA temp_store`, `PRAGMA cache_size` and `PRAGMA mmap_size`
- **THEN** they are `2`, `-65536` and `268435456`

#### Scenario: The writer's connection settings in rollback-journal mode
- **WHEN** a unit of the writer of a crawl file in `delete` mode reads `PRAGMA temp_store`, `PRAGMA cache_size` and `PRAGMA mmap_size`
- **THEN** they are `2`, `-65536` and `0`
