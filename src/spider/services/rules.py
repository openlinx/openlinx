"""The service behind `spider rules` (040-add-rules, rules)."""

from typing import Any

from spider.rules.model import Rule
from spider.rules.registry import RULES

_BY_ID = {rule.id: rule for rule in RULES}


def rule_items() -> list[dict[str, Any]]:
    return [_item(rule) for rule in RULES]


def rule_item(rule_id: str) -> dict[str, Any]:
    return _item(_BY_ID[rule_id])


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
