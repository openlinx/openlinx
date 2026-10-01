"""The table format, for people (design D3 of 010-add-workspace-and-cli-contract)."""

import io
from collections.abc import Mapping
from typing import Any

import orjson


def render_table(value: Mapping[str, Any], width: int) -> str:
    # Imported here: rich is too heavy for the CLI's startup path.
    from rich.console import Console
    from rich.table import Table

    table = Table("key")
    table.add_column("value", overflow="fold")
    for key, cell in value.items():
        table.add_row(key, _cell(cell))
    text = io.StringIO()
    Console(file=text, width=width, color_system=None, legacy_windows=False).print(table)
    return text.getvalue()


def _cell(value: Any) -> str:
    return value if isinstance(value, str) else orjson.dumps(value).decode()
