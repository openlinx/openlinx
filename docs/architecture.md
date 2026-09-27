# Architecture

A short map for contributors and coding agents. Terms follow [CONTEXT.md](../CONTEXT.md), decisions are in [adr/](adr/), and which change builds what is in [ROADMAP.md](../ROADMAP.md).

## Shape

```
        AI agents (Skill)        Claude Desktop, Codex, IDEs      people
               │                          │                         │
         ┌─────▼──────┐            ┌──────▼──────┐                  │
         │  CLI       │            │ MCP server  │                  │
         │  (Typer)   │            │ (stdio)     │                  │
         └─────┬──────┘            └──────┬──────┘                  │
               └──────────────┬───────────┘                         │
        ┌─────────────────────▼──────────────────────┐              │
        │ Services: Query · Crawl · Report            │──── HTML Report
        └─────────────────────┬──────────────────────┘
                     ┌────────▼────────┐
                     │  Crawl Store    │  one SQLite file per Crawl,
                     │  (Workspace)    │  public versioned schema
                     └─────────────────┘
```

- **The CLI and the MCP server are thin.** They parse input, call a service and serialise the result (JSON by default). Neither holds business logic, so a future REST API or web UI can wrap the same services.
- **The services are plain Python** with typed inputs and outputs.
  - The **Query Service** handles summary, pages, page, issues, sql, export and Segments.
  - The **Crawl Service** handles start, detach, status, stop, resume and dry-run.
  - The **Report Service** handles the ReportModel, HTML and Section Briefs.
- **The tool never calls an LLM** ([ADR-0004](adr/0004-tool-never-calls-an-llm.md)).

## Crawl pipeline

```
Frontier ──► Scheduler ──► Fetcher ──► Parse pool ──► Rules ──► Writer ──► Crawl Store
(in store)   per-host      aiohttp     process pool   per Page   single,
             politeness,   behind an   selectolax     + after-   batched
             robots.txt    interface   extractors     crawl pass
```

- **Frontier:** the queue of URLs still to crawl lives in the crawl store, which makes it the single source of truth for resume, `status` and queries during a crawl ([ADR-0001](adr/0001-own-asyncio-engine-over-scrapy.md)).
- **Scheduler:** per-host concurrency (default 5), an optional rate limit and robots.txt (Protego). It also decides Scope: URLs outside it are status-checked but not followed.
- **Fetcher:** aiohttp behind an interface, so httpx2, niquests or Playwright (v1.1) can replace it. It follows redirects hop by hop and records every hop. HTTP version is measured once per host with a TLS ALPN check.
- **Parse pool:** a process pool, so parsing never blocks the event loop.
  - Extractors turn a response into Page data, Links and Resources.
  - lxml is loaded only when an XPath Custom Extraction exists (v0.3).
- **Rules:** run per Page as data arrives, then in a pass after the crawl for checks across Pages (duplicates; site-wide Rules from v0.2).
- **Writer:** the only writer, flushing in batches. A crash loses at most the unflushed batch.
- **Process model:**
  - `crawl` runs in the foreground by default.
  - `--detach` starts a separate background process (CREATE_NO_WINDOW on Windows, so the parse workers open no console windows; `start_new_session` on POSIX).
  - `status`, `stop` and `resume` talk to it through control rows in the store, so no OS signals are needed.
- **Output streams:** stdout carries the Command's single JSON result (or NDJSON rows for data streams). stderr carries JSON lines: diagnostics and progress events. Settings come only from flags and `spider.toml`, never from environment variables.

## Crawl store

- **Files:** one SQLite file per Crawl inside the Workspace.
  - WAL mode lets agents query while the writer works. On network drives it falls back to rollback-journal mode and warns.
  - The schema is a public, versioned contract ([ADR-0002](adr/0002-sqlite-crawl-store-public-schema.md)).
- **Schema definition:** SQLAlchemy 2 Core tables are the single definition ([ADR-0003](adr/0003-sqlalchemy-core-not-orm.md)). They drive batched inserts, safe `--where` → SQL translation (only known columns), Alembic migrations, and the generated SQL reference (`spider schema`, the Skill).
  - Every column has a description, because the descriptions feed that reference.
- **Tables:** each change adds its own tables and columns through a migration. Migrations are squashed before v0.1, and schema version 1 is the first public contract.
- **Read-only access:** `spider sql` opens the file with a read-only URI plus the SQLite authorizer.
- **Missing values:** a value that is not measured yet is `NULL`, never 0 ("not measured" differs from "zero").

## Page data (Screaming Frog "Internal" tab parity)

| Group | Columns |
|---|---|
| Identity and response | Address, URL-encoded address, Content Type, Status Code, Status, Indexability, Indexability Status, Response Time, Last Modified, Redirect URL, Redirect Type, Cookies (Set-Cookie), HTTP Version, Crawl Timestamp |
| Titles and headings | Title 1/2 (+ length, pixel width), Meta Description 1/2 (+ length, pixel width), Meta Keywords, H1-1/2 (+ length), H2-1/2 (+ length) |
| Directives | Meta Robots, X-Robots-Tag, Meta Refresh, Canonical Link Element, rel next/prev (HTML and HTTP header), amphtml, Mobile Alternate |
| Size | Size, Transferred, Content-Encoding |
| Content | Word Count, Sentence Count, Average Words per Sentence, Flesch Reading Ease / Readability, Text Ratio, Language, Hash, Closest Near-Duplicate†, Near-Duplicate count† |
| Links | Crawl Depth, Folder Depth, Link Score†, Inlinks, Unique Inlinks, Unique JS Inlinks†, % of Total, Outlinks, Unique Outlinks, Unique JS Outlinks†, External Outlinks, Unique External Outlinks |
| Structured data | JSON-LD / Microdata item counts and types, validation errors† / warnings† |

† These columns are null until the release that measures them (see [ROADMAP.md](../ROADMAP.md)).

## Report pipeline

```
Crawl Store ──► ReportModel ──┬──► HTML renderer ──► report.html (+ CSV files for full lists)
 (same model as `summary`)    │        ▲
                              └──► Section Briefs (JSON per Report Section)
                                       │  one subagent per Report Section writes notes/<section>.md,
                                       │  the main agent writes notes/summary.md
                                       └──── Report Notes (Markdown, raw HTML disabled)
```

- **The file:** a single self-contained file, with SVG charts and no CDN, so it works offline and can be emailed.
- **Security:** crawled text is untrusted and is always escaped.

## Agent integration

- **Skill:** generated from the CLI's command metadata, stamped with the version, and installed with `spider skill install` into `~/.claude/skills` (Claude Code) and `~/.agents/skills` (Codex and most other agents). The repo keeps a generated copy in the standard layout for plugin marketplaces and `npx skills add`.
- **MCP server:** `spider mcp` (MCP Python SDK 2.x, stdio). It ships as a `.mcpb` for Claude Desktop, and its tools return the same JSON as the CLI.
- **Plugin marketplace:** `.claude-plugin/marketplace.json` in the repo, read by both Claude Code and Codex.
- **Self-description:** `spider commands --format json`, which is the source the Skill is generated from.

## Cross-platform rules

- CI runs on Windows, macOS and Linux × Python 3.12–3.14. `requires-python` is `>=3.12,<3.15` until the dependencies ship Python 3.15 builds.
- Output is written as UTF-8 bytes (Windows pipes default to the ANSI code page until Python 3.15), and `-o <file>` avoids shell encoding problems altogether.
- Use `pathlib` everywhere and `asyncio.run(..., loop_factory=...)`, not event-loop policies.
- SSL certificates come from the OS trust store via truststore, falling back to certifi.
- Detached processes use OS-specific creation flags, and control never relies on signals.

## Package layout (target)

```
src/spider/
  cli/          Typer app, one module per command group
  mcp/          MCP server
  services/     query, crawl, report
  workspace/    Workspace discovery, settings (spider.toml)
  output/       JSON/table/CSV serialisation, paging, errors, exit codes
  store/        schema (Core tables), writer, migrations/, read-only access
  crawl/        frontier, scheduler, fetcher/, robots, scope, engine
  extract/      Page data extractors, links, content, readability, pixel widths
  rules/        Rule registry, rule modules, thresholds, Health Score
  query/        --where language, paging, Segments
  report/       ReportModel, Section Briefs, templates/, charts
  skill/        Skill generator and templates
tests/
  fixture_site/ local test site used by every change
```

## Stack

| Concern | Choice |
|---|---|
| Language | Python ≥3.12, <3.15 |
| HTTP | aiohttp (behind a Fetcher interface) |
| HTML parsing | selectolax (Lexbor); lxml only for XPath |
| robots.txt | Protego |
| Store | SQLite + SQLAlchemy 2 Core + Alembic |
| CLI / settings | Typer, pydantic-settings |
| JSON | msgspec / orjson |
| MCP | MCP Python SDK 2.x |
| TLS trust | truststore (certifi fallback) |
| Tests | pytest + local fixture site |
| Packaging | uv (`uv tool install`), PyPI |
