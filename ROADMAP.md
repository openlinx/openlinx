# Roadmap

> **Working name:** `spider`. That covers the command, the Python package, `spider.toml` and the `.spider/` Workspace folder. The product name is still open and must be chosen, and checked as free on PyPI and GitHub, before the first release.

Terms follow [CONTEXT.md](CONTEXT.md). How the pieces fit together is in [docs/architecture.md](docs/architecture.md), the decisions behind them are in [docs/adr/](docs/adr/), and how everything is tested is in [docs/testing.md](docs/testing.md).

Each milestone ships as a set of OpenSpec changes in `openspec/changes/`. Change numbers give the build order. The graph below shows which changes can run in parallel.

## v0.1: first public pre-release

| # | Change | Capabilities (specs) | Commands | Status |
|---|---|---|---|---|
| 000 | `000-scaffold-project` | none (tooling only) | `spider --version` | done |
| 010 | `010-add-workspace-and-cli-contract` | `workspace`, `cli-contract` | `init`, `commands` | planned |
| 015 | `015-add-crawl-store` | `crawl-store` | `schema`; `--crawl` | planned |
| 020 | `020-add-crawl-core` | `crawling` | `crawl <url>` (foreground) | planned |
| 022 | `022-add-fetch-policy` | `fetching` | `crawl` fetch flags | planned |
| 024 | `024-add-list-and-sitemap-modes` | `crawl-modes` | `crawl --list`, `crawl --sitemap` | planned |
| 026 | `026-add-parse-pool` | `crawl-performance` (only if the pool goes ahead) | none | planned, conditional |
| 030 | `030-add-page-data` | `page-data` | none (data only) | planned |
| 040 | `040-add-rules` | `rules` | `rules` | planned |
| 050 | `050-add-query-and-segments` | `querying`, `segments`; adds to `cli-contract` | `summary`, `pages`, `page`, `issues`, `sql`, `export`; `--segment`, `--format csv`, `--no-bom`, `-o` | planned |
| 060 | `060-add-crawl-control` | `crawl-control` | `crawl --detach/--dry-run`, `status`, `stop`, `resume`, `crawls` | planned |
| 070 | `070-add-html-report` | `reporting` | `report`, `report brief` | planned |
| 080 | `080-add-agent-skill` | `agent-skill`, `diagnostics` | `skill install`, `doctor` | planned |
| 100 | `100-add-installers` | `installation` | none (install scripts, release pipeline) | planned |

### Build order

```
000 ─► 010 ─► 015 ─► 020 ─┬─► 022 ─┬─► 030 ─► 040 ─► 050 ─┬─► 070 ─┐
                          ├─► 024 ─┤                      │        ├─► 080 ─► 100
                          ├─► 026  │                      │        │
                          │        └──────► 060 ──────────┴────────┘
```

- The critical path is mostly sequential: 000 → 010 → 015 → 020 → 022 → 030 → 040 → 050 → 070 → 080 → 100.
- 090 comes after the v0.1 release, as v0.1.1.
- Once 020 is in, 022, 024 and 026 can run in parallel.
- 060 needs 022 and 024 (List mode, and the sitemap reader for the dry-run estimate). It can then run alongside 030–050.
- 070 needs 050 (the summary model, CSV writing, test data) and 060 (for the end-to-end test).
- **After 020 lands:** re-plan 030/040/050 so that a thin end-to-end slice comes first (crawl → store → a minimal `issues` with 3–5 Rules), and deepen from there.

### What each change owns

If a change needs something another change owns, it depends on that change instead of redefining it.

- **000-scaffold-project**:
  - `src/` package layout, the uv-managed project, ruff, strict mypy, and pytest with pytest-asyncio, hypothesis and coverage (a 90% line + branch gate).
  - Asyncio loop wiring for tests on all OSes.
  - The **local fixture site** over plain HTTP: pages, status codes, redirects, robots.txt, sitemaps, headers, slow responses. 022 adds TLS, virtual hosts and gzip.
  - **Guards:**
    - tests may open network connections only to localhost
    - a dependency allowlist test keeps out any telemetry or LLM SDK
  - CI: Windows/macOS/Linux × Python 3.12–3.14, including Node for `openspec validate` and seam 9.
  - The Typer skeleton with `--version`; LICENSE (Apache-2.0), README, CONTRIBUTING (the TDD loop and the OpenSpec workflow).
- **010-add-workspace-and-cli-contract**:
  - **Workspace:**
    - `spider init`; discovery order: `--workspace`, then the nearest `.spider/` or `spider.toml` going upward, then `~/.spider/`.
    - `spider.toml` and settings precedence: flag > `spider.toml` > default. **No environment variables** are settings.
    - `settings_invalid` (exit 3), which also covers `[segments]` checked at load time.
  - **CLI contract:**
    - **stdout** carries the Command's single JSON result, or NDJSON rows for data streams (`--format jsonl`).
    - **stderr** carries JSON lines: diagnostics `{level, code, message, hint, details}` and progress events `{event, ts, data}`.
    - **Partial results:** a Command whose result describes a failed outcome prints it and exits non-zero with exactly one error diagnostic.
    - Formats are `json|jsonl|table`. The `csv` format, the CSV policy and `-o` belong to 050.
    - Also: the paging envelope, exit codes, `spider commands --format json` (including each Command's output kind), and the global flags.
- **015-add-crawl-store**:
  - One SQLite file per Crawl and crawl ids, including ids chosen by the caller and reserved (needed by `--detach`).
  - The `crawl` and `seeds` tables.
  - The transactional writer: units of work mixing inserts, updates and reads, flushed in batches. A crash loses at most the unflushed batch.
  - WAL, with a network-drive fallback and a `store.journal_mode` override.
  - Read-only access, with two stated exceptions: control rows written by other processes, and a reader marking a dead Crawl `interrupted`.
  - Migrations and versioning.
  - `spider schema [TABLE]`, with table order fixed by change number.
  - The `--crawl latest|<id>|<path>` option used by every query Command.
  - Redaction of secrets in recorded commands and config, both whole values and partial (`Cookie: ***`, `user:***@proxy`).
  - Table conventions and `docs/schema.md` as the contract.
- **020-add-crawl-core**:
  - Spider mode (`crawl <url>`) and URL normalisation.
  - **Scope:** `--scope host|subdomains|subfolder`, `--subdomains`, `--include/--exclude`, `--max-depth`, `--max-urls` (default 10,000; reaching it leaves the Crawl resumable), `--strip-params`.
  - **Section Crawl**, and robots.txt (obeyed by default, `--ignore-robots`, `--robots-user-agent`).
  - **The robots directives parser** (meta robots and X-Robots-Tag, used by 030 as well).
  - Politeness (`--concurrency`, `--rate`).
  - The frontier.
  - **Link discovery and the Link type table**, with `--follow-nofollow` and `--check-external`.
  - Crawl Depth.
  - **Hooks:** a per-response writer hook for every recorded URL, and the **post-crawl passes** hook, which runs for `completed` or `stopped` Crawls and is safe to re-run.
  - Progress events and the result.
  - **Ctrl+C:** the Crawl becomes `stopped` with `stop_reason: interrupt`, and the command exits 130.
  - **Unreachable Seed:** the Crawl becomes `failed` and resumable, and the command exits 8.
  - Parsing runs in-process at this stage.
- **022-add-fetch-policy**:
  - Timeouts, retries with backoff, and redirects followed hop by hop, with every hop recorded.
  - Limits: `--max-redirects`, loop detection, body and URL caps.
  - Compression.
  - **TLS trust:** truststore with a certifi fallback, including a speed test.
  - HTTP version per origin via ALPN (`http_1_1` / `http_2`).
  - Proxy, basic auth, custom headers and user agent; no cookies are sent.
  - Status and size checks for Resources.
  - The `response_headers` table, where cookie values are always stored as `***`.
  - HTTPS, virtual hosts and gzip on the fixture site (trustme).
- **024-add-list-and-sitemap-modes**:
  - List mode (`--list <file|->`) and Sitemap mode (`--sitemap <url>`, repeatable, with index files and gzip).
  - `mode_conflict` when two Crawl Modes are given.
- **026-add-parse-pool** (conditional):
  - First, the ~500k-URL benchmark against 020's in-process parsing, run manually or nightly and not part of the CI gate. Its numbers go in `docs/benchmarks.md`.
  - The maintainer then decides. Only if parsing is the bottleneck: parsing in a process pool, with bounded queues, clean shutdown of workers on interrupt, and no console windows on Windows. Otherwise 026 is archived with the benchmark alone.
- **030-add-page-data**:
  - Every Internal-tab column, added in the slice where it is first needed.
  - Indexability and Indexability Status.
  - Link attributes stored for analysis (building on 020's discovered Links and Link types).
  - Inlink and outlink counts, computed in the post-crawl passes.
  - The Content Area and content metrics, Flesch, language, pixel widths and the Exact Duplicate hash.
  - Structured-data item counts, and cookie names without their values.
  - **Raw HTML storage:** zstd; automatic when the Crawl's `--max-urls` is at most 50,000, decided when the Crawl starts; `--store-html/--no-store-html` override it.
- **040-add-rules**:
  - The Rule model and a catalogue of **42 Rules**; `http-url` is a Warning with High Priority.
  - Thresholds and disabling in `spider.toml`.
  - Evaluation per URL (through the per-response hook) and in the post-crawl passes.
  - Issues and Affected URLs, including `issues.affected_count`.
  - The Health Score.
  - `spider rules [list|show <id>]` and `rule_not_found` (exit 4).
- **050-add-query-and-segments**:
  - `summary` (the data model shared with the Report).
  - `pages` with the `--where` language, `--fields`, `--sort` and paging.
  - `page <url>`: JSON, where `--html` adds an `html` field and `--headers` shows redacted headers.
  - `issues` and `issues <rule-id>`.
  - Read-only `sql`.
  - `export <view>`: `jsonl` by default, or `csv`; the `resources` view is defined over `urls` and `links`.
  - **Segments** and `--segment`.
  - **The CSV policy and output files**, for every Command (moved from 010 on 2026-10-01):
    - the `csv` format; the single **CSV policy** is UTF-8 with BOM, CRLF and formula neutralisation, with `--no-bom` to turn the BOM off
    - `-o <file>` writes exactly the stdout bytes, atomically, and leaves stdout empty (`output_written`, `output_not_writable`)
- **060-add-crawl-control**:
  - `crawl --detach`: on Windows it uses CREATE_NO_WINDOW. In List mode, the parent stores the Seeds before spawning the Crawl.
  - `status`, which detects a dead process.
  - `stop` (`--wait`) and `resume`. Resume works for `stopped`, `interrupted` and `failed` Crawls, asks again for secrets, and accepts a higher `--max-urls`.
  - `crawl --dry-run`: the checked config, the equivalent command, and a URL estimate that may be `null`.
  - `crawls list|show|rm`, where `rm` also deletes that Crawl's reports and notes.
- **070-add-html-report**:
  - `report`: a self-contained offline HTML file plus CSV files. It is written to `--dest <dir>` (default `.spider/reports/<crawl-id>/`), and a JSON receipt goes to stdout.
  - Report Sections, and `report brief --section <id>` / `--list`.
  - Report Notes, SVG charts, Health Score per Segment, and escaping.
  - The table script, tested at seam 9.
  - The **end-to-end CI test** on all three OSes: `crawl --detach` → `status` → `issues` → `report`.
- **080-add-agent-skill**:
  - **The Skill** (workflows, Hand-off rule, install instructions and one-liners), generated from `spider commands` by a developer script (`scripts/generate_skill.py`).
    - Hand-off rule: when the URL estimate is `null`, the Skill hands the command to the user.
  - `skill install`, and the outdated-Skill notice (never printed by a detached Crawl process).
  - The plugin marketplace. The plugin ships without an MCP config until 090.
  - `doctor`, whose TLS check uses 022's TLS setup.
- **100-add-installers**:
  - `install.sh` and `install.ps1`: pin Python 3.14, run `doctor`, and ask before installing the Skill.
  - **Installer exit codes** are their own: 0 ok, 1 failed, 2 usage, 10 installed but `doctor` failed.
  - The release pipeline verifies that the committed Skill copy matches the generator's output.
  - Documented developer install with `uv tool install` or `pipx`.

### Columns that stay null until they are measured

| Column(s) | Measured from |
|---|---|
| Link Score | v0.2 |
| Closest Near-Duplicate, Near-Duplicate count | v0.3 |
| Structured-data validation errors / warnings | v0.3 |
| Unique JS Inlinks / Outlinks, cookies set by scripts | v1.1 |

## v0.1.1: MCP server

The first change after v0.1, as the maintainer decided on 2026-10-01. It builds on the released v0.1.

| # | Change | Capabilities (specs) | Commands / MCP tools | Status |
|---|---|---|---|---|
| 090 | `090-add-mcp-server` | `mcp-server`; modifies `installation`, `agent-skill` | `mcp` (+ MCP tools) | planned |

- **090-add-mcp-server**:
  - `spider mcp --workspace <path>`.
  - **Tools:** they mirror the Commands, plus `schema`, `rules` and `doctor`, and `report` accepts notes inline.
  - Errors use 010's full diagnostic shape.
  - The `.mcpb` bundle: `scripts/build_mcpb.py`, added to 100's release pipeline, so it is attached to every GitHub release from v0.1.1.
  - The plugin `.mcp.json`, added to 080's plugin, and config snippets.

## v0.2: link graph

- Link graph views: `links <url> --in|--out`.
- Redirect Chain analysis: `redirects`, with per-hop headers and timing.
- Sitemap analysis: `sitemaps` (sitemap vs crawl, non-indexable URLs in the sitemap).
- Link Score.
- Rules that need the whole site: orphan Pages, hreflang return links, sitemap coverage.
- Report Sections for links, redirects and sitemaps.
- `rules apply`, which recomputes Issues from stored data after thresholds change.

## v0.3: comparison and content

- Crawl Diff (`diff A B`) and a diff Report.
- Custom Extraction (CSS, XPath, regex; configured in `spider.toml`).
- Near-Duplicates (our own MinHash) with `duplicates [--exact|--near]`.
- Offline structured-data validation (schema.org plus Google's rules for about 10 types, stored as YAML) with `structured-data`.

## v1.0: stable

- Hardening, full documentation and the full Rule set.
- xlsx export and a white-label Report.
- Homebrew tap, Scoop bucket, and a multi-arch Docker image on GHCR.

## v1.1: JavaScript rendering

- Playwright rendering as the optional `[render]` extra, which fills the JS-only columns.

## Backlog

- **Report formats:** PDF, report translations.
- **Integrations:** Google Search Console (including URL Inspection), GA4, PageSpeed Insights / Core Web Vitals, Ahrefs.
- **New interfaces:** REST API and web UI.
- **More analysis:** RDFa, accessibility, spelling, screenshots, more rich-result types, third-party Rule plugins.
- **Crawl operation:** scheduled or distributed Crawls.
- **Distribution:** signed standalone binaries and winget.
