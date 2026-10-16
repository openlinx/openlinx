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

_TITLE_DUPLICATE_SQL = """SELECT url_id, json_object('title_1', title_1, 'pages', pages) AS detail
FROM (
  -- = and PARTITION BY compare the titles case-sensitively.
  SELECT url_id, title_1, count(*) OVER (PARTITION BY title_1) AS pages
  FROM pages JOIN indexable_pages USING (url_id)
  -- An empty title is title-missing's.
  WHERE title_1 <> ''
)
WHERE pages > 1"""

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
TITLE_DUPLICATE = Rule(
    id="title-duplicate",
    category="titles",
    issue_type="warning",
    priority="medium",
    population="indexable_pages",
    description="A Page's first title is also the first title of another Indexable Page.",
    why_it_matters=(
        "Search engines cannot tell the pages apart by their titles, and may show one of "
        "them for searches meant for the other."
    ),
    how_to_fix=(
        "Give each page a title that says what sets it apart. If the pages are the same, "
        "point one at the other with a canonical link, or redirect it."
    ),
    reproduce_sql=_TITLE_DUPLICATE_SQL,
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

RULES = (TITLE_MISSING, TITLE_DUPLICATE, TITLE_TOO_LONG)
