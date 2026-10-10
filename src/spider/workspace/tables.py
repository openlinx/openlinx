"""The registry of settings tables (design D2 of 010-add-workspace-and-cli-contract)."""

import importlib
import math
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, cast, get_args, get_origin

if TYPE_CHECKING:
    # Only for typing: pydantic must stay off the CLI's startup path.
    from pydantic import BaseModel

# A table model, or a keyed table: dict[str, V] whose V is a table model.
type Table = type[BaseModel] | type[dict[str, Any]]


class SettingsTables:
    def __init__(self) -> None:
        # "module:Class" references: a table's module, and pydantic, load only with the settings.
        self._references: dict[str, str] = {}

    def register(self, name: str, reference: str) -> None:
        if name in self._references:
            raise TypeError(f"Settings table [{name}] is registered twice.")
        self._references[name] = reference

    def items(self) -> Iterator[tuple[str, Table]]:
        for name, reference in self._references.items():
            yield name, _resolve(reference)

    def is_secret(self, setting: str) -> bool:
        # Declared once, on the settings field (json_schema_extra), so redaction reads it too.
        name, _, key = setting.partition(".")
        model: Any = _resolve(self._references[name])
        extra = model.model_fields[key].json_schema_extra
        return isinstance(extra, dict) and extra.get("secret") is True

    def secret_settings(self) -> frozenset[str]:
        return frozenset(
            f"{name}.{key}"
            for name, table in self.items()
            if keyed_entry(table) is None
            for key in cast(Any, table).model_fields
            if self.is_secret(f"{name}.{key}")
        )


def _resolve(reference: str) -> Table:
    module, _, attribute = reference.partition(":")
    table: Table = getattr(importlib.import_module(module), attribute)
    return table


def keyed_entry(table: Any) -> Any:
    """The entry type of a keyed table, or None for a table model."""
    if get_origin(table) is not dict:
        return None
    key, entry = get_args(table)
    if key is not str:
        raise TypeError(f"A keyed settings table needs str keys, not {key}.")
    return entry


def check_table(name: str, table: Table) -> None:
    """Raises TypeError unless the table follows the table rules of design D2."""
    entry = keyed_entry(table)
    if entry is None:
        _check_model(name, table)
    else:
        # Literal entries (`<name> = <value>`) have no docstring to describe the table in the
        # template, so they wait for the change that needs them (050's [segments]).
        if not isinstance(entry, type) or not hasattr(entry, "model_fields"):
            raise TypeError(f"Settings table [{name}] needs a table model for its entries.")
        _check_model(f"{name}.<name>", entry)
        # The template describes the keyed table with it.
        if not entry.__doc__ or "\n" in entry.__doc__:
            raise TypeError(f"Settings table [{name}] needs a one-line entry docstring.")


def _check_model(name: str, model: Any) -> None:
    # The template and the error hints rely on flat tables whose keys all have a
    # one-line description and a default that is a TOML literal, or None for unset.
    if getattr(model, "model_config", {}).get("extra") != "forbid":
        raise TypeError(f'Settings table [{name}] must set extra="forbid".')
    for key, field in model.model_fields.items():
        if not field.description or "\n" in field.description:
            raise TypeError(f"Setting {name}.{key} needs a one-line description.")
        if field.default is not None and not _is_toml_literal(field.default):
            raise TypeError(f"Setting {name}.{key} needs a default TOML can write.")


def _is_toml_literal(value: Any) -> bool:
    if isinstance(value, list):
        return all(_is_toml_literal(item) for item in value)
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, str | bool | int)
