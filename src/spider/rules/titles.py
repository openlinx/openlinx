"""The titles Rules (040-add-rules, rules)."""

from spider.naming import SETTINGS_FILE_NAME
from spider.rules.model import Rule, Threshold

TITLE_MISSING = Rule(
    id="title-missing",
    category="titles",
    issue_type="issue",
    priority="high",
    applies_to="internal_pages",
    description="A Page has no title, or its first title is empty.",
    why_it_matters=(
        "The title names the page in search results and in browser tabs. Without one, "
        "search engines make up a title from the page, which rarely says what it offers."
    ),
    how_to_fix=(
        "Add one <title> element to the <head> of the page, with a few words that describe "
        "it and set it apart from the site's other pages."
    ),
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
        "what sets the page apart, is not shown."
    ),
    how_to_fix=(
        "Shorten the title to the limit, with the words that describe the page first. Raise "
        f"max_chars in {SETTINGS_FILE_NAME} if the site's titles are meant to be longer."
    ),
    thresholds=(Threshold("max_chars", 60, "characters"),),
)

RULES = (TITLE_MISSING, TITLE_TOO_LONG)
