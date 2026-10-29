# Roadmap

> **Name:** the product is OpenLinx (PyPI `openlinx`, GitHub organisation `openlinx`). The code still uses the working name `spider` for the command, the Python package, `spider.toml` and the `.spider/` Workspace folder, until a rename change moves them to the product name.

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

A deep, local technical crawler for agents. Other tools already ship a crawler with a CLI, an MCP server and a Skill, and a SQLite store or no telemetry alone sets none apart; the open all-in-one SEO suites offer the audit as one capped module on top of a paid data API. This one leads with:
- **Your crawl is a database:** arbitrary read-only SQL over a public, versioned schema, with every Issue reproducible by a query. Each Crawl is a SQLite file with a documented schema ([ADR-0002](docs/adr/0002-sqlite-crawl-store-public-schema.md)), and `spider sql` works while a background Crawl is still writing.
- **A contract-tested CLI for agents:** one JSON result per Command, a registry of diagnostics and error codes, and cursor paging.
- **Local diff and crawl continue:** a stopped or interrupted Crawl continues where it ended, and Crawl Diff (v0.2) compares two crawl files on your machine, with no cloud.
- **Built for large sites, with no page cap:** a full crawl of every URL in Scope, never a sample, at the scale target of about 500k URLs. Checking 50 pages is a commodity; a complete crawl of a large site, run in the background for hours and queried while it runs, is the job. The frontier lives in the crawl file, so memory stays flat.
- **No account, no paid API keys, no telemetry, no LLM calls** ([ADR-0004](docs/adr/0004-tool-never-calls-an-llm.md)).

We deliberately do not claim these as unique: the MCP server, the Skill, the CI gate, the Health Score and `llms.txt` checks.

## v0.1: first public pre-release

| # | Change | Capabilities (specs) | Commands | Status |
|---|---|---|---|---|
| 000 | `000-scaffold-project` | none (tooling only) | `spider --version` | done |
| 010 | `010-add-workspace-and-cli-contract` | `workspace`, `cli-contract` | `init`, `commands` | done |
| 015 | `015-add-crawl-store` | `crawl-store` | `schema`; `--crawl` | done |
| 017 | `017-speed-up-crawl-writer` | `crawl-store` (modified) | none | done |
| 018 | `018-add-schema-conventions` | `crawl-store` (modified) | `schema` (`indexes`) | done |
| 020 | `020-add-crawl-core` | `crawling` | `crawl <url>` (foreground) | first part done; the rest code-complete |
| 022 | `022-add-fetch-policy` | `fetching` | `crawl` fetch flags | done on its branch, min |
| 030 | `030-add-page-data` | `page-data` | none (data only) | in progress, min |
| 040 | `040-add-rules` | `rules` | `rules` | in progress, 15 Rules |
| 050 | `050-add-query-and-segments` | `querying` | `summary`, `pages`, `page`, `issues`, `sql` | in progress, min |
| 026 | `026-add-parse-pool` | `crawl-performance` | none | in progress: the parse pool and its benchmark |
| 060 | `060-add-crawl-control` | `crawl-control` | `crawl --detach` (Spider mode), `status`, `stop`, `resume` | planned, min |
| 080 | `080-add-agent-skill` | `agent-skill`, `diagnostics` | `skill install`, `doctor` | planned, min |
| 085 | `085-add-release` | decided when it is drafted | none (release workflow) | planned, not drafted yet |

v0.1 is installed from PyPI, where 085 publishes it, with `uv tool install` (or `pipx`). The install scripts come with 100 in v0.2.

### Build order

A thin end-to-end slice comes first, so the first Issues reach a user early. The changes then widen.

```
slice:   000 ─► 010 ─► 015 ─► 017 ─► 018 ─► 020 ─► 030-min ─► 040-min ─► 050 issues
                                              │    (first      (3–5       (issues,
                                              │    columns)    Rules)     issues <id>)
                                              │
widen:                                        ├─► 022-min ─┐
                                              ├─► 060-min ─┤
                                              ├─► 026 parse pool, synthetic site, benchmark baseline (before the slice's e2e test) ─────┐
                                              └────────────┴─► rest of 030-min ─► 040 (15 Rules) ─► 050 sql, summary/pages/page ─► 080 ─┴─► 026 benchmark re-run (sizes the pool) ─► 085 ─► v0.1 tag
```

- **Where the build is:**
  - **In main:** 000, 010, 015, 017, 018, and the first part of 020 (its groups 1–6), so `spider crawl <url>` crawls a site in the foreground.
  - **On branches:** 020, the crawl core, is code-complete and reviewed; it merges into main once CI runs on the public repository. 022-min, the fetch policy, is done for v0.1 and merges after 020. 030-min, the page data, is in progress. 026 (the parse pool), 040 (the Rules) and 050 (the queries) are partly built and continue after 020 merges.
  - **Not started:** 060-min (crawl control), 080 (the agent Skill) and 085 (the release).
- **The slice:** 015 → 017 → 018 → 020 → 030-min → 040-min → 050-issues. 017 speeds up 015's writer before 020 writes through it, and 018 sets the schema conventions before 020 adds the first tables after 015's. 030's slice is its task groups 1–3 (Page rows, titles, meta descriptions and headings, which `title-missing` and `h1-missing` read), and its groups 4–12, Indexability included, widen after 022-min, whose size and redirect columns 030 copies. 040 starts with 3–5 Rules that need no redirects (for example `internal-4xx`, `internal-5xx`, `internal-no-response`, `title-missing`, `h1-missing`), and 050 with `issues` and `issues <rule-id>`. The slice ends with a cross-OS end-to-end CI test: a foreground `crawl` → `issues` on Windows, macOS and Linux. 050's slice is its task group 1, `issues` and `issues <rule-id>` with the end-to-end test; 040's slice is its task groups 1–4, the Rule model and `spider rules`, `[rules.<id>]` settings, the Rules as queries with stored and live Issues, and `internal-4xx`, `internal-5xx`, `internal-no-response`, `title-missing` and `h1-missing`.
- **Widening:** 022-min and 060-min can each start as soon as 020 is in, in their own worktrees, alongside the slice. 060-min needs only 015 and 020, and must land before 080, whose workflows start Crawls detached. The rest of 030-min, 040 up to its 15 Rules, and the rest of 050 follow. 050's `sql` can land right after `issues`, before `summary`, `pages` and `page`. 080 comes after them, because the Skill is generated from the finished Commands, columns and Rules.
- **Scale proof:** 026, the parse pool with its synthetic site and benchmark script, starts its synthetic site alongside 020 and the rest once 020's slice is in (its first pull request), and lands before the slice's end-to-end test; its first run is the baseline. The benchmark is re-run on the full v0.1 pipeline after 080, before 085, to size the pool, and its numbers go in `docs/benchmarks.md`.
- **HTML parser:** selectolax 1.0.1 or later, parsing with scripting on, as a browser that runs scripts does. A head `<noscript>` therefore keeps the later head elements (canonical, meta description, robots, hreflang) in `<head>`, and a body `<noscript>` gives its Links.
- **Release:** 085 comes last, before the v0.1 tag, and publishes under the product name, OpenLinx.
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
- **017-speed-up-crawl-writer** (v0.1, from the writer prototype; the store layer only; done):
  - It modifies `crawl-store` and builds on 015's `CrawlWriter` as built. It comes after 015 and before 020, whose per-URL unit uses it.
  - **The writer stays a thread.** A writer process is out: it tied the thread under the parse pool (40.1 against 40.4 Pages/s) and writer-only at ~466 Link rows per Page (17.6 against 17.2), its WAL peaked at 402 MB against 212 MB, and it would need units as records with a registry, errors sent over a pipe and a slow test group.
  - **`run()` and `run_async()` are unchanged:** their result means the unit ran, and `flush()` means it is durable.
  - **`submit(unit)` is new:** it returns a Future that is resolved at the commit that holds the unit, and fails when that commit fails. A window of unresolved units gives backpressure. Units stay closures (`Callable[[Connection], T]`), with no registry; 020 D14's row records stay 020's rule.
  - **Reads through the writer** run in its open transaction and commit nothing, so 020's frontier reads see every unit before them.
  - **The optimistic batch,** internal to the writer: the units of a batch run without a savepoint each. When one fails, the transaction is rolled back, the units before it run again with a savepoint each and are committed at once (the replay commit, a new commit trigger in the spec), and the failing unit never runs again, a `BaseException` included. Unit atomicity is tested with a unit that fails half-way. It gained 14–15% on the clean path in back-to-back runs: 52.8 → 60.9 Pages/s at 120 Link rows per Page, 15.8 → 18.0 at ~466. Since a unit may run twice, a unit has no effect outside its connection.
  - **The writer's connection pragmas,** with no new setting: `temp_store=MEMORY`, a 64 MB `cache_size` and, in WAL mode, a 256 MB `mmap_size` (−33% wall time together in the store benchmark at 2k Pages). The killed-writer proof is re-run on Windows with `mmap_size` on.
  - **Prebuilt statements** are a rule for every store module: built once and run as `execute(stmt, params)`, never `.values(<literals>)` per unit and never `insert().values(list)`. Its design decides whether a guard test enforces it.
  - **A local throughput check,** never part of the CI gate: writer-only, 20k Pages at ~466 Link rows per Page, at least 12 Pages/s, a WAL peak of at most 300 MB and a crawler RSS of at most 400 MB. 017 records only a 5k-Page smoke run; the 20k run that sets the floor moves to 030, once on the links layout that the links benchmark chooses, and restates the floor (decided 2026-10-11).
  - Not in 017: the partial frontier index (020), the parse pool (026), and the pipes between a Crawl's processes (060). A writer process, if one is ever added, starts through a dedicated entry module whose imports a startup-allowlist-style test checks.
- **018-add-schema-conventions** (v0.1; a separate small change before 020; done):
  - [ADR-0005](docs/adr/0005-crawl-file-schema-conventions.md), the crawl file's schema conventions. It records:
    - one v0.1 blueprint, derived values written only by post-crawl passes, later columns as NULL, TEXT + CHECK enumerations
    - indexes built during the Crawl
    - every Link occurrence as a row
    - STRICT tables
    - 15 naming rules
  - The file refuses bad values: every public table is `STRICT`, and the CHECKs of enumerations and flags come from the declaration. 015's `crawl` and `seeds` follow at once.
  - `spider schema` fills `references` and gains `indexes`, each with the query it serves. `docs/schema.md` and the contract test cover indexes, STRICT and `WITHOUT ROWID`.
  - The conventions are revised. A derived column's description starts with `Derived: `, and a later column's with `Filled from v<major>.<minor>. `. The `crawl` row may hold a derived value that a post-crawl pass writes, such as 040's Health Score.
  - Not in 018: the other tables, which their owners add under these rules (020, 022, 030, 040, 060), and the links layout, which the links benchmark chooses for 030.
- **020-add-crawl-core**:
  - Spider mode (`crawl <url>`) and URL normalisation, which keeps the trailing slash.
  - **Scope:** `--scope host|subdomains|subfolder`, `--subdomains`, `--include/--exclude`, `--max-depth`, `--max-urls` (no limit by default; reaching an explicit limit leaves the Crawl resumable), `--strip-params`. An apex Seed admits its `www.` host, never the reverse, and `seed_base_mismatch` warns when a `www.` Seed's site lives on the apex.
  - **Section Crawl**, and robots.txt (obeyed by default, `--ignore-robots`, `--robots-user-agent`).
  - **The robots directives parser** (meta robots and X-Robots-Tag, used by 030 as well).
  - Politeness (`--concurrency`, `--rate`).
  - The frontier: the `urls` table, deduplicated by its unique URL with no in-memory URL map, dispatched depth by depth in `urls.id` order.
  - **Link discovery and the Link type table**, with `--follow-nofollow` and `--check-external`.
  - Crawl Depth.
  - **Hooks:** a per-response hook for every URL that reaches a final state when it is dispatched (a URL that only Links that are not followed reach is recorded `skipped` at discovery and reaches no handler, since a later followed Link may still queue it), whose handlers return rows that the store writes in the URL's unit, and the **post-crawl passes** hook, which runs for `completed` or `stopped` Crawls and is safe to re-run.
  - **Design points of 2026-10-05:** guarded Crawl State transitions (one table and check; 060 adds `interrupted`), a `NormalizedUrl` type, writer units defined only in `spider.store.*`, and one Crawl context object.
  - The `[crawl]` settings table, which 022 and 030 extend.
  - Progress events and the result.
  - **Ctrl+C:** the Crawl becomes `stopped` with `stop_reason: interrupt`, and the command exits 130.
  - **Unreachable Seed:** the Crawl becomes `failed` and resumable, and the command exits 8.
  - **Robustness and backstops:** one URL never stops the Crawl (counted `parse_failed` and `handler_failed` warnings), parsers tested with hypothesis, hostile fixtures, a network pause (decided 2026-10-14: 10 Internal requests in a row without a response pause the Crawl, which probes the Seed at 5, 10, 20 and 40 seconds and then every 60; an answer resumes it, re-queueing the streak once after an outage; nothing within `--network-wait`, default 1800 seconds, fails it with `site_unreachable`, exit 8, resumable), a per-request watchdog, and a stop that waits 10 seconds and then cancels.
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
  - **(v0.2)** Bot-challenge detection, with the hostile-site work: a bot-protection or WAF challenge page, recognised by the headers, cookies and body markers of the common CDNs and WAFs, marks its URL `blocked`, never a Page with a missing title or H1. It detects and classifies; it never evades.
  - **(v0.2)** With that detection, an External URL that answers 403 or a challenge is checked again with a browser-like request before it counts as broken. External URLs are already checked with GET, never HEAD.
  - **(v0.2)** Web Bot Auth, opt-in: requests are signed per RFC 9421 (Ed25519, with the public key served from a key directory), so a site owner behind a bot gatekeeper can verify the crawler and allow it. With no key configured, requests go out unsigned.
- **024-add-list-and-sitemap-modes** (v0.2):
  - List mode (`--list <file|->`) and Sitemap mode (`--sitemap <url>`, repeatable, with index files and gzip).
  - `mode_conflict` when two Crawl Modes are given.
- **026-add-parse-pool** (v0.1: the pool and its benchmark):
  - **The parse pool is unconditional in v0.1** (decided 2026-10-11): page preparation runs in a process pool behind 020's executor seam, with bounded queues, clean shutdown of workers on stop and interrupt, and no console windows on Windows. A Page whose preparation takes over 30 seconds from the moment a worker takes it costs one URL (`parse_timeout`) and one worker, never another Page (decided 2026-10-14, after lexbor took about 80 s on 100,000 nested `<div>`s; preferred over a nesting-depth pre-scan in 020). It is built right after 020's slice and lands before the slice's end-to-end test.
  - The pool's default size is physical cores minus 2, at least 1, until the sweep below picks it (decided 2026-10-14; psutil counts the cores at run time). In the writer prototype, 6 workers (physical cores minus 2) on the maintainer's hybrid laptop (an i5-12450H: 4 performance cores with SMT plus 4 efficiency cores, 12 threads) still took CPU from the writer and capped the Crawl at about 40 Pages/s. So the benchmark sweeps the worker count (for example 2, 3, 4 and 6) on that laptop, records machine-wide CPU and clock frequency, and picks the default that gives the most Pages/s while the writer is never short of CPU. Physical cores minus 2 is the sweep's upper bound. The ~500k-URL benchmark also sizes the queue bounds and doubles as the soak test. It runs by hand on a stated machine, never in CI, and its numbers go in `docs/benchmarks.md`.
  - It also measures the crawl-file layout variants that the store benchmark of 2026-10-10 left out (decided 2026-10-11): the `links` layout, a 16 KB page size, a zstd dictionary for stored HTML, and the WAL size of a ~100k-Page run without a concurrent reader. For the `links` layout, if 030's task 10.1 has already chosen it, 026 uses that layout; otherwise 026 runs 10.1's benchmark and decision rule, and 030 reuses the result. Whichever comes first settles the layout once.
- **030-add-page-data** (min in v0.1):
  - Every per-Page column of the crawl file, under the column names SEO practitioners already use, added in the slice where it is first needed.
  - Indexability and Indexability Status.
  - Link attributes stored for analysis (building on 020's discovered Links and Link types).
  - Inlink and outlink counts, computed in the post-crawl passes.
  - The Content Area and content metrics, and the Exact Duplicate hash.
  - Structured-data item counts, and cookie names without their values.
  - **(v0.2)** Flesch Reading Ease and the Readability band, language detection (`--detect-language`, py3langid), SERP pixel widths, and **raw HTML storage** (zstd). HTML is not stored by default; storing it is opt-in by `--store-html` (`[crawl] store_html`) (decided 2026-10-11: in the store benchmark, HTML was about 70% of the crawl file). The `page_sources` table and the v0.2 columns exist, empty, in v0.1.
- **040-add-rules** (15 Rules in v0.1):
  - The Rule model and the 15 Rules listed above; `http-url` is a Warning with High Priority. **(v0.2)** the other 27 Rules of the 42-Rule catalogue.
  - Thresholds and disabling in `spider.toml`.
  - **Every Rule is one reproducing SQL query** over the public schema, the foundation of v0.3's User SQL Rules, and it is the Rule's only form:
    - a running Crawl writes no Issue; while a Crawl has no final pass (`running`, `failed` or `interrupted`), the Issues reader runs the queries live, read-only, and returns the shape of the stored Issues
    - when a Crawl ends as `completed` or `stopped`, the post-crawl pass materialises each Rule's rows into `affected_urls`, then the Health Score; 050's Commands read Issues through the same reader
    - `rules show <id>` prints the query, and an Issue can point to it ("reproduce with `spider sql`")
  - Issues and Affected URLs. `issues` is a view whose `affected_count` counts each Rule's Affected URLs, so no count is stored (decided 2026-10-11).
  - The Health Score.
  - `spider rules [list|show <id>]` and `rule_not_found` (exit 4).
  - **(v0.2)** A new Rule category `ai_search`, for AI-search readiness. The exact Rule set is decided when it is drafted. Candidates:
    - AI crawlers blocked in robots.txt (GPTBot, ClaudeBot, PerplexityBot, Google-Extended, CCBot and others; the list is kept as data)
    - `/llms.txt` missing or invalid
    - main content missing from the raw HTML, approximated from the Word Count until JavaScript rendering arrives in v1.1
    - no structured data on Indexable Pages
    - deterministic readiness checks: question-style headings, a visible date, author markup and answer blocks, with an optional score of their own next to the Health Score
  - **(v0.2)** A Rules pack, pulled forward from v1.x, that extends the catalogue beyond the 42 Rules:
    - accessibility from the parsed HTML: links and buttons without a name, form controls without a label, iframes without a title, a viewport that blocks zoom, a positive `tabindex`, and skipped heading levels
    - JSON-LD checked against the required fields of Google's rich results
- **050-add-query-and-segments** (min in v0.1):
  - `summary` (the data model shared with the Report). **(v0.2)** its per-Segment breakdown.
  - `pages` with the basic `--where` language (comparisons, `contains`, `is [not] null` and `and`), `--fields`, `--sort` and paging. **(v0.2)** the rest of `--where`: `~`/`!~`, `in`, `or`, `not` and parentheses.
  - `page <url>`: JSON, where `--headers` shows redacted headers. **(v0.2)** `--html`, which needs 030's stored HTML.
  - `issues` and `issues <rule-id>`.
  - The **end-to-end CI test** on Windows, macOS and Linux: a foreground `crawl` → `issues`. It is the last part of the thin slice. 070's end-to-end test is added in v0.2.
  - Read-only `sql`: exactly one `SELECT`/`WITH` statement, with a default row limit and a timeout.
  - **(v0.2)** `export <view>`: `jsonl` by default, or `csv`; the `resources` view is defined over `urls` and `links`. With 030's stored HTML, Pages also export as Markdown, as input for AI tools.
  - **(v0.2)** A ready-made what-to-fix-first ranking: Issues ordered by Priority and Affected URL count, later also an MCP tool (090). Each Rule's guidance (`description`, `why_it_matters`, `how_to_fix`) is already printed by 040's `rules show <id>`.
  - **(v0.2)** **Segments** and `--segment`.
  - **(v0.2)** **The CSV policy and output files**, for every Command (moved from 010 on 2026-10-01):
    - the `csv` format; the single **CSV policy** is UTF-8 with BOM, CRLF and formula neutralisation, with `--no-bom` to turn the BOM off
    - `-o <file>` writes exactly the stdout bytes, atomically, and leaves stdout empty (`output_written`, `output_not_writable`)
- **060-add-crawl-control** (min and `resume` in v0.1, rest in v0.2):
  - `crawl --detach` in Spider mode: on Windows it uses CREATE_NO_WINDOW.
  - `status`, which detects a dead process, and shows `paused_since` while a Crawl waits for the network (020's network pause, 2026-10-14); a stop request during that pause stops the Crawl at once.
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
  - To weigh at its re-grounding, not decided: a polished, terminal-style look with switchable dark palettes and a light one, a monospace and sans-serif pairing, block-character bars, terse copy, and charts richer than a minimal SVG builder; it meets the draft's no-web-fonts rule, its own SVG builder and its offline CSP (070 design, Open Questions).
  - The **end-to-end CI test** on all three OSes: `crawl --detach` → `status` → `issues` → `report`.
- **080-add-agent-skill** (min in v0.1):
  - **The Skill** (workflows, install instructions and one-liners), generated from `spider commands` by a developer script (`scripts/generate_skill.py`). In v0.1 the one-liner is `uv tool install`, and the workflows use only v0.1 Commands.
  - `skill install`, and the outdated-Skill notice.
  - Large Crawls in v0.1: the Skill starts a Crawl with `crawl --detach`, follows it with `status`, queries it with `issues` and `sql` while it runs, ends it with `stop`, and continues an interrupted one with `resume`. Whether it also passes `--max-urls` is decided when 080 is re-grounded.
  - `doctor`, whose TLS check uses 022's TLS setup.
  - An **SQL cookbook** in the Skill: `sql` recipes over the public schema. **(v0.2)** Segment recipes.
  - **(v0.2)** the Full audit workflow (it needs 070's `report brief`); the dry run and the Hand-off rule (when the URL estimate is `null`, the Skill hands the command to the user), which need 060; the install-script one-liners (100); Segments and their recipes; `doctor --proxy`; and the plugin marketplace, which ships with 090's `.mcp.json`.
  - **(v0.2)** The **fix and verify** workflow: the agent reads the Issues, fixes the site's code in the repository, re-crawls only the Affected URLs in List mode, and confirms that the Issue is gone. It depends on 024 and on `rules apply`.
  - **(v0.2)** Plugins: a Claude Code plugin (`.claude-plugin/plugin.json`) bundles the Skill and 090's MCP server and installs with one command, and a Cursor plugin sits next to it.
  - To weigh at its re-grounding: the Skill runs the tool through `uvx openlinx` when no command is installed, and several narrow task Skills (a site audit, broken-link fixes, a pre-launch gate) replace one general Skill.
- **085-add-release** (v0.1; not drafted yet, so `openspec/changes/085-*` does not exist):
  - It publishes the package as `openlinx` on PyPI.
  - Its first task: the re-run of 026's ~500k benchmark on the full v0.1 pipeline, which sweeps the worker count and sets the pool's default, reports `response_headers`' share of the file, and measures 040's live Issues during the Crawl, recorded in `docs/benchmarks.md` (026 design D6).
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
  - CI output formats besides the exit code: SARIF, JUnit XML and GitHub Actions annotations.
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
  - **(v0.2)** MCP UI widgets (MCP Apps) that show results inside the agent's chat.
- **Distribution in v0.1.1:**
  - List the MCP server on the MCP Registry, as OpenLinx.
  - Offer the CLI as a deterministic crawler backend for popular SEO skill packs.

**Re-grounding checklist** (what each change still has to fix or design when it is re-grounded):
- 090: its `design.md`, `specs/installation/` and `tasks.md` still name 100's `release.yml`, its pin test and 080's plugin. They move to 085's release workflow and to `docs/mcp.md`.
- 060: `crawls rm` deletes a crawl file together with its SQLite companions (`<id>.sqlite-wal`, `<id>.sqlite-shm`), because reading a crawl file in WAL mode may leave them behind ([docs/crawl-store.md](docs/crawl-store.md)).
- 024 (v0.2): decide whether 020's apex-to-www Scope rule applies to each Seed of List and Sitemap mode.
- 030 to 050: before v0.1 a change adds no Alembic revision; its tables join the declared schema and `docs/schema.md` in the same slice (015 design D5, D6).

**From a code review of a peer open-source crawler (2026-10-05),** to weigh when each change is re-grounded. Points our drafts already cover are left out.
- 020:
  - Normalisation keeps the trailing slash: `/a` and `/a/` are distinct URLs, because which one redirects is itself a finding. Say so in the normalisation requirement.
  - Backstops that end the Crawl with a `stop_reason`: a zero-success breaker (no URL stored after `max(8, 2 × concurrency)` finished requests; weighed 2026-10-14: 020 pauses the Crawl and probes the Seed instead, and fails it with `site_unreachable` only after `--network-wait`), a per-URL watchdog, and stop as a grace period followed by cancellation.
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
- 026 (weighed 2026-10-14, at its re-grounding: adopted in its design D6): a seeded synthetic site (deterministic, an injected Issue mix with recorded counts, a latency option, and a direct writer into the crawl store) for the 500k-URL benchmark and Rule performance. Benchmark method: interleave runs and take the minimum, use a fresh store per stage, prefer counts to wall time, and keep retracted rows.
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

- **The rest of the v0.1 and v0.1.1 changes,** marked **(v0.2)** under "What each change owns": the rest of 060; 090's tools for the v0.2 Commands and its MCP UI widgets; 022's ALPN, `--proxy`, auth and custom headers, bot-challenge detection with the External re-check, and Web Bot Auth; 030's readability, language, pixel widths and HTML storage; 040's other 27 Rules, the `ai_search` category and the Rules pack; 050's `export` (with Pages as Markdown), the fix-first ranking, Segments, the full `--where`, the `csv` format, `--no-bom` and `-o`; 080's Full audit, fix and verify, dry run and Hand-off, install-script one-liners, plugin marketplace and plugins.
- **Order:** 024 first. The rest of 060 needs 022 and 024 (List mode, and the sitemap reader for the dry-run estimate). 070 needs 050's `export` and CSV writer, and 060 for its end-to-end test. 110 needs 024 and 040's Issues. 100 comes last.
- Link graph views: `links <url> --in|--out`.
- Redirect Chain analysis: `redirects`, with per-hop headers and timing.
- Sitemap analysis: `sitemaps` (sitemap vs crawl, non-indexable URLs in the sitemap).
- Link Score.
- Rules that need the whole site: orphan Pages, hreflang return links, sitemap coverage.
- Soft-404 detection: a random path that cannot exist is fetched once per host, and Pages that answer like it are flagged. 030 or 040 owns it, decided when it is drafted.
- Technology detection as crawl data: the server, CDN or WAF, CMS, framework and analytics of each host, read passively from headers, cookies, the meta generator and script URLs. It serves 080's fix and verify workflow.
- Report Sections for links, redirects and sitemaps.
- `rules apply`, which recomputes Issues from stored data after thresholds change.

## v0.3: comparison and content

- The diff Report. Crawl Diff itself (`diff A B`) moved to v0.2 with 110.
- Custom Extraction (CSS, XPath, regex; configured in `spider.toml`).
- **User SQL Rules**, stage 1: user Rules written as read-only SQL over the public schema ([ADR-0002](docs/adr/0002-sqlite-crawl-store-public-schema.md)), with Rule metadata (Issue Type, Priority, description, how to fix). They are kept in `spider.toml` or in rule files, and can be shared as Rule packs. Stage 1 reuses 040's mechanism, where every built-in Rule already ships its SQL query. Stage 2, Python plugins, comes only after v1.0 (see Backlog).
- Near-Duplicates (our own MinHash) with `duplicates [--exact|--near]`.
- Offline structured-data validation (schema.org plus Google's rules for about 10 types, stored as YAML) with `structured-data`. v0.2's Rules pack checks only the required fields.

## v1.0: stable

- Hardening, full documentation and the full Rule set.
- xlsx export and a white-label Report.
- Homebrew tap, Scoop bucket, and a multi-arch Docker image on GHCR.

## v1.1: JavaScript rendering

- Playwright rendering as the optional `[render]` extra, which fills the JS-only columns.

## Backlog

- **More site metrics:** after v0.1, decide which site-level measurements to add beyond the standard technical-audit columns. Nothing is chosen yet.

- **Data import (high priority, before Integrations):** `spider import <file> --as <table>` loads a CSV, such as a Search Console or a backlink tool export, into the crawl file as an extra table. Agents can then join it with crawl data in SQL and rank Issues by traffic. It is a cheap, agent-first alternative to OAuth integrations, and suits agents that already have Search Console or backlink data through MCP servers.
- **Report formats:** PDF, report translations.
- **Integrations:** Google Search Console (including URL Inspection), GA4, PageSpeed Insights / Core Web Vitals, a backlink data provider. Data import comes first.
- **New interfaces:** REST API and web UI.
- **More analysis:** RDFa, accessibility beyond v0.2's Rules pack, spelling, screenshots, more rich-result types.
- **Rule plugins (after v1.0 only):** stage 2 of User SQL Rules (v0.3): Rules as Python entry-point plugins, once the internal APIs are stable.
- **Crawl operation:** scheduled or distributed Crawls.
- **One source for each crawl setting:** generate `spider crawl`'s options from `CrawlSettings`' fields, so help and default are stated once.
- **Community Skill workflow packs:** workflows such as an e-commerce audit or a migration check, contributed as Markdown through the plugin marketplace.
- **Distribution:** signed standalone binaries and winget.
- **Code quality checks (to weigh, nothing decided):** the aim is to stop agent-written functions and modules from growing, without a second linter as a gate.
  - Widen ruff with complexity and design rules: `C90` and `PLR09xx` with moderate limits first, then `FBT`, `ARG` and `RET`. Other candidates: `N`, `PERF`, `FURB`, `ERA` and `SLF`.
  - Run wemake-python-styleguide (`flake8 --select=WPS`) once as a read-only audit before a large change closes, to find complexity hotspots for its review group. Not a CI gate: its default limits push towards smaller modules and classes than the functional-core style uses.
