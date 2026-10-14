> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

Each task below is one vertical TDD slice and one commit. It is done when:
1. the test for the named scenario, or trivial pair of scenarios, written first at the named seam, fails for the right reason
2. only enough code is written to make it pass
3. ruff, the strict type checker and the full suite (with the coverage gate) pass
4. the commit message names the scenario

A slice that needs a new column, index or table adds it through `018`'s `public_table()` (STRICT, and CHECKs from the declared values), with its description and `info={"change": 22}`, and updates `docs/schema.md` in the same commit. The enumeration values this change writes are already listed by `020` (design D10).

An option and its setting are declared by the task that applies them (`020` D11, no inert option), each with `OptionMeta(setting="crawl.<key>")` and its key in `CrawlSettings`: `--user-agent` in 1.2, `--retries` in 3.2, `--timeout` in 3.5 and `--max-redirects` in 4.11.

`response_headers` rows follow `020` D9 and D14: this change's handler returns them, and `spider.store.response_headers` writes them through the row writer it registers in `Hooks.row_writers`, with statements built once (`017` D9), both listed in `default_hooks()` (`spider.services.hooks`).

**v0.1 and v0.2:** groups 1–8 are 022-min, in v0.1 (ROADMAP). Groups 9–12 are marked (v0.2) and wait for v0.2.

**Order against `020`:** this change starts once `020`'s first pull request (its groups 1–6) is on main. A task that needs a later part of `020` says "after `020` task N", and waits until that task is on main.

Seams (docs/testing.md):
- **[Pure]**: seam 4, pure-logic modules
- **[HTTP]**: seam 3, the real crawler against the fixture site
- **[3+6]**: crawl the fixture site, through `crawl_result` (`tests/support/crawling.py`) or `crawled` (the CLI), both on the real clock, then read the documented tables read-only. A retry test there waits its real backoff (design, Test seams).
- **[2]**: seam 2, a store module through the writer, with `replay_now(writer)` (`017` D7)
- **[CLI]**: seam 1, `CliRunner`
- **[Fake timing]**: `020`'s fake Fetcher plus `FakeClock`, through the context builder, for timing scenarios only
- **[Fixture]**: a new fixture-site or test-support capability, test-first in `tests/fixture_site/` or `tests/support/`

## 1. Request identity and cookies

- [ ] 1.1 [HTTP] Drive "The default user agent identifies the tool": the session's `User-Agent` in `aiohttp_fetcher`, built from `spider.naming` and the tool's version, with a `PROJECT_URL` constant next to `APP_NAME` (design D1).
- [ ] 1.2 [HTTP] Drive "A custom user agent is used on every request": `--user-agent` and `crawl.user_agent`. Its robots.txt half comes after `020` task 10.4.
- [ ] 1.3 [HTTP] **Guard:** "Cookies set by the site are not sent back". `020`'s Fetcher already has a `DummyCookieJar`, so the test may pass on its first run; it then shows its red by a mutation. `/` sets the cookie through the route's `headers`, and the request log shows the request for `/check`.
- [ ] 1.4 Docs: document the user agent and cookies in `docs/crawling.md`.
- [ ] 1.5 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. Proxy variables

- [ ] 2.1 [Fixture] Add a small forward-proxy helper to `tests/support/` that records the requests it relays.
- [ ] 2.2 [HTTP] Drive "The HTTP_PROXY variable is honoured": the proxy chosen per request from `getproxies_environment()`, read when the run starts, with `trust_env=False` (design D1). `000`'s proxy isolation removes the variables before every test, so the test sets them with `monkeypatch.setenv`.
- [ ] 2.3 [HTTP] Drive "A lower-case proxy variable is honoured".
- [ ] 2.4 [HTTP] Drive "NO_PROXY bypasses the proxy": `proxy_bypass_environment()`.
- [ ] 2.5 [3+6] Drive "A proxy password from a variable is redacted": the `environment` table of `crawl.config`, with `environment.http_proxy` and `environment.https_proxy` in `SecretNames.settings` (design D8).
- [ ] 2.6 Docs: document the proxy variables and `NO_PROXY` in `docs/crawling.md`.
- [ ] 2.7 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. Timeouts and retries

- [ ] 3.1 [Fixture] Add response sequences to the fixture site, a new route kind (for example 503 once, then 200).
- [ ] 3.2 [3+6] Drive "A temporary 503 is retried": `--retries` and `crawl.retries`, the engine's retry loop around the Fetcher (design D4), and the `attempt_count` column.
- [ ] 3.3 [3+6] Drive "A persistent 500 is recorded after the retries".
- [ ] 3.4 [3+6] Drive "A 404 is not retried".
- [ ] 3.5 [3+6] Drive "A hanging response times out": `--timeout` and `crawl.timeout` in place of `_REQUEST_DEADLINE_SECONDS`, and `TimeoutError` → `timeout` (design D1). The timeout feeds `020`'s `watchdog_seconds` here if `020` task 12.14 is on main, or in that task otherwise.
- [ ] 3.6 [Fixture] Add a route option for a body that stalls after its headers and one that trickles forever, test-first. Then **Guard:** a trickling body ends as `timeout` within `--timeout` (`test_a_trickling_body_times_out`, design Risks).
- [ ] 3.7 [Fake timing] Drive "Retries wait one and then two seconds", after `020`'s fake Fetcher (its groups 11 and 12).
- [ ] 3.8 [Fake timing] Drive "Retry-After pauses the host": the host's next allowed start in `RequestLimits`, after `020` task 11.1.
- [ ] 3.9 Docs: document timeouts, retries, backoff, `Retry-After` and the network pause's view of a retry in `docs/crawling.md`.
- [ ] 3.10 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. Redirects

- [ ] 4.1 [3+6] Drive "Every hop of a Redirect Chain is recorded", and [CLI] "Index of redirect targets", a pair: hops as URL rows recorded by the engine, the `redirect_location` column, `redirect_url_id` as a declared reference with the partial index `urls_redirect_url_id`, and writing the value `redirect`. Done when: `_crawl_depth` reads the open depth again after its tasks end, so a target recorded at the open depth is dispatched in the same run (design D2).
- [ ] 4.2 [3+6] Drive "A relative Location is resolved": through a public function made of `_resolved` in `spider.crawl.links` (design D2).
- [ ] 4.3 [3+6] Drive "A redirect without Location has no target", with the fixture's `Status(302)`. Done when: a Location that gives no `NormalizedUrl` has no target either, by a [Pure] table (`test_a_location_that_is_no_http_url_has_no_target`, design Risks).
- [ ] 4.4 [3+6] Drive "A redirect target keeps the depth".
- [ ] 4.5 [3+6] Drive "A redirect to an excluded URL is not followed".
- [ ] 4.6 [3+6] Drive "A redirect to an External URL is checked", on `020`'s `fixture_hosts`.
- [ ] 4.7 [Fixture] Let `fixture_hosts` take a site per name (design D9), test-first in `tests/fixture_site/test_hosts.py`.
- [ ] 4.8 [3+6] Drive "A www Seed that redirects to its apex keeps the apex inside the Scope", after `020` tasks 8.11 and 14.2: the Seed's Redirect Chain widens the Scope once, at its end and before its final Page is prepared, with the wider `ScopeRules`, the page executor's new settings snapshot, `crawl.scope.hosts` and the chain's earlier rows updated in the final hop's unit, and a continue that builds the Scope from `crawl.scope` (design D3, the user's decision of 2026-10-14).
- [ ] 4.9 [3+6] Drive "A redirect to another subdomain stays inside the Scope": the added host without a `www.` host, since `en.site.test` is no registrable domain, and `crawl.scope` lists it.
- [ ] 4.10 [CLI] Drive "A redirect to another site is reported". Done when: `seed_redirected_off_site` is declared.
- [ ] 4.11 [3+6] Drive "The eleventh redirect is not followed": `--max-redirects` and `crawl.max_redirects`, the hop count walked back over `found_on_url_id` (design D2), on the fixture's `redirect_chain("/r", 11, "/r12")`, and writing the value `max_redirects`.
- [ ] 4.12 [3+6] Drive "A loop of two URLs is marked": the `in_redirect_loop` column.
- [ ] 4.13 [HTTP] Drive "A looping URL is requested once".
- [ ] 4.14 [3+6] Drive "A meta refresh is not recorded as a redirect", after `020` task 7.7.
- [ ] 4.15 Docs: document Redirect Chains, hop limits, loops, Seed redirects and the meta refresh boundary in `docs/crawling.md`.
- [ ] 4.16 Review: run the code-review skill on group 4's commits, also against `017`'s unit contract (D7) for the redirect, hop-count and loop units, then refactor with the whole suite green.

## 5. Limits, compression and Resource sizes

- [ ] 5.1 [3+6] Drive "A huge page is not parsed": the 20 MiB cap, and the `body_truncated` column, on the fixture's `LargeFile` with `content_type="text/html"`.
- [ ] 5.2 [3+6] Drive "A very long URL is skipped": `ScopeRules.decide` gives `url_too_long` before its patterns (design D12).
- [ ] 5.3 [HTTP] Drive "Requests accept compressed bodies": `auto_decompress=False` and an explicit `Accept-Encoding: gzip, deflate, br`.
- [ ] 5.4 [Fixture] Serve a precompressed gzip file from a site folder with `Page(file=..., headers=[("Content-Encoding", "gzip")])`, test-first; add a raw-bytes route kind only if that cannot serve it (design D9).
- [ ] 5.5 [3+6] Drive "A compressed Resource records both sizes", after `020` task 9.1: decoding in the tool, and the `content_encoding`, `size_bytes` and `transferred_bytes` columns. Done when: the 20 MiB cap applies to the decoded size too (`test_a_compressed_body_is_capped_after_decoding`, design Risks).
- [ ] 5.6 [3+6] Drive "An image's size is recorded", after `020` task 9.1.
- [ ] 5.7 Docs: document the limits, compression and the size columns in `docs/crawling.md`.
- [ ] 5.8 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green.

## 6. TLS

- [ ] 6.1 [Fixture] Add HTTPS listeners with a `trustme` CA to the fixture site, which the DNS resolver hook maps from port 443 of a name: one for `site.test`, one with a certificate for `other.test` served as `badcert.test`, one with a certificate from an untrusted CA, and one with a self-signed certificate served as `selfsigned.test`. The crawler's TLS setup takes extra trust anchors for the test CA through the context builder (design D5).
- [ ] 6.2 [3+6] Drive "A certificate for another name is a TLS error": the truststore context with the certifi fallback in `spider.crawl.tls`, and `aiohttp.ClientSSLError` → `tls_error`, before `020`'s `ClientConnectorError` branch, so `ClientConnectorCertificateError`, a subclass of both, is no longer `connection_error` (design D1). Done when: a [Pure] table maps each aiohttp exception class to its `fetch_error` (`test_each_request_error_has_its_fetch_error`, design Risks).
- [ ] 6.3 [3+6] Drive "A certificate from an unknown CA is a TLS error". Done when: a self-signed certificate is `tls_error` too, through the OS trust store, on Windows, macOS and Linux in CI (`test_a_self_signed_certificate_is_a_tls_error`, design D5 and Risks).
- [ ] 6.4 Speed test: measure TLS handshake time with truststore and with certifi on Windows, macOS and Linux. Record the results in `docs/crawling.md`, and change the default path only if truststore is measurably slower (design D5).
- [ ] 6.5 [CLI] Drive "The HTTP version is a later column" (v0.1): `origins.http_version` declared NULL in every row, with its values and a description that starts with `Filled from v0.2. `. If it is the first later column in the schema, `018`'s guard over derived and later columns switches on its assertion that it saw one.
- [ ] 6.6 Docs: document TLS trust, the speed-test result and `http_version` (NULL in v0.1) in `docs/crawling.md`.
- [ ] 6.7 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.

## 7. Response headers

- [ ] 7.1 [3+6] Drive "Response headers are stored as received", and [CLI] "Columns of response_headers", a pair: the `response_headers` table, declared through `018`'s `public_table()` with `url_id` as its primary key and a declared reference, and no secondary index; this change's handler and the row writer of `spider.store.response_headers`, listed in `default_hooks()`, with a [2] replay test of the writer (design Risks).
- [ ] 7.2 [3+6] Drive "A cookie value is not stored": the Fetcher redacts `Set-Cookie` values in `FetchResult.headers` (design D7).
- [ ] 7.3 [Pure] Drive "A Cookie header is redacted pair by pair".
- [ ] 7.4 Docs: document `response_headers` and the cookie redaction format in `docs/crawling.md`.
- [ ] 7.5 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. Change check (v0.1)

- [ ] 8.1 Verify that every `#### Scenario:` in `specs/fetching/spec.md` that groups 1–7 drive has exactly one test named after it, with a small script over the test ids. The scenarios of groups 9–12 are checked when v0.2 builds them.
- [ ] 8.2 Verify that the whole suite passes in CI on Windows, macOS and Linux × Python 3.12–3.14 with the coverage gate.
- [ ] 8.3 **Guard:** every code this change declares (design D11) is listed by `spider commands` with its level and exit code [CLI].
- [ ] 8.4 Review: run the code-review skill on the whole change against `specs/fetching/spec.md`, then refactor with the whole suite green.

## 9. (v0.2) Custom headers and credentials

- [ ] 9.1 [HTTP] Drive "A custom header is sent to Internal URLs": `--header` with the `crawl.header` setting, and `Request` carries its dispatch decision's `is_internal` (design D1).
- [ ] 9.2 [HTTP] Drive "A custom header never goes to External URLs", on `020`'s two fixture instances.
- [ ] 9.3 [CLI] Drive "A malformed header is rejected".
- [ ] 9.4 [3+6] Drive "A cookie header keeps its name and hides its value": declare `--header` and `crawl.header` a header secret, the header form of `015`'s redaction.
- [ ] 9.5 [HTTP] Drive "Credentials are sent to Internal URLs": `--auth`, marked secret.
- [ ] 9.6 [HTTP] Drive "Credentials never go to External URLs".
- [ ] 9.7 [3+6] Drive "The recorded command hides the password".
- [ ] 9.8 [HTTP] Drive "Credentials in spider.toml are used".
- [ ] 9.9 Docs: document custom headers, basic auth and secrets in `docs/crawling.md`.
- [ ] 9.10 Review: run the code-review skill on group 9's commits, then refactor with the whole suite green.

## 10. (v0.2) The proxy flag

- [ ] 10.1 [HTTP] Drive "Requests go through the proxy": `--proxy` and `crawl.proxy`.
- [ ] 10.2 [HTTP] Drive "The proxy flag overrides the proxy variables".
- [ ] 10.3 [3+6] Drive "A proxy password is redacted": mark `--proxy` a URL secret.
- [ ] 10.4 Docs: document `--proxy` and `[crawl] proxy` in `docs/crawling.md`.
- [ ] 10.5 Review: run the code-review skill on group 10's commits, then refactor with the whole suite green.

## 11. (v0.2) HTTP version

- [ ] 11.1 [Fixture] Add two HTTPS listeners: one that selects `h2`, and one that offers only `http/1.1`.
- [ ] 11.2 [3+6] Drive "A plain http origin": filling `origins.http_version`.
- [ ] 11.3 [3+6] Drive "An origin that selects HTTP/2": the ALPN handshake (design D6).
- [ ] 11.4 [3+6] Drive "An origin that offers only HTTP/1.1".
- [ ] 11.5 Docs: document `http_version` and the ALPN check in `docs/crawling.md`.
- [ ] 11.6 Review: run the code-review skill on group 11's commits, then refactor with the whole suite green.

## 12. (v0.2) zstd

- [ ] 12.1 [3+6] Add zstd decoding (`zstandard`, or `compression.zstd` on 3.14) and the `zstd` token of `Accept-Encoding` (design D1), with a test of a zstd Resource's two sizes, then run the code-review skill on it.
