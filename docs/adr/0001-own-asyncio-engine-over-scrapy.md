# Own asyncio crawl engine instead of Scrapy

We build our own asyncio crawl engine with aiohttp as the fetcher, rather than building on Scrapy. The queue of URLs still to crawl must live in the SQLite crawl store, so that resume, `--detach`, `status` and queries during a crawl all read one source of truth.

Scrapy falls short on three points:
- Its resume state (JOBDIR) is a second, pickle-based queue. It can be corrupted by an unclean shutdown and must be resumed with the same Scrapy version.
- It records redirect hops without their headers or timings.
- Its HTTP/2 handler fails outright on servers that don't offer h2.

## Considered Options

- **Scrapy 2.19**: mature, uses the asyncio reactor by default, and scrapy-playwright covers JS rendering. Rejected for the reasons above.
- **httpx**: supports HTTP/2 and reports each response's HTTP version. But the original project hasn't had a release since 0.28.1 (December 2024), and its fork httpx2 is young.
- **aiohttp**: chosen. It is fast at our concurrency (5–50 requests) and actively maintained. It has no HTTP/2, so the HTTP Version column is measured once per host with a TLS ALPN check.

## Consequences

- We own politeness, retries, redirect handling and robots.txt logic (Protego parses robots.txt).
- The fetcher sits behind an interface, so httpx2, niquests or a Playwright fetcher (v1.1) can replace aiohttp without touching the engine.
