"""Declare the Rules for Page meta descriptions."""

from openlinx.rules.model import Rule, Threshold

META_DESCRIPTION_MISSING = Rule(
    id="meta-description-missing",
    category="meta_descriptions",
    issue_type="opportunity",
    priority="medium",
    applies_to="internal_pages",
    description="A Page has no meta description, or its first meta description is empty.",
    why_it_matters=(
        "A descriptive summary gives search engines text they can use as a search result snippet."
    ),
    how_to_fix=(
        'Add a <meta name="description"> element to <head> if it is missing. '
        "Fill the first description's content attribute with a concise summary of the Page."
    ),
    reproduce_sql="""\
SELECT pages.url_id, NULL AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1
  AND (pages.meta_description_count = 0 OR pages.meta_description_1 = '')""",
)

META_DESCRIPTION_DUPLICATE = Rule(
    id="meta-description-duplicate",
    category="meta_descriptions",
    issue_type="opportunity",
    priority="low",
    applies_to="internal_pages",
    description="Indexable Pages share the same first meta description.",
    why_it_matters="Repeated summaries make Pages harder to tell apart in search results.",
    how_to_fix="Write a distinct summary for each Page based on its specific content.",
    reproduce_sql="""\
WITH duplicate_descriptions AS (
    SELECT pages.meta_description_1 COLLATE BINARY AS meta_description_1, COUNT(*) AS page_count
    FROM pages
    JOIN urls ON urls.id = pages.url_id
    WHERE urls.parsed = 1 AND pages.indexability = 'indexable' AND pages.meta_description_1 <> ''
    GROUP BY pages.meta_description_1 COLLATE BINARY
    HAVING COUNT(*) > 1
)
SELECT pages.url_id,
       json_object('meta_description_1', pages.meta_description_1,
                   'pages', duplicate_descriptions.page_count) AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
JOIN duplicate_descriptions ON duplicate_descriptions.meta_description_1 = pages.meta_description_1
WHERE urls.parsed = 1 AND pages.indexability = 'indexable'""",
)
META_DESCRIPTION_TOO_LONG = Rule(
    id="meta-description-too-long",
    category="meta_descriptions",
    issue_type="opportunity",
    priority="low",
    applies_to="internal_pages",
    description="A Page's first meta description exceeds max_chars or max_pixels.",
    why_it_matters="Search results may cut off a long summary before its most useful information.",
    how_to_fix="Shorten the summary and put the most useful information first.",
    reproduce_sql="""\
WITH limits AS (
    SELECT json_extract(thresholds, '$.max_chars') AS max_chars,
           json_extract(thresholds, '$.max_pixels') AS max_pixels
    FROM rules
    WHERE id = 'meta-description-too-long'
)
SELECT pages.url_id, json_object('length', pages.meta_description_1_length,
                                 'width_px', pages.meta_description_1_width_px) AS detail
FROM limits
CROSS JOIN pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1
  -- An unmeasured width cannot exceed its limit, but the character count still can.
  AND (pages.meta_description_1_length > limits.max_chars
       OR pages.meta_description_1_width_px > limits.max_pixels)""",
    thresholds=(Threshold("max_chars", 155, "characters"), Threshold("max_pixels", 985, "pixels")),
)
META_DESCRIPTION_TOO_SHORT = Rule(
    id="meta-description-too-short",
    category="meta_descriptions",
    issue_type="opportunity",
    priority="low",
    applies_to="internal_pages",
    description="A Page's first meta description is non-empty and shorter than min_chars.",
    why_it_matters="A short summary can omit details that help people choose a search result.",
    how_to_fix="Add useful, Page-specific details to make the summary more informative.",
    reproduce_sql="""\
SELECT pages.url_id, json_object('length', pages.meta_description_1_length) AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1 AND pages.meta_description_1_length >= 1
  AND pages.meta_description_1_length < (
    SELECT json_extract(thresholds, '$.min_chars')
    FROM rules WHERE id = 'meta-description-too-short'
)""",
    thresholds=(Threshold("min_chars", 70, "characters"),),
)
META_DESCRIPTION_MULTIPLE = Rule(
    id="meta-description-multiple",
    category="meta_descriptions",
    issue_type="warning",
    priority="low",
    applies_to="internal_pages",
    description="A Page has more than one meta description.",
    why_it_matters="Several descriptions compete to supply the Page's summary in search results.",
    how_to_fix=(
        'Keep one <meta name="description"> element in <head>. '
        "Check the Page template for duplicate description markup."
    ),
    reproduce_sql="""\
SELECT pages.url_id, json_object('count', pages.meta_description_count) AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1 AND pages.meta_description_count > 1""",
)

RULES = (
    META_DESCRIPTION_MISSING,
    META_DESCRIPTION_DUPLICATE,
    META_DESCRIPTION_TOO_LONG,
    META_DESCRIPTION_TOO_SHORT,
    META_DESCRIPTION_MULTIPLE,
)
