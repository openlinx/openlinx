"""Project catalogue metadata for the Rules Command."""


def rule_items() -> list[dict[str, str]]:
    from openlinx.rules.registry import RULES

    return [
        {
            "id": rule.id,
            "category": rule.category,
            "issue_type": rule.issue_type,
            "priority": rule.priority,
            "applies_to": rule.applies_to,
            "description": rule.description,
            "why_it_matters": rule.why_it_matters,
            "how_to_fix": rule.how_to_fix,
        }
        for rule in RULES
    ]
