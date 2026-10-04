> **Draft** — re-grounded against the code with `/opsx:update` before this change starts; `Green:` names are hints, not requirements.

Each task below is one vertical TDD slice and one commit. It is done when:
1. the test for the named scenario, or trivial pair of scenarios, written first at the named seam, fails for the right reason
2. only enough code is written to make it pass
3. ruff, the strict type checker and the full suite (with the coverage gate) pass
4. the commit message names the scenario

A slice that needs a new table or column adds it, with its description, and updates `docs/schema.md` in the same commit, so `015`'s contract test never goes red. HTTP slices add the fixture pages they need to the fixture site from `000-scaffold-project`.

Seams (docs/testing.md):
- **[Pure]**: seam 4, pure-logic modules
- **[HTTP]**: seam 3, the real crawler against the local fixture site
- **[3+6]**: crawl the fixture site, then read the documented tables read-only
- **[CLI]**: seam 1, Typer `CliRunner`
- **[Subprocess]**: seam 1, a real `spider` process
- **[Services]**: seam 2, the Crawl Service or the store API with a temporary Workspace
- **[Fake timing]**: the fake Fetcher plus the injectable clock, for timing scenarios only
- **[Fixture]**: a new fixture-site capability, test-first in `tests/fixture_site/`

## 1. URL normalisation and Seeds

- [ ] 1.1 [Pure] Drive "Scheme and host case, the default port and the fragment are normalised" and "A non-default port is kept": start the URL normaliser.
- [ ] 1.2 [Pure] Drive "Dot segments are resolved" and "An empty path becomes a slash".
- [ ] 1.3 [Pure] Drive "Percent-encodings are normalised".
- [ ] 1.4 [Pure] Drive "Characters outside ASCII are percent-encoded".
- [ ] 1.5 [Pure] Drive "An internationalised host becomes ASCII".
- [ ] 1.6 [Pure] Drive "The query and its parameter order are kept".
- [ ] 1.7 [Pure] Drive "Normalising twice changes nothing", as a hypothesis property.
- [ ] 1.8 [Pure] Drive "Matching parameters are removed": `--strip-params`.
- [ ] 1.9 [Pure] Drive "Removing every parameter removes the query" and "Parameters are kept by default".
- [ ] 1.10 [Pure] Drive "A bare host becomes an https Seed": the Seed parser.
- [ ] 1.11 Docs: write the "URLs" part of `docs/crawling.md` (the normalisation rules and `--strip-params`).
- [ ] 1.12 Review: run the code-review skill on group 1's commits, then refactor with the whole suite green.

## 2. Scope and robots.txt decisions

- [ ] 2.1 [Pure] Drive "The other scheme of the Seed host is internal" and "Another host is external by default": start `ScopeRules`.
- [ ] 2.2 [Pure] Drive "Subdomains are internal with the subdomains Scope": add `publicsuffixlist`.
- [ ] 2.3 [Pure] Drive "A public suffix is not treated as the site".
- [ ] 2.4 [Pure] Drive "The folder of a Seed page is its parent folder".
- [ ] 2.5 [Pure] Drive "Exclude wins over include".
- [ ] 2.6 [Pure] Drive "The group for the tool's token applies": the robots.txt decision on Protego, with the default token `spider`.
- [ ] 2.7 [Pure] Drive "Another token can be chosen": `--robots-user-agent`.
- [ ] 2.8 Docs: write the "Scope" part of `docs/crawling.md` (host rules, `--scope`, subfolder folders, include and exclude, and a warning about slow regexes).
- [ ] 2.9 Review: run the code-review skill on group 2's commits, then refactor with the whole suite green.

## 3. Link extractor and robots directives

- [ ] 3.1 [Pure] Drive "A relative link is resolved against the base href": start the link extractor on selectolax, with `DiscoveredLink`.
- [ ] 3.2 [Pure] Drive "Every srcset candidate is an image Link".
- [ ] 3.3 [Pure] Drive "rel previous is a pagination Link".
- [ ] 3.4 [Pure] Drive "References that are not http or https are ignored".
- [ ] 3.5 [Pure] Drive "Meta robots directives are read case-insensitively": start the robots directives parser.
- [ ] 3.6 [Pure] Drive "A header for another crawler does not apply": the user-agent prefix rule.
- [ ] 3.7 [Pure] Drive "A header for the robots user-agent token applies".
- [ ] 3.8 [Pure] Drive "none means noindex and nofollow".
- [ ] 3.9 [Pure] Drive "A directive with a value is not a user-agent prefix".
- [ ] 3.10 Docs: add the Link type table and the robots directives rules to `docs/crawling.md`.
- [ ] 3.11 Review: run the code-review skill on group 3's commits, then refactor with the whole suite green.

## 4. Walking skeleton: a foreground Spider crawl

- [ ] 4.1 [CLI] Drive "An invalid Seed is rejected": the `crawl` Command shell calling the Crawl Service, with `010`'s error output.
- [ ] 4.2 [3+6] Drive "The Seed is fetched and recorded". It covers:
  - the Crawl Service start operation
  - the `Fetcher` interface and a one-hop aiohttp implementation
  - the first `urls` columns (`id`, `url`, `host`, `crawl_depth`, `discovered_via`, `fetch_state`, `status_code`)
  - one writer unit per URL
- [ ] 4.3 [3+6] Drive "The Seed is kept as given in seeds": write `seeds` and `crawl.crawl_mode`.
- [ ] 4.4 [3+6] Drive "Pages linked from the Seed are crawled": the frontier loop, and in-process hyperlink discovery through the extractor registry and a sink.
- [ ] 4.5 [3+6] Drive "A discovered URL points to where it was found": `found_on_url_id`.
- [ ] 4.6 [CLI] Drive "The result counts a small site" and "A completed Crawl exits with code 0": the result JSON with `seed_count` and `status_classes`, and the `parsed` column.
- [ ] 4.7 [CLI] Drive "The crawl Command prints one document": register the output kind.
- [ ] 4.8 [3+6] Drive "A completed Crawl records its state": `crawl.state` = `completed`, and the `crawl.stop_reason` column.
- [ ] 4.9 [CLI] Drive "The first event line is the start event": the event bus, and `crawl_started` as a UTF-8 `{event, ts, data}` line.
- [ ] 4.10 [Services] Drive "The recorded config holds every registered crawl setting": the settings registry for `crawl.*` options.
- [ ] 4.11 [CLI] Drive "spider.toml sets a crawl setting" and "A flag overrides spider.toml".
- [ ] 4.12 [3+6] Drive "Response timing is recorded": `response_time_ms` and `fetched_at`.
- [ ] 4.13 [3+6] Drive "The Content-Type is recorded as received".
- [ ] 4.14 Docs: write the `spider crawl` reference in `docs/crawling.md` (the result fields, the event table, exit codes, `[crawl]` keys).
- [ ] 4.15 Review: run the code-review skill on group 4's commits, then refactor with the whole suite green.

## 5. Link following

- [ ] 5.1 [HTTP] Drive "A meta refresh target is followed".
- [ ] 5.2 [3+6] Drive "amphtml targets are not requested": the `skip_reason` column, with `link_type_not_followed`.
- [ ] 5.3 [HTTP] Drive "A canonical in an HTTP header is followed": HTTP `Link` headers of in-Scope 2xx responses.
- [ ] 5.4 [3+6] Drive "Links on an error page are not followed": the parse rule (in Scope, 2xx, HTML).
- [ ] 5.5 [3+6] Drive "A nofollow link is not requested".
- [ ] 5.6 [3+6] Drive "A page-level nofollow applies to every hyperlink", using the robots directives parser.
- [ ] 5.7 [3+6] Drive "A nofollow target reached through a followed Link is fetched".
- [ ] 5.8 [3+6] Drive "Nofollow Links are followed on request": `--follow-nofollow`.
- [ ] 5.9 Docs: document nofollow handling and which responses are parsed in `docs/crawling.md`.
- [ ] 5.10 Review: run the code-review skill on group 5's commits, then refactor with the whole suite green.

## 6. Scope over HTTP and Section Crawls

- [ ] 6.1 [Fixture] Add a second fixture site instance and the DNS resolver hook, which maps `site.test` and `other.test` to the two instances and fails every other name, test-first.
- [ ] 6.2 [3+6] Drive "An External URL is checked": the `is_internal` column.
- [ ] 6.3 [3+6] Drive "An External origin gets its own row": the `origins` table with `id`, `origin`, `host` and `is_internal`.
- [ ] 6.4 [HTTP] Drive "External checks can be turned off": `--check-external/--no-check-external`.
- [ ] 6.5 [HTTP] Drive "URLs that differ only in stripped parameters are fetched once".
- [ ] 6.6 [CLI] Drive "The subdomains shorthand conflicts with a subfolder Scope".
- [ ] 6.7 [CLI] Drive "A Seed without its trailing slash is rejected".
- [ ] 6.8 [3+6] Drive "Pages inside the folder are followed": the `in_scope` column.
- [ ] 6.9 [3+6] Drive "Pages outside the folder are checked but not followed".
- [ ] 6.10 [HTTP] Drive "An excluded URL is never requested" and "An excluded URL is recorded as skipped".
- [ ] 6.11 [3+6] Drive "A skipped URL has no response data".
- [ ] 6.12 [3+6] Drive "A URL that matches no include pattern is checked but not followed".
- [ ] 6.13 [CLI] Drive "An invalid pattern is rejected".
- [ ] 6.14 [CLI] Drive "A Seed outside the Scope is rejected".
- [ ] 6.15 [CLI] Drive "A subfolder Crawl is a Section Crawl".
- [ ] 6.16 [3+6] Drive "An include pattern makes a Section Crawl" and "Exclude patterns alone do not make a Section Crawl".
- [ ] 6.17 [3+6] Drive "A subfolder Scope is recorded": the `crawl.scope` column.
- [ ] 6.18 Docs: document Section Crawls and External URL checks in `docs/crawling.md`.
- [ ] 6.19 Review: run the code-review skill on group 6's commits, then refactor with the whole suite green.

## 7. Resources, Crawl Depth and limits

- [ ] 7.1 [3+6] Drive "An image is checked but not parsed": Resource Link types are requested.
- [ ] 7.2 [3+6] Drive "A broken image is recorded".
- [ ] 7.3 [3+6] Drive "The shortest path wins over a faster, longer one": depth-by-depth dispatch of followed URLs (design D3).
- [ ] 7.4 [3+6] Drive "A Resource is one deeper than its Page".
- [ ] 7.5 [3+6] Drive "Links beyond the limit are not requested": `--max-depth`.
- [ ] 7.6 [3+6] Drive "Resources are checked beyond the depth limit".
- [ ] 7.7 [CLI] Drive "The Crawl stops at the limit": `--max-urls` and the `stopped` Crawl State.
- [ ] 7.8 [3+6] Drive "URLs not requested stay queued".
- [ ] 7.9 [CLI] Drive "The limit warning says how to continue".
- [ ] 7.10 [3+6] Drive "The default limit is recorded".
- [ ] 7.11 [CLI] Drive "Zero means no limit".
- [ ] 7.12 Docs: document Resources, Crawl Depth, `--max-depth` and `--max-urls` (and what counts) in `docs/crawling.md`.
- [ ] 7.13 Review: run the code-review skill on group 7's commits, then refactor with the whole suite green.

## 8. robots.txt over HTTP

- [ ] 8.1 [HTTP] Drive "robots.txt is fetched once per origin".
- [ ] 8.2 [3+6] Drive "A disallowed URL is not requested" and "A disallowed URL is recorded as blocked": the `blocked_by_robots` column.
- [ ] 8.3 [3+6] Drive "robots.txt is stored with its origin": the `robots_*` columns of `origins`.
- [ ] 8.4 [CLI] Drive "A blocked Seed is reported".
- [ ] 8.5 [3+6] Drive "Disallowed URLs are crawled and still labelled": `--ignore-robots`.
- [ ] 8.6 [3+6] Drive "A missing robots.txt allows everything".
- [ ] 8.7 [3+6] Drive "An unreachable robots.txt blocks its origin".
- [ ] 8.8 [CLI] Drive "An unreachable robots.txt of the site is reported".
- [ ] 8.9 [3+6] Drive "A redirected robots.txt is followed".
- [ ] 8.10 [3+6] Drive "More than five robots.txt redirects count as missing".
- [ ] 8.11 Docs: document robots.txt handling (status mapping, `--ignore-robots`, `--robots-user-agent`, Crawl-delay) in `docs/crawling.md`.
- [ ] 8.12 Review: run the code-review skill on group 8's commits, then refactor with the whole suite green.

## 9. Politeness and requests without a response

- [ ] 9.1 [Fixture] Add a count of the most simultaneous requests to the fixture site, test-first.
- [ ] 9.2 [HTTP] Drive "At most five requests to a host by default" and "A lower concurrency is honoured": per-host semaphores and the global cap.
- [ ] 9.3 [CLI] Drive "A concurrency of zero is rejected".
- [ ] 9.4 [Fake timing] Drive "Requests to a host are spaced by the rate": introduce the fake Fetcher and the injectable `Clock`, and add `--rate`.
- [ ] 9.5 [Fake timing] Drive "Crawl-delay is not applied".
- [ ] 9.6 [CLI] Drive "Many 403 responses raise one warning": `possible_blocking`.
- [ ] 9.7 [3+6] Drive "An unknown host is a DNS error": the `fetch_error` column.
- [ ] 9.8 [3+6] Drive "A closed port is a refused connection": `fetch_error_message`.
- [ ] 9.9 Docs: document politeness defaults and the `fetch_error` codes in `docs/crawling.md`.
- [ ] 9.10 Review: run the code-review skill on group 9's commits, then refactor with the whole suite green.

## 10. Events and how a Crawl ends

- [ ] 10.1 [CLI] Drive "Every stderr line is an event or a diagnostic".
- [ ] 10.2 [CLI] Drive "A warning is written as a diagnostic": warnings through `010`'s diagnostics writer.
- [ ] 10.3 [3+6] Drive "Warnings are stored as diagnostics": the `crawl.warnings` column in the full diagnostic shape.
- [ ] 10.4 [Fake timing] Drive "Progress events come every 10 seconds".
- [ ] 10.5 [Subprocess, Windows in CI] Drive "Events are UTF-8 on Windows (Windows)".
- [ ] 10.6 [CLI] Drive "An unreachable Seed fails the Crawl": the `failed` Crawl State, the result and exit code 8.
- [ ] 10.7 [CLI] Drive "An unreachable Seed is reported by one error": `seed_unreachable` as the only error line.
- [ ] 10.8 [CLI] Drive "A write failure fails the Crawl", with "disk full" injected once at the file-system boundary.
- [ ] 10.9 [Subprocess, POSIX in CI] Drive "Ctrl+C stops a Crawl on macOS and Linux": the stop flag and the 10-second grace period.
- [ ] 10.10 [Subprocess, Windows in CI] Drive "Ctrl+Break stops a Crawl on Windows (Windows)".
- [ ] 10.11 [Subprocess] Drive "An interrupt is reported by one error": `interrupted` and exit code 130.
- [ ] 10.12 [Subprocess] Drive "An interrupted Crawl keeps its queue".
- [ ] 10.13 [Subprocess] Drive "A second interrupt ends the process at once".
- [ ] 10.14 Docs: document how a Crawl ends (Crawl States, stop reasons, exit codes, partial results) in `docs/crawling.md`.
- [ ] 10.15 Review: run the code-review skill on group 10's commits, then refactor with the whole suite green.

## 11. Persistent frontier, hooks and parse failures

- [ ] 11.1 [Subprocess] Drive "A killed Crawl leaves no half-recorded Page".
- [ ] 11.2 [Services] Drive "Continuing a killed Crawl completes it": the Crawl Service continue operation.
- [ ] 11.3 [Services] Drive "Continuing does not request fetched URLs again".
- [ ] 11.4 [Services, Windows in CI] Drive "A Crawl killed on Windows can be continued (Windows)".
- [ ] 11.5 [Services] Drive "A failed Crawl is continued once its Seed answers": re-queue `error` and `robots_unreachable` URLs on continue.
- [ ] 11.6 [Services] Drive "A registered handler sees every URL once": the per-response hook registry.
- [ ] 11.7 [Services] Drive "Post-crawl passes run before a Crawl is completed": the post-crawl pass registry.
- [ ] 11.8 [Services] Drive "Post-crawl passes run when the URL limit stops a Crawl".
- [ ] 11.9 [Services] Drive "Post-crawl passes do not run for a failed Crawl".
- [ ] 11.10 [Services] Drive "Post-crawl passes run again after a continue".
- [ ] 11.11 [3+6] Drive "An extractor error is recorded": the `parse_error` column.
- [ ] 11.12 [3+6] Drive "The Crawl continues after an extractor error".
- [ ] 11.13 Docs: document the Fetcher interface, the extractor, sink, per-response and post-crawl registries, and `DiscoveredLink`, in `docs/architecture.md` for `022`–`040`.
- [ ] 11.14 Review: run the code-review skill on group 11's commits, then refactor with the whole suite green.

## 12. Change check

- [ ] 12.1 Verify that every `#### Scenario:` in `specs/crawling/spec.md` has exactly one test named after it. Use a small script over the test ids.
- [ ] 12.2 Verify that the whole suite passes in CI on Windows, macOS and Linux × Python 3.12–3.14 with the coverage gate.
- [ ] 12.3 Review: run the code-review skill on the whole change against `specs/crawling/spec.md`, then refactor with the whole suite green.
