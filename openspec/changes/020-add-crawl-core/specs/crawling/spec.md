## Purpose

Crawl a site in Spider mode. The capability decides which URLs are requested and which are followed, requests them politely, discovers Links, and records every URL in the crawl store, so agents can query a Crawl while it runs and after it ends. It also provides the hooks that later changes build on.

Scenario conventions:
- `{site}` is the origin of the local fixture site, for example `http://127.0.0.1:8765`.
- A bare path such as `/about` means the fixture page at `{site}/about`.
- In scenarios that use the host names `site.test` and `other.test`, the DNS resolver hook maps them to two fixture site instances, and every other name fails to resolve.

## ADDED Requirements

### Requirement: Spider mode
`spider crawl <url>` SHALL start a Crawl in Spider mode with the URL as its only Seed, written to `seeds` as given (`015-add-crawl-store`). It SHALL follow Links from the Seed within the Scope, and run in the foreground until the Crawl ends. A Seed given without a scheme SHALL get `https://`. A Seed that is not a valid http or https URL SHALL be rejected with exit code 2 and error code `invalid_url` before any request is made, and no Crawl SHALL be created.

#### Scenario: The Seed is fetched and recorded
- **WHEN** `/` returns 200 with an HTML page, and `spider crawl {site}/` runs
- **THEN** the `urls` row for `{site}/` has `host` = `127.0.0.1`, `fetch_state` = `fetched`, `status_code` = 200, `crawl_depth` = 0 and `discovered_via` = `seed`

#### Scenario: The Seed is kept as given in seeds
- **WHEN** `spider crawl {site}` runs, without a trailing slash
- **THEN** the `seeds` table holds exactly the row `(1, "{site}")`, while the `urls` row is for `{site}/`

#### Scenario: Pages linked from the Seed are crawled
- **WHEN** `/` links to `/about`, `/about` links to `/team`, and `spider crawl {site}/` runs
- **THEN** the Crawl's `urls` table holds exactly `{site}/`, `{site}/about` and `{site}/team`, each with `fetch_state` = `fetched` and `status_code` = 200

#### Scenario: A bare host becomes an https Seed
- **WHEN** the Seed argument `site.test/shop` is parsed
- **THEN** the Seed is `https://site.test/shop`

#### Scenario: An invalid Seed is rejected
- **WHEN** `spider crawl "http://exa mple.test/"` runs
- **THEN** the Command exits with code 2 and its only stderr error has `code` = `invalid_url`
- **AND** the Workspace holds no new crawl file

### Requirement: URL normalisation
The Crawl SHALL identify every URL by its normalised form, and SHALL request and record only that form. Normalisation SHALL:
- write the scheme and host in lower case, and convert an internationalised host name to its ASCII (IDNA) form
- remove the fragment
- remove the port when it is the scheme's default (80 for http, 443 for https)
- resolve `.` and `..` path segments, and use `/` for an empty path
- write percent-encodings with upper-case hex digits, and decode percent-encoded unreserved characters (letters, digits, `-`, `.`, `_`, `~`)
- percent-encode as UTF-8 the characters that a URL may not contain
- keep the letter case of the path, and keep the query and its parameter order unchanged

#### Scenario: Scheme and host case, the default port and the fragment are normalised
- **WHEN** `HTTP://Site.TEST:80/About#team` is normalised
- **THEN** the result is `http://site.test/About`

#### Scenario: A non-default port is kept
- **WHEN** `https://site.test:8443/a` is normalised
- **THEN** the result is `https://site.test:8443/a`

#### Scenario: Dot segments are resolved
- **WHEN** `https://site.test/a/./b/../c` is normalised
- **THEN** the result is `https://site.test/a/c`

#### Scenario: An empty path becomes a slash
- **WHEN** `https://site.test` is normalised
- **THEN** the result is `https://site.test/`

#### Scenario: Percent-encodings are normalised
- **WHEN** `http://site.test/%7euser/a%2fb` is normalised
- **THEN** the result is `http://site.test/~user/a%2Fb`

#### Scenario: Characters outside ASCII are percent-encoded
- **WHEN** `http://site.test/café?q=ü` is normalised
- **THEN** the result is `http://site.test/caf%C3%A9?q=%C3%BC`

#### Scenario: An internationalised host becomes ASCII
- **WHEN** `http://bücher.test/` is normalised
- **THEN** the result is `http://xn--bcher-kva.test/`

#### Scenario: The query and its parameter order are kept
- **WHEN** `http://site.test/p?b=2&a=1` is normalised
- **THEN** the result is `http://site.test/p?b=2&a=1`

#### Scenario: Normalising twice changes nothing
- **WHEN** any generated valid http or https URL is normalised, and the result is normalised again
- **THEN** the second result equals the first

### Requirement: Stripping query parameters
Query parameters SHALL be kept by default. `--strip-params <patterns>` SHALL remove every query parameter whose name matches one of the comma-separated glob patterns before the URL is recorded. In a pattern, `*` matches any run of characters and `?` matches one character, and matching is case-sensitive. The flag SHALL be accepted more than once. The remaining parameters SHALL keep their order. A query left empty SHALL be removed together with its `?`.

#### Scenario: Matching parameters are removed
- **WHEN** `http://site.test/p?utm_source=x&id=7&fbclid=y` is normalised with `--strip-params "utm_*,fbclid"`
- **THEN** the result is `http://site.test/p?id=7`

#### Scenario: Removing every parameter removes the query
- **WHEN** `http://site.test/p?a=1&b=2` is normalised with `--strip-params "*"`
- **THEN** the result is `http://site.test/p`

#### Scenario: Parameters are kept by default
- **WHEN** `http://site.test/p?utm_source=x` is normalised without `--strip-params`
- **THEN** the result is `http://site.test/p?utm_source=x`

#### Scenario: URLs that differ only in stripped parameters are fetched once
- **WHEN** `/` links to `/p?utm_source=a` and `/p?utm_source=b`, and `spider crawl {site}/ --strip-params "utm_*"` runs
- **THEN** the fixture site receives exactly one request for `/p`

### Requirement: Internal URLs
A URL SHALL be an Internal URL when its scheme is http or https and its host equals a Seed host, whatever its scheme and port. In Spider mode, the Seed host is the Seed's host. `024-add-list-and-sitemap-modes` defines the Seed hosts of the other Crawl Modes.

With `--scope subdomains`, a URL SHALL also be internal when its registrable domain equals the registrable domain of a Seed host. The registrable domain comes from a copy of the Public Suffix List bundled with the tool, which SHALL never be downloaded during a Crawl. Every other URL SHALL be an External URL.

#### Scenario: The other scheme of the Seed host is internal
- **WHEN** the Scope of Seed `http://site.test/` decides on `https://site.test:8443/x`
- **THEN** the URL is internal

#### Scenario: Another host is external by default
- **WHEN** the Scope of Seed `http://site.test/` decides on `http://www.site.test/`
- **THEN** the URL is external

#### Scenario: Subdomains are internal with the subdomains Scope
- **WHEN** the Scope of Seed `http://www.site.test/` with `--scope subdomains` decides on `http://blog.site.test/`
- **THEN** the URL is internal

#### Scenario: A public suffix is not treated as the site
- **WHEN** the Scope of Seed `http://www.shop.co.uk/` with `--scope subdomains` decides on `http://other.co.uk/`
- **THEN** the URL is external

### Requirement: Scope option
`--scope` SHALL accept `host` (the default), `subdomains` or `subfolder`. `--subdomains` SHALL mean the same as `--scope subdomains`. Combining `--subdomains` with another `--scope` value SHALL be rejected with exit code 2 and error code `option_conflict`.

#### Scenario: The subdomains shorthand conflicts with a subfolder Scope
- **WHEN** `spider crawl {site}/blog/ --subdomains --scope subfolder` runs
- **THEN** the Command exits with code 2 and its only stderr error has `code` = `option_conflict`

### Requirement: Subfolder Scope
With `--scope subfolder`, only Internal URLs whose path starts with the Seed's folder SHALL be in the Scope. The folder SHALL be the Seed's path up to and including its last `/`. A Seed whose folder would be `/` SHALL be rejected with exit code 2 and error code `subfolder_is_root`, with a hint that gives the Seed with a trailing `/`.

#### Scenario: The folder of a Seed page is its parent folder
- **WHEN** the Scope of Seed `http://site.test/blog/post-1` with `--scope subfolder` is resolved
- **THEN** its folder is `/blog/`

#### Scenario: Pages inside the folder are followed
- **WHEN** `/blog/` links to `/blog/post`, and `spider crawl {site}/blog/ --scope subfolder` runs
- **THEN** `{site}/blog/post` has `in_scope` = 1 and `parsed` = 1

#### Scenario: Pages outside the folder are checked but not followed
- **WHEN** `/blog/` links to `/shop/`, `/shop/` links to `/shop/item`, and `spider crawl {site}/blog/ --scope subfolder` runs
- **THEN** `{site}/shop/` has `fetch_state` = `fetched` and `parsed` = 0
- **AND** the `urls` table holds no row for `{site}/shop/item`

#### Scenario: A Seed without its trailing slash is rejected
- **WHEN** `spider crawl {site}/blog --scope subfolder` runs
- **THEN** the Command exits with code 2, and its only stderr error has `code` = `subfolder_is_root` and a `hint` that contains `{site}/blog/`

### Requirement: Include and exclude patterns
`--include <regex>` and `--exclude <regex>` SHALL take Python regular expressions, and each flag SHALL be accepted more than once. Each pattern SHALL be searched for anywhere in the normalised URL, case-sensitively.
- **Exclude:** a URL that matches an `--exclude` pattern SHALL NOT be requested. It SHALL be recorded with `fetch_state` = `skipped`, `skip_reason` = `excluded` and `in_scope` = 0.
- **Include:** when at least one `--include` pattern is given, an Internal URL that matches none of them SHALL be outside the Scope.
- **Errors:**
  - An invalid pattern SHALL be rejected with exit code 2 and error code `invalid_pattern`.
  - A Seed outside the Scope SHALL be rejected with exit code 2 and error code `seed_out_of_scope`.

#### Scenario: An excluded URL is never requested
- **WHEN** `/` links to `/logout`, and `spider crawl {site}/ --exclude "/logout$"` runs
- **THEN** the fixture site receives no request for `/logout`

#### Scenario: An excluded URL is recorded as skipped
- **WHEN** `/` links to `/logout`, and `spider crawl {site}/ --exclude "/logout$"` runs
- **THEN** `{site}/logout` has `fetch_state` = `skipped` and `skip_reason` = `excluded`

#### Scenario: A URL that matches no include pattern is checked but not followed
- **WHEN** `/blog/` links to `/news/n`, and `spider crawl {site}/blog/ --include "/blog/"` runs
- **THEN** `{site}/news/n` has `fetch_state` = `fetched`, `in_scope` = 0 and `parsed` = 0

#### Scenario: Exclude wins over include
- **WHEN** the Scope of Seed `http://site.test/blog/` with `--include "/blog/"` and `--exclude "draft"` decides on `http://site.test/blog/draft-1`
- **THEN** the decision is to skip it with `skip_reason` = `excluded`

#### Scenario: An invalid pattern is rejected
- **WHEN** `spider crawl {site}/ --include "("` runs
- **THEN** the Command exits with code 2 and its only stderr error has `code` = `invalid_pattern`

#### Scenario: A Seed outside the Scope is rejected
- **WHEN** `spider crawl http://site.test/ --exclude "site"` runs
- **THEN** the Command exits with code 2 and its only stderr error has `code` = `seed_out_of_scope`

### Requirement: Section Crawl
A Crawl SHALL be a Section Crawl when it uses `--scope subfolder` or at least one `--include` pattern. The Crawl SHALL set `crawl.section_crawl` (`015-add-crawl-store`) to 1 for a Section Crawl and to 0 otherwise. The result SHALL report it as `"section_crawl": true` or `false`. `--exclude` alone SHALL NOT make a Crawl a Section Crawl.

#### Scenario: A subfolder Crawl is a Section Crawl
- **WHEN** `spider crawl {site}/blog/ --scope subfolder` ends
- **THEN** the result has `"section_crawl": true`

#### Scenario: An include pattern makes a Section Crawl
- **WHEN** `spider crawl {site}/blog/ --include "/blog/"` ends
- **THEN** `crawl.section_crawl` is 1

#### Scenario: Exclude patterns alone do not make a Section Crawl
- **WHEN** `spider crawl {site}/ --exclude "/tag/"` ends
- **THEN** the result has `"section_crawl": false`

### Requirement: Recorded Scope
The Crawl SHALL record the resolved Scope in the column `crawl.scope`, which this change adds as TEXT in the `json` format, as the object `{mode, hosts, folder, include, exclude}`:
- `hosts` lists the Seed hosts, or the registrable domains with `--scope subdomains`.
- `folder` is null unless the Scope is `subfolder`.

#### Scenario: A subfolder Scope is recorded
- **WHEN** `spider crawl http://site.test/blog/ --scope subfolder --exclude "/draft"` ends and `http://site.test/blog/` returns 200
- **THEN** `crawl.scope` is `{"mode": "subfolder", "hosts": ["site.test"], "folder": "/blog/", "include": [], "exclude": ["/draft"]}`

### Requirement: Link discovery
The Crawl SHALL discover Links in every response it parses, and in the HTTP `Link` header of every in-Scope 2xx response.
- **Resolution:** it SHALL resolve each relative reference against the Page's `<base href>` when there is one, and otherwise against the response URL. It SHALL then normalise the result, and SHALL ignore references whose scheme is not http or https.
- **Link types:** each discovered Link SHALL have one of these Link types, and its target SHALL be requested by default as shown:

| Link type | Found in | Requested by default |
|---|---|---|
| `hyperlink` | `<a href>`, `<area href>` | yes |
| `canonical` | `<link rel="canonical">`; an HTTP `Link` header with `rel="canonical"` | yes |
| `pagination` | `<link rel="next">`, `<link rel="prev">`, `<link rel="previous">`; an HTTP `Link` header with `rel` `next`, `prev` or `previous` | yes |
| `hreflang` | `<link rel="alternate" hreflang>`; an HTTP `Link` header with `rel="alternate"` and `hreflang` | yes |
| `iframe` | `<iframe src>`, `<frame src>` | yes |
| `meta_refresh` | the URL in `<meta http-equiv="refresh" content="…; url=…">` | yes |
| `image` | `<img src>`; every candidate in the `srcset` of `<img>` and `<source>`; `<video poster>` | yes, as a Resource |
| `css` | `<link rel="stylesheet" href>` | yes, as a Resource |
| `javascript` | `<script src>` | yes, as a Resource |
| `media` | the `src` of `<video>`, `<audio>`, `<source>`, `<track>` and `<embed>`; `<object data>` | yes, as a Resource |
| `amphtml` | `<link rel="amphtml">` | no |
| `mobile_alternate` | `<link rel="alternate" media>` without `hreflang` | no |

- **Link types that are not requested:** a URL reached only through them SHALL be recorded with `fetch_state` = `skipped` and `skip_reason` = `link_type_not_followed`.
- **Provenance:** a URL's `discovered_via` SHALL be how it was first found: `seed`, or the Link type. `found_on_url_id` SHALL point to the URL whose response revealed it. Later changes add other ways of finding URLs.

#### Scenario: A relative link is resolved against the base href
- **WHEN** the Links of `http://site.test/` are extracted from `<base href="http://site.test/docs/"><a href="guide">Guide</a>`
- **THEN** exactly one Link is found: a `hyperlink` to `http://site.test/docs/guide`

#### Scenario: Every srcset candidate is an image Link
- **WHEN** the Links of `http://site.test/` are extracted from `<img src="/a.png" srcset="/a-2x.png 2x, /a-3x.png 3x">`
- **THEN** exactly three `image` Links are found, to `http://site.test/a.png`, `http://site.test/a-2x.png` and `http://site.test/a-3x.png`

#### Scenario: rel previous is a pagination Link
- **WHEN** the Links of `http://site.test/p2` are extracted from `<link rel="previous" href="/p1">`
- **THEN** exactly one Link is found: a `pagination` Link to `http://site.test/p1`

#### Scenario: References that are not http or https are ignored
- **WHEN** the Links of `http://site.test/` are extracted from `<a href="mailto:hi@site.test">Mail</a><a href="javascript:void(0)">Menu</a>`
- **THEN** no URL to request is found

#### Scenario: A discovered URL points to where it was found
- **WHEN** `/` links to `/about`, and `spider crawl {site}/` runs
- **THEN** `{site}/about` has `discovered_via` = `hyperlink` and a `found_on_url_id` pointing to `{site}/`

#### Scenario: A canonical in an HTTP header is followed
- **WHEN** `/` links to `/doc.pdf`, which returns `Content-Type: application/pdf` and `Link: <{site}/doc>; rel="canonical"`
- **THEN** `{site}/doc` has `fetch_state` = `fetched` and `discovered_via` = `canonical`

#### Scenario: amphtml targets are not requested
- **WHEN** `/` holds `<link rel="amphtml" href="/amp/">`, and `spider crawl {site}/` runs
- **THEN** `{site}/amp/` has `fetch_state` = `skipped` and `skip_reason` = `link_type_not_followed`

#### Scenario: A meta refresh target is followed
- **WHEN** `/` links to `/old`, which holds `<meta http-equiv="refresh" content="0; url=/new">`
- **THEN** `{site}/new` has `fetch_state` = `fetched` and `discovered_via` = `meta_refresh`

### Requirement: Robots directives
The Crawl SHALL read the robots directives of every parsed response with one parser, which `030-add-page-data` reuses for its directive columns. For a response, the parser SHALL give these values:
- `meta_robots`: the whitespace-normalised `content` of every `<meta>` element whose `name` is `robots` (compared case-insensitively), joined with `, ` in document order, or null when there is none
- `x_robots_tag`: the whitespace-normalised values of every `X-Robots-Tag` response header, joined with `, ` in the order received, or null when there is none
- `meta_noindex` and `meta_nofollow`: true when a directive in `meta_robots` is `noindex` or `nofollow` respectively, or `none`
- `header_noindex` and `header_nofollow`: the same, for the header values that apply

Directives SHALL be comma-separated tokens, compared case-insensitively. A header value has a user-agent prefix when it starts with `<name>:` and `<name>` is not `unavailable_after`, `max-snippet`, `max-image-preview` or `max-video-preview`. A prefixed header value SHALL apply only when `<name>` equals the robots user-agent token, compared case-insensitively. `<meta>` elements named after a specific crawler SHALL NOT be read.

#### Scenario: Meta robots directives are read case-insensitively
- **WHEN** the directives are read from `<meta name="ROBOTS" content="NOINDEX, follow">`
- **THEN** `meta_robots` is `NOINDEX, follow`, `meta_noindex` is true and `meta_nofollow` is false

#### Scenario: A header for another crawler does not apply
- **WHEN** the directives are read with the default robots user-agent token from the header `X-Robots-Tag: googlebot: noindex`
- **THEN** `x_robots_tag` is `googlebot: noindex` and `header_noindex` is false

#### Scenario: A header for the robots user-agent token applies
- **WHEN** the directives are read with the robots user-agent token `Googlebot` from the header `X-Robots-Tag: googlebot: noindex`
- **THEN** `header_noindex` is true

#### Scenario: none means noindex and nofollow
- **WHEN** the directives are read from the header `X-Robots-Tag: none`
- **THEN** `header_noindex` and `header_nofollow` are both true

#### Scenario: A directive with a value is not a user-agent prefix
- **WHEN** the directives are read from the header `X-Robots-Tag: unavailable_after: 25 Jun 2030 15:00:00 PST, noindex`
- **THEN** `header_noindex` is true

### Requirement: Nofollow
The following SHALL NOT be requested unless the same target is also reached through a Link that is followed:
- a `hyperlink` whose `rel` attribute contains the token `nofollow`
- every `hyperlink` on a Page whose robots directives give `meta_nofollow` or `header_nofollow`

Such a target SHALL be recorded with `fetch_state` = `skipped` and `skip_reason` = `nofollow`. With `--follow-nofollow`, these Links SHALL be treated like any other `hyperlink`.

#### Scenario: A nofollow link is not requested
- **WHEN** `/` holds `<a rel="nofollow" href="/private">`, and `spider crawl {site}/` runs
- **THEN** `{site}/private` has `fetch_state` = `skipped` and `skip_reason` = `nofollow`

#### Scenario: A page-level nofollow applies to every hyperlink
- **WHEN** `/` holds `<meta name="robots" content="noindex, nofollow">` and `<a href="/x">`, and `spider crawl {site}/` runs
- **THEN** `{site}/x` has `skip_reason` = `nofollow`

#### Scenario: A nofollow target reached through a followed Link is fetched
- **WHEN** `/` links to `/p` with `rel="nofollow"` and to `/about`, and `/about` links to `/p` without `rel`
- **THEN** `{site}/p` has `fetch_state` = `fetched`

#### Scenario: Nofollow Links are followed on request
- **WHEN** `/` holds `<a rel="nofollow" href="/private">`, and `spider crawl {site}/ --follow-nofollow` runs
- **THEN** `{site}/private` has `fetch_state` = `fetched`

### Requirement: Parsed responses
The Crawl SHALL parse a response only when all of these hold:
- its URL is in the Scope
- its status code is 2xx
- its Content-Type is `text/html` or `application/xhtml+xml`

It SHALL record `parsed` = 1 for such a URL and 0 for every other URL.

#### Scenario: Links on an error page are not followed
- **WHEN** `/` links to `/gone`, which returns 404 with an HTML body that links to `/secret`
- **THEN** `{site}/gone` has `parsed` = 0 and the `urls` table holds no row for `{site}/secret`

### Requirement: External URLs are checked, not followed
An External URL reached through a Link type that is requested SHALL be requested once to record its response, and SHALL NOT be parsed. With `--no-check-external`, External URLs SHALL NOT be requested, and SHALL be recorded with `fetch_state` = `skipped` and `skip_reason` = `external_not_checked`.

#### Scenario: An External URL is checked
- **WHEN** `http://site.test/` links to `http://other.test/page`, which links to `http://other.test/deeper`, and `spider crawl http://site.test/` runs
- **THEN** `http://other.test/page` has `fetch_state` = `fetched` and `parsed` = 0
- **AND** the `urls` table holds no row for `http://other.test/deeper`

#### Scenario: External checks can be turned off
- **WHEN** `http://site.test/` links to `http://other.test/page`, and `spider crawl http://site.test/ --no-check-external` runs
- **THEN** the `other.test` fixture instance receives no request

### Requirement: Resources are requested, not parsed
URLs reached through `image`, `css`, `javascript` or `media` Links SHALL be requested whenever the Page that references them is followed, even when their Crawl Depth exceeds `--max-depth`. A response that is not HTML SHALL NOT be parsed. `022-add-fetch-policy` adds their size measurements.

#### Scenario: An image is checked but not parsed
- **WHEN** `/` holds `<img src="/logo.png">`, and `/logo.png` returns 200 with an `image/png` body
- **THEN** `{site}/logo.png` has `status_code` = 200 and `parsed` = 0

#### Scenario: A broken image is recorded
- **WHEN** `/` holds `<img src="/missing.png">`, and `/missing.png` returns 404
- **THEN** `{site}/missing.png` has `status_code` = 404

#### Scenario: Resources are checked beyond the depth limit
- **WHEN** `/` holds `<img src="/logo.png">` and `<a href="/about">`, and `spider crawl {site}/ --max-depth 0` runs
- **THEN** `{site}/logo.png` has `fetch_state` = `fetched`

### Requirement: robots.txt is obeyed by default
Before its first request to an origin (a scheme, host and port), the Crawl SHALL fetch that origin's `/robots.txt`, once per origin in each run. It SHALL NOT request URLs that robots.txt disallows for the robots user-agent token.
- **Blocked URLs** SHALL be recorded with `fetch_state` = `skipped`, `skip_reason` = `blocked_by_robots` and `blocked_by_robots` = 1. Requested URLs SHALL have `blocked_by_robots` = 0, and URLs not checked against robots.txt SHALL have NULL.
- **Every origin:** this SHALL apply to every origin, including the origins of External URLs and Resources.
- **robots.txt requests** SHALL NOT be recorded as URLs and SHALL NOT count toward `--max-urls`.
- **Crawl-delay:** the `Crawl-delay` directive SHALL be recorded but not applied.
- **A blocked Seed** SHALL produce a `seed_blocked_by_robots` warning whose hint contains `--ignore-robots`.

#### Scenario: A disallowed URL is not requested
- **WHEN** `/robots.txt` is `User-agent: *` LF `Disallow: /private/`, `/` links to `/private/a`, and `spider crawl {site}/` runs
- **THEN** the fixture site receives no request for `/private/a`

#### Scenario: A disallowed URL is recorded as blocked
- **WHEN** `/robots.txt` is `User-agent: *` LF `Disallow: /private/`, `/` links to `/private/a`, and `spider crawl {site}/` runs
- **THEN** `{site}/private/a` has `skip_reason` = `blocked_by_robots` and `blocked_by_robots` = 1

#### Scenario: robots.txt is fetched once per origin
- **WHEN** `/` links to `/p1` to `/p9`, and `spider crawl {site}/` runs
- **THEN** the fixture site receives exactly one request for `/robots.txt`

#### Scenario: robots.txt is stored with its origin
- **WHEN** `/robots.txt` is `User-agent: *` LF `Crawl-delay: 5` LF `Disallow: /private/` LF `Sitemap: {site}/sitemap.xml`, and `spider crawl {site}/` runs
- **THEN** the `origins` row for `{site}` has `robots_state` = `ok`, `robots_status_code` = 200, `robots_txt` equal to the served text, `robots_crawl_delay_ms` = 5000, `robots_sitemaps` = `["{site}/sitemap.xml"]` and a non-null `robots_fetched_at`

#### Scenario: Crawl-delay is not applied
- **WHEN** a fake Fetcher serves a robots.txt with `Crawl-delay: 30` and three linked pages on one host, and the Crawl runs with a fake clock
- **THEN** all four page requests start before 1 second of clock time has passed

#### Scenario: A blocked Seed is reported
- **WHEN** `/robots.txt` is `User-agent: *` LF `Disallow: /`, and `spider crawl {site}/` runs
- **THEN** the result's `warnings` hold an entry with code `seed_blocked_by_robots` whose `hint` contains `--ignore-robots`

### Requirement: Ignoring robots.txt
With `--ignore-robots`, the Crawl SHALL request URLs that robots.txt disallows, and SHALL still record `blocked_by_robots` = 1 for them.

#### Scenario: Disallowed URLs are crawled and still labelled
- **WHEN** `/robots.txt` disallows `/private/`, `/` links to `/private/a`, and `spider crawl {site}/ --ignore-robots` runs
- **THEN** `{site}/private/a` has `fetch_state` = `fetched` and `blocked_by_robots` = 1

### Requirement: robots.txt fetch outcomes
The Crawl SHALL treat an origin's robots.txt by its response, as RFC 9309 describes:
- **2xx:** its rules apply and `robots_state` = `ok`. Only its first 512,000 bytes SHALL be parsed.
- **4xx other than 429:** every URL on the origin is allowed, and `robots_state` = `missing`.
- **5xx, 429, or no response:** every URL on the origin is disallowed, and `robots_state` = `unreachable`.
  - Its URLs SHALL be recorded with `skip_reason` = `robots_unreachable`.
  - For an Internal origin, a `robots_unreachable` warning SHALL be recorded whose hint contains `--ignore-robots`.
- **Redirects:** the robots.txt request SHALL follow up to 5 redirect hops. A longer chain SHALL be treated as `missing`.

#### Scenario: A missing robots.txt allows everything
- **WHEN** `/robots.txt` returns 404, and `spider crawl {site}/` runs
- **THEN** `{site}/` has `fetch_state` = `fetched` and the `origins` row for `{site}` has `robots_state` = `missing`

#### Scenario: An unreachable robots.txt blocks its origin
- **WHEN** `/robots.txt` returns 503 on every attempt, and `spider crawl {site}/` runs
- **THEN** `{site}/` has `skip_reason` = `robots_unreachable`

#### Scenario: An unreachable robots.txt of the site is reported
- **WHEN** `/robots.txt` returns 503 on every attempt, and `spider crawl {site}/` runs
- **THEN** the result's `warnings` hold an entry with code `robots_unreachable` whose `hint` contains `--ignore-robots`

#### Scenario: A redirected robots.txt is followed
- **WHEN** `/robots.txt` redirects with 301 to `/robots-real.txt`, which disallows `/private/`, and `/` links to `/private/a`
- **THEN** `{site}/private/a` has `skip_reason` = `blocked_by_robots`

#### Scenario: More than five robots.txt redirects count as missing
- **WHEN** `/robots.txt` starts a chain of 6 redirects, and `spider crawl {site}/` runs
- **THEN** the `origins` row for `{site}` has `robots_state` = `missing`

### Requirement: Robots user-agent token
The Crawl SHALL select robots.txt groups, and user-agent-prefixed robots directives, with the token `spider` by default, or with the token given in `--robots-user-agent <token>`. The token is independent of the `User-Agent` request header.

#### Scenario: The group for the tool's token applies
- **WHEN** the robots rules `User-agent: spider` LF `Disallow: /a` LF LF `User-agent: *` LF `Disallow: /b` are applied with the default token
- **THEN** `http://site.test/a` is disallowed and `http://site.test/b` is allowed

#### Scenario: Another token can be chosen
- **WHEN** the robots rules `User-agent: Googlebot` LF `Disallow: /g` are applied with `--robots-user-agent Googlebot`
- **THEN** `http://site.test/g` is disallowed

### Requirement: Per-host concurrency
The Crawl SHALL never have more than `--concurrency` requests in flight to one host. The default SHALL be 5. A value outside 1 to 50 SHALL be rejected with exit code 2 and error code `invalid_value`.

#### Scenario: At most five requests to a host by default
- **WHEN** `/` links to `/slow/1` to `/slow/20`, each answering after 500 ms, and `spider crawl {site}/` runs
- **THEN** the highest number of simultaneous requests the fixture site records is 5

#### Scenario: A lower concurrency is honoured
- **WHEN** `/` links to `/slow/1` to `/slow/20`, each answering after 500 ms, and `spider crawl {site}/ --concurrency 2` runs
- **THEN** the highest number of simultaneous requests the fixture site records is 2

#### Scenario: A concurrency of zero is rejected
- **WHEN** `spider crawl {site}/ --concurrency 0` runs
- **THEN** the Command exits with code 2 and its only stderr error has `code` = `invalid_value`

### Requirement: Rate limit
With `--rate <n>`, where n is a positive number of requests per second, requests to one host SHALL start at least `1/n` seconds apart, and the robots.txt request SHALL count as one of them. Without `--rate`, no limit SHALL apply beyond `--concurrency`.

#### Scenario: Requests to a host are spaced by the rate
- **WHEN** a Crawl with `--rate 2` requests robots.txt and then five URLs on one host through a fake Fetcher that answers at once, with a fake clock
- **THEN** the six requests start at 0.0, 0.5, 1.0, 1.5, 2.0 and 2.5 seconds

### Requirement: Blocking warning
When 10 consecutive responses from one Internal host have status 403 or 429, the Crawl SHALL record one `possible_blocking` warning for that host, whose hint names `--rate` and `--concurrency`, and SHALL go on crawling.

#### Scenario: Many 403 responses raise one warning
- **WHEN** `/` links to `/blocked/1` to `/blocked/12`, which all return 403
- **THEN** the result's `warnings` hold exactly one entry with code `possible_blocking`

### Requirement: Requests without a response
A request that gets no HTTP response SHALL be recorded with:
- `fetch_state` = `error` and `status_code` NULL
- a `fetch_error` code
- a non-empty `fetch_error_message`

This capability SHALL use the codes `dns_error`, `connection_refused`, `connection_error` and `invalid_response`. `022-add-fetch-policy` adds `timeout` and `tls_error`.

#### Scenario: An unknown host is a DNS error
- **WHEN** `http://site.test/` links to `http://nowhere.test/`, and `spider crawl http://site.test/` runs
- **THEN** `http://nowhere.test/` has `fetch_state` = `error` and `fetch_error` = `dns_error`

#### Scenario: A closed port is a refused connection
- **WHEN** `/` links to `http://127.0.0.1:{closed_port}/`, a port on which nothing listens
- **THEN** that URL has `fetch_error` = `connection_refused` and a non-empty `fetch_error_message`

### Requirement: Crawl Depth
Every Seed SHALL have `crawl_depth` = 0. Every other URL SHALL have the smallest number of Links followed from a Seed to reach it, whatever order responses arrive in.

#### Scenario: The shortest path wins over a faster, longer one
- **WHEN** `/` links to `/slow` (which answers after 2 seconds) and to `/a`; `/a` links to `/x`; `/x` links to `/b`; and `/slow` links to `/b`
- **THEN** `{site}/b` has `crawl_depth` = 2

#### Scenario: A Resource is one deeper than its Page
- **WHEN** `/` links to `/about`, which holds `<img src="/i.png">`
- **THEN** `{site}/i.png` has `crawl_depth` = 2

### Requirement: Depth limit
URLs whose Crawl Depth exceeds `--max-depth` SHALL NOT be requested, except Resources of followed Pages. They SHALL be recorded with `fetch_state` = `skipped` and `skip_reason` = `max_depth`. In Spider mode there SHALL be no limit by default.

#### Scenario: Links beyond the limit are not requested
- **WHEN** `/` links to `/a`, `/a` links to `/b`, and `spider crawl {site}/ --max-depth 1` runs
- **THEN** `{site}/b` has `skip_reason` = `max_depth`

### Requirement: URL limit
The Crawl SHALL start at most `--max-urls` requests for URLs. The default SHALL be 10,000, and 0 SHALL mean no limit. Every URL request SHALL count, but robots.txt requests SHALL NOT. When the limit is reached:
- no new request SHALL start
- the Crawl SHALL end with the Crawl State `stopped` and `crawl.stop_reason` = `max_urls`, and SHALL be resumable
- URLs not yet requested SHALL stay `queued`
- the result SHALL hold a `max_urls_reached` warning whose hint is `spider resume --crawl <crawl id> --max-urls <higher>`
- the Command SHALL exit with code 0

#### Scenario: The Crawl stops at the limit
- **WHEN** `/` links to `/p1` to `/p9`, and `spider crawl {site}/ --max-urls 3` runs
- **THEN** the result has `"state": "stopped"`, `"stop_reason": "max_urls"` and `"fetched": 3` in `urls`

#### Scenario: URLs not requested stay queued
- **WHEN** `/` links to `/p1` to `/p9`, and `spider crawl {site}/ --max-urls 3` ends
- **THEN** exactly 7 rows of the `urls` table have `fetch_state` = `queued`

#### Scenario: The limit warning says how to continue
- **WHEN** `/` links to `/p1` to `/p9`, and `spider crawl {site}/ --max-urls 3` ends
- **THEN** the result's `warnings` hold an entry with code `max_urls_reached` whose `hint` contains `--max-urls`

#### Scenario: The default limit is recorded
- **WHEN** `spider crawl {site}/` ends without `--max-urls`
- **THEN** the `crawl` table of `crawl.config` has `max_urls` = 10000

#### Scenario: Zero means no limit
- **WHEN** `/` links to `/p1` to `/p9`, and `spider crawl {site}/ --max-urls 0` runs
- **THEN** the result has `"state": "completed"` and `"fetched": 10` in `urls`

### Requirement: The urls table
The crawl store SHALL hold one row for each distinct normalised URL of the Crawl in a table `urls`, following the conventions of `015-add-crawl-store`. This change SHALL add the following columns, each in the slice whose scenario first needs it. Later changes add more columns and enumeration values.

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `id` | INTEGER, primary key | no | | Row id, stable for the life of the crawl file |
| `url` | TEXT, unique | no | | The normalised URL |
| `host` | TEXT | no | | The URL's host in lower-case ASCII (IDNA) form |
| `is_internal` | INTEGER | no | boolean | 1 for an Internal URL, 0 for an External URL |
| `in_scope` | INTEGER | no | boolean | 1 when the URL is inside the Scope, so it may be followed |
| `crawl_depth` | INTEGER | no | | Crawl Depth; 0 for Seeds |
| `discovered_via` | TEXT | no | `seed` and the Link types | How the URL was first found |
| `found_on_url_id` | INTEGER, references `urls.id` | yes | | The URL whose response first revealed this one; NULL for Seeds |
| `fetch_state` | TEXT | no | `queued`, `fetched`, `error`, `skipped` | Frontier state: waiting, a response was recorded, no response, or not requested |
| `skip_reason` | TEXT | yes | `excluded`, `blocked_by_robots`, `robots_unreachable`, `nofollow`, `link_type_not_followed`, `external_not_checked`, `max_depth` | Why a skipped URL was not requested |
| `blocked_by_robots` | INTEGER | yes | boolean | 1 when robots.txt disallows the URL for the robots user-agent token (also with `--ignore-robots`), 0 when it allows it; NULL when not checked |
| `status_code` | INTEGER | yes | | HTTP status code of the URL's own response; NULL without a response |
| `fetch_error` | TEXT | yes | `dns_error`, `connection_refused`, `connection_error`, `invalid_response` | Why no response was received |
| `fetch_error_message` | TEXT | yes | | Human-readable detail of `fetch_error` |
| `content_type` | TEXT | yes | | The `Content-Type` response header as received |
| `response_time_ms` | INTEGER | yes | | Time from sending the request to receiving the whole body |
| `fetched_at` | TEXT | yes | timestamp | UTC time of the request |
| `parsed` | INTEGER | no | boolean | 1 when the response was parsed for Links and Page data |
| `parse_error` | TEXT | yes | | Why a response that should have been parsed was not; starts with a code such as `extractor_error:` |

#### Scenario: A skipped URL has no response data
- **WHEN** `/` links to `/logout`, and `spider crawl {site}/ --exclude "/logout$"` runs
- **THEN** `{site}/logout` has `status_code`, `content_type`, `response_time_ms` and `fetched_at` all NULL, and `parsed` = 0

#### Scenario: Response timing is recorded
- **WHEN** `/` links to `/slow`, which answers after 500 ms
- **THEN** `{site}/slow` has a `response_time_ms` of at least 500 and a non-null `fetched_at`

#### Scenario: The Content-Type is recorded as received
- **WHEN** `/` links to `/doc.pdf`, which returns `Content-Type: application/pdf`
- **THEN** `{site}/doc.pdf` has `content_type` = `application/pdf`

### Requirement: The origins table
The crawl store SHALL hold one row per origin that the Crawl requested in a table `origins`. This change SHALL add these columns. `022-add-fetch-policy` adds `http_version`.

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `id` | INTEGER, primary key | no | | Row id |
| `origin` | TEXT, unique | no | | Scheme, host and port, for example `https://site.test`, with a default port left out |
| `host` | TEXT | no | | The origin's host in lower-case ASCII (IDNA) form |
| `is_internal` | INTEGER | no | boolean | 1 when the origin's URLs are Internal URLs |
| `robots_state` | TEXT | no | `ok`, `missing`, `unreachable` | Rules applied, everything allowed, or everything disallowed |
| `robots_status_code` | INTEGER | yes | | Status code of the final robots.txt response; NULL without a response |
| `robots_fetched_at` | TEXT | yes | timestamp | UTC time robots.txt was last fetched |
| `robots_txt` | TEXT | yes | | The robots.txt body as parsed, up to 512,000 bytes |
| `robots_crawl_delay_ms` | INTEGER | yes | | The `Crawl-delay` for the robots user-agent token; recorded, not applied |
| `robots_sitemaps` | TEXT | no | json | JSON array of the `Sitemap:` URLs in robots.txt |

#### Scenario: An External origin gets its own row
- **WHEN** `http://site.test/` links to `http://other.test/page`, and `spider crawl http://site.test/` runs
- **THEN** `origins` holds `http://site.test` with `is_internal` = 1 and `http://other.test` with `is_internal` = 0

### Requirement: Crawl metadata written by the engine
The Crawl SHALL fill the crawl metadata of `015-add-crawl-store`:
- `crawl.crawl_mode` (`spider` for this capability), `crawl.section_crawl`, `crawl.command_argv` (redacted by `015`) and `crawl.config`
- the `seeds` table
- the Crawl State in `crawl.state`: `running` while it works, then `completed`, `stopped` or `failed`

This change SHALL add three columns to `crawl`:
- `scope`: TEXT, `json`, the resolved Scope
- `stop_reason`: TEXT, nullable, with the values `max_urls`, `interrupt` and `requested`, set only for a `stopped` Crawl
- `warnings`: TEXT, `json`, a JSON array of diagnostics in the full shape of `010-add-workspace-and-cli-contract` (`{level, code, message, hint, details}`)

The `crawl` table of `crawl.config` SHALL hold every registered crawl setting, including those added by later changes, with secrets redacted by `015`.

#### Scenario: The recorded config holds every registered crawl setting
- **WHEN** `spider crawl {site}/` ends with no other flags and no `spider.toml`
- **THEN** the `crawl` table of `crawl.config` has exactly one key for each option of the `crawl` entry in `spider commands` whose `setting` starts with `crawl.`, and each value equals that option's `default`

#### Scenario: A completed Crawl records its state
- **WHEN** `spider crawl {site}/` ends after every URL is processed
- **THEN** `crawl.state` is `completed` and `crawl.stop_reason` is NULL

#### Scenario: Warnings are stored as diagnostics
- **WHEN** `/robots.txt` returns 503 on every attempt, and `spider crawl {site}/` ends
- **THEN** `crawl.warnings` holds an object whose keys are exactly `level`, `code`, `message`, `hint` and `details`, with `"level": "warning"` and `"code": "robots_unreachable"`

### Requirement: Crawl settings in spider.toml
Every crawl setting SHALL also be settable in the `[crawl]` table of `spider.toml`, under the naming rule of `010-add-workspace-and-cli-contract`: the flag's long name without the leading dashes, with `-` replaced by `_`. The Seed argument and `--subdomains` SHALL have no key, because `scope` covers `--subdomains`. `010`'s precedence SHALL apply: flag, then `spider.toml`, then the built-in default.

Secret settings SHALL be allowed in `spider.toml`. `015-add-crawl-store` redacts them in the recorded config.

#### Scenario: spider.toml sets a crawl setting
- **WHEN** `spider.toml` holds `[crawl]` with `concurrency = 2`, and `spider crawl {site}/` ends
- **THEN** the `crawl` table of `crawl.config` has `concurrency` = 2

#### Scenario: A flag overrides spider.toml
- **WHEN** `spider.toml` holds `[crawl]` with `concurrency = 2`, and `spider crawl {site}/ --concurrency 3` ends
- **THEN** the `crawl` table of `crawl.config` has `concurrency` = 3

### Requirement: Persistent frontier
The `urls` table SHALL be the Crawl's frontier:
- A URL SHALL be recorded as `fetched` or `error` only in the writer unit (`015-add-crawl-store`) that also records its response data and every URL discovered from it.
- URLs whose request has not completed SHALL stay `queued`.

The Crawl Service SHALL be able to continue a Crawl from its store. `spider resume` in `060-add-crawl-control` exposes this operation. Continuing SHALL:
1. put back into `queued` every URL that ended as `error` or with `skip_reason` = `robots_unreachable`
2. request only `queued` URLs
3. end with the same URLs as an uninterrupted Crawl

#### Scenario: A killed Crawl leaves no half-recorded Page
- **WHEN** a `spider crawl {site}/` subprocess on a 30-page fixture site is killed (SIGKILL, or TerminateProcess on Windows) after 10 pages are fetched
- **THEN** every URL that a Page with `parsed` = 1 links to has a row in the `urls` table

#### Scenario: Continuing a killed Crawl completes it
- **WHEN** a `spider crawl {site}/` subprocess on a 30-page fixture site is killed after 10 pages are fetched, and the Crawl Service continues the Crawl
- **THEN** the `urls` table holds the 30 fixture pages, each with `fetch_state` = `fetched` and `status_code` = 200

#### Scenario: Continuing does not request fetched URLs again
- **WHEN** a `spider crawl {site}/` subprocess on a 30-page fixture site is killed after 10 pages are fetched, and the Crawl Service continues the Crawl
- **THEN** the fixture site receives no request during the continuation for a page that had `fetch_state` = `fetched` before it

#### Scenario: A Crawl killed on Windows can be continued (Windows)
- **WHEN** a `spider crawl {site}/` subprocess on a 30-page fixture site is ended with TerminateProcess on Windows after 10 pages are fetched, and the Crawl Service continues the Crawl
- **THEN** the Crawl ends with the Crawl State `completed`

### Requirement: Per-response hook
The Crawl SHALL call every registered per-response handler exactly once for each URL that reaches a final `fetch_state` (`fetched`, `error` or `skipped`), inside the writer unit that records that state. A handler SHALL receive the URL's row values. For a `fetched` URL it SHALL also receive the status code, the response headers and, when the response was parsed, the extractor outputs. Rows written by a handler SHALL be committed in the same unit. Later changes register handlers: `030-add-page-data` for Page data and cookies, and `040-add-rules` for Rules on single URLs.

#### Scenario: A registered handler sees every URL once
- **WHEN** a handler registered for the test records the URLs and states it receives, `/` links to `/a`, `/missing` (which returns 404) and `/logout`, and `spider crawl {site}/ --exclude "/logout$"` runs
- **THEN** the handler has received exactly `({site}/, fetched)`, `({site}/a, fetched)`, `({site}/missing, fetched)` and `({site}/logout, skipped)`, once each

### Requirement: Post-crawl passes
The Crawl SHALL run every registered post-crawl pass when it ends as `completed` or `stopped`, after its last URL is recorded and before its final Crawl State is written. It SHALL NOT run them for a Crawl that ends as `failed`. A continued Crawl SHALL run them again when it ends, so a pass registered by a later change can run more than once for the same Crawl. `030-add-page-data` and `040-add-rules` register passes.

#### Scenario: Post-crawl passes run before a Crawl is completed
- **WHEN** a pass registered for the test records the Crawl State it sees, and `spider crawl {site}/` runs to its end
- **THEN** the pass has run once and saw the Crawl State `running`

#### Scenario: Post-crawl passes run when the URL limit stops a Crawl
- **WHEN** a pass registered for the test counts its runs, `/` links to `/p1` to `/p9`, and `spider crawl {site}/ --max-urls 3` runs
- **THEN** the pass has run once

#### Scenario: Post-crawl passes do not run for a failed Crawl
- **WHEN** a pass registered for the test counts its runs, and `spider crawl http://127.0.0.1:{closed_port}/` runs
- **THEN** the pass has run 0 times

#### Scenario: Post-crawl passes run again after a continue
- **WHEN** a pass registered for the test counts its runs, a Crawl stopped by `--max-urls 3` is continued through the Crawl Service, and the continuation ends
- **THEN** the pass has run twice

### Requirement: Parse failures do not stop the Crawl
When an extractor raises an error while a parsed response is processed, the URL SHALL be recorded with `parsed` = 0 and a `parse_error` that starts with `extractor_error:`, and the Crawl SHALL go on. In this change, extractors run in the crawl process; `026-add-parse-pool` moves them into worker processes.

#### Scenario: An extractor error is recorded
- **WHEN** an extractor registered for the test raises an error on `{site}/boom`, `/` links to `/boom` and `/ok`, and `spider crawl {site}/` runs
- **THEN** `{site}/boom` has `parsed` = 0 and a `parse_error` that starts with `extractor_error:`

#### Scenario: The Crawl continues after an extractor error
- **WHEN** an extractor registered for the test raises an error on `{site}/boom`, `/` links to `/boom` and `/ok`, and `spider crawl {site}/` runs
- **THEN** `{site}/ok` has `parsed` = 1

### Requirement: Progress events
While a foreground Crawl runs, the Command SHALL write progress events to stderr in the event shape of `010-add-workspace-and-cli-contract`: one JSON object per line, `{event, ts, data}`, encoded as UTF-8 and ending with LF on every OS. The events are:

| `event` | When | `data` |
|---|---|---|
| `crawl_started` | once, before any other event | `crawl_id`, `crawl_mode`, `seed_count`, `crawl_file` |
| `progress` | every 10 seconds | `crawl_id`, `elapsed_s`, `urls` (`discovered`, `fetched`, `errors`, `skipped`, `queued`), `rate` (URLs requested per second over the last 60 seconds) |
| `stopping` | when the Crawl starts to stop before its frontier is empty | `crawl_id`, `reason` (`interrupt`, `requested` or `max_urls`) |

A warning SHALL be written to stderr when it first occurs for a host, as a diagnostic line of `010`. It SHALL also be kept for the result and `crawl.warnings`.

#### Scenario: The first event line is the start event
- **WHEN** `spider crawl {site}/` runs
- **THEN** the first event line on stderr has `"event": "crawl_started"`

#### Scenario: Every stderr line is an event or a diagnostic
- **WHEN** `/robots.txt` returns 503 on every attempt, and `spider crawl {site}/` runs
- **THEN** every line on stderr parses as a JSON object that has either an `event` field or a `level` field

#### Scenario: A warning is written as a diagnostic
- **WHEN** `/robots.txt` returns 503 on every attempt, and `spider crawl {site}/` runs
- **THEN** stderr holds a line with `"level": "warning"` and `"code": "robots_unreachable"`

#### Scenario: Progress events come every 10 seconds
- **WHEN** a Crawl runs for 25 seconds of fake-clock time
- **THEN** exactly 2 `progress` events are written

#### Scenario: Events are UTF-8 on Windows (Windows)
- **WHEN** `spider crawl {site}/` runs as a subprocess on Windows with a Workspace whose path contains `Ü`
- **THEN** `data.crawl_file` of the `crawl_started` event, decoded from the UTF-8 bytes on stderr, contains `Ü`

### Requirement: Result of a Crawl
Whenever a foreground Crawl ends, whatever its Crawl State, the Command SHALL print one JSON object on stdout with these fields:
- `crawl_id`, `state`, `stop_reason`, `crawl_mode`, `seed` (the first Seed), `seed_count`, `section_crawl`
- `started_at`, `ended_at`, `duration_s`
- `urls`, with the counts `discovered`, `fetched`, `errors`, `skipped` and `queued`
- `pages`: the number of URLs with `parsed` = 1
- `status_classes`, with the counts `2xx`, `3xx`, `4xx`, `5xx` and `other`
- `crawl_file`
- `warnings`: diagnostics in the full shape

`spider commands` SHALL list the `crawl` Command with `"output": "document"`.

Exit codes follow `010-add-workspace-and-cli-contract`:
- 0 when the Crawl State is `completed`, or `stopped` with `stop_reason` `max_urls` or `requested`
- 130 when the Crawl is `stopped` by an interrupt
- 7 when the Crawl is `failed` because writing the crawl store failed (`crawl_write_failed`)
- 8 when the Crawl is `failed` because its Seed is unreachable (`seed_unreachable`)

For every non-zero exit, stderr SHALL hold exactly one error diagnostic, as its last line.

#### Scenario: The result counts a small site
- **WHEN** `/` links to `/a`, `/b` and `/missing` (which returns 404), and `spider crawl {site}/` ends
- **THEN** stdout holds `"state": "completed"`, `"urls": {"discovered": 4, "fetched": 4, "errors": 0, "skipped": 0, "queued": 0}`, `"pages": 3` and `"status_classes": {"2xx": 3, "3xx": 0, "4xx": 1, "5xx": 0, "other": 0}`

#### Scenario: A completed Crawl exits with code 0
- **WHEN** `spider crawl {site}/` ends with the Crawl State `completed`
- **THEN** the exit code is 0

#### Scenario: The crawl Command prints one document
- **WHEN** `spider commands` runs
- **THEN** its `crawl` entry has `"output": "document"`

#### Scenario: A write failure fails the Crawl
- **WHEN** the file system reports once that the disk is full while the Crawl writes (injected at the file-system boundary)
- **THEN** the Command exits with code 7, stdout holds the result with `"state": "failed"`, and the last stderr line is an error with `code` = `crawl_write_failed`

### Requirement: Unreachable Seed
When a Spider-mode Crawl gets no HTTP response at all from the Seed's origin, the Crawl SHALL end with the Crawl State `failed`, and it SHALL stay resumable. This covers both robots.txt and the Seed, and failures such as DNS, connection, TLS and timeout errors. The Command SHALL:
- print the result
- write exactly one error diagnostic, with code `seed_unreachable` and a hint that mentions network access and sandboxed agents
- exit with code 8

This lets an agent tell a site that is down, or a blocked network, from an empty site.

#### Scenario: An unreachable Seed fails the Crawl
- **WHEN** `spider crawl http://127.0.0.1:{closed_port}/` runs, and nothing listens on that port
- **THEN** the Command exits with code 8 and stdout holds the result with `"state": "failed"`

#### Scenario: An unreachable Seed is reported by one error
- **WHEN** `spider crawl http://127.0.0.1:{closed_port}/` runs, and nothing listens on that port
- **THEN** stderr holds exactly one error line, as its last line, with `code` = `seed_unreachable`

#### Scenario: A failed Crawl is continued once its Seed answers
- **WHEN** a Crawl of `http://127.0.0.1:{port}/` has failed because nothing listened, the fixture site then starts on that port, and the Crawl Service continues the Crawl
- **THEN** the Crawl ends with the Crawl State `completed`, and `http://127.0.0.1:{port}/` has `fetch_state` = `fetched`

### Requirement: Stopping with an interrupt
The first interrupt SHALL stop a foreground Crawl gracefully. An interrupt is Ctrl+C; on Windows also Ctrl+Break; on macOS and Linux also SIGTERM and SIGHUP. After the first interrupt, the Command SHALL:
1. write a `stopping` event and start no new request
2. give requests in flight up to 10 seconds
3. store everything received and run the post-crawl passes
4. end the Crawl with the Crawl State `stopped` and `stop_reason` = `interrupt`
5. print the result, write exactly one error diagnostic with code `interrupted`, and exit with code 130

URLs not completed SHALL stay `queued`, so the Crawl can be continued. A second interrupt SHALL end the process at once, and the Crawl SHALL still be continuable.

#### Scenario: Ctrl+C stops a Crawl on macOS and Linux
- **WHEN** SIGINT is sent to a `spider crawl {site}/` subprocess after 3 pages of a 30-page fixture site are fetched
- **THEN** it exits with code 130 and stdout holds `"state": "stopped"` and `"stop_reason": "interrupt"`

#### Scenario: Ctrl+Break stops a Crawl on Windows (Windows)
- **WHEN** CTRL_BREAK_EVENT is sent to a `spider crawl {site}/` subprocess started in a new process group, after 3 pages of a 30-page fixture site are fetched
- **THEN** it exits with code 130 and stdout holds `"state": "stopped"` and `"stop_reason": "interrupt"`

#### Scenario: An interrupt is reported by one error
- **WHEN** SIGINT (CTRL_BREAK_EVENT on Windows) stops a `spider crawl {site}/` subprocess
- **THEN** stderr holds exactly one error line, as its last line, with `code` = `interrupted`

#### Scenario: An interrupted Crawl keeps its queue
- **WHEN** a Crawl of a 30-page fixture site is stopped by an interrupt after 3 pages are fetched
- **THEN** the `urls` table has at least one row with `fetch_state` = `queued`

#### Scenario: A second interrupt ends the process at once
- **WHEN** a second interrupt follows the first while `/hang` (which answers after 60 seconds) is in flight
- **THEN** the subprocess exits within 2 seconds of the second interrupt, and `{site}/hang` has `fetch_state` = `queued`
