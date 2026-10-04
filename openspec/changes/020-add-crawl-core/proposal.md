## Why

Everything after it reads what a Crawl records: page data (`030`), Rules (`040`) and queries (`050`) in v0.1, then Segments (`050`), crawl control (`060`) and the Report (`070`) in v0.2. ADR-0001 settles an own asyncio engine whose frontier lives in the crawl store.

This change builds the core of that engine: a foreground Spider-mode Crawl with Screaming Frog's Scope, robots.txt and Link-following behaviour, politeness, the persistent frontier, and the hooks that later changes plug into. The rest of the crawler builds on this core, and those changes can then run in parallel:
- fetch policy (`022`)
- List and Sitemap modes (`024`)
- the parse pool (`026`)

## What Changes

- **New Command `spider crawl <url>`** in Spider mode, running in the foreground. A bare host such as `site.test` becomes `https://site.test/`.
- **URL normalisation:**
  - It strips fragments and default ports.
  - It lower-cases the scheme and host (converting IDN hosts to ASCII), resolves dot segments and normalises percent-encoding.
  - It keeps the query unless `--strip-params <globs>` removes parameters.
- **Scope:**
  - `--scope host|subdomains|subfolder` (default `host`), with `--subdomains` as shorthand. The Seed host is internal over http and https, on any port. Subdomains use a bundled Public Suffix List.
  - `--include <regex>` and `--exclude <regex>`, both repeatable. An excluded URL is never requested.
  - `--max-depth <n>`.
  - `--max-urls <n>`: default **10,000**, and `0` means no limit. Reaching it leaves the Crawl `stopped` and resumable.
- **Section Crawl:** `--scope subfolder` or any `--include` makes one. URLs outside the Scope are checked but not followed, and `crawl.section_crawl` is set.
- **Link discovery:**
  - The Link type table follows Screaming Frog's defaults. It includes `prev`/`previous` for pagination and HTTP `Link` headers.
  - Link-level and page-level nofollow are honoured. `--follow-nofollow` overrides them, and `--check-external/--no-check-external` turns External URL checks on or off.
  - Resources are requested for their status, even beyond `--max-depth`, and are never parsed.
- **robots.txt:**
  - Obeyed per origin, with RFC 9309 status handling.
  - `--ignore-robots` still labels blocked URLs.
  - `--robots-user-agent <token>` (default `spider`) selects the group. `Crawl-delay` is recorded but not applied.
- **The robots directives parser** for `<meta name="robots">` and `X-Robots-Tag`, including the user-agent prefix rule. `030` reuses it.
- **Politeness:** `--concurrency` (default 5 per host) and `--rate` (requests per second per host). A `possible_blocking` warning follows 10 consecutive 403/429 responses.
- **Crawl Depth:** breadth-first and exact.
- **The frontier:** the `urls` table is the queue. A killed or interrupted Crawl can be continued through the Crawl Service. `060` exposes this as `resume`.
- **Hooks for later changes:**
  - a **per-response hook**, called once for every URL that reaches a final state, inside the same writer unit
  - the **post-crawl passes**, run when a Crawl ends as `completed` or `stopped`, and run again after every continued run
  - an extractor registry, run in-process at this stage (`026` may move it into a process pool, only if its benchmark shows parsing is the bottleneck)
- **Output, following the stream rules of `010`:**
  - `{event, ts, data}` progress events on stderr: `crawl_started`, `progress` every 10 seconds, and `stopping`.
  - Warnings as diagnostics.
  - One JSON result on stdout with `seed_count` and `status_classes`.
- **Ends of a Crawl:**
  - an unreachable Seed marks the Crawl `failed` (resumable): result, one `seed_unreachable` error, exit 8
  - Ctrl+C (Ctrl+Break on Windows) → `stopped` with `stop_reason: interrupt`: result, one `interrupted` error, exit 130
  - a write failure → `failed`, `crawl_write_failed`, exit 7
- **Settings:** every crawl setting lives in `[crawl]` of `spider.toml` under `010`'s naming rule, and the recorded config holds every registered crawl setting.
- **Store:**
  - The `urls` and `origins` tables, and the `crawl` columns `scope`, `stop_reason` and `warnings`.
  - Each column is added in the slice whose scenario first needs it.
- **Flags that go beyond the wording of ROADMAP.md.** Both are small and plainly needed: `--robots-user-agent` and `--check-external/--no-check-external`.
- **MCP tools:** none in this change. `090-add-mcp-server` wraps `crawl` through `060`'s detached start.

## Capabilities

### New Capabilities
- `crawling`: covers the following.
  - Spider mode, URL normalisation, Scope and Section Crawls.
  - Link discovery and the Link type table, the robots directives parser, and robots.txt.
  - Politeness, Crawl Depth and limits, and the `urls`/`origins` tables with the persistent frontier.
  - The per-response and post-crawl hooks, parse failures in process, progress events, the result, and how a foreground Crawl ends.

### Modified Capabilities
- None. There are no main specs yet.

## Non-goals

- Fetch policy (`022-add-fetch-policy`, v0.1):
  - timeouts, retries, and redirects with every hop recorded
  - body and URL limits, compression, TLS trust, HTTP version
  - user agent, custom headers, basic auth, proxy, and `response_headers`
- List mode, Sitemap mode and `mode_conflict`: `024-add-list-and-sitemap-modes` (v0.2).
- Parsing in a process pool: `026-add-parse-pool` (v0.2), only if its benchmark shows parsing is the bottleneck.
- `--detach`, `--dry-run`, `status`, `stop`, `resume` and `crawls`: `060-add-crawl-control` (v0.2).
- Page-data columns and stored Link attributes: `030-add-page-data` (v0.1). Rules: `040-add-rules` (v0.1).
- Discovering sitemaps during a Spider crawl, and Link Score: **v0.2**.
- JavaScript rendering and JS-only Links: **v1.1**.
- Scheduled or distributed Crawls: **backlog**.
- These are also out of scope, and are listed in design.md under Open Questions: `--resolve`, per-Link-type switches, cookie sessions, and checks for private addresses.

## Impact

- **Depends on:**
  - `000-scaffold-project`: the package, CI, the loop wiring, and the plain-HTTP fixture site with its request log.
  - `010-add-workspace-and-cli-contract`: the stream rules, diagnostics, partial results, exit codes, `settings_invalid`, and the settings naming rule and precedence.
  - `015-add-crawl-store`:
    - the crawl file and ids, the `crawl` and `seeds` tables, and the crawl states
    - the transactional writer and the one-writer claim
    - redaction, `spider schema` and `docs/schema.md`
- **Used by:**
  - `022`, `024` and `026` (the engine, the `urls` table, the Fetcher interface)
  - `030` (the per-response hook, the extractor registry, discovered Links, the robots directives parser, the post-crawl passes)
  - `040` (both hooks)
  - `050` and `070` (`urls`, `section_crawl`)
  - `060` (the continue operation, the stop flag, events, config resolution)
- **Code:**
  - `src/spider/crawl/`: urls, scope, robots, directives, frontier, scheduler, engine, events, `fetcher/` (interface and minimal aiohttp implementation).
  - `src/spider/extract/links.py` and the extractor registry.
  - `src/spider/services/crawl.py`, `src/spider/cli/crawl.py`, and store tables.
- **New dependencies:** `aiohttp`, `protego`, `selectolax`, `msgspec` and `publicsuffixlist` (a bundled list, never downloaded at runtime).
- **Docs:** `docs/crawling.md`, and the hook and extractor seams in `docs/architecture.md`.
