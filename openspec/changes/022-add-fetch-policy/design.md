> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

## Context

See proposal.md (Why) for the motivation. The approach is shaped by these constraints:

- **`020-add-crawl-core`** provides:
  - the `Fetcher` interface (one hop, no redirects) with a minimal aiohttp implementation
  - the per-host politeness gate and the injectable `Clock`
  - the fake Fetcher, and the DNS resolver hook
  - the `urls` and `origins` tables, the depth barrier, and the writer unit per URL
- **`015-add-crawl-store`** redacts secrets, both whole values and partial ones such as `Cookie: ***` and `user:***@proxy`.
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
- **Loops:** when the writer stores a redirect whose target is already known, it walks `redirect_url_id` forward, bounded by the hop limit, and marks every URL on a cycle.
- *Alternative:* a `redirect_hops` table keyed by the first URL of each chain. It stores the same hop once per chain. Rejected.
- *Alternative:* following chains inside the Fetcher. That bypasses politeness and robots.txt for each hop. Rejected.

### D3. The Seed-redirect Scope rule
`site.test` → `www.site.test` is the most common start of a crawl, and without this rule it would crawl one URL. A redirect to another registrable domain (SSO, parking pages) only raises a warning, so the Crawl never wanders onto a third-party site. Hosts added this way are appended to `crawl.scope.hosts`.

### D4. Retries and backoff
- **Retries:** on no response, 5xx or 429, as `--retries`.
- **Backoff:** 1 s, 2 s, …, with no jitter, so fake-clock tests assert exact times.
- **Retry-After:** seconds or an HTTP date, capped at 120 s. A 429 without `Retry-After` pauses the host for 10 s.
- **Pauses** set the host's "next allowed start" in `020`'s gate, so every request to that host waits, not only the retried one.

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

## Test seams

- **HTTP (local fixture site) (3):** everything network-related. The real aiohttp runs against the fixture site's HTTP and HTTPS listeners, with virtual hosts behind `020`'s DNS resolver hook.
- **Seam 3+6:** the new columns and `response_headers` are read through a read-only connection after the Crawl.
- **CLI (1):** argument errors (`--header` without a colon), recorded commands and exit codes.
- **Boundary doubles,** from the approved list:
  - **The fake Fetcher and the injectable clock:** only for "Retries wait one and then two seconds" and "Retry-After pauses the host".
  - **The DNS resolver hook:** for virtual hosts.
  - **A local test proxy:** for the `--proxy` scenarios.
  - **The trustme test CA:** passed into the crawler's TLS setup. It is an approved boundary double.
- **Store contract (6):** every column is added and documented in `docs/schema.md` by the slice that needs it.

## Risks / Trade-offs

- [An extra TLS handshake per External https origin] → One per origin per run, in parallel with robots.txt, and closed right away.
- [Brotli or zstd missing on some platforms] → Both are pure wheels or in the stdlib on 3.14. If a decoder is missing, that encoding is not advertised.
- [Stateless requests on sites that need a session cookie] → These show up as redirect loops or 403 responses, which Googlebot also meets. A cookie option is an open question.
- [truststore behaves differently per OS] → The fallback to certifi, and `doctor` (`080`) reports which trust store is in use.
- [A developer's or CI machine's proxy variables leak into tests] → The test harness sets `NO_PROXY` for localhost and the fixture site's names, so the fixture site is never proxied unless a scenario asks for it.

## Migration Plan

New columns, enumeration values and the `response_headers` table go into the squashed v0.1 migration under `015`'s conventions.

## Open Questions

These are deferrable, and each is additive:
- `--insecure`, for staging sites with self-signed certificates.
- `--ca-cert <file>`, to trust a private CA as well as the OS store.
- SOCKS proxies (`aiohttp-socks`).
- An opt-in cookie session (`--cookies session`).
- A time-to-first-byte column (`ttfb_ms`), which needs a fixture route that delays the body after the headers.
- `--auth-file <path>`, to keep credentials out of shell history, as an alternative to `[crawl] auth` in `spider.toml`.
