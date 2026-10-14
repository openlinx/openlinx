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

> **Blueprint edits (2026-10-11):** the schema parts follow ADR-0005, `018-add-schema-conventions` and the rulings on the schema blueprint (design D10). The rest of this draft is re-grounded before the change starts.

- **Request identity:**
  - `--user-agent <string>`. The default is `spider/<version> (+<project URL>)`.
  - `--header "Name: Value"`, repeatable, setting `crawl.header`.
  - `--auth <user:password>`, a secret.
  - Custom headers and credentials go only to Internal URLs.
  - `Authorization`, `Proxy-Authorization` and `Cookie` header values, and proxy passwords, are marked partly secret for `015`'s redaction. Credentials may also be kept in `spider.toml`.
- **Proxy:**
  - `--proxy <url>` and `[crawl] proxy`.
  - Without them, the standard `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` variables are honoured, in any case, as curl, pip and uv do. This is `010`'s one exception to its no-environment-variables rule.
  - Proxy passwords are redacted, and the variables in use are recorded in the `environment` table of `crawl.config`.
- **No cookies are sent:** `Set-Cookie` is never replayed.
- **Timeouts and retries:**
  - `--timeout <s>` (default 20).
  - `--retries <n>` (default 2), with 1 s/2 s backoff. `Retry-After` is honoured up to 120 s, and 429 pauses the host.
  - The `urls.attempt_count` column.
- **Redirects:**
  - Followed hop by hop. Every hop is a `urls` row with `redirect_location`/`redirect_url_id`, and a target keeps the Crawl Depth of its source.
  - `--max-redirects <n>` (default 10). Loops are marked with `in_redirect_loop`.
  - A Seed that redirects within its registrable domain extends the Scope. An off-site Seed redirect is a warning.
  - A meta refresh stays a Link, never a redirect hop.
- **Limits:** response bodies are read up to 20 MiB (`body_truncated`, `parse_error = body_too_large`), and URLs longer than 2,000 characters are skipped (`url_too_long`).
- **Compression:** `Accept-Encoding: gzip, deflate, br, zstd`, decoded by the tool. The `content_encoding`, `size_bytes` and `transferred_bytes` columns record status and size checks for Resources.
- **TLS trust:** certificates are verified with truststore (the OS trust store), falling back to certifi. A speed test decides the default path. Failures are `tls_error`.
- **HTTP version:** one ALPN handshake per https origin gives `origins.http_version` = `http_2` or `http_1_1` (v0.2). In v0.1 the column exists and is NULL, and its description starts with `Filled from v0.2. `.
- **The `response_headers` table:** one JSON row per URL with a response, keyed by `url_id`. Headers keep their received order and letter case, and `Set-Cookie` values are stored as `***`.
- **Store, under ADR-0005 and `018`:**
  - the `urls` columns `attempt_count`, `redirect_location`, `redirect_url_id`, `in_redirect_loop`, `body_truncated`, `content_encoding`, `size_bytes` and `transferred_bytes`
  - the partial index `urls_redirect_url_id`
  - `origins.http_version`, a v0.1 column that v0.2 fills
  - the `response_headers` table
  - The enumeration values that this change writes (`redirect`, `max_redirects`, `url_too_long`, `timeout`, `tls_error` and `body_too_large`) are listed by `020` from v0.1.
- **Fixture site (test-first):** virtual hosts, HTTPS listeners with a `trustme` CA (one selects `h2`, one offers only `http/1.1`, one has a certificate for the wrong name, one uses an unknown CA), raw and gzip bodies, response sequences, and a test forward proxy.
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
  - `020-add-crawl-core`: the Fetcher interface, the engine, the per-host gate, the fake Fetcher and clock, the DNS resolver hook, and the `urls`/`origins` tables.
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
- **Code:** `spider.crawl.fetcher`, `020`'s module, which becomes a package for the aiohttp policy, decoding, TLS and ALPN, redirect handling in the engine, and store columns.
- **New dependencies:** `truststore`, `certifi` and `brotli`. `zstandard` is shared with `030`, and `compression.zstd` is used on Python 3.14. `trustme` is a test dependency.
- **Docs:** the fetching part of `docs/crawling.md` (identity, credentials, proxy, retries, redirects, limits, compression, TLS, HTTP version).
