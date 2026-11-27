"""Declare the Rules for Page URLs."""

from openlinx.rules.model import NO_ROWS, Rule

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
        "Use a parameter-free URL in internal Links when the parameters do not change the Page. "
        "Keep parameters that are needed for features such as pagination or filtering."
    ),
    reproduce_sql=NO_ROWS,
)

RULES = (URL_PARAMETERS,)
