"""The registry of spider.toml tables (design D2 of 010-add-workspace-and-cli-contract)."""

import math
from collections.abc import ItemsView
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Only for typing: pydantic must stay off the CLI's startup path.
    from pydantic import BaseModel


class SettingsTables:
    def __init__(self) -> None:
        self._models: dict[str, type[BaseModel]] = {}

    def register(self, name: str, model: "type[BaseModel]") -> None:
        # The template and the error hints rely on flat tables whose keys all have a
        # one-line description and a default that is a TOML literal.
        if model.model_config.get("extra") != "forbid":
            raise TypeError(f'Settings table [{name}] must set extra="forbid".')
        for key, field in model.model_fields.items():
            if not field.description or "\n" in field.description:
                raise TypeError(f"Setting {name}.{key} needs a one-line description.")
            if not _is_toml_literal(field.default):
                raise TypeError(f"Setting {name}.{key} needs a default TOML can write.")
        if name in self._models:
            raise TypeError(f"Settings table [{name}] is registered twice.")
        self._models[name] = model

    def items(self) -> "ItemsView[str, type[BaseModel]]":
        return self._models.items()


def _is_toml_literal(value: Any) -> bool:
    if isinstance(value, list):
        return all(_is_toml_literal(item) for item in value)
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, str | bool | int)
