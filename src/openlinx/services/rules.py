"""Project catalogue metadata for the Rules Command."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openlinx.naming import COMMAND_NAME
from openlinx.output.codes import RULE_NOT_FOUND
from openlinx.output.diagnostics import OpenLinxError
from openlinx.workspace.discovery import resolve_workspace
from openlinx.workspace.tables import SettingsTables

if TYPE_CHECKING:
    from openlinx.rules.model import Rule


@dataclass(frozen=True, slots=True, kw_only=True)
class RulesRequest:
    cwd: Path
    home: Path
    workspace: Path | None


def rule_items(request: RulesRequest, tables: SettingsTables) -> tuple[Path, list[dict[str, Any]]]:
    """Return the Workspace settings path and its Rules in catalogue order."""
    from openlinx.rules.registry import RULES

    settings_file, configured = _configured(request, tables)
    return settings_file, [_item(rule, configured[rule.id]) for rule in RULES]


def rule_item(request: RulesRequest, tables: SettingsTables, rule_id: str) -> dict[str, Any]:
    from openlinx.rules.registry import RULES

    _, configured = _configured(request, tables)
    rule = next((candidate for candidate in RULES if candidate.id == rule_id), None)
    if rule is None:
        raise OpenLinxError(
            RULE_NOT_FOUND,
            f"No Rule has the id {rule_id}.",
            hint=f"Use {COMMAND_NAME} rules list to see the available Rule ids.",
            details={"id": rule_id},
        )
    return _item(rule, configured[rule.id])


def _configured(request: RulesRequest, tables: SettingsTables) -> tuple[Path, Mapping[str, Any]]:
    from openlinx.rules.settings import RulesSettings
    from openlinx.workspace.settings import load_settings

    workspace = resolve_workspace(cwd=request.cwd, flag=request.workspace, home=request.home)
    settings = load_settings(workspace, tables).table(RulesSettings)
    return workspace.settings_file, settings.model_dump()


def _item(rule: "Rule", configured: Mapping[str, Any]) -> dict[str, Any]:
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
    }
