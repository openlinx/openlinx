## Purpose

Defines the Rules that turn a Crawl's data into Issues. It covers the Rule model with fixed guidance, the v0.1 catalogue, overrides in `spider.toml`, each Rule's reproducing query, Issues read live during a Crawl and materialised by the post-crawl pass, stored Issues and Affected URLs, the Health Score, and the `spider rules` Command that lets agents inspect them.

## ADDED Requirements

### Requirement: Rule model
Every Rule SHALL have these fields:

- `id`: unique, kebab-case (matching `^[a-z0-9]+(-[a-z0-9]+)*$`), and never renamed or reused in a later release
- `category`
- `issue_type`: `issue`, `warning` or `opportunity`
- `priority`: `high`, `medium` or `low`
- `applies_to`: `internal_urls`, `internal_pages` or `resources`
- `thresholds`: zero or more named, non-negative integer thresholds, each with a default and a unit
- `description`, `why_it_matters` and `how_to_fix`: non-empty English guidance texts
- `reproduce_sql`: the Rule's reproducing query, which is how the Rule is evaluated (see "Rules are SQL queries")

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

- **`internal_urls`**: the rows of the `urls` table of `020-add-crawl-core` (including the columns that `022-add-fetch-policy` adds) with `is_internal` = 1 that were requested (`fetch_state` `fetched` or `error`) or are disallowed by robots.txt (`blocked_by_robots_txt` = 1). Internal URLs outside a Section Crawl's Scope are included.
- **`internal_pages`**: the rows of `030-add-page-data`'s `pages` table whose URL was parsed (`urls.parsed` = 1), which are the analysed Pages. Rules marked *Indexable only* further restrict this to Pages whose `indexability` is `indexable`.
- **`resources`**: image Resources, meaning URLs that are the target of at least one `image` Link whose source is a Page, and that were requested by `022-add-fetch-policy`'s Resource checks (`fetch_state` `fetched` or `error`), whether Internal or External. A Resource is a non-HTML file that a Page references (CONTEXT.md); the Rules of this catalogue check only images.

A Rule SHALL NOT fire when a value its condition needs was not measured (NULL). For example, a canonical target that the Crawl never requested produces no Affected URL.

#### Scenario: External URLs are not Internal URLs
- **WHEN** an External URL linked from a Page responded 404
- **THEN** `internal-4xx` has no Affected URL for it

#### Scenario: Non-analysed Pages are skipped by Page Rules
- **WHEN** a Page responded 404 with an HTML body and no `<title>`
- **THEN** `title-missing` has no Affected URL for it

### Requirement: The v0.1 catalogue
The Rule catalogue SHALL contain exactly the 42 Rules defined in the category requirements below, with the Issue Type, Priority, population, default thresholds, condition and `detail` keys given there. Column names refer to the `urls` table and to the tables of `030-add-page-data`.

#### Scenario: Catalogue size
- **WHEN** `spider rules list --limit 50` runs in a Workspace without `[rules]` settings
- **THEN** `total` is 42 and every item has `enabled` true

### Requirement: Response code Rules
The `response_codes` category SHALL contain these Rules, all over `internal_urls`:

| id | Issue Type | Priority | Fires for an Internal URL that… | `detail` |
|---|---|---|---|---|
| `internal-4xx` | issue | high | has a `status_code` from 400 to 499 | `status_code` |
| `internal-5xx` | issue | high | has a `status_code` from 500 to 599 | `status_code` |
| `internal-no-response` | issue | high | has `fetch_state` `error` and a `fetch_error` other than `record_failed` | `error`: the URL's `fetch_error` |
| `internal-blocked-by-robots-txt` | warning | medium | has `blocked_by_robots_txt` = 1, whether or not it was fetched under `--ignore-robots` | none |
| `internal-3xx` | warning | low | has a `status_code` from 300 to 399 | `status_code`, `redirect_url` (the URL that `redirect_url_id` points to, or null) |
| `redirect-chain` | warning | medium | has a Redirect Chain of more than `max_hops` redirects (default 1) | `hops`, `final_url` |
| `redirect-loop` | issue | high | has `in_redirect_loop` = 1 | `hops`: the number of URLs in the loop |

A URL's *Redirect Chain length* is the number of 3xx responses met when following `redirect_url_id` from the URL. The walk stops at the first URL that is not a 3xx response, has no `redirect_url_id`, was not requested or was already visited. `final_url` is the URL where the walk stops.

`fetch_error` `record_failed` means that the Crawl received a response but could not record it (`020-add-crawl-core`). That is the tool's failure, not the site's, so it is no Issue: the `record_failed` warning reports it, and a continue requests the URL again. `image-broken` excludes it the same way.

#### Scenario: Client error
- **WHEN** the Internal URL `https://example.test/gone` has `status_code` 404
- **THEN** `internal-4xx` fires for it with `detail` `{"status_code": 404}`

#### Scenario: Client error recorded by a Crawl
- **WHEN** a Crawl of the fixture site requests `{site}/gone`, which responds 404 with `Content-Type: text/plain`, and ends as `completed`
- **THEN** `affected_urls` holds an `internal-4xx` row for `{site}/gone` with `detail` `{"status_code": 404}`

#### Scenario: Server error
- **WHEN** the Internal URL `https://example.test/err` has `status_code` 503
- **THEN** `internal-5xx` fires for it with `detail` `{"status_code": 503}`

#### Scenario: No response
- **WHEN** the Internal URL `https://example.test/slow` has `fetch_state` `error` and `fetch_error` `timeout`
- **THEN** `internal-no-response` fires for it with `detail` `{"error": "timeout"}`

#### Scenario: A URL that failed to be recorded is no Issue
- **WHEN** the Internal URL `https://example.test/odd` has `fetch_state` `error` and `fetch_error` `record_failed`
- **THEN** `internal-no-response` has no Affected URL for it

#### Scenario: Blocked even when crawled anyway
- **WHEN** the Internal URL `https://example.test/private/a` has `blocked_by_robots_txt` 1 and was fetched under `--ignore-robots`
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
- **WHEN** `https://example.test/x` redirects to `/y`, `/y` redirects to `/x`, and both have `in_redirect_loop` 1
- **THEN** `redirect-loop` fires for both `/x` and `/y` with `detail` `{"hops": 2}`

### Requirement: Security Rule
The `security` category SHALL contain this Rule. It is a Warning, so it never lowers the Health Score. The maintainer decided this on 2026-09-27.

| id | Issue Type | Priority | Applies to | Fires for… | `detail` |
|---|---|---|---|---|---|
| `http-url` | warning | high | `internal_urls` | an Internal URL with the `http` scheme and a `status_code` from 200 to 299 | `status_code` |

#### Scenario: Content served over HTTP
- **WHEN** the Internal URL `http://example.test/a` has `status_code` 200
- **THEN** `http-url` fires for it with `detail` `{"status_code": 200}`

#### Scenario: HTTP URL that redirects to HTTPS
- **WHEN** the Internal URL `http://example.test/b` has `status_code` 301 and redirects to `https://example.test/b`
- **THEN** `http-url` has no Affected URL for it

### Requirement: Title Rules
The `titles` category SHALL contain these Rules, all over `internal_pages`:

| id | Issue Type | Priority | Fires for a Page where… | Thresholds | `detail` |
|---|---|---|---|---|---|
| `title-missing` | issue | high | `title_count` is 0 or `title_1` is the empty string | none | none |
| `title-duplicate` | warning | medium | *Indexable only*: `title_1` is non-empty and equal (case-sensitive) to the `title_1` of at least one other Indexable Page | none | `title_1`, `pages` (the size of the group) |
| `title-too-long` | opportunity | medium | `title_1_length` > `max_chars`; from v0.2, also `title_1_width_px` > `max_pixels` | `max_chars` 60 (characters); from v0.2, `max_pixels` 561 (pixels) | `length`; from v0.2, `width_px` |
| `title-too-short` | opportunity | low | `title_1_length` is at least 1 and less than `min_chars` | `min_chars` 30 (characters) | `length` |
| `title-multiple` | issue | medium | `title_count` > 1 | none | `count` |
| `title-same-as-h1` | opportunity | low | `title_1` is non-empty and equal (case-sensitive) to `h1_1` | none | none |

In v0.1, `title-too-long` checks characters only. `030-add-page-data` fills `title_1_width_px` from v0.2, and the Rule's `max_pixels` threshold and its `width_px` detail key arrive with it, so v0.1 shows no threshold that cannot fire.

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
- **WHEN** an analysed Page has `title_1_length` 61 and `title_1_width_px` NULL
- **THEN** `title-too-long` fires for it with `detail` `{"length": 61}`

#### Scenario: Title at the limit
- **WHEN** an analysed Page has `title_1_length` 60
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

| id | Issue Type | Priority | Fires for a Page where… | Thresholds | `detail` |
|---|---|---|---|---|---|
| `meta-description-missing` | opportunity | medium | `meta_description_count` is 0 or `meta_description_1` is the empty string | none | none |
| `meta-description-duplicate` | opportunity | low | *Indexable only*: `meta_description_1` is non-empty and equal (case-sensitive) to that of at least one other Indexable Page | none | `meta_description_1`, `pages` |
| `meta-description-too-long` | opportunity | low | `meta_description_1_length` > `max_chars` or `meta_description_1_width_px` > `max_pixels` | `max_chars` 155 (characters), `max_pixels` 985 (pixels) | `length`, `width_px` |
| `meta-description-too-short` | opportunity | low | `meta_description_1_length` is at least 1 and less than `min_chars` | `min_chars` 70 (characters) | `length` |
| `meta-description-multiple` | warning | low | `meta_description_count` > 1 | none | `count` |

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

| id | Issue Type | Priority | Fires for a Page where… | Thresholds | `detail` |
|---|---|---|---|---|---|
| `h1-missing` | warning | medium | `h1_count` is 0 or `h1_1` is the empty string | none | none |
| `h1-duplicate` | opportunity | low | *Indexable only*: `h1_1` is non-empty and equal (case-sensitive) to that of at least one other Indexable Page | none | `h1_1`, `pages` |
| `h1-multiple` | warning | low | `h1_count` > 1 | none | `count` |
| `h1-too-long` | opportunity | low | `h1_1_length` > `max_chars` | `max_chars` 70 (characters) | `length` |
| `h2-missing` | opportunity | low | `h2_count` is 0 or `h2_1` is the empty string | none | none |

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

| id | Issue Type | Priority | Fires for a Page where… | `detail` |
|---|---|---|---|---|
| `canonical-missing` | warning | medium | `canonical_count` is 0, and `meta_robots_noindex` and `x_robots_tag_noindex` are both 0 | none |
| `canonicalised` | warning | medium | `indexability_status` is `canonicalised` | `canonical_url` |
| `canonical-to-non-indexable` | issue | high | `canonical_url` is non-NULL and differs from the Page's URL, and the *target's Indexability* is non-indexable (defined below) | `canonical_url`, `target_reason` (why the target is non-indexable: one of 030's six `indexability_status` values, or `no_response`) |
| `canonical-conflicting` | issue | high | `canonical_count` ≥ 2 and `canonical_url` is NULL | `canonical_link_element_1`, `canonical_link_element_2`, `http_canonical` |
| `canonical-relative` | warning | low | `canonical_relative` is 1 | none |

The *target's Indexability* SHALL come from `030-add-page-data`:

- **When the target is a Page,** it is the Page's stored `indexability` and `indexability_status`.
- **When the target is not a Page,** steps 1–4 of 030's Indexability order are applied to the target's `urls` row: `blocked_by_robots_txt`, `redirected`, `client_error` or `server_error`. A target with `fetch_state` `error` is non-indexable with the reason `no_response`. The reason goes in `detail.target_reason`, not under the column name `indexability_status`, because `no_response` is not one of that column's values. A target with any other outcome, such as a 2xx response that is not HTML, counts as indexable. A target that was never requested has no Indexability, and the Rule does not fire.

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
- **THEN** `canonical-to-non-indexable` fires for `/a` with `detail` `{"canonical_url": "https://example.test/b", "target_reason": "redirected"}`

#### Scenario: Canonical to a noindex Page
- **WHEN** `https://example.test/a` has `canonical_url` `https://example.test/b`, and `/b` is a 200 Page with `indexability_status` `noindex`
- **THEN** `canonical-to-non-indexable` fires for `/a` with `detail` `{"canonical_url": "https://example.test/b", "target_reason": "noindex"}`

#### Scenario: Canonical to a URL without a response
- **WHEN** `https://example.test/a` has `canonical_url` `https://example.test/b`, and `/b` is not a Page and has `fetch_state` `error`
- **THEN** `canonical-to-non-indexable` fires for `/a` with `detail` `{"canonical_url": "https://example.test/b", "target_reason": "no_response"}`

#### Scenario: Canonical to an indexable Page
- **WHEN** `https://example.test/a` has `canonical_url` `https://example.test/b`, and `/b` is a 200 Page with `indexability` `indexable`
- **THEN** `canonical-to-non-indexable` has no Affected URL for `/a`

#### Scenario: Canonical to a non-HTML 200 response
- **WHEN** `https://example.test/a` has `canonical_url` `https://example.test/doc.pdf`, which responded 200 with `Content-Type: application/pdf`
- **THEN** `canonical-to-non-indexable` has no Affected URL for `/a`

#### Scenario: Canonical target never requested
- **WHEN** `https://example.test/a` has `canonical_url` `https://other.test/b`, whose `urls` row has `fetch_state` `skipped` and `blocked_by_robots_txt` NULL
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

| id | Issue Type | Priority | Fires for a Page where… | `detail` |
|---|---|---|---|---|
| `noindex` | warning | high | `meta_robots_noindex` or `x_robots_tag_noindex` is 1 | `sources`: the sources that apply, as a list in the order `meta_robots`, `x_robots_tag` |
| `nofollow` | warning | medium | `meta_robots_nofollow` or `x_robots_tag_nofollow` is 1 | `sources`, in the same way |
| `meta-refresh` | warning | low | `meta_refresh` is non-NULL | `meta_refresh`, `redirect_url` |

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

| id | Issue Type | Priority | Fires for a Page where… | Thresholds | `detail` |
|---|---|---|---|---|---|
| `low-word-count` | opportunity | medium | *Indexable only*: `word_count` < `min_words` | `min_words` 200 (words) | `word_count` |
| `exact-duplicate` | issue | medium | *Indexable only*: `content_hash` is non-NULL and equal to that of at least one other Indexable Page | none | `content_hash`, `pages` |

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

| id | Issue Type | Priority | Fires for a Page where… | Thresholds | `detail` |
|---|---|---|---|---|---|
| `url-uppercase` | opportunity | low | the path or query contains an uppercase letter (Unicode category Lu), ignoring `%XX` escapes | none | none |
| `url-underscores` | opportunity | low | the path contains `_` | none | none |
| `url-parameters` | opportunity | low | the query is non-empty | none | none |
| `url-too-long` | opportunity | low | `url_encoded_address` is longer than `max_chars` characters | `max_chars` 115 (characters) | `length` |
| `url-non-ascii` | opportunity | low | the path or query contains a non-ASCII character | none | none |

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

| id | Issue Type | Priority | Applies to | Fires for… | Thresholds | `detail` |
|---|---|---|---|---|---|---|
| `image-missing-alt-text` | opportunity | low | `internal_pages` | a Page with at least one `image` Link whose `element` is `img`, `attribute` is `src`, and `alt_text` is NULL or the empty string | none | `missing_alt_attribute` (count of NULL), `empty_alt` (count of empty) |
| `image-too-large` | opportunity | medium | `resources` | an image Resource whose `urls.size_bytes` is more than `max_kb` × 1024 | `max_kb` 100 (kilobytes of 1024 bytes) | `size_bytes` |
| `image-broken` | issue | medium | `resources` | an image Resource with a `status_code` from 400 to 599, or with `fetch_state` `error` and a `fetch_error` other than `record_failed` | none | `status_code` or `error` (the `fetch_error`) |

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

#### Scenario: An image that failed to be recorded is not broken
- **WHEN** a Page links the image `https://example.test/odd.png`, which has `fetch_state` `error` and `fetch_error` `record_failed`
- **THEN** `image-broken` has no Affected URL for it

### Requirement: Threshold overrides and disabling Rules
A table `[rules.<id>]` in the Workspace's `spider.toml` SHALL be able to set:

- `enabled = false` to disable that Rule
- any of the Rule's thresholds, by name, to a non-negative integer that replaces the default

The table name is the Rule id itself. These settings mirror no flag, so `010-add-workspace-and-cli-contract`'s flag-mirroring rule for keys does not apply to them. A disabled Rule SHALL NOT be evaluated and SHALL produce no Issue.

#### Scenario: Raised title limit
- **WHEN** `spider.toml` has `[rules.title-too-long]` with `max_chars = 70`, and an analysed Page has `title_1_length` 65
- **THEN** `title-too-long` has no Affected URL for it

#### Scenario: Disabled Rule produces no Issue
- **WHEN** `spider.toml` has `[rules.h2-missing]` with `enabled = false`, and a Crawl of the fixture site with Pages without `<h2>` ends as `completed`
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
When a Crawl starts, it SHALL resolve every Rule's enabled state and effective thresholds and write them to its `rules` table, in the same transaction that creates the `crawl` row. The table follows the conventions of `018-add-schema-conventions` (ADR-0005): it is `STRICT` and `WITHOUT ROWID`, keyed by the Rule id. It holds one row per catalogue Rule, with these columns:

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `id` | TEXT, primary key | no | | The Rule id, as typed in `spider rules show` and `spider.toml` |
| `category` | TEXT | no | the categories of the Rule model | The Rule's category |
| `issue_type` | TEXT | no | `issue`, `warning`, `opportunity` | The Issue Type of the Rule's Issues |
| `priority` | TEXT | no | `high`, `medium`, `low` | The Priority of the Rule's Issues |
| `applies_to` | TEXT | no | `internal_urls`, `internal_pages`, `resources` | The population the Rule is evaluated over |
| `enabled` | INTEGER | no | boolean | 1 when the Rule was evaluated in this Crawl |
| `thresholds` | TEXT | no | json | The effective thresholds, as an object of names to integers; `{}` for a Rule without thresholds |
| `description` | TEXT | no | | What the Rule checks |
| `why_it_matters` | TEXT | no | | Why its Issues matter |
| `how_to_fix` | TEXT | no | | How to fix its Issues |
| `reproduce_sql` | TEXT | no | | The Rule's reproducing query (see "Rules are SQL queries") |

The Crawl SHALL use this configuration throughout, including after `resume`. Editing `spider.toml` later SHALL NOT change the Issues stored for an existing Crawl. v0.1 has no Command that recomputes them; `rules apply` arrives in v0.2.

#### Scenario: Keys of the Rule tables
- **WHEN** `spider schema rules` and `spider schema affected_urls` run
- **THEN** the columns with `primary_key` true are `id` of `rules`, with the type `TEXT`, and `rule_id` and `url_id` of `affected_urls`, whose `references` are `rules.id` and `urls.id`

#### Scenario: Crawl records the thresholds it used
- **WHEN** a Crawl runs with `[rules.low-word-count]` `min_words = 300`
- **THEN** its `rules` row for `low-word-count` has `thresholds` `{"min_words": 300}`

#### Scenario: Later edits do not change a completed Crawl
- **WHEN** a Crawl ended as `completed` with the default `min_words` and `spider.toml` then sets `min_words = 5000`
- **THEN** that Crawl's `issues` and `affected_urls` rows for `low-word-count` are unchanged

#### Scenario: Resumed Crawl keeps the recorded configuration
- **WHEN** a Crawl started with `min_words = 300` stops at its `--max-urls` limit, `spider.toml` is changed to `min_words = 50`, and the Crawl is resumed through the Crawl Service with a higher limit
- **THEN** an Indexable Page with `word_count` 120 written after the resume is an Affected URL of `low-word-count`

### Requirement: Rules are SQL queries
Every Rule SHALL have a reproducing query and SHALL be evaluated only by it. The query is one read-only SQL `SELECT` over the public schema that returns the Rule's Affected URLs in a crawl file, as the columns `url_id` and `detail`.
- It SHALL read only stored columns, and the Rule's effective thresholds from the Crawl's `rules` row, so its text is the same in every Workspace and gives the right answer under overrides.
- A query that leaves out a value the Rule's condition would otherwise match SHALL say why in an SQL comment, as the queries of `internal-no-response` and `image-broken` do for `record_failed`.
- The `rules` table stores it in `reproduce_sql`, and `spider rules list` and `show` print it.

No Rule SHALL be evaluated while a URL is recorded: this change registers no per-response handler, and the Crawl's writer writes no Affected URL while the Crawl runs.

#### Scenario: A Rule's query returns its stored Affected URLs
- **WHEN** a Crawl of the fixture pages under `{site}/rules/` ends as `completed`, and the `reproduce_sql` of each enabled Rule in its `rules` table is run over its file through a read-only connection
- **THEN** for every Rule the rows returned equal the Rule's `affected_urls` rows, with `detail` compared as JSON

#### Scenario: The rules Command prints the reproducing query
- **WHEN** a Crawl has started in a Workspace, and `spider rules show title-missing` runs in that Workspace
- **THEN** its `reproduce_sql` equals the `reproduce_sql` of the Crawl's `rules` row for `title-missing`

### Requirement: Issues of a Crawl without a final pass
This change SHALL provide the Issues reader, through which `050-add-query-and-segments` reads Issues. It returns:
- the Issues, in the shape of the `issues` view
- the Affected URLs of one Rule, and the Issues of one URL, in the shape of `affected_urls`

A Crawl has materialised Issues exactly when its Crawl State is `completed` or `stopped`, because the post-crawl pass runs before either state is written (`020-add-crawl-core`). The reader SHALL then read `affected_urls` and the `issues` view. In every other Crawl State (`running`, `failed` or `interrupted`), it SHALL compute the Issues live: it runs each enabled Rule's query read-only over the stored rows, and ignores `affected_urls`, which may hold an earlier pass's rows.

#### Scenario: Issue visible before the Crawl ends
- **WHEN** the fixture Page `{site}/notitle` has been written and the Crawl is still waiting on `{site}/slow`, which delays its response by 5 s
- **THEN** the Issues reader lists `title-missing` with `affected_count` 1, and its Affected URLs are exactly `{site}/notitle`

#### Scenario: A running Crawl writes no Affected URL
- **WHEN** two fixture Pages with the title `Shoes` have been written and the Crawl is still `running`
- **THEN** `affected_urls` holds no rows, and the Issues reader lists `title-duplicate` with `affected_count` 2

#### Scenario: A Crawl without a final pass is read live
- **WHEN** a Crawl that was `stopped`, then resumed, has ended as `failed`, its `affected_urls` still hold the first pass's rows for `title-missing`, and its stored Pages no longer give `title-missing` any Affected URL
- **THEN** the Issues reader lists no `title-missing` Issue

#### Scenario: Live and materialised Issues agree
- **WHEN** a Crawl of the fixture pages under `{site}/rules/` ends as `completed`, and the Issues reader computes its Issues live as well as reading them
- **THEN** both give the same Issues, and the same Affected URLs for every Rule

### Requirement: Materialising Issues
This change's post-crawl pass SHALL materialise the Issues when a Crawl ends as `completed` or `stopped`, after `030-add-page-data` has computed link counts:
1. For each enabled Rule, one writer unit replaces the Rule's rows in `affected_urls` with the rows its query returns.
2. Then one unit records the Health Score fields.

It SHALL run again when a resumed Crawl ends, and each run SHALL replace the rows of the run before, so an Affected URL is never stored twice. A Crawl that ends as `failed`, or whose process died, gets no pass until it is resumed and ends; until then its Issues are read live.

#### Scenario: Duplicates found by the post-crawl passes
- **WHEN** a Crawl of two fixture Pages with the title `Shoes` ends as `completed`
- **THEN** `affected_urls` holds exactly 2 `title-duplicate` rows

#### Scenario: A second pass does not duplicate rows
- **WHEN** the post-crawl passes run a second time on that Crawl
- **THEN** `affected_urls` still holds exactly 2 `title-duplicate` rows

### Requirement: Issues and Affected URLs are stored
The crawl store SHALL hold the Affected URLs in a table `affected_urls`, under the conventions of `018-add-schema-conventions`: `STRICT` and `WITHOUT ROWID`, with one row per Rule and Affected URL.

| Column | Type | Null | Format / values | Description |
|---|---|---|---|---|
| `rule_id` | TEXT, primary key, references `rules.id` | no | | The Rule that fired |
| `url_id` | INTEGER, primary key, references `urls.id` | no | | The Affected URL |
| `detail` | TEXT | yes | json | The measured values, as an object with the keys listed for the Rule; NULL when the Rule lists none |

Only the post-crawl pass writes `affected_urls`. Its rows are the result of the last pass, which the Issues reader uses only for a `completed` or `stopped` Crawl.

| Index | Columns | Unique | Where | Query it serves |
|---|---|---|---|---|
| `affected_urls_url_id` | `url_id` | no | | The Issues of one URL (`050-add-query-and-segments`' `page <url>`), and the Health Score's count of affected Pages |

The Issues SHALL be a view `issues` over `rules` and `affected_urls`, with one row per Rule that has at least one Affected URL and the columns `rule_id`, `category`, `issue_type`, `priority` and `affected_count`, the number of the Rule's rows in `affected_urls`. No count of Affected URLs SHALL be stored. A Rule that did not fire SHALL have no `issues` row.

#### Scenario: Issue row counts its Affected URLs
- **WHEN** a Crawl of the fixture site ends as `completed` with two Pages that have no `<title>`
- **THEN** the `issues` row for `title-missing` has `category` `titles`, `issue_type` `issue`, `priority` `high` and `affected_count` 2

#### Scenario: Detail is stored as JSON
- **WHEN** a Crawl that stores the fixture Page `{site}/long-title`, whose title is `Buy running shoes, trail boots and sandals online at low cost`, ends as `completed`
- **THEN** its `affected_urls` row for `title-too-long` has `detail` `{"length": 61}`

#### Scenario: Rule that did not fire has no Issue
- **WHEN** a Crawl ends as `completed` and no Page has more than one `<title>`
- **THEN** `issues` holds no row for `title-multiple`

#### Scenario: Issues is a view
- **WHEN** `spider schema issues --fields name,kind` runs
- **THEN** `items` is `[{"name":"issues","kind":"view"}]`

#### Scenario: Indexes of affected_urls
- **WHEN** `spider schema affected_urls --fields indexes` runs
- **THEN** the item's `indexes`, reduced to `name`, `columns`, `unique` and `where`, include `{"name":"affected_urls_url_id","columns":["url_id"],"unique":false,"where":null}`

### Requirement: Health Score
The Health Score of a Crawl SHALL be `floor(100 × (N − A) ÷ N)`:

- N is the number of Internal Pages, meaning rows of `pages` with any status code.
- A is the number of those Pages that are an Affected URL of at least one Rule whose `issue_type` in the Crawl's `rules` table is `issue`.

Warnings, including `http-url`, and Opportunities never lower it.

At the end of the post-crawl passes, the Crawl SHALL record these crawl metadata fields on the `crawl` row of `015-add-crawl-store`. They are derived: only the post-crawl pass writes them, and each description starts with `Derived: ` (ADR-0005).

| Column | Type | Null | Format | Description |
|---|---|---|---|---|
| `health_score` | INTEGER | yes | | The Health Score, from 0 to 100; NULL when N is 0 |
| `health_internal_page_count` | INTEGER | yes | | N |
| `health_affected_page_count` | INTEGER | yes | | A |
| `health_calculated_at` | TEXT | yes | timestamp | When the post-crawl pass calculated the score |

Until the post-crawl passes have run, all four fields SHALL be NULL. A resumed Crawl keeps the values of its last pass until its next pass. The Health Score of any subset of Internal Pages, such as a Segment, SHALL use the same formula restricted to that subset, through one function that `050-add-query-and-segments` and `070-add-html-report` call at query time. While the Issues reader computes Issues live, the function takes the live Affected URLs.

#### Scenario: Pages with Issue-type Issues lower the score
- **WHEN** a Crawl has 10 Internal Pages, 3 of which are Affected URLs of Rules whose Issue Type is `issue`
- **THEN** `health_score` is 70, `health_internal_page_count` is 10 and `health_affected_page_count` is 3

#### Scenario: Score is rounded down
- **WHEN** a Crawl has 3 Internal Pages and 1 of them is an Affected URL of `title-missing`
- **THEN** `health_score` is 66

#### Scenario: Warnings do not lower the score
- **WHEN** a Crawl has 2 Internal Pages and both are Affected URLs of `http-url` (Issue Type `warning`) only
- **THEN** `health_score` is 100

#### Scenario: A Page with several Issues counts once
- **WHEN** a Crawl has 4 Internal Pages and one of them is an Affected URL of both `title-missing` and `exact-duplicate`
- **THEN** `health_score` is 75

#### Scenario: Resource Issues do not change the score
- **WHEN** a Crawl has 1 Internal Page and the only Affected URL is the image Resource `https://example.test/x.png` of `image-broken`
- **THEN** `health_score` is 100

#### Scenario: No Pages means no score
- **WHEN** a Crawl ends as `completed` with 0 Internal Pages
- **THEN** `health_score` is NULL and `health_internal_page_count` is 0

#### Scenario: Score before the passes
- **WHEN** a Crawl is still `running`
- **THEN** `health_score` is NULL

#### Scenario: Health fields are derived
- **WHEN** `spider schema crawl` runs
- **THEN** the columns `health_score`, `health_internal_page_count`, `health_affected_page_count` and `health_calculated_at` have `nullable` `true` and a `description` that starts with `Derived: `

#### Scenario: Health Score of a Segment
- **WHEN** the Health Score function is called with a subset of 4 Internal Pages, 1 of which is an Affected URL of an Issue-type Rule
- **THEN** it returns 75

#### Scenario: End-to-end score on the fixture site
- **WHEN** a Crawl of 4 fixture Pages on the plain-HTTP fixture site ends as `completed`, with one Page without a `<title>` and no other Issue-type problem
- **THEN** `health_score` is 75

### Requirement: List Rules
`spider rules` and `spider rules list` SHALL print the Rules as configured in the current Workspace, without reading any Crawl. The output SHALL follow the output contract of `010-add-workspace-and-cli-contract`: the paging envelope `{total, items, next_cursor}` and the `--fields`, `--limit`, `--cursor` and `--format` options. Items SHALL be in catalogue order: by category, in the order of the Rule model, then in the order the Rules appear in their category's table. Each item SHALL have these fields:

- `id`, `category`, `issue_type`, `priority`, `applies_to` and `enabled`
- `thresholds`: an object that maps each threshold name to `{value, default, unit}`, where the unit is `characters`, `pixels`, `words`, `kilobytes` or `hops`
- `description`, `why_it_matters`, `how_to_fix` and `reproduce_sql`

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
- **THEN** it exits 0 and prints `category` `titles`, `issue_type` `opportunity`, `priority` `medium` and `thresholds` `{"max_chars": {"value": 60, "default": 60, "unit": "characters"}}`

#### Scenario: Unknown Rule id
- **WHEN** `spider rules show nope` runs
- **THEN** the exit code is 4, the error has the code `rule_not_found`, its `message` contains `nope` and its `hint` contains `spider rules list`

#### Scenario: Windows console output
- **WHEN** `spider rules show title-too-long` runs as a subprocess on Windows with console code page 1251
- **THEN** its stdout bytes decode as UTF-8 into a JSON object whose `id` is `title-too-long`

### Requirement: Documented Rule tables
`spider schema` SHALL list the tables `rules` and `affected_urls` with the `kind` `table`, the view `issues` with the `kind` `view`, and the four `health_*` fields of the `crawl` table, following the conventions of `018-add-schema-conventions`:

- `references` for `rule_id` and `url_id`
- the `json` format for `thresholds` and `detail`, and the `boolean` format for `enabled`
- the `timestamp` format for `health_calculated_at`
- `values` for `category`, `issue_type`, `priority` and `applies_to`, in `rules` and, where the view has them, in `issues`
- the index `affected_urls_url_id`

`docs/schema.md` SHALL document them as `018-add-schema-conventions` requires.

#### Scenario: Issue Types are an enumeration
- **WHEN** `spider schema issues` runs
- **THEN** the `values` of the column `issue_type` are `["issue","warning","opportunity"]`

#### Scenario: Categories are an enumeration
- **WHEN** `spider schema rules` runs
- **THEN** the `values` of the column `category` are `["response_codes","security","titles","meta_descriptions","headings","canonicals","directives","content","urls","images"]`
