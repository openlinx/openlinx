# Crawling

How `spider crawl` decides what a URL is, which URLs it requests and how it records them. The spec is [openspec/changes/020-add-crawl-core/specs/crawling/spec.md](../openspec/changes/020-add-crawl-core/specs/crawling/spec.md). Terms follow [CONTEXT.md](../CONTEXT.md).

## The `spider crawl` Command

`spider crawl <url>` crawls a site in Spider mode from one Seed, in the foreground, and records every URL in a new crawl file of the Workspace (`.spider/crawls/<crawl id>.sqlite`). The Seed is an http or https URL, or a host such as `site.test`, which gets `https://` (see [Seeds](#seeds)); it is written to `seeds` as given.

```
spider crawl site.test
spider crawl https://site.test/shop/ --concurrency 2
```

The Crawl requests the Seed, reads the Links of each response it parses, and follows the hyperlinks in its Scope, Crawl Depth by Crawl Depth: every URL at one depth is requested before any URL one deeper, in the order the URLs were first recorded (`urls.id`). The `urls` table is the queue: a URL waits there as `queued` until its response is recorded, and a URL found twice is recorded once. A response is parsed for Links when its status is 2xx and its `Content-Type` is HTML (`text/html` or `application/xhtml+xml`); a PDF, an image or a response without a `Content-Type` is recorded but not parsed.

### Options and `[crawl]` settings

Every crawl setting is an option of `spider crawl` and a key of the `[crawl]` table of `spider.toml`, named after the option's long name without its dashes and with `-` as `_`. A flag beats `spider.toml`, which beats the built-in default. `crawl.config` records the resolved value of every setting of every table, secrets as `***`.

| Option | `[crawl]` key | Default | Meaning |
|---|---|---|---|
| `--concurrency <n>` | `concurrency` | `5` | The most requests in flight to one host. For now the Crawl makes one request at a time, so it never goes above this. |

`--workspace` and `--format` are the global flags of every Command.

### Events

While it runs, the Command writes events to stderr, one JSON object per line, as `{event, ts, data}` (see [the CLI contract](cli.md#progress-events)):

| `event` | When | `data` |
|---|---|---|
| `crawl_started` | once the crawl file exists, before any other event | `crawl_id`, `crawl_mode`, `seed_count`, `crawl_file` |

Warnings are written to stderr as diagnostics when they occur, and kept in the result.

### The result

When the Crawl ends, the Command prints one JSON object on stdout. Its counts come from the crawl file, so they are what an agent's own query over `urls` would count.

| Field | Meaning |
|---|---|
| `crawl_id` | The crawl id, also the crawl file's name. |
| `state` | The Crawl State: `completed` when nothing is left `queued`. |
| `stop_reason` | Why the Crawl ended early, or `null`. |
| `crawl_mode` | `spider`. |
| `seed` | The first Seed, as given. |
| `seed_count` | The number of Seeds. |
| `section_crawl` | Whether the Scope is one part of a site. |
| `started_at`, `ended_at` | UTC timestamps, `YYYY-MM-DDTHH:MM:SS.sssZ`. |
| `duration_s` | Seconds from `started_at` to `ended_at`. |
| `urls` | The counts of `urls` rows: `discovered` (all of them), and by `fetch_state`: `fetched`, `errors`, `skipped`, `queued`. |
| `pages` | URLs whose response was parsed (`parsed` = 1). |
| `status_classes` | URLs by the class of their status code: `2xx`, `3xx`, `4xx`, `5xx`, `other`. |
| `crawl_file` | The absolute path of the crawl file. |
| `warnings` | Every warning of the Crawl, in the full diagnostic shape: `level`, `code`, `message`, `hint`, `details`. |

```json
{"crawl_id": "20261014-101500-k3f9", "state": "completed", "stop_reason": null, "crawl_mode": "spider",
 "seed": "site.test", "seed_count": 1, "section_crawl": false,
 "started_at": "2026-10-14T10:15:00.123Z", "ended_at": "2026-10-14T10:15:04.456Z", "duration_s": 4.333,
 "urls": {"discovered": 4, "fetched": 4, "errors": 0, "skipped": 0, "queued": 0}, "pages": 3,
 "status_classes": {"2xx": 3, "3xx": 0, "4xx": 1, "5xx": 0, "other": 0},
 "crawl_file": "/home/me/shop/.spider/crawls/20261014-101500-k3f9.sqlite", "warnings": []}
```

### Exit codes

| Exit code | When | Error code |
|---|---|---|
| 0 | the Crawl is `completed` | |
| 2 | the Seed is not a valid http or https URL, or an option value is not allowed; no crawl file is created | `invalid_url` (with `details.reason`: `malformed`, `unsupported_scheme`, `userinfo`, `missing_host` or `invalid_host`), `invalid_value` |
| 3 | `spider.toml` is invalid | `settings_invalid` |
| 5 | another connection held the crawl file for longer than the writer waits | `crawl_busy` |
| 7 | the Workspace or the crawl file cannot be written | `workspace_not_writable`, `crawl_not_writable` |

A Seed with a user name or password is refused, and the error never repeats it: give the URL without them. Credentials for a site will be an option of their own (`--auth`, planned for v0.2).

## URLs

Every URL is identified by its normalised form. The Crawl requests that form and records it in `urls.url`, so two spellings of one URL are one row.

### Normalisation

| Rule | Given | Recorded |
|---|---|---|
| The scheme and host are lower-cased | `HTTP://Site.TEST/About` | `http://site.test/About` |
| The fragment is removed | `http://site.test/a#team` | `http://site.test/a` |
| A default port (80 for http, 443 for https) is removed; any other is kept | `https://site.test:443/a`, `https://site.test:8443/a` | `https://site.test/a`, `https://site.test:8443/a` |
| `.` and `..` path segments are resolved | `https://site.test/a/./b/../c` | `https://site.test/a/c` |
| An empty path is `/` | `https://site.test` | `https://site.test/` |
| Percent-encodings get upper-case hex digits, and those of unreserved characters (letters, digits, `-`, `.`, `_`, `~`) are decoded | `http://site.test/%7euser/a%2fb` | `http://site.test/~user/a%2Fb` |
| Characters a URL may not hold are percent-encoded as UTF-8: a space, a stray `%`, and `[` or `]` outside an IPv6 host included | `http://site.test/café?q=ü` | `http://site.test/caf%C3%A9?q=%C3%BC` |
| An internationalised host becomes ASCII | `http://bücher.test/` | `http://xn--bcher-kva.test/` |
| An IPv6 address takes its short form | `http://[2001:DB8:0:0::1]/` | `http://[2001:db8::1]/` |

What normalisation never changes:
- **The letter case of the path.** `/About` and `/about` are two URLs, as they are to most servers.
- **The query.** Its parameters keep their order and their values, and only their percent-encodings are normalised. Only `--strip-params` removes parameters.
- **A trailing slash.** `/a` and `/a/` are two URLs. Which of them redirects to the other, if either does, is itself a finding, so the Crawl keeps both.

**Hosts** are encoded the way aiohttp, the HTTP client, encodes them, so the host recorded is always the host requested. A host that is not ASCII goes through IDNA's UTS46 mapping, as browsers do: `faß.test` is `xn--fa-hia.test`, never `fass.test`. A host with characters that UTS46 would delete without a trace, such as a zero-width space, is refused, so `e<U+200B>vil.test` cannot pass for `evil.test`.

**Rejected:** a URL that is not http or https, that has no host, whose port is not a number up to 65535 (`http://site.test:99999/`), whose host holds a character a host name may not (`http://exa mple.test/`), or whose bracketed host is not an IPv6 address (`http://[v1.x]/`). A host that only cannot resolve, such as `a..b.test`, is not rejected: it is requested, and its DNS error is recorded. So is a URL with a user name or password (`https://user:pass@site.test/`): kept, the credentials would be recorded in the crawl file and sent with every request; dropped, the URL would silently become another one. A rejected Seed fails the Command with `invalid_url` before any request is made; a rejected Link target is not requested.

### Seeds

The Seed is the URL given to `spider crawl`. Without a scheme it gets `https://`: `site.test/shop` is the Seed `https://site.test/shop`.

A Seed has a scheme when it starts with a scheme name and `:`, unless a port number follows the `:`:

| Seed | Read as |
|---|---|
| `site.test/shop` | `https://site.test/shop` |
| `site.test:8080/shop`, `localhost:8080` | a host and a port: `https://site.test:8080/shop`, `https://localhost:8080/` |
| `http://site.test/` | `http://site.test/` |
| `mailto:a@b.test`, `javascript:alert(1)`, `ftp://site.test/` | rejected with `invalid_url`: not http or https |

The `seeds` table keeps the Seed exactly as given, and `urls` holds its normalised form.

### Stripping query parameters

`--strip-params <patterns>` removes every query parameter whose name matches one of the comma-separated patterns, before the URL is recorded or requested:
- In a pattern, `*` matches any run of characters and `?` matches one character. Every other character matches itself, and case counts.
- The flag can be given more than once.
- The remaining parameters keep their order, and a query left empty is removed together with its `?`.
- A name is matched after its percent-encodings are normalised, so `utm_*` also removes `utm%5Fsource`.

```
spider crawl site.test --strip-params "utm_*,fbclid"
http://site.test/p?utm_source=x&id=7&fbclid=y   ->   http://site.test/p?id=7
http://site.test/p?a=1&b=2 with "*"               ->   http://site.test/p
```

URLs that differ only in stripped parameters are one URL, so the Crawl requests it once.

## Scope

The Scope decides which URLs a Crawl follows. Every recorded URL is either an Internal URL or an External URL, and either in the Scope or outside it.

### Internal and External URLs

A URL is internal when its host is a Seed host, whatever its scheme and port: for the Seed `http://site.test/`, `https://site.test:8443/x` is internal too. The Seed hosts are:
- the Seed's host
- `www.` followed by the Seed's host, when the Seed's host is a registrable domain (an apex, such as `site.test` or `shop.co.uk`)

| Seed | URL | |
|---|---|---|
| `site.test` | `https://www.site.test/` | internal: the www host of an apex Seed |
| `www.site.test` | `https://site.test/` | external |
| `site.test` | `https://blog.site.test/` | external, unless `--scope subdomains` |
| `co.uk` | `https://www.co.uk/` | external: `co.uk` is a public suffix, not a registrable domain |
| `127.0.0.1:8765` | `http://127.0.0.1:9000/` | internal: another port of the Seed host |
| `site.test.` | `https://site.test/` | internal: one trailing dot is ignored |
| `127.0.0.1` | `http://127.1/` | external: another spelling of an address is another host |

**Why the www rule goes one way.** A site on `site.test` usually also answers on `www.site.test`, so an apex Seed covers both. The reverse would quietly widen a Crawl of `www.site.test` to a host the user did not name. When a site really lives on the apex, a `www.` Seed gets a `seed_base_mismatch` warning, and the Crawl stays in its Scope. An IP address and a single-label host such as `localhost` have no `www.` host.

Registrable domains come from a copy of the [Public Suffix List](https://publicsuffix.org/) bundled with the tool, which is never downloaded during a Crawl. So `shop.co.uk` and `user.github.io` are registrable domains, while `co.uk` and `github.io` are public suffixes.

Hosts are compared ignoring one trailing dot, because DNS treats `site.test.` and `site.test` as one name. The two URLs are still recorded as two rows. Other spellings of an IP address, such as `127.1` or `0x7f.0.0.1`, are not converted: they are internal only when they are written exactly as the Seed host is.

### `--scope`

| Value | In the Scope |
|---|---|
| `host` (the default) | the Internal URLs |
| `subdomains`, or the shorthand `--subdomains` | also every host whose registrable domain is the Seed host's: for the Seed `www.site.test`, `blog.site.test` and `a.b.site.test`, but not `othersite.test` |
| `subfolder` | only Internal URLs whose path starts with the Seed's folder |

The Seed's folder is its path up to and including its last `/`: the Seed `http://site.test/blog/post-1` has the folder `/blog/`. A Seed whose folder would be `/`, such as `http://site.test/blog` without its trailing slash, is rejected with `subfolder_is_root`, whose hint gives the Seed with the slash.

### Include and exclude patterns

`--include <regex>` and `--exclude <regex>` take Python regular expressions. Each can be given more than once, and each pattern is searched for anywhere in the normalised URL, with case counting.

- **`--exclude`:** a URL that matches is never requested, internal or external. It is recorded with `fetch_state` = `skipped` and `skip_reason` = `excluded`. Use it to keep a Crawl away from logout links, cart actions and endless calendars.
- **`--include`:** when given, an Internal URL that matches no include pattern is outside the Scope. It is still requested once to record its response, but it is not followed.
- **Exclude wins:** a URL that matches both is skipped.

```
spider crawl site.test/blog/ --include "/blog/" --exclude "draft"
http://site.test/blog/a        in the Scope
http://site.test/news/n        internal, outside the Scope: checked, not followed
http://site.test/blog/draft-1  skipped: excluded
```

An invalid pattern is rejected with `invalid_pattern` before any crawl file is created, and so is a Seed outside its own Scope, such as one that an exclude pattern matches (`seed_out_of_scope`).

**Slow patterns.** Every pattern runs against every URL the Crawl finds, and the URLs come from the site. A pattern with nested quantifiers, such as `(a+)+$`, can take seconds on one long URL. Prefer plain substrings and anchors, such as `/logout$` or `\?sessionid=`.

## Links

The Crawl reads Links from every response it parses: an in-Scope 2xx HTML response, plus the HTTP `Link` and `Refresh` headers of every in-Scope 2xx response, such as a PDF's canonical header. Each Link records its type, its normalised target, the element and attribute it came from, its `rel` tokens, and its `ordinal`: its position in the response, from 1, with header Links first and HTML Links after them in document order.

### Resolving a reference

- Spaces and control characters around a reference are removed, and so are tabs and newlines inside it, as browsers do.
- References are read as browsers read them (the [URL Standard](https://url.spec.whatwg.org/)): in an http or https URL a backslash before the query is a slash, so a link written with backslashes is not reported as broken; `///cdn.test/x` names the host `cdn.test`; and `https:cdn.test/x` on an http Page is `https://cdn.test/x`.
- On a Page whose encoding is neither UTF-8 nor UTF-16, such as windows-1251, the query is percent-encoded in that encoding, as a browser requests it: `?q=й` becomes `?q=%E9`. The path is always encoded as UTF-8.
- A relative reference is resolved against the Page's first `<base href>`, and otherwise against the response URL. For `<base href="http://site.test/docs/">`, `href="guide"` is `http://site.test/docs/guide`. A base that is not http or https, such as `javascript:void(0)`, resolves no relative reference, as in a browser.
- The result is normalised (see URLs).
- A reference gives no Link when its scheme is not http or https (`mailto:`, `tel:`, `javascript:`, `data:`), when it holds a user name, or when it cannot be resolved or normalised, such as `http://[bad/x` or `//`. An empty `src`, `data` or `poster` names no file and gives no Link; an empty `href` links to the Page itself. The next references on the Page are still read.

### Link types

| Link type | Found in | Requested |
|---|---|---|
| `hyperlink` | `<a href>`, `<area href>` | yes |
| `canonical` | `<link rel="canonical">`; an HTTP `Link` header with `rel="canonical"` | yes |
| `pagination` | `<link rel>` `next`, `prev` or `previous`; the same in an HTTP `Link` header | yes |
| `hreflang` | `<link rel="alternate" hreflang>`; the same in an HTTP `Link` header | yes |
| `iframe` | `<iframe src>`, `<frame src>` | yes |
| `meta_refresh` | the URL in `<meta http-equiv="refresh" content="0; url=…">` | yes |
| `http_refresh` | the URL in an HTTP `Refresh` header | yes |
| `image` | `<img src>`; every candidate in the `srcset` of `<img>` and `<source>`; `<video poster>` | as a Resource |
| `css` | `<link rel="stylesheet">` | as a Resource |
| `javascript` | `<script src>` | as a Resource |
| `video` | `<video src>`; the `src` of a `<source>` or `<track>` inside `<video>` | as a Resource |
| `audio` | `<audio src>`; the `src` of a `<source>` or `<track>` inside `<audio>` | as a Resource |
| `media` | `<embed src>`, `<object data>` | as a Resource |
| `amphtml` | `<link rel="amphtml">` | no |
| `mobile_alternate` | `<link rel="alternate" media>` without `hreflang` | no |
| `misc` | `<link href>` with any other `rel`, such as `icon`, `manifest`, `preload`, or a feed's `alternate` | no |

- A Resource is checked: requested once to record its response, and parsed only when it turns out to be in-Scope HTML.
- A URL reached only through Links that are not requested is recorded with `fetch_state` = `skipped` and `skip_reason` = `link_type_not_followed`.
- `<link rel="preconnect">` and `rel="dns-prefetch"` name an origin to connect to, not a file, so they give no Link.
- `rel` tokens are compared without case: `rel="NoFollow"` is `nofollow`.

The same list of types also holds, from v0.1, the types of later releases: `xml_sitemap` (a URL listed in an XML sitemap) and `sitemap_hreflang` (an hreflang alternate in a sitemap) in v0.2, and `javascript_redirect` in v1.1, with JavaScript rendering. A URL's `discovered_via` is the type of the Link it was first found through, or `seed`.

HTTP redirects, HSTS, fonts in CSS, SWF and PDF are not Link types: a redirect is the redirecting URL's `redirect_url_id`, and a PDF is a content type.

### Decoding

HTML is decoded by the first of these that applies, and bytes that are invalid in the chosen encoding become replacement characters (`�`), so a Page with broken bytes is still read:

1. a byte order mark (UTF-8, UTF-16LE or UTF-16BE)
2. the `charset` parameter of the `Content-Type` header
3. a `<meta charset>` or `<meta http-equiv="Content-Type">` declaration in the first 1024 bytes
4. UTF-8, or windows-1252 when the body is not valid UTF-8

Encoding labels are those of the [Encoding Standard](https://encoding.spec.whatwg.org/), as browsers read them: `iso-8859-1` and `ascii` mean windows-1252, `iso-8859-9` means windows-1254, and `shift_jis`, `euc-kr` and `gb2312` mean their Windows supersets. A label the Standard does not list, such as `charset=nonsense`, is skipped, and the next source applies; so are `x-user-defined` and the labels of the Standard's replacement encoding. A `<meta>` declaration inside a comment is not read, a `<meta>` with an unknown label gives way to the next one, and a `<meta>` declaration of UTF-16 means UTF-8.
