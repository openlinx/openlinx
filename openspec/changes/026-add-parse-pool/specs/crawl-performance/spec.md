## Purpose

Keep parsing off the crawl process, so a large Crawl uses several CPU cores while fetching goes on. It also keeps that safe: memory stays bounded, a crashing worker is contained, workers end with their Crawl, and no console windows appear on Windows.

Scenario conventions:
- `{site}` is the origin of the local fixture site, for example `http://127.0.0.1:8765`.
- A bare path such as `/about` means `{site}/about`.
- "An extractor registered for the test" is registered through `020-add-crawl-core`'s public extractor registry.

## ADDED Requirements

### Requirement: Parsing in worker processes
The Crawl SHALL run every extractor on parsed responses in worker processes separate from the crawl process, started with the `spawn` method on every OS. There SHALL be `min(8, max(1, CPU count − 1))` workers. The `data` of the `crawl_started` event SHALL add `parse_workers`, the number of workers. Extractors and sinks SHALL keep the interface of `020-add-crawl-core`.

#### Scenario: Pages are parsed outside the crawl process
- **WHEN** an extractor registered for the test records the process id it runs in, `/` links to `/about`, and `spider crawl {site}/` runs
- **THEN** no recorded process id equals the crawl process's id

#### Scenario: The number of parse workers is reported
- **WHEN** `spider crawl {site}/` runs
- **THEN** `data.parse_workers` of the `crawl_started` event is an integer from 1 to 8

#### Scenario: Pages are parsed in worker processes on Windows (Windows)
- **WHEN** `spider crawl {site}/` runs as a subprocess on Windows, and `/` links to `/about`
- **THEN** it exits with code 0, and `{site}/about` has `parsed` = 1

### Requirement: Bounded parse queue
When parsing falls behind, fetching SHALL wait. At no time SHALL more than `--concurrency` + 2 × `parse_workers` Pages be requested but not yet parsed.

#### Scenario: Fetching waits for slow parsing
- **WHEN** an extractor registered for the test takes 1 second per Page, `/` links to `/p1` to `/p50`, and `spider crawl {site}/` runs with the default `--concurrency`
- **THEN** the highest number of Pages requested but not yet parsed is at most 5 + 2 × `parse_workers`

### Requirement: A crashed parse worker is replaced
When a worker process dies while it parses a response, the Crawl SHALL:
- replace the worker
- record that URL with `parsed` = 0 and `parse_error` = `worker_crashed`, a value this change adds
- parse the other responses that were waiting or in flight, and go on

#### Scenario: A crashed worker is recorded
- **WHEN** an extractor registered for the test ends its worker process on `{site}/die`, and `/` links to `/die` and `/ok`
- **THEN** `{site}/die` has `parsed` = 0 and `parse_error` = `worker_crashed`

#### Scenario: The Crawl continues after a worker crash
- **WHEN** an extractor registered for the test ends its worker process on `{site}/die`, and `/` links to `/die` and `/ok`
- **THEN** `{site}/ok` has `parsed` = 1, and the Crawl ends with the Crawl State `completed`

### Requirement: Parse workers end with the Crawl
Every worker process SHALL have ended within 10 seconds after the crawl process ends, whether the Crawl completed or was stopped by an interrupt. Workers SHALL ignore interrupts themselves, so that the crawl process shuts them down in order.

#### Scenario: No parse worker outlives a completed Crawl
- **WHEN** a `spider crawl {site}/` subprocess ends with the Crawl State `completed`
- **THEN** 10 seconds later none of its child processes is still running

#### Scenario: An interrupt ends the parse workers
- **WHEN** a `spider crawl {site}/` subprocess is stopped by SIGINT (CTRL_BREAK_EVENT on Windows) while `/` links to 30 pages
- **THEN** 10 seconds after it exits, none of its child processes is still running

### Requirement: No console windows on Windows
On Windows, worker processes SHALL be created without a console window of their own, inheriting their parent's console. A Crawl running in a process that has no visible console, as `060-add-crawl-control`'s background process has, SHALL therefore open no window.

#### Scenario: Parse workers open no console window (Windows)
- **WHEN** `spider crawl {site}/` runs on Windows in a process created with CREATE_NO_WINDOW, and `/` links to 30 pages
- **THEN** no visible top-level window belongs to any of its child processes while it runs
