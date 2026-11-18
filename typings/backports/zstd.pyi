"""Type the incremental backport API used by the Fetcher from any development Python."""

from collections.abc import Mapping
from enum import IntEnum
from typing import Self, final

from _typeshed import ReadableBuffer

@final
class DecompressionParameter(IntEnum):
    window_log_max = ...

class ZstdError(Exception): ...

@final
class ZstdDecompressor:
    def __new__(cls, *, options: Mapping[int, int] | None = None) -> Self: ...
    def decompress(self, /, data: ReadableBuffer, max_length: int = -1) -> bytes: ...
    @property
    def eof(self) -> bool: ...
    @property
    def needs_input(self) -> bool: ...
    @property
    def unused_data(self) -> bytes: ...
