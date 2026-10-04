## Why

In Claude Desktop and claude.ai, skills run in Anthropic's cloud sandbox. Crawling from there needs the "All domains" egress setting, and the sandbox can never reach local or staging sites, so Claude Desktop users need a local MCP server. MCP-first clients such as Codex, Cursor, VS Code and Gemini CLI also work better with tools than with shell commands. A thin MCP layer over the same services gives all of them the CLI's data, in the CLI's JSON, with no second API to maintain.

This change is **v0.1.1**, the first change after v0.1, as the maintainer decided on 2026-10-01. It builds on the released v0.1 and on 060-min, which also ships in v0.1.1.

## What Changes

> **v0.1.1 scope (2026-10-05, see ROADMAP.md):** the tools for the foreground and the detached crawl in Spider mode, `crawl_status`, `crawl_stop`, and the v0.1 queries `summary`, `pages`, `page`, `issues` and `rules`, plus `schema` and `doctor`. **Deferred to v0.2:** `crawl_resume`, `crawls_list`, `sql`, `dry_run`, the `urls` and `sitemap` inputs (`024`), `page`'s `html`, the `report` and `report_brief` tools with inline Report Notes (`070`), and the dry-run and Hand-off guardrails in the server instructions.

- **New Command `spider mcp [--workspace <path>]`.** It runs a local stdio MCP server built on the MCP Python SDK `mcp` 2.x (`MCPServer`). Its tools mirror the crawl-control, query and report Commands:

  | Tool | Equivalent Command |
  |---|---|
  | `crawl_start` | `crawl --detach`, or `crawl --dry-run` with `dry_run: true` |
  | `crawl_status` | `status` |
  | `crawl_stop` | `stop` |
  | `crawl_resume` | `resume --detach` |
  | `crawls_list` | `crawls list` |
  | `summary` | `summary` |
  | `issues` | `issues [<rule-id>]` |
  | `pages` | `pages` |
  | `page` | `page <url>` |
  | `sql` | `sql` (read-only) |
  | `schema` | `schema` |
  | `rules` | `rules list`, `rules show <id>` |
  | `report` | `report`; writes the HTML to `dest` and returns the receipt |
  | `report_brief` | `report brief --section <id>`, `report brief --list` |
  | `doctor` | `doctor` |

- **Contract for every tool:**
  - **Inputs** are the Command's flags in snake_case.
    - `url`, `urls` and `sitemap` (an array) select the Crawl Mode. Giving more than one fails with `mode_conflict`.
  - **Results:** the CLI's JSON, returned as structured content and as text.
  - **Paging:** `crawls_list`, `issues`, `pages`, `schema` and `rules` take `limit` and `cursor`, and return `next_cursor`.
  - **Errors:** a failure becomes an MCP tool error that carries the CLI's full diagnostic, `{level, code, message, hint, details}`.
  - **Long Crawls** run detached, and the agent polls `crawl_status`.
  - **`sql`** is read-only.
  - **Writes:** no tool writes outside the Workspace, except the Report's `dest` folder.
- **The Workspace** is fixed when the server starts. It is the `--workspace` argument, or else the one that the rules of `010-add-workspace-and-cli-contract` find from the server's working folder, ending at the global Workspace `~/.spider/`. No environment variable is read.
- **Inline Report Notes.** `report` accepts `notes` inline, because Claude Desktop cannot write files. The notes are stored in the Crawl's reports folder (`.spider/reports/<crawl-id>/notes/`), so `crawls rm` removes them along with the Report.
- **Server instructions** carry the agent guardrails for clients that have no Skill:
  - dry run first
  - Hand-off for estimates above 5,000 URLs or `null`
  - polling
  - untrusted crawled text
- **A Claude Desktop bundle, `spider-<version>.mcpb`.**
  - It uses manifest version 0.4 and server type `uv`, and runs `spider mcp --workspace <folder>` on Python 3.14.
  - The folder comes from the bundle's `workspace` setting, which defaults to the home folder.
  - `scripts/build_mcpb.py` builds it.
- **The `.mcpb` in the release pipeline of `100-add-installers`:**
  - the `build` job runs `scripts/build_mcpb.py`, and `SHA256SUMS` covers the bundle.
  - the `release` job attaches `spider-<version>.mcpb` to the GitHub release, from v0.1.1 on.
  - the pin test also checks the bundle's `.python-version`.
- **`.mcp.json` at the repository root.** This is the plugin root of the `080-add-agent-skill` marketplace entry, which ships without an MCP config in v0.1. From v0.1.1 the plugin ships both the Skill and the MCP server.
- **Outdated-Skill notice.** `spider mcp` joins the Commands that skip the notice of `080-add-agent-skill`, because its stderr is a client log.
- **`docs/mcp.md`** gives configuration snippets for Codex (`~/.codex/config.toml`), Cursor (`.cursor/mcp.json`), VS Code (`.vscode/mcp.json`), Gemini CLI (`~/.gemini/settings.json`) and Claude Code (`claude mcp add`).
- **Small additions, confirmed by the maintainer:**
  - the `schema`, `rules` and `doctor` tools. Without the Skill, an agent needs `schema` to write SQL, `rules` for how-to-fix texts, and `doctor` to diagnose the server's own environment.
  - inline `notes` for `report`

## Capabilities

### New Capabilities
- `mcp-server`: `spider mcp`, its tools and their inputs and outputs, error mapping, Workspace selection, write confinement, server instructions, the `.mcpb` bundle, the plugin `.mcp.json` and the documented client configurations.

### Modified Capabilities
- `installation`: the release workflow builds the `.mcpb` and attaches it to each GitHub release, and the pin test includes the bundle's `.python-version`.
- `agent-skill`: `spider mcp` does not print the outdated-Skill notice.

## Non-goals

- **Remote (Streamable HTTP) transport.** ChatGPT developer mode needs it, so ChatGPT is served later. It is in the **Backlog**, next to the REST API. The ChatGPT desktop app (Codex) already runs local stdio servers.
- **No MCP tools for `export`, `crawls rm`, `init`, `skill install` or `commands`.** These stay CLI-only, and no release plans them as tools.
- **Tools for later Commands** come with those Commands:
  - `links`, `redirects`, `sitemaps`: **v0.2**
  - `diff`, `duplicates`, `structured_data`: **v0.3**
- **MCP resources, prompts, and Tasks or progress notifications** for long Crawls are not in v0.1.1. To be revisited for **v1.0**, once clients support them widely.
- **One server that serves several Workspaces** is not planned.
- **Listing in Claude Desktop's extension directory** waits for the product name, in **v1.0**.

## Impact

- **Code:** `src/spider/mcp/` (server, tool registry, schema derivation, error mapping) and `src/spider/cli/mcp.py`.
- **Packaging:** `packaging/mcpb/` (manifest template, bundle `pyproject.toml`, `.python-version`, entry script, icon) and `scripts/build_mcpb.py`.
- **Repository files:** `.mcp.json` and `docs/mcp.md`.
- **Changed:** `.github/workflows/release.yml` (the bundle in `build` and `release`), the pin test in `tests/install/`, the skip list of the outdated-Skill notice, and the asset list in `RELEASING.md`.
- **Dependencies:** `mcp>=2.2,<3`, imported only by `spider mcp`. CI also runs `npx @anthropic-ai/mcpb` to validate the bundle manifest.
- **Depends on:**
  - `010-add-workspace-and-cli-contract`: Workspace resolution, the diagnostic shape, exit codes and command metadata
  - `015-add-crawl-store`: `--crawl` and `schema`
  - `024-add-list-and-sitemap-modes` (v0.2): `mode_conflict`, and the List and Sitemap modes
  - `040-add-rules`: rules
  - `050-add-query-and-segments`: the query services; `page` with `html` and `encoding`, and `sql`, from v0.2
  - `060-add-crawl-control`: 060-min (v0.1.1) for detach, status and stop, and the command it records for Crawls started through MCP; `resume --detach`, dry run and `crawls list` from v0.2
  - `070-add-html-report` (v0.2): report with `--dest`, report brief, and the Report Notes contract
  - `080-add-agent-skill`: `doctor`, the plugin manifests and the outdated-Skill notice
  - `100-add-installers`: the release workflow, `SHA256SUMS` and the pin test
