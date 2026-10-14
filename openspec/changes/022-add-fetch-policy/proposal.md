## Why

`020-add-crawl-core` requests URLs through a minimal one-hop Fetcher. Real sites need more before a Crawl's data can be trusted:
- redirects followed hop by hop, with every hop recorded
- retries for transient failures, and timeouts
- limits against oversized bodies and URL traps
- compressed transfer, with both sizes recorded
- verified TLS against the OS trust store
- the HTTP version each origin offers
- request identity, credentials and proxies for staging sites

The response headers must also be stored, without cookie values, because `page --headers` (`050`) and later Redirect Chain analysis read them. This change adds all of that behind `020`'s Fetcher interface.

## What Changes

> **v0.1 scope (2026-10-05, see ROADMAP.md):** v0.1 ships the minimum: timeouts and retries, redirects, body and URL limits, `--user-agent`, gzip, deflate and br, TLS trust, the Resource checks, `response_headers`, and the `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` variables. **Deferred to v0.2:** `--header`, `--auth`, `--proxy` (and `[crawl] proxy`), the ALPN check behind `origins.http_version`, and zstd decoding.

> **Blueprint edits (2026-10-11):** the schema parts follow ADR-0005, `018-add-schema-conventions` and the rulings on the schema blueprint (design D10).

> **Re-grounded (2026-10-14)** against `020-add-crawl-core`'s code through its group 6, its first pull request: the `Fetcher` Protocol in `spider.crawl.fetcher` with `FetchResult | FetchFailure`, `CrawlSettings`, the context builder, `Hooks` and the `fetch_error` codes. The parts of `020` that land later (robots.txt, `--rate`, the network pause, the watchdog and the fake Fetcher) are named in tasks.md where a task waits for them, and the v0.2 parts are marked there and in the design.

- **Request identity:**
  - `--user-agent <string>`. The default is `spider/<version> (+<project URL>)`.
  - **(v0.2)** `--header "Name: Value"`, repeatable, setting `crawl.header`.
  - **(v0.2)** `--auth <user:password>`, a secret.
  - **(v0.2)** Custom headers and credentials go only to Internal URLs.
  - **(v0.2)** `Authorization`, `Proxy-Authorization` and `Cookie` header values, and proxy passwords, are marked partly secret for `015`'s redaction. Credentials may also be kept in `spider.toml`.
- **Proxy:**
  - **(v0.2)** `--proxy <url>` and `[crawl] proxy`.
  - Without them, the standard `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` variables are honoured, in any case, as curl, pip and uv do. This is `010`'s one exception to its no-environment-variables rule.
  - Proxy passwords are redacted, and the variables in use are recorded in the `environment` table of `crawl.config`.
- **No cookies are sent:** `Set-Cookie` is never replayed. `020`'s Fetcher already keeps no cookies, and this change pins that.
- **Timeouts and retries:**
  - `--timeout <s>` (default 20), which also sets `020`'s watchdog.
  - `--retries <n>` (default 2), with 1 s/2 s backoff. `Retry-After` is honoured up to 120 s, and 429 pauses the host. The engine retries around the Fetcher, which makes one attempt per call.
  - The `urls.attempt_count` column.
- **Redirects:**
  - Followed hop by hop, by the engine. Every hop is a `urls` row with `redirect_location`/`redirect_url_id`, and a target keeps the Crawl Depth of its source.
  - `--max-redirects <n>` (default 10). Loops are marked with `in_redirect_loop`.
  - A Seed that redirects within its registrable domain extends the Scope (whether v0.1 keeps it is the user's decision, still open in the design). An off-site Seed redirect is a warning.
  - A meta refresh stays a Link, never a redirect hop.
- **Limits:** response bodies are read up to 20 MiB, before and after decoding (`body_truncated`, `parse_error = body_too_large`), and URLs longer than 2,000 characters are skipped (`url_too_long`).
- **Compression:** gzip, deflate and br, decoded by the tool; zstd from v0.2, so v0.1 sends `Accept-Encoding: gzip, deflate, br`. The `content_encoding`, `size_bytes` and `transferred_bytes` columns record status and size checks for Resources.
- **TLS trust:** certificates are verified with truststore (the OS trust store), falling back to certifi. A speed test decides the default path. Failures are `tls_error`.
- **HTTP version:** one ALPN handshake per https origin gives `origins.http_version` = `http_2` or `http_1_1` (v0.2). In v0.1 the column exists and is NULL, and its description starts with `Filled from v0.2. `.
- **The `response_headers` table:** one JSON row per URL with a response, keyed by `url_id`. Headers keep their received order and letter case, and `Set-Cookie` values are stored as `***`.
- **Store, under ADR-0005 and `018`:**
  - the `urls` columns `attempt_count`, `redirect_location`, `redirect_url_id`, `in_redirect_loop`, `body_truncated`, `content_encoding`, `size_bytes` and `transferred_bytes`
  - the partial index `urls_redirect_url_id`
  - `origins.http_version`, a v0.1 column that v0.2 fills
  - the `response_headers` table
  - The enumeration values that this change writes (`redirect`, `max_redirects`, `url_too_long`, `timeout`, `tls_error` and `body_too_large`) are listed by `020` from v0.1.
- **Fixture site (test-first):** a site per named host in `020`'s `fixture_hosts`, HTTPS listeners with a `trustme` CA (one for `site.test`, one with a certificate for the wrong name, one with an unknown CA, and from v0.2 one that selects `h2` and one that offers only `http/1.1`), precompressed bodies, response sequences, stalled and trickling bodies, and a test forward proxy.
- **Flags that go beyond the wording of ROADMAP.md:** `--timeout`, `--retries` and `--max-redirects` name the limits ROADMAP lists, and `--header`, `--auth` and `--proxy` spell its request options.
- **MCP tools:** none in this change.

## Capabilities

### New Capabilities
- `fetching`: covers the following.
  - Request identity, credentials and proxy, and no cookies.
  - Timeouts and retries, and redirects with hop limits, loops and the Seed-redirect Scope rule.
  - Body and URL limits, compression and Resource sizes.
  - TLS verification, the HTTP version per origin, and the `response_headers` table.

### Modified Capabilities
- None. `crawling` comes from `020-add-crawl-core`, which is not archived yet. This change adds columns, an index and a table under the conventions of `018-add-schema-conventions`. The enumeration values it writes are already listed by `020`.

## Non-goals

- Redirect Chain views (`redirects`, with per-hop headers and timing): **v0.2**. The per-hop data is recorded now.
- HTTP/2 or HTTP/3 transport, and HTTP/3 detection: **backlog**. Requests use HTTP/1.1, and `http_version` reports what the origin offers.
- SOCKS proxies, cookie sessions, `--insecure`, and extra CA files for users: see design.md, Open Questions.
- Anything that decides which URLs are requested or followed: `020-add-crawl-core`.

## Impact

- **Depends on:**
  - `020-add-crawl-core`: from its first pull request, the Fetcher interface, the engine, the per-host limits, `CrawlSettings`, the context builder, `Hooks`, the DNS resolver hook, and the `urls`/`origins` tables; from its later groups, the meta refresh Link, `crawl.scope`, Resource checks, robots.txt, the next allowed start of `--rate`, the network pause, the watchdog and the fake Fetcher.
  - `015-add-crawl-store`: whole and partial redaction, and secret settings.
  - `017-speed-up-crawl-writer`: the writer through which `020`'s units run, and its unit contract.
  - `018-add-schema-conventions`: `public_table()` and the schema contract test.
  - `010-add-workspace-and-cli-contract`: settings and exit codes.
  - `000-scaffold-project`: the fixture site harness.
- **Used by:**
  - `030` (sizes, redirect data, `http_version`, `response_headers`)
  - `050` (`page --headers`, and the `resources` export)
  - `060` (`--auth` on resume)
  - `080` (`doctor`'s TLS check reuses this TLS setup)
- **Code:**
  - `spider.crawl.fetcher` (`020`'s module): the policy Fetcher, its decoding and its proxy choice
  - `spider.crawl.tls`: the TLS setup that `080`'s `doctor` reuses, and from v0.2 the ALPN check
  - `spider.crawl.engine`: the retry loop and redirects
  - `spider.crawl.scope`: the URL length limit in `ScopeRules.decide`
  - `spider.crawl.settings` and `spider.cli.crawl`: the new keys and options
  - `spider.store.schema` and `spider.store.urls`: the new columns, the index and the redirect units
  - `spider.store.response_headers`: the `response_headers` table's row writer
- **New dependencies:** `truststore`, `certifi` and `brotli`. **(v0.2)** `zstandard`, shared with `030`, and `compression.zstd` on Python 3.14. `trustme` is a test dependency.
- **Docs:** the fetching part of `docs/crawling.md` (identity, credentials, proxy, retries, redirects, limits, compression, TLS, HTTP version).
