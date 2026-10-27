"""The one body reader: a response body read and decoded up to its cap (022-add-fetch-policy D1)."""

import zlib
from collections.abc import AsyncIterable, Sequence
from dataclasses import dataclass
from typing import Protocol

import brotli

BODY_LIMIT = 20 * 1024 * 1024
# The codings every request offers, and the only ones decoded.
OFFERED_CODINGS = ("gzip", "deflate", "br")


class BodyDecodingError(ValueError):
    """A body that is not in the coding its Content-Encoding names, or that ends inside it."""


@dataclass(frozen=True, slots=True)
class Body:
    data: bytes
    # Larger than the cap, as transferred or as decoded, so not read in full.
    truncated: bool
    # The bytes read from the connection, before decoding.
    transferred_bytes: int
    # The decoded size; None for a capped body, whose full size was not measured, or for a body
    # in a coding that was not offered, which is kept as received.
    size_bytes: int | None


class _Decoder(Protocol):
    def decode(self, data: bytes, limit: int) -> bytes:
        """At most `limit` bytes of output; the rest of `data` waits for the next call."""
        ...

    def drain(self, limit: int) -> bytes:
        """At most `limit` bytes of the output still held back."""
        ...

    def finished(self) -> bool: ...


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

    def finished(self) -> bool:
        return self._inflate.eof


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

    def finished(self) -> bool:
        finished: bool = self._inflate.is_finished()
        return finished


class _Chain:
    """Several codings, decoded in the reverse order of the Content-Encoding (RFC 9110 8.4.1)."""

    def __init__(self, stages: Sequence[_Decoder]) -> None:
        self._stages = stages

    def decode(self, data: bytes, limit: int) -> bytes:
        return self._through(0, data, limit)

    def drain(self, limit: int) -> bytes:
        # The stage nearest the output first, so no stage takes input while it holds output.
        for index in reversed(range(len(self._stages))):
            held = self._stages[index].drain(limit)
            if held:
                return self._through(index + 1, held, limit)
        return b""

    def finished(self) -> bool:
        return all(stage.finished() for stage in self._stages)

    def _through(self, start: int, data: bytes, limit: int) -> bytes:
        for stage in self._stages[start:]:
            data = stage.decode(data, limit)
        return data


def _is_zlib_header(data: bytes) -> bool:
    return len(data) >= 2 and data[0] & 0x0F == 8 and (data[0] << 8 | data[1]) % 31 == 0


def codings(content_encoding: str | None) -> list[str]:
    """The codings of a Content-Encoding header, in the order the server applied them."""
    if content_encoding is None:
        return []
    found = (coding.strip().lower() for coding in content_encoding.split(","))
    return [coding for coding in found if coding and coding != "identity"]


def is_decodable(content_encoding: str | None) -> bool:
    return all(coding in OFFERED_CODINGS for coding in codings(content_encoding))


def _decoder(content_encoding: str | None) -> _Decoder | None:
    stages: list[_Decoder] = []
    for coding in reversed(codings(content_encoding)):
        if coding == "gzip":
            stages.append(_Zlib(16 + zlib.MAX_WBITS))
        elif coding == "deflate":
            stages.append(_Zlib(zlib.MAX_WBITS))
        else:
            stages.append(_Brotli())
    return _Chain(stages) if stages else None


async def read_body(
    chunks: AsyncIterable[bytes], coding: str | None, limit: int = BODY_LIMIT
) -> Body:
    """The body that `chunks` stream in the Content-Encoding `coding`, decoded, cut at `limit`
    bytes as transferred and as decoded; reading stops at the cap. A coding that was not
    offered is kept as received; BodyDecodingError for one that fails to decode."""
    decodable = is_decodable(coding)
    decoder = _decoder(coding) if decodable else None
    parts: list[bytes] = []
    size = transferred = 0
    try:
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
    except (zlib.error, brotli.error) as error:
        raise BodyDecodingError(f"The body is not valid {coding}: {error}") from error
    # An empty body, as a redirect may send under the header, holds no stream to end.
    if decoder is not None and transferred and not decoder.finished():
        raise BodyDecodingError(f"The body ends inside its {coding} stream.")
    return Body(b"".join(parts), False, transferred, size if decodable else None)
