"""The one Output object of an invocation (design D3 of 010-add-workspace-and-cli-contract)."""

import shutil
import sys
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


class Output:
    # Bytes, not text: a text stream on Windows would turn the LF into CR LF.
    def text(self, text: str) -> None:
        sys.stdout.buffer.write(text.encode())

    def document(self, document: Document) -> None:
        if document.format is Format.TABLE:
            width = shutil.get_terminal_size().columns if sys.stdout.isatty() else TABLE_WIDTH
            sys.stdout.buffer.write(render_table(document.value, width).encode())
        else:
            sys.stdout.buffer.write(_json_line(document.value))

    def diagnostic(self, diagnostic: Diagnostic) -> None:
        sys.stderr.buffer.write(_json_line(asdict(diagnostic)))


def _json_line(value: Any) -> bytes:
    return orjson.dumps(value) + b"\n"
