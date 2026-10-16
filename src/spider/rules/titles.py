"""The titles Rules (040-add-rules D3, D4)."""

from spider.naming import SETTINGS_FILE_NAME
from spider.rules.model import Rule, Threshold

_TITLE_MISSING_SQL = """SELECT url_id, NULL AS detail
FROM pages JOIN analysed_pages USING (url_id)
WHERE title_count = 0 OR title_1 = ''"""

# The limit is read from the Crawl's rules row, so the query runs on its own (D15).
_TITLE_TOO_LONG_SQL = """SELECT url_id, json_object('length', title_1_length) AS detail
FROM pages JOIN analysed_pages USING (url_id)
WHERE title_1_length > json_extract(
  (SELECT thresholds FROM rules WHERE id = 'title-too-long'), '$.max_chars'
)"""

TITLE_MISSING = Rule(
    id="title-missing",
    category="titles",
    issue_type="issue",
    priority="high",
    population="analysed_pages",
    description="A Page has no title, or its first title is empty.",
    why_it_matters=(
        "The title names the page in search results and in browser tabs. Without one, "
        "search engines make up a title from the page, which may not say what it offers."
    ),
    how_to_fix=(
        "Add one <title> element to the <head> of the page, with a few words that describe "
        "it and set it apart from the site's other pages."
    ),
    reproduce_sql=_TITLE_MISSING_SQL,
)
TITLE_TOO_LONG = Rule(
    id="title-too-long",
    category="titles",
    issue_type="opportunity",
    priority="medium",
    population="analysed_pages",
    description="A Page's first title is longer than max_chars characters.",
    why_it_matters=(
        "Search engines cut a long title short in their results, so its end, often the brand or "
        "what sets the page apart, is not shown."
    ),
    how_to_fix=(
        "Shorten the title to the limit, with the words that describe the page first. Raise "
        f"max_chars in {SETTINGS_FILE_NAME} if the site's titles are meant to be longer."
    ),
    thresholds=(Threshold("max_chars", 60, "characters"),),
    reproduce_sql=_TITLE_TOO_LONG_SQL,
)

RULES = (TITLE_MISSING, TITLE_TOO_LONG)
