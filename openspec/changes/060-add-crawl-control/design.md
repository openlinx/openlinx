> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

## Context

See proposal.md (Why) for the motivation. The approach is shaped by these constraints:

- **`015-add-crawl-store`,** as built and archived:
  - one crawl file per Crawl in `.spider/crawls/`
  - the Crawl State values `running`, `stopped`, `completed`, `failed` and `interrupted`
  - crawl ids, taken when `<id>.sqlite` exists, and crawl files created exclusively
  - the `CrawlWriter`, which is the only writer while no Crawl can be resumed or detached
  - redaction of whole and partial secrets, and `--crawl`
  - It does not build the writer claim, `crawl_locked`, control writes by other processes, recording a dead Crawl as `interrupted`, or reserved and chosen ids. They moved to this change on 2026-10-05 (ROADMAP.md), and D12 defines them.
- **`017-speed-up-crawl-writer` and `018-add-schema-conventions`:** units that may run again (`017` D7), and the schema conventions of ADR-0005 with `public_table()`.
- **`010-add-workspace-and-cli-contract`:**
  - the result on stdout, events and diagnostics on stderr, and partial results
  - the paging envelope, and the exit-code table (busy 5, usage 2)
  - no environment variables as settings
- **`020-add-crawl-core`:**
  - the Crawl Service start and continue operations; the continue operation re-queues URLs that got no response
  - the transition table `TRANSITIONS` with `set_state` (D12), and `StopReason`, the six values of `crawl.stop_reason`
  - the stop flag, the events, the progress counters (D10) and the post-crawl passes
  - the `CrawlContext` (D15), config resolution and the settings registry
- **`024-add-list-and-sitemap-modes`:** the list and sitemap readers.
- **Consumers:**
  - `090-add-mcp-server` (v0.1.1) starts long Crawls detached, needs the detach JSON within 10 seconds, and relies on breakaway from Windows job objects.
  - `080-add-agent-skill`'s dry-run guardrail (deferred to v0.2) runs `--dry-run` before every Crawl and treats a null estimate as large.
  - `070-add-html-report`'s end-to-end test polls `status` until the Crawl State is `completed`.

## Goals / Non-Goals

**Goals:**
- A background Crawl that survives the terminal, the agent's tool call and the MCP server, on all three operating systems, with no console windows on Windows.
- A truthful `status`: a dead process is reported as `interrupted` within one call, never shown as `running` forever.
- Stop, resume and the dry run behave the same for Crawls started by an agent, by the MCP server and by the user (Hand-off).

**Non-Goals:**
- Controlling Crawls across machines, scheduling, or notifications.
- New Crawl States. A pending stop is a flag (`stop_requested`), not a state.
- Changing what a Crawl crawls on resume. Only the limit, politeness and credentials can change.

## Decisions

### D1. No extra Crawl States
`015` fixes the stored states. A pending stop is an unhandled row in `control_requests`, which Commands report as `stop_requested: true`. A "starting" state is not needed, because the child creates the Crawl (D3).
- *Alternative:* adding `starting` and `stopping` to `crawl.state`. That changes `015`'s public enumeration, and every consumer would have to handle two more transient values. Rejected.

### D2. Liveness comes from the writer claim; the heartbeat is diagnostic
The OS releases the claim when a process dies, so "`running` and nobody holds the claim" means the process is dead.
- **When a Command finds this:** it calls `check_writer` (D12), which records `interrupted` when no process holds the claim, and in the same transaction sets the run's `end_state`.
- **The heartbeat:** `crawl_runs.heartbeat_at` and the progress counters (D7), written every 5 seconds through the writer. For liveness it only feeds `heartbeat_age_s` and the `heartbeat_stale` warning, for a live process that is suspended, for example a sleeping laptop.
- **Probing races:** a probe holds the claim for milliseconds, so `resume` and `crawls rm` try to acquire it for up to 2 seconds before they report `crawl_locked`.
- *Alternative:* a heartbeat timeout alone. It is slow to notice deaths, and it wrongly declares suspended processes dead. Rejected as the authority.

### D3. Detach: the parent reserves the id, the child creates the Crawl
1. **The parent checks** the arguments with `020`'s `plan_crawl` (validation and config resolution, in `spider.services.crawling`).
2. **The parent reserves an id** by creating `<id>.log` exclusively (D12). If creation finds the id taken, it draws another. If the child's create still meets `crawl_id_taken`, the child exits and the parent reports `detach_failed`.
3. **In List mode, the parent stores the Seeds first.** It also reads the list, from a file or from standard input, with `024`'s reader. It reports list errors such as `empty_list` itself, and stores the Seeds in the hand-over file `<id>.seeds.json` before spawning, because a detached child cannot read the parent's standard input.
4. **The parent spawns the child** with `sys.executable -m spider crawl --_run-detached <id>`. The child's stdout and stderr go to the log file, and stdin comes from the null device.
5. **The parent passes the rest through the environment:** the original argv (for `crawl.command_argv`) and the secret values, in a single JSON variable that the child removes from its own environment after reading it. This is an internal hand-over, not a settings source.
6. **The child creates the Crawl with the reserved id,** holding the writer claim from the first moment. It writes `seeds` from the hand-over file and deletes that file, then writes its `crawl_runs` row.
7. **The parent polls** every 100 ms, for up to 10 seconds, for that row with the child's PID. Then:
   - a row appears: `state: "running"`
   - the child exits first: `detach_failed`
   - 10 seconds pass: `state: null` with `detach_unconfirmed`

No moment exists in which a Crawl exists without a live writer, so a concurrent `status` can never mark a starting Crawl `interrupted`.
- *Alternative:* the parent creates the Crawl and hands the claim over. The claim cannot be passed between processes: Windows releases locks when the locking process exits. Releasing and re-acquiring opens a window in which the Crawl looks dead. Rejected.
- *Alternative:* passing the Seeds through the child's stdin pipe. The parent could block on a large list, and a crash in between leaves nothing to inspect. Rejected.

### D4. Windows process creation (approved)
- **Flags:** `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB`, with `close_fds=True`.
- **Why CREATE_NO_WINDOW rather than DETACHED_PROCESS:** with CREATE_NO_WINDOW the background process owns a hidden console and is still detached from the caller's console. This also matters for `026`'s parse pool, which is unconditional in v0.1: under DETACHED_PROCESS, which has no console, every `spawn` parse worker would get a visible console window, while under CREATE_NO_WINDOW they inherit the hidden one. The maintainer approved this on 2026-09-27.
- **No breakaway allowed:** if `CreateProcess` fails with `ERROR_ACCESS_DENIED` because the job object forbids breakaway, the call is repeated without `CREATE_BREAKAWAY_FROM_JOB`. If the caller's job object has `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, the output gets `job_may_end_crawl`. The job object is queried through `ctypes`.

### D5. POSIX process creation
`start_new_session=True` (setsid), stdin from `/dev/null`, stdout and stderr to the log file, and `close_fds=True`. SIGHUP and signals to the caller's process group do not reach the Crawl. Some agent sandboxes kill every descendant anyway. `status` then shows `interrupted`, `resume` continues the Crawl, and the Skill prefers Hand-off for large Crawls.

### D6. Control rows
- **Marking the table:** `control_requests` is declared through `018`'s `public_table()` with `info={"control": True}`. Control writes (D12) are allowed only on tables marked this way.
- **Writing a request:** `stop` inserts into `control_requests` through `write_control` (D12): a short transaction with a 5-second busy wait.
- **Checking for requests:** the crawl process checks for unhandled rows at least once per second, through a writer unit that only reads (`017` D5). A request sets `020`'s stop flag with `stop_reason = requested`, the same path as Ctrl+C.
- **Marking it handled:** the unit that handles it sets `handled_at` and `handled_by_run_id`.

### D7. Status computation
- **Counts of a running Crawl** come from the heartbeat (ruling Q1 of the schema blueprint). `urls` has no index for counts by `fetch_state` (`020` D18), so a `GROUP BY` over it scans the whole table, and an agent may poll `status` every few seconds during a Crawl of about 500k URLs. The crawl process already keeps `020`'s progress counters (D10), seeded once per run by a counting query and updated as units commit. This change adds the status classes to them, and the heartbeat writes them to the run's row every 5 seconds. They are control data of the run, like `heartbeat_at`, not counts of the Crawl's data (ADR-0005).
- **Counts of a Crawl that is not running** are counted over `urls` once: no process is writing, and the result is exact.
- **Rate** (ruling Q2): the run's `urls_per_second`, which the crawl process computes from its 60-second window, the `rate` of its progress events, and writes with the heartbeat. `fetched_at` gets no index.
- **Average rate:** the URLs requested in all runs (`fetched` plus `error`) divided by `elapsed_s`, the time spent in all runs. It shows whether the current `rate` is typical, and it is what a user compares with another crawler's average.
- **ETA:** a pure function of rate, queued, `max_urls` and requested.
- **A network pause** (`020`, decided 2026-10-14): while the Crawl waits for the network, it requests nothing but its probes of the Seed. The heartbeat keeps running and writes `paused_since`, and `status` prints it, so an agent tells a waiting Crawl from a slow one. A stop request ends the pause at once, because no request is in flight to wait for.
- **`error`:** the `error` of the last run of a `failed` Crawl.
- **Time source:** "now" comes from the injectable clock, so the rules about rate, ETA, heartbeat and elapsed time are tested with a fake clock.
- *Alternative:* a `(fetch_state)` index or a `fetched_at` index, as the draft assumed. Each costs an index entry for every URL during the Crawl, for a query the counters answer. Rejected by the blueprint's rulings.

### D8. What resume may change, and secrets
Everything that decides which URLs belong to the Crawl stays fixed: the Crawl Mode, the Seeds, the Scope, include/exclude, the depth limit, stripped parameters, robots.txt handling and Link following.
- **What may change:** the URL limit, which can only be raised; politeness (`--concurrency`, `--rate`); and credentials (`--auth`, `--header`, `--proxy`).
- **Where secrets came from** is read from the recorded command:
  - A secret in `crawl.command_argv` came from a flag and must be given again.
  - A redacted value in `crawl.config` with no flag in the argv came from `spider.toml` and is read again from it.
  - The proxy variables (the `environment` table) are simply read again from the resuming process's environment.
- **Recording:** accepted overrides update the `crawl` table of `crawl.config`, and the run's `command_argv` records them.

### D9. The dry run and its estimate
- **Validation:** it reuses `020`'s `plan_crawl` (validation and config resolution, in `spider.services.crawling`), so dry runs and real runs cannot disagree.
- **Network use:** only robots.txt and sitemaps are requested (with `024`'s sitemap reader), one at a time and obeying robots.txt, within a budget of 50 files and 60 seconds.
- **Degrading:** failures lower the confidence and never fail the Command. With the network blocked, `urls` is null and the Skill (`080`) treats the Crawl as large.
- **Confidence:** Spider-mode estimates are never `high`, because sitemaps undercount Pages and a Crawl also requests Resources and External URLs.

### D10. The equivalent command and synthesised commands
- **The renderer** is a pure function over (Crawl Mode, Seeds or list path or sitemap URLs, the `crawl` config table, detach):
  - The flag order follows the change that added each flag. `spider commands` gives the order for later changes.
  - Only non-default values are rendered, and list paths are made absolute with `crawl.cwd`.
  - POSIX quoting follows `shlex.quote`'s safe set. PowerShell uses single quotes and a smaller safe set, because `,` builds arrays and `@` splats.
- **Settings that are not flags:** keys of `crawl.config` outside the `crawl` and `environment` tables that differ from their defaults are listed in `settings_not_in_command`, because the command alone cannot carry them. The `environment` table is left out: the command reads the proxy variables wherever it runs.
- **Synthesised commands:** the Crawl Service uses the same renderer to synthesise `crawl.command_argv` for callers without a command line, which is the MCP server's case.

### D11. Listing and removing
- **Listing:** `crawls list` goes through `.spider/crawls/*.sqlite`, opens each file read-only through `015`, and probes the claim only for Crawls stored as `running`. An unreadable file becomes an item with a full `crawl_file_invalid` diagnostic.
- **Removing:** `crawls rm` acquires the claim, which rules out a writer, and then renames the crawl file to a temporary name.
  - On Windows the rename fails when another process has the file open, and the Command reports `file_in_use` before anything is deleted.
  - Otherwise it deletes, and lists in `paths`:
    - the `-wal`, `-shm`, log and hand-over files
    - `.spider/reports/<id>/`, which holds `070`'s Reports and `090`'s saved notes
  - It then releases the claim and deletes the claim's lock file.

### D12. The writer claim, control writes, `interrupted` and reserved ids
`015` was planned to build these, and they moved here on 2026-10-05, because only background Crawls and `resume` need them. They live in `spider.store` (`020` D14).
- **The writer claim** (`spider.store.claim`): an operating-system lock on `<id>.lock`, taken without waiting: `msvcrt.locking` on Windows and `fcntl.flock` on POSIX, on the lock file, never on the crawl file.
  - The operating system releases it when the process ends, SIGKILL and TerminateProcess included, so "`running` and the claim is free" means the process is dead (D2).
  - The Crawl Service takes it before `create_crawl` creates `<id>.sqlite`, and before a resume opens the writer, and holds it until the writer is closed. A Crawl therefore never exists without a live claim (D3).
  - Failing to take it is `crawl_locked` (exit code 5), declared by this change.
  - The lock file stays behind. It is harmless, it marks the id as taken, and `crawls rm` deletes it.
- **Control writes** (`write_control`, in `spider.store.control`): a read-write connection without the claim, with a 5-second busy timeout, whose SQLite authorizer refuses every write to a table not marked `info={"control": True}`.
- **Recording `interrupted`** (`check_writer`, in the same module): it tries the claim without waiting. When it gets it and the state is `running`, one transaction records `interrupted` through `020`'s `set_state`, whose transition check this change extends with `running` → `interrupted`, and sets the last run's `end_state`. Then it releases the claim.
- **Reserved and chosen ids** (`crawl-store`'s "Crawl ids", modified): the id draw also counts `<id>.lock` and `<id>.log` as taken. The detaching parent reserves an id by creating `<id>.log` exclusively, and `create_crawl` accepts a chosen id, failing with `crawl_id_taken` when `<id>.sqlite` exists.
- *Alternative:* `filelock`, as `015`'s first draft planned. It is a new dependency for about 30 lines of standard-library code. Rejected, unless the two platform locks prove awkward when they are built.
- *Alternative:* a lock inside SQLite. SQLite locks last one transaction, not a process lifetime. Rejected.
- *Alternative:* a PID file. PIDs are reused, and nothing releases the file automatically. Rejected.
- *Alternative:* byte-range locks on the crawl file. POSIX `fcntl` locks are per process, so they would clash with SQLite's own locks on the same file. Rejected.

### D13. The tables under ADR-0005
Both tables go through `018`'s `public_table()`, so they are `STRICT`, with CHECKs on their enumerations and flags.
- **`crawl_runs.id`** (was `run`): the run number is the entity's own key (ADR-0005 rule 2). The Commands' output keeps the field name `run`.
- **`control_requests.handled_by_run_id`** (was `handled_by_run`): a declared reference to `crawl_runs.id` (rule 3).
- **`crawl_runs.stop_reason`** takes its values from `020`'s `StopReason`, the one value set it shares with `crawl.stop_reason` (rule 7), including the `failed` reasons.
- **Two explicit exceptions,** named in their column descriptions:
  - `crawl_runs.end_state` lists the Crawl States without `running` (rule 7: one value set per enumeration), because a run never ends as `running`.
  - `crawl_runs.error` is a JSON diagnostic in `010`'s full shape (rule 10: a code column plus `_message`), because it records the diagnostic the run ended with, as `crawl.warnings` records warnings, and `status` prints it whole.
- **The counters** end in `_count` (rule 5) and are NOT NULL: the run's row is inserted with the counters seeded at the start of the run. `urls_per_second` is NULL until the first heartbeat. `paused_since` is NULL whenever the Crawl is not paused, like `ended_at` while a run runs.

### D14. Codes
Declared as `DiagnosticCode` constants in `spider.output.codes`, as `020` D17 does, each by the slice that first raises it. Exit codes follow `010`'s classes and naming rule; every warning has the level `warning` and no exit code.
- **v0.1:**
  - errors, exit 1: `crawl_completed` (`resume` of a `completed` Crawl), `detach_failed` (the background process ended before it created the Crawl)
  - errors, exit 2: `override_not_allowed`, `limit_reached` (`resume` arguments)
  - errors, exit 5: `crawl_locked` (another process holds the writer claim), `crawl_id_taken` (a chosen id whose `<id>.sqlite` another process already made; the detaching parent reports it as `detach_failed`)
  - warnings: `detach_unconfirmed`, `heartbeat_stale`, `job_may_end_crawl`
- **v0.2:**
  - errors, exit 2: `secrets_required` (`resume` credentials), `explicit_id_required` (`crawls rm latest`)
  - error, exit 5: `file_in_use` (`crawls rm` on Windows)
  - warnings: `estimate_unavailable`, `estimate_exceeds_max_urls`, `secrets_redacted`, `list_from_stdin`, `settings_not_in_command`

From other changes: `empty_list` (`024`, reported by the detaching parent), `crawl_file_invalid`, `crawl_busy` and `crawl_not_found` (`015`), `seed_unreachable` and the other Crawl codes (`020` D17), and `invalid_value` and `settings_invalid` (`010`).
- *Why `crawl_id_taken` is 5:* `010`'s naming rule covers only `invalid_`, `unknown_` and `_not_found`. In v0.1 the chosen id is always the tool's own, reserved by the detaching parent, so it is taken only when another process created that Crawl between the reservation and the create. Running the same command again draws a new id and succeeds, so retrying is the right advice, which is what the `busy` class (5) tells an agent.
- *If a later release lets the user choose an id:* a user-chosen id that is taken is not transient, because running the same command again fails again. It then needs a code of its own with exit 2 (fix the argument), decided in that release.

## Test seams

Seams from docs/testing.md:
- **CLI (1):**
  - `CliRunner` for argument errors and output shapes.
  - **Real subprocess runs on Windows, macOS and Linux** for everything with processes:
    - `--detach`, `status`, `stop` and `resume`
    - killing processes (SIGKILL and TerminateProcess)
    - terminating a CREATE_NEW_CONSOLE launcher on Windows
    - SIGHUP to a pseudo-terminal's process group on POSIX
    - job objects with and without breakaway
    - listing visible windows on Windows
    - `crawls rm` with a file held open
- **Services and store API (2):** status fields, state transitions, the heartbeat's counters, control writes, the synthesised argv, and holding the writer claim from the test process through `spider.store.claim` (for the stale heartbeat).
- **HTTP (local fixture site) (3):**
  - The slow fixture site keeps Crawls running.
  - Request logs prove what resume and the dry run requested.
  - `022`'s virtual hosts and `020`'s DNS resolver hook cover the offline dry run and the credentials scenarios.
- **Pure-logic modules (4):** the command renderer (quoting tables), ETA and rate, and the estimate counter.
- **Seam 3+6:** `crawl_runs`, `control_requests`, `seeds` and `crawl.config` read after the Commands ran. Each column is added, and documented in `docs/schema.md`, by the slice that needs it.

Boundary doubles, all from the approved list:
- **The OS process-spawn call** (`subprocess.Popen` / `CreateProcess`), replaced by a double whose process exits at once or stays alive. It is used only for `detach_failed` and `detach_unconfirmed`. Our own launcher code runs unchanged.
- **The injectable clock:** for rate, ETA, heartbeat staleness and the 10-second confirmation budget.
- **The injectable random source:** only where a test must predict a reserved crawl id.

## Risks / Trade-offs

- [Agent sandboxes kill detached descendants at the end of a tool call] → Detection is immediate (`interrupted`) and `resume` continues the Crawl. The Skill hands large Crawls to the user, and `job_may_end_crawl` warns on Windows.
- [OS file locks on network drives] → `015` warns about network locations. Sharing one Workspace between two machines is unsupported and documented.
- [A suspended but alive process looks stale] → Its claim is still held, so it stays `running` with `heartbeat_stale`.
- [Post-crawl passes make `stop` wait longer than `--wait` on huge Crawls] → `stop` returns `state: running, stop_requested: true`. The request stays pending and is honoured.
- [Antivirus or indexers hold files open on Windows] → `crawls rm` reports `file_in_use` and deletes nothing, so no Crawl is half deleted.
- [Secrets in the child's environment are readable by the same user] → This is the same trust boundary as the user's shell. The variable is removed after it is read, so any parse workers do not inherit it.
- [A hand-over file is left behind when the child dies at start] → `detach_failed` names the log file, and `crawls rm <id>` deletes the files of a reserved id.

## Migration Plan

None. Before v0.1 the schema is not yet public: this change adds `crawl_runs` and `control_requests` to the declared schema and `docs/schema.md`, each in the slice that needs it, and `schema_version` stays `1` (`015` D5). `control_requests` carries `info={"control": True}`.

## Open Questions

These are deferrable, and each adds a Command or flag later without changing these specs:
- `spider crawl --like <id>` (or `crawls rerun <id>`), to re-run a Crawl directly from its recorded config.
- Retention: `crawls prune --older-than`, or a Workspace setting that caps the number of kept Crawls.
- `status --watch` for people.
- `crawls rm --force`, which stops a running Crawl and then removes it.
- Whether `resume` should also accept `--timeout` and `--retries` overrides.
