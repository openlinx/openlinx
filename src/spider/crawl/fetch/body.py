"""The one body reader: a response body read and decoded up to its cap (022-add-fetch-policy D1)."""

import zlib
from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Protocol

import brotli

BODY_LIMIT = 20 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Body:
    data: bytes
    # Larger than the cap, as transferred or as decoded, so not read in full.
    truncated: bool
    # The bytes read from the connection, before decoding.
    transferred_bytes: int
    # The decoded size; None for a capped body, whose full size was not measured.
    size_bytes: int | None


class _Decoder(Protocol):
    def decode(self, data: bytes, limit: int) -> bytes:
        """At most `limit` bytes of output; the rest of `data` waits for the next call."""
        ...

    def drain(self, limit: int) -> bytes:
        """At most `limit` bytes of the output still held back."""
        ...


class _Zlib:
    def __init__(self, wbits: int) -> None:
        self._raw_fallback = wbits == zlib.MAX_WBITS
        self._inflate = zlib.decompressobj(wbits)
        self._started = False

    def decode(self, data: bytes, limit: int) -> bytes:
        if not self._started and data:
            self._started = True
            # "deflate" means the zlib format, but some servers send raw deflate (design D1).
            if self._raw_fallback and not _is_zlib_header(data):
                self._inflate = zlib.decompressobj(-zlib.MAX_WBITS)
        return self._inflate.decompress(self._inflate.unconsumed_tail + data, limit)

    def drain(self, limit: int) -> bytes:
        return self._inflate.decompress(self._inflate.unconsumed_tail, limit)


class _Brotli:
    def __init__(self) -> None:
        self._inflate = brotli.Decompressor()

    def decode(self, data: bytes, limit: int) -> bytes:
        output: bytes = self._inflate.process(data, output_buffer_limit=limit)
        return output

    def drain(self, limit: int) -> bytes:
        if self._inflate.can_accept_more_data():
            return b""
        output: bytes = self._inflate.process(b"", output_buffer_limit=limit)
        return output


def _is_zlib_header(data: bytes) -> bool:
    return len(data) >= 2 and data[0] & 0x0F == 8 and (data[0] << 8 | data[1]) % 31 == 0


def _decoder(coding: str) -> _Decoder | None:
    if coding == "gzip":
        return _Zlib(16 + zlib.MAX_WBITS)
    if coding == "deflate":
        return _Zlib(zlib.MAX_WBITS)
    if coding == "br":
        return _Brotli()
    return None


async def read_body(
    chunks: AsyncIterable[bytes], coding: str | None, limit: int = BODY_LIMIT
) -> Body:
    """The body that `chunks` stream in the Content-Encoding `coding`, decoded, cut at `limit`
    bytes as transferred and as decoded; reading stops at the cap."""
    decoder = None if coding is None else _decoder(coding.strip().lower())
    parts: list[bytes] = []
    size = transferred = 0
    async for chunk in chunks:
        chunk = chunk[: limit - transferred + 1]
        transferred += len(chunk)
        output = chunk if decoder is None else decoder.decode(chunk, limit - size + 1)
        while decoder is not None and size + len(output) <= limit:
            more = decoder.drain(limit - size - len(output) + 1)
            if not more:
                break
            output += more
        if size + len(output) > limit or transferred > limit:
            parts.append(output[: limit - size])
            return Body(b"".join(parts), True, min(transferred, limit), None)
        parts.append(output)
        size += len(output)
    return Body(b"".join(parts), False, transferred, size)
