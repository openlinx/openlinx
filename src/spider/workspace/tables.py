"""The registry of spider.toml tables (design D2 of 010-add-workspace-and-cli-contract)."""

import math
from collections.abc import ItemsView
from typing import TYPE_CHECKING, Any, get_args, get_origin

if TYPE_CHECKING:
    # Only for typing: pydantic must stay off the CLI's startup path.
    from pydantic import BaseModel

# A table model, or a keyed table: dict[str, V] whose V is a table model or a TOML literal type.
type Table = type[BaseModel] | type[dict[str, Any]]

TOML_LITERAL_TYPES = (str, int, float, bool)


class SettingsTables:
    def __init__(self) -> None:
        self._tables: dict[str, Table] = {}

    def register(self, name: str, table: Table) -> None:
        entry = keyed_entry(table)
        if entry is None:
            _check_model(name, table)
        elif entry not in TOML_LITERAL_TYPES:
            _check_model(f"{name}.<name>", entry)
            # The template describes the keyed table with it.
            if not entry.__doc__ or "\n" in entry.__doc__:
                raise TypeError(f"Settings table [{name}] needs a one-line entry docstring.")
        if name in self._tables:
            raise TypeError(f"Settings table [{name}] is registered twice.")
        self._tables[name] = table

    def items(self) -> "ItemsView[str, Table]":
        return self._tables.items()


def keyed_entry(table: Any) -> Any:
    """The entry type of a keyed table, or None for a table model."""
    if get_origin(table) is not dict:
        return None
    key, entry = get_args(table)
    if key is not str:
        raise TypeError(f"A keyed settings table needs str keys, not {key}.")
    return entry


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
