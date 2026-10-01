"""The one Output object of an invocation (design D3 of 010-add-workspace-and-cli-contract)."""

import sys
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

import orjson

from spider.output.diagnostics import Diagnostic


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
        sys.stdout.buffer.write(_json_line(document.value))

    def diagnostic(self, diagnostic: Diagnostic) -> None:
        sys.stderr.buffer.write(_json_line(asdict(diagnostic)))


def _json_line(value: Any) -> bytes:
    return orjson.dumps(value) + b"\n"
