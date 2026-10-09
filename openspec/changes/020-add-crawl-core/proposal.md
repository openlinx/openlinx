## Why

Everything after it reads what a Crawl records: page data (`030`), Rules (`040`) and queries (`050`) in v0.1, background Crawls and `resume` (`060`-min) in v0.1 too, then Segments (`050`) and the Report (`070`) in v0.2. ADR-0001 settles an own asyncio engine whose frontier lives in the crawl store.

This change builds the core of that engine: a foreground Spider-mode Crawl with Screaming Frog's Scope, robots.txt and Link-following behaviour, politeness, the persistent frontier, and the hooks that later changes plug into. The product bets on full crawls of large sites (ROADMAP, Positioning), so the core is built for a 500k-URL Crawl from the start: no default URL limit, memory that does not grow with the site, and no single URL that can stop the Crawl. The rest of the crawler builds on this core, and those changes can then run in parallel:
- fetch policy (`022`)
- background Crawls, `status`, `stop` and `resume` (`060`-min)
- the 500k-URL benchmark, and the parse pool only if the benchmark asks for it (`026`)
- List and Sitemap modes (`024`, v0.2)

## What Changes

> **Re-grounded (2026-10-10)** against the code of `015-add-crawl-store` (groups 1–7 final, on its branch) and the archived `010-add-workspace-and-cli-contract`. It applies the ROADMAP decisions of 2026-10-05: no default `--max-urls`, the robustness rule, 060-min in v0.1, and the four design points of the architecture review (design D12–D15). Where `015`'s groups 8–10 are not built yet (the journal mode and `[store]`, redaction), this change depends on them instead of guessing their interface. The kill-then-continue scenarios moved to `060`, whose `interrupted` state and `resume` cover them.

- **New Command `spider crawl <url>`** in Spider mode, running in the foreground. A bare host such as `site.test` becomes `https://site.test/`.
- **URL normalisation:**
  - It strips fragments and default ports.
  - It lower-cases the scheme and host (converting IDN hosts to ASCII), resolves dot segments and normalises percent-encoding.
  - It keeps the trailing slash, so `/a` and `/a/` stay two URLs.
  - It keeps the query unless `--strip-params <globs>` removes parameters.
- **Scope:**
  - `--scope host|subdomains|subfolder` (default `host`), with `--subdomains` as shorthand. The Seed host is internal over http and https, on any port. An apex Seed (`site.test`) also makes its `www.` host internal; a `www.` Seed does not make the apex internal, and a `seed_base_mismatch` warning says when the site lives on the apex. Subdomains use a bundled Public Suffix List.
  - `--include <regex>` and `--exclude <regex>`, both repeatable. An excluded URL is never requested.
  - `--max-depth <n>`.
  - `--max-urls <n>`: **no limit by default**, and a value below 1 is rejected. Requests in flight and requests of earlier runs count. Reaching it leaves the Crawl `stopped` and resumable.
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
- **Crawl Depth:** breadth-first and exact. Followed URLs of one depth start in the order they were first recorded (`urls.id`), never by timestamp.
- **The frontier:** the `urls` table is the queue, and duplicates are caught by its unique URL, not by an in-memory map. A `stopped` or `failed` Crawl can be continued through the Crawl Service; `060` exposes this as `resume`, and adds `interrupted` Crawls.
- **Crawl State transitions:** one check allows only `running` → `completed` | `stopped` | `failed` and `stopped` | `failed` → `running`, each with its `stop_reason`. `060` adds the `interrupted` rows.
- **Robustness (ROADMAP's rule for every change from 020 on):**
  - one URL never stops the Crawl: request, decoding, extractor and handler failures become the URL's outcome, with counted `parse_failed` and `handler_failed` warnings
  - parsing never trusts its input: the Seed parser, the normaliser, decoding, the link extractor, the directives parser and the robots.txt reader are tested with hypothesis over arbitrary input
  - backstops: losing the site (`site_unreachable`, exit 8, resumable), a per-request watchdog, and a stop that waits 10 seconds and then cancels
  - hostile fixtures on the fixture site: connection resets, deeply nested HTML, bytes invalid in their charset, 429 and 503 robots.txt
- **Hooks for later changes:**
  - a **per-response hook**, called once for every URL that reaches a final state. Handlers return rows, and the store writes them in the URL's writer unit.
  - the **post-crawl passes**, run when a Crawl ends as `completed` or `stopped`, and run again after every continued run
  - an extractor registry, run in-process (`026` may move it into a process pool, only if its benchmark shows parsing is the bottleneck)
- **Output, following the stream rules of `010`:**
  - `{event, ts, data}` progress events on stderr: `crawl_started`, `progress` every 10 seconds, and `stopping`.
  - Warnings as diagnostics.
  - One JSON result on stdout with `seed_count` and `status_classes`, its counts derived from the tables.
- **Ends of a Crawl:**
  - an unreachable Seed marks the Crawl `failed` with `stop_reason: seed_unreachable` (resumable): result, one `seed_unreachable` error, exit 8
  - a lost site → `failed` with `site_unreachable`: result, one `site_unreachable` error, exit 8
  - Ctrl+C (Ctrl+Break on Windows) → `stopped` with `stop_reason: interrupt`: result, one `interrupted` error, exit 130
  - a write failure → `failed` with `write_failed` when it can still be recorded: `crawl_write_failed`, exit 7, or `015`'s `crawl_busy`, exit 5
- **Settings:** this change registers the `[crawl]` table of `spider.toml`, under `010`'s naming rule. Later changes add their keys to its model. The recorded config holds every registered setting.
- **Store:**
  - The `urls` and `origins` tables, and the `crawl` columns `scope`, `stop_reason` and `warnings`.
  - Each column is added in the slice whose scenario first needs it, with its `docs/schema.md` row.
  - Writer units are defined only in `spider.store.*` modules.
- **Flags that go beyond the wording of ROADMAP.md.** Both are small and plainly needed: `--robots-user-agent` and `--check-external/--no-check-external`.
- **MCP tools:** none in this change. `090-add-mcp-server` (v0.1.1) wraps `crawl` through `060`'s detached start.

## Capabilities

### New Capabilities
- `crawling`: covers the following.
  - Spider mode, URL normalisation, Scope with the apex-to-www rule, and Section Crawls.
  - Link discovery and the Link type table, the robots directives parser, and robots.txt.
  - Politeness, Crawl Depth and limits, and the `urls`/`origins` tables with the persistent frontier.
  - Crawl State transitions, the backstops, and the robustness rule.
  - The per-response and post-crawl hooks, progress events, the result, and how a foreground Crawl ends.

### Modified Capabilities
- None. `crawl-store` from `015-add-crawl-store` is used as built: this change adds tables and columns under its conventions, which its spec allows, and replaces nothing.

## Non-goals

- Fetch policy (`022-add-fetch-policy`, v0.1-min):
  - timeouts, retries, and redirects with every hop recorded
  - body and URL limits, compression, TLS trust
  - user agent and `response_headers`, and the proxy variables
  - the hostile fixtures that need them: stalled and trickling bodies, a gzip bomb, huge pages, redirect loops
  - **(v0.2)** HTTP version, custom headers, basic auth and `--proxy`
- `--detach`, `status`, `stop` and `resume`, the writer claim, and recording `interrupted`, with the scenarios that kill a Crawl and resume it: `060-add-crawl-control` (060-min, v0.1). `--dry-run` and `crawls`: `060`, v0.2.
- The ~500k-URL benchmark and soak test: `026-add-parse-pool` (v0.1). Parsing in a process pool: `026`, only if its benchmark shows parsing is the bottleneck.
- Page-data columns and stored Link attributes: `030-add-page-data` (v0.1). Rules: `040-add-rules` (v0.1).
- List mode, Sitemap mode and `mode_conflict`: `024-add-list-and-sitemap-modes` (v0.2).
- Discovering sitemaps during a Spider crawl, and Link Score: **v0.2**.
- Adaptive throttling and blocked-response classification: after v0.1, with the hostile-site work.
- JavaScript rendering and JS-only Links: **v1.1**.
- Scheduled or distributed Crawls: **backlog**.
- These are also out of scope, and are listed in design.md under Open Questions: `--resolve`, per-Link-type switches, cookie sessions, and checks for private addresses.

## Impact

- **Depends on:**
  - `000-scaffold-project`: the package, CI, the loop wiring, `FakeClock`, the network guard, and the plain-HTTP fixture site with its request log.
  - `010-add-workspace-and-cli-contract`: the stream rules, diagnostics, partial results (`Outcome`), exit codes, `settings_invalid`, the settings registry and its precedence, `@command_meta` and `OptionMeta`.
  - `015-add-crawl-store`:
    - **groups 1–7 (built):** `create_crawl` with `NewCrawl`, the crawl ids, the `crawl` and `seeds` tables, `set_state`, `CrawlWriter` (`run_async`, `on_commit`, `crawl_busy`, `CrawlWriterClosedError`), the shared column types, `docs/schema.md` and its contract test
    - **group 8 (not built yet):** the journal-mode choice, the `[store]` table and `store_wal_unavailable`, which the Crawl Service loads and reports with the other settings
    - **group 9 (not built yet):** redaction of the command line and config, which the Crawl Service calls before it creates the Crawl
- **Used by:**
  - `022` (the engine, the Fetcher interface, the per-host gate, the fake Fetcher, the DNS resolver hook, `urls` and `origins`)
  - `030` (the per-response hook, the extractor registry, `DiscoveredLink`, the robots directives parser, the post-crawl passes, the decoding function)
  - `040` (both hooks)
  - `050` and `070` (`urls`, `section_crawl`)
  - `060` (the continue operation, the stop flag, the transition table, events, validation and config resolution)
  - `026` (the engine and its stop flag, the extractor registry, `parse_error`)
- **Code:**
  - `src/spider/crawl/`: urls, scope, robots, directives, frontier, scheduler, engine, the Crawl context, `fetcher/` (interface and minimal aiohttp implementation).
  - `src/spider/extract/links.py` and the extractor registry.
  - `src/spider/store/`: `urls`, `origins`, the new `crawl` columns, the units that write them, and the transition check.
  - the Crawl Service in `src/spider/services/`, built on `015`'s `create_crawl`, and its adapter `src/spider/cli/crawl.py`.
- **New dependencies:** `aiohttp`, `protego`, `selectolax`, `msgspec` and `publicsuffixlist` (a bundled list, never downloaded at runtime), each added to `tests/dependency_allowlist.txt` and kept off the startup path.
- **Docs:** `docs/crawling.md`, the crawl tables in `docs/schema.md`, and the hook and extractor seams in `docs/architecture.md`.
