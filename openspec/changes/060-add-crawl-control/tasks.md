> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

Each task below is one vertical TDD slice and one commit. It is done when:
1. the test for the named scenario, or trivial pair of scenarios, written first at the named seam, fails for the right reason
2. only enough code is written to make it pass
3. ruff, the strict type checker and the full suite (with the coverage gate) pass
4. the commit message names the scenario

A slice that needs a new table or column adds it through `018`'s `public_table()`, with its description, and updates `docs/schema.md` in the same commit, so the contract test never goes red. "The slow fixture site" is the one defined in the spec.

Seams (docs/testing.md):
- **[CLI]**: seam 1, `CliRunner`
- **[Subprocess]**: seam 1, real `spider` processes, run on Windows, macOS and Linux in CI unless a task limits the OS
- **[Services]**: seam 2, the Crawl Service and the store API with a temporary Workspace
- **[HTTP]**: seam 3, the real crawler against the fixture site, asserting on its request log
- **[3+6]**: run the Commands, then read the documented tables read-only
- **[Pure]**: seam 4
- **[Fake clock]**: the injectable clock, for time-based rules only
- **[Spawn double]**: the OS process-spawn call replaced by a double, never our own launcher

## 1. Stop requests through the crawl store

- [ ] 1.1 [Subprocess] Drive "A foreground Crawl in another terminal is stopped". It covers:
  - the `stop` Command
  - the `control_requests` table (`id`, `kind`, `requested_at`, `requested_by_pid`) declared with `info={"control": True}`, and `write_control` in `spider.store.control` (design D12)
  - the engine checking for requests every second and setting `020`'s stop flag with `stop_reason` = `requested`
- [ ] 1.2 [Services] Drive "A control write cannot change other tables": the authorizer of `write_control`.
- [ ] 1.3 [3+6] Drive "A stop request is recorded as handled": the `handled_at` column.
- [ ] 1.4 [3+6] Drive "A stop request names who wrote it and which run handled it": the `crawl_runs` table (`id`, `started_at`, `command_argv`, `detached`, `pid`), and `handled_by_run_id`.
- [ ] 1.5 [CLI] Drive "A stop request refers to its run".
- [ ] 1.6 [Subprocess] Drive "Stop waits for the Crawl to stop": `--wait`, with a default of 60 seconds.
- [ ] 1.7 [Subprocess] Drive "Stop can return at once": `--wait 0` and `stop_requested`.
- [ ] 1.8 [Subprocess] Drive "A request that outlasts the grace period stays queued".
- [ ] 1.9 [CLI] Drive "Stopping a completed Crawl changes nothing".
- [ ] 1.10 [Subprocess] Drive "A Crawl waiting for the network stops at once": a stop request ends `020`'s network pause without waiting for the next probe.
- [ ] 1.11 Docs: start `docs/crawl-control.md` with the Crawl State transitions, `stop_requested` and `spider stop`.
- [ ] 1.12 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. Status, rate and ETA

- [ ] 2.1 [CLI] Drive "Status of a completed Crawl": the `status` Command, with counts over `urls` for a Crawl that is not running, `seed_count`, `status_classes` and `completed_at`.
- [ ] 2.2 [CLI] Drive "Status defaults to the latest Crawl".
- [ ] 2.3 [Services + Fake clock] Drive "The heartbeat records the progress counters": a heartbeat every 5 seconds writing `heartbeat_at`, `020`'s progress counters with the status classes added, and `urls_per_second` (design D7).
- [ ] 2.4 [Services] Drive "Rate and ETA from recent progress": `rate` and the counts of a running Crawl from its last heartbeat.
- [ ] 2.5 [Pure] Drive "The average rate covers every run".
- [ ] 2.6 [Pure] Drive "The URL limit caps the ETA".
- [ ] 2.7 [Pure] Drive "The ETA of a Spider-mode Crawl is a lower bound" and "The ETA of a List-mode Crawl is not a lower bound".
- [ ] 2.8 [Subprocess] Drive "A running Crawl hints how to stop it": the next-step hints per Crawl State.
- [ ] 2.9 [CLI] Drive "A Crawl stopped by the URL limit hints at a higher limit".
- [ ] 2.10 [Subprocess] Drive "A pending stop request is reported".
- [ ] 2.11 [CLI] Drive "Status of a failed Crawl shows its error": the `crawl_runs.error` column.
- [ ] 2.12 [Subprocess] Drive "Status of a Crawl waiting for the network": the `crawl_runs.paused_since` column, written by the heartbeat during `020`'s network pause, and `paused_since` in `status`.
- [ ] 2.13 Docs: document every `status` field, where its counts come from, the rate window, the average rate and ETA semantics in `docs/crawl-control.md`.
- [ ] 2.14 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. Dead processes

- [ ] 3.1 [Subprocess] Drive "A killed Crawl is reported as interrupted". Add the writer claim in `spider.store.claim`, taken by every process that creates or runs a Crawl before the crawl file is written, and `check_writer`, which records `interrupted` under the claim through `020`'s `set_state` with `running` → `interrupted` added to `TRANSITIONS` (design D12).
- [ ] 3.2 [Subprocess, Windows in CI] Drive "A Crawl ended with TerminateProcess is reported as interrupted (Windows)".
- [ ] 3.3 [3+6] Drive "The interrupted state is recorded": the `crawl_runs.end_state` column.
- [ ] 3.4 [Services + Fake clock] Drive "A stale heartbeat is reported as a warning", with the test process holding the claim through `spider.store.claim`.
- [ ] 3.5 Docs: document dead-process detection and `heartbeat_stale` in `docs/crawl-control.md`.
- [ ] 3.6 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. Resume

- [ ] 4.1 [Subprocess] Drive "A stopped Crawl is completed by resume": the `resume` Command on `020`'s continue operation, with a new run row and the `run` field, and `interrupted` → `running` added to `TRANSITIONS`.
- [ ] 4.2 [HTTP] Drive "Fetched URLs are not requested again".
- [ ] 4.3 [HTTP] Drive "robots.txt is fetched again on resume".
- [ ] 4.4 [Subprocess] Drive "A failed Crawl can be resumed".
- [ ] 4.5 [CLI] Drive "A completed Crawl cannot be resumed": `crawl_completed` with the re-run hint.
- [ ] 4.6 [Subprocess] Drive "A running Crawl cannot be resumed": `crawl_locked`, declared by this change.
- [ ] 4.7 [CLI] Drive "Other settings cannot change on resume": `override_not_allowed`.
- [ ] 4.8 [CLI] Drive "A Crawl stopped by the URL limit needs a higher limit": `limit_reached`.
- [ ] 4.9 [HTTP] Drive "A higher URL limit continues the Crawl".
- [ ] 4.10 [CLI] Drive "Redacted credentials must be given again": `secrets_required` for secrets that came from flags.
- [ ] 4.11 [HTTP] Drive "Credentials given again are used".
- [ ] 4.12 [HTTP] Drive "Credentials from spider.toml are read again".
- [ ] 4.13 [3+6] Drive "A politeness override is recorded".
- [ ] 4.14 [HTTP] Drive "Proxy variables are read again on resume", with `022`'s local test proxy. This slice lands after `022`-min, which honours the proxy variables; the rest of 060-min does not depend on `022`.
- [ ] 4.15 [3+6] Drive "Each run is recorded": the `ended_at` and `stop_reason` columns of `crawl_runs`.
- [ ] 4.16 [CLI] Drive "Runs share the stop reasons of the Crawl": `stop_reason` from `020`'s `StopReason`.
- [ ] 4.17 [Subprocess] Drive "Two resumes at the same time": claim acquisition with a 2-second retry.
- [ ] 4.18 [Subprocess, Windows in CI] Drive "A killed Crawl can be resumed at once (Windows)".
- [ ] 4.19 [Subprocess, POSIX in CI] Drive "A killed Crawl can be resumed at once (macOS and Linux)".
- [ ] 4.20 Docs: document `spider resume` (the Crawl States it accepts, what may change, secrets, the URL limit) in `docs/crawl-control.md`.
- [ ] 4.21 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Background Crawls

- [ ] 5.1 [Services] Drive "A reserved id is drawn again" (`crawl-store`): the id draw counts `<id>.lock` and `<id>.log` as taken.
- [ ] 5.2 [Services] Drive "A chosen id is created once" (`crawl-store`): `create_crawl` with a chosen id, and `crawl_id_taken`.
- [ ] 5.3 [Services] Guard "Id from the start time", "A taken id is drawn again" and "Character set" (`crawl-store`, unchanged from `015`): `015`'s tests for them still pass after the id draw counts `<id>.lock` and `<id>.log`. No new test; run them and name them in the commit.
- [ ] 5.4 [Subprocess] Drive "Detach returns while the Crawl runs": spawn the hidden `--_run-detached` entry point, have the child create the Crawl with the id the parent chose, and wait for its run row.
- [ ] 5.5 [Subprocess] Drive "The background Crawl runs to its end".
- [ ] 5.6 [Subprocess] Drive "The log file holds the progress events": reserve the id by creating `<id>.log` exclusively, and send the child's stdout and stderr to it.
- [ ] 5.7 [3+6] Drive "A detached run is marked".
- [ ] 5.8 [Subprocess] Drive "A secret is not on the background command line": secrets handed over in one environment variable, which the child removes after reading.
- [ ] 5.9 [Subprocess, Windows in CI] Drive "Detach prints absolute Windows paths (Windows)".
- [ ] 5.10 [CLI + Spawn double] Drive "A background process that dies at start is reported": `detach_failed`.
- [ ] 5.11 [CLI + Spawn double + Fake clock] Drive "A slow start is reported, not hidden": `detach_unconfirmed`.
- [ ] 5.12 [Subprocess] Drive "A detached Crawl reads its list from standard input": the parent reads the list and writes the Seed hand-over file.
- [ ] 5.13 [CLI] Drive "A bad list fails before anything starts".
- [ ] 5.14 [Subprocess, Windows in CI] Drive "Closing the console does not end the Crawl (Windows)": `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`.
- [ ] 5.15 [Subprocess, Windows in CI] Drive "No console window appears (Windows)".
- [ ] 5.16 [Subprocess, Windows in CI] Drive "A job that would end the Crawl is reported (Windows)": `CREATE_BREAKAWAY_FROM_JOB` with its fallback, and the job-object query.
- [ ] 5.17 [Subprocess, POSIX in CI] Drive "Hanging up the terminal does not end the Crawl (macOS and Linux)": `start_new_session`, stdin from `/dev/null`.
- [ ] 5.18 [Subprocess] Drive "Resume can run in the background": `resume --detach`.
- [ ] 5.19 [Subprocess] Drive "A resumed Crawl is running again".
- [ ] 5.20 [Subprocess] Drive "A Crawl that reaches its end is completed".
- [ ] 5.21 Docs: document background Crawls, log files, detached List mode, agent sandboxes and Windows job objects, and the Hand-off flow, in `docs/crawl-control.md`.
- [ ] 5.22 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green.

## 6. Dry run, estimate and equivalent command

- [ ] 6.1 [CLI] Drive "The resolved config is printed": `--dry-run` reusing `020`'s `plan_crawl` (validation and config resolution, `spider.services.crawling`).
- [ ] 6.2 [CLI] Drive "A dry run writes nothing".
- [ ] 6.3 [CLI] Drive "Invalid arguments fail as in a real Crawl".
- [ ] 6.4 [Pure] Drive "Quoting for POSIX shells": the command renderer, with its flag order and default suppression.
- [ ] 6.5 [Pure] Drive "Quoting for PowerShell".
- [ ] 6.6 [Pure] Drive "A Windows list path is quoted for PowerShell (Windows)".
- [ ] 6.7 [CLI] Drive "A setting from spider.toml becomes a flag".
- [ ] 6.8 [CLI] Drive "Settings that are not flags are reported": `settings_not_in_command`.
- [ ] 6.9 [CLI] Drive "Proxy variables are left to the environment".
- [ ] 6.10 [CLI] Drive "A relative list path becomes absolute".
- [ ] 6.11 [CLI] Drive "Secrets are placeholders".
- [ ] 6.12 [HTTP] Drive "Sitemaps named in robots.txt are counted": the Spider-mode estimate over `024`'s sitemap reader and `020`'s Scope rules.
- [ ] 6.13 [HTTP] Drive "Only robots.txt and sitemaps are requested".
- [ ] 6.14 [HTTP] Drive "The Scope filters the count".
- [ ] 6.15 [HTTP] Drive "No sitemap means no estimate": the `/sitemap.xml` fallback.
- [ ] 6.16 [CLI] Drive "A list is counted exactly".
- [ ] 6.17 [HTTP] Drive "Too many sitemaps lower the confidence": the 50-file and 60-second budget.
- [ ] 6.18 [HTTP] Drive "An estimate above the URL limit is flagged".
- [ ] 6.19 [CLI] Drive "Nothing is requested without an estimate": `--no-estimate`.
- [ ] 6.20 [HTTP] Drive "A dry run without network still validates", with the DNS resolver hook failing every lookup.
- [ ] 6.21 [Subprocess] Drive "The command reproduces the config": the round trip.
- [ ] 6.22 [Services] Drive "A Crawl started through the Crawl Service records an equivalent command": the synthesised argv.
- [ ] 6.23 Docs: document the dry run, the estimate (basis, confidence, what it does not count, a null estimate) and the Hand-off command in `docs/crawl-control.md`.
- [ ] 6.24 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.

## 7. Listing, showing and removing Crawls

- [ ] 7.1 [CLI] Drive "Crawls are listed newest first": `crawls list` in `010`'s paging envelope.
- [ ] 7.2 [CLI] Drive "Crawls are filtered by state": `--state`.
- [ ] 7.3 [CLI] Drive "An unreadable crawl file does not break the list": a full `crawl_file_invalid` diagnostic in the item.
- [ ] 7.4 [Subprocess] Drive "A Crawl started by the user is listed".
- [ ] 7.5 [CLI] Drive "The recorded command is shown": `crawls show`.
- [ ] 7.6 [CLI] Drive "The re-run command is shown".
- [ ] 7.7 [CLI] Drive "A completed Crawl is removed": `crawls rm` with its companion files, `paths` and `freed_bytes`.
- [ ] 7.8 [CLI] Drive "A Crawl's reports are removed with it".
- [ ] 7.9 [CLI] Drive "latest is not accepted".
- [ ] 7.10 [Subprocess] Drive "A running Crawl is not removed".
- [ ] 7.11 [Subprocess, Windows in CI] Drive "A crawl file open in another process is not removed (Windows)": rename first, report `file_in_use`, delete nothing.
- [ ] 7.12 [Subprocess, POSIX in CI] Drive "A crawl file open for reading is removed (macOS and Linux)".
- [ ] 7.13 Docs: document `crawls list|show|rm`, including the removal of reports and notes, in `docs/crawl-control.md`.
- [ ] 7.14 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. Change check

- [ ] 8.1 Verify that every `#### Scenario:` in `specs/crawl-control/spec.md`, and the two new ones in `specs/crawl-store/spec.md`, has exactly one test named after it. Use a small script over the test ids.
- [ ] 8.2 Verify that the whole suite, including the subprocess scenarios, passes in CI on Windows, macOS and Linux × Python 3.12–3.14 with the coverage gate.
- [ ] 8.3 **Guard:** every code this change declares (design D14) is listed by `spider commands` with its level and exit code, at the CLI seam. The v0.2 codes join the guard in the slices that raise them.
- [ ] 8.4 Review: run the code-review skill on the whole change against `specs/crawl-control/spec.md`, then refactor with the whole suite green.
