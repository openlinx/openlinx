"""The service behind `spider rules` (040-add-rules D11)."""

from typing import Any

from spider.naming import APP_NAME
from spider.output.codes import RULE_NOT_FOUND
from spider.output.diagnostics import SpiderError
from spider.rules.model import Rule
from spider.rules.registry import RULES

_BY_ID = {rule.id: rule for rule in RULES}
# The fields of an item, in the order _item gives them.
RULE_FIELDS = (
    "id",
    "category",
    "issue_type",
    "priority",
    "applies_to",
    "thresholds",
    "description",
    "why_it_matters",
    "how_to_fix",
)


def rule_items() -> list[dict[str, Any]]:
    return [_item(rule) for rule in RULES]


def rule_item(rule_id: str) -> dict[str, Any]:
    rule = _BY_ID.get(rule_id)
    if rule is None:
        raise SpiderError(
            RULE_NOT_FOUND,
            f"No Rule has the id {rule_id}.",
            hint=f"{APP_NAME} rules list lists every Rule id.",
            details={"id": rule_id},
        )
    return _item(rule)


def _item(rule: Rule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "category": rule.category,
        "issue_type": rule.issue_type,
        "priority": rule.priority,
        "applies_to": rule.applies_to,
        "thresholds": {
            threshold.name: {
                "value": threshold.default,
                "default": threshold.default,
                "unit": threshold.unit,
            }
            for threshold in rule.thresholds
        },
        "description": rule.description,
        "why_it_matters": rule.why_it_matters,
        "how_to_fix": rule.how_to_fix,
    }
