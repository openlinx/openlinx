## REMOVED Requirements

### Requirement: Crawl settings in spider.toml
**Reason**: renamed with the product, as `Crawl settings in openlinx.toml`.
**Migration**: none; the requirement is added again under its new name.

## MODIFIED Requirements

### Requirement: Spider mode

**In short:** `linx crawl <url>` crawls from one Seed in the foreground; a Seed without a scheme gets `https://`, and an invalid one is refused before any request.

`linx crawl <url>` SHALL start a Crawl in Spider mode with the URL as its only Seed, written to `seeds` as given (`015-add-crawl-store`). It SHALL follow Links from the Seed within the Scope, and run in the foreground until the Crawl ends. A Seed given without a scheme SHALL get `https://`. A Seed has a scheme when it starts with a scheme name (RFC 3986) and `:`, unless what follows the `:` is a port number (digits, then `/`, `?`, `#` or the end), as in `site.test:8080/shop`; so `mailto:a@b.test` names the scheme `mailto`, and `localhost:8080` names none. A Seed that is not a valid http or https URL SHALL be rejected with exit code 2 and error code `invalid_url` before any request is made, and no Crawl SHALL be created.

#### Scenario: The Seed is fetched and recorded
- **WHEN** `/` returns 200 with an HTML page, and `linx crawl {site}/` runs
- **THEN** the `urls` row for `{site}/` has `host` = `127.0.0.1`, `fetch_state` = `fetched`, `status_code` = 200, `crawl_depth` = 0 and `discovered_via` = `seed`

#### Scenario: The Seed is kept as given in seeds
- **WHEN** `linx crawl {site}` runs, without a trailing slash
- **THEN** the `seeds` table holds exactly the row `(1, "{site}")`, while the `urls` row is for `{site}/`

#### Scenario: Pages linked from the Seed are crawled
- **WHEN** `/` links to `/about`, `/about` links to `/team`, and `linx crawl {site}/` runs
- **THEN** the Crawl's `urls` table holds exactly `{site}/`, `{site}/about` and `{site}/team`, each with `fetch_state` = `fetched` and `status_code` = 200

#### Scenario: A bare host becomes an https Seed
- **WHEN** the Seed argument `site.test/shop` is parsed
- **THEN** the Seed is `https://site.test/shop`

#### Scenario: An invalid Seed is rejected
- **WHEN** `linx crawl "http://exa mple.test/"` runs
- **THEN** the Command exits with code 2 and its only stderr error has `code` = `invalid_url`
- **AND** the Workspace holds no new crawl file

### Requirement: Stripping query parameters

**In short:** query parameters are kept unless `--strip-params` names them, and those are removed before a URL is recorded.

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
- **WHEN** `/` links to `/p?utm_source=a` and `/p?utm_source=b`, and `linx crawl {site}/ --strip-params "utm_*"` runs
- **THEN** the fixture site receives exactly one request for `/p`

### Requirement: Seed host mismatch

**In short:** a `www.` Seed whose Page names the apex, which is outside the Scope, gives one `seed_base_mismatch` warning, and the Scope stays.

When the Seed's host is `www.` followed by a registrable domain, the Seed's parsed response names the apex (that registrable domain itself) as the site, and the Seed on the apex host is outside the Scope, the Crawl SHALL record one `seed_base_mismatch` warning, whose hint gives the Seed on the apex host. The response's first `canonical` Link to the apex or to the Seed's host decides: one to the apex names the apex, and one to the Seed's host names no apex. Without such a Link, the response names the apex when more of its `hyperlink` Links target the apex than the Seed's host. The Crawl SHALL go on in its Scope.

#### Scenario: A www Seed whose canonical names the apex is reported
- **WHEN** `http://www.site.test/` holds `<link rel="canonical" href="http://site.test/">`, and `linx crawl http://www.site.test/` runs
- **THEN** the result's `warnings` hold an entry with code `seed_base_mismatch` whose `hint` contains `http://site.test/`

#### Scenario: A www Seed whose Links stay on www is not reported
- **WHEN** `http://www.site.test/` links to `http://www.site.test/a` and `http://www.site.test/b`, and `linx crawl http://www.site.test/` runs
- **THEN** the result's `warnings` hold no entry with code `seed_base_mismatch`

### Requirement: Scope option

**In short:** `--scope` is `host`, `subdomains` or `subfolder`; `--subdomains` is its shorthand and conflicts with any other value.

`--scope` SHALL accept `host` (the default), `subdomains` or `subfolder`. `--subdomains` SHALL mean the same as `--scope subdomains`. Combining `--subdomains` with another `--scope` value SHALL be rejected with exit code 2 and error code `option_conflict`.

#### Scenario: The subdomains shorthand conflicts with a subfolder Scope
- **WHEN** `linx crawl {site}/blog/ --subdomains --scope subfolder` runs
- **THEN** the Command exits with code 2 and its only stderr error has `code` = `option_conflict`

### Requirement: Subfolder Scope

**In short:** under `--scope subfolder` only the Seed's folder is in the Scope, and a Seed whose folder is the root is refused.

With `--scope subfolder`, only Internal URLs whose path starts with the Seed's folder SHALL be in the Scope. The folder SHALL be the Seed's path up to and including its last `/`. A Seed whose folder would be `/` SHALL be rejected with exit code 2 and error code `subfolder_is_root`, with a hint that gives the Seed with a trailing `/`.

#### Scenario: The folder of a Seed page is its parent folder
- **WHEN** the Scope of Seed `http://site.test/blog/post-1` with `--scope subfolder` is resolved
- **THEN** its folder is `/blog/`

#### Scenario: Pages inside the folder are followed
- **WHEN** `/blog/` links to `/blog/post`, and `linx crawl {site}/blog/ --scope subfolder` runs
- **THEN** `{site}/blog/post` has `in_scope` = 1 and `parsed` = 1

#### Scenario: Pages outside the folder are checked but not followed
- **WHEN** `/blog/` links to `/shop/`, `/shop/` links to `/shop/item`, and `linx crawl {site}/blog/ --scope subfolder` runs
- **THEN** `{site}/shop/` has `fetch_state` = `fetched` and `parsed` = 0
- **AND** the `urls` table holds no row for `{site}/shop/item`

#### Scenario: A Seed without its trailing slash is rejected
- **WHEN** `linx crawl {site}/blog --scope subfolder` runs
- **THEN** the Command exits with code 2, and its only stderr error has `code` = `subfolder_is_root` and a `hint` that contains `{site}/blog/`

### Requirement: Include and exclude patterns

**In short:** an excluded URL is never requested, an Internal URL that no include pattern matches is outside the Scope, and an invalid pattern or a Seed outside its own Scope is refused.

`--include <regex>` and `--exclude <regex>` SHALL take Python regular expressions, and each flag SHALL be accepted more than once. Each pattern SHALL be searched for anywhere in the normalised URL, case-sensitively.
- **Exclude:** a URL that matches an `--exclude` pattern SHALL NOT be requested. It SHALL be recorded with `fetch_state` = `skipped`, `skip_reason` = `excluded` and `in_scope` = 0, unless only Links that are not followed reach it, which record it as `nofollow` or `link_type_not_followed` (see "Nofollow" and "Link discovery").
- **Include:** when at least one `--include` pattern is given, an Internal URL that matches none of them SHALL be outside the Scope.
- **Errors:**
  - An invalid pattern SHALL be rejected with exit code 2 and error code `invalid_pattern`.
  - A Seed outside the Scope SHALL be rejected with exit code 2 and error code `seed_out_of_scope`.

#### Scenario: An excluded URL is never requested
- **WHEN** `/` links to `/logout`, and `linx crawl {site}/ --exclude "/logout$"` runs
- **THEN** the fixture site receives no request for `/logout`

#### Scenario: An excluded URL is recorded as skipped
- **WHEN** `/` links to `/logout`, and `linx crawl {site}/ --exclude "/logout$"` runs
- **THEN** `{site}/logout` has `fetch_state` = `skipped` and `skip_reason` = `excluded`

#### Scenario: A URL that matches no include pattern is checked but not followed
- **WHEN** `/blog/` links to `/news/n`, and `linx crawl {site}/blog/ --include "/blog/"` runs
- **THEN** `{site}/news/n` has `fetch_state` = `fetched`, `in_scope` = 0 and `parsed` = 0

#### Scenario: Exclude wins over include
- **WHEN** the Scope of Seed `http://site.test/blog/` with `--include "/blog/"` and `--exclude "draft"` decides on `http://site.test/blog/draft-1`
- **THEN** the decision is to skip it with `skip_reason` = `excluded`

#### Scenario: An invalid pattern is rejected
- **WHEN** `linx crawl {site}/ --include "("` runs
- **THEN** the Command exits with code 2 and its only stderr error has `code` = `invalid_pattern`

#### Scenario: A Seed outside the Scope is rejected
- **WHEN** `linx crawl http://site.test/ --exclude "site"` runs
- **THEN** the Command exits with code 2 and its only stderr error has `code` = `seed_out_of_scope`

### Requirement: Section Crawl

**In short:** a subfolder Scope or an include pattern makes a Section Crawl, recorded in `crawl.section_crawl` and the result.

A Crawl SHALL be a Section Crawl when it uses `--scope subfolder` or at least one `--include` pattern. The Crawl SHALL set `crawl.section_crawl` (`015-add-crawl-store`) to 1 for a Section Crawl and to 0 otherwise. The result SHALL report it as `"section_crawl": true` or `false`. `--exclude` alone SHALL NOT make a Crawl a Section Crawl.

#### Scenario: A subfolder Crawl is a Section Crawl
- **WHEN** `linx crawl {site}/blog/ --scope subfolder` ends
- **THEN** the result has `"section_crawl": true`

#### Scenario: An include pattern makes a Section Crawl
- **WHEN** `linx crawl {site}/blog/ --include "/blog/"` ends
- **THEN** `crawl.section_crawl` is 1

#### Scenario: Exclude patterns alone do not make a Section Crawl
- **WHEN** `linx crawl {site}/ --exclude "/tag/"` ends
- **THEN** the result has `"section_crawl": false`

### Requirement: Recorded Scope

**In short:** the resolved Scope is stored in `crawl.scope` when the Crawl is created.

The Crawl SHALL record the resolved Scope in the column `crawl.scope`, which this change adds as TEXT in the `json` format and writes when the Crawl is created, as the object `{mode, hosts, folder, include, exclude}`:
- `hosts` lists the Seed hosts in the order above, or the registrable domains with `--scope subdomains`, or the Seed host when it has none (an IP address or a single label).
- `folder` is null unless the Scope is `subfolder`.

#### Scenario: A subfolder Scope is recorded
- **WHEN** `linx crawl http://site.test/blog/ --scope subfolder --exclude "/draft"` ends and `http://site.test/blog/` returns 200
- **THEN** `crawl.scope` is `{"mode": "subfolder", "hosts": ["site.test", "www.site.test"], "folder": "/blog/", "include": [], "exclude": ["/draft"]}`

### Requirement: Link discovery

**In short:** every parsed response, and the `Link` and `Refresh` headers of every in-Scope 2xx response, give typed Links resolved as a browser resolves them, and a Page records each URL it links to once.

The Crawl SHALL discover Links in every response it parses, and in the HTTP `Link` and `Refresh` headers of every in-Scope 2xx response.
- **Resolution:** it SHALL resolve each relative reference as the URL Standard does (a backslash counts as a slash), against the Page's `<base href>` when there is one, and otherwise against the response URL. A `<base href>` that is not http or https SHALL resolve no relative reference. On a Page decoded as neither UTF-8 nor UTF-16, a reference's query SHALL be percent-encoded in the Page's encoding, as browsers send it. It SHALL then normalise the result, and SHALL ignore references whose scheme is not http or https, and references that cannot be resolved or normalised. An empty `src`, `data` or `poster` SHALL give no Link, while an empty `href` links to the Page itself, and a `Link` header value with an `anchor` parameter SHALL give no Link, since it describes another resource.
- **Link types:** each discovered Link SHALL have one of these Link types, and its target SHALL be requested by default as shown:

| Link type | Found in | Requested by default |
|---|---|---|
| `hyperlink` | `<a href>`, `<area href>` | yes |
| `canonical` | `<link rel="canonical">`; an HTTP `Link` header with `rel="canonical"` | yes |
| `pagination` | `<link rel="next">`, `<link rel="prev">`, `<link rel="previous">`; an HTTP `Link` header with `rel` `next`, `prev` or `previous` | yes |
| `hreflang` | `<link rel="alternate" hreflang>`; an HTTP `Link` header with `rel="alternate"` and `hreflang` | yes |
| `iframe` | `<iframe src>`, `<frame src>` | yes |
| `meta_refresh` | the URL in `<meta http-equiv="refresh" content="…; url=…">` | yes |
| `http_refresh` | the URL in an HTTP `Refresh` header (`…; url=…`) | yes |
| `image` | `<img src>`; every candidate in the `srcset` of `<img>` and `<source>`; `<video poster>` | yes, as a Resource |
| `css` | `<link rel="stylesheet" href>` | yes, as a Resource |
| `javascript` | `<script src>` | yes, as a Resource |
| `video` | `<video src>`; the `src` of a `<source>` or `<track>` inside `<video>` | yes, as a Resource |
| `audio` | `<audio src>`; the `src` of a `<source>` or `<track>` inside `<audio>` | yes, as a Resource |
| `media` | `<embed src>`, `<object data>` | yes, as a Resource |
| `amphtml` | `<link rel="amphtml">` | no |
| `mobile_alternate` | `<link rel="alternate" media>` without `hreflang` | no |
| `misc` | `<link href>` with any other `rel`, such as `icon`, `manifest`, `preload`, or `alternate` without `hreflang` or `media` (a feed); never `preconnect` or `dns-prefetch`, which name an origin, not a file | no |

- **Later Link types:** the Link type enumeration SHALL also list, from v0.1, the types that later releases discover: `xml_sitemap` (a URL listed in an XML sitemap) and `sitemap_hreflang` (an hreflang alternate in a sitemap), both from `024-add-list-and-sitemap-modes` (v0.2), and `javascript_redirect` (v1.1, with JavaScript rendering).

- **`<noscript>`:** a `<link>` or `<meta>` element inside `<noscript>` SHALL give no Link, since a browser that runs scripts reads the content of `<noscript>` as text; the other elements inside `<noscript>` SHALL give their Links as anywhere else, since a crawler without rendering finds every URL the raw HTML holds. A `<noscript>` in SVG or MathML content, outside an HTML integration point, SHALL give the Links of its child elements other than `<link>` and `<meta>` once, and its text SHALL give no Link.
- **Link types that are not requested:** a URL reached only through them SHALL be recorded with `fetch_state` = `skipped` and `skip_reason` = `link_type_not_followed`.
- **One row per URL of a Page:** a Page SHALL record each URL it links to once. The URL SHALL be followed when any of its Links on the Page is. Its `discovered_via` SHALL be the type of its first Resource Link on the Page, else of its first followed Link, else of its first Link. A URL that none of them follows SHALL have the `skip_reason` of its first Link.
- **Templates:** the content of a Page's own `<template>` element SHALL give no Link.
- **Provenance:** a URL's `discovered_via` SHALL say how it was found, `seed` or a Link type, and `found_on_url_id` SHALL point to the URL whose response gave that Link: the first Link that reached it, except as the rules below say. For a URL reached through a Link that is not followed and later through one that is, its `discovered_via`, `found_on_url_id` and `crawl_depth` SHALL come from the first Page that follows it. A Resource Link SHALL raise a URL that a Link of another type reached first, while the URL is `queued` or skipped as `max_depth`, when it reaches it at the same or a shorter depth: the URL's `discovered_via`, `found_on_url_id` and `crawl_depth` then come from the Resource Link, and a skipped one is queued again. A Link of any type that reaches a URL still `queued`, or skipped as `max_depth`, at a shorter depth SHALL give it that Link's `discovered_via`, `found_on_url_id` and `crawl_depth`. Later changes find URLs in other ways, with values listed from v0.1 (see "The urls table"); a URL listed in a sitemap has the Link type `xml_sitemap`.

#### Scenario: A relative link is resolved against the base href
- **WHEN** the Links of `http://site.test/` are extracted from `<base href="http://site.test/docs/"><a href="guide">Guide</a>`
- **THEN** exactly one Link is found: a `hyperlink` to `http://site.test/docs/guide`

#### Scenario: Every srcset candidate is an image Link
- **WHEN** the Links of `http://site.test/` are extracted from `<img src="/a.png" srcset="/a-2x.png 2x, /a-3x.png 3x">`
- **THEN** exactly three `image` Links are found, to `http://site.test/a.png`, `http://site.test/a-2x.png` and `http://site.test/a-3x.png`

#### Scenario: rel previous is a pagination Link
- **WHEN** the Links of `http://site.test/p2` are extracted from `<link rel="previous" href="/p1">`
- **THEN** exactly one Link is found: a `pagination` Link to `http://site.test/p1`

#### Scenario: Video and audio sources are video and audio Links
- **WHEN** the Links of `http://site.test/` are extracted from `<video src="/v.mp4"><track src="/v.vtt"></video><audio><source src="/a.mp3"></audio>`
- **THEN** exactly three Links are found: `video` Links to `http://site.test/v.mp4` and `http://site.test/v.vtt`, and an `audio` Link to `http://site.test/a.mp3`

#### Scenario: A link element of another rel is a misc Link
- **WHEN** the Links of `http://site.test/` are extracted from `<link rel="icon" href="/favicon.ico"><link rel="preconnect" href="https://cdn.site.test">`
- **THEN** exactly one Link is found: a `misc` Link to `http://site.test/favicon.ico`

#### Scenario: References that are not http or https are ignored
- **WHEN** the Links of `http://site.test/` are extracted from `<a href="mailto:hi@site.test">Mail</a><a href="javascript:void(0)">Menu</a>`
- **THEN** no URL to request is found

#### Scenario: A malformed reference is ignored
- **WHEN** the Links of `http://site.test/` are extracted from `<a href="http://[bad/x">Bad</a><a href="/ok">OK</a>`
- **THEN** exactly one Link is found: a `hyperlink` to `http://site.test/ok`

#### Scenario: A discovered URL points to where it was found
- **WHEN** `/` links to `/about`, and `linx crawl {site}/` runs
- **THEN** `{site}/about` has `discovered_via` = `hyperlink` and a `found_on_url_id` pointing to `{site}/`

#### Scenario: A canonical in an HTTP header is followed
- **WHEN** `/` links to `/doc.pdf`, which returns `Content-Type: application/pdf` and `Link: <{site}/doc>; rel="canonical"`
- **THEN** `{site}/doc` has `fetch_state` = `fetched` and `discovered_via` = `canonical`

#### Scenario: An HTTP Refresh target is followed
- **WHEN** `/` links to `/old`, which returns 200 with the header `Refresh: 0; url=/new`
- **THEN** `{site}/new` has `fetch_state` = `fetched` and `discovered_via` = `http_refresh`

#### Scenario: amphtml targets are not requested
- **WHEN** `/` holds `<link rel="amphtml" href="/amp/">`, and `linx crawl {site}/` runs
- **THEN** `{site}/amp/` has `fetch_state` = `skipped` and `skip_reason` = `link_type_not_followed`

#### Scenario: A meta refresh target is followed
- **WHEN** `/` links to `/old`, which holds `<meta http-equiv="refresh" content="0; url=/new">`
- **THEN** `{site}/new` has `fetch_state` = `fetched` and `discovered_via` = `meta_refresh`

### Requirement: Nofollow

**In short:** a nofollow hyperlink, and every hyperlink of a nofollow Page, is not requested unless a followed Link also reaches its target or `--follow-nofollow` is given.

The following SHALL NOT be requested unless the same target is also reached through a Link that is followed:
- a `hyperlink` whose `rel` attribute contains the token `nofollow`
- every `hyperlink` on a Page whose robots directives give `meta_robots_nofollow` or `x_robots_tag_nofollow`

Such a target SHALL be recorded with `fetch_state` = `skipped` and `skip_reason` = `nofollow`. With `--follow-nofollow`, these Links SHALL be treated like any other `hyperlink`.

#### Scenario: A nofollow link is not requested
- **WHEN** `/` holds `<a rel="nofollow" href="/private">`, and `linx crawl {site}/` runs
- **THEN** `{site}/private` has `fetch_state` = `skipped` and `skip_reason` = `nofollow`

#### Scenario: A page-level nofollow applies to every hyperlink
- **WHEN** `/` holds `<meta name="robots" content="noindex, nofollow">` and `<a href="/x">`, and `linx crawl {site}/` runs
- **THEN** `{site}/x` has `skip_reason` = `nofollow`

#### Scenario: A nofollow target reached through a followed Link is fetched
- **WHEN** `/` links to `/p` with `rel="nofollow"` and to `/about`, and `/about` links to `/p` without `rel`
- **THEN** `{site}/p` has `fetch_state` = `fetched`

#### Scenario: Nofollow Links are followed on request
- **WHEN** `/` holds `<a rel="nofollow" href="/private">`, and `linx crawl {site}/ --follow-nofollow` runs
- **THEN** `{site}/private` has `fetch_state` = `fetched`

### Requirement: External URLs are checked, not followed

**In short:** an External URL is requested once and never parsed, or not requested with `--no-check-external`.

An External URL reached through a Link type that is requested SHALL be requested once to record its response, and SHALL NOT be parsed. With `--no-check-external`, External URLs SHALL NOT be requested, and SHALL be recorded with `fetch_state` = `skipped` and `skip_reason` = `external_not_checked`.

#### Scenario: An External URL is checked
- **WHEN** `http://site.test/` links to `http://other.test/page`, which links to `http://other.test/deeper`, and `linx crawl http://site.test/` runs
- **THEN** `http://other.test/page` has `fetch_state` = `fetched` and `parsed` = 0
- **AND** the `urls` table holds no row for `http://other.test/deeper`

#### Scenario: External URLs can be left unchecked
- **WHEN** `http://site.test/` links to `http://other.test/page`, and `linx crawl http://site.test/ --no-check-external` runs
- **THEN** the `other.test` fixture instance receives no request

### Requirement: Resources are requested, not parsed

**In short:** a Resource of a followed Page is requested, beyond `--max-depth` too, and parsed only when it is HTML.

URLs reached through `image`, `css`, `javascript`, `video`, `audio` or `media` Links SHALL be requested whenever the Page that references them is followed, even when their Crawl Depth exceeds `--max-depth`. A response that is not HTML SHALL NOT be parsed. `022-add-fetch-policy` adds their size measurements.

#### Scenario: An image is checked but not parsed
- **WHEN** `/` holds `<img src="/logo.png">`, and `/logo.png` returns 200 with an `image/png` body
- **THEN** `{site}/logo.png` has `status_code` = 200 and `parsed` = 0

#### Scenario: A broken image is recorded
- **WHEN** `/` holds `<img src="/missing.png">`, and `/missing.png` returns 404
- **THEN** `{site}/missing.png` has `status_code` = 404

#### Scenario: Resources are checked beyond the depth limit
- **WHEN** `/` holds `<img src="/logo.png">` and `<a href="/about">`, and `linx crawl {site}/ --max-depth 0` runs
- **THEN** `{site}/logo.png` has `fetch_state` = `fetched`

#### Scenario: An image skipped beyond the depth limit is checked once a Page shows it
- **WHEN** `/` holds `<img src="/late.html">` and `<a href="/a">`, `/a` holds `<a href="/photo.jpg">`, `/late.html` holds `<img src="/photo.jpg">` and answers after `/photo.jpg` was skipped, and `linx crawl {site}/ --max-depth 1` runs
- **THEN** `{site}/photo.jpg` has `fetch_state` = `fetched` and `discovered_via` = `image`

#### Scenario: An image that another Page hyperlinked first is checked beyond the depth limit
- **WHEN** `/` links to `/a` and `/b`, `/a` holds `<a href="/photo.jpg">` and `/b` holds `<img src="/photo.jpg">`, and `linx crawl {site}/ --max-depth 1` runs
- **THEN** `{site}/photo.jpg` has `fetch_state` = `fetched` and `discovered_via` = `image`

### Requirement: robots.txt is obeyed by default

**In short:** each origin's robots.txt is fetched once per run before its first URL, and the URLs it disallows are not requested.

Before its first request to an origin (a scheme, host and port), the Crawl SHALL fetch that origin's `/robots.txt`, once per origin in each run. It SHALL NOT request URLs that robots.txt disallows for the robots user-agent token.
- **Blocked URLs** SHALL be recorded with `fetch_state` = `skipped`, `skip_reason` = `blocked_by_robots_txt` and `blocked_by_robots_txt` = 1. Requested URLs SHALL have `blocked_by_robots_txt` = 0, and URLs not checked against robots.txt SHALL have NULL.
- **Every origin:** this SHALL apply to every origin, including the origins of External URLs and Resources.
- **robots.txt requests** SHALL NOT be recorded as URLs and SHALL NOT count toward `--max-urls`.
- **Crawl-delay:** the `Crawl-delay` directive SHALL be recorded but not applied.
- **A blocked Seed** SHALL produce a `seed_blocked_by_robots_txt` warning whose hint contains `--ignore-robots`, unless `--ignore-robots` is given.

#### Scenario: A disallowed URL is not requested
- **WHEN** `/robots.txt` is `User-agent: *` LF `Disallow: /private/`, `/` links to `/private/a`, and `linx crawl {site}/` runs
- **THEN** the fixture site receives no request for `/private/a`

#### Scenario: A disallowed URL is recorded as blocked
- **WHEN** `/robots.txt` is `User-agent: *` LF `Disallow: /private/`, `/` links to `/private/a`, and `linx crawl {site}/` runs
- **THEN** `{site}/private/a` has `skip_reason` = `blocked_by_robots_txt` and `blocked_by_robots_txt` = 1

#### Scenario: robots.txt is fetched once per origin
- **WHEN** `/` links to `/p1` to `/p9`, and `linx crawl {site}/` runs
- **THEN** the fixture site receives exactly one request for `/robots.txt`

#### Scenario: robots.txt is stored with its origin
- **WHEN** `/robots.txt` is `User-agent: *` LF `Crawl-delay: 5` LF `Disallow: /private/` LF `Sitemap: {site}/sitemap.xml`, and `linx crawl {site}/` runs
- **THEN** the `origins` row for `{site}` has `robots_state` = `ok`, `robots_status_code` = 200, `robots_txt` equal to the served text, `robots_crawl_delay_ms` = 5000, `robots_sitemaps` = `["{site}/sitemap.xml"]` and a non-null `robots_fetched_at`

#### Scenario: Crawl-delay is not applied
- **WHEN** a fake Fetcher serves a robots.txt with `Crawl-delay: 30` and three linked pages on one host, and the Crawl runs with a fake clock
- **THEN** all four page requests start before 1 second of clock time has passed

#### Scenario: A blocked Seed is reported
- **WHEN** `/robots.txt` is `User-agent: *` LF `Disallow: /`, and `linx crawl {site}/` runs
- **THEN** the result's `warnings` hold an entry with code `seed_blocked_by_robots_txt` whose `hint` contains `--ignore-robots`

### Requirement: Ignoring robots.txt

**In short:** `--ignore-robots` requests the URLs robots.txt disallows and still labels them blocked.

With `--ignore-robots`, the Crawl SHALL request URLs that robots.txt disallows, and SHALL still record `blocked_by_robots_txt` = 1 for them. The URLs of an origin whose robots.txt is `unreachable` with an HTTP response SHALL be requested with `blocked_by_robots_txt` NULL, and an Internal origin SHALL still give the `robots_unreachable` warning, saying that its URLs were requested without rules.

#### Scenario: Disallowed URLs are crawled and still labelled
- **WHEN** `/robots.txt` disallows `/private/`, `/` links to `/private/a`, and `linx crawl {site}/ --ignore-robots` runs
- **THEN** `{site}/private/a` has `fetch_state` = `fetched` and `blocked_by_robots_txt` = 1

#### Scenario: An unreachable robots.txt is reported under --ignore-robots
- **WHEN** `/robots.txt` returns 503, and `linx crawl {site}/ --ignore-robots` runs
- **THEN** `{site}/` has `fetch_state` = `fetched` and `blocked_by_robots_txt` NULL, and the result's `warnings` hold one `robots_unreachable`

### Requirement: robots.txt fetch outcomes

**In short:** robots.txt's response decides as RFC 9309 says: 2xx applies its rules, 4xx and a failed redirect allow everything, 5xx and 429 disallow everything, and no response makes each URL of the origin an error.

The Crawl SHALL treat an origin's robots.txt by its response, as RFC 9309 describes:
- **2xx:** its rules apply and `robots_state` = `ok`. Only its first 512,000 bytes SHALL be parsed, without a line that this limit cuts.
- **4xx other than 429:** every URL on the origin is allowed, and `robots_state` = `missing`.
- **A final 3xx**, one not followed as a redirect, such as 304: as 4xx, `robots_state` = `missing`.
- **5xx (500 to 599), 429, or a status outside 200 to 599** (a 1xx final response, 600 or more): every URL on the origin is disallowed, and `robots_state` = `unreachable`. A status no HTTP server should send says the server is broken, so it is treated as cautiously as 5xx.
  - Its URLs SHALL be recorded with `skip_reason` = `robots_unreachable`.
  - For an Internal origin, a `robots_unreachable` warning SHALL be recorded once per host, whose hint contains `--ignore-robots`, unless it was given (see "Ignoring robots.txt").
- **No HTTP response** (any `fetch_error` of "Requests without a response"): `robots_state` = `unreachable`, `robots_status_code` is NULL, and `robots_fetch_error` and `robots_fetch_error_message` hold the request's error.
  - Every URL on the origin SHALL be recorded with `fetch_state` = `error` and the `fetch_error` of the robots.txt request, without a request of its own, and with a `fetch_error_message` that says the error came from the origin's robots.txt request. A continue re-queues them with the other `error` URLs.
  - On an Internal origin, each such URL SHALL count toward the network pause as a request without an HTTP response (see "Backstops").
  - The Seed's origin is the exception: until it has given an HTTP response, its robots.txt request without one pauses the Crawl (see "Unreachable Seed").
- **Redirects:** the robots.txt request SHALL follow up to 5 redirect hops. A longer chain SHALL be treated as `missing`.
  - A redirect hop that gets no HTTP response SHALL be treated as `missing` too: every URL on the origin is allowed, `robots_status_code` holds the last status received, and `robots_fetch_error` and `robots_fetch_error_message` hold the hop's error.
  - For an Internal origin, a `robots_redirect_failed` warning SHALL be recorded, once per origin.

#### Scenario: A missing robots.txt allows everything
- **WHEN** `/robots.txt` returns 404, and `linx crawl {site}/` runs
- **THEN** `{site}/` has `fetch_state` = `fetched` and the `origins` row for `{site}` has `robots_state` = `missing`

#### Scenario: An unreachable robots.txt blocks its origin
- **WHEN** `/robots.txt` returns 503 on every attempt, and `linx crawl {site}/` runs
- **THEN** `{site}/` has `skip_reason` = `robots_unreachable`

#### Scenario: An unreachable robots.txt of the site is reported
- **WHEN** `/robots.txt` returns 503 on every attempt, and `linx crawl {site}/` runs
- **THEN** the result's `warnings` hold an entry with code `robots_unreachable` whose `hint` contains `--ignore-robots`

#### Scenario: A dead External domain is a DNS error
- **WHEN** `http://site.test/` links to `http://nowhere.test/a` and `http://nowhere.test/b`, and `linx crawl http://site.test/` runs
- **THEN** both URLs have `fetch_state` = `error`, `fetch_error` = `dns_error` and a `fetch_error_message` that contains `robots.txt`, and the `origins` row for `http://nowhere.test` has `robots_state` = `unreachable`, `robots_status_code` NULL and `robots_fetch_error` = `dns_error`

#### Scenario: A redirected robots.txt is followed
- **WHEN** `/robots.txt` redirects with 301 to `/robots-real.txt`, which disallows `/private/`, and `/` links to `/private/a`
- **THEN** `{site}/private/a` has `skip_reason` = `blocked_by_robots_txt`

#### Scenario: A robots.txt redirect to a host that does not resolve counts as missing
- **WHEN** `/robots.txt` redirects with 301 to `http://nowhere.test/robots.txt`, a host that does not resolve, `/` links to `/a`, and `linx crawl {site}/` runs
- **THEN** `{site}/a` has `fetch_state` = `fetched`, the `origins` row for `{site}` has `robots_state` = `missing`, `robots_status_code` = 301 and `robots_fetch_error` = `dns_error`, and the result's `warnings` hold one `robots_redirect_failed`

#### Scenario: More than five robots.txt redirects count as missing
- **WHEN** `/robots.txt` starts a chain of 6 redirects, and `linx crawl {site}/` runs
- **THEN** the `origins` row for `{site}` has `robots_state` = `missing`

### Requirement: Robots user-agent token

**In short:** robots.txt groups and prefixed directives match the token `openlinx`, or the one `--robots-user-agent` gives, which must match RFC 9309.

The Crawl SHALL select robots.txt groups, and user-agent-prefixed robots directives, with the token `openlinx` by default, or with the token given in `--robots-user-agent <token>`. The token is independent of the `User-Agent` request header. A token SHALL match RFC 9309's `[a-zA-Z_-]+`; any other value SHALL be rejected: as `--robots-user-agent` with exit code 2 and error code `invalid_value`, and in `openlinx.toml` with exit code 3 and `settings_invalid`, as any invalid setting is.

#### Scenario: The group for the tool's token applies
- **WHEN** the robots rules `User-agent: openlinx` LF `Disallow: /a` LF LF `User-agent: *` LF `Disallow: /b` are applied with the default token
- **THEN** `http://site.test/a` is disallowed and `http://site.test/b` is allowed

#### Scenario: Another token can be chosen
- **WHEN** the robots rules `User-agent: Googlebot` LF `Disallow: /g` are applied with `--robots-user-agent Googlebot`
- **THEN** `http://site.test/g` is disallowed

### Requirement: Per-host concurrency

**In short:** at most `--concurrency` requests (default 5) are in flight to one host, and 4 times that over all hosts, kept within 20 to 100.

The Crawl SHALL never have more than `--concurrency` requests in flight to one host. The default SHALL be 5. Over all hosts together, it SHALL never have more than 4 × `--concurrency` requests in flight, kept within 20 to 100. A value outside 1 to 50 SHALL be rejected: as `--concurrency` with exit code 2 and error code `invalid_value`, and in `openlinx.toml` with exit code 3 and `settings_invalid`, as any invalid setting is.

#### Scenario: At most five requests to a host by default
- **WHEN** `/` links to `/slow/1` to `/slow/20`, each answering after 500 ms, and `linx crawl {site}/` runs
- **THEN** the highest number of simultaneous requests the fixture site records is 5

#### Scenario: A lower concurrency is honoured
- **WHEN** `/` links to `/slow/1` to `/slow/20`, each answering after 500 ms, and `linx crawl {site}/ --concurrency 2` runs
- **THEN** the highest number of simultaneous requests the fixture site records is 2

#### Scenario: The global cap bounds requests across hosts
- **WHEN** `/` links to one Page on each of 30 External hosts, each answering after 1 second, and `linx crawl {site}/` runs with the default `--concurrency` 5
- **THEN** no more than 20 requests are in flight at once, and the 30 Pages are requested

#### Scenario: A concurrency of zero is rejected
- **WHEN** `linx crawl {site}/ --concurrency 0` runs
- **THEN** the Command exits with code 2 and its only stderr error has `code` = `invalid_value`

### Requirement: Rate limit

**In short:** with `--rate <n>`, one host's requests start at least 1/n seconds apart, robots.txt's included.

With `--rate <n>`, where n is a positive number of requests per second, requests to one host SHALL start at least `1/n` seconds apart, and the robots.txt request SHALL count as one of them. Without `--rate`, no limit SHALL apply beyond `--concurrency`. A value that is not a finite number above 0, such as 0, -1, `nan` or `inf`, or whose interval `1/n` is not finite, such as `1e-310`, SHALL be rejected, and so SHALL a boolean in `openlinx.toml`: as `--rate` with exit code 2 and error code `invalid_value`, and in `openlinx.toml` with exit code 3 and `settings_invalid`, as any invalid setting is.

#### Scenario: Requests to a host are spaced by the rate
- **WHEN** a Crawl with `--rate 2` requests robots.txt and then five URLs on one host through a fake Fetcher that answers at once, with a fake clock
- **THEN** the six requests start at 0.0, 0.5, 1.0, 1.5, 2.0 and 2.5 seconds

### Requirement: Requests without a response

**In short:** a request without an HTTP response is recorded as `error`, with a `fetch_error` code and its message.

A request that gets no HTTP response SHALL be recorded with:
- `fetch_state` = `error` and `status_code` NULL
- a `fetch_error` code
- a non-empty `fetch_error_message`

This capability SHALL use the codes `dns_error`, `connection_refused`, `connection_error`, `invalid_response`, `tls_error` and `watchdog` (see Backstops). `022-add-fetch-policy` writes `timeout`. A URL whose response could not be recorded has `record_failed` (see "One URL never stops the Crawl"). A URL whose origin's robots.txt request got no HTTP response has that request's code, without a request of its own (see "robots.txt fetch outcomes").

#### Scenario: An unknown host is a DNS error
- **WHEN** `http://site.test/` links to `http://nowhere.test/`, and `linx crawl http://site.test/` runs
- **THEN** `http://nowhere.test/` has `fetch_state` = `error` and `fetch_error` = `dns_error`

#### Scenario: A closed port is a refused connection
- **WHEN** `/` links to `http://127.0.0.1:{closed_port}/`, a port on which nothing listens
- **THEN** that URL has `fetch_error` = `connection_refused` and a non-empty `fetch_error_message`

#### Scenario: A connection reset in the body is a connection error
- **WHEN** `/` links to `/reset`, whose connection is reset after part of its body, and to `/after`, and `linx crawl {site}/` runs
- **THEN** `{site}/reset` has `fetch_state` = `error` and `fetch_error` = `connection_error`, and `{site}/after` has `fetch_state` = `fetched`

### Requirement: Depth limit

**In short:** URLs beyond `--max-depth` are skipped as `max_depth`, except the Resources of followed Pages, one deeper.

URLs whose Crawl Depth exceeds `--max-depth` SHALL NOT be requested, except Resources of followed Pages. They SHALL be recorded with `fetch_state` = `skipped` and `skip_reason` = `max_depth`. A URL that a Resource Link reaches SHALL be requested up to one Crawl Depth beyond the limit, where a followed Page puts its Resources, so a Resource of a Resource that is in-Scope HTML, two beyond, is skipped. A URL skipped as `max_depth` SHALL be queued again when a Link found later reaches it within the limit. In Spider mode there SHALL be no limit by default.

#### Scenario: Links beyond the limit are not requested
- **WHEN** `/` links to `/a`, `/a` links to `/b`, and `linx crawl {site}/ --max-depth 1` runs
- **THEN** `{site}/b` has `skip_reason` = `max_depth`

#### Scenario: A Resource of an HTML Resource is beyond the limit
- **WHEN** `/` holds `<img src="/pic">`, `/pic` is an HTML Page that holds `<img src="/i.png">`, and `linx crawl {site}/ --max-depth 0` runs
- **THEN** `{site}/pic` has `fetch_state` = `fetched` and `{site}/i.png` has `skip_reason` = `max_depth`

### Requirement: Skips at dispatch

**In short:** a queued URL gets at most one skip reason, and robots.txt is asked only about a URL that nothing else skips.

A dispatched URL SHALL be skipped as `excluded` when an exclude pattern matches it, else as `max_depth` when it is beyond `--max-depth`, else as `external_not_checked` when it is External under `--no-check-external`. Only a URL that none of these skips SHALL be checked against robots.txt, so these skips never request their origin's robots.txt.

#### Scenario: An excluded URL beyond the depth limit is excluded
- **WHEN** `/` links to `/a`, `/a` links to `/logout`, and `linx crawl {site}/ --max-depth 1 --exclude "/logout$"` runs
- **THEN** `{site}/logout` has `skip_reason` = `excluded`

#### Scenario: An excluded URL requests no robots.txt
- **WHEN** `/` links to `http://other.test/logout`, another fixture site serves `other.test`, and `linx crawl {site}/ --exclude "/logout$"` runs
- **THEN** `other.test` receives no request

### Requirement: URL limit

**In short:** `--max-urls <n>` bounds the URL requests over the Crawl's whole life; at the limit the Crawl stops, resumable, with exit code 0.

The Crawl SHALL have no URL limit by default. With `--max-urls <n>`, the Crawl SHALL request at most n URLs over its whole life:
- a URL SHALL count from the moment its request starts, so requests in flight count too
- a continued Crawl SHALL count the URLs its earlier runs fetched; a URL that a continue requests again, such as an `error` one, SHALL count when it is requested
- a URL that the Backstops request again within a run SHALL count once
- robots.txt requests SHALL NOT count

A value below 1 SHALL be rejected with exit code 2 and error code `invalid_value`. The limit is reached when it refuses a request: a Crawl that requests n URLs and has none left SHALL end `completed`, since `stopped` would promise a resume with nothing to do. When the limit is reached:
- no new request SHALL start
- requests in flight SHALL get the grace of "Stopping with an interrupt", and a request still running after it SHALL be cancelled, leaving its URL `queued`
- the Crawl SHALL end with the Crawl State `stopped` and `crawl.stop_reason` = `max_urls`, and SHALL be resumable
- URLs not yet requested SHALL stay `queued`
- the result SHALL hold a `max_urls_reached` warning whose hint is `linx resume --crawl <crawl id> --max-urls <higher>`
- the Command SHALL exit with code 0

#### Scenario: The Crawl stops at the limit
- **WHEN** `/` links to `/p1` to `/p9`, and `linx crawl {site}/ --max-urls 3` runs
- **THEN** the result has `"state": "stopped"`, `"stop_reason": "max_urls"` and `"fetched": 3` in `urls`

#### Scenario: URLs not requested stay queued
- **WHEN** `/` links to `/p1` to `/p9`, and `linx crawl {site}/ --max-urls 3` ends
- **THEN** exactly 7 rows of the `urls` table have `fetch_state` = `queued`

#### Scenario: The limit warning says how to continue
- **WHEN** `/` links to `/p1` to `/p9`, and `linx crawl {site}/ --max-urls 3` ends
- **THEN** the result's `warnings` hold an entry with code `max_urls_reached` whose `hint` contains `--max-urls`

#### Scenario: The limit holds under concurrency
- **WHEN** `/` links to `/slow/1` to `/slow/20`, each answering after 500 ms, and `linx crawl {site}/ --max-urls 5 --concurrency 5` runs
- **THEN** the fixture site receives exactly 5 requests for paths other than `/robots.txt`

#### Scenario: There is no limit by default
- **WHEN** `/` links to `/p1` to `/p9`, and `linx crawl {site}/` runs without `--max-urls`
- **THEN** the result has `"state": "completed"` and `"fetched": 10` in `urls`

#### Scenario: No limit is recorded as null
- **WHEN** `linx crawl {site}/` ends without `--max-urls`
- **THEN** the `crawl` table of `crawl.config` has `max_urls` = null

#### Scenario: A limit below one is rejected
- **WHEN** `linx crawl {site}/ --max-urls 0` runs
- **THEN** the Command exits with code 2 and its only stderr error has `code` = `invalid_value`

### Requirement: Each URL is requested once

**In short:** a URL is requested at most once a run, the Crawl ends whatever cycles its Links form, and a Crawl Depth's URLs start in discovery order.

Within one run, the Crawl SHALL start at most one request for each URL, however many Links lead to it and however responses interleave, apart from the requests that the Backstops make again. It SHALL end once every URL it may request has been processed, whatever cycles its Links form. Followed URLs of one Crawl Depth SHALL start in the order in which they were first recorded, which `urls.id` gives, never in an order taken from timestamps; URLs that a network pause put back start before the next frontier read.

#### Scenario: Each URL is requested once
- **WHEN** each of `/p1` to `/p10` links to all of the others and to `/`, `/` links to `/p1`, and `linx crawl {site}/` runs
- **THEN** the fixture site's request log holds each of `/` and `/p1` to `/p10` exactly once

#### Scenario: A link cycle ends
- **WHEN** `/` links to `/a`, `/a` links to `/b`, and `/b` links to `/a` and `/`, and `linx crawl {site}/` runs
- **THEN** the Crawl ends with the Crawl State `completed`

#### Scenario: Followed URLs start in discovery order
- **WHEN** `/` links to `/c`, `/a` and `/b`, in that order, and `linx crawl {site}/ --concurrency 1` runs
- **THEN** the fixture site receives the requests for `/c`, `/a` and `/b` in that order

### Requirement: The urls table

**In short:** `urls` holds one row per normalised URL with its frontier state, outcome and provenance, and its value lists already hold later changes' values.

The crawl store SHALL hold one row for each distinct normalised URL of the Crawl in a table `urls`, under the schema conventions of `018-add-schema-conventions` (ADR-0005): the table is `STRICT`, and the file SHALL refuse a value outside a column's listed values and a flag other than 0 and 1. This change SHALL add the following columns, each in the slice whose scenario first needs it. `022-add-fetch-policy` adds more columns.

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `id` | INTEGER, primary key | no | | Row id, stable for the life of the crawl file; it grows in the order URLs are first recorded, and is the dispatch order within a Crawl Depth |
| `url` | TEXT | no | | The normalised URL, unique |
| `host` | TEXT | no | | The URL's host in lower-case ASCII (IDNA) form; the key of the per-host politeness limits |
| `origin_id` | INTEGER, references `origins.id` | no | | The URL's origin: its scheme, host and port |
| `is_internal` | INTEGER | no | boolean | 1 for an Internal URL, 0 for an External URL |
| `in_scope` | INTEGER | no | boolean | 1 when the URL is inside the Scope, so it may be followed |
| `crawl_depth` | INTEGER | no | | Crawl Depth; 0 for Seeds |
| `discovered_via` | TEXT | no | listed below | How the URL was found (see "Link discovery", Provenance) |
| `found_on_url_id` | INTEGER, references `urls.id` | yes | | The URL whose response revealed this one (see "Link discovery"); NULL for Seeds |
| `fetch_state` | TEXT | no | `queued`, `fetched`, `error`, `skipped` | Frontier state: waiting, a response was recorded, no response, or not requested |
| `skip_reason` | TEXT | yes | listed below | Why a skipped URL was not requested |
| `blocked_by_robots_txt` | INTEGER | yes | boolean | 1 when robots.txt disallows the URL for the robots user-agent token (also with `--ignore-robots`), 0 when it allows it; NULL when not checked |
| `status_code` | INTEGER | yes | | HTTP status code of the URL's own response; NULL without a response |
| `fetch_error` | TEXT | yes | listed below | Why no response is recorded for the URL |
| `fetch_error_message` | TEXT | yes | | Human-readable detail of `fetch_error` |
| `content_type` | TEXT | yes | | The `Content-Type` response header as received |
| `response_time_ms` | INTEGER | yes | | Time from sending the request to receiving the whole body |
| `fetched_at` | TEXT | yes | timestamp | UTC time of the request |
| `parsed` | INTEGER | no | boolean | 1 when the response was parsed and its Links were found |
| `parse_error` | TEXT | yes | listed below | Why parsing failed in whole or in part: a registered extractor failed (`parsed` stays 1), or nothing came out of page preparation (`parsed` = 0) |
| `parse_error_message` | TEXT | yes | | Human-readable detail of `parse_error` |

The listed values SHALL include, from v0.1, the values that later changes write, so that no later change adds one:
- `discovered_via`: `seed`; every Link type, the later ones included (see "Link discovery"); `redirect`, for a redirect target (`022-add-fetch-policy`); `list`, `sitemap_input` and `sitemap_index`, for a listed URL and for sitemap files (`024-add-list-and-sitemap-modes`, v0.2). A URL listed in a sitemap has the Link type `xml_sitemap`; there is no separate `sitemap` value.
- `skip_reason`: `excluded`, `blocked_by_robots_txt`, `robots_unreachable`, `nofollow`, `link_type_not_followed`, `external_not_checked`, `max_depth`; `max_redirects` and `url_too_long` (`022`)
- `fetch_error`: `dns_error`, `connection_refused`, `connection_error`, `invalid_response`, `watchdog`, `record_failed`, `tls_error`; `timeout` (`022`)
- `parse_error`: `extractor_error`; `body_too_large` (`022`); `worker_crashed` and `parse_timeout` (`026-add-parse-pool`)

This change SHALL add these indexes to `urls`, built while the Crawl writes:

| Index | Columns | Unique | Where | Query it serves |
|---|---|---|---|---|
| `urls_url` | `url` | yes | | Recording a discovered URL once (`ON CONFLICT (url)`), and finding one URL's row |
| `urls_crawl_depth_id` | `crawl_depth`, `id` | no | `fetch_state = 'queued'` | The frontier: the next queued URLs of the open Crawl Depth, in `id` order |

#### Scenario: A skipped URL has no response data
- **WHEN** `/` links to `/logout`, and `linx crawl {site}/ --exclude "/logout$"` runs
- **THEN** `{site}/logout` has `status_code`, `content_type`, `response_time_ms` and `fetched_at` all NULL, and `parsed` = 0

#### Scenario: Response timing is recorded
- **WHEN** `/` links to `/slow`, which answers after 500 ms
- **THEN** `{site}/slow` has a `response_time_ms` of at least 500 and a non-null `fetched_at`

#### Scenario: The Content-Type is recorded as received
- **WHEN** `/` links to `/doc.pdf`, which returns `Content-Type: application/pdf`
- **THEN** `{site}/doc.pdf` has `content_type` = `application/pdf`

#### Scenario: The ways a URL is found are an enumeration
- **WHEN** `linx schema urls` runs
- **THEN** the `values` of the column `discovered_via` are `["seed","hyperlink","canonical","pagination","hreflang","iframe","meta_refresh","http_refresh","image","css","javascript","video","audio","media","amphtml","mobile_alternate","misc","xml_sitemap","sitemap_hreflang","javascript_redirect","redirect","list","sitemap_input","sitemap_index"]`

#### Scenario: Indexes of urls
- **WHEN** `linx schema urls --fields indexes` runs
- **THEN** the item's `indexes`, reduced to `name`, `columns`, `unique` and `where`, include `{"name":"urls_crawl_depth_id","columns":["crawl_depth","id"],"unique":false,"where":"fetch_state = 'queued'"}` and `{"name":"urls_url","columns":["url"],"unique":true,"where":null}`

### Requirement: The origins table

**In short:** `origins` holds one row per origin with its robots.txt outcome, and every URL points to its origin.

The crawl store SHALL hold one row for each origin of a URL that the Crawl recorded, in a table `origins`, under the same conventions. An origin's row SHALL be recorded in the writer unit that records the first URL on it, and every `urls` row SHALL point to its origin. This change SHALL add these columns. `022-add-fetch-policy` adds `http_version`.

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `id` | INTEGER, primary key | no | | Row id |
| `origin` | TEXT | no | | Scheme, host and port, for example `https://site.test`, with a default port left out; unique |
| `host` | TEXT | no | | The origin's host in lower-case ASCII (IDNA) form |
| `is_internal` | INTEGER | no | boolean | 1 when the origin's URLs are Internal URLs |
| `robots_state` | TEXT | yes | `ok`, `missing`, `unreachable` | Rules applied, everything allowed, or everything disallowed or unanswered; NULL while robots.txt has not been fetched, which happens before the first URL of the origin that the Scope does not skip and the URL limit does not refuse |
| `robots_status_code` | INTEGER | yes | | Status code of the last robots.txt response; NULL without a response |
| `robots_fetch_error` | TEXT | yes | the values of `urls.fetch_error` | Why the robots.txt request, or a redirect hop of it, got no HTTP response; NULL when its last request got one, or while robots.txt has not been fetched |
| `robots_fetch_error_message` | TEXT | yes | | Human-readable detail of `robots_fetch_error` |
| `robots_fetched_at` | TEXT | yes | timestamp | UTC time robots.txt was last fetched |
| `robots_txt` | TEXT | yes | | The robots.txt body as parsed, up to 512,000 bytes |
| `robots_crawl_delay_ms` | INTEGER | yes | | The `Crawl-delay` for the robots user-agent token; recorded, not applied |
| `robots_sitemaps` | TEXT | yes | json | JSON array of the `Sitemap:` URLs in robots.txt; NULL while robots.txt has not been fetched |

This change SHALL add this index to `origins`, built while the Crawl writes:

| Index | Columns | Unique | Where | Query it serves |
|---|---|---|---|---|
| `origins_origin` | `origin` | yes | | Recording an origin once (`ON CONFLICT (origin)`), and finding an origin's row |

#### Scenario: An External origin gets its own row
- **WHEN** `http://site.test/` links to `http://other.test/page`, and `linx crawl http://site.test/` runs
- **THEN** `origins` holds `http://site.test` with `is_internal` = 1 and `http://other.test` with `is_internal` = 0

#### Scenario: A URL that is not requested still points to its origin
- **WHEN** `http://site.test/` links to `http://other.test/page`, and `linx crawl http://site.test/ --no-check-external` runs
- **THEN** `http://other.test/page` has an `origin_id` that points to the `origins` row for `http://other.test`, whose `robots_state`, `robots_fetched_at` and `robots_sitemaps` are NULL

### Requirement: Crawl metadata written by the engine

**In short:** the engine fills `015`'s crawl metadata and adds `crawl.scope`, `crawl.stop_reason` and `crawl.warnings`.

The Crawl SHALL fill the crawl metadata of `015-add-crawl-store`:
- `crawl.crawl_mode` (`spider` for this capability), `crawl.section_crawl`, `crawl.command_argv` (redacted by `015`) and `crawl.config`
- the `seeds` table
- the Crawl State in `crawl.state`: `running` while it works, then `completed`, `stopped` or `failed`, along the Crawl State transitions below

This change SHALL add three columns to `crawl`, under the conventions of `018-add-schema-conventions`:
- `scope`: TEXT, `json`, not null, the resolved Scope, written with the `crawl` row when the Crawl is created
- `stop_reason`: TEXT, nullable, why the Crawl ended early: `max_urls`, `interrupt` or `requested` for a `stopped` Crawl, and `seed_unreachable`, `site_unreachable` or `write_failed` for a `failed` one; NULL while it runs and when it is `completed`. These six values SHALL be the one value set of every column that records why a Crawl or one of its runs ended, including those of `060-add-crawl-control`.
- `warnings`: TEXT, `json`, not null, a JSON array of diagnostics in the full shape of `010-add-workspace-and-cli-contract` (`{level, code, message, hint, details}`); `[]` when the Crawl is created, and written when a run ends, so a run whose process is killed leaves its warnings out. It SHALL hold the warnings of the Crawl's whole life: a continued Crawl SHALL keep those of its earlier runs, write a warning kept once per host, origin, Seed or code only when it is new to the Crawl, and add a counted warning's counts to the stored ones. `max_urls_reached` describes how one run ended, so a continue SHALL drop it.

The `crawl` table of `crawl.config` SHALL hold every registered crawl setting, including those added by later changes, with secrets redacted by `015`.

#### Scenario: The recorded config holds every registered crawl setting
- **WHEN** `linx crawl {site}/` ends with no other flags and no `openlinx.toml`
- **THEN** the `crawl` table of `crawl.config` has exactly one key for each option of the `crawl` entry in `linx commands` whose `setting` starts with `crawl.`, and each value equals that option's `default`

#### Scenario: A completed Crawl records its state
- **WHEN** `linx crawl {site}/` ends after every URL is processed
- **THEN** `crawl.state` is `completed` and `crawl.stop_reason` is NULL

#### Scenario: Warnings are stored as diagnostics
- **WHEN** `/robots.txt` returns 503 on every attempt, and `linx crawl {site}/` ends
- **THEN** `crawl.warnings` holds an object whose keys are exactly `level`, `code`, `message`, `hint` and `details`, with `"level": "warning"` and `"code": "robots_unreachable"`

#### Scenario: Warnings cover the Crawl's whole life
- **WHEN** the robots.txt of `a.{host}` returns 503 on every attempt, a Crawl of `{site}/` with `--subdomains` that requested a URL on `a.{host}` is stopped by `--max-urls`, and the Crawl Service continues it while that robots.txt still returns 503 and the continuation requests a URL on `b.{host}`, whose robots.txt returns 503 too
- **THEN** `crawl.warnings` and the result's `warnings` hold exactly two `robots_unreachable` warnings, one for `a.{host}` and one for `b.{host}`

### Requirement: Persistent frontier

**In short:** a URL is recorded `fetched` or `error` in one unit with everything found from it, so a `stopped` or `failed` Crawl continues from its file.

The `urls` table SHALL be the Crawl's frontier:
- A URL SHALL be recorded as `fetched` or `error` only in the writer unit (`015-add-crawl-store`) that also records its response data and every URL discovered from it, or as `error` by the fallback unit of a unit that failed (see "One URL never stops the Crawl").
- URLs whose request has not completed SHALL stay `queued`.

The Crawl Service SHALL be able to continue a Crawl from its store when its Crawl State is `stopped` or `failed`. `linx resume` in `060-add-crawl-control` exposes this operation, and adds `interrupted` Crawls, including those whose process was killed. Continuing SHALL:
1. set the Crawl State back to `running`
2. put back into `queued` every URL that ended as `error` or with `skip_reason` = `robots_unreachable`
3. request only `queued` URLs, with the URL limit counted over the Crawl's whole life, and fetch each origin's robots.txt again, whose answer replaces the stored one; URLs that the earlier robots.txt blocked stay skipped
4. end with the same URLs as an uninterrupted Crawl

#### Scenario: A killed Crawl leaves no half-recorded Page
- **WHEN** a `linx crawl {site}/` subprocess on a 30-page fixture site is killed (SIGKILL, or TerminateProcess on Windows) after 10 pages are fetched
- **THEN** every URL that a Page with `parsed` = 1 links to has a row in the `urls` table

#### Scenario: Continuing a stopped Crawl completes it
- **WHEN** `/` links to `/p1` to `/p9`, a Crawl of `{site}/` stopped by `--max-urls 3` is continued through the Crawl Service without a URL limit, and the continuation ends
- **THEN** the Crawl State is `completed`, and the `urls` table holds 10 rows with `fetch_state` = `fetched`

#### Scenario: Continuing does not request fetched URLs again
- **WHEN** `/` links to `/p1` to `/p9`, and a Crawl of `{site}/` stopped by `--max-urls 3` is continued through the Crawl Service without a URL limit
- **THEN** the fixture site receives no request during the continuation for a URL that had `fetch_state` = `fetched` before it

#### Scenario: The URL limit counts over the Crawl's whole life
- **WHEN** `/` links to `/p1` to `/p9`, a Crawl of `{site}/` stopped by `--max-urls 3` is continued through the Crawl Service with a URL limit of 5, and the continuation ends
- **THEN** the `urls` table holds 5 rows with `fetch_state` = `fetched`, and the Crawl State is `stopped` with `stop_reason` = `max_urls`

#### Scenario: A continue requests the URLs an unreachable robots.txt blocked
- **WHEN** `/` links to `http://other.test/a` and to `/p1` to `/p9`, `http://other.test/robots.txt` returns 503, a Crawl of `{site}/` stopped by `--max-urls 3` recorded `http://other.test/a` with `skip_reason` = `robots_unreachable`, and the Crawl Service continues it without a URL limit once that robots.txt returns 404
- **THEN** `http://other.test/a` has `fetch_state` = `fetched`

### Requirement: Per-response hook

**In short:** every registered handler's rows for a URL are written once per recorded outcome, with the URL's final state and row values.

For each URL that reaches a final `fetch_state` (`fetched`, `error` or `skipped`) when it is dispatched, the rows of every registered per-response handler SHALL be written exactly once per recorded outcome, with that state. A URL that a network pause re-queues (see "Backstops"), or that `060-add-crawl-control` continues, is recorded again, and its handlers' rows are written again with its new state, so a handler that writes rows for an outcome without a response SHALL key them by `url_id` and replace them. A URL that only Links that are not followed reach is recorded `skipped` when it is discovered, and reaches no handler, since a later followed Link may still queue it. A URL skipped as `max_depth` reaches no handler either, since a Link found later at a smaller depth re-queues it. A handler SHALL receive the URL's row values. For a URL with a response it SHALL also receive the status code, the reason phrase, the response headers, the robots directives (the `X-Robots-Tag` for the robots user-agent token, and the robots `<meta>` when the response was parsed) and, when the response was parsed, the extractor outputs. For an in-Scope 2xx response it SHALL receive the Links the Crawl read: those of the `Link` and `Refresh` headers, whatever became of the response's preparation, then those of the document when it was prepared. Each Link SHALL say where it was declared, `head` or `body` as the parser placed the element, or `http_header`, and whether the Crawl requests its target through it, which the Link type table and nofollow decide. A handler SHALL NOT write to the crawl store itself: it returns rows, and the crawl store writes them in the writer unit that records the URL's final state, so they are committed together. Later changes register handlers: `030-add-page-data` for Page data and cookies.

#### Scenario: A registered handler sees each recorded outcome once
- **WHEN** a handler registered for the test records the URLs and states it receives, `/` links to `/a`, `/missing` (which returns 404) and `/logout`, and `linx crawl {site}/ --exclude "/logout$"` runs
- **THEN** the handler has received exactly `({site}/, fetched)`, `({site}/a, fetched)`, `({site}/missing, fetched)` and `({site}/logout, skipped)`, once each

#### Scenario: A handler sees the X-Robots-Tag of a PDF
- **WHEN** a handler registered for the test records the directives it receives, `/` links to `/report.pdf`, which returns `application/pdf` with the headers `X-Robots-Tag: googlebot: noindex` and `X-Robots-Tag: nofollow`, and `linx crawl {site}/` runs
- **THEN** the handler has received for `{site}/report.pdf` an X-Robots-Tag that says nofollow and not noindex

#### Scenario: A handler sees the Links of a Page whose extractor failed
- **WHEN** an extractor registered for the test raises on every Page, a handler registered for the test records the Links it receives, `/` links to `/a`, and `linx crawl {site}/` runs
- **THEN** the handler has received for `{site}/` one Link, a hyperlink to `{site}/a`

#### Scenario: A canonical in the body is placed in the body
- **WHEN** a handler registered for the test records the Links it receives, and `/` holds `<head><link rel="canonical" href="/c"></head><body><p>Text</p><link rel="canonical" href="/d"></body>`
- **THEN** the handler has received for `{site}/` the canonical to `{site}/c` declared in `head`, and the canonical to `{site}/d` declared in `body`

#### Scenario: A nofollow Link does not request its target
- **WHEN** a handler registered for the test records the Links it receives, and `/` holds `<a href="/a">A</a>` and `<a rel="nofollow" href="/b">B</a>`
- **THEN** the handler has received for `{site}/` the Link to `{site}/a` as one that requests its target, and the Link to `{site}/b` as one that does not

#### Scenario: A handler sees the reason phrase
- **WHEN** a handler registered for the test records the reason phrases it receives, `/` links to `/missing`, which returns 404 Not Found, and `linx crawl {site}/` runs
- **THEN** the handler has received the reason phrase `Not Found` for `{site}/missing`

### Requirement: Post-crawl passes

**In short:** registered passes run when a Crawl ends `completed` or `stopped`, again after a continue, and never for a `failed` Crawl.

The Crawl SHALL run every registered post-crawl pass when it ends as `completed` or `stopped`, after its last URL is recorded and before its final Crawl State is written. It SHALL NOT run them for a Crawl that ends as `failed`. A continued Crawl SHALL run them again when it ends, so a pass registered by a later change can run more than once for the same Crawl. `030-add-page-data` and `040-add-rules` register passes.

#### Scenario: Post-crawl passes run before a Crawl is completed
- **WHEN** a pass registered for the test records the Crawl State it sees, and `linx crawl {site}/` runs to its end
- **THEN** the pass has run once and saw the Crawl State `running`

#### Scenario: Post-crawl passes run when the URL limit stops a Crawl
- **WHEN** a pass registered for the test counts its runs, `/` links to `/p1` to `/p9`, and `linx crawl {site}/ --max-urls 3` runs
- **THEN** the pass has run once

#### Scenario: Post-crawl passes do not run for a failed Crawl
- **WHEN** a pass registered for the test counts its runs, and `linx crawl http://127.0.0.1:{closed_port}/ --network-wait 0` runs
- **THEN** the pass has run 0 times

#### Scenario: Post-crawl passes run again after a continue
- **WHEN** a pass registered for the test counts its runs, a Crawl stopped by `--max-urls 3` is continued through the Crawl Service, and the continuation ends
- **THEN** the pass has run twice

### Requirement: One URL never stops the Crawl

**In short:** a failure of one URL becomes its recorded outcome, counted in one warning per kind, and only failures of the whole Crawl stop it.

A failure while one URL is fetched, decoded, parsed, extracted or handled SHALL become that URL's recorded outcome, and the Crawl SHALL go on:
- **Requests:** a request without a response is recorded as "Requests without a response" says.
- **Decoding:** bytes that are invalid in the response's character encoding SHALL be decoded with replacement characters.
- **Extractors:** when a registered extractor raises an error, the URL SHALL be recorded with `parsed` = 1, `parse_error` = `extractor_error`, and a `parse_error_message` that names the extractor and the error's type. The link extractor never raises, so the Page's Links SHALL still be followed, and handlers SHALL receive every extractor output except the failed one's.
- **Handlers:** when a per-response handler raises an error, the URL SHALL be recorded without that handler's rows.
- **Recording:** when the writer unit that records a URL fails on its first run with an error of one row, the URL SHALL be recorded by a fallback unit with `fetch_state` = `error`, `fetch_error` = `record_failed` and the error in `fetch_error_message`, without the URLs discovered from it and without its handler rows. An error of one row is a value that the file refuses (a constraint, a value too big, or a value that cannot be bound), or an error that the tool's own row code raises. Each of these SHALL instead fail the Crawl as a write failure (see "Result of a Crawl"):
  - any other error that SQLite reports, such as a full disk, an I/O error, or a read-only, corrupt or busy file
  - a unit that fails, or gives another result, when the writer runs it again (`017-speed-up-crawl-writer`)
  - a fallback unit that fails, a commit that fails, and a writer that has ended
  - 100 URL units in a row that fail on their first run, with no URL unit committed in between
- **Counted warnings:** each kind of failure SHALL be reported by one warning, `parse_failed` for extractors and for a page preparation that gives nothing (`body_too_large`, `worker_crashed`, `parse_timeout`), `handler_failed` for handlers and `record_failed` for recording. It SHALL be written to stderr when it first occurs, and kept once in the result and `crawl.warnings`, with `details.count` (the number of URLs it affected) and `details.first_url`.

Only failures of the whole Crawl stop it: an unreachable Seed, the Backstops, a crawl file that cannot be written, and a bug in the tool that escapes a URL's task, which ends it with `internal_error` (see "Result of a Crawl"). Page preparation (decoding, parsing, the extractors and the robots directives) SHALL be one function of the response, called through an executor: in this change it runs in the crawl process, and `026-add-parse-pool` runs it in worker processes.

#### Scenario: An extractor error is recorded
- **WHEN** an extractor registered for the test raises an error on `{site}/boom`, `/` links to `/boom` and `/ok`, and `linx crawl {site}/` runs
- **THEN** `{site}/boom` has `parsed` = 1, `parse_error` = `extractor_error`, and a `parse_error_message` that contains the extractor's name

#### Scenario: The Crawl continues after an extractor error
- **WHEN** an extractor registered for the test raises an error on `{site}/boom`, `/` links to `/boom` and `/ok`, and `linx crawl {site}/` runs
- **THEN** `{site}/ok` has `parsed` = 1

#### Scenario: Links of a Page whose extractor failed are followed
- **WHEN** an extractor registered for the test raises an error on `{site}/boom`, `/` links to `/boom`, `/boom` links to `/deeper`, and `linx crawl {site}/` runs
- **THEN** `{site}/deeper` has `fetch_state` = `fetched`

#### Scenario: Parse failures are counted in one warning
- **WHEN** an extractor registered for the test raises an error on `{site}/boom1` and `{site}/boom2`, `/` links to both, and `linx crawl {site}/` ends
- **THEN** the result's `warnings` hold exactly one entry with code `parse_failed`, and its `details.count` is 2

#### Scenario: Two handlers that fail on one URL count it once
- **WHEN** two handlers registered for the test raise an error on `{site}/boom`, `/` links to `/boom` and `/ok`, and `linx crawl {site}/` ends
- **THEN** the result's `warnings` hold one entry with code `handler_failed` whose `details.count` is 1

#### Scenario: A failing handler does not stop the Crawl
- **WHEN** a handler registered for the test raises an error on `{site}/boom`, `/` links to `/boom` and `/ok`, and `linx crawl {site}/` ends
- **THEN** the Crawl State is `completed`, and the result's `warnings` hold one entry with code `handler_failed` whose `details.count` is 1

#### Scenario: A URL whose rows cannot be written is recorded as an error
- **WHEN** a handler registered for the test returns, for `{site}/boom`, a row whose store writer, registered for the test, raises an error, `/` links to `/boom` and `/ok`, and `linx crawl {site}/` ends
- **THEN** `{site}/boom` has `fetch_state` = `error` and `fetch_error` = `record_failed`, `{site}/ok` has `fetch_state` = `fetched`, the Crawl State is `completed`, and the result's `warnings` hold one entry with code `record_failed` whose `details.count` is 1

#### Scenario: Recording that fails for every URL fails the Crawl
- **WHEN** a handler registered for the test returns, for every URL other than `{site}/`, a row whose store writer, registered for the test, raises an error, `/` links to `/p1` to `/p120`, and `linx crawl {site}/` runs
- **THEN** the Command exits with code 7, stdout holds the result with `"state": "failed"` and `"stop_reason": "write_failed"`, and the last stderr line is an error with `code` = `crawl_write_failed`

#### Scenario: Deeply nested HTML does not stop the Crawl
- **WHEN** `/` links to `/deep`, whose body nests 10,000 `<div>` elements around a link to `/after`, and `linx crawl {site}/` ends
- **THEN** the Crawl State is `completed`, and `{site}/deep` has `parsed` = 1 or a `parse_error`

#### Scenario: Undecodable bytes do not stop the Crawl
- **WHEN** `/` links to `/bad-bytes`, served as `text/html; charset=utf-8` with bytes that are not UTF-8 before a link to `/after`, and `linx crawl {site}/` runs
- **THEN** `{site}/after` has `fetch_state` = `fetched`

### Requirement: Backstops

**In short:** a run of Internal requests without a response pauses the Crawl and probes the Seed instead of recording the site as errors, and a watchdog cancels a request that hangs.

- **The network pause:** when `max(8, 2 × --concurrency)` requests in a row for Internal URLs end without an HTTP response, the Crawl SHALL pause instead of recording the rest of the site as errors.
  - **Without an HTTP response** means the `fetch_error` `dns_error`, `connection_refused`, `connection_error`, `invalid_response` or `watchdog`, or `022-add-fetch-policy`'s `timeout`. `tls_error` SHALL NOT count: a certificate failure is an answer of sorts, and a site-wide one SHALL NOT wait `--network-wait` and then fail with a misleading `site_unreachable`. A response of any status SHALL reset the count, and requests for External URLs SHALL NOT count.
  - **While paused,** no new request SHALL start. Requests in flight SHALL finish: one that gets a response SHALL be recorded, and one that ends without a response SHALL NOT be recorded, so its URL stays `queued` and is requested again when the Crawl resumes.
  - **Probes:** while paused, the Crawl SHALL request the Seed URL at 5, 10, 20 and 40 seconds after the pause began, then every 60 seconds, through the per-host limits of "Per-host concurrency" and "Rate limit". A probe SHALL NOT be recorded as a URL and SHALL NOT count toward `--max-urls`. A probe that gets a response of any status ends the pause:
    - **A dead section:** when the first probe answers before the second probe is due, or before the wait ends when there is no second probe, the failures were the site's own, and the Crawl SHALL resume and keep their errors. For the rest of the run, the failures of requests to an origin with at least 2 of those URLs, the Seed's origin aside, SHALL NOT count toward the pause, and their URLs SHALL still be requested and recorded as errors.
    - **An outage:** when a probe answers later, the URLs whose requests made up the count SHALL be re-queued and requested again, each at most once in a run, and the Crawl SHALL resume.
  - **Giving up:** a probe SHALL start only before `--network-wait <seconds>` have passed since the pause's start (setting `crawl.network_wait`, default 1800). When no probe has got a response by then, the probes in flight SHALL be cancelled, and the Crawl SHALL end as `failed` with `stop_reason` = `site_unreachable`, and URLs not requested SHALL stay `queued`, so the Crawl can be continued. With `--network-wait 0` no probe starts, so the Crawl fails at once. A negative value SHALL be rejected with exit code 2 and error code `invalid_value`. The Command SHALL print the result, write exactly one error diagnostic, with code `site_unreachable` and a hint that says how long the Crawl waited and names `linx resume`, and exit with code 8.
  - **Visibility:** the Crawl SHALL write a `crawl_paused` event when it pauses and a `crawl_resumed` event when it resumes (see "Progress events"), and one counted `network_paused` warning, with `details.count` (the number of pauses) and `details.total_seconds` (the time spent paused).
  - **A stop** (the URL limit, an interrupt or a stop request) SHALL end a pause, and the Crawl SHALL stop as it does otherwise.
- **The watchdog:** a request that has not ended within the watchdog time after it started SHALL be cancelled. The watchdog time SHALL be the longer of 120 seconds and the Fetcher's total request deadline plus 30 seconds, so it never cuts a response that the Fetcher still allows. Its URL SHALL be recorded with `fetch_state` = `error` and `fetch_error` = `watchdog`, and the Crawl SHALL go on. A request ended by the watchdog SHALL count as a request without an HTTP response for the network pause.

#### Scenario: A network wait of zero fails at once
- **WHEN** `/` links to `/down/1` to `/down/20` and then to `/p1`, every `/down/<n>` resets its connection, and `linx crawl {site}/ --concurrency 1 --network-wait 0` runs
- **THEN** stdout holds the result with `"state": "failed"` and `"stop_reason": "site_unreachable"`, and `{site}/p1` has `fetch_state` = `queued`

#### Scenario: Losing the site is reported by one error
- **WHEN** `/` links to `/down/1` to `/down/20`, every `/down/<n>` resets its connection, and `linx crawl {site}/ --concurrency 1 --network-wait 0` runs
- **THEN** the Command exits with code 8, and stderr holds exactly one error line, as its last line, with `code` = `site_unreachable` and a `hint` that contains `linx resume`

#### Scenario: A dead section does not stop the Crawl
- **WHEN** a fake Fetcher gets no response for `{site}/down/1` to `{site}/down/20` and answers every other request, `/` links to them and then to `/p1`, and the Crawl runs with `--concurrency 1` and a fake clock
- **THEN** the Crawl State is `completed`, every `{site}/down/<n>` has `fetch_state` = `error`, `{site}/p1` has `fetch_state` = `fetched`, and the result's `warnings` hold an entry with code `network_paused`

#### Scenario: A dead subdomain pauses the Crawl once
- **WHEN** `/` links to 300 URLs on the subdomain `dead.{host}` and then to `/p1` to `/p20`, a fake Fetcher answers 404 for the robots.txt of `dead.{host}` and gets no response for its other URLs, and none for any request to `{host}` from the one for `/p10` on until 120 seconds of clock time have passed, and the Crawl runs with `--subdomains`, `--concurrency 1` and a fake clock
- **THEN** the events hold exactly two `crawl_resumed` events, the first with `data.outcome` = `dead_section` and the second with `data.outcome` = `outage`, every URL on `dead.{host}` has `fetch_state` = `error`, every `{site}/p<n>` has `fetch_state` = `fetched`, and the Crawl State is `completed`

#### Scenario: An outage pauses and resumes the Crawl
- **WHEN** `/` links to `/p1` to `/p20`, a fake Fetcher gets no response for any request from `/p2` on until 30 seconds of clock time have passed, and the Crawl runs with `--concurrency 1` and a fake clock
- **THEN** the events hold one `crawl_paused` event and then one `crawl_resumed` event with `data.outcome` = `outage`, and the Crawl State is `completed`

#### Scenario: URLs that failed in an outage are requested again
- **WHEN** `/` links to `/p1` to `/p20`, a fake Fetcher gets no response for any request from `/p2` on until 30 seconds of clock time have passed, and the Crawl runs with `--concurrency 1` and a fake clock
- **THEN** every `{site}/p<n>` has `fetch_state` = `fetched`

#### Scenario: A Crawl that waits longer than the network wait fails
- **WHEN** `/` links to `/p1` to `/p20`, a fake Fetcher gets no response for any request after the one for `/`, and the Crawl runs with `--concurrency 1`, `--network-wait 30` and a fake clock
- **THEN** the Seed is probed 3 times, and the Crawl ends as `failed` with `stop_reason` = `site_unreachable`

#### Scenario: Probes back off to once a minute
- **WHEN** the probe times of a network wait of 200 seconds are computed
- **THEN** they are 5, 10, 20, 40, 100 and 160 seconds after the pause began

#### Scenario: Progress events say when the Crawl is paused
- **WHEN** a Crawl is paused for 30 seconds of fake-clock time
- **THEN** every `progress` event written during the pause has `data.paused` = true, and every other one `data.paused` = false

#### Scenario: A negative network wait is rejected
- **WHEN** `linx crawl {site}/ --network-wait -1` runs
- **THEN** the Command exits with code 2 and its only stderr error has `code` = `invalid_value`

#### Scenario: Dead External links do not fail the Crawl
- **WHEN** `http://site.test/` links to `http://nowhere.test/1` to `http://nowhere.test/12`, which do not resolve, and `linx crawl http://site.test/ --concurrency 1` runs
- **THEN** the Crawl ends with the Crawl State `completed`

#### Scenario: A stuck request is ended by the watchdog
- **WHEN** a fake Fetcher never answers for `{site}/stuck`, `/` links to `/stuck` and `/ok`, and the Crawl runs with the default settings and a fake clock that passes 120 seconds
- **THEN** `{site}/stuck` has `fetch_state` = `error` and `fetch_error` = `watchdog`, and the Crawl State is `completed`

### Requirement: Progress events

**In short:** a foreground Crawl writes JSON events to stderr: its start, progress every 10 seconds, pauses and resumes, and its stop.

While a foreground Crawl runs, the Command SHALL write progress events to stderr in the event shape of `010-add-workspace-and-cli-contract`: one JSON object per line, `{event, ts, data}`, encoded as UTF-8 and ending with LF on every OS. The events are:

| `event` | When | `data` |
|---|---|---|
| `crawl_started` | once, before any other event | `crawl_id`, `crawl_mode`, `seed_count`, `crawl_file`, `parse_workers` (the processes that prepare Pages besides the crawl process: 0 in this change, the size of `026-add-parse-pool`'s pool) |
| `progress` | every 10 seconds, during a network pause too | `crawl_id`, `elapsed_s`, `urls` (`discovered`, `fetched`, `errors`, `skipped`, `queued`), `rate` (URLs requested per second over the last 60 seconds), `paused` (true while the Crawl is paused) |
| `crawl_paused` | when the Crawl pauses (see "Backstops") | `crawl_id`, `reason` (the `fetch_error` of the request that paused it), `urls` (the URLs whose requests made up the count) |
| `crawl_resumed` | when a probe answers | `crawl_id`, `duration_s` (the time paused), `outcome` (`outage` or `dead_section`) |
| `stopping` | when the Crawl starts to stop before its frontier is empty: at the URL limit, on an interrupt or a stop request, or as it fails | `crawl_id`, `reason` (the `stop_reason` it starts to stop with, which a later failure can outrank) |

The `urls` counts of a `progress` event SHALL be those of the URLs that committed units recorded, kept as counters while the Crawl runs.

A warning SHALL be written to stderr when it first occurs for a host, as a diagnostic line of `010`. It SHALL also be kept for the result and `crawl.warnings`.

#### Scenario: The first event line is the start event
- **WHEN** `linx crawl {site}/` runs
- **THEN** the first event line on stderr has `"event": "crawl_started"`

#### Scenario: Every stderr line is an event or a diagnostic
- **WHEN** `/robots.txt` returns 503 on every attempt, and `linx crawl {site}/` runs
- **THEN** every line on stderr parses as a JSON object that has either an `event` field or a `level` field

#### Scenario: A warning is written as a diagnostic
- **WHEN** `/robots.txt` returns 503 on every attempt, and `linx crawl {site}/` runs
- **THEN** stderr holds a line with `"level": "warning"` and `"code": "robots_unreachable"`

#### Scenario: Progress events come every 10 seconds
- **WHEN** a Crawl runs for 25 seconds of fake-clock time
- **THEN** exactly 2 `progress` events are written

#### Scenario: Events are UTF-8 on Windows (Windows)
- **WHEN** `linx crawl {site}/` runs as a subprocess on Windows with a Workspace whose path contains `Ü`
- **THEN** `data.crawl_file` of the `crawl_started` event, decoded from the UTF-8 bytes on stderr, contains `Ü`

### Requirement: Result of a Crawl

**In short:** a Crawl that records its end prints one JSON result, and its exit code says how it ended.

Whenever a foreground Crawl ends with its Crawl State recorded, whatever that state, the Command SHALL print one JSON object on stdout with these fields:
- `crawl_id`, `state`, `stop_reason`, `crawl_mode`, `seed` (the first Seed), `seed_count`, `section_crawl`
- `started_at`, `ended_at`, `duration_s`
- `urls`, with the counts `discovered`, `fetched`, `errors`, `skipped` and `queued`
- `pages`: the number of URLs with `parsed` = 1
- `status_classes`, with the counts `2xx`, `3xx`, `4xx`, `5xx` and `other`
- `crawl_file`
- `warnings`: diagnostics in the full shape

`linx commands` SHALL list the `crawl` Command with `"output": "document"`.

Exit codes follow `010-add-workspace-and-cli-contract`:
- 0 when the Crawl State is `completed`, or `stopped` with `stop_reason` `max_urls` or `requested`
- 130 when the Crawl is `stopped` by an interrupt
- 7 when the Crawl is `failed` because writing the crawl store failed (`crawl_write_failed`), or 5 when the crawl file stayed locked by another connection for longer than the writer waits (`crawl_busy`, `015-add-crawl-store`)
- 70 when a bug in the tool ends the Crawl (`internal_error`): no result is printed, and the crawl file keeps the Crawl State `running`
- 8 when the Crawl is `failed` because its Seed is unreachable (`seed_unreachable`) or the site stayed unreachable for `--network-wait` (`site_unreachable`)

When writing fails, the Crawl Service SHALL try once more to record `failed` with `stop_reason` = `write_failed`. When that write fails too, the crawl file keeps the Crawl State `running`, which `060-add-crawl-control` reports as `interrupted`, and the Command prints no result, only the error `crawl_write_failed`, and exits with code 7.

For every non-zero exit, stderr SHALL hold exactly one error diagnostic, as its last line.

#### Scenario: The result counts a small site
- **WHEN** `/` links to `/a`, `/b` and `/missing` (which returns 404), and `linx crawl {site}/` ends
- **THEN** stdout holds `"state": "completed"`, `"urls": {"discovered": 4, "fetched": 4, "errors": 0, "skipped": 0, "queued": 0}`, `"pages": 3` and `"status_classes": {"2xx": 3, "3xx": 0, "4xx": 1, "5xx": 0, "other": 0}`

#### Scenario: A completed Crawl exits with code 0
- **WHEN** `linx crawl {site}/` ends with the Crawl State `completed`
- **THEN** the exit code is 0

#### Scenario: The crawl Command prints one document
- **WHEN** `linx commands` runs
- **THEN** its `crawl` entry has `"output": "document"`

#### Scenario: A write failure fails the Crawl
- **WHEN** SQLite reports that the disk is full while the Crawl writes
- **THEN** the Command exits with code 7, stdout holds the result with `"state": "failed"`, and the last stderr line is an error with `code` = `crawl_write_failed`

### Requirement: Unreachable Seed

**In short:** a Seed whose origin never answers pauses the Crawl at once, and when `--network-wait` runs out the Crawl fails with `seed_unreachable`, exit code 8.

Until the Seed's origin has given an HTTP response, a robots.txt or Seed request that gets none (see "Backstops" for what counts) SHALL pause the Crawl at once, with the probes, outcomes and `--network-wait` of the network pause, because a network may come up or switch just as a Crawl starts. When a probe answers, the Seed's robots.txt and the Seed SHALL be requested again. When no probe that starts within `--network-wait` answers, the Crawl SHALL end with the Crawl State `failed` and `stop_reason` = `seed_unreachable`, and it SHALL stay resumable. The Command SHALL:
- print the result
- write exactly one error diagnostic, with code `seed_unreachable` and a hint that mentions network access and sandboxed agents and says how long the Crawl waited
- exit with code 8

This lets an agent tell a site that is down, or a blocked network, from an empty site.

#### Scenario: An unreachable Seed fails the Crawl
- **WHEN** `linx crawl http://127.0.0.1:{closed_port}/ --network-wait 0` runs, and nothing listens on that port
- **THEN** the Command exits with code 8 and stdout holds the result with `"state": "failed"` and `"stop_reason": "seed_unreachable"`

#### Scenario: An unreachable Seed is reported by one error
- **WHEN** `linx crawl http://127.0.0.1:{closed_port}/ --network-wait 0` runs, and nothing listens on that port
- **THEN** stderr holds exactly one error line, as its last line, with `code` = `seed_unreachable`

#### Scenario: A failed Crawl is continued once its Seed answers
- **WHEN** a Crawl of `http://127.0.0.1:{port}/` with `--network-wait 0` has failed because nothing listened, the fixture site then starts on that port, and the Crawl Service continues the Crawl
- **THEN** the Crawl ends with the Crawl State `completed`, and `http://127.0.0.1:{port}/` has `fetch_state` = `fetched`

#### Scenario: A Seed that answers late is crawled
- **WHEN** a fake Fetcher gets no response for any request until 12 seconds of clock time have passed, and a Crawl of `{site}/` runs with a fake clock
- **THEN** the Seed is probed 3 times, the Crawl State is `completed`, and `{site}/` has `fetch_state` = `fetched`

### Requirement: Stopping with an interrupt

**In short:** the first interrupt stops the Crawl gracefully, so it can be continued, with exit code 130; a second ends the process at once.

The first interrupt SHALL stop a foreground Crawl gracefully. An interrupt is Ctrl+C; on Windows also Ctrl+Break; on macOS and Linux also SIGTERM and SIGHUP. After the first interrupt, the Command SHALL:
1. write a `stopping` event and start no new request
2. give requests in flight up to 10 seconds, then cancel those still running, whose URLs stay `queued`; a URL whose response was already handed to the writer SHALL still be recorded
3. store everything received and run the post-crawl passes
4. end the Crawl with the Crawl State `stopped` and `stop_reason` = `interrupt`
5. print the result, write exactly one error diagnostic with code `interrupted`, and exit with code 130

URLs not completed SHALL stay `queued`, so the Crawl can be continued. A second interrupt SHALL end the process at once, and the Crawl SHALL still be continuable.

#### Scenario: Ctrl+C stops a Crawl on macOS and Linux
- **WHEN** SIGINT is sent to a `linx crawl {site}/` subprocess after 3 pages of a 30-page fixture site are fetched
- **THEN** it exits with code 130 and stdout holds `"state": "stopped"` and `"stop_reason": "interrupt"`

#### Scenario: Ctrl+Break stops a Crawl on Windows (Windows)
- **WHEN** CTRL_BREAK_EVENT is sent to a `linx crawl {site}/` subprocess started in a new process group, after 3 pages of a 30-page fixture site are fetched
- **THEN** it exits with code 130 and stdout holds `"state": "stopped"` and `"stop_reason": "interrupt"`

#### Scenario: An interrupt is reported by one error
- **WHEN** SIGINT (CTRL_BREAK_EVENT on Windows) stops a `linx crawl {site}/` subprocess
- **THEN** stderr holds exactly one error line, as its last line, with `code` = `interrupted`

#### Scenario: An interrupted Crawl keeps its queue
- **WHEN** a Crawl of a 30-page fixture site is stopped by an interrupt after 3 pages are fetched
- **THEN** the `urls` table has at least one row with `fetch_state` = `queued`

#### Scenario: A request still running after the grace period is cancelled
- **WHEN** a fake Fetcher never answers for `{site}/hang`, the Crawl is stopped through the Crawl Service's stop flag while `/hang` is in flight, and a fake clock passes 10 seconds
- **THEN** the Crawl ends with the Crawl State `stopped`, and `{site}/hang` has `fetch_state` = `queued`

#### Scenario: A second interrupt ends the process at once
- **WHEN** a second interrupt follows the first while `/hang` (which answers after 60 seconds) is in flight
- **THEN** the subprocess exits within 2 seconds of the second interrupt, and `{site}/hang` has `fetch_state` = `queued`

#### Scenario: A stop ends a pause
- **WHEN** `/` links to `/down/1` to `/down/20`, each of which resets its connection, `linx crawl {site}/ --concurrency 1 --network-wait 1800` runs as a subprocess, and SIGINT (CTRL_BREAK_EVENT on Windows) is sent once stderr holds its `crawl_paused` event
- **THEN** the Command exits with code 130, stdout holds `"state": "stopped"` and `"stop_reason": "interrupt"`, and the site gets no request for `/` after the interrupt

## ADDED Requirements

### Requirement: Crawl settings in openlinx.toml

**In short:** every crawl setting has a key in the `[crawl]` table of `openlinx.toml`, under `010`'s naming rule and precedence.

Every crawl setting SHALL also be settable in the `[crawl]` table of `openlinx.toml`, which this change registers and later changes add keys to, under the naming rule of `010-add-workspace-and-cli-contract`: the flag's long name without the leading dashes, with `-` replaced by `_`. The Seed argument and `--subdomains` SHALL have no key, because `scope` covers `--subdomains`. `010`'s precedence SHALL apply: flag, then `openlinx.toml`, then the built-in default.

Secret settings SHALL be allowed in `openlinx.toml`. `015-add-crawl-store` redacts them in the recorded config.

#### Scenario: openlinx.toml sets a crawl setting
- **WHEN** `openlinx.toml` holds `[crawl]` with `concurrency = 2`, and `linx crawl {site}/` ends
- **THEN** the `crawl` table of `crawl.config` has `concurrency` = 2

#### Scenario: A flag overrides openlinx.toml
- **WHEN** `openlinx.toml` holds `[crawl]` with `concurrency = 2`, and `linx crawl {site}/ --concurrency 3` ends
- **THEN** the `crawl` table of `crawl.config` has `concurrency` = 3
