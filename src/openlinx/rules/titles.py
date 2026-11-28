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

TITLE_TOO_SHORT = Rule(
    id="title-too-short",
    category="titles",
    issue_type="opportunity",
    priority="low",
    applies_to="internal_pages",
    description="A Page's first title is non-empty and shorter than min_chars characters.",
    why_it_matters="A short title can leave out details that set the Page apart in search results.",
    how_to_fix="Add specific words that explain what the Page offers, up to a readable length.",
    reproduce_sql="""\
SELECT pages.url_id, json_object('length', pages.title_1_length) AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1 AND pages.title_1_length >= 1 AND pages.title_1_length < (
    SELECT json_extract(thresholds, '$.min_chars') FROM rules WHERE id = 'title-too-short'
)""",
    thresholds=(Threshold("min_chars", 30, "characters"),),
)
TITLE_MULTIPLE = Rule(
    id="title-multiple",
    category="titles",
    issue_type="issue",
    priority="medium",
    applies_to="internal_pages",
    description="A Page has more than one <title> element.",
    why_it_matters="Multiple titles send conflicting signals about how to label the Page.",
    how_to_fix=(
        "Keep one descriptive <title> in <head> and remove the others. "
        "Check the Page template for duplicate title markup."
    ),
    reproduce_sql="""\
SELECT pages.url_id, json_object('count', pages.title_count) AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1 AND pages.title_count > 1""",
)
TITLE_SAME_AS_H1 = Rule(
    id="title-same-as-h1",
    category="titles",
    issue_type="opportunity",
    priority="low",
    applies_to="internal_pages",
    description="A Page's first title repeats the text of its first <h1>.",
    why_it_matters=(
        "A title can give people context in search results, while the main heading "
        "introduces the content once they arrive."
    ),
    how_to_fix=(
        "If useful, add distinguishing context to the title and keep the <h1> "
        "focused on the Page's main topic."
    ),
    reproduce_sql="""\
SELECT pages.url_id, NULL AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1 AND pages.title_1 <> '' AND pages.title_1 COLLATE BINARY = pages.h1_1""",
)

RULES = (
    TITLE_MISSING,
    TITLE_DUPLICATE,
    TITLE_TOO_LONG,
    TITLE_TOO_SHORT,
    TITLE_MULTIPLE,
    TITLE_SAME_AS_H1,
)
