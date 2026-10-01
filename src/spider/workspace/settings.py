"""Resolved settings: spider.toml and flags (design D2 of 010-add-workspace-and-cli-contract)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, create_model
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, TomlConfigSettingsSource

from spider.workspace.discovery import Workspace
from spider.workspace.tables import SettingsTables


@dataclass(frozen=True)
class Settings:
    root: BaseSettings

    def table[M: BaseModel](self, model: type[M]) -> M:
        return next(value for value in vars(self.root).values() if isinstance(value, model))


def load_settings(workspace: Workspace, tables: SettingsTables) -> Settings:
    fields: dict[str, Any] = {name: (model, model()) for name, model in tables.items()}
    root_model = create_model(
        "SpiderSettings", __base__=_sources(workspace.settings_file), **fields
    )
    return Settings(root_model())


def _sources(settings_file: Path) -> type[BaseSettings]:
    class Root(BaseSettings):
        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            return (
                init_settings,
                env_settings,
                dotenv_settings,
                file_secret_settings,
                TomlConfigSettingsSource(settings_cls, toml_file=settings_file),
            )

    return Root
