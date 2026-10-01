"""The registry of spider.toml tables (design D2 of 010-add-workspace-and-cli-contract)."""

from collections.abc import ItemsView
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Only for typing: pydantic must stay off the CLI's startup path.
    from pydantic import BaseModel


class SettingsTables:
    def __init__(self) -> None:
        self._models: dict[str, type[BaseModel]] = {}

    def register(self, name: str, model: "type[BaseModel]") -> None:
        self._models[name] = model

    def items(self) -> "ItemsView[str, type[BaseModel]]":
        return self._models.items()
