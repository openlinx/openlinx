## MODIFIED Requirements

### Requirement: Crawl ids

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

#### Scenario: A chosen id is created once
- **WHEN** a Crawl has been created with the chosen id `20260927-140312-k3f9`, and a second Crawl is created with the same chosen id
- **THEN** the second creation fails with the error code `crawl_id_taken`, and the first Crawl's file is unchanged

#### Scenario: Character set
- **WHEN** ids are created with the system random source for any UTC start time from `2000-01-01T00:00:00.000Z` to `2099-12-31T23:59:59.999Z`
- **THEN** every id matches `^[0-9]{8}-[0-9]{6}-[0-9a-hjkmnp-tv-z]{4}$`
