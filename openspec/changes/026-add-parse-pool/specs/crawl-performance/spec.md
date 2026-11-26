## Purpose

Keep page preparation off the crawl process, so a large Crawl uses several CPU cores while fetching goes on. It also keeps that safe: memory stays bounded, a crashing worker and a Page that takes too long are contained, workers end with their Crawl, and no console windows appear on Windows.

Scenario conventions:
- `{site}` is the origin of the local fixture site, for example `http://127.0.0.1:8765`.
- A bare path such as `/about` means `{site}/about`.
- "An extractor added for the test" is added to `020-add-crawl-core`'s `default_hooks()` and passed to the Crawl Service, as `020`'s design D9 allows.
- A test may shorten the preparation deadline through the pool executor's parameter; the scenarios hold for any deadline.

## ADDED Requirements

### Requirement: Page preparation in worker processes
The Crawl SHALL run page preparation (parsing, the link extractor and every registered extractor) in worker processes separate from the crawl process, started with the `spawn` method on every OS. There SHALL be one worker per physical core available to the crawl process minus 2, and at least 1. The `data` of the `crawl_started` event SHALL add `parse_workers`, the number of workers. Extractors and per-response handlers SHALL keep the interface of `020-add-crawl-core`.

#### Scenario: Pages are parsed outside the crawl process
- **WHEN** an extractor added for the test records the process id it runs in, `/` links to `/about`, and a Crawl of `{site}/` runs
- **THEN** no recorded process id equals the crawl process's id

#### Scenario: The number of parse workers is reported
- **WHEN** `linx crawl {site}/` runs
- **THEN** `data.parse_workers` of the `crawl_started` event is the number of physical cores available to the crawl process minus 2, and at least 1

#### Scenario: Pages are parsed in worker processes on Windows (Windows)
- **WHEN** `linx crawl {site}/` runs as a subprocess on Windows, and `/` links to `/about`
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
Every worker process SHALL have ended within 10 seconds after the crawl process ends, whether the Crawl completed or was stopped by an interrupt. The crawl process SHALL handle the owner's interrupts and shut its workers down in order. On Windows the guardian and every worker, including replacements, SHALL be isolated from the Crawl's console beginning at process creation.

#### Scenario: No parse worker outlives a completed Crawl
- **WHEN** a `linx crawl {site}/` subprocess ends with the Crawl State `completed`
- **THEN** 10 seconds later none of its child processes is still running

#### Scenario: An interrupt ends the parse workers
- **WHEN** a `linx crawl {site}/` subprocess is stopped by SIGINT on POSIX or by Ctrl+Break on Windows while `/` links to 30 Pages
- **THEN** 10 seconds after it exits, none of its child processes is still running
- **AND** a URL whose Page was still in preparation when the grace period ended remains `queued`

#### Scenario: Ctrl+Break ends the parse tree during Windows bootstrap
- **WHEN** the foreground Crawl receives a single Ctrl+Break targeted at its process group or broadcast across its console while the guardian, an initial worker or a replacement is still bootstrapping
- **THEN** only the Crawl receives the event, reports `stopping` with reason `interrupt`, and exits with code 130 and Crawl State `stopped`
- **AND** its guardian and workers are shut down by the Crawl, without a console termination and within 10 seconds of Crawl exit
- **AND** an unfinished URL whose outcome was never submitted remains `queued`

### Requirement: No console windows on Windows
On Windows, the guardian and worker processes SHALL start without a visible console window, including when the Crawl starts with no visible console. Redirected standard streams backed by a file or pipe SHALL remain usable in those children.

#### Scenario: Parse workers open no console window (Windows)
- **WHEN** `linx crawl {site}/` runs on Windows in a process created with CREATE_NO_WINDOW, and `/` links to 30 pages
- **THEN** no visible top-level window belongs to any of its child processes while it runs
