# Roadmap

> **Working name:** `spider`. That covers the command, the Python package, `spider.toml` and the `.spider/` Workspace folder. The product name is still open and must be chosen, and checked as free on PyPI and GitHub, before the first release.

Terms follow [CONTEXT.md](CONTEXT.md). How the pieces fit together is in [docs/architecture.md](docs/architecture.md), the decisions behind them are in [docs/adr/](docs/adr/), and how everything is tested is in [docs/testing.md](docs/testing.md).

Each milestone ships as a set of OpenSpec changes in `openspec/changes/`. Change numbers name the changes; the build order below says when each one starts.

**Scope cut (2026-10-05).** v0.1 is cut to the core path: crawl a site, store it, and ask it for Issues. Several changes ship only their minimum in v0.1 (marked *min*), and the rest of them moves to v0.2. The specs stay as written. The `design.md` and `tasks.md` of 015 and later are drafts: each is re-grounded against the code with `/opsx:update` just before its change starts, and that is also when the deferred requirements leave its specs.

## v0.1: first public pre-release

| # | Change | Capabilities (specs) | Commands | Status |
|---|---|---|---|---|
| 000 | `000-scaffold-project` | none (tooling only) | `spider --version` | done |
| 010 | `010-add-workspace-and-cli-contract` | `workspace`, `cli-contract` | `init`, `commands` | in progress |
| 015 | `015-add-crawl-store` | `crawl-store` | `schema`; `--crawl` | planned |
| 020 | `020-add-crawl-core` | `crawling` | `crawl <url>` (foreground) | planned |
| 022 | `022-add-fetch-policy` | `fetching` | `crawl` fetch flags | planned, min |
| 030 | `030-add-page-data` | `page-data` | none (data only) | planned, min |
| 040 | `040-add-rules` | `rules` | `rules` | planned, 15 Rules |
| 050 | `050-add-query-and-segments` | `querying` | `summary`, `pages`, `page`, `issues` | planned, min |
| 080 | `080-add-agent-skill` | `agent-skill`, `diagnostics` | `skill install`, `doctor` | planned, min |
| 085 | `085-add-release` | decided when it is drafted | none (release workflow) | planned, not drafted yet |

v0.1 is installed from PyPI, where 085 publishes it, with `uv tool install` (or `pipx`). The install scripts come with 100 in v0.2.

### Build order

A thin end-to-end slice comes first, so the first Issues reach a user early. The changes then widen.

```
slice:   000 ─► 010 ─► 015 ─► 020 ─► 030-min ─► 040-min ─► 050 issues
                                │    (first      (3–5       (issues,
                                │    columns)    Rules)     issues <id>)
                                │
widen:                          ├─► 022-min ─┐
                                └────────────┴─► rest of 030-min ─► 040 (15 Rules) ─► 050 summary/pages/page ─► 080 ─► 085 ─► v0.1 tag
```

- **The slice:** 015 → 020 → 030-min → 040-min → 050-issues. 030 starts with only the columns its first Rules read, 040 with 3–5 Rules that need no redirects (for example `internal-4xx`, `internal-5xx`, `internal-no-response`, `title-missing`, `h1-missing`), and 050 with `issues` and `issues <rule-id>`. The slice ends with a cross-OS end-to-end CI test: a foreground `crawl` → `issues` on Windows, macOS and Linux. How 030, 040 and 050 split into slice and widening task groups is settled when 030 is re-grounded.
- **Widening:** 022-min can start as soon as 020 is in, in its own worktree, alongside the slice. The rest of 030-min, 040 up to its 15 Rules, and 050's `summary`, `pages` and `page` follow. 080 comes after them, because the Skill is generated from the finished Commands, columns and Rules.
- **Release:** 085 comes last, before the v0.1 tag. The product name must be chosen, and checked as free on PyPI and GitHub, before 085 starts.
- **v0.1.1** comes after the v0.1 release: 060-min first, then 090. The v0.2 changes come after that.

### The v0.1 Rules

040 ships these 15 Rules in v0.1. The other 27 Rules of its catalogue move to v0.2.

| Category | Rules |
|---|---|
| `response_codes` | `internal-4xx`, `internal-5xx`, `internal-no-response`, `internal-3xx`, `redirect-chain`, `redirect-loop`, `internal-blocked-by-robots-txt` |
| `security` | `http-url` (a Warning with High Priority) |
| `titles` | `title-missing`, `title-duplicate`, `title-too-long` (characters only, since pixel widths are v0.2) |
| `meta_descriptions` | `meta-description-missing` |
| `headings` | `h1-missing` |
| `directives` | `noindex` |
| `canonicals` | `canonical-to-non-indexable` |

### What each change owns

If a change needs something another change owns, it depends on that change instead of redefining it. Parts marked **(v0.1.1)** or **(v0.2)** are deferred by the 2026-10-05 scope cut. The changes that move to v0.2 as a whole are marked on their own line, and what they own is unchanged.

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
  - Parsing runs in-process.
- **022-add-fetch-policy** (min in v0.1):
  - Timeouts, retries with backoff, and redirects followed hop by hop, with every hop recorded.
  - Limits: `--max-redirects`, loop detection, body and URL caps.
  - `--user-agent`.
  - Compression: gzip, deflate and br. **(v0.2)** zstd.
  - **TLS trust:** truststore with a certifi fallback, including a speed test.
  - Status and size checks for Resources.
  - The `response_headers` table, where cookie values are always stored as `***`. No cookies are sent.
  - The standard proxy variables `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` are honoured (010's one exception to its no-environment-variables rule), with proxy passwords redacted.
  - HTTPS, virtual hosts and gzip on the fixture site (trustme).
  - **(v0.2)** HTTP version per origin via ALPN (`http_1_1` / `http_2`), the `--proxy` flag (and `[crawl] proxy`), basic auth and custom headers.
- **024-add-list-and-sitemap-modes** (v0.2):
  - List mode (`--list <file|->`) and Sitemap mode (`--sitemap <url>`, repeatable, with index files and gzip).
  - `mode_conflict` when two Crawl Modes are given.
- **026-add-parse-pool** (v0.2, conditional):
  - First, the ~500k-URL benchmark against 020's in-process parsing, run manually or nightly and not part of the CI gate. Its numbers go in `docs/benchmarks.md`.
  - The maintainer then decides. Only if parsing is the bottleneck: parsing in a process pool, with bounded queues, clean shutdown of workers on interrupt, and no console windows on Windows. Otherwise 026 is archived with the benchmark alone.
- **030-add-page-data** (min in v0.1):
  - Every Internal-tab column, added in the slice where it is first needed.
  - Indexability and Indexability Status.
  - Link attributes stored for analysis (building on 020's discovered Links and Link types).
  - Inlink and outlink counts, computed in the post-crawl passes.
  - The Content Area and content metrics, and the Exact Duplicate hash.
  - Structured-data item counts, and cookie names without their values.
  - **(v0.2)** Flesch Reading Ease and the Readability band, language detection (`--detect-language`, py3langid), SERP pixel widths, and **raw HTML storage** (zstd; automatic when the Crawl's `--max-urls` is at most 50,000; `--store-html/--no-store-html`).
- **040-add-rules** (15 Rules in v0.1):
  - The Rule model and the 15 Rules listed above; `http-url` is a Warning with High Priority. **(v0.2)** the other 27 Rules of the 42-Rule catalogue.
  - Thresholds and disabling in `spider.toml`.
  - Evaluation per URL (through the per-response hook) and in the post-crawl passes.
  - Issues and Affected URLs, including `issues.affected_count`.
  - The Health Score.
  - `spider rules [list|show <id>]` and `rule_not_found` (exit 4).
- **050-add-query-and-segments** (min in v0.1):
  - `summary` (the data model shared with the Report). **(v0.2)** its per-Segment breakdown.
  - `pages` with the basic `--where` language (comparisons, `contains`, `is [not] null` and `and`), `--fields`, `--sort` and paging. **(v0.2)** the rest of `--where`: `~`/`!~`, `in`, `or`, `not` and parentheses.
  - `page <url>`: JSON, where `--headers` shows redacted headers. **(v0.2)** `--html`, which needs 030's stored HTML.
  - `issues` and `issues <rule-id>`.
  - The **end-to-end CI test** on Windows, macOS and Linux: a foreground `crawl` → `issues`. It is the last part of the thin slice. 070's end-to-end test is added in v0.2.
  - **(v0.2)** Read-only `sql`.
  - **(v0.2)** `export <view>`: `jsonl` by default, or `csv`; the `resources` view is defined over `urls` and `links`.
  - **(v0.2)** **Segments** and `--segment`.
  - **(v0.2)** **The CSV policy and output files**, for every Command (moved from 010 on 2026-10-01):
    - the `csv` format; the single **CSV policy** is UTF-8 with BOM, CRLF and formula neutralisation, with `--no-bom` to turn the BOM off
    - `-o <file>` writes exactly the stdout bytes, atomically, and leaves stdout empty (`output_written`, `output_not_writable`)
- **060-add-crawl-control** (min in v0.1.1, rest in v0.2):
  - **(v0.1.1)** `crawl --detach` in Spider mode: on Windows it uses CREATE_NO_WINDOW.
  - **(v0.1.1)** `status`, which detects a dead process.
  - **(v0.1.1)** `stop` (`--wait`).
  - **(v0.1.1)** The recorded runs and control requests behind them, and the command recorded for Crawls started through MCP.
  - **(v0.2)** Detached List mode, where the parent stores the Seeds before spawning the Crawl.
  - **(v0.2)** `resume`. Resume works for `stopped`, `interrupted` and `failed` Crawls, asks again for secrets, and accepts a higher `--max-urls`.
  - **(v0.2)** `crawl --dry-run`: the checked config, the equivalent command, and a URL estimate that may be `null`.
  - **(v0.2)** `crawls list|show|rm`, where `rm` also deletes that Crawl's reports and notes.
- **070-add-html-report** (v0.2):
  - `report`: a self-contained offline HTML file plus CSV files. It is written to `--dest <dir>` (default `.spider/reports/<crawl-id>/`), and a JSON receipt goes to stdout.
  - Report Sections, and `report brief --section <id>` / `--list`.
  - Report Notes, SVG charts, Health Score per Segment, and escaping.
  - The table script, tested at seam 9.
  - The **end-to-end CI test** on all three OSes: `crawl --detach` → `status` → `issues` → `report`.
- **080-add-agent-skill** (min in v0.1):
  - **The Skill** (workflows, install instructions and one-liners), generated from `spider commands` by a developer script (`scripts/generate_skill.py`). In v0.1 the one-liner is `uv tool install`, and the workflows use only v0.1 Commands.
  - `skill install`, and the outdated-Skill notice.
  - The large-Crawl guardrail in v0.1: the Skill always passes `--max-urls` (decided when 080 is re-grounded).
  - `doctor`, whose TLS check uses 022's TLS setup.
  - **(v0.2)** the Full audit workflow (it needs 070's `report brief`); the dry run and the Hand-off rule (when the URL estimate is `null`, the Skill hands the command to the user), which need 060; the install-script one-liners (100); `sql` recipes and Segments; `doctor --proxy`; and the plugin marketplace, which ships with 090's `.mcp.json`.
- **085-add-release** (v0.1; not drafted yet, so `openspec/changes/085-*` does not exist):
  - Before it starts: the product name is chosen and checked as free on PyPI and GitHub.
  - A GitHub Actions workflow triggered by `v*` tags: the test suite, the sdist and wheel built with `uv build`, publishing to PyPI through trusted publishing, and a GitHub release with them.
  - The release gates: the tag matches the package version, and the committed Skill copy matches the generator's output (moved from 100).
  - The documented install with `uv tool install` or `pipx` (moved from 100).
  - An install smoke check instead of a pin test: on Windows, macOS and Linux, the workflow installs the built wheel with uv on the Python version from `.python-version` (3.14), then runs `spider --version` and `spider doctor`.
  - **(v0.1.1)** The `.mcpb` bundle that 090 builds, attached to every GitHub release.
- **100-add-installers** (v0.2):
  - `install.sh` and `install.ps1`: pin Python 3.14, run `doctor`, and ask before installing the Skill. They are attached to 085's GitHub release.
  - **Installer exit codes** are their own: 0 ok, 1 failed, 2 usage, 10 installed but `doctor` failed.

### Columns that stay null until they are measured

| Column(s) | Measured from |
|---|---|
| Link Score | v0.2 |
| Closest Near-Duplicate, Near-Duplicate count | v0.3 |
| Structured-data validation errors / warnings | v0.3 |
| Unique JS Inlinks / Outlinks, cookies set by scripts | v1.1 |

## v0.1.1: background Crawls and the MCP server

The first release after v0.1. MCP was moved here on 2026-10-01, and 060-min joined it on 2026-10-05, because MCP needs background Crawls. It builds on the released v0.1.

| # | Change | Capabilities (specs) | Commands / MCP tools | Status |
|---|---|---|---|---|
| 060 | `060-add-crawl-control` | `crawl-control` | `crawl --detach` (Spider mode), `status`, `stop` | planned, min |
| 090 | `090-add-mcp-server` | `mcp-server`; modifies `agent-skill` and 085's release capability | `mcp` (+ MCP tools) | planned |

- **Order:** 060-min, then 090.
- **060-min** is `crawl --detach`, `status` (with dead-process detection) and `stop` (`--wait`), for Spider mode only. `resume`, `crawl --dry-run`, `crawls list|show|rm` and detached List mode stay in v0.2.

- **090-add-mcp-server**:
  - `spider mcp --workspace <path>`.
  - **Tools:** the foreground and the detached crawl, `status` and `stop`, and the v0.1 queries `summary`, `pages`, `page`, `issues` and `rules`, plus `schema` and `doctor`.
  - **(v0.2)** the tools of the v0.2 Commands: `resume`, the dry run, `crawls list`, `sql`, List and Sitemap modes, and the `report` and `report_brief` tools with inline Report Notes, which come with 070.
  - Errors use 010's full diagnostic shape.
  - The `.mcpb` bundle: `scripts/build_mcpb.py`, added to 085's release workflow, so it is attached to every GitHub release from v0.1.1.
  - A `.mcp.json` example and the client config snippets, shipped as docs in `docs/mcp.md`.
  - **(v0.2)** The plugin `.mcp.json`, which comes with 080's plugin marketplace.

## v0.2: crawl control, reports, link graph

The changes deferred by the 2026-10-05 scope cut come first, then the link-graph work.

| # | Change | Capabilities (specs) | Commands | Status |
|---|---|---|---|---|
| 024 | `024-add-list-and-sitemap-modes` | `crawl-modes` | `crawl --list`, `crawl --sitemap` | planned |
| 026 | `026-add-parse-pool` | `crawl-performance` (only if the pool goes ahead) | none | planned, conditional on its benchmark |
| 060 | `060-add-crawl-control` | `crawl-control` | `crawl --dry-run`, `resume`, `crawls`, detached List mode | planned, rest after v0.1.1 |
| 070 | `070-add-html-report` | `reporting` | `report`, `report brief` | planned |
| 100 | `100-add-installers` | `installation` | none (install scripts) | planned |

- **The rest of the v0.1 and v0.1.1 changes,** marked **(v0.2)** under "What each change owns": the rest of 060; 090's tools for the v0.2 Commands; 022's ALPN, `--proxy`, auth and custom headers; 030's readability, language, pixel widths and HTML storage; 040's other 27 Rules; 050's `sql`, `export`, Segments, the full `--where`, the `csv` format, `--no-bom` and `-o`; 080's Full audit, dry run and Hand-off, install-script one-liners and plugin marketplace.
- **Order:** 024 and 026 first (026's benchmark decides whether its pool is built). The rest of 060 needs 022 and 024 (List mode, and the sitemap reader for the dry-run estimate). 070 needs 050's `export` and CSV writer, and 060 for its end-to-end test. 100 comes last.
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
