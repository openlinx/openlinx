"""Declare the Rules for Page content."""

from openlinx.rules.model import NO_ROWS, Rule, Threshold

LOW_WORD_COUNT = Rule(
    id="low-word-count",
    category="content",
    issue_type="opportunity",
    priority="medium",
    applies_to="internal_pages",
    description="An Indexable Page has fewer words than the min_words threshold.",
    why_it_matters="A short Page may omit information visitors came to find.",
    how_to_fix=(
        "Add information that answers the questions visitors bring to this Page. "
        "Keep the Page concise when it already answers them."
    ),
    reproduce_sql=NO_ROWS,
    thresholds=(Threshold("min_words", 200, "words"),),
)

RULES = (LOW_WORD_COUNT,)
