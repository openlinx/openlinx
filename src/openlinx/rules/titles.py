"""Declare the Rules for Page titles."""

from openlinx.rules.model import Rule, Threshold

TITLE_MISSING = Rule(
    id="title-missing",
    category="titles",
    issue_type="issue",
    priority="high",
    applies_to="internal_pages",
    description="A Page has no title, or its first title is empty.",
    why_it_matters=(
        "A descriptive title helps people identify the Page in search results and browser tabs."
    ),
    how_to_fix=(
        "If the Page has no title, add a <title> element to its <head>. If the first "
        "<title> is empty, fill it in. Use words that describe the Page and set it "
        "apart from the site's other Pages."
    ),
    reproduce_sql="""\
SELECT pages.url_id, NULL AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1 AND (pages.title_count = 0 OR pages.title_1 = '')""",
)
TITLE_DUPLICATE = Rule(
    id="title-duplicate",
    category="titles",
    issue_type="warning",
    priority="medium",
    applies_to="internal_pages",
    description="Indexable Pages share the same first title.",
    why_it_matters="Distinct titles help people tell Pages apart in search results.",
    how_to_fix=(
        "Give each Page in the group a unique title that describes the content of that Page."
    ),
    reproduce_sql="""\
WITH indexable_titles AS (
    SELECT pages.url_id, pages.title_1 COLLATE BINARY AS title_1
    FROM pages
    JOIN urls ON urls.id = pages.url_id
    WHERE urls.parsed = 1 AND pages.indexability = 'indexable' AND pages.title_1 <> ''
), duplicate_titles AS (
    SELECT title_1, COUNT(*) AS page_count
    FROM indexable_titles
    GROUP BY title_1
    HAVING COUNT(*) > 1
)
SELECT indexable_titles.url_id,
       json_object('title_1', indexable_titles.title_1, 'pages', page_count) AS detail
FROM indexable_titles
JOIN duplicate_titles ON duplicate_titles.title_1 = indexable_titles.title_1""",
)
TITLE_TOO_LONG = Rule(
    id="title-too-long",
    category="titles",
    issue_type="opportunity",
    priority="medium",
    applies_to="internal_pages",
    description="A Page's first title is longer than max_chars characters.",
    why_it_matters=(
        "Search engines cut a long title short in their results, so its end, often the brand or "
        "what sets the Page apart, is not shown."
    ),
    how_to_fix="Shorten the title to the limit, with the words that describe the Page first.",
    reproduce_sql="""\
SELECT pages.url_id, json_object('length', pages.title_1_length) AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1 AND pages.title_1_length > (
    SELECT json_extract(thresholds, '$.max_chars') FROM rules WHERE id = 'title-too-long'
)""",
    thresholds=(Threshold("max_chars", 60, "characters"),),
)

RULES = (TITLE_MISSING, TITLE_DUPLICATE, TITLE_TOO_LONG)
