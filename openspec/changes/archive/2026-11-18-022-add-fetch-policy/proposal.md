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

> **Foundation:** the Crawl core, network pause and v0.1 fetching policy are implemented. The remaining v0.2 work is custom headers and credentials, the explicit proxy, ALPN capability measurement and bounded zstd decoding.

- **Request identity:**
  - `--user-agent <string>`. The default is `OpenLinx/<version> (+https://github.com/openlinx/openlinx/blob/main/docs/crawler.md)`, the page for site owners.
  - **(v0.2)** `--header "Name: Value"`, repeatable, setting `crawl.header`.
  - **(v0.2)** `--auth <user:password>`, a secret.
  - **(v0.2)** Custom headers and credentials go only to Internal URLs.
  - **(v0.2)** One per-attempt header resolver combines defaults, Workspace settings and CLI inputs. Explicit inputs beat implicit/default values; among explicit inputs CLI wins over Workspace inputs, then dedicated `user_agent` wins over a custom `User-Agent` at the same source level, regardless of argument order. The dedicated input is global; a custom header remains Internal-only. An absent CLI option never overrides an explicit Workspace input. Neither `User-Agent` nor `Accept-Encoding` is a forbidden custom name.
  - **(v0.2)** Nonempty `crawl.auth` together with a custom `Authorization` header, matched without case, is `invalid_value` before any network request, including when the values come from different configuration sources.
  - **(v0.2)** `Authorization`, `Proxy-Authorization` and `Cookie` header values, and proxy passwords, are marked partly secret for `015`'s redaction. Credentials may also be kept in `openlinx.toml`.
  - **(v0.2)** Recorded header lists retain harmless entries, names and order. A continue uses fresh secret values or refuses with actionable `secrets_required`; it never sends stored redaction markers or reloads unrelated Workspace settings. This is a Crawl Service contract; `resume` Commands remain in `060`.
  - **(v0.2)** A continue preserves the selected header policy and explicit literals using the service-owned boolean `crawl.config.request_policy.custom_user_agent`; settings and recorded header entries stay untouched. A null dedicated UA still generates the running tool's default. This adds config JSON metadata, not a public setting or SQL column, and reserves the `request_policy` root name against settings-table registration.
- **Proxy:**
  - **(v0.2)** `--proxy <url>` and `[crawl] proxy`.
  - Without them, the standard `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` variables are honoured, in any case, as curl, pip and uv do. This is `010`'s one exception to its no-environment-variables rule.
  - Proxy passwords are redacted, and the variables in use are recorded in the `environment` table of `crawl.config`.
- **No cookies are sent:** `Set-Cookie` is never replayed. `020`'s Fetcher already keeps no cookies, and this change pins that.
- **Timeouts and retries:**
  - `--timeout <s>` (default 20), which also sets `020`'s watchdog.
  - `--retries <n>` (default 2), with 1 s/2 s backoff. `Retry-After` is honoured up to 120 s, and 429 pauses the host. `020`'s Requester retries around the Fetcher, which makes one attempt per call, and a retry does not count again towards `--max-urls`.
  - The `urls.attempt_count` column.
- **Redirects:**
  - Followed hop by hop, by the engine. Every hop is a `urls` row with `redirect_location`/`redirect_url_id`, and a target keeps the Crawl Depth of its source.
  - `--max-redirects <n>` (default 10). Loops are marked with `in_redirect_loop`.
  - A Seed that redirects within its registrable domain extends the Scope, once, when its Redirect Chain ends. An off-site Seed redirect is a warning.
  - A meta refresh stays a Link, never a redirect hop.
- **Limits:** response bodies are read up to 20 MiB, before and after decoding (`body_truncated`, `parse_error = body_too_large`), and URLs longer than 2,000 characters are skipped (`url_too_long`).
- **Compression:** gzip, deflate and br, decoded by the tool; zstd from v0.2, so v0.1 sends `Accept-Encoding: gzip, deflate, br`. From v0.2 the default adds zstd, while an explicit custom `Accept-Encoding` replaces the default on Internal requests, including subsets, identity, weights and unsupported coding names. Decoding depends on supported response codings, not what that request advertised; unsupported responses keep `unsupported_encoding`. All body and decoder bounds remain. The `content_encoding`, `size_bytes` and `transferred_bytes` columns record status and size checks for Resources.
- **TLS trust:** certificates are verified with truststore (the OS trust store), falling back to certifi only when truststore cannot be loaded. A speed test records the cost of this policy; it does not select the trust store. Failures are `tls_error`.
- **HTTP version:** one bounded ALPN probe per requested https origin per run gives `origins.http_version` = `http_2` or `http_1_1` (v0.2), or NULL on failure. It measures offered capability; crawler requests keep HTTP/1.1 transport. The probe uses the request's DNS, TLS trust and effective proxy, and is cancelled and joined on stop. In v0.1 the column exists and is NULL, and its description starts with `Filled from v0.2. `.
- **The `response_headers` table:** one JSON row per URL with a response, keyed by `url_id`. Headers keep their received order and letter case, and cookie values in `Set-Cookie` and `Cookie` are stored as `***`, with their names and attributes kept.
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
- `crawling`: the existing delta extends the network pause and watchdog contracts for request deadlines and retries. ALPN measurement does not contribute to either URL attempts or the network pause.

## Non-goals

- Redirect Chain views (`redirects`, with per-hop headers and timing): **v0.2**. The per-hop data is recorded now.
- HTTP/2 or HTTP/3 transport, and HTTP/3 detection: **backlog**. Requests use HTTP/1.1, and `http_version` reports what the origin offers.
- SOCKS proxies, cookie sessions, `--insecure`, and extra CA files for users: see design.md, Open Questions.
- Anything that decides which URLs are requested or followed: `020-add-crawl-core`.

## Impact

- **Depends on:**
  - `020-add-crawl-core`: the Fetcher interface, engine, per-host limits, settings, context builder, Hooks, DNS resolver hook, store records, Requester, RateGate, Scope, Resource checks, robots.txt, fake Fetcher and network pause already in the base.
  - `015-add-crawl-store`: whole and partial redaction, and secret settings.
  - `017-speed-up-crawl-writer`: the writer through which `020`'s units run, and its unit contract.
  - `018-add-schema-conventions`: `public_table()` and the schema contract test.
  - `010-add-workspace-and-cli-contract`: settings and exit codes.
  - `000-scaffold-project`: the fixture site harness.
- **Used by:**
  - `030` (sizes, redirect data, `http_version`, `response_headers`)
  - `050` (`page --headers`, and the `resources` export)
  - `060` (resume Commands supply fresh credentials to the continue service; they are not a prerequisite for this change)
  - `080` (`doctor`'s TLS check reuses this TLS setup)
- **Code:**
  - `openlinx.crawl.fetch.fetcher` (`020`'s module): `FetchPolicy`, the policy Fetcher, its decoding and its proxy choice
  - `openlinx.crawl.fetch.requester` and `openlinx.crawl.robots`: per-hop Internal classification for requests, retries and robots.txt redirects
  - `openlinx.crawl.fetch.tls`: the TLS setup that `080`'s `doctor` reuses, and from v0.2 the ALPN check
  - `openlinx.crawl.engine`: redirects, the open depth read again, and the Seed-redirect Scope rule
  - `openlinx.crawl.scope`: the URL length limit in `ScopeRules.decide`
  - `openlinx.crawl.settings` and `openlinx.cli.crawl`: the new keys and options
  - `openlinx.store.schema` and `openlinx.store.urls`: the new columns, the index and the redirect units
  - `openlinx.store.response_headers`: the `response_headers` table's row writer
  - `openlinx.services.crawling`: the Fetcher factory, the `environment` table, fresh continue secrets and refusal before opening a writer or network connection
  - settings and CLI metadata, and `openlinx.store.redaction`: explicit whole/header/URL secret forms, preserving the public boolean secret indicator
- **Dependencies:** the existing TLS and compression dependencies remain. **(v0.2)** use `compression.zstd` on Python 3.14 and conditional `backports.zstd` on 3.12–3.13, with the same incremental API and an explicit window bound. Lockfile, dependency allowlist and compatibility checks accompany its first use. The future Page source encoder in `030` can reuse this API without becoming a prerequisite.
- **Docs:** the fetching part of `docs/crawling.md` (identity, credentials, proxy, retries, redirects, limits, compression, TLS, HTTP version).
