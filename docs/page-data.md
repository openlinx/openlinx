# Page data

What a Crawl stores about each Page: the flat Page record in `pages`, one row per Page, read without joins, and one `links` row for each Link the Crawl discovered. The spec is [openspec/changes/030-add-page-data/specs/page-data/spec.md](../openspec/changes/030-add-page-data/specs/page-data/spec.md), and each column's one definition is its description in [schema.md](schema.md#table-pages) and [its `links` section](schema.md#table-links); this page explains what several columns share. Terms follow [CONTEXT.md](../CONTEXT.md).

## What a Page is

A Page is a URL of the Crawl that returned an HTML document. In the `urls` table, it is a row with all of:
- `is_internal` = 1 and `in_scope` = 1: an Internal URL in the Scope. An External URL is checked, never a Page.
- `fetch_state` = `fetched`: a response was recorded. A URL that was skipped, such as one that robots.txt disallows, or that got no response, is not a Page.
- a `content_type` whose media type is `text/html` or `application/xhtml+xml`, in any letter case, with its parameters ignored. An image, a PDF or a response without a `Content-Type` is not a Page.

The status code does not matter: a 404 or a 301 with an HTML body is a Page too.

Every Page has exactly one `pages` row, keyed by `url_id`, which is `urls.id`. It is written in the same transaction as the URL's response, so a reader never sees one without the other. Every other URL has none.

## Analysed and non-analysed Pages

A Page is *analysed* when the Crawl parsed it (`urls.parsed` = 1): its status is 2xx and its body was read in full. Only an analysed Page has values in the columns that come from its HTML, such as its titles and headings. A Page that is not analysed, such as a 404 or a redirect, has NULL in them; the columns that come from the URL and its response are set for every Page. When the Page extractor or the Link extractor fails on an analysed Page (`urls.parse_error` = `extractor_error`, with `parse_error_message` naming it), only the columns that extractor derives from the HTML are NULL, and the Page still has its `pages` row and its `links` rows. For the Link extractor, those are the `anchor_text`, `alt_text` and `link_position` of every Link, and the `hreflang` and `media` of the Links in the HTML; what a Link takes from Link discovery stays set.

## NULL, empty and zero

The columns follow the conventions of [schema.md](schema.md#conventions):
- NULL means not measured, or not applicable: an HTML column of a Page that is not analysed, an element the HTML does not have, or a column that a later release fills.
- The empty string is an element that is present but empty, such as `<title></title>`.
- 0 is a measured zero: a count of an analysed Page is 0 or more, and NULL only when the Page extractor failed on it.

## Decoding

Page preparation decodes an analysed Page's body once, as Link discovery does, from the first source that applies:
1. a byte order mark
2. the `charset` parameter of `Content-Type`
3. a `<meta charset>` or `<meta http-equiv="Content-Type">` declaration in the first 1024 bytes, outside comments; a declaration of UTF-16 means UTF-8, since it was read from ASCII bytes
4. UTF-8, or windows-1252 when the body is not valid UTF-8

Labels are those of the WHATWG Encoding Standard, and an unknown label is skipped, so the next source applies. A byte that does not decode becomes U+FFFD. The Page extractor reads the parsed document and never decodes anything itself.

## Text

The *text* of an element, such as a heading, is its text nodes in document order, with character references decoded. The content of `script`, `style`, `noscript`, `template`, `iframe`, `svg` and `math` elements is left out, since it is no text that the Page shows. A `br` element, and the start and end of every block-level element (such as `p`, `div`, `li` or `td`; the spec lists them all), give a break, so `<h1>Hello<br>World</h1>` reads `Hello World`, while an inline element such as `span` joins the text around it.

Every text column is whitespace-normalised, and breaks become spaces: each run of ASCII whitespace (tab, line feed, form feed, carriage return and space) becomes one space, and ASCII whitespace at either end is removed. A no-break space is text, so it is kept. A length is counted in Unicode code points of the normalised text.

## Elements of the HTML

Titles, meta descriptions, meta keywords and headings follow one pattern:
- **Which elements count.** An element with an `svg` or `math` ancestor does not count: it names a picture or a formula, not the Page, also inside an SVG image's `<foreignObject>`. Nothing inside `noscript` is an element, since page preparation reads the HTML as a browser that runs scripts does, so the metadata inside it is ignored, while the Links inside it are still discovered.
- **Meta elements** count by their `name`, trimmed of ASCII whitespace and compared in any ASCII letter case. Their text is their `content`, and a missing `content` gives the empty string.
- **Columns.** A `_count` column counts the elements, and is 0 when there are none. The `_1` and `_2` columns hold the normalised texts of the first two, in document order, NULL when there is no such element; meta keywords keep only the first, with no count. Each `_length` column is NULL exactly when its text is.
- **Headings** take the text of the whole element, nested elements such as `<span>` included (see [Text](#text)).

## Content Area

`word_count`, `sentence_count` and `average_words_per_sentence` are counted over the Page's Content Area (see [CONTEXT.md](../CONTEXT.md)). The `[content_area]` table of `openlinx.toml` sets it with two lists of CSS selectors:

```toml
[content_area]
include = []                          # the default: the root is <body>
exclude = ["nav", "header", "footer"] # the default
```

- **Roots.** With `include` empty, `<body>` is the only root. Otherwise the roots are the elements that an `include` selector matches and that no other match encloses, so an `<article>` inside a matched `<main>` is read once. Each root's text is a block of its own.
- **Exclusions.** Everything inside a root is in the Content Area, except an element that an `exclude` selector matches and everything inside it.
- **A list replaces the default.** Setting `exclude` in `openlinx.toml` replaces the whole default list, and `exclude = []` counts the whole `<body>`.
- **Invalid selectors** stop the Crawl before any request, with `settings_invalid` and the key `content_area.include` or `content_area.exclude`.
- **Recorded.** The Crawl records the values it used under `content_area` in its config. They apply to the Crawls started after a change, never to Pages already stored.

The default leaves out every `<header>`, also the header of an article, such as a post's title and byline. To keep those, leave out only the headers outside articles:

```toml
[content_area]
exclude = ["nav", "header:not(article header)", "footer"]
```

On a site whose template marks its parts with classes rather than elements, name them:

```toml
[content_area]
include = ["main"]
exclude = [".cookie-banner", ".share-buttons"]
```

## Words and sentences

The Content Area text is read as [Text](#text) is, block by block.

- **Words** are runs of letters, marks and digits (Unicode categories L, M and N), so a word in Devanagari keeps its vowel signs. One apostrophe, hyphen, full stop or comma between two such characters joins them, so `don't`, `state-of-the-art` and `v2.0` are one word each, while `_` separates words.
- **Ideographs.** Each Han, Hiragana or Katakana character, with the marks after it, is a word of its own, and so is the prolonged sound mark `ー`, so `カード` is three words.
- **Unicode version.** The letter, mark and ideograph classes come from Unicode 16.0.0's Scripts.txt and DerivedGeneralCategory.txt (`scripts/unicode_scripts.py` writes them), so a count is the same whichever Python ran the Crawl.
- **Limitation.** Scripts written without spaces between words, such as Thai, Lao, Khmer and Myanmar, are undercounted: a run of them is one word.
- **Sentences** end at the end of a block, so a heading is a sentence of its own, and after a run of `.`, `!`, `?` or `…` followed by whitespace, a no-break space or U+3000 included. The full-width `。`, `！` and `？` end a sentence with no space after them. A part of a block without a word is no sentence.
- **Rounding.** `average_words_per_sentence` and `text_ratio_pct` are rounded half up to 2 decimals from the exact quotient, so 1.125 is 1.13.

## Text Ratio

`text_ratio_pct` compares the text of the whole `<body>`, without Content Area exclusions, with the length of the decoded HTML document in characters, so a Page heavy in markup and scripts has a low ratio.

## Declared language

`declared_language` is the `lang` attribute of the root `<html>` element as the Page declares it, only trimmed: `en-GB` stays `en-GB`, and an invalid tag is kept as written. It is the empty string for `<html lang>` and NULL without the attribute. A `lang` on any other element is not read.

## Exact Duplicates

`content_hash` is the SHA-256, in lowercase hex, of the Content Area text as UTF-8, after the whitespace normalisation of every text column, so `<p>Hello   world</p>` and `<div><p>Hello</p><p>world</p></div>` hash the same. Two Pages with the same `content_hash` are Exact Duplicates.

- **No Unicode normalisation.** The text is hashed as the Page spells it, and letter case is kept. A precomposed `é` (U+00E9) and an `e` followed by a combining acute accent (U+0301) hash differently, and the hash is the same whichever Python ran the Crawl.
- **No words, no hash.** `content_hash` is NULL when `word_count` is 0, so Pages whose Content Area holds only navigation, or the empty shell of a client-rendered page, do not form one big duplicate group.

## Structured data

The structured-data columns count the items a Page declares in JSON-LD and Microdata. Only top-level items count: an Offer inside a Product is a property of the Product, so it adds neither a count nor a type.

- **JSON-LD scripts.** A `<script>` is JSON-LD when its `type`, trimmed of ASCII whitespace, is `application/ld+json` in any letter case. `jsonld_parse_error_count` counts the scripts that are not valid JSON (RFC 8259), such as a block a template cut short or one that holds `NaN`, and the scripts nested more than 1024 levels deep. A number beyond the range of a double, such as `1e400`, and an unpaired surrogate escape, such as a description cut in the middle of an emoji, make a script invalid too, as RFC 8259 lets a parser decide. Such a script adds no items.
- **JSON-LD items.** A top-level object is one item, unless its `@graph` is an array or an object: then the objects of its `@graph` are the items. A top-level array contributes what each of its objects does. Strings, numbers and nested arrays add nothing.
- **Microdata items.** `microdata_item_count` counts the elements with `itemscope` and no `itemprop`.
- **Types.** `structured_data_types` is a JSON array of the distinct types of the counted items, sorted by code point, and `[]` when there are none. A type comes from `@type`, a string or an array of strings, where an empty string or a value of another kind is skipped, and from `itemtype`, which can name several types separated by whitespace. A leading `http://schema.org/` or `https://schema.org/` is removed, so `https://schema.org/Product` is `Product`, and a type that is only that prefix, as a template without a type to fill in leaves it, is skipped.

## Values of the response and of `urls`

- **Copies of `urls`.** `content_type`, `status_code`, `response_time_ms` and `crawl_depth` repeat the URL's row, and `crawl_timestamp` repeats its `fetched_at`. They are written in the URL's own unit, so they always agree.
- **Reason phrase.** `status` is the reason phrase the server sent, such as `Nicht Gefunden`. A status line without one, such as `HTTP/1.1 429`, gets the phrase that the IANA HTTP Status Code Registry gives the code, here `Too Many Requests`, from a copy of the registry kept with the code, so it does not change with the Python that ran the Crawl. A code the registry leaves unassigned or lists as unused, such as 299 or 418, gives NULL.

## Robots directives

`meta_robots` and `x_robots_tag` hold the directives as the Page sent them, normalised and joined by the robots directives parser that the Crawl itself uses to decide what to follow. Their `_noindex` and `_nofollow` flags are that parser's verdicts, so a column never disagrees with what the Crawl did. The parser decides which tokens count, so `none` counts as both, and which `X-Robots-Tag` values name another crawler, so `otherbot: noindex` does not count.

The `X-Robots-Tag` columns are set for every Page, since every response can carry the header; the meta columns only for an analysed Page.

## Redirects

`redirect_type` says how a Page sends its visitors elsewhere, and `redirect_url` where, resolved as Link discovery resolves the target:
- **`http_refresh`**: a 2xx Page whose `Refresh` header names a URL, such as `Refresh: 0; url=/new`.
- **`meta_refresh`**: an analysed Page without one, whose first refresh `<meta>` names a URL. Only the first counts, as a browser acts on the first only, so a page that reloads itself every five minutes (`content="300"`) does not redirect even when a later `<meta>` names a URL. `meta_refresh` holds that first `<meta>`'s `content`, with or without a URL.
- A refresh that names the Page's own URL, as a live page reloads, is no redirect.
- `javascript_redirect` is filled from v1.1, by JavaScript rendering.

## Canonicals

A Page declares its canonical URL in two ways: a `<link rel="canonical" href="...">` that the HTML parser puts in `<head>`, and a `Link: <...>; rel="canonical"` response header. A `<link>` after an element that ends `<head>` for the parser, such as an `<img>` or stray text, lands in `<body>`: it is still stored as a Link but declares nothing, a common mistake that the canonical columns show.

`canonical_url` is set only when every declaration names one URL, so a Page whose HTML and header disagree has none. `canonical_relative` reads the `href` as written, after the spaces the URL parser ignores, so `/b` is relative and ` https://example.test/b` is not. An `href` that resolves to no URL makes no declaration.

## Pagination, AMP and mobile alternate

These columns hold the targets of Links that Link discovery finds, by the Link type of their `rel`:
- `rel_next_1` and `rel_prev_1`: the first `<link rel="next">` and `<link rel="prev">` (or `rel="previous"`) of the HTML; `http_rel_next_1` and `http_rel_prev_1` the same in `Link` headers.
- `amphtml_link_element`: the first `<link rel="amphtml">`.
- `mobile_alternate_link`: the first `<link rel="alternate" media="...">` without `hreflang`, such as a separate mobile site's.

## Indexability

`indexability` says whether a search engine may index the Page, and `indexability_status` gives the first reason it may not, in the order a search engine meets them:
1. `blocked_by_robots_txt`: robots.txt disallows the URL, which a Crawl fetches anyway only under `--ignore-robots`.
2. `redirected`: a 3xx response.
3. `client_error`: a 4xx response, or a status of 600 or more, such as the 999 some sites send to bots.
4. `server_error`: a 5xx response.
5. `noindex`: the robots `<meta>` or the `X-Robots-Tag` says noindex.
6. `redirected`: a meta refresh or HTTP Refresh redirect (see [Redirects](#redirects)).
7. `canonicalised`: the canonical URL is another URL.

A search engine first has to be allowed to fetch the URL, then needs a usable response, and only then reads the directives. Every 2xx can be indexed, not only 200. A self-referencing canonical keeps a Page indexable, and so do canonicals that disagree, since they leave `canonical_url` NULL.

## Links

`links` has one row for each Link that the Crawl's Link discovery found in a response, keyed by the URL of that response (`source_url_id`) and the Link's `ordinal` there, from 1: the `Link` and `Refresh` header Links first, in the order received, then the document's in document order. The target is a URL id; join `urls` on `target_url_id` for its text and whether it is Internal. See [schema.md](schema.md#table-links) for each column.

- **What Link discovery decides.** Which references are Links, their type, their target, where they were declared (`declared_in`: `head` or `body` as the parser builds them, or `http_header`), the element and attribute they came from, their `rel` tokens, and which targets the Crawl requests. Every discovered Link gets a row, whether or not the Crawl requests its target: a `nofollow` hyperlink is stored, and its target has a `urls` row. A malformed or non-http(s) reference is no Link and has no row.
- **What Page data adds.** The `anchor_text` of a hyperlink, the `alt_text` of an `<img>`, the `hreflang` and `media` of alternate Links, and the `link_position`, all read from the same parse of the Page, so the HTML is never parsed twice. These are NULL for a header Link, which has no element, except the `hreflang` of a header Link, which is its `hreflang` parameter.
- **Which responses have Links.** An analysed Page has its header Links and its document's. Any other in-Scope 2xx response, such as a PDF or a Page too large to analyse, has its header Links only, so a PDF's `Link: <...>; rel="canonical"` is stored. Other responses, such as a redirect or a 404, have no Links in `links`.
- **Link position.** `link_position` reads elements only, so a site that marks its menu with a class rather than `nav` gets `content` for it, and the `[content_area]` settings do not change it.

## Link counts

The link counts count `hyperlink` Links whose source is a Page, nofollow included, and leave out a Link to its own source, since every Page listed in a menu would otherwise count a link to itself.
- **Outlinks** are written with each analysed Page, from its own Links: `outlinks` and `external_outlinks` count its Links to Internal and to External URLs, and the `unique_` columns their distinct targets. They are NULL for a Page that is not analysed.
- **Inlinks** are derived: `inlinks` counts the Links from Pages to the Page, `unique_inlinks` their distinct sources, and `linking_pages_pct` is the share of the Crawl's Pages with status 200 that link to it, rounded half up to 2 decimals. They are NULL until the post-crawl passes have run, and then set for every Page, 0 for one that no Page links to.
- **When the passes run:** after the last URL is recorded, before the Crawl is written as `completed` or `stopped`, and again after a continue, each run replacing the last. A Crawl that fails before its passes have run once keeps the inlink columns NULL.

## Crawl Depth and Folder Depth

- **`crawl_depth`** is the Crawl Depth that the Crawl records in `urls`: the fewest followed Links from a Seed. The Crawl gets it by finishing each depth before it starts the next, so it does not depend on the order responses arrive in. The one exception: a URL that a Resource Link such as an `<img src>` reached, which turns out to be an HTML Page and answers late, may record the URLs it finds a level or two deeper. A URL skipped beyond `--max-depth` is the target of `links` rows but has no `pages` row, since it got no response.
- **`folder_depth`** counts the non-empty segments of the path of `address`: `/` is 0, `/blog/` is 1 and `/blog/post.html` is 2. The query, a trailing slash and an empty segment add none, and an escaped `/` (`%2F`) stays inside its segment.

## Cookies

A Page's cookies are the `Set-Cookie` headers of its response, one `cookies` row each. They come from the response, not the HTML, so a Page that is not analysed, such as a redirect, has its cookies too.

A header is read as RFC 6265 asks of a browser: attribute names match in any letter case, a repeated attribute takes its last value, except that a `Domain`, `Expires` or `Max-Age` whose value does not parse is ignored, and a column without a valid value is NULL instead of failing the Page.

Page data never holds a cookie's value, only its name and attributes, since a value can be a session token that lets anyone who reads the Crawl file sign in as the crawler.

## The two address forms

- **`url_encoded_address`** is what the Crawl requested, so it joins `urls.url`, such as `https://xn--bcher-kva.test/%C3%BCber%20uns`.
- **`address`** is the form people read, such as `https://bücher.test/über%20uns`. What could hide or spoof what was requested stays encoded: escaped ASCII such as `%20` and `%2F`, a byte that is no UTF-8, a punycode label that is not valid, and invisible characters such as a right-to-left override or a no-break space.
- **`url_path`** and **`url_query`** are cut from `address`, so they hold non-ASCII characters decoded, while an escaped `/` stays escaped.

`address` is unique, through the index `pages_address`, so a Page can be found by the URL a person reads: normalising an `address` gives back its `url_encoded_address`, so two URLs never share one.
