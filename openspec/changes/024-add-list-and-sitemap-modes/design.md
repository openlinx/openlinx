## Context

See proposal.md (Why) for the motivation. The approach is shaped by these constraints:

- **`020-add-crawl-core`** provides:
  - the engine and the frontier in `urls`, with Seeds at Crawl Depth 0
  - `ScopeRules` with its host rule
  - `--max-depth`, and the result and warnings
- **`015-add-crawl-store`** holds the Seeds in `seeds` and the Crawl Mode in `crawl.crawl_mode`.
- **`060-add-crawl-control`** reuses both readers for the dry-run estimate, and reads the list in the detaching process for a detached List-mode Crawl. So the readers must be pure and usable without a running Crawl.
- **`000-scaffold-project`** already serves sitemaps, sitemap indexes and gzipped sitemaps on the fixture site.

## Goals / Non-Goals

**Goals:**
- Two pure readers, `read_url_list(bytes)` and `read_sitemap(bytes, content_type)`, with literal table-driven tests.
- List and Sitemap modes that differ from Spider mode only in where Seeds come from, which hosts are Seed hosts, and the default depth.

**Non-Goals:**
- Sitemap analysis in v0.2: comparing sitemaps with the Crawl, checking `lastmod`, and so on.
- Reading CSV or XLSX lists.

## Decisions

### D1. Decoding a list
The list reader sniffs the byte order mark: UTF-8-SIG, UTF-16 LE or UTF-16 BE, and otherwise strict UTF-8. A line that does not decode counts as an invalid line. CR LF and LF are both line ends. Standard input is read in binary (`sys.stdin.buffer`), so the Windows console code page never gets involved.
- *Alternative:* the locale's encoding. Windows PowerShell 5.1 writes UTF-16 with `Out-File` and ANSI through pipes, so a guess would silently corrupt non-ASCII URLs. Rejected.

### D2. Deduplicating Seeds
Seeds are deduplicated by their normalised form, and the first occurrence, as given, goes to `seeds`. So `seeds` keeps the user's spelling, `urls` holds one normalised row, and the counts in the result match the number of distinct Seeds.

### D3. Reading sitemaps
- **Parsing:** the sitemap reader uses `xml.etree.ElementTree.XMLPullParser`, which expands no external entities, over a decompressing reader capped at 100 MiB. Gzip is recognised by its magic bytes, whatever the file name or Content-Type.
- **Text sitemaps:** a response that is not XML is read as one URL per line.
- **Index files:** a set of sitemap URLs already read gives loop protection, and a depth counter stops nesting after 3 levels.
- **Fetching:** sitemap files are requested through the normal engine, so robots.txt, politeness and `020`'s Fetcher apply. Each is recorded as a `urls` row (`sitemap_input` or `sitemap_index`), and parsed by the sitemap reader instead of the HTML extractors.

### D4. Seeds, hosts and depth
- **Seeds:** listed URLs enter the frontier at depth 0 with `discovered_via` `list` or `sitemap`.
- **Seed hosts:** `ScopeRules` gets the set of Seed hosts instead of one host. For Sitemap mode, the set grows as the sitemaps are read, before any listed URL is dispatched: the depth-0 barrier waits for the sitemap files.
- **Depth:** the default `--max-depth` of 0 is resolved per Crawl Mode when settings are resolved, so the recorded config shows 0. `060`'s equivalent command omits it because it is that mode's default.

### D5. Fixture site addition
A gzip-bomb route (a small gzip stream that expands to 110 MiB of spaces) is added test-first in `tests/fixture_site/`. `000`'s gzip sitemaps cover the normal cases.

## Test seams

- **Pure-logic modules (4):** the list reader (comments, invalid lines, byte order marks, UTF-16 from Windows PowerShell) and the sitemap reader (text format), with literal inputs and outputs.
- **HTTP (local fixture site) (3) and seam 3+6:** Sitemap-mode Crawls over the fixture's sitemap routes and List-mode Crawls, read back from `urls` and `seeds`.
- **CLI (1):** standard input, `empty_list`, `mode_conflict` and `option_conflict`.
- **New seams or doubles:** none.

## Risks / Trade-offs

- [Huge sitemap indexes (50,000 sitemaps) cost many requests] → Each sitemap file counts toward `--max-urls`, and the dry run (`060`) shows the estimate first.
- [Sitemaps that list URLs on other hosts] → They become Seeds and their hosts become Seed hosts, which is what a user who hands in the sitemap expects. v0.2's sitemap analysis will flag them.
- [Windows PowerShell pipes ANSI text into `--list -`] → Non-ASCII URLs may arrive mangled. docs/crawling.md recommends `--list <file>` on Windows PowerShell 5.1.

## Migration Plan

The new enumeration values go into the squashed v0.1 migration. There are no new tables.

## Open Questions

These are deferrable, and each is additive:
- Reading URLs from CSV or XLSX exports, taking the first column that looks like a URL.
- `--sitemap <local file>`, for sitemaps that are not deployed yet.
- RSS or Atom feeds as sitemaps.
