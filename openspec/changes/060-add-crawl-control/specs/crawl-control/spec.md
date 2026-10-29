## Purpose

Run long Crawls in the background, then watch, stop and resume them through the crawl store. Check a Crawl's configuration and size with a dry run before it starts, and list, inspect and remove the Crawls of a Workspace. This is the mechanism behind Hand-off: an agent gives the user a ready command, and reads the Crawl's data later.

Scenario conventions:
- `{site}` is the origin of the local fixture site, for example `http://127.0.0.1:8765`.
- "The slow fixture site" is a site whose `/` links to `/p1` to `/p60`, each answering after 1 second.
- `site.test` and `other.test` are virtual hosts of the fixture site (`022-add-fetch-policy`).
- `<id>` is the crawl id printed by the Command that started the Crawl.
- Scenarios that start processes run real `linx` subprocesses in a temporary Workspace on each OS.

## ADDED Requirements

### Requirement: Crawl State transitions
A Crawl's Crawl State is `crawl.state` from `015-add-crawl-store`: `running`, `stopped`, `completed`, `failed` or `interrupted`. It SHALL change only along the transitions of `020-add-crawl-core`'s transition table, to which this change adds `running` → `interrupted` and `interrupted` → `running`:

| From | To | When |
|---|---|---|
| (new) | `running` | a process creates the Crawl and holds its writer claim |
| `running` | `completed` | nothing is left `queued` and the post-crawl passes are done |
| `running` | `stopped` | a stop request, an interrupt or `--max-urls` ended it early (`crawl.stop_reason` `requested`, `interrupt` or `max_urls`) |
| `running` | `failed` | it could not continue (`crawl.stop_reason` `seed_unreachable`, `site_unreachable` or `write_failed`) |
| `running` | `interrupted` | its process is gone without having recorded an end |
| `stopped`, `interrupted`, `failed` | `running` | `linx resume` |

`completed` SHALL be final. While a stop request is waiting to be handled, the Crawl SHALL stay `running`, and the Commands of this capability SHALL report `"stop_requested": true`.

> **v0.1.**

#### Scenario: A Crawl that reaches its end is completed
- **WHEN** `linx crawl {site}/ --detach` runs on a site whose `/` links to `/a`, and `linx status --crawl <id>` is polled until the state is no longer `running`
- **THEN** `linx status --crawl <id>` prints `"state": "completed"` and `"stop_reason": null`

#### Scenario: A pending stop request is reported
- **WHEN** a stop request for a `running` Crawl has been written and not yet handled, and `linx status --crawl <id>` runs
- **THEN** it prints `"state": "running"` and `"stop_requested": true`

#### Scenario: A resumed Crawl is running again
- **WHEN** a `stopped` Crawl of the slow fixture site is resumed with `linx resume --crawl <id> --detach`
- **THEN** `linx status --crawl <id>` prints `"state": "running"`

### Requirement: Background Crawls
`linx crawl … --detach` SHALL validate its arguments exactly like a foreground `linx crawl`, with the same error codes and exit codes. It SHALL then start a separate background process that creates the Crawl, with an id that the detaching Command reserved by creating `<crawl id>.log` (see `crawl-store`'s "Crawl ids"), and runs it to its end. Within 10 seconds, the Command SHALL:
1. print on stdout `{"crawl_id", "state", "run", "pid", "crawl_file", "log_file", "warnings", "hint"}`
2. exit with code 0

The fields are:
- `state`: `running` once the background process has created the Crawl and holds its writer claim. It is `null`, with a `detach_unconfirmed` warning, when that has not happened within 10 seconds.
- `run`: 1.
- `pid`: the background process id.
- `hint`: names `linx status --crawl <crawl id>` and `linx stop --crawl <crawl id>`.

Other rules:
- **Paths:** they SHALL be absolute.
- **The log file:** it SHALL be `<crawl id>.log` in the same folder as the crawl file. The background process SHALL write its progress events and diagnostics there, in the formats a foreground Crawl writes to stderr.
- **The run:** it SHALL be recorded with `detached` = 1.
- **Secrets:** they SHALL be passed to the background process through its environment, never on its command line.
- **Failure to start:** if the background process exits before it has created the Crawl, the Command SHALL exit with code 1 and error code `detach_failed`, with a hint that contains the log file's path.

> **v0.1**, except the scenario "A secret is not on the background command line", which needs the `--auth` flag of `022-add-fetch-policy` (**v0.2**).

#### Scenario: Detach returns while the Crawl runs
- **WHEN** `linx crawl {site}/ --detach` runs against the slow fixture site
- **THEN** it exits with code 0 within 10 seconds and prints `"state": "running"` and `"run": 1`

#### Scenario: The background Crawl runs to its end
- **WHEN** `linx crawl {site}/ --detach` runs against a site whose `/` links to `/a`, and the detaching process has exited
- **THEN** `linx status --crawl <id>` reports `"state": "completed"` within 60 seconds

#### Scenario: The log file holds the progress events
- **WHEN** a Crawl started with `linx crawl {site}/ --detach` has completed
- **THEN** the first line of the file named by `log_file` parses as a JSON object with `"event": "crawl_started"`

#### Scenario: A detached run is marked
- **WHEN** a Crawl started with `linx crawl {site}/ --detach` has completed
- **THEN** its `crawl_runs` row with `id` 1 has `detached` = 1

#### Scenario: A secret is not on the background command line
- **WHEN** `linx crawl {site}/ --auth "alice:s3cret" --detach` runs against the slow fixture site
- **THEN** the command line of the process with the printed `pid`, as the operating system reports it, does not contain `s3cret`

#### Scenario: Detach prints absolute Windows paths (Windows)
- **WHEN** `linx crawl {site}/ --detach` runs on Windows
- **THEN** `crawl_file` and `log_file` both match `^[A-Za-z]:\\`, and `log_file` ends with `.log`

#### Scenario: A slow start is reported, not hidden
- **WHEN** the operating system's process-spawn call is replaced by a double whose process stays alive without creating the Crawl, and `linx crawl {site}/ --detach` runs with a fake clock
- **THEN** it exits with code 0 after 10 seconds of clock time, prints `"state": null`, and its `warnings` hold an entry with code `detach_unconfirmed`

#### Scenario: A background process that dies at start is reported
- **WHEN** the operating system's process-spawn call is replaced by a double whose process exits with code 1 at once, and `linx crawl {site}/ --detach` runs
- **THEN** the Command exits with code 1, and its only stderr error has `code` = `detach_failed` and a `hint` that contains the path of the log file

### Requirement: Detached List-mode Crawls
With `--list` (`024-add-list-and-sitemap-modes`) and `--detach`, the detaching Command SHALL read and check the list itself, and store the Seeds for the background process, before that process starts. So `--list -` SHALL work with `--detach`, and list errors such as `empty_list` SHALL be reported by the detaching Command, with no background process started and no Crawl created.

> **v0.2.**

#### Scenario: A detached Crawl reads its list from standard input
- **WHEN** `linx crawl --list - --detach` runs with the line `{site}/a` on standard input, and the Crawl then completes
- **THEN** its `seeds` table holds exactly the row `(1, "{site}/a")`

#### Scenario: A bad list fails before anything starts
- **WHEN** `linx crawl --list urls.txt --detach` runs and `urls.txt` holds only the line `# nothing yet`
- **THEN** the Command exits with code 2 with the error code `empty_list`, and the crawls folder holds no new file

### Requirement: Background Crawls outlive their terminal
The background process SHALL survive the end of the process and terminal that started it:
- **On Windows:**
  - It SHALL be created in a new process group with CREATE_NO_WINDOW, so that it shows no console window. The parse worker processes of `026-add-parse-pool` SHALL show none either.
  - It SHALL be created outside the caller's job object when that job allows breakaway.
  - When the caller's job object kills its processes on close and does not allow breakaway, the output SHALL hold a `job_may_end_crawl` warning whose hint suggests running the Command from a normal terminal.
- **On macOS and Linux:** it SHALL run in a new session, with standard input from the null device.

> **v0.1.**

#### Scenario: Closing the console does not end the Crawl (Windows)
- **WHEN** `linx crawl {site}/ --detach` runs inside a console process started with CREATE_NEW_CONSOLE against the slow fixture site, and that console process is then terminated
- **THEN** `linx status --crawl <id>` reports `"state": "completed"` within 120 seconds

#### Scenario: Hanging up the terminal does not end the Crawl (macOS and Linux)
- **WHEN** `linx crawl {site}/ --detach` runs from a shell on a pseudo-terminal against the slow fixture site, and SIGHUP is then sent to that shell's process group
- **THEN** `linx status --crawl <id>` reports `"state": "completed"` within 120 seconds

#### Scenario: No console window appears (Windows)
- **WHEN** a Crawl started with `linx crawl {site}/ --detach` is running against the slow fixture site on Windows
- **THEN** no visible top-level window belongs to the background process or to any of its child processes

#### Scenario: A job that would end the Crawl is reported (Windows)
- **WHEN** `linx crawl {site}/ --detach` runs from a process assigned to a job object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE and without JOB_OBJECT_LIMIT_BREAKAWAY_OK
- **THEN** the printed `warnings` hold an entry with code `job_may_end_crawl`

### Requirement: Control through the crawl store
`status`, `stop` and `resume` SHALL work only through the crawl store and its writer claim, never through operating-system signals.
- **Stop requests:** a stop request SHALL be a row in `control_requests`, a control table.
- **Control writes:** a process that does not hold the Crawl's writer claim (see "One writer per Crawl") SHALL write only to control tables, through a connection on which every write to another table is refused, waiting up to 5 seconds for a busy file. Recording `interrupted` is the only other write without the running process's claim (see "Detecting a dead crawl process").
- **Checking for requests:** the crawl process, foreground or background, SHALL check for new requests at least once per second.
- **Handling:** for each request it acts on, it SHALL set `handled_at` and `handled_by_run_id`.

> **v0.1.**

#### Scenario: A foreground Crawl in another terminal is stopped
- **WHEN** `linx crawl {site}/` runs as a subprocess against the slow fixture site, and `linx stop --crawl <id>` runs in another process
- **THEN** the crawl subprocess exits with code 0 and prints `"state": "stopped"` and `"stop_reason": "requested"`

#### Scenario: A stop request is recorded as handled
- **WHEN** a running Crawl has been stopped with `linx stop --crawl <id>`
- **THEN** `control_requests` holds one row with `kind` = `stop` and a non-null `handled_at`

#### Scenario: A control write cannot change other tables
- **WHEN** a process that does not hold the writer claim of a `running` Crawl tries to set its `crawl.state` to `stopped` through the control-write connection
- **THEN** the write is refused, and `crawl.state` is still `running`

### Requirement: Stopping a Crawl
`linx stop [--crawl <ref>]` (default `latest`) SHALL request a graceful stop. The crawl process then:
- starts no new request
- gives requests in flight up to 10 seconds
- stores everything received
- runs the post-crawl passes
- ends with the Crawl State `stopped` and `crawl.stop_reason` = `requested`

URLs not completed SHALL stay `queued`.

The Command SHALL wait until the state is `stopped`, or until `--wait <seconds>` (default 60) has passed. It SHALL then print `{"crawl_id", "state", "stop_reason", "stop_requested"}` and exit with code 0. With `--wait 0` it SHALL return as soon as the request is recorded.

A Crawl that is paused waiting for the network (`020-add-crawl-core`) has no request in flight, so a stop request SHALL stop it at once, without waiting for its next probe of the Seed.

For a Crawl that is not `running`, `stop` SHALL change nothing, print its Crawl State and exit with code 0. For a `running` Crawl whose process is gone, it SHALL first record `interrupted`, as "Detecting a dead crawl process" describes.

> **v0.1.**

#### Scenario: Stop waits for the Crawl to stop
- **WHEN** a Crawl of the slow fixture site is running in another process, and `linx stop --crawl <id>` runs
- **THEN** it exits with code 0 and prints `"state": "stopped"` and `"stop_reason": "requested"`

#### Scenario: Stop can return at once
- **WHEN** a Crawl of the slow fixture site is running in another process, and `linx stop --crawl <id> --wait 0` runs
- **THEN** it prints `"state": "running"` and `"stop_requested": true`

#### Scenario: A request that outlasts the grace period stays queued
- **WHEN** a running Crawl has `/hang` (which answers after 60 seconds) in flight, and `linx stop --crawl <id>` runs
- **THEN** after the Crawl is `stopped`, `{site}/hang` has `fetch_state` = `queued`

#### Scenario: A Crawl waiting for the network stops at once
- **WHEN** a Crawl in another process has paused because its site stopped answering, and `linx stop --crawl <id>` runs
- **THEN** it exits with code 0 within 15 seconds and prints `"state": "stopped"` and `"stop_reason": "requested"`

#### Scenario: Stopping a completed Crawl changes nothing
- **WHEN** `linx stop --crawl <id>` runs for a `completed` Crawl
- **THEN** it exits with code 0 and prints `"state": "completed"`

### Requirement: The status Command
`linx status [--crawl <ref>]` (default `latest`) SHALL print, for a Crawl in any Crawl State, one JSON object with these fields:
- `crawl_id`, `state`, `stop_reason`, `stop_requested`, `crawl_mode`, `seed`, `seed_count`, `section_crawl`
- `paused_since`: while a `running` Crawl is paused waiting for the network (`020-add-crawl-core`), when the pause began, as its last heartbeat recorded it; otherwise null
- `started_at`, `completed_at`, `elapsed_s` (seconds spent in all runs, including the current run up to now)
- `urls`: `discovered`, `fetched`, `errors`, `skipped` and `queued`
- `status_classes`: `2xx`, `3xx`, `4xx`, `5xx` and `other`
- `rate`, `average_rate`, `eta_s`, `eta_is_lower_bound`, `max_urls`
- `pid`, `detached`, `heartbeat_age_s` (for the current or last run)
- `error`: the diagnostic of a `failed` Crawl in the full shape, and null otherwise
- `log_file`, `warnings`, `hint`

Where `urls` and `status_classes` come from depends on the Crawl State:
- **`running`:** from the progress counters that the crawl process recorded at its last heartbeat (see "Recorded runs"), so they trail the process by up to 5 seconds. `status` SHALL NOT count over `urls` while a Crawl runs: `urls` has no index for such counts (`020-add-crawl-core`), so each count would scan the table.
- **Any other state:** counted over the stored `urls` table.

`hint` SHALL be a next-step command:
- `running`: `linx stop --crawl <crawl id>`
- `stopped` by `max_urls`: `linx resume --crawl <crawl id> --max-urls <higher>`
- `stopped` otherwise, `interrupted` or `failed`: `linx resume --crawl <crawl id>`
- `completed`: `linx summary --crawl <crawl id>`

> **v0.1.**

#### Scenario: Status of a completed Crawl
- **WHEN** a Crawl of a site where `/` links to `/a`, `/b` and `/missing` (which returns 404) has completed, and `linx status --crawl <id>` runs
- **THEN** it prints `"state": "completed"`, `"urls": {"discovered": 4, "fetched": 4, "errors": 0, "skipped": 0, "queued": 0}` and `"eta_s": null`

#### Scenario: Status defaults to the latest Crawl
- **WHEN** two Crawls have been started one after the other, and `linx status` runs without `--crawl`
- **THEN** it prints the `crawl_id` of the second Crawl

#### Scenario: A running Crawl hints how to stop it
- **WHEN** a Crawl of the slow fixture site is running in another process, and `linx status --crawl <id>` runs
- **THEN** `hint` contains `linx stop --crawl <id>`

#### Scenario: A Crawl stopped by the URL limit hints at a higher limit
- **WHEN** a Crawl has been stopped by `--max-urls 3`, and `linx status --crawl <id>` runs
- **THEN** `hint` contains `linx resume --crawl <id> --max-urls`

#### Scenario: Status of a Crawl waiting for the network
- **WHEN** a Crawl in another process has paused because its site stopped answering, its heartbeat has been written since, and `linx status --crawl <id>` runs
- **THEN** it prints `"state": "running"` and a timestamp in `paused_since`

#### Scenario: Status of a failed Crawl shows its error
- **WHEN** a Crawl of `http://127.0.0.1:{closed_port}/` has failed because nothing listened, and `linx status --crawl <id>` runs
- **THEN** it prints `"state": "failed"` and an `error` whose `code` is `seed_unreachable`

### Requirement: Rate and ETA
The Commands of this capability SHALL compute four values:
- **`rate`:** the run's `urls_per_second` at its last heartbeat: the URLs requested (`fetched` or `error`) in the last 60 seconds, divided by 60, or by the run's age when it is younger than 60 seconds. It is the `rate` of `020-add-crawl-core`'s progress events. It SHALL be null unless the state is `running`.
- **`average_rate`:** the URLs requested so far in all runs, divided by `elapsed_s`. It SHALL be null when `elapsed_s` is 0.
- **`eta_s`:** the remaining URLs divided by `rate`, rounded to whole seconds. The remaining URLs are the `queued` URLs, capped by the number of requests that `--max-urls` still allows. It SHALL be null unless the state is `running` and `rate` is above 0.
- **`eta_is_lower_bound`:** `true` when new URLs can still be discovered (Spider mode, or a `--max-depth` above 0), and `false` otherwise.

> **v0.1.**

#### Scenario: Rate and ETA from recent progress
- **WHEN** the last heartbeat of a running Crawl with no URL limit recorded `urls_per_second` 2.0 and `queued_count` 300, and its status is computed
- **THEN** `rate` is 2.0 and `eta_s` is 150

#### Scenario: The average rate covers every run
- **WHEN** a Crawl has 600 URLs requested across its runs and an `elapsed_s` of 300, and its status is computed
- **THEN** `average_rate` is 2.0

#### Scenario: The URL limit caps the ETA
- **WHEN** the ETA is computed with `rate` 2.0, 300 URLs queued, `max_urls` 200 and 100 URLs requested so far
- **THEN** `eta_s` is 50

#### Scenario: The ETA of a Spider-mode Crawl is a lower bound
- **WHEN** the ETA of a running Spider-mode Crawl without `--max-depth` is computed
- **THEN** `eta_is_lower_bound` is `true`

#### Scenario: The ETA of a List-mode Crawl is not a lower bound
- **WHEN** the ETA of a running List-mode Crawl with the default `--max-depth` of 0 is computed
- **THEN** `eta_is_lower_bound` is `false`

### Requirement: Detecting a dead crawl process
A crawl process SHALL write a heartbeat in its `crawl_runs` row at least every 5 seconds: `heartbeat_at` and its progress counters. When `status`, `stop`, `resume`, `crawls list` or `crawls show` meets a Crawl whose Crawl State is `running`, it SHALL try to take the Crawl's writer claim without waiting. When it gets the claim, no process is running the Crawl, and it SHALL:
1. in one transaction under the claim, record the Crawl State `interrupted` (with `020-add-crawl-core`'s transition check) and set the last run's `end_state` to `interrupted`
2. release the claim
3. report the Crawl as `interrupted`

When a process holds the claim but its heartbeat is older than 60 seconds, the state SHALL stay `running`, and `status` SHALL add a `heartbeat_stale` warning.

> **v0.1.**

#### Scenario: A killed Crawl is reported as interrupted
- **WHEN** the process of a running Crawl of the slow fixture site is killed with SIGKILL, and `linx status --crawl <id>` runs
- **THEN** it prints `"state": "interrupted"`, and `hint` contains `linx resume --crawl <id>`

#### Scenario: A Crawl ended with TerminateProcess is reported as interrupted (Windows)
- **WHEN** the process of a running Crawl of the slow fixture site is ended with TerminateProcess on Windows, and `linx status --crawl <id>` runs
- **THEN** it prints `"state": "interrupted"`

#### Scenario: The interrupted state is recorded
- **WHEN** `linx status --crawl <id>` has reported a killed Crawl as `interrupted`
- **THEN** `crawl.state` in its crawl file is `interrupted`, and its last `crawl_runs` row has `end_state` = `interrupted`

#### Scenario: A stale heartbeat is reported as a warning
- **WHEN** a test process holds the writer claim of a `running` Crawl whose last `heartbeat_at` is 90 seconds old on the fake clock, and its status is computed
- **THEN** the state is `running`, and `warnings` hold an entry with code `heartbeat_stale`

### Requirement: Resuming a Crawl
`linx resume [--crawl <ref>]` (default `latest`) SHALL continue a Crawl whose Crawl State is `stopped`, `interrupted` or `failed`. It uses the Crawl Service's continue operation (`020-add-crawl-core`) and the recorded config, and SHALL:
- request the `queued` URLs, after putting back every URL that ended as `error`, or with `skip_reason` = `robots_unreachable`, as `020-add-crawl-core`'s continue operation does
- fetch robots.txt again for each origin it requests
- print the result of a foreground `linx crawl`, in the field order of `020-add-crawl-core`'s result (`docs/crawling.md`, "The result"), with the added field `"run"`

With `--detach`, it SHALL run in the background and print the output of `crawl --detach` with the new `run` number.

`resume` SHALL be refused, without changing the Crawl:
- with exit code 1 and error code `crawl_completed` for a `completed` Crawl, with a hint that gives the Crawl's re-run command
- with exit code 5 and error code `crawl_locked` while another process holds the writer claim (see "One writer per Crawl")

> **v0.1.**

#### Scenario: A stopped Crawl is completed by resume
- **WHEN** a Crawl of the slow fixture site has been stopped after about 10 pages, and `linx resume --crawl <id>` runs
- **THEN** it exits with code 0 and prints `"state": "completed"`, and the `urls` table holds `{site}/` and the 60 pages, each with `status_code` = 200

#### Scenario: Fetched URLs are not requested again
- **WHEN** a Crawl of the slow fixture site has been stopped after `/p1` was fetched, and `linx resume --crawl <id>` runs to the end
- **THEN** the fixture site has received exactly one request for `/p1` across both runs

#### Scenario: robots.txt is fetched again on resume
- **WHEN** a stopped Crawl of `{site}` is resumed and runs to the end
- **THEN** the fixture site has received exactly two requests for `/robots.txt` across both runs

#### Scenario: A failed Crawl can be resumed
- **WHEN** a Crawl of `http://127.0.0.1:{port}/` has failed because nothing listened, the fixture site then starts on that port, and `linx resume --crawl <id>` runs
- **THEN** it exits with code 0 and prints `"state": "completed"`

#### Scenario: A completed Crawl cannot be resumed
- **WHEN** `linx resume --crawl <id>` runs for a `completed` Crawl
- **THEN** it exits with code 1, and its only stderr error has `code` = `crawl_completed`

#### Scenario: A running Crawl cannot be resumed
- **WHEN** a Crawl of the slow fixture site is running in another process, and `linx resume --crawl <id>` runs
- **THEN** it exits with code 5, and its only stderr error has `code` = `crawl_locked`

#### Scenario: Resume can run in the background
- **WHEN** `linx resume --crawl <id> --detach` runs for a `stopped` Crawl of the slow fixture site
- **THEN** it exits with code 0 within 10 seconds and prints `"state": "running"` and `"run": 2`

### Requirement: What resume may change
`resume` SHALL accept `--crawl`, `--detach` and the global flags of `010-add-workspace-and-cli-contract`. Of the crawl flags, it SHALL accept only these:
- `--max-urls`
- `--concurrency` and `--rate`
- `--auth`, `--header` and `--proxy` (`022-add-fetch-policy`). A `--header` replaces a recorded header of the same name.

Any other crawl flag SHALL be rejected with exit code 2 and error code `override_not_allowed`. Accepted values SHALL update the `crawl` table of `crawl.config`, with secrets redacted.

Secrets are never stored in clear:
- A secret first given as a flag SHALL be given again as a flag. Otherwise `resume` SHALL be refused with exit code 2 and error code `secrets_required`, with a hint that names the flag.
- A secret that came from `openlinx.toml` SHALL be read again from `openlinx.toml`. When it is no longer there, `resume` SHALL be refused in the same way.
- The proxy variables (`022-add-fetch-policy`) SHALL be read again from the resuming process's environment, and SHALL never cause `secrets_required`.

`resume` SHALL also be refused with exit code 2 and error code `limit_reached` when the URLs requested so far already reach `--max-urls`, with a hint that gives `--max-urls`.

> **v0.1**, except the credential overrides `--auth`, `--header` and `--proxy`, secrets from flags or `openlinx.toml` and `secrets_required`, with the scenarios "Redacted credentials must be given again", "Credentials given again are used" and "Credentials from openlinx.toml are read again", which are **v0.2** with those flags of `022-add-fetch-policy`. v0.1 has no secret crawl setting. The proxy variables are v0.1, with `022`'s minimum.

#### Scenario: Other settings cannot change on resume
- **WHEN** `linx resume --crawl <id> --include "/x"` runs for a `stopped` Crawl
- **THEN** it exits with code 2, and its only stderr error has `code` = `override_not_allowed`

#### Scenario: A Crawl stopped by the URL limit needs a higher limit
- **WHEN** a Crawl of a site where `/` links to `/p1` to `/p9` was stopped by `--max-urls 3`, and `linx resume --crawl <id>` runs
- **THEN** it exits with code 2, and its only stderr error has `code` = `limit_reached`

#### Scenario: A higher URL limit continues the Crawl
- **WHEN** a Crawl of a site where `/` links to `/p1` to `/p9` was stopped by `--max-urls 3`, and `linx resume --crawl <id> --max-urls 6` runs
- **THEN** it prints `"state": "stopped"`, `"stop_reason": "max_urls"` and `"fetched": 6` in `urls`

#### Scenario: Redacted credentials must be given again
- **WHEN** a Crawl started with `--auth "alice:s3cret"` is `stopped`, and `linx resume --crawl <id>` runs without `--auth`
- **THEN** it exits with code 2, and its only stderr error has `code` = `secrets_required`

#### Scenario: Credentials given again are used
- **WHEN** a Crawl of `http://site.test/` started with `--auth "alice:s3cret"` is `stopped`, and `linx resume --crawl <id> --auth "alice:s3cret"` runs
- **THEN** the requests of the resumed run to `http://site.test/` have `Authorization` = `Basic YWxpY2U6czNjcmV0`

#### Scenario: Credentials from openlinx.toml are read again
- **WHEN** `openlinx.toml` holds `[crawl]` with `auth = "alice:s3cret"`, a Crawl of `http://site.test/` is `stopped`, and `linx resume --crawl <id>` runs without `--auth`
- **THEN** the requests of the resumed run to `http://site.test/` have `Authorization` = `Basic YWxpY2U6czNjcmV0`

#### Scenario: Proxy variables are read again on resume
- **WHEN** a Crawl of `http://site.test/` started with `HTTP_PROXY` = `http://u:pw@127.0.0.1:{proxy_port}` is `stopped`, and `linx resume --crawl <id>` runs with the same variable
- **THEN** it does not fail with `secrets_required`, and the test proxy receives the resumed run's requests

#### Scenario: A politeness override is recorded
- **WHEN** `linx resume --crawl <id> --concurrency 2` runs for a `stopped` Crawl
- **THEN** the `crawl` table of `crawl.config` has `concurrency` = 2

### Requirement: One writer per Crawl
A Crawl's writer claim SHALL be an operating-system lock on the file `<crawl id>.lock` next to its crawl file, taken without waiting. The operating system releases it when its process ends, however it ends.
- Every process that creates, runs or resumes a Crawl SHALL take the claim before it creates or opens the crawl file for writing, and SHALL hold it for as long as it runs.
- A second such process SHALL be refused with exit code 5 and error code `crawl_locked`, whose hint names `linx status`.
- A process that takes the claim for another purpose, such as recording `interrupted` or `crawls rm`, SHALL hold it only for that operation.

> **v0.1.**

#### Scenario: Two resumes at the same time
- **WHEN** two `linx resume --crawl <id>` processes start at the same time for a `stopped` Crawl of the slow fixture site
- **THEN** exactly one of them exits with code 5 and the error code `crawl_locked`

#### Scenario: A killed Crawl can be resumed at once (Windows)
- **WHEN** the process of a running Crawl of the slow fixture site is ended with TerminateProcess on Windows, and `linx resume --crawl <id>` runs right after
- **THEN** it exits with code 0 and prints `"state": "completed"`, and the fixture site receives no second request for a URL that was `fetched` before the process ended

#### Scenario: A killed Crawl can be resumed at once (macOS and Linux)
- **WHEN** the process of a running Crawl of the slow fixture site is killed with SIGKILL, and `linx resume --crawl <id>` runs right after
- **THEN** it exits with code 0 and prints `"state": "completed"`, and the fixture site receives no second request for a URL that was `fetched` before the kill

### Requirement: Dry run
`linx crawl … --dry-run` SHALL validate its arguments exactly like a real Crawl, with the same error codes and exit codes. It SHALL create no file in the Workspace. It SHALL print `{"dry_run": true, "crawl_mode", "config", "command", "estimate", "warnings"}` and exit with code 0. `config` SHALL be the resolved config, as a Crawl would record it in `crawl.config`, with secrets redacted.

To build the estimate, it SHALL request nothing except robots.txt of the Seed's origin and sitemap files. It SHALL request nothing at all with `--no-estimate`. When no request succeeds because the network is unavailable, `estimate.urls` SHALL be null, and `warnings` SHALL hold `estimate_unavailable` with a hint about network access.

> **v0.2.**

#### Scenario: The resolved config is printed
- **WHEN** `linx crawl {site}/ --concurrency 2 --dry-run` runs
- **THEN** it exits with code 0, and its `config` has a `crawl` table with `concurrency` = 2 and `max_urls` = null

#### Scenario: A dry run writes nothing
- **WHEN** `linx crawl {site}/ --dry-run` runs in a Workspace whose crawls folder is empty
- **THEN** the crawls folder is still empty

#### Scenario: Invalid arguments fail as in a real Crawl
- **WHEN** `linx crawl {site}/ --include "(" --dry-run` runs
- **THEN** it exits with code 2, and its only stderr error has `code` = `invalid_pattern`

#### Scenario: Only robots.txt and sitemaps are requested
- **WHEN** `/robots.txt` lists `{site}/sitemap.xml`, and `linx crawl {site}/ --dry-run` runs
- **THEN** the fixture site has received requests only for `/robots.txt` and `/sitemap.xml`

#### Scenario: Nothing is requested without an estimate
- **WHEN** `linx crawl {site}/ --dry-run --no-estimate` runs
- **THEN** the fixture site has received no request, and `estimate.basis` is `none`

#### Scenario: A dry run without network still validates
- **WHEN** `linx crawl http://site.test/ --dry-run` runs while every name lookup fails at the DNS boundary
- **THEN** it exits with code 0, `estimate.urls` is null, and `warnings` hold an entry with code `estimate_unavailable`

### Requirement: URL estimate
`estimate` SHALL be `{"urls", "basis", "confidence", "sitemaps_read", "sitemaps_failed", "urls_listed", "explanation"}`. `urls` is the estimated number of URLs in the Scope that the Crawl will follow, or null when there is no basis. It SHALL be computed per Crawl Mode, with the readers of `024-add-list-and-sitemap-modes`:

**Spider mode.** The sitemaps are the `Sitemap:` lines of the Seed origin's robots.txt, or `{origin}/sitemap.xml` when there are none. They are read like Sitemap mode reads them, with at most 50 sitemap files and 60 seconds.
- `urls` is the number of distinct normalised listed URLs inside the Scope, and `basis` is `sitemaps`.
- `confidence` is `medium` when every sitemap was read, and `low` when a limit cut reading short or a sitemap failed.
- Without any sitemap, `urls` is null, `basis` is `none` and `confidence` is `none`.

**List mode.** `urls` is the number of distinct valid listed URLs, `basis` is `list` and `confidence` is `high`.

**Sitemap mode.** `urls` is the number of distinct URLs listed in the given sitemaps, and `basis` is `sitemaps`. `confidence` is `high` when every sitemap was read, and `low` otherwise.

`urls_listed` SHALL count every listed URL read before filtering. `explanation` SHALL say that a Spider Crawl usually finds more Pages than its sitemaps list, and that it also requests Resources and External URLs. When `urls` is above `--max-urls` (and `--max-urls` is not 0), `warnings` SHALL hold `estimate_exceeds_max_urls`.

> **v0.2.**

#### Scenario: Sitemaps named in robots.txt are counted
- **WHEN** `/robots.txt` lists `{site}/sitemap.xml`, which lists `{site}/a`, `{site}/b`, `{site}/c` and `http://other.test/x`, and `linx crawl {site}/ --dry-run` runs
- **THEN** `estimate` has `"urls": 3`, `"basis": "sitemaps"`, `"confidence": "medium"` and `"urls_listed": 4`

#### Scenario: The Scope filters the count
- **WHEN** `/robots.txt` lists `{site}/sitemap.xml`, which lists `{site}/blog/a`, `{site}/blog/b` and `{site}/shop/c`, and `linx crawl {site}/blog/ --scope subfolder --dry-run` runs
- **THEN** `estimate.urls` is 2

#### Scenario: No sitemap means no estimate
- **WHEN** `/robots.txt` has no `Sitemap:` line, `/sitemap.xml` returns 404, and `linx crawl {site}/ --dry-run` runs
- **THEN** `estimate` has `"urls": null` and `"confidence": "none"`

#### Scenario: A list is counted exactly
- **WHEN** `linx crawl --list urls.txt --dry-run` runs and `urls.txt` holds `{site}/a`, `{site}/a#x` and `{site}/b`
- **THEN** `estimate` has `"urls": 2`, `"basis": "list"` and `"confidence": "high"`

#### Scenario: Too many sitemaps lower the confidence
- **WHEN** `/robots.txt` lists `{site}/index.xml`, a sitemap index listing 60 sitemaps, and `linx crawl {site}/ --dry-run` runs
- **THEN** `estimate` has `"sitemaps_read": 50` and `"confidence": "low"`

#### Scenario: An estimate above the URL limit is flagged
- **WHEN** the sitemap of `{site}` lists 12 URLs in the Scope, and `linx crawl {site}/ --max-urls 10 --dry-run` runs
- **THEN** `warnings` hold an entry with code `estimate_exceeds_max_urls`

### Requirement: Equivalent command
A dry run's `command`, and the `rerun_command` of `crawls show`, SHALL be `{"argv", "sh", "powershell"}`: a `linx crawl` Command that reproduces the Crawl's crawl settings without `openlinx.toml`.
- **`argv`** SHALL be, in order:
  1. `linx` and `crawl`
  2. the Seed (Spider mode), or `--list <absolute path>`, or each `--sitemap <url>`
  3. every crawl setting whose value differs from the built-in default for the Crawl Mode, as flags in this fixed order, with repeated flags in their recorded order: `--scope`, `--include`, `--exclude`, `--strip-params`, `--max-depth`, `--max-urls`, `--ignore-robots`, `--robots-user-agent`, `--follow-nofollow`, `--no-check-external`, `--concurrency`, `--rate`, `--user-agent`, `--header`, `--auth`, `--proxy`, `--timeout`, `--retries`, `--max-redirects`, and then the flags of later changes in the order `linx commands` lists them
  4. `--detach`, when it was given
- **`sh`** SHALL quote each argument for POSIX shells. An argument made only of letters, digits and `@%+=:,./_-` stays bare. Any other argument is wrapped in single quotes, with each `'` written as `'"'"'`.
- **`powershell`** SHALL quote each argument for PowerShell. An argument made only of letters, digits and `+=:./_-` stays bare. Any other argument is wrapped in single quotes, with each `'` doubled.
- **Secrets:** redacted values SHALL appear as `***`, with a `secrets_redacted` warning.
- **Standard input:** a list read from standard input SHALL keep `--list -`, with a `list_from_stdin` warning whose hint shows how to feed the stored Seeds back in.
- **Settings that are not flags:** settings from `openlinx.toml` that are not flags of `linx crawl` and differ from their defaults (for example `[store]`, `[rules]` or `[content_area]`) SHALL be listed by their dotted keys in `details.keys` of a `settings_not_in_command` warning. Its hint SHALL say to copy them into the `openlinx.toml` of the Workspace where the command runs.
- **Proxy variables:** the `environment` table of `crawl.config` SHALL be neither rendered nor listed, because the command reads the proxy variables from the environment where it runs.

> **v0.2**, except the `argv` rule for Spider mode, which v0.1.1 needs for Crawls started through MCP.

#### Scenario: Quoting for POSIX shells
- **WHEN** the command is rendered for a Spider-mode Crawl of `http://site.test/` with `include` = `["/blog/(a|b)"]` and `user_agent` = `Bob's Bot`
- **THEN** `sh` is `linx crawl http://site.test/ --include '/blog/(a|b)' --user-agent 'Bob'"'"'s Bot'`

#### Scenario: Quoting for PowerShell
- **WHEN** the command is rendered for a Spider-mode Crawl of `http://site.test/` with `include` = `["/blog/(a|b)"]` and `user_agent` = `Bob's Bot`
- **THEN** `powershell` is `linx crawl http://site.test/ --include '/blog/(a|b)' --user-agent 'Bob''s Bot'`

#### Scenario: A setting from openlinx.toml becomes a flag
- **WHEN** `openlinx.toml` holds `[crawl]` with `concurrency = 2`, and `linx crawl {site}/ --dry-run` runs
- **THEN** `command.argv` is `["linx", "crawl", "{site}/", "--concurrency", "2"]`

#### Scenario: Settings that are not flags are reported
- **WHEN** `openlinx.toml` holds `[store]` with `journal_mode = "delete"`, and `linx crawl {site}/ --dry-run` runs
- **THEN** `warnings` hold an entry with code `settings_not_in_command` and `"details": {"keys": ["store.journal_mode"]}`

#### Scenario: Proxy variables are left to the environment
- **WHEN** `HTTP_PROXY` is `http://127.0.0.1:{proxy_port}`, and `linx crawl {site}/ --dry-run` runs
- **THEN** `command.argv` contains no `--proxy`, and `warnings` hold no entry with code `settings_not_in_command`

#### Scenario: A Windows list path is quoted for PowerShell (Windows)
- **WHEN** the command is rendered for a List-mode Crawl whose list file is `C:\My Work\urls.txt`
- **THEN** `powershell` is `linx crawl --list 'C:\My Work\urls.txt'`

#### Scenario: A relative list path becomes absolute
- **WHEN** `linx crawl --list urls.txt --dry-run` runs in the folder `W`, which holds `urls.txt`
- **THEN** `command.argv` is `["linx", "crawl", "--list", "<W>/urls.txt"]`, where `<W>/urls.txt` is the absolute path of that file in the OS's own form

#### Scenario: Secrets are placeholders
- **WHEN** `linx crawl {site}/ --auth "alice:s3cret" --dry-run` runs
- **THEN** `command.argv` ends with `"--auth", "***"`, and `warnings` hold an entry with code `secrets_redacted`

#### Scenario: The command reproduces the config
- **WHEN** `linx crawl {site}/blog/ --scope subfolder --exclude "/tag/" --max-depth 3 --dry-run` runs, and its `command.argv` is then run as a Command in the same folder
- **THEN** the `crawl` table of the new Crawl's `crawl.config` equals the `crawl` table of the dry run's `config`

### Requirement: Crawls started without a command line
When the Crawl Service starts or resumes a Crawl for a caller that has no command line, such as the MCP server (`090-add-mcp-server`), the command it records SHALL be synthesised:
- **`crawl.command_argv`:** the equivalent command's `argv`, with `--detach` when the start is detached
- **The run's `command_argv`:** that same argv for a start, and `linx resume --crawl <crawl id>` followed by the overrides for a resume

Secrets SHALL be redacted as in any recorded command.

> **v0.1.1**, for `090-add-mcp-server`, which starts and resumes Crawls through the Crawl Service.

#### Scenario: A Crawl started through the Crawl Service records an equivalent command
- **WHEN** the Crawl Service starts a detached Crawl of `{site}/` with `max_depth` 2 for a caller without a command line
- **THEN** `crawl.command_argv` is `["linx", "crawl", "{site}/", "--max-depth", "2", "--detach"]`

### Requirement: Recorded runs
Every run of a Crawl SHALL add one row to the table `crawl_runs`: the first `linx crawl`, and each `linx resume`, foreground or background. This change adds the table, under the conventions of `018-add-schema-conventions`, with these columns:

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `id` | INTEGER, primary key | no | | The run number: 1 for the first run, then one more for each resume |
| `started_at` | TEXT | no | timestamp | When the run started |
| `ended_at` | TEXT | yes | timestamp | When the run ended; NULL while it runs or when its process died |
| `command_argv` | TEXT | no | json | The run's command line as a JSON array that starts with `"linx"`, secrets redacted |
| `detached` | INTEGER | no | boolean | 1 when the run was started with `--detach` |
| `pid` | INTEGER | no | | Process id of the run |
| `heartbeat_at` | TEXT | yes | timestamp | Last time the run's process reported that it is alive |
| `discovered_count`, `fetched_count`, `error_count`, `skipped_count`, `queued_count` | INTEGER | no | | The Crawl's URLs by `fetch_state`, all runs included, as the run's progress counters held them at the start of the run and then at its last heartbeat |
| `status_2xx_count`, `status_3xx_count`, `status_4xx_count`, `status_5xx_count`, `status_other_count` | INTEGER | no | | The Crawl's responses by status class, counted the same way |
| `urls_per_second` | REAL | yes | | URLs requested per second over the last 60 seconds at the last heartbeat; NULL before the first heartbeat |
| `paused_since` | TEXT | yes | timestamp | When the run's Crawl paused to wait for the network (`020-add-crawl-core`), as the last heartbeat recorded it; NULL when it was not paused |
| `end_state` | TEXT | yes | `completed`, `stopped`, `failed`, `interrupted` | The Crawl State the run ended in; NULL while it runs. An explicit exception to ADR-0005 rule 7: it lists the Crawl States without `running`, because a run never ends as `running` |
| `stop_reason` | TEXT | yes | `max_urls`, `interrupt`, `requested`, `seed_unreachable`, `site_unreachable`, `write_failed` | Why a stopped or failed run ended: the value set of `crawl.stop_reason` (`020-add-crawl-core`) |
| `error` | TEXT | yes | json | The error diagnostic of a failed run, in the full shape of `010-add-workspace-and-cli-contract`. An explicit exception to ADR-0005 rule 10: it is a recorded diagnostic, like `crawl.warnings`, not an error code with a message |

The counters are control data of the run, not counts of the Crawl's data: `status` reads them while the Crawl runs, and every other count comes from the Crawl's tables.

> **v0.1.**

#### Scenario: Each run is recorded
- **WHEN** a Crawl is started with `linx crawl {site}/`, stopped, and resumed with `linx resume --crawl <id>` until it completes
- **THEN** `crawl_runs` holds 2 rows, each with a non-null `ended_at`: run 1 with `command_argv` starting `["linx", "crawl"` and `end_state` = `stopped`, and run 2 with `command_argv` starting `["linx", "resume"` and `end_state` = `completed`

#### Scenario: The heartbeat records the progress counters
- **WHEN** a Crawl on a fake clock has requested 30 URLs, all answering 200, by 15 seconds into its first run, and its heartbeat at 15 seconds is written
- **THEN** its `crawl_runs` row with `id` 1 has `fetched_count` 30, `status_2xx_count` 30, `urls_per_second` 2.0 and `heartbeat_at` at 15 seconds

#### Scenario: Runs share the stop reasons of the Crawl
- **WHEN** `linx schema crawl_runs` and `linx schema crawl` run
- **THEN** the `values` of `crawl_runs.stop_reason` and of `crawl.stop_reason` are both `["max_urls","interrupt","requested","seed_unreachable","site_unreachable","write_failed"]`

### Requirement: Control requests table
The crawl store SHALL hold stop requests in `control_requests`, a control table (see "Control through the crawl store"), declared under the conventions of `018-add-schema-conventions`. This change adds the table with these columns:

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `id` | INTEGER, primary key | no | | Row id |
| `kind` | TEXT | no | `stop` | What is requested |
| `requested_at` | TEXT | no | timestamp | When the request was written |
| `requested_by_pid` | INTEGER | no | | Process id of the Command that wrote it |
| `handled_at` | TEXT | yes | timestamp | When the crawl process acted on it; NULL until then |
| `handled_by_run_id` | INTEGER, references `crawl_runs.id` | yes | | The run that acted on it |

> **v0.1.**

#### Scenario: A stop request names who wrote it and which run handled it
- **WHEN** a running Crawl in its first run has been stopped by a `linx stop --crawl <id>` process
- **THEN** its `control_requests` row has `requested_by_pid` equal to that process's id, and `handled_by_run_id` = 1

#### Scenario: A stop request refers to its run
- **WHEN** `linx schema control_requests` runs
- **THEN** the column `handled_by_run_id` has `references` `crawl_runs.id`

### Requirement: Listing Crawls
`linx crawls list` (also `linx crawls`) SHALL be a list Command of `010-add-workspace-and-cli-contract`, with the envelope `{total, items, next_cursor}` and `--fields`, `--limit` and `--cursor`. Its items SHALL be the Workspace's Crawls, newest first. Each item SHALL hold:
- `crawl_id`, `state`, `crawl_mode`, `seed`, `seed_count`, `section_crawl`
- `started_at`, `completed_at`
- `urls`, with the counts `discovered`, `fetched`, `errors`, `skipped` and `queued`
- `file_size_bytes`

`--state <state>` SHALL keep only Crawls in that Crawl State. A crawl file that cannot be read SHALL be listed with `state` null, and an `error` diagnostic in the full shape `{level, code, message, hint, details}` with the code `crawl_file_invalid`. It SHALL NOT fail the list. A Crawl started by another process in the same Workspace, for example by the user after a Hand-off, SHALL be listed like any other.

> **v0.2.**

#### Scenario: Crawls are listed newest first
- **WHEN** a Workspace holds a Crawl started at 10:00 and one started at 11:00, and `linx crawls list` runs
- **THEN** `total` is 2 and the first item is the Crawl started at 11:00

#### Scenario: A Crawl started by the user is listed
- **WHEN** the user starts `linx crawl {site}/ --detach` from another terminal in the same Workspace, and the agent then runs `linx crawls list`
- **THEN** an item has that Crawl's `crawl_id`

#### Scenario: Crawls are filtered by state
- **WHEN** a Workspace holds one `completed` and one `stopped` Crawl, and `linx crawls list --state stopped` runs
- **THEN** `total` is 1 and the item's `state` is `stopped`

#### Scenario: An unreadable crawl file does not break the list
- **WHEN** the crawls folder holds a valid Crawl and a file `20260927-110000-bbbb.sqlite` that contains 100 zero bytes, and `linx crawls list` runs
- **THEN** it exits with code 0, and the item for `20260927-110000-bbbb` has `state` null and an `error` with `"level": "error"` and `"code": "crawl_file_invalid"`

### Requirement: Showing a Crawl
`linx crawls show <ref>` SHALL accept `latest`, a crawl id or a crawl file path, as `--crawl` does (`015-add-crawl-store`). It SHALL print the list item fields and also:
- `stop_reason`, `command_argv`, `cwd`, `config` and `scope`
- `runs`: the `crawl_runs` rows
- `rerun_command`
- `warnings`, `crawl_file`, `log_file`, `tool_version` and `schema_version`

> **v0.2.**

#### Scenario: The recorded command is shown
- **WHEN** `linx crawl {site}/ --max-depth 2` has completed, and `linx crawls show <id>` runs
- **THEN** `command_argv` is `["linx", "crawl", "{site}/", "--max-depth", "2"]`

#### Scenario: The re-run command is shown
- **WHEN** `linx crawl {site}/ --max-depth 2` has completed, and `linx crawls show <id>` runs
- **THEN** `rerun_command.sh` is `linx crawl {site}/ --max-depth 2`

### Requirement: Removing Crawls
`linx crawls rm <id>…` SHALL delete each given Crawl, including:
- its crawl file, with the `-wal`, `-shm`, writer-claim and log files
- any files left for its background process
- its reports folder `.openlinx/reports/<crawl id>/` (`070-add-html-report`), which also holds the Report Notes saved by `090-add-mcp-server`'s `report` tool (v0.2)

It SHALL print `{"removed": [<crawl ids>], "paths": [<removed paths>], "freed_bytes": <n>}` and exit with code 0. It SHALL refuse, deleting nothing for the Crawl concerned:
- with exit code 2 and error code `explicit_id_required` for `latest`
- with exit code 5 and error code `crawl_locked` for a Crawl whose writer claim another process holds
- with exit code 5 and error code `file_in_use` when, on Windows, another process has the crawl file open

> **v0.2.**

#### Scenario: A completed Crawl is removed
- **WHEN** `linx crawls rm <id>` runs for a `completed` Crawl
- **THEN** it prints `"removed": ["<id>"]`, and neither `<id>.sqlite` nor `<id>.log` exists in the crawls folder

#### Scenario: A Crawl's reports are removed with it
- **WHEN** the Workspace holds `.openlinx/reports/<id>/report.html` and `.openlinx/reports/<id>/notes/summary.md` for a `completed` Crawl, and `linx crawls rm <id>` runs
- **THEN** `.openlinx/reports/<id>` no longer exists, and `paths` contains its absolute path

#### Scenario: A running Crawl is not removed
- **WHEN** `linx crawls rm <id>` runs while a Crawl of the slow fixture site is running in another process
- **THEN** it exits with code 5 with the error code `crawl_locked`, and `<id>.sqlite` still exists

#### Scenario: latest is not accepted
- **WHEN** `linx crawls rm latest` runs
- **THEN** it exits with code 2, and its only stderr error has `code` = `explicit_id_required`

#### Scenario: A crawl file open in another process is not removed (Windows)
- **WHEN** on Windows another process holds an open SQLite connection to the crawl file of a `completed` Crawl, and `linx crawls rm <id>` runs
- **THEN** it exits with code 5 with the error code `file_in_use`, and `<id>.sqlite` still exists

#### Scenario: A crawl file open for reading is removed (macOS and Linux)
- **WHEN** on macOS or Linux another process holds an open read-only SQLite connection to the crawl file of a `completed` Crawl, and `linx crawls rm <id>` runs
- **THEN** it exits with code 0, and `<id>.sqlite` no longer exists
