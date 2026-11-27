"""Declare the Rules for Page meta descriptions."""

from openlinx.rules.model import Rule

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

RULES = (META_DESCRIPTION_MISSING,)
