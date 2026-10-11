"Drive" means one TDD slice:
1. Write the failing test for the named scenario at the named seam, and watch it fail for the right reason.
2. Write only enough code to pass.
3. Run `uv run scripts/check.py`.
4. Commit. One task = one commit, and the message names the scenario.

Scenario names are the `#### Scenario:` titles in `specs/crawling/spec.md`. Seams are those of docs/testing.md:
- seam 1: CLI, through `run_cli`; "seam 1, subprocess" is a real `spider` process through `run_cli_process`
- seam 2: services and the store API, with a real crawl store in `temp_workspace`
- seam 3: the real crawler and aiohttp against the local fixture site
- seam 4: pure logic, table-driven, with hypothesis where the task says so
- seam 3+6: crawl the fixture site, then read the documented tables read-only with `015`'s `query` and `crawl_row`
- "fake timing": seam 2 with the fake Fetcher and `FakeClock`, for timing scenarios only
- "fixture": a new fixture-site capability, test-first in `tests/fixture_site/`, without changing what an existing route kind does

"Done when" says what must be true, not which helper to write. Names appear only where another change depends on them (design, Interface points).

**No schema-first slices:** a table, column or index is added in the slice whose scenario first needs it, through `018`'s declaration helper, with its description and `docs/schema.md` row in the same commit, so the contract test (`015`'s, extended by `018`) is never red between commits. HTTP slices add the fixture pages they need.

**Dependencies:** a new runtime dependency (`aiohttp`, `protego`, `selectolax`, `msgspec`, `publicsuffixlist`) is added in the slice that first needs it, with its line in `tests/dependency_allowlist.txt`, and the startup allowlist test (`tests/cli/test_startup.py`) must still pass without allowing it.

A **guard** is a test for a scenario that earlier code already satisfies. It passes on its first run, and it is kept to pin the contract.

**The robustness rule** (ROADMAP) applies to every task: a parser that a task adds gets its never-raises hypothesis property in that task or the one the group names, and a failure of one URL is recorded on that URL.

**The thin slice** (ROADMAP, Build order) needs groups 1–6: normalisation, the host Scope, hyperlink discovery, a foreground Crawl recorded through the writer, the hooks `030` and `040` plug into, `fetch_error` and `is_internal`. Groups 7–15 widen the change after that.

## 1. URL normalisation and Seeds (slice, seam 4)

- [ ] 1.1 Drive "Scheme and host case, the default port and the fragment are normalised" and "A non-default port is kept", a trivial pair.

  Done when: the normaliser returns a `NormalizedUrl` (design D13), the only producer of that type, or its own rejection type, and never raises.
- [ ] 1.2 Drive "Dot segments are resolved" and "An empty path becomes a slash", a trivial pair.
- [ ] 1.3 Drive "Percent-encodings are normalised".
- [ ] 1.4 Drive "Characters outside ASCII are percent-encoded".
- [ ] 1.5 Drive "An internationalised host becomes ASCII".
- [ ] 1.6 **Guard:** "The query and its parameter order are kept" and "A trailing slash is kept", a pair.
- [ ] 1.7 **Guard:** "Normalising twice changes nothing", as a hypothesis property over generated http and https URLs.
- [ ] 1.8 Drive "Normalising any text gives a URL or a rejection", as a hypothesis property over arbitrary text.
- [ ] 1.9 Drive "Matching parameters are removed". Done when: `--strip-params` patterns apply as part of normalisation, keeping the order of the other parameters.
- [ ] 1.10 Drive "Removing every parameter removes the query" and "Parameters are kept by default", a trivial pair.
- [ ] 1.11 Drive "A bare host becomes an https Seed". Done when: the Seed parser returns a `NormalizedUrl` or a rejection that the Command reports as `invalid_url`.
- [ ] 1.12 Docs: write the "URLs" part of `docs/crawling.md` (the normalisation rules, the kept trailing slash, and `--strip-params`).
- [ ] 1.13 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. Scope decisions (slice, seam 4)

- [ ] 2.1 Drive "The other scheme of the Seed host is internal" and "Another host is external by default", a trivial pair.

  Done when: `ScopeRules` (design D4) is a frozen value built from the Seed and the settings, whose decision on a `NormalizedUrl` is a pure function.
- [ ] 2.2 Drive "The www host of an apex Seed is internal".

  Done when: registrable domains come from the bundled `publicsuffixlist`, and a table test of about 20 Seed/URL cases passes: apex and `www.` both ways, other subdomains, ports, IDN hosts, public suffixes such as `co.uk`, IP addresses, single-label hosts and upper case.
- [ ] 2.3 **Guard:** "The apex of a www Seed is external".
- [ ] 2.4 Drive "Subdomains are internal with the subdomains Scope".
- [ ] 2.5 **Guard:** "A public suffix is not treated as the site".
- [ ] 2.6 Drive "The folder of a Seed page is its parent folder".
- [ ] 2.7 Drive "Exclude wins over include".
- [ ] 2.8 Docs: write the "Scope" part of `docs/crawling.md` (host rules, the apex-to-www rule and why it goes one way, `--scope`, subfolder folders, include and exclude, and a warning about slow regexes).
- [ ] 2.9 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. The link extractor (slice, seam 4)

- [ ] 3.1 Drive "A relative link is resolved against the base href".

  Done when: the link extractor takes HTML bytes, their Content-Type and the response URL, parses once with `selectolax.lexbor.LexborHTMLParser`, and returns `DiscoveredLink` values (design D5), which `030` enriches.
- [ ] 3.2 Drive "Every srcset candidate is an image Link" and "Video and audio sources are video and audio Links", a pair.
- [ ] 3.3 Drive "rel previous is a pagination Link" and "A link element of another rel is a misc Link", a pair.
- [ ] 3.4 Drive "References that are not http or https are ignored" and "A malformed reference is ignored", a trivial pair.
- [ ] 3.5 Drive "The link extractor accepts any bytes", as a hypothesis property over arbitrary bytes, Content-Types and malformed HTML.

  Done when: decoding follows design D5's order with replacement characters, in one function that `030` imports.
- [ ] 3.6 Docs: add the Link type table, with the types listed for later releases, and decoding to `docs/crawling.md`.
- [ ] 3.7 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. Walking skeleton: a foreground Spider crawl (slice)

- [ ] 4.1 Drive "An invalid Seed is rejected" at seam 1.

  Done when: `spider crawl <url>` is registered with `@command_meta(name=CRAWL, output="document", events=True)`, its adapter calls the Crawl Service, `invalid_url` is declared in `spider.output.codes`, and the Workspace holds no new crawl file.
- [ ] 4.2 Drive "The Seed is fetched and recorded" at seam 3+6.

  Done when:
  - the Crawl Service's start operation creates the Crawl with `015`'s `create_crawl`, and builds the `CrawlContext` (design D15) in one place, opening and closing `CrawlWriter` through `asyncio.to_thread`, and submits each URL's unit with `017`'s `submit_async()`, so the URL's task ends at the submit (design D2)
  - every `NewCrawl` gets both of its required fields, `secret_names` and `journal_setting`, from this first slice on; task 4.12 checks what they do
  - the `Fetcher` Protocol (design D8) has a one-hop aiohttp implementation
  - the first `urls` columns (`id`, `url`, `host`, `crawl_depth`, `discovered_via`, `fetch_state`, `status_code`) and the unique index `urls_url` are declared through `018`'s declaration helper, each enumeration with every value of design D18, with their `docs/schema.md` rows; `018`'s guard over index names switches on its assertion that it saw an index
  - every writer unit is defined in a `spider.store.*` module, follows `017` D7 (deterministic given the file's state, values as results), and its seam-2 test forces a replay with `017`'s `replay_now(writer)` (design D14); ruff's banned-API rule (TID251) bans `sqlalchemy` in `src/`, with per-file-ignores for `src/spider/store/**` and `src/spider/services/schema.py` (design D14)
- [ ] 4.3 **Guard:** "The Seed is kept as given in seeds" (seam 3+6) and "The ways a URL is found are an enumeration" (seam 1), a pair. `015`'s `create_crawl` writes the Seeds as given, and task 4.2 declared `discovered_via` from the `LinkType` `Literal` (design D5).
- [ ] 4.4 Drive "Pages linked from the Seed are crawled" at seam 3+6, and "Indexes of urls" at seam 1, a pair.

  Done when:
  - the scheduler takes queued URLs depth by depth in `urls.id` order through a writer unit that only reads and commits nothing, above a per-depth cursor of the run, over the partial index `urls_crawl_depth_id`, declared with its description (design D1)
  - hyperlinks are discovered by the page preparation function, called through the in-process executor of the `CrawlContext` (design D9)
  - new URLs are deduplicated by `urls_url` inside the URL's unit, with no in-memory map of URLs (design D1)
- [ ] 4.5 Drive "A discovered URL points to where it was found" at seam 3+6.

  Done when: `found_on_url_id` is declared with a foreign key to `urls.id`, the first in the schema, and `docs/schema.md` shows it as `018` documents references; `018`'s guard over reference columns switches on its assertion that it saw a reference.
- [ ] 4.6 Drive "The result counts a small site" and "A completed Crawl exits with code 0" at seam 1, a trivial pair.

  Done when: the result's counts come from queries over `urls`, never from counters, and the `parsed` column exists.
- [ ] 4.7 **Guard:** "The crawl Command prints one document", at seam 1.
- [ ] 4.8 Drive "Only the listed transitions are allowed" and "An early end needs a reason of its kind" at seam 4, a trivial pair; the first as a check over every pair of states.

  Done when: `TRANSITIONS` and `check_transition` exist (design D12), `StopReason` is a `Literal` next to `CrawlState`, and `015`'s `set_state` takes the `stop_reason` and checks the transition against the state it reads in the same unit.
- [ ] 4.9 Drive "A completed Crawl records its state" at seam 3+6. Done when: `crawl.stop_reason` is declared, with its values from `StopReason` and its `docs/schema.md` row.
- [ ] 4.10 Drive "The first event line is the start event" at seam 1.
- [ ] 4.11 Drive "The recorded config holds every registered crawl setting" at seam 2.

  Done when: `[crawl]` is registered in `build_app` as `"spider.crawl.settings:CrawlSettings"` and passes `010`'s table-rules test, every crawl option declares its setting with `OptionMeta(setting=...)`, `max_urls`, `max_depth` and `rate` default to `None`, and `NewCrawl.config` holds every registered table.
- [ ] 4.12 Wire `015`'s journal mode (group 8) and redaction (group 9), at seam 2.

  Done when: the `crawl` adapter always passes `spider.cli.options.secret_names(<its Click command>, <the settings tables>)` to the Crawl Service, which puts it in `NewCrawl.secret_names` (`create_crawl` redacts by itself); and the Crawl Service always sets `NewCrawl.journal_setting` from the resolved `[store] journal_mode`, `"auto"` included, since neither field has a default, so `[store] journal_mode = "delete"` gives `crawl.journal_mode` = `delete`, and a `store_wal_unavailable` warning that `create_crawl` reports reaches the result's `warnings` (and `crawl.warnings` once task 12.3 declares it).
- [ ] 4.13 Drive "spider.toml sets a crawl setting" and "A flag overrides spider.toml" at seam 1, a trivial pair.
- [ ] 4.14 Drive "Response timing is recorded" at seam 3+6.
- [ ] 4.15 Drive "The Content-Type is recorded as received" at seam 3+6.
- [ ] 4.16 Docs: write the `spider crawl` reference in `docs/crawling.md` (the result fields, the event table, exit codes, `[crawl]` keys), and the `urls` and `crawl` columns and indexes so far in `docs/schema.md`.
- [ ] 4.17 Review: run the code-review skill on group 4's commits, also against `017`'s unit contract (D7) and prebuilt statements (D9) and ADR-0005's naming rules, then refactor with the whole suite green.

## 5. Hooks, and one URL never stops the Crawl (slice)

- [ ] 5.1 Drive "An excluded URL is never requested" (seam 3) and "An excluded URL is recorded as skipped" (seam 3+6), a trivial pair. Done when: `skip_reason` is declared, and an excluded URL gets its row without a request.
- [ ] 5.2 **Guard:** "A skipped URL has no response data", at seam 3+6.
- [ ] 5.3 Drive "A registered handler sees every URL once" at seam 2.

  Done when: `Hooks` and `default_hooks()` exist (design D9), the Crawl Service takes the `Hooks` to use, a handler is pure and returns store rows, and the store writes them in the unit that records the URL's final state (design D14).
- [ ] 5.4 Drive "Post-crawl passes run before a Crawl is completed" at seam 2. Done when: a pass is a store function that submits its own units, and runs before `completed` is written.
- [ ] 5.5 Drive "An extractor error is recorded" and "The Crawl continues after an extractor error" at seam 3+6, a trivial pair. Done when: `parse_error` and `parse_error_message` are declared, and an extractor's failure is recorded as `extractor_error`, with `<name>: <type>` as its message.
- [ ] 5.6 Drive "Parse failures are counted in one warning" at seam 1.

  Done when: the Crawl Service's warning log (design D10) keeps one entry per counted warning with `details.count` and `details.first_url`, writes it to stderr when it first occurs, and `parse_failed` is declared.
- [ ] 5.7 Drive "A failing handler does not stop the Crawl" at seam 2. Done when: `handler_failed` is declared, and only the failing handler's rows are dropped.
- [ ] 5.8 Drive "Deeply nested HTML does not stop the Crawl" at seam 3+6, a hostile fixture page.
- [ ] 5.9 **Guard:** "Undecodable bytes do not stop the Crawl", at seam 3+6, a hostile fixture page. Decoding with replacement comes from task 3.5.
- [ ] 5.10 Drive "A closed port is a refused connection" at seam 3+6. Done when: `fetch_error` and `fetch_error_message` are declared, and the Fetcher returns every request failure in its result, never as an exception (design D8).
- [ ] 5.11 Fixture: a route option that resets the connection after part of the body, test-first.
- [ ] 5.12 Drive "A connection reset in the body is a connection error" at seam 3+6.
- [ ] 5.13 Drive "A URL whose rows cannot be written is recorded as an error" at seam 2.

  Done when:
  - a failed unit gets a fallback unit that records only the URL's state (`fetch_state` = `error`, `fetch_error` = `record_failed`, the error in `fetch_error_message`), and `record_failed` is declared as a value and as a counted warning
  - a failure of the crawl file itself (SQLite's FULL, IOERR, READONLY, CORRUPT, NOTADB or BUSY), a failing fallback, a failed commit or `CrawlWriterClosedError` sets the stop flag with `write_failed` instead (design D2)
- [ ] 5.14 Docs: document the Fetcher Protocol, `Hooks` and how `030` and `040` add extractors, handlers, store rows and passes, in `docs/architecture.md`; and the per-URL failure outcomes in `docs/crawling.md`.
- [ ] 5.15 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green.

## 6. Internal and External URLs over HTTP (slice)

- [ ] 6.1 Fixture: a second fixture site instance and the DNS resolver hook, which maps `site.test` and `www.site.test` to the first instance and `other.test` to the second, and fails every other name, test-first. Done when: the hook goes into the Crawl through the context builder (design D15).
- [ ] 6.2 Drive "An External URL is checked" at seam 3+6. Done when: `is_internal` and `in_scope` are declared.
- [ ] 6.3 Drive "An External origin gets its own row" at seam 3+6. Done when: the `origins` table is declared with `id`, `origin` (with the unique index `origins_origin`), `host` and `is_internal`, with its `docs/schema.md` section; `urls.origin_id` is declared NOT NULL with a foreign key to `origins.id`; and the unit that records a URL records its origin (design D18).
- [ ] 6.4 Drive "External checks can be turned off" at seam 3.
- [ ] 6.5 Drive "An unknown host is a DNS error" at seam 3+6.
- [ ] 6.6 Docs: document External URL checks and the `fetch_error` codes in `docs/crawling.md`.
- [ ] 6.7 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.

## 7. Robots directives and Link following (widening)

- [ ] 7.1 Drive "Meta robots directives are read case-insensitively" at seam 4. Done when: the robots directives parser is a pure function that `030` imports, whose fields carry `030`'s column names (design D6).
- [ ] 7.2 Drive "A header for another crawler does not apply" at seam 4.
- [ ] 7.3 Drive "A header for the robots user-agent token applies" at seam 4.
- [ ] 7.4 Drive "none means noindex and nofollow" at seam 4.
- [ ] 7.5 Drive "A directive with a value is not a user-agent prefix" at seam 4.
- [ ] 7.6 **Guard:** "The robots directives parser accepts any values", as a hypothesis property at seam 4.
- [ ] 7.7 Drive "A meta refresh target is followed" at seam 3.
- [ ] 7.8 Drive "amphtml targets are not requested" at seam 3+6.
- [ ] 7.9 Drive "A canonical in an HTTP header is followed" and "An HTTP Refresh target is followed" at seam 3, a pair. Done when: the HTTP `Link` and `Refresh` headers of in-Scope 2xx responses are read, parsed or not.
- [ ] 7.10 Drive "Links on an error page are not followed" at seam 3+6. Done when: only in-Scope 2xx HTML responses are parsed.
- [ ] 7.11 Drive "A nofollow link is not requested" at seam 3+6.
- [ ] 7.12 Drive "A page-level nofollow applies to every hyperlink" at seam 3+6.
- [ ] 7.13 Drive "A nofollow target reached through a followed Link is fetched" at seam 3+6.
- [ ] 7.14 Drive "Nofollow Links are followed on request" at seam 3+6.
- [ ] 7.15 Docs: add the robots directives rules, nofollow handling and which responses are parsed to `docs/crawling.md`.
- [ ] 7.16 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. Scope over HTTP and Section Crawls (widening)

- [ ] 8.1 Drive "URLs that differ only in stripped parameters are fetched once" at seam 3.
- [ ] 8.2 Drive "The subdomains shorthand conflicts with a subfolder Scope" at seam 1. Done when: `option_conflict` is declared.
- [ ] 8.3 Drive "A Seed without its trailing slash is rejected" at seam 1. Done when: `subfolder_is_root` is declared, with a hint built from the Seed.
- [ ] 8.4 Drive "Pages inside the folder are followed" at seam 3+6.
- [ ] 8.5 Drive "Pages outside the folder are checked but not followed" at seam 3+6.
- [ ] 8.6 Drive "A URL that matches no include pattern is checked but not followed" at seam 3+6.
- [ ] 8.7 Drive "An invalid pattern is rejected" at seam 1. Done when: `invalid_pattern` is declared, and patterns are compiled before any crawl file is created.
- [ ] 8.8 Drive "A Seed outside the Scope is rejected" at seam 1. Done when: `seed_out_of_scope` is declared.
- [ ] 8.9 Drive "A subfolder Crawl is a Section Crawl" at seam 1.
- [ ] 8.10 Drive "An include pattern makes a Section Crawl" and "Exclude patterns alone do not make a Section Crawl" at seam 3+6, a trivial pair.
- [ ] 8.11 Drive "A subfolder Scope is recorded" at seam 3+6. Done when: `crawl.scope` is declared NOT NULL, with the Seed hosts in order, and `create_crawl` writes it with the `crawl` row from a `scope` field added to `NewCrawl` (design D18).
- [ ] 8.12 Drive "A www Seed whose canonical names the apex is reported" at seam 1. Done when: `seed_base_mismatch` is declared, and the Scope is unchanged.
- [ ] 8.13 **Guard:** "A www Seed whose Links stay on www is not reported", at seam 1.
- [ ] 8.14 Docs: document Section Crawls, the recorded Scope and `seed_base_mismatch` in `docs/crawling.md`.
- [ ] 8.15 Review: run the code-review skill on group 8's commits, then refactor with the whole suite green.

## 9. Resources, Crawl Depth, limits and invariants (widening)

- [ ] 9.1 Drive "An image is checked but not parsed" at seam 3+6.
- [ ] 9.2 **Guard:** "A broken image is recorded", at seam 3+6.
- [ ] 9.3 Drive "The shortest path wins over a faster, longer one" at seam 3+6. Done when: followed URLs of depth d+1 wait for every followed URL of depth d, and checks never wait (design D3).
- [ ] 9.4 Drive "A Resource is one deeper than its Page" at seam 3+6.
- [ ] 9.5 Drive "Links beyond the limit are not requested" at seam 3+6.
- [ ] 9.6 Drive "Resources are checked beyond the depth limit" at seam 3+6.
- [ ] 9.7 Drive "The Crawl stops at the limit" at seam 1. Done when: the `stopped` end goes through `check_transition` with `max_urls`.
- [ ] 9.8 Drive "URLs not requested stay queued" at seam 3+6.
- [ ] 9.9 Drive "The limit warning says how to continue" at seam 1. Done when: `max_urls_reached` is declared, with a hint built from `spider.naming`.
- [ ] 9.10 Drive "The limit holds under concurrency" at seam 3. Done when: requests in flight count toward the limit.
- [ ] 9.11 **Guard:** "There is no limit by default" (seam 1) and "No limit is recorded as null" (seam 3+6), a pair.
- [ ] 9.12 Drive "A limit below one is rejected" at seam 1.
- [ ] 9.13 **Guard:** "Each URL is requested once", at seam 3.
- [ ] 9.14 **Guard:** "A link cycle ends", at seam 3+6.
- [ ] 9.15 **Guard:** "Followed URLs start in discovery order", at seam 3.
- [ ] 9.16 Drive "Post-crawl passes run when the URL limit stops a Crawl" at seam 2.
- [ ] 9.17 Docs: document Resources, Crawl Depth, `--max-depth`, `--max-urls` (no default, what counts) and the dispatch order in `docs/crawling.md`.
- [ ] 9.18 Review: run the code-review skill on group 9's commits, then refactor with the whole suite green.

## 10. robots.txt (widening)

- [ ] 10.1 Drive "The group for the tool's token applies" at seam 4. Done when: the robots.txt reader is on Protego and reads at most 512,000 bytes, decoded with replacement.
- [ ] 10.2 Drive "Another token can be chosen" at seam 4.
- [ ] 10.3 **Guard:** "Any robots.txt gives a decision", as a hypothesis property at seam 4.
- [ ] 10.4 Drive "robots.txt is fetched once per origin" at seam 3.
- [ ] 10.5 Drive "A disallowed URL is not requested" (seam 3) and "A disallowed URL is recorded as blocked" (seam 3+6), a trivial pair. Done when: `blocked_by_robots_txt` is declared.
- [ ] 10.6 Drive "robots.txt is stored with its origin" and "A URL that is not requested still points to its origin" at seam 3+6, a pair. Done when: the `robots_*` columns of `origins` are declared, with `robots_state` and `robots_sitemaps` NULL until robots.txt is fetched.
- [ ] 10.7 Drive "A blocked Seed is reported" at seam 1. Done when: `seed_blocked_by_robots_txt` is declared.
- [ ] 10.8 Drive "Disallowed URLs are crawled and still labelled" at seam 3+6.
- [ ] 10.9 Drive "A missing robots.txt allows everything" at seam 3+6.
- [ ] 10.10 Drive "An unreachable robots.txt blocks its origin" at seam 3+6.
- [ ] 10.11 Drive "An unreachable robots.txt of the site is reported" at seam 1. Done when: `robots_unreachable` is declared.
- [ ] 10.12 Drive "A redirected robots.txt is followed" at seam 3+6.
- [ ] 10.13 Drive "More than five robots.txt redirects count as missing" at seam 3+6.
- [ ] 10.14 Docs: document robots.txt handling (status mapping, `--ignore-robots`, `--robots-user-agent`, Crawl-delay) in `docs/crawling.md`.
- [ ] 10.15 Review: run the code-review skill on group 10's commits, then refactor with the whole suite green.

## 11. Politeness (widening)

- [ ] 11.1 Fixture: a count of the most simultaneous requests, test-first.
- [ ] 11.2 Drive "At most five requests to a host by default" and "A lower concurrency is honoured" at seam 3, a trivial pair. Done when: per-host semaphores and the global cap of design D7 bound requests.
- [ ] 11.3 Drive "A concurrency of zero is rejected" at seam 1.
- [ ] 11.4 Drive "Requests to a host are spaced by the rate", fake timing.

  Done when: the fake Fetcher exists in `tests/support/` and goes into the Crawl through the context builder with `FakeClock`, and every wait of the engine goes through the context's `Clock`.
- [ ] 11.5 **Guard:** "Crawl-delay is not applied", fake timing.
- [ ] 11.6 Drive "Many 403 responses raise one warning" at seam 1. Done when: `possible_blocking` is declared.
- [ ] 11.7 Docs: document politeness defaults in `docs/crawling.md`.
- [ ] 11.8 Review: run the code-review skill on group 11's commits, then refactor with the whole suite green.

## 12. Events, failures and backstops (widening)

- [ ] 12.1 Drive "Every stderr line is an event or a diagnostic" at seam 1.
- [ ] 12.2 **Guard:** "A warning is written as a diagnostic", at seam 1.
- [ ] 12.3 Drive "Warnings are stored as diagnostics" at seam 3+6. Done when: `crawl.warnings` is declared NOT NULL, `[]` when the Crawl is created, and holds every warning of the result, `store_wal_unavailable` included.
- [ ] 12.4 Drive "Progress events come every 10 seconds", fake timing. Done when: the `urls` counts of `progress` come from counters that the outcomes of committed units update, seeded once by a counting query when the run starts, and no count over `urls` runs for each event (design D10).
- [ ] 12.5 Drive "Events are UTF-8 on Windows (Windows)" at seam 1, subprocess, Windows in CI.
- [ ] 12.6 Drive "An unreachable Seed fails the Crawl" at seam 1. Done when: the `failed` end goes through `check_transition` with `seed_unreachable`, and the adapter returns the result as an `Outcome`.
- [ ] 12.7 Drive "An unreachable Seed is reported by one error" at seam 1. Done when: `seed_unreachable` is declared, with a hint about network access and sandboxed agents.
- [ ] 12.8 Drive "Post-crawl passes do not run for a failed Crawl" at seam 2.
- [ ] 12.9 Drive "A write failure fails the Crawl" at seam 1, with SQLite's `max_page_count` set by a test-scoped connection listener so that SQLite reports a full disk.

  Done when: `crawl_write_failed` is declared, the stop flag ends the Crawl with `write_failed`, the service records the end once through a fresh writer, and a writer's `crawl_busy` is reported as it is (exit 5). The full disk shows inside a unit; it is a failure of the file itself, never `record_failed` (design D2).
- [ ] 12.10 Drive "Losing the site fails the Crawl" at seam 1, with the reset route of task 5.11. Done when: the count of design D16 trips at `max(8, 2 × concurrency)` Internal requests in a row without a response.
- [ ] 12.11 Drive "Losing the site is reported by one error" at seam 1. Done when: `site_unreachable` is declared.
- [ ] 12.12 **Guard:** "Dead External links do not fail the Crawl", at seam 1.
- [ ] 12.13 Drive "A stuck request is ended by the watchdog", fake timing.

  Done when: `watchdog` is a `fetch_error` value; the watchdog waits on the context's `Clock` for a time computed from the settings by one pure function, `max(120 s, the Fetcher's total request deadline + 30 s)`, tested at seam 4; and a request it ends counts as one without a response for the site-lost count.
- [ ] 12.14 Docs: document warnings, the counted warnings, how a Crawl fails (stop reasons, exit codes, partial results), and the backstops in `docs/crawling.md`.
- [ ] 12.15 Review: run the code-review skill on group 12's commits, then refactor with the whole suite green.

## 13. Stopping with an interrupt (widening)

- [ ] 13.1 Drive "Ctrl+C stops a Crawl on macOS and Linux" at seam 1, subprocess, POSIX in CI.

  Done when: the signal handlers set the `StopSignal` through `loop.call_soon_threadsafe`, no `KeyboardInterrupt` reaches `010`'s runner during a Crawl, and the `stopped` end goes through `check_transition` with `interrupt`.
- [ ] 13.2 Drive "Ctrl+Break stops a Crawl on Windows (Windows)" at seam 1, subprocess, Windows in CI.
- [ ] 13.3 Drive "An interrupt is reported by one error" at seam 1, subprocess. Done when: `010`'s `interrupted` is the one error, with exit code 130.
- [ ] 13.4 **Guard:** "An interrupted Crawl keeps its queue", at seam 1, subprocess.
- [ ] 13.5 Drive "A request still running after the grace period is cancelled", fake timing. Done when: after the stop flag, requests in flight get 10 seconds of clock time and are then cancelled before their submit, so no unit is written for them.
- [ ] 13.6 Drive "A second interrupt ends the process at once" at seam 1, subprocess.
- [ ] 13.7 Docs: document interrupts, the grace period and the second interrupt in `docs/crawling.md`.
- [ ] 13.8 Review: run the code-review skill on group 13's commits, then refactor with the whole suite green.

## 14. Persistent frontier and continuing (widening)

- [ ] 14.1 **Guard:** "A killed Crawl leaves no half-recorded Page", at seam 1, subprocess, killed with `Popen.kill()`. Mark it `slow`.
- [ ] 14.2 Drive "Continuing a stopped Crawl completes it" at seam 2.

  Done when: the Crawl Service's continue operation (which `060`'s `resume` calls) accepts `stopped` and `failed` Crawls, goes back to `running` through `check_transition`, counts the URL limit over the Crawl's whole life, and inserts the `urls` row of a Seed that has none.
- [ ] 14.3 **Guard:** "Continuing does not request fetched URLs again", at seam 2.
- [ ] 14.4 Drive "Continuing clears how the Crawl ended" at seam 2, read by a handler registered for the test.
- [ ] 14.5 Drive "A failed Crawl is continued once its Seed answers" at seam 2. Done when: continuing re-queues `error` and `robots_unreachable` URLs.
- [ ] 14.6 Drive "Post-crawl passes run again after a continue" at seam 2.
- [ ] 14.7 Docs: document the frontier, what a killed Crawl keeps, and the continue operation for `060` in `docs/crawling.md`.
- [ ] 14.8 Review: run the code-review skill on group 14's commits, then refactor with the whole suite green.

## 15. Change check

- [ ] 15.1 Verify that every `#### Scenario:` in `specs/crawling/spec.md` has exactly one test named after it, with a small script over the test ids.
- [ ] 15.2 **Guard:** every code this change declares is listed by `spider commands` with its level and exit code, at seam 1.
- [ ] 15.3 Docs: the crawl pipeline section of `docs/architecture.md` says what is built (the context, the hooks, store-only units, page preparation behind the in-process executor), and `docs/schema.md` documents `urls`, `origins` and the new `crawl` columns, with their indexes and the values listed for later changes.
- [ ] 15.4 Verify that the whole suite passes in CI on Windows, macOS and Linux × Python 3.12–3.14 with the coverage gate.
- [ ] 15.5 Review: run the code-review skill on the whole change against `specs/crawling/spec.md`, then refactor with the whole suite green.
