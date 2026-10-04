> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

## Context

See proposal.md (Why) for the motivation. The approach is shaped by these constraints:

- **`015-add-crawl-store`:**
  - one crawl file per Crawl in `.spider/crawls/`
  - the Crawl States `running`, `stopped`, `completed`, `failed` and `interrupted`
  - crawl ids that a caller may reserve and then choose; an id is taken when `<id>.sqlite`, `<id>.lock` or `<id>.log` exists
  - a writer claim that the OS releases when the process ends, refusing a second writer with `crawl_locked`
  - two stated exceptions: control writes by other processes into control tables, and recording a dead Crawl as `interrupted`
  - redaction of whole and partial secrets
- **`010-add-workspace-and-cli-contract`:**
  - the result on stdout, events and diagnostics on stderr, and partial results
  - the paging envelope, and the exit-code table (busy 5, usage 2)
  - no environment variables as settings
- **`020-add-crawl-core`:**
  - the Crawl Service start and continue operations; the continue operation re-queues URLs that got no response
  - the stop flag, the events and the post-crawl passes
  - config resolution and the settings registry
- **`024-add-list-and-sitemap-modes`:** the list and sitemap readers.
- **Consumers:**
  - `090-add-mcp-server` (v0.1.1) always starts Crawls detached, needs the detach JSON within 10 seconds, and relies on breakaway from Windows job objects.
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
- **When a Command finds this:** it calls `015`'s `check_writer`, which records `interrupted` when no process holds the claim, and in the same step sets the run's `end_state`. This change does not redefine the check.
- **The heartbeat:** `crawl_runs.heartbeat_at`, written every 5 seconds through the batched writer. It only feeds `heartbeat_age_s` and the `heartbeat_stale` warning, for a live process that is suspended, for example a sleeping laptop.
- **Probing races:** a probe holds the claim for milliseconds, so `resume` and `crawls rm` try to acquire it for up to 2 seconds before they report `crawl_locked`.
- *Alternative:* a heartbeat timeout alone. It is slow to notice deaths, and it wrongly declares suspended processes dead. Rejected as the authority.

### D3. Detach: the parent reserves the id, the child creates the Crawl
1. **The parent checks** the arguments with `020`'s validation and config resolution.
2. **The parent reserves an id** by creating `<id>.log` exclusively (`015`'s reservation). If creation finds the id taken, it draws another. If the child's create still meets `015`'s `crawl_id_taken`, the child exits and the parent reports `detach_failed`.
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
- **Why CREATE_NO_WINDOW rather than DETACHED_PROCESS:** with CREATE_NO_WINDOW the background process owns a hidden console and is still detached from the caller's console. If `026` builds its parse pool (the gate of 026's task 1.5), this also matters for the workers: under DETACHED_PROCESS, which has no console, every `spawn` parse worker would get a visible console window, while under CREATE_NO_WINDOW they inherit the hidden one. The maintainer approved this on 2026-09-27.
- **No breakaway allowed:** if `CreateProcess` fails with `ERROR_ACCESS_DENIED` because the job object forbids breakaway, the call is repeated without `CREATE_BREAKAWAY_FROM_JOB`. If the caller's job object has `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, the output gets `job_may_end_crawl`. The job object is queried through `ctypes`.

### D5. POSIX process creation
`start_new_session=True` (setsid), stdin from `/dev/null`, stdout and stderr to the log file, and `close_fds=True`. SIGHUP and signals to the caller's process group do not reach the Crawl. Some agent sandboxes kill every descendant anyway. `status` then shows `interrupted`, `resume` continues the Crawl, and the Skill prefers Hand-off for large Crawls.

### D6. Control rows
- **Marking the table:** the Core table `control_requests` is declared with `info={"control": True}`. `015`'s `write_control` exception relies on that marker, and allows writes by processes without the writer claim only on tables marked this way.
- **Writing a request:** `stop` inserts into `control_requests` through `015`'s `write_control`: a short transaction with a 5-second busy wait.
- **Checking for requests:** the crawl process checks for unhandled rows at least once per second on its read connection. A request sets `020`'s stop flag with `stop_reason = requested`, the same path as Ctrl+C.
- **Marking it handled:** the unit that handles it sets `handled_at` and `handled_by_run`.

### D7. Status computation
- **Counts:** one indexed `GROUP BY fetch_state` over `urls`, and one over the classes of `status_code`.
- **Rate:** the number of `urls` with `fetched_at` inside the last 60 seconds, divided by the window.
- **ETA:** a pure function of rate, queued, `max_urls` and requested.
- **`error`:** the `error` of the last run of a `failed` Crawl.
- **Time source:** "now" comes from the injectable clock, so the rules about rate, ETA, heartbeat and elapsed time are tested with a fake clock.

### D8. What resume may change, and secrets
Everything that decides which URLs belong to the Crawl stays fixed: the Crawl Mode, the Seeds, the Scope, include/exclude, the depth limit, stripped parameters, robots.txt handling and Link following.
- **What may change:** the URL limit, which can only be raised; politeness (`--concurrency`, `--rate`); and credentials (`--auth`, `--header`, `--proxy`).
- **Where secrets came from** is read from the recorded command:
  - A secret in `crawl.command_argv` came from a flag and must be given again.
  - A redacted value in `crawl.config` with no flag in the argv came from `spider.toml` and is read again from it.
  - The proxy variables (the `environment` table) are simply read again from the resuming process's environment.
- **Recording:** accepted overrides update the `crawl` table of `crawl.config`, and the run's `command_argv` records them.

### D9. The dry run and its estimate
- **Validation:** it reuses `020`'s validation and config resolution, so dry runs and real runs cannot disagree.
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
- **Services and store API (2):** status fields, state transitions, the synthesised argv, and holding the writer claim from the test process through `015`'s API (for the stale heartbeat).
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

`crawl_runs` and `control_requests` go into the squashed v0.1 migration under `015`'s conventions. `control_requests` carries `info={"control": True}`.

## Open Questions

These are deferrable, and each adds a Command or flag later without changing these specs:
- `spider crawl --like <id>` (or `crawls rerun <id>`), to re-run a Crawl directly from its recorded config.
- Retention: `crawls prune --older-than`, or a Workspace setting that caps the number of kept Crawls.
- `status --watch` for people.
- `crawls rm --force`, which stops a running Crawl and then removes it.
- Whether `resume` should also accept `--timeout` and `--retries` overrides.
