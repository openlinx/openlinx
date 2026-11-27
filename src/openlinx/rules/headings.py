"""Declare the Rules for Page headings."""

from openlinx.rules.model import NO_ROWS, Rule

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

H2_MISSING = Rule(
    id="h2-missing",
    category="headings",
    issue_type="opportunity",
    priority="low",
    applies_to="internal_pages",
    description="A Page has no <h2> heading, or its first <h2> is empty.",
    why_it_matters=(
        "Descriptive subheadings help people scan a Page and understand how its sections "
        "are organised."
    ),
    how_to_fix=(
        "Add a descriptive <h2> for the first section if the Page has sections. "
        "If its first <h2> is empty, give it a meaningful label."
    ),
    reproduce_sql=NO_ROWS,
)

RULES = (H1_MISSING, H2_MISSING)
