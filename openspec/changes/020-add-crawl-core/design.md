> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

## Context

See proposal.md (Why) for the motivation. The approach is shaped by these constraints:

- **ADR-0001:** an own asyncio engine on aiohttp. The frontier lives in the SQLite crawl store and is the single source of truth for resume, `status` and queries during a Crawl. The Fetcher sits behind an interface.
- **`015-add-crawl-store`:**
  - one file per Crawl, and the `crawl` and `seeds` tables
  - the Crawl States `running`, `stopped`, `completed`, `failed` and `interrupted`
  - the transactional writer: units flushed in batches, so a crash loses at most the unflushed batch
  - the one-writer claim, and redaction of whole and partial secrets
  - table conventions, with `docs/schema.md` as the contract
- **`010-add-workspace-and-cli-contract`:**
  - stdout carries one JSON result, and stderr carries `{event, ts, data}` events and `{level, code, message, hint, details}` diagnostics
  - partial results: a failed outcome prints its result and exactly one error
  - the exit-code table, and the settings naming rule and precedence, with no environment variables
- **The split of the crawler:**
  - this change is the core
  - `022` adds the fetch policy (timeouts, retries, redirects, limits, compression, TLS, HTTP version, request identity)
  - `024` adds List and Sitemap modes
  - `026` may move parsing into a process pool, only if its benchmark shows parsing is the bottleneck
  - each must plug in without reworking the core
- **Platforms:** Windows, macOS and Linux × Python 3.12–3.14, using `asyncio.run(..., loop_factory=...)` with the loop wiring from `000`.

## Goals / Non-Goals

**Goals:**
- A foreground Spider-mode Crawl that behaves like Screaming Frog's spider for Scope, Link following and robots.txt, with every decision visible in `urls.fetch_state` and `urls.skip_reason`.
- A frontier that is crash-consistent at every commit, and a continue operation that `060` exposes as `resume`.
- Stable extension points for `022`–`060`: the Fetcher interface, the per-response hook, the post-crawl passes, the extractor registry and the robots directives parser.

**Non-Goals:**
- Fetch policy, other Crawl Modes and the process pool, which `022`, `024` and `026` add.
- Background processes, control rows and the `interrupted` state (`060`).
- Storing Links or Page columns (`030`), and evaluating Rules (`040`).

## Decisions

### D1. The `urls` table is the frontier
Each distinct normalised URL has one row, and its `fetch_state` (`queued` → `fetched` | `error` | `skipped`) is the queue.
- **No in-flight state:** there is no separate frontier table and no persisted "in flight" state. A URL leaves `queued` only in the writer unit that stores its response and the URLs discovered from it. After a crash, anything in flight is still `queued`.
- **Continuing:** the continue operation first re-queues URLs that ended with no response (`error`) or were blocked by an unreachable robots.txt. Those outcomes are usually transient, and this is what makes a `failed` Crawl with an unreachable Seed resumable.
- *Alternative:* a separate `frontier` table. It duplicates URL identity and needs two writes per URL. Rejected.
- *Alternative:* an in-memory queue with snapshots. It contradicts ADR-0001. Rejected.

### D2. One writer unit per completed URL
The unit of `015`'s writer is one completed URL. It holds:
- the `urls` update
- inserts for the newly discovered URLs, deduplicated through an in-memory map from URL to row id (about 100 bytes per URL, so roughly 50 MB at 500k URLs, rebuilt from the store on continue)
- whatever the per-response handlers write
- the rows of every extractor sink

The writer flushes units in batches, every second or every 500 units.

### D3. Followed URLs are dispatched depth by depth
No followed URL (an Internal URL in the Scope) at depth d+1 starts until every followed URL at depth ≤ d has been processed. Checks, meaning External URLs, URLs outside the Scope and Resources, never block that barrier. Crawl Depth is then exact however responses interleave.
- **Redirects:** `022`'s redirect targets inherit their source's depth and join the depth that is still open, so the barrier stays exact with zero-weight edges.
- *Alternative:* free order with depth lowering. Descendants of a URL whose depth was lowered late keep a wrong depth. Rejected.
- **Cost:** a stall at each boundary until the slowest internal Page of that depth is processed, bounded by the request timeout.

### D4. The Scope model
- **`ScopeRules`** is a pure function from a normalised URL to `is_internal`, `in_scope` and an optional skip reason. The host rule (`host`, `subdomains` or `subfolder`) matches on the host only, any scheme and any port. `--include`/`--exclude` come after it, and exclude wins.
- **Registrable domains** come from `publicsuffixlist`, which ships the list and never downloads it.
  - *Alternative:* `tldextract`. It downloads on first use unless configured otherwise, which is surprising network traffic for a tool without telemetry. Rejected.
- **Flag shape:** one enum plus the `--subdomains` shorthand that ROADMAP names.
  - *Alternative:* orthogonal flags. They double the combinations to test for the rare "subfolder on every subdomain" case, which `--scope subdomains --include` already covers. Rejected.
- **`--exclude` means never requested,** because it exists to keep a Crawl away from logout links, cart actions and calendars. **`--include` makes a Section Crawl**, whose outside URLs are checked but not followed, as the approved design says.

### D5. Request versus parse, and the Link type table
Two independent decisions:
- **Request** depends on the Link type table, nofollow, the Scope, robots.txt and the limits.
- **Parse** depends only on the URL being in the Scope with a 2xx HTML response. A Resource Link that returns in-Scope HTML is therefore parsed, and is not a Resource under the glossary.

**The link extractor** is ours. It parses the HTML once with selectolax, and produces:
- `DiscoveredLink` values: type, normalised target or null, raw value, element, attribute, rel tokens, nofollow, source `html|http_header`, and position in the HTML
- the page-level robots directives

The engine's discovery step consumes them. **`030` enriches** each `DiscoveredLink` with analysis attributes (anchor text, alt text, target, position in the page) through its own extractor over the same parsed tree, and stores them. It never redefines discovery.

**Decoding for discovery:** HTML is decoded in this order:
1. a byte order mark
2. the `charset` parameter of `Content-Type`
3. a `<meta charset>` in the first 1024 bytes
4. otherwise UTF-8, falling back to windows-1252

This is the same order `030` documents for text, and both go through one shared function.

### D6. robots.txt and the robots directives
- **Parsing:** Protego parses robots.txt, and the rules are cached per origin for the run.
- **Status mapping:** the RFC 9309 mapping (2xx `ok`, 4xx except 429 `missing`, 5xx/429/no response `unreachable`, more than 5 redirects `missing`) is a pure function.
- **The robots.txt request** follows its own redirects internally, up to 5 hops. It goes through the same politeness gate and counts for `--rate`, but not for `--max-urls`.
- **Crawl-delay** is recorded, not applied, which matches Googlebot and Screaming Frog.
- **The robots directives parser** is a pure function from meta `content` values, `X-Robots-Tag` header values and the robots token to the directive values. `030` imports it, so the two changes can never disagree about noindex or nofollow.

### D7. Politeness
- **Per-host limits:** a semaphore per host (`--concurrency`) and a per-host "next allowed start" time (`--rate`).
- **Global cap:** 4 × concurrency, clamped to 20–100, bounds sockets when many External hosts are checked.
- **Clock:** all waiting goes through an injectable `Clock` (`now()`, `sleep()`).
- **Blocking detection:** a counter of consecutive 403/429 responses per Internal host.
- `022` adds retry backoff and `Retry-After` pauses on the same per-host gate.

### D8. The minimal Fetcher
- **The interface:** `Fetcher.fetch(Request) -> FetchResult` makes exactly one hop and never follows redirects. `022` adds policy around it without changing it.
- **The aiohttp implementation in this change:**
  - raw response headers in order and letter case
  - a fixed 20-second timeout, which `022` makes configurable
  - aiohttp's default TLS context, which `022` replaces with truststore
  - a DNS resolver hook
- **Errors** map to `fetch_error` as follows: name resolution → `dns_error`, `ConnectionRefusedError` → `connection_refused`, protocol errors → `invalid_response`, other client errors → `connection_error`.

### D9. Hooks and the extractor registry
- **Registries:** explicit module-level registries, with no plugin discovery:
  - extractors, which run on a parsed tree and return msgspec structs
  - sinks, which turn those structs into rows inside the URL's writer unit
  - per-response handlers
  - post-crawl passes
- **Where extractors run:** in the crawl process in this change. If `026` builds its pool (only if its benchmark shows parsing is the bottleneck), it moves the same extractor functions into worker processes without changing their signatures.
- **Per-response handlers** run for every URL that reaches a final state, including `error` and `skipped`. So `030` can record cookies on any status and header Links on non-HTML responses, and `040` can evaluate Rules on single URLs.
- **Post-crawl passes** run when a Crawl ends as `completed` or `stopped`, before its final Crawl State is written:
  - `030` computes inlink counts there, and `040` evaluates the Rules that span several Pages.
  - They run again after every continued run.
  - They do not run for a Crawl that ends as `failed` or whose process was killed.

### D10. Events, result, exit codes and interrupts
- **Events and diagnostics:** an event bus feeds a stderr writer.
  - It writes `{event, ts, data}` lines as UTF-8 bytes plus LF to `sys.stderr.buffer`.
  - Warnings go through `010`'s diagnostics writer, once per code per host, and are kept for the result and `crawl.warnings`.
  - `progress` is fixed at every 10 seconds. `--progress-interval` was cut from v0.1.
- **The result:** printed on stdout whenever the Crawl ends. A failed outcome adds exactly one error diagnostic, following `010`'s partial-result rule:
  - `interrupted` → exit 130
  - `seed_unreachable` → exit 8
  - `crawl_write_failed` → exit 7
- **Interrupts:**
  - The Crawl runs under `asyncio.Runner`. `signal.signal` handles SIGINT (plus SIGBREAK on Windows, and SIGTERM/SIGHUP on POSIX) and sets the stop flag through `loop.call_soon_threadsafe`, because Windows loops have no `add_signal_handler`.
  - A second interrupt calls `os._exit(130)`. The last committed unit keeps the store consistent (D1).
  - The same stop flag is what `060`'s control rows set.

### D11. Settings and the recorded config
- **Declaring settings:** every crawl option registers its `crawl.<key>` setting, its default and its secret form in `010`'s settings registry. `022`, `024` and `030` register theirs the same way. The recorded config is built from that registry, so settings that later changes add (`022`'s fetch settings, `030`'s `store_html`) are recorded without touching this change, and the scenario "The recorded config holds every registered crawl setting" stays generic.
- **Redaction:** secrets are redacted by `015`.
- **`--subdomains`** is resolved into `scope` before recording.

## Test seams

Seams from docs/testing.md:
- **Pure-logic modules (4):**
  - URL normalisation: table-driven, plus a hypothesis property that normalising twice changes nothing.
  - `--strip-params`, the Seed parser and `ScopeRules`.
  - The robots.txt status mapping and token groups, and the robots directives parser.
  - The link extractor (HTML bytes and URL in, Links out).
- **HTTP (local fixture site) (3):** the real engine and the real aiohttp against the plain-HTTP fixture site from `000`. aiohttp is never mocked. Multi-host scenarios (`site.test`, `other.test`) use two fixture site instances behind the **DNS resolver hook**, an allowed boundary double. This change adds the hook and a count of the most simultaneous requests to the harness, test-first.
- **Seam 3+6:** crawl the fixture site, then read `urls`, `origins`, `crawl` and `seeds` through a read-only connection.
- **CLI (1):**
  - Exit codes, stdout and stderr JSON, through `CliRunner`.
  - Real subprocess runs on each OS: SIGINT on POSIX, CTRL_BREAK_EVENT to a new process group on Windows, kill/TerminateProcess, and UTF-8 bytes on Windows.
- **Services and store API (2):** the Crawl Service's start and continue operations with a real crawl store in a temporary Workspace. Test handlers, test post-crawl passes and test extractors are **registered through the public registries** that `026`, `030` and `040` use. That is using the extension point, not replacing our code.
- **Store contract (6):** `docs/schema.md` gains every column in the same commit as the slice that adds it, so `015`'s contract test never goes red between commits.

Boundary doubles used, all from the approved list:
- **The fake Fetcher and the injectable clock:** for rate spacing, Crawl-delay and the progress interval only.
- **The DNS resolver hook:** for the multi-host scenarios.
- **File-system fault injection:** for "disk full".

## Risks / Trade-offs

- [Depth barrier stalls on a slow internal Page] → Checks never block the barrier, and the stall is bounded by the request timeout.
- [SQLite write throughput once `030` adds tens of millions of Link rows] → Batched units through `015`'s writer in WAL mode, measured by `026`'s 500k benchmark.
- [User-supplied regexes applied to URLs controlled by the site (ReDoS)] → `022` caps URL length at 2,000 characters, and docs/crawling.md warns against nested quantifiers.
- [Protego differs from Google's parser on edge cases] → The status mapping is ours and tested, and matching edge cases are pinned in pure-logic tests.
- [The Public Suffix List snapshot goes stale] → `publicsuffixlist` releases often, and the pin is updated with every release.
- [Windows delivers console control events to every process on the console] → CTRL_BREAK tests start the crawler in a new process group.

## Migration Plan

The new tables and columns go into the squashed v0.1 migration under `015`'s conventions. There is nothing to migrate from earlier crawl files.

## Open Questions

These are deferrable: each would add a flag or column later without changing these specs.
- `--resolve host:port:address`, to crawl a pre-launch server under the production host name.
- Screaming Frog-style store/crawl switches per Link type, for example crawling `amphtml`.
- An opt-in cookie session, for sites that gate on a session cookie.
- Refusing External checks of private or link-local addresses, for example `169.254.169.254`, when crawling from cloud machines.
- A `robots_matched_line` column, Screaming Frog's "Matched Robots.txt Line", as a v0.2 candidate.
- Reading `<meta name="<token>">` for the robots user-agent token. `030` does not read crawler-specific meta elements in v0.1.
- A human-readable progress line when stderr is a terminal and `--format table` is used.
