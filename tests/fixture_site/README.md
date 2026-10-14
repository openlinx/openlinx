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
- **A site too large to declare,** such as the synthetic site of `026`, passes `resolve=`, a function from a path to a route or `None`. The server calls it for a path that `routes` does not declare.
- A path that no route declares, and that `resolve` does not resolve, answers 404.

## Route kinds

| Route | Answers with |
|---|---|
| `Page(file=... \| body=..., template=False)` | 200 and the file's exact bytes, or the body as UTF-8. The content type comes from the file extension through a fixed table (never `mimetypes`); a `body` page is `text/html; charset=utf-8`. With `template=True`, every `{{base_url}}` becomes the server's base URL. |
| `Status(code)` | That status and an empty body. |
| `Redirect(location, status=301)` | That status and `Location` exactly as declared, never made absolute. `redirect_chain(prefix, hops, to)` builds `<prefix>1` → … → `<prefix><hops>` → `to`. |
| `Robots(text)` | 200, `text/plain; charset=utf-8` and the text. |
| `Sitemap(paths)` | 200, `application/xml` and a `<urlset>` with one absolute `<loc>` per path. |
| `SitemapIndex(paths)` | 200, `application/xml` and a `<sitemapindex>` with one absolute `<loc>` per path. |
| `LargeFile(size)` | 200, `Content-Length: size` and a stream of the bytes 0–255 repeated. |
| `Bytes(data)` | 200, `application/octet-stream` unless `content_type` says otherwise, and the bytes exactly, for a page whose bytes are broken on purpose. |

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
- **`ServerHandle`**:
  - `base_url`, such as `http://127.0.0.1:53124`
  - `url(path)`
  - `most_simultaneous`, the most requests the site has handled at once, from a request's arrival until its handler returned
  - `requests`, a snapshot of the request log. A server started as `RunningServer(site, keep_log=False)` logs nothing, so a run of hundreds of thousands of requests keeps its memory flat. Each entry is a `LoggedRequest(method, path, headers, received_at)`: the path includes the query, and `received_at` is `time.monotonic()`.

Clients in tests:
- aiohttp needs nothing special.
- `http.client` needs nothing special.
- A `urllib` opener needs `urllib.request.build_opener(urllib.request.ProxyHandler({}))`. On Windows urllib otherwise reads proxy settings from the registry.

Timing tests assert only lower bounds, such as "not before 0.5 s", and use generous client timeouts.

## The synthetic site

The site that the 500k benchmark crawls (design D6 of `026-add-parse-pool`), in `synthetic/`. It is a function, not data: `SyntheticSite(seed=..., pages=...)` computes each Page when it is requested, so 500,000 Pages take no memory per Page.

- **Its Pages:** `/` and `/p/1` to `/p/<pages - 1>`.
  - A Page is about 50 KB with about 450 Links of every Link type: a header navigation of 200 Links, a footer that repeats 80 of them, 60 internal Links drawn from the seed, and its Resources.
  - Page `n` links to its `fanout` children (`n * fanout + 1` onwards), a spanning tree that reaches every Page from `/`. `fanout` is 50 by default (a depth of about 4 at 500k); 10 gives a deeper site.
  - `page_model(n)` gives a Page's Links, its type, element, attribute and anchor, in document order, and `render(n)` gives its bytes. Both come from one build, so they always agree.
- **Its other URLs** come from bounded pools that do not grow with the Pages: images, stylesheets, scripts, video, audio and media under `/r/`, the not-followed `/amp/`, `/m/` and `/misc/`, and `/missing/`, which answers 404.
- **Determinism:** every draw comes from `blake2b(seed, n, purpose)` and splitmix64, never `hash()` or `random`, so a seed gives the same bytes on every Python, OS and process.
- **Faults:** `shares` maps each `Fault` to the share of Pages that carry it (`DEFAULT_SHARES` by default, `NO_FAULTS` for none):
  - nested `<div>`s, 100,000 levels deep
  - the end-worker marker, `END_WORKER`, on which the benchmark's own extractor ends its worker
  - a 500
  - invalid UTF-8, windows-1251 bytes declared UTF-8, or an unknown charset label
  - NULs and unclosed markup after the last Link
  - a slow answer after `slow_seconds`
  - no `<title>` or no `<h1>`

  Only leaves of the spanning tree carry a fault, so no fault cuts other Pages off. `latency` delays every response.
- **`manifest()`:** the injected counts, the outcome each fault should leave in `urls`, the Issues it injects, and the URLs a Crawl must account for, in one pass that keeps nothing per Page.
- **`SiteProcess(site)`** (`synthetic/serve.py`) serves it from its own `spawn` process, so the server's CPU and memory never count against the crawl process's. It keeps no request log. `stop()` returns a `Tally` of the Pages requested, those requested more than once, the other requests and the 404s. It ignores Ctrl+C (and Ctrl+Break on Windows), so the benchmark stops it in order.
- **`prepared_page(site, url, scope)`** (`synthetic/preparation.py`) is the `PreparedPage` that preparing the Page at `url` gives, built from its model without HTML; the benchmark's direct mode uses it. `END_WORKER_EXTRACTOR` ends its process with exit code 70 on a Page with the end-worker marker.
- **`account(site, rows, recorded_pools=..., tally=...)`** (`synthetic/accounting.py`) checks a Crawl's `urls` rows against the manifest: each Page's outcome, the count of each kind, no URL that is not the site's, and, with the `Tally`, every Page served once.

## Extending it

- A new route kind or option starts with a failing test in `tests/fixture_site/`; then implement it.
- New sites are new folders under `sites/`.
- Never change what an existing route kind or option does. Later changes rely on it: `022-add-fetch-policy` adds TLS, named virtual hosts and gzip this way.
