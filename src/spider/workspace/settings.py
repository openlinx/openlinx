"""Resolved settings: spider.toml and flags (design D2 of 010-add-workspace-and-cli-contract)."""

import difflib
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ValidationError, create_model
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

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
    settings_file = workspace.settings_file
    if settings_file.exists() and not settings_file.is_file():
        raise _invalid(settings_file, "is not a file", [{"key": None, "message": "Not a file."}])
    values: dict[str, Any] = dict(flags or {})
    try:
        return Settings(root_model(**values))
    except UnicodeDecodeError as error:
        problem: dict[str, Any] = {"key": None, "message": "The file is not UTF-8.", "line": None}
        raise _invalid(settings_file, "is not UTF-8", [problem]) from error
    except tomllib.TOMLDecodeError as error:
        problem = {"key": None, "message": str(error), "line": _line(error)}
        raise _invalid(settings_file, "is not valid TOML", [problem]) from error
    except ValidationError as error:
        problems: list[dict[str, Any]] = [
            {"key": ".".join(str(part) for part in problem["loc"]), "message": problem["msg"]}
            for problem in error.errors()
        ]
        raise _invalid(
            settings_file,
            "is invalid",
            _in_file_order(problems, settings_file),
            hint=_suggestion(error, root_model),
        ) from error


def _invalid(
    settings_file: Path, what: str, errors: list[dict[str, Any]], hint: str | None = None
) -> ConfigError:
    return ConfigError(
        "settings_invalid",
        f"The settings file {settings_file} {what}.",
        hint=hint,
        details={"file": str(settings_file), "errors": errors},
    )


def _in_file_order(errors: list[dict[str, Any]], settings_file: Path) -> list[dict[str, Any]]:
    # tomllib keeps the file's order, so a key's index in the flattened document is its place.
    order = {key: index for index, key in enumerate(_dotted_keys(_read_toml(settings_file)))}

    def place(error: dict[str, Any]) -> int:
        parts = str(error["key"]).split(".")
        prefixes = (".".join(parts[:size]) for size in range(len(parts), 0, -1))
        return next((order[prefix] for prefix in prefixes if prefix in order), len(order))

    return sorted(errors, key=place)


def _read_toml(settings_file: Path) -> dict[str, Any]:
    return (
        tomllib.loads(settings_file.read_text(encoding="utf-8")) if settings_file.is_file() else {}
    )


def _dotted_keys(table: Mapping[str, Any], prefix: str = "") -> list[str]:
    keys: list[str] = []
    for key, value in table.items():
        keys.append(prefix + key)
        if isinstance(value, Mapping):
            keys += _dotted_keys(value, f"{prefix}{key}.")
    return keys


def _line(error: tomllib.TOMLDecodeError) -> int | None:
    # Python 3.14 added lineno; 3.12 and 3.13 only put it in the message.
    lineno: int | None = getattr(error, "lineno", None)
    if lineno is not None:
        return lineno
    match = re.search(r"at line (\d+)", str(error))
    return int(match.group(1)) if match else None


def _suggestion(error: ValidationError, root_model: type[BaseModel]) -> str | None:
    for problem in error.errors():
        if problem["type"] != "extra_forbidden":
            continue
        *parents, unknown = (str(part) for part in problem["loc"])
        model = root_model
        for part in parents:
            # Every table, and every nested level of one, is a registered BaseModel.
            model = cast(type[BaseModel], model.model_fields[part].annotation)
        matches = difflib.get_close_matches(unknown, list(model.model_fields), n=1)
        if matches:
            return f"Did you mean {'.'.join([*parents, matches[0]])}?"
    return None


def _sources(settings_file: Path) -> type[BaseSettings]:
    class Root(BaseSettings):
        model_config = SettingsConfigDict(extra="forbid")

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
