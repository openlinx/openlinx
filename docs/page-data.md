# Page data

What a Crawl stores about each Page: the flat Page record in `pages`, one row per Page, read without joins. The spec is [openspec/changes/030-add-page-data/specs/page-data/spec.md](../openspec/changes/030-add-page-data/specs/page-data/spec.md), and each column's one definition is its description in [schema.md](schema.md#table-pages); this page explains what several columns share. Terms follow [CONTEXT.md](../CONTEXT.md).

## What a Page is

A Page is a URL of the Crawl that returned an HTML document. In the `urls` table, it is a row with all of:
- `is_internal` = 1 and `in_scope` = 1: an Internal URL in the Scope. An External URL is checked, never a Page.
- `fetch_state` = `fetched`: a response was recorded. A URL that was skipped, such as one that robots.txt disallows, or that got no response, is not a Page.
- a `content_type` whose media type is `text/html` or `application/xhtml+xml`, in any letter case, with its parameters ignored. An image, a PDF or a response without a `Content-Type` is not a Page.

The status code does not matter: a 404 or a 301 with an HTML body is a Page too.

Every Page has exactly one `pages` row, keyed by `url_id`, which is `urls.id`. It is written in the same transaction as the URL's response, so a reader never sees one without the other. Every other URL has none.

## Analysed and non-analysed Pages

A Page is *analysed* when the Crawl parsed it (`urls.parsed` = 1): its status is 2xx and its body was read in full. Only an analysed Page has values in the columns that come from its HTML, such as its titles and headings. A Page that is not analysed, such as a 404 or a redirect, has NULL in them; the columns that come from the URL and its response are set for every Page. When the Page extractor fails on an analysed Page (`urls.parse_error` = `extractor_error`), only the columns it derives from the HTML are NULL.

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

## Values of the response and of `urls`

- **Copies of `urls`.** `content_type`, `status_code`, `response_time_ms` and `crawl_depth` repeat the URL's row, and `crawl_timestamp` repeats its `fetched_at`. They are written in the URL's own unit, so they always agree.

## Cookies

A Page's cookies are the `Set-Cookie` headers of its response, one `cookies` row each. They come from the response, not the HTML, so a Page that is not analysed, such as a redirect, has its cookies too.

A header is read as RFC 6265 asks of a browser: attribute names match in any letter case, a repeated attribute takes its last value, except that a `Domain`, `Expires` or `Max-Age` whose value does not parse is ignored, and a column without a valid value is NULL instead of failing the Page.

Page data never holds a cookie's value, only its name and attributes, since a value can be a session token that lets anyone who reads the Crawl file sign in as the crawler.

## The two address forms

- **`url_encoded_address`** is what the Crawl requested, so it joins `urls.url`, such as `https://xn--bcher-kva.test/%C3%BCber%20uns`.
- **`address`** is the form people read, such as `https://bücher.test/über%20uns`. What could hide or spoof what was requested stays encoded: escaped ASCII such as `%20` and `%2F`, a byte that is no UTF-8, a punycode label that is not valid, and invisible characters such as a right-to-left override or a no-break space.
- **`url_path`** and **`url_query`** are cut from `address`, so they hold non-ASCII characters decoded, while an escaped `/` stays escaped.

`address` is unique, through the index `pages_address`, so a Page can be found by the URL a person reads: normalising an `address` gives back its `url_encoded_address`, so two URLs never share one.
