"""Build the threshold settings with one subtable per registered Rule."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model

from openlinx.rules.model import Rule
from openlinx.rules.registry import RULES


def _rule_table(rule: Rule) -> type[BaseModel]:
    fields: dict[str, Any] = {
        threshold.name: (
            int,
            Field(
                threshold.default,
                strict=True,
                ge=0,
                description=f"The limit, in {threshold.unit}.",
            ),
        )
        for threshold in rule.thresholds
    }
    name = "".join(word.title() for word in rule.id.split("-")) + "Settings"
    return create_model(name, __config__=ConfigDict(extra="forbid"), **fields)


def _tables() -> dict[str, Any]:
    tables: dict[str, Any] = {}
    for rule in RULES:
        table = _rule_table(rule)
        tables[rule.id.replace("-", "_")] = (
            table,
            Field(default_factory=table, alias=rule.id, description=rule.description),
        )
    return tables


RulesSettings: type[BaseModel] = create_model(
    "RulesSettings",
    # Keep the Rule ids in the recorded Crawl config as well as in the settings file.
    __config__=ConfigDict(extra="forbid", serialize_by_alias=True),
    __doc__="Thresholds by Rule id, for example [rules.title-too-long].",
    **_tables(),
)
