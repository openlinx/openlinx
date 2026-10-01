"""Resolved settings: spider.toml and flags (design D2 of 010-add-workspace-and-cli-contract)."""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, create_model
from pydantic_settings import BaseSettings

from spider.workspace.discovery import Workspace
from spider.workspace.tables import SettingsTables


@dataclass(frozen=True)
class Settings:
    root: BaseSettings

    def table[M: BaseModel](self, model: type[M]) -> M:
        return next(value for value in vars(self.root).values() if isinstance(value, model))


def load_settings(workspace: Workspace, tables: SettingsTables) -> Settings:
    fields: dict[str, Any] = {name: (model, model()) for name, model in tables.items()}
    root_model = create_model("SpiderSettings", __base__=BaseSettings, **fields)
    return Settings(root_model())
