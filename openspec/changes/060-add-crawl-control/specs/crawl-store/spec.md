## MODIFIED Requirements

### Requirement: Crawl ids
**In short:** A new Crawl draws an id unused by any crawl file, writer claim file or log file in its Workspace.

A crawl id SHALL consist of:
- the Crawl's UTC start time, formatted `YYYYMMDD-HHMMSS`
- a hyphen
- 4 random characters from `0123456789abcdefghjkmnpqrstvwxyz`

An id SHALL count as taken in a Workspace when `<id>.sqlite`, the writer claim's file `<id>.lock` or the log file `<id>.log` exists in its `crawls/` folder. A new id SHALL never be a taken one: new random characters SHALL be drawn until it is not, and the crawl file SHALL be created exclusively, so two processes can never create the same id.

A process MAY reserve a new id by creating `<id>.log` exclusively, and then create the Crawl with that chosen id (`060-add-crawl-control`'s background Crawls). Creating a Crawl with a chosen id SHALL fail with the error code `crawl_id_taken` (exit code 5, because another process made that Crawl), and create nothing, when `<id>.sqlite` exists.

#### Scenario: Id from the start time
- **WHEN** a Crawl is created at `2026-09-27T14:03:12.345Z`, and the random source yields `k3f9`
- **THEN** its id is `20260927-140312-k3f9`

#### Scenario: A taken id is drawn again
- **WHEN** `20260927-140312-k3f9.sqlite` exists, and a Crawl is created at `2026-09-27T14:03:12.900Z` while the random source yields `k3f9` and then `m2p7`
- **THEN** the new Crawl's id is `20260927-140312-m2p7`

#### Scenario: A reserved id is drawn again
- **WHEN** only `20260927-140312-k3f9.log` exists, and a Crawl is created at `2026-09-27T14:03:12.900Z` while the random source yields `k3f9` and then `m2p7`
- **THEN** the new Crawl's id is `20260927-140312-m2p7`

#### Scenario: An id with a writer claim file is drawn again
- **WHEN** only `20260927-140312-k3f9.lock` exists, and a Crawl is created at `2026-09-27T14:03:12.900Z` while the random source yields `k3f9` and then `m2p7`
- **THEN** the new Crawl's id is `20260927-140312-m2p7`

#### Scenario: A chosen id is created once
- **WHEN** a Crawl has been created with the chosen id `20260927-140312-k3f9`, and a second Crawl is created with the same chosen id
- **THEN** the second creation fails with the error code `crawl_id_taken`, and the first Crawl's file is unchanged

#### Scenario: Character set
- **WHEN** ids are created with the system random source for any UTC start time from `2000-01-01T00:00:00.000Z` to `2099-12-31T23:59:59.999Z`
- **THEN** every id matches `^[0-9]{8}-[0-9]{6}-[0-9a-hjkmnp-tv-z]{4}$`

## ADDED Requirements

### Requirement: A Crawl being created is not latest
While a process creates a Crawl, its file `<id>.sqlite` exists before its schema is written. The schema is complete when `PRAGMA user_version` holds the schema version, which the creating process writes in the same transaction as the schema, the `crawl` row and the Seeds, so a reader sees either no schema or all of it.

`latest` (see "Selecting a Crawl with --crawl") SHALL skip a file whose schema is not complete while its writer claim `<id>.lock` is held (`crawl-control`'s "One writer per Crawl"), and SHALL select the most recent of the other Crawls, or fail with `no_crawls` when none is left. A file whose schema is not complete while no process holds its claim is broken, and SHALL still be reported as `crawl_file_invalid`, as the scenario "A broken newest file is reported, not skipped" says.

#### Scenario: A Crawl being created is not the latest
- **WHEN** `latest` is resolved in a Workspace holding a valid `20260927-100000-aaaa` and a file `20260927-110000-bbbb.sqlite` whose schema is not written yet, while a process holds the writer claim `20260927-110000-bbbb.lock`
- **THEN** the Crawl `20260927-100000-aaaa` is selected

### Requirement: Historical URL outcomes
**In short:** A URL stays marked as processed after its first committed fetch or error outcome.

`urls.ever_processed` SHALL be a non-null INTEGER flag, 0 for a new URL and 1 once a `fetched` or `error` outcome for that URL commits. The flag SHALL be written in the same transaction as that outcome. Once set, it SHALL stay 1 for the life of the URL row, including during network recovery, resume and any later outcome. Merely queueing a URL, starting a request, skipping a URL or rolling back an outcome SHALL NOT set the flag.

#### Scenario: Requeue preserves committed URL outcomes
- **GIVEN** a Crawl has one URL with a committed `error` outcome and one queued URL that has never recorded an outcome
- **WHEN** the error is requeued and the Store is read before another outcome commits
- **THEN** both URLs are queued, with `ever_processed` = 1 for the former error and 0 for the other URL
- **WHEN** the former error is fetched successfully
- **THEN** its `ever_processed` remains 1 and the Crawl still has only one processed URL
