## Context

See proposal.md (Why) for the motivation. The approach is shaped by these constraints:

- **`020-add-crawl-core`** provides:
  - the `Fetcher` Protocol in `spider.crawl.fetch.fetcher`, `async def fetch(self, request: Request) -> FetchResult | FetchFailure`: one attempt and one hop, never a redirect followed, and nothing raised but cancellation (`020` D8). `Request` holds the `NormalizedUrl`. `FetchResult` holds the status, the headers as received, the body and the timing, and `FetchFailure` the `fetch_error`, its message and the time
  - the minimal `AiohttpFetcher`, with a fixed 20-second total timeout, aiohttp's default TLS context and a `DummyCookieJar`, and `fetch_error_of`, which maps an exception to a `fetch_error`
  - the Requester in `spider.crawl.fetch.requester`, through which a URL's request and robots.txt go, with the per-host slots and `RateGate` of `spider.crawl.fetch.politeness`
  - the context builder (`020` D15) in `spider.services.crawling`, which opens the writer and the Fetcher and yields the frozen `CrawlContext`
  - `CrawlSettings` in `spider.crawl.settings`, to which this change adds its keys, and options with `OptionMeta(setting="crawl.<key>")` in `spider.cli.crawl`, declared by the task that applies them (`020` D11)
  - the engine in `spider.crawl.engine`: `dispatch` reads the frontier depth by depth, and `units` makes one unit per URL from its `UrlResult`, whose outcome is a `UrlResponse` (`response`) or a `UrlFailure` (`failure`), from which the store record is built (`020` task 5.20)
  - `Hooks` in `spider.crawl.engine.hooks`, with `handler(name, handle, write)`, whose writer takes a URL's rows as one sequence (`020` task 5.19), and `default_hooks()` in `spider.services.hooks`, the composition root (`020` D9, D14)
  - `resolve_reference` in `spider.crawl.references`, by which a Link's reference is resolved, and from `020` task 5.23 the Link following rule in `spider.crawl.following`
  - the `urls` and `origins` tables, and the enumeration values this change writes (`020` D18): `redirect` (`discovered_via`), `max_redirects` and `url_too_long` (`skip_reason`), `timeout` and `tls_error` (`fetch_error`), and `body_too_large` (`parse_error`)
  - the fixture site's `Redirect`, `redirect_chain`, `Status` and `LargeFile` routes, the `headers`, `content_type`, `delay`, `hang` and `reset_after` options, the request log with each request's headers, and `fixture_hosts(site, other)`, whose DNS resolver hook maps `site.test` and `www.site.test` to one instance and `other.test` to another, on any port
- **What `020` has not merged yet,** which some tasks here wait for (tasks.md names each): the scenario script (task 16.1).
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
**In short:** one frozen `FetchPolicy` carries every request setting from the Crawl's plan to the Fetcher, which stays one attempt and one hop behind `020`'s Protocol.
- **The policy:** `plan_crawl` builds `FetchPolicy` from the resolved `CrawlSettings` and the proxy variables: the user agent, the timeout and the proxy snapshot. The Crawl Service opens the Fetcher through one factory that takes the policy and the clock, which replaces `start_crawl`'s `resolver=` and `fetcher=` keywords. Tests pass a factory with the DNS resolver hook, the test CA or a fake Fetcher bound in, and `crawl_result` builds one from its own keywords. A new request setting is then a field of the policy, not a keyword of `start_crawl` (`020` D15).
  - *Alternative: a keyword of `start_crawl` per setting.* The user agent, the proxy, the timeout, decoding and trust anchors would widen it five times, and every test helper with it. Rejected.
- **The values it adds:** `FetchResult` gains only `body_truncated` and `transferred_bytes`, with defaults, so `020`'s fake Fetcher keeps working. The URL's unit derives the rest for `UrlResponse` and the store record: `content_encoding` through the one header lookup, and `size_bytes` as the body's length, NULL for a capped body. A redirect's target id is assigned in the URL's unit, so it is never on `UrlResult`; `030` reads `urls.redirect_url_id`.
- **Errors:** `TimeoutError`, from which aiohttp's timeouts derive, is `timeout`. `aiohttp.ClientSSLError` (a certificate that does not verify, or another TLS failure) is `tls_error`, tested before `020`'s `ClientConnectorError` branch, which would make it `connection_error`. The rest stay as `020` D8 maps them, a host the resolver cannot encode included (`dns_error`).
- **Timeout:** `--timeout` sets `FetchPolicy.timeout_seconds`, 20 until then, which goes into `aiohttp.ClientTimeout(total=...)`, which covers the body read too, so a stalled or trickling body times out. It also feeds `020`'s `watchdog_seconds`, `max(120, timeout + 30)` (`020` D16).
- **Identity:** the session's `User-Agent` is built from `APP_NAME`, `spider.__version__` and `PROJECT_URL`, and `--user-agent` replaces it. `PROJECT_URL` is one constant next to `APP_NAME` in `spider.naming`: the repository's URL until the product is named, changed with the name.
- **Redirects:** `allow_redirects=False` on every request, as `020`'s Fetcher does already.
- **Decoding:** `auto_decompress=False` and an explicit `Accept-Encoding`, `gzip, deflate, br` in v0.1. The Fetcher decodes gzip and deflate (`zlib`, with raw deflate as the fallback) and br (`brotli`) itself, so it measures both `transferred_bytes` and `size_bytes`.
  - **One body reader:** `read_body(chunks, coding, limit)` in `spider.crawl.fetch.body` reads the stream up to the cap and chains the bounded decoders, several codings in the reverse order of `Content-Encoding` (RFC 9110 8.4.1). Its [Pure] tests run on real compressed bytes: a bomb, a truncated body, raw deflate and a corrupt stream.
  - **A body that fails to decode** is `invalid_response`. **A coding that was not offered,** such as zstd in v0.1, is a server that ignored the negotiation: the body is kept undecoded, `size_bytes` is NULL, and an HTML body gets `parse_error` = `unsupported_encoding` instead of being prepared. **(v0.2)** zstd (`zstandard`, or `compression.zstd` on 3.14).
- **Body limit:** the body is streamed up to 20 MiB, and its decoded size is capped at the same 20 MiB by a decoder bounded in output, so a small compressed body cannot expand past the cap. A capped body has `body_truncated`, `transferred_bytes` the bytes read, and `size_bytes` NULL, since its full size was not measured; the URL's unit gives a capped HTML body `parse_error` = `body_too_large` instead of preparing it.
  - **(v0.2)** `Request` gains its dispatch decision's `in_scope`: a URL outside the Scope is only checked, never parsed (`020` D5), so when its response has a `Content-Length` and no `Content-Encoding` the Fetcher may stop after the headers and take both sizes from `Content-Length`. The 20 MiB cap bounds such a body in v0.1.
- **No cookies:** `020`'s `DummyCookieJar` stays, so no cookie is ever replayed. This change pins it with a guard.
- **Environment:** `trust_env=False`, aiohttp's default, which `020` keeps, so aiohttp reads no `.netrc` and no variables by itself. The Fetcher chooses the proxy per request:
  1. **(v0.2)** `--proxy` or `[crawl] proxy` when set
  2. otherwise `ProxyVariables` in `spider.crawl.fetch.proxy`: `HTTP_PROXY`, `HTTPS_PROXY` and `NO_PROXY` read once from the environment into `FetchPolicy` when each run starts, so a resumed Crawl reads them again, and the `environment` table of D8 records the same record. It applies the spec's rule itself: the lower-case name wins, an empty variable is unset, a proxy without a scheme is an http proxy, as curl reads it, and `NO_PROXY` names hosts and domain suffixes.
     - *Alternative: urllib's `getproxies_environment()` and `proxy_bypass_environment()`.* The second is undocumented and has no type stubs, both read every scheme's variable, `ALL_PROXY` included, and the bypass also matches ports and IP addresses, which the spec does not define. Rejected.

  **(v0.2)** The ALPN check uses the same choice.
- **TLS:** the context of D5 goes into the `TCPConnector`, next to the resolver.
- **(v0.2) Internal URLs only:** custom headers and preemptive basic auth are added only when `Request` says the URL is internal (its dispatch decision's `is_internal`), never for External URLs. Each redirect hop is its own `Request` with its own decision, so a hop to an External URL never carries them.

### D2. Redirects are URL rows
**In short:** every hop is a `urls` row linked through `redirect_url_id`, and the engine, never the Fetcher, follows it as a URL of its own.

The unit that records a 3xx response records its target as a URL discovered from it, with `discovered_via` = `redirect` and the source's Crawl Depth, and the target goes through the Scope, robots.txt and the per-host limits like any URL. A redirect is not a Link: no Link type, nofollow or Link following rule applies to it.
- **The decision:** `REDIRECT_STATUSES` (301, 302, 303, 307 and 308) and the pure `redirect_target(url, status, location, strip_params)` live in `spider.crawl.following`, beside `020`'s Link following rule, which a redirect never goes through. The robots.txt loader calls the same function, and `UrlResponse.redirect_target` carries its result to the unit and the handlers. A 300, 304 or 305 keeps its `redirect_location` and has no target.
- **The insert:** one `insert_urls` helper in `spider.store.urls` records the rows' origins before it inserts them, and every inserter goes through it: today an inserter that forgot `record_origins` would get a NULL `origin_id`, an integrity error, and a silent `record_failed`. A target is inserted at its source's depth, a Link's target at depth + 1.
- **Resource status:** a Resource's target stays a Resource; any other target is decided by its own Scope. A target keeps the way its chain was found, so a redirected Resource beyond `--max-depth` is still checked, and the depth barrier treats it as a Resource. An in-Scope target of an External or out-of-Scope URL is a Page of the site like any other, and an off-site target is checked by its own decision anyway.
  - *Alternative:* every target keeps its source's checked status. The outcome would then depend on order: an internal Page first reached through an External redirect would be fetched as checked and never parsed, even after an internal hyperlink reaches it, since a fetched row is not decided again. Rejected.
- **Location:** `redirect_target` resolves it against the redirecting URL through `020`'s `resolve_reference`, with the Crawl's `strip_params`, so URL resolution stays in one place, and then normalises it. A Location that gives no `NormalizedUrl` (a scheme other than http or https, userinfo, or a malformed reference) is not usable: `redirect_url_id` stays NULL, and `redirect_location` keeps the raw text.
- **The open depth:** `020`'s engine stops reading a depth at the first empty frontier read and then waits for that depth's tasks, and `next_depth` looks only deeper. So `_crawl_depth` reads the open depth again after its tasks end, until a read is empty while no task runs, skipping the URLs still in flight. A target recorded at the open depth in the meantime, or a URL lowered to it below the read cursor, is then dispatched in the same run, and `020`'s depth barrier (D3) stays exact.
- **Shortest paths:** a redirect is an edge of weight 0 that is not a Link, so `030`'s shortest-path pass over the stored Links agrees with the engine's depths (`020` D5) only if it walks `urls.redirect_url_id` at weight 0 too.
- **Hop limit:** the unit that records a 3xx response counts the consecutive redirects that led to its URL by walking `found_on_url_id` back while `discovered_via` = `redirect`, at most `--max-redirects` reads by primary key. A target beyond `--max-redirects` is recorded in that unit as `skipped` with `max_redirects`. The count comes from the file, so the unit gives the same result when it runs again (`017` D7), and a continue keeps it.
  - *Alternative:* a count per target kept in memory by the engine, as the draft had. It grows with the queued redirect targets, is lost on a continue, and goes against `020` D1, where memory follows the site's shape and not its size. Rejected.
- **Loops:** when the writer stores a redirect whose target is already known, it walks `redirect_url_id` forward, bounded by the hop limit, and sets `in_redirect_loop` on every URL on a cycle. The walk stops at a URL it has already seen, so a redirect into a cycle that does not run through it, such as `/x` → `/cart` while `/cart` and `/login` send each other back, ends at once. The walk reads only the file, so the unit gives the same result when it runs again (`017` D7).
- *Alternative:* a `redirect_hops` table keyed by the first URL of each chain. It stores the same hop once per chain. Rejected.
- *Alternative:* following chains inside the Fetcher. That bypasses politeness and robots.txt for each hop. Rejected.

### D3. The Seed-redirect Scope rule
**In short:** a Seed whose Redirect Chain ends on another host of its registrable domain widens the Scope once, when the chain ends; one that ends on another registrable domain only raises a warning.

`020`'s www rule (its D4) already makes `www.<host>` a Seed host of an apex Seed, so `site.test` → `www.site.test` needs nothing from this change. This rule covers a `www.` Seed that redirects to its apex, and an apex that redirects to another subdomain, such as `en.` or `m.`. It is in v0.1. A redirect to another registrable domain (SSO, parking pages) raises `seed_redirected_out_of_scope`, so the Crawl never wanders onto a third-party site.
- **A provisional Scope while the chain is open:** `Run` holds the Seed chain's state, open from the Seed's 3xx response with a provisional Scope that admits the hosts of the Seed's registrable domain. Only a redirect target of the Seed's chain is decided with it, and no other URL ever is: no Link exists before the chain ends, since a chain is made of 3xx responses. Without it, a www Seed's apex target would be decided External and skipped before the chain could end on it.
- **Closed once, by the final URL's unit:** after its response, before page preparation, it writes `is_internal` and `in_scope` of every URL of the chain against the final Scope, so no hop keeps values of a Scope that no longer exists. When the chain ends on a host of the Seed's registrable domain with a response, the unit also appends that host to `crawl.scope.hosts`. The Scope is then the chain's wider one, and the chain is the one place the current Scope is read from: the context keeps only the planned Scope, under a name that says so, which the chain starts from. Page preparation starts with the chain's Scope, so its snapshot, which `026`'s workers start with, holds the wider Scope.
- **A chain cut short:** when its last target is never requested, skipped with `max_redirects` or refused by `--max-urls`, the fallback close after depth 0 walks `redirect_url_id` from the Seed in the store, at most `--max-redirects` + 1 point reads. The URL the walk ends on is the final URL, and every URL on it is a URL of the chain, so one stored fact gives both, with no join kept in memory.
- **Out of the Crawl's Scope:** a chain that ends on another registrable domain, or under `--scope subfolder` outside the Seed's folder, widens nothing and raises `seed_redirected_out_of_scope`, whose hint names the final URL as the Seed to use.
  - *Alternative:* widen the section to the final URL's folder. `/blog/` → `/` would silently turn a section crawl into a whole-site crawl. Rejected.
- **No widening** when the chain ends outside the Crawl's Scope, in a `fetch_error` or in a skip: every URL of the chain is classified by the Seed's own Scope. A continue rebuilds the Scope from `crawl.scope`. Under `--scope subdomains` the Scope already holds every host of the registrable domain, so nothing widens.
  - *Alternative: a one-shot callback on `Run`* that the final unit calls. It hides the chain's state in a closure that a test cannot inspect, and a second call is a silent no-op instead of a visible state. Rejected for the explicit state.
- **The Seed's checks:** `020`'s `seed_base_mismatch` and `seed_blocked_by_robots_txt` read the URL that the Seed's chain ends on, since the Seed itself answered with a redirect.

### D4. Retries and backoff
- **Where:** one retry loop in `020`'s Requester (`020` D7), around the Fetcher, so a URL's own request and a robots.txt request both get it. Each attempt is one `fetch` that takes the host's slot and its `--rate` turn again, raced by `020`'s watchdog on its own. Backoff waits on the context's `Clock` outside the slot, so a waiting retry holds none of the host's `--concurrency` slots.
- **`--max-urls`:** a retry is the same URL, so only the first attempt counts towards the limit, and a retry is never refused by it. `020`'s fake Fetcher then drives the retries in the timing scenarios; a retry loop inside the Fetcher would bypass it.
- **Retries:** on a failure that may pass, `timeout`, `connection_refused` or `connection_error`, and on 5xx or 429, as `--retries`, at most 10, since a doubling backoff past that waits hours for one URL. `--max-redirects` is capped the same way, at 50: a longer chain is a misconfiguration, and each hop is a request. `dns_error`, `tls_error` and `invalid_response` are the server's or the name's answer, and a retry would only add 1 + 2 seconds per URL, which multiplies over the dead External domains a real site links to; `watchdog` has already waited past `--timeout`. A network-wide outage, DNS down or Wi-Fi off, is `020`'s network pause, not the retry loop's.
  - *Alternative: retry every request without a response.* Each dead link to a gone domain would then cost the full backoff for no chance of an answer. Rejected.
- **The count:** `Requester.request_url` returns the outcome with its attempt count, which `UrlResult` carries as a top-level field, since a skip has neither a response nor a failure and a robots.txt failure made no request for the URL. `FetchedUrl` and `ErroredUrl` copy it into `attempt_count`.
- **Backoff:** 1 s, 2 s, …, with no jitter, so fake-clock tests assert exact times.
- **Retry-After:** seconds or an HTTP date, capped at 120 s. A 429 without `Retry-After` pauses the host for 10 s.
- **Pauses** set the host's "next allowed start" in `020`'s `RateGate`, which then acts without `--rate` too, so every request to that host waits, not only the retried one. A pause is politeness toward the host and a retry belongs to the URL, so a 429 or a `Retry-After` pauses the host even when the URL has no retry left.
- **`020`'s network pause**: a timeout counts as a request without a response, like a refused connection; a `tls_error` does not count, because a certificate failure is an answer of sorts, and a site-wide one would otherwise wait out `--network-wait` (1800 s by default) and fail as a misleading `site_unreachable`.
  - A URL counts once, when its last attempt has failed, so the count does not depend on `--retries`.
  - While the Crawl is paused, an attempt that fails is neither retried nor recorded: no request starts during the pause (`020` D16), so its URL stays `queued` and is requested after the pause. An outage spends no retries and leaves no false `timeout` rows.
- **robots.txt without a response:** after its retries, a robots.txt that timed out or failed TLS gives its origin's URLs the same `fetch_error` without a request (`020` D6); one that answered 5xx or 429 stays `robots_unreachable`.

### D5. TLS trust
- **The default:** `truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)`, in a module of its own (`spider.crawl.fetch.tls`), uses the OS trust store on Windows, macOS and Linux. truststore and certifi are imported only from `spider.crawl.fetch`, which `--help` never loads.
- **The fallback:** if truststore cannot be loaded, `ssl.create_default_context(cafile=certifi.where())`.
- **Speed test:** a benchmark task measures handshake cost with truststore and with certifi on each OS, and records the result in the docs. If truststore is measurably slower, only the default path changes, not the behaviour.
- **Shared setup:** the same context is used for requests and robots.txt, and from v0.2 for the ALPN check. `080`'s `doctor` TLS check reuses it.
- **Tests:** the TLS setup accepts extra trust anchors, and tests pass the trustme CA through them. They go into a Crawl through the Fetcher factory of D1, as the DNS resolver hook does. It is an approved boundary double, and docs/testing.md lists it. The real TLS stack still verifies every certificate.

### D6. (v0.2) HTTP version by ALPN
There is one `asyncio.open_connection(host, port, ssl=ctx, server_hostname=host)` per https origin, with `ctx.set_alpn_protocols(["h2", "http/1.1"])`. It runs in parallel with the origin's robots.txt request and is closed right after the handshake. With a proxy, it tunnels through `CONNECT`. Any failure gives NULL.

### D7. Response headers and cookie values
- **Source:** `FetchResult.headers`, which `020`'s Fetcher decodes from aiohttp's `raw_headers` as Latin-1, keeping order and letter case, and which reaches `UrlResponse.headers`.
- **Cookie redaction happens before storage,** in the exact format of the spec: `sid=abc123; Path=/` becomes `sid=***; Path=/`, and `a=1; b=2` becomes `a=***; b=***`. Names and attributes stay. The `crawl` redaction itself is `015`'s. This is value hygiene for crawled data, applied where the Fetcher decodes the received headers, so no layer ever holds a cookie value it could store.
- **How it is written:** `handler("response_headers", handle, write)` in `default_hooks()` (`020` D9, D14). `handle` returns one row for a `UrlResult` with a `response`, and none otherwise; it reads the engine's `UrlResult`, so it lives outside `spider.store`, which imports nothing of the engine. The row type is declared in `spider.store.records`, and the writer in `spider.store.response_headers` takes the URL's rows as one sequence.
- **A plain INSERT:** a URL never gets a second row, so a duplicate is a bug that surfaces as `record_failed`. A replayed unit runs after its batch is rolled back; a `fetched` URL is never queued again; and retries stay in the Requester, so one unit carries the last attempt.
  - *Alternative: `ON CONFLICT(url_id) DO UPDATE`.* It would hide such a bug as a silent overwrite. Rejected.
- **Consumers:** `030` reads cookie names and attributes from `UrlResult.headers`, so the redaction loses nothing for Page data.

### D8. What is secret
- **v0.1, the proxy variables:** the ones that are set are recorded in an `environment` table of `crawl.config`, which the Crawl Service adds to `NewCrawl.config` next to the registered tables. `environment.http_proxy` and `environment.https_proxy` are added to `SecretNames.settings`, so `015`'s `create_crawl` redacts them by its URL form (`user:***@host`), and no public `redact_url` is needed (ROADMAP's 022-min item). `no_proxy` is not a secret. A proxy URL without a password is then recorded as `***`, as `015` records every secret that has none.
  - *Alternative:* a public `redact_url` in `spider.store.redaction` that keeps a URL without a password, called by the Crawl Service for the `environment` table. It makes the Crawl Service a second redactor. Not taken in v0.1.
- **(v0.2) The flags** declare their secret form, and `015` does all the redaction:
  - `--auth` is a whole secret, so `015` writes `***`.
  - `--header` (and the setting `crawl.header`) is a header secret. `015` redacts `Cookie`, and every header whose name contains `auth`, `token`, `secret`, `key` or `password`.
  - `--proxy` is a URL secret, so its password becomes `***`.

  Credentials in `spider.toml` are allowed, and `060`'s `resume` re-reads them from there.

  **The setting key** is `crawl.header`, a list of `Name: Value` strings, because `010`'s rule makes a setting's key the flag's long name. It keeps the curl-style `--header` flag.

### D9. Fixture site additions
Each is added test-first in `tests/fixture_site/` or `tests/support/` by the first slice that needs it, and no existing route kind or option changes what it does:
- **Named hosts:** `fixture_hosts` takes a site per name (`site.test`, `www.site.test`, `other.test`, `badcert.test`), so a host that redirects to another one is an instance of its own, and no route needs the `Host` header.
- **HTTPS listeners** with a `trustme` CA, which the DNS resolver hook maps from port 443 of a name:
  - one for `site.test`
  - one whose certificate names `other.test`, served as `badcert.test`
  - one with a certificate from a CA the test never trusts
  - **(v0.2)** one that selects `h2`, and one that offers only `http/1.1`
- **Response sequences,** a new route kind: for example 503 once and then 200.
- **Stalled and trickling bodies,** a new route option: the hostile fixtures that `020` D16 leaves to this change, with the huge page (`LargeFile`) and the compressed one.
- **Precompressed bodies:** a file under a site folder, served with `Page(file=..., headers=[("Content-Encoding", "gzip")])`, whose bytes the fixture keeps exactly. A new route kind is added only if that cannot serve one.
- **A small forward proxy** helper in `tests/support/`, which records the requests it relays.
- **No cookie-echo route:** the request log already keeps each request's headers.

### D10. The schema under ADR-0005
This change adds to `020`'s tables and adds one of its own, all through `018`'s `public_table()` (`STRICT`, and CHECKs from the declared values and flags). `response_headers` passes `change=22`; the columns added to `urls` and `origins` carry no change tag, since `public_table()` tags tables only.
- **`urls` columns:**
  - `attempt_count` (ADR-0005 rule 5: a count ends with `_count`), NOT NULL with a default of 0, so the inserts of `020`'s units need no change
  - `redirect_location`, the raw header text
  - `redirect_url_id`, a declared reference to `urls.id`
  - `in_redirect_loop`, a `Flag` that reads as yes or no (rule 6)
  - `body_truncated`, a `Flag`
  - `content_encoding`, `size_bytes` and `transferred_bytes`
- **Enumeration values:** `redirect`, `max_redirects`, `url_too_long`, `timeout`, `tls_error` and `body_too_large` are already listed by `020` (its D18). This change adds one value, `unsupported_encoding`, to `parse_error`'s CHECK and its `Literal`.
- **`urls_redirect_url_id`** on `(redirect_url_id) WHERE redirect_url_id IS NOT NULL`: it serves "which URLs redirect to this one", the reverse walk of a Redirect Chain. The forward walk reads `redirect_url_id` from the row and needs no index. The index is partial, because most URLs do not redirect, so most rows have no entry.
- **`origins.http_version`** exists from v0.1 and is NULL until v0.2's ALPN check fills it. Its description starts with `Filled from v0.2. ` (ADR-0005), so the `origins` contract does not change in v0.2. It is the schema's first later column, so `018`'s guard over derived and later columns asserts from then on that it saw one.
- **`response_headers`:**
  - It has `url_id` as an `INTEGER PRIMARY KEY` (a rowid alias), with a declared reference to `urls.id`.
  - `headers` is one `Json` array per URL (ruling Q5). `080` documents a `json_each` recipe for filtering by a header.
  - It has no secondary index: `page --headers` reads one row by its key.
  - A URL without a response has no row.
- *Alternative:* one row per header. That is about 7.5M rows at 500k URLs, for a filter that no Rule or documented query needs in v0.1. Rejected by ruling Q5.

### D11. Codes
Declared as `DiagnosticCode` constants in `spider.output.codes`, as `020` D17 does, by the slice that first raises them:
- warning: `seed_redirected_out_of_scope` (a Seed's redirect chain ends outside the Crawl's Scope, on another registrable domain or outside the Seed's folder; the Scope does not change)

Argument errors, such as `--header` without a colon (v0.2), use `010`'s `invalid_value` (exit 2). The values that this change writes to `urls.fetch_error`, `skip_reason` and `parse_error` (`timeout`, `tls_error`, `max_redirects`, `url_too_long`, `body_too_large`, `unsupported_encoding`) are enumeration values, not diagnostic codes.

### D12. The URL length limit
`url_too_long` is decided by `ScopeRules.decide`, before its `--include` and `--exclude` patterns, so every caller (the engine's dispatch and discovery, and page preparation's `is_internal`) gets it, and no pattern of the user's ever runs over a URL longer than 2,000 characters (`020`'s Risks: ReDoS). Such a URL keeps its host's `is_internal`, has `in_scope` = 0, and is recorded as `skipped`, as `020`'s engine records any skip reason of the Scope.

## Test seams

- **HTTP (local fixture site) (3):** everything network-related. The real aiohttp runs against the fixture site's HTTP and HTTPS listeners, with named hosts behind `020`'s DNS resolver hook (`fixture_hosts`).
- **Seam 3+6:** the new columns and `response_headers` are read through a read-only connection after the Crawl, which runs through `crawl_result` (`tests/support/crawling.py`) or through the CLI (`crawled`). Both run on the real clock. `020`'s virtual clock wakes a sleep when virtual time reaches it and jumps only when nothing runs, but a request waiting on a real socket leaves nothing to run, so time would jump to the watchdog's wake and cut the request. So a [3+6] retry test waits its real backoff (1 s, then 2 s), a [3+6] test whose scenario is not about retries passes `--retries 0`, and only the fake-timing scenarios assert exact times.
- **Pure-logic modules (4):** the cookie redaction, the redirect target table, the `fetch_error` mapping, and the certifi fallback of the TLS setup.
- **Services and store API (2):** the `response_headers` writer forces a replay with `replay_now(writer)` (`017` D7).
- **CLI (1):** argument errors, recorded commands and exit codes.
- **Boundary doubles,** from the approved list:
  - **The fake Fetcher and the injectable clock:** only for "Retries wait one and then two seconds" and "Retry-After pauses the host". The fake Fetcher gains a status, headers and a response sequence per path.
  - **The DNS resolver hook:** for named hosts.
  - **A local test proxy:** for the proxy scenarios. `000`'s proxy isolation removes the proxy variables before every test, so a scenario sets them itself with `monkeypatch.setenv`.
  - **The trustme test CA:** passed into the crawler's TLS setup through the Fetcher factory. It is an approved boundary double.
- **Store contract (6):** every column, index and table is declared through `018`'s `public_table()` and documented in `docs/schema.md` by the slice that needs it. `018`'s contract test also compares the index and STRICT.

## Risks / Trade-offs

- **(v0.2)** [An extra TLS handshake per External https origin] → One per origin per run, in parallel with robots.txt, and closed right away.
- [Brotli missing on some platform, or zstd before v0.2] → brotli ships wheels for every supported platform, and zstd is in the stdlib on 3.14. An encoding the Fetcher cannot decode is not advertised, so a zstd body in v0.1 is a server that ignored `Accept-Encoding`: it is recorded, not parsed (`unsupported_encoding`).
- [A hop limit counted in the writer unit, while a Link found later re-queues a target] → D2's walk over `found_on_url_id` is exact for the hop limit. One walk of the Redirect Chain at the frontier read, a bounded recursive query in `queued_batch` giving each queued URL its hop count and the way its chain was found, would serve the hop limit, the checked status of a redirected Resource and the Seed's chain at once, and survive `024`'s many depth-0 Seeds; it counts at read time, so it is not taken for v0.1.
- [A small compressed body that expands without bound (a decompression bomb)] → The 20 MiB cap applies to the decoded size too, through a decoder bounded in output (D1).
- [Stateless requests on sites that need a session cookie] → These show up as redirect loops or 403 responses, which Googlebot also meets. A cookie option is an open question.
- [truststore behaves differently per OS] → The fallback to certifi, and `doctor` (`080`) reports which trust store is in use.
- [A developer's or CI machine's proxy variables leak into tests] → `000`'s proxy isolation removes them before every test, so the fixture site is never proxied unless a scenario sets them.
- [`response_headers` takes a large share of a 500k-URL crawl file] → `026`'s 500k run reports its share; above 10%, the table keeps Internal URLs only.
- [No adaptive slow-down after repeated 429s: each 429 pauses its host once, for its own wait, and the next request may meet the next 429] → v0.2, a host rate that falls after repeated 429s and recovers slowly.
- [A retry waiting for `Retry-After` (up to 120 s) keeps its URL task, and its place under `020`'s global cap] → The host pause makes that host's other requests wait anyway, and the cap of 20–100 tasks leaves room for other hosts.
- [Tests of this change named after no scenario, which the scenario count ignores] → `test_a_trickling_body_times_out`, since `--timeout` must bound a body that never ends; `test_a_raised_timeout_raises_the_watchdog_with_it`, since `020`'s watchdog must outlast `--timeout`, not a fixed deadline; `test_a_body_at_the_cap_is_read_whole`, `test_a_body_past_the_cap_is_cut_at_the_cap` and `test_the_cap_falls_inside_a_chunk`, since `read_body`'s cap must hold at its exact byte and inside a chunk; `test_a_url_past_2000_characters_is_too_long_before_any_pattern_runs`, since no pattern of the user's may run over such a URL (D12); `test_a_precompressed_file_keeps_its_bytes` (fixture site), since the compression scenarios need the site to send a gzip file's bytes as they are (D9); `test_a_redirect_gives_the_http_url_its_location_names_or_no_target`, since an unusable Location or a 300, 304 or 305 must leave no target; `test_a_compressed_body_is_capped_after_decoding`, since a decompression bomb must stop at the cap; `test_a_bomb_in_one_chunk_is_decoded_only_up_to_the_cap`, since a decoder must never hold a bomb's output in memory; `test_a_compressed_body_is_decoded`, since each offered coding, raw deflate included, must decode to the bytes sent; `test_stacked_codings_are_decoded_last_first`, `test_a_body_that_fails_to_decode_is_refused`, `test_a_coding_that_was_not_offered_is_kept_as_received` and `test_an_empty_body_under_a_coding_is_empty`, since read_body must decode a stack in reverse, refuse a corrupt or cut-short stream, keep an unoffered coding's bytes, and take a bodiless response under a coding as empty; `test_stacked_codings_decode_a_body_up_to_the_cap`, `test_a_zlib_body_whose_first_chunk_is_one_byte_is_decoded` and `test_every_member_of_a_gzip_body_is_decoded`, since a stack must drain fully near the cap, the zlib-or-raw choice needs two bytes, and a gzip body may hold several members; `test_codings_on_repeated_header_lines_are_decoded_as_one_list`, since repeated Content-Encoding lines are one list (RFC 9110 5.3); `test_bytes_after_a_finished_stream_are_ignored` and `test_a_gzip_member_boundary_split_after_its_first_byte_is_decoded`, since bytes after a stream are ignored for every coding and a gzip member split across reads is still decoded; the [Pure] tests of `read_body` on real compressed bytes; `test_the_proxy_of_a_url`, since the lower-case variable, `NO_PROXY` and an ignored `ALL_PROXY` decide a proxy before any request; `test_an_invalid_user_agent_in_the_settings_file_is_refused`, since `crawl.user_agent` must refuse what `--user-agent` refuses; `test_a_timeout_that_is_not_a_finite_number_above_0_is_rejected`, its settings-file twin and `test_a_whole_number_timeout_in_the_settings_file_is_taken`, since a timeout of 0, a negative one or one that is not finite would end every request at once or never; `test_the_backoff_doubles_with_each_retry`, since two retries cannot tell a doubling backoff from one that grows by a second; `test_a_retry_after_or_a_429_sets_the_wait_before_the_retry`, since the spec's 10-second 429 wait, a 503's Retry-After, an HTTP-date Retry-After and the 120-second cap have no scenario of their own; `test_a_request_waiting_for_the_global_cap_when_its_host_pauses_starts_after_it`, since a request whose turn came before the pause must still not start during it; `test_a_request_without_a_response_is_retried`, `test_robots_txt_is_retried`, `test_a_robots_txt_that_times_out_gives_its_urls_timeout_without_a_request` and `test_only_the_first_attempt_counts_towards_the_url_limit`, since the spec's retry rules for a request without a response, for robots.txt and for `--max-urls` have no scenario of their own; `test_a_proxy_that_is_down_is_named_in_the_failure`, since a proxy that is down makes every URL fail as though the site were; `test_every_fetch_error_is_classified` and the tables of `tests/crawl/test_requester.py`, since a new `fetch_error` value must be classified as retried or not; `test_more_than_10_retries_are_rejected` and its settings-file twin, since a doubling backoff past 10 retries waits hours for one URL; `test_a_redirect_target_is_requested_before_the_next_depth`, for each redirect status, since a target recorded at its source's depth must be dispatched before the next depth, or the depth barrier is broken; `test_a_redirect_target_loses_the_stripped_parameters`, since a redirect's target is a URL of the Crawl as a Link's is, and `--strip-params` applies to it; `test_every_hop_of_a_seed_chain_that_widens_the_scope_is_internal`, since every URL of a Seed's chain, not only its last, belongs to the Scope it ended in; `test_an_image_redirected_twice_beyond_the_depth_limit_is_checked`, since the way a chain was found is read back over every hop; `test_a_link_to_a_url_past_the_hop_limit_queues_it_again`, since `max_redirects` is a skip at discovery that a later Link lifts; `test_the_hop_limit_is_read_from_the_settings_file`, since `crawl.max_redirects` must count as `--max-redirects` does; `test_only_a_redirect_on_a_loop_is_marked`, since `in_redirect_loop` is 0 for a plain redirect, NULL without one, and 1 for a URL that redirects to itself; `test_a_url_a_redirect_lowers_to_the_open_depth_is_requested_at_that_depth`, since a URL a redirect lowers below the read cursor must be dispatched before the next depth, or what it links gets too deep a path; `test_a_blog_seed_that_moved_to_the_apex_widens_the_scope_once_its_chain_ends`, since a Seed chain that ends on a Checked URL must close once, by that URL's unit, before depth 0 ends; `test_the_units_of_redirects_run_again_the_same`, since the hop count and the loop walk must read only the file; `test_a_section_seed_that_moved_to_the_apex_keeps_its_section`, since a section's chain that ends inside the folder on the apex still widens the hosts; `test_a_seed_chain_that_ends_on_a_checked_url_widens_the_scope_once_it_ends`, since a chain whose last URL is only checked must close once, by that URL's unit, with its response; `test_more_than_50_redirects_in_the_settings_file_are_refused`, since `crawl.max_redirects` must refuse what `--max-redirects` refuses; `test_a_redirect_into_a_loop_that_does_not_run_through_it_ends_its_walk_at_once`, since the loop walk runs in the writer's thread; the `fetch_error` table that maps aiohttp's timeouts to `timeout`; the guard that every insert into `urls` goes through `insert_urls`; the fallback test of the TLS setup; and the replay test of `spider.store.response_headers`.
- [A chain that a Page also links into midway is followed past `--max-redirects`: the hop count walks back only over hops found as redirects, so a hop first found through a Link starts it again] → Accepted: that hop is a URL of the site in its own right, and counting through it would need a walk over every way a URL was found. `test_a_hop_that_a_link_reached_first_starts_the_hop_count_again` pins it, against a count that silently starts honouring the Link or stops counting.
- [br bytes after the stream, in the same read as its end] → brotli's decoder refuses input past the end of its stream and reports neither where the stream ended nor what is left, so such a body is `invalid_response`. Bytes after the end that arrive in a later read are ignored, as gzip's and deflate's always are. Feeding brotli a byte at a time would find the end, at a call per byte of every br body. Accepted for v0.1.
- [`PROJECT_URL` names a private repository] → A site owner who follows the user agent's link gets a 404 until the repository is public. The release (`085`) does not start before the product is named and `PROJECT_URL` points to a public page (ROADMAP, Release).
- [`seed_base_mismatch` reads the depth-0 Page of a Seed's chain] → In Spider mode, depth 0 is exactly the Seed and its Redirect Chain. `024`'s listed Seeds are all depth 0 too, so `024` decides how the check finds a Seed's chain there.

## Migration Plan

None. Before v0.1 the schema is not yet public. This change adds its columns, its index and the `response_headers` table to the declared schema and `docs/schema.md`, each in the slice that needs it, and `schema_version` stays `1` (`015` D5). Its one new enumeration value, `unsupported_encoding`, goes into the CHECK in the slice that writes it.

## Open Questions

**To add when `020`'s network pause lands** (its group 12), with its final numbers then:
- A scenario under "Retries with backoff": "A request that fails during a network pause is not retried". WHEN `/` links to `/p1` to `/p20`, a fake Fetcher gets no response for any request after the one for `/`, and the Crawl runs with `--concurrency 1`, `--network-wait 30` and a fake clock; THEN no URL is requested again after the pause began until the Crawl ends, and the URL whose attempt failed during the pause stays `queued`.

**Deferrable, each additive:**
- `--insecure`, for staging sites with self-signed certificates.
- `--ca-cert <file>`, to trust a private CA as well as the OS store.
- SOCKS proxies (`aiohttp-socks`).
- An opt-in cookie session (`--cookies session`).
- A time-to-first-byte column (`ttfb_ms`), which needs a fixture route that delays the body after the headers.
- `--auth-file <path>`, to keep credentials out of shell history, as an alternative to `[crawl] auth` in `spider.toml`.
