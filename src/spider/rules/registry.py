"""The catalogue: every Rule, in catalogue order (040-add-rules D4)."""

from spider.rules import headings, meta_descriptions, response_codes, titles
from spider.rules.model import Rule

# By category in the Rule model's order, then in the order of the category's table in the spec.
RULES: tuple[Rule, ...] = (
    *response_codes.RULES,
    *titles.RULES,
    *meta_descriptions.RULES,
    *headings.RULES,
)
