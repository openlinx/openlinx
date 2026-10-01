## Why

Every later change finds its Workspace, reads settings and prints results for agents. These foundations must be fixed once, before the other changes start:
- **The Workspace:** where Crawls and settings live, and how a Command finds them.
- **The CLI contract:** what goes to stdout and stderr, the output formats, paging, partial results, errors and exit codes.

With these settled and tested, `015-add-crawl-store` and every later change build on stable conventions instead of each inventing its own.

## What Changes

- **Workspace**
  - **Finding the Workspace:** `--workspace <dir>` wins. Otherwise the tool uses the nearest folder, from the current folder upwards, that holds `.spider/` or `spider.toml`. The search stops at the home folder. Otherwise it uses the global Workspace `~/.spider/`, whose settings file is `~/.spider/spider.toml`.
  - **`spider init [--workspace <dir>]`** is idempotent:
    - It creates `.spider/`, `.spider/.gitignore` (which ignores the folder's contents), `.spider/crawls/` and a fully commented `spider.toml`.
    - It never modifies an existing file, and it validates an existing `spider.toml`.
    - It warns `workspace_nested` when a parent folder is already a Workspace.
  - **`spider.toml` settings:**
    - Each change registers its own table.
    - Precedence is flag > `spider.toml` > default.
    - The whole file is checked when settings load. Unknown keys and invalid values fail with `settings_invalid` (exit 3), and the error names the dotted key.
  - **No environment variables:** no variable selects the Workspace, sets a setting or changes the output. There are two exceptions:
    - the standard proxy variables `HTTP_PROXY`, `HTTPS_PROXY` and `NO_PROXY`, honoured for fetching (owned by `022`, and listed under `environment` in `spider commands`)
    - read-only detection signals such as `CODEX_SANDBOX_NETWORK_DISABLED`, which may only shape hints
- **CLI contract**
  - **stdout** carries the Command's single JSON result, or JSON Lines for lists and rows (`--format jsonl`).
  - **stderr** carries JSON lines of two kinds:
    - diagnostics `{level, code, message, hint, details}`
    - progress events `{event, ts, data}`

    There is no result event.
  - **Partial results:** a Command whose result describes a failed outcome prints it, and exits non-zero with exactly one error diagnostic. Every other failing Command writes nothing to stdout.
  - **Formats:** `--format json|jsonl|table`, as each Command supports them.
  - **UTF-8 bytes** and `\n` line endings on every OS, whatever the console code page.
  - **Lists:** the envelope `{total, items, next_cursor}`, with `--fields` (including `all`), `--limit` (default 50, from 0 to 1000) and `--cursor` (opaque).
  - **Diagnostics:** lowercase codes. Errors and warnings inside results use the same shape.
  - **Exit codes:** success 0, failed 1, usage 2, config 3, not found 4, busy 5, incompatible 6, I/O 7, network 8, internal 70, interrupted 130.
  - **`spider commands`** describes every Command:
    - its output kind (`document`, `list` or `rows`) and whether it reports progress events
    - its formats, arguments and options
    - the exit codes and every diagnostic code

**Commands added:** `spider init`, `spider commands`.

**Flags added:**
- the global flags `--workspace <dir>` and `--format json|jsonl|table`, accepted after the Command name
- the list flags `--fields`, `--limit` and `--cursor`, used by every list Command from `015` on

**Settings added:** none of this change's own. It provides the settings system that later changes register their tables in. No MCP tools are added.

**Small additions beyond ROADMAP.md, all needed by the scenarios:**
- `spider.toml` alone also marks a Workspace. Otherwise a fresh clone of a repository with a committed `spider.toml` would silently fall back to the global Workspace.
- `.spider/.gitignore`.
- The `workspace_nested` warning.
- `--fields all`, and `--limit 0` for counting without items.

## Capabilities

### New Capabilities

- `workspace`: where a Workspace's Crawls and settings live, how Commands find it, `spider init`, the settings system with its precedence and validation, and the no-environment-variables rule.
- `cli-contract`: the stdout and stderr streams, the formats, the paging envelope, progress events, partial results, diagnostics, exit codes, the global flags and `spider commands`.

### Modified Capabilities

None. No specs exist yet.

## Non-goals

- **`015-add-crawl-store` (v0.1):**
  - crawl files and the store
  - `spider schema`, and the `--crawl` flag
  - the `[store]` settings table
- **`020-add-crawl-core` (v0.1):**
  - the first Command that reports progress events and partial results, `crawl`, with its exit codes 8 (`seed_unreachable`) and 130 (Ctrl+C)
- **`022-add-fetch-policy` (v0.1):** the fetch flags and which of them are secret. `015` does the redaction.
- **`050-add-query-and-segments` (v0.1):**
  - the query Commands
  - `unknown_column` for `--where` and `--sort`
  - `[segments]`, which is checked when settings load and fails as `settings_invalid`
  - the rows Command `export`
  - the `csv` format, the CSV policy, `--no-bom` and `-o/--output`, moved out of this change by the maintainer on 2026-10-01
- **`060-add-crawl-control` (v0.1):** crawl control.
- **`070-add-html-report` (v0.1):** the report receipt and `--dest`.
- **`080-add-agent-skill` (v0.1):** the Skill, generated from `spider commands`, and `spider doctor`.
- **`090-add-mcp-server` (v0.1):** MCP tools, which reuse the diagnostic shape.

## Impact

- **New runtime dependencies:** `pydantic-settings`, `orjson`, and `rich`, which is made explicit for table output.
- **Code:**
  - `src/spider/workspace/`: discovery, the settings registry and the template
  - `src/spider/output/`: formats, paging, cursors, events, diagnostics and exit codes
  - `src/spider/cli/`: the app factory, `init`, `commands`, and the global flag definitions
- **Docs:** new `docs/cli.md` and `docs/workspace.md`. Also updates to `docs/architecture.md` and `README.md`.
- **Test support:**
  - the CliRunner helper gains JSON and stderr-line helpers
  - **contract fixture Commands** and an example settings table, registered on a fresh app in tests (design D8)
- **Every later change depends on this one.** It must follow these conventions for its output, errors, exit codes and settings.
