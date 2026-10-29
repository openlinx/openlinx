## MODIFIED Requirements

### Requirement: Transactional writer

**In short:** all Crawl data goes through one writer that runs units of work in order, each all-or-nothing, and commits them in batches that survive a crash.

Crawl data SHALL be written only through the Crawl's transactional writer. Callers submit units of work, and each unit may insert, update and read rows.
- **Order:** units SHALL run one at a time, in the order they were submitted. Each unit runs in the writer's open transaction and sees the effects of every unit before it. A unit that only reads SHALL commit nothing.
- **Atomic units:** a unit that fails SHALL leave no change, and its error SHALL be raised to its caller. The other units SHALL be unaffected. A unit that fails SHALL NOT run again.
- **Units may run again:** when a unit fails, the units that ran before it since the last commit MAY run a second time before they are committed. A unit SHALL therefore have no effect outside the writer's connection, SHALL NOT change its input, SHALL be deterministic given the file's state, and SHALL return a value that compares by value. When a unit that runs again raises, returns a different result or changes a different number of rows, the writer SHALL end without that commit: the failing unit's caller still gets its own error, and later units fail with the error that the writer is closed.
- **Units it refuses:** at a unit's first run, the writer SHALL refuse a result whose type compares by identity, or a tuple, list or frozenset with such an element, or a dict with such a key or value; an enumeration member is a value. The unit's caller gets an error that names the unit and says to return values, the unit leaves no change, and the other units are unaffected.
- **A unit that commits:** a unit that commits the writer's transaction SHALL end the writer. Its caller gets an error that names the unit and says never to commit. What the unit committed stays in the file: its own changes before the commit, and those of the units before it since the last commit. Its changes after the commit are rolled back, and later units fail with the error that the writer is closed.
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

#### Scenario: A unit that returns a cursor is refused
- **WHEN** a unit inserts the Seed `(1, "https://example.com/a")` and returns the result of its `execute`, the next unit inserts the Seed `(2, "https://example.com/b")`, and the writer is closed
- **THEN** the caller of the first unit receives an error that names the unit, and `seeds` holds exactly the position 2

#### Scenario: A unit that commits ends the writer
- **WHEN** a unit inserts the Seed at position 1, the next unit inserts the Seed at position 2, commits the connection and inserts the Seed at position 3, and a third unit inserts the Seed at position 4
- **THEN** the caller of the second unit receives an error that names the unit, the caller of the third unit receives `CrawlWriterClosedError("The crawl writer is closed.")`, and `seeds` holds exactly the positions 1 and 2


## ADDED Requirements

### Requirement: A writer driven by an event loop

**In short:** under a loop's commit deadline, units go through the async calls, which commit on the loop's clock; the sync calls are refused.

While a caller holds the writer's loop commit deadline, as a Crawl does:
- the 1-second commit of "Transactional writer" SHALL be measured on the loop's clock, from the first unit an async call submitted after the last commit;
- a sync `submit` or `run` SHALL fail at once with an error that names the async call to use, and SHALL queue nothing.

#### Scenario: A sync submit under a loop's commit deadline is refused
- **WHEN** a unit is submitted with the sync `submit` while the loop's commit deadline is held
- **THEN** the call fails at once with an error that names `submit_async`, and the unit does not run

#### Scenario: A unit submitted under a loop's commit deadline commits at the deadline
- **WHEN** one unit is submitted with `submit_async` while the loop's commit deadline is held, and the loop's clock advances 1 second
- **THEN** the unit's future resolves, and a reader sees its row
