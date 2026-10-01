"""The byte sinks every output goes through (design D3 of 010-add-workspace-and-cli-contract)."""

import sys


def write_stdout(data: bytes) -> None:
    # Bytes, not text: a text stream on Windows would turn the LF into CR LF.
    sys.stdout.buffer.write(data)
