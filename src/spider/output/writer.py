"""The one Output object of an invocation (design D3 of 010-add-workspace-and-cli-contract)."""

import sys
from typing import Any

import orjson


class Output:
    # Bytes, not text: a text stream on Windows would turn the LF into CR LF.
    def text(self, text: str) -> None:
        sys.stdout.buffer.write(text.encode())

    def document(self, result: Any) -> None:
        sys.stdout.buffer.write(orjson.dumps(result) + b"\n")
