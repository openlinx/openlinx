"""Declare the Rules over the stored display and encoded addresses of analysed Pages."""

from openlinx.extract.unicode_scripts import NON_ASCII_UPPERCASE_GLOB_RANGES
from openlinx.rules.model import Rule, Threshold

# The display path and query keep ASCII controls percent-encoded. SQLite GLOB ranges
# compare code points without depending on the platform's SQLite build or locale.
_NON_ASCII = "'*[^' || char(1) || '-' || char(127) || ']*'"
_HEX_PAIR = "[0-9A-Fa-f][0-9A-Fa-f]"

URL_UPPERCASE = Rule(
    id="url-uppercase",
    category="urls",
    issue_type="opportunity",
    priority="low",
    applies_to="internal_pages",
    description="A Page URL's path or query contains an uppercase letter.",
    why_it_matters=(
        "Servers can treat differently cased URLs as distinct, splitting Links across "
        "multiple versions of the same Page."
    ),
    how_to_fix=(
        "Choose consistent casing for Page URLs. Update Inlinks to the preferred URLs and "
        "redirect variants that currently serve the same content."
    ),
    reproduce_sql=f"""\
SELECT page.url_id, NULL AS detail
FROM (
    SELECT pages.url_id, pages.url_path || '?' || coalesce(pages.url_query, '') AS path_query
    FROM pages
    JOIN urls ON urls.id = pages.url_id
    WHERE urls.parsed = 1
) AS page
WHERE CASE
    -- Only A-F can be uppercase letters inside a %XX escape.
    WHEN page.path_query GLOB '*[G-Z]*' THEN 1
    WHEN page.path_query GLOB ({_NON_ASCII})
         AND page.path_query GLOB '*[{NON_ASCII_UPPERCASE_GLOB_RANGES}]*' THEN 1
    WHEN page.path_query NOT GLOB '*[A-F]*' THEN 0
    WHEN instr(page.path_query, '%') = 0 THEN 1
    -- Walk between percent signs only on paths or queries with possible hex capitals.
    -- Drop two hex digits after a percent sign because they are part of an escape.
    ELSE EXISTS (
        WITH RECURSIVE chunks(text, rest) AS (
            SELECT '', page.path_query
            UNION ALL
            SELECT CASE WHEN instr(rest, '%') = 0 THEN rest
                        ELSE substr(rest, 1, instr(rest, '%') - 1) END,
                   CASE WHEN instr(rest, '%') = 0 THEN ''
                        WHEN substr(rest, instr(rest, '%') + 1, 2) GLOB '{_HEX_PAIR}'
                        THEN substr(rest, instr(rest, '%') + 3)
                        ELSE substr(rest, instr(rest, '%') + 1) END
            FROM chunks
            WHERE rest <> ''
        )
        SELECT 1 FROM chunks WHERE text GLOB '*[A-F]*'
    )
END""",  # noqa: S608 - only fixed SQL fragments
)

URL_UNDERSCORES = Rule(
    id="url-underscores",
    category="urls",
    issue_type="opportunity",
    priority="low",
    applies_to="internal_pages",
    description="A Page URL's path contains an underscore.",
    why_it_matters="Hyphens make word boundaries easier to read in Page URLs.",
    how_to_fix=(
        "For URLs you can change, use hyphens between words and redirect the old paths. "
        "Update Inlinks to use the preferred paths."
    ),
    reproduce_sql="""\
SELECT pages.url_id, NULL AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1 AND instr(pages.url_path, '_') > 0""",
)

URL_PARAMETERS = Rule(
    id="url-parameters",
    category="urls",
    issue_type="opportunity",
    priority="low",
    applies_to="internal_pages",
    description="A Page URL has a non-empty query string.",
    why_it_matters=(
        "Parameters can create multiple URLs for the same content, making it harder for search "
        "engines to find the preferred URL."
    ),
    how_to_fix=(
        "Use a parameter-free URL in Inlinks when the parameters do not change the Page. "
        "Keep parameters that are needed for features such as pagination or filtering."
    ),
    reproduce_sql="""\
SELECT pages.url_id, NULL AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1 AND pages.url_query <> ''""",
)

URL_TOO_LONG = Rule(
    id="url-too-long",
    category="urls",
    issue_type="opportunity",
    priority="low",
    applies_to="internal_pages",
    description="A Page's encoded URL exceeds max_chars characters.",
    why_it_matters="Long URLs can be hard to read, share and maintain.",
    how_to_fix=(
        "Remove redundant path segments or parameters where possible. If the URL changes, "
        "redirect the old URL and update its Inlinks."
    ),
    reproduce_sql="""\
SELECT pages.url_id, json_object('length', length(pages.url_encoded_address)) AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1 AND length(pages.url_encoded_address) > (
    SELECT json_extract(thresholds, '$.max_chars') FROM rules WHERE id = 'url-too-long'
)""",
    thresholds=(Threshold("max_chars", 115, "characters"),),
)

URL_NON_ASCII = Rule(
    id="url-non-ascii",
    category="urls",
    issue_type="opportunity",
    priority="low",
    applies_to="internal_pages",
    description="A Page URL's display path or query contains a non-ASCII character.",
    why_it_matters=(
        "Non-ASCII text can be useful to readers, but some tools display it as percent escapes."
    ),
    how_to_fix=(
        "Keep meaningful local-language URLs when they suit the audience. If compatibility "
        "requires an ASCII URL, redirect the old URL and update its Inlinks."
    ),
    reproduce_sql=f"""\
SELECT pages.url_id, NULL AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1
  AND (
      pages.url_path GLOB ({_NON_ASCII})
      OR pages.url_query GLOB ({_NON_ASCII})
  )""",  # noqa: S608 - only fixed SQL fragments
)

RULES = (URL_UPPERCASE, URL_UNDERSCORES, URL_PARAMETERS, URL_TOO_LONG, URL_NON_ASCII)
