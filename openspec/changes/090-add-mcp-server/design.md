## Context

See proposal.md for the motivation. The facts that shape this design:
- **SDK:** the MCP Python SDK is `mcp` 2.2.0. It implements the stateless 2026-07-28 revision and renames FastMCP to `MCPServer`.
- **Claude Desktop** installs local servers as `.mcpb` Desktop Extensions. Manifest version 0.4 adds `"server": {"type": "uv"}`: Claude Desktop manages Python and the dependencies itself from the bundle's `pyproject.toml`.
- **ChatGPT developer mode** needs a remote server, so it is out of scope. The ChatGPT desktop app (Codex) runs local stdio servers.
- **Configuration files:**
  - Codex: `~/.codex/config.toml` `[mcp_servers.<name>]`
  - Cursor: `.cursor/mcp.json` `mcpServers`
  - VS Code: `.vscode/mcp.json` `servers`
  - Gemini CLI: `~/.gemini/settings.json` `mcpServers`
- **Services already exist:** the CLI and the Query, Crawl and Report services exist from the changes before this one in the build order. The MCP server must stay as thin as the CLI (docs/architecture.md).
- **No environment variables are settings** (`010-add-workspace-and-cli-contract`). The server's only way to choose a Workspace is its `--workspace` argument.

## Goals / Non-Goals

**Goals:**
- Parity by construction. A tool and its Command share the input definition, the service call and the serialiser, so their JSON cannot drift.
- A server that never blocks on a Crawl and never loses one when a client quits.

**Non-Goals:**
- A second, MCP-specific data model or output format.
- Multi-Workspace servers.

## Decisions

### D1. One registry maps tools to Commands
A registry entry holds:
- the tool name
- the Command whose option metadata supplies the input schema: flags in snake_case, JSON types from the option types, and arrays for repeatable flags such as `--sitemap`
- the service call
- the annotations

The same serialiser that the CLI uses with `--format json` produces the structured content.
- *Alternative:* hand-written tool functions with typed signatures. They are more idiomatic for the SDK, but every new CLI flag would need a second edit, and parity tests would only catch the drift afterwards.

### D2. The result is the CLI JSON as `structuredContent` plus serialised text
Clients that ignore structured content still get the JSON as text. The paging envelope and every other result are already objects, as `structuredContent` requires.
- *Alternative:* return large results as MCP resources. Client support is uneven, and the paging envelope already bounds the size.

### D3. Errors are tool results that carry the full diagnostic
- CLI errors are returned as `isError: true` results whose structured content is the full diagnostic of `010-add-workspace-and-cli-contract`, `{level, code, message, hint, details}`. `details` is kept whole, including `suggestions` and `accepted`, so the model can read the hint and correct itself.
- Input-schema violations are returned the same way.
- JSON-RPC protocol errors remain only for unknown tools and malformed messages, which the SDK handles.
- `mode_conflict` (`024-add-list-and-sitemap-modes`) is raised by the same validation that `spider crawl` uses, so its details match.
- `doctor` is the one deliberate exception: a failing check is its normal output.

### D4. Crawls are always detached, and progress comes from polling
- `crawl_start` and `crawl_resume` call the Crawl Service's detached start from `060-add-crawl-control`, so the Crawl is a separate OS process that owns its own store writer.
  - 060 records a synthesised equivalent `spider crawl` argv as the Crawl's command, so `crawls show` works for Crawls started through MCP too.
- Progress comes from `crawl_status` over the control rows in the store.
- *Alternative:* MCP progress notifications or the experimental Tasks. Client support is spotty, the tool call would have to stay open for minutes or hours, and a client restart would lose the link to the Crawl. Polling works in every client and survives restarts.

### D5. The Workspace is chosen once at startup, from `--workspace`
- The order is `spider mcp --workspace <path>`, then the rules of `010-add-workspace-and-cli-contract` from the server's working folder: the nearest `.spider/` or `spider.toml` up to the home folder, otherwise the global Workspace.
- Client configs pass `--workspace` in their `args`, and the `.mcpb` maps its `workspace` setting to that argument (D9).
- Each tool call opens its own read-only connection for queries, so the server keeps no state between calls, which fits the stateless protocol and cursor-based paging.
- *Alternative:* an environment variable. The maintainer ruled these out on 2026-09-27: settings come only from flags and `spider.toml`.
- *Alternative:* a `workspace` input on every tool. It gives flexibility, but it would let a model point writes at any folder, which breaks write confinement.

### D6. Blocking service calls run in worker threads
Service calls are synchronous: SQLite queries and Report rendering. The server runs them with `anyio.to_thread.run_sync`, so the stdio loop stays responsive. For example, `crawl_status` answers while a slow `sql` runs, and cancellation notifications are still read.

### D7. The tool set
- It follows the Commands that make sense for an agent without a shell.
- It adds three tools, which the maintainer confirmed:
  - `schema`, because without the Skill an agent needs it to write SQL
  - `rules`, for how-to-fix texts
  - `doctor`, because a `.mcpb` server runs in Claude Desktop's own uv environment, not in the terminal's `uv tool` environment, so only an MCP tool can diagnose it
- These Commands are left out:
  - `export` produces large files meant for people. The Report already writes CSV files for them.
  - `crawls rm` is destructive.
  - `init`, `skill install` and `commands` have no use for a client without a shell.

### D8. Inline Report Notes live in the Crawl's reports folder
Claude Desktop has no file-writing tool by default, so `report` accepts `notes` as an object.
- The server writes them as Report Notes files, following 070's contract, into `.spider/reports/<crawl-id>/notes/`, and passes that folder as `--notes`.
- The folder is next to the Report's default location, so `crawls rm` (060) removes notes and Reports together.
- Write confinement holds, and 070's merge path is reused unchanged.

### D9. `.mcpb` layout: a thin bundle that installs the released package
```
manifest.json      (manifest_version 0.4, server.type "uv", user_config.workspace, tools, compatibility)
pyproject.toml     (dependencies = ["spider==<version>"], requires-python ">=3.12,<3.15")
uv.lock            (locked for all three platforms at build time)
.python-version    (3.14)
server.py          (entry point: runs the package's `spider mcp` entry with the given arguments)
icon.png
```
- `server.mcp_config.args` ends with `mcp --workspace ${user_config.workspace}`.
- `user_config.workspace` is a required `directory` setting whose default is `${HOME}`. With that default, the Crawls go to `~/.spider/crawls/`, the same data folder as the global Workspace, and the bundle never passes an empty argument.
- `scripts/build_mcpb.py` does the following:
  1. renders the manifest from the package version and the tool registry
  2. runs `uv lock`
  3. zips the files into `dist/spider-<version>.mcpb`
- CI validates the result with `npx @anthropic-ai/mcpb validate`.
- The exact `mcp_config` for the `uv` type follows the uv example in the MCPB repository. Implementation checks it with the validator and a manual install.
- *Alternative:* server type `python` with vendored dependencies. It means a large archive and platform-specific wheels (aiohttp, selectolax, msgspec, zstandard) per OS, and it gets no uv-managed Python.

### D10. The plugin `.mcp.json` runs `spider mcp` from PATH
The plugin's Skill drives the installed CLI, so the MCP server should be the same version. Without `--workspace`, the server finds the project's Workspace from the working folder, as the CLI does.
- *Alternative:* `uvx --python 3.14 spider mcp`. It works without an installed CLI, but it can run a different version than the CLI and starts more slowly.
- Side effect: a contributor who opens this repository in Claude Code sees the same file as a project MCP config. CONTRIBUTING says so.

### D11. `mcp` is a core dependency, imported lazily
`spider mcp` works after a plain install. The import happens inside the `mcp` Command, so other Commands' startup time and the outdated-Skill check stay unaffected.
- *Alternative:* an optional `[mcp]` extra. It would complicate the installers, the plugin and the bundle for little gain.

## Test seams

- **MCP tools (5):** every tool, schema, annotation, instruction and error-mapping scenario runs through an in-process MCP client session connected to the server object with the SDK's in-memory transport. Parity scenarios compare the session result with the CLI output produced for the same inputs in the same temporary Workspace.
- **CLI (1), real subprocess runs:** these cover the stdio behaviour:
  - stdout purity
  - exit when stdin closes
  - UTF-8 with console code page 437 on Windows
  - Crawls outliving the server, on Windows, macOS and Linux
- **HTTP fixture site (3):** every Crawl in these tests targets the local fixture site, using its `delay` option for the polling, stop and resume scenarios.
- **Report (7):** the notes scenarios parse the generated HTML.
- **Install and packaging (8):** covers the `.mcpb` bundle, `.mcp.json` and the fenced snippets of `docs/mcp.md`.
  - Tests run `scripts/build_mcpb.py` and inspect the archive's `manifest.json`, `pyproject.toml` and `.python-version`.
  - The official validator runs as a CI step.
- **No test doubles.** `open: true` is tested through 070's own headless behaviour on Linux, with no display. The result is `open_failed`, and no browser is started.

## Risks / Trade-offs

- **SDK 2.x speaks the 2026-07-28 revision, which older clients may not.**
  - Mitigation: pin `mcp>=2.2,<3`.
  - Mitigation: check the server by hand in Claude Desktop, Codex, Cursor and VS Code (tasks in groups 7 and 8).
  - Mitigation: if an important client lags, keep the SDK's compatibility negotiation on.
- **Windows job objects.** A client may run servers in a job object that kills child processes when the job closes. The detached Crawl would then die with the server.
  - Mitigation: the detach of `060-add-crawl-control` breaks away from the job where it is allowed, and otherwise warns `job_may_end_crawl`.
  - Mitigation: `crawl_status` then shows the Crawl as interrupted, and `crawl_resume` continues it.
- **GUI clients don't see PATH changes made after they started.**
  - Mitigation: `docs/mcp.md` shows the absolute `spider.exe` path. The `.mcpb` does not depend on PATH.
- **Large results fill the model's context.**
  - Mitigation: the CLI's default `limit`, the `fields` input, `LIMIT` in `sql`, and server instructions that push `summary` and `issues` first.
  - `page` with `html: true` returns what the agent asked for, and the instructions discourage it.
- **Prompt injection through crawled text in tool results.**
  - Mitigation: the instructions label crawled text as untrusted, and the Report escapes it (070).
- **Long `report` builds on very large Crawls may hit client tool timeouts.**
  - Mitigation: `docs/mcp.md` documents the client timeout settings. Moving `report` to a detached job is a later option.
- **`manifest_version` 0.4 and the `uv` type are new.**
  - Mitigation: validate in CI, and install the bundle by hand in Claude Desktop on Windows and macOS for each release.

## Migration Plan

This is new functionality with nothing to migrate. When the product name changes, the tool names stay the same, and the server name, bundle name, `.mcp.json` key and snippets change together with the CLI name.

## Open Questions

- When `--workspace` is the home folder (the bundle's default), should settings be read from `~/spider.toml` or `~/.spider/spider.toml`? That depends on how `010-add-workspace-and-cli-contract` treats a `--workspace` equal to the home folder. The data folder is `~/.spider/` either way.
- Should there be a read-only server mode (`spider mcp --read-only`) that hides `crawl_start`, `crawl_stop`, `crawl_resume` and `report`, for cautious users? It would be an additive flag.
- Should `crawl_start` refuse, by itself, a Crawl above 5,000 estimated URLs unless the call confirms it? This would be a hard guard. For now the instructions hand such Crawls off.
- Should polling move to MCP Tasks once Claude Desktop and Codex support them? That is a v1.0 decision.
