# Roadmap

> **Working name:** `spider`. That covers the command, the Python package, `spider.toml` and the `.spider/` Workspace folder. The product name is still open and must be chosen, and checked as free on PyPI and GitHub, before the first release.

Terms follow [CONTEXT.md](CONTEXT.md). How the pieces fit together is in [docs/architecture.md](docs/architecture.md), the decisions behind them are in [docs/adr/](docs/adr/), and how everything is tested is in [docs/testing.md](docs/testing.md).

Each milestone ships as a set of OpenSpec changes in `openspec/changes/`. Change numbers name the changes; the build order below says when each one starts.

**Scope cut (2026-10-05).** v0.1 is cut to the core path: crawl a site, store it, and ask it for Issues. Several changes ship only their minimum in v0.1 (marked *min*), and the rest of them moves to v0.2. The specs stay as written. The `design.md` and `tasks.md` of 015 and later are drafts: each is re-grounded against the code with `/opsx:update` just before its change starts, and that is also when the deferred requirements leave its specs.

**060-min joins v0.1 (2026-10-05).** An agent runs Commands through its shell tool, which times out after minutes, so a foreground Crawl caps what an agent can crawl. With `crawl --detach`, `status` and `stop` in v0.1, an agent crawls a large site in the background and queries the crawl file while the Crawl is still writing.

**Large sites first (2026-10-05).** The product bets on full crawls of large sites (see Positioning), so three more things join v0.1: 060's `resume`, no default `--max-urls` limit, and 026's ~500k-URL benchmark. Hostile sites wait until after the v0.1 release: anti-bot and WAF challenges, adaptive throttling. The first users' sites are friendly to crawl. The standard proxy variables stay in v0.1 (022-min): corporate networks need them, and 010's `spider commands` already lists them under `environment`.

**Robustness rule (2026-10-05), for every change from 020 on.** On a 500k-URL Crawl every rare failure happens, so:
- **One URL never stops the Crawl.** A failure in fetching, decoding, parsing, extraction or Rule evaluation becomes that URL's recorded outcome (`fetch_state`, its error kind, `parse_error`) plus a counted warning, and the Crawl moves on. Only failures of the whole Crawl stop it, each with a `stop_reason`, and leave it resumable: an unreachable Seed, a crawl file that cannot be written (disk full included), and the zero-success breaker.
- **Parsing never trusts its input.** Every extractor gets property-based tests (hypothesis) over arbitrary bytes and malformed HTML. It returns Page data or a `parse_error`, and never raises.
- **Hostile fixtures, grown by each change** on the fixture site: stalled and trickling bodies, missing or broken `Content-Encoding`, wrong or invalid charsets, a gzip bomb, huge pages, deeply nested HTML, connection resets, redirect loops, and 429 and 503 responses.
- **026's benchmark is also a soak test.** Its synthetic site injects a share of those faults, and a run passes only if it ends with no crash, flat memory, and every URL accounted for in `urls`.

## Positioning

Other tools already ship a crawler with a CLI, an MCP server and a Skill. This one stands on four things:
- **Built for large sites:** a full crawl of every URL in Scope, never a sample, at the scale target of about 500k URLs. Checking 50 pages is a commodity; a complete crawl of a large site, run in the background for hours and queried while it runs, is the job. The frontier lives in the crawl file, so memory stays flat and a Crawl can stop and continue.
- **Your crawl is a database:** each Crawl is a SQLite file with a public, versioned, documented schema ([ADR-0002](docs/adr/0002-sqlite-crawl-store-public-schema.md)) and read-only `spider sql`, which works while a background Crawl is still writing. Every Issue can be reproduced by a query.
- **A contract-tested CLI for agents:** one JSON result per Command, a registry of diagnostics and error codes, and cursor paging.
- **No telemetry, no account, no LLM calls** ([ADR-0004](docs/adr/0004-tool-never-calls-an-llm.md)).

We deliberately do not claim these as unique: the MCP server, the Skill, the CI gate, Crawl Diff, the Health Score and `llms.txt` checks.

## v0.1: first public pre-release

| # | Change | Capabilities (specs) | Commands | Status |
|---|---|---|---|---|
| 000 | `000-scaffold-project` | none (tooling only) | `spider --version` | done |
| 010 | `010-add-workspace-and-cli-contract` | `workspace`, `cli-contract` | `init`, `commands` | done |
| 015 | `015-add-crawl-store` | `crawl-store` | `schema`; `--crawl` | done |
| 017 | `017-speed-up-crawl-writer` | `crawl-store` (modified) | none | planned |
| 020 | `020-add-crawl-core` | `crawling` | `crawl <url>` (foreground) | planned |
| 022 | `022-add-fetch-policy` | `fetching` | `crawl` fetch flags | planned, min |
| 030 | `030-add-page-data` | `page-data` | none (data only) | planned, min |
| 040 | `040-add-rules` | `rules` | `rules` | planned, 15 Rules |
| 050 | `050-add-query-and-segments` | `querying` | `summary`, `pages`, `page`, `issues`, `sql` | planned, min |
| 026 | `026-add-parse-pool` | `crawl-performance` | none | planned: the parse pool and its benchmark |
| 060 | `060-add-crawl-control` | `crawl-control` | `crawl --detach` (Spider mode), `status`, `stop`, `resume` | planned, min |
| 080 | `080-add-agent-skill` | `agent-skill`, `diagnostics` | `skill install`, `doctor` | planned, min |
| 085 | `085-add-release` | decided when it is drafted | none (release workflow) | planned, not drafted yet |

v0.1 is installed from PyPI, where 085 publishes it, with `uv tool install` (or `pipx`). The install scripts come with 100 in v0.2.

### Build order

A thin end-to-end slice comes first, so the first Issues reach a user early. The changes then widen.

```
slice:   000 ─► 010 ─► 015 ─► 017 ─► 020 ─► 030-min ─► 040-min ─► 050 issues
                                       │    (first      (3–5       (issues,
                                       │    columns)    Rules)     issues <id>)
                                       │
widen:                                 ├─► 022-min ─┐
                                       ├─► 060-min ─┤
                                       ├─► 026 parse pool, synthetic site, benchmark baseline (before the slice's e2e test) ─────┐
                                       └────────────┴─► rest of 030-min ─► 040 (15 Rules) ─► 050 sql, summary/pages/page ─► 080 ─┴─► 026 benchmark re-run (sizes the pool) ─► 085 ─► v0.1 tag
```

- **The slice:** 015 → 017 → 020 → 030-min → 040-min → 050-issues. 017 speeds up 015's writer before 020 writes through it. 030 starts with only the columns its first Rules read, 040 with 3–5 Rules that need no redirects (for example `internal-4xx`, `internal-5xx`, `internal-no-response`, `title-missing`, `h1-missing`), and 050 with `issues` and `issues <rule-id>`. The slice ends with a cross-OS end-to-end CI test: a foreground `crawl` → `issues` on Windows, macOS and Linux. How 030, 040 and 050 split into slice and widening task groups is settled when 030 is re-grounded.
- **Widening:** 022-min and 060-min can each start as soon as 020 is in, in their own worktrees, alongside the slice. 060-min needs only 015 and 020, and must land before 080, whose workflows start Crawls detached. The rest of 030-min, 040 up to its 15 Rules, and the rest of 050 follow. 050's `sql` can land right after `issues`, before `summary`, `pages` and `page`. 080 comes after them, because the Skill is generated from the finished Commands, columns and Rules.
- **Scale proof:** 026, the parse pool with its synthetic site and benchmark script, starts once 020's slice is in and lands before the slice's end-to-end test; its first run is the baseline. The benchmark is re-run on the full v0.1 pipeline after 080, before 085, to size the pool, and its numbers go in `docs/benchmarks.md`.
- **Release:** 085 comes last, before the v0.1 tag. The product name must be chosen, and checked as free on PyPI and GitHub, before 085 starts.
- **v0.1.1** comes after the v0.1 release: 090. The v0.2 changes come after that.

### The v0.1 Rules

040 ships these 15 Rules in v0.1, each with a reproducing SQL query over the public schema. The other 27 Rules of its catalogue move to v0.2.

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
  - One SQLite file per Crawl, and crawl ids.
  - The `crawl` and `seeds` tables. Counts are derived from tables, never stored on `crawl`.
  - The transactional writer: units of work mixing inserts, updates and reads, flushed in batches. A crash loses at most the unflushed batch. Opening it runs a rolled-back write check (`crawl_not_writable`).
  - WAL with `synchronous=NORMAL`, a rollback journal on UNC paths, and a `store.journal_mode` override. **(v0.2)** network-drive detection from the mount table.
  - Read-only access that releases the file after each operation, and `crawl_schema_too_new` for files from a newer tool.
  - Schema versioning. No migrations before v0.1; the first schema change after v0.1 brings them, with a migration test from every published schema version.
  - `spider schema [TABLE]`, with table order fixed by change number.
  - The `--crawl latest|<id>|<path>` option used by every query Command.
  - Redaction of secrets in recorded commands and config: whole values (`***`) and URL passwords (`user:***@proxy`). 022 adds the header shape (`Cookie: ***`) in v0.2.
  - Table conventions, and `docs/schema.md` as the contract: the public schema reference of [ADR-0002](docs/adr/0002-sqlite-crawl-store-public-schema.md), in v0.1. It is checked against the declared schema, and a new crawl file against both through `PRAGMA table_info`.
- **017-speed-up-crawl-writer** (v0.1, decided 2026-10-11 from the writer prototype; the store layer only):
  - It modifies `crawl-store` and builds on 015's `CrawlWriter` as built. It comes after 015 and before 020, whose per-URL unit uses it.
  - **The writer stays a thread.** A writer process is out: it tied the thread under the parse pool (40.1 against 40.4 Pages/s) and writer-only at ~466 Link rows per Page (17.6 against 17.2), its WAL peaked at 402 MB against 212 MB, and it would need units as records with a registry, errors sent over a pipe and a slow test group.
  - **`run()` and `run_async()` are unchanged:** their result means the unit ran, and `flush()` means it is durable.
  - **`submit(unit)` is new:** it returns a Future that is resolved at the commit that holds the unit, and fails when that commit fails. A window of unresolved units gives backpressure. Units stay closures (`Callable[[Connection], T]`), with no registry; 020 D14's row records stay 020's rule.
  - **Reads through the writer** run in its open transaction and commit nothing, so 020's frontier reads see every unit before them.
  - **The optimistic batch,** internal to the writer: the units of a batch run without a savepoint each. When one fails, the transaction is rolled back, the units before it run again with a savepoint each and are committed at once (the replay commit, a new commit trigger in the spec), and the failing unit never runs again, a `BaseException` included. Unit atomicity is tested with a unit that fails half-way. It gained 14–15% on the clean path in back-to-back runs: 52.8 → 60.9 Pages/s at 120 Link rows per Page, 15.8 → 18.0 at ~466. Since a unit may run twice, a unit has no effect outside its connection.
  - **The writer's connection pragmas,** with no new setting: `temp_store=MEMORY`, a 64 MB `cache_size` and, in WAL mode, a 256 MB `mmap_size` (−33% wall time together in the store benchmark at 2k Pages). The killed-writer proof is re-run on Windows with `mmap_size` on.
  - **Prebuilt statements** are a rule for every store module: built once and run as `execute(stmt, params)`, never `.values(<literals>)` per unit and never `insert().values(list)`. Its design decides whether a guard test enforces it.
  - **A local throughput check,** never part of the CI gate: writer-only, 20k Pages at ~466 Link rows per Page, at least 12 Pages/s, a WAL peak of at most 300 MB and a crawler RSS of at most 400 MB. It is provisional until the schema blueprint's links layout lands.
  - Not in 017: the partial frontier index (020), the parse pool (026), and the pipes between a Crawl's processes (060). A writer process, if one is ever added, starts through a dedicated entry module whose imports a startup-allowlist-style test checks.
- **020-add-crawl-core**:
  - Spider mode (`crawl <url>`) and URL normalisation, which keeps the trailing slash.
  - **Scope:** `--scope host|subdomains|subfolder`, `--subdomains`, `--include/--exclude`, `--max-depth`, `--max-urls` (no limit by default; reaching an explicit limit leaves the Crawl resumable), `--strip-params`. An apex Seed admits its `www.` host, never the reverse, and `seed_base_mismatch` warns when a `www.` Seed's site lives on the apex.
  - **Section Crawl**, and robots.txt (obeyed by default, `--ignore-robots`, `--robots-user-agent`).
  - **The robots directives parser** (meta robots and X-Robots-Tag, used by 030 as well).
  - Politeness (`--concurrency`, `--rate`).
  - The frontier: the `urls` table, deduplicated by its unique URL with no in-memory URL map, dispatched depth by depth in `urls.id` order.
  - **Link discovery and the Link type table**, with `--follow-nofollow` and `--check-external`.
  - Crawl Depth.
  - **Hooks:** a per-response hook for every recorded URL, whose handlers return rows that the store writes in the URL's unit, and the **post-crawl passes** hook, which runs for `completed` or `stopped` Crawls and is safe to re-run.
  - **Design points of 2026-10-05:** guarded Crawl State transitions (one table and check; 060 adds `interrupted`), a `NormalizedUrl` type, writer units defined only in `spider.store.*`, and one Crawl context object.
  - The `[crawl]` settings table, which 022 and 030 extend.
  - Progress events and the result.
  - **Ctrl+C:** the Crawl becomes `stopped` with `stop_reason: interrupt`, and the command exits 130.
  - **Unreachable Seed:** the Crawl becomes `failed` and resumable, and the command exits 8.
  - **Robustness and backstops:** one URL never stops the Crawl (counted `parse_failed` and `handler_failed` warnings), parsers tested with hypothesis, hostile fixtures, a lost site (`site_unreachable`, exit 8, resumable), a per-request watchdog, and a stop that waits 10 seconds and then cancels.
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
- **026-add-parse-pool** (v0.1: the pool and its benchmark):
  - **The parse pool is unconditional in v0.1** (decided 2026-10-11): page preparation runs in a process pool behind 020's executor seam, with bounded queues, clean shutdown of workers on stop and interrupt, and no console windows on Windows. It is built right after 020's slice and lands before the slice's end-to-end test.
  - The pool starts at the number of physical cores minus 2, so the writer keeps a full core: in the writer prototype, 6 workers on 8 physical cores cut the Crawl to about 40 Pages/s by taking CPU from the writer. The ~500k-URL benchmark then sizes the pool (pool size, queue bounds) and doubles as the soak test. It runs manually or nightly, never as part of the CI gate, and its numbers go in `docs/benchmarks.md`.
  - It also measures the crawl-file layout variants that the store benchmark of 2026-10-10 left out (decided 2026-10-11): `links` as a `WITHOUT ROWID` table, a 16 KB page size, a zstd dictionary for stored HTML, and the WAL size of a ~100k-Page run without a concurrent reader.
- **030-add-page-data** (min in v0.1):
  - Every Internal-tab column, added in the slice where it is first needed.
  - Indexability and Indexability Status.
  - Link attributes stored for analysis (building on 020's discovered Links and Link types).
  - Inlink and outlink counts, computed in the post-crawl passes.
  - The Content Area and content metrics, and the Exact Duplicate hash.
  - Structured-data item counts, and cookie names without their values.
  - **(v0.2)** Flesch Reading Ease and the Readability band, language detection (`--detect-language`, py3langid), SERP pixel widths, and **raw HTML storage** (zstd). HTML is not stored by default; storing it is opt-in by a flag, whose name is decided when 030 is re-grounded (decided 2026-10-11: in the store benchmark, HTML was about 70% of the crawl file).
- **040-add-rules** (15 Rules in v0.1):
  - The Rule model and the 15 Rules listed above; `http-url` is a Warning with High Priority. **(v0.2)** the other 27 Rules of the 42-Rule catalogue.
  - Thresholds and disabling in `spider.toml`.
  - Evaluation per URL (through the per-response hook) and in the post-crawl passes.
  - **Every Rule ships a reproducing SQL query** over the public schema, the foundation of v0.3's User SQL Rules:
    - post-crawl Rules are evaluated by that query
    - per-URL Rules may still be evaluated in Python during the Crawl, but a test checks, for each of them, that the Python result equals its SQL query over the stored Crawl
    - `rules show <id>` prints the query, and an Issue can point to it ("reproduce with `spider sql`")
  - Issues and Affected URLs, including `issues.affected_count`.
  - The Health Score.
  - `spider rules [list|show <id>]` and `rule_not_found` (exit 4).
  - **(v0.2)** A new Rule category `ai_search`, for AI-search readiness. The exact Rule set is decided when it is drafted. Candidates:
    - AI crawlers blocked in robots.txt (GPTBot, ClaudeBot, PerplexityBot, Google-Extended, CCBot and others; the list is kept as data)
    - `/llms.txt` missing or invalid
    - main content missing from the raw HTML, approximated from the Word Count until JavaScript rendering arrives in v1.1
    - no structured data on Indexable Pages
- **050-add-query-and-segments** (min in v0.1):
  - `summary` (the data model shared with the Report). **(v0.2)** its per-Segment breakdown.
  - `pages` with the basic `--where` language (comparisons, `contains`, `is [not] null` and `and`), `--fields`, `--sort` and paging. **(v0.2)** the rest of `--where`: `~`/`!~`, `in`, `or`, `not` and parentheses.
  - `page <url>`: JSON, where `--headers` shows redacted headers. **(v0.2)** `--html`, which needs 030's stored HTML.
  - `issues` and `issues <rule-id>`.
  - The **end-to-end CI test** on Windows, macOS and Linux: a foreground `crawl` → `issues`. It is the last part of the thin slice. 070's end-to-end test is added in v0.2.
  - Read-only `sql`: exactly one `SELECT`/`WITH` statement, with a default row limit and a timeout.
  - **(v0.2)** `export <view>`: `jsonl` by default, or `csv`; the `resources` view is defined over `urls` and `links`.
  - **(v0.2)** **Segments** and `--segment`.
  - **(v0.2)** **The CSV policy and output files**, for every Command (moved from 010 on 2026-10-01):
    - the `csv` format; the single **CSV policy** is UTF-8 with BOM, CRLF and formula neutralisation, with `--no-bom` to turn the BOM off
    - `-o <file>` writes exactly the stdout bytes, atomically, and leaves stdout empty (`output_written`, `output_not_writable`)
- **060-add-crawl-control** (min and `resume` in v0.1, rest in v0.2):
  - `crawl --detach` in Spider mode: on Windows it uses CREATE_NO_WINDOW.
  - `status`, which detects a dead process.
  - `stop` (`--wait`).
  - The recorded runs and control requests behind them. **(v0.1.1)** The command recorded for Crawls started through MCP.
  - The **end-to-end CI test** on Windows, macOS and Linux: `crawl --detach` → `status` → `issues`, with a `sql` query while the Crawl is still running, then `stop`.
  - Moved from 015 on 2026-10-05: the writer claim (`crawl_locked`) and liveness, recording a dead Crawl `interrupted`, control writes by processes without the claim, and reserved crawl ids (`<id>.log`, `crawl_id_taken`).
  - **(v0.2)** Detached List mode, where the parent stores the Seeds before spawning the Crawl.
  - `resume`. Resume works for `stopped`, `interrupted` and `failed` Crawls, asks again for secrets, and accepts a higher `--max-urls`.
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
  - Large Crawls in v0.1: the Skill starts a Crawl with `crawl --detach`, follows it with `status`, queries it with `issues` and `sql` while it runs, ends it with `stop`, and continues an interrupted one with `resume`. Whether it also passes `--max-urls` is decided when 080 is re-grounded.
  - `doctor`, whose TLS check uses 022's TLS setup.
  - An **SQL cookbook** in the Skill: `sql` recipes over the public schema. **(v0.2)** Segment recipes.
  - **(v0.2)** the Full audit workflow (it needs 070's `report brief`); the dry run and the Hand-off rule (when the URL estimate is `null`, the Skill hands the command to the user), which need 060; the install-script one-liners (100); Segments and their recipes; `doctor --proxy`; and the plugin marketplace, which ships with 090's `.mcp.json`.
  - **(v0.2)** The **fix and verify** workflow: the agent reads the Issues, fixes the site's code in the repository, re-crawls only the Affected URLs in List mode, and confirms that the Issue is gone. It depends on 024 and on `rules apply`.
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
- **110-add-ci-gate** (v0.2; not drafted yet): SEO regression testing in CI, "SEO checks that block a bad deploy, the way tests do".
  - Crawl Diff (`diff A B`), pulled forward from v0.3. The diff Report stays in v0.3.
  - `--fail-on <issue|warning|opportunity>`: a non-zero exit when the new Crawl has new Issues of that Issue Type or a more severe one, compared with a baseline Crawl. The exit code is decided when 110 is drafted.
  - CI output formats besides the exit code: SARIF and JUnit.
  - A composite GitHub Action: install spider, crawl a staging site or localhost, diff against a baseline crawl file kept as a CI artifact, and fail the job.
  - Depends on 024 (List mode, to re-crawl a URL list) and on 040's Issues.

### Columns that stay null until they are measured

| Column(s) | Measured from |
|---|---|
| Link Score | v0.2 |
| Closest Near-Duplicate, Near-Duplicate count | v0.3 |
| Structured-data validation errors / warnings | v0.3 |
| Unique JS Inlinks / Outlinks, cookies set by scripts | v1.1 |

## v0.1.1: the MCP server

The first release after v0.1. MCP was moved here on 2026-10-01. It builds on the released v0.1, including 060-min's background Crawls, which MCP needs.

| # | Change | Capabilities (specs) | Commands / MCP tools | Status |
|---|---|---|---|---|
| 090 | `090-add-mcp-server` | `mcp-server`; modifies `agent-skill` and 085's release capability | `mcp` (+ MCP tools) | planned |

- **090-add-mcp-server**:
  - `spider mcp --workspace <path>`.
  - **Tools:** the foreground and the detached crawl, `status` and `stop`, and the v0.1 queries `summary`, `pages`, `page`, `issues`, `sql` and `rules`, plus `schema` and `doctor`.
  - `resume`. **(v0.2)** the tools of the v0.2 Commands: the dry run, `crawls list`, List and Sitemap modes, and the `report` and `report_brief` tools with inline Report Notes, which come with 070.
  - Errors use 010's full diagnostic shape.
  - The `.mcpb` bundle: `scripts/build_mcpb.py`, added to 085's release workflow, so it is attached to every GitHub release from v0.1.1.
  - A `.mcp.json` example and the client config snippets, shipped as docs in `docs/mcp.md`.
  - **(v0.2)** The plugin `.mcp.json`, which comes with 080's plugin marketplace.
- **Distribution in v0.1.1:**
  - List the MCP server on the MCP Registry, under the chosen product name.
  - Offer the CLI as a deterministic crawler backend for popular SEO skill packs.

**Re-grounding checklist** (what to fix or design when each change is re-grounded):
- 090: `design.md` lines 14, 99 and 127, `specs/installation/` and `tasks.md` still name 100's `release.yml`, its pin test and 080's plugin; they move to 085's release workflow and to `docs/mcp.md`.
- 080: `design.md:95` and task 7.8 still name 100's release pipeline for the Skill-copy check, which is now 085's.
- 060: re-ground for v0.1. Its proposal and the release notes in `specs/crawl-control/spec.md` still say v0.1.1 for 060-min; they become v0.1, except the command recorded for Crawls started through MCP (v0.1.1). It may not assume 022: 060-min needs only 015 and 020.
- 015 (done at its archive, 2026-10-10): its `design.md` (lines 13 and 86) and `proposal.md` (lines 11 and 71) say 060-min is v0.1.1. Fix the wording when 015 is archived; the one-writer-by-construction rule in 015 is unchanged until 060 lands.
- 015 (done at its archive, 2026-10-10): its design D6 names "020's `seq` on URLs" as the order column; 020 D1 uses `urls.id`, which already grows in insertion order. `docs/crawl-store.md` says resuming arrives with 060 in v0.2; it is v0.1 now. Fix both when 015 is archived.
- 060: own what moved from 015 (see 060's entry): its design still calls `015`'s `check_writer`, `write_control`, reservation and `crawl_id_taken`, and its spec and tasks rely on them.
- 060: remove the window in which a just-claimed, still-empty `<id>.sqlite` makes `--crawl latest` report crawl_file_invalid. Create the file as `<id>.sqlite.tmp` (claimed exclusively, counted as taken) and rename it after the schema is written, together with the reservations.
- 060: `crawls rm` deletes a crawl file together with its SQLite companions (`<id>.sqlite-wal`, `<id>.sqlite-shm`), because reading a WAL crawl file may leave them behind (015 crawl-store.md).
- 020 (done 2026-10-10): `--max-urls` has no default limit (was 10,000); the spec, the `max_urls_reached` scenarios and the URL estimate are updated. 030: raw HTML storage can no longer be decided from a default `--max-urls`. Decided 2026-10-11: opt-in by a flag (see 030's entry); only the flag's name is left for the re-grounding.
- 020 (done 2026-10-10, design D12–D15): decide four design points from the architecture review of 2026-10-05 before its tasks are written:
  - **Crawl state transitions:** 015's `set_state` writes any state from any state. A table of allowed transitions and one pure function that refuses the others, used by 020 (`running`, `completed`, `stopped`, `failed`) and later by 060 (`interrupted`, resume).
  - **URL types:** a `NormalizedUrl` type (a `NewType` or a small frozen class) that only URL normalisation creates, so mypy refuses a raw string wherever the frontier, Scope or Links expect a normalised URL. Decide whether crawl ids get a type too.
  - **Data access stays in the store:** writer units are defined only in `spider.store.*` modules, and the engine, extractors and Rules call them instead of writing SQL. Decide how 030 and 040 add their units under that rule.
  - **One context for a Crawl's dependencies:** the clock, the Reporter, the writer, the settings, the Fetcher and the Scope are built in one place and passed as one object, instead of growing every signature.
- 020: page preparation (parse, extract and normalise, ending in frozen records) is one pure, picklable function of the fetched response, called through an executor seam. 020 ships the in-process executor; 026 plugs in the pool without touching the engine.
- 020: selectolax 1.0 removed its old backend (`from selectolax.parser import HTMLParser` raises `ImportError`); the link extractor uses `selectolax.lexbor.LexborHTMLParser` (found by the store benchmark, 2026-10-11).
- 020: D2's unit goes through 017's `submit()`: the URL's task ends at the submit, and the unit's outcome arrives at its commit. Under the robustness rule, a unit that fails, even when it runs again after another unit failed, never stops the Crawl: the engine records that URL as `error` through a fallback unit. Only a failed commit or a writer that has ended is `write_failed` (D16).
- 020: D1's frontier reads are writer units that commit nothing (017), and `urls` gets the partial index `(crawl_depth, id) WHERE fetch_state = 'queued'` (flat at 1–2 ms in the store benchmark; a cursor alone breaks once a continue re-queues URLs).
- 060: `resume` is v0.1 now; its spec markers move with 060-min's.
- 060: its "Crawl State transitions" requirement builds on 020's (020 D12): it adds `running` → `interrupted` and `interrupted` → `running` to 020's `TRANSITIONS`, and records `interrupted` through 020's `set_state`. 020's `stop_reason` now also covers `failed` (`seed_unreachable`, `site_unreachable`, `write_failed`).
- 060: 020 dropped its kill-then-continue scenarios ("Continuing a killed Crawl completes it", "Continuing does not request fetched URLs again" after a kill, "A Crawl killed on Windows can be continued"), because continuing a killed Crawl needs `interrupted`. 060's "A killed Crawl can be resumed at once" scenarios cover them; add that the resume requests no URL that was `fetched` before the kill.
- 060: builds the detached Crawl's `CrawlContext` (020 D15) and sets its `StopSignal` from control rows with `requested`.
- 060: the detached process tree includes 026's pool workers: no console windows, and a clean shutdown on stop and interrupt.
- 060: on Windows, a process started with `sys.executable` from a venv, or from `spider.exe`, is a launcher whose child is the real interpreter, so killing the recorded pid leaves the Crawl running. Start the base interpreter (`sys._base_executable`) with `__PYVENV_LAUNCHER__` set, as `multiprocessing` does, or put the tree in a Job object, and record the real pid for `status`.
- 060: any `OSError` on a pipe between the Crawl's processes means end of input: on Windows a closed pipe can surface as `BrokenPipeError` at `poll()`, not as `EOFError`.
- 060: `status` reports the average rate over the whole Crawl next to `rate`.
- 050: check `summary` against Screaming Frog's Overview counts: URLs encountered, blocked by robots.txt and crawled; Internal and External; Indexable and non-Indexable; and content types with their shares.
- 030 and 040: under 020 D9 and D14, handlers are pure and return store rows declared in `spider.store.*`, and post-crawl passes are store functions (030: `spider.store.pages` and `spider.store.links`; 040: `spider.store.issues`). Their drafts still describe handlers that write in the unit, and sinks; and they add their entries to 020's `default_hooks()`.
- 024 (v0.2): decide whether 020's apex-to-www rule applies to each Seed of List and Sitemap mode.
- 022-min: the recorded `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` values must go through 015's URL redaction (`user:***@host`). Today it is the private `_redact_value` in `spider.store.redaction`, so 022 either makes a public `redact_url` or routes the variables through `SecretNames`.
- 026: re-ground for v0.1; the benchmark runs on Windows, macOS and Linux runners or a stated machine, never as part of the CI gate.
- 026: `psutil` is no longer a dependency of 015; add it as a test dependency for the pool's benchmark.
- 020–050: no Alembic revision per change before v0.1; tables are added to the declared schema and `docs/schema.md` in the same slice (015 D5, D6).
- 040: every v0.1 Rule ships a reproducing SQL query over the public schema. Post-crawl Rules are evaluated by it; for per-URL Rules evaluated in Python, a test checks that the Python result equals the query over the stored Crawl. `rules show <id>` prints the query, and an Issue can point to it.

**From a code review of a peer open-source crawler (2026-10-05),** to weigh when each change is re-grounded. Points our drafts already cover are left out.
- 020:
  - Normalisation keeps the trailing slash: `/a` and `/a/` are distinct URLs, because which one redirects is itself a finding. Say so in the normalisation requirement.
  - Backstops that end the Crawl with a `stop_reason`: a zero-success breaker (no URL stored after `max(8, 2 × concurrency)` finished requests), a per-URL watchdog, and stop as a grace period followed by cancellation.
  - Invariant tests at seam 3+6: `--max-urls` is never exceeded under concurrency (in-flight URLs count toward it), each URL is fetched once, and link cycles end.
  - A deterministic dispatch order: an explicit insertion sequence as the tie-break, never a timestamp.
  - The apex→www direction joins Scope in one direction only. A `seed_base_mismatch` warning when the Seed's canonical or Links point to the other host. About 20 seed/base cases make a good table test.
- 022 (after v0.1, with the hostile-site work; v0.1 keeps 022's retries, `Retry-After` and host pause as designed):
  - Throttling is host state: after a 429 the host drops to 1 request in flight and recovers step by step after N consecutive 2xx. Waiting per host is capped in total; after that, its remaining URLs are recorded as rate-limited without a request.
  - Classification: 429 is always rate-limited. 503 is rate-limited only with `Retry-After`, otherwise a server error. 403, or a challenge page (`cf-mitigated: challenge`), is `blocked` and never retried. Each is its own outcome value, distinct from a 4xx Page.
  - Separate retry budgets for rate limits and for transport errors and 5xx, so they never multiply.
- 022 (v0.1):
  - The request timeout covers the body read. Fixture routes: a stalled body, a body that trickles forever, and a 503 whose body stalls.
  - A `Location` that is not http(s) is refused.
- 024: sitemap URLs are taken round-robin across child sitemaps, capped relative to `--max-urls`, within a total time budget. A walk cut short is `truncated` ("unknown", not "missing"). `Sitemap:` lines that are not http(s) are ignored.
- 026: a seeded synthetic site (deterministic, an injected Issue mix with recorded counts, a latency option, and a direct writer into the crawl store) for the 500k-URL benchmark and Rule performance. Benchmark method: interleave runs and take the minimum, use a fresh store per stage, prefer counts to wall time, and keep retracted rows.
- 080: `skill install --project` and `--dry-run`, detecting files the user edited, and atomic writes.
- 110: a small `--fail-on` grammar (`score<90`, `severity>=error`, `errors>0`). Exit 2 for a tripped gate, with the result printed first.
- Not adopted, on purpose: ignoring robots.txt by default, robots.txt 5xx as allow-all, browser or AI-bot user-agent impersonation, tracking-parameter stripping by default, sampling coverage modes as the default, telemetry and auto-update.

## v0.2: crawl control, reports, CI gate, link graph

The changes deferred by the 2026-10-05 scope cut come first, then the link-graph work.

| # | Change | Capabilities (specs) | Commands | Status |
|---|---|---|---|---|
| 024 | `024-add-list-and-sitemap-modes` | `crawl-modes` | `crawl --list`, `crawl --sitemap` | planned |
| 060 | `060-add-crawl-control` | `crawl-control` | `crawl --dry-run`, `crawls`, detached List mode | planned, rest after v0.1 |
| 070 | `070-add-html-report` | `reporting` | `report`, `report brief` | planned |
| 100 | `100-add-installers` | `installation` | none (install scripts) | planned |
| 110 | `110-add-ci-gate` | decided when it is drafted | `diff A B`, `--fail-on`; a GitHub Action | planned, not drafted yet |

- **The rest of the v0.1 and v0.1.1 changes,** marked **(v0.2)** under "What each change owns": the rest of 060; 090's tools for the v0.2 Commands; 022's ALPN, `--proxy`, auth and custom headers; 030's readability, language, pixel widths and HTML storage; 040's other 27 Rules and the `ai_search` category; 050's `export`, Segments, the full `--where`, the `csv` format, `--no-bom` and `-o`; 080's Full audit, fix and verify, dry run and Hand-off, install-script one-liners and plugin marketplace.
- **Order:** 024 first. The rest of 060 needs 022 and 024 (List mode, and the sitemap reader for the dry-run estimate). 070 needs 050's `export` and CSV writer, and 060 for its end-to-end test. 110 needs 024 and 040's Issues. 100 comes last.
- Link graph views: `links <url> --in|--out`.
- Redirect Chain analysis: `redirects`, with per-hop headers and timing.
- Sitemap analysis: `sitemaps` (sitemap vs crawl, non-indexable URLs in the sitemap).
- Link Score.
- Rules that need the whole site: orphan Pages, hreflang return links, sitemap coverage.
- Report Sections for links, redirects and sitemaps.
- `rules apply`, which recomputes Issues from stored data after thresholds change.

## v0.3: comparison and content

- The diff Report. Crawl Diff itself (`diff A B`) moved to v0.2 with 110.
- Custom Extraction (CSS, XPath, regex; configured in `spider.toml`).
- **User SQL Rules**, stage 1: user Rules written as read-only SQL over the public schema ([ADR-0002](docs/adr/0002-sqlite-crawl-store-public-schema.md)), with Rule metadata (Issue Type, Priority, description, how to fix). They are kept in `spider.toml` or in rule files, and can be shared as Rule packs. Stage 1 reuses 040's mechanism, where every built-in Rule already ships its SQL query. Stage 2, Python plugins, comes only after v1.0 (see Backlog).
- Near-Duplicates (our own MinHash) with `duplicates [--exact|--near]`.
- Offline structured-data validation (schema.org plus Google's rules for about 10 types, stored as YAML) with `structured-data`.

## v1.0: stable

- Hardening, full documentation and the full Rule set.
- xlsx export and a white-label Report.
- Homebrew tap, Scoop bucket, and a multi-arch Docker image on GHCR.

## v1.1: JavaScript rendering

- Playwright rendering as the optional `[render]` extra, which fills the JS-only columns.

## Backlog

- **Site metrics beyond Screaming Frog parity:** after v0.1, decide which site-level measurements to add on top of the Screaming Frog tabs. Nothing is chosen yet.

- **Data import (high priority, before Integrations):** `spider import <file> --as <table>` loads a CSV, such as a GSC or Ahrefs export, into the crawl file as an extra table. Agents can then join it with crawl data in SQL and rank Issues by traffic. It is a cheap, agent-first alternative to OAuth integrations, and suits agents that already have Ahrefs or GSC MCP servers.
- **Report formats:** PDF, report translations.
- **Integrations:** Google Search Console (including URL Inspection), GA4, PageSpeed Insights / Core Web Vitals, Ahrefs. Data import comes first.
- **New interfaces:** REST API and web UI.
- **More analysis:** RDFa, accessibility, spelling, screenshots, more rich-result types.
- **Rule plugins (after v1.0 only):** stage 2 of User SQL Rules (v0.3): Rules as Python entry-point plugins, once the internal APIs are stable.
- **Crawl operation:** scheduled or distributed Crawls.
- **Community Skill workflow packs:** workflows such as an e-commerce audit or a migration check, contributed as Markdown through the plugin marketplace.
- **Distribution:** signed standalone binaries and winget.
