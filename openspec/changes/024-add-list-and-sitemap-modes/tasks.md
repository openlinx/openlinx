> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

Each task below is one vertical TDD slice and one commit. It is done when:
1. the test for the named scenario, written first at the named seam, fails for the right reason
2. only enough code is written to make it pass
3. ruff, the strict type checker and the full suite (with the coverage gate) pass
4. the commit message names the scenario

A slice that adds an enumeration value updates `docs/schema.md` in the same commit.

Seams (docs/testing.md):
- **[Pure]**: seam 4
- **[HTTP]**: seam 3
- **[3+6]**: crawl the fixture site, then read the documented tables read-only
- **[CLI]**: seam 1, `CliRunner`
- **[Fixture]**: a new fixture-site capability, test-first in `tests/fixture_site/`

## 1. The list reader

- [ ] 1.1 [Pure] Drive "Comments, blank lines and duplicates are ignored": start `read_url_list`.
- [ ] 1.2 [Pure] Drive "Invalid lines are reported in one warning".
- [ ] 1.3 [Pure] Drive "A UTF-8 byte order mark is ignored".
- [ ] 1.4 [Pure] Drive "A UTF-16 list written by Windows PowerShell is read (Windows)".
- [ ] 1.5 Docs: document the list format and its encodings in the List mode part of `docs/crawling.md`.
- [ ] 1.6 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. List mode

- [ ] 2.1 [CLI] Drive "Two Crawl Modes at once are rejected": `--list`, and `mode_conflict`.
- [ ] 2.2 [CLI] Drive "A list without URLs is rejected".
- [ ] 2.3 [3+6] Drive "URLs are read from standard input": List mode in the Crawl Service, the value `list`, and `crawl.crawl_mode`.
- [ ] 2.4 [3+6] Drive "Listed Seeds keep their order".
- [ ] 2.5 [Pure] Drive "Every listed host is internal": Seed hosts from every Seed in `ScopeRules`.
- [ ] 2.6 [3+6] Drive "List mode requests only the listed URLs by default": the default `--max-depth` of 0 per Crawl Mode.
- [ ] 2.7 [3+6] Drive "A List mode depth can be raised".
- [ ] 2.8 [CLI] Drive "A subfolder Scope needs Spider mode".
- [ ] 2.9 Docs: document List mode (standard input, the default depth, the Windows PowerShell advice) in `docs/crawling.md`.
- [ ] 2.10 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. The sitemap reader and Sitemap mode

- [ ] 3.1 [Pure] Drive "A plain-text sitemap is read": start `read_sitemap` over a size-capped reader.
- [ ] 3.2 [3+6] Drive "URLs listed in a sitemap become Seeds": `--sitemap`, XML urlsets, the value `sitemap`, and `crawl.crawl_mode`.
- [ ] 3.3 [3+6] Drive "A sitemap index with a gzip-compressed sitemap is read".
- [ ] 3.4 [3+6] Drive "A sitemap file is recorded as a URL": the values `sitemap_input` and `sitemap_index`.
- [ ] 3.5 [HTTP] Drive "Index files that list each other are read once".
- [ ] 3.6 [CLI] Drive "A failed sitemap is reported and skipped".
- [ ] 3.7 [Fixture] Add a gzip-bomb route to the fixture site.
- [ ] 3.8 [CLI] Drive "An oversized compressed sitemap is not expanded".
- [ ] 3.9 [3+6] Drive "Sitemap mode requests only the listed URLs by default".
- [ ] 3.10 Docs: document Sitemap mode (formats, index files, limits, failures) in `docs/crawling.md`.
- [ ] 3.11 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. Change check

- [ ] 4.1 Verify that every `#### Scenario:` in `specs/crawl-modes/spec.md` has exactly one test named after it.
- [ ] 4.2 Verify that the whole suite passes in CI on Windows, macOS and Linux × Python 3.12–3.14 with the coverage gate.
- [ ] 4.3 Review: run the code-review skill on the whole change against `specs/crawl-modes/spec.md`, then refactor with the whole suite green.
