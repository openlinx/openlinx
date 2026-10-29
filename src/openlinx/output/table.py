"""The table format, for people (design D3 of 010-add-workspace-and-cli-contract)."""

import io
from collections.abc import Mapping, Sequence
from typing import Any

import orjson


def render_table(document: Mapping[str, Any], width: int) -> str:
    return _render(["key", "value"], [[key, value] for key, value in document.items()], width)


def render_items_table(items: Sequence[Mapping[str, Any]], width: int) -> str:
    columns = list(items[0]) if items else []
    return _render(columns, [[item[column] for column in columns] for item in items], width)


def _render(columns: Sequence[str], rows: Sequence[Sequence[Any]], width: int) -> str:
    # Imported here: rich is too heavy for the CLI's startup path.
    from rich.console import Console
    from rich.table import Table

    table = Table()
    for column in columns:
        table.add_column(column, overflow="fold")
    for row in rows:
        table.add_row(*(_cell(value) for value in row))
    text = io.StringIO()
    Console(file=text, width=width, color_system=None, legacy_windows=False).print(table)
    return text.getvalue()


def _cell(value: Any) -> str:
    return value if isinstance(value, str) else orjson.dumps(value).decode()
