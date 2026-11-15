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
- `site.test`, `www.site.test`, `en.site.test`, `other.test` and `badcert.test` are virtual hosts of the fixture site, over http and https. The DNS resolver hook maps them to the fixture site, and every other name fails to resolve.
- The fixture's test CA is added to the crawler's trust anchors through the TLS setup.

## ADDED Requirements

### Requirement: User agent
Every request, including robots.txt, SHALL carry the `User-Agent` header `OpenLinx/<version> (+https://github.com/openlinx/openlinx/blob/main/docs/crawler.md)` by default, where `<version>` is the tool's version and the URL is the page that tells a site owner what the crawler does and how to limit or block it. `--user-agent <string>` (setting `crawl.user_agent`) SHALL supply its global replacement. From v0.2, an Internal request's custom `User-Agent` SHALL participate in the source precedence below. A value that is empty or only spaces, or holds a character other than visible ASCII, space and tab (RFC 9110's VCHAR, SP and HTAB), SHALL be rejected with exit code 2 and error code `invalid_value` when given by a flag or service input, or `settings_invalid` (exit 3) when given in Workspace settings. The same value validation SHALL apply to a custom `User-Agent`.

#### Scenario: The default user agent identifies the tool
- **WHEN** `linx crawl {site}/` runs
- **THEN** every request the fixture site receives has a `User-Agent` that matches `^OpenLinx/\d+\.\d+\.\d+\S* \(\+https://github\.com/openlinx/openlinx/blob/main/docs/crawler\.md\)$`

#### Scenario: A custom user agent is used on every request
- **WHEN** `linx crawl {site}/ --user-agent "AuditBot/1.0"` runs
- **THEN** every request the fixture site receives, including the one for `/robots.txt`, has `User-Agent` = `AuditBot/1.0`

#### Scenario: An invalid user agent is rejected
- **WHEN** `linx crawl {site}/ --user-agent ""` runs
- **THEN** it exits with code 2 and error code `invalid_value`, and no request is made

### Requirement: Custom headers
**In short:** custom headers reach each Internal request, while stored metadata hides sensitive values and keeps harmless entries.

**(v0.2)** `--header "Name: Value"` SHALL add a request header. It SHALL be accepted more than once, and its setting `crawl.header` SHALL be a list of `Name: Value` strings. A value without `:` SHALL be rejected with exit code 2 and error code `invalid_value`. Custom headers SHALL be sent only with requests for Internal URLs and their robots.txt, never with requests for External URLs.

Header input SHALL split at the first `:`; `Name:Value` and `Name: Value` SHALL both be accepted. Names SHALL be nonempty HTTP tokens, compared without case. Values SHALL reject CR, LF and other characters outside visible ASCII, space and tab before dispatch. Invalid flag/service values SHALL raise `invalid_value` (exit 2); invalid Workspace values SHALL raise `settings_invalid` (exit 3). The effective custom list SHALL contain at most one `User-Agent` entry, even when entries have equal values or a dedicated input would override them; duplicates SHALL be rejected before network access with the same source-specific error. Other accepted repeated custom entries SHALL retain their order and repetitions; no generic comma-joining or last-entry-wins rule SHALL be applied. Repeated `Accept-Encoding` lines have list semantics as specified under Compression. There SHALL be no managed-header denylist that rejects `User-Agent` or `Accept-Encoding` merely by name.

#### Scenario: A custom header is sent to Internal URLs
- **WHEN** `linx crawl {site}/ --header "X-Env: staging"` runs
- **THEN** the request for `/` has the header `X-Env` = `staging`

#### Scenario: A custom header never goes to External URLs
- **WHEN** `http://site.test/` links to `http://other.test/page`, and `linx crawl http://site.test/ --header "X-Env: staging"` runs
- **THEN** the request for `http://other.test/page` has no `X-Env` header

#### Scenario: A malformed header is rejected
- **WHEN** `linx crawl {site}/ --header "NoColon"` runs
- **THEN** the Command exits with code 2 and its only stderr error has `code` = `invalid_value`

### Requirement: Request header precedence
**In short:** explicit source priority chooses one User-Agent per request without widening custom headers beyond Internal URLs.

**(v0.2)** Every attempt and redirect hop SHALL resolve its final headers from applicable inputs before transport dispatch. An explicitly supplied input SHALL take priority over an implicit/generated default. Among explicit inputs, CLI inputs (or the service's explicit flag-equivalent inputs) SHALL take priority over Workspace inputs; within the same source level, a dedicated input SHALL take priority over a generic header for the same field. An absent CLI option or its parser default SHALL NOT override an explicit Workspace input. Explicitness SHALL follow input presence, not inequality with the default value. These precedence rules SHALL NOT bypass the separately specified auth/Authorization conflict rejection or widen an input's request scope. A CLI `--header` list SHALL replace the entire Workspace `crawl.header` list, not merge individual names into it. Repeated entries in the selected list SHALL preserve their order.

For `User-Agent`, both the selected custom entry and the dedicated `user_agent` input SHALL contribute candidates with their original source priority. At the same source level an explicitly supplied, non-null dedicated `user_agent` SHALL win. An absent/null dedicated setting or its generated default SHALL NOT have that tie-breaking priority. A lower-priority candidate SHALL NOT survive as an additional User-Agent field. The dedicated input applies globally; the custom candidate applies only to Internal URLs. CLI argument order SHALL NOT affect the winner. An explicit dedicated value equal to the generated default is still explicit. Transport defaults SHALL NOT change these outcomes.

#### Scenario: User-Agent sources and scopes have literal outcomes
- **GIVEN** tool version `0.1.0.dev0`, whose default is `OpenLinx/0.1.0.dev0 (+https://github.com/openlinx/openlinx/blob/main/docs/crawler.md)`, denoted `D` below, and `http://site.test/` links to `http://other.test/page`
- **WHEN** a separate Crawl runs for each row with the listed `[crawl]` entries and CLI suffix
- **THEN** every Internal request, including robots.txt, has the Internal value, every External request has the External value, and each has exactly one User-Agent field

| Workspace entries | CLI suffix | Internal | External |
|---|---|---|---|
| none | none | `D` | `D` |
| none | `--header "User-Agent: Header/1"` | `Header/1` | `D` |
| `header = ["User-Agent: FileHeader/1"]` | none | `FileHeader/1` | `D` |
| `user_agent = "File/1"` | none | `File/1` | `File/1` |
| none | `--user-agent Cli/1` | `Cli/1` | `Cli/1` |
| `user_agent = "File/1"; header = ["User-Agent: FileHeader/1"]` | none | `File/1` | `File/1` |
| `user_agent = "File/1"` | `--header "uSeR-aGeNt: Header/1"` | `Header/1` | `File/1` |
| `header = ["User-Agent: FileHeader/1"]` | `--user-agent Cli/1` | `Cli/1` | `Cli/1` |
| none | `--user-agent Cli/1 --header "User-Agent: Header/1"` | `Cli/1` | `Cli/1` |
| none | `--header "User-Agent: Header/1" --user-agent Cli/1` | `Cli/1` | `Cli/1` |
| `user_agent = "File/1"; header = ["User-Agent: FileHeader/1"]` | `--header "User-Agent: Header/1"` | `Header/1` | `File/1` |
| none | `--header "User-Agent: Header/1" --user-agent "OpenLinx/0.1.0.dev0 (+https://github.com/openlinx/openlinx/blob/main/docs/crawler.md)"` | `D` | `D` |

Semicolons in the Workspace column separate TOML lines, not literal TOML syntax. `D` is the full literal above, not an implementation-derived expectation; another tested tool version substitutes its independently specified version literal.

#### Scenario: CLI headers replace the Workspace list
- **GIVEN** `[crawl] header = ["User-Agent: FileHeader/1", "X-Env: file"]`
- **WHEN** a Crawl uses `--header "X-Env: cli" --header "x-env: audit"`
- **THEN** Internal requests contain both X-Env values in order `cli`, `audit`, no `file` value, and the default User-Agent; External requests have no X-Env

#### Scenario: Duplicate custom User-Agent fields are refused
- **WHEN** a Crawl uses `--header "User-Agent: One/1" --header "user-agent: Two/1" --user-agent Dedicated/1`, or the two custom values are both `One/1`
- **THEN** it exits with code 2 and `invalid_value` before any request

#### Scenario: Duplicate Workspace User-Agent fields are refused
- **WHEN** `[crawl] header` is `["User-Agent: One/1", "USER-AGENT: Two/1"]` and no CLI header list replaces it
- **THEN** the Crawl exits with code 3 and `settings_invalid` before any request

### Requirement: Custom header recording and per-hop identity
**In short:** recording retains the selected custom inputs while each hop applies its own Internal decision.

`--header` and `crawl.header` SHALL be declared a header secret while their public secret indicator remains boolean `true`. Recorded config and argv SHALL keep header names, repetitions, harmless values and order, replacing only sensitive values with `***`: `Cookie` and every name containing `auth`, `token`, `secret`, `key` or `password`, matched without case. Both split and `--header=value` argv forms SHALL be redacted. Diagnostics and stored failure messages SHALL NOT reveal sensitive header values.

A custom User-Agent overridden by the dedicated input SHALL remain in the recorded header list as supplied; precedence SHALL NOT delete or rewrite harmless input. Recording the selected inputs SHALL NOT be treated as sufficient evidence of their original source priority on continue.

Every new Crawl SHALL record the object `request_policy` at the root of `crawl.config`, with boolean `custom_user_agent`: `true` when the selected generic User-Agent wins on Internal requests, otherwise `false`. It SHALL NOT alter `crawl.user_agent` or the selected `crawl.header` list. This is service-owned recorded metadata, not a public setting. A continued Crawl SHALL retain it on every subsequent recording.

Internal identity SHALL be decided for each attempt and each redirect hop, including robots.txt redirects, retries and outage probes. A checked Internal URL outside a Seed folder SHALL still receive it. No origin identity header SHALL be copied into a proxy CONNECT request.

A Seed Redirect Chain Page and the robots requests made to check that Page SHALL use the same current provisional or final Scope context. Each robots redirect target SHALL be classified anew in that context, without inheriting a source boolean. Requests after the Seed chain settles SHALL use final Scope only.

#### Scenario: Provisional Seed identity agrees between a Page and its robots
- **GIVEN** the Seed `http://www.site.test/` redirects to `http://site.test/`, whose `/robots.txt` redirects to `http://other.test/robots.txt`, and the Crawl uses `--header "X-Env: staging"`
- **WHEN** the apex Page is dispatched using the Seed chain's provisional Internal decision, before its response settles Scope
- **THEN** both `http://site.test/robots.txt` and `http://site.test/` receive `X-Env: staging`, but `http://other.test/robots.txt` receives no X-Env; later ordinary requests use the settled Scope

#### Scenario: A cookie header keeps its name and hides its value
- **WHEN** `linx crawl {site}/ --header "Cookie: session=abc123"` ends
- **THEN** the `crawl` table of `crawl.config` has `"header": ["Cookie: ***"]`

#### Scenario: Harmless headers survive recording beside secrets
- **WHEN** a Crawl runs with `--header "X-Env: staging" --header "x-ToKeN: abc123" --header "X-Env: audit"`
- **THEN** `crawl.config` contains `"header": ["X-Env: staging", "x-ToKeN: ***", "X-Env: audit"]`

#### Scenario: Joined header arguments hide only sensitive values
- **WHEN** a Crawl runs with `--header=X-Env: staging` and `--header=Cookie: sid=abc123` as two argv entries
- **THEN** the recorded entries are `"--header=X-Env: staging"` and `"--header=Cookie: ***"`

#### Scenario: Internal robots requests carry custom headers
- **WHEN** `linx crawl http://site.test/ --header "X-Env: staging"` runs
- **THEN** the request for `http://site.test/robots.txt` has `X-Env` = `staging`

#### Scenario: A robots redirect drops Internal headers at an External hop
- **WHEN** `http://site.test/robots.txt` redirects to `http://other.test/robots.txt`, and the Crawl uses `--header "X-Env: staging"`
- **THEN** the request for `http://other.test/robots.txt` has no `X-Env` header

#### Scenario: A checked Internal URL still gets custom headers
- **WHEN** `http://site.test/docs/` links to `http://site.test/outside`, and `linx crawl http://site.test/docs/ --header "X-Env: staging"` runs
- **THEN** the checked request for `http://site.test/outside` has `X-Env` = `staging`

#### Scenario: An External URL redirect never inherits custom headers
- **WHEN** `http://site.test/` redirects to `http://other.test/page`, and the Crawl uses `--header "X-Env: staging"`
- **THEN** the request for `http://other.test/page` has no `X-Env` header

#### Scenario: Sensitive header values are absent from failure diagnostics
- **WHEN** a Crawl uses `--header "X-Token: abc123"` and a boundary failure message quotes `abc123`
- **THEN** emitted diagnostics and stored failure messages contain `***` and do not contain `abc123`

### Requirement: HTTP basic authentication
**In short:** basic auth is Internal-only and conflicting custom Authorization is rejected before network access.

**(v0.2)** `--auth <user:password>` (setting `crawl.auth`, marked secret) SHALL send HTTP basic authentication preemptively with every request for an Internal URL and its robots.txt, never with requests for External URLs. The setting SHALL also be accepted from `openlinx.toml`. Recorded config and argv hide it as `***`, in both split and joined argv forms; diagnostics SHALL also hide credentials. Nonempty resolved `crawl.auth` together with a custom `Authorization` header, matched without case, SHALL be rejected with error code `invalid_value` and exit code 2 before any network access, regardless of whether either value came from flags or Workspace settings.

#### Scenario: Credentials are sent to Internal URLs
- **WHEN** `linx crawl http://site.test/ --auth "alice:s3cret"` runs
- **THEN** the request for `http://site.test/` has `Authorization` = `Basic YWxpY2U6czNjcmV0`

#### Scenario: Credentials never go to External URLs
- **WHEN** `http://site.test/` links to `http://other.test/page`, and `linx crawl http://site.test/ --auth "alice:s3cret"` runs
- **THEN** the request for `http://other.test/page` has no `Authorization` header

#### Scenario: The recorded command hides the password
- **WHEN** `linx crawl {site}/ --auth "alice:s3cret"` ends
- **THEN** `crawl.command_argv` is `["linx", "crawl", "{site}/", "--auth", "***"]`

#### Scenario: Credentials in openlinx.toml are used
- **WHEN** `openlinx.toml` holds `[crawl]` with `auth = "alice:s3cret"`, and `linx crawl http://site.test/` runs
- **THEN** the request for `http://site.test/` has `Authorization` = `Basic YWxpY2U6czNjcmV0`

#### Scenario: Internal robots requests carry credentials
- **WHEN** `linx crawl http://site.test/ --auth "alice:s3cret"` runs
- **THEN** `http://site.test/robots.txt` receives `Authorization` = `Basic YWxpY2U6czNjcmV0`

#### Scenario: A robots redirect drops credentials at an External hop
- **WHEN** `http://site.test/robots.txt` redirects to `http://other.test/robots.txt`, and the Crawl uses `--auth "alice:s3cret"`
- **THEN** the request for `http://other.test/robots.txt` has no `Authorization` header

#### Scenario: Conflicting authentication is refused before network
- **WHEN** a Crawl uses `--auth "alice:s3cret" --header "aUtHoRiZaTiOn: Bearer abc123"`
- **THEN** it exits with code 2 and `invalid_value`, and the fixture request log is empty

#### Scenario: Authentication conflicts across settings sources
- **WHEN** `[crawl] auth` is `alice:s3cret` and a Crawl uses `--header "Authorization: Bearer abc123"`
- **THEN** it exits with code 2 and `invalid_value`, and the fixture request log is empty

#### Scenario: Auth diagnostics hide plaintext and encoded credentials
- **WHEN** a Crawl uses `--auth "alice:s3cret"` and a transport error quotes `alice:s3cret`, `s3cret`, `YWxpY2U6czNjcmV0` and `Basic YWxpY2U6czNjcmV0`
- **THEN** neither emitted diagnostics nor stored failure messages contain any of those four values

### Requirement: Fresh secrets on continue
**In short:** continuing a Crawl requires fresh credentials and preserves its recorded harmless configuration.

A continue SHALL NOT send recorded redaction markers as credentials. Required auth, sensitive header values and explicit proxy credentials SHALL be supplied afresh by the caller, or the continue SHALL refuse with `secrets_required` (exit 2) and a hint naming the required flag or Workspace setting, before opening a writer or network connection. Harmless stored header entries, their order, and all unrelated recorded non-secret settings SHALL remain unchanged. Fresh headers SHALL replace the matching sensitive name and occurrence. Resolved auth/header conflicts SHALL use the same validation as a new Crawl. Current process proxy variables SHALL be read again and SHALL NOT cause `secrets_required`.

This contract applies to the existing continue service; the resume Command's flag/provenance and Workspace reread adapter is specified by crawl control.

A continue SHALL preserve the selected Internal and External header policy and explicit literal values, including the cross-source User-Agent winner and the distinction between explicit and default dedicated inputs. A null dedicated User-Agent SHALL still generate the running tool's default; its expanded bytes need not remain identical across tool versions. The default Accept-Encoding likewise follows supported decoder capabilities, while an explicit custom value remains literal. Fresh secrets SHALL NOT acquire a higher priority for unrelated harmless headers. Current Workspace values and resumed argument order SHALL NOT recompute the original harmless precedence. The stored custom list SHALL retain overridden harmless entries, case, order and repetitions; preserving the winner SHALL NOT be implemented by deleting those entries.

At continue service entry, including direct callers, recorded `request_policy` SHALL be validated before opening any writer or network connection. It SHALL be an object with an actual JSON boolean `custom_user_agent`; missing metadata, a non-object, or a missing/non-boolean member SHALL produce `crawl_file_invalid` (exit 6) with `details.file`. A true value SHALL require exactly one valid custom User-Agent entry. No inference from argv, current Workspace inputs or unsupported pre-release files SHALL replace missing metadata.

#### Scenario: The initial Crawl records the selected User-Agent winner
- **WHEN** a Crawl starts with Workspace `user_agent = "File/1"` and CLI `--header "User-Agent: Header/1"`
- **THEN** `crawl.config.request_policy` is `{"custom_user_agent": true}`, `crawl.config.crawl.user_agent` is `File/1`, and `crawl.config.crawl.header` is `["User-Agent: Header/1"]`
- **AND** an otherwise identical Crawl using CLI `--user-agent File/1` records `{"custom_user_agent": false}` while retaining the same settings values; a Crawl with neither input also records `{"custom_user_agent": false}`

#### Scenario: A direct continue refuses invalid request policy metadata
- **WHEN** the continue service directly receives a Crawl whose request_policy is missing, null, `[]`, or `"false"`, or whose custom_user_agent member is missing, `0`, `1`, `"false"` or null
- **THEN** it raises `crawl_file_invalid` with exit 6 and `details.file` before any writer or network connection opens
- **AND** `{"custom_user_agent": true}` with no custom User-Agent or multiple custom User-Agent entries is refused the same way

#### Scenario: Repeated continues preserve the non-secret header winner
- **GIVEN** a stopped Crawl with `user_agent = "File/1"`, `header = ["User-Agent: Header/1"]` and `request_policy = {"custom_user_agent": true}`
- **WHEN** the service continues it, it stops again, and the service continues it a second time
- **THEN** each run uses Internal `User-Agent: Header/1` and External `User-Agent: File/1`, and each recorded request_policy remains `{"custom_user_agent": true}`

#### Scenario: Continue preserves a CLI header over a Workspace dedicated User-Agent
- **GIVEN** a stopped Crawl started with Workspace `user_agent = "File/1"` and CLI `--header "User-Agent: Header/1" --header "X-Env: staging" --header "X-Token: old123" --header "X-Env: audit"`
- **WHEN** the continue service receives fresh `X-Token: new123`, while current Workspace `user_agent` is `Changed/1`
- **THEN** Internal requests use `User-Agent: Header/1`, External requests use `User-Agent: File/1`, both Internal X-Env values remain `staging`, `audit` in order, and stored headers are `["User-Agent: Header/1", "X-Env: staging", "X-Token: ***", "X-Env: audit"]`

#### Scenario: Continue preserves a dedicated winner with the same resolved values
- **GIVEN** a stopped Crawl started with CLI `--user-agent File/1 --header "User-Agent: Header/1" --header "X-Env: staging" --header "X-Token: old123" --header "X-Env: audit"`, producing the same resolved `crawl.user_agent` and `crawl.header` values as the preceding scenario
- **WHEN** the continue service receives fresh `X-Token: new123`
- **THEN** both Internal and External requests use `User-Agent: File/1`, while the stored header list remains `["User-Agent: Header/1", "X-Env: staging", "X-Token: ***", "X-Env: audit"]`

#### Scenario: Service inputs retain their winner without CLI argv evidence
- **GIVEN** a stopped Crawl was planned by a service with explicit flag-equivalent `header = ["User-Agent: Header/1"]`, Workspace `user_agent = "File/1"`, and diagnostic `command_argv = ["service-crawl"]`
- **WHEN** the continue service runs it without harmless overrides
- **THEN** Internal requests use `User-Agent: Header/1` and External requests use `User-Agent: File/1`; the diagnostic argv does not change the winner

#### Scenario: Continue preserves an Internal Accept-Encoding override
- **GIVEN** a stopped v0.2 Crawl recorded `header = ["Accept-Encoding: identity", "X-Token: ***"]`
- **WHEN** the continue service receives fresh `X-Token: new123`
- **THEN** Internal requests send `Accept-Encoding: identity` and External requests send `Accept-Encoding: gzip, deflate, br, zstd`

#### Scenario: Continue refuses a recorded password without a fresh value
- **WHEN** the continue service receives a stopped Crawl whose recorded `auth` is `***`, without fresh auth
- **THEN** it raises `secrets_required` with exit code 2 and a hint naming `--auth`, before any request or writer opens

#### Scenario: Fresh credentials preserve stored harmless settings
- **WHEN** a stopped Crawl recorded `timeout` = 7 and `header` = `["X-Env: staging", "X-Token: ***", "X-Env: audit"]`, and the continue service receives fresh `X-Token: new123` while the current Workspace has `timeout` = 99
- **THEN** requests use `X-Token` = `new123`, both stored `X-Env` entries in order and timeout 7, and none uses `***`

#### Scenario: Continue refuses a missing sensitive header value
- **WHEN** a stopped Crawl recorded `header` = `["X-Env: staging", "Cookie: ***"]` and no fresh Cookie value is supplied
- **THEN** the continue service raises `secrets_required` with exit code 2 and a hint naming `--header`, before any request or writer opens

### Requirement: Proxy
**In short:** an explicit HTTP proxy overrides the environment and keeps proxy credentials out of origin requests and recorded secrets.

**(v0.2)** `--proxy <url>` (setting `crawl.proxy`) SHALL send every request, robots.txt included, through the given HTTP proxy, with credentials when the URL contains them.

Without `--proxy` or `[crawl] proxy`, the Crawl SHALL honour the standard proxy variables, as curl, pip and uv do:
- **Which variable:** `HTTP_PROXY` for http URLs and `HTTPS_PROXY` for https URLs.
- **Bypass:** `NO_PROXY`, a comma-separated list of host names and domain suffixes, or `*`, names the hosts that bypass the proxy.
- **Letter case:** each variable is read under its lower-case and its upper-case name, as curl reads them. When both are set, the lower-case one wins. An empty variable counts as unset.
- **Scheme:** a proxy given without a scheme, such as `proxy.corp:3128`, SHALL be used as the http proxy `http://proxy.corp:3128`.

The proxy variables are honoured from v0.1. This is the exception to the no-environment-variables rule of `010-add-workspace-and-cli-contract`. From v0.2, `--proxy` and `[crawl] proxy` SHALL override all proxy variables, including `NO_PROXY`, and the scenarios that pass `--proxy` apply. A resumed Crawl SHALL read the variables again.

The password in a proxy URL SHALL be marked partly secret, whether it comes from `--proxy`, Workspace settings or a variable, and `015-add-crawl-store` records it as `http://<user>:***@<host>:<port>`; a proxy URL from a variable without a password is recorded as `***`. The proxy variables in use SHALL be recorded, set ones only, in the `environment` table of `crawl.config` under the lower-case keys `http_proxy`, `https_proxy` and `no_proxy`.

#### Scenario: Requests go through the proxy
- **WHEN** a test proxy listens on `127.0.0.1:{proxy_port}`, and `linx crawl http://site.test/ --proxy http://127.0.0.1:{proxy_port}` runs
- **THEN** the test proxy receives a request for `http://site.test/`

#### Scenario: The HTTP_PROXY variable is honoured
- **WHEN** `HTTP_PROXY` is `http://127.0.0.1:{proxy_port}`, and `linx crawl http://site.test/` runs
- **THEN** the test proxy receives a request for `http://site.test/`

#### Scenario: A lower-case proxy variable is honoured
- **WHEN** `http_proxy` is `http://127.0.0.1:{proxy_port}`, and `linx crawl http://site.test/` runs
- **THEN** the test proxy receives a request for `http://site.test/`

#### Scenario: NO_PROXY bypasses the proxy
- **WHEN** `HTTP_PROXY` is `http://127.0.0.1:{proxy_port}`, `NO_PROXY` is `site.test`, and `linx crawl http://site.test/` runs
- **THEN** the test proxy receives no request, and the fixture site receives the request for `/`

#### Scenario: The proxy flag overrides the proxy variables
- **WHEN** `HTTP_PROXY` is `http://127.0.0.1:{proxy_port_a}`, and `linx crawl http://site.test/ --proxy http://127.0.0.1:{proxy_port_b}` runs
- **THEN** the test proxy on `{proxy_port_b}` receives a request for `http://site.test/`, and the one on `{proxy_port_a}` receives none

#### Scenario: An explicit proxy overrides NO_PROXY
- **WHEN** `NO_PROXY` is `*` and a Crawl uses `--proxy http://127.0.0.1:{proxy_port}` for `http://site.test/`
- **THEN** the proxy receives the request for `http://site.test/`

#### Scenario: HTTPS uses an authenticated proxy tunnel
- **WHEN** a test proxy accepts `u:pw`, and a Crawl requests `https://site.test/` with `--proxy http://u:pw@127.0.0.1:{proxy_port}`
- **THEN** the proxy receives `CONNECT site.test:443` with `Proxy-Authorization` = `Basic dTpwdw==`, while the origin receives no `Proxy-Authorization`

#### Scenario: CONNECT does not carry custom origin identity
- **WHEN** a Crawl uses an HTTPS Seed, an explicit proxy, `--auth "alice:s3cret"` and `--header "X-Env: staging"`
- **THEN** the proxy's CONNECT request has neither `Authorization` nor `X-Env`

#### Scenario: Continue refuses an explicit proxy password without a fresh value
- **WHEN** a stopped Crawl recorded `proxy` = `http://u:***@127.0.0.1:{proxy_port}` and the continue service receives no fresh proxy credentials
- **THEN** it raises `secrets_required` with exit code 2 and a hint naming `--proxy`, before any request or writer opens

#### Scenario: A proxy password is redacted
- **WHEN** `linx crawl {site}/ --proxy http://u:pw@127.0.0.1:{proxy_port}` ends
- **THEN** `crawl.command_argv` contains `http://u:***@127.0.0.1:{proxy_port}`

#### Scenario: A proxy password from a variable is redacted
- **WHEN** `HTTP_PROXY` is `http://u:pw@127.0.0.1:{proxy_port}`, and `linx crawl http://site.test/` ends
- **THEN** the `environment` table of `crawl.config` has `http_proxy` = `http://u:***@127.0.0.1:{proxy_port}`

### Requirement: No cookies are sent
The Crawl SHALL NOT send cookies that responses set. After a response with `Set-Cookie`, no later request SHALL carry a `Cookie` header unless `--header "Cookie: …"` asks for one.

#### Scenario: Cookies set by the site are not sent back
- **WHEN** `/` answers with `Set-Cookie: sid=abc123` and links to `/check`, and `linx crawl {site}/` runs
- **THEN** the request for `/check` has no `Cookie` header

### Requirement: Timeouts
A request attempt that has not completed within `--timeout` seconds (default 20, setting `crawl.timeout`) SHALL fail. When every attempt for a URL times out, the URL SHALL be recorded with `fetch_state` = `error`, `status_code` NULL and `fetch_error` = `timeout`. `timeout` is a value of `urls.fetch_error` that `020-add-crawl-core` lists.

A timeout is a request without an HTTP response, so it counts towards the network pause of `020-add-crawl-core`. When every attempt at an origin's robots.txt times out, the origin's URLs SHALL be recorded with `fetch_error` = `timeout` without a request, as `020-add-crawl-core` records the URLs behind a robots.txt that got no HTTP response; a robots.txt that answers 5xx or 429 after the retries stays `robots_unreachable`.

#### Scenario: A hanging response times out
- **WHEN** `/` links to `/hang`, which never answers, and `linx crawl {site}/ --timeout 1 --retries 0` runs
- **THEN** `{site}/hang` has `fetch_state` = `error` and `fetch_error` = `timeout`

### Requirement: Retries with backoff
The Crawl SHALL retry a request attempt, robots.txt included, that ends with the `fetch_error` `timeout`, `connection_refused` or `connection_error`, or with a 5xx status or a 429 status, up to `--retries` times (default 2, at most 10, setting `crawl.retries`). An attempt that ends with `dns_error`, `tls_error`, `invalid_response` or `watchdog` SHALL NOT be retried. A `--retries` above 10 SHALL be rejected with exit code 2 and error code `invalid_value`.
- **Backoff:** before retry n (counting from 1), the Crawl SHALL wait 2^(n-1) seconds.
- **Retry-After:** a `Retry-After` header on a 429 or 503 response SHALL set the wait instead, capped at 120 seconds.
- **429 without Retry-After:** the wait SHALL be 10 seconds.
- **Host pause:** during a wait caused by a 429 status or a `Retry-After` header, no request to that host SHALL start. A 429 or a `Retry-After` SHALL pause the host even when the URL is not retried, with `--retries 0` or on its last attempt.
- **Other 4xx statuses** SHALL NOT be retried.
- **URL limit:** a retry is the same URL, so only a URL's first attempt SHALL count towards `--max-urls`, and the URL limit SHALL NOT end the retries of a URL already requested: they go on within the stop's grace, as any request in flight does. When the URL limit refuses a URL while the network pause of `020-add-crawl-core` is on, or while Internal requests in a row without an HTTP response count towards one, the Crawl SHALL NOT stop yet: it SHALL wait while those requests end and, when a pause is on, for the pause to end, at most `--network-wait`. A URL given back meanwhile frees room under the limit, and the Crawl SHALL then request the URLs the limit refused, up to the limit; otherwise it stops.
- **Stop:** after any other stop, such as an interrupt, a retry that is due SHALL NOT start, and its URL SHALL NOT be recorded: it stays `queued`, so a continue requests it.
- **Network pause:** a URL SHALL count once towards the network pause of `020-add-crawl-core`, at its first attempt that gets no HTTP response while the Crawl is not paused; its later attempts SHALL NOT count again. While the Crawl is paused waiting for the network, a request attempt that fails SHALL NOT be retried, and a URL whose retry is due SHALL make no further attempt. A URL of the pause's count SHALL be recorded with its last failure, and the pause's end decides on it as on the rest of its count; any other such URL SHALL NOT be recorded: it stays `queued` and is requested after the pause. When the pause ends in an outage, only the URLs of its count recorded as errors SHALL be re-queued.

The URL SHALL record the last attempt's response. This change adds this column to `urls`, under the conventions of `018-add-schema-conventions`:

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `attempt_count` | INTEGER | no | | The requests made for the URL in the dispatch that recorded it, its retries included; 0 when it was not requested |

#### Scenario: A temporary 503 is retried
- **WHEN** `/flaky` returns 503 once and 200 after that
- **THEN** `{site}/flaky` has `status_code` = 200 and `attempt_count` = 2

#### Scenario: A persistent 500 is recorded after the retries
- **WHEN** `/down` always returns 500 and the default `--retries` applies
- **THEN** `{site}/down` has `status_code` = 500 and `attempt_count` = 3

#### Scenario: Retries wait one and then two seconds
- **WHEN** a fake Fetcher always returns 500 for `http://site.test/down`, with a fake clock
- **THEN** the three attempts start at 0, 1 and 3 seconds

#### Scenario: A 429 pauses the host without a retry
- **WHEN** a fake Fetcher returns 429 with `Retry-After: 7` for `http://site.test/a` at 0 seconds, with a fake clock and `--retries 0`
- **THEN** the next request to `site.test` starts at 7 seconds

#### Scenario: Retry-After pauses the host
- **WHEN** a fake Fetcher returns 429 with `Retry-After: 7` for `http://site.test/a` at 0 seconds, with a fake clock
- **THEN** the next request to `site.test` starts at 7 seconds

#### Scenario: A 404 is not retried
- **WHEN** `/` links to `/missing`, which returns 404
- **THEN** `{site}/missing` has `attempt_count` = 1

#### Scenario: An unresolvable External host is requested once
- **WHEN** `http://site.test/` links to `http://gone.test/`, a host name that does not resolve
- **THEN** `http://gone.test/` has `fetch_error` = `dns_error`, and the name `gone.test` is resolved once

#### Scenario: A retry under way outlasts the URL limit
- **WHEN** `http://site.test/` links to `/a`, `/b` and `/c`, a fake Fetcher answers `/a` with 503 once and with 200 after that, and the Crawl runs with `--max-urls 3` and a fake clock
- **THEN** `http://site.test/a` has `status_code` = 200 and `attempt_count` = 2

#### Scenario: A Crawl that reaches its URL limit during a network pause waits for the pause to end
- **WHEN** `http://site.test/` links to `/p1` to `/p30`, each `/pN` answers after 0.5 + N/100 seconds, a fake Fetcher gets no response for any request started from 1 to 30 seconds of clock time, and the Crawl runs with `--concurrency 4`, `--max-urls 19` and a fake clock
- **THEN** the `crawl_resumed` event, with `data.outcome` = `outage`, comes before the `stopping` event, whose reason is `max_urls`, and 19 URLs have `fetch_state` = `fetched`

#### Scenario: A stop cuts a pending retry and keeps its URL queued
- **WHEN** a fake Fetcher answers `http://site.test/` with 503 once and with 200 after that, and the Crawl is interrupted as that 503 arrives, with a fake clock
- **THEN** `http://site.test/` has `fetch_state` = `queued`, so a continue requests it

#### Scenario: A request that fails during a network pause is not retried
- **WHEN** `http://site.test/` links to `/p1` to `/p20`, a fake Fetcher answers `/` and gets no response for any later request, and the Crawl runs with `--concurrency 1`, `--network-wait 30` and a fake clock
- **THEN** no request for a `/pN` URL starts after the pause began; `/p1` to `/p8`, the pause's count, are `error` with `attempt_count` = 1, and every later `/pN` URL is `queued` when the Crawl ends

#### Scenario: A network that goes down pauses the Crawl before the retries
- **WHEN** `http://site.test/` links to `/p1` to `/p20`, a fake Fetcher answers `/` and refuses every later connection at once, and the Crawl runs with `--concurrency 1`, the default `--retries` and a fake clock
- **THEN** the `crawl_paused` event comes before any retry starts

### Requirement: Redirects are followed hop by hop
The Crawl SHALL NOT follow redirects within one request. For a 301, 302, 303, 307 or 308 response with a `Location` header:
- **On the redirecting URL** it SHALL record the status code, the raw header in `redirect_location`, and the target in `redirect_url_id`.
- **The target** is resolved against the redirecting URL and normalised. It SHALL be recorded as a URL with `discovered_via` = `redirect`, `found_on_url_id` pointing to the redirecting URL, and the same Crawl Depth.
- **Requests:** each target SHALL be requested on its own, subject to the Scope, robots.txt and `--exclude`. The target of a Resource's redirect SHALL also be a Resource; any other target SHALL be decided by its own Scope, whatever its source's.

A 3xx response without a usable `Location`, and a 300, 304 or 305 response, SHALL have `redirect_url_id` NULL; any 3xx response SHALL keep its raw `Location` header in `redirect_location`.

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
- **WHEN** `/` links to `/go`, `/go` returns 302 to `/logout`, and `linx crawl {site}/ --exclude "/logout"` runs
- **THEN** `{site}/logout` has `skip_reason` = `excluded`

#### Scenario: A redirect to an External URL is checked
- **WHEN** `http://site.test/` links to `http://site.test/out`, which returns 301 to `http://other.test/landing`
- **THEN** `http://other.test/landing` has `fetch_state` = `fetched` and `parsed` = 0

#### Scenario: A redirected image beyond the depth limit is checked
- **WHEN** `/` holds `<img src="/logo.png">`, `/logo.png` returns 301 to `/img/logo.png`, and `linx crawl {site}/ --max-depth 0` runs
- **THEN** `{site}/img/logo.png` has `fetch_state` = `fetched`

#### Scenario: A Page reached through an External redirect is followed
- **WHEN** `http://site.test/` links to `http://other.test/go`, which redirects with 302 to `http://site.test/promo`, which links to `/deal`, and `linx crawl http://site.test/` runs
- **THEN** `http://site.test/promo` has `parsed` = 1 and `http://site.test/deal` has `fetch_state` = `fetched`

#### Scenario: Index of redirect targets
- **WHEN** `linx schema urls --fields indexes` runs
- **THEN** the item's `indexes`, reduced to `name`, `columns`, `unique` and `where`, include `{"name":"urls_redirect_url_id","columns":["redirect_url_id"],"unique":false,"where":"redirect_url_id IS NOT NULL"}`

### Requirement: A Seed that redirects within its site extends the Scope
When a Seed's Redirect Chain ends with a response inside the Seed's section on a host with the same registrable domain as the Seed host, that host SHALL be treated as a Seed host for the rest of the Crawl, and SHALL be listed in `crawl.scope`. The `seed_base_mismatch` and `seed_blocked_by_robots_txt` checks of `020-add-crawl-core` SHALL read the URL that the Seed's Redirect Chain ends on. When the chain ends outside the Crawl's Scope, on another registrable domain or, under `--scope subfolder`, outside the Seed's folder, the Scope SHALL NOT change, and the Crawl SHALL record a `seed_redirected_out_of_scope` warning whose hint contains the final URL of the chain. A chain whose last target is never requested, skipped with `max_redirects` or refused by `--max-urls`, SHALL end on that target.

#### Scenario: A www Seed that redirects to its apex keeps the apex inside the Scope
- **WHEN** `http://www.site.test/` redirects with 301 to `http://site.test/`, which links to `/a`, and `linx crawl http://www.site.test/` runs
- **THEN** `http://site.test/a` has `fetch_state` = `fetched` and `is_internal` = 1

#### Scenario: A redirect to another subdomain stays inside the Scope
- **WHEN** `http://site.test/` redirects with 301 to `http://en.site.test/`, which links to `/a`, and `linx crawl http://site.test/` runs
- **THEN** `http://en.site.test/a` has `fetch_state` = `fetched` and `is_internal` = 1, and `crawl.scope` lists `en.site.test` among its hosts

#### Scenario: A www Seed that redirects on its host is checked on its final Page
- **WHEN** `http://www.site.test/` redirects with 301 to `http://www.site.test/home`, which holds `<link rel="canonical" href="http://site.test/">`, and `linx crawl http://www.site.test/` runs
- **THEN** the result's `warnings` hold an entry with code `seed_base_mismatch` whose `hint` contains `http://site.test/`

#### Scenario: A Seed chain that ends off its site widens nothing
- **WHEN** `http://www.site.test/` redirects with 301 to `http://site.test/old`, which redirects with 301 to `http://other.test/`, and `linx crawl http://www.site.test/` runs
- **THEN** `http://site.test/old` and `http://other.test/` have `is_internal` = 0, and `crawl.scope` does not list `site.test`

#### Scenario: A Seed blocked by robots.txt at its chain's end is reported
- **WHEN** `http://www.site.test/` redirects with 301 to `http://site.test/`, whose robots.txt disallows `/`, and `linx crawl http://www.site.test/` runs
- **THEN** the result's `warnings` hold an entry with code `seed_blocked_by_robots_txt`

#### Scenario: A section Seed whose chain leaves the section is reported
- **WHEN** `http://site.test/blog/` redirects with 301 to `http://site.test/`, and `linx crawl http://site.test/blog/ --scope subfolder` runs
- **THEN** the result's `warnings` hold an entry with code `seed_redirected_out_of_scope` whose `hint` contains `http://site.test/`, `http://site.test/` has `in_scope` = 0, and `crawl.scope` keeps the folder `/blog/`

#### Scenario: A Seed chain cut by the URL limit is decided by its final Scope
- **WHEN** `http://www.site.test/` redirects with 301 to `http://site.test/`, and `linx crawl http://www.site.test/ --max-urls 1` runs
- **THEN** `http://site.test/` has `fetch_state` = `queued` and `is_internal` = 0, and `crawl.scope` does not list `site.test`

#### Scenario: A Seed chain cut by the hop limit off its site is reported
- **WHEN** `http://site.test/` redirects with 301 to `http://other.test/`, and `linx crawl http://site.test/ --max-redirects 0` runs
- **THEN** the result's `warnings` hold an entry with code `seed_redirected_out_of_scope` whose `hint` contains `http://other.test/`, and `http://other.test/` has `is_internal` = 0

#### Scenario: A redirect to another site is reported
- **WHEN** `http://site.test/` redirects with 301 to `http://other.test/`, and `linx crawl http://site.test/` runs
- **THEN** the result's `warnings` hold an entry with code `seed_redirected_out_of_scope` whose `hint` contains `http://other.test/`

### Requirement: Redirect hop limit
The Crawl SHALL NOT follow a redirect that would be more than `--max-redirects` (default 10, at most 50, setting `crawl.max_redirects`) consecutive redirects from the first URL of its chain. A value above 50 SHALL be rejected as `invalid_value`, and in the settings file as `settings_invalid`. The target of such a redirect SHALL be recorded with `fetch_state` = `skipped` and `skip_reason` = `max_redirects`, a value that `020-add-crawl-core` lists.

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

#### Scenario: More than 50 redirects are rejected
- **WHEN** `linx crawl http://site.test/ --max-redirects 51` runs
- **THEN** it exits with code 2 and an error with code `invalid_value` that names `--max-redirects`

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
The Crawl SHALL stop reading a response body within one read past 20,971,520 bytes (20 MiB), and keep at most 20 MiB of it. This change adds this column to `urls`:

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `body_truncated` | INTEGER | yes | boolean | 1 when the body was larger and not read in full |

A URL with a larger body SHALL have `body_truncated` = 1, `parsed` = 0, `size_bytes` NULL, and `transferred_bytes` the number of bytes read. If it would otherwise have been parsed, it SHALL have `parse_error` = `body_too_large`, a value that `020-add-crawl-core` lists.

#### Scenario: A huge page is not parsed
- **WHEN** `/` links to `/huge.html`, a 26,214,400-byte (25 MiB) HTML page
- **THEN** `{site}/huge.html` has `body_truncated` = 1, `parsed` = 0 and `parse_error` = `body_too_large`

### Requirement: URL length limit
URLs longer than 2,000 characters SHALL NOT be requested, and SHALL be recorded with `fetch_state` = `skipped` and `skip_reason` = `url_too_long`, a value that `020-add-crawl-core` lists.

#### Scenario: A very long URL is skipped
- **WHEN** `/` links to a URL made of `{site}/` followed by 2,001 `a` characters
- **THEN** that URL has `skip_reason` = `url_too_long`

### Requirement: Compression
**In short:** request preferences are configurable; supported response codings decode incrementally under unchanged body and memory bounds.

Every request SHALL default to `Accept-Encoding: gzip, deflate, br`, and from v0.2 `Accept-Encoding: gzip, deflate, br, zstd`. From v0.2, an explicit custom Accept-Encoding SHALL replace this entire default for Internal requests only, including robots.txt and retries; External requests SHALL retain the default. Header names SHALL be matched without case. An explicit empty field value SHALL be sent as an empty field, not omitted or replaced by a transport default. Values SHALL follow RFC 9110 section 12.5.3, including coding tokens, `identity`, `*`, and qvalues from 0 to 1 with at most three fractional digits. A syntactically valid unsupported coding name SHALL be accepted. Repeated custom Accept-Encoding entries SHALL replace the default as one ordered field-value list while preserving the recorded entries. Malformed values SHALL fail before dispatch using the header input's source-specific error.

Decoder support SHALL be independent of the advertised Accept-Encoding: the Crawl SHALL decode supported response codings (gzip, deflate, br, and zstd from v0.2) even if not advertised or assigned `q=0`. Several supported codings SHALL be decoded in the reverse order of the Content-Encoding header. Advertising a coding SHALL NOT add decoder support. A body that fails to decode SHALL be recorded with `fetch_state` = `error` and `fetch_error` = `invalid_response`. A body with any unsupported Content-Encoding SHALL be recorded as `fetched`, with `size_bytes` NULL and `parsed` = 0; if it would otherwise have been parsed, it SHALL have `parse_error` = `unsupported_encoding`, whether or not the request advertised that coding. No new negotiation-mismatch outcome is introduced. For zstd, a stream SHALL support concatenated frames, reject corrupt or incomplete frames as `invalid_response`, and reject windows larger than 8,388,608 bytes, the HTTP content-coding limit. The 20 MiB body cap SHALL apply during decompression, including every intermediate stage of stacked encodings; neither a frame content-size field nor a small compressed body may cause unbounded allocation. These behaviours SHALL agree on Python 3.12, 3.13 and 3.14 on Windows, macOS and Linux. This change adds these columns to `urls`:

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `content_encoding` | TEXT | yes | | The `Content-Encoding` header as received |
| `size_bytes` | INTEGER | yes | | The body size after content decoding |
| `transferred_bytes` | INTEGER | yes | | The body size as transferred, before decoding |

#### Scenario: Requests accept compressed bodies
- **WHEN** `linx crawl {site}/` runs
- **THEN** the request for `/` has `Accept-Encoding` = `gzip, deflate, br, zstd` from v0.2 (`gzip, deflate, br` in v0.1)

#### Scenario: Accept-Encoding overrides have literal Internal and External outcomes
- **GIVEN** a v0.2 Crawl from `http://site.test/` linking to `http://other.test/page`
- **WHEN** a separate Crawl runs for each row below
- **THEN** every Internal request, including robots.txt, has the listed combined Accept-Encoding value, while every External request has `gzip, deflate, br, zstd`

| Workspace entries | CLI suffix | Internal Accept-Encoding |
|---|---|---|
| none | none | `gzip, deflate, br, zstd` |
| none | `--header "Accept-Encoding: identity"` | `identity` |
| none | `--header "accept-encoding:gzip"` | `gzip` |
| none | `--header "Accept-Encoding: br;q=1, gzip;q=0.5, identity;q=0"` | `br;q=1, gzip;q=0.5, identity;q=0` |
| none | `--header "Accept-Encoding: *;q=0.5"` | `*;q=0.5` |
| none | `--header "Accept-Encoding: x-unknown"` | `x-unknown` |
| none | `--header "Accept-Encoding:"` | empty field present |
| `header = ["Accept-Encoding: identity"]` | none | `identity` |
| `header = ["Accept-Encoding: identity"]` | `--header "Accept-Encoding: gzip"` | `gzip` |
| none | `--header "Accept-Encoding: gzip" --header "accept-encoding: br;q=0.5"` | `gzip, br;q=0.5` |

#### Scenario: Invalid negotiation syntax is refused before network
- **WHEN** a Crawl uses `--header "Accept-Encoding: gzip;q=1.1"`, `--header "Accept-Encoding: br;q=0.1234"` or `--header "Accept-Encoding: gzip;level=1"`
- **THEN** it exits with code 2 and `invalid_value` before any request; each equivalent invalid Workspace-only header exits with code 3 and `settings_invalid`

#### Scenario: A supported response is decoded despite the request preference
- **WHEN** a Crawl uses `--header "Accept-Encoding: identity, gzip;q=0"` and `/app.js` returns a gzip body decoding to the five ASCII bytes `hello`, with `Content-Encoding: gzip`
- **THEN** `/app.js` has `fetch_state` = `fetched`, `content_encoding` = `gzip`, `size_bytes` = 5 and `body_truncated` = 0

#### Scenario: Advertising an unsupported coding does not install a decoder
- **WHEN** a Crawl uses `--header "Accept-Encoding: x-unknown"` and `/unknown.html` returns an HTML response with `Content-Encoding: x-unknown`
- **THEN** `/unknown.html` has `fetch_state` = `fetched`, `parsed` = 0, `parse_error` = `unsupported_encoding` and `size_bytes` NULL

#### Scenario: A compressed Resource records both sizes
- **WHEN** `/app.js` returns a 10,000-byte script as a 2,500-byte gzip body with `Content-Encoding: gzip`, and `/` holds `<script src="/app.js">`
- **THEN** `{site}/app.js` has `size_bytes` = 10000, `transferred_bytes` = 2500 and `content_encoding` = `gzip`

#### Scenario: Stacked encodings are decoded in reverse order
- **WHEN** `/app.js` returns a 10,000-byte script compressed with gzip and then with br, with `Content-Encoding: gzip, br`, and `/` holds `<script src="/app.js">`
- **THEN** `{site}/app.js` has `size_bytes` = 10000 and `content_encoding` = `gzip, br`

#### Scenario: A corrupt compressed body is an invalid response
- **WHEN** `/broken.js` returns bytes that are no gzip stream with `Content-Encoding: gzip`, and `/` holds `<script src="/broken.js">`
- **THEN** `{site}/broken.js` has `fetch_state` = `error` and `fetch_error` = `invalid_response`

#### Scenario: A body in an encoding that was not offered is not parsed
- **WHEN** `/` links to `/unknown.html`, an HTML page that returns an unsupported body with `Content-Encoding: x-unknown`, and no custom Accept-Encoding is given
- **THEN** `{site}/unknown.html` has `fetch_state` = `fetched`, `parsed` = 0, `parse_error` = `unsupported_encoding` and `size_bytes` NULL

This retained v0.1 scenario exercises an unsupported coding. From v0.2, an unadvertised but supported coding follows "A supported response is decoded despite the request preference" instead.

#### Scenario: A zstd Resource records both sizes
- **WHEN** `/app.js` returns the 14-byte zstd frame `28b52ffd200529000068656c6c6f` decoding to `hello`, and `/` holds `<script src="/app.js">`
- **THEN** `{site}/app.js` has `size_bytes` = 5, `transferred_bytes` = 14 and `content_encoding` = `zstd`

#### Scenario: Concatenated zstd frames form one body
- **WHEN** `/app.js` returns two consecutive copies of the 14-byte frame `28b52ffd200529000068656c6c6f` with `Content-Encoding: zstd`
- **THEN** its decoded body is `hellohello`, `size_bytes` = 10 and `transferred_bytes` = 28

#### Scenario: An incomplete zstd frame is an invalid response
- **WHEN** `/broken.js` returns the incomplete frame `28b52ffd200529000068656c6c` with `Content-Encoding: zstd`
- **THEN** its URL has `fetch_state` = `error` and `fetch_error` = `invalid_response`

#### Scenario: A zstd window above the HTTP limit is refused
- **WHEN** `/large-window.js` returns a zstd frame declaring a 16,777,216-byte window
- **THEN** its URL has `fetch_state` = `error` and `fetch_error` = `invalid_response`

#### Scenario: A zstd bomb stops at the decoded cap
- **WHEN** `/huge.html` returns a zstd body decoding to 26,214,400 bytes of HTML
- **THEN** its URL has `body_truncated` = 1, `parse_error` = `body_too_large` and `size_bytes` NULL, and at most 20,971,520 decoded bytes are retained

### Requirement: Resource sizes
Every requested Resource SHALL have its `status_code`, `size_bytes` and `transferred_bytes` recorded, and SHALL NOT be parsed.

#### Scenario: An image's size is recorded
- **WHEN** `/` holds `<img src="/logo.png">`, and `/logo.png` returns 200 with a 2,048-byte `image/png` body
- **THEN** `{site}/logo.png` has `status_code` = 200, `size_bytes` = 2048 and `transferred_bytes` = 2048

### Requirement: TLS certificate verification
HTTPS requests SHALL verify the server certificate and its host name against the operating system's trust store, through truststore. When truststore cannot be loaded, certifi's bundle SHALL be the fallback. A request whose certificate does not verify SHALL be recorded with `fetch_state` = `error` and `fetch_error` = `tls_error`, a value that `020-add-crawl-core` lists. When an origin's robots.txt request fails verification, the origin's URLs SHALL be recorded with `fetch_error` = `tls_error` without a request, as `020-add-crawl-core` records the URLs behind a robots.txt that got no HTTP response. A `tls_error` SHALL NOT count towards the network pause of `020-add-crawl-core`: a certificate that fails verification is an answer from the server, and a site-wide certificate failure would otherwise wait out `--network-wait` and fail as `site_unreachable`.

#### Scenario: A certificate for another name is a TLS error
- **WHEN** `http://site.test/` links to `https://badcert.test/`, whose certificate is issued for `other.test`
- **THEN** `https://badcert.test/` has `fetch_error` = `tls_error`

#### Scenario: A certificate from an unknown CA is a TLS error
- **WHEN** `http://site.test/` links to `https://other.test:{untrusted_port}/`, whose certificate comes from a CA that is not trusted
- **THEN** that URL has `fetch_error` = `tls_error`

#### Scenario: TLS errors never pause the Crawl
- **WHEN** `https://site.test/` links to `https://a1.site.test/` to `https://a12.site.test/`, whose certificates do not verify, a fake Fetcher gives each of them `tls_error`, and `linx crawl https://site.test/ --scope subdomains --network-wait 0` runs with a fake clock
- **THEN** the Crawl completes, and no `crawl_paused` event is written

### Requirement: HTTP version per origin
**In short:** a dedicated ALPN probe records the origin's offered capability while crawler requests use HTTP/1.1.

In v0.1, before capability measurement, `origins.http_version` SHALL be NULL in every row and its description SHALL start with `Filled from v0.2. `.

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `http_version` | TEXT | yes | `http_2`, `http_1_1` | Filled from v0.2. The HTTP capability selected by a dedicated ALPN probe; crawler requests use HTTP/1.1 |

From v0.2, for every https origin it requests, the Crawl SHALL make one TLS handshake that offers the ALPN protocols `h2` and `http/1.1`. It SHALL record `origins.http_version` as `http_2` when `h2` is selected, and `http_1_1` otherwise. For http origins it SHALL record `http_1_1`. When measurement fails or is cancelled, `http_version` SHALL be NULL for that run and the Crawl SHALL go on according to its URL results. The measuring version SHALL remove the `Filled from v0.2. ` description prefix and describe offered capability.

The probe SHALL use the same DNS routing, TLS trust and effective proxy as requests, but send no origin HTTP request. Each requested origin SHALL be measured once per run, including External origins, failed probes and runs ignoring robots.txt. One total `--timeout` deadline SHALL bound admission, DNS, connection, CONNECT and TLS. Probe concurrency SHALL respect the run's connection and host limits without waiting for a probe permit while holding a URL/robots.txt permit. CONNECT headers SHALL be limited to 65,536 bytes. Probe failure SHALL NOT change a URL outcome, attempt count, URL limit or network pause. Stop SHALL cancel probes, close their connections and join them before the run returns; normal completion SHALL join them before closing the writer.

#### Scenario: The HTTP version is a later column
- **WHEN** `linx schema origins` runs in v0.1, before capability measurement is implemented
- **THEN** the column `http_version` has `nullable` `true`, `values` `["http_2","http_1_1"]`, and a `description` that starts with `Filled from v0.2. `

#### Scenario: An origin that selects HTTP/2
- **WHEN** `https://site.test` is served by a TLS listener that selects `h2`, and `linx crawl https://site.test/` runs
- **THEN** the `origins` row for `https://site.test` has `http_version` = `http_2`

#### Scenario: An origin that offers only HTTP/1.1
- **WHEN** `https://site.test` is served by a TLS listener that offers only `http/1.1`, and `linx crawl https://site.test/` runs
- **THEN** the `origins` row for `https://site.test` has `http_version` = `http_1_1`

#### Scenario: A plain http origin
- **WHEN** `linx crawl {site}/` runs
- **THEN** the `origins` row for `{site}` has `http_version` = `http_1_1`

#### Scenario: A listener with no ALPN selection is HTTP/1.1 capable
- **WHEN** a trusted `https://site.test` listener completes TLS without selecting ALPN
- **THEN** its `origins.http_version` is `http_1_1`

#### Scenario: One failed probe is not repeated for another URL
- **WHEN** two URLs on `https://site.test` are requested in one run and the dedicated probe fails TLS
- **THEN** exactly one dedicated probe is attempted and `origins.http_version` is NULL

#### Scenario: Ignoring robots does not skip capability measurement
- **WHEN** a Crawl ignores robots.txt and requests `https://site.test/` from an h2-selecting listener
- **THEN** its `origins.http_version` is `http_2`

#### Scenario: An External origin is measured
- **WHEN** `http://site.test/` links to `https://other.test/page` and that trusted listener selects `h2`
- **THEN** the row for `https://other.test` has `http_version` = `http_2`

#### Scenario: Probe failure leaves URL requests unchanged
- **WHEN** a dedicated probe fails while the ordinary request for `https://site.test/` returns 200 on its first attempt
- **THEN** the origin has `http_version` NULL, and its URL has `status_code` = 200 and `attempt_count` = 1

#### Scenario: A stalled capability probe has a total deadline
- **WHEN** a dedicated probe stalls in DNS, CONNECT or TLS and the Crawl uses `--timeout 1`
- **THEN** the probe is cancelled at its one-second total deadline, closes any connection it opened and leaves `http_version` NULL

#### Scenario: A single host slot cannot deadlock the capability probe
- **WHEN** `linx crawl https://site.test/ --concurrency 1` runs with one per-host slot and a trusted h2-selecting listener
- **THEN** the Crawl completes with its Seed at status 200 and the origin at `http_2`

#### Scenario: Stop closes an admitted capability probe
- **WHEN** the continue service is stopped after its dedicated TLS probe opens a connection and stalls
- **THEN** it returns with that connection closed, no probe task running and `http_version` NULL

#### Scenario: The measured column describes capability
- **WHEN** `linx schema origins` runs in the version that measures ALPN
- **THEN** `http_version` describes offered capability, says crawler requests use HTTP/1.1, and has no `Filled from v0.2. ` prefix

### Requirement: The response_headers table
The crawl store SHALL keep the response headers of each requested URL's last attempt in a table `response_headers`, under the conventions of `018-add-schema-conventions`, with one row for each URL whose last attempt received a response, and two columns:

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `url_id` | INTEGER, primary key, references `urls.id` | no | | The URL whose response the headers are |
| `headers` | TEXT | no | json | A JSON array of `[name, value]` pairs in the order and letter case they were received, with cookie values as `***` |

The table SHALL have no secondary index: its rows are read by `url_id`, its primary key. A query that filters by a header reads `headers` with `json_each`.

Cookie values SHALL never be stored. They SHALL be redacted in this exact format:
- **`Set-Cookie`:** the cookie value, meaning the text after the first `=` and before the first `;`, SHALL be replaced by `***`. So `sid=abc123; Path=/; HttpOnly` is stored as `sid=***; Path=/; HttpOnly`. A value with no `=` before its first `;` SHALL be stored as `***` followed by its attributes.
- **`Cookie`:** the value of each `name=value` pair, separated by `;`, SHALL be replaced by `***`. So `a=1; b=2` is stored as `a=***; b=***`. A part without `=` is a value alone, and SHALL be stored as `***`.

Header names, cookie names, attributes, and the order of the headers SHALL be kept.

#### Scenario: Columns of response_headers
- **WHEN** `linx schema response_headers` runs
- **THEN** the item's columns, reduced to `name`, `type`, `nullable`, `primary_key` and `references`, are `[{"name":"url_id","type":"INTEGER","nullable":false,"primary_key":true,"references":"urls.id"},{"name":"headers","type":"TEXT","nullable":false,"primary_key":false,"references":null}]`, and its `indexes` are `[]`

#### Scenario: Response headers are stored as received
- **WHEN** `/` returns the header `X-Robots-Tag: noindex`, and `linx crawl {site}/` runs
- **THEN** the `headers` of `{site}/` in `response_headers` contain the pair `["X-Robots-Tag", "noindex"]`

#### Scenario: A cookie value is not stored
- **WHEN** `/` returns the header `Set-Cookie: sid=abc123; Path=/; HttpOnly`, and `linx crawl {site}/` ends
- **THEN** the `headers` of `{site}/` contain the pair `["Set-Cookie", "sid=***; Path=/; HttpOnly"]`, and the bytes of the Crawl's files do not contain `abc123`

#### Scenario: A Cookie header is redacted pair by pair
- **WHEN** the response header `Cookie: a=1; b=2` is prepared for storage
- **THEN** it is stored as the pair `["Cookie", "a=***; b=***"]`
