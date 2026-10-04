## Why

Many SEO checks do not start from a home page. Common starting points are:
- a list of URLs to re-check after a fix
- the landing pages from an analytics export
- every URL a site's XML sitemaps promise

Screaming Frog serves these with its List mode and its sitemap upload. `020-add-crawl-core` crawls in Spider mode only, so this change adds the other two Crawl Modes from CONTEXT.md, List and Sitemap. It reuses the same engine, Scope and store.

## What Changes

- **List mode:** `spider crawl --list <file|->`.
  - The input is one URL per line, from a file or from standard input (`-`).
  - Whitespace is trimmed, blank lines and `#` comments are ignored, and URLs that are equal after normalisation become one Seed.
  - UTF-8 with or without a BOM is read, and so is UTF-16 with a BOM, as Windows PowerShell 5.1 writes it.
  - Invalid lines produce one `list_invalid_lines` warning. A list without URLs is rejected with `empty_list`.
- **Sitemap mode:** `spider crawl --sitemap <url>`, repeatable.
  - It reads XML sitemaps, sitemap index files, gzip-compressed sitemaps and plain-text sitemaps.
  - Index files are followed with loop protection, down to 3 nested levels.
  - A 100 MiB cap guards against decompression bombs (`sitemap_too_large`), and a sitemap that fails produces `sitemap_failed`.
- **Seeds:**
  - List mode: the listed URLs, written to `seeds` in the order read. Their `urls` rows have `discovered_via` = `list`.
  - Sitemap mode: the URLs listed in the sitemaps. Their rows have `discovered_via` = `sitemap`. The sitemap files themselves are URLs with `sitemap_input` or `sitemap_index`.
  - `crawl.crawl_mode` is `list` or `sitemap`.
- **Scope:** the Seed hosts are the hosts of all Seeds.
- **Depth:** `--max-depth` defaults to 0 in these modes, so only the Seeds and their Resources are requested. It can be raised.
- **Errors:**
  - Giving more than one Crawl Mode (a Seed, `--list`, `--sitemap`) is rejected with `mode_conflict`.
  - `--scope subfolder` needs Spider mode (`option_conflict`).
- **Fixture site:** a gzip-bomb sitemap route, added test-first.
- **MCP tools:** none in this change. `090-add-mcp-server` passes List-mode URLs through `060`'s detached start.

## Capabilities

### New Capabilities
- `crawl-modes`: covers List mode and Sitemap mode (the list and sitemap readers, limits and failures), Seeds and Seed hosts in both modes, their default depth, and the one-Crawl-Mode rule.

### Modified Capabilities
- None. There are no main specs yet. This change adds the enumeration values `list`, `sitemap`, `sitemap_input` and `sitemap_index` to `020-add-crawl-core`'s `urls.discovered_via`, under `015`'s conventions.

## Non-goals

- Sitemap analysis (`sitemaps`: sitemap versus crawl, and non-indexable URLs in sitemaps): **v0.2**.
- Discovering sitemaps during a Spider crawl: **v0.2**.
- Reading lists from CSV or XLSX files, and sitemaps from local files: see design.md, Open Questions.
- The dry-run URL estimate from lists and sitemaps: `060-add-crawl-control` (v0.2), which reuses this change's readers.

## Impact

- **Depends on:**
  - `020-add-crawl-core`: the engine, `ScopeRules`, `crawl.scope`, the `urls` table, URL normalisation, and the result.
  - `015-add-crawl-store`: `seeds` and `crawl.crawl_mode`.
  - `010-add-workspace-and-cli-contract`: diagnostics and exit codes.
  - `000-scaffold-project`: the sitemap routes of the fixture site.
- **Used by:**
  - `060-add-crawl-control`: the estimate and the detached List mode.
  - `090-add-mcp-server` (v0.1.1): `crawl_start` with a list of URLs.
- **Code:** `src/spider/crawl/listfile.py`, `src/spider/crawl/sitemaps.py`, and the mode handling in the Crawl Service and `src/spider/cli/crawl.py`.
- **New dependencies:** none. XML is read with the standard library's pull parser, with no entity expansion.
- **Docs:** the List and Sitemap modes part of `docs/crawling.md`.
