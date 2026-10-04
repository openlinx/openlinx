> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

Each task below is one vertical TDD slice and one commit. It is done when:
1. the test for the named scenario, or trivial pair of scenarios, written first at the named seam, fails for the right reason
2. only enough code is written to make it pass
3. ruff, the strict type checker and the full suite (with the coverage gate) pass
4. the commit message names the scenario

A slice that needs a new column, enumeration value or table adds it, with its description, and updates `docs/schema.md` in the same commit.

Seams (docs/testing.md):
- **[Pure]**: seam 4, pure-logic modules
- **[HTTP]**: seam 3, the real crawler against the fixture site
- **[3+6]**: crawl the fixture site, then read the documented tables read-only
- **[CLI]**: seam 1, `CliRunner`
- **[Fake timing]**: `020`'s fake Fetcher plus the injectable clock, for timing scenarios only
- **[Fixture]**: a new fixture-site or test-support capability, test-first in `tests/fixture_site/` or `tests/support/`

## 1. Request identity and credentials

- [ ] 1.1 [HTTP] Drive "The default user agent identifies the tool".
- [ ] 1.2 [HTTP] Drive "A custom user agent is used on every request": `--user-agent`.
- [ ] 1.3 [HTTP] Drive "A custom header is sent to Internal URLs": `--header` with the `crawl.header` setting.
- [ ] 1.4 [HTTP] Drive "A custom header never goes to External URLs", on `020`'s two fixture instances.
- [ ] 1.5 [CLI] Drive "A malformed header is rejected".
- [ ] 1.6 [3+6] Drive "A cookie header keeps its name and hides its value": declare `--header` and `crawl.header` a header secret for `015`.
- [ ] 1.7 [HTTP] Drive "Credentials are sent to Internal URLs": `--auth`, marked secret.
- [ ] 1.8 [HTTP] Drive "Credentials never go to External URLs".
- [ ] 1.9 [3+6] Drive "The recorded command hides the password".
- [ ] 1.10 [HTTP] Drive "Credentials in spider.toml are used".
- [ ] 1.11 [Fixture] Add a cookie-echo route that sets a cookie and reports whether a `Cookie` header arrived.
- [ ] 1.12 [HTTP] Drive "Cookies set by the site are not sent back": `DummyCookieJar`.
- [ ] 1.13 Docs: document the user agent, custom headers, basic auth, secrets and cookies in `docs/crawling.md`.
- [ ] 1.14 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. Proxy

- [ ] 2.1 [Fixture] Add a small forward-proxy helper to `tests/support/` that records the requests it relays.
- [ ] 2.2 [HTTP] Drive "Requests go through the proxy": `--proxy`.
- [ ] 2.3 [HTTP] Drive "The HTTP_PROXY variable is honoured": proxy choice from the standard variables. The harness sets `NO_PROXY` for localhost and the fixture site's names.
- [ ] 2.4 [HTTP] Drive "A lower-case proxy variable is honoured".
- [ ] 2.5 [HTTP] Drive "NO_PROXY bypasses the proxy".
- [ ] 2.6 [HTTP] Drive "The proxy flag overrides the proxy variables".
- [ ] 2.7 [3+6] Drive "A proxy password is redacted": mark the proxy password partly secret.
- [ ] 2.8 [3+6] Drive "A proxy password from a variable is redacted": the `environment` table of `crawl.config`.
- [ ] 2.9 Docs: document `--proxy`, `[crawl] proxy`, the proxy variables and `NO_PROXY` in `docs/crawling.md`.
- [ ] 2.10 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. Timeouts and retries

- [ ] 3.1 [3+6] Drive "A hanging response times out": `--timeout`, and the value `timeout` of `fetch_error`.
- [ ] 3.2 [Fixture] Add response sequences to the fixture site (for example 503 once, then 200).
- [ ] 3.3 [3+6] Drive "A temporary 503 is retried": `--retries`, and the `attempts` column.
- [ ] 3.4 [3+6] Drive "A persistent 500 is recorded after the retries".
- [ ] 3.5 [3+6] Drive "A 404 is not retried".
- [ ] 3.6 [Fake timing] Drive "Retries wait one and then two seconds".
- [ ] 3.7 [Fake timing] Drive "Retry-After pauses the host": the host pause in `020`'s gate.
- [ ] 3.8 Docs: document timeouts, retries, backoff and `Retry-After` in `docs/crawling.md`.
- [ ] 3.9 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. Redirects

- [ ] 4.1 [3+6] Drive "Every hop of a Redirect Chain is recorded": `allow_redirects=False`, hops as URL rows, the `redirect_location`/`redirect_url_id` columns and the value `redirect`.
- [ ] 4.2 [3+6] Drive "A relative Location is resolved".
- [ ] 4.3 [3+6] Drive "A redirect without Location has no target".
- [ ] 4.4 [3+6] Drive "A redirect target keeps the depth".
- [ ] 4.5 [3+6] Drive "A redirect to an excluded URL is not followed".
- [ ] 4.6 [3+6] Drive "A redirect to an External URL is checked".
- [ ] 4.7 [Fixture] Add named virtual hosts (routing by `Host` header) to the fixture site, mapped through `020`'s DNS resolver hook.
- [ ] 4.8 [3+6] Drive "A redirect to the www host stays inside the Scope".
- [ ] 4.9 [CLI] Drive "A redirect to another site is reported".
- [ ] 4.10 [3+6] Drive "The eleventh redirect is not followed": `--max-redirects`, and the value `max_redirects`.
- [ ] 4.11 [3+6] Drive "A loop of two URLs is marked": the `redirect_loop` column.
- [ ] 4.12 [HTTP] Drive "A looping URL is requested once".
- [ ] 4.13 [3+6] Drive "A meta refresh is not recorded as a redirect".
- [ ] 4.14 Docs: document Redirect Chains, hop limits, loops, Seed redirects and the meta refresh boundary in `docs/crawling.md`.
- [ ] 4.15 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Limits, compression and Resource sizes

- [ ] 5.1 [3+6] Drive "A huge page is not parsed": the 20 MiB cap, and the `body_truncated` column.
- [ ] 5.2 [3+6] Drive "A very long URL is skipped": the value `url_too_long`.
- [ ] 5.3 [HTTP] Drive "Requests accept compressed bodies".
- [ ] 5.4 [Fixture] Add a raw-bytes route to the fixture site (exact body bytes and headers, for example a precompressed gzip body).
- [ ] 5.5 [3+6] Drive "A compressed Resource records both sizes": decoding in the tool, and the `content_encoding`, `size_bytes` and `transferred_bytes` columns.
- [ ] 5.6 [3+6] Drive "An image's size is recorded".
- [ ] 5.7 Docs: document the limits, compression and the size columns in `docs/crawling.md`.
- [ ] 5.8 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green.

## 6. TLS and HTTP version

- [ ] 6.1 [Fixture] Add HTTPS listeners with a `trustme` CA to the fixture site, and extra trust anchors to the crawler's TLS setup for the test CA. There are four listeners: one selects `h2`, one offers only `http/1.1`, one has a certificate for `other.test` served as `badcert.test`, and one has a certificate from an untrusted CA.
- [ ] 6.2 [3+6] Drive "A certificate for another name is a TLS error": the truststore context with the certifi fallback, and the value `tls_error`.
- [ ] 6.3 [3+6] Drive "A certificate from an unknown CA is a TLS error".
- [ ] 6.4 Speed test: measure TLS handshake time with truststore and with certifi on Windows, macOS and Linux. Record the results in `docs/crawling.md`, and change the default path only if truststore is measurably slower (design D5).
- [ ] 6.5 [3+6] Drive "A plain http origin": the `origins.http_version` column.
- [ ] 6.6 [3+6] Drive "An origin that selects HTTP/2": the ALPN handshake.
- [ ] 6.7 [3+6] Drive "An origin that offers only HTTP/1.1".
- [ ] 6.8 Docs: document TLS trust, the speed-test result and `http_version` in `docs/crawling.md`.
- [ ] 6.9 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.

## 7. Response headers

- [ ] 7.1 [3+6] Drive "Response headers are stored as received": the `response_headers` table.
- [ ] 7.2 [3+6] Drive "A cookie value is not stored": `Set-Cookie` values become `***` before storage.
- [ ] 7.3 [Pure] Drive "A Cookie header is redacted pair by pair".
- [ ] 7.4 Docs: document `response_headers` and the cookie redaction format in `docs/crawling.md`.
- [ ] 7.5 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. Change check

- [ ] 8.1 Verify that every `#### Scenario:` in `specs/fetching/spec.md` has exactly one test named after it. Use a small script over the test ids.
- [ ] 8.2 Verify that the whole suite passes in CI on Windows, macOS and Linux × Python 3.12–3.14 with the coverage gate.
- [ ] 8.3 Review: run the code-review skill on the whole change against `specs/fetching/spec.md`, then refactor with the whole suite green.
