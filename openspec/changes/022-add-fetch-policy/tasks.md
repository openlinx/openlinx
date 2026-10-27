Each task below is one vertical TDD slice and one commit. It is done when:
1. the test for the named scenario, or trivial pair of scenarios, written first at the named seam, fails for the right reason
2. only enough code is written to make it pass
3. ruff, the strict type checker and the full suite (with the coverage gate) pass
4. the commit message names the scenario

A **Guard** is a test that may pass on its first run, since `020` already gives the behaviour; it then shows its red by a mutation, which its commit names.

A slice that needs a new column, index or table adds it through `018`'s `public_table()` (STRICT, and CHECKs from the declared values), with its description, and updates `docs/schema.md` in the same commit. A new table passes `change=22`; a column added to `urls` or `origins` carries no change tag, since `public_table()` tags tables only (design D10). The enumeration values this change writes are already listed by `020`.

An option and its setting are declared by the task that applies them (`020` D11, no inert option), each with `OptionMeta(setting="crawl.<key>")` and its key in `CrawlSettings`: `--user-agent` in 1.2, `--retries` in 3.2, `--timeout` in 3.5 and `--max-redirects` in 4.10.

`response_headers` rows follow `020` D9 and D14: `handler("response_headers", handle, write)` in `default_hooks()` (`spider.services.hooks`), whose writer takes a URL's rows as one sequence and runs one `executemany` of a statement built once (`017` D9).

A value that a handler or the store needs from a response goes on `020`'s `UrlResponse` (`UrlResult.response`), and a request that got none keeps its `UrlFailure` (`UrlResult.failure`); the store record is built from them (`020` task 5.20).

**v0.1 and v0.2:** groups 1–8 are 022-min, in v0.1 (ROADMAP). Groups 9–12 are marked (v0.2) and wait for v0.2.

**Order against `020`:** this change builds on `020`'s accepted code with its `UrlResult` shape (`020` tasks 5.19–5.25), merged in at the manager's SHA. A task that needs a part of `020` that is not merged yet says "after `020` task N": 12.0 (the auto-advancing clock), 12.14 (the watchdog) and 16.1 (the scenario script) are still open.

Seams (docs/testing.md):
- **[Pure]**: seam 4, pure-logic modules
- **[HTTP]**: seam 3, the real crawler against the fixture site
- **[3+6]**: crawl the fixture site, through `crawl_result` (`tests/support/crawling.py`) or `crawled` (the CLI), both on the real clock, then read the documented tables read-only. A retry test there waits its real backoff (design, Test seams).
- **[2]**: seam 2, a store module through the writer, with `replay_now(writer)` (`017` D7)
- **[CLI]**: seam 1, `CliRunner`
- **[Fake timing]**: `020`'s fake Fetcher (`tests/support/fetcher.py`) plus `FakeClock`, through the context builder, for timing scenarios only
- **[Fixture]**: a new fixture-site or test-support capability, test-first in `tests/fixture_site/` or `tests/support/`

## 1. Request identity and cookies

- [x] 1.0 Refactor, behaviour unchanged: the Crawl Service opens the Fetcher through one factory that takes a frozen `FetchPolicy` and the clock, and the factory replaces `start_crawl`'s `resolver=` and `fetcher=` keywords (design D1). `plan_crawl` builds the policy; `crawl_result` keeps its own keywords and builds the factory from them, so its callers do not change. After `020` task 5.24, which edits the same Fetcher.
- [x] 1.1 [HTTP] Drive "The default user agent identifies the tool": the session's `User-Agent` from `FetchPolicy`, built from `APP_NAME`, `spider.__version__` and a `PROJECT_URL` constant next to `APP_NAME` in `spider.naming`, the repository's URL until the product is named (design D1). No `User-Agent` is set today, so aiohttp's own goes out.
- [x] 1.2 [HTTP] Drive "A custom user agent is used on every request", and [CLI] "An invalid user agent is rejected", a pair: `--user-agent` and `crawl.user_agent`, which `setting_rules` refuses when it is empty or holds CR, LF or another control character. robots.txt goes through the same Requester and Fetcher, so its request carries it too.
- [x] 1.3 [HTTP] **Guard:** "Cookies set by the site are not sent back". `020`'s Fetcher already has a `DummyCookieJar`. `/` sets the cookie through the route's `headers`, and the request log shows the request for `/check`.
- [x] 1.4 Docs: document the user agent and cookies in `docs/crawling.md`.
- [ ] 1.5 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. Proxy variables

- [ ] 2.1 [Fixture] Add a small forward-proxy helper to `tests/support/` that records the requests it relays. It resolves the fixture's names itself through `hosts_for` and `FixtureResolver`, since a proxied request leaves name resolution to the proxy.
- [ ] 2.2 [HTTP] Drive "The HTTP_PROXY variable is honoured": `getproxies_environment()` read once in `plan_crawl` into `FetchPolicy`, and the proxy chosen per request from that snapshot, with `trust_env=False` (design D1). `000`'s proxy isolation removes the variables before every test, so the test sets them with `monkeypatch.setenv`.
- [ ] 2.3 [HTTP] Drive "A lower-case proxy variable is honoured".
- [ ] 2.4 [HTTP] Drive "NO_PROXY bypasses the proxy": `proxy_bypass_environment(host, proxies=snapshot)`, inside a pure `proxy_for(url, snapshot)`, with a [Pure] table of its cases: the lower-case variable wins, `NO_PROXY` bypasses, and `ALL_PROXY` is ignored (`test_the_proxy_of_a_url`, design Risks).
- [ ] 2.5 [3+6] Drive "A proxy password from a variable is redacted": the Crawl Service adds the `environment` table of the same snapshot to `crawl.config`, and `environment.http_proxy` and `environment.https_proxy` to `NewCrawl.secret_names` (design D8). `crawl_result` passes empty `SecretNames()`, so the service, not the test helper, must add them, or the test cannot go red.
- [ ] 2.6 Docs: document the proxy variables and `NO_PROXY` in `docs/crawling.md`, and correct `ENVIRONMENT` in `spider.cli.commands`, which names a `--proxy` that v0.1 lacks, with the `commands.json` snapshot.
- [ ] 2.7 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. Timeouts and retries

- [ ] 3.1 [Fixture] Add response sequences to the fixture site, a new route kind (for example 503 once, then 200).
- [ ] 3.2 [3+6] Drive "A temporary 503 is retried": `--retries` and `crawl.retries`, the retry loop around the Fetcher in `020`'s Requester (design D4, `020` D7), and the `attempt_count` column, a top-level field of `UrlResult`: `Requester.request_url` returns the outcome with its count, and `FetchedUrl` and `ErroredUrl` copy it. A retry is the same URL: only its first attempt counts towards `--max-urls`, each attempt takes the host's slot and its `--rate` turn again, and the backoff holds no slot.
- [ ] 3.3 [3+6] Drive "A persistent 500 is recorded after the retries".
- [ ] 3.4 [3+6] **Guard:** "A 404 is not retried".
- [ ] 3.5a [Pure] `fetch_error_of` maps `TimeoutError`, from which aiohttp's timeouts derive, to `timeout`, checked before the fallback to `connection_error`; the table in `tests/crawl/test_fetcher.py` that pins them to `connection_error` flips (design D1, Risks).
- [ ] 3.5 [3+6] Drive "A hanging response times out": `--timeout` and `crawl.timeout`, finite and above 0 through `setting_rules`, through `FetchPolicy` in place of `_REQUEST_DEADLINE_SECONDS`. The timeout feeds `020`'s `watchdog_seconds` here if `020` task 12.14 is merged, or in that task otherwise.
- [ ] 3.6 [Fixture] Add a route option for a body that stalls after its headers and one that trickles forever, test-first (`delay` and `hang` act before the headers). Then **Guard:** a trickling body ends as `timeout` within `--timeout` (`test_a_trickling_body_times_out`, design Risks).
- [ ] 3.7a [Fixture] Let `020`'s fake Fetcher answer a status, headers and a response sequence per path, test-first in `tests/support/`.
- [ ] 3.7 [Fake timing] Drive "Retries wait one and then two seconds".
- [ ] 3.8 [Fake timing] Drive "Retry-After pauses the host": the host's next allowed start in `020`'s `RateGate`, which must also act without `--rate`. After `020` task 12.0, since the pause makes requests wait concurrently.
- [ ] 3.9 Docs: document timeouts, retries, backoff, `Retry-After` and the network pause's view of a retry in `docs/crawling.md`.
- [ ] 3.10 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. Redirects

- [ ] 4.0 Refactor, behaviour unchanged: one `insert_urls` helper in `spider.store.urls` records the rows' origins before it inserts them, and `record_seed` and `record_fetched` insert through it, so no inserter can forget the origin (design D2). A guard test refuses any other insert into `urls`, red by a mutation that inserts directly.
- [ ] 4.1 [3+6] Drive "Every hop of a Redirect Chain is recorded", and [CLI] "Index of redirect targets", a pair: `REDIRECT_STATUSES` and the pure `redirect_target(url, status, location, strip_params)` in `spider.crawl.following`, which the robots.txt loader calls too, carried on `UrlResponse.redirect_target`; the target recorded by the unit of the 3xx response through `insert_urls` at the source's Crawl Depth, the `redirect_location` column, `redirect_url_id` as a declared reference with the partial index `urls_redirect_url_id`, and writing the value `redirect`. Done when: `_crawl_depth` reads the open depth again after its tasks end, so a target recorded at the open depth, or a URL lowered to it below the read cursor, is dispatched in the same run, and no in-flight URL of that depth is dispatched twice (design D2).
- [ ] 4.2 [3+6] **Guard:** "A relative Location is resolved": `redirect_target` resolves through `020`'s `resolve_reference` with the Crawl's `strip_params` (design D2).
- [ ] 4.3 [3+6] Drive "A redirect without Location has no target", with the fixture's `Status(302)`. Done when: a Location that gives no `NormalizedUrl`, and a 300, 304 or 305 response, have no target either, by a [Pure] table of `redirect_target` (`test_a_location_that_is_no_http_url_has_no_target`, design Risks).
- [ ] 4.4 [3+6] **Guard:** "A redirect target keeps the depth", red by a mutation that records the target at depth + 1.
- [ ] 4.5 [3+6] **Guard:** "A redirect to an excluded URL is not followed".
- [ ] 4.6 [3+6] Drive "A redirect to an External URL is checked", on `020`'s `fixture_hosts`. The target is recorded for any 3xx, whatever the source's Scope, outside the branch that follows Links.
- [ ] 4.7 [Fixture] Let `fixture_hosts` take a site per name (design D9), test-first in `tests/fixture_site/test_hosts.py`.
- [ ] 4.8 [3+6] Drive "A redirect to the apex host stays inside the Scope", and "A Seed chain that ends off its site widens nothing", a pair (design D3). `Run` holds the Seed chain's state, open with its provisional Scope, which admits only the hosts of the Seed's registrable domain and only for a target of the chain. The final URL's unit closes it once: it writes `is_internal` and `in_scope` of every URL of the chain against the final Scope, and, when the chain ends on the Seed's registrable domain with a response, appends the host to `crawl.scope`; then the context is replaced and `pages.start` runs. Done when: every hop of a two-hop chain is checked, not only the last.
- [ ] 4.8a [3+6] Drive "A www Seed that redirects on its host is checked on its final Page": `020`'s `seed_base_mismatch` reads the final Page of the Seed's Redirect Chain (design D3).
- [ ] 4.8b [3+6] Drive "A redirected image beyond the depth limit is checked": a redirect target keeps its source's checked status, so the depth limit and the depth barrier treat it as a Resource (design D2).
- [ ] 4.9 [CLI] Drive "A redirect to another site is reported". Done when: `seed_redirected_off_site` is declared.
- [ ] 4.10 [3+6] Drive "The eleventh redirect is not followed": `--max-redirects` and `crawl.max_redirects`, the hop count walked back over `found_on_url_id` (design D2), on the fixture's `redirect_chain("/r", 11, "/r12")`, writing the value `max_redirects`, which joins `DiscoverySkipReason`, so a Link found later queues the URL again.
- [ ] 4.11 [3+6] Drive "A loop of two URLs is marked": the `in_redirect_loop` column, 0 for any other 3xx, and 1 for a URL that redirects to itself.
- [ ] 4.12 [HTTP] **Guard:** "A looping URL is requested once".
- [ ] 4.13 [3+6] **Guard:** "A meta refresh is not recorded as a redirect".
- [ ] 4.14 Docs: document Redirect Chains, hop limits, loops, Seed redirects and the meta refresh boundary in `docs/crawling.md`, and that a redirect is not a Link.
- [ ] 4.15 Review: run the code-review skill on group 4's commits, also against `017`'s unit contract (D7) for the redirect, hop-count and loop units, then refactor with the whole suite green.

## 5. Limits, compression and Resource sizes

- [ ] 5.1 [3+6] Drive "A huge page is not parsed": the 20 MiB cap in `read_body` of `spider.crawl.fetch.body`, with [Pure] tests of the cap on real bytes, and the `body_truncated` column, through `FetchResult`, `UrlResponse` and `FetchedUrl` (design D1); the URL's unit gives a capped HTML body `PreparedPage(parse_error="body_too_large")` instead of preparing it. On the fixture's `LargeFile` with `content_type="text/html"`.
- [ ] 5.2 [3+6] Drive "A very long URL is skipped": `ScopeRules.decide` gives `url_too_long` before its patterns (design D12).
- [ ] 5.3 [HTTP] Drive "Requests accept compressed bodies": `auto_decompress=False` and an explicit `Accept-Encoding: gzip, deflate, br` in `aiohttp_fetcher`, and the `brotli` dependency with its allowlist line.
- [ ] 5.4 [Fixture] **Guard:** a precompressed gzip file from a site folder, served with `Page(file=..., content_type="text/javascript", headers=[("Content-Encoding", "gzip")])`, keeps its bytes (design D9).
- [ ] 5.5 [3+6] Drive "A compressed Resource records both sizes": decoding in `read_body` with decoders bounded in output, and the `content_encoding`, `size_bytes` and `transferred_bytes` columns (design D1). Done when: the 20 MiB cap applies to the decoded size too, and raw deflate is decoded, by [Pure] tests on real compressed bytes (`test_a_compressed_body_is_capped_after_decoding`, design Risks).
- [ ] 5.5a [3+6] Drive "Stacked encodings are decoded in reverse order", "A corrupt compressed body is an invalid response" and "A body in an encoding that was not offered is not parsed", on real compressed bytes, with the `parse_error` value `unsupported_encoding` (design D1, D10).
- [ ] 5.6 [3+6] Drive "An image's size is recorded".
- [ ] 5.7 Docs: document the limits, compression and the size columns in `docs/crawling.md`.
- [ ] 5.8 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green.

## 6. TLS

- [ ] 6.1 [Fixture] Add HTTPS listeners with a `trustme` CA to the fixture site, which the DNS resolver hook maps from port 443 of a name, so `FixtureResolver` is keyed by name and port: one for `site.test`, one with a certificate for `other.test` served as `badcert.test`, and one with a certificate from an untrusted CA. The crawler's TLS setup takes extra trust anchors for the test CA through the Fetcher factory of 1.0 (design D5). `trustme` is a dev dependency.
- [ ] 6.2 [3+6] Drive "A certificate for another name is a TLS error": the truststore context with the certifi fallback in `spider.crawl.fetch.tls`, both runtime dependencies with their allowlist lines, imported only from `spider.crawl.fetch`. `aiohttp.ClientSSLError` → `tls_error` is `020`'s already. A [Pure] test covers the fallback branch.
- [ ] 6.3 [3+6] Drive "A certificate from an unknown CA is a TLS error".
- [ ] 6.4 Speed test: measure TLS handshake time with truststore and with certifi on Windows, macOS and Linux. Record the results in `docs/crawling.md`, and change the default path only if truststore is measurably slower (design D5).
- [ ] 6.5 [CLI] Drive "The HTTP version is a later column" (v0.1): `origins.http_version` declared NULL in every row, with its values from a `Literal` in `spider.store.records` and a description that starts with `Filled from v0.2. `. It is the first later column, so `018`'s guard over derived and later columns gains the assertion that it saw one.
- [ ] 6.6 Docs: document TLS trust, the speed-test result and `http_version` (NULL in v0.1) in `docs/crawling.md`.
- [ ] 6.7 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.

## 7. Response headers

- [ ] 7.1 [3+6] Drive "Response headers are stored as received", and [CLI] "Columns of response_headers", a pair: the `response_headers` table, declared through `018`'s `public_table()` with `url_id` as its primary key and a declared reference, and no secondary index; `handler("response_headers", handle, write)` in `default_hooks()`, whose `handle` returns no row for a `UrlResult` without a `response`, and whose writer runs a plain INSERT, with a [2] replay test of the writer (design D7, Risks).
- [ ] 7.2 [3+6] Drive "A cookie value is not stored": the Fetcher redacts `Set-Cookie` values where it decodes the received headers, so `FetchResult.headers` never holds one (design D7).
- [ ] 7.3 [Pure] Drive "A Cookie header is redacted pair by pair", over the same function.
- [ ] 7.4 Docs: document `response_headers` and the cookie redaction format in `docs/crawling.md`.
- [ ] 7.5 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. Change check (v0.1)

- [ ] 8.1 Verify that every `#### Scenario:` in `specs/fetching/spec.md` that groups 1–7 drive has exactly one test named after it, with `020` task 16.1's scenario script made generic over the spec path.
- [ ] 8.2 Verify that the whole suite passes in CI on Windows, macOS and Linux × Python 3.12–3.14 with the coverage gate.
- [ ] 8.3 **Guard:** every code this change declares (design D11) is listed by `spider commands` with its level and exit code [CLI], with the `commands.json` snapshot.
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
