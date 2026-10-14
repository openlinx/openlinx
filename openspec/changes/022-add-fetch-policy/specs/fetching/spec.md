## Purpose

Decide how each request of a Crawl is made, and what is recorded about its response:
- request identity, credentials and proxy
- timeouts and retries
- redirects followed hop by hop
- body and URL limits, and compression
- TLS verification, the HTTP version each origin offers, and the response headers

Scenario conventions:
- `{site}` is the origin of the local fixture site, for example `http://127.0.0.1:8765`.
- A bare path such as `/about` means `{site}/about`.
- `site.test`, `www.site.test`, `other.test` and `badcert.test` are virtual hosts of the fixture site, over http and https. The DNS resolver hook maps them to the fixture site, and every other name fails to resolve.
- The fixture's test CA is added to the crawler's trust anchors through the TLS setup.

## ADDED Requirements

### Requirement: User agent
Every request, including robots.txt, SHALL carry the `User-Agent` header `spider/<version> (+<project URL>)` by default, where `<version>` is the tool's version. `--user-agent <string>` (setting `crawl.user_agent`) SHALL replace it on every request.

#### Scenario: The default user agent identifies the tool
- **WHEN** `spider crawl {site}/` runs
- **THEN** every request the fixture site receives has a `User-Agent` that matches `^spider/\d+\.\d+\.\d+\S* \(\+https://\S+\)$`

#### Scenario: A custom user agent is used on every request
- **WHEN** `spider crawl {site}/ --user-agent "AuditBot/1.0"` runs
- **THEN** every request the fixture site receives, including the one for `/robots.txt`, has `User-Agent` = `AuditBot/1.0`

### Requirement: Custom headers
**(v0.2)** `--header "Name: Value"` SHALL add a request header. It SHALL be accepted more than once, and its setting `crawl.header` SHALL be a list of `Name: Value` strings. A value without `:` SHALL be rejected with exit code 2 and error code `invalid_value`. Custom headers SHALL be sent only with requests for Internal URLs and their robots.txt, never with requests for External URLs.

`--header` and `crawl.header` SHALL be declared a header secret. `015-add-crawl-store` then records the value of every sensitive header as `Name: ***`: `Cookie`, and every header whose name contains `auth`, `token`, `secret`, `key` or `password`.

#### Scenario: A custom header is sent to Internal URLs
- **WHEN** `spider crawl {site}/ --header "X-Env: staging"` runs
- **THEN** the request for `/` has the header `X-Env` = `staging`

#### Scenario: A custom header never goes to External URLs
- **WHEN** `http://site.test/` links to `http://other.test/page`, and `spider crawl http://site.test/ --header "X-Env: staging"` runs
- **THEN** the request for `http://other.test/page` has no `X-Env` header

#### Scenario: A malformed header is rejected
- **WHEN** `spider crawl {site}/ --header "NoColon"` runs
- **THEN** the Command exits with code 2 and its only stderr error has `code` = `invalid_value`

#### Scenario: A cookie header keeps its name and hides its value
- **WHEN** `spider crawl {site}/ --header "Cookie: session=abc123"` ends
- **THEN** the `crawl` table of `crawl.config` has `"header": ["Cookie: ***"]`

### Requirement: HTTP basic authentication
**(v0.2)** `--auth <user:password>` (setting `crawl.auth`, marked secret) SHALL send HTTP basic authentication preemptively with every request for an Internal URL and its robots.txt, never with requests for External URLs. The setting SHALL also be accepted from `spider.toml`. `015-add-crawl-store` records it as `***`.

#### Scenario: Credentials are sent to Internal URLs
- **WHEN** `spider crawl http://site.test/ --auth "alice:s3cret"` runs
- **THEN** the request for `http://site.test/` has `Authorization` = `Basic YWxpY2U6czNjcmV0`

#### Scenario: Credentials never go to External URLs
- **WHEN** `http://site.test/` links to `http://other.test/page`, and `spider crawl http://site.test/ --auth "alice:s3cret"` runs
- **THEN** the request for `http://other.test/page` has no `Authorization` header

#### Scenario: The recorded command hides the password
- **WHEN** `spider crawl {site}/ --auth "alice:s3cret"` ends
- **THEN** `crawl.command_argv` is `["spider", "crawl", "{site}/", "--auth", "***"]`

#### Scenario: Credentials in spider.toml are used
- **WHEN** `spider.toml` holds `[crawl]` with `auth = "alice:s3cret"`, and `spider crawl http://site.test/` runs
- **THEN** the request for `http://site.test/` has `Authorization` = `Basic YWxpY2U6czNjcmV0`

### Requirement: Proxy
**(v0.2)** `--proxy <url>` (setting `crawl.proxy`) SHALL send every request, robots.txt included, through the given HTTP proxy, with credentials when the URL contains them.

Without `--proxy` or `[crawl] proxy`, the Crawl SHALL honour the standard proxy variables, as curl, pip and uv do:
- **Which variable:** `HTTP_PROXY` for http URLs and `HTTPS_PROXY` for https URLs.
- **Bypass:** `NO_PROXY`, a comma-separated list of host names and domain suffixes, or `*`, names the hosts that bypass the proxy.
- **Letter case:** each variable is read in any letter case. When both cases are set, the lower-case one wins.

The proxy variables are honoured from v0.1. This is the exception to the no-environment-variables rule of `010-add-workspace-and-cli-contract`. From v0.2, `--proxy` and `[crawl] proxy` SHALL override the variables, and the scenarios that pass `--proxy` apply. A resumed Crawl SHALL read the variables again.

The password in a proxy URL SHALL be marked partly secret, whether it comes from `--proxy` or from a variable, and `015-add-crawl-store` records it as `http://<user>:***@<host>:<port>`. The proxy variables in use SHALL be recorded, set ones only, in the `environment` table of `crawl.config` under the lower-case keys `http_proxy`, `https_proxy` and `no_proxy`.

#### Scenario: Requests go through the proxy
- **WHEN** a test proxy listens on `127.0.0.1:{proxy_port}`, and `spider crawl http://site.test/ --proxy http://127.0.0.1:{proxy_port}` runs
- **THEN** the test proxy receives a request for `http://site.test/`

#### Scenario: The HTTP_PROXY variable is honoured
- **WHEN** `HTTP_PROXY` is `http://127.0.0.1:{proxy_port}`, and `spider crawl http://site.test/` runs
- **THEN** the test proxy receives a request for `http://site.test/`

#### Scenario: A lower-case proxy variable is honoured
- **WHEN** `http_proxy` is `http://127.0.0.1:{proxy_port}`, and `spider crawl http://site.test/` runs
- **THEN** the test proxy receives a request for `http://site.test/`

#### Scenario: NO_PROXY bypasses the proxy
- **WHEN** `HTTP_PROXY` is `http://127.0.0.1:{proxy_port}`, `NO_PROXY` is `site.test`, and `spider crawl http://site.test/` runs
- **THEN** the test proxy receives no request, and the fixture site receives the request for `/`

#### Scenario: The proxy flag overrides the proxy variables
- **WHEN** `HTTP_PROXY` is `http://127.0.0.1:{proxy_port_a}`, and `spider crawl http://site.test/ --proxy http://127.0.0.1:{proxy_port_b}` runs
- **THEN** the test proxy on `{proxy_port_b}` receives a request for `http://site.test/`, and the one on `{proxy_port_a}` receives none

#### Scenario: A proxy password is redacted
- **WHEN** `spider crawl {site}/ --proxy http://u:pw@127.0.0.1:{proxy_port}` ends
- **THEN** `crawl.command_argv` contains `http://u:***@127.0.0.1:{proxy_port}`

#### Scenario: A proxy password from a variable is redacted
- **WHEN** `HTTP_PROXY` is `http://u:pw@127.0.0.1:{proxy_port}`, and `spider crawl http://site.test/` ends
- **THEN** the `environment` table of `crawl.config` has `http_proxy` = `http://u:***@127.0.0.1:{proxy_port}`

### Requirement: No cookies are sent
The Crawl SHALL NOT send cookies that responses set. After a response with `Set-Cookie`, no later request SHALL carry a `Cookie` header unless `--header "Cookie: …"` asks for one.

#### Scenario: Cookies set by the site are not sent back
- **WHEN** `/` answers with `Set-Cookie: sid=abc123` and links to `/check`, and `spider crawl {site}/` runs
- **THEN** the request for `/check` has no `Cookie` header

### Requirement: Timeouts
A request attempt that has not completed within `--timeout` seconds (default 20, setting `crawl.timeout`) SHALL fail. When no attempt for a URL succeeds, the URL SHALL be recorded with `fetch_state` = `error`, `status_code` NULL and `fetch_error` = `timeout`. `timeout` is a value of `urls.fetch_error` that `020-add-crawl-core` lists.

A timeout is a request without an HTTP response, so it counts towards the network pause of `020-add-crawl-core`. When every attempt at an origin's robots.txt times out, the origin's URLs SHALL be recorded with `fetch_error` = `timeout` without a request, as `020-add-crawl-core` records the URLs behind a robots.txt that got no HTTP response; a robots.txt that answers 5xx or 429 after the retries stays `robots_unreachable`.

#### Scenario: A hanging response times out
- **WHEN** `/` links to `/hang`, which never answers, and `spider crawl {site}/ --timeout 1 --retries 0` runs
- **THEN** `{site}/hang` has `fetch_state` = `error` and `fetch_error` = `timeout`

### Requirement: Retries with backoff
The Crawl SHALL retry a request attempt, robots.txt included, that gets no response, a 5xx status or a 429 status, up to `--retries` times (default 2, setting `crawl.retries`).
- **Backoff:** before retry n (counting from 1), the Crawl SHALL wait 2^(n-1) seconds.
- **Retry-After:** a `Retry-After` header on a 429 or 503 response SHALL set the wait instead, capped at 120 seconds.
- **429 without Retry-After:** the wait SHALL be 10 seconds.
- **Host pause:** during a wait caused by a 429 status or a `Retry-After` header, no request to that host SHALL start.
- **Other 4xx statuses** SHALL NOT be retried.
- **Network pause:** while the Crawl is paused waiting for the network (`020-add-crawl-core`), a request attempt that fails SHALL be neither retried nor recorded; its URL stays `queued` and is requested after the pause.

The URL SHALL record the last attempt's response. This change adds this column to `urls`, under the conventions of `018-add-schema-conventions`:

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `attempt_count` | INTEGER | no | | The number of requests made for the URL; 0 when it was not requested |

#### Scenario: A temporary 503 is retried
- **WHEN** `/flaky` returns 503 once and 200 after that
- **THEN** `{site}/flaky` has `status_code` = 200 and `attempt_count` = 2

#### Scenario: A persistent 500 is recorded after the retries
- **WHEN** `/down` always returns 500 and the default `--retries` applies
- **THEN** `{site}/down` has `status_code` = 500 and `attempt_count` = 3

#### Scenario: Retries wait one and then two seconds
- **WHEN** a fake Fetcher always returns 500 for `http://site.test/down`, with a fake clock
- **THEN** the three attempts start at 0, 1 and 3 seconds

#### Scenario: Retry-After pauses the host
- **WHEN** a fake Fetcher returns 429 with `Retry-After: 7` for `http://site.test/a` at 0 seconds, with a fake clock
- **THEN** the next request to `site.test` starts at 7 seconds

#### Scenario: A 404 is not retried
- **WHEN** `/` links to `/missing`, which returns 404
- **THEN** `{site}/missing` has `attempt_count` = 1

### Requirement: Redirects are followed hop by hop
The Crawl SHALL NOT follow redirects within one request. For a 3xx response with a `Location` header:
- **On the redirecting URL** it SHALL record the status code, the raw header in `redirect_location`, and the target in `redirect_url_id`.
- **The target** is resolved against the redirecting URL and normalised. It SHALL be recorded as a URL with `discovered_via` = `redirect`, `found_on_url_id` pointing to the redirecting URL, and the same Crawl Depth.
- **Requests:** each target SHALL be requested on its own, subject to the Scope, robots.txt and `--exclude`. The target of a URL that is only checked SHALL also be checked.

A 3xx response without a usable `Location` SHALL have `redirect_url_id` NULL.

`redirect` is a value of `urls.discovered_via` that `020-add-crawl-core` lists. This change adds these columns to `urls`, under the conventions of `018-add-schema-conventions`:

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `redirect_location` | TEXT | yes | | The raw `Location` header of a 3xx response |
| `redirect_url_id` | INTEGER, references `urls.id` | yes | | The redirect's target, resolved against the URL and normalised; NULL without a usable `Location` |

It also adds this index to `urls`, built while the Crawl writes:

| Index | Columns | Unique | Where | Query it serves |
|---|---|---|---|---|
| `urls_redirect_url_id` | `redirect_url_id` | no | `redirect_url_id IS NOT NULL` | Finding the URLs that redirect to a URL: the reverse walk of a Redirect Chain |

#### Scenario: Every hop of a Redirect Chain is recorded
- **WHEN** `/` links to `/a`, `/a` returns 301 to `/b`, `/b` returns 302 to `/c`, and `/c` returns 200
- **THEN** `{site}/a` has `status_code` = 301 with `redirect_url_id` pointing to `{site}/b`
- **AND** `{site}/b` has `status_code` = 302 with `redirect_url_id` pointing to `{site}/c`

#### Scenario: A relative Location is resolved
- **WHEN** `/` links to `/dir/r`, which returns 301 with `Location: ../x`
- **THEN** `{site}/dir/r` has `redirect_location` = `../x` and a `redirect_url_id` pointing to `{site}/x`

#### Scenario: A redirect without Location has no target
- **WHEN** `/` links to `/nolocation`, which returns 302 without a `Location` header
- **THEN** `{site}/nolocation` has `status_code` = 302 and `redirect_url_id` NULL

#### Scenario: A redirect target keeps the depth
- **WHEN** `/` links to `/moved`, which returns 301 to `/new`
- **THEN** `{site}/new` has `crawl_depth` = 1 and `discovered_via` = `redirect`

#### Scenario: A redirect to an excluded URL is not followed
- **WHEN** `/` links to `/go`, `/go` returns 302 to `/logout`, and `spider crawl {site}/ --exclude "/logout"` runs
- **THEN** `{site}/logout` has `skip_reason` = `excluded`

#### Scenario: A redirect to an External URL is checked
- **WHEN** `http://site.test/` links to `http://site.test/out`, which returns 301 to `http://other.test/landing`
- **THEN** `http://other.test/landing` has `fetch_state` = `fetched` and `parsed` = 0

#### Scenario: Index of redirect targets
- **WHEN** `spider schema urls --fields indexes` runs
- **THEN** the item's `indexes`, reduced to `name`, `columns`, `unique` and `where`, include `{"name":"urls_redirect_url_id","columns":["redirect_url_id"],"unique":false,"where":"redirect_url_id IS NOT NULL"}`

### Requirement: A Seed that redirects within its site extends the Scope
When a Seed's Redirect Chain ends on a host with the same registrable domain as the Seed host, that host SHALL be treated as a Seed host for the rest of the Crawl, and SHALL be listed in `crawl.scope`. When the chain ends on another registrable domain, the Scope SHALL NOT change, and the Crawl SHALL record a `seed_redirected_off_site` warning whose hint contains the final URL of the chain.

#### Scenario: A redirect to the www host stays inside the Scope
- **WHEN** `http://site.test/` redirects with 301 to `http://www.site.test/`, which links to `/a`, and `spider crawl http://site.test/` runs
- **THEN** `http://www.site.test/a` has `fetch_state` = `fetched` and `is_internal` = 1

#### Scenario: A redirect to another site is reported
- **WHEN** `http://site.test/` redirects with 301 to `http://other.test/`, and `spider crawl http://site.test/` runs
- **THEN** the result's `warnings` hold an entry with code `seed_redirected_off_site` whose `hint` contains `http://other.test/`

### Requirement: Redirect hop limit
The Crawl SHALL NOT follow a redirect that would be more than `--max-redirects` (default 10, setting `crawl.max_redirects`) consecutive redirects from the first URL of its chain. The target of such a redirect SHALL be recorded with `fetch_state` = `skipped` and `skip_reason` = `max_redirects`, a value that `020-add-crawl-core` lists.

#### Scenario: The eleventh redirect is not followed
- **WHEN** `/` links to `/r1`, and each of `/r1` to `/r11` returns 301 to the next one (`/r1` to `/r2`, and so on up to `/r11` to `/r12`)
- **THEN** `{site}/r11` has `fetch_state` = `fetched` and `{site}/r12` has `skip_reason` = `max_redirects`

### Requirement: Redirect loops
The Crawl SHALL request each URL at most once in a run, so every redirect loop ends. This change adds this column to `urls`:

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `in_redirect_loop` | INTEGER | yes | boolean | 1 when the URL is in a redirect loop |

Its values are:
- It is 1 for every URL in a loop.
- It is 0 for other 3xx responses.
- It is NULL for URLs without a 3xx response.

#### Scenario: A loop of two URLs is marked
- **WHEN** `/` links to `/loop-a`, `/loop-a` returns 301 to `/loop-b`, and `/loop-b` returns 301 to `/loop-a`
- **THEN** `{site}/loop-a` and `{site}/loop-b` both have `in_redirect_loop` = 1

#### Scenario: A looping URL is requested once
- **WHEN** `/` links to `/loop-a`, `/loop-a` returns 301 to `/loop-b`, and `/loop-b` returns 301 to `/loop-a`
- **THEN** the fixture site receives exactly one request for `/loop-a`

### Requirement: Meta refresh is a Link, not a redirect hop
A `<meta http-equiv="refresh">` SHALL stay a Link of type `meta_refresh` (`020-add-crawl-core`), not a redirect hop. The Page SHALL keep its own status code, and its `redirect_url_id` SHALL stay NULL. Reporting a meta refresh as the Page's redirect belongs to page data (`030-add-page-data`).

#### Scenario: A meta refresh is not recorded as a redirect
- **WHEN** `/` links to `/old`, which returns 200 with `<meta http-equiv="refresh" content="0; url=/new">`
- **THEN** `{site}/old` has `status_code` = 200 and `redirect_url_id` NULL

### Requirement: Response size limit
The Crawl SHALL read at most 20,971,520 bytes (20 MiB) of a response body. This change adds this column to `urls`:

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `body_truncated` | INTEGER | yes | boolean | 1 when the body was larger and not read in full |

A URL with a larger body SHALL have `body_truncated` = 1 and `parsed` = 0. If it would otherwise have been parsed, it SHALL have `parse_error` = `body_too_large`, a value that `020-add-crawl-core` lists.

#### Scenario: A huge page is not parsed
- **WHEN** `/` links to `/huge.html`, a 26,214,400-byte (25 MiB) HTML page
- **THEN** `{site}/huge.html` has `body_truncated` = 1, `parsed` = 0 and `parse_error` = `body_too_large`

### Requirement: URL length limit
URLs longer than 2,000 characters SHALL NOT be requested, and SHALL be recorded with `fetch_state` = `skipped` and `skip_reason` = `url_too_long`, a value that `020-add-crawl-core` lists.

#### Scenario: A very long URL is skipped
- **WHEN** `/` links to a URL made of `{site}/` followed by 2,001 `a` characters
- **THEN** that URL has `skip_reason` = `url_too_long`

### Requirement: Compression
Every request SHALL send `Accept-Encoding: gzip, deflate, br`, and from v0.2 `Accept-Encoding: gzip, deflate, br, zstd`. The Crawl SHALL decode those encodings itself. This change adds these columns to `urls`:

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `content_encoding` | TEXT | yes | | The `Content-Encoding` header as received |
| `size_bytes` | INTEGER | yes | | The body size after content decoding |
| `transferred_bytes` | INTEGER | yes | | The body size as transferred, before decoding |

#### Scenario: Requests accept compressed bodies
- **WHEN** `spider crawl {site}/` runs
- **THEN** the request for `/` has `Accept-Encoding` = `gzip, deflate, br`

#### Scenario: A compressed Resource records both sizes
- **WHEN** `/app.js` returns a 10,000-byte script as a 2,500-byte gzip body with `Content-Encoding: gzip`, and `/` holds `<script src="/app.js">`
- **THEN** `{site}/app.js` has `size_bytes` = 10000, `transferred_bytes` = 2500 and `content_encoding` = `gzip`

### Requirement: Resource sizes
Every requested Resource SHALL have its `status_code`, `size_bytes` and `transferred_bytes` recorded, and SHALL NOT be parsed.

#### Scenario: An image's size is recorded
- **WHEN** `/` holds `<img src="/logo.png">`, and `/logo.png` returns 200 with a 2,048-byte `image/png` body
- **THEN** `{site}/logo.png` has `status_code` = 200, `size_bytes` = 2048 and `transferred_bytes` = 2048

### Requirement: TLS certificate verification
HTTPS requests SHALL verify the server certificate and its host name against the operating system's trust store. When that store cannot be used, certifi's bundle SHALL be the fallback. A request whose certificate does not verify SHALL be recorded with `fetch_state` = `error` and `fetch_error` = `tls_error`, a value that `020-add-crawl-core` lists. When an origin's robots.txt request fails verification, the origin's URLs SHALL be recorded with `fetch_error` = `tls_error` without a request, as `020-add-crawl-core` records the URLs behind a robots.txt that got no HTTP response. A `tls_error` SHALL NOT count towards the network pause of `020-add-crawl-core`: a certificate that fails verification is an answer from the server, and a site-wide certificate failure would otherwise wait out `--network-wait` and fail as `site_unreachable`.

#### Scenario: A certificate for another name is a TLS error
- **WHEN** `http://site.test/` links to `https://badcert.test/`, whose certificate is issued for `other.test`
- **THEN** `https://badcert.test/` has `fetch_error` = `tls_error`

#### Scenario: A certificate from an unknown CA is a TLS error
- **WHEN** `http://site.test/` links to `https://other.test:{untrusted_port}/`, whose certificate comes from a CA that is not trusted
- **THEN** that URL has `fetch_error` = `tls_error`

### Requirement: HTTP version per origin
This change adds this column to `origins` in v0.1. Its description SHALL start with `Filled from v0.2. `, and it SHALL be NULL in every row until then.

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `http_version` | TEXT | yes | `http_2`, `http_1_1` | Filled from v0.2. The HTTP version that the origin's requests use |

From v0.2, for every https origin it requests, the Crawl SHALL make one TLS handshake that offers the ALPN protocols `h2` and `http/1.1`. It SHALL record `origins.http_version` as `http_2` when `h2` is selected, and `http_1_1` otherwise. For http origins it SHALL record `http_1_1`. When the handshake fails, `http_version` SHALL be NULL and the Crawl SHALL go on.

#### Scenario: The HTTP version is a later column
- **WHEN** `spider schema origins` runs
- **THEN** the column `http_version` has `nullable` `true`, `values` `["http_2","http_1_1"]`, and a `description` that starts with `Filled from v0.2. `

#### Scenario: An origin that selects HTTP/2
- **WHEN** `https://site.test` is served by a TLS listener that selects `h2`, and `spider crawl https://site.test/` runs
- **THEN** the `origins` row for `https://site.test` has `http_version` = `http_2`

#### Scenario: An origin that offers only HTTP/1.1
- **WHEN** `https://site.test` is served by a TLS listener that offers only `http/1.1`, and `spider crawl https://site.test/` runs
- **THEN** the `origins` row for `https://site.test` has `http_version` = `http_1_1`

#### Scenario: A plain http origin
- **WHEN** `spider crawl {site}/` runs
- **THEN** the `origins` row for `{site}` has `http_version` = `http_1_1`

### Requirement: The response_headers table
The crawl store SHALL keep the response headers of each requested URL's last attempt in a table `response_headers`, under the conventions of `018-add-schema-conventions`, with one row for each URL that received a response, and two columns:

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `url_id` | INTEGER, primary key, references `urls.id` | no | | The URL whose response the headers are |
| `headers` | TEXT | no | json | A JSON array of `[name, value]` pairs in the order and letter case they were received |

The table SHALL have no secondary index: its rows are read by `url_id`, its primary key. A query that filters by a header reads `headers` with `json_each`.

Cookie values SHALL never be stored. They SHALL be redacted in this exact format:
- **`Set-Cookie`:** the cookie value, meaning the text after the first `=` and before the first `;`, SHALL be replaced by `***`. So `sid=abc123; Path=/; HttpOnly` is stored as `sid=***; Path=/; HttpOnly`. A value with no `=` before its first `;` SHALL be stored as `***` followed by its attributes.
- **`Cookie`:** the value of each `name=value` pair, separated by `;`, SHALL be replaced by `***`. So `a=1; b=2` is stored as `a=***; b=***`.

Header names, cookie names, attributes, and the order of the headers SHALL be kept.

#### Scenario: Columns of response_headers
- **WHEN** `spider schema response_headers` runs
- **THEN** the item's columns, reduced to `name`, `type`, `nullable`, `primary_key` and `references`, are `[{"name":"url_id","type":"INTEGER","nullable":false,"primary_key":true,"references":"urls.id"},{"name":"headers","type":"TEXT","nullable":false,"primary_key":false,"references":null}]`, and its `indexes` are `[]`

#### Scenario: Response headers are stored as received
- **WHEN** `/` returns the header `X-Robots-Tag: noindex`, and `spider crawl {site}/` runs
- **THEN** the `headers` of `{site}/` in `response_headers` contain the pair `["X-Robots-Tag", "noindex"]`

#### Scenario: A cookie value is not stored
- **WHEN** `/` returns the header `Set-Cookie: sid=abc123; Path=/; HttpOnly`, and `spider crawl {site}/` ends
- **THEN** the `headers` of `{site}/` contain the pair `["Set-Cookie", "sid=***; Path=/; HttpOnly"]`, and the bytes of the Crawl's files do not contain `abc123`

#### Scenario: A Cookie header is redacted pair by pair
- **WHEN** the response header `Cookie: a=1; b=2` is prepared for storage
- **THEN** it is stored as the pair `["Cookie", "a=***; b=***"]`
