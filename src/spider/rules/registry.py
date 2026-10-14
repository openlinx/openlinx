"""The catalogue: every Rule, in catalogue order (040-add-rules, rules)."""

from spider.rules import response_codes
from spider.rules.model import Rule

# By category in the Rule model's order, then in the order of the category's table in the spec.
RULES: tuple[Rule, ...] = (*response_codes.RULES,)
