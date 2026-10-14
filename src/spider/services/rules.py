"""The service behind `spider rules` (040-add-rules D11)."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spider.naming import APP_NAME
from spider.output.codes import RULE_NOT_FOUND
from spider.output.diagnostics import SpiderError
from spider.rules.model import Rule
from spider.rules.registry import RULES
from spider.workspace.discovery import resolve_workspace
from spider.workspace.tables import SettingsTables

_BY_ID = {rule.id: rule for rule in RULES}
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
    rule = _BY_ID.get(rule_id)
    if rule is None:
        raise SpiderError(
            RULE_NOT_FOUND,
            f"No Rule has the id {rule_id}.",
            hint=f"{APP_NAME} rules list lists every Rule id.",
            details={"id": rule_id},
        )
    return _item(rule, configured[rule.id])


def _configured(request: RulesRequest, tables: SettingsTables) -> Mapping[str, Any]:
    """The [rules.<id>] settings of the Workspace, by Rule id, with their defaults."""
    # Imported here: pydantic stays off the CLI's startup path.
    from spider.workspace.settings import load_settings

    workspace = resolve_workspace(cwd=request.cwd, flag=request.workspace, home=request.home)
    configured: Mapping[str, Any] = load_settings(workspace, tables).root.model_dump()["rules"]
    return configured


def _item(rule: Rule, configured: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": rule.id,
        "category": rule.category,
        "issue_type": rule.issue_type,
        "priority": rule.priority,
        "applies_to": rule.applies_to,
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
    }
