"""Resolved settings: spider.toml and flags (design D2 of 010-add-workspace-and-cli-contract)."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError, create_model
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, TomlConfigSettingsSource

from spider.output.diagnostics import ConfigError
from spider.workspace.discovery import Workspace
from spider.workspace.tables import SettingsTables


@dataclass(frozen=True)
class Settings:
    root: BaseSettings

    def table[M: BaseModel](self, model: type[M]) -> M:
        return next(value for value in vars(self.root).values() if isinstance(value, model))


def load_settings(
    workspace: Workspace,
    tables: SettingsTables,
    flags: Mapping[str, Mapping[str, Any]] | None = None,
) -> Settings:
    fields: dict[str, Any] = {name: (model, model()) for name, model in tables.items()}
    root_model = create_model(
        "SpiderSettings", __base__=_sources(workspace.settings_file), **fields
    )
    values: dict[str, Any] = dict(flags or {})
    try:
        return Settings(root_model(**values))
    except ValidationError as error:
        raise ConfigError(
            "settings_invalid",
            f"The settings file {workspace.settings_file} is invalid.",
            details={
                "file": str(workspace.settings_file),
                "errors": [
                    {
                        "key": ".".join(str(part) for part in problem["loc"]),
                        "message": problem["msg"],
                    }
                    for problem in error.errors()
                ],
            },
        ) from error


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
            # No env, .env or secrets source: settings come only from flags and spider.toml.
            return (init_settings, TomlConfigSettingsSource(settings_cls, toml_file=settings_file))

    return Root
