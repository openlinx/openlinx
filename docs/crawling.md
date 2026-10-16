# Crawling

How `spider crawl` decides what a URL is, which URLs it requests and how it records them. The spec is [openspec/changes/020-add-crawl-core/specs/crawling/spec.md](../openspec/changes/020-add-crawl-core/specs/crawling/spec.md). Terms follow [CONTEXT.md](../CONTEXT.md).

## The `spider crawl` Command

`spider crawl <url>` crawls a site in Spider mode from one Seed, in the foreground, and records every URL in a new crawl file of the Workspace (`.spider/crawls/<crawl id>.sqlite`). The Seed is an http or https URL, or a host such as `site.test`, which gets `https://` (see [Seeds](#seeds)); it is written to `seeds` as given.

```
spider crawl site.test
spider crawl https://site.test/shop/ --concurrency 2
```

The Crawl requests the Seed, reads the Links of each response it parses, follows the hyperlinks in its Scope and checks the others, unless they are skipped (see [External URLs](#external-urls)), Crawl Depth by Crawl Depth (see [Crawl Depth](#crawl-depth)): every followed URL at one depth is done before any followed URL one deeper starts, and the URLs of a depth start in the order they were first recorded (`urls.id`), several at a time (see [Requests in flight](#requests-in-flight)). The `urls` table is the queue: a URL waits there as `queued` until its response is recorded, and a URL found twice is recorded once. A response is parsed for Links when its URL is in the Scope, its status is 2xx and its `Content-Type` is HTML (`text/html` or `application/xhtml+xml`); a PDF, an image, a response without a `Content-Type` or the response of an External URL is recorded but not parsed.

### Options and `[crawl]` settings

Every crawl setting is an option of `spider crawl` and a key of the `[crawl]` table of `spider.toml`, named after the option's long name without its dashes and with `-` as `_`. A flag beats `spider.toml`, which beats the built-in default. `crawl.config` records the resolved value of every setting of every table, secrets as `***`.

| Option | `[crawl]` key | Default | Meaning |
|---|---|---|---|
| `--concurrency <n>` | `concurrency` | `5` | The most requests in flight to one host, 1 to 50. |
| `--rate <n>` | `rate` | none | The most requests per second that start to one host, robots.txt's included: a finite number above 0, such as `0.5` or `2` (see [Requests in flight](#requests-in-flight)). |
| `--check-external` / `--no-check-external` | `check_external` | `true` | Request each External URL once to record its response; with `--no-check-external`, record it as skipped, unrequested (see [External URLs](#external-urls)). |
| `--follow-nofollow` | `follow_nofollow` | `false` | Follow nofollow hyperlinks, and every hyperlink of a Page whose robots directives say nofollow, like any other hyperlink (see [Nofollow](#nofollow)). |
| `--scope <kind>` | `scope` | `host` | Which Internal URLs are in the Scope: `host`, `subdomains` or `subfolder` (see [`--scope`](#--scope)). |
| `--subdomains` | | | The same as `--scope subdomains`; it has no key of its own. |
| `--strip-params <globs>` | `strip_params` | `[]` | Query parameters removed from every URL before it is recorded or requested (see [Stripping query parameters](#stripping-query-parameters)). |
| `--include <regex>` | `include` | `[]` | When given, an Internal URL that matches no include pattern is checked but not followed; give the option once per pattern. |
| `--exclude <regex>` | `exclude` | `[]` | A URL that the pattern matches is never requested; give the option once per pattern (see [Include and exclude patterns](#include-and-exclude-patterns)). |
| `--max-depth <n>` | `max_depth` | none | The deepest Crawl Depth whose URLs are requested, 0 or more; Resources of followed Pages are requested one deeper (see [Crawl Depth](#crawl-depth)). |
| `--max-urls <n>` | `max_urls` | none | The most URL requests the Crawl starts, 1 or more (see [The URL limit](#the-url-limit)). |
| `--ignore-robots` | `ignore_robots` | `false` | Request URLs that robots.txt disallows; they are still recorded with `blocked_by_robots_txt` = 1 (see [`--ignore-robots`](#--ignore-robots)). |
| `--robots-user-agent <token>` | `robots_user_agent` | `spider` | The token that selects robots.txt groups and crawler-prefixed `X-Robots-Tag` values (see [The robots user-agent token](#the-robots-user-agent-token)). |

`--workspace` and `--format` are the global flags of every Command.

### Requests in flight

URLs are requested concurrently, and three limits bound them:

- **Per host:** at most `--concurrency` requests to one host at a time, 5 by default. The host is the URL's host, whatever its scheme or port.
- **In all:** at most 4 × `--concurrency` URLs in progress at once, kept within 20 to 100, so a Page that links to many External hosts never opens hundreds of connections.
- **Per host in time:** with `--rate <n>`, requests to one host start at least 1/n seconds apart, its robots.txt request included, so `--rate 2` starts at most two a second. A request waiting for its turn takes no place in the limit in all. Without `--rate`, only `--concurrency` holds requests back.

So by default a Crawl sends at most 5 requests at once to a host, as fast as the host answers. robots.txt's `Crawl-delay` is not applied (see [robots.txt](#robotstxt)): give `--rate` to slow a Crawl down.

When 10 responses in a row from one Internal host have status 403 or 429, the result holds a `possible_blocking` warning for that host, once in a Crawl, whose hint names `--rate` and `--concurrency`, and the Crawl goes on. Only a URL's own responses count, in the order they complete, not robots.txt's. A response with any other status ends the run, and a request without an HTTP response neither counts nor ends it.

### Crawl Depth

The Seed has `crawl_depth` = 0, and every other URL the fewest Links followed from the Seed to reach it, whatever order the responses come in. A Resource is one deeper than the Page that references it.

- **The depth barrier:** a Crawl Depth ends only when every followed URL of it is done, an Internal URL in the Scope reached by a Link that is not a Resource. A followed URL one deeper never starts before that, so a slow Page holds the next depth back, and the depth stays the shortest path.
- **Checks never wait:** External URLs, URLs outside the Scope and Resources are checks. They start in their depth's turn but never hold the next depth back, so a slow image or a slow outbound link costs no time.
- **A check that is HTML:** a Resource Link to in-Scope HTML is parsed when it answers, even after its depth has ended. When nothing is left to start, the Crawl waits for every check and reads the queue again from the smallest depth, so what such a check found is still crawled. A URL it reaches that is still `queued`, or in flight, takes the shorter depth, and the URLs found on a URL are recorded one deeper than its depth as the crawl file holds it; a URL already fetched keeps its depth.

With `--max-depth <n>`, a URL deeper than `n` is not requested: it is recorded with `fetch_state` = `skipped` and `skip_reason` = `max_depth`. Resources of followed Pages are the exception, one deeper than `n` and no deeper, so with `--max-depth 0` the Seed's images are still checked. A URL that a Page reaches through a Resource Link is a Resource, even when the Page also hyperlinks it; one that another Page hyperlinked first stays a followed URL. There is no depth limit by default.

The rows of `spider crawl site.test --max-depth 1`, for a Seed that links to `/a` and holds `/logo.png`, where `/a` links to `/b` and holds `/a.png`:

```
http://site.test/          depth 0, fetched
http://site.test/a         depth 1, fetched
http://site.test/logo.png  depth 1, fetched (a Resource of /)
http://site.test/b         depth 2, skipped: max_depth
http://site.test/a.png     depth 2, fetched (a Resource of /a)
```

### The URL limit

There is no URL limit by default. With `--max-urls <n>`, the Crawl starts at most `n` URL requests:

- A request counts from the moment it starts, so requests in flight count. A URL recorded without a request, such as an excluded one, does not count, and neither do robots.txt requests.
- At the first request the limit refuses, nothing new starts. The requests in flight end and are recorded, and every URL not requested stays `queued`.
- The Crawl ends `stopped` with `crawl.stop_reason` = `max_urls`, and exits with code 0. Its post-crawl passes have run, as for a `completed` Crawl.
- The result holds a `max_urls_reached` warning whose hint is the command that continues the Crawl with twice the limit, such as `spider resume --crawl 20261014-101500-k3f9 --max-urls 6`.
- A site with exactly `n` URLs ends `completed`, since no request was refused.

A value below 1 is rejected with `invalid_value` (exit 2) on the command line, and with `settings_invalid` (exit 3) in `spider.toml`.

### Events

While it runs, the Command writes events to stderr, one JSON object per line, as `{event, ts, data}` (see [the CLI contract](cli.md#progress-events)):

| `event` | When | `data` |
|---|---|---|
| `crawl_started` | once the crawl file exists, before any other event | `crawl_id`, `crawl_mode`, `seed_count`, `crawl_file`, `parse_workers` (the processes that prepare Pages besides the crawl process; 0 while Pages are prepared in it) |

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
| 0 | the Crawl is `completed`, or `stopped` by `--max-urls` | |
| 2 | the Seed is not a valid http or https URL, a pattern is not a valid regular expression, or an option value is not allowed; no crawl file is created | `invalid_url` (with `details.reason`: `malformed`, `unsupported_scheme`, `userinfo`, `missing_host` or `invalid_host`), `invalid_pattern` (with `details.pattern`), `invalid_value` |
| 3 | `spider.toml` is invalid | `settings_invalid` |
| 5 | another connection held the crawl file for longer than the writer waits | `crawl_busy` |
| 7 | the Workspace or the crawl file cannot be written | `workspace_not_writable`, `crawl_not_writable` |

A Seed with a user name or password is refused, and the error never repeats it: give the URL without them. Credentials for a site will be an option of their own (`--auth`, planned for v0.2).

When the crawl file itself cannot be written, for example on a full disk, the Crawl stops requesting URLs and the Command ends with the writer's error: `crawl_busy` (exit 5) for a file another connection holds, otherwise `internal_error`. The crawl file is left `running`, with every URL recorded so far. A later release reports this as `crawl_write_failed` and records the Crawl as `failed`.

### When one URL fails

One URL never stops the Crawl: what goes wrong with it is recorded on its row, and the Crawl goes on.

| What fails | How the URL is recorded |
|---|---|
| The request gets no HTTP response | `fetch_state` = `error`, `status_code` NULL, and a `fetch_error` code with its detail in `fetch_error_message`: `dns_error` (the host name does not resolve, or cannot be looked up, such as `a..b.test`), `connection_refused` (nothing listens on the port), `invalid_response` (the answer is not HTTP), `tls_error` (the TLS handshake failed, such as a self-signed or expired certificate), `connection_error` (any other failure, a connection reset in the middle of the body included) |
| The body has bytes its character encoding cannot hold | Nothing: they are decoded as replacement characters, and the Page is parsed as usual. |
| A registered extractor raises an error | `parsed` stays 1 and the Page's Links are followed; `parse_error` = `extractor_error`, and `parse_error_message` names the extractor and the error's type, such as `title: ValueError`. Only that extractor's output is missing. |
| A registered handler raises an error | The URL is recorded without that handler's rows; the other handlers' rows are kept. |
| The URL's rows cannot be written | The URL alone is recorded, with `fetch_state` = `error`, `fetch_error` = `record_failed` and the error in `fetch_error_message`, without the URLs found on it or its handlers' rows. This holds for a value the file refuses (a constraint, a value too big, a value that cannot be bound) and for an error of the tool's own row code; any other database error stops the Crawl, as above. |
| The URL matches an `--exclude` pattern | It is not requested: `fetch_state` = `skipped`, `skip_reason` = `excluded`, and no response columns. When only Links that are not followed reach it, its `skip_reason` is `nofollow` or `link_type_not_followed` instead. |
| Only nofollow Links reach the URL | It is not requested: `fetch_state` = `skipped`, `skip_reason` = `nofollow` (see [Nofollow](#nofollow)). |
| Only Links of a type that is not requested reach the URL | It is not requested: `fetch_state` = `skipped`, `skip_reason` = `link_type_not_followed` (see [Link types](#link-types)). |
| The URL is External, with `--no-check-external` | It is not requested: `fetch_state` = `skipped`, `skip_reason` = `external_not_checked`; an External URL that an `--exclude` pattern matches is `excluded`. |
| The URL is deeper than `--max-depth`, and no Resource | It is not requested: `fetch_state` = `skipped`, `skip_reason` = `max_depth` (see [Crawl Depth](#crawl-depth)). |

Each of the three failures of the tool's own code is reported by one counted warning, written to stderr when it first occurs and kept once in the result's `warnings`, however many URLs it affects:

| Code | Counts URLs where | `details` |
|---|---|---|
| `parse_failed` | an extractor failed, or a Page's preparation gave nothing (`body_too_large`, `worker_crashed`, `parse_timeout`) | `count`, `first_url` |
| `handler_failed` | a handler failed | `count`, `first_url` |
| `record_failed` | the rows could not be written | `count`, `first_url` |

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

URLs that differ only in stripped parameters are one URL, so the Crawl requests it once. The Seed is stripped too, and so are the targets of the HTTP `Link` and `Refresh` headers; the `seeds` table keeps the Seed as given.

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

**`seed_base_mismatch`.** The Seed's Page is read for this once, when its response is parsed. The warning comes when the Seed's host is `www.` followed by a registrable domain, its Page names the apex as the site, and the Seed on the apex is outside the Scope. The Page's first `canonical` Link to the apex or to the Seed's host, from `<link rel="canonical">` or a `Link` header, decides: one to the apex names the apex, and one to the Seed's host says www is the site. Without one, the Page names the apex when more of its `hyperlink` Links go to the apex than to the Seed's host. So `--scope subdomains`, which crawls the apex already, gives no warning. Its hint gives the Seed on the apex, with the scheme, port and path kept, and `details` holds `seed` and `apex_seed`. For the Seed `http://www.site.test/` whose canonical is `http://site.test/`, the hint is "Give http://site.test/ as the Seed to crawl the site its Page names." The Crawl goes on in the Scope it was given; the warning only tells you the Seed may be the wrong one. A Seed whose hyperlinks stay on `www.site.test` gets no warning.

Registrable domains come from a copy of the [Public Suffix List](https://publicsuffix.org/) bundled with the tool, which is never downloaded during a Crawl. So `shop.co.uk` and `user.github.io` are registrable domains, while `co.uk` and `github.io` are public suffixes.

Hosts are compared ignoring one trailing dot, because DNS treats `site.test.` and `site.test` as one name. The two URLs are still recorded as two rows. Other spellings of an IP address, such as `127.1` or `0x7f.0.0.1`, are not converted: they are internal only when they are written exactly as the Seed host is.

Each URL's row says what it is: `urls.is_internal` is 1 for an Internal URL, and `urls.in_scope` is 1 when the URL is in the Scope, so it may be followed. An excluded URL has `in_scope` = 0.

### External URLs

A hyperlink to an External URL is checked, not followed: the URL is requested once, its response is recorded (`status_code`, `content_type`, `response_time_ms`), and it is never parsed, so `parsed` = 0 and nothing it links to is recorded. A broken outbound link therefore shows as a 4xx or 5xx `status_code`, or as a `fetch_error`, such as `dns_error` for a host that no longer exists (see [When one URL fails](#when-one-url-fails)).

External URLs count against the same limits as internal ones: at most `--concurrency` requests to each External host, and the cap on URLs in progress in all.

With `--no-check-external`, no External URL is requested. Each one is still recorded, with `fetch_state` = `skipped` and `skip_reason` = `external_not_checked`, so the Links to it can be counted.

### Origins

Every URL belongs to an origin: its scheme, host and port, such as `https://site.test` or `http://site.test:8080`, with a default port left out. The `origins` table holds one row for each origin of a recorded URL, requested or not, with its `host` and whether its URLs are internal (`is_internal`), and `urls.origin_id` points to it. `http://site.test` and `https://site.test` are two origins of one host. The row also records the origin's robots.txt (see [robots.txt](#robotstxt)).

### `--scope`

| Value | In the Scope |
|---|---|
| `host` (the default) | the Internal URLs |
| `subdomains`, or the shorthand `--subdomains` | also every host whose registrable domain is the Seed host's: for the Seed `www.site.test`, `blog.site.test` and `a.b.site.test`, but not `othersite.test` |
| `subfolder` | only Internal URLs whose path starts with the Seed's folder |

`--subdomains` with another `--scope` value, such as `--subdomains --scope subfolder`, is rejected with `option_conflict`. `scope` is also a key of the settings file's `[crawl]` table; `--subdomains` has none, and on the command line it overrides the file's `scope`, as every option overrides its setting.

The Seed's folder is its path up to and including its last `/`: the Seed `http://site.test/blog/post-1` has the folder `/blog/`. A Seed whose folder would be `/`, such as `http://site.test/blog` without its trailing slash, is rejected with `subfolder_is_root`, whose hint gives the Seed with the slash. A root Seed, such as `http://site.test/`, is rejected too, since its folder is the whole site.

### Include and exclude patterns

`--include <regex>` and `--exclude <regex>` take Python regular expressions. Each can be given more than once, and each pattern is searched for anywhere in the normalised URL, with case counting.

- **`--exclude`:** a URL that matches is never requested, internal or external. It is recorded with `fetch_state` = `skipped` and `skip_reason` = `excluded`, unless only Links that are not followed reach it, which record it as `nofollow` or `link_type_not_followed`. Use it to keep a Crawl away from logout links, cart actions and endless calendars.
- **`--include`:** when given, an Internal URL that matches no include pattern is outside the Scope. It is still requested once to record its response, but it is not followed.
- **Exclude wins:** a URL that matches both is skipped.

```
spider crawl site.test/blog/ --include "/blog/" --exclude "draft"
http://site.test/blog/a        in the Scope
http://site.test/news/n        internal, outside the Scope: checked, not followed
http://site.test/blog/draft-1  skipped: excluded
```

An invalid pattern is rejected with `invalid_pattern` (the pattern in `details.pattern`) before any crawl file is created. A Seed outside its own Scope, one that an exclude pattern matches or that no include pattern matches, is rejected with `seed_out_of_scope` before any crawl file is created, since nothing would be crawled.

**Slow patterns.** Every pattern runs against every URL the Crawl finds, and the URLs come from the site. A pattern with nested quantifiers, such as `(a+)+$`, can take seconds on one long URL. Prefer plain substrings and anchors, such as `/logout$` or `\?sessionid=`.

### Section Crawls

A Crawl is a Section Crawl when its Scope is one part of a site: it uses `--scope subfolder` or at least one `--include` pattern. `--exclude` alone keeps a whole-site Crawl, since it only leaves some URLs out. The result's `section_crawl` and the column `crawl.section_crawl` say which it is, so a report can tell that the Pages it counts are a section, not the whole site.

### The recorded Scope

The Crawl records the Scope it resolved in `crawl.scope` when the crawl file is created, as a JSON object:

| Key | Value |
|---|---|
| `mode` | `host`, `subdomains` or `subfolder` |
| `hosts` | the Seed hosts, in the order of [Internal and External URLs](#internal-and-external-urls); with `--scope subdomains`, the registrable domains |
| `folder` | the Seed's folder with `--scope subfolder`, otherwise `null` |
| `include`, `exclude` | the patterns, as given |

```
spider crawl site.test/blog/ --scope subfolder --exclude "/draft"
{"mode": "subfolder", "hosts": ["site.test", "www.site.test"], "folder": "/blog/", "include": [], "exclude": ["/draft"]}
```

An agent reads it to know what a Crawl covered without parsing its command line.

## robots.txt

Before its first request to an origin, the Crawl requests the origin's `/robots.txt`, once per origin in a run, and obeys it for the robots user-agent token (see [The robots user-agent token](#the-robots-user-agent-token)). Every origin is asked: Internal ones, External ones and those of Resources. A URL recorded without a request, such as an excluded URL or an External URL under `--no-check-external`, never makes its origin's robots.txt be requested, and neither does a URL that the URL limit refuses.

- A robots.txt request goes through the same per-host limits as a URL's, but it is not recorded as a URL and does not count toward `--max-urls`.
- A redirected robots.txt is followed for up to 5 hops; a longer chain counts as missing.
- Only its first 512,000 bytes are parsed, without a line that this limit cuts, decoded as UTF-8 with replacement; a leading byte order mark is dropped. So a cut `Disallow: /private` never becomes the shorter `Disallow: /priv`.
- `Crawl-delay` is recorded, not applied; `--rate` spaces requests instead (see [Requests in flight](#requests-in-flight)).

### What the response means

| robots.txt response | `origins.robots_state` | The origin's URLs |
|---|---|---|
| 2xx | `ok` | Requested, unless its rules disallow them for the token: a disallowed URL is `skipped` with `skip_reason` = `blocked_by_robots_txt`. |
| 4xx other than 429, or more than 5 redirects | `missing` | All requested. |
| 5xx, 429, or a status outside 200–599 | `unreachable` | None requested: each is `skipped` with `skip_reason` = `robots_unreachable`. An Internal origin gives a `robots_unreachable` warning, once per host, whose hint names `--ignore-robots`. |
| No HTTP response | `unreachable` | None requested: each is `error`, with the `fetch_error` of the robots.txt request, such as `dns_error`, and a `fetch_error_message` that names that request. |

`urls.blocked_by_robots_txt` is 1 for a URL the rules disallow, 0 for one they allow, and NULL for a URL that was not checked: one skipped before robots.txt mattered, or one of an origin whose rules are unknown.

The origin's row keeps what robots.txt gave: `robots_state`, `robots_status_code` (of the final response), `robots_fetch_error` and `robots_fetch_error_message` (when there was no response), `robots_fetched_at`, `robots_txt` (the text as parsed), `robots_crawl_delay_ms` and `robots_sitemaps` (a JSON array of its `Sitemap:` URLs). They stay NULL while robots.txt has not been requested: it is requested for the origin's first URL that the Scope does not skip and the URL limit does not refuse, so an origin whose every URL robots.txt kept out still has them.

A Seed that robots.txt disallows is reported as a `seed_blocked_by_robots_txt` warning whose hint names `--ignore-robots`.

### `--ignore-robots`

With `--ignore-robots`, the Crawl requests the URLs that robots.txt disallows and still records `blocked_by_robots_txt` = 1 for them, since robots.txt is still read. It also requests the URLs of an origin whose robots.txt answered 5xx or 429, with `blocked_by_robots_txt` NULL. An origin whose robots.txt got no HTTP response still gives each of its URLs that error.

### The robots user-agent token

`--robots-user-agent <token>` (default `spider`) selects the robots.txt group that applies, and the `X-Robots-Tag` values with a crawler prefix (see [Robots directives](#robots-directives)). It is independent of the `User-Agent` request header. As RFC 9309 says, a token has only letters, `_` and `-`: any other is rejected, as `invalid_value` (exit code 2), or in `spider.toml` as `settings_invalid` (exit code 3).

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

- A Resource is checked: requested once to record its response, whenever its Page is followed, even one deeper than `--max-depth`, and parsed only when it turns out to be in-Scope HTML. A broken image shows as its 4xx or 5xx `status_code`.
- A URL reached only through Links that are not requested is recorded with `fetch_state` = `skipped` and `skip_reason` = `link_type_not_followed`. A Link that is requested, on the same Page or a later one, still requests it.
- `<link rel="preconnect">` and `rel="dns-prefetch"` name an origin to connect to, not a file, so they give no Link.
- `rel` tokens are compared without case: `rel="NoFollow"` is `nofollow`.
- In an HTTP `Link` header, a link-value with an `anchor` parameter describes another resource than the response, as RFC 8288 says, so it gives no Link.
- `<noscript>` is read as a browser that runs scripts reads it: as text, up to the next `</noscript>`, which never ends `<head>`, so a tracking pixel in a head `<noscript>` leaves the canonical, robots and hreflang declarations after it in `<head>`. Inside it, a `<link>` or `<meta>` gives no Link, and a `<title>`, `<base>` or robots `<meta>` is not read, as such a browser never sees them; the other elements there, such as `<a>` and `<img>`, give their Links, in document order, since a crawler without rendering finds every URL the raw HTML holds. That includes a pixel in a head `<noscript>`.
- Inside a `<template>`, nothing gives a Link: its content is markup that scripts copy into the Page, often with placeholder URLs such as `{{ item.url }}`.

The same list of types also holds, from v0.1, the types of later releases: `xml_sitemap` (a URL listed in an XML sitemap) and `sitemap_hreflang` (an hreflang alternate in a sitemap) in v0.2, and `javascript_redirect` in v1.1, with JavaScript rendering. A URL's `discovered_via` is the type of the Link it was first found through, or `seed`, and `found_on_url_id` points to the URL whose response revealed it. A Page that links to a URL several times records it once. When Links that are not followed reach a URL first and a followed Link reaches it later, its `discovered_via`, `found_on_url_id` and `crawl_depth` are those of the followed Link, so its depth and where it was found tell one story.

HTTP redirects, HSTS, fonts in CSS, SWF and PDF are not Link types: a redirect is the redirecting URL's `redirect_url_id`, and a PDF is a content type.

### Nofollow

These Links are not followed:

- a `hyperlink` whose `rel` holds `nofollow`, in any letter case, such as `<a rel="nofollow sponsored">`
- every `hyperlink` of a Page whose robots directives say `nofollow` or `none` (see [Robots directives](#robots-directives))

A URL that only such Links reach is recorded with `fetch_state` = `skipped` and `skip_reason` = `nofollow`, and it is never requested, even when it is External. Nofollow is a property of a Link, not of a URL: once any followed Link reaches the URL, on the same Page or a later one, it is requested. With `--follow-nofollow`, nofollow Links are followed like any other hyperlink.

### Robots directives

The Crawl reads the robots directives of every parsed Page from two sources:

| Source | Read from |
|---|---|
| `meta_robots` | the `content` of every `<meta name="robots">`, in any letter case, joined with `, ` in document order |
| `x_robots_tag` | every `X-Robots-Tag` response header, joined with `, ` in the order received |

- Directives are comma-separated tokens, compared without case: `NOINDEX` is `noindex`, and `none` means `noindex, nofollow`.
- A header value that starts with a name and a colon, such as `googlebot: noindex`, applies only to the crawler it names. It applies to this Crawl when the name equals the robots user-agent token (`spider` by default), compared without case.
- `unavailable_after:`, `max-snippet:`, `max-image-preview:` and `max-video-preview:` are directives with a value, not crawler names: `unavailable_after: 25 Jun 2030 15:00:00 PST, noindex` gives `noindex`.
- `<meta>` elements named after one crawler, such as `<meta name="googlebot">`, are not read, nor a robots `<meta>` inside `<noscript>`, which a browser that runs scripts never sees.

A page-level `nofollow` stops the Page's hyperlinks from being followed (see [Nofollow](#nofollow)).

### Decoding

HTML is decoded by the first of these that applies, and bytes that are invalid in the chosen encoding become replacement characters (`�`), so a Page with broken bytes is still read:

1. a byte order mark (UTF-8, UTF-16LE or UTF-16BE)
2. the `charset` parameter of the `Content-Type` header
3. a `<meta charset>` or `<meta http-equiv="Content-Type">` declaration in the first 1024 bytes
4. UTF-8, or windows-1252 when the body is not valid UTF-8

Encoding labels are those of the [Encoding Standard](https://encoding.spec.whatwg.org/), as browsers read them: `iso-8859-1` and `ascii` mean windows-1252, `iso-8859-9` means windows-1254, and `shift_jis`, `euc-kr` and `gb2312` mean their Windows supersets. A label the Standard does not list, such as `charset=nonsense`, is skipped, and the next source applies; so are `x-user-defined` and the labels of the Standard's replacement encoding. A `<meta>` declaration inside a comment is not read, a `<meta>` with an unknown label gives way to the next one, and a `<meta>` declaration of UTF-16 means UTF-8.
