"""Render result items as tables for people."""

import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from openlinx.json_numbers import encode_json


def render_table(document: Mapping[str, Any], width: int) -> str:
    return _render(["key", "value"], [[key, value] for key, value in document.items()], width)


def render_items_table(items: Sequence[Mapping[str, Any]], width: int) -> str:
    return _render_items(items, width)


@dataclass(frozen=True, slots=True)
class TitledTables:
    """A document presented as a sequence of named tables."""

    sections: Sequence[tuple[str, Sequence[Mapping[str, Any]]]]

    def render(self, width: int) -> str:
        return "\n".join(
            _render_items(items, width, title=title) for title, items in self.sections if items
        )


def _render_items(
    items: Sequence[Mapping[str, Any]], width: int, *, title: str | None = None
) -> str:
    columns = list(items[0]) if items else []
    rows = [[item[column] for column in columns] for item in items]
    return _render(columns, rows, width, title=title)


def _render(
    columns: Sequence[str], rows: Sequence[Sequence[Any]], width: int, *, title: str | None = None
) -> str:
    # Imported here: rich is too heavy for the CLI's startup path.
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text

    table = Table(title=Text(title) if title is not None else None)
    for column in columns:
        table.add_column(Text(column), overflow="fold")
    for row in rows:
        table.add_row(*(Text(_cell(value)) for value in row))
    text = io.StringIO()
    Console(file=text, width=width, color_system=None, legacy_windows=False).print(table)
    return text.getvalue()


def _cell(value: Any) -> str:
    return value if isinstance(value, str) else encode_json(value).decode()
