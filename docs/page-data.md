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

A Page is *analysed* when the Crawl parsed it (`urls.parsed` = 1): its status is 2xx and its body was read in full. Only an analysed Page has values in the columns that come from its HTML, such as its titles and headings. A Page that is not analysed, such as a 404 or a redirect, has NULL in them; the columns that come from the URL and its response are set for every Page.

## NULL, empty and zero

The columns follow the conventions of [schema.md](schema.md#conventions):
- NULL means not measured, or not applicable: an HTML column of a Page that is not analysed, an element the HTML does not have, or a column that a later release fills.
- The empty string is an element that is present but empty, such as `<title></title>`.
- 0 is a measured zero: a count of an analysed Page is 0 or more, never NULL.

## The two address forms

- **`url_encoded_address`** is the URL as the Crawl requested it, equal to `urls.url`: the host in IDNA (punycode) form and every non-ASCII character percent-encoded as UTF-8, such as `https://xn--bcher-kva.test/%C3%BCber%20uns`.
- **`address`** is the same URL for people: the host in Unicode, and every percent-encoded UTF-8 sequence of a non-ASCII character decoded, such as `https://bücher.test/über%20uns`. Percent-encoded ASCII characters, such as `%20` and `%2F`, stay encoded, and so does what does not decode: a byte that is no UTF-8, or a punycode label that is not valid.

`address` is unique, through the index `pages_address`, so a Page can be found by the URL a person reads.
