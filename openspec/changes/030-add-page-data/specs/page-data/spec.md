## Purpose

Defines the Page data a Crawl stores. This covers the flat Page record that matches Screaming Frog's "Internal" tab, the attributes stored for every discovered Link, the cookies Pages set and the stored HTML. Rules, query Commands and Reports all read this one documented set of columns, and each column has an exact definition.

## ADDED Requirements

### Requirement: Page rows
The crawl store SHALL hold one row in the `pages` table for every Page of a Crawl.

- **What counts as a Page.** A Page is a row of the `urls` table of `020-add-crawl-core` that meets all of these conditions:
  - `is_internal` = 1
  - `in_scope` = 1
  - `fetch_state` = `fetched`
  - its `content_type` has the media type `text/html` or `application/xhtml+xml`, compared case-insensitively with parameters ignored
  
  The status code does not matter.
- **Key.** The row SHALL be keyed by `url_id`, which references `urls.id`.
- **When it is written.** The row SHALL be written in the same transaction as the URL's response data.
- **What gets no row.** There SHALL be no `pages` row for any other URL.

In the scenarios, `{site}` is the origin of the local fixture site.

#### Scenario: HTML response becomes a Page
- **WHEN** a Crawl of the fixture site fetches `{site}/about`, which responds 200 with `Content-Type: text/html; charset=utf-8`
- **THEN** `pages` holds exactly 1 row whose `address` is `{site}/about`

#### Scenario: Image response is not a Page
- **WHEN** the Crawl fetches `{site}/logo.png`, which responds 200 with `Content-Type: image/png`
- **THEN** `pages` holds 0 rows whose `address` is `{site}/logo.png`

#### Scenario: URL blocked by robots.txt is not a Page
- **WHEN** the fixture's robots.txt disallows `/private/` and the Crawl, run without `--ignore-robots`, discovers `{site}/private/x`
- **THEN** `pages` holds 0 rows whose `address` is `{site}/private/x`

#### Scenario: URL without a response is not a Page
- **WHEN** `{site}/timeout` never answers within the Crawl's timeout
- **THEN** `pages` holds 0 rows whose `address` is `{site}/timeout`

### Requirement: Analysed and non-analysed Pages
A Page SHALL be *analysed* exactly when `020-add-crawl-core` parsed it (`urls.parsed` = 1), meaning it had a 2xx status and a body that was read in full. For every Page, analysed or not, these columns SHALL be set as their own requirements define:

- the identity and response columns
- the size columns
- `set_cookie_count`
- `crawl_depth` and `folder_depth`
- the inlink columns, once the post-crawl passes have run

For a Page that is not analysed, these columns SHALL be NULL:

- every title and heading column
- every directive column
- every content column
- the outlink columns (`outlinks`, `unique_outlinks`, `external_outlinks`, `unique_external_outlinks`)
- the structured-data columns

For an analysed Page, following the table conventions of `015-add-crawl-store`:

- A count column SHALL be 0 or more.
- A flag column SHALL be 0 or 1.
- A text column SHALL be NULL when its element or header is absent, and the empty string when the element is present but empty.
- A length or width column SHALL be NULL exactly when its text column is NULL.

#### Scenario: Error Page keeps response data
- **WHEN** `{site}/missing` responds 404 with `Content-Type: text/html` and the body `<title>Not found</title>`
- **THEN** its `pages` row has `status_code` 404 and `title_1` NULL

#### Scenario: Absent and empty elements differ
- **WHEN** an analysed Page's HTML is `<head><title></title></head><body></body>`
- **THEN** `title_1` is the empty string, `title_1_length` is 0 and `h1_1` is NULL

### Requirement: Page record columns
The `pages` table SHALL have exactly the columns below, grouped as in the Screaming Frog "Internal" tab. A later requirement defines each column's value. Names, types, formats and allowed values SHALL follow the table conventions of `015-add-crawl-store`: widths end in `_px`, percentages in `_pct`, times in `_ms` and sizes in `_bytes`.

| Group | Columns |
|---|---|
| Identity and response | `url_id`, `address`, `url_encoded_address`, `content_type`, `status_code`, `status`, `indexability`, `indexability_status`, `response_time_ms`, `last_modified`, `redirect_url`, `redirect_type`, `set_cookie_count`, `js_cookie_count`, `http_version`, `crawl_timestamp` |
| Titles and headings | `title_1`, `title_1_length`, `title_1_width_px`, `title_2`, `title_2_length`, `title_2_width_px`, `title_count`, `meta_description_1`, `meta_description_1_length`, `meta_description_1_width_px`, `meta_description_2`, `meta_description_2_length`, `meta_description_2_width_px`, `meta_description_count`, `meta_keywords_1`, `meta_keywords_1_length`, `h1_1`, `h1_1_length`, `h1_2`, `h1_2_length`, `h1_count`, `h2_1`, `h2_1_length`, `h2_2`, `h2_2_length`, `h2_count` |
| Directives | `meta_robots`, `meta_robots_noindex`, `meta_robots_nofollow`, `x_robots_tag`, `x_robots_tag_noindex`, `x_robots_tag_nofollow`, `meta_refresh`, `canonical_url`, `canonical_link_element_1`, `canonical_link_element_2`, `http_canonical`, `canonical_count`, `canonical_relative`, `rel_next_1`, `rel_prev_1`, `http_rel_next_1`, `http_rel_prev_1`, `amphtml_link_element`, `mobile_alternate_link` |
| Size | `size_bytes`, `transferred_bytes`, `content_encoding` |
| Content | `word_count`, `sentence_count`, `average_words_per_sentence`, `syllable_count`, `flesch_reading_ease`, `readability`, `text_ratio_pct`, `declared_language`, `detected_language`, `content_hash`, `closest_similarity_pct`, `near_duplicate_count` |
| Links | `crawl_depth`, `folder_depth`, `link_score`, `inlinks`, `unique_inlinks`, `unique_js_inlinks`, `linking_pages_pct`, `outlinks`, `unique_outlinks`, `unique_js_outlinks`, `external_outlinks`, `unique_external_outlinks` |
| Structured data | `jsonld_items`, `microdata_items`, `jsonld_parse_errors`, `structured_data_types`, `structured_data_errors`, `structured_data_warnings` |

#### Scenario: Schema lists exactly the Page record columns
- **WHEN** `spider schema pages` runs
- **THEN** the set of the item's column names equals the 94 names of the table above

### Requirement: Address columns
Each Page row SHALL store two forms of the Page's URL:

- **`url_encoded_address`** is the URL as the Crawl requested it, equal to `urls.url`. The host is in IDNA (punycode) form, and every non-ASCII character is percent-encoded as UTF-8.
- **`address`** is `url_encoded_address` with two changes:
  - the host is converted to Unicode
  - every percent-encoded byte sequence that decodes as UTF-8 to a non-ASCII character is replaced by that character
  
  Percent-encoded ASCII characters SHALL stay encoded.

#### Scenario: Non-ASCII path is decoded for display
- **WHEN** the Page's `url_encoded_address` is `https://example.test/%C3%BCber%20uns`
- **THEN** its `address` is `https://example.test/über%20uns`

#### Scenario: Punycode host is shown in Unicode
- **WHEN** the Page's `url_encoded_address` is `https://xn--bcher-kva.test/`
- **THEN** its `address` is `https://bücher.test/`

### Requirement: Response columns
Each Page row SHALL store these columns. All of them come from the Page's own response, never from a redirect target. Where a column repeats a value of the `urls` table (`020-add-crawl-core`, including the columns that `022-add-fetch-policy` adds) or of the `origins` table, it SHALL be equal to that value.

| Column | Value |
|---|---|
| `content_type` | `urls.content_type` |
| `status_code` | `urls.status_code` |
| `status` | the reason phrase the server sent; when it sent none, the standard reason phrase for the status code from RFC 9110; NULL when neither exists |
| `response_time_ms` | `urls.response_time_ms` |
| `last_modified` | the `Last-Modified` header parsed as an HTTP-date, as a `timestamp` (`YYYY-MM-DDTHH:MM:SS.sssZ`); NULL when absent or invalid |
| `http_version` | `origins.http_version` for the Page's origin (`http_1_1` or `http_2`) |
| `crawl_timestamp` | `urls.fetched_at` |

#### Scenario: Last-Modified is normalised to a timestamp
- **WHEN** the response has `Last-Modified: Wed, 21 Oct 2015 07:28:00 GMT`
- **THEN** `last_modified` is `2015-10-21T07:28:00.000Z`

#### Scenario: Invalid Last-Modified is NULL
- **WHEN** the response has `Last-Modified: yesterday`
- **THEN** `last_modified` is NULL

#### Scenario: Reason phrase falls back to the standard phrase
- **WHEN** the response status line is `HTTP/1.1 404` with no reason phrase
- **THEN** `status` is `Not Found`

#### Scenario: Crawl timestamp repeats fetched_at
- **WHEN** the injectable clock makes the Crawl record `fetched_at` `2026-01-02T03:04:05.000Z` for `{site}/about`
- **THEN** that Page's `crawl_timestamp` is `2026-01-02T03:04:05.000Z`

#### Scenario: HTTP version is copied from the origin
- **WHEN** a Crawl of the plain-HTTP fixture site completes
- **THEN** every Page has `http_version` `http_1_1`

#### Scenario: Repeated values equal the urls row
- **WHEN** a Crawl stores the Page `{site}/about`
- **THEN** its `content_type`, `status_code`, `response_time_ms`, `size_bytes`, `transferred_bytes`, `content_encoding`, `crawl_depth` and `crawl_timestamp` equal the `content_type`, `status_code`, `response_time_ms`, `size_bytes`, `transferred_bytes`, `content_encoding`, `crawl_depth` and `fetched_at` of its `urls` row

### Requirement: Size columns
Each Page row SHALL store these size columns, repeating the values that `022-add-fetch-policy` records on the `urls` row:

- **`size_bytes`:** the body size after content decoding.
- **`transferred_bytes`:** the body size as transferred, before content decoding.
- **`content_encoding`:** the `Content-Encoding` header as received, or NULL when absent.

#### Scenario: Compressed Page sizes
- **WHEN** `{site}/gzip` sends a 46-byte gzip body that decodes to 10,000 bytes, with `Content-Encoding: gzip`
- **THEN** its row has `size_bytes` 10000, `transferred_bytes` 46 and `content_encoding` `gzip`

#### Scenario: Uncompressed Page sizes
- **WHEN** `{site}/plain` sends a 1,234-byte body with no `Content-Encoding`
- **THEN** its row has `size_bytes` 1234, `transferred_bytes` 1234 and `content_encoding` NULL

### Requirement: Redirect columns
A Page SHALL have `redirect_url` and `redirect_type` set in these cases:

- **HTTP redirect.** A Page with a 3xx status code has `redirect_type` `http_redirect`. Its `redirect_url` is the URL that `urls.redirect_url_id` (`022-add-fetch-policy`) points to, or NULL when that is null.
- **Meta refresh.** An analysed Page whose meta refresh names a URL different from its own `address` has `redirect_type` `meta_refresh` and `redirect_url` set to that URL (see "Meta refresh").

In every other case both columns SHALL be NULL.

#### Scenario: HTTP redirect with an HTML body
- **WHEN** `{site}/old` responds 301 with `Content-Type: text/html` and `Location: /new`
- **THEN** its row has `redirect_type` `http_redirect` and `redirect_url` `{site}/new`

### Requirement: Cookies from Set-Cookie headers
The crawl store SHALL hold one row in the `cookies` table for each `Set-Cookie` header on a Page's response, whatever the Page's status code. Its columns are:

- `url_id` and `ordinal`: the header's position among the response's `Set-Cookie` headers, from 1
- `name`: the text before the first `=`, trimmed
- `domain`: the `Domain` attribute, lowercased with any leading dot removed, or NULL
- `path`: the `Path` attribute, or NULL
- `expires`: the `Expires` attribute as a `timestamp`, or NULL when absent or invalid
- `max_age`: the `Max-Age` attribute as an integer number of seconds, or NULL
- `secure`, `http_only` and `partitioned`: flags, 0 or 1
- `same_site`: `strict`, `lax` or `none`, or NULL when absent

Attribute names SHALL be matched case-insensitively. The Page's `set_cookie_count` SHALL equal its number of `cookies` rows. `js_cookie_count` SHALL be NULL, because cookies set by scripts are measured from v1.1.

The cookie value SHALL NOT be stored in any table this change adds. Together with `022-add-fetch-policy`, which stores `Set-Cookie` values as `***` in `response_headers`, no cookie value is stored anywhere in a crawl file.

#### Scenario: Cookie attributes are stored
- **WHEN** a Page's response has `Set-Cookie: sid=abc123; Path=/; Secure; HttpOnly; SameSite=Lax`
- **THEN** its `cookies` row has `name` `sid`, `path` `/`, `secure` 1, `http_only` 1, `same_site` `lax` and `domain` NULL

#### Scenario: Cookie count matches the headers
- **WHEN** a Page's response has two `Set-Cookie` headers, `a=1; Max-Age=3600` and `b=2; Domain=.Example.test`
- **THEN** the Page has `set_cookie_count` 2, the first cookie has `max_age` 3600 and the second has `domain` `example.test`

#### Scenario: Cookies of a redirect are stored
- **WHEN** `{site}/login` responds 302 with `Content-Type: text/html`, `Location: /` and `Set-Cookie: s=1; Path=/`
- **THEN** its Page row has `set_cookie_count` 1

#### Scenario: Cookie values are not stored in Page data
- **WHEN** a Crawl stores the cookie `sid=abc123` from `{site}/cookie`, whose body does not contain `abc123`
- **THEN** 0 rows of `cookies`, `pages`, `links` and `page_sources` (decompressed) contain the text `abc123`

### Requirement: Decoding, text and URL resolution
Analysed Pages SHALL be decoded to text using the first source that applies, in this order:

1. a byte order mark
2. the `charset` parameter of `Content-Type`
3. a `<meta charset>` or `<meta http-equiv="Content-Type">` declaration in the first 1024 bytes
4. UTF-8, or windows-1252 when the body is not valid UTF-8

**Element text.** The *text* of an element SHALL be built as follows:

- Take its descendant text nodes in document order, with character references decoded.
- Leave out the contents of `script`, `style`, `noscript`, `template`, `iframe`, `svg` and `math` elements.
- Insert a *block break* at every `br` element and at the start and end of every block-level element. The block-level elements are `address`, `article`, `aside`, `blockquote`, `caption`, `dd`, `details`, `dialog`, `div`, `dl`, `dt`, `fieldset`, `figcaption`, `figure`, `footer`, `form`, `h1`–`h6`, `header`, `hgroup`, `hr`, `li`, `main`, `nav`, `ol`, `p`, `pre`, `section`, `summary`, `table`, `tbody`, `td`, `tfoot`, `th`, `thead`, `tr` and `ul`.

**Text normalisation.** Every text column extracted from HTML SHALL be whitespace-normalised:

- Block breaks become spaces.
- Leading and trailing ASCII whitespace is removed.
- Each run of ASCII whitespace is replaced by one space.

**Lengths** SHALL be counted in Unicode code points of the normalised text.

**URL resolution.** URLs SHALL be resolved and normalised as the Link discovery of `020-add-crawl-core` does.

#### Scenario: Charset declared in a meta element
- **WHEN** an analysed Page is served as `Content-Type: text/html` (no charset) and its body is the windows-1251 bytes of `<meta charset="windows-1251"><title>Привет</title>`
- **THEN** its `title_1` is `Привет`

#### Scenario: Whitespace is collapsed before measuring
- **WHEN** an analysed Page's `<title>` contains two spaces, `Hello`, a line feed, three spaces, `World` and a space
- **THEN** `title_1` is `Hello World` and `title_1_length` is 11

#### Scenario: Line break separates heading words
- **WHEN** an analysed Page's HTML contains `<h1>Hello<br>World</h1>`
- **THEN** `h1_1` is `Hello World`

#### Scenario: Base element changes resolution
- **WHEN** the analysed Page `https://example.test/a/b` contains `<base href="https://example.test/docs/">` and `<link rel="canonical" href="page">` in its head
- **THEN** its `canonical_link_element_1` is `https://example.test/docs/page`

### Requirement: Titles
Titles SHALL be extracted from HTML-namespace `<title>` elements anywhere in the document. `<title>` elements inside SVG or MathML content SHALL be ignored.

- `title_count` is the number of such elements.
- `title_1` and `title_2` are the texts of the first and second, in document order.
- `title_1_length` and `title_2_length` are their lengths.

#### Scenario: Title in SVG is ignored
- **WHEN** an analysed Page's HTML is `<head><title>Main</title></head><body><svg><title>Icon</title></svg></body>`
- **THEN** `title_count` is 1 and `title_2` is NULL

#### Scenario: Second title element
- **WHEN** an analysed Page's HTML is `<head><title>One</title><title>Two</title></head>`
- **THEN** `title_count` is 2, `title_2` is `Two`, `title_2_length` is 3 and `title_2_width_px` is 38

#### Scenario: Missing title
- **WHEN** an analysed Page's HTML has no `<title>` element
- **THEN** `title_count` is 0 and `title_1` and `title_1_length` are NULL

### Requirement: Meta description and meta keywords
Meta descriptions SHALL be extracted from `<meta>` elements anywhere in the document whose trimmed `name` equals `description`, compared case-insensitively.

- `meta_description_count` is the number of such elements.
- `meta_description_1` and `meta_description_2` are the normalised `content` values of the first two. An element without `content` gives the empty string.
- `meta_description_1_length` and `meta_description_2_length` are their lengths.

`meta_keywords_1` and `meta_keywords_1_length` SHALL be defined the same way for the first `<meta name="keywords">` element.

#### Scenario: Meta description is normalised
- **WHEN** an analysed Page's HTML contains `<meta name="Description" content="  Buy   shoes ">`
- **THEN** `meta_description_1` is `Buy shoes` and `meta_description_1_length` is 9

#### Scenario: Multiple meta descriptions
- **WHEN** an analysed Page's HTML contains `<meta name="description" content="A">` followed by `<meta name="description" content="B">`
- **THEN** `meta_description_count` is 2, `meta_description_2` is `B`, `meta_description_2_length` is 1 and `meta_description_2_width_px` is 9

#### Scenario: Meta keywords
- **WHEN** an analysed Page's HTML contains `<meta name="keywords" content="shoes, boots">`
- **THEN** `meta_keywords_1` is `shoes, boots` and `meta_keywords_1_length` is 12

### Requirement: Headings
Headings SHALL be extracted from `<h1>` and `<h2>` elements anywhere in the document.

- `h1_count` and `h2_count` are the numbers of such elements.
- `h1_1`, `h1_2`, `h2_1` and `h2_2` are the texts of the first and second of each, in document order.
- Each has a matching `_length` column.

#### Scenario: Heading text includes nested elements
- **WHEN** an analysed Page's HTML is `<body><h1>Main <span>Title</span></h1><h1>Second</h1><h2>Sub</h2></body>`
- **THEN** these values are stored:
  - `h1_1` is `Main Title` and `h1_1_length` is 10
  - `h1_2` is `Second` and `h1_2_length` is 6
  - `h1_count` is 2
  - `h2_1` is `Sub` and `h2_1_length` is 3
  - `h2_count` is 1
  - `h2_2` and `h2_2_length` are NULL

### Requirement: SERP pixel widths
Pixel widths SHALL be computed for titles and meta descriptions:

- `title_1_width_px` and `title_2_width_px` are the widths of the texts in Arial regular at 20 px.
- `meta_description_1_width_px` and `meta_description_2_width_px` are the widths in Arial regular at 14 px.

Each width is the sum, over the text's characters, of advance × size ÷ 2048, rounded to the nearest whole pixel with halves rounded up. Advances come from a bundled table of Arial advance widths in units of 1/2048 em, and kerning is not applied. A character missing from the table SHALL count as:

- 2048 units for East Asian Wide and Fullwidth characters
- 0 for combining marks (Mn, Me) and format characters (Cf)
- the advance of the digit `0` (1139 units) for any other character

The result SHALL NOT depend on the fonts installed on the machine.

#### Scenario: Title pixel width
- **WHEN** an analysed Page's title is `Hello`
- **THEN** `title_1_width_px` is 46

#### Scenario: Meta description pixel width
- **WHEN** an analysed Page's meta description is `Buy shoes`
- **THEN** `meta_description_1_width_px` is 65

#### Scenario: Wide characters use one em
- **WHEN** an analysed Page's title is `日本`
- **THEN** `title_1_width_px` is 40

#### Scenario: Realistic long title
- **WHEN** an analysed Page's title is `Buy running shoes, trail boots and sandals online at low cost`
- **THEN** `title_1_length` is 61 and `title_1_width_px` is 536

### Requirement: Meta robots and X-Robots-Tag
An analysed Page SHALL store the robots directives found in its HTML and in its headers:

- **`meta_robots`**: the normalised `content` values of all `<meta>` elements whose `name` is `robots` (compared case-insensitively), joined with `, ` in document order. It is NULL when there are none.
- **`x_robots_tag`**: the normalised values of all `X-Robots-Tag` response headers, joined with `, ` in the order received. It is NULL when there are none.
- **`meta_robots_noindex`, `meta_robots_nofollow`, `x_robots_tag_noindex` and `x_robots_tag_nofollow`**: the noindex and nofollow verdicts, as 0 or 1, that the robots directives parser of `020-add-crawl-core` gives for each source. That parser defines which tokens count (such as `none`) and which header values apply only to a named crawler.

#### Scenario: Meta robots keeps case but reads directives
- **WHEN** an analysed Page's HTML contains `<meta name="ROBOTS" content="NOINDEX, follow">`
- **THEN** `meta_robots` is `NOINDEX, follow`, `meta_robots_noindex` is 1 and `meta_robots_nofollow` is 0

#### Scenario: X-Robots-Tag is stored with the parser's verdict
- **WHEN** an analysed Page's response has `X-Robots-Tag: noindex` and its HTML has no robots `<meta>`
- **THEN** `x_robots_tag` is `noindex`, `x_robots_tag_noindex` is 1, `x_robots_tag_nofollow` is 0 and `meta_robots` is NULL

### Requirement: Meta refresh
`meta_refresh` SHALL be the normalised `content` of the first `<meta>` element whose `http-equiv` is `refresh` (compared case-insensitively). It is NULL when there is none. The refresh target is the target of the `meta_refresh` Link that `020-add-crawl-core` discovers.

#### Scenario: Meta refresh with a quoted target
- **WHEN** the analysed Page `https://example.test/old` contains `<meta http-equiv="Refresh" content="5; URL='/new'">`
- **THEN** `meta_refresh` is `5; URL='/new'`, `redirect_type` is `meta_refresh` and `redirect_url` is `https://example.test/new`

#### Scenario: Meta refresh without a target is not a redirect
- **WHEN** an analysed Page contains `<meta http-equiv="refresh" content="30">`
- **THEN** `meta_refresh` is `30` and `redirect_type` is NULL

### Requirement: Canonicals
The canonical columns of an analysed Page SHALL be computed from its *canonical declarations*. A canonical declaration is either of these:

- a `<link>` element that the HTML parser places inside `<head>`, whose `rel` tokens include `canonical` (compared case-insensitively), and which has an `href`
- a `Link` response header entry with `rel="canonical"`

The canonical columns SHALL be:

- `canonical_link_element_1` and `canonical_link_element_2`: the resolved URLs of the first two HTML declarations, in document order.
- `http_canonical`: the resolved URL of the first header declaration.
- `canonical_count`: the number of declarations.
- `canonical_url`: the URL that all declarations resolve to, when they resolve to exactly one distinct URL. It is NULL when there are no declarations or when they disagree.
- `canonical_relative`: 1 when the `href` of any HTML declaration does not start with `http:` or `https:`, compared case-insensitively.

A `canonical` Link that `020-add-crawl-core` discovers outside `<head>` is still stored as a Link, but SHALL NOT be a canonical declaration.

#### Scenario: Relative canonical to another URL
- **WHEN** the analysed Page `https://example.test/a` has `<link rel="canonical" href="/b">` in its head
- **THEN** `canonical_url` is `https://example.test/b`, `canonical_count` is 1 and `canonical_relative` is 1

#### Scenario: HTML and header canonicals disagree
- **WHEN** the analysed Page `https://example.test/a` has `<link rel="canonical" href="https://example.test/b">` and the header `Link: <https://example.test/c>; rel="canonical"`
- **THEN** `canonical_count` is 2, `canonical_link_element_2` is NULL, `http_canonical` is `https://example.test/c` and `canonical_url` is NULL

#### Scenario: Canonical after an image in head is ignored
- **WHEN** an analysed Page's HTML is `<head><title>T</title><img src="x.png"><link rel="canonical" href="/b"></head>`
- **THEN** `canonical_count` is 0

### Requirement: Pagination, AMP and mobile alternate links
These columns SHALL each hold the target URL of a Link that `020-add-crawl-core` discovers in the Page's response, or NULL when there is none. Which `rel` values count as next or previous (for example both `prev` and `previous`) is decided by that change's Link type table.

- `rel_next_1` and `rel_prev_1`: the first HTML `pagination` Link for the next and for the previous page
- `http_rel_next_1` and `http_rel_prev_1`: the same for `Link` header entries
- `amphtml_link_element`: the first `amphtml` Link
- `mobile_alternate_link`: the first `mobile_alternate` Link

#### Scenario: Pagination from HTML and header
- **WHEN** the analysed Page `https://example.test/p2` has `<link rel="prev" href="/p1">` and the header `Link: </p3>; rel="next"`
- **THEN** `rel_prev_1` is `https://example.test/p1`, `http_rel_next_1` is `https://example.test/p3`, and `rel_next_1` and `http_rel_prev_1` are NULL

#### Scenario: Mobile alternate and AMP
- **WHEN** the analysed Page `https://example.test/a` has `<link rel="alternate" media="only screen and (max-width: 640px)" href="https://m.example.test/a">` and `<link rel="amphtml" href="/a.amp">`
- **THEN** `mobile_alternate_link` is `https://m.example.test/a` and `amphtml_link_element` is `https://example.test/a.amp`

### Requirement: Indexability
Every Page SHALL have `indexability` set to `indexable` or `non_indexable`. When it is `non_indexable`, `indexability_status` SHALL be the first reason that applies, checked in this order:

1. `blocked_by_robots_txt`: `urls.blocked_by_robots_txt` is 1. This applies to a Page fetched under `--ignore-robots`.
2. `redirected`: the status code is 3xx.
3. `client_error`: the status code is 4xx.
4. `server_error`: the status code is 5xx.
5. `noindex`: `meta_robots_noindex` or `x_robots_tag_noindex` is 1.
6. `redirected`: `redirect_type` is `meta_refresh`.
7. `canonicalised`: `canonical_url` is not NULL and differs from the Page's URL after normalisation.

When no reason applies, `indexability` SHALL be `indexable` and `indexability_status` NULL. Indexability SHALL NOT be stored for URLs that are not Pages.

#### Scenario: Plain 200 Page is indexable
- **WHEN** a Page responds 200, is allowed by robots.txt, has no noindex directive, no meta refresh and no canonical declaration
- **THEN** `indexability` is `indexable` and `indexability_status` is NULL

#### Scenario: Noindex wins over a canonical
- **WHEN** a 200 Page has `meta_robots_noindex` 1 and a `canonical_url` of another URL
- **THEN** `indexability_status` is `noindex`

#### Scenario: Self-referencing canonical stays indexable
- **WHEN** the 200 Page `https://example.test/a` has `canonical_url` `https://example.test/a`
- **THEN** `indexability` is `indexable`

#### Scenario: Canonical to another URL
- **WHEN** the 200 Page `https://example.test/a` has `canonical_url` `https://example.test/b`
- **THEN** `indexability_status` is `canonicalised`

#### Scenario: Server error
- **WHEN** a Page responds 503 with an HTML body
- **THEN** `indexability_status` is `server_error`

#### Scenario: Robots.txt beats the status code
- **WHEN** a Page with `urls.blocked_by_robots_txt` 1 was fetched under `--ignore-robots` and responded 404
- **THEN** `indexability_status` is `blocked_by_robots_txt`

#### Scenario: Meta refresh redirect is not indexable
- **WHEN** a 200 Page has `redirect_type` `meta_refresh`
- **THEN** `indexability_status` is `redirected`

### Requirement: Content Area
The Content Area of an analysed Page SHALL be found from the `[content_area]` settings in `spider.toml`, which take two lists of CSS selectors:

- `include` (default: empty)
- `exclude` (default: `["nav", "header", "footer"]`)

A value set in `spider.toml` replaces the default list.

- **Roots.** When `include` is empty, the only root is `<body>`. Otherwise the roots are the elements that match an `include` selector and have no ancestor that also matches one.
- **Membership.** A node is in the Content Area when it is a root or inside a root, and neither the node nor any of its ancestors matches an `exclude` selector.

The *Content Area text* is the text of the nodes in the Content Area, in document order, with block breaks kept.

An invalid selector SHALL make `spider crawl` fail before any URL is requested, with the error code `settings_invalid` of `010-add-workspace-and-cli-contract`. The effective settings SHALL be recorded in the Crawl's recorded config under `content_area`.

Fixture A below is referred to by later scenarios:

```html
<html lang="en"><head><title>Hello</title></head><body>
<header><p>Site header text</p></header>
<nav><a href="/">Home</a></nav>
<main><h1>Welcome</h1><p>Reading is fun. Water is wet.</p></main>
<footer><p>Footer text</p></footer>
</body></html>
```

#### Scenario: Default Content Area leaves out navigation
- **WHEN** fixture A is analysed with the default settings
- **THEN** `word_count` is 7

#### Scenario: Empty exclude list counts everything
- **WHEN** fixture A is analysed with `exclude = []`
- **THEN** `word_count` is 13

#### Scenario: Include selector limits the Content Area
- **WHEN** fixture A is analysed with `include = ["p"]` and the default `exclude`
- **THEN** `word_count` is 6

#### Scenario: Invalid selector stops the Crawl
- **WHEN** `spider crawl {site}/` runs with `spider.toml` containing `[content_area]` and `exclude = ["nav["]`
- **THEN** the exit code is 3, the error has the code `settings_invalid` and `details.errors[0].key` `"content_area.exclude"`, and the fixture site receives 0 requests

### Requirement: Word, sentence and syllable counts
These counts SHALL be taken over the Content Area text.

**Words.** A word is a maximal sequence of letters, marks and digits (Unicode categories L, M and N). A single apostrophe (`'` or `’`), hyphen (`-` or U+2010), full stop or comma between two such characters does not end the sequence. There is one exception: each Han, Hiragana or Katakana character is a word on its own. `word_count` is the number of words.

**Sentences.** A sentence is a part of a text block that contains at least one word and ends in one of two ways:

- at the end of the block
- after a run of the terminators `.`, `!`, `?`, `…`, `。`, `！` or `？`, when the run is followed by whitespace or the end of the block, or when it contains `。`, `！` or `？`

`sentence_count` is the number of sentences.

**Average.** `average_words_per_sentence` is `word_count` ÷ `sentence_count`, rounded to 2 decimals, or NULL when `sentence_count` is 0.

**Syllables.** `syllable_count` is the sum of the words' syllables, counted with the syllable rules of the Page's readability language (see "Flesch Reading Ease and Readability"). Every word counts at least 1 syllable. It is NULL when the Page has no readability language.

#### Scenario: Words with apostrophes, hyphens and dots
- **WHEN** the Content Area text is `Don't stop — it's state-of-the-art, v2.0!`
- **THEN** `word_count` is 5

#### Scenario: Each ideograph and kana is a word
- **WHEN** the Content Area text is `日本語のテキスト`
- **THEN** `word_count` is 8

#### Scenario: Blocks end sentences
- **WHEN** the Content Area is `<h1>Welcome</h1><p>This is it. Really! Yes</p>`
- **THEN** `sentence_count` is 4

#### Scenario: Counts for fixture A
- **WHEN** fixture A is analysed with the default settings
- **THEN** `sentence_count` is 3, `average_words_per_sentence` is 2.33 and `syllable_count` is 10

#### Scenario: Syllables per language
- **WHEN** the Content Area text and declared language are, in turn: `make table beautiful rhythm queue` (en), `Wasser Haus Bäume` (de) and `молоко очень вкусное` (ru)
- **THEN** `syllable_count` is 8, 5 and 8 respectively

### Requirement: Flesch Reading Ease and Readability
The *readability language* of a Page SHALL be the primary subtag of its `declared_language`, lowercased. The primary subtag is the text before the first `-` or `_`. When that language has a formula below, `flesch_reading_ease` SHALL be computed with it and rounded to 1 decimal. ASL is `word_count` ÷ `sentence_count` and ASW is `syllable_count` ÷ `word_count`.

| Language | Formula | Source |
|---|---|---|
| `en` | 206.835 − 1.015 × ASL − 84.6 × ASW | Flesch (1948) |
| `de` | 180 − ASL − 58.5 × ASW | Amstad (1978) |
| `es` | 206.835 − 62.3 × ASW − ASL | Szigriszt-Pazos (1993) |
| `fr` | 207 − 1.015 × ASL − 73.6 × ASW | Kandel & Moles (1958) |
| `nl` | 206.835 − 0.93 × ASL − 77 × ASW | Douma (1960) |
| `pt` | 248.835 − 1.015 × ASL − 84.6 × ASW | Martins et al. (1996) |
| `ru` | 206.835 − 1.3 × ASL − 60.1 × ASW | Oborneva (2006) |

`readability` SHALL be the band of the stored score:

| Score | Band |
|---|---|
| 90 or more | `very_easy` |
| 80 to under 90 | `easy` |
| 70 to under 80 | `fairly_easy` |
| 60 to under 70 | `normal` |
| 50 to under 60 | `fairly_difficult` |
| 30 to under 50 | `difficult` |
| under 30 | `very_difficult` |

Both columns SHALL be NULL in any of these cases:

- the Page has no `declared_language`
- the Page's readability language has no formula
- `word_count` is 0

The detected language SHALL NOT be used.

#### Scenario: English score for fixture A
- **WHEN** fixture A is analysed with the default settings
- **THEN** `flesch_reading_ease` is 83.6 and `readability` is `easy`

#### Scenario: Scores in German, Dutch and Russian
- **WHEN** a Page's Content Area text and `<html lang>` are, in turn: `Der Hund ist gut.` (de), `Het huis is groot.` (nl) and `Молоко очень вкусное.` (ru)
- **THEN** `flesch_reading_ease` is 117.5, 126.1 and 42.7 respectively

#### Scenario: Scores in Spanish, French and Portuguese
- **WHEN** a Page's Content Area text and `<html lang>` are, in turn: `La casa es blanca.` (es), `Le chat dort.` (fr) and `A casa é grande.` (pt)
- **THEN** `flesch_reading_ease` is 109.4, 130.4 and 117.9 respectively

#### Scenario: Band of a difficult text
- **WHEN** a Page with `<html lang="ru">` has the Content Area text `Молоко очень вкусное.`
- **THEN** `readability` is `difficult`

#### Scenario: Region subtag and case are ignored
- **WHEN** fixture A is changed to `<html lang="EN-gb">`
- **THEN** `flesch_reading_ease` is 83.6

#### Scenario: Language without a formula
- **WHEN** fixture A is changed to `<html lang="ja">`
- **THEN** `flesch_reading_ease` and `readability` are NULL

#### Scenario: Detected language is not used for readability
- **WHEN** fixture A without its `lang` attribute is crawled with `--detect-language`
- **THEN** `flesch_reading_ease` is NULL

### Requirement: Text Ratio
`text_ratio_pct` SHALL be 100 × (the length of the normalised text of `<body>`) ÷ (the length in characters of the decoded HTML document), rounded to 2 decimals. The text of `<body>` is taken without Content Area exclusions.

#### Scenario: Text ratio of a small document
- **WHEN** an analysed Page's decoded HTML is exactly `<html><body><p>Hello world</p></body></html>`
- **THEN** `text_ratio_pct` is 25.00

### Requirement: Declared and detected language
The two languages SHALL be stored separately:

- **`declared_language`** is the trimmed `lang` attribute of the root `<html>` element. It is the empty string when the attribute is present but empty, and NULL when it is absent.
- **`detected_language`** SHALL be NULL unless the Crawl was started with `--detect-language`, or with `detect_language = true` under `[crawl]` in `spider.toml`. In that case it is the ISO 639-1 code of the language detected offline from the Content Area text. It is NULL when that text has no words.

#### Scenario: Declared language is trimmed, not normalised
- **WHEN** an analysed Page's HTML starts with `<html lang=" en-GB ">`
- **THEN** `declared_language` is `en-GB`

#### Scenario: Language detection is off by default
- **WHEN** a Crawl runs without `--detect-language` and without `detect_language = true` in `spider.toml`
- **THEN** every Page of the Crawl has `detected_language` NULL

#### Scenario: Detected Russian text
- **WHEN** a Crawl with `--detect-language` analyses a Page whose Content Area text is `Быстрая коричневая лиса прыгает через ленивую собаку, пока фермер смотрит со старого деревянного крыльца и медленно пьёт утренний кофе.`
- **THEN** that Page's `detected_language` is `ru`

### Requirement: Exact Duplicate hash
`content_hash` SHALL be the lowercase hexadecimal SHA-256 of the UTF-8 encoding of the Content Area text after these steps:

1. whitespace normalisation, with block breaks turned into spaces
2. Unicode NFC normalisation

Letter case SHALL be kept. `content_hash` SHALL be NULL when `word_count` is 0. Two Pages are Exact Duplicates exactly when both have the same non-NULL `content_hash`.

#### Scenario: Hash of a simple Content Area
- **WHEN** an analysed Page's Content Area is `<p>Hello   world</p>`
- **THEN** `content_hash` is `64ec88ca00b268e5ba1a35678a1b5316d212f4f366b2477232534a8aeca37f3c`

#### Scenario: Different markup, same text
- **WHEN** an analysed Page's Content Area is `<div><p>Hello</p><p>world</p></div>`
- **THEN** `content_hash` is `64ec88ca00b268e5ba1a35678a1b5316d212f4f366b2477232534a8aeca37f3c`

#### Scenario: Composed and decomposed accents hash the same
- **WHEN** one Page's Content Area is `<p>Caf&#233;</p>` and another's is `<p>Cafe&#769;</p>`
- **THEN** both have `content_hash` `73473dcc12b763085904a5279d048c4d5b3b008c46f1f32443b99de04aa83a14`

#### Scenario: Empty Content Area has no hash
- **WHEN** an analysed Page's body is `<body><nav><a href="/">Home</a></nav></body>`, with the default settings
- **THEN** `content_hash` is NULL

### Requirement: Structured-data counts and types
For an analysed Page, the structured-data columns SHALL be:

- **`jsonld_items`**: the number of JSON-LD items. Each `<script>` whose `type` is `application/ld+json` (compared case-insensitively) is parsed as JSON:
  - A top-level array contributes each of its object elements.
  - An object with an `@graph` array contributes the objects in `@graph`.
  - Any other object is one item.
- **`jsonld_parse_errors`**: the number of such scripts that are not valid JSON.
- **`microdata_items`**: the number of elements that have `itemscope` and no `itemprop`.
- **`structured_data_types`**: a JSON array of the distinct types of all counted items, sorted by code point. Types come from `@type` or `itemtype`, which can hold several values. A leading `http://schema.org/` or `https://schema.org/` is removed from each type. The array is `[]` when there are none.

`structured_data_errors` and `structured_data_warnings` SHALL be NULL, because validation is measured from v0.3.

#### Scenario: JSON-LD graph, a broken block and nested Microdata
- **WHEN** an analysed Page contains the script `{"@context":"https://schema.org","@graph":[{"@type":"Organization"},{"@type":"WebSite"}]}`, the script `{bad json`, and `<div itemscope itemtype="https://schema.org/Product"><span itemprop="offers" itemscope itemtype="https://schema.org/Offer"></span></div>`
- **THEN** `jsonld_items` is 2, `jsonld_parse_errors` is 1, `microdata_items` is 1 and `structured_data_types` is `["Organization","Product","WebSite"]`

#### Scenario: Page without structured data
- **WHEN** an analysed Page contains no JSON-LD script and no `itemscope` element
- **THEN** `jsonld_items` is 0, `microdata_items` is 0 and `structured_data_types` is `[]`

### Requirement: Link attributes
The crawl store SHALL hold one row in the `links` table for each Link that the Link discovery of `020-add-crawl-core` finds. That requirement defines:

- which responses are read (the HTML of parsed Pages, and the `Link` headers of in-Scope 2xx responses)
- the Link types
- which references are ignored

This change stores each discovered Link together with the attributes that analysis needs:

| Column | Value |
|---|---|
| `source_url_id` | the `urls.id` of the URL whose response contains the Link |
| `ordinal` | the Link's position in that response, from 1: header Links first in the order received, then HTML Links in document order |
| `target_url_id` | the `urls.id` of the Link's normalised target |
| `type` | the Link type from the Link type table of `020-add-crawl-core` |
| `origin` | `html` or `http_header` |
| `element`, `attribute` | the HTML element and attribute the Link came from (for example `img` and `srcset`); NULL for header Links |
| `anchor_text` | for `hyperlink`, the element text. When that is empty, the `alt` texts of the `<img>` elements inside, joined with a space. For `<area>`, its `alt`. NULL for other types. |
| `alt_text` | for `image` Links from an `<img>` element, the normalised `alt` attribute: NULL when absent, the empty string when empty. NULL otherwise. |
| `rel` | the `rel` value with tokens lowercased and single-spaced, or NULL |
| `rel_nofollow`, `rel_ugc`, `rel_sponsored` | 1 when `rel` contains that token, otherwise 0 |
| `hreflang` | the trimmed `hreflang` value for `hreflang` Links, otherwise NULL |
| `media` | the trimmed `media` value for `mobile_alternate` Links, otherwise NULL |
| `target_is_internal` | the target's `urls.is_internal` |
| `in_content_area` | 1 when the element is inside the Content Area of an analysed Page; 0 otherwise, including Links in `<head>` and in headers |

`(source_url_id, ordinal)` SHALL be the primary key.

#### Scenario: Hyperlink with rel flags
- **WHEN** the analysed Page `https://example.test/a` contains `<main><a href="/b" rel="nofollow UGC">Read  more</a></main>`
- **THEN** one `links` row has `type` `hyperlink`, `anchor_text` `Read more`, `rel` `nofollow ugc`, `rel_nofollow` 1, `rel_ugc` 1, `rel_sponsored` 0 and `target_is_internal` 1

#### Scenario: Image alt attribute absent or empty
- **WHEN** an analysed Page contains `<img src="/a.png">` and `<img src="/b.png" alt="">`
- **THEN** the `image` Link to `/a.png` has `element` `img`, `attribute` `src` and `alt_text` NULL, and the one to `/b.png` has `alt_text` equal to the empty string

#### Scenario: Image-only anchor takes the alt text
- **WHEN** an analysed Page contains `<a href="/c"><img src="/i.png" alt="Logo"></a>`
- **THEN** the `hyperlink` Link to `/c` has `anchor_text` `Logo`

#### Scenario: Every occurrence is stored
- **WHEN** an analysed Page contains `<a href="/b">1</a><a href="/b">2</a>`
- **THEN** `links` holds 2 `hyperlink` rows from that Page to `/b`

#### Scenario: Navigation Links are outside the Content Area
- **WHEN** fixture A is analysed with the default settings
- **THEN** its `hyperlink` Link to `/` has `in_content_area` 0

#### Scenario: Hreflang and mobile alternate Links
- **WHEN** an analysed Page has `<link rel="alternate" hreflang="de" href="/de/">` and `<link rel="alternate" media="only screen and (max-width: 640px)" href="https://m.example.test/">` in its head
- **THEN** its `hreflang` Link has `hreflang` `de` and `media` NULL, and its `mobile_alternate` Link has `media` `only screen and (max-width: 640px)` and `hreflang` NULL

### Requirement: Stored Links match discovery
The distinct targets of the Links stored for a response SHALL be exactly the URLs that the Link discovery of `020-add-crawl-core` found in that response. That change still decides which of those URLs are requested. Every `links.target_url_id` SHALL refer to a `urls` row, whether or not that URL was requested.

#### Scenario: Discovered URLs are the stored Link targets
- **WHEN** a Crawl starts at `{site}/links`, whose body is `<a href="/a">a</a><a href="/b" rel="nofollow">b</a><img src="/i.png">`, and `/a`, `/b` and `/i.png` contain no Links
- **THEN** the `urls` table holds exactly `{site}/links`, `{site}/a`, `{site}/b` and `{site}/i.png`, and `links` holds 3 rows whose targets are the last three

### Requirement: Inlink and outlink counts
The link count columns SHALL count only `hyperlink` Links whose source is a Page, and SHALL leave out Links whose target is their own source (self-links). Hyperlinks with `rel_nofollow` 1 still count.

**Outlinks.** These SHALL be written with an analysed Page:

- `outlinks`: its Links to Internal URLs
- `unique_outlinks`: the distinct Internal targets of those Links
- `external_outlinks`: its Links to External URLs
- `unique_external_outlinks`: the distinct External targets of those Links

**Inlinks.** These SHALL be NULL until the post-crawl passes have run, and then filled for every Page:

- `inlinks`: the Links from any Page to this Page
- `unique_inlinks`: the distinct source Pages of those Links
- `linking_pages_pct` (Screaming Frog's "% of Total"): 100 × (the number of distinct source Pages with status 200 that link to this Page) ÷ (the number of Pages with status 200 in the Crawl), rounded to 2 decimals, or NULL when there are no Pages with status 200

**The post-crawl passes.** The inlink counts are computed in the post-crawl passes that `020-add-crawl-core` runs when a Crawl ends as `completed` or `stopped`. They run again when a resumed Crawl ends, and each run SHALL replace the earlier results. They run before the post-crawl passes of `040-add-rules`.

`unique_js_inlinks` and `unique_js_outlinks` SHALL be NULL, because they are measured from v1.1.

The two scenarios below use this site: four 200 Pages A, B, C and D, where A links to B twice, to C once, to itself once, to the External URL E1 twice and to E2 once; B, C and D each link to A once.

#### Scenario: Counts for a linked Page
- **WHEN** the post-crawl passes have run on the site above
- **THEN** A has `inlinks` 3, `unique_inlinks` 3, `linking_pages_pct` 75.00, `outlinks` 3, `unique_outlinks` 2, `external_outlinks` 3 and `unique_external_outlinks` 2

#### Scenario: Repeated inlinks from one source
- **WHEN** the post-crawl passes have run on the site above
- **THEN** B has `inlinks` 2, `unique_inlinks` 1 and `linking_pages_pct` 25.00, and D has `inlinks` 0 and `linking_pages_pct` 0.00

#### Scenario: Inlinks are NULL while the Crawl runs
- **WHEN** a Crawl is still `running`
- **THEN** every stored Page has `inlinks` NULL

### Requirement: Crawl Depth and Folder Depth
`crawl_depth` SHALL equal `urls.crawl_depth` for the Page. `folder_depth` SHALL be the number of non-empty segments in the path of the Page's `address`. The query string is ignored, and a trailing slash does not add a segment.

#### Scenario: Folder depth
- **WHEN** Pages have the paths `/`, `/blog/`, `/blog/post.html` and `/a//b/`
- **THEN** their `folder_depth` values are 0, 1, 2 and 2

#### Scenario: Crawl Depth is copied from the crawl engine
- **WHEN** the Seed `{site}/` links to `{site}/l1`, which links to `{site}/l2`
- **THEN** `{site}/l2` has `crawl_depth` 2

### Requirement: Raw HTML storage
Whether a Crawl stores the HTML of its Pages SHALL be decided once, when the Crawl starts:

- `--store-html`, or `store_html = true` under `[crawl]` in `spider.toml`, turns storage on.
- `--no-store-html`, or `store_html = false`, turns it off.
- A flag overrides `spider.toml`, as `010-add-workspace-and-cli-contract` defines.
- When neither is set, storage is on exactly when the Crawl's `max_urls` is from 1 to 50,000. The default of 10,000 turns it on. 0, which means no limit, turns it off.

The Crawl's recorded config SHALL hold the decision as `store_html` = `true` or `false`, and a resumed Crawl SHALL keep it, even when it is resumed with a higher `--max-urls`.

When storage is on, each Page SHALL have one `page_sources` row with these columns:

- `url_id`
- `encoding`: the character encoding found by the decoding rules of this capability
- `html`: a zstd frame of the response body bytes after content decoding

When storage is off, `page_sources` SHALL hold no rows.

#### Scenario: The automatic decision follows the URL limit
- **WHEN** the storage decision is made without `--store-html`, `--no-store-html` or `store_html`, for `max_urls` 10000, 50000, 50001 and 0 in turn
- **THEN** storage is on, on, off and off respectively

#### Scenario: Default limit stores HTML automatically
- **WHEN** a Crawl of a 3-Page fixture site runs with the default settings
- **THEN** `page_sources` holds 3 rows

#### Scenario: Large limit turns automatic storage off
- **WHEN** a Crawl of a 3-Page fixture site runs with `--max-urls 60000`
- **THEN** `page_sources` holds 0 rows

#### Scenario: Stored HTML is byte-identical
- **WHEN** the stored `html` of `{site}/about` is decompressed as a zstd frame
- **THEN** the result equals the exact body bytes the fixture served for `/about`

#### Scenario: HTML storage turned off
- **WHEN** a Crawl runs with `--no-store-html`
- **THEN** `page_sources` holds 0 rows and the recorded `store_html` is `false`

#### Scenario: Flag overrides spider.toml
- **WHEN** `spider.toml` sets `store_html = false` under `[crawl]` and the Crawl runs with `--store-html`
- **THEN** every Page of the Crawl has a `page_sources` row

#### Scenario: Encoding of stored HTML
- **WHEN** the windows-1251 Page from "Charset declared in a meta element" is stored
- **THEN** its `page_sources.encoding` is `windows-1251`

### Requirement: Columns measured by later releases stay NULL
These columns SHALL exist in v0.1 and SHALL be NULL for every Page, never 0:

- `link_score` (measured from v0.2)
- `closest_similarity_pct` and `near_duplicate_count` (v0.3)
- `structured_data_errors` and `structured_data_warnings` (v0.3)
- `unique_js_inlinks`, `unique_js_outlinks` and `js_cookie_count` (v1.1)

Their column descriptions SHALL name the release that fills them.

#### Scenario: Deferred columns are NULL after a completed Crawl
- **WHEN** a Crawl of the fixture site ends as `completed` and its post-crawl passes have run
- **THEN** 0 Pages have a non-NULL value in any of the eight deferred columns

#### Scenario: Deferred columns are described with their release
- **WHEN** `spider schema pages` runs
- **THEN** the description of `link_score` contains `v0.2` and the description of `unique_js_inlinks` contains `v1.1`

### Requirement: Documented Page data tables
`spider schema` SHALL list the tables `pages`, `links`, `cookies` and `page_sources`, following the table conventions of `015-add-crawl-store`:

- `references` for every id column
- the `timestamp`, `boolean` and `json` formats
- `values` for every enumeration

`docs/schema.md` SHALL document these tables as `015-add-crawl-store` requires.

#### Scenario: Link types are an enumeration
- **WHEN** `spider schema links` runs
- **THEN** the `values` of the column `type` are `["hyperlink","canonical","pagination","hreflang","iframe","meta_refresh","image","css","javascript","media","amphtml","mobile_alternate"]`

### Requirement: Same values on every operating system
The same fixture Crawl SHALL store identical Page data on Windows, macOS and Linux, whatever the console code page, locale or installed fonts.

#### Scenario: Non-ASCII title on a Windows console
- **WHEN** `spider crawl {site}/ru` runs as a subprocess on Windows with console code page 1251, and the Page's title is `Привет, мир`
- **THEN** the stored `title_1` is `Привет, мир` and `title_1_length` is 11
