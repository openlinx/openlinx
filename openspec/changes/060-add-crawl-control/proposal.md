## Why

A Crawl of a real site takes minutes to hours. Agents run Commands inside tool calls that have time limits and sandboxes, and people close their terminals. The approved design has two answers:
- an agent hands a large Crawl to the user (Hand-off) and reads the results later
- an agent runs a smaller one in the background and polls it

Both need five things:
- Crawls that outlive the process that started them
- a way to watch, stop and resume them through the crawl store (no OS signals)
- a dry run that shows what a Crawl will do, and roughly how big it is, before anything runs
- a recorded command that re-runs any Crawl
- a way to list and clean up past Crawls

`020-add-crawl-core` provides the foreground Crawl, its stop flag and its continue operation. This change turns them into Commands.

## What Changes

- **`spider crawl … --detach`**:
  - It validates like a foreground `crawl`, reserves the crawl id, and starts a separate background process that creates the Crawl.
  - Within 10 seconds it prints `{crawl_id, state, run, pid, crawl_file, log_file, warnings, hint}`.
  - The background process survives closing the terminal:
    - Windows: CREATE_NO_WINDOW (approved) in a new process group, so it opens no window (nor do 026's parse workers, if that pool is built), breaking away from the caller's job object when the job allows it.
    - macOS and Linux: a new session.
  - Progress events and diagnostics go to `<crawl-id>.log`. Secrets are passed through the environment, never on the command line.
  - In List mode, the detaching Command reads and checks the list and stores the Seeds before the background process starts, so `--list -` works and list errors come back at once.
- **`spider crawl … --dry-run`** with **`--no-estimate`**:
  - It validates exactly like a real Crawl and writes nothing.
  - It prints the resolved config, the equivalent command (argv, POSIX shell and PowerShell forms) and a URL estimate.
  - The estimate comes from sitemaps, or from the list. It has a stated basis and a confidence, and `urls` may be null.
  - Only robots.txt and sitemap files are requested.
  - Settings that are not `crawl` flags (for example `[store]` or `[rules]`) are listed in a `settings_not_in_command` warning.
- **`spider status [--crawl]`:**
  - It reports:
    - the Crawl State and whether a stop request is pending
    - `urls` counts, `status_classes`, `seed_count`
    - rate, ETA (and whether it is a lower bound), heartbeat age and PID
    - the error of a failed Crawl, the log file, warnings and a next-step hint
  - It detects a dead crawl process and records `interrupted`.
- **`spider stop [--crawl] [--wait <s>]`:** it writes a stop request row, and the Crawl stops gracefully and stays resumable.
- **`spider resume [--crawl] [--detach]`:**
  - It continues a `stopped`, `interrupted` or `failed` Crawl with its recorded config, and refuses a `completed` one.
  - The only overrides are `--max-urls`, `--concurrency`, `--rate`, `--auth`, `--header` and `--proxy`.
  - Secrets given as flags must be given again (`secrets_required`). Secrets from `spider.toml` are read again from it.
- **`spider crawls list [--state]`, `crawls show <id|latest>`, `crawls rm <id>…`:**
  - `show` includes the recorded command, every run and a re-run command.
  - `rm` also deletes the Crawl's reports folder and its Report Notes, and lists the removed paths.
- **Crawls started without a command line,** such as by the MCP server, record a synthesised equivalent argv.
- **New tables:** `crawl_runs` (one row per run) and `control_requests` (a control table).
- **Flags that go beyond the wording of ROADMAP.md.** All are small and plainly needed: `--no-estimate`, `stop --wait`, `crawls list --state`, and `resume --detach` together with the `resume` override flags.
- **MCP tools:** none in this change. `090-add-mcp-server` mirrors these Commands through the same Crawl Service.

## Capabilities

### New Capabilities
- `crawl-control`: covers the following.
  - Crawl State transitions and background Crawls, with detached List mode.
  - Stop requests through the crawl store, `status` with rate and ETA, and dead-process detection.
  - `resume` with its overrides and secrets.
  - The dry run with its URL estimate and equivalent command, synthesised commands and run history.
  - `crawls list|show|rm`, and the `crawl_runs` and `control_requests` tables.

### Modified Capabilities
- None. There are no main specs yet. `crawling`, `fetching` and `crawl-modes` come from `020`, `022` and `024`, which are being drafted in parallel.

## Non-goals

- Scheduled Crawls, distributed Crawls, and controlling Crawls on another machine: **backlog**.
- A REST API or web UI for crawl control: **backlog**.
- MCP progress notifications or Tasks for long Crawls: revisited in **v1.0** (see `090-add-mcp-server`).
- `--progress-interval`: cut from v0.1. Progress is fixed at every 10 seconds.
- These are also out of scope, and are listed in design.md under Open Questions: re-running a Crawl from its id (`crawl --like <id>`), retention and pruning of old Crawls, `status --watch`, and `crawls rm --force`.

## Impact

- **Depends on:**
  - `010-add-workspace-and-cli-contract`:
    - the result on stdout, events and diagnostics on stderr, and partial results
    - the paging envelope, and the exit codes and settings
  - `015-add-crawl-store`:
    - the Crawl States, caller-chosen reserved ids, and the writer claim (`crawl_locked`)
    - its rules for control writes by other processes and for recording a dead Crawl as interrupted
    - redaction and `--crawl`
  - `020-add-crawl-core`:
    - the Crawl Service start and continue operations, the stop flag and the events
    - config resolution and the settings registry, and the post-crawl passes
  - `022-add-fetch-policy`: `--auth`, `--header` and `--proxy`.
  - `024-add-list-and-sitemap-modes`: List mode, and the list and sitemap readers used by the estimate.
- **Edits this change makes to others' areas:**
  - **In `015`'s store:** it adds `crawl_runs` and the control table `control_requests`, following `015`'s conventions.
  - **In `020`'s engine:**
    - it writes a `crawl_runs` row per run, with a heartbeat every 5 seconds
    - it checks `control_requests` every second and sets the stop flag with `stop_reason` = `requested`
    - it records synthesised argv for callers without a command line
- **Used by:**
  - `070-add-html-report`: the end-to-end test `crawl --detach` → `status` → `completed`.
  - `080-add-agent-skill`: Hand-off and polling workflows.
  - `090-add-mcp-server`: the crawl-control tools and detached starts.
- **Code:**
  - `src/spider/services/crawl.py`: detach, status, stop, resume, dry run and crawls.
  - `src/spider/crawl/process.py`: background start per OS.
  - `src/spider/crawl/control.py`: control requests, heartbeat and liveness.
  - `src/spider/crawl/commandline.py`: equivalent-command rendering.
  - `src/spider/crawl/estimate.py`, `src/spider/cli/control.py`, and the store tables.
- **Dependencies:** none new. The Windows job-object check uses `ctypes`.
- **Docs:** `docs/crawl-control.md` (background Crawls, Hand-off, Crawl States, status fields, resume rules and the dry run).
