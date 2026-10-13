> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

## Context

See proposal.md (Why) for the motivation. The approach is shaped by these constraints:

- **`020-add-crawl-core`** provides:
  - the `Fetcher` interface (one hop, no redirects) with a minimal aiohttp implementation
  - the per-host politeness gate and the injectable `Clock`
  - the fake Fetcher, and the DNS resolver hook
  - the `urls` and `origins` tables, the depth barrier, and the writer unit per URL
- **`015-add-crawl-store`** redacts secrets, both whole values and partial ones such as `Cookie: ***` and `user:***@proxy`.
- **`017-speed-up-crawl-writer`** gives the writer that `020`'s unit per URL goes through. A unit may run twice, so the units of this change follow its D7 contract, including the loop walk of D2.
- **`018-add-schema-conventions` and ADR-0005** set the schema rules. Every column, index and table of this change is declared through `018`'s declaration helper (D10).
- **`010-add-workspace-and-cli-contract`** takes settings only from flags and `spider.toml`, never from environment variables.
- **ADR-0001:** aiohttp has no HTTP/2, so `http_version` is measured with an ALPN handshake.
- **`000-scaffold-project`** leaves HTTPS, virtual hosts and gzip on the fixture site to this change.

## Goals / Non-Goals

**Goals:**
- Every request policy lives behind the Fetcher interface and the per-host gate, so the engine's decisions (Scope, robots.txt, depth) are untouched.
- Per-hop data (status, Location, timing, headers) is recorded now, so v0.2's `redirects` needs no re-crawl.
- Deterministic tests: the real aiohttp against the fixture site, with fake timing only for backoff and pauses.

**Non-Goals:**
- HTTP/2 or HTTP/3 transport, cookie sessions, and SOCKS proxies.
- Deciding what is followed (`020`).

## Decisions

### D1. The aiohttp policy Fetcher
The Fetcher that replaces `020`'s minimal one keeps its interface:
- **Redirects:** `allow_redirects=False` on every request.
- **Decoding:** `auto_decompress=False`, and the Fetcher decodes gzip and deflate (`zlib`), br (`brotli`) and zstd (`zstandard`, or `compression.zstd` on 3.14) itself. That way it measures both `transferred_bytes` and `size_bytes`.
- **Body limit:** the body is streamed up to 20 MiB. For checked URLs whose response has a `Content-Length` and no `Content-Encoding`, the Fetcher may stop after the headers and take both sizes from `Content-Length`.
- **No cookies:** a `DummyCookieJar`, so no cookie is ever replayed.
- **Environment:** `trust_env=False`, so aiohttp reads no `.netrc` and no variables by itself. The Fetcher chooses the proxy per request:
  1. `--proxy` or `[crawl] proxy` when set
  2. otherwise `urllib.request.getproxies_environment()` (any case; lower-case wins) and `proxy_bypass_environment()` for `NO_PROXY`

  The ALPN check uses the same choice.
- **Internal URLs only:** custom headers and preemptive basic auth are added only when the request URL is internal (`020`'s `ScopeRules`), and never for External URLs, even on a redirect hop.

### D2. Redirects are URL rows
Every hop is a normal `urls` row with its own status and timing, linked through `redirect_url_id`. The target is enqueued at its source's depth, where `020`'s depth barrier (D3) keeps depths exact, and it goes through the Scope, robots.txt and the per-host gate like any URL.
- **Hop limit:** the engine keeps, in memory, the number of consecutive redirects that led to each target discovered through a redirect. A target beyond `--max-redirects` is recorded as `skipped` with `max_redirects`.
- **Loops:** when the writer stores a redirect whose target is already known, it walks `redirect_url_id` forward, bounded by the hop limit, and sets `in_redirect_loop` on every URL on a cycle. The walk reads only the file, so the unit gives the same result when it runs again (`017` D7).
- *Alternative:* a `redirect_hops` table keyed by the first URL of each chain. It stores the same hop once per chain. Rejected.
- *Alternative:* following chains inside the Fetcher. That bypasses politeness and robots.txt for each hop. Rejected.

### D3. The Seed-redirect Scope rule
`site.test` → `www.site.test` is the most common start of a crawl, and without this rule it would crawl one URL. A redirect to another registrable domain (SSO, parking pages) only raises a warning, so the Crawl never wanders onto a third-party site. Hosts added this way are appended to `crawl.scope.hosts`, in the unit that records the Seed's last hop.

### D4. Retries and backoff
- **Retries:** on no response, 5xx or 429, as `--retries`.
- **Backoff:** 1 s, 2 s, …, with no jitter, so fake-clock tests assert exact times.
- **Retry-After:** seconds or an HTTP date, capped at 120 s. A 429 without `Retry-After` pauses the host for 10 s.
- **Pauses** set the host's "next allowed start" in `020`'s gate, so every request to that host waits, not only the retried one.
- **`020`'s network pause** (decided 2026-10-14): a timeout counts as a request without a response, like a refused connection. While the Crawl is paused, a failing attempt is neither retried nor recorded, and its URL waits in `queued`, so an outage spends no retries and leaves no false `timeout` rows.
- **robots.txt without a response:** after its retries, a robots.txt that timed out or failed TLS gives its origin's URLs the same `fetch_error` without a request (`020`); one that answered 5xx or 429 stays `robots_unreachable`.

### D5. TLS trust
- **The default:** `truststore.SSLContext` uses the OS trust store on Windows, macOS and Linux.
- **The fallback:** if truststore cannot be loaded, `ssl.create_default_context(cafile=certifi.where())`.
- **Speed test:** a benchmark task measures handshake cost with truststore and with certifi on each OS, and records the result in the docs. If truststore is measurably slower, only the default path changes, not the behaviour.
- **Shared setup:** the same context is used for requests, robots.txt and the ALPN check, and `080`'s `doctor` TLS check reuses it.
- **Tests:** the TLS setup accepts extra trust anchors, and tests pass the trustme CA through them. The maintainer approved this on 2026-09-27 as a boundary double, and docs/testing.md lists it. The real TLS stack still verifies every certificate.

### D6. HTTP version by ALPN
There is one `asyncio.open_connection(host, port, ssl=ctx, server_hostname=host)` per https origin, with `ctx.set_alpn_protocols(["h2", "http/1.1"])`. It runs in parallel with the origin's robots.txt request and is closed right after the handshake. With a proxy, it tunnels through `CONNECT`. Any failure gives NULL.

### D7. Response headers and cookie values
- **Source:** raw headers come from aiohttp's `raw_headers`, keeping order and letter case.
- **Cookie redaction happens before storage,** in the exact format of the spec: `sid=abc123; Path=/` becomes `sid=***; Path=/`, and `a=1; b=2` becomes `a=***; b=***`. Names and attributes stay. The `crawl` redaction itself is `015`'s. This is value hygiene for crawled data, applied by the Fetcher so no layer ever holds a cookie value in the store.
- **Consumers:** `030` reads cookie names and attributes from the live response through `020`'s per-response hook, so the redacted stored copy loses nothing for Page data.

### D8. What is secret
The flags declare their secret form, and `015` does all the redaction:
- `--auth` is a whole secret, so `015` writes `***`.
- `--header` (and the setting `crawl.header`) is a header secret. `015` redacts `Cookie`, and every header whose name contains `auth`, `token`, `secret`, `key` or `password`.
- `--proxy` is a URL secret, so its password becomes `***`.

Credentials in `spider.toml` are allowed, and `060`'s `resume` re-reads them from there.

**The setting key** is `crawl.header`, a list of `Name: Value` strings, because `010`'s rule makes a setting's key the flag's long name. It keeps the curl-style `--header` flag.

### D9. Fixture site additions
Each is added test-first in `tests/fixture_site/` by the first slice that needs it:
- **Virtual hosts:** routing by `Host` header on one server.
- **HTTPS listeners** with a `trustme` CA:
  - one that selects `h2`
  - one that offers only `http/1.1`
  - one whose certificate names `other.test`
  - one with a certificate from a CA the test never trusts
- **Raw byte bodies,** such as precompressed gzip.
- **Response sequences,** for example 503 once and then 200.
- **A cookie-echo route** that shows whether a `Cookie` header arrived.
- **A small forward proxy** helper for the `--proxy` scenarios.

### D10. The schema under ADR-0005
This change adds to `020`'s tables and adds one of its own, all through `018`'s declaration helper (`STRICT`, and CHECKs from the declared values and flags).
- **`urls` columns:**
  - `attempt_count` (ADR-0005 rule 5: a count ends with `_count`), NOT NULL with a default of 0, so the inserts of `020`'s units need no change
  - `redirect_location`, the raw header text
  - `redirect_url_id`, a declared reference to `urls.id`
  - `in_redirect_loop`, a flag that reads as yes or no (rule 6)
  - `body_truncated`
  - `content_encoding`, `size_bytes` and `transferred_bytes`
- **Enumeration values:** `redirect`, `max_redirects`, `url_too_long`, `timeout`, `tls_error` and `body_too_large` are already listed by `020` (its D18), so this change adds no value to a CHECK.
- **`urls_redirect_url_id`** on `(redirect_url_id) WHERE redirect_url_id IS NOT NULL`: it serves "which URLs redirect to this one", the reverse walk of a Redirect Chain. The forward walk reads `redirect_url_id` from the row and needs no index. The index is partial, because most URLs do not redirect, so most rows have no entry.
- **`origins.http_version`** exists from v0.1 and is NULL until v0.2's ALPN check fills it. Its description starts with `Filled from v0.2. ` (ADR-0005), so the `origins` contract does not change in v0.2.
- **`response_headers`:**
  - It has `url_id` as an `INTEGER PRIMARY KEY` (a rowid alias), with a declared reference to `urls.id`.
  - `headers` is one JSON array per URL (ruling Q5). `080` documents a `json_each` recipe for filtering by a header.
  - It has no secondary index: `page --headers` reads one row by its key.
  - A URL without a response has no row.
- *Alternative:* one row per header. That is about 7.5M rows at 500k URLs, for a filter that no Rule or documented query needs in v0.1. Rejected by ruling Q5.

### D11. Codes
Declared as `DiagnosticCode` constants in `spider.output.codes`, as `020` D17 does, by the slice that first raises them:
- warning: `seed_redirected_off_site` (a Seed's redirect chain ends on another registrable domain; the Scope does not change)

Argument errors, such as `--header` without a colon, use `010`'s `invalid_value` (exit 2). The values that this change writes to `urls.fetch_error`, `skip_reason` and `parse_error` (`timeout`, `tls_error`, `max_redirects`, `url_too_long`, `body_too_large`) are enumeration values that `020` lists, not diagnostic codes.

## Test seams

- **HTTP (local fixture site) (3):** everything network-related. The real aiohttp runs against the fixture site's HTTP and HTTPS listeners, with virtual hosts behind `020`'s DNS resolver hook.
- **Seam 3+6:** the new columns and `response_headers` are read through a read-only connection after the Crawl.
- **CLI (1):** argument errors (`--header` without a colon), recorded commands and exit codes.
- **Boundary doubles,** from the approved list:
  - **The fake Fetcher and the injectable clock:** only for "Retries wait one and then two seconds" and "Retry-After pauses the host".
  - **The DNS resolver hook:** for virtual hosts.
  - **A local test proxy:** for the `--proxy` scenarios.
  - **The trustme test CA:** passed into the crawler's TLS setup. It is an approved boundary double.
- **Store contract (6):** every column, index and table is declared through `018`'s helper and documented in `docs/schema.md` by the slice that needs it. `018`'s contract test also compares the index and STRICT.

## Risks / Trade-offs

- [An extra TLS handshake per External https origin] → One per origin per run, in parallel with robots.txt, and closed right away.
- [Brotli or zstd missing on some platforms] → Both are pure wheels or in the stdlib on 3.14. If a decoder is missing, that encoding is not advertised.
- [Stateless requests on sites that need a session cookie] → These show up as redirect loops or 403 responses, which Googlebot also meets. A cookie option is an open question.
- [truststore behaves differently per OS] → The fallback to certifi, and `doctor` (`080`) reports which trust store is in use.
- [A developer's or CI machine's proxy variables leak into tests] → The test harness sets `NO_PROXY` for localhost and the fixture site's names, so the fixture site is never proxied unless a scenario asks for it.

## Migration Plan

None. Before v0.1 the schema is not yet public. This change adds its columns, its index and the `response_headers` table to the declared schema and `docs/schema.md`, each in the slice that needs it, and `schema_version` stays `1` (`015` D5). It adds no enumeration value, because `020` lists them all.

## Open Questions

These are deferrable, and each is additive:
- `--insecure`, for staging sites with self-signed certificates.
- `--ca-cert <file>`, to trust a private CA as well as the OS store.
- SOCKS proxies (`aiohttp-socks`).
- An opt-in cookie session (`--cookies session`).
- A time-to-first-byte column (`ttfb_ms`), which needs a fixture route that delays the body after the headers.
- `--auth-file <path>`, to keep credentials out of shell history, as an alternative to `[crawl] auth` in `spider.toml`.
