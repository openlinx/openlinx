# Crawling

How `spider crawl` decides what a URL is, which URLs it requests and how it records them. The spec is [openspec/changes/020-add-crawl-core/specs/crawling/spec.md](../openspec/changes/020-add-crawl-core/specs/crawling/spec.md). Terms follow [CONTEXT.md](../CONTEXT.md).

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
