"""Declare the Rules for Page titles."""

from openlinx.rules.model import NO_ROWS, Rule, Threshold

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
WHERE urls.parsed = 1 AND pages.title_count = 0""",
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
    reproduce_sql=NO_ROWS,
    thresholds=(Threshold("max_chars", 60, "characters"),),
)

RULES = (TITLE_MISSING, TITLE_TOO_LONG)
