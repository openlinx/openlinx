"""The commented settings file init writes (design D2 of 010-add-workspace-and-cli-contract)."""

import json
from typing import Any

from spider.naming import APP_NAME, SETTINGS_FILE_NAME
from spider.workspace.tables import SettingsTables, keyed_entry, table_kind

HEADER = (
    f"# {APP_NAME} settings. Each setting takes the first value it finds:\n"
    f"# its flag, then this file ({SETTINGS_FILE_NAME}), then its default.\n"
    "# Every setting below is commented out, so its default applies.\n"
)


def settings_template(tables: SettingsTables) -> str:
    parts = [HEADER]
    for name, table in tables.items():
        kind = table_kind(table)
        if kind == "named":
            # Each named table has settings of its own, which its docstring points to.
            lines = [f"# {table.__doc__}", f"# [{name}.<name>]"]
        elif kind == "plain":
            lines = [f"[{name}]", *_settings(table)]
        else:
            # No entry exists until the user names one, so even the header stays a comment.
            entry = keyed_entry(table)
            lines = [f"# {entry.__doc__}", f"# [{name}.<name>]", *_settings(entry)]
        parts.append("\n".join(lines) + "\n")
    return "\n".join(parts)


def _settings(model: Any) -> list[str]:
    lines = []
    for key, field in model.model_fields.items():
        lines.append(f"# {field.description}")
        if field.default is None:
            lines.append(f"# {key} =")
        else:
            lines.append(f"# {key} = {_toml_literal(field.default)}")
    return lines


def _toml_literal(value: Any) -> str:
    # JSON strings, numbers, booleans and arrays are valid TOML literals too.
    return json.dumps(value, ensure_ascii=False)
