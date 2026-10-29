## ADDED Requirements

### Requirement: Units the writer refuses

**In short:** a unit whose result compares by identity, or that ends the writer's transaction, fails at its first run, before a replay could fail on it.

"Transactional writer" lets a unit run again and compares its results. So at a unit's first run the writer SHALL refuse:
- a result whose type compares by identity, or a tuple, list, frozenset or dict that holds one;
- a unit after which the writer's connection is no longer in a transaction, such as one that commits.

A refused unit SHALL fail with an error that names the unit and says to return values and never commit, and SHALL leave no change. The writer and the other units SHALL be unaffected.

#### Scenario: A unit that returns a cursor is refused
- **WHEN** a unit that inserts a row and returns the result of its `execute` runs on a writer
- **THEN** it fails with an error that names the unit, the row is not in the file, and the next unit runs and commits

#### Scenario: A unit that commits is refused
- **WHEN** a unit that inserts a row and commits the connection runs on a writer
- **THEN** it fails with an error that names the unit, and the next unit runs and commits

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
