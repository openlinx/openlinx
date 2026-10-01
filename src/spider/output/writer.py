"""The one Output object of an invocation (design D3 of 010-add-workspace-and-cli-contract)."""

import shutil
import sys
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

import orjson

from spider.output.diagnostics import Diagnostic
from spider.output.table import render_table

# Not a terminal: a fixed width, so the table is the same on every OS and in CI.
TABLE_WIDTH = 120


class Format(StrEnum):
    JSON = "json"
    JSONL = "jsonl"
    TABLE = "table"


@dataclass(frozen=True)
class Document:
    value: Any
    format: Format


@dataclass(frozen=True)
class Rows:
    rows: Iterable[Mapping[str, Any]]
    format: Format


class Output:
    # Bytes, not text: a text stream on Windows would turn the LF into CR LF.
    def text(self, text: str) -> None:
        sys.stdout.buffer.write(text.encode())

    def document(self, document: Document) -> None:
        if document.format is Format.JSONL:
            # Only list Commands offer jsonl, so the value is the paging envelope.
            for item in document.value["items"]:
                sys.stdout.buffer.write(_json_line(item))
        elif document.format is Format.TABLE:
            width = shutil.get_terminal_size().columns if sys.stdout.isatty() else TABLE_WIDTH
            sys.stdout.buffer.write(render_table(document.value, width).encode())
        else:
            sys.stdout.buffer.write(_json_line(document.value))

    def rows(self, rows: Rows) -> None:
        for row in rows.rows:
            sys.stdout.buffer.write(_json_line(row))
            # Each row as it is made: a reader sees it before the next one exists.
            sys.stdout.buffer.flush()

    def diagnostic(self, diagnostic: Diagnostic) -> None:
        sys.stderr.buffer.write(_json_line(asdict(diagnostic)))


def _json_line(value: Any) -> bytes:
    return orjson.dumps(value) + b"\n"
