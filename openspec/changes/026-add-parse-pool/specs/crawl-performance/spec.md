## Purpose

Allow Page preparation to use several CPU cores while fetching goes on. With the pool selected, memory stays bounded, a crashing worker and a Page that takes too long are contained, workers end with their Crawl, and no console windows appear on Windows.

Scenario conventions:
- `{site}` is the origin of the local fixture site, for example `http://127.0.0.1:8765`.
- A bare path such as `/about` means `{site}/about`.
- "An extractor added for the test" is added to `020-add-crawl-core`'s `default_hooks()` and passed to the Crawl Service, as `020`'s design D9 allows.
- Pool scenarios select the executor explicitly through the Crawl Service. A test may shorten the preparation deadline through the pool executor's parameter; the scenarios hold for any deadline.

## ADDED Requirements

### Requirement: Page preparation in worker processes
The Crawl SHALL prepare Pages in-process by default. When the pool is selected, the Crawl SHALL run page preparation (parsing, the link extractor and every registered extractor) in fresh worker interpreters on every OS. The `data` of the `crawl_started` event SHALL report `parse_workers`, the selected worker count, or zero for in-process preparation. Extractors and per-response handlers SHALL keep the interface of `020-add-crawl-core`.

#### Scenario: Pages are parsed outside the crawl process
- **WHEN** an extractor added for the test records the process id it runs in, `/` links to `/about`, and a Crawl of `{site}/` runs
- **THEN** no recorded process id equals the crawl process's id

#### Scenario: The number of parse workers is reported
- **WHEN** one Crawl uses the in-process default and another explicitly selects a two-worker pool
- **THEN** `data.parse_workers` of their `crawl_started` events is zero and two respectively

#### Scenario: Pages are parsed in worker processes on Windows (Windows)
- **WHEN** a Crawl of `{site}/` runs as a subprocess on Windows with the pool selected, and `/` links to `/about`
- **THEN** it exits with code 0, and `{site}/about` has `parsed` = 1

### Requirement: Bounded parse queue
When page preparation falls behind, fetching SHALL wait. At no time SHALL more than the global request cap of `020-add-crawl-core` (`min(100, max(20, 4 × --concurrency))`) + 2 × `parse_workers` Pages be requested but not yet prepared. `--concurrency` limits the requests to one host, so on a single host the bound is `--concurrency` + 2 × `parse_workers`.

#### Scenario: Fetching waits for slow parsing
- **WHEN** an extractor added for the test takes 1 second per Page, `/` links to `/p1` to `/p50`, and a Crawl of `{site}/` runs with the default `--concurrency`
- **THEN** the highest number of Pages requested but not yet prepared is at most 5 + 2 × `parse_workers`

### Requirement: A crashed parse worker is replaced
When a worker process dies while it prepares a response, the Crawl SHALL:
- replace the worker
- record that URL with `parsed` = 0 and `parse_error` = `worker_crashed`, a value `020-add-crawl-core` lists for this change
- prepare the other responses that were waiting or in flight, and go on

#### Scenario: A crashed worker is recorded
- **WHEN** an extractor added for the test ends its worker process on `{site}/die`, and `/` links to `/die` and `/ok`
- **THEN** `{site}/die` has `parsed` = 0 and `parse_error` = `worker_crashed`

#### Scenario: The Crawl continues after a worker crash
- **WHEN** an extractor added for the test ends its worker process on `{site}/die`, and `/` links to `/die` and `/ok`
- **THEN** `{site}/ok` has `parsed` = 1, and the Crawl ends with the Crawl State `completed`

### Requirement: A Page that takes too long to prepare is stopped
When preparing one Page takes longer than 30 seconds from the moment a worker took it, the Crawl SHALL:
- end that worker and replace it
- record that URL with `parsed` = 0 and `parse_error` = `parse_timeout`, a value `020-add-crawl-core` lists for this change
- prepare every other Page as if that one had not been there, and go on

#### Scenario: A Page that takes too long to prepare is recorded
- **WHEN** an extractor added for the test never returns on `{site}/slow`, and `/` links to `/slow` and `/ok`
- **THEN** `{site}/slow` has `parsed` = 0 and `parse_error` = `parse_timeout`

#### Scenario: The Crawl continues after a preparation timeout
- **WHEN** an extractor added for the test never returns on `{site}/slow`, and `/` links to `/slow` and `/ok`
- **THEN** `{site}/ok` has `parsed` = 1, and the Crawl ends with the Crawl State `completed`

#### Scenario: Other Pages are not charged for a preparation timeout
- **WHEN** an extractor added for the test never returns on `{site}/slow` and takes a third of the deadline on each other Page, and `/` links to `/slow` and to `/p1` to `/p10`
- **THEN** each of `{site}/p1` to `{site}/p10` has `parsed` = 1 and no `parse_error`

### Requirement: Parse workers end with the Crawl
The guardian and every worker process SHALL have ended within 10 seconds after the Crawl owner exits, including during startup or replacement. The attached foreground Crawl SHALL handle its first keyboard interrupt (Ctrl+C or Ctrl+Break on Windows) through the normal interrupt stop path, leaving unfinished URLs `queued`. On Windows, a programmatic Ctrl+Break addressed to the owner's process group or broadcast on its console SHALL take the same path. The owner SHALL begin shutdown without waiting for a starting guardian, initial worker or replacement to become ready. These children SHALL be isolated from the owner's Windows console events from creation, including during bootstrap.

#### Scenario: No parse worker outlives a completed Crawl
- **WHEN** a Crawl subprocess with the pool selected ends with the Crawl State `completed`
- **THEN** 10 seconds later none of its child processes is still running

#### Scenario: An interrupt ends the parse workers
- **WHEN** a foreground Crawl subprocess with the pool selected receives SIGINT on POSIX or Ctrl+Break addressed to its process group on Windows while a worker is preparing a Page
- **THEN** the Crawl stops with exit code 130 and Store state `stopped` with `stop_reason = interrupt`, unfinished URLs remain `queued`, and no parse child remains 10 seconds after the owner exits

#### Scenario: Ctrl+Break ends the parse tree during Windows bootstrap
- **WHEN** a foreground Crawl with the pool selected receives programmatic Ctrl+Break addressed to the owner's process group or broadcast on its Windows console, while the guardian, an initial worker or a replacement is in bootstrap
- **THEN** the owner takes the interrupt stop path and exits with code 130, the children end through owner or guardian cleanup, no parse child remains 10 seconds after the owner exits, and the Store retains the committed results and leaves unfinished URLs `queued`

### Requirement: No console windows on Windows
On Windows, the guardian and workers SHALL start without visible console windows, whether or not the Crawl owner is attached to a console. Redirected file and pipe standard streams SHALL remain usable in the children during bootstrap and afterwards.

#### Scenario: Parse workers open no console window (Windows)
- **WHEN** a Crawl with the pool selected runs on Windows in a process created with `CREATE_NO_WINDOW`, and `/` links to 30 Pages
- **THEN** no visible top-level window belongs to any of its child processes while it runs, and the Store contains all 31 parsed Pages after completion
