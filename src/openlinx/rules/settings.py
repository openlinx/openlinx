"""Build the settings with one subtable per registered Rule."""

from collections.abc import Iterator
from typing import Annotated, Any, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    ValidationError,
    create_model,
    model_validator,
)
from pydantic_core import InitErrorDetails, PydanticCustomError

from openlinx.rules.model import Rule
from openlinx.rules.registry import RULES
from openlinx.workspace.settings import NonNegativeDecimalDigits
from openlinx.workspace.toml_order import format_toml_key

_PREVIEW_RULE_IDS = frozenset({"h2-missing", "low-word-count", "url-parameters"})

ThresholdValue = Annotated[
    int, Field(strict=True, ge=0), AfterValidator(NonNegativeDecimalDigits(4300))
]


def _rule_table(rule: Rule) -> type[BaseModel]:
    fields: dict[str, Any] = {
        threshold.name: (
            ThresholdValue,
            Field(
                threshold.default,
                description=f"The limit, in {threshold.unit}.",
            ),
        )
        for threshold in rule.thresholds
    }
    fields["enabled"] = (bool, Field(True, strict=True, description="Set to false to disable."))
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


def _preview_errors(path: tuple[str, ...], value: object) -> Iterator[InitErrorDetails]:
    # Dotted TOML declarations can produce a valid tree deeper than Python's call stack.
    pending = [(path, value)]
    while pending:
        location, entry = pending.pop()
        if isinstance(entry, dict) and entry:
            pending.extend(((*location, key), child) for key, child in reversed(entry.items()))
            continue
        yield {
            "type": PydanticCustomError(
                "preview_rule_setting",
                "Remove {toml_key} from the settings file. This Rule is deferred to v0.2.",
                {"toml_key": format_toml_key(("rules", *location))},
            ),
            "loc": location,
            "input": entry,
        }


class _RulesSettings(BaseModel):
    # Keep the Rule ids in the recorded Crawl config as well as in the settings file.
    model_config = ConfigDict(extra="forbid", serialize_by_alias=True)

    @model_validator(mode="wrap")
    @classmethod
    def _validate_preview_tables(
        cls, value: Any, validate: ModelWrapValidatorHandler[Self]
    ) -> Self:
        if not isinstance(value, dict) or _PREVIEW_RULE_IDS.isdisjoint(value):
            return validate(value)

        active = {key: entry for key, entry in value.items() if key not in _PREVIEW_RULE_IDS}
        # Preview init emitted real table headers with only commented-out settings.
        problems = [
            problem
            for key, entry in value.items()
            if key in _PREVIEW_RULE_IDS and entry != {}
            for problem in _preview_errors((key,), entry)
        ]
        if not problems:
            return validate(active)

        try:
            validate(active)
        except ValidationError as error:
            # Combine both sets in one error so Workspace diagnostics keep TOML declaration order.
            problems.extend(
                {
                    "type": PydanticCustomError(
                        problem["type"], problem["msg"], problem.get("ctx")
                    ),
                    "loc": problem["loc"],
                    "input": problem["input"],
                }
                for problem in error.errors()
            )
        raise ValidationError.from_exception_data(cls.__name__, problems)


RulesSettings: type[BaseModel] = create_model(
    "RulesSettings",
    __base__=_RulesSettings,
    __doc__="Thresholds and enabled state by Rule id, for example [rules.title-too-long].",
    **_tables(),
)
