"""The [rules.<id>] settings: one table per Rule, named by its id (040-add-rules D9)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model

from spider.rules.model import Rule
from spider.rules.registry import RULES


def _rule_table(rule: Rule) -> type[BaseModel]:
    fields: dict[str, Any] = {
        "enabled": (bool, Field(True, description="false leaves the Rule out of every Crawl.")),
    }
    for threshold in rule.thresholds:
        fields[threshold.name] = (
            int,
            Field(threshold.default, ge=0, description=f"The limit, in {threshold.unit}."),
        )
    name = "".join(word.title() for word in rule.id.split("-")) + "Settings"
    return create_model(name, __config__=ConfigDict(extra="forbid"), **fields)


def _tables() -> dict[str, Any]:
    # Rule ids hold "-", so each field is aliased by its Rule id, as the settings file names it.
    tables: dict[str, Any] = {}
    for rule in RULES:
        table = _rule_table(rule)
        tables[rule.id.replace("-", "_")] = (
            table,
            Field(default_factory=table, alias=rule.id, description=rule.description),
        )
    return tables


RulesSettings = create_model(
    "RulesSettings",
    # A Crawl's recorded config names them by Rule id too.
    __config__=ConfigDict(extra="forbid", serialize_by_alias=True),
    __doc__="A Rule's thresholds and whether it runs, in a table named by its id, such as "
    "[rules.title-too-long].",
    **_tables(),
)
