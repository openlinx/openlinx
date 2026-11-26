"""Project catalogue metadata for the Rules Command."""

from typing import TYPE_CHECKING, Any

from openlinx.naming import COMMAND_NAME
from openlinx.output.codes import RULE_NOT_FOUND
from openlinx.output.diagnostics import OpenLinxError

if TYPE_CHECKING:
    from openlinx.rules.model import Rule


def rule_items() -> list[dict[str, Any]]:
    from openlinx.rules.registry import RULES

    return [_item(rule) for rule in RULES]


def rule_item(rule_id: str) -> dict[str, Any]:
    from openlinx.rules.registry import RULES

    rule = next((candidate for candidate in RULES if candidate.id == rule_id), None)
    if rule is None:
        raise OpenLinxError(
            RULE_NOT_FOUND,
            f"No Rule has the id {rule_id}.",
            hint=f"Use {COMMAND_NAME} rules list to see the available Rule ids.",
            details={"id": rule_id},
        )
    return _item(rule)


def _item(rule: "Rule") -> dict[str, Any]:
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
