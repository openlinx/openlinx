"""Declare the Rules for Page headings."""

from openlinx.rules.model import NO_ROWS, Rule

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

RULES = (H2_MISSING,)
