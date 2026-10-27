"""The service behind `spider rules` (040-add-rules D11)."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spider.rules.model import ConfiguredRule, find_rule
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
    return [_item(configured) for configured in _configured(request, tables)]


def rule_item(request: RulesRequest, tables: SettingsTables, rule_id: str) -> dict[str, Any]:
    configured = _configured(request, tables)
    rule = find_rule(RULES, rule_id)
    return _item(next(found for found in configured if found.rule is rule))


def _configured(request: RulesRequest, tables: SettingsTables) -> tuple[ConfiguredRule, ...]:
    """Every Rule with the [rules.<id>] settings of the Workspace, defaults filled in."""
    # Imported here: pydantic stays off the CLI's startup path.
    from spider.rules.settings import RulesSettings, configured_rules
    from spider.workspace.settings import load_settings

    workspace = resolve_workspace(cwd=request.cwd, flag=request.workspace, home=request.home)
    return configured_rules(load_settings(workspace, tables).table(RulesSettings))


def _item(configured: ConfiguredRule) -> dict[str, Any]:
    rule = configured.rule
    return {
        "id": rule.id,
        "category": rule.category,
        "issue_type": rule.issue_type,
        "priority": rule.priority,
        "applies_to": rule.applies_to,
        "enabled": configured.enabled,
        "thresholds": {
            threshold.name: {
                "value": configured.thresholds[threshold.name],
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


def rule_rows(configured: Sequence[ConfiguredRule]) -> tuple[RuleRow, ...]:
    """Every Rule as a Crawl records it, with its settings."""
    return tuple(
        RuleRow(
            id=found.rule.id,
            category=found.rule.category,
            issue_type=found.rule.issue_type,
            priority=found.rule.priority,
            applies_to=found.rule.applies_to,
            enabled=found.enabled,
            thresholds=found.thresholds,
            description=found.rule.description,
            why_it_matters=found.rule.why_it_matters,
            how_to_fix=found.rule.how_to_fix,
            reproduce_sql=found.rule.reproduce_sql,
        )
        for found in configured
    )
