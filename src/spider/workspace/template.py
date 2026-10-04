"""The commented spider.toml that init writes (design D2 of 010-add-workspace-and-cli-contract)."""

import json
from typing import Any

from spider import APP_NAME
from spider.workspace.discovery import SETTINGS_FILE_NAME
from spider.workspace.tables import SettingsTables

HEADER = (
    f"# {APP_NAME} settings. Each setting takes the first value it finds:\n"
    f"# its flag, then this file ({SETTINGS_FILE_NAME}), then its default.\n"
    "# Every setting below is commented out, so its default applies.\n"
)


def settings_template(tables: SettingsTables) -> str:
    parts = [HEADER]
    for name, model in tables.items():
        lines = [f"[{name}]"]
        for key, field in model.model_fields.items():
            lines.append(f"# {field.description}")
            if field.default is None:
                lines.append(f"# {key} =")
            else:
                lines.append(f"# {key} = {_toml_literal(field.default)}")
        parts.append("\n".join(lines) + "\n")
    return "\n".join(parts)


def _toml_literal(value: Any) -> str:
    # JSON strings, numbers, booleans and arrays are valid TOML literals too.
    return json.dumps(value, ensure_ascii=False)
