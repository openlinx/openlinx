## Purpose

Defines the Rules that turn a Crawl's data into Issues. It covers the Rule model with fixed guidance, the v0.1 catalogue, overrides in `spider.toml`, evaluation during the Crawl and in the post-crawl passes, stored Issues and Affected URLs, the Health Score, and the `spider rules` Command that lets agents inspect them.

## ADDED Requirements

### Requirement: Rule model
Every Rule SHALL have these fields:

- `id`: unique, kebab-case (matching `^[a-z0-9]+(-[a-z0-9]+)*$`), and never renamed or reused in a later release
- `category`
- `issue_type`: `issue`, `warning` or `opportunity`
- `priority`: `high`, `medium` or `low`
- `applies_to`: `internal_urls`, `internal_pages` or `resources`
- `evaluation`: `during_crawl` or `post_crawl`
- `thresholds`: zero or more named, non-negative integer thresholds, each with a default and a unit
- `description`, `why_it_matters` and `how_to_fix`: non-empty English guidance texts

The categories SHALL be, in this order: `response_codes`, `security`, `titles`, `meta_descriptions`, `headings`, `canonicals`, `directives`, `content`, `urls` and `images`.

In the scenarios, `{site}` is the origin of the local fixture site.

#### Scenario: Rule ids are unique kebab-case
- **WHEN** `spider rules list --limit 50` runs
- **THEN** all 42 `id` values match `^[a-z0-9]+(-[a-z0-9]+)*$` and no value appears twice

#### Scenario: Every Rule has its guidance
- **WHEN** `spider rules list --limit 50` runs
- **THEN** 0 items have an empty `description`, `why_it_matters` or `how_to_fix`

### Requirement: What Rules apply to
Each Rule SHALL be evaluated over exactly one population, and its Affected URLs SHALL be members of that population:

- **`internal_urls`**: the rows of the `urls` table of `020-add-crawl-core` (including the columns that `022-add-fetch-policy` adds) with `is_internal` = 1 that were requested (`fetch_state` `fetched` or `error`) or are disallowed by robots.txt (`blocked_by_robots` = 1). Internal URLs outside a Section Crawl's Scope are included.
- **`internal_pages`**: the rows of `030-add-page-data`'s `pages` table whose URL was parsed (`urls.parsed` = 1), which are the analysed Pages. Rules marked *Indexable only* further restrict this to Pages whose `indexability` is `indexable`.
- **`resources`**: URLs that are the target of at least one `image` Link whose source is a Page, and that were requested by `022-add-fetch-policy`'s Resource checks (`fetch_state` `fetched` or `error`), whether Internal or External.

A Rule SHALL NOT fire when a value its condition needs was not measured (NULL). For example, a canonical target that the Crawl never requested produces no Affected URL.

#### Scenario: External URLs are not Internal URLs
- **WHEN** an External URL linked from a Page responded 404
- **THEN** `internal-4xx` has no Affected URL for it

#### Scenario: Non-analysed Pages are skipped by Page Rules
- **WHEN** a Page responded 404 with an HTML body and no `<title>`
- **THEN** `title-missing` has no Affected URL for it

### Requirement: The v0.1 catalogue
The Rule catalogue SHALL contain exactly the 42 Rules defined in the category requirements below, with the Issue Type, Priority, population, evaluation timing, default thresholds, condition and `detail` keys given there. In the tables, *during* means `during_crawl` and *post* means `post_crawl`. Column names refer to the `urls` table and to the tables of `030-add-page-data`.

#### Scenario: Catalogue size
- **WHEN** `spider rules list --limit 50` runs in a Workspace without `[rules]` settings
- **THEN** `total` is 42 and every item has `enabled` true

### Requirement: Response code Rules
The `response_codes` category SHALL contain these Rules, all over `internal_urls`:

| id | Issue Type | Priority | When | Fires for an Internal URL that… | `detail` |
|---|---|---|---|---|---|
| `internal-4xx` | issue | high | during | has a `status_code` from 400 to 499 | `status_code` |
| `internal-5xx` | issue | high | during | has a `status_code` from 500 to 599 | `status_code` |
| `internal-no-response` | issue | high | during | has `fetch_state` `error` | `error`: the URL's `fetch_error` |
| `internal-blocked-by-robots-txt` | warning | medium | during | has `blocked_by_robots` = 1, whether or not it was fetched under `--ignore-robots` | none |
| `internal-3xx` | warning | low | during | has a `status_code` from 300 to 399 | `status_code`, `redirect_url` (the URL that `redirect_url_id` points to, or null) |
| `redirect-chain` | warning | medium | post | has a Redirect Chain of more than `max_hops` redirects (default 1) | `hops`, `final_url` |
| `redirect-loop` | issue | high | post | has `redirect_loop` = 1 | `hops`: the number of URLs in the loop |

A URL's *Redirect Chain length* is the number of 3xx responses met when following `redirect_url_id` from the URL. The walk stops at the first URL that is not a 3xx response, has no `redirect_url_id`, was not requested or was already visited. `final_url` is the URL where the walk stops.

#### Scenario: Client error
- **WHEN** the Internal URL `https://example.test/gone` has `status_code` 404
- **THEN** `internal-4xx` fires for it with `detail` `{"status_code": 404}`

#### Scenario: Client error recorded during the Crawl
- **WHEN** a Crawl of the fixture site requests `{site}/gone`, which responds 404 with `Content-Type: text/plain`
- **THEN** `affected_urls` holds an `internal-4xx` row for `{site}/gone` with `detail` `{"status_code": 404}`

#### Scenario: Server error
- **WHEN** the Internal URL `https://example.test/err` has `status_code` 503
- **THEN** `internal-5xx` fires for it with `detail` `{"status_code": 503}`

#### Scenario: No response
- **WHEN** the Internal URL `https://example.test/slow` has `fetch_state` `error` and `fetch_error` `timeout`
- **THEN** `internal-no-response` fires for it with `detail` `{"error": "timeout"}`

#### Scenario: Blocked even when crawled anyway
- **WHEN** the Internal URL `https://example.test/private/a` has `blocked_by_robots` 1 and was fetched under `--ignore-robots`
- **THEN** `internal-blocked-by-robots-txt` fires for it

#### Scenario: Internal redirect
- **WHEN** the Internal URL `https://example.test/old` has `status_code` 301 and a `redirect_url_id` pointing to `https://example.test/new`
- **THEN** `internal-3xx` fires for it with `detail` `{"status_code": 301, "redirect_url": "https://example.test/new"}`

#### Scenario: Two-hop chain
- **WHEN** `https://example.test/a` redirects to `/b`, which redirects to `/c`, which responds 200
- **THEN** `redirect-chain` fires for `/a` with `detail` `{"hops": 2, "final_url": "https://example.test/c"}`

#### Scenario: One hop is not a chain
- **WHEN** `https://example.test/b` redirects to `/c`, which responds 200
- **THEN** `redirect-chain` has no Affected URL for `/b`

#### Scenario: Loop
- **WHEN** `https://example.test/x` redirects to `/y`, `/y` redirects to `/x`, and both have `redirect_loop` 1
- **THEN** `redirect-loop` fires for both `/x` and `/y` with `detail` `{"hops": 2}`

### Requirement: Security Rule
The `security` category SHALL contain this Rule. It is a Warning, so it never lowers the Health Score. The maintainer decided this on 2026-09-27.

| id | Issue Type | Priority | Applies to | When | Fires for… | `detail` |
|---|---|---|---|---|---|---|
| `http-url` | warning | high | `internal_urls` | during | an Internal URL with the `http` scheme and a `status_code` from 200 to 299 | `status_code` |

#### Scenario: Content served over HTTP
- **WHEN** the Internal URL `http://example.test/a` has `status_code` 200
- **THEN** `http-url` fires for it with `detail` `{"status_code": 200}`

#### Scenario: HTTP URL that redirects to HTTPS
- **WHEN** the Internal URL `http://example.test/b` has `status_code` 301 and redirects to `https://example.test/b`
- **THEN** `http-url` has no Affected URL for it

### Requirement: Title Rules
The `titles` category SHALL contain these Rules, all over `internal_pages`:

| id | Issue Type | Priority | When | Fires for a Page where… | Thresholds | `detail` |
|---|---|---|---|---|---|---|
| `title-missing` | issue | high | during | `title_count` is 0 or `title_1` is the empty string | none | none |
| `title-duplicate` | warning | medium | post | *Indexable only*: `title_1` is non-empty and equal (case-sensitive) to the `title_1` of at least one other Indexable Page | none | `title_1`, `pages` (the size of the group) |
| `title-too-long` | opportunity | medium | during | `title_1_length` > `max_chars` or `title_1_width_px` > `max_pixels` | `max_chars` 60 (characters), `max_pixels` 561 (pixels) | `length`, `width_px` |
| `title-too-short` | opportunity | low | during | `title_1_length` is at least 1 and less than `min_chars` | `min_chars` 30 (characters) | `length` |
| `title-multiple` | issue | medium | during | `title_count` > 1 | none | `count` |
| `title-same-as-h1` | opportunity | low | during | `title_1` is non-empty and equal (case-sensitive) to `h1_1` | none | none |

#### Scenario: Missing title
- **WHEN** an analysed Page has `title_count` 0
- **THEN** `title-missing` fires for it

#### Scenario: Empty title counts as missing
- **WHEN** an analysed Page has `title_count` 1 and `title_1` equal to the empty string
- **THEN** `title-missing` fires for it

#### Scenario: Duplicate titles among Indexable Pages
- **WHEN** two Indexable Pages both have `title_1` `Shoes`
- **THEN** `title-duplicate` fires for both with `detail` `{"title_1": "Shoes", "pages": 2}`

#### Scenario: Non-indexable Pages are not compared
- **WHEN** one Indexable Page and one Page with `indexability_status` `noindex` both have `title_1` `Shoes`
- **THEN** `title-duplicate` has no Affected URLs

#### Scenario: Title too long by characters
- **WHEN** an analysed Page has `title_1_length` 61 and `title_1_width_px` 536
- **THEN** `title-too-long` fires for it with `detail` `{"length": 61, "width_px": 536}`

#### Scenario: Title too long by pixels
- **WHEN** an analysed Page has `title_1_length` 50 and `title_1_width_px` 600
- **THEN** `title-too-long` fires for it

#### Scenario: Title at both limits
- **WHEN** an analysed Page has `title_1_length` 60 and `title_1_width_px` 561
- **THEN** `title-too-long` has no Affected URL for it

#### Scenario: Title too short
- **WHEN** an analysed Page has `title_1_length` 29
- **THEN** `title-too-short` fires for it with `detail` `{"length": 29}`

#### Scenario: Title at the minimum
- **WHEN** an analysed Page has `title_1_length` 30
- **THEN** `title-too-short` has no Affected URL for it

#### Scenario: Multiple titles
- **WHEN** an analysed Page has `title_count` 2
- **THEN** `title-multiple` fires for it with `detail` `{"count": 2}`

#### Scenario: Title equals H1
- **WHEN** an analysed Page has `title_1` `Shoes` and `h1_1` `Shoes`
- **THEN** `title-same-as-h1` fires for it

#### Scenario: Comparison with H1 is case-sensitive
- **WHEN** an analysed Page has `title_1` `Shoes` and `h1_1` `shoes`
- **THEN** `title-same-as-h1` has no Affected URL for it

### Requirement: Meta description Rules
The `meta_descriptions` category SHALL contain these Rules, all over `internal_pages`:

| id | Issue Type | Priority | When | Fires for a Page where… | Thresholds | `detail` |
|---|---|---|---|---|---|---|
| `meta-description-missing` | opportunity | medium | during | `meta_description_count` is 0 or `meta_description_1` is the empty string | none | none |
| `meta-description-duplicate` | opportunity | low | post | *Indexable only*: `meta_description_1` is non-empty and equal (case-sensitive) to that of at least one other Indexable Page | none | `meta_description_1`, `pages` |
| `meta-description-too-long` | opportunity | low | during | `meta_description_1_length` > `max_chars` or `meta_description_1_width_px` > `max_pixels` | `max_chars` 155 (characters), `max_pixels` 985 (pixels) | `length`, `width_px` |
| `meta-description-too-short` | opportunity | low | during | `meta_description_1_length` is at least 1 and less than `min_chars` | `min_chars` 70 (characters) | `length` |
| `meta-description-multiple` | warning | low | during | `meta_description_count` > 1 | none | `count` |

#### Scenario: Missing meta description
- **WHEN** an analysed Page has `meta_description_count` 0
- **THEN** `meta-description-missing` fires for it

#### Scenario: Duplicate meta descriptions
- **WHEN** three Indexable Pages have `meta_description_1` `Buy shoes online`
- **THEN** `meta-description-duplicate` fires for all three with `detail` `{"meta_description_1": "Buy shoes online", "pages": 3}`

#### Scenario: Meta description too long
- **WHEN** an analysed Page has `meta_description_1_length` 156 and `meta_description_1_width_px` 900
- **THEN** `meta-description-too-long` fires for it with `detail` `{"length": 156, "width_px": 900}`

#### Scenario: Meta description at both limits
- **WHEN** an analysed Page has `meta_description_1_length` 155 and `meta_description_1_width_px` 985
- **THEN** `meta-description-too-long` has no Affected URL for it

#### Scenario: Meta description too short
- **WHEN** an analysed Page has `meta_description_1_length` 69
- **THEN** `meta-description-too-short` fires for it with `detail` `{"length": 69}`

#### Scenario: Multiple meta descriptions
- **WHEN** an analysed Page has `meta_description_count` 2
- **THEN** `meta-description-multiple` fires for it with `detail` `{"count": 2}`

### Requirement: Heading Rules
The `headings` category SHALL contain these Rules, all over `internal_pages`:

| id | Issue Type | Priority | When | Fires for a Page where… | Thresholds | `detail` |
|---|---|---|---|---|---|---|
| `h1-missing` | warning | medium | during | `h1_count` is 0 or `h1_1` is the empty string | none | none |
| `h1-duplicate` | opportunity | low | post | *Indexable only*: `h1_1` is non-empty and equal (case-sensitive) to that of at least one other Indexable Page | none | `h1_1`, `pages` |
| `h1-multiple` | warning | low | during | `h1_count` > 1 | none | `count` |
| `h1-too-long` | opportunity | low | during | `h1_1_length` > `max_chars` | `max_chars` 70 (characters) | `length` |
| `h2-missing` | opportunity | low | during | `h2_count` is 0 or `h2_1` is the empty string | none | none |

#### Scenario: Missing H1
- **WHEN** an analysed Page has `h1_count` 0
- **THEN** `h1-missing` fires for it

#### Scenario: Duplicate H1
- **WHEN** two Indexable Pages both have `h1_1` `Welcome`
- **THEN** `h1-duplicate` fires for both with `detail` `{"h1_1": "Welcome", "pages": 2}`

#### Scenario: Multiple H1
- **WHEN** an analysed Page has `h1_count` 3
- **THEN** `h1-multiple` fires for it with `detail` `{"count": 3}`

#### Scenario: H1 too long
- **WHEN** an analysed Page has `h1_1_length` 71
- **THEN** `h1-too-long` fires for it with `detail` `{"length": 71}`

#### Scenario: H1 at the limit
- **WHEN** an analysed Page has `h1_1_length` 70
- **THEN** `h1-too-long` has no Affected URL for it

#### Scenario: Missing H2
- **WHEN** an analysed Page has `h2_count` 0
- **THEN** `h2-missing` fires for it

### Requirement: Canonical Rules
The `canonicals` category SHALL contain these Rules, all over `internal_pages`:

| id | Issue Type | Priority | When | Fires for a Page where… | `detail` |
|---|---|---|---|---|---|
| `canonical-missing` | warning | medium | during | `canonical_count` is 0, and `meta_robots_noindex` and `x_robots_tag_noindex` are both 0 | none |
| `canonicalised` | warning | medium | during | `indexability_status` is `canonicalised` | `canonical_url` |
| `canonical-to-non-indexable` | issue | high | post | `canonical_url` is non-NULL and differs from the Page's URL, and the *target's Indexability* is non-indexable (defined below) | `canonical_url`, `indexability_status` (the target's reason) |
| `canonical-conflicting` | issue | high | during | `canonical_count` ≥ 2 and `canonical_url` is NULL | `canonical_link_element_1`, `canonical_link_element_2`, `http_canonical` |
| `canonical-relative` | warning | low | during | `canonical_relative` is 1 | none |

The *target's Indexability* SHALL come from `030-add-page-data`:

- **When the target is a Page,** it is the Page's stored `indexability` and `indexability_status`.
- **When the target is not a Page,** steps 1–4 of 030's Indexability order are applied to the target's `urls` row: `blocked_by_robots_txt`, `redirected`, `client_error` or `server_error`. A target with `fetch_state` `error` is non-indexable with the reason `no_response`. A target with any other outcome, such as a 2xx response that is not HTML, counts as indexable. A target that was never requested has no Indexability, and the Rule does not fire.

#### Scenario: Missing canonical
- **WHEN** an analysed Page has `canonical_count` 0 and no noindex directive
- **THEN** `canonical-missing` fires for it

#### Scenario: Noindex Page needs no canonical
- **WHEN** an analysed Page has `canonical_count` 0 and `meta_robots_noindex` 1
- **THEN** `canonical-missing` has no Affected URL for it

#### Scenario: Canonicalised Page
- **WHEN** the analysed Page `https://example.test/a` has `indexability_status` `canonicalised` and `canonical_url` `https://example.test/b`
- **THEN** `canonicalised` fires for it with `detail` `{"canonical_url": "https://example.test/b"}`

#### Scenario: Canonical to a redirect
- **WHEN** `https://example.test/a` has `canonical_url` `https://example.test/b`, and `/b` is a Page with `indexability_status` `redirected`
- **THEN** `canonical-to-non-indexable` fires for `/a` with `detail` `{"canonical_url": "https://example.test/b", "indexability_status": "redirected"}`

#### Scenario: Canonical to a noindex Page
- **WHEN** `https://example.test/a` has `canonical_url` `https://example.test/b`, and `/b` is a 200 Page with `indexability_status` `noindex`
- **THEN** `canonical-to-non-indexable` fires for `/a` with `detail` `{"canonical_url": "https://example.test/b", "indexability_status": "noindex"}`

#### Scenario: Canonical to a URL without a response
- **WHEN** `https://example.test/a` has `canonical_url` `https://example.test/b`, and `/b` is not a Page and has `fetch_state` `error`
- **THEN** `canonical-to-non-indexable` fires for `/a` with `detail` `{"canonical_url": "https://example.test/b", "indexability_status": "no_response"}`

#### Scenario: Canonical to an indexable Page
- **WHEN** `https://example.test/a` has `canonical_url` `https://example.test/b`, and `/b` is a 200 Page with `indexability` `indexable`
- **THEN** `canonical-to-non-indexable` has no Affected URL for `/a`

#### Scenario: Canonical to a non-HTML 200 response
- **WHEN** `https://example.test/a` has `canonical_url` `https://example.test/doc.pdf`, which responded 200 with `Content-Type: application/pdf`
- **THEN** `canonical-to-non-indexable` has no Affected URL for `/a`

#### Scenario: Canonical target never requested
- **WHEN** `https://example.test/a` has `canonical_url` `https://other.test/b`, whose `urls` row has `fetch_state` `skipped` and `blocked_by_robots` NULL
- **THEN** `canonical-to-non-indexable` has no Affected URL for `/a`

#### Scenario: Conflicting canonicals
- **WHEN** an analysed Page has `canonical_count` 2, `canonical_url` NULL, `canonical_link_element_1` `https://example.test/b`, `canonical_link_element_2` NULL and `http_canonical` `https://example.test/c`
- **THEN** `canonical-conflicting` fires for it with `detail` `{"canonical_link_element_1": "https://example.test/b", "canonical_link_element_2": null, "http_canonical": "https://example.test/c"}`

#### Scenario: Agreeing canonicals
- **WHEN** an analysed Page has `canonical_count` 2 and `canonical_url` `https://example.test/b`
- **THEN** `canonical-conflicting` has no Affected URL for it

#### Scenario: Relative canonical
- **WHEN** an analysed Page has `canonical_relative` 1
- **THEN** `canonical-relative` fires for it

### Requirement: Directive Rules
The `directives` category SHALL contain these Rules, all over `internal_pages`:

| id | Issue Type | Priority | When | Fires for a Page where… | `detail` |
|---|---|---|---|---|---|
| `noindex` | warning | high | during | `meta_robots_noindex` or `x_robots_tag_noindex` is 1 | `sources`: the sources that apply, as a list in the order `meta_robots`, `x_robots_tag` |
| `nofollow` | warning | medium | during | `meta_robots_nofollow` or `x_robots_tag_nofollow` is 1 | `sources`, in the same way |
| `meta-refresh` | warning | low | during | `meta_refresh` is non-NULL | `meta_refresh`, `redirect_url` |

#### Scenario: Noindex from X-Robots-Tag only
- **WHEN** an analysed Page has `meta_robots_noindex` 0 and `x_robots_tag_noindex` 1
- **THEN** `noindex` fires for it with `detail` `{"sources": ["x_robots_tag"]}`

#### Scenario: Noindex from both sources
- **WHEN** an analysed Page has `meta_robots_noindex` 1 and `x_robots_tag_noindex` 1
- **THEN** `noindex` fires for it with `detail` `{"sources": ["meta_robots", "x_robots_tag"]}`

#### Scenario: Nofollow from meta robots
- **WHEN** an analysed Page has `meta_robots_nofollow` 1 and `x_robots_tag_nofollow` 0
- **THEN** `nofollow` fires for it with `detail` `{"sources": ["meta_robots"]}`

#### Scenario: Meta refresh used
- **WHEN** the analysed Page `https://example.test/old` has `meta_refresh` `0; url=/new` and `redirect_url` `https://example.test/new`
- **THEN** `meta-refresh` fires for it with `detail` `{"meta_refresh": "0; url=/new", "redirect_url": "https://example.test/new"}`

### Requirement: Content Rules
The `content` category SHALL contain these Rules, both over `internal_pages`:

| id | Issue Type | Priority | When | Fires for a Page where… | Thresholds | `detail` |
|---|---|---|---|---|---|---|
| `low-word-count` | opportunity | medium | during | *Indexable only*: `word_count` < `min_words` | `min_words` 200 (words) | `word_count` |
| `exact-duplicate` | issue | medium | post | *Indexable only*: `content_hash` is non-NULL and equal to that of at least one other Indexable Page | none | `content_hash`, `pages` |

#### Scenario: Thin Page
- **WHEN** an Indexable Page has `word_count` 199
- **THEN** `low-word-count` fires for it with `detail` `{"word_count": 199}`

#### Scenario: Word count at the minimum
- **WHEN** an Indexable Page has `word_count` 200
- **THEN** `low-word-count` has no Affected URL for it

#### Scenario: Thin noindex Page is ignored
- **WHEN** a Page with `indexability_status` `noindex` has `word_count` 10
- **THEN** `low-word-count` has no Affected URL for it

#### Scenario: Exact Duplicates
- **WHEN** three Indexable Pages have `content_hash` `64ec88ca00b268e5ba1a35678a1b5316d212f4f366b2477232534a8aeca37f3c`
- **THEN** `exact-duplicate` fires for all three with `detail` `{"content_hash": "64ec88ca00b268e5ba1a35678a1b5316d212f4f366b2477232534a8aeca37f3c", "pages": 3}`

#### Scenario: Pages without a hash are not duplicates
- **WHEN** two Indexable Pages both have `content_hash` NULL
- **THEN** `exact-duplicate` has no Affected URLs

### Requirement: URL Rules
The `urls` category SHALL contain these Rules, all over `internal_pages`. The *path* and *query* are those of the Page's `address`, and the host is never checked.

| id | Issue Type | Priority | When | Fires for a Page where… | Thresholds | `detail` |
|---|---|---|---|---|---|---|
| `url-uppercase` | opportunity | low | during | the path or query contains an uppercase letter (Unicode category Lu), ignoring `%XX` escapes | none | none |
| `url-underscores` | opportunity | low | during | the path contains `_` | none | none |
| `url-parameters` | opportunity | low | during | the query is non-empty | none | none |
| `url-too-long` | opportunity | low | during | `url_encoded_address` is longer than `max_chars` characters | `max_chars` 115 (characters) | `length` |
| `url-non-ascii` | opportunity | low | during | the path or query contains a non-ASCII character | none | none |

#### Scenario: Uppercase letters in the path
- **WHEN** an analysed Page has `address` `https://example.test/Shoes`
- **THEN** `url-uppercase` fires for it

#### Scenario: Uppercase percent escapes are ignored
- **WHEN** an analysed Page has `address` `https://example.test/a%2Fb`
- **THEN** `url-uppercase` has no Affected URL for it

#### Scenario: Underscore in the path
- **WHEN** an analysed Page has `address` `https://example.test/red_shoes`
- **THEN** `url-underscores` fires for it

#### Scenario: Underscore only in the query
- **WHEN** an analysed Page has `address` `https://example.test/shoes?utm_source=x`
- **THEN** `url-underscores` has no Affected URL for it

#### Scenario: Parameters
- **WHEN** an analysed Page has `address` `https://example.test/shoes?page=2`
- **THEN** `url-parameters` fires for it

#### Scenario: URL too long
- **WHEN** an analysed Page's `url_encoded_address` is 116 characters long
- **THEN** `url-too-long` fires for it with `detail` `{"length": 116}`

#### Scenario: URL at the limit
- **WHEN** an analysed Page's `url_encoded_address` is 115 characters long
- **THEN** `url-too-long` has no Affected URL for it

#### Scenario: Non-ASCII path
- **WHEN** an analysed Page has `address` `https://example.test/über`
- **THEN** `url-non-ascii` fires for it

#### Scenario: Non-ASCII host only
- **WHEN** an analysed Page has `address` `https://bücher.test/`
- **THEN** `url-non-ascii` has no Affected URL for it

### Requirement: Image Rules
The `images` category SHALL contain these Rules:

| id | Issue Type | Priority | Applies to | When | Fires for… | Thresholds | `detail` |
|---|---|---|---|---|---|---|---|
| `image-missing-alt-text` | opportunity | low | `internal_pages` | during | a Page with at least one `image` Link whose `element` is `img`, `attribute` is `src`, and `alt_text` is NULL or the empty string | none | `missing_alt_attribute` (count of NULL), `empty_alt` (count of empty) |
| `image-too-large` | opportunity | medium | `resources` | post | an image Resource whose `urls.size_bytes` is more than `max_kb` × 1024 | `max_kb` 100 (kilobytes of 1024 bytes) | `size_bytes` |
| `image-broken` | issue | medium | `resources` | post | an image Resource with a `status_code` from 400 to 599, or with `fetch_state` `error` | none | `status_code` or `error` (the `fetch_error`) |

#### Scenario: Images without alt text
- **WHEN** an analysed Page has one `img`/`src` `image` Link with `alt_text` NULL and one with `alt_text` equal to the empty string
- **THEN** `image-missing-alt-text` fires for the Page with `detail` `{"missing_alt_attribute": 1, "empty_alt": 1}`

#### Scenario: Srcset candidates are not counted twice
- **WHEN** an analysed Page's only image is `<img src="/a.png" srcset="/a-2x.png 2x">` without `alt`
- **THEN** `image-missing-alt-text` fires for the Page with `detail` `{"missing_alt_attribute": 1, "empty_alt": 0}`

#### Scenario: All images described
- **WHEN** every `image` Link of an analysed Page has `alt_text` `Logo`
- **THEN** `image-missing-alt-text` has no Affected URL for it

#### Scenario: Image over the size limit
- **WHEN** the image Resource `https://example.test/hero.jpg` has `size_bytes` 102401
- **THEN** `image-too-large` fires for it with `detail` `{"size_bytes": 102401}`

#### Scenario: Image at the size limit
- **WHEN** the image Resource `https://example.test/hero.jpg` has `size_bytes` 102400
- **THEN** `image-too-large` has no Affected URL for it

#### Scenario: Broken external image
- **WHEN** a Page links the External image `https://cdn.other.test/x.png`, which has `status_code` 404
- **THEN** `image-broken` fires for it with `detail` `{"status_code": 404}`

### Requirement: Threshold overrides and disabling Rules
A table `[rules.<id>]` in the Workspace's `spider.toml` SHALL be able to set:

- `enabled = false` to disable that Rule
- any of the Rule's thresholds, by name, to a non-negative integer that replaces the default

The table name is the Rule id itself. These settings mirror no flag, so `010-add-workspace-and-cli-contract`'s flag-mirroring rule for keys does not apply to them. A disabled Rule SHALL NOT be evaluated and SHALL produce no Issue.

#### Scenario: Raised title limit
- **WHEN** `spider.toml` has `[rules.title-too-long]` with `max_chars = 70`, and an analysed Page has `title_1_length` 65 and `title_1_width_px` 420
- **THEN** `title-too-long` has no Affected URL for it

#### Scenario: Disabled Rule produces no Issue
- **WHEN** `spider.toml` has `[rules.h2-missing]` with `enabled = false`, and a Crawl of the fixture site stores Pages without `<h2>`
- **THEN** `issues` holds no row for `h2-missing`

#### Scenario: Override shown by the rules Command
- **WHEN** `spider.toml` has `[rules.title-too-long]` with `max_chars = 70` and `spider rules show title-too-long` runs
- **THEN** its output has `thresholds.max_chars` equal to `{"value": 70, "default": 60, "unit": "characters"}`

### Requirement: Invalid Rule configuration is rejected
Any Command that loads the Workspace's `spider.toml` SHALL fail with the settings error of `010-add-workspace-and-cli-contract` (exit code 3, error code `settings_invalid`), which is checked when the settings load. It SHALL do so in any of these cases:

- `[rules]` names an unknown Rule id
- a Rule table has a key other than `enabled` or one of that Rule's threshold names
- a threshold is not a non-negative integer
- `enabled` is not a boolean

Each problem's `details.errors[].key` SHALL be the dotted key, for example `rules.title-to-long`, and the hint SHALL name the closest known Rule id or key when there is one. `spider crawl` SHALL fail before any URL is requested.

#### Scenario: Misspelt Rule id
- **WHEN** `spider.toml` has `[rules.title-to-long]` and `spider rules list` runs
- **THEN** the exit code is 3, the error has the code `settings_invalid` and `details.errors[0].key` `"rules.title-to-long"`, and the hint contains `title-too-long`

#### Scenario: Negative threshold
- **WHEN** `spider.toml` has `[rules.low-word-count]` with `min_words = -5` and `spider crawl {site}/` runs
- **THEN** the exit code is 3, `details.errors[0].key` is `"rules.low-word-count.min_words"`, and the fixture site receives 0 requests

#### Scenario: Unknown key
- **WHEN** `spider.toml` has `[rules.h2-missing]` with `max_chars = 10` and `spider rules list` runs
- **THEN** the exit code is 3 and `details.errors[0].key` is `"rules.h2-missing.max_chars"`

### Requirement: Rule configuration is fixed per Crawl
When a Crawl starts, it SHALL resolve every Rule's enabled state and effective thresholds and write them to its `rules` table. That table holds one row per catalogue Rule, with these columns:

- `id`, `category`, `issue_type`, `priority`, `applies_to` and `evaluation`
- `enabled`: 0 or 1
- `thresholds`: a JSON object mapping threshold names to effective values
- `description`, `why_it_matters` and `how_to_fix`

The Crawl SHALL use this configuration throughout, including after `resume`. Editing `spider.toml` later SHALL NOT change the Issues stored for an existing Crawl. v0.1 has no Command that recomputes them; `rules apply` arrives in v0.2.

#### Scenario: Crawl records the thresholds it used
- **WHEN** a Crawl runs with `[rules.low-word-count]` `min_words = 300`
- **THEN** its `rules` row for `low-word-count` has `thresholds` `{"min_words": 300}`

#### Scenario: Later edits do not change a completed Crawl
- **WHEN** a Crawl ended as `completed` with the default `min_words` and `spider.toml` then sets `min_words = 5000`
- **THEN** that Crawl's `issues` and `affected_urls` rows for `low-word-count` are unchanged

#### Scenario: Resumed Crawl keeps the recorded configuration
- **WHEN** a Crawl started with `min_words = 300` stops at its `--max-urls` limit, `spider.toml` is changed to `min_words = 50`, and the Crawl is resumed through the Crawl Service with a higher limit
- **THEN** an Indexable Page with `word_count` 120 written after the resume is an Affected URL of `low-word-count`

### Requirement: Evaluation during the Crawl
Rules whose `evaluation` is `during_crawl` SHALL be evaluated for each Internal URL or Page in the writer unit that records it. URL Rules run from the per-response hook of `020-add-crawl-core`, which runs for every recorded URL. Page Rules run with the Page's data from `030-add-page-data`. Their Affected URLs and `issues` counts SHALL be written in that same writer unit, so they can be queried while the Crawl runs.

#### Scenario: Issue visible before the Crawl ends
- **WHEN** the fixture Page `{site}/notitle` has been written and the Crawl is still waiting on `{site}/slow`, which delays its response by 5 s
- **THEN** `affected_urls` already holds a `title-missing` row for `{site}/notitle`

#### Scenario: Post-crawl Rules wait for the passes
- **WHEN** two fixture Pages with the title `Shoes` have been written and the Crawl is still `running`
- **THEN** `affected_urls` holds no `title-duplicate` rows

### Requirement: Post-crawl passes
The Rules whose `evaluation` is `post_crawl` SHALL be evaluated over the whole Crawl in the post-crawl passes of `020-add-crawl-core`. Those run when a Crawl ends as `completed` or `stopped`, and again when a resumed Crawl ends. They SHALL run after `030-add-page-data` has computed link counts, and before the Health Score is calculated. Each run SHALL replace the results of `post_crawl` Rules from any earlier run for the same Crawl, so an Affected URL is never stored twice.

#### Scenario: Duplicates found by the post-crawl passes
- **WHEN** a Crawl of two fixture Pages with the title `Shoes` ends as `completed`
- **THEN** `affected_urls` holds exactly 2 `title-duplicate` rows

#### Scenario: A second pass does not duplicate rows
- **WHEN** the post-crawl passes run a second time on that Crawl
- **THEN** `affected_urls` still holds exactly 2 `title-duplicate` rows

### Requirement: Issues and Affected URLs are stored
The crawl store SHALL hold two tables for results:

- **`issues`**: one row per Rule that has at least one Affected URL. Its columns are `rule_id` (references `rules.id`), `category`, `issue_type`, `priority` and `affected_count` (the number of its Affected URLs).
- **`affected_urls`**: one row per Rule and Affected URL. Its columns are:
  - `rule_id` (references `rules.id`)
  - `url_id` (references `urls.id`)
  - `detail`: a JSON object with the keys listed for the Rule, or NULL when the Rule lists none

`(rule_id, url_id)` SHALL be unique. A Rule that did not fire SHALL have no `issues` row.

#### Scenario: Issue row counts its Affected URLs
- **WHEN** a Crawl of the fixture site ends as `completed` with two Pages that have no `<title>`
- **THEN** the `issues` row for `title-missing` has `category` `titles`, `issue_type` `issue`, `priority` `high` and `affected_count` 2

#### Scenario: Detail is stored as JSON
- **WHEN** a Crawl stores the fixture Page `{site}/long-title`, whose title is `Buy running shoes, trail boots and sandals online at low cost`
- **THEN** its `affected_urls` row for `title-too-long` has `detail` `{"length": 61, "width_px": 536}`

#### Scenario: Rule that did not fire has no Issue
- **WHEN** a Crawl ends as `completed` and no Page has more than one `<title>`
- **THEN** `issues` holds no row for `title-multiple`

### Requirement: Health Score
The Health Score of a Crawl SHALL be `floor(100 × (N − A) ÷ N)`:

- N is the number of Internal Pages, meaning rows of `pages` with any status code.
- A is the number of those Pages that are an Affected URL of at least one Rule whose `issue_type` in the Crawl's `rules` table is `issue`.

Warnings, including `http-url`, and Opportunities never lower it.

At the end of the post-crawl passes, the Crawl SHALL record these crawl metadata fields on the `crawl` row of `015-add-crawl-store`:

- `health_score_pct`: the Health Score, or NULL when N is 0
- `health_internal_pages`: N
- `health_affected_pages`: A
- `health_calculated_at`: a `timestamp`

Until the post-crawl passes have run, all four fields SHALL be NULL. The Health Score of any subset of Internal Pages, such as a Segment, SHALL use the same formula restricted to that subset, through one function that `050-add-query-and-segments` and `070-add-html-report` call at query time.

#### Scenario: Pages with Issue-type Issues lower the score
- **WHEN** a Crawl has 10 Internal Pages, 3 of which are Affected URLs of Rules whose Issue Type is `issue`
- **THEN** `health_score_pct` is 70, `health_internal_pages` is 10 and `health_affected_pages` is 3

#### Scenario: Score is rounded down
- **WHEN** a Crawl has 3 Internal Pages and 1 of them is an Affected URL of `title-missing`
- **THEN** `health_score_pct` is 66

#### Scenario: Warnings do not lower the score
- **WHEN** a Crawl has 2 Internal Pages and both are Affected URLs of `http-url` (Issue Type `warning`) only
- **THEN** `health_score_pct` is 100

#### Scenario: A Page with several Issues counts once
- **WHEN** a Crawl has 4 Internal Pages and one of them is an Affected URL of both `title-missing` and `exact-duplicate`
- **THEN** `health_score_pct` is 75

#### Scenario: Resource Issues do not change the score
- **WHEN** a Crawl has 1 Internal Page and the only Affected URL is the image Resource `https://example.test/x.png` of `image-broken`
- **THEN** `health_score_pct` is 100

#### Scenario: No Pages means no score
- **WHEN** a Crawl ends as `completed` with 0 Internal Pages
- **THEN** `health_score_pct` is NULL and `health_internal_pages` is 0

#### Scenario: Score before the passes
- **WHEN** a Crawl is still `running`
- **THEN** `health_score_pct` is NULL

#### Scenario: Health Score of a Segment
- **WHEN** the Health Score function is called with a subset of 4 Internal Pages, 1 of which is an Affected URL of an Issue-type Rule
- **THEN** it returns 75

#### Scenario: End-to-end score on the fixture site
- **WHEN** a Crawl of 4 fixture Pages on the plain-HTTP fixture site ends as `completed`, with one Page without a `<title>` and no other Issue-type problem
- **THEN** `health_score_pct` is 75

### Requirement: List Rules
`spider rules` and `spider rules list` SHALL print the Rules as configured in the current Workspace, without reading any Crawl. The output SHALL follow the output contract of `010-add-workspace-and-cli-contract`: the paging envelope `{total, items, next_cursor}` and the `--fields`, `--limit`, `--cursor` and `--format` options. Items SHALL be in catalogue order: by category, in the order of the Rule model, then in the order the Rules appear in their category's table. Each item SHALL have these fields:

- `id`, `category`, `issue_type`, `priority`, `applies_to`, `evaluation` and `enabled`
- `thresholds`: an object that maps each threshold name to `{value, default, unit}`, where the unit is `characters`, `pixels`, `words`, `kilobytes` or `hops`
- `description`, `why_it_matters` and `how_to_fix`

#### Scenario: First Rule in the list
- **WHEN** `spider rules list --limit 1` runs without `[rules]` settings
- **THEN** `items[0].id` is `internal-4xx`, `items[0].category` is `response_codes` and `next_cursor` is not null

#### Scenario: Rule without thresholds
- **WHEN** `spider rules list --limit 50` runs
- **THEN** the item with `id` `title-missing` has `thresholds` `{}`

#### Scenario: Disabled Rule is listed
- **WHEN** `spider.toml` has `[rules.url-parameters]` with `enabled = false` and `spider rules list --limit 50` runs
- **THEN** the item with `id` `url-parameters` has `enabled` false

### Requirement: Show one Rule
`spider rules show <id>` SHALL print one JSON object with the same fields as a list item. An unknown id SHALL fail with the error code `rule_not_found`, which maps to exit code 4 under the rules of `010-add-workspace-and-cli-contract`. Its `message` SHALL contain the id and its `hint` SHALL mention `spider rules list`.

#### Scenario: Show a Rule with thresholds
- **WHEN** `spider rules show title-too-long` runs without `[rules]` settings
- **THEN** it exits 0 and prints `category` `titles`, `issue_type` `opportunity`, `priority` `medium` and `thresholds` `{"max_chars": {"value": 60, "default": 60, "unit": "characters"}, "max_pixels": {"value": 561, "default": 561, "unit": "pixels"}}`

#### Scenario: Unknown Rule id
- **WHEN** `spider rules show nope` runs
- **THEN** the exit code is 4, the error has the code `rule_not_found`, its `message` contains `nope` and its `hint` contains `spider rules list`

#### Scenario: Windows console output
- **WHEN** `spider rules show title-too-long` runs as a subprocess on Windows with console code page 1251
- **THEN** its stdout bytes decode as UTF-8 into a JSON object whose `id` is `title-too-long`

### Requirement: Documented Rule tables
`spider schema` SHALL list the tables `rules`, `issues` and `affected_urls`, and the four `health_*` fields of the `crawl` table, following the table conventions of `015-add-crawl-store`:

- `references` for `rule_id` and `url_id`
- the `json` format for `thresholds` and `detail`
- the `timestamp` format for `health_calculated_at`
- `values` for `category`, `issue_type`, `priority`, `applies_to` and `evaluation`

`docs/schema.md` SHALL document them as `015-add-crawl-store` requires.

#### Scenario: Issue Types are an enumeration
- **WHEN** `spider schema issues` runs
- **THEN** the `values` of the column `issue_type` are `["issue","warning","opportunity"]`

#### Scenario: Categories are an enumeration
- **WHEN** `spider schema rules` runs
- **THEN** the `values` of the column `category` are `["response_codes","security","titles","meta_descriptions","headings","canonicals","directives","content","urls","images"]`
