"""The headings Rules (040-add-rules D3, D4)."""

from spider.rules.model import NO_ROWS, Rule

H1_MISSING = Rule(
    id="h1-missing",
    category="headings",
    issue_type="warning",
    priority="medium",
    applies_to="internal_pages",
    description="A Page has no h1 heading, or its first h1 is empty.",
    why_it_matters=(
        "The h1 tells visitors and search engines what the page is about. Without one, the "
        "page's main topic is less clear to both."
    ),
    how_to_fix=(
        "Give the page one <h1> element that names its main topic, near the top of its content."
    ),
    reproduce_sql=NO_ROWS,
)

RULES = (H1_MISSING,)
