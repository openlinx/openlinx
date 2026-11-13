# The OpenLinx crawler

If you found `OpenLinx` in your server logs, this page explains what it is and how to limit or block it.

## What it is

OpenLinx is a free, open-source website crawler for SEO audits (Apache-2.0, source at https://github.com/openlinx/openlinx). A person runs it on their own computer to check a site: broken links, redirects, titles and descriptions, canonical tags, robots rules, page structure.

OpenLinx is a tool, not a service. There is no central OpenLinx server that crawls the web. Each crawl is started by the person who runs it, from their own machine and network, and its results stay on that machine. OpenLinx sends nothing to us: no telemetry, no crawl data.

## How to recognise it

- **User-Agent:** `OpenLinx/<version> (+https://github.com/openlinx/openlinx/blob/main/docs/crawler.md)`, the address of this page.
- **robots.txt token:** `openlinx`
- **IP addresses:** those of whoever runs it. We have no IP ranges to publish.

## What it does on your site

- Before any other request to an origin (a scheme, host and port), it fetches that origin's `/robots.txt` and obeys it, as RFC 9309 describes. It reads the `User-agent: openlinx` group, or the `*` group if there is none.
- If `/robots.txt` still answers with a 5xx or 429 status after its retries, it requests nothing else on that origin.
- It starts from one URL and follows links within the scope its user chose (by default, the same host). It requests each URL once per crawl, plus up to 2 retries by default, and only after a timeout, a refused or reset connection, a 5xx or a 429.
- By default it has at most 5 requests in flight per host. Its user can set a lower number, or a limit in requests per second.
- On a 429 response, or a 429 or 503 with `Retry-After`, it pauses all requests to that host for the time `Retry-After` gives (up to 120 seconds), or 10 seconds for a 429 without one.
- When many requests in a row get no answer at all, it stops and checks back on its start URL at growing intervals, at most once a minute, rather than going on.
- It honours `nofollow` in `<meta name="robots">` and in the `X-Robots-Tag` header, including `X-Robots-Tag` directives addressed to `openlinx:`.
- It requests each link to another site once, to check that the link works. It does not crawl that site.
- It does not submit forms or log in.

## How to limit or block it

Block it from the whole site:

```
User-agent: openlinx
Disallow: /
```

Keep it out of one section:

```
User-agent: openlinx
Disallow: /private/
```

`Crawl-delay` is recorded but not applied. To slow it down, answer with `429 Too Many Requests` and a `Retry-After` header.

## What we can and cannot promise

OpenLinx runs on its users' computers, so its users control it. A user can tell it to ignore robots.txt (`--ignore-robots`), to follow `nofollow` links, or to send a different User-Agent. The defaults are polite, and the documentation asks users to crawl only sites they are allowed to crawl. We cannot enforce that.

If a crawler that names itself OpenLinx causes problems on your site, block it at your server by User-Agent or by IP address. Then tell us at https://github.com/openlinx/openlinx/issues, so we can check whether the defaults need to change.
