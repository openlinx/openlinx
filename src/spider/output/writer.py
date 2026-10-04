"""The one Output object of an invocation (design D3 of 010-add-workspace-and-cli-contract)."""

import shutil
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, BinaryIO, Literal

import orjson

from spider.output.diagnostics import Diagnostic
from spider.output.table import render_items_table, render_table

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
    kind: Literal["document", "list"]
    notice: Diagnostic | None = None


@dataclass(frozen=True)
class Rows:
    rows: Iterable[Mapping[str, Any]]
    format: Format


class Output:
    # Bytes, not text: a text stream on Windows would turn the LF into CR LF.
    def __init__(self, stdout: BinaryIO, stderr: BinaryIO) -> None:
        self._stdout = stdout
        self._stderr = stderr

    def text(self, text: str) -> None:
        self._stdout.write(text.encode())

    def document(self, document: Document) -> None:
        if document.format is Format.JSONL:
            for item in document.value["items"]:
                self._stdout.write(_json_line(item))
        elif document.format is Format.TABLE:
            width = shutil.get_terminal_size().columns if self._stdout.isatty() else TABLE_WIDTH
            if document.kind == "list":
                text = render_items_table(document.value["items"], width)
            else:
                text = render_table(document.value, width)
            self._stdout.write(text.encode())
        else:
            self._stdout.write(_json_line(document.value))

    def rows(self, rows: Rows) -> None:
        for row in rows.rows:
            self._stdout.write(_json_line(row))
            # Each row as it is made: a reader sees it before the next one exists.
            self._stdout.flush()

    def diagnostic(self, diagnostic: Diagnostic) -> None:
        self.stderr_line(_json_line(asdict(diagnostic)))

    def stderr_line(self, line: bytes) -> None:
        self._stderr.write(line)


def _json_line(value: Any) -> bytes:
    return orjson.dumps(value) + b"\n"
