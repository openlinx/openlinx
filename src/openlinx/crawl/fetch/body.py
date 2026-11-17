"""Read and decode response bodies within the configured size cap."""

import sys
import zlib
from collections.abc import AsyncIterable, Sequence
from dataclasses import dataclass
from typing import Protocol

import brotli

if sys.version_info >= (3, 14):
    from compression import zstd
else:
    from backports import zstd

BODY_LIMIT = 20 * 1024 * 1024
# Decoder capabilities do not depend on a request's Accept-Encoding preference.
SUPPORTED_CODINGS = ("gzip", "deflate", "br", "zstd")
_GZIP_MAGIC = b"\x1f\x8b"


class BodyDecodingError(ValueError):
    """A body that is not in the coding its Content-Encoding names, or that ends inside it."""


@dataclass(frozen=True, slots=True)
class Body:
    # Decoded, unless its coding is unsupported: then as received.
    data: bytes
    # Larger than the cap, as transferred or as decoded, so not read in full.
    truncated: bool
    # The bytes read from the connection, before decoding.
    transferred_bytes: int


class _Decoder(Protocol):
    def decode(self, data: bytes, limit: int) -> bytes:
        """At most `limit` bytes of output; the rest of `data` waits for the next call."""
        ...

    def drain(self, limit: int) -> bytes:
        """At most `limit` bytes of the output still held back."""
        ...

    def finished(self) -> bool: ...


class _Zlib:
    def __init__(self, wbits: int, *, raw_fallback: bool = False) -> None:
        self._wbits = wbits
        self._raw_fallback = raw_fallback
        self._inflate = zlib.decompressobj(wbits)
        self._trailing_junk = False
        # The first bytes, until two have arrived to tell the zlib format from raw deflate.
        self._head: bytes | None = b"" if raw_fallback else None

    def decode(self, data: bytes, limit: int) -> bytes:
        if self._head is not None:
            data = self._head + data
            if len(data) < 2:
                self._head = data
                return b""
            self._head = None
            # Some servers send raw deflate instead of the zlib format (022-add-fetch-policy D1).
            if not _is_zlib_header(data):
                self._inflate = zlib.decompressobj(-zlib.MAX_WBITS)
        if self._inflate.eof:
            return self._next_member(data, limit)
        return self._inflate.decompress(self._inflate.unconsumed_tail + data, limit)

    def drain(self, limit: int) -> bytes:
        if self._inflate.eof:
            return self._next_member(b"", limit)
        return self._inflate.decompress(self._inflate.unconsumed_tail, limit)

    def finished(self) -> bool:
        return self._head is None and self._inflate.eof

    def _next_member(self, data: bytes, limit: int) -> bytes:
        if self._trailing_junk:
            return b""
        rest = self._inflate.unused_data + data
        if self._wbits == 16 + zlib.MAX_WBITS and rest == _GZIP_MAGIC[:1]:
            # Keep the lone prefix in unused_data until another read completes the magic.
            return self._inflate.decompress(data, limit)
        # A gzip body may hold several members, as gunzip reads them; other bytes after the
        # stream are ignored, as browsers ignore them.
        if self._wbits != 16 + zlib.MAX_WBITS or not rest.startswith(_GZIP_MAGIC):
            # A later chunk cannot restart decoding after trailing junk was rejected.
            self._trailing_junk = bool(rest)
            return b""
        self._inflate = zlib.decompressobj(self._wbits)
        return self._inflate.decompress(rest, limit)


class _Brotli:
    def __init__(self) -> None:
        self._inflate = brotli.Decompressor()

    def decode(self, data: bytes, limit: int) -> bytes:
        # Bytes after the stream are ignored, as gzip's are; brotli would refuse them.
        if self._inflate.is_finished():
            return b""
        output: bytes = self._inflate.process(data, output_buffer_limit=limit)
        return output

    def drain(self, limit: int) -> bytes:
        if self._inflate.is_finished() or self._inflate.can_accept_more_data():
            return b""
        output: bytes = self._inflate.process(b"", output_buffer_limit=limit)
        return output

    def finished(self) -> bool:
        finished: bool = self._inflate.is_finished()
        return finished


class _Zstd:
    def __init__(self) -> None:
        # RFC 9659 limits an HTTP zstd window to 8 MiB independently of its output size.
        self._inflate = zstd.ZstdDecompressor(
            options={zstd.DecompressionParameter.window_log_max: 23}
        )

    def decode(self, data: bytes, limit: int) -> bytes:
        if self._inflate.eof:
            if data:
                raise BodyDecodingError("The body contains data after its zstd frame.")
            return b""
        output = self._inflate.decompress(data, max_length=limit)
        if self._inflate.unused_data:
            raise BodyDecodingError("The body contains data after its zstd frame.")
        return output

    def drain(self, limit: int) -> bytes:
        if self._inflate.eof or self._inflate.needs_input:
            return b""
        return self.decode(b"", limit)

    def finished(self) -> bool:
        return self._inflate.eof


class _Chain:
    """Several codings, decoded in the reverse order of the Content-Encoding (RFC 9110 8.4.1)."""

    def __init__(self, stages: Sequence[_Decoder], body_limit: int) -> None:
        self._stages = stages
        self._remaining = [body_limit] * (len(stages) - 1)
        self.truncated = False

    def decode(self, data: bytes, limit: int) -> bytes:
        return self._through(0, data, limit)

    def drain(self, limit: int) -> bytes:
        # Until a whole pass finds nothing held: a held piece, such as part of a trailer, may
        # give no output of its own while an earlier stage still holds more.
        while not self.truncated:
            # The stage nearest the output first, so no stage takes input while it holds output.
            for index in reversed(range(len(self._stages))):
                held = self._stages[index].drain(self._stage_limit(index, limit))
                held = self._account(index, held)
                if held:
                    output = self._through(index + 1, held, limit)
                    if output:
                        return output
                    break
            else:
                return b""
        return b""

    def finished(self) -> bool:
        return all(stage.finished() for stage in self._stages)

    def _through(self, start: int, data: bytes, limit: int) -> bytes:
        for index in range(start, len(self._stages)):
            data = self._stages[index].decode(data, self._stage_limit(index, limit))
            data = self._account(index, data)
        return data

    def _stage_limit(self, index: int, limit: int) -> int:
        if index == len(self._remaining):
            return limit
        return min(limit, self._remaining[index] + 1)

    def _account(self, index: int, data: bytes) -> bytes:
        # The body reader accounts for the final stage. Earlier stages can exceed the
        # cap even when a later stage returns little or no output.
        if index == len(self._remaining):
            return data
        remaining = self._remaining[index]
        self._remaining[index] -= min(len(data), remaining)
        if len(data) > remaining:
            self.truncated = True
        return data[:remaining]


def _is_zlib_header(data: bytes) -> bool:
    return data[0] & 0x0F == 8 and (data[0] << 8 | data[1]) % 31 == 0


def codings(content_encoding: str | None) -> list[str]:
    """The codings of a Content-Encoding header, in the order the server applied them."""
    if content_encoding is None:
        return []
    found = (coding.strip().lower() for coding in content_encoding.split(","))
    return [coding for coding in found if coding and coding != "identity"]


def is_decodable(content_encoding: str | None) -> bool:
    return all(coding in SUPPORTED_CODINGS for coding in codings(content_encoding))


def _decoder(content_encoding: str | None, limit: int) -> _Chain | None:
    stages: list[_Decoder] = []
    for coding in reversed(codings(content_encoding)):
        if coding == "gzip":
            stages.append(_Zlib(16 + zlib.MAX_WBITS))
        elif coding == "deflate":
            stages.append(_Zlib(zlib.MAX_WBITS, raw_fallback=True))
        elif coding == "zstd":
            stages.append(_Zstd())
        else:
            stages.append(_Brotli())
    return _Chain(stages, limit) if stages else None


async def read_body(
    chunks: AsyncIterable[bytes], coding: str | None, limit: int = BODY_LIMIT
) -> Body:
    """The body that `chunks` stream in the Content-Encoding `coding`, decoded, cut at `limit`
    bytes as transferred and at each decoding stage; reading stops at the cap. An unsupported
    coding is kept as received; BodyDecodingError for one that fails to decode."""
    decoder = _decoder(coding, limit) if is_decodable(coding) else None
    parts: list[bytes] = []
    size = transferred = 0
    try:
        async for chunk in chunks:
            transferred += len(chunk)
            # One byte past the cap is enough to know the body is larger.
            chunk = chunk[: limit + 1 - (transferred - len(chunk))]
            output = chunk if decoder is None else decoder.decode(chunk, limit - size + 1)
            while decoder is not None and not decoder.truncated and size + len(output) <= limit:
                more = decoder.drain(limit - size - len(output) + 1)
                if not more:
                    break
                output += more
            if size + len(output) > limit or transferred > limit or (decoder and decoder.truncated):
                parts.append(output[: limit - size])
                return Body(b"".join(parts), True, transferred)
            parts.append(output)
            size += len(output)
    except (zlib.error, brotli.error, zstd.ZstdError) as error:
        raise BodyDecodingError(f"The body is not valid {coding}: {error}") from error
    # An empty body, as a redirect may send under the header, holds no stream to end.
    if decoder is not None and transferred and not decoder.finished():
        raise BodyDecodingError(f"The body ends inside its {coding} stream.")
    return Body(b"".join(parts), False, transferred)
