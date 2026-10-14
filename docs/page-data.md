# Page data

What a Crawl stores about each Page: the flat Page record in `pages`, one row per Page, read without joins. The spec is [openspec/changes/030-add-page-data/specs/page-data/spec.md](../openspec/changes/030-add-page-data/specs/page-data/spec.md), and the columns are listed in [schema.md](schema.md#table-pages). Terms follow [CONTEXT.md](../CONTEXT.md).

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

Every text column is whitespace-normalised: each run of ASCII whitespace (tab, line feed, form feed, carriage return and space) becomes one space, and ASCII whitespace at either end is removed. A no-break space is text, so it is kept. A length is counted in Unicode code points of the normalised text.

## Titles

- **`title_count`** is the number of `<title>` elements without an `svg` or `math` ancestor: a title inside an SVG image or a MathML formula names the image or the formula, not the Page. It is 0 when the Page has none.
- **`title_1`** and **`title_2`** are the normalised texts of the first and second of them, in document order. Each is NULL when there is no such element, and the empty string for `<title></title>`.
- **`title_1_length`** and **`title_2_length`** are their lengths, NULL exactly when their text is.

## The two address forms

- **`url_encoded_address`** is the URL as the Crawl requested it, equal to `urls.url`: the host in IDNA (punycode) form and every non-ASCII character percent-encoded as UTF-8, such as `https://xn--bcher-kva.test/%C3%BCber%20uns`.
- **`address`** is the same URL for people: the host in Unicode, and every percent-encoded UTF-8 sequence of a non-ASCII character decoded, such as `https://bücher.test/über%20uns`. Percent-encoded ASCII characters, such as `%20` and `%2F`, stay encoded, and so does what does not decode: a byte that is no UTF-8, or a punycode label that is not valid. Controls, format characters such as a right-to-left override, and spaces and separators such as the no-break space stay encoded too (Unicode categories `Cc`, `Cf`, `Zs`, `Zl` and `Zp`), so an address never hides or spoofs what was requested.

`address` is unique, through the index `pages_address`, so a Page can be found by the URL a person reads: normalising an `address` gives back its `url_encoded_address`, so two URLs never share one.
