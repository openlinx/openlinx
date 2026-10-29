# The crawl file schema

Every Crawl is one SQLite file, and its tables are a public, versioned contract ([ADR-0002](adr/0002-sqlite-crawl-store-public-schema.md)): agents and people may query them directly with read-only SQL. This page is the reference for those tables. Terms follow [CONTEXT.md](../CONTEXT.md).

This page is written by hand, for people and agents. A test compares it with the schema the tool declares, so the two cannot drift apart. Where crawl files live and how they are written is in [crawl-store.md](crawl-store.md).

## How to read a table section

Each table has a section headed ``## Table `<name>` ``, with a description and one row per column, in table order:

| Heading | Meaning |
|---|---|
| Column | the column name |
| Type | the SQLite type: `INTEGER`, `REAL`, `TEXT` or `BLOB` |
| Null | `yes` when the column may hold NULL, `no` when it may not |
| Key | `PK` for the primary key, ``→ `<table>.<column>` `` for a reference to another table, or empty |
| Format | `timestamp`, `boolean` or `json` when the column holds one of those, otherwise empty |
| Values | the allowed values of an enumeration, otherwise empty |
| Description | what the column holds |

A table with secondary indexes has a ``### Indexes`` table after its columns, with one row per index, in name order. The indexes SQLite makes for primary keys are not listed.

| Heading | Meaning |
|---|---|
| Name | the index name, `<table>_<columns>` |
| Columns | the indexed columns, in index order, each in backticks and separated by commas |
| Unique | `yes` when no two rows may share the indexed values, otherwise `no` |
| Where | the condition of a partial index, which holds only the rows that meet it, in backticks as `CREATE INDEX` writes it, with bare column names and literal values, such as `` `fetch_state = 'queued'` ``; otherwise empty |
| Description | the query the index serves |

Tables are listed in the order of the change that added them, and within a change in the order it added them.

## Conventions

Every public table, column and index follows the conventions of [ADR-0005](adr/0005-crawl-file-schema-conventions.md), which gives all the naming rules and their reasons. The file enforces the ones it can, tests over `linx schema` and the declaration check some others, and review checks the rest:
- **STRICT tables:** every table is `STRICT`, so a column's type is `INTEGER`, `REAL`, `TEXT` or `BLOB`, and the file refuses a value of another type. Reading a crawl file needs SQLite 3.37 or later.
- **Names:** lowercase snake_case. Table names are plural nouns, except the one-row `crawl`.
- **Descriptions:** every table, column and index has one. Two prefixes mark a column that stays NULL for a while:
  - `Derived: `: only a post-crawl pass writes it, and it is NULL until the pass has run.
  - `Filled from v<major>.<minor>. `: a later release fills it, and it is NULL in every row until then.
- **Keys and references:**
  - An entity's own key is `id`, INTEGER. Only the public identifiers that a user types, the crawl id and Rule ids, are TEXT. A table with a natural key uses it.
  - A column that refers to another table is named `<table singular>_id`, with a role prefix when a table refers to the same table twice, such as `source_url_id` and `target_url_id`. It is declared as a foreign key.
- **Timestamps:** TEXT in the form `YYYY-MM-DDTHH:MM:SS.sssZ`, in UTC, with the format `timestamp`, in a column whose name ends with `_at`. They sort as text. A time read from a header keeps the header's name, such as `last_modified`, and so does a header's raw value, which keeps its text, such as `content_type`.
- **Booleans:** INTEGER `0` or `1`, with the format `boolean`. The file refuses any other value, through a CHECK named `<table>_<column>_flag`. The name reads as yes or no, such as `is_*` or `has_*`, and is never negated.
- **JSON:** TEXT holding valid JSON, with the format `json`, only for recorded inputs and for lists without a fixed shape. A value that queries filter, sort or count by is a column of its own.
- **Enumerations:** TEXT whose allowed values are lowercase snake_case, listed under Values. The file refuses any other value, through a CHECK named `<table>_<column>_values`. A CHECK passes on NULL: `NOT NULL` is what refuses NULL. Values that a later release adds are listed from v0.1, and one enumeration has one value set in every table that holds it.
- **Errors:** an error is a code column whose values are listed, and its text is in a column named `<code column>_message`. A code is never a prefix inside free text.
- **Measured quantities:** the column name ends with its unit: `_ms`, `_seconds`, `_bytes`, `_px` or `_pct` (a share from 0 to 100). A count ends with `_count`. Each column has one meaning, so two different measures, such as two hashes or two sizes, are two distinctly named columns. A column that carries the name SEO practitioners already use keeps that name.
- **Indexes:** each is named `<table>_<columns>`, and its description names the query it serves. An index is built while the Crawl writes, never after it, so its queries are fast on a running Crawl too.
- **Order:** a table whose rows have an order carries it in an INTEGER column that grows in insert order. List rows in order by that column, never by a timestamp.
- **Counts:** no count or statistic is written while the Crawl runs. Counts are derived from the tables that hold the rows they count. A derived value over the stored rows, such as a score, is stored only by a post-crawl pass, in a `Derived: ` column.
- **Not measured is NULL.** A value that was not measured, or that does not apply, is NULL, never `0` or an empty string. `0` is a measured zero, and an empty string is a value that is present but empty. A later or derived column is NULL until it is filled.

## How to add a table

A change that stores new data adds its tables and columns in the slice whose scenario first needs them:
1. **Declare it** with `public_table(name, *columns, comment=..., change=<n>)` in `openlinx.store.schema`, the only definition of the schema, with the change's number as `change`. It makes the table `STRICT` and adds the CHECKs of its enumerations and flags, so no CHECK is written by hand.
   - Give every column a `comment`, and use the shared column types for timestamps (`Timestamp`), JSON (`Json`) and booleans (`Flag`).
   - Declare a real number with `sqlalchemy.REAL`: `Float` and `Double` declare `FLOAT` and `DOUBLE`, which STRICT refuses.
   - Read an enumeration's `values` from the `Literal` the code uses.
   - Declare each index with `info={"description": ...}`, naming the query it serves. Declare a unique rule as an index with `unique=True`, never as a `UNIQUE` constraint, whose index SQLite makes and nothing lists.
2. **Document it here, in the same commit:** a ``## Table `<name>` `` section, placed in change order, with the same description, one row per column, and an Indexes table when it has secondary indexes. The contract test compares this page with `linx schema --limit 1000`, so it is never red between commits.
3. **Follow the [conventions](#conventions).** Tests over `linx schema` and the declaration check names, descriptions, types, booleans, enumeration values, references, index names, unique rules declared as indexes, and that derived and later columns may hold NULL, for every table, including new ones.
4. **No migration before v0.1.** Until the first release the schema is not yet public: a change edits the declared tables directly, and `schema_version` stays `1`. From v0.1 on, a schema change adds 1 to `schema_version` and brings a migration, with a test from every published schema version.

A table whose name starts with `_` is internal: it is left out of `linx schema` and of this page.

## Table `crawl`

The Crawl's metadata, in exactly one row.

| Column | Type | Null | Key | Format | Values | Description |
|---|---|---|---|---|---|---|
| `id` | TEXT | no | PK | | | The crawl id. |
| `crawl_mode` | TEXT | no | | | `spider`, `list`, `sitemap` | How the Crawl finds URLs. |
| `section_crawl` | INTEGER | no | | `boolean` | | 1 for a Section Crawl, whose Scope is one part of a site, otherwise 0. |
| `scope` | TEXT | no | | `json` | | The resolved Scope, as an object of mode, hosts, folder, include and exclude. |
| `state` | TEXT | no | | | `running`, `stopped`, `completed`, `failed`, `interrupted` | The Crawl State. |
| `started_at` | TEXT | no | | `timestamp` | | When the Crawl started. |
| `completed_at` | TEXT | yes | | `timestamp` | | When the state became completed; NULL in every other state. |
| `stop_reason` | TEXT | yes | | | `max_urls`, `interrupt`, `requested`, `seed_unreachable`, `site_unreachable`, `write_failed` | Why the Crawl ended early: max_urls, interrupt or requested for a stopped Crawl, seed_unreachable, site_unreachable or write_failed for a failed one; NULL while it runs and when it is completed. |
| `warnings` | TEXT | no | | `json` | | The Crawl's warnings, as an array of diagnostics of level, code, message, hint and details; [] when the Crawl is created. |
| `command_argv` | TEXT | no | | `json` | | The command line as an array that starts with the command name, secrets redacted. |
| `cwd` | TEXT | no | | | | The absolute folder the Command ran in. |
| `settings_file` | TEXT | yes | | | | The absolute path of the settings file that was read, or NULL without one. |
| `config` | TEXT | no | | `json` | | The resolved settings as an object of tables and keys, secrets redacted. |
| `tool_version` | TEXT | no | | | | The version of the tool that created the Crawl. |
| `schema_version` | INTEGER | no | | | | The schema version of this file, also stored as SQLite's user_version. |
| `journal_mode` | TEXT | no | | | `wal`, `delete` | The SQLite journal mode the file was created with. |
| `python_version` | TEXT | no | | | | The Python version that created the Crawl. |
| `platform` | TEXT | no | | | | The operating system that created the Crawl, as Python describes it. |

## Table `seeds`

The Seeds the Crawl started from, in the order they were given.

| Column | Type | Null | Key | Format | Values | Description |
|---|---|---|---|---|---|---|
| `position` | INTEGER | no | PK | | | The 1-based order in which the Seed was given. |
| `url` | TEXT | no | | | | The Seed URL as given. |

## Table `urls`

One row for each distinct normalised URL of the Crawl; the frontier is its queued rows.

| Column | Type | Null | Key | Format | Values | Description |
|---|---|---|---|---|---|---|
| `id` | INTEGER | no | PK | | | Row id, stable for the life of the crawl file; it grows in the order URLs are first recorded, and is the dispatch order within a Crawl Depth. |
| `url` | TEXT | no | | | | The normalised URL, unique. |
| `host` | TEXT | no | | | | The URL's host in lower-case ASCII (IDNA) form; the key of the per-host politeness limits. |
| `origin_id` | INTEGER | no | → `origins.id` | | | The URL's origin: its scheme, host and port. |
| `is_internal` | INTEGER | no | | `boolean` | | 1 for an Internal URL, 0 for an External URL. |
| `in_scope` | INTEGER | no | | `boolean` | | 1 when the URL is inside the Scope, so it may be followed. |
| `crawl_depth` | INTEGER | no | | | | Crawl Depth; 0 for Seeds. |
| `discovered_via` | TEXT | no | | | `seed`, `hyperlink`, `canonical`, `pagination`, `hreflang`, `iframe`, `meta_refresh`, `http_refresh`, `image`, `css`, `javascript`, `video`, `audio`, `media`, `amphtml`, `mobile_alternate`, `misc`, `xml_sitemap`, `sitemap_hreflang`, `javascript_redirect`, `redirect`, `list`, `sitemap_input`, `sitemap_index` | How the URL was found: seed, or the type of the Link the Provenance rule takes, a followed one once one has reached it, a Resource Link over another type. |
| `found_on_url_id` | INTEGER | yes | → `urls.id` | | | The URL whose response gave that Link; NULL for Seeds. |
| `fetch_state` | TEXT | no | | | `queued`, `fetched`, `error`, `skipped` | Frontier state: waiting, a response was recorded, no response, or not requested. |
| `skip_reason` | TEXT | yes | | | `excluded`, `blocked_by_robots_txt`, `robots_unreachable`, `nofollow`, `link_type_not_followed`, `external_not_checked`, `max_depth`, `max_redirects`, `url_too_long` | Why a skipped URL was not requested. |
| `blocked_by_robots_txt` | INTEGER | yes | | `boolean` | | 1 when robots.txt disallows the URL for the robots user-agent token (also with --ignore-robots), 0 when it allows it; NULL when not checked. |
| `status_code` | INTEGER | yes | | | | HTTP status code of the URL's own response; NULL without a response. |
| `fetch_error` | TEXT | yes | | | `dns_error`, `connection_refused`, `connection_error`, `invalid_response`, `watchdog`, `record_failed`, `timeout`, `tls_error` | Why no response is recorded for the URL. |
| `fetch_error_message` | TEXT | yes | | | | Human-readable detail of fetch_error. |
| `content_type` | TEXT | yes | | | | The Content-Type response header as received; NULL without a response or without the header. |
| `response_time_ms` | INTEGER | yes | | | | Time from sending the request to receiving the whole body. |
| `fetched_at` | TEXT | yes | | `timestamp` | | UTC time of the request. |
| `parsed` | INTEGER | no | | `boolean` | | 1 when the response was parsed and its Links were found. |
| `parse_error` | TEXT | yes | | | `extractor_error`, `body_too_large`, `worker_crashed`, `parse_timeout` | Why parsing failed in whole or in part: a registered extractor failed (parsed stays 1), or nothing came out of page preparation (parsed = 0). |
| `parse_error_message` | TEXT | yes | | | | Human-readable detail of parse_error. |

### Indexes

| Name | Columns | Unique | Where | Description |
|---|---|---|---|---|
| `urls_crawl_depth_id` | `crawl_depth`, `id` | no | `fetch_state = 'queued'` | The frontier: the next queued URLs of the open Crawl Depth, in id order. |
| `urls_url` | `url` | yes | | Recording a discovered URL once (ON CONFLICT (url)), and finding one URL's row. |

## Table `origins`

One row for each origin of a URL that the Crawl recorded.

| Column | Type | Null | Key | Format | Values | Description |
|---|---|---|---|---|---|---|
| `id` | INTEGER | no | PK | | | Row id. |
| `origin` | TEXT | no | | | | Scheme, host and port, for example https://site.test, with a default port left out; unique. |
| `host` | TEXT | no | | | | The origin's host in lower-case ASCII (IDNA) form. |
| `is_internal` | INTEGER | no | | `boolean` | | 1 when the origin's URLs are Internal URLs. |
| `robots_state` | TEXT | yes | | | `ok`, `missing`, `unreachable` | Rules applied, everything allowed, or everything disallowed or unanswered; NULL while robots.txt has not been fetched, which happens before the first URL of the origin that the Scope does not skip and the URL limit does not refuse. |
| `robots_status_code` | INTEGER | yes | | | | Status code of the final robots.txt response; NULL without a response. |
| `robots_fetch_error` | TEXT | yes | | | `dns_error`, `connection_refused`, `connection_error`, `invalid_response`, `watchdog`, `record_failed`, `timeout`, `tls_error` | Why the robots.txt request got no HTTP response; NULL when it got one, or while robots.txt has not been fetched. |
| `robots_fetch_error_message` | TEXT | yes | | | | Human-readable detail of robots_fetch_error. |
| `robots_fetched_at` | TEXT | yes | | `timestamp` | | UTC time robots.txt was last fetched. |
| `robots_txt` | TEXT | yes | | | | The robots.txt body as parsed, up to 512,000 bytes. |
| `robots_crawl_delay_ms` | INTEGER | yes | | | | The Crawl-delay for the robots user-agent token; recorded, not applied. |
| `robots_sitemaps` | TEXT | yes | | `json` | | JSON array of the Sitemap: URLs in robots.txt; NULL while robots.txt has not been fetched. |

### Indexes

| Name | Columns | Unique | Where | Description |
|---|---|---|---|---|
| `origins_origin` | `origin` | yes | | Recording an origin once (ON CONFLICT (origin)), and finding an origin's row. |

## Table `pages`

One row for each Page of the Crawl: an Internal URL in the Scope whose response is an HTML document, whatever its status code.

| Column | Type | Null | Key | Format | Values | Description |
|---|---|---|---|---|---|---|
| `url_id` | INTEGER | no | PK, → `urls.id` | | | The Page's URL. |
| `address` | TEXT | no | | | | The Page's URL for display: url_encoded_address with the host in Unicode and every percent-encoded UTF-8 sequence of a non-ASCII character decoded; percent-encoded ASCII characters stay encoded, and so do characters of the Unicode categories Cc, Cf, Zs, Zl and Zp. |
| `url_encoded_address` | TEXT | no | | | | The Page's URL as the Crawl requested it, equal to urls.url: the host in IDNA (punycode) form and every non-ASCII character percent-encoded as UTF-8. |
| `url_path` | TEXT | no | | | | The path of address: from the first / after the host up to the first ?, or to the end. |
| `url_query` | TEXT | yes | | | | The query of address: the text after the first ?; NULL when address has no ?, and the empty string when nothing follows it. |
| `content_type` | TEXT | no | | | | The Content-Type response header as received, equal to urls.content_type. |
| `status_code` | INTEGER | no | | | | The HTTP status code of the Page's own response, equal to urls.status_code. |
| `status` | TEXT | yes | | | | The reason phrase the server sent; when it sent none, the phrase that the IANA HTTP Status Code Registry gives the status code; NULL when the registry gives none. |
| `indexability` | TEXT | no | | | `indexable`, `non_indexable` | Whether a search engine may index the Page, by the first reason in the Indexability order that applies. |
| `indexability_status` | TEXT | yes | | | `blocked_by_robots_txt`, `redirected`, `client_error`, `server_error`, `noindex`, `canonicalised` | The first reason in the Indexability order that makes the Page non_indexable: robots.txt, then the status class, then noindex, then a refresh redirect, then a canonical to another URL; NULL when the Page is indexable. |
| `response_time_ms` | INTEGER | no | | | | Time from sending the request to receiving the whole body, equal to urls.response_time_ms. |
| `last_modified` | TEXT | yes | | `timestamp` | | The first Last-Modified response header as a UTC time, read as an HTTP-date or another Internet Message Format date; NULL when absent, another text or a leap second. |
| `redirect_url` | TEXT | yes | | | | The URL the Page redirects to: the target of its 3xx response, of its HTTP Refresh header, or of its first meta refresh; NULL when it does not redirect, or when the target is its own URL. |
| `redirect_type` | TEXT | yes | | | `http_redirect`, `http_refresh`, `meta_refresh`, `javascript_redirect` | How the Page redirects to redirect_url; NULL when it does not redirect. javascript_redirect is filled from v1.1. |
| `set_cookie_count` | INTEGER | no | | | | The number of Set-Cookie headers of the Page's response, equal to its rows in cookies. |
| `crawl_timestamp` | TEXT | no | | `timestamp` | | The UTC time of the Page's request, equal to urls.fetched_at. |
| `title_1` | TEXT | yes | | | | The text of the Page's first title element without an svg, math or noscript ancestor, whitespace-normalised; NULL without one, or when the Page is not analysed or its Page extractor failed. |
| `title_1_length` | INTEGER | yes | | | | The length of title_1 in Unicode code points; NULL exactly when title_1 is. |
| `title_2` | TEXT | yes | | | | The text of the Page's second title element without an svg, math or noscript ancestor, whitespace-normalised; NULL without one, or when the Page is not analysed or its Page extractor failed. |
| `title_2_length` | INTEGER | yes | | | | The length of title_2 in Unicode code points; NULL exactly when title_2 is. |
| `title_count` | INTEGER | yes | | | | The number of title elements without an svg, math or noscript ancestor; NULL when the Page is not analysed or its Page extractor failed. |
| `meta_description_1` | TEXT | yes | | | | The content of the Page's first meta description, whitespace-normalised, the empty string for one without content; NULL without one, or when the Page is not analysed or its Page extractor failed. |
| `meta_description_1_length` | INTEGER | yes | | | | The length of meta_description_1 in Unicode code points; NULL exactly when meta_description_1 is. |
| `meta_description_2` | TEXT | yes | | | | The content of the Page's second meta description, whitespace-normalised, the empty string for one without content; NULL without one, or when the Page is not analysed or its Page extractor failed. |
| `meta_description_2_length` | INTEGER | yes | | | | The length of meta_description_2 in Unicode code points; NULL exactly when meta_description_2 is. |
| `meta_description_count` | INTEGER | yes | | | | The number of meta elements named description without an svg, math or noscript ancestor; NULL when the Page is not analysed or its Page extractor failed. |
| `meta_keywords_1` | TEXT | yes | | | | The content of the Page's first meta keywords element, whitespace-normalised, the empty string for one without content; NULL without one, or when the Page is not analysed or its Page extractor failed. |
| `meta_keywords_1_length` | INTEGER | yes | | | | The length of meta_keywords_1 in Unicode code points; NULL exactly when meta_keywords_1 is. |
| `h1_1` | TEXT | yes | | | | The text of the Page's first h1 element without an svg, math or noscript ancestor, whitespace-normalised; NULL without one, or when the Page is not analysed or its Page extractor failed. |
| `h1_1_length` | INTEGER | yes | | | | The length of h1_1 in Unicode code points; NULL exactly when h1_1 is. |
| `h1_2` | TEXT | yes | | | | The text of the Page's second h1 element without an svg, math or noscript ancestor, whitespace-normalised; NULL without one, or when the Page is not analysed or its Page extractor failed. |
| `h1_2_length` | INTEGER | yes | | | | The length of h1_2 in Unicode code points; NULL exactly when h1_2 is. |
| `h1_count` | INTEGER | yes | | | | The number of h1 elements without an svg, math or noscript ancestor; NULL when the Page is not analysed or its Page extractor failed. |
| `h2_1` | TEXT | yes | | | | The text of the Page's first h2 element without an svg, math or noscript ancestor, whitespace-normalised; NULL without one, or when the Page is not analysed or its Page extractor failed. |
| `h2_1_length` | INTEGER | yes | | | | The length of h2_1 in Unicode code points; NULL exactly when h2_1 is. |
| `h2_2` | TEXT | yes | | | | The text of the Page's second h2 element without an svg, math or noscript ancestor, whitespace-normalised; NULL without one, or when the Page is not analysed or its Page extractor failed. |
| `h2_2_length` | INTEGER | yes | | | | The length of h2_2 in Unicode code points; NULL exactly when h2_2 is. |
| `h2_count` | INTEGER | yes | | | | The number of h2 elements without an svg, math or noscript ancestor; NULL when the Page is not analysed or its Page extractor failed. |
| `meta_robots` | TEXT | yes | | | | The content of every meta element named robots, in document order, as the robots directives parser normalises and joins them; NULL without one, or when the Page is not analysed. |
| `meta_robots_noindex` | INTEGER | yes | | `boolean` | | 1 when the robots directives parser reads noindex in meta_robots; NULL when the Page is not analysed. |
| `meta_robots_nofollow` | INTEGER | yes | | `boolean` | | 1 when the robots directives parser reads nofollow in meta_robots; NULL when the Page is not analysed. |
| `x_robots_tag` | TEXT | yes | | | | The values of every X-Robots-Tag response header, in the order received, as the robots directives parser normalises and joins them; NULL without one. |
| `x_robots_tag_noindex` | INTEGER | yes | | `boolean` | | 1 when the robots directives parser reads noindex in x_robots_tag for the robots user-agent token. |
| `x_robots_tag_nofollow` | INTEGER | yes | | `boolean` | | 1 when the robots directives parser reads nofollow in x_robots_tag for the robots user-agent token. |
| `meta_refresh` | TEXT | yes | | | | The content of the first meta element whose http-equiv is refresh, whitespace-normalised; NULL without one, or when the Page is not analysed or its Page extractor failed. |
| `canonical_url` | TEXT | yes | | | | The URL that every canonical declaration resolves to, when they resolve to one URL; NULL without a declaration, when they disagree, or when the Page is not analysed. |
| `canonical_link_element_1` | TEXT | yes | | | | The resolved URL of the first canonical link element in head; NULL without one, or when the Page is not analysed. |
| `canonical_link_element_2` | TEXT | yes | | | | The resolved URL of the second canonical link element in head; NULL without one, or when the Page is not analysed. |
| `http_canonical` | TEXT | yes | | | | The resolved URL of the first canonical Link header entry; NULL without one, or when the Page is not analysed. |
| `canonical_count` | INTEGER | yes | | | | The number of canonical declarations: canonical link elements in head and canonical Link header entries; NULL when the Page is not analysed. |
| `canonical_relative` | INTEGER | yes | | `boolean` | | 1 when the href of a canonical link element in head, after the leading control characters and spaces that the URL parser removes, does not start with http: or https:, compared case-insensitively; NULL when the Page is not analysed. |
| `rel_next_1` | TEXT | yes | | | | The target of the first pagination link element of the HTML whose rel names next; NULL without one, or when the Page is not analysed. |
| `rel_prev_1` | TEXT | yes | | | | The target of the first pagination link element of the HTML whose rel names prev or previous; NULL without one, or when the Page is not analysed. |
| `http_rel_next_1` | TEXT | yes | | | | The target of the first pagination Link header entry whose rel names next; NULL without one, or when the Page is not analysed. |
| `http_rel_prev_1` | TEXT | yes | | | | The target of the first pagination Link header entry whose rel names prev or previous; NULL without one, or when the Page is not analysed. |
| `amphtml_link_element` | TEXT | yes | | | | The target of the first amphtml link element; NULL without one, or when the Page is not analysed. |
| `mobile_alternate_link` | TEXT | yes | | | | The target of the first link element whose rel is alternate with a media attribute and no hreflang; NULL without one, or when the Page is not analysed. |
| `word_count` | INTEGER | yes | | | | The number of words in the Content Area text; NULL when the Page is not analysed or its Page extractor failed. |
| `sentence_count` | INTEGER | yes | | | | The number of sentences in the Content Area text; NULL when the Page is not analysed or its Page extractor failed. |
| `average_words_per_sentence` | REAL | yes | | | | word_count divided by sentence_count, rounded half up to 2 decimals; NULL when sentence_count is 0, or the Page is not analysed or its Page extractor failed. |
| `text_ratio_pct` | REAL | yes | | | | 100 times the length of the normalised text of body, without Content Area exclusions, divided by the decoded HTML document's length in characters, rounded half up to 2 decimals; NULL when the document is empty, or the Page is not analysed or its Page extractor failed. |
| `declared_language` | TEXT | yes | | | | The lang attribute of the root html element, trimmed: the empty string when it has no value; NULL when it is absent, or the Page is not analysed or its Page extractor failed. |
| `content_hash` | TEXT | yes | | | | The SHA-256, as lowercase hex, of the normalised Content Area text as UTF-8, with no Unicode normalisation: Pages with the same value are Exact Duplicates; NULL when word_count is 0, or the Page is not analysed or its Page extractor failed. |
| `crawl_depth` | INTEGER | no | | | | Crawl Depth, equal to urls.crawl_depth: 0 for Seeds. |
| `jsonld_item_count` | INTEGER | yes | | | | The number of JSON-LD items in the application/ld+json scripts: each top-level object, of a script or of a top-level array, or instead the content of its @graph, an array of objects or one object; NULL when the Page is not analysed or its Page extractor failed. |
| `microdata_item_count` | INTEGER | yes | | | | The number of top-level Microdata items: elements with itemscope and no itemprop; NULL when the Page is not analysed or its Page extractor failed. |
| `jsonld_parse_error_count` | INTEGER | yes | | | | The number of application/ld+json scripts that are not valid JSON, or nest more than 1024 levels deep; NULL when the Page is not analysed or its Page extractor failed. |
| `structured_data_types` | TEXT | yes | | `json` | | JSON array of the distinct types of the counted items, from @type and itemtype without a leading http://schema.org/ or https://schema.org/, sorted by code point: [] when there are none; NULL when the Page is not analysed or its Page extractor failed. |

### Indexes

| Name | Columns | Unique | Where | Description |
|---|---|---|---|---|
| `pages_address` | `address` | yes | | Finding a Page by its display address, and the tie-breaker of keyset paging over Pages. |

## Table `cookies`

One row for each Set-Cookie header of a Page's response, with the cookie's name and attributes, never its value.

| Column | Type | Null | Key | Format | Values | Description |
|---|---|---|---|---|---|---|
| `url_id` | INTEGER | no | PK, → `urls.id` | | | The Page whose response set the cookie. |
| `ordinal` | INTEGER | no | PK | | | The header's position among the response's Set-Cookie headers, from 1. |
| `name` | TEXT | no | | | | The text before the header's first =, trimmed; the empty string when its first part has no =. |
| `domain` | TEXT | yes | | | | The Domain attribute, lowercased, without a leading dot; NULL when absent, empty, or neither a host name nor an IP address. |
| `path` | TEXT | yes | | | | The Path attribute, trimmed, as sent; NULL when absent, when it does not start with /, which RFC 6265 reads as the default path, or when it holds a comma, which only a header that a proxy folded gives it. |
| `expires` | TEXT | yes | | `timestamp` | | The Expires attribute as a UTC time, a two-digit year read as RFC 6265 reads it; NULL when absent or invalid. |
| `max_age` | INTEGER | yes | | | | The Max-Age attribute, in seconds; NULL when absent or not an optional - followed by digits; a value beyond a 64-bit INTEGER is clamped to its bound. |
| `secure` | INTEGER | no | | `boolean` | | 1 when the Secure attribute is present. |
| `http_only` | INTEGER | no | | `boolean` | | 1 when the HttpOnly attribute is present. |
| `partitioned` | INTEGER | no | | `boolean` | | 1 when the Partitioned attribute is present. |
| `same_site` | TEXT | yes | | | `strict`, `lax`, `none` | The SameSite attribute, lowercased; NULL when absent or another value. |

## Table `links`

One row for each Link the Crawl discovered in a response: in an analysed Page's HTML, or in the Link and Refresh headers of an in-Scope 2xx response.

| Column | Type | Null | Key | Format | Values | Description |
|---|---|---|---|---|---|---|
| `source_url_id` | INTEGER | no | PK, → `urls.id` | | | The URL whose response contains the Link. |
| `ordinal` | INTEGER | no | PK | | | The Link's position in that response, from 1: header Links first in the order received, then the document's in document order, as the Crawl's Link discovery numbers them. |
| `target_url_id` | INTEGER | no | → `urls.id` | | | The URL of the Link's normalised target. |
| `type` | TEXT | no | | | `hyperlink`, `canonical`, `pagination`, `hreflang`, `iframe`, `meta_refresh`, `http_refresh`, `image`, `css`, `javascript`, `video`, `audio`, `media`, `amphtml`, `mobile_alternate`, `misc`, `xml_sitemap`, `sitemap_hreflang`, `javascript_redirect` | The Link type. |
| `declared_in` | TEXT | no | | | `head`, `body`, `http_header` | Where the Link was declared: in the document's head or body as the parser builds them, or in a response header. |
| `element` | TEXT | yes | | | `a`, `area`, `link`, `iframe`, `frame`, `meta`, `img`, `source`, `video`, `audio`, `track`, `embed`, `object`, `script` | The HTML element the Link came from; NULL for a header Link. |
| `attribute` | TEXT | yes | | | `href`, `src`, `srcset`, `poster`, `data`, `content` | The attribute the Link came from, such as src or srcset of an img; NULL for a header Link. |
| `anchor_text` | TEXT | yes | | | | For a hyperlink, the normalised text of its element, or when that is empty the alt texts of the img elements inside it, joined with a space; for an area, its alt; NULL for other types, or when the Page's Link extractor failed. |
| `alt_text` | TEXT | yes | | | | For an image Link from an img element, its alt attribute, normalised: the empty string when it has no value; NULL when it is absent, for other Links, or when the Page's Link extractor failed. |
| `rel` | TEXT | yes | | | | The Link's rel tokens, ASCII-lowercased, joined with single spaces; NULL without any. |
| `rel_nofollow` | INTEGER | no | | `boolean` | | 1 when rel holds nofollow. |
| `rel_ugc` | INTEGER | no | | `boolean` | | 1 when rel holds ugc. |
| `rel_sponsored` | INTEGER | no | | `boolean` | | 1 when rel holds sponsored. |
| `hreflang` | TEXT | yes | | | | For a hreflang Link, the trimmed hreflang of its element, or the hreflang parameter of its Link header; NULL for other Links, and for a Link of the HTML when the Page's Link extractor failed. |
| `media` | TEXT | yes | | | | For a mobile_alternate Link, the trimmed media of its element; NULL for other Links, or when the Page's Link extractor failed. |
| `link_position` | TEXT | yes | | | `head`, `navigation`, `header`, `footer`, `sidebar`, `content` | Where on the Page the Link is: head for a Link the parser places in head; otherwise from the nearest enclosing nav (navigation), header, footer or aside (sidebar), and content without one, a Link from a noscript's content taking the noscript's place; NULL for a header Link, or when the Page's Link extractor failed. |

### Indexes

| Name | Columns | Unique | Where | Description |
|---|---|---|---|---|
| `links_target` | `target_url_id` | no | | The inlinks of a URL: every Link that points at it. |
| `links_type_target` | `type`, `target_url_id` | no | | The inlinks of a URL of one Link type, such as its hyperlink inlinks. |
