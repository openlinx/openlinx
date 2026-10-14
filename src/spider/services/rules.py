"""The service behind `spider rules` (040-add-rules D11)."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spider.rules.model import Rule, find_rule
from spider.rules.registry import RULES
from spider.store.records import RuleRow
from spider.workspace.discovery import resolve_workspace
from spider.workspace.tables import SettingsTables

RULE_FIELDS = (
    "id",
    "category",
    "issue_type",
    "priority",
    "applies_to",
    "enabled",
    "thresholds",
    "description",
    "why_it_matters",
    "how_to_fix",
    "reproduce_sql",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class RulesRequest:
    cwd: Path
    home: Path
    workspace: Path | None


def rule_items(request: RulesRequest, tables: SettingsTables) -> list[dict[str, Any]]:
    configured = _configured(request, tables)
    return [_item(rule, configured[rule.id]) for rule in RULES]


def rule_item(request: RulesRequest, tables: SettingsTables, rule_id: str) -> dict[str, Any]:
    configured = _configured(request, tables)
    rule = find_rule(RULES, rule_id)
    return _item(rule, configured[rule.id])


def _configured(request: RulesRequest, tables: SettingsTables) -> Mapping[str, Any]:
    """The [rules.<id>] settings of the Workspace, by Rule id, with their defaults."""
    # Imported here: pydantic stays off the CLI's startup path.
    from spider.rules.settings import RulesSettings
    from spider.workspace.settings import load_settings

    workspace = resolve_workspace(cwd=request.cwd, flag=request.workspace, home=request.home)
    rules = load_settings(workspace, tables).table(RulesSettings)
    configured: Mapping[str, Any] = rules.model_dump(by_alias=True)
    return configured


def _item(rule: Rule, configured: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": rule.id,
        "category": rule.category,
        "issue_type": rule.issue_type,
        "priority": rule.priority,
        "applies_to": rule.applies_to,
        "enabled": configured["enabled"],
        "thresholds": {
            threshold.name: {
                "value": configured[threshold.name],
                "default": threshold.default,
                "unit": threshold.unit,
            }
            for threshold in rule.thresholds
        },
        "description": rule.description,
        "why_it_matters": rule.why_it_matters,
        "how_to_fix": rule.how_to_fix,
        "reproduce_sql": rule.reproduce_sql,
    }


def rule_rows(configured: Mapping[str, Mapping[str, Any]]) -> tuple[RuleRow, ...]:
    """Every Rule as a Crawl records it, from the [rules.<id>] settings dumped by Rule id."""
    return tuple(
        RuleRow(
            id=rule.id,
            category=rule.category,
            issue_type=rule.issue_type,
            priority=rule.priority,
            applies_to=rule.applies_to,
            enabled=configured[rule.id]["enabled"],
            thresholds={
                threshold.name: configured[rule.id][threshold.name] for threshold in rule.thresholds
            },
            description=rule.description,
            why_it_matters=rule.why_it_matters,
            how_to_fix=rule.how_to_fix,
            reproduce_sql=rule.reproduce_sql,
        )
        for rule in RULES
    )
