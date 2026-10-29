> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

## Context

See proposal.md (Why) for the motivation. The approach is shaped by these constraints:

- **`020-add-crawl-core`,** re-grounded on 2026-10-14 against its code through group 6 (its first pull request), provides:
  - the `Fetcher` Protocol in `spider.crawl.fetcher`, `async def fetch(self, request: Request) -> FetchResult | FetchFailure`: one attempt and one hop, never a redirect followed, and nothing raised but cancellation (`020` D8). `Request` holds the `NormalizedUrl`. `FetchResult` is `kw_only` (`status_code`, `headers` as received, `body`, `fetched_at`, `response_time_ms`, and `header(name)`), and `FetchFailure` is a separate record of `fetch_error`, `message` (the exception's type and text) and `fetched_at`
  - the minimal `AiohttpFetcher(session, clock)`, which requests `yarl.URL(url, encoded=True)` so the request is the recorded URL. `aiohttp_fetcher(clock, resolver)` opens it with a fixed 20-second total timeout (`_REQUEST_DEADLINE_SECONDS`), aiohttp's default TLS context and a `DummyCookieJar`, and `_fetch_error` maps an exception to `dns_error`, `connection_refused`, `invalid_response` or `connection_error`
  - the context builder (`020` D15): `_crawl_context` in `spider.services.crawling` opens the writer and the Fetcher and yields the frozen `CrawlContext` (`settings`, `scope`, `clock`, `reporter`, `writer`, `fetcher`, `pages`, `hooks`, `stop`). Boundary doubles go in through it: `start_crawl(..., resolver=...)` takes the DNS resolver hook, which reaches the Fetcher's `TCPConnector`
  - `CrawlSettings` in `spider.crawl.settings`, the pydantic model of `[crawl]`, to which this change adds its keys. Options declare `OptionMeta(setting="crawl.<key>")` in `spider.cli.crawl`, and an option and its setting come with the task that applies them (`020` D11, no inert option)
  - the engine in `spider.crawl.engine`: the frontier read depth by depth (`queued_batch`, `next_depth`), one task per URL whose dispatch decision is made once with `ScopeRules.decide` (a `ScopeDecision` of `is_internal`, `in_scope` and `skip_reason`), and `RequestLimits` (`020` D7): the global cap on URL tasks, and a semaphore per host around each `fetch`
  - `Hooks` in `spider.crawl.hooks` (`extractors`, `handlers`, `passes` and `row_writers`), with `Handler`, `Pass` and `UrlResult`, the URL's row values that a handler gets, and `default_hooks()` in `spider.services.hooks`, the composition root, which lists the built-in hooks, so the crawl core never imports its plugins (`020` D9, D14)
  - `is_html_type(content_type)` in `spider.crawl.pages`, the one rule of an HTML response, which decides with the Scope and a 2xx status whether a response is parsed (`020` D5)
  - the `urls` and `origins` tables, and the enumeration values this change writes, which `020` already lists (D18): `redirect` (`discovered_via`), `max_redirects` and `url_too_long` (`skip_reason`), `timeout` and `tls_error` (`fetch_error`), and `body_too_large` (`parse_error`)
  - the fixture site's `Redirect`, `redirect_chain`, `Status` and `LargeFile` routes, the `headers`, `content_type`, `delay`, `hang` and `reset_after` options, and the request log with each request's headers. `fixture_hosts(site, other)` starts two instances, and its DNS resolver hook (`tests/fixture_site/hosts.py`) maps `site.test` and `www.site.test` to the first and `other.test` to the second, on any port
- **What `020` builds after its first pull request,** which some tasks here wait for (tasks.md names the `020` task each time): the meta refresh Link followed (task 7.7), `crawl.scope` recorded (task 8.11), Resource Links requested (task 9.1), the robots.txt loader (group 10), the per-host "next allowed start" of `--rate` (task 11.1), and the network pause, the watchdog with its `watchdog_seconds` function and the fake Fetcher of its fake-timing tasks (groups 11 and 12).
- **`015-add-crawl-store`** redacts secrets in `create_crawl`, from `NewCrawl.secret_names` (a `SecretNames(flags, settings)`): whole values become `***`, and a URL's password becomes `user:***@host` (the private `_redact_value` in `spider.store.redaction`). It has no header form yet (`Cookie: ***`), which this change adds in v0.2.
- **`017-speed-up-crawl-writer`** gives the writer that `020`'s unit per URL goes through. A unit may run twice, so the units of this change follow its D7 contract, including the hop count and the loop walk of D2.
- **`018-add-schema-conventions` and ADR-0005** set the schema rules. Every column, index and table of this change is declared through `018`'s `public_table()` (D10).
- **`010-add-workspace-and-cli-contract`** takes settings only from flags and `spider.toml`, never from environment variables. The proxy variables are its one exception, which this change owns (the workspace capability, "Proxy variables").
- **ADR-0001:** aiohttp has no HTTP/2, so `http_version` is measured with an ALPN handshake (v0.2).
- **`000-scaffold-project`:** its proxy isolation removes `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` and `ALL_PROXY`, in both cases, before every test, and it leaves HTTPS, named hosts and gzip on the fixture site to this change.

## Goals / Non-Goals

**Goals:**
- Every request policy lives behind the Fetcher interface and `020`'s Requester (`020` D7), with its retry loop and the per-host gate, so the engine's decisions (Scope, robots.txt, depth) are untouched.
- The Fetcher stays one attempt and one hop. Retries and redirects are the engine's, so `020`'s fake Fetcher drives them in the timing tests, and `020`'s watchdog races one attempt.
- Per-hop data (status, Location, timing, headers) is recorded now, so v0.2's `redirects` needs no re-crawl.
- Deterministic tests: the real aiohttp against the fixture site, with fake timing only for backoff and pauses.

**Non-Goals:**
- HTTP/2 or HTTP/3 transport, cookie sessions, and SOCKS proxies.
- Deciding what is followed (`020`).

## Decisions

### D1. The aiohttp policy Fetcher
`aiohttp_fetcher` opens the policy Fetcher in the context builder, from the resolved `CrawlSettings`, behind the same Protocol: one attempt per `fetch`, one hop, `FetchResult | FetchFailure` with nothing raised but cancellation, and the `yarl.URL(url, encoded=True)` request. The fields it adds to `FetchResult` have defaults, so `020`'s call sites and its fake Fetcher keep working. `UrlResult` gains the same row values (`content_encoding`, `size_bytes`, `transferred_bytes`, `redirect_url_id`), which `030`'s handler copies.
- **Errors:** `TimeoutError`, from which aiohttp's timeouts derive, is `timeout`. `aiohttp.ClientSSLError` is `tls_error`. It covers `ClientConnectorCertificateError`, which aiohttp raises when a certificate does not verify (a self-signed or unknown chain, a wrong name, an expired certificate), and `ClientConnectorSSLError`, for the other TLS failures. `ClientConnectorCertificateError` is a subclass of both `ClientSSLError` and `ClientConnectorError`, and `020`'s `_fetch_error` has only the `ClientConnectorError` branch, where a certificate failure falls through to `connection_error`. So the `ClientSSLError` branch comes first. A table test maps every aiohttp exception class this change meets to its `fetch_error` (`test_each_request_error_has_its_fetch_error`), so the next subclass that an earlier branch would catch fails a test, not a Crawl. The rest stay as `020` D8 maps them, a host the resolver cannot encode included (`dns_error`).
- **Timeout:** `--timeout` replaces `_REQUEST_DEADLINE_SECONDS` in `aiohttp.ClientTimeout(total=...)`, which covers the body read too, so a stalled or trickling body times out. It also feeds `020`'s `watchdog_seconds`, `max(120, timeout + 30)` (`020` D16).
- **Identity:** the session's `User-Agent` is built from `spider.naming` and the tool's version, and `--user-agent` replaces it. Its project URL is a `PROJECT_URL` constant next to `APP_NAME` in `spider.naming`, set with the product name (ruled 2026-10-14).
- **Redirects:** `allow_redirects=False` on every request, as `020`'s Fetcher does already.
- **Decoding:** `auto_decompress=False` and an explicit `Accept-Encoding`, `gzip, deflate, br` in v0.1 (ruled 2026-10-14). The Fetcher decodes gzip and deflate (`zlib`) and br (`brotli`) itself, so it measures both `transferred_bytes` and `size_bytes`. **(v0.2)** zstd (`zstandard`, or `compression.zstd` on 3.14).
- **Body limit:** the body is streamed up to 20 MiB, and its decoded size is capped at the same 20 MiB by a decoder bounded in output, so a small compressed body cannot expand past the cap. `Request` gains its dispatch decision's `in_scope`: a URL outside the Scope is only checked, never parsed (`020` D5), so when its response has a `Content-Length` and no `Content-Encoding` the Fetcher may stop after the headers and take both sizes from `Content-Length`.
- **No cookies:** `020`'s `DummyCookieJar` stays, so no cookie is ever replayed. This change pins it with a guard.
- **Environment:** `trust_env=False`, aiohttp's default, which `020` keeps, so aiohttp reads no `.netrc` and no variables by itself. The Fetcher chooses the proxy per request:
  1. **(v0.2)** `--proxy` or `[crawl] proxy` when set
  2. otherwise `urllib.request.getproxies_environment()` (any case; lower-case wins) and `proxy_bypass_environment()` for `NO_PROXY`, read when each run starts, so a resumed Crawl reads them again

  **(v0.2)** The ALPN check uses the same choice.
- **TLS:** the context of D5 goes into the `TCPConnector`, next to the resolver.
- **(v0.2) Internal URLs only:** custom headers and preemptive basic auth are added only when `Request` says the URL is internal (its dispatch decision's `is_internal`), never for External URLs. Each redirect hop is its own `Request` with its own decision, so a hop to an External URL never carries them.

### D2. Redirects are URL rows
Every hop is a normal `urls` row with its own status and timing, linked through `redirect_url_id`. The engine follows them, never the Fetcher: the unit that records a 3xx response records its target as a URL discovered from it, with `discovered_via` = `redirect` and the source's Crawl Depth, and the target goes through the Scope, robots.txt and the per-host limits like any URL.
- **Location:** it is resolved against the redirecting URL as `020`'s link extractor resolves a reference, by the URL Standard (`020` task 3.8), through a public function that this change makes of `_resolved` in `spider.crawl.links`, and then normalised. A Location that gives no `NormalizedUrl` (a scheme other than http or https, userinfo, or a malformed reference) is not usable: `redirect_url_id` stays NULL, and `redirect_location` keeps the raw text.
- **The open depth:** `020`'s engine stops reading a depth at the first empty frontier read and then waits for that depth's tasks, and `next_depth` looks only deeper. So `_crawl_depth` reads the open depth again from its cursor after its tasks end, until a read is empty while no task runs. A target recorded at the open depth in the meantime is then dispatched in the same run, and `020`'s depth barrier (D3) stays exact.
- **Hop limit:** the unit that records a 3xx response counts the consecutive redirects that led to its URL by walking `found_on_url_id` back while `discovered_via` = `redirect`, at most `--max-redirects` reads by primary key. A target beyond `--max-redirects` is recorded in that unit as `skipped` with `max_redirects`. The count comes from the file, so the unit gives the same result when it runs again (`017` D7), and a continue keeps it.
  - *Alternative:* a count per target kept in memory by the engine, as the draft had. It grows with the queued redirect targets, is lost on a continue, and goes against `020` D1, where memory follows the site's shape and not its size. Rejected at the re-grounding of 2026-10-14.
- **Loops:** when the writer stores a redirect whose target is already known, it walks `redirect_url_id` forward, bounded by the hop limit, and sets `in_redirect_loop` on every URL on a cycle. The walk reads only the file, so the unit gives the same result when it runs again (`017` D7).
- *Alternative:* a `redirect_hops` table keyed by the first URL of each chain. It stores the same hop once per chain. Rejected.
- *Alternative:* following chains inside the Fetcher. That bypasses politeness and robots.txt for each hop. Rejected.

### D3. The Seed-redirect Scope rule
The user's decision of 2026-10-14 keeps this rule in v0.1: the Scope widens once, at the end of the Seed's Redirect Chain, before the chain's final Page is prepared, and `026`'s workers start after that, with the final Scope in their settings snapshot.

`020`'s www rule (its D4) already makes `www.<host>` a Seed host of an apex Seed, so `site.test` → `www.site.test` needs nothing from this change. The rule covers the two cases that one leaves out:
- **A `www.` Seed that redirects to its apex** (`020` goes one direction only): `http://www.site.test/` → `http://site.test/`.
- **An apex that redirects to another subdomain:** `http://site.test/` → `http://en.site.test/`, or `m.`.

A chain that ends on another registrable domain (SSO, parking pages) only raises `seed_redirected_off_site`, so the Crawl never wanders onto a third-party site.

**What this change builds:**
- **The Seed's chain** is the Seed and the redirect targets recorded at Crawl Depth 0: in Spider mode only the Seed is at depth 0, and a redirect target keeps its source's depth (D2), so depth 0 with `discovered_via` = `redirect` names a hop of the Seed's chain without a walk. Each hop is requested whatever `--check-external` says, because the chain decides the Scope; the Scope's other decisions (`--exclude`, robots.txt) still apply to it, and a hop they refuse ends the chain.
- **The end of the chain** is the first hop that gets a response other than a 3xx with a usable Location, or a failure, or a target refused by the hop limit. Only a response can widen the Scope.
- **Widening:** when the final hop's host has the Seed host's registrable domain and is not a Seed host yet, the engine builds the wider `ScopeRules` with a pure function of `spider.crawl.scope` that adds the host, and `www.<host>` when the host is a registrable domain, as `020` D4 does for a Seed host. Then, before the final hop's response is parsed:
  1. the final hop's dispatch decision is made again with the wider Scope, so it is `is_internal` = 1 and `in_scope` = 1, and is parsed as a Page when it is 2xx HTML (`020` D5)
  2. the page executor gets the settings snapshot built from the wider Scope (`PageSettings`), so `DiscoveredLink.is_internal` and every later decision use it
  3. the engine goes on with a context that holds the wider `ScopeRules` (`dataclasses.replace` of the frozen `CrawlContext`, `020` D15): at depth 0 nothing else is in flight, so no task holds the old one
- **Recorded in the final hop's unit,** with no effect outside the writer's connection (`017` D7): `crawl.scope.hosts` gains the added hosts (`020` task 8.11), and the URLs and origins already recorded on them, which at that point are only earlier hops of the chain, get `is_internal` = 1 and `in_scope` = 1, so no row disagrees with the final Scope.
- **A continue** builds `ScopeRules` from the recorded `crawl.scope`, never from the Seed again, so the widened Scope survives a stop or a crash.

**Interface points it uses:**
- `020`: `ScopeRules` and `ScopeDecision` (D4); `CrawlContext` (D15), replaced once by the engine; the page executor taking a new settings snapshot before its first prepare (D9); `crawl.scope`, written by `create_crawl` (task 8.11) and updated by a unit of `spider.store.crawls`; and the continue operation (group 14) building `ScopeRules` from `crawl.scope`. The last two are wordings for `020`'s design.
- `026`: the pool starts its workers when it gets its settings snapshot, after the Seed's chain has ended, never with an earlier Scope (a wording for `026`'s design D1). The common Seed answers at once, so the chain ends at its first response, and the workers' start overlaps the Seed's own parsing no longer; that costs about one worker start (about 1 second on Windows) once per Crawl.
- *Alternative:* start the workers early with the first Scope and replace them when the Scope widens. It keeps the overlap, but adds a restart path for the rare widening. Not taken: the user's decision starts them once, with the final Scope.

### D4. Retries and backoff
- **Where:** one retry loop in `020`'s Requester (`020` D7), around the Fetcher, so a URL's own request and a robots.txt request both get it. Each attempt is one `fetch` inside the host's semaphore, raced by `020`'s watchdog on its own. Backoff waits on the context's `Clock` outside the semaphore, so a waiting retry holds none of the host's `--concurrency` slots. `020`'s fake Fetcher then drives the retries in the timing scenarios; a retry loop inside the Fetcher would bypass it.
- **Retries:** on no response, 5xx or 429, as `--retries`. The URL's unit writes `attempt_count`.
- **Backoff:** 1 s, 2 s, …, with no jitter, so fake-clock tests assert exact times.
- **Retry-After:** seconds or an HTTP date, capped at 120 s. A 429 without `Retry-After` pauses the host for 10 s.
- **Pauses** set the host's "next allowed start" in `020`'s per-host gate (D7; `RequestLimits` gains it with `--rate`, `020` task 11.1), so every request to that host waits, not only the retried one.
- **`020`'s network pause** (decided 2026-10-14): a timeout counts as a request without a response, like a refused connection; a `tls_error` does not count (ruled 2026-10-14), because a certificate failure is an answer of sorts, and a site-wide one would otherwise wait out `--network-wait` (1800 s by default) and fail as a misleading `site_unreachable`.
  - A URL counts once, when its last attempt has failed, so the count does not depend on `--retries` (ruled 2026-10-14).
  - While the Crawl is paused, an attempt that fails is neither retried nor recorded: no request starts during the pause (`020` D16), so its URL stays `queued` and is requested after the pause. An outage spends no retries and leaves no false `timeout` rows.
- **robots.txt without a response:** after its retries, a robots.txt that timed out or failed TLS gives its origin's URLs the same `fetch_error` without a request (`020` D6); one that answered 5xx or 429 stays `robots_unreachable`.

### D5. TLS trust
- **The default:** `truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)`, in a module of its own (`spider.crawl.tls`), uses the OS trust store on Windows, macOS and Linux.
- **A self-signed chain** is in no OS trust store and not in certifi's bundle, so either path refuses it as it refuses an unknown CA: `ssl.SSLCertVerificationError`, which aiohttp raises as `ClientConnectorCertificateError`, recorded as `tls_error` (D1). A test pins it on each OS (task 6.3), since each OS verifies through its own platform API.
- **The fallback:** if truststore cannot be loaded, `ssl.create_default_context(cafile=certifi.where())`.
- **Speed test:** a benchmark task measures handshake cost with truststore and with certifi on each OS, and records the result in the docs. If truststore is measurably slower, only the default path changes, not the behaviour.
- **Shared setup:** the same context is used for requests and robots.txt, and from v0.2 for the ALPN check. `080`'s `doctor` TLS check reuses it.
- **Tests:** the TLS setup accepts extra trust anchors, and tests pass the trustme CA through them. They go into a Crawl through the context builder, as the DNS resolver hook does (a keyword of `start_crawl`, `020` D15). The maintainer approved this on 2026-09-27 as a boundary double, and docs/testing.md lists it. The real TLS stack still verifies every certificate.

### D6. (v0.2) HTTP version by ALPN
There is one `asyncio.open_connection(host, port, ssl=ctx, server_hostname=host)` per https origin, with `ctx.set_alpn_protocols(["h2", "http/1.1"])`. It runs in parallel with the origin's robots.txt request and is closed right after the handshake. With a proxy, it tunnels through `CONNECT`. Any failure gives NULL.

### D7. Response headers and cookie values
- **Source:** `FetchResult.headers`, which `020`'s Fetcher decodes from aiohttp's `raw_headers` as Latin-1, keeping order and letter case.
- **Cookie redaction happens before storage,** in the exact format of the spec: `sid=abc123; Path=/` becomes `sid=***; Path=/`, and `a=1; b=2` becomes `a=***; b=***`. Names and attributes stay. The `crawl` redaction itself is `015`'s. This is value hygiene for crawled data, applied by the Fetcher to `FetchResult.headers`, so no layer ever holds a cookie value it could store.
- **How it is written:** this change's per-response handler returns one `response_headers` row for a `fetched` URL, as a frozen row type declared in a module of `spider.store` that loads no sqlalchemy. `spider.store.response_headers` registers the row's writer in `Hooks.row_writers`, and both are listed in `default_hooks()` in `spider.services.hooks` (`020` D9, D14). A URL without a response gets no row.
- **Consumers:** `030` reads cookie names and attributes from `UrlResult.headers`, so the redaction loses nothing for Page data.

### D8. What is secret
- **v0.1, the proxy variables:** the ones that are set are recorded in an `environment` table of `crawl.config`, which the Crawl Service adds to `NewCrawl.config` next to the registered tables. `environment.http_proxy` and `environment.https_proxy` are added to `SecretNames.settings`, so `015`'s `create_crawl` redacts them by its URL form (`user:***@host`), and no public `redact_url` is needed (ROADMAP's 022-min item). `no_proxy` is not a secret. A proxy URL without a password is then recorded as `***`, as `015` records every secret that has none (ruled 2026-10-14 for v0.1).
  - *Alternative:* a public `redact_url` in `spider.store.redaction` that keeps a URL without a password, called by the Crawl Service for the `environment` table. It makes the Crawl Service a second redactor. Not taken in v0.1.
- **(v0.2) The flags** declare their secret form, and `015` does all the redaction:
  - `--auth` is a whole secret, so `015` writes `***`.
  - `--header` (and the setting `crawl.header`) is a header secret. `015` redacts `Cookie`, and every header whose name contains `auth`, `token`, `secret`, `key` or `password`.
  - `--proxy` is a URL secret, so its password becomes `***`.

  Credentials in `spider.toml` are allowed, and `060`'s `resume` re-reads them from there.

  **The setting key** is `crawl.header`, a list of `Name: Value` strings, because `010`'s rule makes a setting's key the flag's long name. It keeps the curl-style `--header` flag.

### D9. Fixture site additions
Each is added test-first in `tests/fixture_site/` or `tests/support/` by the first slice that needs it, and no existing route kind or option changes what it does:
- **Named hosts:** `fixture_hosts` takes a site per name (`site.test`, `www.site.test`, `en.site.test`, `other.test`, `badcert.test`), so a host that redirects to another one is an instance of its own, and no route needs the `Host` header.
- **HTTPS listeners** with a `trustme` CA, which the DNS resolver hook maps from port 443 of a name:
  - one for `site.test`
  - one whose certificate names `other.test`, served as `badcert.test`
  - one with a certificate from a CA the test never trusts
  - one with a self-signed certificate (no CA), served as `selfsigned.test`, made with `cryptography`, which `trustme` already brings
  - **(v0.2)** one that selects `h2`, and one that offers only `http/1.1`
- **Response sequences,** a new route kind: for example 503 once and then 200.
- **Stalled and trickling bodies,** a new route option: the hostile fixtures that `020` D16 leaves to this change, with the huge page (`LargeFile`) and the compressed one.
- **Precompressed bodies:** a file under a site folder, served with `Page(file=..., headers=[("Content-Encoding", "gzip")])`, whose bytes the fixture keeps exactly. A new route kind is added only if that cannot serve one.
- **A small forward proxy** helper in `tests/support/`, which records the requests it relays.
- **No cookie-echo route:** the request log already keeps each request's headers.

### D10. The schema under ADR-0005
This change adds to `020`'s tables and adds one of its own, all through `018`'s `public_table()` (`STRICT`, and CHECKs from the declared values and flags). Each new column carries `info={"change": 22}`.
- **`urls` columns:**
  - `attempt_count` (ADR-0005 rule 5: a count ends with `_count`), NOT NULL with a default of 0, so the inserts of `020`'s units need no change
  - `redirect_location`, the raw header text
  - `redirect_url_id`, a declared reference to `urls.id`
  - `in_redirect_loop`, a `Flag` that reads as yes or no (rule 6)
  - `body_truncated`, a `Flag`
  - `content_encoding`, `size_bytes` and `transferred_bytes`
- **Enumeration values:** `redirect`, `max_redirects`, `url_too_long`, `timeout`, `tls_error` and `body_too_large` are already listed by `020` (its D18), so this change adds no value to a CHECK.
- **`urls_redirect_url_id`** on `(redirect_url_id) WHERE redirect_url_id IS NOT NULL`: it serves "which URLs redirect to this one", the reverse walk of a Redirect Chain. The forward walk reads `redirect_url_id` from the row and needs no index. The index is partial, because most URLs do not redirect, so most rows have no entry.
- **`origins.http_version`** exists from v0.1 and is NULL until v0.2's ALPN check fills it. Its description starts with `Filled from v0.2. ` (ADR-0005), so the `origins` contract does not change in v0.2.
- **`response_headers`:**
  - It has `url_id` as an `INTEGER PRIMARY KEY` (a rowid alias), with a declared reference to `urls.id`.
  - `headers` is one `Json` array per URL (ruling Q5). `080` documents a `json_each` recipe for filtering by a header.
  - It has no secondary index: `page --headers` reads one row by its key.
  - A URL without a response has no row.
- *Alternative:* one row per header. That is about 7.5M rows at 500k URLs, for a filter that no Rule or documented query needs in v0.1. Rejected by ruling Q5.

### D11. Codes
Declared as `DiagnosticCode` constants in `spider.output.codes`, as `020` D17 does, by the slice that first raises them:
- warning: `seed_redirected_off_site` (a Seed's redirect chain ends on another registrable domain; the Scope does not change)

Argument errors, such as `--header` without a colon (v0.2), use `010`'s `invalid_value` (exit 2). The values that this change writes to `urls.fetch_error`, `skip_reason` and `parse_error` (`timeout`, `tls_error`, `max_redirects`, `url_too_long`, `body_too_large`) are enumeration values that `020` lists, not diagnostic codes.

### D12. The URL length limit
`url_too_long` is decided by `ScopeRules.decide`, before its `--include` and `--exclude` patterns, so every caller (the engine's dispatch and discovery, and page preparation's `is_internal`) gets it, and no pattern of the user's ever runs over a URL longer than 2,000 characters (`020`'s Risks: ReDoS). Such a URL keeps its host's `is_internal`, has `in_scope` = 0, and is recorded as `skipped`, as `020`'s engine records any skip reason of the Scope.

## Test seams

- **HTTP (local fixture site) (3):** everything network-related. The real aiohttp runs against the fixture site's HTTP and HTTPS listeners, with named hosts behind `020`'s DNS resolver hook (`fixture_hosts`).
- **Seam 3+6:** the new columns and `response_headers` are read through a read-only connection after the Crawl, which runs through `crawl_result` (`tests/support/crawling.py`) or through the CLI (`crawled`). Both run on the real clock, since `020`'s watchdog would cut every request under a `FakeClock`, whose sleeps end at once. So a [3+6] retry test waits its real backoff (1 s, then 2 s), and only the fake-timing scenarios assert exact times.
- **Pure-logic modules (4):** the cookie redaction, and the Location resolution table.
- **Services and store API (2):** the `response_headers` writer forces a replay with `replay_now(writer)` (`017` D7).
- **CLI (1):** argument errors, recorded commands and exit codes.
- **Boundary doubles,** from the approved list:
  - **The fake Fetcher and the injectable clock:** only for "Retries wait one and then two seconds" and "Retry-After pauses the host".
  - **The DNS resolver hook:** for named hosts.
  - **A local test proxy:** for the proxy scenarios. `000`'s proxy isolation removes the proxy variables before every test, so a scenario sets them itself with `monkeypatch.setenv`.
  - **The trustme test CA:** passed into the crawler's TLS setup through the context builder. It is an approved boundary double.
- **Store contract (6):** every column, index and table is declared through `018`'s `public_table()` and documented in `docs/schema.md` by the slice that needs it. `018`'s contract test also compares the index and STRICT.

## Risks / Trade-offs

- **(v0.2)** [An extra TLS handshake per External https origin] → One per origin per run, in parallel with robots.txt, and closed right away.
- [Brotli missing on some platform, or zstd before v0.2] → brotli ships wheels for every supported platform, and zstd is in the stdlib on 3.14. An encoding the Fetcher cannot decode is not advertised.
- [A small compressed body that expands without bound (a decompression bomb)] → The 20 MiB cap applies to the decoded size too, through a decoder bounded in output (D1).
- [Stateless requests on sites that need a session cookie] → These show up as redirect loops or 403 responses, which Googlebot also meets. A cookie option is an open question.
- [truststore behaves differently per OS] → The fallback to certifi, and `doctor` (`080`) reports which trust store is in use.
- [A developer's or CI machine's proxy variables leak into tests] → `000`'s proxy isolation removes them before every test, so the fixture site is never proxied unless a scenario sets them.
- [`response_headers` takes a large share of a 500k-URL crawl file] → `026`'s 500k run reports its share; above 10%, the table keeps Internal URLs only (decided 2026-10-11).
- [A retry waiting for `Retry-After` (up to 120 s) keeps its URL task, and its place under `020`'s global cap] → The host pause makes that host's other requests wait anyway, and the cap of 20–100 tasks leaves room for other hosts.
- [Tests of this change named after no scenario, which the scenario count of task 8.1 ignores] → `test_a_trickling_body_times_out` (task 3.6), `test_a_location_that_is_no_http_url_has_no_target` (task 4.3), `test_a_compressed_body_is_capped_after_decoding` (task 5.5), `test_each_request_error_has_its_fetch_error` (task 6.2), `test_a_self_signed_certificate_is_a_tls_error` (task 6.3) and the replay test of `spider.store.response_headers` (task 7.1).

## Migration Plan

None. Before v0.1 the schema is not yet public. This change adds its columns, its index and the `response_headers` table to the declared schema and `docs/schema.md`, each in the slice that needs it, and `schema_version` stays `1` (`015` D5). It adds no enumeration value, because `020` lists them all.

## Open Questions

**To add when `020`'s network pause lands** (its group 12), with its final numbers then (ruled 2026-10-14 as a draft):
- A scenario under "Retries with backoff": "A request that fails during a network pause is not retried". WHEN `/` links to `/p1` to `/p20`, a fake Fetcher gets no response for any request after the one for `/`, and the Crawl runs with `--concurrency 1`, `--network-wait 30` and a fake clock; THEN no URL is requested again after the pause began until the Crawl ends, and the URL whose attempt failed during the pause stays `queued`.

**Deferrable, each additive:**
- `--insecure`, for staging sites with self-signed certificates.
- `--ca-cert <file>`, to trust a private CA as well as the OS store.
- SOCKS proxies (`aiohttp-socks`).
- An opt-in cookie session (`--cookies session`).
- A time-to-first-byte column (`ttfb_ms`), which needs a fixture route that delays the body after the headers.
- `--auth-file <path>`, to keep credentials out of shell history, as an alternative to `[crawl] auth` in `spider.toml`.
