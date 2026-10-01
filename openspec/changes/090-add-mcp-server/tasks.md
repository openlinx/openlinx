Every task is one red → green slice and one commit whose message names its scenario:
1. Write the failing test at the named seam (docs/testing.md) and watch it fail for the right reason.
2. Write only enough code to make it pass.
3. Run the full suite.

MCP-seam tests use an in-process MCP client session. Crawls in tests always target the local fixture site. No test doubles are used in this change.

## 1. Server skeleton

- [ ] 1.1 Drive "Server identity" (MCP seam). Add `mcp>=2.2,<3`, and a `spider mcp` Command that imports `mcp` lazily and starts an `MCPServer` named `spider` with the CLI version.
- [ ] 1.2 Drive "Exit when the client disconnects" (CLI seam, with a real subprocess on Windows, macOS and Linux).
- [ ] 1.3 Drive "The MCP server does not print the notice" (CLI seam, with a real subprocess). Add `mcp` to the skip list of the outdated-Skill check of `080-add-agent-skill`.
- [ ] 1.4 Docs: create `docs/mcp.md` with what the server is and how to start it with `spider mcp [--workspace <path>]`.
- [ ] 1.5 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. Registry, parity and error mapping

- [ ] 2.1 Drive "summary parity" (MCP seam, with a completed fixture Crawl). Add the first registry entry: tool name, Command, service call, and the CLI serialiser into `structuredContent`.
- [ ] 2.2 Drive "Text content mirrors structured content" (MCP seam).
- [ ] 2.3 Drive "Unknown Crawl" (MCP seam) by returning the CLI's full error diagnostic as an `isError` result.
- [ ] 2.4 Drive "pages parity with fields and limit" (MCP seam). Add the `pages` tool, with its input schema derived from the Command's option metadata.
- [ ] 2.5 Drive "Details are kept" (MCP seam): `unknown_field` with its `details` intact.
- [ ] 2.6 Drive "Arrays for list-valued flags" (MCP seam).
- [ ] 2.7 Drive "No Workspace input" (MCP seam). Unknown properties are rejected.
- [ ] 2.8 Drive "Invalid input" (MCP seam) by mapping schema violations to the CLI's usage-error code.
- [ ] 2.9 Drive "Server survives errors" (MCP seam).
- [ ] 2.10 Docs: explain in `docs/mcp.md` that results are the CLI's JSON and that errors are the CLI's diagnostics.
- [ ] 2.11 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. Workspace and crawl_start

- [ ] 3.1 Drive "crawls_list parity" (MCP seam).
- [ ] 3.2 Drive "Workspace argument" (MCP seam). `spider mcp --workspace <path>` resolves the Workspace once, at startup.
- [ ] 3.3 Drive "Only protocol messages on stdout" (CLI seam, with a real subprocess). Route logging and warnings to stderr.
- [ ] 3.4 Drive "Dry run" (MCP seam) for `crawl_start` with `dry_run`.
- [ ] 3.5 Drive "Dry run starts nothing" (MCP seam).
- [ ] 3.6 Drive "crawl_start mirrors spider crawl" (MCP seam), with the Crawl Mode inputs `url`, `urls` and `sitemap`.
- [ ] 3.7 Drive "Sitemap input is an array" (MCP seam).
- [ ] 3.8 Drive "Two Crawl Modes at once" (MCP seam), with `mode_conflict` from `024-add-list-and-sitemap-modes`.
- [ ] 3.9 Drive "Detached start returns quickly" (MCP seam, with the fixture site's `delay` option), through the Crawl Service's detached start from `060-add-crawl-control`.
- [ ] 3.10 Drive "Global Workspace by default" (MCP seam, with a temporary home folder).
- [ ] 3.11 Drive "Windows global Workspace" (MCP seam, in the Windows CI job).
- [ ] 3.12 Docs: add a "Workspace" section to `docs/mcp.md`: the `--workspace` argument and the fallback rules.
- [ ] 3.13 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. Polling and crawl control

- [ ] 4.1 Drive "Status answers quickly during a Crawl" (MCP seam, with `delay`). Add the `crawl_status` tool, and run service calls in worker threads.
- [ ] 4.2 Drive "List mode" (MCP seam, polling until `state` is `completed`).
- [ ] 4.3 Drive "Partial data during a Crawl" (MCP seam, with a 20-Page fixture site and `delay`).
- [ ] 4.4 Drive "Crawl completes after the server exits" (CLI seam, with real subprocesses on macOS and Linux).
- [ ] 4.5 Drive "Windows detached Crawl" (CLI seam, with real subprocesses in the Windows CI job).
- [ ] 4.6 Drive "Stop" (MCP seam, with `delay`) for `crawl_stop`.
- [ ] 4.7 Drive "Resume" (MCP seam, with `delay`) for `crawl_resume` as `resume --detach`.
- [ ] 4.8 Docs: add a "Long Crawls" section to `docs/mcp.md`: detached Crawls, polling, stop and resume.
- [ ] 4.9 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Paging and query tools

- [ ] 5.1 Drive "Two pages" (MCP seam, with a three-Page fixture Crawl).
- [ ] 5.2 Drive "Cursor survives a new server" (MCP seam).
- [ ] 5.3 Drive "Rules page" (MCP seam) for `rules` without `rule_id`.
- [ ] 5.4 Drive "Segment input" (MCP seam).
- [ ] 5.5 Drive "Issues of one Rule" (MCP seam).
- [ ] 5.6 Drive "One Rule" (MCP seam) for `rules` with `rule_id`.
- [ ] 5.7 Drive "One Page" (MCP seam).
- [ ] 5.8 Drive "Page HTML" (MCP seam), with the `html` and `encoding` fields of `050-add-query-and-segments`.
- [ ] 5.9 Drive "UTF-8 on Windows" (CLI seam, with a real subprocess and console code page 437 in the Windows CI job).
- [ ] 5.10 Drive "Schema" (MCP seam).
- [ ] 5.11 Docs: add the tool reference table (tool, Command, inputs) to `docs/mcp.md`.
- [ ] 5.12 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green.

## 6. Read-only sql

- [ ] 6.1 Drive "Schema change is rejected" (MCP seam). The code comes from `050-add-query-and-segments` (`sql_not_allowed`), and the `sql` result stays `{columns, rows, row_count, truncated, limit}`.
- [ ] 6.2 Drive "Crawl file unchanged" (MCP seam).
- [ ] 6.3 Drive "Attach is rejected" (MCP seam).
- [ ] 6.4 Docs: add an "SQL through MCP" note (read-only; use with `schema`) to `docs/mcp.md`.
- [ ] 6.5 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.

## 7. Report, report_brief and doctor tools, and write confinement

- [ ] 7.1 Drive "Default destination" (MCP seam) for `report`.
- [ ] 7.2 Drive "Destination on Windows" (MCP seam, in the Windows CI job) for `dest`.
- [ ] 7.3 Drive "Inline notes" (MCP seam, with the Report seam's HTML parsing).
- [ ] 7.4 Drive "Inline notes are kept with the Crawl's reports" (MCP seam). Write the notes to `.spider/reports/<crawl-id>/notes/` and pass that folder as `--notes`.
- [ ] 7.5 Drive "Notes folder" (MCP seam, with HTML parsing).
- [ ] 7.6 Drive "Both notes inputs" (MCP seam).
- [ ] 7.7 Drive "Open without a display" (MCP seam, on Linux in CI).
- [ ] 7.8 Drive "Section Brief parity" (MCP seam) for `report_brief`.
- [ ] 7.9 Drive "Listing the Report Sections" (MCP seam).
- [ ] 7.10 Drive "Failing checks are a normal result" (MCP seam) for the `doctor` tool.
- [ ] 7.11 Drive "Server Workspace" (MCP seam).
- [ ] 7.12 Drive "File-system audit" (MCP seam). Snapshot `<tmp>/home`, `<tmp>/cwd`, `<tmp>/ws` and `<tmp>/out`, call every tool once, and compare.
- [ ] 7.13 Docs: add "Reports from an MCP client" (inline notes, `dest`, `open`) to `docs/mcp.md`.
- [ ] 7.14 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. Tool list, annotations and instructions

- [ ] 8.1 Drive "Tool names" (MCP seam) against the exact set of 15 names.
- [ ] 8.2 Drive "Read-only tools" (MCP seam).
- [ ] 8.3 Drive "Open-world tools" and "Destructive tools" (MCP seam). This is a trivial pair of annotation flags.
- [ ] 8.4 Drive "Instructions delivered" (MCP seam).
- [ ] 8.5 Drive "Unknown estimate is handed off" (MCP seam).
- [ ] 8.6 Drive "crawl_start description" (MCP seam).
- [ ] 8.7 Docs: add "Guidance for agents without the Skill" to `docs/mcp.md`, quoting the server instructions.
- [ ] 8.8 Review: run the code-review skill on group 8's commits, then refactor with the whole suite green.

## 9. Claude Desktop bundle

- [ ] 9.1 Drive "Bundle file" (install-and-packaging seam) with a skeleton `scripts/build_mcpb.py` and a template in `packaging/mcpb/`.
- [ ] 9.2 Drive "Manifest fields" (install-and-packaging seam).
- [ ] 9.3 Drive "Tools match the server" (install-and-packaging seam, compared with an MCP-seam listing) by rendering `tools` from the registry.
- [ ] 9.4 Drive "Workspace setting" (install-and-packaging seam): `user_config.workspace` mapped to `--workspace`.
- [ ] 9.5 Drive "Python and package pins" (install-and-packaging seam), with `pyproject.toml` pinned to `spider==<version>`, `.python-version` set to 3.14, and `uv lock`.
- [ ] 9.6 Drive "Official validation" (install-and-packaging seam, as a CI step that runs `npx @anthropic-ai/mcpb validate` on the built manifest).
- [ ] 9.7 Drive "Pins agree" (install-and-packaging seam). Add `packaging/mcpb/.python-version` to the pin test of `100-add-installers`.
- [ ] 9.8 Drive "Bundle built in the release" (install-and-packaging seam). The `build` job of `.github/workflows/release.yml` runs `scripts/build_mcpb.py` before it writes `SHA256SUMS`.
- [ ] 9.9 Drive "Bundle is a release asset" (install-and-packaging seam). The `release` job attaches `spider-<version>.mcpb`.
- [ ] 9.10 Docs: add a "Claude Desktop" section to `docs/mcp.md`, and the `.mcpb` to the release assets in `RELEASING.md`. Check it by hand on Windows and macOS: install the bundle, keep the default Workspace setting, then run `crawl_start` (a dry run and a small Crawl), `summary` and `report`. Record the results in the PR.
- [ ] 9.11 Review: run the code-review skill on group 9's commits, then refactor with the whole suite green.

## 10. Plugin config and client snippets

- [ ] 10.1 Drive "Plugin MCP config" (install-and-packaging seam) by adding `.mcp.json` at the repository root.
- [ ] 10.2 Drive "Codex snippet" (install-and-packaging seam).
- [ ] 10.3 Drive "JSON snippets" (install-and-packaging seam) for Cursor, VS Code and Gemini CLI.
- [ ] 10.4 Drive "Claude Code, Workspace and Windows notes" (install-and-packaging seam).
- [ ] 10.5 Docs: add the README pointer to `docs/mcp.md`, and a CONTRIBUTING note that the repository-root `.mcp.json` doubles as a project MCP config. Check by hand that the snippets work in Codex and in Cursor or VS Code, and that installing the plugin in Claude Code adds the tools. Record the results in the PR.
- [ ] 10.6 Review: run the code-review skill on group 10's commits and on the whole change, then refactor with the whole suite green.
