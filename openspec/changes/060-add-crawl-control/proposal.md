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

> **Scope (2026-10-05, see ROADMAP.md):** **v0.1** ships 060-min and `resume`: `crawl --detach`, `status` (with dead-process detection) and `stop` (`--wait`), for Spider mode only, with the recorded runs and the control requests. **v0.1.1:** the command recorded for Crawls started through MCP. **Deferred to v0.2:** `resume`'s credential overrides (`022`'s flags), `crawl --dry-run` with its URL estimate and equivalent command, `crawls list|show|rm`, and detached List mode (`024` is v0.2). Each requirement in the spec is marked with its release.
>
> **Moved from 015 (2026-10-05):** the writer claim (`crawl_locked`), control writes by processes without the claim, recording a dead Crawl as `interrupted`, and reserved and chosen crawl ids (`crawl_id_taken`). `015` did not build them, so this change does (design D12).
>
> **Schema blueprint (2026-10-11):** `crawl_runs.id` and `control_requests.handled_by_run_id` follow ADR-0005, `crawl_runs.stop_reason` shares `crawl.stop_reason`'s six values, and the heartbeat records the progress counters, so `status` never counts over `urls` while a Crawl runs.

- **`spider crawl … --detach`**:
  - It validates like a foreground `crawl`, reserves the crawl id, and starts a separate background process that creates the Crawl.
  - Within 10 seconds it prints `{crawl_id, state, run, pid, crawl_file, log_file, warnings, hint}`.
  - The background process survives closing the terminal:
    - Windows: CREATE_NO_WINDOW (approved) in a new process group, so it opens no window (nor do 026's parse workers), breaking away from the caller's job object when the job allows it.
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
    - the Crawl State and whether a stop request is pending, and since when a Crawl waits for the network (`020`'s network pause)
    - `urls` counts, `status_classes`, `seed_count`
    - rate (from the heartbeat), average rate over all runs, ETA (and whether it is a lower bound), heartbeat age and PID
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
- **New tables:** `crawl_runs` (one row per run, with its heartbeat and progress counters) and `control_requests` (a control table).
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
- `crawl-store`: "Crawl ids" counts the writer claim's file and the log file as taking an id, and adds reserved and chosen ids with `crawl_id_taken`.

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
  - `015-add-crawl-store`: the crawl file, crawl ids, the Crawl State values, the writer, redaction and `--crawl`
  - `017-speed-up-crawl-writer` and `018-add-schema-conventions`: the contract of a unit, and the schema conventions with the declaration helper
  - `020-add-crawl-core`:
    - the Crawl Service start and continue operations, the transition table, the stop flag, the events and the progress counters
    - config resolution and the settings registry, and the post-crawl passes
  - `022-add-fetch-policy`: the proxy variables in v0.1, and `--auth`, `--header` and `--proxy` in v0.2.
  - `024-add-list-and-sitemap-modes`: List mode, and the list and sitemap readers used by the estimate.
- **Edits this change makes to others' areas:**
  - **In `015`'s store:** it adds the writer claim, control writes, recording `interrupted` and reserved ids, which moved from `015`, and the tables `crawl_runs` and `control_requests`, following ADR-0005.
  - **In `020`'s engine:**
    - it adds `running` → `interrupted` and `interrupted` → `running` to `020`'s transition table
    - it writes a `crawl_runs` row per run, with a heartbeat every 5 seconds that records the progress counters
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
