# The fixture site

A local HTTP server that tests crawl instead of the internet (design D9 of `000-scaffold-project`). It runs aiohttp on `127.0.0.1`, on a free port, in a background thread with its own `spider.aio.loop_factory()` loop. In-process sync tests, async tests and child processes all reach it over TCP.

## Declaring a site

A site is data: a `Site` maps request paths to routes.

```python
from pathlib import Path

from tests.fixture_site.routes import Page, Redirect, Robots, Site

SITE = Site(
    root=Path(__file__).parent,  # where Page(file=...) looks for files
    routes={
        "/": Page(file="index.html"),
        "/old": Redirect("/"),
        "/robots.txt": Robots("User-agent: *\nDisallow: /private/\n"),
    },
)
```

- **A reusable site** is a folder `sites/<name>/` with an empty `__init__.py`, a `site.py` that defines `SITE`, and its page files. Everything under `sites/` is `-text` in `.gitattributes`, so the files keep their exact bytes, line endings included.
- **A one-off site** is built inline in the test: `Site(routes={...})`.
- A site is checked when it is declared: a `Page` takes exactly one of `file=` and `body=`, and a site with `Page(file=...)` routes needs `root=`.
- A path that no route declares answers 404.

## Route kinds

| Route | Answers with |
|---|---|
| `Page(file=... \| body=..., template=False)` | 200 and the file's exact bytes, or the body as UTF-8. The content type comes from the file extension through a fixed table (never `mimetypes`); a `body` page is `text/html; charset=utf-8`. With `template=True`, every `{{base_url}}` becomes the server's base URL. |
| `Status(code, body=None)` | That status and an empty body, or the body as UTF-8 with `text/html; charset=utf-8`, as an error page. |
| `Redirect(location, status=301)` | That status and `Location` exactly as declared, never made absolute. `redirect_chain(prefix, hops, to)` builds `<prefix>1` → … → `<prefix><hops>` → `to`. |
| `Robots(text)` | 200, `text/plain; charset=utf-8` and the text. |
| `Sitemap(paths)` | 200, `application/xml` and a `<urlset>` with one absolute `<loc>` per path. |
| `SitemapIndex(paths)` | 200, `application/xml` and a `<sitemapindex>` with one absolute `<loc>` per path. |
| `LargeFile(size)` | 200, `Content-Length: size` and a stream of the bytes 0–255 repeated. |
| `Responses(answers)` | The answers in turn, one per request to the path, then the last one again: `Responses((Status(503), Page(body=...)))` is a page that fails once. Each path counts its own requests. |

A gzipped sitemap is an ordinary `Page(file="sitemap.xml.gz", content_type="application/gzip")`. The extension table knows only `.html`, `.txt` and `.xml`; any other extension is `application/octet-stream` unless `content_type` says otherwise.

## Options on every route

Every route takes these as keyword arguments:

- `headers=[(name, value), ...]`: added to the response in order. A name may repeat, such as two `Set-Cookie`. A `Content-Type` here is added next to the route's own, so use `content_type` to replace it.
- `content_type="..."`: replaces the route's own `Content-Type`.
- `delay=0.5`: seconds to wait before the response headers.
- `hang=True`: never answer.
- `reset_after=100`: send the headers, with the whole body's `Content-Length`, and that many bytes of the body, then reset the connection (TCP RST).

When the server stops, it cancels every handler still running (hanging or delayed) before aiohttp's cleanup, which would otherwise wait up to 60 s for them.

## Fixtures

- **`fixture_site`** (function-scoped): `server = fixture_site(SITE)` starts the site and returns a `ServerHandle`. Every site it started stops after the test.
- **`module_fixture_site`**: the same, stopped after the module. It is for hypothesis tests, which cannot use function-scoped fixtures.
- **`fixture_hosts`** (function-scoped), for multi-host Crawls: `hosts = fixture_hosts(SITE, OTHER)` starts two instances and returns a `FixtureHosts`:
  - `site`, the `ServerHandle` that `site.test` and `www.site.test` name, and `other`, the one that `other.test` names
  - `resolver`, the DNS resolver hook: an aiohttp resolver that maps those names, on any port, to their instance's address and port, and fails every other name as the system resolver does, so aiohttp reports `ClientConnectorDNSError`. It goes into a Crawl through `tests.support.crawling.crawl_result(..., resolver=hosts.resolver)`, which binds it into the Fetcher factory that the Crawl Service's `start_crawl` takes.
- **`fixture_proxy`** (function-scoped), for the proxy scenarios: `proxy = fixture_proxy(hosts.resolver)` starts a forward proxy (`tests/support/proxy.py`) at `proxy.url`. It relays each plain-http request it receives in absolute form, resolving the fixture's names with the DNS resolver hook it is given, since behind a proxy the crawler resolves only the proxy's address, and `proxy.requests` holds each relayed URL in order.
- **`ServerHandle`**:
  - `base_url`, such as `http://127.0.0.1:53124`
  - `url(path)`
  - `most_simultaneous`, the most requests the site has handled at once, from a request's arrival until its handler returned
  - `requests`, a snapshot of the request log. Each entry is a `LoggedRequest(method, path, headers, received_at)`: the path includes the query, and `received_at` is `time.monotonic()`.

Clients in tests:
- aiohttp needs nothing special.
- `http.client` needs nothing special.
- A `urllib` opener needs `urllib.request.build_opener(urllib.request.ProxyHandler({}))`. On Windows urllib otherwise reads proxy settings from the registry.

Timing tests assert only lower bounds, such as "not before 0.5 s", and use generous client timeouts.

## Extending it

- A new route kind or option starts with a failing test in `tests/fixture_site/`; then implement it.
- New sites are new folders under `sites/`.
- Never change what an existing route kind or option does. Later changes rely on it: `022-add-fetch-policy` adds TLS, named virtual hosts and gzip this way.
