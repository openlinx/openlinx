## Purpose

Crawl a given list of URLs (List mode) or the URLs listed in XML sitemaps (Sitemap mode), with the same engine, Scope and store as a Spider-mode Crawl.

Scenario conventions:
- `{site}` is the origin of the local fixture site, for example `http://127.0.0.1:8765`.
- A bare path such as `/a` means `{site}/a`.

## ADDED Requirements

### Requirement: List mode
`linx crawl --list <file|->` SHALL start a Crawl in List mode, with `crawl.crawl_mode` = `list`. Its Seeds SHALL be the URLs read from the file, or from standard input when the value is `-`. The input SHALL be read as one URL per line:
- Surrounding whitespace SHALL be trimmed.
- Blank lines and lines starting with `#` SHALL be ignored.
- URLs that are equal after normalisation SHALL become one Seed.
- UTF-8 with or without a byte order mark, and UTF-16 with a byte order mark, SHALL be accepted.
- Lines that are not valid http or https URLs SHALL be left out and reported together in one warning with code `list_invalid_lines`.

A list without any valid URL SHALL be rejected with exit code 2 and error code `empty_list`, and no Crawl SHALL be created.

The Seeds SHALL be written to the `seeds` table (`015-add-crawl-store`) in the order they were read, each once. Their `urls` rows SHALL have `discovered_via` = `list`, a value this change adds.

#### Scenario: Comments, blank lines and duplicates are ignored
- **WHEN** the list input is the lines `# pages`, an empty line, `http://site.test/a`, `http://site.test/a#top` and ` http://site.test/b `
- **THEN** the parsed Seeds are exactly `http://site.test/a` and `http://site.test/b`

#### Scenario: Invalid lines are reported in one warning
- **WHEN** the list input is the lines `http://site.test/a`, `not a url` and `ftp://site.test/x`
- **THEN** the parsed Seeds are exactly `http://site.test/a`, and the warnings hold exactly one entry, with code `list_invalid_lines`

#### Scenario: A UTF-8 byte order mark is ignored
- **WHEN** the list input is the UTF-8 bytes of `http://site.test/a`, preceded by a byte order mark
- **THEN** the parsed Seeds are exactly `http://site.test/a`

#### Scenario: A UTF-16 list written by Windows PowerShell is read (Windows)
- **WHEN** the list input is the UTF-16 LE bytes, with a byte order mark, of `http://site.test/a` followed by CR LF, as Windows PowerShell 5.1 `Out-File` writes them
- **THEN** the parsed Seeds are exactly `http://site.test/a`

#### Scenario: URLs are read from standard input
- **WHEN** `linx crawl --list -` runs with the line `{site}/a` on standard input
- **THEN** the Crawl's `urls` table holds exactly one row with `discovered_via` = `list`, for `{site}/a`

#### Scenario: Listed Seeds keep their order
- **WHEN** `linx crawl --list urls.txt` runs and `urls.txt` holds the lines `{site}/b` and `{site}/a`
- **THEN** the `seeds` table holds exactly the rows `(1, "{site}/b")` and `(2, "{site}/a")`

#### Scenario: A list without URLs is rejected
- **WHEN** `linx crawl --list urls.txt` runs and `urls.txt` holds only the line `# nothing yet`
- **THEN** the Command exits with code 2, and its only stderr error has `code` = `empty_list`

### Requirement: Sitemap mode
`linx crawl --sitemap <url>` SHALL start a Crawl in Sitemap mode, with `crawl.crawl_mode` = `sitemap`, and `--sitemap` SHALL be accepted more than once.
- **Formats:** the Crawl SHALL read XML sitemaps, sitemap index files, gzip-compressed sitemaps (recognised by their content, not only by their name) and plain-text sitemaps with one URL per line.
- **Index files:** every sitemap listed in an index SHALL be read, each sitemap URL at most once, through index files nested up to 3 times.
- **Seeds:** the URLs listed in the sitemaps SHALL be the Seeds, written to `seeds` in the order read, with Crawl Depth 0.
- **What is recorded:** this change adds three values to `urls.discovered_via`:
  - Each sitemap file SHALL be recorded as a URL, with `discovered_via` = `sitemap_input` for a sitemap given on the command line and `sitemap_index` for one listed in an index.
  - Each listed URL SHALL be recorded with `discovered_via` = `sitemap` and a `found_on_url_id` that points to the first sitemap that listed it.
- **Failures:** a sitemap that cannot be fetched or parsed SHALL produce a `sitemap_failed` warning, and the Crawl SHALL go on with the other sitemaps.
- **Size limit:** no sitemap SHALL be decompressed or parsed beyond 104,857,600 bytes (100 MiB). A larger one SHALL produce a `sitemap_too_large` warning.

#### Scenario: URLs listed in a sitemap become Seeds
- **WHEN** `/sitemap.xml` is an XML sitemap listing `{site}/a` and `{site}/b`, and `linx crawl --sitemap {site}/sitemap.xml` runs
- **THEN** `{site}/a` and `{site}/b` both have `fetch_state` = `fetched` and `discovered_via` = `sitemap`

#### Scenario: A sitemap index with a gzip-compressed sitemap is read
- **WHEN** `/sitemap_index.xml` lists `/s1.xml.gz` (a gzip-compressed sitemap listing `{site}/a`) and `/s2.xml` (a sitemap listing `{site}/b`), and `linx crawl --sitemap {site}/sitemap_index.xml` runs
- **THEN** `{site}/a` and `{site}/b` both have `fetch_state` = `fetched`

#### Scenario: A sitemap file is recorded as a URL
- **WHEN** `linx crawl --sitemap {site}/sitemap_index.xml` runs, and the index lists `/s2.xml`
- **THEN** `{site}/sitemap_index.xml` has `discovered_via` = `sitemap_input`, and `{site}/s2.xml` has `discovered_via` = `sitemap_index`

#### Scenario: A plain-text sitemap is read
- **WHEN** the sitemap reader parses the text `http://site.test/a` LF `http://site.test/b` LF
- **THEN** it returns exactly `http://site.test/a` and `http://site.test/b`

#### Scenario: Index files that list each other are read once
- **WHEN** `/idx1.xml` lists `/idx2.xml`, `/idx2.xml` lists `/idx1.xml`, and `linx crawl --sitemap {site}/idx1.xml` runs
- **THEN** the fixture site receives exactly one request for `/idx1.xml` and exactly one for `/idx2.xml`

#### Scenario: A failed sitemap is reported and skipped
- **WHEN** `linx crawl --sitemap {site}/missing.xml --sitemap {site}/sitemap.xml` runs, `/missing.xml` returns 404, and `/sitemap.xml` lists `{site}/a`
- **THEN** `{site}/a` has `fetch_state` = `fetched`, and the result's `warnings` hold exactly one entry with code `sitemap_failed`

#### Scenario: An oversized compressed sitemap is not expanded
- **WHEN** `/bomb.xml.gz` is 115,343,360 bytes (110 MiB) of spaces compressed with gzip, and `linx crawl --sitemap {site}/bomb.xml.gz` runs
- **THEN** the result's `warnings` hold exactly one entry with code `sitemap_too_large`

### Requirement: Seed hosts in List and Sitemap modes
In List and Sitemap modes, the Seed hosts that decide Internal URLs (`020-add-crawl-core`) SHALL be the hosts of all Seeds. With `--scope subdomains`, they SHALL be the registrable domains of all Seeds.

#### Scenario: Every listed host is internal
- **WHEN** the Scope of a List-mode Crawl with the Seeds `http://site.test/a` and `http://other.test/b` decides on `http://other.test/c`
- **THEN** the URL is internal

### Requirement: Default depth in List and Sitemap modes
In List and Sitemap modes, `--max-depth` SHALL default to 0. Only the Seeds, and the Resources of the Seeds that are followed, SHALL then be requested. A higher `--max-depth` SHALL follow Links from the Seeds as in Spider mode.

#### Scenario: List mode requests only the listed URLs by default
- **WHEN** a list holds only `{site}/a`, which links to `/c`, and `linx crawl --list urls.txt` runs
- **THEN** `{site}/c` has `skip_reason` = `max_depth`

#### Scenario: Sitemap mode requests only the listed URLs by default
- **WHEN** `/sitemap.xml` lists only `{site}/a`, which links to `/c`, and `linx crawl --sitemap {site}/sitemap.xml` runs
- **THEN** `{site}/c` has `skip_reason` = `max_depth`

#### Scenario: A List mode depth can be raised
- **WHEN** a list holds only `{site}/a`, which links to `/c`, and `linx crawl --list urls.txt --max-depth 1` runs
- **THEN** `{site}/c` has `fetch_state` = `fetched`

### Requirement: One Crawl Mode per Command
Giving more than one Crawl Mode (a Seed, `--list`, `--sitemap`) SHALL be rejected with exit code 2 and error code `mode_conflict`. `--scope subfolder` SHALL be accepted only in Spider mode; otherwise the Command SHALL be rejected with exit code 2 and error code `option_conflict`. No Crawl SHALL be created in either case.

#### Scenario: Two Crawl Modes at once are rejected
- **WHEN** `linx crawl {site}/ --list urls.txt` runs
- **THEN** the Command exits with code 2, and its only stderr error has `code` = `mode_conflict`

#### Scenario: A subfolder Scope needs Spider mode
- **WHEN** `linx crawl --list urls.txt --scope subfolder` runs
- **THEN** the Command exits with code 2, and its only stderr error has `code` = `option_conflict`
