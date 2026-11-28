"""Declare the Rules for Page headings."""

from openlinx.rules.model import Rule, Threshold

H1_MISSING = Rule(
    id="h1-missing",
    category="headings",
    issue_type="warning",
    priority="medium",
    applies_to="internal_pages",
    description="A Page has no <h1> heading, or its first <h1> is empty.",
    why_it_matters=("A descriptive main heading helps people understand what a Page is about."),
    how_to_fix=(
        "Add a descriptive <h1> to the Page. If its first <h1> is empty, give it a meaningful "
        "label."
    ),
    reproduce_sql="""\
SELECT pages.url_id, NULL AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1 AND (pages.h1_count = 0 OR pages.h1_1 = '')""",
)

H1_DUPLICATE = Rule(
    id="h1-duplicate",
    category="headings",
    issue_type="opportunity",
    priority="low",
    applies_to="internal_pages",
    description="Indexable Pages share the same first <h1>.",
    why_it_matters="Distinct main headings help people tell related Pages apart.",
    how_to_fix="Give each Page a main heading that reflects its specific content.",
    reproduce_sql="""\
WITH duplicate_headings AS (
    SELECT pages.h1_1 COLLATE BINARY AS h1_1, COUNT(*) AS page_count
    FROM pages
    JOIN urls ON urls.id = pages.url_id
    WHERE urls.parsed = 1 AND pages.indexability = 'indexable' AND pages.h1_1 <> ''
    GROUP BY pages.h1_1 COLLATE BINARY
    HAVING COUNT(*) > 1
)
SELECT pages.url_id,
       json_object('h1_1', pages.h1_1, 'pages', duplicate_headings.page_count) AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
JOIN duplicate_headings ON duplicate_headings.h1_1 = pages.h1_1
WHERE urls.parsed = 1 AND pages.indexability = 'indexable'""",
)
H1_MULTIPLE = Rule(
    id="h1-multiple",
    category="headings",
    issue_type="warning",
    priority="low",
    applies_to="internal_pages",
    description="A Page has more than one <h1> heading.",
    why_it_matters="Several main headings can make the Page's content hierarchy harder to follow.",
    how_to_fix=(
        "Check the heading hierarchy. Use the main <h1> for the Page's topic and "
        "lower-level headings for its sections where appropriate."
    ),
    reproduce_sql="""\
SELECT pages.url_id, json_object('count', pages.h1_count) AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1 AND pages.h1_count > 1""",
)
H1_TOO_LONG = Rule(
    id="h1-too-long",
    category="headings",
    issue_type="opportunity",
    priority="low",
    applies_to="internal_pages",
    description="A Page's first <h1> is longer than max_chars characters.",
    why_it_matters="A concise main heading makes it easier to scan the Page.",
    how_to_fix="Put the main topic in the <h1> and move supporting detail into the Page text.",
    reproduce_sql="""\
SELECT pages.url_id, json_object('length', pages.h1_1_length) AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1 AND pages.h1_1_length > (
    SELECT json_extract(thresholds, '$.max_chars') FROM rules WHERE id = 'h1-too-long'
)""",
    thresholds=(Threshold("max_chars", 70, "characters"),),
)
H2_MISSING = Rule(
    id="h2-missing",
    category="headings",
    issue_type="opportunity",
    priority="low",
    applies_to="internal_pages",
    description="A Page has no <h2> heading, or its first <h2> is empty.",
    why_it_matters="Descriptive subheadings help people navigate and scan a Page's content.",
    how_to_fix=(
        "Give an empty <h2> a descriptive label. If the Page has distinct sections, "
        "use <h2> headings to identify them."
    ),
    reproduce_sql="""\
SELECT pages.url_id, NULL AS detail
FROM pages
JOIN urls ON urls.id = pages.url_id
WHERE urls.parsed = 1 AND (pages.h2_count = 0 OR pages.h2_1 = '')""",
)

RULES = (H1_MISSING, H1_DUPLICATE, H1_MULTIPLE, H1_TOO_LONG, H2_MISSING)
