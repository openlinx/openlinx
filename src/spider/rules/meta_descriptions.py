"""The meta description Rules (040-add-rules D3, D4)."""

from spider.rules.model import Rule

_META_DESCRIPTION_MISSING_SQL = """SELECT url_id, NULL AS detail
FROM pages JOIN analysed_pages USING (url_id)
WHERE meta_description_count = 0 OR meta_description_1 = ''"""

META_DESCRIPTION_MISSING = Rule(
    id="meta-description-missing",
    category="meta_descriptions",
    issue_type="opportunity",
    priority="medium",
    population="analysed_pages",
    description="A Page has no meta description, or its first meta description is empty.",
    why_it_matters=(
        "Search engines often show the meta description under the title in their results. "
        "Without one, they pick a snippet from the page, which may not say why to visit it."
    ),
    how_to_fix=(
        'Add one <meta name="description" content="..."> to the <head> of the page, with a '
        "sentence or two that says what the page offers."
    ),
    reproduce_sql=_META_DESCRIPTION_MISSING_SQL,
)

RULES = (META_DESCRIPTION_MISSING,)
